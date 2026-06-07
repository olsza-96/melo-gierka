import pytest
from django.core.management import call_command
from django.db.models import Count
from django.urls import reverse

from catalog.models import MusicSet, Track
from game.forms import HostSessionCreateForm
from game.views import SPOTIFY_AUTH_SESSION_KEY, SPOTIFY_USER_SESSION_KEY


@pytest.mark.django_db
def test_index_renders_signed_out_landing_page(client):
	response = client.get(reverse("catalog:index"))

	content = response.content.decode()
	assert response.status_code == 200
	assert "text/html" in response.headers["Content-Type"]
	assert "Log in with Spotify" in content
	assert reverse("game_host:spotify-login") in content
	assert "Join a game" in content
	assert "melo-gierka is up" not in content
	assert reverse("game_host:player-join") in content


@pytest.mark.django_db
def test_index_renders_player_join_cta(client):
	response = client.get(reverse("catalog:index"))

	content = response.content.decode()
	assert response.status_code == 200
	assert "Open player join" in content
	assert reverse("game_host:player-join") in content


@pytest.mark.django_db
def test_index_renders_signed_in_host_create_form(client):
	set_names = [
		"Dance Floor Hits",
		"Indie Mix",
		"Polish Hits",
		"Pop Hits 2010s",
		"Rock Classics",
	]
	for index, name in enumerate(set_names):
		MusicSet.objects.create(slug=f"set-{index}", name=name)

	session = client.session
	session[SPOTIFY_AUTH_SESSION_KEY] = {"access_token": "access-token"}
	session[SPOTIFY_USER_SESSION_KEY] = {"display_name": "Host User"}
	session.save()

	response = client.get(reverse("catalog:index"))

	content = response.content.decode()
	assert response.status_code == 200
	assert "Host User" in content
	assert "Create your session" in content
	assert "Create session" in content
	assert "Create session in Phase 3" not in content
	assert reverse("game_host:session-create") in content
	for name in set_names:
		assert name in content
	assert reverse("game_host:spotify-logout") in content


@pytest.mark.django_db
def test_host_create_form_uses_music_sets_as_choices():
	MusicSet.objects.create(slug="rock", name="Rock Classics")
	MusicSet.objects.create(slug="pop", name="Pop Hits 2010s")

	form = HostSessionCreateForm()

	assert list(form.fields["music_set"].queryset.values_list("name", flat=True)) == [
		"Pop Hits 2010s",
		"Rock Classics",
	]


@pytest.mark.django_db
def test_seed_catalog_loads_five_music_sets_with_tracks():
	call_command("seed_catalog")

	assert MusicSet.objects.count() == 5
	assert Track.objects.count() >= 50


@pytest.mark.django_db
def test_catalog_capacity_supports_ten_round_sessions_after_seed():
	call_command("seed_catalog")

	music_sets = MusicSet.objects.annotate(track_count=Count("tracks")).order_by("name")

	assert music_sets.count() == 5
	assert all(music_set.track_count >= 10 for music_set in music_sets)
	assert all(
		music_set.tracks.values("artist").distinct().count() >= 4
		for music_set in music_sets
	)
