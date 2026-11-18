"""Team experiment canvases. Ported from myproduct.pro without auth: anyone can
create, edit or delete (access is the CDP network boundary)."""
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from .models import Team, Experiment
from .forms import ExperimentCreateForm, ExperimentForm
from .experiment_sync import reconcile_experiment, default_sync_roadmaps


def experiment_create(request, pk):
    team = get_object_or_404(Team, pk=pk)
    form = ExperimentCreateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        experiment = Experiment.objects.create(team=team, title=form.cleaned_data['title'])
        experiment.roadmaps.set(default_sync_roadmaps(team))   # default: the team's opted-in roadmaps
        reconcile_experiment(experiment)
        return redirect('roadmap:experiment_detail', pk=team.pk, experiment_pk=experiment.pk)
    return render(request, 'roadmap/experiment_create.html', {'team': team, 'form': form})


def experiment_detail(request, pk, experiment_pk):
    team = get_object_or_404(Team, pk=pk)
    experiment = get_object_or_404(
        Experiment.objects.select_related('objective'), pk=experiment_pk, team=team)
    form = ExperimentForm(request.POST or None, instance=experiment, team=team)
    if request.method == 'POST' and form.is_valid():
        form.save()                        # persists the roadmaps selection
        reconcile_experiment(experiment)   # add/remove backing activities to match
        return redirect('roadmap:experiment_detail', pk=team.pk, experiment_pk=experiment.pk)
    return render(request, 'roadmap/experiment_detail.html', {
        'team': team, 'experiment': experiment, 'form': form,
    })


@require_POST
def experiment_delete(request, pk, experiment_pk):
    team = get_object_or_404(Team, pk=pk)
    get_object_or_404(Experiment, pk=experiment_pk, team=team).delete()
    return redirect('roadmap:team_home', pk=team.pk)
