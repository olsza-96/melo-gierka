# Game Session Models + Ephemeral Cleanup — Implementation Plan

## Overview

Build the data spine for melo-gierka: three Django models (`GameSession`, `Player`, `Round`) in a new `game` app, plus a session-code generator and a cleanup management command that purges sessions idle > 1 h. Establishes `pytest-django` as the project's test convention (this is the first test in the repo per CLAUDE.md). Unlocks F-04 (polling endpoint) and slices S-01..S-04.

## Current State Analysis

- **Existing app**: `catalog` (`catalog/models.py:4-32`) ships `MusicSet(slug, name, description)` and `Track(music_set FK, spotify_track_id, artist, title, duration_ms)`. These are reused as FK targets — no changes to `catalog/`.
- **Settings**: SQLite default (`melo_gierka/settings.py:96-101`), `django.contrib.sessions` middleware enabled (line 66), `BigAutoField` default. Tokens for Spotify will land in `request.session` (Django sessions backend), and `GameSession` stores `host_session_key` as a pointer.
- **No app for game/play domain yet** — `catalog` is wrong home for session/player/round (mixes concerns). New app `game` is created.
- **No test infrastructure** — `pyproject.toml` has 3 deps (django, gunicorn, whitenoise); no pytest, no factories, no `conftest.py`. CLAUDE.md says "first test sets convention".
- **No scheduler** — no APScheduler/Celery/cron. Cleanup is via `manage.py` command + Fly scheduled machine (separate operational concern, documented but not wired in this change).
- **uv + Django 5.2.14**: dependencies managed by `uv add` / `uv add --dev`. Run Django via `DJANGO_DEBUG=True uv run python manage.py ...` per CLAUDE.md.

## Desired End State

After this plan lands:

1. `uv run pytest` passes, including new tests for `game` models and code generator.
2. `DJANGO_DEBUG=True uv run python manage.py migrate` applies new `game/migrations/0001_initial.py` cleanly to an empty database.
3. `DJANGO_DEBUG=True uv run python manage.py shell` can create a `GameSession` with a unique 4-digit code, attach a `Player`, and a `Round` pointing at an existing `Track`.
4. `DJANGO_DEBUG=True uv run python manage.py cleanup_sessions --dry-run` reports which sessions would be deleted; without `--dry-run` it deletes them.
5. `pyproject.toml` has `[tool.pytest.ini_options]` block configuring `DJANGO_SETTINGS_MODULE` and a project-root `tests/` discovery convention.

### Key Discoveries:

- `catalog.Track` already carries `duration_ms` (`catalog/models.py:25`) — `Round.offset_ms` computation (FR-008: 20–80% of track length) can use this directly, no schema change.
- Django session middleware is enabled in `melo_gierka/settings.py:66`, so `request.session.session_key` is available once the host's session is touched by the OAuth callback (F-01 work).
- `lessons.md` rule about `SECURE_REDIRECT_EXEMPT` for `/health` is informational only — no impact on this change.

## What We're NOT Doing

- **No Spotify OAuth code** — F-01 owns it. `GameSession.host_session_key` is a CharField; F-01 will write `request.session["spotify_access_token"]` against that session.
- **No polling endpoint** — F-04 owns `/api/sessions/<code>/state`. This change does NOT update `last_activity_at` from any view; that happens in F-04.
- **No views, URLs, templates, or admin theming** — F-03 owns templates; user-facing screens are S-01+.
- **No Redis / TTL store** — PRD Open Q #3 default for v0 is Django DB + cleanup command. Redis swap is a v1 concern when "mid-game deploy = lost games" actually bites.
- **No automatic Fly scheduled machine setup** — the management command is the deliverable; wiring it to a cron-like Fly scheduler is documented in this plan but the actual Fly configuration change is out of scope for this F-02 PR (operational, lands in deployment plan).
- **No CI integration of pytest** — `.github/workflows/fly-deploy.yml` stays as-is. Wiring tests into CI is a separate concern.
- **No partial-unique constraint enforcing "one active session per host"** — host UI in S-01 will guard this in app logic; constraint is post-MVP polish.

## Implementation Approach

Three phases, each fully testable in isolation. Phase 1 establishes test infra so Phases 2 and 3 can ship tests alongside code (no retrofit). Phase 2 is the meat — models + migrations + code generator. Phase 3 is the cleanup operational tooling.

