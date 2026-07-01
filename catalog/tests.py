import pytest
from django.core.management import call_command
from django.db.models import Count
from django.urls import reverse
import re

from catalog.models import MusicSet, Track
from game.forms import HostSessionCreateForm
from game.views import SPOTIFY_AUTH_SESSION_KEY, SPOTIFY_USER_SESSION_KEY


SPOTIFY_TRACK_ID_RE = re.compile(r"^[A-Za-z0-9]{22}$")
MIN_TRACKS_PER_SET = 10
MIN_DISTINCT_ARTISTS_PER_SET = 4

GENRE_GUARDRAILS = {
	"indie-mix": {
		"forbidden_artists": {
			"Billie Eilish",
			"Dua Lipa",
			"The Weeknd",
		},
	},
	"dance-hits": {
		"forbidden_artists": {
			"Arctic Monkeys",
			"The Strokes",
			"Tame Impala",
		},
	},
	"polish-hits": {
		"forbidden_artists": {
			"Calvin Harris",
			"Daft Punk",
			"David Guetta",
		},
	},
}


def _build_gate_compliant_catalog(*, tracks_per_set: int = 10, artist_pool: int = 10):
	"""Build deterministic in-memory catalog payload used by quality gate tests."""
	sets = []
	tracks = []
	pk = 1
	for set_idx in range(1, 6):
		sets.append({"pk": set_idx, "name": f"Set {set_idx}", "tracks": []})
		for track_idx in range(tracks_per_set):
			artist_idx = track_idx % artist_pool
			track = {
				"pk": pk,
				"music_set": set_idx,
				"spotify_track_id": f"A{set_idx:01d}{track_idx:020d}",
				"artist": f"Artist {artist_idx}",
				"title": f"Track {set_idx}-{track_idx}",
				"duration_ms": 180000,
			}
			sets[-1]["tracks"].append(track)
			tracks.append(track)
			pk += 1
	return sets, tracks


def _quality_gate_violations(sets):
	violations = []
	global_seen_ids = set()
	for music_set in sets:
		tracks = music_set["tracks"]
		if len(tracks) < MIN_TRACKS_PER_SET:
			violations.append(f"{music_set['name']}: track_count<{MIN_TRACKS_PER_SET}")

		distinct_artists = {track["artist"] for track in tracks}
		if len(distinct_artists) < MIN_DISTINCT_ARTISTS_PER_SET:
			violations.append(
				f"{music_set['name']}: distinct_artists<{MIN_DISTINCT_ARTISTS_PER_SET}"
			)

		seen_ids = set()
		for track in tracks:
			spotify_track_id = track["spotify_track_id"]
			if not SPOTIFY_TRACK_ID_RE.fullmatch(spotify_track_id):
				violations.append(f"{music_set['name']}: invalid_spotify_track_id={spotify_track_id}")
			if track["duration_ms"] < 90000:
				violations.append(f"{music_set['name']}: duration_below_floor={track['pk']}")
			if spotify_track_id in seen_ids:
				violations.append(f"{music_set['name']}: duplicate_spotify_track_id={spotify_track_id}")
			if spotify_track_id in global_seen_ids:
				violations.append(
					f"{music_set['name']}: duplicate_spotify_track_id_across_sets={spotify_track_id}"
				)
			seen_ids.add(spotify_track_id)
			global_seen_ids.add(spotify_track_id)

	return violations


def _genre_guardrail_violations(*, music_set_slug, artists):
	rules = GENRE_GUARDRAILS.get(music_set_slug)
	if not rules:
		return []

	violations = []
	forbidden = rules.get("forbidden_artists", set())
	found_forbidden = sorted(artists.intersection(forbidden))
	for artist in found_forbidden:
		violations.append(f"{music_set_slug}: forbidden_artist={artist}")

	return violations


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
	assert all(music_set.track_count >= MIN_TRACKS_PER_SET for music_set in music_sets)
	assert all(
		music_set.tracks.values("artist").distinct().count() >= MIN_DISTINCT_ARTISTS_PER_SET
		for music_set in music_sets
	)


@pytest.mark.django_db
def test_seeded_catalog_tracks_match_spotify_id_and_duration_quality_gates():
	call_command("seed_catalog")

	tracks = Track.objects.all()

	assert tracks.count() >= 50
	assert all(
		SPOTIFY_TRACK_ID_RE.fullmatch(track.spotify_track_id) is not None
		for track in tracks
	)
	assert all(track.duration_ms >= 90000 for track in tracks)


@pytest.mark.django_db
def test_seeded_catalog_has_no_cross_set_track_duplicates():
	call_command("seed_catalog")

	spotify_ids = list(Track.objects.values_list("spotify_track_id", flat=True))

	assert len(spotify_ids) == len(set(spotify_ids))


@pytest.mark.django_db
def test_seeded_catalog_respects_genre_guardrails():
	call_command("seed_catalog")

	violations = []
	for music_set in MusicSet.objects.prefetch_related("tracks"):
		artists = set(music_set.tracks.values_list("artist", flat=True))
		violations.extend(
			_genre_guardrail_violations(music_set_slug=music_set.slug, artists=artists)
		)

	assert violations == []


@pytest.mark.django_db
def test_seed_catalog_is_idempotent_for_counts_and_per_set_uniqueness():
	call_command("seed_catalog")
	first_track_count = Track.objects.count()

	call_command("seed_catalog")

	assert MusicSet.objects.count() == 5
	assert Track.objects.count() == first_track_count

	music_sets = MusicSet.objects.all()
	for music_set in music_sets:
		spotify_ids = list(music_set.tracks.values_list("spotify_track_id", flat=True))
		assert len(spotify_ids) == len(set(spotify_ids))


def test_catalog_quality_gates_pass_for_gate_compliant_catalog_payload():
	sets, _tracks = _build_gate_compliant_catalog()

	assert _quality_gate_violations(sets) == []


def test_catalog_quality_gate_detects_invalid_spotify_track_id():
	sets, _tracks = _build_gate_compliant_catalog()
	sets[0]["tracks"][0]["spotify_track_id"] = "bad-id"

	violations = _quality_gate_violations(sets)

	assert any("invalid_spotify_track_id" in violation for violation in violations)


def test_catalog_quality_gate_detects_duration_floor_violation():
	sets, _tracks = _build_gate_compliant_catalog()
	sets[1]["tracks"][0]["duration_ms"] = 89000

	violations = _quality_gate_violations(sets)

	assert any("duration_below_floor" in violation for violation in violations)


def test_catalog_quality_gate_detects_low_artist_diversity():
	sets, _tracks = _build_gate_compliant_catalog(artist_pool=2)

	violations = _quality_gate_violations(sets)

	assert any(
		f"distinct_artists<{MIN_DISTINCT_ARTISTS_PER_SET}" in violation
		for violation in violations
	)


def test_catalog_quality_gate_detects_duplicate_spotify_track_id_in_set():
	sets, _tracks = _build_gate_compliant_catalog()
	sets[2]["tracks"][1]["spotify_track_id"] = sets[2]["tracks"][0]["spotify_track_id"]

	violations = _quality_gate_violations(sets)

	assert any("duplicate_spotify_track_id" in violation for violation in violations)


def test_catalog_quality_gate_detects_duplicate_spotify_track_id_across_sets():
	sets, _tracks = _build_gate_compliant_catalog()
	sets[1]["tracks"][0]["spotify_track_id"] = sets[0]["tracks"][0]["spotify_track_id"]

	violations = _quality_gate_violations(sets)

	assert any(
		"duplicate_spotify_track_id_across_sets" in violation for violation in violations
	)
