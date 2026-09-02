"""Backfill for durable objectives (B2).

Two non-destructive data fixes:

1. KeyResult.objective_set from its objective's (now-deprecated) set, so every
   existing KR keeps the same timeline period it had when it spanned that set.
2. Objective.team from its set's team where the objective has no team yet. B2
   keys team ownership on Objective.team (the durable link), so a legacy objective
   sitting in a team's set but with team=None would otherwise be invisible to that
   team's roadmap and to the "reuse an existing objective" picker.

Objective.objective_set is left populated (vestigial).
"""
from django.db import migrations


def forward(apps, schema_editor):
    KeyResult = apps.get_model('roadmap', 'KeyResult')
    Objective = apps.get_model('roadmap', 'Objective')
    # 1. Copy the objective's set down onto each key result.
    for kr in KeyResult.objects.select_related('objective').all():
        set_id = kr.objective.objective_set_id
        if set_id and kr.objective_set_id != set_id:
            kr.objective_set_id = set_id
            kr.save(update_fields=['objective_set'])
    # 2. Adopt the set's team for any team-less objective that lives in a team set.
    for obj in Objective.objects.select_related('objective_set').filter(
        team__isnull=True, objective_set__team__isnull=False,
    ):
        obj.team_id = obj.objective_set.team_id
        obj.save(update_fields=['team'])


def reverse(apps, schema_editor):
    # Only the KR period is reversible; the team backfill can't be undone safely
    # (we can't tell which objectives were originally team-less), so leave it.
    apps.get_model('roadmap', 'KeyResult').objects.update(objective_set=None)


class Migration(migrations.Migration):
    dependencies = [('roadmap', '0025_durable_objectives_schema')]
    operations = [migrations.RunPython(forward, reverse)]