The shape mirrors the **roadmap F-02 contract**: "models with migrations; cleanup task; reuses catalog.MusicSet/Track". Each phase ends with both automated verification (commands that run unattended) and manual verification (Django shell smoke tests) before proceeding.

## Critical Implementation Details

- **Test runner shifts from `manage.py test` to `pytest`** after Phase 1. Future foundations (F-03, F-04) and slices inherit this convention. CLAUDE.md update in Phase 1 makes this discoverable for the next agent run.
- **4-digit code with leading zeros must be `CharField(max_length=4)`, not `IntegerField`.** A code of `0014` rendered from an int becomes `14` and breaks ergonomics. Generator uses `f"{n:04d}"` formatting.
- **Cleanup uses `last_activity_at`, not `created_at`** as the idle signal. The field exists from migration 0001 with `default=django.utils.timezone.now`; F-04 will update it on every polling tick. Cleanup of lobbies that never started works because `last_activity_at == created_at` until the first tick.

## Phase 1: Test infrastructure

### Overview

Add `pytest-django` + `pytest-cov` as dev deps, configure `pyproject.toml`, add a project-root `tests/` directory with a smoke test that exercises `catalog.MusicSet`. This anchors the test convention for every subsequent change.

### Changes Required:

#### 1. Dev dependencies

**File**: `pyproject.toml`

**Intent**: Add a `[dependency-groups] dev` block with `pytest`, `pytest-django`, `pytest-cov` so `uv sync --dev` and `uv add --dev` populate dev tooling without leaking into the production wheel built by `Dockerfile`.

**Contract**: New top-level `[dependency-groups]` table with a `dev` array. `uv.lock` regenerates accordingly. The Dockerfile already uses `uv sync --frozen --no-dev`, so production image is unchanged.

#### 2. Pytest configuration

**File**: `pyproject.toml`

**Intent**: Add `[tool.pytest.ini_options]` so `uv run pytest` discovers tests under both `tests/` (repo root, for cross-app/integration) and `<app>/tests.py` (per-app, Django convention), and uses `melo_gierka.settings` as `DJANGO_SETTINGS_MODULE`.

**Contract**: Block specifies `DJANGO_SETTINGS_MODULE = "melo_gierka.settings"`, `python_files = ["test_*.py", "tests.py"]`, `testpaths = ["tests", "catalog", "game"]` (game added in Phase 2 but pre-listed). Also sets `addopts = "--strict-markers --tb=short"`. Coverage config is minimal: `[tool.coverage.run] source = ["catalog", "game"]`.

#### 3. Root smoke test

**File**: `tests/test_smoke.py` (new) + `tests/__init__.py` (empty)

**Intent**: Verify pytest + Django wiring works end-to-end by creating a `MusicSet` and asserting it round-trips through the ORM. This is intentionally trivial — it catches "pytest-django not installed" or "settings module wrong" before any non-trivial test depends on the wiring.

**Contract**: Single `@pytest.mark.django_db` test function. Imports `from catalog.models import MusicSet`. Asserts `MusicSet.objects.create(slug=..., name=...).pk` is not None. No fixtures yet.

#### 4. CLAUDE.md update

**File**: `CLAUDE.md`

**Intent**: Add a line under "Stack quirks" documenting the test runner and how to run it, so future agent invocations don't suggest `manage.py test`.

**Contract**: One bullet near the existing test/lint/CI note: `Tests: pytest-django via `uv run pytest`. Config in `pyproject.toml` `[tool.pytest.ini_options]`. Use `@pytest.mark.django_db` for DB-touching tests.` Existing "No tests, no lint, no CI yet" sentence is replaced by "Tests: pytest. No lint, no CI yet."

### Success Criteria:

#### Automated Verification:

- `uv sync --dev` exits 0 and installs pytest, pytest-django, pytest-cov.
- `uv run pytest --collect-only` discovers `tests/test_smoke.py::test_music_set_round_trip`.
- `uv run pytest` exits 0 with 1 passing test.
- `uv run pytest --cov` reports coverage (any %, just verifying the plugin loads).
- Production image build is unchanged: `docker build .` exits 0 and the image does not contain `pytest` (verify via `docker run --rm <image> python -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('pytest') is None else 1)"`).

#### Manual Verification:

