"""Seed roadmap.tags membership so the header reflects a single source of truth.

Mirrors the Node backfill: roadmap.tags becomes the authoritative set of
objectives / outcomes / teams "on" a roadmap. We seed it from what is currently
displayed — the roadmap's scoped tags (teams, objectives) plus the central
outcome / gov-objective tags used by its items — so nothing disappears when the
header switches from item-derived display to membership-based display.
"""
from django.db import migrations

CENTRAL_HEADER_TYPES = ('outcome', 'gov_objective')
SCOPED_TYPES = ('organisation', 'objective')


def forwards(apps, schema_editor):
    Roadmap = apps.get_model('roadmap', 'Roadmap')
    Tag = apps.get_model('roadmap', 'Tag')

    for roadmap in Roadmap.objects.all():
        scoped = Tag.objects.filter(roadmap=roadmap, tag_type__in=SCOPED_TYPES)
        central_used = Tag.objects.filter(
            tag_type__in=CENTRAL_HEADER_TYPES, items__roadmap=roadmap
        ).distinct()
        existing = roadmap.tags.all()
        ids = set()
        for qs in (scoped, central_used, existing):
            ids.update(qs.values_list('pk', flat=True))
        if ids:
            roadmap.tags.add(*ids)


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('roadmap', '0012_alter_tag_colour'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
