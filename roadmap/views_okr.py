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
from .models import Objective, ObjectiveSet, KeyResult
from .forms import ObjectiveForm, ObjectiveSetForm, KeyResultFormSet, set_form_seed


def _kr_misaligned(kr, obj_set):
    """True if a key result has a custom roadmap date that falls outside its
    set's window (i.e. it was dragged off the set period). Blank dates inherit
    the set period and are never misaligned."""
    if not (obj_set.start_date and obj_set.end_date):
        return False
    lo, hi = obj_set.start_date, obj_set.end_date
    return any(d is not None and (d < lo or d > hi) for d in (kr.start_date, kr.end_date))


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
            'key_results__objective__team', 'objectives__key_results', 'roadmaps',
        ),
        pk=pk,
    )
    # Durable objectives (B2): the objectives on this set page are those with a key
    # result in this period (kr.objective_set), unioned with any legacy objectives
    # still linked by the deprecated Objective.objective_set so nothing vanishes.
    objectives = {kr.objective_id: kr.objective for kr in obj_set.key_results.all()}
    for o in obj_set.objectives.all():
        objectives.setdefault(o.pk, o)
    objectives = sorted(objectives.values(), key=lambda o: (-o.created_at.timestamp(), o.pk))
    # Each objective shows only THIS set's key results — a reused objective keeps
    # its other sets' KRs elsewhere, and new KRs here don't leak into its origin.
    period_krs = {}
    for kr in obj_set.key_results.all():
        period_krs.setdefault(kr.objective_id, []).append(kr)
    for o in objectives:
        o.card_key_results = period_krs.get(o.pk, [])
    misaligned_krs = [kr for kr in obj_set.key_results.all() if _kr_misaligned(kr, obj_set)]
    return render(request, 'roadmap/objective_set_detail.html', {
        'objective_set': obj_set,
        'objectives': objectives,
        'roadmaps': obj_set.roadmaps.all(),
        'misaligned_krs': misaligned_krs,
    })


@require_POST
def key_result_snap_to_set(request, pk):
    """Clear a key result's custom roadmap dates so it re-spans its set period."""
    kr = get_object_or_404(KeyResult.objects.select_related('objective'), pk=pk)
    # Restore the default placement: clear the custom dates (re-span the set) and
    # the drag-assigned row so it re-stacks naturally with its siblings.
    kr.start_date = None
    kr.end_date = None
    kr.row = None
    kr.save(update_fields=['start_date', 'end_date', 'row'])
    set_id = kr.objective_set_id
    if set_id:
        return redirect('roadmap:objective_set_detail', pk=set_id)
    return redirect('roadmap:objective_detail', pk=kr.objective_id)


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
    """Shared create/edit handler with the Key Result inline formset.

    Objectives are durable (B2): authoring under a set can either create a new
    objective or reuse an existing team one, and the key results entered here are
    tagged with *this set's* period (kr.objective_set) so the same objective can
    carry fresh KRs each quarter under one persistent roadmap lane.
    """
    # The set being authored under drives the KRs' period and the reuse picker.
    # On POST it comes from the submitted objective_set (or the ?set= seed); on a
    # blank GET, from the instance or the ?set= query param.
    authored_set = objective.objective_set if objective.objective_set_id else None
    if authored_set is None:
        set_val = request.POST.get('objective_set') or request.GET.get('set')
        if set_val:
            authored_set = ObjectiveSet.objects.filter(pk=set_val).first()
    reuse_team = authored_set.team if (authored_set and not objective.pk) else None

    form = ObjectiveForm(request.POST or None, instance=objective, team=reuse_team)
    formset = KeyResultFormSet(request.POST or None, instance=objective)

    if request.method == 'POST' and form.is_valid() and formset.is_valid():
        existing = form.cleaned_data.get('existing_objective')
        if existing is not None:
            obj = existing  # reuse the durable objective; keep its own set/team
        else:
            obj = form.save(commit=False)
            # A new objective inherits its set's team (team isn't asked for).
            obj.team = obj.objective_set.team if obj.objective_set_id else None
            obj.save()
        # Attach the entered key results to this objective for this set's period.
        for kr in formset.save(commit=False):
            kr.objective = obj
            if kr.objective_set_id is None:
                kr.objective_set = authored_set
            kr.save()
        for kr in formset.deleted_objects:
            kr.delete()
        return redirect('roadmap:objective_detail', pk=obj.pk)

    # authored_set already resolves the instance / submitted / ?set= sources; it
    # drives the team breadcrumb back to the team page.
    obj_set = authored_set
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
