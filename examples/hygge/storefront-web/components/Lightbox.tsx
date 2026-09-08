// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { useCallback, useEffect, useState } from "react";

/** A full-screen photo gallery: prev/next, thumbnails, keyboard nav, backdrop-to-close. */
export function Lightbox({
  images,
  startIndex = 0,
  onClose,
}: {
  images: string[];
  startIndex?: number;
  onClose: () => void;
}) {
  const [index, setIndex] = useState(startIndex);
  const count = images.length;
  const go = useCallback((delta: number) => setIndex((i) => (i + delta + count) % count), [count]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowRight") go(1);
      else if (e.key === "ArrowLeft") go(-1);
    };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [go, onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col items-center justify-center"
      style={{ background: "rgba(12,20,16,0.92)" }}
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Gallery"
    >
      <button
        type="button"
        onClick={onClose}
        aria-label="Close"
        className="absolute right-4 top-4 flex h-10 w-10 items-center justify-center rounded-full text-2xl text-white/90 hover:bg-white/10"
      >
        ×
      </button>

      <div className="relative flex w-full flex-1 items-center justify-center" onClick={(e) => e.stopPropagation()}>
        {count > 1 ? (
          <button
            type="button"
            onClick={() => go(-1)}
            aria-label="Previous photo"
            className="absolute left-2 flex h-12 w-12 items-center justify-center rounded-full text-3xl text-white/90 hover:bg-white/10 sm:left-6"
          >
            ‹
          </button>
        ) : null}

        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={images[index]}
          alt={`Photo ${index + 1} of ${count}`}
          className="max-h-[78vh] max-w-[92vw] rounded-lg object-contain shadow-2xl"
          onClick={() => count > 1 && go(1)}
        />

        {count > 1 ? (
          <button
            type="button"
            onClick={() => go(1)}
            aria-label="Next photo"
            className="absolute right-2 flex h-12 w-12 items-center justify-center rounded-full text-3xl text-white/90 hover:bg-white/10 sm:right-6"
          >
            ›
          </button>
        ) : null}
      </div>

      <div className="flex flex-col items-center gap-2 pb-4 pt-3" onClick={(e) => e.stopPropagation()}>
        <span className="text-[13px] tabular-nums text-white/80">
          {index + 1} / {count}
        </span>
        {count > 1 ? (
          <div className="flex max-w-[92vw] gap-1.5 overflow-x-auto px-2">
            {images.map((src, i) => (
              <button
                key={src}
                type="button"
                onClick={() => setIndex(i)}
                aria-label={`Go to photo ${i + 1}`}
                className={`h-12 w-16 shrink-0 overflow-hidden rounded ${i === index ? "ring-2 ring-white" : "opacity-60 hover:opacity-100"}`}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={src} alt="" className="h-full w-full object-cover" />
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
