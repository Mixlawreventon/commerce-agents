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
    Product,
    SearchFilters,
    ShoppingSessionContext,
)

from .mock_travel import DATA_DIR, MockTravel, _travel_date, cancellation_deadline

logger = logging.getLogger("hygge.live")

# idobooking cabin id -> the catalog's stable product id, so orders and copy stay aligned.
_ID_TO_SLUG = {12: "HY-FIKA", 13: "HY-LAGOM", 14: "HY-GRON", 15: "HY-HYGGELIG", 17: "HY-LYKKE"}
# A dated search only knows the arrival; quote this many nights to check availability/price.
_DEFAULT_QUOTE_NIGHTS = 2


class HyggeLive(MockTravel):
    def __init__(self, middleware_url: str, data_dir=DATA_DIR, today: date | None = None) -> None:
        super().__init__(data_dir=data_dir, today=today)
        self.mw = middleware_url.rstrip("/")
        self._overlay_live_cabins()

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
        """Refresh price, photos, gallery, area, and booking URL from ``/api/cabins`` onto
        the static products, keeping the catalog's long copy. Silent no-op if unreachable."""
        data = self._get("/api/cabins")
        if not data:
            logger.warning("no live cabin data; serving the static catalog")
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

        # Map available cabins to their catalog products and their live nightly price.
        live_price: dict[str, float] = {}
        available: list = []
        for cabin in avail.get("available_cabins", []):
            slug = _ID_TO_SLUG.get(cabin.get("id"))
            product = self.products.get(slug) if slug else None
            if product is None:
                continue
            available.append(product)
            if cabin.get("price_per_night"):
                live_price[slug] = float(cabin["price_per_night"])

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
            if product.product_id in live_price:
                product.price = live_price[product.product_id]
            if product.attributes.get("refundable") == "yes":
                product.attributes["free_cancellation_until"] = cancellation_deadline(
                    product.category, travel_date
                )
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
