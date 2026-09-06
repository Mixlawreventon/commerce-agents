// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

/** A trip is an order here: these are travel's words for the shared order pieces. */

import { isOpen, type Order, ORDER_NOUNS, type OrderNouns, useCatalogIndex } from "web-shared";
import { PostcardWindow } from "@/components/PostcardWindow";
import { fetchProducts } from "./api";
import { productCity } from "./format";

export const NOUNS: OrderNouns = {
  ...ORDER_NOUNS,
  one: "trip",
  title: "Trips",
  cardTitle: "Coming up",
  noneOpen: "No trips ahead",
  openVerb: "Starts",
  closedWhen: (_order, date) => `For ${date}`,
  statusLabels: { processing: "Confirming", shipped: "Confirmed", out_for_delivery: "Confirmed", delivered: "Completed", return_initiated: "Refund requested" },
  filters: [
    { id: "open", label: "Upcoming", match: isOpen },
    { id: "closed", label: "Past", match: (order) => !isOpen(order) },
  ],
  handoff(order) {
    const ref = `trip ${order.order_id}`;
    if (isOpen(order)) return { label: "Ask", prompt: `What's the status of my ${ref}?` };
    if (order.status === "delivered") return { label: "Plan it again", prompt: `Plan another trip like ${ref}.` };
    return { label: "Ask", prompt: `What happened with ${ref}?` };
  },
};

/** The trip's destination: the city of its first stay, experience, or flight. */
export function TripThumb({ order }: { order: Order }) {
  const catalog = useCatalogIndex(fetchProducts);
  const product = order.items.map((item) => catalog[item.product_id]).find(Boolean);
  const city = product ? productCity(product) : undefined;
  return <PostcardWindow city={city} title={order.items[0]?.title ?? order.order_id} className="h-[42px] w-[60px] shrink-0" />;
}
