// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { useEffect, useState } from "react";
import { useStoreFrame } from "web-shared";
import { api } from "@/lib/api";
import { formatPrice } from "@/lib/format";
import { type Lang, t } from "@/lib/i18n";
import type { HomeCabin, HomeOffer, HomeOpening, HomeOverview } from "@/lib/types";
import { PostcardWindow } from "./PostcardWindow";

/**
 * The stay panel before anything is chosen: the nearest open dates with a price, the five
 * cabins with their lowest rate, and the offers on. Every tile is a ready question, so a
 * guest who has not typed yet still starts from real dates and real prices. Read once on
 * mount from `GET /api/home`; the panel returns to the cart as soon as a stay is added.
 */

const LOCALES: Record<Lang, string> = { pl: "pl-PL", en: "en-GB", de: "de-DE" };

/** "pt 23 paź" from an ISO day; UTC so no timezone moves the date. */
function stayDate(lang: Lang, iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) return iso;
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
  return new Intl.DateTimeFormat(LOCALES[lang], { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" }).format(date);
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-5">
      <h3 className="mb-2 text-[12px] font-semibold uppercase tracking-[0.08em]" style={{ color: "var(--ink-soft)" }}>
        {title}
      </h3>
      {children}
    </section>
  );
}

function OpeningTile({ opening, lang, disabled }: { opening: HomeOpening; lang: Lang; disabled: boolean }) {
  const { ask } = useStoreFrame();
  const kind = t(lang, opening.kind === "weekend" ? "openingsWeekend" : "openingsMidweek");
  const arrival = stayDate(lang, opening.arrival);
  const departure = stayDate(lang, opening.departure);
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => ask(t(lang, "openingsPrompt", { arrival, departure, kind: kind.toLowerCase() }))}
      className="flex w-full flex-col gap-0.5 rounded-(--radius) border p-3 text-left transition hover:border-(--accent) disabled:opacity-50"
      style={{ borderColor: "var(--line)", background: "var(--surface)" }}
    >
      <span className="flex items-baseline justify-between gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-[0.06em]" style={{ color: opening.kind === "weekend" ? "var(--accent)" : "var(--ink-soft)" }}>
          {kind}
        </span>
        <span className="text-[11px]" style={{ color: "var(--ink-soft)" }}>
          {t(lang, "openingsNights", { n: String(opening.nights) })}
        </span>
      </span>
      <span className="al-display text-[14px] font-semibold leading-snug" style={{ color: "var(--ink)" }}>
        {arrival} – {departure}
      </span>
      <span className="flex items-baseline justify-between gap-2">
        <span className="text-[13px] font-bold tabular-nums" style={{ color: "var(--ink)" }}>
          {t(lang, "cabinsFrom", { price: formatPrice(opening.price_from) })}
        </span>
        <span className="text-[11px]" style={{ color: "var(--ink-soft)" }}>
          {t(lang, "openingsCabinsLeft", { n: String(opening.cabins_left) })}
        </span>
      </span>
    </button>
  );
}

function CabinTile({ cabin, lang, disabled }: { cabin: HomeCabin; lang: Lang; disabled: boolean }) {
  const { ask } = useStoreFrame();
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => ask(t(lang, "cabinPrompt", { name: cabin.name }))}
      aria-label={t(lang, "cabinPrompt", { name: cabin.name })}
      className="flex flex-col gap-1 text-left disabled:opacity-50"
    >
      <PostcardWindow city={cabin.name} title={cabin.name} imageUrl={cabin.image_url} showLabel={false} className="aspect-[4/3] w-full overflow-hidden rounded-(--radius) border border-(--line)" />
      <span className="al-display text-[12.5px] font-semibold leading-tight" style={{ color: "var(--ink)" }}>
        {cabin.name}
      </span>
      <span className="text-[11px] leading-tight tabular-nums" style={{ color: "var(--ink-soft)" }}>
        {t(lang, "cabinsFrom", { price: formatPrice(cabin.price_from) })}
      </span>
    </button>
  );
}

function OfferTile({ offer, lang, disabled }: { offer: HomeOffer; lang: Lang; disabled: boolean }) {
  const { ask } = useStoreFrame();
  const title = offer.kind === "code" ? offer.code : offer.title;
  const window_ =
    offer.stay_from || offer.stay_to
      ? t(lang, "offersStay", { from: offer.stay_from ? stayDate(lang, offer.stay_from) : "…", to: offer.stay_to ? stayDate(lang, offer.stay_to) : "…" })
      : offer.kind === "code" && offer.valid_to
        ? t(lang, "offersBookBy", { date: stayDate(lang, offer.valid_to) })
        : null;
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => ask(t(lang, "offerPrompt", { title }))}
      className="flex w-full items-center gap-3 rounded-(--radius) border p-3 text-left transition hover:border-(--accent) disabled:opacity-50"
      style={{ borderColor: "var(--line)", background: "var(--accent-soft)" }}
    >
      <span className="min-w-0 flex-1">
        <span className="block text-[11px] font-semibold uppercase tracking-[0.06em]" style={{ color: "var(--accent-ink)" }}>
          {offer.kind === "code" ? t(lang, "offersCode") : t(lang, "offersTitle")}
        </span>
        <span className="al-display block truncate text-[14px] font-semibold" style={{ color: "var(--ink)" }}>
          {title}
        </span>
        {offer.kind === "promotion" && offer.detail ? (
          <span className="block truncate text-[11px]" style={{ color: "var(--ink-soft)" }}>
            {offer.detail}
          </span>
        ) : null}
        {window_ ? (
          <span className="block text-[11px]" style={{ color: "var(--ink-soft)" }}>
            {window_}
          </span>
        ) : null}
      </span>
      {offer.kind === "code" ? (
        <span className="al-display shrink-0 text-[18px] font-bold" style={{ color: "var(--accent)" }}>
          {offer.discount_label}
        </span>
      ) : null}
    </button>
  );
}

export default function StayOpenings({ lang, fallback }: { lang: Lang; fallback: React.ReactNode }) {
  const { chat } = useStoreFrame();
  const disabled = !chat || chat.busy || !chat.ready;
  const [overview, setOverview] = useState<HomeOverview | null | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    void api.get<HomeOverview>("/home").then((data) => {
      if (!cancelled) setOverview(data);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  if (overview === undefined) return null;
  if (!overview || (!overview.openings.length && !overview.cabins.length && !overview.offers.length)) {
    return <>{fallback}</>;
  }
  return (
    <div className="text-left">
      {overview.openings.length ? (
        <Section title={t(lang, "openingsTitle")}>
          <div className="flex flex-col gap-2">
            {overview.openings.slice(0, 4).map((opening) => (
              <OpeningTile key={`${opening.kind}-${opening.arrival}`} opening={opening} lang={lang} disabled={disabled} />
            ))}
          </div>
        </Section>
      ) : null}
      {overview.cabins.length ? (
        <Section title={t(lang, "cabinsTitle")}>
          <div className="grid grid-cols-3 gap-2">
            {overview.cabins.map((cabin) => (
              <CabinTile key={cabin.product_id} cabin={cabin} lang={lang} disabled={disabled} />
            ))}
          </div>
        </Section>
      ) : null}
      {overview.offers.length ? (
        <Section title={t(lang, "offersTitle")}>
          <div className="flex flex-col gap-2">
            {overview.offers.map((offer, index) => (
              <OfferTile key={`${offer.kind}-${index}`} offer={offer} lang={lang} disabled={disabled} />
            ))}
          </div>
        </Section>
      ) : null}
    </div>
  );
}
