<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Host Creates Session (S-01)

- **Plan**: context/changes/host-creates-session/plan.md
- **Scope**: All phases (1–4 of 4)
- **Date**: 2026-06-04
- **Verdict**: APPROVED (post-fix)
- **Findings**: 1 critical (fixed) | 1 warning (fixed) | 2 observations (accepted)

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | WARNING |
| Safety & Quality | PASS |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

## Automated Verification

| Check | Command | Result |
|-------|---------|--------|
| 1.1 | `pytest -k "spotify or oauth or callback"` | ✅ 6/6 passed |
| 1.2 | `manage.py check` | ✅ 0 issues |
| 2.1 | `pytest -k "index or landing or host_create"` | ✅ 3/3 passed |
| 2.2 | `collectstatic --noinput` | ✅ 128 files copied |
| 3.1 | `pytest -k "session_create or host_lobby or host_owner or music_set_edit"` | ✅ 7/7 passed |
| 3.2 | `manage.py check` | ✅ 0 issues |
| 4.1 | `pytest -k "oauth or host_lobby or music_set_edit"` | ✅ 4/4 passed |
| 4.2 | `pytest tests/test_smoke.py game/tests.py` | ✅ 34/34 passed |

Manual: all 15 plan criteria marked `[x]` in Progress. Items 4.4 (Fly smoke) and 4.5 (smoke checklist) taken at face value as human-confirmed.

## Findings

### F1 — Timing-unsafe OAuth state comparison

- **Severity**: ❌ CRITICAL
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: game/views.py:118
- **Detail**: The PKCE `state` parameter is validated with `state != expected_state`, a plain Python string equality check with early-exit semantics. For any CSRF-token/secret comparison, `hmac.compare_digest()` is the OWASP-recommended constant-time approach.
- **Fix**:
  ```python
  import hmac
  if not expected_state or not code_verifier or not code or \
          not hmac.compare_digest(state or "", expected_state):
  ```
- **Decision**: FIXED — applied `hmac.compare_digest()` in `spotify_callback`

### F2 — Session fixation: session key not cycled after OAuth

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: game/views.py:142 (`_ensure_session_key` call at end of `spotify_callback`)
- **Detail**: After the OAuth callback establishes host auth state, `_ensure_session_key(request)` only saves the session if no key exists yet — it does not cycle the session key. A host with a pre-existing anonymous session retains the same session ID post-authentication, enabling a classic session fixation attack. Django's `request.session.cycle_key()` is the canonical mitigation for privilege escalation.
- **Fix A ⭐ Recommended**: Replace `_ensure_session_key(request)` with `request.session.cycle_key()` in the success branch of `spotify_callback`.
  - Strength: Django's built-in method for privilege escalation — new key, retained data, old entry deleted.
  - Tradeoff: Pre-existing anonymous sessions (unlikely here) are invalidated.
  - Confidence: HIGH — Django docs prescribe exactly this pattern on login.
  - Blind spot: The `_ensure_session_key()` call in `session_create` is unaffected — host is already authenticated there, no privilege change.
- **Fix B**: Keep `_ensure_session_key()` and add `cycle_key()` immediately after.
  - Strength: Preserves existing logic while adding the protection.
  - Tradeoff: Redundant; `_ensure_session_key` becomes a no-op on the happy path.
  - Confidence: MEDIUM.
  - Blind spot: None significant.
- **Decision**: FIXED — replaced `_ensure_session_key(request)` with `request.session.cycle_key()` in success branch of `spotify_callback`

### F3 — .dockerignore tightened but not mentioned in plan

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Scope Discipline
- **Location**: .dockerignore
- **Detail**: `.env` and `.env.*` added to `.dockerignore`. Security-positive change (prevents local secrets from leaking into Docker build context). Not listed in any phase's "Changes Required".
- **Fix**: Append a one-line addendum to `context/changes/host-creates-session/plan.md` noting this as discovered-scope. No code change needed.
- **Decision**: ACCEPTED — security-positive, no action required

### F4 — catalog/tests.py not listed in Phase 2 "Changes Required"

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Scope Discipline
- **Location**: catalog/tests.py
- **Detail**: Phase 2 success criteria require `pytest catalog/tests.py` landing-page tests to pass (criterion 2.1), but `catalog/tests.py` is absent from Phase 2's "Changes Required" file list. Three new passing tests were correctly added. Planning gap only.
- **Fix**: Add `catalog/tests.py` to Phase 2 "Changes Required" as a plan addendum. No code change needed.
- **Decision**: ACCEPTED — planning gap only, tests are correct
