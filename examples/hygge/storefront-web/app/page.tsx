// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { useCallback, useEffect, useState } from "react";
import { type AgentEvent, OrdersView, StoreShell, type StoreView, useAgentTurn, useResource, useSession } from "web-shared";
import Chat from "@/components/Chat";
import TripPanel from "@/components/TripPanel";
import HomeView from "@/components/views/HomeView";
import { api, UNREACHABLE } from "@/lib/api";
import { formatPrice } from "@/lib/format";
import { type Lang, LANGS, t, useLang } from "@/lib/i18n";
import { guestProfileId, LIGHT_UI } from "@/lib/light";
import { NOUNS, TripThumb } from "@/lib/orders";
import type { CartPayload } from "@/lib/types";

type View = "assistant" | "trips";

function Wordmark() {
  return (
    <span className="al-display pr-1 text-[22px] italic leading-none text-(--ink)" style={{ fontWeight: 650 }}>
      <span className="mr-1 not-italic text-[13px] text-(--accent)" aria-hidden>
        ◈
      </span>
      Osada Hygge
    </span>
  );
}

function LangSwitcher({ lang, onChange }: { lang: Lang; onChange: (l: Lang) => void }) {
  return (
    <div className="ml-2 flex items-center gap-0.5 rounded-full border border-(--line) p-0.5 text-[11px]" role="group" aria-label="Language">
      {LANGS.map(({ code, label }) => (
        <button
          key={code}
          type="button"
          onClick={() => onChange(code)}
          aria-pressed={lang === code}
          className={`rounded-full px-1.5 py-0.5 leading-none ${lang === code ? "bg-(--ink) text-(--surface)" : "text-(--muted) hover:text-(--ink)"}`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

export default function StorefrontPage() {
  // Computed once: a changing profile would restart the session on every render.
  const [guestId] = useState(() => (LIGHT_UI ? guestProfileId() : undefined));
  const session = useSession(api, { profile: guestId });
  const [view, setView] = useState<View>("assistant");
  const [cart, setCart] = useState<CartPayload | null>(null);
  // A staged checkout owns the panel's primary action until the trip changes again.
  const [checkoutStaged, setCheckoutStaged] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const [lang, setLang] = useLang();

  // Every chat turn carries the UI language so the assistant replies in it.
  useEffect(() => {
    api.language = lang;
  }, [lang]);

  const onEvent = useCallback((event: AgentEvent) => {
    if (event.type === "cart_update") {
      setCart(event.data.cart as CartPayload);
      setCheckoutStaged(false);
    } else if (event.type === "ui" && event.data.component === "checkout") {
      setCheckoutStaged(true);
    }
  }, []);

  const chat = useAgentTurn(api, { ...session, unreachable: UNREACHABLE, onEvent });
  // A reply may have changed or refunded a booking, so trips re-read after each one.
  const { data: trips, failed: tripsFailed } = useResource(
    session.sessionId && !LIGHT_UI ? () => api.fetchOrders() : null,
    [session.sessionId, chat.completed],
  );

  useEffect(() => {
    if (session.sessionId) void api.fetchCart<CartPayload>().then((next) => next && setCart(next));
  }, [session.sessionId]);

  const views: StoreView<View>[] = [
    { id: "assistant", label: t(lang, "viewAssistant"), icon: "spark" },
    ...(LIGHT_UI ? [] : [{ id: "trips" as const, label: t(lang, "viewStays"), icon: "plane" as const }]),
  ];
  // Light mode faces real guests, who are nobody the seeded profile knows.
  const shopper = LIGHT_UI ? { name: t(lang, "guestName") } : (session.shopper ?? { name: "Guest" });
  const count = cart?.items.length ?? 0;

  return (
    <StoreShell
      brand={
        <span className="flex items-center">
          <Wordmark />
          <LangSwitcher lang={lang} onChange={setLang} />
        </span>
      }
      views={views}
      view={view}
      onViewChange={setView}
      chat={chat}
      api={api}
      assistantName={t(lang, "assistantName")}
      shopper={shopper}
      bag={{ label: t(lang, "bagLabel"), count, noun: t(lang, "bagNoun"), figure: count ? formatPrice(cart?.subtotal ?? 0) : null }}
      panel={<TripPanel cart={cart} checkoutStaged={checkoutStaged} lang={lang} light={LIGHT_UI} />}
      panelOpen={panelOpen}
      onPanelOpenChange={setPanelOpen}
      placeholder={view === "trips" ? t(lang, "placeholderStays") : t(lang, "placeholderAssistant")}
    >
      {/* The conversation stays mounted under the other view so its cards keep their state. */}
      <div className={view === "assistant" ? "h-full" : "hidden"}>
        <Chat chat={chat} home={<HomeView lang={lang} travelerName={shopper.name} trips={trips} tripsFailed={tripsFailed} onSeeTrips={() => setView("trips")} light={LIGHT_UI} />} />
      </div>
      {view === "trips" && !LIGHT_UI ? (
        <OrdersView
          orders={trips}
          failed={tripsFailed}
          nouns={NOUNS}
          subtitle={trips ? t(lang, "staysSubtitle") : undefined}
          thumb={(order) => <TripThumb order={order} />}
        />
      ) : null}
    </StoreShell>
  );
}
