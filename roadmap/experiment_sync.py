"""Keep team experiments in step with roadmap activities.

Which roadmaps a canvas appears on is chosen per-canvas (Experiment.roadmaps). The
backing Item links back via Item.experiment; reconciling creates/updates an Item
on each selected roadmap and removes it from any deselected one. Deleting the
experiment (FK cascade) removes its activities.
"""
from .access import objective_assignable_to_roadmap
from .models import Experiment, Roadmap


def team_roadmaps(team):
    """Non-archived roadmaps owned by the team — the selectable sync targets."""
    if team is None:
        return Roadmap.objects.none()
    return Roadmap.objects.filter(owning_team=team, archived=False).order_by('name')


def default_sync_roadmaps(team):
    """Roadmaps a new experiment syncs to by default: the team's non-archived
    roadmaps that opt in (Roadmap.sync_experiments)."""
    return team_roadmaps(team).filter(sync_experiments=True)


def _item_objective_for_roadmap(experiment, roadmap):
    if experiment.objective_id and objective_assignable_to_roadmap(experiment.objective, roadmap):
        return experiment.objective
    return None


def sync_experiment_to_roadmap(experiment, roadmap):
    """Create or update the roadmap activity backing an experiment."""
    from .models import Item
    item = Item.objects.filter(roadmap=roadmap, experiment=experiment).first()
    if item is None:
        item = Item(roadmap=roadmap, experiment=experiment, item_type=Item.ACTIVITY)
    item.title = experiment.title
    item.description = experiment.hypothesis or ''
    item.start_date = experiment.start_date
    item.end_date = experiment.end_date
    item.objective = _item_objective_for_roadmap(experiment, roadmap)
    item.save()
    return item


def reconcile_experiment(experiment):
    """Make the backing activities match experiment.roadmaps exactly."""
    selected_ids = set(experiment.roadmaps.values_list('pk', flat=True))
    experiment.roadmap_items.exclude(roadmap_id__in=selected_ids).delete()
    for roadmap in Roadmap.objects.filter(pk__in=selected_ids):
        sync_experiment_to_roadmap(experiment, roadmap)


def add_roadmap_to_team_experiments(roadmap):
    """When a roadmap is created with sync on, include it on the team's existing
    experiments and sync."""
    if not (roadmap.sync_experiments and roadmap.owning_team_id and not roadmap.archived):
        return
    for experiment in Experiment.objects.filter(team_id=roadmap.owning_team_id):
        experiment.roadmaps.add(roadmap)
        sync_experiment_to_roadmap(experiment, roadmap)
