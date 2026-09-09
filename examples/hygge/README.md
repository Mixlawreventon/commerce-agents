# Osada Hygge (hygge)

A shopping agent for Osada Hygge, a five-cabin forest retreat by a lake in the
Gostynin-Wloclawek Landscape Park. The storefront runs over one date-bound catalog of
cabins — Fika and Lagom (jacuzzi on the terrace), Gron, Hyggelig, and Lykke — priced per
night in PLN: it quotes dated searches, lays a stay out night by night, and books the
planned nights. The vertical is built on the `travel` example's date-bound backend.

## Run locally

```bash
python scripts/run_demo.py hygge                 # API :8004 + storefront :3004
```

Or start the pieces yourself, after `npm install` in `examples/`:

```bash
uvicorn hygge.api.main:app --app-dir examples --reload --port 8004
(cd examples/hygge/storefront-web && npm run dev)     # :3004
```

Chat needs `ANTHROPIC_API_KEY` in the repo-root `.env` or the environment; browsing the
cabins does not.

## Try

Storefront:

1. Find me a cosy cabin for two for a weekend in October — a jacuzzi on the terrace would be perfect, and we're bringing our dog.
2. Compare Fika and Lagom for those dates — what's the difference, and which is better value?
3. Add Lagom for two nights, and what does the Osada Hygge cancellation window look like?

## Deploy

The storefront is a Python API (backend) and a Next.js app (frontend), deployed as two
services:

- **API → Railway.** `railway.json` at the repo root sets the start command
  (`uvicorn hygge.api.main:app --app-dir examples --host 0.0.0.0 --port $PORT`) and a
  `/api/health` check. Set `ANTHROPIC_API_KEY`, `DEMO_ALLOWED_HOSTS=*`,
  `DEMO_ALLOWED_ORIGINS=<the Vercel URL>`, and `NIXPACKS_PYTHON_VERSION=3.12`.
- **Web → Vercel.** Root directory `examples/hygge/storefront-web` (an npm workspace that
  links `../../web-shared`). Set `NEXT_PUBLIC_API_URL=<the Railway URL>`.

See [`../../docs/deployment.md`](../../docs/deployment.md) for other model platforms and
`.env.example` for the deploy variables. The demo host has no authentication of its own; a
real deployment puts its own auth in front.

## What is specific to this example

- `api/mock_travel.py`: `MockTravel`, the `StorefrontBackend` over the fixtures in `data/`.
  A `travel_date` filter is enforced as availability; a dated result is a quote with a
  `date_flex` rate strip and `free_cancellation_until`. A cabin's first `add_to_cart` books
  the planned nights. A `guests` filter is enforced as capacity against `max_guests`: every
  head counts the same, and a baby under one sleeping with its parents is not a head. A
  `nights` filter is the stay length the quote covers.
- `api/live_hygge.py`: `HyggeLive`, the same backend with live idobooking data overlaid
  when `IDOBOOKING_MIDDLEWARE_URL` is set — price, photos, real availability, and the
  named packages a stay earns. Every card carries the packages on offer, including the
  deeper one a longer stay would reach; the season rate behind them is an internal
  pricing-plan name and never shown. Checkout hands off a widget URL pre-configured with
  the cabin, dates, and party size.
- Analytics: with `DATABASE_URL` set, `../demo_common/analytics.py` records one row per
  session start, message, tool call, error, guest verdict, and booking hand-off followed;
  `POST /api/feedback` and `POST /api/click` take the last two. Rows past
  `EVENT_RETENTION_DAYS` (90) are dropped daily. `GET /api/admin/stats` and
  `/api/admin/conversations` read them back, behind `ADMIN_TOKEN` and 404 without one.
  Unset `DATABASE_URL` and nothing is recorded, with every route behaving the same.
- Booking hand-off: each cabin card links to its idobooking widget, tagged
  `utm_source=osada-hygge&utm_medium=assistant&utm_campaign=hygge-agent` so the booking
  system's own analytics attributes the visit.
- `api/agent_config.py`: the shopping config (brand, warm Scandinavian voice, PLN, and a
  real model id via `SHOPPING_MODEL`) and the merchant config.
- `api/main.py`: the storefront host with the itinerary extension and an in-memory store
  that `MemorySeeder` refills from `data/memory-seed.json` on boot.
- `storefront-web/`: this example's cards, views, and tokens, over `../web-shared/`.
  `lib/light.ts` reads `NEXT_PUBLIC_LIGHT_UI=1`, the trimmed storefront for real
  guests: no seeded shopper name, no stays tab or arriving panel, no checkout.

## Data

`data/catalog.json`, `users.json`, `orders.json`, `policies.json`, and `memory-seed.json`
feed the storefront. The catalog carries each cabin's real photo URL in `image_url`; the
current cards render gradient tiles rather than the photos.
