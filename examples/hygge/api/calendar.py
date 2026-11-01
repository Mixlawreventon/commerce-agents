# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""``present_calendar``: the availability calendar as a card. The model names a cabin
(or none, for the whole property), a month, and how many months; the host fills in
every day from the booking system's own calendar (``/api/calendar-pricing``: whether
each cabin is free that night and at what price), so the card shows the same days the
idobooking widget does, inside the conversation. A day's click is a question about a
stay starting that day."""

from __future__ import annotations

import logging
import re
import time
from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel, Field

from commerce_common.presentation import (
    EnrichmentContext,
    PresentationExtension,
    PresentationRefused,
)

logger = logging.getLogger("hygge.calendar")

MAX_MONTHS = 2
# The middleware answers whole months from the current one; this many is as far as it
# is asked for in one read.
_MAX_FETCH_MONTHS = 6
_CACHE_SECONDS = 5 * 60
_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

# Catalog id -> idobooking cabin id, and the short name the card shows.
CABIN_IDS = {"HY-FIKA": 12, "HY-LAGOM": 13, "HY-GRON": 14, "HY-HYGGELIG": 15, "HY-LYKKE": 17}
CABIN_NAMES = {
    "HY-FIKA": "Fika",
    "HY-LAGOM": "Lagom",
    "HY-GRON": "Gron",
    "HY-HYGGELIG": "Hyggelig",
    "HY-LYKKE": "Lykke",
}


class CalendarPayload(BaseModel):
    title: str | None = Field(default=None, max_length=80)
    cabin_id: str | None = Field(default=None, max_length=40)
    month: str | None = Field(default=None, pattern=_MONTH.pattern)
    months: int = Field(default=1, ge=1, le=MAX_MONTHS)
    guests: int = Field(default=2, ge=1, le=12)


INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "maxLength": 80, "description": "Short heading for the card."},
        "cabin_id": {
            "type": "string",
            "description": (
                "product_id of one cabin to show; omit for the whole property (how many "
                "cabins are free each night, and the lowest price)."
            ),
        },
        "month": {
            "type": "string",
            "pattern": _MONTH.pattern,
            "description": "First month to show, YYYY-MM; the current month when omitted.",
        },
        "months": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_MONTHS,
            "description": "How many months from the first; one unless the guest looks further.",
        },
        "guests": {
            "type": "integer",
            "minimum": 1,
            "maximum": 12,
            "description": "Party size the prices are for; two when unknown.",
        },
    },
    "additionalProperties": False,
}


def _month_start(value: str | None, today: date) -> date:
    if not value:
        return today.replace(day=1)
    year, month = (int(part) for part in value.split("-"))
    return date(year, month, 1)


def _add_months(start: date, count: int) -> date:
    month = start.month - 1 + count
    return date(start.year + month // 12, month % 12 + 1, 1)


def _months_between(start: date, target: date) -> int:
    return (target.year - start.year) * 12 + (target.month - start.month)


def month_grid(
    first: date,
    today: date,
    day_state: Any,
) -> dict[str, Any]:
    """One month as the card renders it: every day with its availability, price, and
    how many cabins are free. ``day_state(iso)`` returns ``(available, price,
    cabins_free)`` for a night, or None when the calendar has nothing for it."""
    last = _add_months(first, 1) - timedelta(days=1)
    days: list[dict[str, Any]] = []
    day = first
    while day <= last:
        iso = day.isoformat()
        state = day_state(iso)
        past = day < today
        entry: dict[str, Any] = {
            "iso": iso,
            "day": day.day,
            "weekday": day.isoweekday(),
            "past": past,
            "available": bool(state and state[0]) and not past,
            "price": state[1] if state and state[0] and not past else None,
        }
        if state and state[2] is not None:
            entry["cabins_free"] = 0 if past else state[2]
        days.append(entry)
        day += timedelta(days=1)
    return {"month": first.strftime("%Y-%m"), "days": days}


def calendar_from_pricing(
    payload: dict,
    *,
    today: date,
    first: date,
    months: int,
    cabin_id: int | None,
) -> list[dict[str, Any]]:
    """The months the card shows, read off the middleware's calendar. One cabin: its own
    nights and prices. The property: free cabins per night and the lowest price."""
    cabins = [
        cabin
        for cabin in payload.get("cabins", [])
        if cabin_id is None or cabin.get("id") == cabin_id
    ]

    def day_state(iso: str) -> tuple[bool, float | None, int | None] | None:
        seen = False
        prices: list[float] = []
        free = 0
        for cabin in cabins:
            state = (cabin.get("days") or {}).get(iso)
            if not isinstance(state, dict):
                continue
            seen = True
            if state.get("available"):
                free += 1
                if state.get("price"):
                    prices.append(float(state["price"]))
        if not seen:
            return None
        price = round(min(prices)) if prices else None
        return free > 0, price, (None if cabin_id is not None else free)

    return [month_grid(_add_months(first, offset), today, day_state) for offset in range(months)]


class CalendarSource:
    """Reads the property's calendar for the card: the live middleware when the backend
    has one, else the static fixtures' availability window. Live reads are cached a few
    minutes per party size, as the calendar moves slowly and a card is one read."""

    def __init__(self, backend: Any) -> None:
        self.backend = backend
        self._cache: dict[tuple[int, int], tuple[float, dict]] = {}

    async def _pricing(self, guests: int, months: int) -> dict | None:
        reader = getattr(self.backend, "_aget", None)
        if reader is None:
            return None
        key = (guests, months)
        now = time.monotonic()
        cached = self._cache.get(key)
        if cached and now - cached[0] < _CACHE_SECONDS:
            return cached[1]
        payload = await reader("/api/calendar-pricing", {"months": months, "adults": guests})
        if payload:
            self._cache[key] = (now, payload)
        return payload

    def _static_months(self, first: date, months: int, product_id: str | None) -> list[dict]:
        """Without live data: the catalog's availability window and nightly rate, so the
        card still renders in the example."""
        from .mock_travel import _available_on  # the fixtures' date window

        products = [
            product
            for pid, product in self.backend.products.items()
            if pid in CABIN_IDS and (product_id is None or pid == product_id)
        ]

        def day_state(iso: str) -> tuple[bool, float | None, int | None] | None:
            night = date.fromisoformat(iso)
            open_ = [product for product in products if _available_on(product, night)]
            price = round(min(product.price for product in open_)) if open_ else None
            return bool(open_), price, (None if product_id else len(open_))

        today = self.backend.today
        return [
            month_grid(_add_months(first, offset), today, day_state) for offset in range(months)
        ]

    async def months(
        self, first: date, months: int, product_id: str | None, guests: int
    ) -> list[dict[str, Any]]:
        today: date = self.backend.today
        span = _months_between(today.replace(day=1), first) + months
        if span < 1 or span > _MAX_FETCH_MONTHS:
            raise PresentationRefused(
                f"The calendar covers the next {_MAX_FETCH_MONTHS} months from today; "
                "pick a month inside that."
            )
        payload = await self._pricing(guests, span)
        if not payload:
            return self._static_months(first, months, product_id)
        return calendar_from_pricing(
            payload,
            today=today,
            first=first,
            months=months,
            cabin_id=CABIN_IDS.get(product_id) if product_id else None,
        )


def build_calendar_extension(backend: Any) -> PresentationExtension:
    source = CalendarSource(backend)

    async def enrich(payload: CalendarPayload, context: EnrichmentContext) -> dict[str, Any]:
        product_id = (payload.cabin_id or "").strip().upper() or None
        if product_id is not None and product_id not in CABIN_IDS:
            raise PresentationRefused(
                f"No cabin with id {payload.cabin_id}; use a product_id from the catalog "
                "or omit cabin_id for the whole property."
            )
        today: date = context.backend.today
        first = _month_start(payload.month, today)
        months = await source.months(first, payload.months, product_id, payload.guests)
        enriched: dict[str, Any] = {
            "title": payload.title,
            "guests": payload.guests,
            "months": months,
            "cabin": (
                {"product_id": product_id, "name": CABIN_NAMES[product_id]} if product_id else None
            ),
        }
        # The card says what it shows so the model's text can stay on the stay to book.
        free_nights = sum(1 for month in months for day in month["days"] if day["available"])
        context.notes.append(f"The calendar shows {free_nights} free nights in the months shown.")
        return {key: value for key, value in enriched.items() if value is not None}

    return PresentationExtension(
        name="present_calendar",
        component="calendar",
        description=(
            "Show the availability calendar as a month grid: which nights are free and "
            "at what price, for one cabin (cabin_id) or for the whole property (how many "
            "cabins are free each night, lowest price). Use it whenever the guest asks "
            "what is free, for a calendar, or about a cabin's dates, in the same round as "
            "your text; the text still names the nearest concrete stay with its price. A "
            "day on the card is clickable and asks about a stay starting that night."
        ),
        input_schema=INPUT_SCHEMA,
        payload_model=CalendarPayload,
        enrich=enrich,
    )
