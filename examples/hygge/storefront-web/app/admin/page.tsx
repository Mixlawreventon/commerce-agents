// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { useCallback, useEffect, useState } from "react";
import { API_URL } from "@/lib/api";

/**
 * What the assistant did, read back.
 *
 * The token is asked for here and kept in sessionStorage rather than put in the URL: a
 * query string ends up in history, in referrers, and in every access log between here and
 * the API. Nothing on this page is fetched until a token is entered, so the page itself
 * gives away nothing.
 */

type Stats = {
  days: number;
  sessions: number;
  interactions: number;
  replies: number;
  offers: number;
  cabins_shown: number;
  booking_clicks: number;
  thumbs_down: number;
  errors: number;
};

type Event = { at: string; kind: string; data: Record<string, unknown> };
type Conversation = { session_id: string; started: string; events: Event[] };

const TOKEN_KEY = "hygge-admin-token";
const WINDOWS = [7, 30, 90];

async function read<T>(path: string, token: string): Promise<T> {
  const response = await fetch(`${API_URL}/api/admin/${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (response.status === 401) throw new Error("Nieprawidłowy token.");
  if (response.status === 404) throw new Error("Panel wyłączony: ADMIN_TOKEN nie jest ustawiony.");
  if (!response.ok) throw new Error(`Błąd ${response.status}.`);
  return (await response.json()) as T;
}

function Tile({ label, value, hint }: { label: string; value: number; hint?: string }) {
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
            : event.kind === "error"
              ? String(data.message ?? "")
              : "";
  const loud = event.kind === "feedback" || event.kind === "error";
  return (
    <div className="flex gap-2 py-0.5 text-[12px]">
      <span className="shrink-0 tabular-nums" style={{ color: "var(--ink-soft)" }}>
        {at}
      </span>
      <span className="w-[92px] shrink-0" style={{ color: loud ? "var(--accent)" : "var(--ink-soft)" }}>
        {event.kind}
      </span>
      <span className="min-w-0 break-words" style={{ color: "var(--ink)" }}>
        {detail}
      </span>
    </div>
  );
}

export default function AdminPage() {
  const [token, setToken] = useState("");
  const [typed, setTyped] = useState("");
  const [days, setDays] = useState(30);
  const [stats, setStats] = useState<Stats | null>(null);
  const [talks, setTalks] = useState<Conversation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    try {
      setToken(window.sessionStorage.getItem(TOKEN_KEY) ?? "");
    } catch {
      // Storage blocked: the token simply has to be typed again.
    }
  }, []);

  const load = useCallback(async () => {
    if (!token) return;
    setError(null);
    try {
      const [summary, recent] = await Promise.all([
        read<Stats>(`stats?days=${days}`, token),
        read<{ conversations: Conversation[] }>("conversations?limit=25", token),
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

  if (!token) {
    return (
      <main className="mx-auto max-w-[420px] p-8">
        <h1 className="al-display mb-1 text-[22px]" style={{ color: "var(--ink)" }}>
          Asystent Hygge — panel
        </h1>
        <p className="mb-4 text-[13px]" style={{ color: "var(--ink-soft)" }}>
          Wklej token dostępu, żeby zobaczyć statystyki i rozmowy.
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
          <button
            type="submit"
            className="rounded-lg px-4 py-2 text-[13px] font-semibold"
            style={{ background: "var(--ink)", color: "var(--surface)" }}
          >
            Wejdź
          </button>
        </form>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-[900px] p-6">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h1 className="al-display text-[22px]" style={{ color: "var(--ink)" }}>
          Asystent Hygge — panel
        </h1>
        <div className="ml-auto flex items-center gap-1">
          {WINDOWS.map((window_) => (
            <button
              key={window_}
              type="button"
              onClick={() => setDays(window_)}
              aria-pressed={days === window_}
              className="rounded-full px-2.5 py-1 text-[12px]"
              style={
                days === window_
                  ? { background: "var(--ink)", color: "var(--surface)" }
                  : { color: "var(--ink-soft)", background: "var(--well)" }
              }
            >
              {window_} dni
            </button>
          ))}
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
            className="ml-2 text-[12px] underline underline-offset-2"
            style={{ color: "var(--ink-soft)" }}
          >
            Wyloguj
          </button>
        </div>
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
          <Tile label="Oferty" value={stats.offers} hint={`${stats.cabins_shown} domków pokazanych`} />
          <Tile label="Do idobooking" value={stats.booking_clicks} hint="kliknięć w rezerwację" />
          <Tile label="Odpowiedzi" value={stats.replies} />
          <Tile label="Kciuki w dół" value={stats.thumbs_down} hint="odpowiedzi ocenione źle" />
          <Tile label="Błędy" value={stats.errors} />
          <Tile
            label="Na sesję"
            value={stats.sessions ? Math.round((stats.interactions / stats.sessions) * 10) / 10 : 0}
            hint="pytań na jedną rozmowę"
          />
        </div>
      ) : null}

      <h2 className="mb-2 text-[13px] font-semibold" style={{ color: "var(--ink)" }}>
        Ostatnie rozmowy
      </h2>
      <div className="flex flex-col gap-2">
        {talks.map((talk) => {
          const asked = talk.events.filter(
            (event) => event.kind === "message" && event.data.role === "guest",
          );
          const first = asked[0]?.data.text ? String(asked[0].data.text) : "(bez pytania)";
          const flagged = talk.events.some((event) => event.kind === "feedback");
          const expanded = open === talk.session_id;
          return (
            <div
              key={talk.session_id}
              className="rounded-xl border p-3"
              style={{ borderColor: "var(--line)", background: "var(--surface)" }}
            >
              <button
                type="button"
                onClick={() => setOpen(expanded ? null : talk.session_id)}
                className="flex w-full items-center gap-2 text-left"
              >
                <span className="text-[11px] tabular-nums" style={{ color: "var(--ink-soft)" }}>
                  {talk.started.slice(0, 16).replace("T", " ")}
                </span>
                {flagged ? (
                  <span
                    className="rounded-full px-1.5 text-[10px] font-semibold"
                    style={{ background: "var(--accent)", color: "var(--surface)" }}
                  >
                    ocena
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
        {!talks.length && !error ? (
          <p className="text-[13px]" style={{ color: "var(--ink-soft)" }}>
            Jeszcze nic nie zapisano.
          </p>
        ) : null}
      </div>
    </main>
  );
}
