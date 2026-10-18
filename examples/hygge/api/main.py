# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Osada Hygge example API: the mock cabin platform behind the shared storefront routes,
with the ``present_itinerary`` extension, and the supplier router under /api/merchant.

    uvicorn hygge.api.main:app --app-dir examples --reload --port 8004
"""

from __future__ import annotations

import os

from commerce_common.memory import InMemoryMemoryStore
from demo_common import REPO_ROOT, MemorySeeder, build_storefront_host, load_demo_env
from shopping_agent_runtime import ShoppingAgent

from .agent_config import build_shopping_config
from .booking import create_booking_router
from .discount_codes import OfferDesk, build_store
from .home import create_home_router
from .itinerary import build_itinerary_extension
from .live_hygge import build_backend
from .merchant import create_merchant_router
from .mock_travel import DATA_DIR
from .offers import ELIGIBLE_OFFERS_TOOL, HyggeToolExecutor, create_discount_admin_router

load_demo_env(DATA_DIR.parent)

# Live idobooking data when IDOBOOKING_MIDDLEWARE_URL is set, else the static catalog.
backend = build_backend()
# The discount codes mirrored from the idobooking panel: in the same Postgres as the event
# log when DATABASE_URL is set, else in memory for the run.
offer_desk = OfferDesk(build_store(os.environ.get("DATABASE_URL")), today=lambda: backend.today)
backend.offer_desk = offer_desk
agent = ShoppingAgent(
    backend=backend,
    skills_dir=REPO_ROOT / "shopping-agent" / "skills",
    config=build_shopping_config(),
    memory_store=InMemoryMemoryStore(),
    extra_presentation_tools=[build_itinerary_extension()],
    extra_tools=[ELIGIBLE_OFFERS_TOOL],
    executor_class=HyggeToolExecutor,
)
host = build_storefront_host(
    title="Osada Hygge demo API",
    example_root=DATA_DIR.parent,
    backend=backend,
    agent=agent,
    memory_seeder=MemorySeeder(DATA_DIR / "memory-seed.json"),
    on_startup=[offer_desk.store.open],
    on_shutdown=[offer_desk.store.close],
)
# offer_proposed and offer_handoff rows go to the same log as the rest of the traffic.
offer_desk.bind(host.events)
app = host.app
app.include_router(create_merchant_router(backend, InMemoryMemoryStore()), prefix="/api/merchant")
# The stay panel's empty state (public) and the operator's code table (ADMIN_TOKEN).
app.include_router(create_home_router(backend, offer_desk), prefix="/api")
app.include_router(create_discount_admin_router(offer_desk), prefix="/api/admin")
# Optional "book with the assistant" path (idobooking reservations/add); dormant until
# IDOBOOKING_API_LOGIN/PASSWORD are set. Self-service booking via the widget needs none of it.
app.include_router(create_booking_router(), prefix="/api")
