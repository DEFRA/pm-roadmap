"""Forms for the standalone OKR + team pages.

Ported from myproduct.pro, stripped of authentication: there is no user owner,
no premium gate, and no membership scoping. Objectives are attached to a
first-class Team (a dropdown) rather than resolved from the current user.
"""
from django import forms
from django.db.models import Q
from django.forms import inlineformset_factory

from .models import (
    Objective, ObjectiveSet, KeyResult, Team, Organisation, Roadmap,
    Experiment, ProductRequirement,
)
from . import okr_periods


class TeamRoadmapForm(forms.ModelForm):
    """Minimal form to create a roadmap owned by a team (from the team page)."""
    class Meta:
        model = Roadmap
        fields = ['name', 'roadmap_type', 'sync_okrs']
        labels = {
            'sync_okrs': "Sync this team's objectives and key results onto the roadmap",
        }
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
    # Team is not asked for — an objective inherits its set's team (set in the view).
    # When authoring under a set, an existing team objective can be reused instead
    # of creating a new one (durable objectives, B2) — its new key results attach
    # to this set's period. Enabled by passing `team=` (create-under-a-set only).
    existing_objective = forms.ModelChoiceField(
        queryset=Objective.objects.none(), required=False,
        widget=forms.Select(attrs={'class': 'form-input'}),
        label='Reuse an existing objective',
        empty_label='— create a new objective —',
    )

    class Meta:
        model = Objective
        fields = ['sets', 'title', 'description']
        widgets = {
            'sets': forms.CheckboxSelectMultiple(),
            'title': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Objective title'}),
            'description': forms.Textarea(attrs={'class': 'form-input', 'rows': 2}),
        }

    def __init__(self, *args, team=None, default_set=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Set membership is multi-select: a durable objective can belong to several
        # sets (periods) at once. Scope the choices to the objective's own team —
        # keeping any sets it is already a member of visible, so editing never drops
        # an existing (maybe archived) membership.
        sets_field = self.fields['sets']
        sets_field.required = False
        sets_field.label = 'Sets'
        owning_team = (self.instance.team if (self.instance and self.instance.pk) else None) or team
        if owning_team is not None:
            allowed = Q(scope=ObjectiveSet.TEAM, team=owning_team, archived=False)
            if self.instance and self.instance.pk:
                allowed |= Q(member_objectives=self.instance)
            sets_field.queryset = ObjectiveSet.objects.filter(allowed).distinct()
        else:
            sets_field.queryset = ObjectiveSet.objects.filter(archived=False)
        sets_field.label_from_instance = _set_choice_label
        # A brand-new objective authored under a set starts a member of that set.
        if default_set is not None and not (self.instance and self.instance.pk):
            sets_field.initial = [default_set.pk]
        self.allow_reuse = team is not None
        if self.allow_reuse:
            qs = Objective.objects.filter(team=team, archived=False).select_related('objective_set')
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            field = self.fields['existing_objective']
            field.queryset = qs
            # Show the objective's primary set in brackets so same-named objectives
            # across quarters can be told apart, e.g. "obj 1 (2026 Q3)".
            field.label_from_instance = lambda o: (
                f'{o.title} ({o.objective_set.name})' if o.objective_set_id else o.title
            )
            self.fields['title'].required = False  # optional: pick existing OR name a new one

    def clean(self):
        cleaned = super().clean()
        if self.allow_reuse and not cleaned.get('existing_objective') \
                and not (cleaned.get('title') or '').strip():
            self.add_error('title', 'Enter a title, or pick an existing objective to reuse.')
        return cleaned


def _set_choice_label(s):
    """Dropdown label for a set — name plus its timeframe so periods are obvious."""
    if s.start_date and s.end_date:
        return f'{s.name} ({s.start_date:%b %Y}–{s.end_date:%b %Y})'
    return s.name


class KeyResultForm(forms.ModelForm):
    class Meta:
        model = KeyResult
        fields = ['objective_set', 'start_date', 'end_date', 'title', 'unit',
                  'start_value', 'target_value', 'current_value', 'direction', 'status', 'archived']
        widgets = {
            'objective_set': forms.Select(attrs={'class': 'form-input'}),
            'start_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}, format='%Y-%m-%d'),
            'end_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}, format='%Y-%m-%d'),
            'title': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Key result'}),
            'unit': forms.TextInput(attrs={'class': 'form-input', 'placeholder': '%, £, users'}),
            'start_value': forms.NumberInput(attrs={'class': 'form-input'}),
            'target_value': forms.NumberInput(attrs={'class': 'form-input'}),
            'current_value': forms.NumberInput(attrs={'class': 'form-input'}),
            'direction': forms.Select(attrs={'class': 'form-input'}),
            'status': forms.Select(attrs={'class': 'form-input'}),
        }

    def __init__(self, *args, team=None, default_set=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Each key result carries its own period (set), so one durable objective can
        # hold different KRs set-to-set. Scope the picker to the objective's team —
        # a KR's period must be one of that team's sets — but keep the KR's current
        # set selectable so an existing KR never loses its (maybe archived) period.
        field = self.fields['objective_set']
        field.required = False
        field.label = 'Set / timeframe'
        field.empty_label = 'No set (use own dates)'
        if team is not None:
            allowed = Q(scope=ObjectiveSet.TEAM, team=team, archived=False)
            if self.instance and self.instance.objective_set_id:
                allowed |= Q(pk=self.instance.objective_set_id)
            field.queryset = ObjectiveSet.objects.filter(allowed)
        else:
            field.queryset = ObjectiveSet.objects.filter(archived=False)
        field.label_from_instance = _set_choice_label
        # A fresh (extra) row defaults to the set being authored under, if any.
        if default_set is not None and not (self.instance and self.instance.pk):
            field.initial = default_set.pk
        # Own dates: optional. When set, the KR plots across them instead of the
        # set period (choose 'No set' to rely on them entirely).
        for name in ('start_date', 'end_date'):
            self.fields[name].required = False
        self.fields['start_date'].label = 'Own start'
        self.fields['end_date'].label = 'Own end'

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
        # Own dates are both-or-neither, and the end can't precede the start.
        s_date, e_date = cleaned.get('start_date'), cleaned.get('end_date')
        if bool(s_date) != bool(e_date):
            self.add_error('end_date' if s_date else 'start_date', 'Set both own dates, or neither.')
        elif s_date and e_date and e_date < s_date:
            self.add_error('end_date', 'The end date can’t be before the start date.')
        return cleaned


KeyResultFormSet = inlineformset_factory(
    Objective, KeyResult, form=KeyResultForm, extra=2, can_delete=True,
)


def _team_objectives(team):
    """A team's durable objectives, for the canvas 'OKR related to' picker."""
    if team is None:
        return Objective.objects.none()
    return Objective.objects.filter(team=team, archived=False).order_by('title')


def _init_roadmaps_field(field, team):
    """The per-canvas 'sync to roadmaps' multi-select, scoped to the team's
    non-archived roadmaps."""
    # Set the widget before the queryset: the queryset setter populates the
    # widget's choices, so a widget swapped in afterwards would render empty.
    field.widget = forms.CheckboxSelectMultiple()
    field.queryset = (
        Roadmap.objects.filter(owning_team=team, archived=False).order_by('name')
        if team else Roadmap.objects.none()
    )
    field.required = False
    field.label = 'Sync to roadmaps'
    field.help_text = 'Show this canvas as an activity on the chosen roadmaps.'


class ExperimentCreateForm(forms.Form):
    title = forms.CharField(
        max_length=200, label='Title',
        widget=forms.TextInput(attrs={'class': 'form-input',
                                      'placeholder': 'What should we call the experiment?'}),
    )

    def clean_title(self):
        title = (self.cleaned_data['title'] or '').strip()
        if not title:
            raise forms.ValidationError('Title is required.')
        return title


class ExperimentForm(forms.ModelForm):
    class Meta:
        model = Experiment
        fields = ['title', 'objective', 'roadmaps', 'start_date', 'end_date', 'customer',
                  'segment_size', 'hypothesis', 'actions', 'metric', 'line_in_the_sand', 'result']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input'}),
            'objective': forms.Select(attrs={'class': 'form-input'}),
            'start_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}, format='%Y-%m-%d'),
            'end_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}, format='%Y-%m-%d'),
            'customer': forms.Textarea(attrs={'class': 'form-input', 'rows': 3}),
            'segment_size': forms.Textarea(attrs={'class': 'form-input', 'rows': 2}),
            'hypothesis': forms.Textarea(attrs={'class': 'form-input', 'rows': 3}),
            'actions': forms.Textarea(attrs={'class': 'form-input', 'rows': 3}),
            'metric': forms.Textarea(attrs={'class': 'form-input', 'rows': 3}),
            'line_in_the_sand': forms.Textarea(attrs={'class': 'form-input', 'rows': 2}),
            'result': forms.Textarea(attrs={'class': 'form-input', 'rows': 3}),
        }

    def __init__(self, *args, team=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._team = team
        f = self.fields['objective']
        f.queryset = _team_objectives(team)
        f.required = False
        f.label = 'OKR related to'
        f.empty_label = 'Choose from existing OKRs'
        self.fields['actions'].label = 'Experiment'
        _init_roadmaps_field(self.fields['roadmaps'], team)

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get('start_date'), cleaned.get('end_date')
        if start and end and end < start:
            self.add_error('end_date', 'End date must be after the start date.')
        return cleaned


class PRDCreateForm(forms.Form):
    name = forms.CharField(
        max_length=200, label='Initiative name',
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Checkout improvements'}),
    )
    title = forms.CharField(
        max_length=200, label='Top line summary',
        widget=forms.TextInput(attrs={'class': 'form-input',
                                      'placeholder': 'A succinct summary of the initiative'}),
    )
    start_date = forms.DateField(required=False, label='Estimated start',
                                 widget=forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}))
    end_date = forms.DateField(required=False, label='Estimated end',
                               widget=forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}))

    def clean_name(self):
        name = (self.cleaned_data['name'] or '').strip()
        if not name:
            raise forms.ValidationError('Initiative name is required.')
        return name

    def clean_title(self):
        title = (self.cleaned_data['title'] or '').strip()
        if not title:
            raise forms.ValidationError('Summary is required.')
        return title

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get('start_date'), cleaned.get('end_date')
        if start and end and end < start:
            self.add_error('end_date', 'End date must be after the start date.')
        return cleaned


