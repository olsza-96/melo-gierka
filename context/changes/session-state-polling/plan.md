# Session State Polling Endpoint Implementation Plan

## Overview

Build F-04: a canonical polling endpoint at `GET /api/sessions/<code>/state` that returns the authoritative session snapshot for lobby, round, and finished-session screens. This gives S-02/S-03/S-04 one shared read surface while preserving the v0 constraints already chosen for melo-gierka: plain Django views, HTTP polling at ~1 second, and ephemeral session cleanup driven by `last_activity_at`.

## Current State Analysis

- **Game state model is ready:** `GameSession`, `Player`, and `Round` shipped in `game/models.py:4-79`, including `last_activity_at` for TTL cleanup and `Round.offset_ms` / `started_at` for round timing.
- **Cleanup already depends on poll freshness:** `game/management/commands/cleanup_sessions.py:12-49` deletes sessions whose `last_activity_at` is older than the idle cutoff. F-04 is the first slice that will keep active sessions alive by updating that field during normal client traffic.
- **Root routing is still catalog-only:** `melo_gierka/urls.py:4-7` includes only `catalog.urls`; there is no `game.urls` file and no API route registered yet.
- **Existing view pattern is plain Django:** `catalog/views.py:1-19` uses `@require_GET`, `JsonResponse`, and no DRF. F-04 should follow the same stack unless the repo grows a broader API framework later.
- **The current app has no gameplay read surface:** `/` still returns plain text and `/health` returns static JSON. There is no serialization helper, no game view module, and no request-level tests yet.
- **Test infrastructure is now stable:** `pyproject.toml` already configures `pytest-django`, and `game/tests.py` shows the established fixture style and DB-test pattern for the `game` app.
- **Product and roadmap decisions are already narrowed:** PRD + shape notes + roadmap fix the architecture to HTTP polling instead of WebSockets, code-based session access, ≤1s perceived lag, and keeping final session state ephemeral but available long enough to show the results screen.

## Desired End State

After this plan lands:

1. `GET /api/sessions/<code>/state` is reachable under the canonical `/api/sessions/<code>/state` path and returns a structured JSON snapshot for any valid session code.
2. The response contract covers the current needs of F-04 without front-loading S-03 gameplay fields: session metadata, ordered player list, current round timing metadata, and final-session state when the session is finished.
3. Unknown or cleaned-up session codes return a structured `404` JSON error.
4. Successful polls refresh `GameSession.last_activity_at` so active lobbies and active finished-session screens are not reaped by `cleanup_sessions`.
5. The endpoint emits conditional `ETag` / `304 Not Modified` responses for unchanged semantic state while still supporting the 1-second polling cadence.
6. `DJANGO_DEBUG=True uv run pytest game/tests.py` passes the new endpoint tests, including timing, freshness, and caching cases.

### Key Discoveries:

- `GameSession.last_activity_at` already exists specifically for idle cleanup in `game/models.py:25`, and `cleanup_sessions` consumes it directly in `game/management/commands/cleanup_sessions.py:30-49`.
- The current project routing surface is minimal (`melo_gierka/urls.py:4-7`), so F-04 must introduce `game.urls` rather than bolt more behavior into `catalog`.
- `Round` already stores the two timing primitives the user selected for the polling contract: `offset_ms` and `started_at` in `game/models.py:65-67`.
- The selected F-04 contract deliberately excludes answer `options` and `locks`; those remain S-03 concerns even though the route itself will be reused there.
- The roadmap mentions ETag support now, not as a later optimization, so caching belongs inside F-04 rather than as polish after S-02.
- Older notes in `TODO.md` still say `/api/room/<code>/state`, but roadmap + model naming are already aligned on `/api/sessions/<code>/state`; the plan treats the roadmap route as canonical.

## What We're NOT Doing

- **No join/start/submit-answer write endpoints.** F-04 is read-only; S-01/S-02/S-03 own state mutation.
- **No answer options, distractors, or lock-state generation.** F-04 exposes only session + player + current-round metadata. S-03 extends the payload contract with gameplay-specific fields.
- **No extra auth boundary beyond the 4-char session code.** The valid code is the v0 bearer secret for reading the session snapshot.
- **No WebSockets, Channels, SSE, or background workers.** CLAUDE.md and the stack docs lock v0 to HTTP polling.
- **No expired-vs-never-existed distinction in transport semantics.** Unknown or already-cleaned-up sessions both return structured `404` JSON; `410 Gone` is intentionally out of scope.
- **No separate results endpoint.** Finished sessions stay readable through the same polling route until TTL cleanup removes them.
- **No deploy / infrastructure changes.** `fly.toml`, machine sizing, and deployment mechanics stay untouched in this slice.

