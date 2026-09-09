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

Rows hold what guests typed. Treat the table as personal data — say so in the interface,
and give it a retention window rather than keeping it forever.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

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
            logger.info("event log ready")

    async def close(self) -> None:
        if self._pool is not None:
            pool, self._pool = self._pool, None
            await pool.close()

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
