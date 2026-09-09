// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import type { ReactNode } from "react";
import { type AgentTurn, Chat as ChatShell } from "web-shared";
import type { Lang } from "@/lib/i18n";
import GenerativeBlock from "./generative";
import ReplyFeedback from "./ReplyFeedback";

const WIDE = new Set(["comparison", "itinerary"]);

export default function Chat({ chat, home, lang }: { chat: AgentTurn; home: ReactNode; lang: Lang }) {
  return (
    <ChatShell
      chat={chat}
      home={home}
      wide={WIDE}
      renderBlock={(segment) => <GenerativeBlock block={segment.block} status={segment.status} />}
      renderFooter={(_item, index) => <ReplyFeedback lang={lang} messageIndex={index} />}
    />
  );
}
