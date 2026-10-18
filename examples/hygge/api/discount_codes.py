# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Discount codes: the assistant's mirror of the codes an operator creates by hand in the
idobooking panel.

idobooking has no API for codes. A code is created there, copied here with the same
spelling and the same windows, and the assistant decides when to mention it; the guest
types it into the booking form, where idobooking prices it. So a record holds two kinds of
fields: the ones that must match the panel (``code``, ``discount_label``, the stay window,
the validity window) and the ones only the assistant reads (when to propose the code and
how to word it). ``discount_label`` is wording, never a number the assistant computes with.

``eligible_codes`` is the one rule: which codes a stay earns, given what the conversation
has shown. ``OfferDesk`` runs it per session, keeps the per-session cap, records the two
events a deployment counts (``offer_proposed``, ``offer_handoff``), and hands the code the
checkout card carries. ``DiscountCodeStore`` keeps the records in memory; with
``DATABASE_URL`` set, ``PostgresDiscountCodeStore`` keeps them in the same Postgres the
event log writes to, so a deploy does not lose them.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger("hygge.discount_codes")

# The signals a conversation can carry; the tool's schema lists the same three.
RETURNING_GUEST = "returning_guest"
PRICE_HESITATION = "price_hesitation"
ASKED_FOR_DISCOUNT = "asked_for_discount"
CONVERSATION_SIGNALS = frozenset({RETURNING_GUEST, PRICE_HESITATION, ASKED_FOR_DISCOUNT})

# How many codes one call may name; two is a choice, more is a price list.
MAX_OFFERS = 2

_CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{1,39}$")
_LIST_PATTERN = re.compile(r"^\[?([^\]]*)\]?$")


# ---------------------------------------------------------------------------
# Trigger signals
# ---------------------------------------------------------------------------


def parse_trigger(signal: str) -> tuple[str, Any]:
    """One entry of ``trigger_signals`` as ``(kind, value)``. Raises ``ValueError`` on
    anything outside the closed set: ``lead_days_max:N``, ``weekdays:[1-7]``,
    ``min_nights:N``, ``cabins:[ids]``, and the three conversation signals."""
    text = signal.strip()
    if text in CONVERSATION_SIGNALS:
        return text, None
    kind, separator, raw = text.partition(":")
    kind = kind.strip()
    if not separator:
        raise ValueError(f"unknown trigger signal {signal!r}")
    raw = raw.strip()
    if kind in ("lead_days_max", "min_nights"):
        try:
            value = int(raw)
        except ValueError:
            raise ValueError(f"{kind} needs a whole number, got {raw!r}") from None
        if value < 0:
            raise ValueError(f"{kind} cannot be negative")
        return kind, value
    if kind == "weekdays":
        match = _LIST_PATTERN.match(raw)
        items = [part.strip() for part in (match.group(1) if match else "").split(",")]
        try:
            days = {int(part) for part in items if part}
        except ValueError:
            raise ValueError(f"weekdays needs numbers 1-7, got {raw!r}") from None
        if not days or any(day < 1 or day > 7 for day in days):
            raise ValueError(f"weekdays needs numbers 1-7, got {raw!r}")
        return kind, days
    if kind == "cabins":
        match = _LIST_PATTERN.match(raw)
        ids = {
            part.strip().strip("'\"")
            for part in (match.group(1) if match else "").split(",")
            if part.strip()
        }
        if not ids:
            raise ValueError("cabins needs at least one cabin id")
        return kind, ids
    raise ValueError(f"unknown trigger signal {signal!r}")


def normalize_trigger(signal: str) -> str:
    """The canonical spelling of a trigger, so two operators write the same list."""
    kind, value = parse_trigger(signal)
    if value is None:
        return kind
    if isinstance(value, set):
        items = sorted((str(item) for item in value), key=lambda item: (len(item), item))
        return f"{kind}:[{','.join(items)}]"
    return f"{kind}:{value}"


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


