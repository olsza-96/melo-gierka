# Session State Polling Endpoint — Plan Brief

> Full plan: `context/changes/session-state-polling/plan.md`

## What & Why

This plan builds F-04: the canonical polling endpoint that every later gameplay slice will read from. It turns the F-02 data model into a usable live session surface for lobby updates, round timing, and final-state rendering while staying inside the product’s v0 constraint of plain HTTP polling at ~1 second.

## Starting Point

The repo already has the persistent session model from F-02 (`GameSession`, `Player`, `Round`) plus cleanup based on `last_activity_at`, but no game API routes, no game view module, and no request-level tests. Root routing still points only at `catalog`, so there is currently no way for a host or player UI to read live session state from the backend.

## Desired End State

After this plan, `/api/sessions/<code>/state` returns the authoritative JSON snapshot for a valid session: session metadata, ordered players, current round timing metadata, and final-session state when the game is finished. The endpoint also supports conditional `ETag` / `304` polling and refreshes `last_activity_at` so active sessions survive the cleanup TTL.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Canonical route | `/api/sessions/<code>/state` | Aligns the API path with roadmap wording and `GameSession` model naming. | Plan |
| Payload scope | Session + players + current round metadata only | Keeps F-04 a clean foundation without freezing speculative S-03 answer fields too early. | Plan |
| Cache strategy | Real conditional `ETag` support in F-04 | The roadmap already names ETag support, and 1s polling benefits immediately from unchanged-state `304`s. | Plan |
| Missing session semantics | Structured `404` JSON | Standard HTTP semantics are clearer than inventing a `200 status=missing` branch or tracking `410` causes. | Plan |
| Timing contract | `started_at` + `offset_ms` + `server_now` | Gives clients enough information to reason about drift without relying only on local clocks. | Plan |
| Late-client behavior | Always return the latest snapshot | Matches the roadmap default and keeps the polling surface stateless. | Plan |
| Read boundary | Valid 4-char code acts as the v0 bearer secret | Fits the no-account party model without dragging auth mechanics into a foundation endpoint. | Plan |
| Finished-state behavior | Keep returning final state until TTL cleanup | Lets the same polling route power results screens reliably before cleanup removes the session. | Plan |

## Scope

**In scope:**
- Canonical game API route and URL wiring
- Read-only session snapshot builder
- Plain Django GET polling view
- Ordered players + current round timing metadata + finished-session state
- `ETag` / `304` support and `last_activity_at` refresh semantics
- Request-level pytest coverage and contract README

**Out of scope:**
- Join/start/submit-answer write endpoints
- Answer options, distractors, and lock-state fields
- Extra auth beyond possession of the session code
- WebSockets / SSE / Channels
- Separate results endpoint or `410 Gone` lifecycle split
- Deploy / infra changes

## Architecture / Approach

Clients poll `/api/sessions/<code>/state` once per second. A plain Django view loads the `GameSession` plus related `players` and current `Round` through a dedicated snapshot helper, computes an ETag from the semantic snapshot, then either returns `304` for unchanged state or `200` JSON with `server_now`. On both successful paths, the view refreshes `last_activity_at` so F-02 cleanup does not delete active sessions.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Endpoint scaffold and state contract | Canonical route, snapshot helper, view, and base request tests | Locking the right response shape without leaking future S-03 assumptions |
| 2. Timing, freshness, and conditional caching | `server_now`, activity refresh, deterministic ETag / `304`, and cache tests | Accidentally making every poll miss the ETag path by hashing volatile fields |
| 3. Contract handoff and downstream verification | README contract note and repeatable manual smoke flow | Leaving the endpoint usable in code but under-documented for S-02/S-03 |

**Prerequisites:** F-02 is implemented; no schema work is required before starting.
**Estimated effort:** ~2-3 implementation sessions across 3 phases.

## Open Risks & Assumptions

- The 4-char session code is accepted as a sufficient read secret for v0, even though it is not strong auth.
- S-03 will extend the response contract with answer options and lock-state instead of introducing a second read endpoint.
- `last_activity_at` must be refreshed on both `200` and `304`; otherwise unchanged but active sessions will still be cleaned up.
- The ETag must ignore `server_now` and `last_activity_at`, or cache hits will collapse to zero.

## Success Criteria (Summary)

- Valid sessions poll successfully through `/api/sessions/<code>/state`, and missing sessions return structured `404` JSON.
- Unchanged state yields `304` with `If-None-Match`, while real state changes produce a new `ETag` and fresh `200` JSON.
- Active polling prevents cleanup from classifying a live session as stale.
