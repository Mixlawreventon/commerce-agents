# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""``GET /api/home``: what the stay panel shows before anything is chosen. Three blocks,
all from live data: the nearest open dates with a price (weekends and midweek stays off
the availability calendar), the five cabins with their lowest rate, and the offers on
(idobooking's own promotions, and the announceable discount codes). The web app renders
them as tiles; a tile's click is a ready question to the assistant."""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter

from .discount_codes import OfferDesk

logger = logging.getLogger("hygge.home")

# How far ahead the openings look, and how many of each kind to name.
OPENINGS_DAYS = 30
MAX_WEEKENDS = 2
MAX_MIDWEEK = 2
# The overview is public and cheap to serve from memory; the calendar behind it moves slowly.
_CACHE_SECONDS = 10 * 60

# Catalog id -> the short cabin name the storefront shows.
CABIN_NAMES = {
    "HY-FIKA": "Fika",
    "HY-LAGOM": "Lagom",
    "HY-GRON": "Gron",
    "HY-HYGGELIG": "Hyggelig",
    "HY-LYKKE": "Lykke",
}


def _day_prices(payload: dict) -> dict[str, list[float]]:
    """For each day, the nightly price in every cabin free that night."""
    prices: dict[str, list[float]] = {}
    for cabin in payload.get("cabins", []):
        for day, state in (cabin.get("days") or {}).items():
            if isinstance(state, dict) and state.get("available") and state.get("price"):
                prices.setdefault(day, []).append(float(state["price"]))
    return prices


def _stay_quote(
    prices: dict[str, list[float]], arrival: date, nights: int, payload: dict
) -> dict | None:
    """The cheapest cabin free for every night from ``arrival``, and how many are."""
    days = [(arrival + timedelta(days=offset)).isoformat() for offset in range(nights)]
    totals: list[float] = []
    for cabin in payload.get("cabins", []):
        states = cabin.get("days") or {}
        nightly = [states.get(day) for day in days]
        if all(isinstance(s, dict) and s.get("available") and s.get("price") for s in nightly):
            totals.append(sum(float(s["price"]) for s in nightly))  # type: ignore[index]
    if not totals:
        return None
    return {"price_from": round(min(totals)), "cabins_left": len(totals)}


def openings_from_calendar(payload: dict, today: date) -> list[dict[str, Any]]:
    """The nearest weekends (Friday to Sunday) and midweek stays (Monday to Wednesday)
    with a cabin free for the whole stay, each priced for its cheapest free cabin."""
    prices = _day_prices(payload)
    horizon = today + timedelta(days=OPENINGS_DAYS)
    weekends: list[dict[str, Any]] = []
    midweek: list[dict[str, Any]] = []
    day = today + timedelta(days=1)
    while day <= horizon:
        if day.weekday() == 4 and len(weekends) < MAX_WEEKENDS:
            quote = _stay_quote(prices, day, 2, payload)
            if quote:
                weekends.append(
                    {"kind": "weekend", "arrival": day.isoformat(), "nights": 2, **quote}
                )
        elif day.weekday() == 0 and len(midweek) < MAX_MIDWEEK:
            quote = _stay_quote(prices, day, 2, payload)
            if quote:
                midweek.append(
                    {"kind": "midweek", "arrival": day.isoformat(), "nights": 2, **quote}
                )
        day += timedelta(days=1)
    openings = weekends + midweek
    for opening in openings:
        arrival = date.fromisoformat(opening["arrival"])
        opening["departure"] = (arrival + timedelta(days=opening["nights"])).isoformat()
    return sorted(openings, key=lambda opening: opening["arrival"])


def promotions_from_payload(payload: dict) -> list[dict[str, Any]]:
    """idobooking's promotions as the panel's offer tiles; keys are read tolerantly since
    the middleware passes the booking system's own records through."""
    offers: list[dict[str, Any]] = []
    for promotion in payload.get("promotions", []) or []:
        if not isinstance(promotion, dict):
            continue
        title = promotion.get("name") or promotion.get("title")
        if not title:
            continue
        offers.append(
            {
                "kind": "promotion",
                "title": str(title).strip(),
                "detail": str(promotion.get("description") or "").strip() or None,
                "stay_from": promotion.get("date_from") or promotion.get("stay_from"),
                "stay_to": promotion.get("date_to") or promotion.get("stay_to"),
            }
        )
    return offers


class HomeOverview:
    """Builds the payload from the backend's live reads and the desk's codes, cached for
    a few minutes. A backend without live data (the static catalog) still lists the
    cabins and the codes."""

    def __init__(self, backend: Any, desk: OfferDesk) -> None:
        self.backend = backend
        self.desk = desk
        self._cached: tuple[float, dict[str, Any]] | None = None

    async def _live(self, path: str, params: dict | None = None) -> dict | None:
        reader = getattr(self.backend, "_aget", None)
        if reader is None:
            return None
        return await reader(path, params)

    def _cabins(self) -> list[dict[str, Any]]:
        cabins = []
        for product_id, name in CABIN_NAMES.items():
            product = self.backend.products.get(product_id)
            if product is None:
                continue
            cabins.append(
                {
                    "product_id": product_id,
                    "name": name,
                    "price_from": round(product.price),
                    "image_url": product.image_url,
                    "hot_tub": product.attributes.get("hot_tub") == "tak",
                    "max_guests": product.attributes.get("max_guests"),
                }
            )
        return cabins

    async def _live_blocks(self, today: date) -> dict[str, Any]:
        """The openings and promotions, from two middleware reads, cached; the codes are
        read fresh on every call so an operator's edit shows at once."""
        now = time.monotonic()
        if self._cached and now - self._cached[0] < _CACHE_SECONDS:
            return self._cached[1]
        calendar = await self._live("/api/calendar-pricing", {"months": 2, "adults": 2})
        promotions = await self._live("/api/promotions")
        blocks = {
            "openings": openings_from_calendar(calendar, today) if calendar else [],
            "promotions": promotions_from_payload(promotions) if promotions else [],
        }
        self._cached = (now, blocks)
        return blocks

    async def build(self) -> dict[str, Any]:
        today = self.desk.today()
        live = await self._live_blocks(today)
        codes = await self.desk.announceable()
        return {
            "openings": live["openings"],
            "cabins": self._cabins(),
            "offers": [
                *live["promotions"],
                *({"kind": "code", **code.public_payload()} for code in codes),
            ],
            "generated_for": today.isoformat(),
        }


def create_home_router(backend: Any, desk: OfferDesk) -> APIRouter:
    overview = HomeOverview(backend, desk)
    router = APIRouter()

    @router.get("/home")
    async def home() -> dict:
        return await overview.build()

    return router
