"""Migrate existing tag-based objectives / key results into the new OKR entities.

Non-destructive: every existing Tag is kept exactly as-is. This migration only
*adds* the mirrored entity structure and back-links, so it can be reversed and
so the old data is still there if anything needs checking after deploy.

Mapping (defaults chosen per the plan's open decisions — easy to change later):
  1. One Team per Organisation (named after the org).
  2. Roadmap.owning_team = the team of the roadmap's first organisation.
  3. Each objective Tag -> a standalone Objective owned by that roadmap's team and
     linked to the roadmap via roadmap.objectives (stays scoped to its roadmap).
  4. Every item carrying an objective tag -> item.objective (first tag wins);
     metric items additionally get a backing KeyResult.
  5. Squad tags (tag_type='organisation') -> Tag.team = the roadmap's owning team.
  6. Gov Objective tags are left untouched (central government-alignment refs).

The forward logic lives in roadmap/okr_backfill.py so it can be unit-tested with
the real models; here it is fed the historical models via apps.get_model.
"""
from django.db import migrations

from roadmap.okr_backfill import run_okr_backfill


def forward(apps, schema_editor):
    run_okr_backfill(lambda name: apps.get_model('roadmap', name))


def reverse(apps, schema_editor):
    # Everything created here is new as of migration 0018/0019, so a full clear is
    # a clean reversal. Tags are untouched by forward, so nothing to restore there.
    apps.get_model('roadmap', 'KeyResult').objects.all().delete()
    apps.get_model('roadmap', 'Objective').objects.all().delete()
    apps.get_model('roadmap', 'Item').objects.update(objective=None)
    apps.get_model('roadmap', 'Roadmap').objects.update(owning_team=None)
    apps.get_model('roadmap', 'Tag').objects.update(team=None)
    apps.get_model('roadmap', 'Team').objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [('roadmap', '0019_tag_squad')]
    operations = [migrations.RunPython(forward, reverse)]
