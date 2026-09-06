// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { useState } from "react";
import { ArrivingPanel, estimateOf, Greeting, HomeSection, type Order, plural, type Starter, Starters, upcoming, useStoreFrame } from "web-shared";
import { NOUNS, TripThumb } from "@/lib/orders";
import { PostcardWindow } from "../PostcardWindow";

const STARTERS: Starter[] = [
  { icon: "calendar", prompt: "Find a cabin for next weekend" },
  { icon: "plane", prompt: "A cabin with a jacuzzi on the terrace" },
  { icon: "return", prompt: "Somewhere pet-friendly near the lake" },
  { icon: "pin", prompt: "What's the status of my booking?" },
];

/** The keys of DESTINATION_GRADIENTS in lib/format.ts. */
const POSTCARD_CITIES = ["Fika", "Lagom", "Gron", "Hyggelig", "Lykke"];

/** Sends just before the 300ms mail animation ends. */
const MAILING_MS = 260;

const OPENER = "Tell me your dates and the Hygge Assistant finds the right forest cabin for your stay.";

function Brief({ trips }: { trips: Order[] | null }) {
  const open = trips ? upcoming(trips) : [];
  if (!open.length) return <>{OPENER}</>;
  const next = estimateOf(open[0])?.date;
  return (
    <>
      {plural(open.length, "stay")} coming up{next ? `; the next starts ${next}` : ""}. {OPENER}
    </>
  );
}

function Postcards() {
  const { ask, chat } = useStoreFrame();
  const [mailingCity, setMailingCity] = useState<string | null>(null);
  const disabled = !chat || chat.busy || !chat.ready;
  const planTrip = (city: string) => {
    const request = () => ask(`Tell me about the ${city} cabin`);
    // Reduced motion, or a card already on its way, sends at once.
    if (mailingCity || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      request();
      return;
    }
    setMailingCity(city);
    window.setTimeout(() => {
      setMailingCity(null);
      request();
    }, MAILING_MS);
  };
  return (
    <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
      {POSTCARD_CITIES.map((city, index) => (
        <button
          key={city}
          type="button"
          onClick={() => planTrip(city)}
          disabled={disabled}
          aria-label={`Explore the ${city} cabin`}
          className="al-reveal-item"
          style={{ animationDelay: `${(index + 4) * 60}ms` }}
        >
          {/* Transforms live here; the button's reveal animation would pin them. */}
          <div
            className={`overflow-hidden rounded-(--radius) border border-(--line) ${
              index % 2 ? "al-postcard-rest al-postcard-rest--alt" : "al-postcard-rest"
            } ${mailingCity === city ? "al-postcard-mailing" : ""}`}
          >
            <PostcardWindow city={city} title={city} className="aspect-[4/3] w-full" />
          </div>
        </button>
      ))}
    </div>
  );
}

export default function HomeView({ travelerName, trips, tripsFailed, onSeeTrips }: { travelerName: string; trips: Order[] | null; tripsFailed: boolean; onSeeTrips: () => void }) {
  return (
    <div className="flex flex-col gap-4">
      <Greeting
        title={
          <h1 className="al-hero">
            Ready to unwind, <em>{travelerName}</em>?
          </h1>
        }
      >
        <Brief trips={trips} />
      </Greeting>
      <Starters items={STARTERS} />
      <ArrivingPanel orders={trips} failed={tripsFailed} nouns={NOUNS} thumb={(order) => <TripThumb order={order} />} onSeeAll={onSeeTrips} />
      <HomeSection title="Start from a cabin" subtitle="Pick one and the Hygge Assistant tells you about it">
        <Postcards />
      </HomeSection>
    </div>
  );
}
