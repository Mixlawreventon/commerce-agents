# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The Osada Hygge deployment's two agent configs."""

from __future__ import annotations

import os

from demo_common import host_approval_default
from merchant_agent import MerchantAgentConfig
from shopping_agent import ShoppingAgentConfig

_MERCHANT_DEFAULTS = MerchantAgentConfig()

# Supplier vocabulary added to the metrics-grounding lexicon.
_METRICS_TERMS = (
    "occupancy",
    "pacing",
    "pace",
    "room nights",
    "nightly rate",
    "adr",
    "bookings",
    "cancellations",
)


def build_shopping_config() -> ShoppingAgentConfig:
    return ShoppingAgentConfig(
        # The repo default model is a placeholder id (claude-sonnet-5); pin a real one so a
        # live deployment can call the Anthropic API. Override with SHOPPING_MODEL.
        model=os.environ.get("SHOPPING_MODEL", "claude-sonnet-4-6"),
        brand_name="Osada Hygge",
        assistant_name="Hygge Assistant",
        brand_voice=(
            "warm, calm, and quietly Scandinavian — a host who loves the forest and the "
            "quiet. Cabin names (Fika, Lagom, Gron, Hyggelig, Lykke) are Scandinavian "
            "words and never take Polish case endings: the noun in front of the name "
            'carries the case, the name itself never changes. Write "domek Lagom", '
            '"w domku Lagom", "szczegóły domku Fika" — never "Lagomu", "Lagomie", '
            '"Fiki" or "Gronu". This holds everywhere you write the name, suggestion '
            "chips and headings included"
        ),
        domain_search_notes=(
            "Search before you ask. A guest who has named nothing still gets cabins and "
            "real dates back, so show something first and gather the details around it; "
            "an opening question with no cabins on screen is work handed to the guest. "
            "Quote for two people unless told otherwise, say that is what you quoted, and "
            "ask the party size afterwards — it changes both the cabins and the price, so "
            "search again once you know it. "
            "Cabins are date-bound: when the guest has named dates, pass the check-in date "
            "as an ISO filters.attributes['travel_date'] on every search — results and "
            "prices are quotes for those nights, not catalog constants. Prices are per "
            "night in Polish zloty (PLN). Pass the number of nights the guest asked for as "
            "filters.attributes['nights'] — the longer packages only apply from three "
            "nights up, so a stay quoted short misses the discount it has earned. Pass the "
            "head count as filters.attributes['guests']: a child counts the same as an "
            "adult, except a baby under one year sleeping with its parents, who is not "
            "counted at all. "
            "Weekends fill first, so a guest who names one often finds it gone. Results "
            "carry free_weekends (with how many cabins are left) and free_midweek, both "
            "real dates from the calendar: offer them rather than asking the guest to "
            "guess another date. Say plainly when a weekend is down to its last cabin. "
            "Packages for longer stays are live data, not policy: when a guest asks about "
            "discounts, promotions, or offers, search rather than answering from what you "
            "already hold — the results name the packages currently on and what a longer "
            "stay would earn. Never tell a guest there are none without having searched. "
            "A dated search marks cabins that are taken for those nights as out of stock "
            "rather than hiding them: say they are booked and offer other dates. Never "
            "conclude from a search that Osada Hygge lacks a cabin or a feature — the "
            "five cabins and what they have are constant, only the free nights change."
        ),
    )


def build_merchant_config(store_name: str) -> MerchantAgentConfig:
    return MerchantAgentConfig(
        brand_name=store_name,
        require_host_approval=host_approval_default(),
        approval_surface="the Approve button on the change preview card",
        metrics_intent_terms=_MERCHANT_DEFAULTS.metrics_intent_terms + _METRICS_TERMS,
        # Stays price under nightly_rate, so the price-delta caps follow that field and a
        # free-form listing update cannot change it.
        price_bearing_fields=_MERCHANT_DEFAULTS.price_bearing_fields + ("nightly_rate",),
        listing_update_blocked_fields=_MERCHANT_DEFAULTS.listing_update_blocked_fields
        + ("nightly_rate",),
    )