## Implementation Approach

Create a small game API surface inside the `game` app: `game.urls` for routing, a plain-Django GET view for `/api/sessions/<code>/state`, and a focused snapshot-building helper to keep the JSON contract and ETag logic deterministic. Build the response around the existing ORM models and their relationships, then add request-level pytest coverage that treats the endpoint as the authoritative state source for later lobby and round UIs.

## Critical Implementation Details

The endpoint must refresh `last_activity_at` on both `200 OK` and `304 Not Modified` responses; otherwise an unchanged but active lobby will be cleaned up as idle. To make `304` possible, the ETag must be computed from the semantic snapshot only — not from `server_now` and not from `last_activity_at`, because both values change every poll and would destroy cache hits.

## Phase 1: Endpoint scaffold and state contract

### Overview

Create the canonical route, build the read-only state snapshot, and cover the basic transport semantics: valid session, missing session, lobby state, playing state, and finished state.

### Changes Required:

#### 1. Game API routing

**File**: `game/urls.py` (new), `melo_gierka/urls.py`

**Intent**: Introduce a dedicated routing surface for game APIs and wire it under the existing project URLconf without coupling F-04 to `catalog`.

**Contract**: `melo_gierka/urls.py` includes `game.urls` under `/api/`, and `game/urls.py` defines the canonical `sessions/<str:code>/state` GET route. The older `/api/room/<code>/state` wording from `TODO.md` is not carried forward as a live alias.

#### 2. Session snapshot builder

**File**: `game/state.py` (new)

**Intent**: Centralize ORM loading and JSON-shape assembly so the route contract stays deterministic and can be extended in S-03 without bloating the view.

**Contract**: Add a helper that loads a `GameSession` by code with the related `music_set`, ordered `players`, and the current/latest `Round` plus its `track`. It returns a snapshot dict containing:
- top-level session metadata (`code`, `status`, `music_set`, `started_at`, `finished_at`)
- ordered players (`name`, `score`, `joined_at`)
- `current_round` as `null` or an object containing `index`, `started_at`, `offset_ms`, and track metadata (`spotify_track_id`, `artist`, `title`, `duration_ms`)

The phase-1 snapshot intentionally omits answer options, distractors, and lock-state fields.

#### 3. Polling view

**File**: `game/views.py` (new)

**Intent**: Expose the state snapshot through a plain Django GET endpoint that matches the project’s existing `JsonResponse` pattern.

**Contract**: Add a `@require_GET` view that accepts a session `code`, returns `404` JSON for unknown sessions, and returns `200` JSON for valid sessions in `lobby`, `playing`, or `finished` status. The `finished` response uses the same route and includes the final player ranking snapshot rather than redirecting callers to a different endpoint.

#### 4. Request-level endpoint tests

**File**: `game/tests.py`

**Intent**: Extend the `game` test suite from model coverage to request/response coverage so F-04 has a durable contract before S-02 builds on it.

**Contract**: Add client-based pytest coverage for:
- unknown session code returns structured `404` JSON
- lobby session returns ordered player state with `current_round = null`
- playing session returns current-round timing + track metadata
- finished session still returns `200` with the final snapshot

Reuse the existing `music_set`, `track`, and `session` fixture style already present in `game/tests.py`.

### Success Criteria:

#### Automated Verification:

- `DJANGO_DEBUG=True uv run pytest game/tests.py -k state` passes the new route and snapshot tests.
- `DJANGO_DEBUG=True uv run python manage.py check` exits 0 after wiring the new URL module and view.
- `DJANGO_DEBUG=True uv run python manage.py show_urls` is not available in this repo, so route verification stays inside request tests rather than relying on a separate URL-inspection command.

#### Manual Verification:

- With a shell-created lobby session, `curl http://127.0.0.1:8000/api/sessions/<code>/state` returns `200` JSON with session + players and no round object.
- With an unknown code, the same route returns a `404` JSON error rather than HTML.
- After marking a session `finished`, the route still returns the final snapshot through the same endpoint.

**Implementation Note**: After Phase 1 passes automated verification, pause for a quick manual curl/shell sanity check before adding caching logic in Phase 2.

---

## Phase 2: Timing, freshness, and conditional caching

### Overview

Teach the endpoint to support 1-second polling efficiently and safely: include server-side timing context, refresh `last_activity_at` for active sessions, and return `304` when the semantic snapshot has not changed.

### Changes Required:

#### 1. Timing contract finalization

**File**: `game/state.py`, `game/views.py`

**Intent**: Expose enough timing information for polling clients to reconcile elapsed round time without depending on device-clock luck.

