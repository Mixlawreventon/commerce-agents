# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The discount-code rules, the desk that runs them per session, and the tool over it."""

from __future__ import annotations

from datetime import date

import pytest

from hygge.api.discount_codes import (
    DiscountCode,
    DiscountCodeDraft,
    DiscountCodeStore,
    OfferDesk,
    StayFacts,
    code_applies,
    eligible_codes,
    normalize_trigger,
    parse_trigger,
)

TODAY = date(2026, 10, 18)  # a Sunday


def code(name: str = "JESIEN15", **fields) -> DiscountCode:
    base = {"code": name, "discount_label": "-15%", "announceable": True}
    return DiscountCode(**{**base, **fields})


def stay(arrival: str, nights: int = 2, cabin_id: str | None = None) -> StayFacts:
    start = date.fromisoformat(arrival)
    return StayFacts(
        arrival=start,
        departure=date.fromordinal(start.toordinal() + nights),
        today=TODAY,
        cabin_id=cabin_id,
    )


# -- triggers ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "parsed", "canonical"),
    [
        ("lead_days_max:7", ("lead_days_max", 7), "lead_days_max:7"),
        ("min_nights: 3", ("min_nights", 3), "min_nights:3"),
        ("weekdays:[1,2,3,4]", ("weekdays", {1, 2, 3, 4}), "weekdays:[1,2,3,4]"),
        ("weekdays:7,5", ("weekdays", {5, 7}), "weekdays:[5,7]"),
        ("cabins:[12, 13]", ("cabins", {"12", "13"}), "cabins:[12,13]"),
        ("returning_guest", ("returning_guest", None), "returning_guest"),
    ],
)
def test_triggers_parse_and_normalize(raw, parsed, canonical):
    assert parse_trigger(raw) == parsed
    assert normalize_trigger(raw) == canonical


@pytest.mark.parametrize(
    "raw", ["weekdays:[0]", "weekdays:[8]", "lead_days_max:x", "vip", "cabins:[]"]
)
def test_an_unknown_or_malformed_trigger_is_rejected(raw):
    with pytest.raises(ValueError):
        parse_trigger(raw)
    with pytest.raises(ValueError):
        DiscountCodeDraft(code="x1", discount_label="-5%", trigger_signals=[raw])


def test_a_code_is_stored_upper_case_and_in_a_closed_shape():
    assert DiscountCodeDraft(code=" jesien15 ", discount_label="-15%").code == "JESIEN15"
    with pytest.raises(ValueError):
        DiscountCodeDraft(code="kod z spacją", discount_label="-15%")


# -- eligibility ------------------------------------------------------------------------


def test_validity_is_about_today_and_the_stay_window_about_every_night():
    windowed = code(
        valid_from=date(2026, 10, 1),
        valid_to=date(2026, 10, 20),
        stay_from=date(2026, 11, 1),
        stay_to=date(2026, 11, 30),
    )
    assert code_applies(windowed, stay("2026-11-06"), [])
    # The last night (Nov 30 -> Dec 1) is past the window.
    assert not code_applies(windowed, stay("2026-11-29", nights=3), [])
    assert not code_applies(windowed, stay("2026-10-30"), [])
    late = code(valid_to=date(2026, 10, 17))
    assert not code_applies(late, stay("2026-11-06"), [])
    assert not code_applies(code(active=False), stay("2026-11-06"), [])


def test_computed_triggers_read_lead_time_weekdays_nights_and_cabin():
    assert code_applies(code(trigger_signals=["lead_days_max:7"]), stay("2026-10-23"), [])
    assert not code_applies(code(trigger_signals=["lead_days_max:3"]), stay("2026-10-23"), [])
    # A midweek code: every night must start Monday-Thursday.
    midweek = code(trigger_signals=["weekdays:[1,2,3,4]"])
    assert code_applies(midweek, stay("2026-10-19"), [])  # Mon, Tue nights
    assert not code_applies(midweek, stay("2026-10-23"), [])  # Fri, Sat nights
    assert not code_applies(code(trigger_signals=["min_nights:3"]), stay("2026-10-19"), [])
    assert code_applies(code(trigger_signals=["min_nights:3"]), stay("2026-10-19", nights=3), [])
    jacuzzi = code(trigger_signals=["cabins:[12,13]"])
    assert code_applies(jacuzzi, stay("2026-10-19", cabin_id="12"), [])
    assert not code_applies(jacuzzi, stay("2026-10-19", cabin_id="14"), [])
    assert not code_applies(jacuzzi, stay("2026-10-19"), [])


