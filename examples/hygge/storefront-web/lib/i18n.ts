// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { useEffect, useState } from "react";

export type Lang = "pl" | "en" | "de";

export const LANGS: { code: Lang; label: string }[] = [
  { code: "pl", label: "PL" },
  { code: "en", label: "EN" },
  { code: "de", label: "DE" },
];

export const DEFAULT_LANG: Lang = "pl";

type Key =
  | "viewAssistant"
  | "viewStays"
  | "bagLabel"
  | "bagNoun"
  | "placeholderAssistant"
  | "placeholderStays"
  | "heroTitle"
  | "opener"
  | "starterWeekend"
  | "starterJacuzzi"
  | "starterPets"
  | "starterBooking"
  | "sectionTitle"
  | "sectionSubtitle"
  | "staysSubtitle"
  | "askCabin"
  | "assistantName";

const DICT: Record<Lang, Record<Key, string>> = {
  pl: {
    viewAssistant: "Asystent",
    viewStays: "Pobyty",
    bagLabel: "Pobyt",
    bagNoun: "rezerwacja",
    placeholderAssistant: "Zapytaj o domek, terminy, jacuzzi, psa…",
    placeholderStays: "Zapytaj o rezerwację, zmianę, zwrot…",
    heroTitle: "Gotowi na odpoczynek, {name}?",
    opener: "Podaj termin, a Asystent Hygge znajdzie odpowiedni domek w lesie na Wasz pobyt.",
    starterWeekend: "Znajdź domek na najbliższy weekend",
    starterJacuzzi: "Domek z jacuzzi na tarasie",
    starterPets: "Coś przyjaznego zwierzakom blisko jeziora",
    starterBooking: "Jaki jest status mojej rezerwacji?",
    sectionTitle: "Zacznij od domku",
    sectionSubtitle: "Wybierz jeden, a Asystent Hygge opowie Ci o nim",
    staysSubtitle: "Zapytaj o dowolny z nich albo zaplanuj kolejny pobyt na podstawie poprzedniego.",
    askCabin: "Opowiedz o domku {city}",
    assistantName: "Asystent Hygge",
  },
  en: {
    viewAssistant: "Assistant",
    viewStays: "Stays",
    bagLabel: "Stay",
    bagNoun: "booking",
    placeholderAssistant: "Ask about a cabin, dates, a jacuzzi, your dog…",
    placeholderStays: "Ask about a booking, a change, a refund…",
    heroTitle: "Ready to unwind, {name}?",
    opener: "Tell me your dates and the Hygge Assistant finds the right forest cabin for your stay.",
    starterWeekend: "Find a cabin for next weekend",
    starterJacuzzi: "A cabin with a jacuzzi on the terrace",
    starterPets: "Somewhere pet-friendly near the lake",
    starterBooking: "What's the status of my booking?",
    sectionTitle: "Start from a cabin",
    sectionSubtitle: "Pick one and the Hygge Assistant tells you about it",
    staysSubtitle: "Ask about any of them, or plan the next one from a past stay.",
    askCabin: "Tell me about the {city} cabin",
    assistantName: "Hygge Assistant",
  },
  de: {
    viewAssistant: "Assistent",
    viewStays: "Aufenthalte",
    bagLabel: "Aufenthalt",
    bagNoun: "Buchung",
    placeholderAssistant: "Frag nach einem Häuschen, Terminen, Whirlpool, Hund…",
    placeholderStays: "Frag nach einer Buchung, Änderung, Erstattung…",
    heroTitle: "Bereit zum Entspannen, {name}?",
    opener: "Nenne deine Termine und der Hygge-Assistent findet das passende Waldhäuschen für deinen Aufenthalt.",
    starterWeekend: "Finde ein Häuschen fürs nächste Wochenende",
    starterJacuzzi: "Ein Häuschen mit Whirlpool auf der Terrasse",
    starterPets: "Etwas Haustierfreundliches am See",
    starterBooking: "Wie ist der Status meiner Buchung?",
    sectionTitle: "Beginne mit einem Häuschen",
    sectionSubtitle: "Wähle eines und der Hygge-Assistent erzählt dir davon",
    staysSubtitle: "Frag nach einem davon oder plane den nächsten Aufenthalt aus einem früheren.",
    askCabin: "Erzähl mir vom Häuschen {city}",
    assistantName: "Hygge-Assistent",
  },
};

export function t(lang: Lang, key: Key, vars?: Record<string, string>): string {
  let s = DICT[lang]?.[key] ?? DICT.en[key] ?? key;
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.replace(`{${k}}`, v);
  return s;
}

const STORAGE_KEY = "hygge-lang";

/** Reactive language state persisted to localStorage; defaults to Polish. */
export function useLang(): [Lang, (l: Lang) => void] {
  const [lang, setLang] = useState<Lang>(DEFAULT_LANG);
  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY) as Lang | null;
    if (stored && stored in DICT) setLang(stored);
  }, []);
  const update = (l: Lang) => {
    setLang(l);
    window.localStorage.setItem(STORAGE_KEY, l);
    document.documentElement.lang = l;
  };
  return [lang, update];
}