- Open `pyproject.toml` and confirm `[dependency-groups] dev` and `[tool.pytest.ini_options]` are present and readable.
- Confirm CLAUDE.md update reads naturally and the "No tests" wording is corrected.

**Implementation Note**: After Phase 1 passes automated verification, pause for manual confirmation that the smoke test actually runs locally (the human reads pytest output once) before Phase 2.

---

## Phase 2: Game app + models + migrations + code generator

### Overview

Create a new Django app `game`. Define `GameSession`, `Player`, `Round` models with the agreed schema. Add a `generate_session_code()` utility that produces a unique 4-digit string with retry-on-collision. Wire models into admin for shell-free inspection. Generate and ship `game/migrations/0001_initial.py`.

### Changes Required:

#### 1. New Django app scaffold

**File**: `game/` (new directory) + `game/__init__.py`, `game/apps.py`, `game/admin.py`, `game/tests.py`, `game/migrations/__init__.py`

**Intent**: Standard `python manage.py startapp game`-shaped scaffold. The `apps.py` declares `default_auto_field = "django.db.models.BigAutoField"` (consistent with the project default in `settings.py:128`).

**Contract**: `game.apps.GameConfig` registered in `INSTALLED_APPS` (next change). Directory layout matches Django default; no custom layout.

#### 2. Register `game` in settings

**File**: `melo_gierka/settings.py`

**Intent**: Append `"game"` to `INSTALLED_APPS` so its migrations and admin register.

**Contract**: Single line addition after `"catalog"` (line 60).

#### 3. `GameSession` model

**File**: `game/models.py`

**Intent**: Persist a play session keyed by a 4-digit code. Tracks host identity via Django session key (not the access_token; F-01 stores the token in `request.session`). Status moves `lobby → playing → finished`. Timestamps support cleanup logic.

**Contract**:
- Fields: `code: CharField(max_length=4, unique=True, db_index=True)`, `music_set: ForeignKey(catalog.MusicSet, on_delete=PROTECT)`, `host_session_key: CharField(max_length=40)`, `status: CharField(max_length=10, choices=Status.choices, default=Status.LOBBY)`, `created_at: DateTimeField(auto_now_add=True)`, `started_at: DateTimeField(null=True, blank=True)`, `finished_at: DateTimeField(null=True, blank=True)`, `last_activity_at: DateTimeField(default=timezone.now, db_index=True)`.
- Inner `Status` is `models.TextChoices` with members `LOBBY = "lobby"`, `PLAYING = "playing"`, `FINISHED = "finished"`.
- `Meta.ordering = ["-created_at"]`.
- `__str__` returns `f"{code} ({status})"`.

Snippet — TextChoices block is the non-obvious part:

```python
class GameSession(models.Model):
    class Status(models.TextChoices):
        LOBBY = "lobby", "Lobby"
        PLAYING = "playing", "Playing"
        FINISHED = "finished", "Finished"
```

#### 4. `Player` model

**File**: `game/models.py`

**Intent**: One row per joined player per session. `name` unique within a session. `score` is a persisted integer, incremented atomically when a round locks.

**Contract**:
- Fields: `session: ForeignKey(GameSession, related_name="players", on_delete=CASCADE)`, `name: CharField(max_length=40)`, `score: IntegerField(default=0)`, `joined_at: DateTimeField(auto_now_add=True)`.
- `Meta.constraints = [UniqueConstraint(fields=["session", "name"], name="unique_player_name_per_session")]`.
- `Meta.ordering = ["session", "-score", "joined_at"]` so default queryset already sorts by leaderboard within a session.
- `__str__` returns `f"{name} @ {session.code}"`.

#### 5. `Round` model

**File**: `game/models.py`

**Intent**: One row per round. `offset_ms` carries the random 20–80% offset (FR-008); computed in the round-start flow (S-03), not here. `started_at` is when host began the fragment; `locked_at` is when round closed (any player locked, or timeout).

**Contract**:
- Fields: `session: ForeignKey(GameSession, related_name="rounds", on_delete=CASCADE)`, `index: PositiveSmallIntegerField()` (1..10 per session), `track: ForeignKey(catalog.Track, on_delete=PROTECT)`, `offset_ms: PositiveIntegerField()`, `started_at: DateTimeField()`, `locked_at: DateTimeField(null=True, blank=True)`.
- `Meta.constraints = [UniqueConstraint(fields=["session", "index"], name="unique_round_index_per_session"), UniqueConstraint(fields=["session", "track"], name="unique_track_per_session")]` — second constraint enforces PRD Business Logic rule "bez powtórzeń w obrębie jednej sesji".
- `Meta.ordering = ["session", "index"]`.
- `__str__` returns `f"Round {index} of {session.code}"`.

