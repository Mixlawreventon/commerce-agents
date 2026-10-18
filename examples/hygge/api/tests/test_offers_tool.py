# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""``get_eligible_offers`` on the executor, the tool in the deployment's tool list, the
code on the checkout card, and the home overview."""

from __future__ import annotations

import json
from datetime import date

import pytest

from commerce_common.skills import SkillRegistry
from hygge.api.discount_codes import DiscountCode, DiscountCodeStore, OfferDesk
from hygge.api.home import openings_from_calendar, promotions_from_payload
from hygge.api.live_hygge import HyggeLive
from hygge.api.mock_travel import MockTravel
from hygge.api.offers import ELIGIBLE_OFFERS_TOOL, TOOL_NAME, HyggeToolExecutor
from shopping_agent import (
    Cart,
    CartItem,
    ShoppingAgentConfig,
    ShoppingSessionContext,
    ShoppingSessionState,
)
from shopping_agent.tools.registry import build_tools

TODAY = date(2026, 10, 18)


class OfflineLive(HyggeLive):
    """The live backend with the middleware unreachable: static catalog, live rules."""

    def _get(self, path, params=None):
        return None

    async def _aget(self, path, params=None):
        return None


def fenced_json(text: str) -> dict:
    start, end = text.index("{"), text.rindex("}")
    return json.loads(text[start : end + 1])


@pytest.fixture
def backend() -> MockTravel:
    backend = OfflineLive("http://middleware.invalid", today=TODAY)
    backend.offer_desk = OfferDesk(
        DiscountCodeStore(
            [
                DiscountCode(
                    code="JESIEN15",
                    discount_label="-15%",
                    announceable=True,
                    notes_for_agent="podkreśl, że tylko do niedzieli",
                ),
                DiscountCode(
                    code="FIKA",
                    discount_label="-100 zł",
                    announceable=True,
                    trigger_signals=["cabins:[12]"],
                    priority=1,
                ),
            ]
        ),
        today=TODAY,
    )
    return backend


def executor(backend: MockTravel, state: ShoppingSessionState | None = None) -> HyggeToolExecutor:
    return HyggeToolExecutor(
        backend=backend,
        config=ShoppingAgentConfig(brand_name="Osada Hygge"),
        skills=SkillRegistry([]),
        session=ShoppingSessionContext(session_id="s-1", user_id="u-1"),
        state=state or ShoppingSessionState(),
    )


async def test_the_tool_names_the_codes_the_stay_earns_with_label_and_note(backend):
    outcome = await executor(backend).execute(
        TOOL_NAME, {"arrival": "2026-10-23", "departure": "2026-10-25", "cabin_id": "HY-FIKA"}
    )
    assert not outcome.is_error
    payload = fenced_json(outcome.result_text)
    assert [offer["code"] for offer in payload["offers"]] == ["FIKA", "JESIEN15"]
    assert payload["offers"][1] == {
        "code": "JESIEN15",
        "discount_label": "-15%",
        "how_to_offer": "podkreśl, że tylko do niedzieli",
    }


async def test_the_tool_answers_bad_dates_and_a_missing_desk_plainly(backend):
    outcome = await executor(backend).execute(
        TOOL_NAME, {"arrival": "piątek", "departure": "2026-10-25"}
    )
    assert outcome.is_error and "ISO date" in outcome.result_text
    outcome = await executor(backend).execute(
        TOOL_NAME, {"arrival": "2026-10-25", "departure": "2026-10-25"}
    )
    assert outcome.is_error
    backend.offer_desk = None
    outcome = await executor(backend).execute(
        TOOL_NAME, {"arrival": "2026-10-23", "departure": "2026-10-25"}
    )
    assert fenced_json(outcome.result_text)["offers"] == []


def test_the_tool_joins_the_list_after_the_extensions_with_a_status_line():
    config = ShoppingAgentConfig(brand_name="Osada Hygge")
    tools = build_tools(config, [], extra_tools=[ELIGIBLE_OFFERS_TOOL])
    assert tools[-1]["name"] == TOOL_NAME
    assert list(tools[-1]["input_schema"]["properties"])[0] == "status"
    assert build_tools(config, [], extra_tools=[ELIGIBLE_OFFERS_TOOL]) == tools
    with pytest.raises(ValueError, match="collides"):
        build_tools(config, [], extra_tools=[{**ELIGIBLE_OFFERS_TOOL, "name": "search_products"}])


async def test_checkout_carries_the_proposed_code_and_counts_the_handoff(backend):
    session = ShoppingSessionContext(session_id="s-1", user_id="u-1")
    await executor(backend).execute(TOOL_NAME, {"arrival": "2026-10-23", "departure": "2026-10-25"})
    backend._session_dates["s-1"] = "2026-10-23"
    cart = Cart(
        items=[CartItem(product_id="HY-LAGOM", title="Lagom", price=499.0, quantity=2)],
        currency="PLN",
    )
    handoffs = await backend.checkout_handoff(session, cart)
    assert len(handoffs) == 1
    assert handoffs[0].promo_code == "JESIEN15" and handoffs[0].promo_label == "-15%"
    assert "start_date/2026-10-23/end_date/2026-10-25" in handoffs[0].url
    assert (await backend.offer_desk.store.get("JESIEN15")).usage_handoff == 1
    # A reset forgets the session's offers: the next card carries none.
    backend.reset_session("s-1")
    assert (await backend.checkout_handoff(session, cart))[0].promo_code is None


def test_openings_name_the_next_weekends_and_midweek_stays_with_a_price():
    def days(free: dict[str, float]) -> dict:
        return {day: {"available": True, "price": price} for day, price in free.items()}

    calendar = {
        "cabins": [
            {
                "id": 12,
                "days": days(
                    {"2026-10-23": 599, "2026-10-24": 549, "2026-10-26": 499, "2026-10-27": 499}
                ),
            },
            {
                "id": 14,
                "days": days(
                    {"2026-10-23": 499, "2026-10-24": 499, "2026-10-30": 499, "2026-10-31": 499}
                ),
            },
        ]
    }
    openings = openings_from_calendar(calendar, TODAY)
    assert [
        (o["kind"], o["arrival"], o["departure"], o["price_from"], o["cabins_left"])
        for o in openings
    ] == [
        ("weekend", "2026-10-23", "2026-10-25", 998, 2),
        ("midweek", "2026-10-26", "2026-10-28", 998, 1),
        ("weekend", "2026-10-30", "2026-11-01", 998, 1),
    ]
    assert openings_from_calendar({"cabins": []}, TODAY) == []


def test_promotions_pass_through_tolerantly():
    payload = {
        "promotions": [
            {"name": " Jesień ", "description": "", "date_from": "2026-10-01"},
            {"id": 3},
            "x",
        ]
    }
    assert promotions_from_payload(payload) == [
        {
            "kind": "promotion",
            "title": "Jesień",
            "detail": None,
            "stay_from": "2026-10-01",
            "stay_to": None,
        }
    ]
