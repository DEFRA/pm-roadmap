"""OKR → roadmap sync helpers.

Ported from myproduct.pro's roadmap/access.py, with all authentication /
membership / premium logic removed (pm-roadmap has no auth). What remains is the
pure scoping question: *which objective sets and objectives appear on a given
roadmap?*

Scoping rule (unchanged from the source):
  * A roadmap with an owning team syncs only that team's TEAM-scoped sets.
  * A roadmap with no team syncs its organisation(s)' GROUP-scoped sets.
  * Archived sets never sync.
  * Objectives also reach a roadmap via a direct M2M link (roadmap.objectives).

pm-roadmap reconciliation: the source used roadmap.organisation (a single FK);
here a roadmap has organisations (M2M) plus an optional owning team, so a
teamless roadmap's org scope is "any of its organisations".
"""

from .models import ObjectiveSet, Objective


def _roadmap_org_ids(roadmap):
    """Organisation ids in scope for a teamless (group) roadmap."""
    return list(roadmap.organisations.values_list('pk', flat=True))


def linkable_sets(roadmap):
    """Objective sets whose objectives appear as synced lanes on this roadmap.

    Team roadmaps sync their own team's sets; teamless (group) roadmaps sync
    their organisations' group-level sets. Archived sets are excluded.
    """
    if roadmap.owning_team_id:
        return ObjectiveSet.objects.filter(
            scope=ObjectiveSet.TEAM,
            team_id=roadmap.owning_team_id,
            archived=False,
        )
    return ObjectiveSet.objects.filter(
        scope=ObjectiveSet.GROUP,
        organisation_id__in=_roadmap_org_ids(roadmap),
        archived=False,
    )


def applied_objective_sets(roadmap):
    """Objective sets whose objectives appear on this roadmap (empty if sync off)."""
    if roadmap.sync_okrs:
        qs = linkable_sets(roadmap)
    else:
        qs = ObjectiveSet.objects.none()
    return qs.prefetch_related('objectives__key_results')


def roadmap_objective_ids(roadmap):
    """Objective PKs shown on this roadmap.

    Team roadmaps show ALL the owning team's (durable) objectives, minus any the
    roadmap has hidden (see Roadmap.hidden_objectives) — the objective persists
    across quarters as one lane. Teamless/group roadmaps still source via their
    linkable group sets. Directly-linked objectives are always included; the
    sync_okrs toggle gates the team/group sourcing.
    """
    ids = set(roadmap.objectives.values_list('pk', flat=True))
    if not roadmap.sync_okrs:
        return ids
    if roadmap.owning_team_id:
        team_obj_ids = set(
            Objective.objects.filter(team_id=roadmap.owning_team_id).values_list('pk', flat=True)
        )
        hidden = set(roadmap.hidden_objectives.values_list('pk', flat=True))
        ids.update(team_obj_ids - hidden)
    else:
        for obj_set in linkable_sets(roadmap).prefetch_related('objectives'):
            ids.update(o.pk for o in obj_set.objectives.all())
    return ids


def objective_on_roadmap(objective, roadmap):
    """True if this objective is on the roadmap: a durable objective owned by the
    roadmap's team (B2), a directly-linked objective, or one via a synced set."""
    if roadmap.sync_okrs and roadmap.owning_team_id and objective.team_id == roadmap.owning_team_id:
        return True
    if roadmap.objectives.filter(pk=objective.pk).exists():
        return True
    if roadmap.sync_okrs and objective.objective_set_id:
        return linkable_sets(roadmap).filter(pk=objective.objective_set_id).exists()
    return False


def objective_assignable_to_roadmap(objective, roadmap):
    """True when an item on this roadmap may reference the objective.

    A team roadmap may assign work to its organisation's active GROUP objectives
    without those objectives syncing into the roadmap's swim lanes.
    """
    if objective_on_roadmap(objective, roadmap):
        return True
    obj_set = objective.objective_set
    if not (roadmap.owning_team_id and obj_set and not obj_set.archived and obj_set.scope == ObjectiveSet.GROUP):
        return False
    return obj_set.organisation_id in set(_roadmap_org_ids(roadmap)) or (
        obj_set.organisation_id == getattr(roadmap.owning_team, 'organisation_id', None)
    )
