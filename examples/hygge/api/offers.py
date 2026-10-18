# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The discount codes on the assistant's side: the ``get_eligible_offers`` tool the model
calls, the executor that handles it, and the admin routes an operator keeps the codes
with. The rules of which code a stay earns are in ``discount_codes``; this module is the
seam between them and the agent, the host, and the panel."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from commerce_common.streaming import ToolOutcome
from demo_common import require_admin
from shopping_agent.executor import ShoppingToolExecutor

from .discount_codes import (
    CONVERSATION_SIGNALS,
    DiscountCode,
    DiscountCodeDraft,
    OfferDesk,
)

TOOL_NAME = "get_eligible_offers"

ELIGIBLE_OFFERS_TOOL: dict[str, Any] = {
    "name": TOOL_NAME,
    "description": (
        "The discount codes this stay earns right now, best first, each with its "
        "discount_label (the only wording of its value you may use) and a note on how to "
        "offer it. Call it once the guest has dates on the table and you are about to "
        "name a price: after the full price and what it includes, before any code. Pass "
        "every signal the conversation has shown; a code that is not announceable only "
        "comes back after one. An empty list means there is no code to offer: say nothing "
        "about codes. Never invent a code or a value, and never promise more than the "
        "label says."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "arrival": {
                "type": "string",
                "description": "Check-in date, ISO YYYY-MM-DD.",
            },
            "departure": {
                "type": "string",
                "description": "Check-out date, ISO YYYY-MM-DD.",
            },
            "cabin_id": {
                "type": "string",
                "description": (
                    "The cabin the guest is weighing, as a product_id from this session's "
                    "results; omit while no cabin is chosen."
                ),
            },
            "guest_signals": {
                "type": "array",
                "items": {"type": "string", "enum": sorted(CONVERSATION_SIGNALS)},
                "maxItems": 3,
                "description": (
                    "What the conversation has shown: returning_guest (they stayed before), "
                    "price_hesitation (the price gave them pause), asked_for_discount (they "
                    "asked for a discount or a code)."
                ),
            },
        },
        "required": ["arrival", "departure"],
        "additionalProperties": False,
    },
}


def _iso_date(value: Any, name: str) -> date:
    try:
        return date.fromisoformat(str(value or "").strip())
    except ValueError:
        raise ValueError(f"{name} must be an ISO date (YYYY-MM-DD)") from None


def offer_payload(code: DiscountCode) -> dict[str, Any]:
    """What the model hears about one code; counters and windows it cannot act on stay
    out."""
    payload: dict[str, Any] = {"code": code.code, "discount_label": code.discount_label}
    if code.notes_for_agent:
        payload["how_to_offer"] = code.notes_for_agent
    if code.stay_from or code.stay_to:
        payload["stay_window"] = (
            f"{code.stay_from.isoformat() if code.stay_from else '...'}"
            f"..{code.stay_to.isoformat() if code.stay_to else '...'}"
        )
    if code.valid_to:
        payload["book_by"] = code.valid_to.isoformat()
    return payload


class HyggeToolExecutor(ShoppingToolExecutor):
    """The shopping executor plus ``get_eligible_offers``, served by the backend's
    ``offer_desk`` (an :class:`OfferDesk`); a backend without one answers that there is
    no code to offer."""

    def handlers(self):  # type: ignore[override]
        return {**super().handlers(), TOOL_NAME: self._get_eligible_offers}

    def _cabin_id(self, raw: Any) -> str | None:
        """A product id from this session resolves to its idobooking cabin id; anything
        else is taken as the cabin id itself."""
        value = str(raw or "").strip()
        if not value:
            return None
        product = self._state.seen_products.get(value)
        if product is None:
            products = getattr(self._backend, "products", {})
            product = products.get(value)
        if product is not None:
            return product.attributes.get("cabin_id") or value
        return value

    async def _get_eligible_offers(self, tool_input: dict[str, Any]) -> ToolOutcome:
        desk: OfferDesk | None = getattr(self._backend, "offer_desk", None)
        try:
            arrival = _iso_date(tool_input.get("arrival"), "arrival")
            departure = _iso_date(tool_input.get("departure"), "departure")
        except ValueError as invalid:
            return ToolOutcome.error(f"{TOOL_NAME}: {invalid}. Adjust and call it again.")
        if departure <= arrival:
            return ToolOutcome.error(f"{TOOL_NAME}: departure must be after arrival.")
        signals = [
            str(signal)
            for signal in tool_input.get("guest_signals") or []
            if str(signal) in CONVERSATION_SIGNALS
        ]
        if desk is None:
            return self._fenced({"offers": [], "note": "No discount codes are configured."})
        picks = await desk.propose(
            self._session.session_id,
            self._session.user_id,
            arrival,
            departure,
            self._cabin_id(tool_input.get("cabin_id")),
            signals,
        )
        payload: dict[str, Any] = {"offers": [offer_payload(code) for code in picks]}
        if not picks:
            payload["note"] = "No code applies to this stay; do not mention codes."
        else:
            payload["note"] = (
                "Name at most one code per reply, with its discount_label as the value. "
                "The guest types it into the booking form; the checkout card shows it."
            )
        return self._fenced(payload)


def admin_payload(code: DiscountCode) -> dict[str, Any]:
    return {
        **code.model_dump(mode="json"),
        "conversion_pct": code.conversion_pct,
    }


def create_discount_admin_router(desk: OfferDesk) -> APIRouter:
    """``/discount-codes``: the operator's CRUD, behind the same ``ADMIN_TOKEN`` as the
    traffic read-back. Mounted under ``/api/admin``."""
    router = APIRouter(dependencies=[Depends(require_admin)])

    @router.get("/discount-codes")
    async def list_codes() -> dict:
        return {"codes": [admin_payload(code) for code in await desk.store.list()]}

    @router.post("/discount-codes")
    async def create_code(draft: DiscountCodeDraft) -> dict:
        if await desk.store.get(draft.code) is not None:
            raise HTTPException(status_code=409, detail="A code with this name already exists")
        return {"code": admin_payload(await desk.store.upsert(draft))}

    @router.put("/discount-codes/{code}")
    async def replace_code(code: str, draft: DiscountCodeDraft) -> dict:
        if draft.code != code.strip().upper():
            raise HTTPException(status_code=400, detail="The code in the path and body differ")
        return {"code": admin_payload(await desk.store.upsert(draft))}

    @router.delete("/discount-codes/{code}")
    async def delete_code(code: str) -> dict:
        if not await desk.store.delete(code):
            raise HTTPException(status_code=404, detail="No such code")
        return {"ok": True}

    return router