def test_a_code_that_is_not_announceable_waits_for_a_signal():
    quiet = code(announceable=False)
    assert not code_applies(quiet, stay("2026-10-23"), [])
    assert code_applies(quiet, stay("2026-10-23"), ["price_hesitation"])
    returning = code(announceable=False, trigger_signals=["returning_guest"])
    assert not code_applies(returning, stay("2026-10-23"), ["price_hesitation"])
    assert code_applies(returning, stay("2026-10-23"), ["returning_guest"])
    # Announceable, but with a conversation trigger: still needs the signal.
    asked = code(trigger_signals=["asked_for_discount"])
    assert not code_applies(asked, stay("2026-10-23"), [])
    assert code_applies(asked, stay("2026-10-23"), ["asked_for_discount"])


def test_eligible_codes_sort_by_priority_cap_at_two_and_skip_exhausted_ones():
    codes = [
        code("C3", priority=30),
        code("A1", priority=10),
        code("B2", priority=20),
        code("D4", priority=5, active=False),
    ]
    picks = [c.code for c in eligible_codes(codes, stay("2026-10-23"), [])]
    assert picks == ["A1", "B2"]
    picks = [c.code for c in eligible_codes(codes, stay("2026-10-23"), [], proposed={"A1": 1})]
    assert picks == ["B2", "C3"]


# -- the desk ---------------------------------------------------------------------------


class Events:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []

    def record(self, kind: str, *, session_id: str, user_id: str, **data) -> None:
        self.rows.append((kind, session_id, data["code"]))


@pytest.fixture
def desk() -> tuple[OfferDesk, Events]:
    store = DiscountCodeStore(
        [code("WEEKEND10", priority=10), code("CICHY", announceable=False, priority=5)]
    )
    events = Events()
    desk = OfferDesk(store, today=TODAY)
    desk.bind(events)
    return desk, events


async def test_the_desk_counts_each_proposal_once_per_session_cap(desk):
    desk, events = desk
    start, end = date(2026, 10, 23), date(2026, 10, 25)
    first = await desk.propose("s-1", "u-1", start, end, None, [])
    assert [c.code for c in first] == ["WEEKEND10"]
    assert events.rows == [("offer_proposed", "s-1", "WEEKEND10")]
    # max_per_session is one: the same session hears it no more.
    assert await desk.propose("s-1", "u-1", start, end, None, []) == []
    # A later signal opens the quiet code; the earlier one stays spent.
    second = await desk.propose("s-1", "u-1", start, end, None, ["price_hesitation"])
    assert [c.code for c in second] == ["CICHY"]
    assert (await desk.store.get("WEEKEND10")).usage_proposed == 1
    # Another session starts fresh.
    assert [c.code for c in await desk.propose("s-2", "u-2", start, end, None, [])] == ["WEEKEND10"]


async def test_the_handoff_carries_the_first_proposed_code_that_still_applies(desk):
    desk, events = desk
    start, end = date(2026, 10, 23), date(2026, 10, 25)
    assert await desk.handoff("s-1", "u-1", start, end, None) is None
    await desk.propose("s-1", "u-1", start, end, None, ["price_hesitation"])
    handed = await desk.handoff("s-1", "u-1", start, end, None)
    assert handed is not None and handed.code == "CICHY"
    assert ("offer_handoff", "s-1", "CICHY") in events.rows
    # Rendered twice, counted once.
    await desk.handoff("s-1", "u-1", start, end, None)
    assert (await desk.store.get("CICHY")).usage_handoff == 1
    assert (await desk.store.get("CICHY")).conversion_pct == 100.0
    desk.reset("s-1")
    assert await desk.handoff("s-1", "u-1", start, end, None) is None


async def test_the_store_keeps_counters_across_an_edit_and_lists_announceable_codes(desk):
    desk, _ = desk
    await desk.store.bump("WEEKEND10", "usage_proposed")
    edited = await desk.store.upsert(
        DiscountCodeDraft(code="weekend10", discount_label="-10%", announceable=True)
    )
    assert edited.usage_proposed == 1 and edited.discount_label == "-10%"
    assert [c.code for c in await desk.announceable()] == ["WEEKEND10"]
    assert await desk.store.delete("WEEKEND10") and not await desk.store.delete("WEEKEND10")
