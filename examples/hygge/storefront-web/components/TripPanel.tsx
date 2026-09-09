// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { AskLink, BagPanel, CheckoutButton, plural, RemoveLink, Stepper, TotalRow, useCatalogIndex, useStoreFrame } from "web-shared";
import { bagCount, DEFAULT_LANG, type Lang, t } from "@/lib/i18n";
import { fetchProducts } from "@/lib/api";
import { formatPrice, productCity, productPlace, quantityLabel, shortDate } from "@/lib/format";
import type { CartItem, CartPayload, Product } from "@/lib/types";
import { PostcardWindow } from "./PostcardWindow";

/** Stays count nights, experiences count guests; flights get no stepper. */
function quantityNoun(item: CartItem): "night" | "guest" | null {
  if (item.product_id.startsWith("AL-STAY-")) return "night";
  if (item.product_id.startsWith("AL-EXP-")) return "guest";
  return null;
}

function quantityMessage(item: CartItem, quantity: number): string {
  const s = quantity === 1 ? "" : "s";
  return quantityNoun(item) === "night" ? `Make the ${item.title} ${quantity} night${s}.` : `Make the ${item.title} for ${quantity} guest${s}.`;
}

function cancellationLine(product?: Product): { text: string; free: boolean } | null {
  if (!product?.attributes) return null;
  const refundable = /^(yes|true)$/i.test(product.attributes.refundable ?? "");
  if (refundable) {
    const until = shortDate(product.attributes.free_cancellation_until);
    return { text: until ? `Cancel free until ${until}` : "Free cancellation", free: true };
  }
  if (/^(no|false|none)$/i.test((product.attributes.refundable ?? "").trim())) {
    return { text: "Non-refundable", free: false };
  }
  return null;
}

function CartRow({ item, product }: { item: CartItem; product?: Product }) {
  const { ask } = useStoreFrame();
  const noun = quantityNoun(item);
  const cancellation = cancellationLine(product);
  const nights = noun === "night" ? item.quantity : 0;
  return (
    <div>
      <div className="flex min-w-0 items-start gap-3">
        <PostcardWindow
          city={product ? productPlace(product) : undefined}
          title={item.title}
          className="h-[56px] w-[88px] shrink-0"
        />
        <div className="min-w-0 flex-1">
          <div className="al-display truncate text-[14px] font-semibold leading-snug text-(--ink)">
            {item.title}
          </div>
          {product ? (
            <div className="al-meta mt-0.5 truncate">
              {[product.brand, productCity(product)].filter(Boolean).join(" · ")}
            </div>
          ) : null}
          {nights > 0 ? (
            <div className="mt-1.5 flex items-center gap-1.5">
              <span aria-hidden className="flex gap-[3px]">
                {Array.from({ length: Math.min(nights, 7) }, (_, i) => (
                  <span
                    key={i}
                    className="h-2 w-3.5 rounded-[3px]"
                    style={{ background: "var(--well)", border: "1px solid var(--line)" }}
                  />
                ))}
              </span>
              <span className="text-[11px] font-semibold text-(--ink-soft)">
                {nights} night{nights === 1 ? "" : "s"}
              </span>
            </div>
          ) : null}
          {cancellation ? (
            <div
              className={`mt-1 text-[11px] font-semibold ${
                cancellation.free ? "text-(--accent)" : "text-(--ink-soft)"
              }`}
            >
              {cancellation.free ? "✓ " : ""}
              {cancellation.text}
            </div>
          ) : null}
        </div>
      </div>
      {/* Line totals share the trip total's right edge. */}
      <div className="mt-1.5 flex items-baseline justify-between gap-3 pl-[100px]">
        <span className="text-[12px] text-(--ink-soft)">
          {formatPrice(item.price)} {quantityLabel(item.product_id, item.quantity)}
        </span>
        <span className="al-display shrink-0 text-[15px] font-bold text-(--ink)">
          {formatPrice(item.line_total)}
        </span>
      </div>
      <div className="mt-2 flex items-center gap-2.5">
        {noun ? (
          <Stepper
            quantity={item.quantity}
            unit={noun}
            itemTitle={item.title}
            onChange={(quantity) => ask(quantity < 1 ? `Remove the ${item.title} from my trip.` : quantityMessage(item, quantity))}
          />
        ) : null}
        <RemoveLink itemTitle={item.title} onClick={() => ask(`Remove the ${item.title} from my trip.`)} />
      </div>
    </div>
  );
}

/** The trip beside the conversation. `productIndex` lets /showcase render it from fixtures. */
export default function TripPanel({
  cart,
  checkoutStaged = false,
  productIndex,
  lang = DEFAULT_LANG,
  light = false,
}: {
  cart: CartPayload | null;
  checkoutStaged?: boolean;
  productIndex?: Record<string, Product>;
  lang?: Lang;
  /** Light mode has no checkout: booking is not the flow being tested yet. */
  light?: boolean;
}) {
  const catalog = useCatalogIndex(fetchProducts);
  const index = productIndex ?? catalog;
  const items = cart?.items ?? [];
  // A three-night stay counts as one booking.
  const count = items.length;
  return (
    <BagPanel
      title={t(lang, "bagTitle")}
      count={bagCount(lang, count)}
      isEmpty={count === 0}
      empty={
        <>
          {t(lang, "bagEmpty")
            .split("\n")
            .map((line, index) => (
              <span key={line}>
                {index > 0 ? <br /> : null}
                {line}
              </span>
            ))}
        </>
      }
      footer={
        <>
          <TotalRow label={t(lang, "bagTotal")} value={formatPrice(cart?.subtotal ?? 0)} note={count ? t(lang, "bagTotalNote") : undefined} />
          {light ? null : <CheckoutButton staged={checkoutStaged} disabled={count === 0} prompt="Check out my trip." />}
          {count ? (
            <div className="mt-2.5 flex justify-center">
              <AskLink label={t(lang, "bagAsk")} prompt="Look over my trip: anything missing or worth changing?" />
            </div>
          ) : null}
        </>
      }
    >
      <ul>
        {items.map((item, position) => (
          <li key={item.product_id} className={`py-3.5 first:pt-0 ${position > 0 ? "border-t border-dashed border-(--line)" : ""}`}>
            <CartRow item={item} product={index[item.product_id]} />
          </li>
        ))}
      </ul>
    </BagPanel>
  );
}
