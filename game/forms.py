from django import forms

from catalog.models import MusicSet


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