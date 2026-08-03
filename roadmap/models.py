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


class Team(models.Model):
    """A team within an organisation — the owner of OKRs (objective sets,
    objectives, key results) and of roadmaps. A team is a higher level of
    organisation than a squad (which groups delivery items within a roadmap).

    NOTE: pm-roadmap has no authentication yet, so teams have no user members
    or creator. Ownership/scoping is by team identity alone; edit access is
    open. When auth arrives, member/owner fields can be reintroduced.
    """
    organisation = models.ForeignKey(
        Organisation, on_delete=models.CASCADE, related_name='teams'
    )
    name = models.CharField(max_length=120)
    mission = models.TextField(blank=True)
    vision = models.TextField(blank=True)
    sort_order = models.IntegerField(default=0, help_text='Manual ordering (lower = first)')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sort_order', 'name']
        constraints = [
            models.UniqueConstraint(fields=['organisation', 'name'], name='unique_team_per_org'),
        ]

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
        (ORGANISATION, 'Squad'),
        (CATEGORY, 'Item Category'),
    ]
    # Roadmap-scoped types (organisation/Squads, objective/Service objectives) set
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
        help_text='Set for roadmap-scoped tags (squads, objectives); null for central tags.',
    )
    # For squad tags (tag_type=organisation): the higher-level Team this squad
    # rolls up to. Null for other tag types and unmigrated squads.
    team = models.ForeignKey(
        'Team', on_delete=models.SET_NULL, null=True, blank=True, related_name='squad_tags',
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
    # The owning team (first-class Team entity). OKRs sync only between a team
    # and its own roadmaps. Distinct from the legacy free-text `team` label above.
    owning_team = models.ForeignKey(
        'Team', on_delete=models.SET_NULL, null=True, blank=True, related_name='roadmaps',
    )
    # When true, the owning team's (or, for teamless roadmaps, the org's) objective
    # sets surface as swim lanes on this roadmap. See roadmap/access.py.
    sync_okrs = models.BooleanField(default=True)
    # Objective sets explicitly linked to this roadmap (in addition to synced ones).
    objective_sets = models.ManyToManyField('ObjectiveSet', blank=True, related_name='roadmaps')
    # Standalone objectives (not in a set) attached directly to this roadmap.
    objectives = models.ManyToManyField('Objective', blank=True, related_name='applied_roadmaps')
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
    # The objective this item belongs to. For metric items (key results) this is
    # the parent objective; assigning it backs the item with a KeyResult (see
    # roadmap/api.py _ensure_key_result). SET_NULL so items survive objective deletion.
    objective = models.ForeignKey(
        'Objective', on_delete=models.SET_NULL, null=True, blank=True, related_name='items',
    )
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


class ObjectiveSet(models.Model):
    """A named collection of objectives (an OKR cycle / planning period) with a
    timeframe. Scoped to an organisation (group) or a team.

    Ported from myproduct.pro without the user `owner` field — pm-roadmap has no
    auth, so a set is owned by its team/organisation alone.
    """
    GROUP = 'group'
    TEAM = 'team'
    SCOPE_CHOICES = [
        (GROUP, 'Organisation'),
        (TEAM, 'Team'),
    ]

    scope = models.CharField(max_length=10, choices=SCOPE_CHOICES, default=GROUP)
    organisation = models.ForeignKey(
        Organisation, on_delete=models.CASCADE, related_name='objective_sets'
    )
    team = models.ForeignKey(
        Team, on_delete=models.CASCADE, null=True, blank=True, related_name='objective_sets'
    )
    name = models.CharField(max_length=120, help_text='e.g. "FY26 Q1"')
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    # How the timeframe was chosen: quarterly / annual presets, or null for a custom range.
    QUARTERLY = 'quarterly'
    ANNUAL = 'annual'
    PERIOD_CHOICES = [
        (QUARTERLY, 'Quarterly'),
        (ANNUAL, 'Annual'),
    ]
    period = models.CharField(
        max_length=10, choices=PERIOD_CHOICES, null=True, blank=True,
        help_text='quarterly / annual when created from a preset; blank for a custom date range.',
    )
    archived = models.BooleanField(default=False, help_text='Hidden from active lists; kept for reference.')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_date', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['organisation', 'scope', 'team', 'name'],
                name='unique_objective_set_scope_name',
            ),
            models.CheckConstraint(
                check=(
                    models.Q(scope='group', team__isnull=True)
                    | models.Q(scope='team', team__isnull=False)
                ),
                name='objective_set_scope_team_consistency',
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def period_label(self):
        """User-facing pill text for the set's timeframe kind."""
        if self.period == self.QUARTERLY:
            return 'Quarterly'
        if self.period == self.ANNUAL:
            return 'Annual'
        return 'Custom timeframe'


class Objective(models.Model):
    """A first-class objective (OKR). Owns a set of Key Results and can be synced
    onto its team's roadmaps as a swim lane.

    Ported from myproduct.pro without the user `owner` field.
    """
    objective_set = models.ForeignKey(
        'ObjectiveSet', on_delete=models.SET_NULL, null=True, blank=True, related_name='objectives'
    )
    team = models.ForeignKey(
        'Team', on_delete=models.SET_NULL, null=True, blank=True, related_name='objectives'
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    sort_order = models.IntegerField(
        default=0, help_text='Manual swim-lane order on roadmaps (lower = higher up)',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class KeyResult(models.Model):
    """A measurable key result under an objective. On a roadmap it is backed by a
    metric Item for timeline placement (see roadmap/api.py _ensure_key_result)."""
    INCREASE = 'increase'
    DECREASE = 'decrease'
    DIRECTION_CHOICES = [
        (INCREASE, 'Increase (higher is better)'),
        (DECREASE, 'Decrease (lower is better)'),
    ]

    ON_TRACK = 'on_track'
    AT_RISK = 'at_risk'
    OFF_TRACK = 'off_track'
    ACHIEVED = 'achieved'
    STATUS_CHOICES = [
        (ON_TRACK, 'On track'),
        (AT_RISK, 'At risk'),
        (OFF_TRACK, 'Off track'),
        (ACHIEVED, 'Achieved'),
    ]

    objective = models.ForeignKey(
        'Objective', on_delete=models.CASCADE, related_name='key_results'
    )
    title = models.CharField(max_length=200)
    unit = models.CharField(max_length=20, blank=True, help_text='e.g. %, £, users')
    start_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    target_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    current_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES, default=INCREASE)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=ON_TRACK)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'created_at']

    def __str__(self):
        return self.title

    @property
    def progress(self):
        """Percent complete (0–100). Works for both directions because the sign
        of (current−start) and (target−start) cancels out."""
        span = self.target_value - self.start_value
        if span == 0:
            return 100 if self.current_value == self.target_value else 0
        pct = (self.current_value - self.start_value) / span * 100
        return max(0, min(100, round(float(pct))))
