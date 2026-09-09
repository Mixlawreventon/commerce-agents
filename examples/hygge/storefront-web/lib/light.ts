// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

/**
 * The trimmed storefront put in front of real guests while the rest is still being built.
 *
 * Light mode drops the parts of the example that only make sense with the demo's seeded
 * data or its unfinished booking path: the seeded shopper's name, the stays history (its
 * tab and the arriving panel), and checkout. Nothing is deleted — the full example runs
 * whenever the flag is off, which is the default.
 *
 * Set `NEXT_PUBLIC_LIGHT_UI=1` on the deployment to turn it on. It is read at build time,
 * so changing it needs a rebuild.
 */
export const LIGHT_UI = process.env.NEXT_PUBLIC_LIGHT_UI === "1";
