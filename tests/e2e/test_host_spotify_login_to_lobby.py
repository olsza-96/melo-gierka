import os
import re
import time

import pytest

from catalog.models import MusicSet
from game.models import GameSession

pytest.importorskip("pytest_playwright")

# Playwright's pytest plugin can run with an active event loop during fixture setup.
# Allow Django DB operations in this controlled test context.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


@pytest.mark.django_db(transaction=True)
def test_host_can_log_in_create_session_and_reach_lobby(page, live_server, monkeypatch, settings):
    """Critical host path: Spotify login -> create session -> host lobby."""
    run_id = str(time.time_ns())

    settings.SPOTIFY_CLIENT_ID = "e2e-client-id"
    settings.SPOTIFY_CLIENT_SECRET = "e2e-client-secret"
    settings.SPOTIFY_SCOPE = "user-read-email user-read-private"

    fake_token_payload = {
        "access_token": "e2e-access-token",
        "refresh_token": "e2e-refresh-token",
        "scope": settings.SPOTIFY_SCOPE,
        "expires_at": int(time.time()) + 3600,
    }
    fake_profile = {
        "display_name": f"E2E Host {run_id[-6:]}",
        "product": "premium",
    }

    monkeypatch.setattr("game.spotify_auth.generate_oauth_state", lambda: f"e2e-state-{run_id}")
    monkeypatch.setattr("game.spotify_auth.generate_code_verifier", lambda: f"e2e-verifier-{run_id}")

    def _fake_build_authorize_url(*, state, **_kwargs):
        return f"{live_server.url}/oauth/spotify/callback?code=e2e-code&state={state}"

    monkeypatch.setattr("game.spotify_auth.build_authorize_url", _fake_build_authorize_url)
    monkeypatch.setattr(
        "game.spotify_auth.exchange_code_for_token",
        lambda **_kwargs: fake_token_payload,
    )
    monkeypatch.setattr(
        "game.spotify_auth.fetch_user_profile",
        lambda _access_token: fake_profile,
    )

    music_set = MusicSet.objects.create(
        slug=f"e2e-host-flow-{run_id}",
        name=f"E2E Host Set {run_id[-6:]}",
        description="Music set used by host e2e flow.",
    )

    page.goto(f"{live_server.url}/")
    page.get_by_role("link", name="Log in with Spotify").click()

    page.wait_for_url(re.compile(r".*/$"))
    page.get_by_text("Signed in as").wait_for()
    page.locator(".host-status-name").get_by_text(fake_profile["display_name"], exact=True).wait_for()

    page.select_option("select[name='music_set']", str(music_set.pk))
    page.get_by_role("button", name="Create session").click()

    page.wait_for_url(re.compile(r".*/host/sessions/\d{4}$"))
    page.get_by_role("heading", name="Your room is live.").wait_for()

    session_code = page.locator(".session-code-value").inner_text().strip()
    assert re.fullmatch(r"\d{4}", session_code)
    assert GameSession.objects.filter(code=session_code, music_set=music_set).exists()
