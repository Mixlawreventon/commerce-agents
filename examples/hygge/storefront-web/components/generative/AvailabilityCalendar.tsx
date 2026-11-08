// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { useStoreFrame } from "web-shared";
import { formatPrice } from "@/lib/format";
import { type Lang, t, useLang } from "@/lib/i18n";
import type { CalendarDay, CalendarMonth, CalendarPayload } from "@/lib/types";
import { BODY, CARD, DISPLAY, META, display } from "./shared";

/**
 * The availability calendar inside the conversation: the same nights the booking
 * widget shows, filled in by the server from the booking system's calendar. A free
 * night carries its price; a click asks the assistant about a stay starting that night.
 */

const LOCALES: Record<Lang, string> = { pl: "pl-PL", en: "en-GB", de: "de-DE" };

function monthLabel(lang: Lang, month: string): string {
  const [year, index] = month.split("-").map(Number);
  const date = new Date(Date.UTC(year, index - 1, 1));
  const text = new Intl.DateTimeFormat(LOCALES[lang], { month: "long", year: "numeric", timeZone: "UTC" }).format(date);
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function weekdayLabels(lang: Lang): string[] {
  // 2024-01-01 is a Monday; the week runs Monday to Sunday as the booking widget does.
  return Array.from({ length: 7 }, (_, i) =>
    new Intl.DateTimeFormat(LOCALES[lang], { weekday: "short", timeZone: "UTC" }).format(new Date(Date.UTC(2024, 0, 1 + i))).replace(".", ""),
  );
}

function dayLabel(lang: Lang, iso: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  return new Intl.DateTimeFormat(LOCALES[lang], { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" }).format(new Date(Date.UTC(year, month - 1, day)));
}

function Day({ day, lang, cabin, guests, disabled }: { day: CalendarDay; lang: Lang; cabin?: string; guests: number; disabled: boolean }) {
  const { ask } = useStoreFrame();
  const state = day.past ? "past" : day.available ? "free" : "booked";
  const prompt = cabin
    ? t(lang, "calendarDayPromptCabin", { name: cabin, date: dayLabel(lang, day.iso), guests: String(guests) })
    : t(lang, "calendarDayPrompt", { date: dayLabel(lang, day.iso), guests: String(guests) });
  const label = `${dayLabel(lang, day.iso)}: ${state === "free" ? t(lang, "calendarFree") : state === "booked" ? t(lang, "calendarBooked") : t(lang, "calendarPast")}${day.price ? `, ${formatPrice(day.price)}` : ""}`;
  return (
    <button
      type="button"
      disabled={disabled || state !== "free"}
      onClick={() => ask(prompt)}
      aria-label={label}
      title={label}
      className="flex aspect-square flex-col items-center justify-center gap-0.5 rounded-md border transition disabled:cursor-default"
      style={{
        gridColumnStart: day.day === 1 ? day.weekday : undefined,
        fontFamily: BODY,
        borderColor: state === "free" ? "var(--line)" : "transparent",
        background: state === "free" ? "var(--surface)" : state === "booked" ? "var(--well)" : "transparent",
        color: state === "free" ? "var(--ink)" : "var(--ink-faint)",
        textDecoration: state === "booked" ? "line-through" : undefined,
        opacity: state === "past" ? 0.45 : 1,
      }}
    >
      <span style={{ fontSize: 13, fontWeight: state === "free" ? 600 : 400, lineHeight: 1 }}>{day.day}</span>
      {state === "free" && day.price ? (
        <span className="tabular-nums" style={{ fontSize: 9.5, color: "var(--accent-ink)", lineHeight: 1 }}>
          {Math.round(day.price)}
        </span>
      ) : null}
      {state === "free" && day.cabins_free != null ? (
        <span aria-hidden className="flex gap-[2px]">
          {Array.from({ length: Math.min(day.cabins_free, 5) }, (_, i) => (
            <span key={i} className="h-[3px] w-[3px] rounded-full" style={{ background: "var(--accent)" }} />
          ))}
        </span>
      ) : null}
    </button>
  );
}

function Month({ month, lang, cabin, guests, disabled }: { month: CalendarMonth; lang: Lang; cabin?: string; guests: number; disabled: boolean }) {
  const labels = weekdayLabels(lang);
  return (
    <div className="min-w-0 flex-1">
      <div className="mb-2" style={display(16, 600)}>
        {monthLabel(lang, month.month)}
      </div>
      <div className="grid grid-cols-7 gap-1">
        {labels.map((label, index) => (
          <div key={label} className="text-center" style={{ ...META, fontSize: 10, color: index >= 5 ? "var(--accent-ink)" : "var(--ink-soft)" }}>
            {label}
          </div>
        ))}
        {month.days.map((day) => (
          <Day key={day.iso} day={day} lang={lang} cabin={cabin} guests={guests} disabled={disabled} />
        ))}
      </div>
    </div>
  );
}

export default function AvailabilityCalendar({ payload }: { payload: CalendarPayload }) {
  const [lang] = useLang();
  const { chat } = useStoreFrame();
  const disabled = !chat || chat.busy || !chat.ready;
  const cabin = payload.cabin?.name;
  const months = payload.months ?? [];
  const freeNights = months.reduce((sum, month) => sum + month.days.filter((day) => day.available).length, 0);
  return (
    <section className="al-reveal" style={CARD} data-calendar-card>
      <div className="p-5">
        <div style={META}>{cabin ? t(lang, "calendarCabin", { name: cabin }) : t(lang, "calendarProperty")}</div>
        <h3 className="mt-1" style={display(20, 600)}>
          {payload.title ?? t(lang, "calendarTitle")}
        </h3>
        <p className="mt-1" style={{ fontFamily: BODY, fontSize: 13, color: "var(--ink-soft)" }}>
          {t(lang, "calendarSubtitle", { nights: String(freeNights), guests: String(payload.guests ?? 2) })}
        </p>
        <div className={`mt-4 flex flex-col gap-5 ${months.length > 1 ? "sm:flex-row" : ""}`}>
          {months.map((month) => (
            <Month key={month.month} month={month} lang={lang} cabin={cabin} guests={payload.guests ?? 2} disabled={disabled} />
          ))}
        </div>
        <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1" style={{ fontFamily: BODY, fontSize: 11.5, color: "var(--ink-soft)" }}>
          <span className="flex items-center gap-1.5">
            <span className="h-3 w-3 rounded-sm border" style={{ borderColor: "var(--line)", background: "var(--surface)" }} />
            {t(lang, "calendarFree")} · {t(lang, "calendarPricePerNight")}
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-3 w-3 rounded-sm" style={{ background: "var(--well)" }} />
            {t(lang, "calendarBooked")}
          </span>
          {!cabin ? (
            <span className="flex items-center gap-1.5">
              <span className="h-[3px] w-[3px] rounded-full" style={{ background: "var(--accent)" }} />
              {t(lang, "calendarDots")}
            </span>
          ) : null}
          <span style={{ fontFamily: DISPLAY, fontStyle: "italic" }}>{t(lang, "calendarClickHint")}</span>
        </div>
      </div>
    </section>
  );
}
