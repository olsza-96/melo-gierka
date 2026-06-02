# TODO — Next-session planning

Last updated: 2026-06-02 (after `game-session-models` change shipped)

The app is live at `https://melo-gierka.fly.dev` but ships **zero game logic** — just an empty Django + read-only catalog DB. Below is what to plan next, roughly in priority order.

## 1. Spotify integration (biggest unblocker)

Cannot start gameplay without it. Pre-work to do **outside the code**:

- [ ] Register a Spotify app at https://developer.spotify.com/dashboard
- [ ] Add redirect URI: `https://melo-gierka.fly.dev/auth/spotify/callback` (or whichever path you choose — fix it before registering)
- [ ] Capture Client ID + Client Secret → will become `fly secrets`: `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`

Design decisions for the session:

- [ ] **OAuth flow**: standard Authorization Code with PKCE. Tokens live in the **host's HTTP session** (signed cookie or short-lived in-memory), never in the DB.
- [ ] **Required scopes** per PRD FR-001 / FR-008: `streaming`, `user-read-email`, `user-read-private`, `user-modify-playback-state`, `user-read-playback-state`
- [ ] **Playback model**: Spotify Web Playback SDK in the host's browser (JS-only). Backend never streams audio — it just orchestrates "play this track starting at offset X for 30 seconds" via the Web API.
- [ ] **FR-008 random-offset**: 30-second fragment starting at `random.uniform(0.2, 0.8) * track.duration_ms`. Implement by issuing `PUT /me/player/play` with `position_ms` to the SDK-controlled player, then `PUT /me/player/pause` 30 s later.
- [ ] **Library choice**: `spotipy` (mature, well-documented) vs `httpx` + hand-rolled OAuth (smaller surface, no extra dep). Recommend `spotipy` for the auth flow, `httpx` directly for the time-sensitive playback calls.

## 2. Game-state model + endpoints (the actual gameplay)

> **Architectural update (2026-06-02):** in-memory dict approach REJECTED. Shipped via `game-session-models` change as Django ORM models + DB persistence + `cleanup_sessions` management command (PRD Open Q #3 default for v0). Sessions now survive restarts; single-worker constraint no longer applies.

- [x] **Models**: `GameSession`, `Player`, `Round` Django models in `game/` app (NOT dataclasses; reuses `catalog.MusicSet`/`Track` as FK targets). Shipped in `game-session-models`.
- [ ] **Lifecycle**: partial — `generate_session_code()` produces the 4-char code (FR-002). `join` (FR-004, FR-005 with unique-name suggestion), `start_round`, `submit_answer`, `end_session` still TODO (view layer).
- [x] ~~**State container**: module-level `dict[str, Room]` guarded by `threading.Lock`~~ — SUPERSEDED by Django ORM + `cleanup_sessions` (sessions idle > 1 h get deleted).
- [ ] **Polling endpoints**: `GET /api/room/<code>/state` returning JSON snapshot. Players poll ~1×/sec. (F-04, future change.)
- [ ] **Scoring (FR-011)**: time-weighted points, `score = max(0, 1000 * (1 - elapsed_s / 30))` or similar — settle on a formula.
- [ ] **End-of-game ranking screen** (FR-013).

## 3. Catalog curation (replace placeholder fixture)

PRD Open Question #4 — still unresolved.

- [ ] Decide the 5 sets: genre/era/mood mix. Current placeholders: `pop-2010s`, `rock-classics`, `polish-hits`, `dance-hits`, `indie-mix`. Keep, rename, or replace.
- [ ] Decide curation method: hand-pick via Spotify search → script that exports a `catalog/fixtures/initial.json`, or one-time scrape from a public playlist.
- [ ] ~30–50 tracks per set so the per-session no-repeat rule (10 rounds) has headroom.
- [ ] Replace `catalog/fixtures/initial.json` with real Spotify track IDs.

## 4. Frontend (the host + player UI)

Currently zero templates. Decide:

- [ ] Server-rendered Django templates vs HTMX vs a separate JS layer (the PRD says no separate SPA; HTMX + Alpine is the simplest fit).
- [ ] Two distinct UIs: **host screen** (desktop browser, plays audio, shows session code + lobby + current-round artist reveal) vs **player screen** (mobile, joins, sees 4 options, taps one, sees result).
- [ ] Static assets pipeline: keep using whitenoise.

## 5. Loose ends to capture as lessons

> Both items below are **MOOT** as of 2026-06-02 — `game-session-models` shifted state from in-memory dict to Django ORM. Sessions now survive worker count and deploys.

- ~~[ ] `/10x-lesson` — Single-worker gunicorn is mandatory when game state lives in process memory.~~ MOOT.
- ~~[ ] `/10x-lesson` — "No `fly deploy` during a session." Restart wipes in-memory rooms.~~ MOOT.

## 6. Infrastructure follow-ups (lower priority)

- [x] **GitHub Actions auto-deploy** — `.github/workflows/fly-deploy.yml` exists (assumes `FLY_API_TOKEN` secret is configured in repo settings — verify before relying on it).
- [ ] **Custom domain** — only after first real party-day if you decide to keep the project. `fly certs add …`, DNS at registrar, update `DJANGO_ALLOWED_HOSTS`.
- [ ] **Spending guardrails** — Google Calendar reminder set for 2026-05-31 to decide on payment method / shut down.
- [ ] **AGENTS.md** — per CLAUDE.md Lesson 4, run `/10x-agents-md` to write the contributor guide. **`game/` app now exists** (shipped 2026-06-02) — layout has settled, this is unblocked.

## 7. First real test session

After 1–4 land:

- [ ] Solo dry-run from two browser tabs (host + 1 player) end-to-end.
- [ ] Friend dry-run with 4–6 actual phones.
- [ ] Real party night. Per PRD success criteria: one full 10-round session must finish without anyone stuck on an error.

## What is already done

For context — don't re-do these:

- ✅ App deployed to `melo-gierka.fly.dev` on Fly.io (region `ams`)
- ✅ Catalog app + models + migrations + placeholder fixture
- ✅ Production Django settings (env-driven, secure cookies, HSTS, SSL redirect, `/health` exempt)
- ✅ Hand-rolled uv Dockerfile baking DB into image at build time
- ✅ `fly.toml` hardened (autostop off, min 1 machine, health check)
- ✅ Rollback drill verified
- ✅ Deploy contract written to `context/deployment/deploy-plan.md`
- ✅ Lesson captured: SSL-redirect exempt for `/health` on Fly
- ✅ `game` app with `GameSession` / `Player` / `Round` Django models, 4-char code generator (`secrets.randbelow`), `cleanup_sessions` management command, pytest-django test infra (`game-session-models` change, 2026-06-02)

See `context/changes/deployment/deployment-plan.md` for the full deploy log.
