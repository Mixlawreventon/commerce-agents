// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { type Lang, t } from "@/lib/i18n";

/**
 * A quiet "this reply missed" control under a finished answer.
 *
 * Only the negative verdict is offered: at testing volumes nobody clicks approval, and a
 * reply a guest disliked is the row worth reading. The optional sentence is where the
 * useful part usually is, so it is asked for — but never required, and the click is
 * already recorded before it is typed.
 */
export default function ReplyFeedback({ lang, messageIndex }: { lang: Lang; messageIndex: number }) {
  const [state, setState] = useState<"idle" | "asking" | "sent">("idle");
  const [reason, setReason] = useState("");

  const send = (text?: string) => {
    void api.post("/feedback", {
      verdict: "down",
      message_index: messageIndex,
      reason: text?.trim() || null,
    });
  };

  if (state === "sent") {
    return (
      <p className="text-[12px]" style={{ color: "var(--ink-soft)" }}>
        {t(lang, "feedbackThanks")}
      </p>
    );
  }

  if (state === "asking") {
    return (
      <form
        className="flex flex-wrap items-center gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          send(reason);
          setState("sent");
        }}
      >
        <input
          autoFocus
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          placeholder={t(lang, "feedbackReason")}
          maxLength={2000}
          className="min-w-0 flex-1 rounded-full border px-3 py-1 text-[12px]"
          style={{ borderColor: "var(--line)", background: "var(--surface)", color: "var(--ink)" }}
        />
        <button
          type="submit"
          className="rounded-full px-3 py-1 text-[12px] font-semibold"
          style={{ background: "var(--ink)", color: "var(--surface)" }}
        >
          {t(lang, "feedbackSend")}
        </button>
      </form>
    );
  }

  return (
    <button
      type="button"
      // The verdict is recorded on the click; the sentence, if it comes, is a second row.
      onClick={() => {
        send();
        setState("asking");
      }}
      className="self-start text-[12px] underline underline-offset-2"
      style={{ color: "var(--ink-soft)" }}
    >
      {t(lang, "feedbackDown")}
    </button>
  );
}
