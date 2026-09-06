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
  the planned nights.
- `api/agent_config.py`: the shopping config (brand, warm Scandinavian voice, PLN, and a
  real model id via `SHOPPING_MODEL`) and the merchant config.
- `api/main.py`: the storefront host with the itinerary extension and an in-memory store
  that `MemorySeeder` refills from `data/memory-seed.json` on boot.
- `storefront-web/`: this example's cards, views, and tokens, over `../web-shared/`.

## Data

`data/catalog.json`, `users.json`, `orders.json`, `policies.json`, and `memory-seed.json`
feed the storefront. The catalog carries each cabin's real photo URL in `image_url`; the
current cards render gradient tiles rather than the photos.
