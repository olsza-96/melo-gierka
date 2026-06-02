# Game Session Models + Ephemeral Cleanup — Plan Brief

> Full plan: `context/changes/game-session-models/plan.md`
> Change identity: `context/changes/game-session-models/change.md`

## What & Why

Build the data spine for melo-gierka — three Django models (`GameSession`, `Player`, `Round`) in a new `game` app, plus a session-code generator and a cleanup command. This is Foundation F-02 in the roadmap; it unlocks F-04 (polling endpoint) and slices S-01..S-04 (the entire gameplay loop up to the north star S-04). Without it, no other foundation has data to read or write.

## Starting Point

Codebase has one Django app `catalog` with `MusicSet` and `Track` models (`catalog/models.py:4-32`) — both will be reused as FK targets. SQLite is the default DB; `django.contrib.sessions` middleware is enabled, which is the substrate `GameSession.host_session_key` references. There is no test infrastructure yet (`pyproject.toml` ships only django + gunicorn + whitenoise), no scheduler, no `game/` app. CLAUDE.md says "first test sets convention" — this change picks pytest-django.

## Desired End State

After this lands: `uv run pytest` passes; `manage.py migrate` creates three tables (`game_gamesession`, `game_player`, `game_round`) with FKs to `catalog`; `manage.py shell` can produce a session with a unique 4-digit code, attach a player, attach a round; `manage.py cleanup_sessions --dry-run` reports which sessions would be purged; `cleanup_sessions` without the flag actually purges. The deployment image is unchanged (dev deps don't leak into the production wheel).

## Key Decisions Made

| Decision                            | Choice                                         | Why (1 sentence)                                                                                       | Source |
| ----------------------------------- | ---------------------------------------------- | ------------------------------------------------------------------------------------------------------ | ------ |
| `Player.score` storage              | Persisted `IntegerField`                       | One `ORDER BY -score` for scoreboard queries; race resolved with atomic `F('score') + delta` updates.  | Plan   |
| Cleanup mechanism                   | `manage.py cleanup_sessions` + Fly scheduled machine | Zero new Python deps; idiomatic Django; commit-able; Fly cron wiring deferred to a deployment plan.    | Plan   |
| Host token reference shape          | `host_session_key: CharField` (Django session id) | F-01 writes `request.session["spotify_access_token"]`; no token bytes in our DB.                       | Plan   |
| `GameSession.status` shape          | Explicit `TextChoices` (`lobby`/`playing`/`finished`) | Clear querysets for S-04 transitions and cleanup filtering.                                            | Plan   |
| 4-digit code generation             | Digits 0–9, `secrets.randbelow(10000)` with retry | Easy to dictate orally; 10k space; collisions handled by N-retry loop.                                 | Plan   |
| Test infrastructure                 | `pytest-django` + `pytest-cov` (dev deps)      | Richest Python test ecosystem; one-time setup cost; convention-setting for all future foundations.     | Plan   |
| New app `game`                      | Separate from `catalog`                        | Catalog domain (music sets, tracks) ≠ game domain (sessions, players, rounds); avoid mixing concerns.  | Plan   |
| `Round.(session, track)` uniqueness | DB constraint                                  | PRD Business Logic rule "bez powtórzeń w obrębie jednej sesji" enforced at schema, not app layer.      | Plan   |

## Scope

**In scope:**
- New Django app `game` with `GameSession`, `Player`, `Round` models + initial migration
- `generate_session_code()` utility (4-digit string, retry-on-collision)
- `manage.py cleanup_sessions` command with `--dry-run` and `--idle-hours` flags
- `pytest-django` + `pytest-cov` dev deps + `pyproject.toml` config
- Root smoke test `tests/test_smoke.py` anchoring the convention
- CLAUDE.md update documenting the test runner

**Out of scope:**
- Spotify OAuth code (F-01 owns it)
- Polling endpoint or any view that updates `last_activity_at` (F-04 owns it)
- Templates, URLs, admin theming beyond `list_display` (F-03 / S-01)
- Redis/TTL store swap (PRD Open Q #3 default = Django DB for v0)
- Fly scheduled machine wiring (operational follow-up; documented but not coded)
- CI integration of pytest (separate change)
- Partial-unique "one active session per host" constraint (post-MVP polish)

## Architecture / Approach

```
catalog/                          game/                       management cmd
+-------------+                  +----------------+           +-------------------+
| MusicSet    |<---------+       | GameSession    |           | cleanup_sessions  |
|             |          |       |  code (4-digit)|<--+       | --dry-run         |
+-------------+          +-----<-+  music_set FK  |   |       | --idle-hours      |
| Track       |<-----+           |  host_session  |   |       +---------+---------+
|  music_set  |      |           |  status enum   |   |                 |
|  duration_ms|      |           |  timestamps    |   |                 v
+-------------+      |           +----------------+   |       filter(last_activity_at__lt=now-1h)
                     |                                |       .delete()  -> CASCADE
                     |           +----------------+   |
                     +-----------+ Round          +---+
                                 |  session FK    |
                                 |  track FK      |
                                 |  offset_ms     |
                                 +----------------+
                                 +----------------+
                                 | Player         +---+
                                 |  session FK    |   |
                                 |  name (unique) |   |
                                 |  score         |   +---> session FK
                                 +----------------+
```

Three phases, each fully testable: (1) test infra anchors convention, (2) models + code generator land the spine, (3) cleanup command closes the ephemeral guardrail. Each phase ends with both automated (`pytest`, `migrate`, `check`) and manual (`shell` smoke walk) verification.

## Phases at a Glance

| Phase                                              | What it delivers                                            | Key risk                                                                                                 |
| -------------------------------------------------- | ----------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| 1. Test infrastructure                             | `pytest-django` installed, configured, smoke-tested         | Convention drift if a later foundation re-introduces `manage.py test`; CLAUDE.md update mitigates.       |
| 2. Game app + models + migrations + code generator | Three models, initial migration, code generator with tests  | `Round.(session, track)` uniqueness over-constrains if PRD ever allows track repetition (currently no).  |
| 3. Cleanup management command                      | `cleanup_sessions` cmd + tests + operational README in change folder | Fly scheduled machine wiring is deferred — manual run is the v0 fallback until that wiring lands.        |

**Prerequisites:** None. F-02 has no upstream Foundation dependencies. Existing `catalog` app + SQLite DB + `django.contrib.sessions` middleware are all already in place per `melo_gierka/settings.py`.

**Estimated effort:** ~1 working session for an experienced Django dev with `/10x-implement`, or 2–3 short sessions if learning pytest-django for the first time.

## Open Risks & Assumptions

- **Assumption:** Django session cookies survive the host's OAuth round-trip to Spotify. F-01 will verify and add `SESSION_COOKIE_SAMESITE` config if needed.
- **Risk:** Cleanup management command without a scheduled runner means "0 cleanup until human runs it" — acceptable for v0 (sessions die with `Player.score=0` if forgotten, no harm), but the README must be explicit about this.
- **Risk:** `Round.(session, track)` unique constraint at DB level couples the model to PRD Business Logic point #1 (no repeats per session). If PRD ever softens this rule, a migration to drop the constraint is required.

## Success Criteria (Summary)

- `uv run pytest` passes (all phases' tests).
- `manage.py migrate` applies cleanly to a fresh DB.
- `manage.py shell` walk-through: GameSession + Player + Round round-trip end-to-end.
- `cleanup_sessions --dry-run` reports stale sessions; `cleanup_sessions` deletes them.
- Production Docker image build is unchanged (pytest not in image).
