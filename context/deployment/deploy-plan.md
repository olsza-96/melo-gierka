---
project: melo-gierka
shipped_at: 2026-05-25
platform: Fly.io
status: live
context_type: greenfield
---

# Deploy Contract — melo-gierka

Audit record of the first production deploy. Downstream milestone planning treats this file as ground truth for "what's already deployed", "what's already configured", and "what invariants must be preserved." Update on every meaningful infrastructure change.

## Live surface

| Field | Value |
|---|---|
| App name | `melo-gierka` |
| Org | `personal` (olsza96@wp.pl) |
| Public hostname | `melo-gierka.fly.dev` |
| Primary region | `ams` (Amsterdam) — `waw` was deprecated by Fly during deploy |
| Image registry | `registry.fly.io/melo-gierka` |
| Current image tag at write-time | `deployment-01KSGJF6HT2ST2QDVYJ56A9GDD` (v5) |
| Image size | ~64 MB |
| Fly app admin URL | https://fly.io/apps/melo-gierka |

Anyone reading this later can verify the live state with `fly status -a melo-gierka` and `fly releases --image -a melo-gierka`.

## Runtime configuration

### Non-secret env (in `fly.toml [env]`)

| Key | Value | Why |
|---|---|---|
| `PORT` | `8080` | Matches gunicorn `--bind 0.0.0.0:8080` and Dockerfile `EXPOSE 8080`. |
| `DJANGO_DEBUG` | `False` | Locks production Django mode. Triggers the SECRET_KEY guard, the SSL redirect, and the `/health` exempt rule. |

### Secrets (in `fly secrets`, names only — values never recorded)

| Name | Purpose |
|---|---|
| `DJANGO_SECRET_KEY` | 50-byte urlsafe token, generated locally. Rotating triggers a redeploy. |
| `DJANGO_ALLOWED_HOSTS` | `melo-gierka.fly.dev` — the only host Fly's edge routes to this app. The machine's private IPv4 is appended at startup by `settings.py` so internal Consul health checks pass. |

### VM

| Field | Value |
|---|---|
| Size | `shared-cpu-1x` |
| Memory | `256 MB` |
| CPUs | `1` |
| `auto_stop_machines` | `"off"` |
| `min_machines_running` | `1` |
| Machines deployed | 1 (no HA; `auto_stop_machines = off` always-on) |

### gunicorn

- `--workers 1 --threads 4` — **deliberate** single-worker so the in-memory game state dict is shared across all request handlers. Multiple workers (separate processes) would not share memory and game sessions would split inconsistently across workers.
- Access + error logs streamed to stdout (`fly logs` consumes them).

### Static files

- whitenoise `CompressedManifestStaticFilesStorage`. 127 static files collected at image build time and served by gunicorn (no Fly static accelerator, no separate CDN).

## DB strategy (the load-bearing decision)

- **SQLite, no volume.** The DB file lives at `/app/db.sqlite3` inside the image and is **baked at image build time** by these Dockerfile lines:
  ```
  RUN export DJANGO_DEBUG=True && \
      uv run python manage.py migrate --noinput && \
      uv run python manage.py seed_catalog && \
      uv run python manage.py collectstatic --noinput
  ```
