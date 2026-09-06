// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import {
  AskButton,
  AttentionList,
  AttentionRow,
  formatDayMonth,
  formatMoney,
  formatNumber,
  KindIcon,
  Notice,
  PageHeader,
  Panel,
  plural,
  QuotedAsData,
  RecordList,
  runwayLabel,
  Skeleton,
  useResource,
} from "web-shared";
import { fetchAlerts } from "@/lib/api";
import { BOOKING_STATUS, INVENTORY_KINDS, inventoryPrompt, ISSUE_KINDS } from "@/lib/kinds";
import type { InventoryAlert, OrderIssue, RecentOrder } from "@/lib/types";

export function issuePrompt(issue: OrderIssue): string {
  return `What are my options for booking ${issue.order_id}? ${issue.summary}.`;
}

export function runway(alert: InventoryAlert): string | null {
  return alert.days_of_cover == null || alert.stock === 0 ? null : runwayLabel(alert.days_of_cover);
}

export function bookingRows(bookings: RecentOrder[]) {
  return bookings.map((booking) => ({
    id: booking.order_id,
    sub: `${formatDayMonth(booking.placed_at)} · ${formatMoney(booking.total, "USD", { whole: true })}`,
    status: BOOKING_STATUS[booking.status] ?? { label: booking.status.replaceAll("_", " "), tone: "muted" as const },
  }));
}

function IssueCard({ issue, onAskAssistant }: { issue: OrderIssue; onAskAssistant: (text: string) => void }) {
  const style = ISSUE_KINDS[issue.kind];
  return (
    <li className="flex gap-3 px-[18px] py-3.5">
      <KindIcon icon={style.icon} tone={style.tone} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-start gap-x-3 gap-y-1">
          <div className="min-w-0 flex-1">
            <div className="text-[14px] font-medium leading-snug text-(--ink)">{issue.summary}</div>
            <div className="mt-0.5 text-[12.5px] tabular-nums text-(--ink-soft)">
              {[style.label, `Booking ${issue.order_id}`, issue.listing_id, issue.opened_at ? `opened ${formatDayMonth(issue.opened_at)}` : ""].filter(Boolean).join(" · ")}
            </div>
          </div>
          <AskButton label={issue.kind === "buyer_message" ? "Draft reply" : "Ask"} onClick={() => onAskAssistant(issuePrompt(issue))} />
        </div>
        {issue.buyer_message_excerpt ? (
          <div className="mt-2 rounded-[10px] bg-(--ground) px-3 py-2">
            <blockquote className="text-[13px] leading-snug text-(--ink-2)">&ldquo;{issue.buyer_message_excerpt}&rdquo;</blockquote>
            {/* Some fixture excerpts are injection attempts, so the note sits beside the quote. */}
            <QuotedAsData subject="Guest message" className="mt-1.5" />
          </div>
        ) : null}
      </div>
    </li>
  );
}

function AlertRow({ alert, onAskAssistant }: { alert: InventoryAlert; onAskAssistant: (text: string) => void }) {
  const style = INVENTORY_KINDS[alert.kind];
  const tight = alert.kind === "low_stock";
  return (
    <AttentionRow
      icon={style.icon}
      tone={tight ? "warn" : style.tone}
      title={alert.title}
      meta={
        <>
          <span className={tight ? "font-semibold text-(--warn)" : ""}>{formatNumber(alert.stock)} room-nights available</span>
          {["", tight ? runway(alert) : null, alert.sales_last_30d != null ? `${formatNumber(alert.sales_last_30d)} booked in 30 days` : "", alert.listing_id]
            .filter((part, index) => index === 0 || part)
            .join(" · ")}
        </>
      }
      action={{ label: tight ? "Ask" : "Plan rates", onClick: () => onAskAssistant(inventoryPrompt(alert.kind, `${alert.title} (${alert.listing_id})`)) }}
    />
  );
}

export default function BookingsView({
  refreshKey,
  recentBookings,
  onAskAssistant,
}: {
  refreshKey: number;
  recentBookings: RecentOrder[] | null;
  onAskAssistant: (text: string) => void;
}) {
  const { data, failed } = useResource(fetchAlerts, [refreshKey]);
  const issues = data?.order_issues ?? [];
  const tight = (data?.inventory ?? [])
    .filter((alert) => alert.kind === "low_stock")
    .sort((a, b) => (a.days_of_cover ?? Infinity) - (b.days_of_cover ?? Infinity));
  const soft = (data?.inventory ?? []).filter((alert) => alert.kind === "slow_mover");

  return (
    <div className="ac-reveal @container flex flex-col gap-4">
      <PageHeader
        title="Bookings"
        subtitle={data ? `${plural(issues.length, "open issue")} · ${formatNumber(tight.length)} tight on availability · ${formatNumber(soft.length)} pacing soft` : undefined}
      />
      {failed && !data ? (
        <Notice>The travel API isn&apos;t reachable, so booking and pacing alerts can&apos;t load.</Notice>
      ) : !data ? (
        <div className="grid gap-4 @4xl:grid-cols-[minmax(0,1fr)_minmax(0,0.8fr)]">
          <Skeleton className="h-96" />
          <Skeleton className="h-64" />
        </div>
      ) : (
        <div className="grid items-start gap-4 @4xl:grid-cols-[minmax(0,1fr)_minmax(0,0.8fr)]">
          <div className="flex flex-col gap-4">
            <Panel title="Open issues" subtitle={issues.length ? formatNumber(issues.length) : undefined}>
              {issues.length === 0 ? (
                <p className="px-[18px] pb-4 text-[13.5px] text-(--ink-soft)">No open booking issues.</p>
              ) : (
                <ul className="divide-y divide-(--line)">
                  {issues.map((issue) => (
                    <IssueCard key={issue.issue_id} issue={issue} onAskAssistant={onAskAssistant} />
                  ))}
                </ul>
              )}
            </Panel>
            <Panel title="Recent bookings">
              {!recentBookings ? (
                <Skeleton className="mx-[18px] mb-4 h-40" />
              ) : recentBookings.length === 0 ? (
                <p className="px-[18px] pb-4 text-[13px] text-(--ink-soft)">No bookings yet.</p>
              ) : (
                <RecordList rows={bookingRows(recentBookings)} />
              )}
            </Panel>
          </div>
          <div className="flex flex-col gap-4">
            <Panel title="Tight availability" subtitle="soonest to sell out first">
              {tight.length === 0 ? (
                <p className="px-[18px] pb-4 text-[13.5px] text-(--ink-soft)">Every property has dates to sell.</p>
              ) : (
                <AttentionList>
                  {tight.map((alert) => (
                    <AlertRow key={alert.listing_id} alert={alert} onAskAssistant={onAskAssistant} />
                  ))}
                </AttentionList>
              )}
            </Panel>
            <Panel title="Soft pacing" subtitle="midweek occupancy under 55% in the coming weeks">
              {soft.length === 0 ? (
                <p className="px-[18px] pb-4 text-[13.5px] text-(--ink-soft)">Nothing is pacing soft.</p>
              ) : (
                <AttentionList>
                  {soft.map((alert) => (
                    <AlertRow key={alert.listing_id} alert={alert} onAskAssistant={onAskAssistant} />
                  ))}
                </AttentionList>
              )}
            </Panel>
          </div>
        </div>
      )}
    </div>
  );
}
