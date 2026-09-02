"""Team pages.

A Team owns OKRs (objective sets, objectives, key results) and roadmaps. These
pages list teams and show a team's OKRs + roadmaps. Ported from myproduct.pro's
team_home, trimmed to the OKR scope: no user members, no experiments/PRDs (out
of scope), and no authentication.
"""
import json

from django.shortcuts import render, redirect, get_object_or_404

from .models import Team, ObjectiveSet, Roadmap, Organisation
from .forms import TeamForm, TeamRoadmapForm, ObjectiveSetForm, set_form_seed


def team_list(request):
    teams = Team.objects.select_related('organisation').all()
    teams_json = json.dumps([
        {'id': t.pk, 'name': t.name, 'org_id': t.organisation_id, 'org_name': t.organisation.name}
        for t in teams
    ])
    return render(request, 'roadmap/team_list.html', {
        'teams': teams,
        'teams_json': teams_json,
        'organisations': Organisation.objects.all(),
    })


def team_home(request, pk):
    team = get_object_or_404(Team.objects.select_related('organisation'), pk=pk)
    team_sets = list(
        ObjectiveSet.objects.filter(scope=ObjectiveSet.TEAM, team=team, archived=False)
        .prefetch_related('objectives__key_results', 'key_results')
    )
    archived_sets = list(
        ObjectiveSet.objects.filter(scope=ObjectiveSet.TEAM, team=team, archived=True)
        .prefetch_related('objectives', 'key_results')
    )

    # Durable objectives (B2): a set's objectives are those with a key result in
    # this period (kr.objective_set) plus any still linked by the deprecated
    # Objective.objective_set — so a reused objective counts under each set it
    # carries KRs in, not only its original one.
    def _durable_count(s):
        ids = {kr.objective_id for kr in s.key_results.all()}
        ids |= {o.pk for o in s.objectives.all()}
        return len(ids)
    for s in team_sets + archived_sets:
        s.durable_objective_count = _durable_count(s)
    team_roadmaps = Roadmap.objects.filter(owning_team=team).prefetch_related('items')
    return render(request, 'roadmap/team_home.html', {
        'team': team,
        'team_sets': team_sets,
        'archived_sets': archived_sets,
        'team_roadmaps': team_roadmaps,
    })


def _team_form(request, instance):
    form = TeamForm(request.POST or None, instance=instance)
    if request.method == 'POST' and form.is_valid():
        team = form.save()
        return redirect('roadmap:team_home', pk=team.pk)
    return render(request, 'roadmap/team_form.html', {
        'form': form,
        'team': instance if instance.pk else None,
    })


def team_set_create(request, pk):
    """Create an objective set owned by this team (scope=team). Organisation and
    team come from the team, so the form only asks for name + timeframe."""
    team = get_object_or_404(Team.objects.select_related('organisation'), pk=pk)
    instance = ObjectiveSet(organisation=team.organisation, scope=ObjectiveSet.TEAM, team=team)
    form = ObjectiveSetForm(request.POST or None, instance=instance)
    if request.method == 'POST' and form.is_valid():
        obj_set = form.save(commit=False)
        obj_set.organisation = team.organisation
        obj_set.scope = ObjectiveSet.TEAM
        obj_set.team = team
        obj_set.save()
        return redirect('roadmap:objective_set_detail', pk=obj_set.pk)
    return render(request, 'roadmap/objective_set_form.html', {
        'form': form, 'team': team, 'form_seed': set_form_seed(form),
    })


def team_roadmap_create(request, pk):
    """Create a roadmap owned by this team (owning_team set, so the team's OKRs
    sync onto it). Defaults to a service/product roadmap."""
    team = get_object_or_404(Team, pk=pk)
    form = TeamRoadmapForm(request.POST or None, initial={'roadmap_type': Roadmap.SERVICE})
    if request.method == 'POST' and form.is_valid():
        roadmap = form.save(commit=False)
        roadmap.owning_team = team
        roadmap.save()
        if team.organisation_id:
            roadmap.organisations.add(team.organisation)
        return redirect('roadmap:detail', pk=roadmap.pk)
    return render(request, 'roadmap/team_roadmap_form.html', {'form': form, 'team': team})


def team_create(request):
    return _team_form(request, Team())


def team_edit(request, pk):
    return _team_form(request, get_object_or_404(Team, pk=pk))
