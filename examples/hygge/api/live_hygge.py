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
from typing import Any

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

from .mock_travel import (
    _DEFAULT_GUESTS,
    DATA_DIR,
    MockTravel,
    _guest_count,
    _night_count,
    _travel_date,
)

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
# idobooking is a separate property with its own analytics, and a guest arriving there has
# crossed a domain boundary: without these the visit lands in its "direct" bucket and the
# assistant looks like it sent nobody. Standard UTM keys, so any analytics reads them.
_UTM = "utm_source=osada-hygge&utm_medium=assistant&utm_campaign=hygge-agent"


def _tagged(url: str) -> str:
    """The widget URL with the campaign tags a booking system's analytics expects."""
    if not url or "utm_source=" in url:
        return url
    return f"{url}{'&' if '?' in url else '?'}{_UTM}"


# A dated search only knows the arrival; quote this many nights to check availability/price.
_DEFAULT_QUOTE_NIGHTS = 2


def _read_offers(offers: list[dict], nights: int) -> dict[str, Any]:
    """The cheapest nightly rate per rate type, and the named package the best price uses.

    idobooking quotes one entry per bookable offer: a season rate carrying a null
    ``promotion_id``, plus every package the stay is long enough to earn (a longer stay
    earns a bigger discount, e.g. "Sezon na grzyby 2026 - 5 nocy - 20%"). Several entries
    usually share one rate type, so each type keeps its cheapest rather than whichever
    the API happened to list last.
    """
    priced = [offer for offer in offers if offer.get("price")]
    rates: dict[str, float] = {}
    for offer in priced:
        kind = offer.get("type")
        if kind not in ("refundable", "nonrefundable"):
            continue
        nightly = round(float(offer["price"]) / nights)
        if kind not in rates or nightly < rates[kind]:
            rates[kind] = nightly

    package: dict[str, Any] | None = None
    if priced:
        best = min(priced, key=lambda offer: float(offer["price"]))
        base = next((offer for offer in priced if offer.get("promotion_id") is None), None)
        # Only a named package that actually beats the season rate is worth showing.
        if best.get("promotion_id") is not None and base is not None:
            before, after = float(base["price"]), float(best["price"])
            if after < before:
                package = {
                    "name": str(best.get("name", "")).strip(),
                    "rate_before": round(before / nights),
                    "discount_pct": round((before - after) / before * 100),
                }
    return {"rates": rates, "package": package}


# A span long enough to qualify for every package, so an undersized stay still learns what
# a longer one would earn. Packages top out at five nights.
_LADDER_SPAN_NIGHTS = 7
# Near-term dates are often fully booked and quote no price at all, so an undated search
# steps forward until the property quotes one rather than concluding it runs no packages.
_LADDER_PROBE_OFFSETS = (7, 21, 45)


def _ladder_from_pricing(payload: dict) -> list[dict[str, Any]]:
    """Every named package active for a date, as ``{name, discount_pct}``, deepest first.

    The discount is read off whichever cabin quotes both a season rate and the package, so
    the ladder states the customer's own percentages rather than any we compute a rate from.
    """
    ladder: dict[int, dict[str, Any]] = {}
    for cabin in payload.get("pricing", []):
        offers = [offer for offer in cabin.get("offers", []) if offer.get("total_price")]
        base = next((offer for offer in offers if offer.get("promotion_id") is None), None)
        if base is None:
            continue
        before = float(base["total_price"])
        for offer in offers:
            promotion_id = offer.get("promotion_id")
            after = float(offer["total_price"])
            if promotion_id is None or promotion_id in ladder or after >= before:
                continue
            ladder[promotion_id] = {
                "name": str(offer.get("name", "")).strip(),
                "discount_pct": round((before - after) / before * 100),
            }
    return sorted(ladder.values(), key=lambda entry: entry["discount_pct"], reverse=True)


# How far ahead to look, and how many options to name. More than a few is not a suggestion.
_SUGGEST_DAYS = 70
_SUGGEST_WEEKENDS = 3
_SUGGEST_MIDWEEK = 2


