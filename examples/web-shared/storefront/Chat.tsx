// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import type { ReactNode } from "react";
import { useStickToBottom } from "../scroll";
import { LatestPill, Transcript, type TranscriptProps } from "../Transcript";
import type { AgentTurn } from "../turn";

/** The storefronts' conversation page: the home until the first message, then the transcript. */
export function Chat({
  chat,
  home,
  renderBlock,
  renderPending,
  renderFooter,
  wide,
  fullWidth = false,
}: {
  chat: AgentTurn;
  home: ReactNode;
  renderBlock: TranscriptProps["renderBlock"];
  renderPending?: TranscriptProps["renderPending"];
  renderFooter?: TranscriptProps["renderFooter"];
  /** Components that may extend past the text measure when the page has room. */
  wide?: ReadonlySet<string>;
  /** Let the conversation fill the page instead of the reading measure. */
  fullWidth?: boolean;
}) {
  const { scrollRef, onScroll, showLatest, jumpToLatest } = useStickToBottom(chat.items, chat.busy);
  return (
    <div className="relative h-full">
      <div ref={scrollRef} onScroll={onScroll} className="panel-scroll h-full overflow-y-auto px-4 pb-8 pt-6 sm:px-6">
        <div className={`mx-auto flex flex-col gap-5 text-[15.5px] ${fullWidth ? "max-w-[1100px]" : "max-w-[760px]"}`}>
          {chat.items.length === 0 ? (
            home
          ) : (
            <Transcript items={chat.items} busy={chat.busy} send={chat.send} renderBlock={renderBlock} renderPending={renderPending} renderFooter={renderFooter} wide={wide} />
          )}
        </div>
      </div>
      {showLatest ? <LatestPill onClick={jumpToLatest} /> : null}
    </div>
  );
}