#### 6. Session code generator

**File**: `game/codegen.py` (new)

**Intent**: Produce a unique 4-digit code as a 4-char string with leading zeros preserved. Retry up to N times on collision; raise on exhaustion (effectively never hit at 10k space + a few sessions per day, but defensive).

**Contract**: Public function `generate_session_code(*, max_attempts: int = 10) -> str`. Uses `secrets.randbelow(10000)` for unbiased generation, formats with `f"{n:04d}"`, queries `GameSession.objects.filter(code=...).exists()` for collision check. Raises `RuntimeError` if all attempts collide.

Snippet — `secrets` (not `random`) is the non-obvious part:

```python
import secrets

def generate_session_code(*, max_attempts: int = 10) -> str:
    from game.models import GameSession  # lazy to avoid circular import
    for _ in range(max_attempts):
        code = f"{secrets.randbelow(10000):04d}"
        if not GameSession.objects.filter(code=code).exists():
            return code
    raise RuntimeError(f"could not generate unique session code in {max_attempts} attempts")
```

#### 7. Admin registration

**File**: `game/admin.py`

**Intent**: Register `GameSession`, `Player`, `Round` in admin with sensible `list_display` so shell isn't the only inspection path. Keep this inspection-focused and avoid custom admin workflows at this stage — F-01/S-01 will mutate via app logic.

**Contract**: Three `@admin.register(...)` blocks with `list_display`, `list_filter` (on `status` for GameSession), `search_fields` (on `code` for GameSession, `name` for Player). No custom forms.

#### 8. Migrations

**File**: `game/migrations/0001_initial.py` (generated, committed)

**Intent**: Single initial migration covering all three models and constraints. Generated by `makemigrations game`, then committed.

**Contract**: `dependencies = [("catalog", "0001_initial")]` (auto-derived from FK to `catalog.MusicSet` / `catalog.Track`). All constraints from the model `Meta` blocks present.

#### 9. Model tests

**File**: `game/tests.py`

**Intent**: Cover the schema invariants and the code generator:
- `GameSession` can be created with valid fields; default status is `lobby`.
- `Player` `name` unique-per-session: second insert with same `(session, name)` raises `IntegrityError`.
- `Round` `(session, index)` and `(session, track)` uniqueness raise `IntegrityError` on violation.
- `generate_session_code()` returns a 4-character string of digits.
- `generate_session_code()` retries on collision: pre-seed one occupied code, monkeypatch `secrets.randbelow` to return that occupied value first and an unoccupied value second, then assert the function retries and returns the free code.
- `generate_session_code()` raises `RuntimeError` when all attempts collide: pre-seed one occupied code, monkeypatch `secrets.randbelow` to keep returning that occupied value, call with a low `max_attempts`, and assert `RuntimeError`.

**Contract**: All tests use `@pytest.mark.django_db`. Collision/exhaustion tests are deterministic: they use `monkeypatch` on `secrets.randbelow` plus a tiny pre-seeded set of occupied codes, so there is no 10k-row setup and no probabilistic failure mode.

### Success Criteria:

#### Automated Verification:

- `DJANGO_DEBUG=True uv run python manage.py makemigrations game --check --dry-run` reports no pending changes after the migration is committed (verifies the migration matches the models).
- `DJANGO_DEBUG=True uv run python manage.py migrate game` applies cleanly on a fresh DB.
- `uv run pytest game/tests.py` passes all model + code-generator tests.
- `DJANGO_DEBUG=True uv run python manage.py check` exits 0 (no system check errors).
- Smoke test still passes: `uv run pytest tests/test_smoke.py` exits 0.

#### Manual Verification:

- In `DJANGO_DEBUG=True uv run python manage.py shell`:
  - Import models, create `MusicSet`, `Track` (or reuse seeded data), `GameSession` with `code=generate_session_code()`.
  - Attach a `Player`, then attach a `Round` pointing at the `Track`.
  - Confirm `gs.players.all()` returns the player, `gs.rounds.all()` returns the round.
