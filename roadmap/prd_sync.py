"""Keep team PRDs in step with roadmap activities (see experiment_sync.py)."""
from .access import objective_assignable_to_roadmap
from .models import Item, ProductRequirement, Roadmap


def prd_sync_roadmaps(prd):
    """Team roadmaps that should show this PRD as an activity."""
    return Roadmap.objects.filter(
        owning_team_id=prd.team_id, archived=False, sync_prds=True,
    )


def _item_objective_for_roadmap(prd, roadmap):
    if prd.objective_id and objective_assignable_to_roadmap(prd.objective, roadmap):
        return prd.objective
    return None


def _prd_description(prd):
    return prd.problems or prd.high_level_requirements or ''


def prds_not_on_roadmap(roadmap):
    """Team PRDs that don't yet have an activity on this roadmap."""
    if not roadmap.owning_team_id:
        return ProductRequirement.objects.none()
    return (
        ProductRequirement.objects.filter(team_id=roadmap.owning_team_id)
        .exclude(roadmap_items__roadmap=roadmap)
        .order_by('-created_at')
    )


def sync_prd_to_roadmap(prd, roadmap):
    """Create or update the roadmap activity backing a PRD."""
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


def sync_prd_to_roadmaps(prd):
    for roadmap in prd_sync_roadmaps(prd):
        sync_prd_to_roadmap(prd, roadmap)


def sync_all_prds_to_roadmap(roadmap):
    if not roadmap.sync_prds or not roadmap.owning_team_id:
        return
    for prd in ProductRequirement.objects.filter(team_id=roadmap.owning_team_id):
        sync_prd_to_roadmap(prd, roadmap)


def remove_synced_prds_from_roadmap(roadmap):
    roadmap.items.filter(product_requirement__isnull=False).delete()