class DiscountCodeDraft(BaseModel):
    """What an operator edits. The first block mirrors the idobooking panel one to one;
    the second is the assistant's own."""

    code: str = Field(min_length=2, max_length=40)
    discount_label: str = Field(min_length=1, max_length=60)
    stay_from: date | None = None
    stay_to: date | None = None
    valid_from: date | None = None
    valid_to: date | None = None

    active: bool = True
    # True: may open a conversation and sit on the home panel; False: only after a signal.
    announceable: bool = False
    trigger_signals: list[str] = Field(default_factory=list, max_length=12)
    # Lower is proposed earlier.
    priority: int = Field(default=100, ge=0, le=10_000)
    max_per_session: int = Field(default=1, ge=1, le=20)
    # One sentence on how to sell it; never shown to the guest as is.
    notes_for_agent: str = Field(default="", max_length=300)

    @field_validator("code", mode="before")
    @classmethod
    def _upper(cls, value: Any) -> Any:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("code", mode="after")
    @classmethod
    def _code_shape(cls, value: str) -> str:
        if not _CODE_PATTERN.match(value):
            raise ValueError("a code is 2-40 letters, digits, dashes, or underscores")
        return value

    @field_validator("trigger_signals", mode="after")
    @classmethod
    def _known_triggers(cls, signals: list[str]) -> list[str]:
        seen: list[str] = []
        for signal in signals:
            canonical = normalize_trigger(signal)
            if canonical not in seen:
                seen.append(canonical)
        return seen

    @field_validator("discount_label", "notes_for_agent", mode="before")
    @classmethod
    def _strip(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @property
    def conversation_triggers(self) -> frozenset[str]:
        return frozenset(
            signal for signal in self.trigger_signals if signal in CONVERSATION_SIGNALS
        )


class DiscountCode(DiscountCodeDraft):
    """A stored record: the draft plus the counters the events feed."""

    usage_proposed: int = 0
    usage_handoff: int = 0
    updated_at: datetime | None = None

    @property
    def conversion_pct(self) -> float:
        if not self.usage_proposed:
            return 0.0
        return round(100 * self.usage_handoff / self.usage_proposed, 1)

    def valid_on(self, today: date) -> bool:
        if self.valid_from is not None and today < self.valid_from:
            return False
        return not (self.valid_to is not None and today > self.valid_to)

    def covers_stay(self, arrival: date, departure: date) -> bool:
        """Every night of the stay lies inside the code's stay window."""
        last_night = departure - timedelta(days=1)
        if self.stay_from is not None and arrival < self.stay_from:
            return False
        return not (self.stay_to is not None and last_night > self.stay_to)

    def public_payload(self) -> dict[str, Any]:
        """What the guest-facing surfaces may show: the code, its label, and its windows.
        ``notes_for_agent`` and the counters stay behind the admin token."""
        return {
            "code": self.code,
            "discount_label": self.discount_label,
            "stay_from": self.stay_from.isoformat() if self.stay_from else None,
            "stay_to": self.stay_to.isoformat() if self.stay_to else None,
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
        }


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StayFacts:
    """The stay the guest is weighing, and what is derived from it: lead time, length,
    and the ISO weekdays (Monday 1 .. Sunday 7) each night begins on."""

    arrival: date
    departure: date
    today: date
    cabin_id: str | None = None

    @property
    def nights(self) -> int:
        return max((self.departure - self.arrival).days, 0)

    @property
    def lead_days(self) -> int:
        return (self.arrival - self.today).days

    @property
    def weekdays(self) -> frozenset[int]:
        return frozenset(
            (self.arrival + timedelta(days=offset)).isoweekday() for offset in range(self.nights)
        )


def code_applies(code: DiscountCode, stay: StayFacts, guest_signals: Iterable[str]) -> bool:
    """Whether a stay earns a code, given the signals the conversation has shown. Every
    trigger must hold; a code that is not announceable also needs one of its conversation
    triggers (or, when it lists none, any conversation signal) to have been shown."""
    signals = {signal for signal in guest_signals if signal in CONVERSATION_SIGNALS}
    if not code.active or not code.valid_on(stay.today) or stay.nights < 1:
        return False
    if not code.covers_stay(stay.arrival, stay.departure):
        return False
    for signal in code.trigger_signals:
        kind, value = parse_trigger(signal)
        if kind == "lead_days_max" and stay.lead_days > value:
            return False
        if kind == "min_nights" and stay.nights < value:
            return False
        if kind == "weekdays" and not stay.weekdays <= value:
            return False
        if kind == "cabins" and (stay.cabin_id is None or stay.cabin_id not in value):
            return False
        if kind in CONVERSATION_SIGNALS and kind not in signals:
            return False
    if not code.announceable:
        wanted = code.conversation_triggers or CONVERSATION_SIGNALS
        if not wanted & signals:
            return False
    return True


def eligible_codes(
    codes: Iterable[DiscountCode],
    stay: StayFacts,
    guest_signals: Iterable[str],
    proposed: Mapping[str, int] | None = None,
    limit: int = MAX_OFFERS,
) -> list[DiscountCode]:
    """The codes to propose for a stay, best first: the ones that apply, less those this
    session has already heard ``max_per_session`` times, ordered by priority."""
    counts = proposed or {}
    signals = list(guest_signals)
    picks = [
        code
        for code in codes
        if counts.get(code.code, 0) < code.max_per_session and code_applies(code, stay, signals)
    ]
    picks.sort(key=lambda code: (code.priority, code.code))
    return picks[: max(limit, 0)]


# ---------------------------------------------------------------------------
# Stores
# ---------------------------------------------------------------------------


class DiscountCodeStore:
    """The records, in memory. The Postgres store below keeps the same interface."""

    def __init__(self, codes: Iterable[DiscountCode] = ()) -> None:
        self._codes: dict[str, DiscountCode] = {code.code: code for code in codes}

    async def open(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def list(self) -> list[DiscountCode]:
        return sorted(self._codes.values(), key=lambda code: (code.priority, code.code))

    async def get(self, code: str) -> DiscountCode | None:
        return self._codes.get(code.strip().upper())

    async def upsert(self, draft: DiscountCodeDraft) -> DiscountCode:
        """Create or replace the editable fields; the counters survive an edit."""
        existing = self._codes.get(draft.code)
        record = DiscountCode(
            **draft.model_dump(),
            usage_proposed=existing.usage_proposed if existing else 0,
            usage_handoff=existing.usage_handoff if existing else 0,
            updated_at=datetime.now().astimezone(),
        )
        self._codes[record.code] = record
        return record

    async def delete(self, code: str) -> bool:
        return self._codes.pop(code.strip().upper(), None) is not None

    async def bump(self, code: str, counter: str) -> None:
        """Add one to ``usage_proposed`` or ``usage_handoff``."""
        record = self._codes.get(code)
        if record is None:
            return
        self._codes[code] = record.model_copy(update={counter: getattr(record, counter) + 1})


_SCHEMA = """
CREATE TABLE IF NOT EXISTS discount_codes (
    code            text PRIMARY KEY,
    discount_label  text NOT NULL,
    stay_from       date,
    stay_to         date,
    valid_from      date,
    valid_to        date,
    active          boolean NOT NULL DEFAULT true,
    announceable    boolean NOT NULL DEFAULT false,
    trigger_signals jsonb NOT NULL DEFAULT '[]'::jsonb,
    priority        integer NOT NULL DEFAULT 100,
    max_per_session integer NOT NULL DEFAULT 1,
    notes_for_agent text NOT NULL DEFAULT '',
    usage_proposed  integer NOT NULL DEFAULT 0,
    usage_handoff   integer NOT NULL DEFAULT 0,
    updated_at      timestamptz NOT NULL DEFAULT now()
);
"""

_COUNTERS = ("usage_proposed", "usage_handoff")


def _record_from_row(row: Mapping[str, Any]) -> DiscountCode:
    data = dict(row)
    signals = data.get("trigger_signals") or []
    if isinstance(signals, str):
        signals = json.loads(signals)
    data["trigger_signals"] = list(signals)
    return DiscountCode.model_validate(data)


class PostgresDiscountCodeStore(DiscountCodeStore):
    """The records in Postgres. Every read goes to the table, so two API instances see
    one list; a failed read answers with no codes and a warning, never an error on the
    guest's turn."""

    def __init__(self, dsn: str) -> None:
        super().__init__()
        self._dsn = dsn.strip()
        self._pool: Any = None

    async def open(self) -> None:
        if not self._dsn or self._pool is not None:
            return
        try:
            import asyncpg
        except ImportError:
            logger.warning("DATABASE_URL is set but asyncpg is not installed; codes stay in memory")
            return
        try:
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=2)
            async with self._pool.acquire() as connection:
                await connection.execute(_SCHEMA)
        except Exception:
            self._pool = None
            logger.warning(
                "could not open the discount code table; codes stay in memory", exc_info=True
            )
        else:
            logger.info("discount code table ready")

    async def close(self) -> None:
        if self._pool is not None:
            pool, self._pool = self._pool, None
            await pool.close()

    async def list(self) -> list[DiscountCode]:
        if self._pool is None:
            return await super().list()
        try:
            async with self._pool.acquire() as connection:
                rows = await connection.fetch(
                    "SELECT * FROM discount_codes ORDER BY priority ASC, code ASC"
                )
        except Exception:
            logger.warning("could not read discount codes", exc_info=True)
            return []
        return [_record_from_row(row) for row in rows]

    async def get(self, code: str) -> DiscountCode | None:
        if self._pool is None:
            return await super().get(code)
        try:
            async with self._pool.acquire() as connection:
                row = await connection.fetchrow(
                    "SELECT * FROM discount_codes WHERE code = $1", code.strip().upper()
                )
        except Exception:
            logger.warning("could not read discount code %s", code, exc_info=True)
            return None
        return _record_from_row(row) if row else None

    async def upsert(self, draft: DiscountCodeDraft) -> DiscountCode:
        if self._pool is None:
            return await super().upsert(draft)
        async with self._pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO discount_codes
                  (code, discount_label, stay_from, stay_to, valid_from, valid_to, active,
                   announceable, trigger_signals, priority, max_per_session, notes_for_agent)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $11, $12)
                ON CONFLICT (code) DO UPDATE SET
                  discount_label = EXCLUDED.discount_label,
                  stay_from = EXCLUDED.stay_from, stay_to = EXCLUDED.stay_to,
                  valid_from = EXCLUDED.valid_from, valid_to = EXCLUDED.valid_to,
                  active = EXCLUDED.active, announceable = EXCLUDED.announceable,
                  trigger_signals = EXCLUDED.trigger_signals, priority = EXCLUDED.priority,
                  max_per_session = EXCLUDED.max_per_session,
                  notes_for_agent = EXCLUDED.notes_for_agent, updated_at = now()
                RETURNING *
                """,
                draft.code,
                draft.discount_label,
                draft.stay_from,
                draft.stay_to,
                draft.valid_from,
                draft.valid_to,
                draft.active,
                draft.announceable,
                json.dumps(draft.trigger_signals),
                draft.priority,
                draft.max_per_session,
                draft.notes_for_agent,
            )
        return _record_from_row(row)

    async def delete(self, code: str) -> bool:
        if self._pool is None:
            return await super().delete(code)
        async with self._pool.acquire() as connection:
            done = await connection.execute(
                "DELETE FROM discount_codes WHERE code = $1", code.strip().upper()
            )
        return done.endswith(" 1")

    async def bump(self, code: str, counter: str) -> None:
        if counter not in _COUNTERS:
            raise ValueError(f"unknown counter {counter!r}")
        if self._pool is None:
            await super().bump(code, counter)
            return
        try:
            async with self._pool.acquire() as connection:
                await connection.execute(
                    f"UPDATE discount_codes SET {counter} = {counter} + 1 WHERE code = $1", code
                )
        except Exception:
            logger.warning("could not count %s for %s", counter, code, exc_info=True)


def build_store(dsn: str | None) -> DiscountCodeStore:
    """Postgres when ``dsn`` (``DATABASE_URL``) names one, else memory."""
    return PostgresDiscountCodeStore(dsn) if dsn and dsn.strip() else DiscountCodeStore()


# ---------------------------------------------------------------------------
# The desk: codes per session
# ---------------------------------------------------------------------------


@dataclass
class _SessionOffers:
    proposed: Counter[str] = field(default_factory=Counter)
    # Codes in the order they were proposed, so checkout carries the earliest still valid.
    order: list[str] = field(default_factory=list)
    signals: set[str] = field(default_factory=set)
    handed: set[str] = field(default_factory=set)


class OfferDesk:
    """Runs ``eligible_codes`` for a session, keeps its per-session counts, and records
    the two events. ``events`` is the host's ``EventLog`` once the host exists; until
    then nothing is recorded, which is also what a test gets."""

    def __init__(self, store: DiscountCodeStore, today: Any = None) -> None:
        self.store = store
        self._today = today
        self.events: Any = None
        self._sessions: dict[str, _SessionOffers] = {}

    def bind(self, events: Any) -> None:
        self.events = events

    def today(self) -> date:
        if callable(self._today):
            return self._today()
        return self._today or datetime.now().astimezone().date()

    def reset(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def _session(self, session_id: str) -> _SessionOffers:
        return self._sessions.setdefault(session_id, _SessionOffers())

    def _record(self, kind: str, session_id: str, user_id: str, code: str) -> None:
        if self.events is None:
            return
        try:
            self.events.record(kind, session_id=session_id, user_id=user_id, code=code)
        except Exception:  # counting must never break the turn
            logger.warning("could not record %s", kind, exc_info=True)

    async def announceable(self) -> list[DiscountCode]:
        """The codes the home panel may show: active, valid today, announceable, with a
        stay window that has not closed."""
        today = self.today()
        return [
            code
            for code in await self.store.list()
            if code.active
            and code.announceable
            and code.valid_on(today)
            and (code.stay_to is None or code.stay_to >= today)
        ]

    async def propose(
        self,
        session_id: str,
        user_id: str,
        arrival: date,
        departure: date,
        cabin_id: str | None,
        guest_signals: Iterable[str],
    ) -> list[DiscountCode]:
        """The codes to name now; each one counts against the session and is recorded."""
        session = self._session(session_id)
        session.signals |= {signal for signal in guest_signals if signal in CONVERSATION_SIGNALS}
        stay = StayFacts(
            arrival=arrival, departure=departure, today=self.today(), cabin_id=cabin_id
        )
        picks = eligible_codes(await self.store.list(), stay, session.signals, session.proposed)
        for code in picks:
            session.proposed[code.code] += 1
            if code.code not in session.order:
                session.order.append(code.code)
            await self.store.bump(code.code, "usage_proposed")
            self._record("offer_proposed", session_id, user_id, code.code)
        return picks

    async def handoff(
        self,
        session_id: str,
        user_id: str,
        arrival: date | None,
        departure: date | None,
        cabin_id: str | None,
    ) -> DiscountCode | None:
        """The code the checkout card carries: the first one proposed this session that
        still applies to the stay being booked. Counted once per session and code."""
        session = self._sessions.get(session_id)
        if session is None or not session.order:
            return None
        stay = (
            StayFacts(arrival=arrival, departure=departure, today=self.today(), cabin_id=cabin_id)
            if arrival and departure
            else None
        )
        for name in session.order:
            code = await self.store.get(name)
            if code is None:
                continue
            if stay is not None and not code_applies(code, stay, session.signals):
                continue
            if stay is None and not (code.active and code.valid_on(self.today())):
                continue
            if name not in session.handed:
                session.handed.add(name)
                await self.store.bump(name, "usage_handoff")
                self._record("offer_handoff", session_id, user_id, name)
            return code
        return None
