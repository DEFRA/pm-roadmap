"""Standalone Objectives & Key Results (OKR) pages.

Objectives are grouped into Objective Sets (an OKR cycle / planning period with a
start & end date), owned by a team or the organisation. Roadmaps link to a set —
a live reference, not a copy (see roadmap/access.py for the sync rules).

Ported from myproduct.pro with authentication removed: pm-roadmap has no users,
so there is no owner, no premium gate, and editing is open to everyone.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from . import okr_periods
from .models import Objective, ObjectiveSet
from .forms import ObjectiveForm, ObjectiveSetForm, KeyResultFormSet, set_form_seed


def objective_list(request):
    sets = (
        ObjectiveSet.objects.filter(archived=False)
        .prefetch_related('objectives__key_results', 'objectives__team', 'organisation', 'team')
    )
    unassigned = (
        Objective.objects.filter(objective_set__isnull=True)
        .select_related('team')
        .prefetch_related('key_results')
    )
    return render(request, 'roadmap/objective_list.html', {
        'objective_sets': sets,
        'unassigned': unassigned,
    })


# ── Objective sets ────────────────────────────────────────────────────────────
# New sets are always created from a team page (views_team.team_set_create) so
# they are tied to a team. Only editing lives here.

def objective_set_detail(request, pk):
    obj_set = get_object_or_404(
        ObjectiveSet.objects.prefetch_related(
            'objectives__key_results', 'objectives__team', 'roadmaps',
        ),
        pk=pk,
    )
    return render(request, 'roadmap/objective_set_detail.html', {
        'objective_set': obj_set,
        'objectives': obj_set.objectives.all(),
        'roadmaps': obj_set.roadmaps.all(),
    })


def _set_home_redirect(obj_set):
    if obj_set.scope == ObjectiveSet.TEAM and obj_set.team_id:
        return redirect('roadmap:team_home', pk=obj_set.team_id)
    return redirect('roadmap:objective_list')


def objective_set_edit(request, pk):
    obj_set = get_object_or_404(ObjectiveSet, pk=pk)
    form = ObjectiveSetForm(request.POST or None, instance=obj_set)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('roadmap:objective_set_detail', pk=obj_set.pk)
    return render(request, 'roadmap/objective_set_form.html', {
        'form': form,
        'objective_set': obj_set,
        'team': obj_set.team,
        'form_seed': set_form_seed(form),
    })


@require_POST
def objective_set_archive(request, pk):
    obj_set = get_object_or_404(ObjectiveSet, pk=pk)
    obj_set.archived = True
    obj_set.save(update_fields=['archived'])
    return _set_home_redirect(obj_set)


@require_POST
def objective_set_unarchive(request, pk):
    obj_set = get_object_or_404(ObjectiveSet, pk=pk)
    obj_set.archived = False
    obj_set.save(update_fields=['archived'])
    return redirect('roadmap:objective_set_detail', pk=obj_set.pk)


def objective_set_delete(request, pk):
    obj_set = get_object_or_404(ObjectiveSet, pk=pk)
    redirect_to = _set_home_redirect(obj_set)
    if request.method == 'POST':
        obj_set.delete()
    return redirect_to


# ── Objectives ────────────────────────────────────────────────────────────────

def _objective_form(request, objective):
    """Shared create/edit handler with the Key Result inline formset."""
    form = ObjectiveForm(request.POST or None, instance=objective)
    formset = KeyResultFormSet(request.POST or None, instance=objective)

    if request.method == 'POST' and form.is_valid() and formset.is_valid():
        obj = form.save(commit=False)
        # The objective inherits its set's team (team isn't asked for).
        obj.team = obj.objective_set.team if obj.objective_set_id else None
        obj.save()
        formset.instance = obj
        formset.save()
        return redirect('roadmap:objective_detail', pk=obj.pk)

    # The set (from the instance or the submitted/queried value) drives the team
    # breadcrumb back to the team page.
    obj_set = objective.objective_set if objective.objective_set_id else None
    if obj_set is None:
        set_val = form['objective_set'].value()
        if set_val:
            obj_set = ObjectiveSet.objects.filter(pk=set_val).first()
    return render(request, 'roadmap/objective_form.html', {
        'form': form,
        'formset': formset,
        'objective': objective if objective.pk else None,
        'objective_set': obj_set,
        'team': obj_set.team if obj_set else None,
    })


def objective_create(request):
    objective = Objective()
    set_pk = request.GET.get('set')
    if set_pk and request.method == 'GET':
        objective.objective_set = ObjectiveSet.objects.filter(pk=set_pk).first()
    return _objective_form(request, objective)


def objective_detail(request, pk):
    """Read-only view of an objective + its key results (most people just read)."""
    objective = get_object_or_404(
        Objective.objects.select_related('objective_set', 'team').prefetch_related('key_results'),
        pk=pk,
    )
    next_objective = prev_objective = None
    obj_set = objective.objective_set
    if obj_set_id := objective.objective_set_id:
        # Same order as the set page (newest first) so next/prev match scrolling down/up.
        siblings = list(
            Objective.objects.filter(objective_set_id=obj_set_id).order_by('-created_at', 'pk')
        )
        index = next((i for i, sib in enumerate(siblings) if sib.pk == objective.pk), None)
        if index is not None and len(siblings) > 1:
            next_objective = siblings[(index + 1) % len(siblings)]
            prev_objective = siblings[(index - 1) % len(siblings)]
    return render(request, 'roadmap/objective_detail.html', {
        'objective': objective,
        'objective_set': obj_set,
        'team': objective.team,
        'next_objective': next_objective,
        'prev_objective': prev_objective,
    })


def objective_edit(request, pk):
    return _objective_form(request, get_object_or_404(Objective, pk=pk))


def objective_delete(request, pk):
    objective = get_object_or_404(Objective, pk=pk)
    set_id = objective.objective_set_id
    if request.method == 'POST':
        objective.delete()
    if set_id:
        return redirect('roadmap:objective_set_detail', pk=set_id)
    return redirect('roadmap:objective_list')