def _open_counts(payload: dict) -> dict[str, int]:
    """How many cabins are free on each day of the calendar."""
    counts: dict[str, int] = {}
    for cabin in payload.get("cabins", []):
        for day, state in (cabin.get("days") or {}).items():
            if isinstance(state, dict) and state.get("available"):
                counts[day] = counts.get(day, 0) + 1
    return counts


def _suggestions_from_calendar(payload: dict, today: date) -> dict[str, str]:
    """Concrete dates to offer: the next weekends with anything left, and the next midweek
    stretches.

    Merging every free day into one range is useless here — one cabin free on each of fifty
    days reads as "everything is open" when the weekends inside it are gone. The property
    fills Friday and Saturday first, so weekends are counted as whole Fri-Sun stays and
    named with how much is left; midweek is offered separately, where the choice is wide.
    """
    counts = _open_counts(payload)
    horizon = today + timedelta(days=_SUGGEST_DAYS)
    weekends: list[str] = []
    midweek: list[str] = []
    day = today
    while day <= horizon:
        iso = day.isoformat()
        free = counts.get(iso, 0)
        if day.weekday() == 4:  # Friday: a weekend stay needs Friday and Saturday
            saturday = (day + timedelta(days=1)).isoformat()
            together = min(free, counts.get(saturday, 0))
            if together and len(weekends) < _SUGGEST_WEEKENDS:
                cabins = "1 domek" if together == 1 else f"{together} domki"
                weekends.append(f"{iso}..{(day + timedelta(days=2)).isoformat()} ({cabins})")
        elif day.weekday() == 0 and free and len(midweek) < _SUGGEST_MIDWEEK:
            # Monday opening a stretch that reaches at least Thursday.
            nights = [(day + timedelta(days=n)).isoformat() for n in range(1, 4)]
            if all(counts.get(night) for night in nights):
                midweek.append(f"{iso}..{(day + timedelta(days=4)).isoformat()}")
        day += timedelta(days=1)
    found: dict[str, str] = {}
    if weekends:
        found["free_weekends"] = "; ".join(weekends)
    if midweek:
        found["free_midweek"] = "; ".join(midweek)
    return found


