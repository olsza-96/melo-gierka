# Fly.io Deployment Plan — melo-gierka

## Context

Project is a Django 5.2 scaffold (Python 3.10, uv) targeting Fly.io per `context/foundation/infrastructure.md`. Currently: hardcoded insecure `SECRET_KEY`, `DEBUG=True`, empty `ALLOWED_HOSTS`, no Dockerfile, no `fly.toml`, no gunicorn/whitenoise, no apps. This plan ships the empty Django to Fly.io's `waw` region with a read-only **music catalog database** (Option B) so future game code lands on infra that's already proven.

The plan is also a learning vehicle: you'll touch Django models, migrations, fixtures, the admin, a hand-rolled uv Dockerfile, Fly secrets, and rollback — end-to-end.

## Architectural decisions (locked)

- **Catalog DB**: SQLite, **no volume**, baked into the Docker image. `migrate` + `loaddata` run at image **build time**, so every deploy ships a fresh DB pre-seeded from `catalog/fixtures/initial.json`. This honours PRD ephemerality (no persisted session data) and gives you a real DB to learn with.
- **Game state**: in-memory Python dict on the Fly machine. **gunicorn runs 1 worker + 4 threads** so threads share memory; multiple workers would not. This deliberately overrides `infrastructure.md`'s 2-worker suggestion — the load (≤6 players × ~1 req/sec) is trivial for a single worker.
- **Static files**: whitenoise, compressed manifest, served by gunicorn — no separate static host.
- **Region**: `waw` (Warsaw), `auto_stop_machines = "off"`, `min_machines_running = 1` — protects the ≤1 s polling guardrail (`infrastructure.md` risk #1).
- **Domain**: `*.fly.dev` only for MVP. Custom domain deferred.
- **CI/CD**: deferred. Manual `fly deploy` from your shell.
- **Spotify**: deferred. Production URL needs to exist first so OAuth redirect URI can be registered.
- **Execution boundary**: Agent writes all files and provides exact commands. **You run every `fly …` command yourself.** Secrets never enter the conversation.

## Phase 0 — Pre-flight (manual)

- [x] Install flyctl: `brew install flyctl`
- [x] `fly auth login` (browser flow)
- [x] `fly auth whoami` to confirm
- [x] Confirm Docker Desktop is installed and running (`docker version`) for local image build verification in Phase 5
- [x] Confirm `uv --version` works in repo root

**Edge case**: if `brew install flyctl` fails on macOS with permissions, fall back to `curl -L https://fly.io/install.sh | sh` and add `~/.fly/bin` to `PATH`.

## Phase 1 — Catalog app + models + fixture (agent writes) ✅

- [x] Create `catalog/` app: `uv run python manage.py startapp catalog`
- [x] Define models in `catalog/models.py`:
  - `MusicSet(slug: SlugField unique, name: CharField, description: TextField blank)`
  - `Track(music_set: FK to MusicSet, spotify_track_id: CharField, artist: CharField, title: CharField, duration_ms: IntegerField)` with `unique_together = (music_set, spotify_track_id)`
- [x] Register both models in `catalog/admin.py` for inspection in the Django admin
- [x] Add `catalog` to `INSTALLED_APPS` in `melo_gierka/settings.py`
- [x] Create initial migration: `uv run python manage.py makemigrations catalog`
- [x] Write `catalog/fixtures/initial.json` with **placeholder data**: 5 `MusicSet` rows (slugs: `pop-2010s`, `rock-classics`, `polish-hits`, `dance-hits`, `indie-mix`) and 7 tracks per set (35 tracks total). Real curation pending PRD Open Question #4.
- [x] Add a `catalog/management/commands/seed_catalog.py` wrapper that calls `loaddata initial.json` — gives you a single canonical seed command (`uv run python manage.py seed_catalog`).

**Verified locally**: `DJANGO_DEBUG=True uv run python manage.py migrate && … seed_catalog` → "Installed 40 object(s) from 1 fixture(s)".

**Edge case**: if you later edit the fixture and want to re-seed locally, delete `db.sqlite3` and rerun migrate + seed_catalog. Document this in the eventual `AGENTS.md` / `CLAUDE.md` update (out of scope here).

## Phase 2 — Production-grade settings refactor (agent writes) ✅

Edit `melo_gierka/settings.py`:

- [x] Read `DJANGO_SECRET_KEY` from env, default to a clearly-marked insecure dev value (`"insecure-dev-key-do-not-use-in-prod"`). Hard runtime check: if `DEBUG` is `False` and `SECRET_KEY` starts with `insecure-` → `raise ImproperlyConfigured`. **Verified firing** during local makemigrations.
- [x] `DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() == "true"` (default False — safer)
- [x] `ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")`
- [x] `CSRF_TRUSTED_ORIGINS = [f"https://{h}" for h in ALLOWED_HOSTS if h not in ("localhost", "127.0.0.1")]`
- [x] Add whitenoise: inserted `"whitenoise.middleware.WhiteNoiseMiddleware"` **directly after** `SecurityMiddleware` in `MIDDLEWARE`
- [x] `STATIC_ROOT = BASE_DIR / "staticfiles"`
- [x] `STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"`
- [x] When `DEBUG` is False: `SECURE_PROXY_SSL_HEADER`, `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS = 3600`, `SECURE_HSTS_INCLUDE_SUBDOMAINS = True`
- [x] Logging: stdout handler at INFO; Django at INFO, `django.request` at WARNING
- [x] `uv add gunicorn whitenoise` — landed in `pyproject.toml` + `uv.lock` (gunicorn 26.0.0, whitenoise 6.12.0)
- [x] CLAUDE.md note added: local `manage.py` commands need `DJANGO_DEBUG=True` prefix to bypass the guard

**Edge case (SECRET_KEY at build time)**: `collectstatic` doesn't need a real secret. The dev default lets the build succeed; the production secret comes from `fly secrets` at runtime. The `ImproperlyConfigured` guard prevents accidentally booting prod with the dev key.

**Edge case (ALLOWED_HOSTS chicken-and-egg)**: the app name is decided in Phase 6 (`fly launch`). Before then, the default `localhost,127.0.0.1` is fine; you set the real value via `fly secrets` in Phase 8 once the app name is known.

## Phase 3 — Health endpoint + root view (agent writes) ✅

- [x] Create `catalog/views.py` with two views:
  - `health(request)`: returns `JsonResponse({"status": "ok"})`, decorated with `@require_GET`, **no DB query**
  - `index(request)`: returns plain-text `HttpResponse` listing available `MusicSet` slugs (verifies DB end-to-end)
- [x] Wire URLs in `catalog/urls.py`: `/` → `index`, `/health` → `health`
- [x] Include `catalog.urls` from `melo_gierka/urls.py` at the root (kept `/admin/` as-is)

**Verified locally** with `runserver 127.0.0.1:8765`:
- `GET /health` → `200 {"status": "ok"}`
- `GET /` → `200 melo-gierka is up — available catalog sets: dance-hits, indie-mix, polish-hits, pop-2010s, rock-classics`

**Why two views, not one**: a DB-free `/health` is what Fly's health checks should hit (Phase 7); a DB-touching `/` proves the seeded catalog is reachable when you smoke-test in Phase 10. If `/health` queried the DB and the DB seed failed, Fly would mark the machine unhealthy and pull it — making debugging harder.

## Phase 4 — Dockerfile + .dockerignore (agent writes) ✅

`Dockerfile` at repo root (hand-rolled per `infrastructure.md`):

- [x] Base: `FROM python:3.10-slim`
- [x] Install uv: `RUN pip install --no-cache-dir uv`
- [x] Working dir `/app`
- [x] Copy `pyproject.toml`, `uv.lock`, `.python-version` first (layer caching)
- [x] `RUN uv sync --frozen --no-dev`
- [x] Copy the rest of the repo
- [x] `RUN export DJANGO_DEBUG=True && uv run python manage.py migrate --noinput && … seed_catalog && … collectstatic --noinput` — the inline `DJANGO_DEBUG=True` bypasses the SECRET_KEY guard for build-time management commands. Runtime CMD does **not** inherit this — `fly.toml [env]` sets `DJANGO_DEBUG=False` and `fly secrets` supplies the real key.
- [x] `EXPOSE 8080`
- [x] `CMD ["uv", "run", "gunicorn", "melo_gierka.wsgi", "--workers", "1", "--threads", "4", "--bind", "0.0.0.0:8080", "--access-logfile", "-", "--error-logfile", "-"]`

`.dockerignore`:
- [x] Includes: `.git`, `.venv`, `__pycache__`, `*.pyc`, `db.sqlite3`, `staticfiles/`, `context/`, `.claude/`, `*.md`, `.DS_Store`, `.vscode/`, `.idea/`

**Edge case (uv lock drift)**: `--frozen` makes the build fail if `uv.lock` is out of sync with `pyproject.toml`. That's the intended behaviour — fix lock before rebuilding (`uv lock`).

**Edge case (DB baking into image)**: the SQLite file ends up at `/app/db.sqlite3` inside the image. Make sure `.dockerignore` includes the **local** `db.sqlite3` so your dev DB doesn't overwrite the freshly seeded one when Docker copies the repo in. (The `COPY . .` happens before `migrate`, so the freshly built DB always wins regardless, but excluding local is cleaner.)

**Edge case (image size)**: `python:3.10-slim` is ~120 MB base. With uv + Django + whitenoise + gunicorn the image lands around 250–300 MB. Acceptable for MVP. Multi-stage build is `infrastructure.md` Out-of-Scope.

## Phase 5 — Local container verification (manual) ✅

- [x] `docker build -t melo-gierka:local .` — succeeded after the `DJANGO_DEBUG=True` build-time fix
- [x] `docker run --rm -p 8080:8080 -e DJANGO_DEBUG=False -e DJANGO_SECRET_KEY=… -e DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1 melo-gierka:local`
- [x] `curl -H "X-Forwarded-Proto: https" http://127.0.0.1:8765/health` → `200 {"status":"ok"}`. (Without the `X-Forwarded-Proto` header you get a 301 because `SECURE_SSL_REDIRECT=True`; Fly's proxy sets this header in production, so this is expected prod behaviour, not a bug.)
- [x] `curl -H "X-Forwarded-Proto: https" http://127.0.0.1:8765/` → `200` with all 5 catalog slugs in the body
- [x] Container stopped

**Edge case (Apple Silicon, amd64 mismatch)**: Fly's `shared-cpu-1x` is amd64. Docker on M-series Macs may build arm64 by default. If `fly deploy` later fails with "exec format error", rebuild with `docker build --platform=linux/amd64 …` or skip local verification and let Fly's remote builder do it (default). Fly's builder builds for the right arch regardless of your Mac — local verification is purely a smoke test.

**Skip rule**: if local Docker is painful (M-series, missing Docker Desktop), skip this whole phase. Fly's remote builder is the source of truth.

## Phase 6 — `fly launch` scaffolding (manual)

- [x] `fly launch --no-deploy --copy-config=false` from repo root
  - When prompted: **No** to "would you like to copy its configuration", **No** to Postgres/Redis/Tigris, name the app `melo-gierka` (or pick a unique name Fly suggests if taken), region `waw`
- [x] flyctl writes `fly.toml`. **Do not deploy yet** — the generated file needs hardening (Phase 7).
- [x] Note the resolved app name — you'll need it for Phase 8 secrets.

**Edge case (`fly launch` overwrites Dockerfile)**: pass `--copy-config=false` and `--no-deploy` and decline when prompted about Dockerfile. If it still overwrites, restore from git: `git checkout Dockerfile .dockerignore`.

**Edge case (region not available on free tier)**: `waw` is broadly available. If Fly says the org can't use `waw`, fall back to `fra` (Frankfurt, ~950 km from Warsaw) and update `fly.toml.primary_region` in Phase 7.

## Phase 7 — Harden `fly.toml` (agent edits) ✅

Rewrote the generated `fly.toml` (it shipped with `primary_region = ams`, `PORT = 8000`, `auto_stop_machines = stop`, `min_machines_running = 0`, a wrong-path `[[statics]]` block, and no health check). Final state:

- [x] `primary_region = "ams"` — initially tried `"waw"`, but `fly deploy` errored: *"Region waw is deprecated and cannot have new resources provisioned."* Fly's suggested alternates are `arn` (Stockholm) and `ams` (Amsterdam). Chose `ams` — ~1100 km from Warsaw, ~30 ms one-way latency, well within the ≤1 s polling guardrail.
- [x] `console_command = "uv run python manage.py shell"` (was `/code/manage.py shell` — wrong path; our WORKDIR is `/app`)
- [x] `[env]`: `PORT = "8080"`, `DJANGO_DEBUG = "False"` (was port `8000`, no DEBUG flag)
- [x] `[http_service]`: `internal_port = 8080`, `force_https = true`, `auto_stop_machines = "off"`, `auto_start_machines = true`, `min_machines_running = 1`, `processes = ["app"]`
- [x] `[[http_service.checks]]`: `GET /health`, `interval = "15s"`, `grace_period = "10s"`, `timeout = "5s"`
- [x] `[[vm]]`: `size = "shared-cpu-1x"`, `memory = "256mb"`, `cpus = 1`
- [x] Removed the generated `[[statics]]` block — pointed at `/code/static` which doesn't exist in our image; whitenoise serves static files in-process via gunicorn
- [x] No `[mounts]` section — Option B + no-volume choice locked

**Region fallback**: if `fly deploy` errors with "region not available", change `primary_region` to `ams` and redeploy. The plan's `infrastructure.md` cross-check accepted `ams`/`fra` as documented fallbacks.

## Phase 8 — Secrets (manual)

You run these in your terminal. Values never appear in the conversation.

- [x] Generate a SECRET_KEY locally: `python3 -c "import secrets; print(secrets.token_urlsafe(50))"`
- [x] `fly secrets set DJANGO_SECRET_KEY='<paste-the-value>'` (single-quote to protect special chars)
- [x] `fly secrets set DJANGO_ALLOWED_HOSTS='<app-name>.fly.dev'` (use the resolved app name from Phase 6)
- [ ] `fly secrets list` to verify both are set (values are masked)

**Edge case (rotating SECRET_KEY)**: re-running `fly secrets set DJANGO_SECRET_KEY=…` triggers a redeploy automatically. In v0 this is fine — there are no DB-backed sessions to invalidate; signed cookies survive a key change only if you ever switch to them, which we haven't.

**Edge case (secrets vs env in fly.toml)**: `DJANGO_DEBUG` is non-sensitive → lives in `[env]` (Phase 7). `DJANGO_SECRET_KEY` and `DJANGO_ALLOWED_HOSTS` are sensitive / environment-specific → live in `fly secrets`. Don't mix these up.

## Phase 9 — First deploy (manual)

- [x] `fly deploy` from repo root
- [x] Watch the build log: expect `migrate` and `seed_catalog` lines to run cleanly during the Docker build phase
- [x] On success Fly reports a machine ID and a green health check

**Edge case (build fails on `uv sync --frozen`)**: regenerate the lockfile with `uv lock` locally, commit, redeploy.

**Edge case (build fails on `migrate`)**: usually a missing migration. Run `uv run python manage.py makemigrations` locally, commit the generated file in `catalog/migrations/`, redeploy.

**Edge case (build fails on `collectstatic`)**: whitenoise complains about referenced files missing. For v0 (no templates yet) this is unlikely; if it happens, double-check `STATIC_ROOT` is set and `staticfiles` is in `INSTALLED_APPS` (it already is via Django defaults).

**Edge case (machine starts but health check fails)**: tail `fly logs`. Likely causes: `ALLOWED_HOSTS` doesn't include `<app>.fly.dev` (re-set the secret), `SECRET_KEY` failed the dev-key guard (re-set the secret), gunicorn binding to wrong port (`fly.toml internal_port` must match the gunicorn `--bind` port — both `8080`).

## Phase 10 — Smoke tests (manual)

- [X] `fly status` — machine `started`, health check `passing`, region `ams`
- [x] `curl -i https://<app>.fly.dev/health` → `200 {"status":"ok"}`
- [x] `curl -i https://<app>.fly.dev/` → `200`, body lists 5 catalog set slugs
- [X] `curl -i https://<app>.fly.dev/admin/login/` → `200`, Django admin login page renders (proves whitenoise serving admin static assets)
- [X] `fly logs` — no `WARNING`/`ERROR` lines on the first request

**Optional**: create a Django superuser inside the running machine to inspect the catalog via admin:
- [ ] `fly ssh console -C "uv run python manage.py createsuperuser --noinput --username=admin --email=you@example.com"` then set the password via shell (`fly ssh console` → `uv run python manage.py changepassword admin`). **Note**: this superuser dies on the next deploy because the DB is rebuilt from the image — that's expected for Option B.

## Phase 11 — Rollback drill (manual, do it once now)

Modern `flyctl` (≥0.3.x) removed the `releases list` and `releases rollback` subcommands. Rollback is now "redeploy a prior image tag":

- [X] `fly releases --image` — lists releases with their image refs (e.g. `registry.fly.io/melo-gierka:deployment-01KSGHYMQ5…`). Note the current and the previous image tags.
- [X] Make a trivial whitespace change to `melo_gierka/urls.py`, commit, `fly deploy` to get a second release on record
- [X] `fly deploy --image registry.fly.io/melo-gierka:deployment-<previous-id>` — confirm `fly status` reports the prior image restored within ~60 s
- [X] Roll forward again with `fly deploy --image registry.fly.io/melo-gierka:deployment-<latest-id>` so you end on the current code

**Why now**: practising rollback before you need it is the whole point of `infrastructure.md` listing it as a Pass criterion. The first time you need this in production is the worst time to learn the command.

**Note on `infrastructure.md`**: that doc still references `fly releases rollback` as a first-class CLI command, which is what flyctl used to expose. The mechanism still exists, just under a different name (re-deploying a tagged image).

## Phase 12 — Cost + observability (manual, deferred during trial)

Fly's billing-alert UX is thin. There's no universal "set an alert at $X" toggle today; what's available varies by account state. Practical checklist:

- [ ] **Trial-period cost guard**: set a calendar reminder for day 5 of the 7-day trial to log into `https://fly.io/dashboard/<org>/billing` and decide whether to add a payment method. `infrastructure.md` projects $2–6/mo on `shared-cpu-1x` always-on post-trial.
- [ ] **After adding a payment method**: check **Organization Settings → Billing** for a "spending limit" / "spending cap" control. If exposed for your org, set it to ~$10–15 as a hard cap. If not exposed, fall back to a monthly calendar reminder to spot-check the billing page.
- [ ] (Optional) Bookmark `https://fly.io/apps/melo-gierka/metrics` — live CPU/memory/network; reachable from `fly status` regardless.
- [ ] (Optional) Bookmark the rollback flow: `fly releases --image` then `fly deploy --image registry.fly.io/melo-gierka:deployment-<id>`.

**Plan note**: my earlier draft of this phase referenced an "Account → Billing → Alerts" menu that doesn't exist as a first-class UI feature on Fly. Corrected above.

## Phase 13 — Document deploy outcome (agent writes) ✅

- [x] Wrote `context/deployment/deploy-plan.md` capturing: app name (`melo-gierka`), region (`ams`, with the `waw` deprecation noted), public hostname (`melo-gierka.fly.dev`), the two configured secrets (names only), gunicorn worker model (1 worker × 4 threads with rationale), DB-baking-into-image strategy, rollback procedure (modern flyctl), `/health` SSL-exempt invariant, six load-bearing invariants, deferred items, and cross-references to the foundation docs.

## Files the agent will create or modify

| Path | Action |
|---|---|
| `pyproject.toml` | `uv add gunicorn whitenoise` |
| `uv.lock` | regenerated by `uv add` |
| `melo_gierka/settings.py` | refactor for env-based config, whitenoise, secure cookies |
| `melo_gierka/urls.py` | include `catalog.urls` |
| `catalog/` (new app) | full structure via `startapp` |
| `catalog/models.py` | `MusicSet`, `Track` |
| `catalog/admin.py` | register both models |
| `catalog/views.py` | `health`, `index` |
| `catalog/urls.py` | route to views |
| `catalog/migrations/0001_initial.py` | generated |
| `catalog/fixtures/initial.json` | placeholder catalog (5 sets, sample tracks) |
| `catalog/management/commands/seed_catalog.py` | wraps `loaddata` |
| `Dockerfile` | hand-rolled uv build |
| `.dockerignore` | exclude dev cruft and local SQLite |
| `fly.toml` | created by `fly launch`, then hardened |
| `context/deployment/deploy-plan.md` | post-deploy summary |

## Verification (end-to-end)

After Phase 10 passes you have:
- ✅ HTTPS endpoint serving from `waw` (verify region in `fly status`)
- ✅ `/health` returns 200 without touching DB
- ✅ `/` returns 200 listing 5 catalog set slugs (proves DB seed worked)
- ✅ `/admin/` reachable with whitenoise-served CSS (proves static pipeline)
- ✅ Machine stays warm (`auto_stop_machines = "off"`) — no cold-start violation of the ≤1 s polling guardrail
- ✅ Rollback drill passed (Phase 11) — you can revert in under 60 s

## Edge-case coverage (consolidated)

Each row below maps to a phase that addresses it.

| Risk | Phase | Mitigation in plan |
|---|---|---|
| Autostop kills cold poll (infra risk #1) | 7 | `auto_stop_machines = "off"`, `min_machines_running = 1` |
| Hand-rolled uv Dockerfile (infra risk #2) | 4, 5 | Documented pattern; local `docker build` verification |
| `fly deploy` mid-game kills in-memory rooms (infra risk #3) | 13 | Capture "no deploys during a session" in deploy-plan.md |
| Whitenoise misconfigured (infra risk #4) | 2, 5 | Middleware order pinned; `collectstatic` runs at build; local curl proves static |
| gunicorn OOM on 256 MB (infra risk #6) | 7 | Start with 1 worker × 4 threads at 256 MB; scale to 512 if logs show OOM |
| Free-tier-removed surprise (infra risk #7) | 12 | Spend alert at $10/mo |
| Single-machine deploy disconnects (infra risk #8) | 13 | Documented "no deploys during a session" |
| SECRET_KEY accidentally insecure in prod | 2 | `ImproperlyConfigured` guard when `DEBUG=False` and key starts with `insecure-` |
| ALLOWED_HOSTS chicken-and-egg with app name | 8 | Default localhost in settings; real value via `fly secrets` after `fly launch` resolves the name |
| Apple Silicon arch mismatch | 5 | Phase marked optional; Fly's remote builder is authoritative |
| Migration failure on deploy | 1, 9 | `makemigrations` runs locally; build fails loudly if a migration is missing |
| `fly launch` overwrites Dockerfile | 6 | `--no-deploy --copy-config=false`; restore from git if it slips |

## External integrations & out-of-scope

Captured here so they don't get lost — each is a separate task after this plan completes.

- **Spotify** — needs the live `<app>.fly.dev` URL (or future custom domain) to register a redirect URI at developer.spotify.com. Required scopes for melo-gierka (FR-001, FR-008): `streaming`, `user-read-email`, `user-read-private`, `user-modify-playback-state`, `user-read-playback-state`. Web Playback SDK runs in the host's browser only. Tokens stored in host's HTTP session (signed cookie or in-memory) — never in the DB. Plan a dedicated task once URL is live.
- **GitHub Actions auto-deploy** — `FLY_API_TOKEN` GitHub repo secret + `.github/workflows/deploy.yml` calling `superfly/flyctl-actions/setup-flyctl@master` then `fly deploy --remote-only`. Defer until manual deploy is proven and you've decided how to gate it (PR labels, branch protection, etc.).
- **Custom domain** — `fly certs add melo-gierka.party`, DNS A/AAAA records at your registrar, update `DJANGO_ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`. `infrastructure.md` flags up to 60+ min for cert provisioning — plan ahead.
- **Postgres / Redis upgrade** — only if the in-memory-state-dies-on-deploy risk becomes unacceptable during testing. `infrastructure.md` calls out Upstash Redis as the natural next step.
