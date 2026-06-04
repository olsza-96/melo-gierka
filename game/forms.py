from django import forms

from catalog.models import MusicSet
from game.models import GameSession, Player


class HostSessionCreateForm(forms.Form):
    music_set = forms.ModelChoiceField(
        queryset=MusicSet.objects.none(),
        empty_label=None,
        label="Music set",
        help_text="Choose one of the current seeded sets for the next party round.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["music_set"].queryset = MusicSet.objects.order_by("name")


class PlayerJoinForm(forms.Form):
    code = forms.RegexField(
        regex=r"^\d{4}$",
        max_length=4,
        min_length=4,
        label="Session code",
        error_messages={
            "invalid": "Enter a valid 4-digit session code.",
        },
    )
    name = forms.CharField(
        max_length=Player._meta.get_field("name").max_length,
        label="Your name",
        help_text="Use a unique name within this session.",
        strip=True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = None
        self.suggested_name = None

    def clean_name(self):
        name = (self.cleaned_data["name"] or "").strip()
        if not name:
            raise forms.ValidationError("Enter your name.")
        return name

    def clean(self):
        cleaned_data = super().clean()
        if self.errors:
            return cleaned_data

        code = cleaned_data.get("code")
        name = cleaned_data.get("name")
        if not code or not name:
            return cleaned_data

        session = GameSession.objects.filter(code=code).first()
        if session is None:
            self.add_error("code", "Enter a valid session code.")
            return cleaned_data

        if session.status != GameSession.Status.LOBBY:
            self.add_error("code", "This session is no longer accepting players.")
            return cleaned_data

        if Player.objects.filter(session=session, name=name).exists():
            suggestion = build_player_name_suggestion(session=session, base_name=name)
            self.suggested_name = suggestion
            self.add_error(
                "name",
                f'That name is already taken in this session. Try "{self.suggested_name}".',
            )
            return cleaned_data

        self.session = session
        cleaned_data["session"] = session
        return cleaned_data


def build_player_name_suggestion(*, session: GameSession, base_name: str) -> str:
    suffix = 2
    while True:
        candidate = _candidate_name(base_name=base_name, suffix=suffix)
        if not Player.objects.filter(session=session, name=candidate).exists():
            return candidate
        suffix += 1


def _candidate_name(*, base_name: str, suffix: int) -> str:
    suffix_text = f" {suffix}"
    max_length = Player._meta.get_field("name").max_length
    trimmed_name = base_name[: max_length - len(suffix_text)].rstrip()
    if not trimmed_name:
        trimmed_name = "Player"
    return f"{trimmed_name}{suffix_text}"