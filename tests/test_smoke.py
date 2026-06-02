import pytest

from catalog.models import MusicSet


@pytest.mark.django_db
def test_music_set_round_trip():
    music_set = MusicSet.objects.create(slug="smoke", name="Smoke Test Set")
    assert music_set.pk is not None
    assert MusicSet.objects.get(pk=music_set.pk).slug == "smoke"
