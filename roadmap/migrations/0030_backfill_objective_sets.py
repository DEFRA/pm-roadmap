"""Backfill Objective.sets (multi-set membership).

Non-destructive: for every objective, its new `sets` M2M is seeded from the two
places membership was previously implied —

1. its (now-deprecated) single `objective_set`, if any; and
2. the distinct sets its key results already sit in (KeyResult.objective_set).

so an objective keeps appearing on exactly the sets it did before, and a durable
objective that already carries KRs across quarters becomes a member of each of
those sets. The single `objective_set` FK is left untouched (kept as the
"primary" pointer).
"""
from django.db import migrations


def forward(apps, schema_editor):
    Objective = apps.get_model('roadmap', 'Objective')
    for obj in Objective.objects.all():
        set_ids = set(
            obj.key_results.exclude(objective_set__isnull=True)
            .values_list('objective_set_id', flat=True)
        )
        if obj.objective_set_id:
            set_ids.add(obj.objective_set_id)
        if set_ids:
            obj.sets.add(*set_ids)


def reverse(apps, schema_editor):
    Objective = apps.get_model('roadmap', 'Objective')
    for obj in Objective.objects.all():
        obj.sets.clear()


class Migration(migrations.Migration):
    dependencies = [('roadmap', '0029_objective_sets_m2m')]
    operations = [migrations.RunPython(forward, reverse)]
