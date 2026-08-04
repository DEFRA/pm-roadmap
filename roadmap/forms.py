"""Forms for the standalone OKR + team pages.

Ported from myproduct.pro, stripped of authentication: there is no user owner,
no premium gate, and no membership scoping. Objectives are attached to a
first-class Team (a dropdown) rather than resolved from the current user.
"""
from django import forms
from django.forms import inlineformset_factory

from .models import Objective, ObjectiveSet, KeyResult, Team, Organisation, Roadmap
from . import okr_periods


class TeamRoadmapForm(forms.ModelForm):
    """Minimal form to create a roadmap owned by a team (from the team page)."""
    class Meta:
        model = Roadmap
        fields = ['name', 'roadmap_type']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Licensing Service Roadmap'}),
            'roadmap_type': forms.Select(attrs={'class': 'form-input'}),
        }


class TeamForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ['organisation', 'name']
        widgets = {
            'organisation': forms.Select(attrs={'class': 'form-input'}),
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Licensing'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # An org might not exist yet — let the user proceed without picking one.
        # A team with no org chosen is linked to a background "No org" placeholder
        # (see save). Eventually org creation will be required up front.
        self.fields['organisation'].required = False
        self.fields['organisation'].empty_label = "My organisation isn't listed yet"

    def save(self, commit=True):
        team = super().save(commit=False)
        if team.organisation_id is None:
            team.organisation = Organisation.objects.get_or_create(
                name='No org',
                defaults={'description': "Placeholder for teams whose organisation "
                                         "has not been created yet."},
            )[0]
        if commit:
            team.save()
        return team


class ObjectiveSetForm(forms.ModelForm):
    """Create/edit an OKR set's name + timeframe. Organisation, scope and team are
    not asked for here — a set is always created from (and owned by) a team, so the
    view sets them from the team in the URL."""
    period_preset = forms.ChoiceField(label='Timeframe', widget=forms.RadioSelect)

    class Meta:
        model = ObjectiveSet
        fields = ['name', 'start_date', 'end_date']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. FY26 Q1'}),
            'start_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
        }

    def __init__(self, *args, today=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._today = today
        self.fields['name'].required = False
        self.fields['start_date'].required = False
        self.fields['end_date'].required = False

        labelled = []
        for key, label in okr_periods.PRESET_CHOICES:
            if key == okr_periods.WINDOW_CUSTOM:
                labelled.append((key, label))
            else:
                _p, start, end, _name = okr_periods.resolve_preset(key, today=today)
                labelled.append((key, f'{label} ({start:%d %b %Y} – {end:%d %b %Y})'))
        self.fields['period_preset'].choices = labelled

        if not self.is_bound and self.instance and self.instance.pk:
            self.fields['period_preset'].initial = okr_periods.detect_preset(
                self.instance.period, self.instance.start_date, self.instance.end_date, today=today,
            )
        elif not self.is_bound:
            self.fields['period_preset'].initial = okr_periods.WINDOW_CURRENT_QUARTER

    def clean(self):
        cleaned = super().clean()
        preset = cleaned.get('period_preset') or okr_periods.WINDOW_CUSTOM
        name = (cleaned.get('name') or '').strip()
        if preset != okr_periods.WINDOW_CUSTOM:
            period, start, end, suggested = okr_periods.resolve_preset(preset, today=self._today)
            cleaned['period'] = period
            cleaned['start_date'] = start
            cleaned['end_date'] = end
            if not name and suggested:
                name = suggested
        else:
            cleaned['period'] = None
            start, end = cleaned.get('start_date'), cleaned.get('end_date')
            if start and end and end < start:
                self.add_error('end_date', 'End date must be after the start date.')
        if not name:
            self.add_error('name', 'This field is required.')
        else:
            cleaned['name'] = name
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.period = self.cleaned_data.get('period')
        if commit:
            instance.save()
        return instance


def set_form_seed(form):
    """Data for the timeframe preset cards + conditional date inputs on
    objective_set_form.html. Serialised to the page via json_script."""
    presets = []
    for key, label in okr_periods.PRESET_CHOICES:
        if key == okr_periods.WINDOW_CUSTOM:
            presets.append({'key': key, 'title': label, 'range': '', 'wide': True,
                            'start': '', 'end': '', 'suggestedName': ''})
        else:
            _p, start, end, suggested = okr_periods.resolve_preset(key)
            presets.append({'key': key, 'title': label, 'range': f'{start:%b} – {end:%b %Y}',
                            'wide': False, 'start': start.isoformat(), 'end': end.isoformat(),
                            'suggestedName': suggested})

    def iso(value):
        if not value:
            return ''
        return value.isoformat() if hasattr(value, 'isoformat') else str(value)

    return {
        'presets': presets,
        'preset': form['period_preset'].value() or okr_periods.WINDOW_CUSTOM,
        'name': form['name'].value() or '',
        'startDate': iso(form['start_date'].value()),
        'endDate': iso(form['end_date'].value()),
    }


class ObjectiveForm(forms.ModelForm):
    class Meta:
        model = Objective
        fields = ['objective_set', 'team', 'title', 'description']
        widgets = {
            'objective_set': forms.Select(attrs={'class': 'form-input'}),
            'team': forms.Select(attrs={'class': 'form-input'}),
            'title': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Objective title'}),
            'description': forms.Textarea(attrs={'class': 'form-input', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['objective_set'].queryset = ObjectiveSet.objects.filter(archived=False)
        self.fields['objective_set'].required = False
        self.fields['objective_set'].label = 'Set'
        self.fields['objective_set'].empty_label = 'No set'
        self.fields['team'].required = False
        self.fields['team'].empty_label = 'No team'


class KeyResultForm(forms.ModelForm):
    class Meta:
        model = KeyResult
        fields = ['title', 'unit', 'start_value', 'target_value', 'current_value', 'direction', 'status']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Key result'}),
            'unit': forms.TextInput(attrs={'class': 'form-input', 'placeholder': '%, £, users'}),
            'start_value': forms.NumberInput(attrs={'class': 'form-input'}),
            'target_value': forms.NumberInput(attrs={'class': 'form-input'}),
            'current_value': forms.NumberInput(attrs={'class': 'form-input'}),
            'direction': forms.Select(attrs={'class': 'form-input'}),
            'status': forms.Select(attrs={'class': 'form-input'}),
        }

    def clean(self):
        """Target must sit on the side the direction claims (equal start/target is
        a legitimate "maintain this level" key result and is left alone)."""
        cleaned = super().clean()
        direction = cleaned.get('direction')
        start = cleaned.get('start_value')
        target = cleaned.get('target_value')
        if direction and start is not None and target is not None:
            if direction == KeyResult.INCREASE and target < start:
                self.add_error('target_value', 'Target must be above the start value when higher is better.')
            elif direction == KeyResult.DECREASE and target > start:
                self.add_error('target_value', 'Target must be below the start value when lower is better.')
        return cleaned


KeyResultFormSet = inlineformset_factory(
    Objective, KeyResult, form=KeyResultForm, extra=1, can_delete=True,
)
