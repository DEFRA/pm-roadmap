"""Backfill new fields from legacy data, mirroring the Node migrations.

- Roadmap.team  <- legacy Roadmap.organisation string
- Organisation rows created from distinct organisation strings and linked (M2M)
- Roadmap.roadmap_type inferred from the name ('service' if it mentions service)
- Roadmap-scoped tags (organisation/Teams, objective) get a roadmap, based on
  which roadmap's items / direct tags reference them.
"""
from django.db import migrations


SCOPED_TYPES = ('organisation', 'objective')


def forwards(apps, schema_editor):
    Roadmap = apps.get_model('roadmap', 'Roadmap')
    Organisation = apps.get_model('roadmap', 'Organisation')
    Tag = apps.get_model('roadmap', 'Tag')

    # 1. team <- organisation; create + link Organisation; infer roadmap_type
    for roadmap in Roadmap.objects.all():
        legacy = (roadmap.organisation or '').strip()
        changed = False
        if legacy and not roadmap.team:
            roadmap.team = legacy
            changed = True
        if 'service' in (roadmap.name or '').lower():
            roadmap.roadmap_type = 'service'
            changed = True
        if changed:
            roadmap.save()

        if legacy:
            org, _ = Organisation.objects.get_or_create(name=legacy)
            roadmap.organisations.add(org)

    # 2. Scope existing team/objective tags to the roadmap that uses them.
    for tag in Tag.objects.filter(tag_type__in=SCOPED_TYPES, roadmap__isnull=True):
        roadmap_ids = set(
            tag.items.values_list('roadmap_id', flat=True)
        ) | set(
            tag.roadmaps.values_list('id', flat=True)
        )
        roadmap_ids.discard(None)
        if roadmap_ids:
            tag.roadmap_id = sorted(roadmap_ids)[0]
            tag.save()


def backwards(apps, schema_editor):
    # One-way data backfill; nothing to undo.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('roadmap', '0009_organisation_roadmap_fields_tag_scoping'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
