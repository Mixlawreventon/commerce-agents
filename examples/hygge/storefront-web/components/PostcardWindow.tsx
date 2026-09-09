// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

import { destinationGradientCss } from "@/lib/format";

/** A product image when one is available, with a captioned gradient tile as the fallback. */
export function PostcardWindow({
  city,
  title,
  imageUrl,
  showLabel = true,
  className = "",
}: {
  city?: string;
  title: string;
  imageUrl?: string | null;
  showLabel?: boolean;
  className?: string;
}) {
  const label = city ?? title.split(/\s+/)[0] ?? "";
  // Container-query units scale the name to the window; longer names get a smaller size.
  const fontSize = `${Math.max(14, Math.min(34, Math.round(190 / Math.max(label.length, 1))))}cqw`;

  if (imageUrl) {
    return (
      <div className={`al-postcard relative overflow-hidden ${className}`} aria-hidden>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={imageUrl} alt="" loading="lazy" className="absolute inset-0 h-full w-full object-cover" />
        {showLabel ? (
          <>
            <div className="absolute inset-0 bg-gradient-to-t from-black/45 via-transparent to-transparent" />
            <span
              className="al-postcard-city relative z-[1] self-end p-2 text-white drop-shadow"
              style={{ fontSize }}
            >
              {label}
            </span>
          </>
        ) : null}
      </div>
    );
  }

  return (
    <div
      className={`al-postcard ${className}`}
      style={{ backgroundImage: destinationGradientCss(city, title) }}
      aria-hidden
    >
      {showLabel ? (
        <span className="al-postcard-city" style={{ fontSize }}>
          {label}
        </span>
      ) : null}
    </div>
  );
}
