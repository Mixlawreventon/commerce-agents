// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";
import { API_URL } from "@/lib/api";

/**
 * What the assistant did, read back, and the discount codes it may offer.
 *
 * The token is asked for here and kept in sessionStorage rather than put in the URL: a
 * query string ends up in history, in referrers, and in every access log between here and
 * the API. Nothing on this page is fetched until a token is entered, so the page itself
 * gives away nothing.
 *
 * The codes tab mirrors the idobooking panel: a code is created there by hand, then copied
 * here with the same spelling and windows, plus the rules of when the assistant offers it.
 */

/** Every count is absent when no DATABASE_URL is set: the API answers an empty object. */
type Stats = Partial<{
  days: number;
  sessions: number;
  interactions: number;
  replies: number;
  offers: number;
  cabins_shown: number;
  booking_clicks: number;
  thumbs_down: number;
  errors: number;
}>;

type Event = { at: string; kind: string; data: Record<string, unknown> };
type Conversation = { session_id: string; started: string; events: Event[] };

type DiscountCode = {
  code: string;
  discount_label: string;
  stay_from: string | null;
  stay_to: string | null;
  valid_from: string | null;
  valid_to: string | null;
  active: boolean;
  announceable: boolean;
  trigger_signals: string[];
  priority: number;
  max_per_session: number;
  notes_for_agent: string;
  usage_proposed: number;
  usage_handoff: number;
  conversion_pct: number;
  updated_at?: string | null;
};

type Draft = Omit<DiscountCode, "usage_proposed" | "usage_handoff" | "conversion_pct" | "updated_at" | "trigger_signals"> & {
  trigger_signals: string;
};

type Tab = "traffic" | "codes";
type CodeFilter = "all" | "with" | "without";

const TOKEN_KEY = "hygge-admin-token";
const WINDOWS = [7, 30, 90];

const EMPTY_DRAFT: Draft = {
  code: "",
  discount_label: "",
  stay_from: null,
  stay_to: null,
  valid_from: null,
  valid_to: null,
  active: true,
  announceable: false,
  trigger_signals: "",
  priority: 100,
  max_per_session: 1,
  notes_for_agent: "",
};

const TRIGGER_HELP =
  "lead_days_max:N · weekdays:[1-7] (1 = pon.) · min_nights:N · cabins:[12,13] · returning_guest · price_hesitation · asked_for_discount";

async function read<T>(path: string, token: string): Promise<T> {
  return request<T>(path, token);
}

