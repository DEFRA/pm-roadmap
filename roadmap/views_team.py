"""Team pages.

A Team owns OKRs (objective sets, objectives, key results) and roadmaps. These
pages list teams and show a team's OKRs + roadmaps. Ported from myproduct.pro's
team_home, trimmed to the OKR scope: no user members, no experiments/PRDs (out
of scope), and no authentication.
"""
import json

from django.shortcuts import render, redirect, get_object_or_404

from .models import Team, ObjectiveSet, Roadmap, Organisation
from .forms import TeamForm


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
    team_sets = (
        ObjectiveSet.objects.filter(scope=ObjectiveSet.TEAM, team=team, archived=False)
        .prefetch_related('objectives__key_results')
    )
    archived_sets = ObjectiveSet.objects.filter(scope=ObjectiveSet.TEAM, team=team, archived=True)
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


def team_create(request):
    return _team_form(request, Team())


def team_edit(request, pk):
    return _team_form(request, get_object_or_404(Team, pk=pk))