class HyggeLive(MockTravel):
    def __init__(self, middleware_url: str, data_dir=DATA_DIR, today: date | None = None) -> None:
        super().__init__(data_dir=data_dir, today=today)
        self.mw = middleware_url.rstrip("/")
        self.property: dict = {}
        # Last check-in date searched per session, so checkout can hand off a dated offer.
        self._session_dates: dict[str, str] = {}
        # Party size per session, so checkout hands off the same head count it quoted.
        self._session_guests: dict[str, int] = {}
        # Package ladders keyed by the date they were quoted from; one probe serves a date.
        self._ladders: dict[str, list[dict[str, Any]]] = {}
        # Dates worth offering, from the calendar, keyed by party size.
        self._stretches: dict[str, dict[str, str]] = {}
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

    async def _package_ladder(self, quoted_from: date, guests: int) -> list[dict[str, Any]]:
        """The packages active from a date, so a stay too short to earn one still sees what
        a longer stay would. Quoted once per date and party — the ladder is the same for
        every cabin, but a package is priced for the heads it covers."""
        key = f"{quoted_from.isoformat()}:{guests}"
        if key not in self._ladders:
            payload = await self._aget(
                "/api/pricing",
                {
                    "date_from": quoted_from.isoformat(),
                    "date_to": (quoted_from + timedelta(days=_LADDER_SPAN_NIGHTS)).isoformat(),
                    "adults": guests,
                },
            )
            self._ladders[key] = _ladder_from_pricing(payload) if payload else []
        return self._ladders[key]

    async def _suggestions(self, guests: int) -> dict[str, str]:
        """Dates worth offering, from the calendar. One call covers three months and is
        served from the middleware's own database, so it is cheap; cached per party."""
        key = str(guests)
        if key not in self._stretches:
            payload = await self._aget("/api/calendar-pricing", {"months": 3, "adults": guests})
            self._stretches[key] = (
                _suggestions_from_calendar(payload, self.today) if payload else {}
            )
        return self._stretches[key]

    async def _current_ladder(self, guests: int) -> list[dict[str, Any]]:
        """The packages on offer when no dates are on the table yet. Each probed date is
        cached, so the walk costs nothing after the first undated search."""
        for offset in _LADDER_PROBE_OFFSETS:
            ladder = await self._package_ladder(self.today + timedelta(days=offset), guests)
            if ladder:
                return ladder
        return []

    def _overlay_live_cabins(self) -> None:
        """Refresh price, photos, gallery, and area from ``/api/cabins`` onto the static
        products, keeping the catalog's long copy. The booking widget URL is set for every
        cabin from the id template, so the self-service path works even if the live call
        returns a partial list or fails."""
        for cabin_id, slug in _ID_TO_SLUG.items():
            product = self.products.get(slug)
            if product is not None:
                product.attributes["cabin_id"] = str(cabin_id)
                product.attributes["booking_url"] = _tagged(_WIDGET_URL.format(id=cabin_id))
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
                product.attributes["booking_url"] = _tagged(cabin["widget_url"])
            product.attributes["cabin_id"] = str(cabin.get("id", ""))
        logger.info("overlaid %d live cabins", len(data.get("cabins", [])))

    def _load_property(self) -> None:
        """Real contact and stay facts (address, phone, email, check-in/out) from the
        ``/api/agent-data`` property block, so the assistant answers with live values."""
        arrival = self.today + timedelta(days=30)
        # The endpoint wants a stay to quote; only the property block is read back, so the
        # dates and party here are a probe and carry no guest's numbers.
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
        guests = self._session_guests.get(session.session_id, _DEFAULT_GUESTS)
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
            url = self._booking_url(
                cabin_id, arrival, item.quantity, guests
            ) or product.attributes.get("booking_url")
            if url:
                handoffs.append(
                    CheckoutHandoff(url=url, label=f"Zarezerwuj w idobooking — {name}", seller=name)
                )
        return handoffs

    def _booking_url(
        self, cabin_id: str | None, arrival: str | None, nights: int, guests: int
    ) -> str | None:
        """A dated widget URL (cabin + dates + guests) when the check-in is known, else None
        so the caller falls back to the plain per-cabin URL."""
        if not cabin_id or not arrival:
            return None
        try:
            start = date.fromisoformat(arrival)
            end = start + timedelta(days=max(nights, 1))
        except ValueError:
            return None
        return _tagged(
            _WIDGET_URL_DATED.format(
                start=start.isoformat(), end=end.isoformat(), id=cabin_id, adults=guests
            )
        )

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _attach_suggestions(self, results: list[Product], found: dict[str, str]) -> None:
        """Dates to offer, on every card, so a guest whose weekend is gone is handed others
        rather than asked to guess again."""
        for product in results:
            for key, value in found.items():
                product.attributes[key] = value

    def _attach_ladder(self, results: list[Product], ladder: list[dict[str, Any]]) -> None:
        """Name the active packages on every card, whether or not this stay already earns
        one. A longer-stay discount only works as an invitation if a guest looking at two
        nights can see what five would cost, so the deepest package the stay has not
        reached yet rides along as ``package_next_*``."""
        if not ladder:
            return
        for product in results:
            product.attributes["package_offers"] = "; ".join(
                f"{entry['name']} (-{entry['discount_pct']}%)" for entry in ladder
            )
            earned = float(product.attributes.get("package_discount_pct") or 0)
            deeper = next(
                (entry for entry in ladder if entry["discount_pct"] > earned),
                None,
            )
            if deeper is not None:
                product.attributes["package_next_name"] = deeper["name"]
                product.attributes["package_next_pct"] = str(deeper["discount_pct"])

    async def search_products(
        self,
        session: ShoppingSessionContext,
        query: str,
        filters: SearchFilters | None = None,
        limit: int = 8,
    ) -> list[Product]:
        travel_date = _travel_date(filters) if filters is not None else None
        if travel_date is None:
            # No dates: rank the whole (live-priced) catalog, as the static backend does,
            # still naming the packages on offer from today.
            guests = _guest_count(filters)
            results = await super().search_products(session, query, filters, limit)
            self._attach_ladder(results, await self._current_ladder(guests))
            self._attach_suggestions(results, await self._suggestions(guests))
            return results

        # Remember the check-in so checkout can hand off a dated, ready-to-pay offer.
        self._session_dates[session.session_id] = travel_date.isoformat()
        # Quote the nights the guest actually plans: idobooking's packages only apply from
        # three nights up, so a fixed two-night probe would hide every one of them.
        # What the guest said on this search wins; the itinerary's plan is the fallback, and
        # two nights only when neither knows. The length decides which package applies.
        plan = self._trip_plans.get(session.session_id)
        planned = plan.trip_nights if plan else None
        quote_nights = _night_count(filters) or planned or _DEFAULT_QUOTE_NIGHTS
        quote_nights = max(quote_nights, 1)
        departure = travel_date + timedelta(days=quote_nights)
        # The stated party drives availability and price: a cabin that cannot sleep them is
        # not a result, and a package is priced for the heads it covers.
        guests = _guest_count(filters)
        self._session_guests[session.session_id] = guests
        avail = await self._aget(
            "/api/availability",
            {
                "arrival": travel_date.isoformat(),
                "departure": departure.isoformat(),
                "persons": guests,
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
        packages: dict[str, dict[str, Any]] = {}
        available: list = []
        for cabin in avail.get("available_cabins", []):
            slug = _ID_TO_SLUG.get(cabin.get("id"))
            product = self.products.get(slug) if slug else None
            if product is None:
                continue
            available.append(product)
            if cabin.get("price_per_night"):
                live_price[slug] = float(cabin["price_per_night"])
            quote = _read_offers(cabin.get("pricing_offers", []), nights)
            if quote["rates"]:
                offer_rates[slug] = quote["rates"]
            if quote["package"]:
                packages[slug] = quote["package"]

        if not available:
            # Every cabin is taken for these dates. Returning nothing would be read as "no
            # such cabin exists" — asked which cabins have a jacuzzi in a fully booked
            # week, the assistant answered that the property may not have one. Show what
            # matches, marked as taken, so the answer is "booked then" and the card wears
            # its sold-out band.
            taken = await super().search_products(session, query, filters, limit)
            for product in taken:
                product.in_stock = False
                product.attributes["quoted_for"] = (
                    f"{travel_date.isoformat()}..{departure.isoformat()}"
                )
            self._attach_ladder(taken, await self._package_ladder(travel_date, guests))
            self._attach_suggestions(taken, await self._suggestions(guests))
            return taken

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
            # The named package the quoted rate comes from, so the card and the assistant
            # can say which one earned the discount rather than only showing a lower price.
            package = packages.get(product.product_id)
            if package:
                product.attributes["package_name"] = package["name"]
                product.attributes["package_rate_before"] = str(package["rate_before"])
                product.attributes["package_discount_pct"] = str(package["discount_pct"])
            # The exact free-cancellation deadline is not exposed by the API — it is shown
            # at booking — so we do not assert one here (only that a refundable rate exists).
            product.attributes["quoted_for"] = f"{travel_date.isoformat()}..{departure.isoformat()}"
        self._attach_ladder(results, await self._package_ladder(travel_date, guests))
        self._attach_suggestions(results, await self._suggestions(guests))
        return results


def build_backend() -> MockTravel:
    """``HyggeLive`` when ``IDOBOOKING_MIDDLEWARE_URL`` is set, else the static ``MockTravel``."""
    url = os.environ.get("IDOBOOKING_MIDDLEWARE_URL", "").strip()
    if url:
        logger.info("using live idobooking backend at %s", url)
        return HyggeLive(url)
    logger.info("IDOBOOKING_MIDDLEWARE_URL unset; using the static catalog")
    return MockTravel()
