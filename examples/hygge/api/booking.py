# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Optional "book with the assistant" path for Osada Hygge.

Creates a reservation directly in idobooking via the Administration Panel API
(``reservations/add``); online payment is left to idobooking/idopayments (the guest gets a
payment link for a ``waitingForPayment`` reservation). The self-service path (opening the
cabin's idobooking widget) needs none of this and always works.

Enabled only when Admin API credentials are present, so the store runs fine without them:

    IDOBOOKING_API_LOGIN         panel API login (systemLogin)
    IDOBOOKING_API_PASSWORD      panel API key (systemKey)
    IDOBOOKING_ADMIN_DOMAIN      default "client9681.idosell.com"
    IDOBOOKING_API_VERSION       default "36"
    IDOBOOKING_RESERVATION_STATUS  default "unconfirmed" — set to "waitingForPayment" to go live

Creating a reservation is a write to the live booking system, so the endpoint is a
deliberate, explicit action (the guest confirms), not something the model calls on its own.
"""

from __future__ import annotations

import logging
import os

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger("hygge.booking")

# Catalog product id -> idobooking offer/object id (the five real cabins).
_SLUG_TO_ID = {"HY-FIKA": 12, "HY-LAGOM": 13, "HY-GRON": 14, "HY-HYGGELIG": 15, "HY-LYKKE": 17}


def _creds() -> tuple[str, str] | None:
    login = os.environ.get("IDOBOOKING_API_LOGIN", "").strip()
    key = os.environ.get("IDOBOOKING_API_PASSWORD", "").strip()
    return (login, key) if login and key else None


def booking_configured() -> bool:
    return _creds() is not None


class Guest(BaseModel):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=160)
    phone: str = Field(default="", max_length=40)


class BookRequest(BaseModel):
    product_id: str = Field(min_length=1, max_length=40)
    date_from: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    date_to: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    adults: int = Field(default=2, ge=1, le=12)
    children: int = Field(default=0, ge=0, le=12)
    price: float | None = Field(default=None, ge=0)
    guest: Guest


def _admin_url(gateway: str, method: str) -> str:
    domain = os.environ.get("IDOBOOKING_ADMIN_DOMAIN", "client9681.idosell.com").strip()
    version = os.environ.get("IDOBOOKING_API_VERSION", "36").strip()
    return f"https://{domain}/api/{gateway}/{method}/{version}/json"


async def auth_check() -> dict:
    """Read-only probe of the Admin API credentials via ``payments/getPaymentForms`` (no
    reservation is created). Confirms login/key before attempting any write."""
    creds = _creds()
    if creds is None:
        return {"ok": False, "configured": False}
    login, key = creds
    payload = {"authenticate": {"systemLogin": login, "systemKey": key}}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(_admin_url("payments", "getPaymentForms"), json=payload)
            body = resp.json()
    except Exception as error:
        return {"ok": False, "message": str(error)}
    result = (body or {}).get("result", body) or {}
    errors = result.get("errors") or {}
    if errors.get("faultCode"):
        return {"ok": False, "fault": errors, "raw": body}
    return {"ok": True, "payment_forms": result.get("results"), "raw": body}


async def create_reservation(req: BookRequest) -> dict:
    """Call idobooking ``reservations/add``. Returns a normalized result dict; on any
    problem returns ``{ok: False, ...}`` with the raw response for diagnosis."""
    creds = _creds()
    if creds is None:
        return {"ok": False, "configured": False, "message": "Booking is not configured."}
    cabin_id = _SLUG_TO_ID.get(req.product_id)
    if cabin_id is None:
        return {"ok": False, "message": f"Unknown cabin {req.product_id}."}

    login, key = creds
    status = os.environ.get("IDOBOOKING_RESERVATION_STATUS", "unconfirmed").strip()
    # Only notify the guest for a real (live) booking; a test reservation stays silent.
    notify = "y" if status == "waitingForPayment" else "n"
    payload = {
        "authenticate": {"systemLogin": login, "systemKey": key},
        "params": {
            "reservations": [
                {
                    "dateFrom": req.date_from,
                    "dateTo": req.date_to,
                    "price": req.price,
                    "status": status,
                    "currency": "PLN",
                    "notify": notify,
                    "internalSource": "other",
                    "clientData": {
                        "type": "person",
                        "firstName": req.guest.first_name,
                        "lastName": req.guest.last_name,
                        "email": req.guest.email,
                        "phone": req.guest.phone,
                        "language": "pol",
                        "currency": "PLN",
                    },
                    "packages": [
                        {
                            "items": [
                                {
                                    "objectId": cabin_id,
                                    "price": req.price,
                                    "numberOfAdults": req.adults,
                                    "numberOfBigChildren": req.children,
                                    "numberOfSmallChildren": 0,
                                }
                            ]
                        }
                    ],
                }
            ]
        },
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(_admin_url("reservations", "add"), json=payload)
            body = resp.json()
    except Exception as error:
        logger.warning("reservations/add call failed", exc_info=True)
        return {"ok": False, "message": f"Could not reach the booking system: {error}"}

    # Responses are wrapped: {"result": {"reservations":[{"success":true,"reservationId":123}]}}
    result = (body or {}).get("result", body) or {}
    rows = result.get("reservations") or []
    row = rows[0] if rows else {}
    if row.get("success") and row.get("reservationId"):
        return {
            "ok": True,
            "reservation_id": row["reservationId"],
            "status": status,
            "raw": body,
        }
    return {"ok": False, "message": "idobooking did not confirm the reservation.", "raw": body}


async def cancel_reservation(reservation_id: int) -> dict:
    """Cancel a reservation via ``reservations/editStatus`` (used to clean up test bookings)."""
    creds = _creds()
    if creds is None:
        return {"ok": False, "configured": False}
    login, key = creds
    payload = {
        "authenticate": {"systemLogin": login, "systemKey": key},
        "reservations": [{"reservationId": reservation_id, "status": "canceled", "notify": "n"}],
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(_admin_url("reservations", "editStatus"), json=payload)
            body = resp.json()
    except Exception as error:
        return {"ok": False, "message": str(error)}
    result = (body or {}).get("result", body) or {}
    rows = result.get("reservations") or []
    ok = bool(rows and rows[0].get("success"))
    return {"ok": ok, "raw": body}


class CancelRequest(BaseModel):
    reservation_id: int = Field(ge=1)


def create_booking_router() -> APIRouter:
    router = APIRouter()

    @router.get("/book/config")
    async def config() -> dict:
        """Whether the assistant-booking path is available (drives the storefront UI)."""
        return {"configured": booking_configured()}

    @router.get("/book/auth-check")
    async def auth() -> dict:
        """Read-only check that the Admin API credentials work (no reservation created)."""
        return await auth_check()

    @router.get("/book/egress-ip")
    async def egress_ip() -> dict:
        """This service's outbound IP — to allowlist it in idobooking's API access, if the
        panel restricts API calls by IP."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                v4 = (await client.get("https://api.ipify.org")).text.strip()
            return {"egress_ip": v4}
        except Exception as error:
            return {"error": str(error)}

    @router.post("/book")
    async def book(request: BookRequest) -> dict:
        return await create_reservation(request)

    @router.post("/book/cancel")
    async def cancel(request: CancelRequest) -> dict:
        return await cancel_reservation(request.reservation_id)

    return router
