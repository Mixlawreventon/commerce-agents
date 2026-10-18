// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { useEffect, useState } from "react";
import { type Lang, t } from "@/lib/i18n";
import { BODY, DISPLAY } from "./shared";

/**
 * The discount code on the checkout card: large, with a copy button and the one line that
 * says where it goes. idobooking has no API for codes, so the guest carries it over by
 * hand; the value shown is the operator's own label, never a figure computed here.
 */
export default function PromoCode({ code, label, lang }: { code: string; label?: string | null; lang: Lang }) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 1800);
    return () => window.clearTimeout(timer);
  }, [copied]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
    } catch {
      // Clipboard blocked: the code is on screen to type over.
    }
  };

  return (
    <div
      className="mt-4 rounded-(--radius) p-3"
      style={{ background: "var(--accent-soft)", border: "1px dashed var(--accent)" }}
      data-promo-code
    >
      <div style={{ fontFamily: BODY, fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--accent-ink)" }}>
        {t(lang, "promoTitle")}
        {label ? <span style={{ textTransform: "none", letterSpacing: 0 }}> · {label}</span> : null}
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-3">
        <code
          className="select-all"
          style={{ fontFamily: DISPLAY, fontSize: 28, fontWeight: 700, letterSpacing: "0.06em", color: "var(--ink)", lineHeight: 1.1 }}
        >
          {code}
        </code>
        <button
          type="button"
          onClick={copy}
          aria-live="polite"
          className="rounded-full px-3 py-1.5 text-[12.5px] font-semibold transition hover:brightness-110"
          style={{ background: copied ? "var(--ink)" : "var(--accent)", color: "var(--surface)", fontFamily: BODY }}
        >
          {copied ? t(lang, "promoCopied") : t(lang, "promoCopy")}
        </button>
      </div>
      <p className="mt-1.5" style={{ fontFamily: BODY, fontSize: 12.5, lineHeight: 1.45, color: "var(--ink-2)" }}>
        {t(lang, "promoHint")}
      </p>
    </div>
  );
}