- Every deploy ships a **fresh DB** seeded from `catalog/fixtures/initial.json` (5 `MusicSet` rows × 7 `Track` rows = 35 tracks, all placeholder pending PRD Open Question #4).
- **Invariant**: any DB write that lands at runtime (e.g. a Django superuser created via `fly ssh console`, sessions, log entries) **dies on the next deploy**. Acceptable for melo-gierka because the PRD requires session ephemerality.
- **No `[mounts]` section** in `fly.toml` and **no Fly volume** allocated. Adding a volume later would be a real architectural change, not just a config toggle — game-state semantics would need to be reconsidered.

## Game-state strategy

- In-memory Python dict on the single Fly machine.
- **`fly deploy` mid-session kills every active room** because the machine restarts. This is a known accepted risk (`infrastructure.md` risk #3, also in this plan's risk register). Operational rule: **do not deploy during a party**.
- Future migration path if this becomes unacceptable: Upstash Redis or similar shared store, per `infrastructure.md`'s deferred-decision note.

## Health checks

- `fly.toml` `[[http_service.checks]]` hits `GET /health` every 15 s, 5 s timeout, 10 s grace period.
- `/health` returns `200 {"status":"ok"}` without touching the DB — must succeed even if seeding fails.
- **`SECURE_REDIRECT_EXEMPT = [r"^health$"]`** in `settings.py` is load-bearing: Consul probes hit the machine on plain HTTP at the internal IP, never carrying `X-Forwarded-Proto: https`. Without the exempt, `SECURE_SSL_REDIRECT` returns 301, Fly marks the machine unhealthy, and the edge proxy 503s all public traffic. Captured as a recurring rule in `context/foundation/lessons.md`.

## Operational runbook

### Smoke test (post-deploy)

```bash
fly status -a melo-gierka
curl -i https://melo-gierka.fly.dev/health     # → 200 {"status":"ok"}
curl -i https://melo-gierka.fly.dev/           # → 200, lists 5 catalog slugs
curl -iL https://melo-gierka.fly.dev/admin/login   # → 200, Django admin login HTML
```

### Logs

```bash
fly logs -a melo-gierka            # tail live
```

### Rollback

Modern flyctl (≥0.3.x) removed `fly releases rollback`. Procedure:

```bash
fly releases --image -a melo-gierka                                # find prior image tag
fly deploy --image registry.fly.io/melo-gierka:deployment-<id>     # redeploy that tag
```

Round-trip verified in Phase 11 — completes in <60 s.

### Approval boundaries

| Action | Who runs it |
|---|---|
| `fly status`, `fly logs`, `fly releases --image` | Agent OK to run unattended (read-only) |
| `fly deploy` to production | Human in the loop |
| `fly secrets set …` | Human only (values must not enter the conversation) |
| `fly scale …`, `fly machine destroy`, `fly volumes …` | Human only |

## Known invariants (don't break these without revisiting the contract)

1. **No deploys during a session.** Restart wipes in-memory game state.
2. **DB wipe is by design.** Anything you need persisted past a deploy must move to a volume or external store first.
3. **`/health` must stay DB-free** and remain exempt from SSL redirect. Both are tested by Fly's Consul probe every 15 s.
4. **gunicorn stays at `--workers 1`** until game state moves to a shared store. Bumping workers without that migration silently splits sessions.
5. **`DJANGO_DEBUG` is `False`** in `[env]`. Build-time `manage.py` commands override with `DJANGO_DEBUG=True` inline to bypass the SECRET_KEY guard. Runtime never sees `True`.
6. **`primary_region = "ams"`** locked. `waw` is deprecated by Fly; don't put it back. If a closer region becomes available again, that's a deliberate change.

## What was not deployed in this milestone (deferred)

- **Spotify OAuth + Web Playback SDK** — requires the live `melo-gierka.fly.dev` URL (✅ now available) to register a redirect URI at developer.spotify.com. Scopes needed: `streaming`, `user-read-email`, `user-read-private`, `user-modify-playback-state`, `user-read-playback-state`. Tokens to live in the host's HTTP session, never the DB.
- **GitHub Actions auto-deploy** — `FLY_API_TOKEN` secret + `.github/workflows/deploy.yml` calling `superfly/flyctl-actions/setup-flyctl@master` then `fly deploy --remote-only`.
- **Custom domain** — `fly certs add <domain>`, DNS A/AAAA at registrar, update `DJANGO_ALLOWED_HOSTS` + `CSRF_TRUSTED_ORIGINS`.
- **Spending guardrails** — 7-day trial in progress; calendar reminder set for 2026-05-31 to add a payment method or shut down with `fly scale count 0 -a melo-gierka`. Re-check whether Fly exposes a spending limit/cap once a card is attached.
- **Game logic itself** — no game code yet. This deploy ships an empty Django + read-only catalog. Future implementation work lands on top of this proven infra.

## Cross-references

- Plan that drove this deploy: `context/changes/deployment/deployment-plan.md`
- Platform research and risk register: `context/foundation/infrastructure.md`
- Recurring rules captured during this deploy: `context/foundation/lessons.md`
- Stack rationale: `context/foundation/tech-stack.md`
- Product spec: `context/foundation/prd.md`
