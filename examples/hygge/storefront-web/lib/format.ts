// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

import { formatMoney } from "web-shared";
import type { Product } from "./types";

const DESTINATION_GRADIENTS: Record<string, [string, string]> = {
  fika: ["#E4E7EA", "#C4CBD1"],
  lagom: ["#F0E2CF", "#E4C9A8"],
  gron: ["#CFE0D0", "#DDE8D6"],
  hyggelig: ["#E8DED0", "#D8E0D6"],
  lykke: ["#E6E0EA", "#D4D8E4"],
  "osada hygge": ["#D9E2DA", "#E6EAE3"],
};

const GRADIENT_FALLBACKS = Object.values(DESTINATION_GRADIENTS);

function hash(text: string): number {
  let value = 0;
  for (let i = 0; i < text.length; i++) {
    value = (value * 31 + text.charCodeAt(i)) >>> 0;
  }
  return value;
}

/** The seed keeps two items in one unmapped place from sharing a gradient. */
export function destinationGradientCss(city?: string | null, seed?: string): string {
  const key = city?.trim().toLowerCase();
  const [from, to] =
    (key && DESTINATION_GRADIENTS[key]) ||
    GRADIENT_FALLBACKS[hash(`${key ?? ""}·${seed ?? "osada-hygge"}`) % GRADIENT_FALLBACKS.length];
  return `linear-gradient(135deg, ${from}, ${to})`;
}

export function productCity(product: Product): string | undefined {
  return product.attributes?.city ?? product.attributes?.destination_city ?? undefined;
}

/** Neighborhood before city, so cards in a one-city flow stay distinct. */
export function productPlace(product: Product): string | undefined {
  return product.attributes?.neighborhood ?? productCity(product);
}

// per_traveler folds into "/ person" so mixed data renders one unit.
const PRICE_UNIT_LABELS: Record<string, string> = {
  per_night: "za noc",
  per_person: "za osobę",
  per_traveler: "za osobę",
};

export function priceUnitLabel(unit?: string | null): string | null {
  if (!unit) return null;
  return PRICE_UNIT_LABELS[unit] ?? `/ ${unit.replace(/^per[_\s]+/, "").replace(/_/g, " ")}`;
}

export function productPriceUnit(product: Product): string | null {
  return priceUnitLabel(product.attributes?.price_unit);
}

export function formatPrice(value: number): string {
  return formatMoney(value, "PLN", { whole: Number.isInteger(value) });
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-10-13" → "Oct 13", from the string parts so no timezone shifts the day. */
export function shortDate(iso?: string): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso ?? "");
  if (!match) return null;
  const month = MONTHS[Number(match[2]) - 1];
  return month ? `${month} ${Number(match[3])}` : null;
}

function quantityNoun(productId: string): "nights" | "guests" | "travelers" | null {
  if (productId.startsWith("HY-")) return "nights";
  return null;
}

export function quantityLabel(productId: string, quantity: number): string {
  const noun = quantityNoun(productId);
  if (!noun) return `× ${quantity}`;
  return `× ${quantity} ${quantity === 1 ? noun.slice(0, -1) : noun}`;
}