- In admin (`DJANGO_DEBUG=True uv run python manage.py createsuperuser` + `runserver`), inspect `Game sessions` list and confirm `list_display`, `list_filter`, `search_fields` render correctly.

**Implementation Note**: After Phase 2 passes, pause for manual confirmation that the shell session smoke-walk works before Phase 3.

---

## Phase 3: Cleanup management command

### Overview

Implement `python manage.py cleanup_sessions` that deletes sessions idle > 1 h. Provide `--dry-run` for safe inspection. Document how to wire this to a Fly scheduled machine (operational follow-up; not a code change).

### Changes Required:

#### 1. Management command

**File**: `game/management/__init__.py` (empty), `game/management/commands/__init__.py` (empty), `game/management/commands/cleanup_sessions.py` (new)

**Intent**: Delete every `GameSession` whose `last_activity_at` is more than `idle_hours` (default 1) old. Cascade removes `Player`s and `Round`s via `on_delete=CASCADE`. `--dry-run` prints what would be deleted without executing.

**Contract**:
- Subclass `django.core.management.base.BaseCommand`.
- `add_arguments` registers `--dry-run` (store_true) and `--idle-hours` (int, default 1).
- `handle` computes `cutoff = timezone.now() - timedelta(hours=idle_hours)`, filters `GameSession.objects.filter(last_activity_at__lt=cutoff)`, prints count + codes, then deletes unless `--dry-run`.
- Uses `self.stdout.write` (not `print`) for output; uses `self.style.WARNING` for the delete summary so it's visible in Fly logs.
- Logs through Python `logging.getLogger("game.cleanup")` so the cleanup is greppable in production logs.

#### 2. Tests for cleanup command

**File**: `game/tests.py` (append)

**Intent**: Verify dry-run leaves sessions intact, real run deletes only sessions past the cutoff, cascading drops related Players and Rounds.

**Contract**: Three test functions with `@pytest.mark.django_db`:
- `test_cleanup_dry_run_deletes_nothing`: create 1 session with `last_activity_at = timezone.now() - timedelta(hours=2)`, run `call_command("cleanup_sessions", "--dry-run")`, assert session still exists.
- `test_cleanup_deletes_idle_sessions`: same setup, run without flag, assert session and its Player/Round are gone.
- `test_cleanup_preserves_fresh_sessions`: create 1 session with `last_activity_at = timezone.now()`, run, assert session remains.

Each test patches `timezone.now()` via `freezegun` if available, OR (recommended) just sets `last_activity_at` explicitly on creation via `GameSession.objects.create(..., last_activity_at=...)` then calls the command — no time mocking needed.

#### 3. Operational doc

**File**: `context/changes/game-session-models/README.md` (new, inside change folder)

**Intent**: Short operational note covering: how to run cleanup manually (`uv run python manage.py cleanup_sessions`), how it's invoked in production (Fly scheduled machine, deferred to a deployment plan), and what the failure mode looks like.

**Contract**: ~30 lines. Three sections: "Manual run", "Production wiring (TODO)", "Failure modes". The "Production wiring" section explicitly notes that this change does NOT modify `fly.toml` or `.github/workflows/`; that wiring lands in a future deployment plan once F-04 and S-01 prove the model works on a real party.

### Success Criteria:

#### Automated Verification:

- `uv run pytest game/tests.py::test_cleanup_dry_run_deletes_nothing` passes.
- `uv run pytest game/tests.py::test_cleanup_deletes_idle_sessions` passes.
- `uv run pytest game/tests.py::test_cleanup_preserves_fresh_sessions` passes.
- `DJANGO_DEBUG=True uv run python manage.py cleanup_sessions --help` shows the help text including both flags.

#### Manual Verification:

- In shell: create one fresh session, one stale session (set `last_activity_at` manually to 2h ago). Run `cleanup_sessions --dry-run`. Verify both still exist and the stale one is reported. Run `cleanup_sessions` without `--dry-run`. Verify only the fresh one remains.
- Read `context/changes/game-session-models/README.md` and confirm the operational sections are accurate.

**Implementation Note**: After Phase 3 passes, the F-02 deliverable is complete. The Fly scheduled machine wiring is intentionally deferred — log a TODO in `context/foundation/roadmap.md` `## Open Roadmap Questions` if not already there, then `/10x-archive game-session-models`.

