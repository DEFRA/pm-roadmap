import random

from django.db import models


# Palette for tag chips — accessible GDS colours that read well both as text on a
# light background (header pills) and as a fill behind white text (selected chips).
TAG_COLOUR_PALETTE = [
    '#1d70b8',  # blue
    '#4c2c92',  # purple
    '#d4351c',  # red
    '#00703c',  # green
    '#28a197',  # turquoise
    '#912b88',  # bright purple
    '#f47738',  # orange
    '#b58840',  # brown
    '#5694ca',  # light blue
    '#d53880',  # pink
    '#801650',  # magenta (brand)
]


def random_tag_colour():
    """A random colour from the palette — the default for new tags."""
    return random.choice(TAG_COLOUR_PALETTE)


class Organisation(models.Model):
    """A delivery organisation (e.g. MMO, EA). Roadmaps belong to one or more."""
    name = models.CharField(max_length=200, unique=True)
    abbreviation = models.CharField(max_length=20, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Tag(models.Model):
    OUTCOME = 'outcome'
    GOV_OBJECTIVE = 'gov_objective'
    OBJECTIVE = 'objective'
    ORGANISATION = 'organisation'
    CATEGORY = 'category'
    TAG_TYPE_CHOICES = [
        (OUTCOME, 'Defra Outcome'),
        (GOV_OBJECTIVE, 'Gov Objective'),
        (OBJECTIVE, 'Objective'),
        (ORGANISATION, 'Team'),
        (CATEGORY, 'Item Category'),
    ]
    # Roadmap-scoped types (organisation/Teams, objective/Service objectives) set
    # this to the owning roadmap. Central types (gov_objective, outcome, category)
    # leave it null and are shared across all roadmaps.
    SCOPED_TYPES = (ORGANISATION, OBJECTIVE)

    name = models.CharField(max_length=100)
    tag_type = models.CharField(max_length=20, choices=TAG_TYPE_CHOICES)
    colour = models.CharField(max_length=7, default=random_tag_colour, help_text='Hex colour, e.g. #1d70b8')
    description = models.TextField(blank=True)
    link = models.URLField(blank=True, help_text='Optional third-party link with more information')
    sort_order = models.IntegerField(default=0, help_text='Manual swim-lane order (lower = higher up)')
    roadmap = models.ForeignKey(
        'Roadmap',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='scoped_tags',
        help_text='Set for roadmap-scoped tags (teams, objectives); null for central tags.',
    )

    class Meta:
        ordering = ['tag_type', 'name']
        constraints = [
            # Enforces uniqueness for roadmap-scoped tags: the same team /
            # objective name can't be duplicated within one roadmap, but is
            # allowed across different roadmaps. NOTE: for central tags
            # (roadmap is NULL) SQLite treats NULLs as distinct, so this does
            # NOT block duplicate central tags — that uniqueness is enforced at
            # the API layer (tags_collection returns 409 on a duplicate).
            models.UniqueConstraint(
                fields=['name', 'tag_type', 'roadmap'],
                name='unique_tag_name_type_roadmap',
            ),
        ]

    def __str__(self):
        return f'{self.name} ({self.get_tag_type_display()})'


class Roadmap(models.Model):
    GROUP = 'group'
    SERVICE = 'service'
    ROADMAP_TYPE_CHOICES = [
        (GROUP, 'Group'),
        (SERVICE, 'Service/Product'),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    team = models.CharField(max_length=200, blank=True, help_text='The owning team, e.g. "Delivery Group"')
    organisations = models.ManyToManyField('Organisation', blank=True, related_name='roadmaps')
    roadmap_type = models.CharField(
        max_length=20,
        choices=ROADMAP_TYPE_CHOICES,
        default=GROUP,
        help_text='Group roadmaps use Government Objectives; Service roadmaps use Objectives.',
    )
    mission = models.TextField(blank=True)
    vision = models.TextField(blank=True)
    tags = models.ManyToManyField('Tag', blank=True, related_name='roadmaps')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Item(models.Model):
    ACTIVITY = 'activity'
    MILESTONE = 'milestone'
    METRIC = 'metric'
    ITEM_TYPE_CHOICES = [
        (ACTIVITY, 'Activity'),
        (MILESTONE, 'Milestone'),
        (METRIC, 'Metric'),
    ]

    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'
    CRITICAL = 'critical'
    PRIORITY_CHOICES = [
        (LOW, 'Low'),
        (MEDIUM, 'Medium'),
        (HIGH, 'High'),
        (CRITICAL, 'Critical'),
    ]

    SIZE_CHOICES = [
        ('S', 'S'),
        ('M', 'M'),
        ('L', 'L'),
        ('XL', 'XL'),
        ('XXL', 'XXL'),
    ]

    roadmap = models.ForeignKey(Roadmap, on_delete=models.CASCADE, related_name='items')
    item_type = models.CharField(max_length=20, choices=ITEM_TYPE_CHOICES)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    tags = models.ManyToManyField(Tag, blank=True, related_name='items')

    # Activity-specific fields
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, blank=True)
    size = models.CharField(max_length=5, choices=SIZE_CHOICES, blank=True)
    prd_link = models.URLField(blank=True)
    backlog_link = models.URLField(blank=True)

    # Date range – all item types can have dates for timeline placement
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    # Milestones and metrics can link to activities
    linked_activities = models.ManyToManyField(
        'self',
        symmetrical=False,
        blank=True,
        related_name='linked_milestones_metrics',
        limit_choices_to={'item_type': ACTIVITY},
    )

    class Meta:
        ordering = ['start_date', 'title']

    def __str__(self):
        return f'[{self.get_item_type_display()}] {self.title}'

    @property
    def outcome_tags(self):
        return self.tags.filter(tag_type=Tag.OUTCOME)

    @property
    def organisation_tags(self):
        return self.tags.filter(tag_type=Tag.ORGANISATION)

    @property
    def category_tags(self):
        return self.tags.filter(tag_type=Tag.CATEGORY)
