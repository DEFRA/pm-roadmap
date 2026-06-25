import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('roadmap', '0008_set_tag_colour_to_grey'),
    ]

    operations = [
        migrations.CreateModel(
            name='Organisation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, unique=True)),
                ('abbreviation', models.CharField(blank=True, max_length=20)),
                ('description', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ['name']},
        ),
        migrations.AddField(
            model_name='roadmap',
            name='team',
            field=models.CharField(blank=True, help_text='The owning team, e.g. "Delivery Group"', max_length=200),
        ),
        migrations.AddField(
            model_name='roadmap',
            name='organisations',
            field=models.ManyToManyField(blank=True, related_name='roadmaps', to='roadmap.organisation'),
        ),
        migrations.AddField(
            model_name='roadmap',
            name='roadmap_type',
            field=models.CharField(
                choices=[('group', 'Group'), ('service', 'Service/Product')],
                default='group',
                help_text='Group roadmaps use Government Objectives; Service roadmaps use Objectives.',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='tag',
            name='roadmap',
            field=models.ForeignKey(
                blank=True,
                help_text='Set for roadmap-scoped tags (teams, objectives); null for central tags.',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='scoped_tags',
                to='roadmap.roadmap',
            ),
        ),
        migrations.AlterField(
            model_name='tag',
            name='tag_type',
            field=models.CharField(
                choices=[
                    ('outcome', 'Defra Outcome'),
                    ('gov_objective', 'Gov Objective'),
                    ('objective', 'Objective'),
                    ('organisation', 'Team'),
                    ('category', 'Item Category'),
                ],
                max_length=20,
            ),
        ),
    ]