---

## Testing Strategy

### Unit Tests:

- Model field constraints (`unique_together`, FK protection, choices defaults).
- `generate_session_code()` happy path + retry path + exhaustion.
- Cleanup command: dry-run, real-run, fresh-preservation.

### Integration Tests:

- Smoke test (`tests/test_smoke.py`) confirms `pytest-django` wiring against the existing `catalog` app.
- Shell-driven walk-through (Phase 2 manual verification) acts as integration: create session → player → round → cleanup.

### Manual Testing Steps:

1. After Phase 1: run `uv run pytest`, see 1 passing test.
2. After Phase 2: run `manage.py shell`, create + inspect models; open admin and verify list views.
3. After Phase 3: run `cleanup_sessions --dry-run`, verify report; run without flag, verify deletion.

## Performance Considerations

- `GameSession.code` and `GameSession.last_activity_at` have `db_index=True` — cleanup query `filter(last_activity_at__lt=...)` is index-backed.
- `Player.session` and `Round.session` FK indexes are auto-generated by Django; default queryset on related-name (`gs.players.all()`) is index-backed.
- Code-collision retries: at <100 active sessions, collision probability per attempt < 1%; 10 attempts gives effective 100% success.
- Cleanup deletion at MVP scale (handful of sessions/day) is sub-millisecond; no batching needed.

## Migration Notes

- This is an additive migration; no data backfill required.
- Existing `db.sqlite3` (with seeded `catalog.MusicSet` / `catalog.Track`) is preserved.
- Rollback: `manage.py migrate game zero` drops the three tables. SQLite drops constraints with the tables.

## References

- Roadmap entry: `@context/foundation/roadmap.md` (F-02)
- Change identity: `@context/changes/game-session-models/change.md`
- GitHub issue: https://github.com/olsza-96/melo-gierka/issues/2
- Existing FK targets: `catalog/models.py:4-32`
- Settings (sessions middleware, BigAutoField default): `melo_gierka/settings.py:55-72, 128`
- PRD references: `@context/foundation/prd.md` §FR-002, FR-005, FR-006, FR-013, NFR §Sesja ulotna
- Lessons inherited: `@context/foundation/lessons.md` (no rules apply to this change)

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles.

### Phase 1: Test infrastructure

#### Automated

- [x] 1.1 `uv sync --dev` installs pytest, pytest-django, pytest-cov — a90557d
- [x] 1.2 `uv run pytest --collect-only` discovers `tests/test_smoke.py::test_music_set_round_trip` — a90557d
- [x] 1.3 `uv run pytest` exits 0 with 1 passing test — a90557d
- [x] 1.4 `uv run pytest --cov` reports coverage — a90557d
- [x] 1.5 `docker build .` exits 0; pytest not in production image — a90557d

#### Manual

- [x] 1.6 `pyproject.toml` `[dependency-groups] dev` + `[tool.pytest.ini_options]` readable — a90557d
- [x] 1.7 CLAUDE.md test-convention line reads naturally — a90557d

### Phase 2: Game app + models + migrations + code generator

#### Automated

- [x] 2.1 `manage.py makemigrations game --check --dry-run` reports no pending changes — 109d8e2
- [x] 2.2 `manage.py migrate game` applies cleanly on fresh DB — 109d8e2
- [x] 2.3 `uv run pytest game/tests.py` passes all model + codegen tests — 109d8e2
- [x] 2.4 `manage.py check` exits 0 — 109d8e2
- [x] 2.5 Smoke test still passes (`uv run pytest tests/test_smoke.py`) — 109d8e2

#### Manual

- [x] 2.6 Shell smoke-walk: GameSession + Player + Round round-trip — 109d8e2
- [x] 2.7 Admin list views render for all three models — 109d8e2

### Phase 3: Cleanup management command

#### Automated

- [ ] 3.1 `test_cleanup_dry_run_deletes_nothing` passes
- [ ] 3.2 `test_cleanup_deletes_idle_sessions` passes
- [ ] 3.3 `test_cleanup_preserves_fresh_sessions` passes
- [ ] 3.4 `cleanup_sessions --help` shows both flags

#### Manual

- [ ] 3.5 Two-session shell walk: dry-run preserves; real-run deletes only stale
- [ ] 3.6 `context/changes/game-session-models/README.md` operational note reads accurately
