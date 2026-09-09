# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""A ``StorefrontBackend`` that overlays live Osada Hygge data on the static fixtures.

The static catalog (``data/catalog.json``) supplies the rich Polish copy — long
descriptions, specs, review highlights. The idobooking middleware (the same service the
Hygge MCP calls: ``/api/cabins``, ``/api/availability``, ``/api/pricing``) supplies the
live parts: current per-night price, real photos, the booking widget URL, and — for a
dated search — which cabins are actually free and what the nights cost.

Set ``IDOBOOKING_MIDDLEWARE_URL`` (e.g. ``https://api-idobooking-production.up.railway.app``)
to turn this on; ``main.py`` falls back to the static ``MockTravel`` when it is unset. Every
live call is best-effort: on any error the backend serves the static catalog so the store
never goes dark. Booking is a hand-off — each cabin carries its idobooking ``booking_url``.
"""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta

import httpx

from demo_common.storefront_fixtures import rank_products, summary_of
from shopping_agent import (
    Cart,
    CheckoutHandoff,
    Policy,
    Product,
    SearchFilters,
    ShoppingSessionContext,
)

from .mock_travel import DATA_DIR, MockTravel, _travel_date

logger = logging.getLogger("hygge.live")

# idobooking cabin id -> the catalog's stable product id, so orders and copy stay aligned.
_ID_TO_SLUG = {12: "HY-FIKA", 13: "HY-LAGOM", 14: "HY-GRON", 15: "HY-HYGGELIG", 17: "HY-LYKKE"}
# The booking widget URL only varies by cabin id, so build it deterministically rather than
# relying on /api/cabins (which can return a partial cabin list).
_WIDGET_URL = "https://client9681.idobooking.com/book-now/booking/defaultchoice/currency/1/language/1?ob[{id}]"
# Same widget, pre-configured with the guest's dates and party size — a ready-to-pay offer.
_WIDGET_URL_DATED = (
    "https://client9681.idobooking.com/book-now/booking/defaultchoice"
    "/start_date/{start}/end_date/{end}/currency/1/language/1?ob[{id}]&rooms=1&persons-adult={adults}"
)
# A dated search only knows the arrival; quote this many nights to check availability/price.
_DEFAULT_QUOTE_NIGHTS = 2


class HyggeLive(MockTravel):
    def __init__(self, middleware_url: str, data_dir=DATA_DIR, today: date | None = None) -> None:
        super().__init__(data_dir=data_dir, today=today)
        self.mw = middleware_url.rstrip("/")
        self.property: dict = {}
        # Last check-in date searched per session, so checkout can hand off a dated offer.
        self._session_dates: dict[str, str] = {}
        self._overlay_live_cabins()
        self._load_property()

    # ------------------------------------------------------------------
    # Middleware
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict | None = None) -> dict | None:
        try:
            r = httpx.get(f"{self.mw}{path}", params=params, timeout=12)
            r.raise_for_status()
            return r.json()
        except Exception:
            logger.warning("idobooking middleware call failed: %s", path, exc_info=True)
            return None

    async def _aget(self, path: str, params: dict | None = None) -> dict | None:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(f"{self.mw}{path}", params=params)
                r.raise_for_status()
                return r.json()
        except Exception:
            logger.warning("idobooking middleware call failed: %s", path, exc_info=True)
            return None

    def _overlay_live_cabins(self) -> None:
        """Refresh price, photos, gallery, and area from ``/api/cabins`` onto the static
        products, keeping the catalog's long copy. The booking widget URL is set for every
        cabin from the id template, so the self-service path works even if the live call
        returns a partial list or fails."""
        for cabin_id, slug in _ID_TO_SLUG.items():
            product = self.products.get(slug)
            if product is not None:
                product.attributes["cabin_id"] = str(cabin_id)
                product.attributes["booking_url"] = _WIDGET_URL.format(id=cabin_id)
        data = self._get("/api/cabins")
        if not data:
            logger.warning(
                "no live cabin data; serving the static catalog (booking URLs still set)"
            )
            return
        for cabin in data.get("cabins", []):
            slug = _ID_TO_SLUG.get(cabin.get("id"))
            product = self.products.get(slug) if slug else None
            if product is None:
                continue
            if cabin.get("min_price"):
                product.price = float(cabin["min_price"])
            images = cabin.get("images") or []
            if images:
                product.image_url = images[0]
                product.attributes["gallery"] = "|".join(images[:12])
            if cabin.get("area_m2"):
                product.attributes["area_m2"] = str(cabin["area_m2"])
            if cabin.get("widget_url"):
                product.attributes["booking_url"] = cabin["widget_url"]
            product.attributes["cabin_id"] = str(cabin.get("id", ""))
        logger.info("overlaid %d live cabins", len(data.get("cabins", [])))

    def _load_property(self) -> None:
        """Real contact and stay facts (address, phone, email, check-in/out) from the
        ``/api/agent-data`` property block, so the assistant answers with live values."""
        arrival = self.today + timedelta(days=30)
        data = self._get(
            "/api/agent-data",
            {
                "arrival": arrival.isoformat(),
                "departure": (arrival + timedelta(days=2)).isoformat(),
                "persons": 2,
            },
        )
        self.property = (data or {}).get("property", {}) or {}
        if self.property:
            logger.info("loaded property info for %s", self.property.get("name"))

    def _contact_policy(self) -> Policy | None:
        """A searchable policy built from the live property block; None if unavailable."""
        p = self.property
        if not p:
            return None
        checkin = (p.get("checkin") or {}).get("from")
        checkout = (p.get("checkout") or {}).get("to")
        lines = ["Osada Hygge — leśne domki nad jeziorem."]
        if p.get("address"):
            lines.append(f"Adres: {p['address']}.")
        if p.get("phone"):
            lines.append(f"Telefon: {p['phone'].replace('.', ' ').strip()}.")
        if p.get("email"):
            lines.append(f"E-mail: {p['email']}.")
        if checkin or checkout:
            lines.append(
                f"Doba hotelowa: zameldowanie od {checkin or '15:00'}, "
                f"wymeldowanie do {checkout or '11:00'}."
            )
        lines.append(
            "Dokładne wskazówki dojazdu i zameldowania wysyłamy przed przyjazdem; "
            "w razie pytań prosimy o kontakt telefoniczny lub mailowy."
        )
        return Policy(
            policy_id="contact-and-practical",
            title="Kontakt, adres i doba hotelowa",
            category="contact",
            content=" ".join(lines),
        )

    async def search_policies(self, session: ShoppingSessionContext, query: str) -> list[Policy]:
        results = await super().search_policies(session, query)
        contact = self._contact_policy()
        if contact is not None:
            # Live contact/stay facts lead; drop any static stand-in for the same thing.
            results = [contact] + [p for p in results if p.policy_id != "contact-and-practical"]
        return results

    async def checkout_handoff(
        self, session: ShoppingSessionContext, cart: Cart
    ) -> list[CheckoutHandoff]:
        """Self-service path: each cabin in the cart links to its idobooking booking widget,
        pre-configured with the guest's dates and party size when known — a ready-to-pay
        offer. Reservation and payment happen in idobooking/idopayments. The URL never
        reaches the model; the host renders it on the checkout card."""
        arrival = self._session_dates.get(session.session_id)
        handoffs: list[CheckoutHandoff] = []
        seen: set[str] = set()
        for item in cart.items:
            if item.product_id in seen:
                continue
            seen.add(item.product_id)
            product = self.products.get(item.product_id)
            if product is None:
                continue
            cabin_id = product.attributes.get("cabin_id")
            name = product.title
            url = self._booking_url(cabin_id, arrival, item.quantity) or product.attributes.get(
                "booking_url"
            )
            if url:
                handoffs.append(
                    CheckoutHandoff(url=url, label=f"Zarezerwuj w idobooking — {name}", seller=name)
                )
        return handoffs

    def _booking_url(self, cabin_id: str | None, arrival: str | None, nights: int) -> str | None:
        """A dated widget URL (cabin + dates + guests) when the check-in is known, else None
        so the caller falls back to the plain per-cabin URL."""
        if not cabin_id or not arrival:
            return None
        try:
            start = date.fromisoformat(arrival)
            end = start + timedelta(days=max(nights, 1))
        except ValueError:
            return None
        return _WIDGET_URL_DATED.format(
            start=start.isoformat(), end=end.isoformat(), id=cabin_id, adults=2
        )

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search_products(
        self,
        session: ShoppingSessionContext,
        query: str,
        filters: SearchFilters | None = None,
        limit: int = 8,
    ) -> list[Product]:
        travel_date = _travel_date(filters) if filters is not None else None
        if travel_date is None:
            # No dates: rank the whole (live-priced) catalog, as the static backend does.
            return await super().search_products(session, query, filters, limit)

        # Remember the check-in so checkout can hand off a dated, ready-to-pay offer.
        self._session_dates[session.session_id] = travel_date.isoformat()
        departure = travel_date + timedelta(days=_DEFAULT_QUOTE_NIGHTS)
        avail = await self._aget(
            "/api/availability",
            {
                "arrival": travel_date.isoformat(),
                "departure": departure.isoformat(),
                "persons": 2,
            },
        )
        if avail is None:
            # Middleware down: fall back to the static dated search.
            return await super().search_products(session, query, filters, limit)

        nights = max((departure - travel_date).days, 1)
        # Map available cabins to their catalog products, live nightly price, and the
        # refundable / non-refundable rate split from each cabin's pricing_offers.
        live_price: dict[str, float] = {}
        offer_rates: dict[str, dict[str, float]] = {}
        available: list = []
        for cabin in avail.get("available_cabins", []):
            slug = _ID_TO_SLUG.get(cabin.get("id"))
            product = self.products.get(slug) if slug else None
            if product is None:
                continue
            available.append(product)
            if cabin.get("price_per_night"):
                live_price[slug] = float(cabin["price_per_night"])
            rates: dict[str, float] = {}
            for offer in cabin.get("pricing_offers", []):
                total = offer.get("price")
                if offer.get("type") in ("refundable", "nonrefundable") and total:
                    rates[offer["type"]] = round(float(total) / nights)
            if rates:
                offer_rates[slug] = rates

        ranked = rank_products(
            available,
            query,
            filters,
            limit,
            score=self._score,
            hard_filter=self._soft_filter,  # availability already applied by the middleware
            soft_filter=self._soft_filter,
        )
        results = [summary_of(product) for product in ranked]
        for product in results:
            rates = offer_rates.get(product.product_id, {})
            # Show the lowest available rate on the card; keep both for the assistant.
            product.price = min(
                [live_price.get(product.product_id, product.price), *rates.values()]
            )
            if rates.get("refundable"):
                product.attributes["refundable_rate"] = str(rates["refundable"])
            if rates.get("nonrefundable"):
                product.attributes["nonrefundable_rate"] = str(rates["nonrefundable"])
            # The exact free-cancellation deadline is not exposed by the API — it is shown
            # at booking — so we do not assert one here (only that a refundable rate exists).
            product.attributes["quoted_for"] = f"{travel_date.isoformat()}..{departure.isoformat()}"
        return results


def build_backend() -> MockTravel:
    """``HyggeLive`` when ``IDOBOOKING_MIDDLEWARE_URL`` is set, else the static ``MockTravel``."""
    url = os.environ.get("IDOBOOKING_MIDDLEWARE_URL", "").strip()
    if url:
        logger.info("using live idobooking backend at %s", url)
        return HyggeLive(url)
    logger.info("IDOBOOKING_MIDDLEWARE_URL unset; using the static catalog")
    return MockTravel()
