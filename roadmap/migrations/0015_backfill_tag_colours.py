"""Give existing tags a colour from the palette.

Tags created before colours were introduced default to grey (#595959). Assign
each a random palette colour so the chips render with variety, matching the Node
app. We cycle a shuffled palette so colours are well distributed rather than
clustering on one or two.
"""
import random

from django.db import migrations

PALETTE = [
    '#1d70b8', '#4c2c92', '#d4351c', '#00703c', '#28a197', '#912b88',
    '#f47738', '#b58840', '#5694ca', '#d53880', '#801650',
]


def forwards(apps, schema_editor):
    Tag = apps.get_model('roadmap', 'Tag')
    grey = list(Tag.objects.filter(colour='#595959').order_by('tag_type', 'name'))
    bag = []
    for tag in grey:
        if not bag:
            bag = PALETTE[:]
            random.shuffle(bag)
        tag.colour = bag.pop()
        tag.save(update_fields=['colour'])


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('roadmap', '0014_alter_tag_colour'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
