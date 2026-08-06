"""Backfill logic for migration 0020 (tag-based OKRs -> OKR entities).

Kept as a standalone function taking a ``get_model(name)`` accessor so the data
migration can pass historical models (via apps.get_model) while tests can pass
the real models. It imports nothing from .models at module load, so it is safe
to import from within a migration.

See migration 0020_migrate_okr_data for the mapping rationale.
"""

OBJECTIVE = 'objective'
ORGANISATION = 'organisation'
METRIC = 'metric'


def run_okr_backfill(get_model):
    Organisation = get_model('Organisation')
    Team = get_model('Team')
    Roadmap = get_model('Roadmap')
    Tag = get_model('Tag')
    Item = get_model('Item')
    Objective = get_model('Objective')
    KeyResult = get_model('KeyResult')

    # 1. One Team per Organisation.
    org_team = {}
    for org in Organisation.objects.all():
        team, _ = Team.objects.get_or_create(organisation=org, name=org.name[:120])
        org_team[org.pk] = team

    # 2. Roadmap.owning_team from the roadmap's first organisation. Never clobber
    #    a team that has already been set (defensive — it is null pre-migration).
    for rm in Roadmap.objects.prefetch_related('organisations').all():
        if rm.owning_team_id:
            continue
        orgs = list(rm.organisations.all())
        if orgs and org_team.get(orgs[0].pk):
            rm.owning_team = org_team[orgs[0].pk]
            rm.save(update_fields=['owning_team'])

    # 3. Objective tags -> standalone Objectives, linked to their roadmap.
    tag_to_obj = {}
    for tag in Tag.objects.filter(tag_type=OBJECTIVE).select_related('roadmap'):
        rm = tag.roadmap
        team = None
        if rm and rm.owning_team_id:
            team = Team.objects.filter(pk=rm.owning_team_id).first()
        obj = Objective.objects.create(
            title=(tag.name or '')[:200], description=tag.description or '', team=team,
        )
        tag_to_obj[tag.pk] = obj
        if rm:
            rm.objectives.add(obj)

    # 4. Items carrying an objective tag -> item.objective (+ KeyResult for metrics).
    for item in Item.objects.prefetch_related('tags').all():
        obj_tags = [t for t in item.tags.all() if t.tag_type == OBJECTIVE]
        if not obj_tags:
            continue
        obj_tags.sort(key=lambda t: (t.sort_order, t.name))
        objective = tag_to_obj.get(obj_tags[0].pk)
        if objective is None:
            continue
        item.objective = objective
        item.save(update_fields=['objective'])
        if item.item_type == METRIC and not KeyResult.objects.filter(
            objective=objective, title=item.title,
        ).exists():
            last = KeyResult.objects.filter(objective=objective).order_by('-sort_order').first()
            KeyResult.objects.create(
                objective=objective, title=(item.title or '')[:200],
                sort_order=(last.sort_order + 1) if last else 0,
            )

    # 5. Squad tags -> their roadmap's owning team.
    for tag in Tag.objects.filter(tag_type=ORGANISATION).select_related('roadmap'):
        if tag.roadmap and tag.roadmap.owning_team_id:
            tag.team_id = tag.roadmap.owning_team_id
            tag.save(update_fields=['team'])

    # 6. Gov Objective tags are left untouched (central alignment references).
