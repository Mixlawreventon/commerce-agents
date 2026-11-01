# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""``present_calendar``: the month grid read off the booking system's calendar, and the
extension that renders it."""

from __future__ import annotations

from datetime import date

import pytest

from commerce_common.presentation import EnrichmentContext, run_presentation
from hygge.api.calendar import build_calendar_extension, calendar_from_pricing
from hygge.api.live_hygge import HyggeLive
from shopping_agent import ShoppingAgentConfig, ShoppingSessionContext, ShoppingSessionState

TODAY = date(2026, 11, 10)


def _days(free: dict[str, float | None]) -> dict:
    return {day: {"available": price is not None, "price": price} for day, price in free.items()}


PRICING = {
    "cabins": [
        {
            "id": 12,
            "days": _days(
                {"2026-11-09": 499, "2026-11-10": 499, "2026-11-11": None, "2026-11-12": 549}
            ),
        },
        {
            "id": 14,
            "days": _days(
                {"2026-11-09": None, "2026-11-10": 449, "2026-11-11": 449, "2026-11-12": None}
            ),
        },
    ]
}


def test_one_cabin_shows_its_own_nights_and_prices():
    [month] = calendar_from_pricing(
        PRICING, today=TODAY, first=date(2026, 11, 1), months=1, cabin_id=12
    )
    assert month["month"] == "2026-11" and len(month["days"]) == 30
    by_day = {day["iso"]: day for day in month["days"]}
    # Yesterday is past, whatever the calendar says.
    assert by_day["2026-11-09"]["past"] and not by_day["2026-11-09"]["available"]
    assert by_day["2026-11-10"] == {
        "iso": "2026-11-10",
        "day": 10,
        "weekday": 2,
        "past": False,
        "available": True,
        "price": 499,
    }
    assert not by_day["2026-11-11"]["available"] and by_day["2026-11-11"]["price"] is None
    # A night the calendar does not cover is simply not free.
    assert not by_day["2026-11-20"]["available"] and "cabins_free" not in by_day["2026-11-20"]


def test_the_property_view_counts_free_cabins_and_takes_the_lowest_price():
    [month] = calendar_from_pricing(
        PRICING, today=TODAY, first=date(2026, 11, 1), months=1, cabin_id=None
    )
    by_day = {day["iso"]: day for day in month["days"]}
    assert by_day["2026-11-10"]["cabins_free"] == 2 and by_day["2026-11-10"]["price"] == 449
    assert by_day["2026-11-11"]["cabins_free"] == 1 and by_day["2026-11-11"]["price"] == 449
    assert by_day["2026-11-09"]["cabins_free"] == 0


def test_two_months_from_a_later_start_roll_the_year():
    months = calendar_from_pricing(
        {"cabins": []}, today=TODAY, first=date(2026, 12, 1), months=2, cabin_id=None
    )
    assert [month["month"] for month in months] == ["2026-12", "2027-01"]
    assert months[1]["days"][0]["weekday"] == 5  # 1 January 2027 is a Friday


class OfflineLive(HyggeLive):
    def __init__(self) -> None:
        self.calls: list[dict] = []
        super().__init__("http://middleware.invalid", today=TODAY)

    def _get(self, path, params=None):
        return None

    async def _aget(self, path, params=None):
        self.calls.append({"path": path, **(params or {})})
        return PRICING if path == "/api/calendar-pricing" else None


async def _render(backend, tool_input: dict, spec=None):
    spec = spec or build_calendar_extension(backend)
    context = EnrichmentContext(
        backend=backend,
        config=ShoppingAgentConfig(brand_name="Osada Hygge"),
        session=ShoppingSessionContext(session_id="s-1", user_id="u-1"),
        state=ShoppingSessionState(),
    )
    return await run_presentation(spec, tool_input, context, "Displayed to the customer.")


async def test_the_card_is_filled_in_from_the_live_calendar_and_cached():
    backend = OfflineLive()
    spec = build_calendar_extension(backend)
    outcome = await _render(backend, {"cabin_id": "hy-fika", "title": "Fika w listopadzie"}, spec)
    assert not outcome.is_error
    [event] = outcome.events
    assert event.data["component"] == "calendar"
    payload = event.data["payload"]
    assert payload["cabin"] == {"product_id": "HY-FIKA", "name": "Fika"}
    assert payload["guests"] == 2 and payload["months"][0]["month"] == "2026-11"
    assert "2 free nights" in outcome.result_text
    # A second card in the same party reads nothing new; a bigger party does.
    await _render(backend, {"months": 1}, spec)
    await _render(backend, {"guests": 4}, spec)
    assert [
        call["adults"] for call in backend.calls if call["path"] == "/api/calendar-pricing"
    ] == [2, 4]


@pytest.mark.parametrize(
    ("tool_input", "message"),
    [({"cabin_id": "HY-NOPE"}, "No cabin"), ({"month": "2027-09"}, "next 6 months")],
)
async def test_an_unknown_cabin_or_a_far_month_is_refused_with_a_reason(tool_input, message):
    outcome = await _render(OfflineLive(), tool_input)
    assert outcome.is_error and message in outcome.result_text


async def test_without_live_data_the_fixtures_window_fills_the_card():
    class Static(OfflineLive):
        async def _aget(self, path, params=None):
            return None

    outcome = await _render(Static(), {})
    payload = outcome.events[0].data["payload"]
    assert payload["months"][0]["days"][10]["available"] is True
    assert payload["months"][0]["days"][10]["cabins_free"] == 5
