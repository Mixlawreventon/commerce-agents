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
  | "starterBooking"
  | "sectionTitle"
  | "sectionSubtitle"
  | "staysSubtitle"
  | "askCabin"
  | "assistantName"
  | "heroTitleAnon"
  | "guestName"
  | "bagTitle"
  | "bagEmpty"
  | "bagTotal"
  | "bagTotalNote"
  | "bagAsk"
  | "starterPackages"
  | "feedbackDown"
  | "feedbackReason"
  | "feedbackSend"
  | "feedbackThanks"
  | "privacyNote"
  | "bookAt"
  | "openingsTitle"
  | "openingsWeekend"
  | "openingsMidweek"
  | "openingsNights"
  | "openingsCabinsLeft"
  | "openingsPrompt"
  | "cabinsTitle"
  | "cabinsFrom"
  | "cabinPrompt"
  | "offersTitle"
  | "offersCode"
  | "offersStay"
  | "offersBookBy"
  | "offerPrompt"
  | "homeUnavailable"
  | "promoTitle"
  | "promoCopy"
  | "promoCopied"
  | "promoHint";

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
    starterBooking: "Jaki jest status mojej rezerwacji?",
    sectionTitle: "Zacznij od domku",
    sectionSubtitle: "Wybierz jeden, a Asystent Hygge pokaże wolne terminy, ceny i promocje",
    staysSubtitle: "Zapytaj o dowolny z nich albo zaplanuj kolejny pobyt na podstawie poprzedniego.",
    askCabin: "Pokaż wolne terminy domku {city} w najbliższych tygodniach z aktualnymi cenami i promocjami.",
    assistantName: "Asystent Hygge",
    heroTitleAnon: "Gotowi na odpoczynek?",
    guestName: "Gość",
    bagTitle: "Pobyt",
    bagEmpty: "Nic jeszcze nie wybrano.\nZapytaj Asystenta Hygge o wolny domek.",
    bagTotal: "Razem za pobyt",
    bagTotalNote: "Cena całkowita; nic nie jest pobierane na tym etapie.",
    bagAsk: "Zapytaj o ten pobyt",
    starterPackages: "Jakie są promocje na dłuższy pobyt?",
    feedbackDown: "Ta odpowiedź mi nie pomogła",
    feedbackReason: "Co było nie tak? (opcjonalnie)",
    feedbackSend: "Wyślij",
    feedbackThanks: "Dziękujemy — przekazaliśmy to dalej.",
    privacyNote: "Rozmowy z asystentem zapisujemy, żeby go ulepszać. Nie podawaj danych karty ani hasła.",
    bookAt: "Rezerwuj w idobooking",
    openingsTitle: "Najbliższe wolne terminy",
    openingsWeekend: "Weekend",
    openingsMidweek: "W tygodniu",
    openingsNights: "{n} noce",
    openingsCabinsLeft: "{n} wolnych domków",
    openingsPrompt: "Szukam domku dla 2 osób od {arrival} do {departure} ({kind}). Co jest wolne i w jakiej cenie?",
    cabinsTitle: "Domki",
    cabinsFrom: "od {price}",
    cabinPrompt: "Pokaż wolne terminy domku {name} w najbliższych tygodniach z aktualnymi cenami i promocjami.",
    offersTitle: "Oferty",
    offersCode: "Kod",
    offersStay: "pobyt {from} – {to}",
    offersBookBy: "rezerwacja do {date}",
    offerPrompt: "Jak skorzystać z oferty {title}? Jakie terminy obejmuje?",
    homeUnavailable: "Nic jeszcze nie wybrano.\nZapytaj Asystenta Hygge o wolny domek.",
    promoTitle: "Twój kod rabatowy",
    promoCopy: "Kopiuj",
    promoCopied: "Skopiowano",
    promoHint: "Wklej kod w polu kodu rabatowego w formularzu rezerwacji.",
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
    starterBooking: "What's the status of my booking?",
    sectionTitle: "Start from a cabin",
    sectionSubtitle: "Pick one and the Hygge Assistant shows its free dates, prices and offers",
    staysSubtitle: "Ask about any of them, or plan the next one from a past stay.",
    askCabin: "Show the {city} cabin's free dates in the coming weeks, with current prices and offers.",
    assistantName: "Hygge Assistant",
    heroTitleAnon: "Ready to unwind?",
    guestName: "Guest",
    bagTitle: "Stay",
    bagEmpty: "Nothing chosen yet.\nAsk the Hygge Assistant about a free cabin.",
    bagTotal: "Stay total",
    bagTotalNote: "All-in; nothing is charged at this stage.",
    bagAsk: "Ask about this stay",
    starterPackages: "What discounts are there for a longer stay?",
    feedbackDown: "This reply didn't help",
    feedbackReason: "What was wrong? (optional)",
    feedbackSend: "Send",
    feedbackThanks: "Thank you — we've passed this on.",
    privacyNote: "We keep these conversations to improve the assistant. Please don't share card details or passwords.",
    bookAt: "Book on idobooking",
    openingsTitle: "Nearest open dates",
    openingsWeekend: "Weekend",
    openingsMidweek: "Midweek",
    openingsNights: "{n} nights",
    openingsCabinsLeft: "{n} cabins free",
    openingsPrompt: "I'm looking for a cabin for 2 from {arrival} to {departure} ({kind}). What's free and at what price?",
    cabinsTitle: "Cabins",
    cabinsFrom: "from {price}",
    cabinPrompt: "Show the {name} cabin's free dates in the coming weeks, with current prices and offers.",
    offersTitle: "Offers",
    offersCode: "Code",
    offersStay: "stays {from} – {to}",
    offersBookBy: "book by {date}",
    offerPrompt: "How do I use the {title} offer? Which dates does it cover?",
    homeUnavailable: "Nothing chosen yet.\nAsk the Hygge Assistant about a free cabin.",
    promoTitle: "Your discount code",
    promoCopy: "Copy",
    promoCopied: "Copied",
    promoHint: "Paste the code into the discount code field of the booking form.",
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
    starterBooking: "Wie ist der Status meiner Buchung?",
    sectionTitle: "Beginne mit einem Häuschen",
    sectionSubtitle: "Wähle eines und der Hygge-Assistent zeigt freie Termine, Preise und Angebote",
    staysSubtitle: "Frag nach einem davon oder plane den nächsten Aufenthalt aus einem früheren.",
    askCabin: "Zeig die freien Termine vom Häuschen {city} in den nächsten Wochen mit aktuellen Preisen und Angeboten.",
    assistantName: "Hygge-Assistent",
    heroTitleAnon: "Bereit zum Entspannen?",
    guestName: "Gast",
    bagTitle: "Aufenthalt",
    bagEmpty: "Noch nichts ausgewählt.\nFrag den Hygge-Assistenten nach einem freien Häuschen.",
    bagTotal: "Aufenthalt gesamt",
    bagTotalNote: "Gesamtpreis; in dieser Phase wird nichts abgebucht.",
    bagAsk: "Frag nach diesem Aufenthalt",
    starterPackages: "Welche Rabatte gibt es für einen längeren Aufenthalt?",
    feedbackDown: "Diese Antwort hat nicht geholfen",
    feedbackReason: "Was war falsch? (optional)",
    feedbackSend: "Senden",
    feedbackThanks: "Danke — wir geben das weiter.",
    privacyNote: "Wir speichern diese Gespräche, um den Assistenten zu verbessern. Bitte keine Kartendaten oder Passwörter.",
    bookAt: "Auf idobooking buchen",
    openingsTitle: "Nächste freie Termine",
    openingsWeekend: "Wochenende",
    openingsMidweek: "Unter der Woche",
    openingsNights: "{n} Nächte",
    openingsCabinsLeft: "{n} Häuschen frei",
    openingsPrompt: "Ich suche ein Häuschen für 2 vom {arrival} bis {departure} ({kind}). Was ist frei und zu welchem Preis?",
    cabinsTitle: "Häuschen",
    cabinsFrom: "ab {price}",
    cabinPrompt: "Zeig die freien Termine vom Häuschen {name} in den nächsten Wochen mit aktuellen Preisen und Angeboten.",
    offersTitle: "Angebote",
    offersCode: "Code",
    offersStay: "Aufenthalt {from} – {to}",
    offersBookBy: "buchbar bis {date}",
    offerPrompt: "Wie nutze ich das Angebot {title}? Welche Termine umfasst es?",
    homeUnavailable: "Noch nichts ausgewählt.\nFrag den Hygge-Assistenten nach einem freien Häuschen.",
    promoTitle: "Dein Rabattcode",
    promoCopy: "Kopieren",
    promoCopied: "Kopiert",
    promoHint: "Füge den Code im Feld für den Rabattcode des Buchungsformulars ein.",
  },
};

const BAG_NOUNS: Record<Lang, (count: number) => string> = {
  // 1 rezerwacja / 2-4 rezerwacje / 5+ rezerwacji, with the teens taking the last form.
  pl: (n) => {
    const tens = n % 100;
    if (n === 1) return "rezerwacja";
    const ones = n % 10;
    return ones >= 2 && ones <= 4 && (tens < 12 || tens > 14) ? "rezerwacje" : "rezerwacji";
  },
  en: (n) => (n === 1 ? "booking" : "bookings"),
  de: (n) => (n === 1 ? "Buchung" : "Buchungen"),
};

/** "1 rezerwacja", "3 rezerwacje", "0 rezerwacji" — what the bag holds, counted. */
export function bagCount(lang: Lang, count: number): string {
  return `${count} ${(BAG_NOUNS[lang] ?? BAG_NOUNS.en)(count)}`;
}

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
