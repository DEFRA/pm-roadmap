"""Team PRD canvases. Ported from myproduct.pro without auth (see views_experiments)."""
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from .models import Team, ProductRequirement
from .forms import PRDCreateForm, PRDForm
from .prd_sync import reconcile_prd, default_sync_roadmaps


def prd_create(request, pk):
    team = get_object_or_404(Team, pk=pk)
    form = PRDCreateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        prd = ProductRequirement.objects.create(
            team=team,
            name=form.cleaned_data['name'],
            title=form.cleaned_data['title'],
            start_date=form.cleaned_data.get('start_date'),
            end_date=form.cleaned_data.get('end_date'),
        )
        prd.roadmaps.set(default_sync_roadmaps(team))
        reconcile_prd(prd)
        return redirect('roadmap:prd_detail', pk=team.pk, prd_pk=prd.pk)
    return render(request, 'roadmap/prd_create.html', {'team': team, 'form': form})


# The PRD canvas, in render order: (label, model field name).
PRD_FIELDS = [
    ('Requester', 'requester'),
    ('Stakeholders', 'stakeholders'),
    ('Context', 'context'),
    ('Genesis of the idea', 'genesis'),
    ('User / customer that will benefit', 'user_customer'),
    ('Problems to be solved / job to be done', 'problems'),
    ('Intended business value outcomes', 'business_outcomes'),
    ('Addressable market size', 'addressable_market'),
    ('Costs', 'costs'),
    ('Revenue / value', 'revenue_value'),
    ('Metrics', 'metrics'),
    ('Validations', 'validations'),
    ('High level requirements / features', 'high_level_requirements'),
    ('Risks / known unknowns', 'risks'),
    ('Assumptions', 'assumptions'),
    ('Possible solutions', 'possible_solutions'),
    ('Affected application & service map', 'affected_services'),
    ('Comment / decision log', 'decision_log'),
]


def prd_detail(request, pk, prd_pk):
    team = get_object_or_404(Team, pk=pk)
    prd = get_object_or_404(
        ProductRequirement.objects.select_related('objective'), pk=prd_pk, team=team)
    form = PRDForm(request.POST or None, instance=prd, team=team)
    if request.method == 'POST' and form.is_valid():
        form.save()                 # persists the roadmaps selection
        reconcile_prd(prd)          # add/remove backing activities to match
        return redirect('roadmap:prd_detail', pk=team.pk, prd_pk=prd.pk)
    canvas = [(label, form[name]) for label, name in PRD_FIELDS]
    return render(request, 'roadmap/prd_detail.html', {
        'team': team, 'prd': prd, 'form': form, 'canvas': canvas,
    })


@require_POST
def prd_delete(request, pk, prd_pk):
    team = get_object_or_404(Team, pk=pk)
    get_object_or_404(ProductRequirement, pk=prd_pk, team=team).delete()
    return redirect('roadmap:team_home', pk=team.pk)
