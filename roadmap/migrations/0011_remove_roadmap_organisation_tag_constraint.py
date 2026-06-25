from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('roadmap', '0010_backfill_orgs_teams_tag_scoping'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='roadmap',
            name='organisation',
        ),
        migrations.AddConstraint(
            model_name='tag',
            constraint=models.UniqueConstraint(
                fields=['name', 'tag_type', 'roadmap'],
                name='unique_tag_name_type_roadmap',
            ),
        ),
    ]
