# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""An append-only record of what happened in a session, for a deployment that wants to
read its own traffic back.

The demo's ``SessionStore`` keeps conversations in memory, so every restart drops them:
fine for a demo, useless for a deployment learning from real use. This log is the separate,
durable half — one ``events`` row per thing worth counting (a session opening, a message
either way, a search and how many results it found, a guest's verdict on a reply).

It is off unless ``DATABASE_URL`` names a Postgres, so the examples, the tests, and a local
run behave exactly as before. Every write goes out on a background task and every failure
is swallowed after a warning: a deployment that cannot record its traffic still serves it.

Rows hold what guests typed. Treat the table as personal data: say so in the interface, and
keep only as long as the data is useful — ``EVENT_RETENTION_DAYS`` (90 by default) drops
older rows at startup and once a day after that.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# How long a row is kept. Conversations are personal data; the default is a window long
# enough to read a season's traffic back and short enough to be defensible.
_DEFAULT_RETENTION_DAYS = 90
_PURGE_EVERY_SECONDS = 24 * 60 * 60

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id         bigserial PRIMARY KEY,
    at         timestamptz NOT NULL DEFAULT now(),
    session_id text NOT NULL,
    user_id    text NOT NULL,
    kind       text NOT NULL,
    data       jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS events_at_idx ON events (at DESC);
CREATE INDEX IF NOT EXISTS events_session_idx ON events (session_id, id);
CREATE INDEX IF NOT EXISTS events_kind_idx ON events (kind, at DESC);
"""

# Long enough for a real message, short enough that one row cannot run away with the table.
_MAX_TEXT = 8000


def _clip(value: Any) -> Any:
    return value[:_MAX_TEXT] if isinstance(value, str) and len(value) > _MAX_TEXT else value


class EventLog:
    """Writes one row per event, or nothing at all when no database is configured.

    ``record`` never awaits and never raises, so a caller on the request path pays a
    dictionary build and nothing else.
    """

    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = (dsn if dsn is not None else os.environ.get("DATABASE_URL", "")).strip()
        self._pool: Any = None
        self._purge: asyncio.Task[None] | None = None
        try:
            self._retention_days = int(os.environ.get("EVENT_RETENTION_DAYS", ""))
        except ValueError:
            self._retention_days = _DEFAULT_RETENTION_DAYS

    @property
    def enabled(self) -> bool:
        return bool(self._pool)

    async def open(self) -> None:
        """Connect and create the table. A failure here leaves the log disabled rather than
        stopping the app from starting, so recording is never what takes a deployment down."""
        if not self._dsn or self._pool is not None:
            return
        try:
            import asyncpg
        except ImportError:
            logger.warning("DATABASE_URL is set but asyncpg is not installed; not recording")
            return
        try:
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=4)
            async with self._pool.acquire() as connection:
                await connection.execute(_SCHEMA)
        except Exception:
            self._pool = None
            logger.warning("could not open the event log; not recording", exc_info=True)
        else:
            logger.info("event log ready, keeping %d days", self._retention_days)
            self._purge = asyncio.create_task(self._purge_loop())

    async def purge(self) -> int:
        """Drop rows past the retention window; returns how many went."""
        if not self._pool or self._retention_days <= 0:
            return 0
        try:
            async with self._pool.acquire() as connection:
                done = await connection.execute(
                    "DELETE FROM events WHERE at < now() - ($1 || ' days')::interval",
                    str(self._retention_days),
                )
            dropped = int(done.rsplit(" ", 1)[-1]) if done.startswith("DELETE") else 0
        except Exception:
            logger.warning("could not purge old events", exc_info=True)
            return 0
        if dropped:
            logger.info("purged %d events past %d days", dropped, self._retention_days)
        return dropped

    async def _purge_loop(self) -> None:
        """Once at startup, then daily, so a long-running deployment keeps its own window."""
        try:
            while True:
                await self.purge()
                await asyncio.sleep(_PURGE_EVERY_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("the purge loop stopped", exc_info=True)

    async def close(self) -> None:
        if self._purge is not None:
            self._purge.cancel()
            self._purge = None
        if self._pool is not None:
            pool, self._pool = self._pool, None
            await pool.close()

    async def summary(self, days: int = 30) -> dict[str, Any]:
        """The counts a deployment watches: how many guests arrived, how much they asked,
        how many offers went out, and how many left for the booking system."""
        if not self._pool:
            return {}
        window = str(max(days, 1))
        try:
            async with self._pool.acquire() as connection:
                row = await connection.fetchrow(
                    """
                    SELECT
                      count(*) FILTER (WHERE kind = 'session_start')            AS sessions,
                      count(*) FILTER (WHERE kind = 'message'
                                         AND data->>'role' = 'guest')           AS interactions,
                      count(*) FILTER (WHERE kind = 'message'
                                         AND data->>'role' = 'assistant')       AS replies,
                      count(*) FILTER (WHERE kind = 'tool_call'
                                         AND data->>'tool' = 'present_products') AS offers,
                      coalesce(sum(jsonb_array_length(data->'arguments'->'picks'))
                               FILTER (WHERE kind = 'tool_call'
                                         AND data->>'tool' = 'present_products'), 0) AS cabins_shown,
                      count(*) FILTER (WHERE kind = 'click'
                                         AND data->>'target' = 'booking')       AS booking_clicks,
                      count(*) FILTER (WHERE kind = 'feedback'
                                         AND data->>'verdict' = 'down')         AS thumbs_down,
                      count(*) FILTER (WHERE kind = 'error')                    AS errors
                    FROM events WHERE at > now() - ($1 || ' days')::interval
                    """,
                    window,
                )
        except Exception:
            logger.warning("could not summarise events", exc_info=True)
            return {}
        return {"days": max(days, 1), **{key: int(value) for key, value in dict(row).items()}}

    async def conversations(self, limit: int = 20) -> list[dict[str, Any]]:
        """The most recent sessions, each with what was said, newest first."""
        if not self._pool:
            return []
        try:
            async with self._pool.acquire() as connection:
                rows = await connection.fetch(
                    """
                    WITH recent AS (
                      SELECT session_id, max(id) AS last_id, min(at) AS started
                      FROM events GROUP BY session_id ORDER BY last_id DESC LIMIT $1
                    )
                    SELECT e.session_id, r.started, e.at, e.kind, e.data
                    FROM events e JOIN recent r USING (session_id)
                    ORDER BY r.last_id DESC, e.id ASC
                    """,
                    max(1, min(limit, 200)),
                )
        except Exception:
            logger.warning("could not read conversations", exc_info=True)
            return []
        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            talk = grouped.setdefault(
                row["session_id"],
                {"session_id": row["session_id"], "started": row["started"], "events": []},
            )
            talk["events"].append(
                {"at": row["at"], "kind": row["kind"], "data": json.loads(row["data"])}
            )
        return list(grouped.values())

    async def write(self, kind: str, *, session_id: str, user_id: str, **data: Any) -> None:
        """The awaitable behind ``record``; failures are logged, never raised."""
        if not self._pool:
            return
        try:
            payload = json.dumps({key: _clip(value) for key, value in data.items()})
            async with self._pool.acquire() as connection:
                await connection.execute(
                    "INSERT INTO events (session_id, user_id, kind, data)"
                    " VALUES ($1, $2, $3, $4::jsonb)",
                    session_id,
                    user_id,
                    kind,
                    payload,
                )
        except Exception:
            logger.warning("could not record %s", kind, exc_info=True)

    def record(self, kind: str, *, session_id: str, user_id: str, **data: Any) -> None:
        """Queue one row. Call from a request: it returns before the row is written."""
        if not self._pool:
            return
        from .host import spawn_background

        spawn_background(self.write(kind, session_id=session_id, user_id=user_id, **data))