async function request<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_URL}/api/admin/${path}`, {
    ...init,
    headers: { Authorization: `Bearer ${token}`, ...(init.body ? { "Content-Type": "application/json" } : {}) },
  });
  if (response.status === 401) throw new Error("Nieprawidłowy token.");
  if (response.status === 404) throw new Error("Panel wyłączony: ADMIN_TOKEN nie jest ustawiony.");
  if (response.status === 409) throw new Error("Taki kod już istnieje.");
  if (response.status === 422) {
    const body = (await response.json().catch(() => null)) as { detail?: { loc?: unknown[]; msg?: string }[] } | null;
    const first = body?.detail?.[0];
    throw new Error(first ? `Błąd w polu ${String(first.loc?.at(-1) ?? "")}: ${first.msg ?? ""}` : "Nieprawidłowe dane.");
  }
  if (!response.ok) throw new Error(`Błąd ${response.status}.`);
  return (await response.json()) as T;
}

function hasCode(talk: Conversation): boolean {
  return talk.events.some((event) => event.kind === "offer_proposed");
}

function Tile({ label, value = 0, hint }: { label: string; value?: number; hint?: string }) {
  return (
    <div
      className="flex flex-col gap-0.5 rounded-xl border p-3"
      style={{ borderColor: "var(--line)", background: "var(--surface)" }}
    >
      <span className="text-[11px] uppercase tracking-wide" style={{ color: "var(--ink-soft)" }}>
        {label}
      </span>
      <span className="text-[26px] font-bold tabular-nums leading-none" style={{ color: "var(--ink)" }}>
        {value}
      </span>
      {hint ? (
        <span className="text-[11px]" style={{ color: "var(--ink-soft)" }}>
          {hint}
        </span>
      ) : null}
    </div>
  );
}

/** One line per event, so a whole conversation can be read in the order it happened. */
function EventLine({ event }: { event: Event }) {
  const data = event.data;
  const at = event.at.slice(11, 19);
  const detail =
    event.kind === "message"
      ? `${data.role === "guest" ? "gość" : "asystent"}: ${String(data.text ?? "")}`
      : event.kind === "tool_call"
        ? `${String(data.tool ?? "")} ${JSON.stringify(data.arguments ?? {})}`
        : event.kind === "feedback"
          ? `${data.verdict === "down" ? "kciuk w dół" : String(data.verdict)}${data.reason ? ` — ${String(data.reason)}` : ""}`
          : event.kind === "click"
            ? `przejście do idobooking (${String(data.product_id ?? "")})`
            : event.kind === "offer_proposed"
              ? `zaproponowano kod ${String(data.code ?? "")}`
              : event.kind === "offer_handoff"
                ? `kod ${String(data.code ?? "")} na karcie rezerwacji`
                : event.kind === "error"
                  ? String(data.message ?? "")
                  : "";
  const loud = event.kind === "feedback" || event.kind === "error";
  const offer = event.kind === "offer_proposed" || event.kind === "offer_handoff";
  return (
    <div className="flex gap-2 py-0.5 text-[12px]">
      <span className="shrink-0 tabular-nums" style={{ color: "var(--ink-soft)" }}>
        {at}
      </span>
      <span className="w-[108px] shrink-0" style={{ color: loud ? "var(--accent)" : offer ? "var(--accent-ink)" : "var(--ink-soft)" }}>
        {event.kind}
      </span>
      <span className="min-w-0 break-words" style={{ color: "var(--ink)" }}>
        {detail}
      </span>
    </div>
  );
}

function Segmented<T extends string | number>({ value, options, onChange }: { value: T; options: { id: T; label: string }[]; onChange: (id: T) => void }) {
  return (
    <div className="flex items-center gap-1">
      {options.map((option) => (
        <button
          key={option.id}
          type="button"
          onClick={() => onChange(option.id)}
          aria-pressed={value === option.id}
          className="rounded-full px-2.5 py-1 text-[12px]"
          style={value === option.id ? { background: "var(--ink)", color: "var(--surface)" } : { color: "var(--ink-soft)", background: "var(--well)" }}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

const INPUT: React.CSSProperties = { borderColor: "var(--line)", background: "var(--surface)", color: "var(--ink)" };

function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <label className="flex flex-col gap-1 text-[12px]" style={{ color: "var(--ink-soft)" }}>
      <span>{label}</span>
      {children}
      {hint ? <span className="text-[11px]">{hint}</span> : null}
    </label>
  );
}

function toDraft(code: DiscountCode): Draft {
  return { ...code, trigger_signals: code.trigger_signals.join(", ") };
}

function fromDraft(draft: Draft) {
  return {
    ...draft,
    code: draft.code.trim().toUpperCase(),
    stay_from: draft.stay_from || null,
    stay_to: draft.stay_to || null,
    valid_from: draft.valid_from || null,
    valid_to: draft.valid_to || null,
    trigger_signals: draft.trigger_signals
      .split(/[,\n;]+/)
      .map((signal) => signal.trim())
      .filter(Boolean),
  };
}

function CodeForm({ initial, editing, busy, onSave, onCancel }: { initial: Draft; editing: boolean; busy: boolean; onSave: (draft: Draft) => Promise<void>; onCancel: () => void }) {
  const [draft, setDraft] = useState<Draft>(initial);
  useEffect(() => setDraft(initial), [initial]);
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((current) => ({ ...current, [key]: value }));
  const submit = (event: FormEvent) => {
    event.preventDefault();
    void onSave(draft);
  };
  return (
    <form onSubmit={submit} className="mb-4 rounded-xl border p-4" style={{ borderColor: "var(--line)", background: "var(--surface)" }}>
      <h3 className="mb-3 text-[13px] font-semibold" style={{ color: "var(--ink)" }}>
        {editing ? `Edytuj kod ${initial.code}` : "Nowy kod"}
      </h3>
      <p className="mb-3 text-[12px]" style={{ color: "var(--ink-soft)" }}>
        Pola z panelu IdoBooking (1:1): kod, rabat i terminy muszą być identyczne z tym, co wpisano tam.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Kod (dokładnie jak w IdoBooking)">
          <input required disabled={editing} value={draft.code} onChange={(e) => set("code", e.target.value.toUpperCase())} className="rounded-lg border px-2.5 py-1.5 font-mono uppercase" style={INPUT} maxLength={40} />
        </Field>
        <Field label="Rabat (etykieta, np. -15% / -100 zł / 3. noc -50%)" hint="Tylko do komunikacji — wartość liczy IdoBooking.">
          <input required value={draft.discount_label} onChange={(e) => set("discount_label", e.target.value)} className="rounded-lg border px-2.5 py-1.5" style={INPUT} maxLength={60} />
        </Field>
        <Field label="Termin objęty rabatem — od">
          <input type="date" value={draft.stay_from ?? ""} onChange={(e) => set("stay_from", e.target.value || null)} className="rounded-lg border px-2.5 py-1.5" style={INPUT} />
        </Field>
        <Field label="Termin objęty rabatem — do">
          <input type="date" value={draft.stay_to ?? ""} onChange={(e) => set("stay_to", e.target.value || null)} className="rounded-lg border px-2.5 py-1.5" style={INPUT} />
        </Field>
        <Field label="Ważność kodu — od">
          <input type="date" value={draft.valid_from ?? ""} onChange={(e) => set("valid_from", e.target.value || null)} className="rounded-lg border px-2.5 py-1.5" style={INPUT} />
        </Field>
        <Field label="Ważność kodu — do">
          <input type="date" value={draft.valid_to ?? ""} onChange={(e) => set("valid_to", e.target.value || null)} className="rounded-lg border px-2.5 py-1.5" style={INPUT} />
        </Field>
      </div>
      <p className="mb-3 mt-4 text-[12px]" style={{ color: "var(--ink-soft)" }}>
        Reguły agenta: kiedy i komu proponować.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-2 text-[13px]" style={{ color: "var(--ink)" }}>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={draft.active} onChange={(e) => set("active", e.target.checked)} /> Aktywny
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={draft.announceable} onChange={(e) => set("announceable", e.target.checked)} /> Ogłaszany (może pojawić się na ekranie głównym i bez pytania)
          </label>
        </div>
        <Field label="Sygnały (wszystkie muszą być spełnione), po przecinku" hint={TRIGGER_HELP}>
          <textarea value={draft.trigger_signals} onChange={(e) => set("trigger_signals", e.target.value)} rows={2} className="rounded-lg border px-2.5 py-1.5 font-mono text-[12px]" style={INPUT} />
        </Field>
        <Field label="Priorytet (niższy = proponowany wcześniej)">
          <input type="number" min={0} max={10000} value={draft.priority} onChange={(e) => set("priority", Number(e.target.value))} className="rounded-lg border px-2.5 py-1.5" style={INPUT} />
        </Field>
        <Field label="Maks. propozycji w jednej rozmowie">
          <input type="number" min={1} max={20} value={draft.max_per_session} onChange={(e) => set("max_per_session", Number(e.target.value))} className="rounded-lg border px-2.5 py-1.5" style={INPUT} />
        </Field>
        <div className="sm:col-span-2">
          <Field label="Wskazówka dla agenta (jedno zdanie, jak go sprzedać)">
            <input value={draft.notes_for_agent} onChange={(e) => set("notes_for_agent", e.target.value)} className="rounded-lg border px-2.5 py-1.5" style={INPUT} maxLength={300} placeholder="np. podkreśl, że tylko do niedzieli" />
          </Field>
        </div>
      </div>
      <div className="mt-4 flex gap-2">
        <button type="submit" disabled={busy} className="rounded-lg px-4 py-2 text-[13px] font-semibold disabled:opacity-50" style={{ background: "var(--ink)", color: "var(--surface)" }}>
          {editing ? "Zapisz" : "Dodaj kod"}
        </button>
        <button type="button" onClick={onCancel} className="rounded-lg px-4 py-2 text-[13px]" style={{ color: "var(--ink-soft)", background: "var(--well)" }}>
          Anuluj
        </button>
      </div>
    </form>
  );
}

function CodesTab({ token }: { token: string }) {
  const [codes, setCodes] = useState<DiscountCode[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Draft | null>(null);
  const [isNew, setIsNew] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      setCodes((await read<{ codes: DiscountCode[] }>("discount-codes", token)).codes);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Nie udało się pobrać kodów.");
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async (draft: Draft) => {
    setBusy(true);
    setError(null);
    try {
      const body = JSON.stringify(fromDraft(draft));
      if (isNew) await request("discount-codes", token, { method: "POST", body });
      else await request(`discount-codes/${encodeURIComponent(draft.code)}`, token, { method: "PUT", body });
      setEditing(null);
      await load();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Nie udało się zapisać.");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (code: string) => {
    if (!window.confirm(`Usunąć kod ${code} z agenta? (W IdoBooking pozostaje bez zmian.)`)) return;
    setError(null);
    try {
      await request(`discount-codes/${encodeURIComponent(code)}`, token, { method: "DELETE" });
      await load();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Nie udało się usunąć.");
    }
  };

  const total = codes.reduce((sum, code) => sum + code.usage_proposed, 0);
  const handed = codes.reduce((sum, code) => sum + code.usage_handoff, 0);

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <p className="text-[12.5px]" style={{ color: "var(--ink-soft)" }}>
          IdoBooking nie ma API do kodów: kod zakładasz ręcznie w panelu IdoBooking, a tu odwzorowujesz go i ustalasz, kiedy agent ma go proponować. Gość wpisuje kod sam w formularzu rezerwacji.
        </p>
        <button
          type="button"
          onClick={() => {
            setIsNew(true);
            setEditing(EMPTY_DRAFT);
          }}
          className="ml-auto rounded-lg px-3 py-1.5 text-[12.5px] font-semibold"
          style={{ background: "var(--ink)", color: "var(--surface)" }}
        >
          + Nowy kod
        </button>
      </div>
      {error ? (
        <p className="mb-3 text-[13px]" style={{ color: "var(--accent)" }}>
          {error}
        </p>
      ) : null}
      {editing ? <CodeForm initial={editing} editing={!isNew} busy={busy} onSave={save} onCancel={() => setEditing(null)} /> : null}
      <div className="mb-4 grid grid-cols-3 gap-2">
        <Tile label="Zaproponowano" value={total} hint="razem, wszystkie kody" />
        <Tile label="Handoff" value={handed} hint="kod trafił na kartę rezerwacji" />
        <Tile label="Konwersja" value={total ? Math.round((handed / total) * 1000) / 10 : 0} hint="% handoff / zaproponowano" />
      </div>
      <div className="overflow-x-auto rounded-xl border" style={{ borderColor: "var(--line)", background: "var(--surface)" }}>
        <table className="w-full text-left text-[12px]" style={{ color: "var(--ink)" }}>
          <thead>
            <tr className="text-[11px] uppercase tracking-wide" style={{ color: "var(--ink-soft)" }}>
              {["Kod", "Rabat", "Pobyt", "Ważność", "Stan", "Sygnały", "Prior.", "Max/rozm.", "Zaproponowano", "Handoff", "Konwersja", ""].map((head) => (
                <th key={head} className="whitespace-nowrap px-3 py-2 font-semibold">
                  {head}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {codes.map((code) => (
              <tr key={code.code} className="border-t align-top" style={{ borderColor: "var(--line)", opacity: code.active ? 1 : 0.55 }}>
                <td className="px-3 py-2 font-mono font-semibold">{code.code}</td>
                <td className="px-3 py-2">{code.discount_label}</td>
                <td className="whitespace-nowrap px-3 py-2 tabular-nums">
                  {code.stay_from ?? "…"} – {code.stay_to ?? "…"}
                </td>
                <td className="whitespace-nowrap px-3 py-2 tabular-nums">
                  {code.valid_from ?? "…"} – {code.valid_to ?? "…"}
                </td>
                <td className="whitespace-nowrap px-3 py-2">
                  {code.active ? "aktywny" : "wyłączony"}
                  <br />
                  <span style={{ color: "var(--ink-soft)" }}>{code.announceable ? "ogłaszany" : "po sygnale"}</span>
                </td>
                <td className="px-3 py-2 font-mono text-[11px]">{code.trigger_signals.join(", ") || "—"}</td>
                <td className="px-3 py-2 tabular-nums">{code.priority}</td>
                <td className="px-3 py-2 tabular-nums">{code.max_per_session}</td>
                <td className="px-3 py-2 tabular-nums">{code.usage_proposed}</td>
                <td className="px-3 py-2 tabular-nums">{code.usage_handoff}</td>
                <td className="px-3 py-2 tabular-nums">{code.conversion_pct}%</td>
                <td className="whitespace-nowrap px-3 py-2">
                  <button
                    type="button"
                    onClick={() => {
                      setIsNew(false);
                      setEditing(toDraft(code));
                    }}
                    className="mr-2 underline underline-offset-2"
                  >
                    Edytuj
                  </button>
                  <button type="button" onClick={() => remove(code.code)} className="underline underline-offset-2" style={{ color: "var(--accent)" }}>
                    Usuń
                  </button>
                </td>
              </tr>
            ))}
            {!codes.length && !error ? (
              <tr>
                <td colSpan={12} className="px-3 py-4 text-[13px]" style={{ color: "var(--ink-soft)" }}>
                  Brak kodów. Dodaj pierwszy, odwzorowując kod z panelu IdoBooking.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TrafficTab({ token }: { token: string }) {
  const [days, setDays] = useState(30);
  const [stats, setStats] = useState<Stats | null>(null);
  const [talks, setTalks] = useState<Conversation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [codeFilter, setCodeFilter] = useState<CodeFilter>("all");

  const load = useCallback(async () => {
    setError(null);
    try {
      const [summary, recent] = await Promise.all([
        read<Stats>(`stats?days=${days}`, token),
        read<{ conversations: Conversation[] }>("conversations?limit=50", token),
      ]);
      setStats(summary);
      setTalks(recent.conversations);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Nie udało się pobrać danych.");
      setStats(null);
      setTalks([]);
    }
  }, [token, days]);

  useEffect(() => {
    void load();
  }, [load]);

  const withCode = talks.filter(hasCode).length;
  const shown = talks.filter((talk) => (codeFilter === "all" ? true : codeFilter === "with" ? hasCode(talk) : !hasCode(talk)));

  return (
    <div>
      <div className="mb-4 flex items-center gap-1">
        <Segmented value={days} options={WINDOWS.map((window_) => ({ id: window_, label: `${window_} dni` }))} onChange={setDays} />
      </div>
      {error ? (
        <p className="mb-4 text-[13px]" style={{ color: "var(--accent)" }}>
          {error}
        </p>
      ) : null}
      {stats ? (
        <div className="mb-6 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Tile label="Sesje" value={stats.sessions} hint="ilu gości zaczęło rozmowę" />
          <Tile label="Interakcje" value={stats.interactions} hint="pytań od gości" />
          <Tile label="Oferty" value={stats.offers} hint={`${stats.cabins_shown ?? 0} domków pokazanych`} />
          <Tile label="Do idobooking" value={stats.booking_clicks} hint="kliknięć w rezerwację" />
          <Tile label="Odpowiedzi" value={stats.replies} />
          <Tile label="Kciuki w dół" value={stats.thumbs_down} hint="odpowiedzi ocenione źle" />
          <Tile label="Błędy" value={stats.errors} />
          <Tile label="Na sesję" value={stats.sessions ? Math.round(((stats.interactions ?? 0) / stats.sessions) * 10) / 10 : 0} hint="pytań na jedną rozmowę" />
        </div>
      ) : null}

      <div className="mb-2 flex flex-wrap items-center gap-3">
        <h2 className="text-[13px] font-semibold" style={{ color: "var(--ink)" }}>
          Ostatnie rozmowy
        </h2>
        <Segmented
          value={codeFilter}
          options={[
            { id: "all", label: `wszystkie (${talks.length})` },
            { id: "with", label: `z kodem (${withCode})` },
            { id: "without", label: `bez kodu (${talks.length - withCode})` },
          ]}
          onChange={setCodeFilter}
        />
      </div>
      <div className="flex flex-col gap-2">
        {shown.map((talk) => {
          const asked = talk.events.filter((event) => event.kind === "message" && event.data.role === "guest");
          const first = asked[0]?.data.text ? String(asked[0].data.text) : "(bez pytania)";
          const flagged = talk.events.some((event) => event.kind === "feedback");
          const codes = [...new Set(talk.events.filter((event) => event.kind === "offer_proposed").map((event) => String(event.data.code ?? "")))];
          const handed = talk.events.some((event) => event.kind === "offer_handoff");
          const expanded = open === talk.session_id;
          return (
            <div key={talk.session_id} className="rounded-xl border p-3" style={{ borderColor: "var(--line)", background: "var(--surface)" }}>
              <button type="button" onClick={() => setOpen(expanded ? null : talk.session_id)} className="flex w-full items-center gap-2 text-left">
                <span className="text-[11px] tabular-nums" style={{ color: "var(--ink-soft)" }}>
                  {talk.started.slice(0, 16).replace("T", " ")}
                </span>
                {flagged ? (
                  <span className="rounded-full px-1.5 text-[10px] font-semibold" style={{ background: "var(--accent)", color: "var(--surface)" }}>
                    ocena
                  </span>
                ) : null}
                {codes.length ? (
                  <span className="rounded-full px-1.5 text-[10px] font-semibold" style={{ background: "var(--accent-soft)", color: "var(--accent-ink)" }}>
                    {codes.join(", ")}
                    {handed ? " ✓" : ""}
                  </span>
                ) : null}
                <span className="min-w-0 flex-1 truncate text-[13px]" style={{ color: "var(--ink)" }}>
                  {first}
                </span>
                <span className="text-[11px]" style={{ color: "var(--ink-soft)" }}>
                  {asked.length} pyt. · {expanded ? "zwiń" : "rozwiń"}
                </span>
              </button>
              {expanded ? (
                <div className="mt-2 border-t pt-2" style={{ borderColor: "var(--line)" }}>
                  {talk.events.map((event, index) => (
                    <EventLine key={index} event={event} />
                  ))}
                </div>
              ) : null}
            </div>
          );
        })}
        {!shown.length && !error ? (
          <p className="text-[13px]" style={{ color: "var(--ink-soft)" }}>
            {talks.length ? "Brak rozmów w tym filtrze." : "Jeszcze nic nie zapisano."}
          </p>
        ) : null}
      </div>
    </div>
  );
}

export default function AdminPage() {
  const [token, setToken] = useState("");
  const [typed, setTyped] = useState("");
  const [tab, setTab] = useState<Tab>("traffic");

  useEffect(() => {
    try {
      setToken(window.sessionStorage.getItem(TOKEN_KEY) ?? "");
    } catch {
      // Storage blocked: the token simply has to be typed again.
    }
  }, []);

  if (!token) {
    return (
      <main className="mx-auto max-w-[420px] p-8">
        <h1 className="al-display mb-1 text-[22px]" style={{ color: "var(--ink)" }}>
          Asystent Hygge — panel
        </h1>
        <p className="mb-4 text-[13px]" style={{ color: "var(--ink-soft)" }}>
          Wklej token dostępu, żeby zobaczyć statystyki, rozmowy i kody rabatowe.
        </p>
        <form
          className="flex gap-2"
          onSubmit={(submit) => {
            submit.preventDefault();
            try {
              window.sessionStorage.setItem(TOKEN_KEY, typed.trim());
            } catch {
              // Not stored is fine; the value in state still works for this visit.
            }
            setToken(typed.trim());
          }}
        >
          <input
            type="password"
            value={typed}
            onChange={(change) => setTyped(change.target.value)}
            placeholder="Token"
            className="min-w-0 flex-1 rounded-lg border px-3 py-2 text-[13px]"
            style={{ borderColor: "var(--line)", background: "var(--surface)", color: "var(--ink)" }}
          />
          <button type="submit" className="rounded-lg px-4 py-2 text-[13px] font-semibold" style={{ background: "var(--ink)", color: "var(--surface)" }}>
            Wejdź
          </button>
        </form>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-[1100px] p-6">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h1 className="al-display text-[22px]" style={{ color: "var(--ink)" }}>
          Asystent Hygge — panel
        </h1>
        <nav className="flex items-center gap-1" aria-label="Zakładki">
          <Segmented
            value={tab}
            options={[
              { id: "traffic", label: "Statystyki i rozmowy" },
              { id: "codes", label: "Kody rabatowe" },
            ]}
            onChange={setTab}
          />
        </nav>
        <button
          type="button"
          onClick={() => {
            try {
              window.sessionStorage.removeItem(TOKEN_KEY);
            } catch {
              // Nothing stored to clear.
            }
            setToken("");
          }}
          className="ml-auto text-[12px] underline underline-offset-2"
          style={{ color: "var(--ink-soft)" }}
        >
          Wyloguj
        </button>
      </div>
      {tab === "codes" ? <CodesTab token={token} /> : <TrafficTab token={token} />}
    </main>
  );
}
