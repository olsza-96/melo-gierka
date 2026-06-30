import os
import re
import time

import pytest

from catalog.models import MusicSet
from game.models import GameSession, Player

pytest.importorskip("pytest_playwright")

# Playwright's pytest plugin can run with an active event loop during fixture setup.
# Allow Django DB operations in this controlled test context.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


@pytest.mark.django_db(transaction=True)
def test_player_can_join_lobby_with_valid_code(page, live_server):
    """Critical path: a player joins a live lobby and lands in the correct room."""
    run_id = str(time.time_ns())
    unique_code = run_id[-4:]
    unique_player_name = f"Alice-{run_id[-6:]}"

    music_set = MusicSet.objects.create(
        slug=f"e2e-set-{run_id}",
        name=f"E2E Set {run_id[-6:]}",
        description="Seed set for e2e player-join flow.",
    )
    session = GameSession.objects.create(
        code=unique_code,
        music_set=music_set,
        host_session_key="h" * 40,
        status=GameSession.Status.LOBBY,
    )

    page.goto(f"{live_server.url}/player/join")

    page.get_by_label("Session code").fill(session.code)
    page.get_by_label("Your name").fill(unique_player_name)
    page.get_by_role("button", name="Join lobby").click()

    expect_url = re.compile(rf".*/player/sessions/{unique_code}$")
    page.wait_for_url(expect_url)

    page.get_by_role("heading", name="You are in the lobby.").wait_for()
    page.get_by_text(f"Joined as {unique_player_name}.").wait_for()
    page.get_by_text("Session code").wait_for()

    assert Player.objects.filter(session=session, name=unique_player_name).exists()
