"""Keep team experiments in step with roadmap activities.

An experiment can surface as an activity bar on the owning team's roadmaps that
opt in (Roadmap.sync_experiments). The backing Item links back via Item.experiment;
saving the experiment creates or updates that Item, deleting the experiment (via
the FK cascade) removes it.
"""
from .access import objective_assignable_to_roadmap
from .models import Experiment, Item, Roadmap


def experiment_sync_roadmaps(experiment):
    """Team roadmaps that should show this experiment as an activity."""
    return Roadmap.objects.filter(
        owning_team_id=experiment.team_id, archived=False, sync_experiments=True,
    )


def _item_objective_for_roadmap(experiment, roadmap):
    if experiment.objective_id and objective_assignable_to_roadmap(experiment.objective, roadmap):
        return experiment.objective
    return None


def experiments_not_on_roadmap(roadmap):
    """Team experiments that don't yet have an activity on this roadmap."""
    if not roadmap.owning_team_id:
        return Experiment.objects.none()
    return (
        Experiment.objects.filter(team_id=roadmap.owning_team_id)
        .exclude(roadmap_items__roadmap=roadmap)
        .order_by('-created_at')
    )


def sync_experiment_to_roadmap(experiment, roadmap):
    """Create or update the roadmap activity backing an experiment."""
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


def sync_experiment_to_roadmaps(experiment):
    for roadmap in experiment_sync_roadmaps(experiment):
        sync_experiment_to_roadmap(experiment, roadmap)


def sync_all_experiments_to_roadmap(roadmap):
    if not roadmap.sync_experiments or not roadmap.owning_team_id:
        return
    for experiment in Experiment.objects.filter(team_id=roadmap.owning_team_id):
        sync_experiment_to_roadmap(experiment, roadmap)


def remove_synced_experiments_from_roadmap(roadmap):
    roadmap.items.filter(experiment__isnull=False).delete()
