// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

import { AgentApi } from "web-shared";
import { LIGHT_UI } from "./light";
import type { Product } from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8004";

export const api = new AgentApi(API_URL, "/api");

// A guest who cannot reach the API is owed an apology, not the command that starts it:
// the developer hint belongs only to the local run it is about.
export const UNREACHABLE = LIGHT_UI
  ? "Przepraszamy — Asystent Hygge jest chwilowo niedostępny. Spróbuj za chwilę, " +
    "albo zadzwoń do nas: +48 691 661 677."
  : "Couldn't reach the Osada Hygge API on port 8004. Start it with " +
    "`uvicorn hygge.api.main:app --app-dir examples --port 8004` and try again.";

export async function fetchProducts(): Promise<Product[] | null> {
  const data = await api.get<{ products: Product[] }>("/products", { limit: "100" });
  return data?.products ?? null;
}
