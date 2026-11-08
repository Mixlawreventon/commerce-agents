# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""What a live card carries: idobooking's figures, never the fixtures' stand-ins."""

from __future__ import annotations

from datetime import date

from hygge.api.live_hygge import HyggeLive
from shopping_agent import SearchFilters, ShoppingSessionContext

TODAY = date(2026, 11, 8)


class FullyBooked(HyggeLive):
    """The middleware answers: nothing free for these dates, no other data."""

    def _get(self, path, params=None):
        return None

    async def _aget(self, path, params=None):
        if path == "/api/availability":
            return {"available_cabins": []}
        return None


async def test_a_taken_weekend_shows_no_fixture_strip_cutoff_or_room_count():
    backend = FullyBooked("http://middleware.invalid", today=TODAY)
    session = ShoppingSessionContext(session_id="s-1", user_id="u-1")
    results = await backend.search_products(
        session,
        "domek z jacuzzi",
        SearchFilters(attributes={"travel_date": "2026-11-20", "nights": "2"}),
    )
    assert results and all(not product.in_stock for product in results)
    for product in results:
        for key in (
            "date_flex",
            "free_cancellation_until",
            "units_left_for_dates",
            "typical_rate_band",
        ):
            assert key not in product.attributes, key
        assert product.attributes["quoted_for"] == "2026-11-20..2026-11-22"
        assert product.attributes["booking_url"].startswith("https://client9681.idobooking.com/")


async def test_the_catalog_band_is_gone_from_every_live_product():
    backend = FullyBooked("http://middleware.invalid", today=TODAY)
    assert all("typical_rate_band" not in p.attributes for p in backend.products.values())