**Contract**: Successful `200` responses include `server_now` alongside the semantic snapshot and keep `current_round.started_at` + `current_round.offset_ms` as the stable timing primitives. Datetime values use one consistent serialized format across session and round fields.

#### 2. Activity refresh semantics

**File**: `game/views.py`

**Intent**: Ensure normal polling traffic keeps active sessions alive under the F-02 cleanup regime.

**Contract**: Every successful poll for an existing session updates `GameSession.last_activity_at`, including requests that ultimately return `304 Not Modified`. Missing-session `404` responses do not create or mutate state.

#### 3. ETag and cache headers

**File**: `game/state.py`, `game/views.py`

**Intent**: Reduce repeated idle payload transfer without changing the polling cadence or introducing a different transport.

**Contract**: Add deterministic ETag generation from the semantic snapshot only. The view honors `If-None-Match` and returns `304` with the same caching headers when the snapshot is unchanged. `Cache-Control` is explicit and compatible with private, client-driven polling. `server_now` and `last_activity_at` are excluded from ETag generation so unchanged state can really produce `304` responses.

#### 4. Caching and freshness tests

**File**: `game/tests.py`

**Intent**: Lock the non-obvious endpoint guarantees in tests before downstream slices start depending on them.

**Contract**: Add pytest coverage for:
- identical consecutive polls return `304` when the client sends the matching `If-None-Match`
- semantic state changes (for example: player list mutation, session status mutation, or new round creation) produce a new ETag and a fresh `200`
- `last_activity_at` advances on both `200` and `304` responses for valid sessions
- the timing response shape includes `server_now` without forcing every poll to miss the ETag path

### Success Criteria:

#### Automated Verification:

- `DJANGO_DEBUG=True uv run pytest game/tests.py -k "state or etag"` passes the caching and freshness scenarios.
- `DJANGO_DEBUG=True uv run pytest game/tests.py` still passes the existing F-02 model and cleanup tests plus the new F-04 request tests.
- `DJANGO_DEBUG=True uv run python manage.py cleanup_sessions --dry-run` continues to run cleanly after the endpoint code is added.

#### Manual Verification:

- Two consecutive `curl` requests with the returned `ETag` and `If-None-Match` header yield `200` then `304` when state is unchanged.
- After editing session state in the shell (for example, adding a player or creating a round), the next poll returns `200` with a different `ETag`.
- Repeated polling of an unchanged valid session does not make it eligible for cleanup while the poll loop is active.

**Implementation Note**: After Phase 2 passes, pause for manual confirmation that the `304` path still refreshes activity correctly before moving to the final handoff phase.

---

## Phase 3: Contract handoff and downstream verification

### Overview

Document the F-04 contract for the next slices and lock in the manual verification story for host/player polling behavior.

### Changes Required:

#### 1. Endpoint contract note

**File**: `context/changes/session-state-polling/README.md` (new)

**Intent**: Give S-02/S-03/S-04 a concise contract reference without forcing future implementers to reverse-engineer the route behavior from tests.

**Contract**: Document the canonical route, response shape, `404` behavior, `ETag` / `304` semantics, and the explicit out-of-scope fields deferred to S-03 (answer options and lock-state). Include one example `curl` flow for `200` then `304`.

#### 2. Manual verification scriptability

**File**: `context/changes/session-state-polling/plan.md` (progress only during implementation), `context/changes/session-state-polling/README.md`

**Intent**: Make the downstream handoff operationally useful for a solo developer testing host and player tabs locally.

**Contract**: The change README names the exact local verification flow: create data in the shell, poll from one terminal or browser tab, mutate state in another shell, and confirm `ETag`, `server_now`, and final-state behavior.

### Success Criteria:

#### Automated Verification:

- `DJANGO_DEBUG=True uv run pytest game/tests.py` remains green with the full F-02 + F-04 suite.
- `DJANGO_DEBUG=True uv run python manage.py check` remains green after all F-04 files are present.

#### Manual Verification:

- A local two-tab or curl-plus-shell smoke test demonstrates lobby polling, a state change producing a fresh `200`, and a finished session still rendering through the same endpoint.
- The change README is sufficient for a later implementer to consume the endpoint without reopening the roadmap or PRD to rediscover the contract.

**Implementation Note**: After Phase 3 lands and the manual smoke passes, F-04 is complete and the next planning target should shift to S-02 or the remaining ready foundations depending on delivery order.

## Testing Strategy

### Unit Tests:

- Snapshot-builder tests for player ordering, round selection, and null-vs-object `current_round` behavior.
- ETag determinism tests proving non-semantic fields do not churn the cache key.
- `last_activity_at` refresh tests for both `200` and `304` responses.

