// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

import { AgentApi } from "web-shared";
import type { Product } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8004";

export const api = new AgentApi(API_URL, "/api");

export const UNREACHABLE =
  "Couldn't reach the Osada Hygge API on port 8004. Start it with " +
  "`uvicorn hygge.api.main:app --app-dir examples --port 8004` and try again.";

export async function fetchProducts(): Promise<Product[] | null> {
  const data = await api.get<{ products: Product[] }>("/products", { limit: "100" });
  return data?.products ?? null;
}
