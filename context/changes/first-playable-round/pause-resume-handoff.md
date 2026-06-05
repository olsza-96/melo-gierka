# Pause/Resume Debug Handoff

Date: 2026-06-05
Change: `first-playable-round` (S-03, phase 3 manual verification)
Status: resolved

## Resolution

Resolved during the resumed debugging pass on 2026-06-05.

Fix summary:

- pause/resume now refresh and, when needed, reselect the active commandable Spotify device before host controls run
- Spotify pause/resume network calls were moved outside `transaction.atomic()` to avoid SQLite `database is locked` failures during polling
- resume now treats `transfer_playback(play=True)` plus active-device verification as sufficient, avoiding a redundant `/me/player/play` call that could fail after audio had already resumed

Verification after the fix:

- `DJANGO_DEBUG=True uv run pytest game/tests.py -k "pause or resume or skip or restart or state or etag"` -> 27 passed
- `DJANGO_DEBUG=True uv run pytest game/tests.py` -> 83 passed
- `DJANGO_DEBUG=True uv run python manage.py check` -> no issues
- manual host test confirmed pause works, resume continues playback, and host/player round state leaves `Paused`

## Historical issue

The host round control flow was unstable in manual testing before the resolution above.

Latest user-visible failure:

- pressing `Pause` can return the host-visible error: `Spotify playback could not be paused on the active browser device.`

Other failures observed during this debugging session:

- Spotify audio paused but the countdown kept running
- `Resume` stayed disabled after a pause
- `Resume` sometimes worked once, but a second `Pause` failed
- after `Resume`, the page could snap back to `Paused` instead of returning to the live countdown

## What is already verified

- Focused automated tests are green throughout the debugging work:
  - `DJANGO_DEBUG=True uv run pytest game/tests.py -k "pause or resume or skip or restart"`
  - later widened to include state checks during countdown debugging:
    - `DJANGO_DEBUG=True uv run pytest game/tests.py -k "pause or resume or skip or restart or state or etag"`
- The mocked backend sequence `pause -> resume -> pause` is covered in tests and passes.
- The remaining failure appears to depend on the real browser + Spotify device state, not on the basic Django round-state mutation path under mocks.

## Historical diagnosis

The unresolved problem was probably on the real Spotify device/control boundary rather than the persisted Django round state.

Reasons:

- tests that mock Spotify pass consistently
- round state mutations (`paused_at`, `deadline_at`) have been exercised repeatedly in tests without failure
- the latest concrete manual error is Spotify-specific: `Spotify playback could not be paused on the active browser device.`

That suggests the persisted `device_id` / browser playback readiness / actual active Spotify device can drift over time in ways the mocked tests do not model.

## What was tried

The following fixes were attempted during this session.

### 1. Spotify pause/resume endpoints were implemented

- added Spotify helper methods in `game/spotify_auth.py`
- wired `session_pause` / `session_resume` in `game/views.py`
- goal: make pause/resume actually control Spotify, not only Django round state

### 2. Countdown was changed to derive locally between polls

- updated `game/static/game/round.js`
- goal: stop the timer freezing on unchanged `ETag` / `304` state polls

### 3. Host control buttons got in-flight guards

- added client-side request locking in `game/static/game/round.js`
- goal: prevent overlapping pause clicks from racing each other

### 4. Forced fresh snapshot refresh after control actions

- added a manual refresh path in the poller
- tried optimistic local state changes after successful `pause` / `resume`
- goal: make the UI stop relying on the next ordinary poll to update phase

### 5. Stale poll response guards were added

- guarded against older in-flight poll responses overwriting newer control mutations
- goal: stop the page from snapping from `paused` back to `active`, or from `active` back to `paused`

### 6. Resume flow was aligned with start-playback device activation

- added `_resume_round_playback(...)` in `game/views.py`
- reused `transfer_playback(..., play=True)` and `_wait_for_active_playback_device(...)`
- goal: ensure `Resume` re-activates the correct Spotify device before issuing the playback command

### 7. Pause/resume responses were changed to return authoritative snapshots

- `session_pause` and `session_resume` were updated to return `snapshot` payloads
- `game/static/game/round.js` was updated to prefer those authoritative snapshots over local guesses
- goal: render exact server phase after each control action

### 8. Host controls were switched to full page resync after success

- successful host control actions were changed to force a fresh page load
- goal: avoid trying to keep a long-lived host page perfectly in sync after each action

### 9. Host controls were moved off normal fetch flow for browser use

- `game/templates/game/host_round.html` now renders host controls as real POST form submissions
- `game/views.py` was updated so host control endpoints:
  - return JSON for explicit fetch callers
  - redirect back to the host page for normal browser form posts
- `game/static/game/round.js` was updated to skip fetch binding for form-backed host control buttons
- goal: reduce client-side state drift by re-entering through fresh server-rendered host pages after every host action

### 10. Regression coverage was extended

- `game/tests.py` now includes repeated control coverage, especially `pause -> resume -> pause`
- tests assert pause/resume snapshots and repeated pauseability under mocked Spotify calls

## Files touched during debugging

These are the primary files involved in the pause/resume investigation:

- `game/views.py`
- `game/static/game/round.js`
- `game/templates/game/host_round.html`
- `game/templates/game/player_round.html`
- `game/tests.py`

Earlier related changes also touched:

- `game/spotify_auth.py`
- `game/state.py`
- `game/api_urls.py`

Current diff summary for the most relevant files at the time this note was written:

- `game/views.py`: heavy pause/resume/control flow changes
- `game/static/game/round.js`: heavy polling/state/control changes
- `game/tests.py`: extensive control/regression additions
- `game/templates/game/host_round.html`: host controls changed to form posts
- `game/templates/game/player_round.html`: asset version bumps during debugging

## Worktree note at pause time

At the time of writing, there are uncommitted changes in the worktree, including the files above. The repo also has unrelated dirty/untracked files, so any later cleanup or commit should be selective.

## Original next step before resolution

Do not start by changing the timer or round.js again.

The next debugging pass should instrument the real Spotify/device path around host controls and capture the actual Spotify-side failure details for a manual `pause -> resume -> pause` sequence.

Most useful places to inspect/log next:

- `game/views.py`
  - `_host_playback_device_for_round_control(...)`
  - `session_pause(...)`
  - `session_resume(...)`
  - `_resume_round_playback(...)`
- `game/spotify_auth.py`
  - `pause_playback(...)`
  - `resume_playback(...)`
  - `transfer_playback(...)`
  - `fetch_available_devices(...)`

Specifically capture on real failures:

- persisted playback state from `request.session[SPOTIFY_PLAYBACK_SESSION_KEY]`
- chosen `device_id`
- Spotify available devices snapshot before the failing pause
- `SpotifyOAuthError.status_code`
- `SpotifyOAuthError.response_body`

The most likely question to answer next time is:

`Is the stored browser device still the active/commandable Spotify device by the time the second pause is attempted?`

If not, the real fix is probably in device-state refresh/reselection before pause, not in more client-side countdown logic.