### Integration Tests:

- Request-level client tests for unknown, lobby, playing, and finished sessions.
- Conditional request tests that poll the endpoint, reuse `ETag`, mutate state, and verify the response flips back to `200`.
- Regression coverage ensuring the F-04 endpoint coexists with F-02 cleanup semantics.

### Manual Testing Steps:

1. Start the dev server and create a session, players, and (optionally) a round in `manage.py shell`.
2. Poll `/api/sessions/<code>/state` from `curl` or the browser and verify the JSON shape for lobby, then for playing and finished states.
3. Reuse the returned `ETag` with `If-None-Match`, observe `304`, then mutate state in the shell and confirm the next poll returns `200` with a new `ETag`.
4. Leave a valid session polling unchanged for several requests, then confirm `cleanup_sessions --dry-run` does not mark it stale while polling remains active.

## Performance Considerations

- Polling frequency stays ~1 request per second per client, as already chosen in the roadmap; at 4–6 players plus one host, this remains trivial for the current Fly footprint.
- The snapshot loader should use `select_related` / `prefetch_related` appropriately so the common poll path does not degrade into per-player or per-round query chatter.
- ETag support cuts repeated idle payload transfer during lobby waits and finished-state viewing without introducing transport complexity.

## Migration Notes

- No schema migration is required for F-04; it builds entirely on the F-02 models already in place.
- Rollback is file-level only: removing the route and view returns the app to its current catalog-only behavior.
- Because there is no schema change, this slice should keep the existing `db.sqlite3` and seeded catalog data untouched.

## References

- Roadmap entry: `@context/foundation/roadmap.md` (F-04)
- Upstream data model: `@context/changes/game-session-models/plan.md`
- Existing models: `game/models.py:4-79`, `catalog/models.py:1-30`
- Existing root routing: `melo_gierka/urls.py:4-7`
- Existing plain-Django view pattern: `catalog/views.py:1-19`
- Cleanup dependency: `game/management/commands/cleanup_sessions.py:12-49`
- Product requirements: `@context/foundation/prd.md` FR-006, FR-009, FR-013 and NFR §Lag / §Sesja ulotna
- Prior decision record: `@context/foundation/shape-notes.md`, `TODO.md`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles.

### Phase 1: Endpoint scaffold and state contract

#### Automated

- [x] 1.1 `DJANGO_DEBUG=True uv run pytest game/tests.py -k state` passes the new route and snapshot tests — 19cb59f
- [x] 1.2 `DJANGO_DEBUG=True uv run python manage.py check` exits 0 after wiring the new URL module and view — 19cb59f
- [x] 1.3 Route verification stays covered by request tests because this repo has no `show_urls` command — 19cb59f

#### Manual

- [x] 1.4 Valid lobby session returns `200` JSON with session + players and no round object — 19cb59f
- [x] 1.5 Unknown code returns structured `404` JSON rather than HTML — 19cb59f
- [x] 1.6 Finished session still returns the final snapshot through the same endpoint — 19cb59f

### Phase 2: Timing, freshness, and conditional caching

#### Automated

- [x] 2.1 `DJANGO_DEBUG=True uv run pytest game/tests.py -k "state or etag"` passes the caching and freshness scenarios — 9d08c6a
- [x] 2.2 `DJANGO_DEBUG=True uv run pytest game/tests.py` stays green with the full F-02 + F-04 suite — 9d08c6a
- [x] 2.3 `DJANGO_DEBUG=True uv run python manage.py cleanup_sessions --dry-run` still runs cleanly after the endpoint code is added — 9d08c6a

#### Manual

- [x] 2.4 Consecutive requests with `If-None-Match` yield `200` then `304` for unchanged state — 9d08c6a
- [x] 2.5 A shell-driven state mutation produces a new `ETag` and a fresh `200` — 9d08c6a
- [x] 2.6 Repeated valid polling keeps the session from appearing stale to cleanup — 9d08c6a

### Phase 3: Contract handoff and downstream verification

#### Automated

- [x] 3.1 `DJANGO_DEBUG=True uv run pytest game/tests.py` remains green with the full suite — 63af875
- [x] 3.2 `DJANGO_DEBUG=True uv run python manage.py check` remains green after all F-04 files are present — 63af875

#### Manual

- [x] 3.3 A local two-tab or curl-plus-shell smoke test demonstrates lobby, changed-state, and finished-session behavior — 63af875
- [x] 3.4 `context/changes/session-state-polling/README.md` is sufficient for downstream slices to consume the endpoint contract — 63af875
