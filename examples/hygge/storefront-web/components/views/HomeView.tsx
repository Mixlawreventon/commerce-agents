// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { useState } from "react";
import { ArrivingPanel, Greeting, HomeSection, type Order, type Starter, Starters, useStoreFrame } from "web-shared";
import { type Lang, t } from "@/lib/i18n";
import { NOUNS, TripThumb } from "@/lib/orders";
import { PostcardWindow } from "../PostcardWindow";

/** The keys of DESTINATION_GRADIENTS in lib/format.ts. */
const POSTCARD_CITIES = ["Fika", "Lagom", "Gron", "Hyggelig", "Lykke"];

/** Primary photo per cabin (idobooking); mirrors each cabin's image_url in data/catalog.json. */
const POSTCARD_IMAGES: Record<string, string> = {
  Fika: "https://client9681.idobooking.com/images/objects/pictures/large/2/1/104.jpg",
  Lagom: "https://client9681.idobooking.com/images/objects/pictures/large/3/1/108.jpg",
  Gron: "https://client9681.idobooking.com/images/objects/pictures/large/4/1/186.jpg",
  Hyggelig: "https://client9681.idobooking.com/images/objects/pictures/large/5/1/166.jpg",
  Lykke: "https://client9681.idobooking.com/images/objects/pictures/large/7/1/213.jpg",
};

/** Sends just before the 300ms mail animation ends. */
const MAILING_MS = 260;

function starters(lang: Lang, light: boolean): Starter[] {
  return [
    { icon: "calendar", prompt: t(lang, "starterWeekend") },
    { icon: "plane", prompt: t(lang, "starterJacuzzi") },
    { icon: "return", prompt: t(lang, "starterPets") },
    // Light mode has no stays to look up, so it offers the packages instead.
    { icon: "pin", prompt: t(lang, light ? "starterPackages" : "starterBooking") },
  ];
}

function Postcards({ lang }: { lang: Lang }) {
  const { ask, chat } = useStoreFrame();
  const [mailingCity, setMailingCity] = useState<string | null>(null);
  const disabled = !chat || chat.busy || !chat.ready;
  const planTrip = (city: string) => {
    const request = () => ask(t(lang, "askCabin", { city }));
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
          aria-label={t(lang, "askCabin", { city })}
          className="al-reveal-item"
          style={{ animationDelay: `${(index + 4) * 60}ms` }}
        >
          {/* Transforms live here; the button's reveal animation would pin them. */}
          <div
            className={`overflow-hidden rounded-(--radius) border border-(--line) ${
              index % 2 ? "al-postcard-rest al-postcard-rest--alt" : "al-postcard-rest"
            } ${mailingCity === city ? "al-postcard-mailing" : ""}`}
          >
            <PostcardWindow city={city} title={city} imageUrl={POSTCARD_IMAGES[city]} className="aspect-[4/3] w-full" />
          </div>
        </button>
      ))}
    </div>
  );
}

export default function HomeView({ lang, travelerName, trips, tripsFailed, onSeeTrips, light = false }: { lang: Lang; travelerName: string; trips: Order[] | null; tripsFailed: boolean; onSeeTrips: () => void; light?: boolean }) {
  return (
    <div className="flex flex-col gap-4">
      <Greeting title={<h1 className="al-hero">{light ? t(lang, "heroTitleAnon") : t(lang, "heroTitle", { name: travelerName })}</h1>}>
        {t(lang, "opener")}
      </Greeting>
      <Starters items={starters(lang, light)} />
      {/* Recording guests' words is only fair if they are told, where they start typing. */}
      {light ? (
        <p className="text-[12px]" style={{ color: "var(--ink-soft)" }}>
          {t(lang, "privacyNote")}
        </p>
      ) : null}
      {light ? null : (
        <ArrivingPanel orders={trips} failed={tripsFailed} nouns={NOUNS} thumb={(order) => <TripThumb order={order} />} onSeeAll={onSeeTrips} />
      )}
      <HomeSection title={t(lang, "sectionTitle")} subtitle={t(lang, "sectionSubtitle")}>
        <Postcards lang={lang} />
      </HomeSection>
    </div>
  );
}
