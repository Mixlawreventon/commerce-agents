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
        brand_voice="warm, calm, and quietly Scandinavian — a host who loves the forest and the quiet",
        domain_search_notes=(
            "Cabins are date-bound: when the guest has named dates, pass the check-in "
            "date as an ISO filters.attributes['travel_date'] on every search — results "
            "and prices are quotes for those nights, not catalog constants. Prices are "
            "per night in Polish zloty (PLN). Ask how many people are coming and pass the "
            "head count as filters.attributes['guests']: a child counts the same as an "
            "adult, except a baby under one year sleeping with its parents, who is not "
            "counted at all."
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