class PRDForm(forms.ModelForm):
    class Meta:
        model = ProductRequirement
        fields = ['name', 'title', 'start_date', 'end_date', 'objective', 'roadmaps', 'requester',
                  'stakeholders', 'context', 'genesis', 'user_customer', 'problems',
                  'business_outcomes', 'addressable_market', 'costs', 'revenue_value',
                  'metrics', 'validations', 'high_level_requirements', 'risks',
                  'assumptions', 'possible_solutions', 'affected_services', 'decision_log']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input'}),
            'title': forms.TextInput(attrs={'class': 'form-input'}),
            'start_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}, format='%Y-%m-%d'),
            'end_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}, format='%Y-%m-%d'),
            'objective': forms.Select(attrs={'class': 'form-input'}),
        }

    def __init__(self, *args, team=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._team = team
        f = self.fields['objective']
        f.queryset = _team_objectives(team)
        f.required = False
        f.label = 'OKR related to'
        f.empty_label = 'Choose from existing OKRs'
        _init_roadmaps_field(self.fields['roadmaps'], team)
        # Every remaining text field is a canvas textarea.
        for name in self.fields:
            if name not in ('name', 'title', 'start_date', 'end_date', 'objective', 'roadmaps'):
                self.fields[name].widget = forms.Textarea(attrs={'class': 'form-input', 'rows': 3})
                self.fields[name].required = False

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get('start_date'), cleaned.get('end_date')
        if start and end and end < start:
            self.add_error('end_date', 'End date must be after the start date.')
        return cleaned
