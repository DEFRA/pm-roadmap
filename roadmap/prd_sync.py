"""Keep team PRDs in step with roadmap activities (see experiment_sync.py)."""
from .access import objective_assignable_to_roadmap
from .models import ProductRequirement, Roadmap


def team_roadmaps(team):
    """Non-archived roadmaps owned by the team — the selectable sync targets."""
    if team is None:
        return Roadmap.objects.none()
    return Roadmap.objects.filter(owning_team=team, archived=False).order_by('name')


def default_sync_roadmaps(team):
    """Roadmaps a new PRD syncs to by default: the team's non-archived roadmaps
    that opt in (Roadmap.sync_prds)."""
    return team_roadmaps(team).filter(sync_prds=True)


def _item_objective_for_roadmap(prd, roadmap):
    if prd.objective_id and objective_assignable_to_roadmap(prd.objective, roadmap):
        return prd.objective
    return None


def _prd_description(prd):
    return prd.problems or prd.high_level_requirements or ''


def sync_prd_to_roadmap(prd, roadmap):
    """Create or update the roadmap activity backing a PRD."""
    from .models import Item
    item = Item.objects.filter(roadmap=roadmap, product_requirement=prd).first()
    if item is None:
        item = Item(roadmap=roadmap, product_requirement=prd, item_type=Item.ACTIVITY)
    item.title = prd.name
    item.description = prd.title or _prd_description(prd)
    item.start_date = prd.start_date
    item.end_date = prd.end_date
    item.objective = _item_objective_for_roadmap(prd, roadmap)
    item.save()
    return item


def reconcile_prd(prd):
    """Make the backing activities match prd.roadmaps exactly."""
    selected_ids = set(prd.roadmaps.values_list('pk', flat=True))
    prd.roadmap_items.exclude(roadmap_id__in=selected_ids).delete()
    for roadmap in Roadmap.objects.filter(pk__in=selected_ids):
        sync_prd_to_roadmap(prd, roadmap)


def add_roadmap_to_team_prds(roadmap):
    """When a roadmap is created with sync on, include it on the team's existing
    PRDs and sync."""
    if not (roadmap.sync_prds and roadmap.owning_team_id and not roadmap.archived):
        return
    for prd in ProductRequirement.objects.filter(team_id=roadmap.owning_team_id):
        prd.roadmaps.add(roadmap)
        sync_prd_to_roadmap(prd, roadmap)
