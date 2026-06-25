from django.db import IntegrityError, transaction
from django.test import TestCase

from roadmap.models import (
    Organisation, Roadmap, Item, Tag, TAG_COLOUR_PALETTE, random_tag_colour,
)


class TagScopingTests(TestCase):
    def setUp(self):
        self.r1 = Roadmap.objects.create(name='R1', roadmap_type=Roadmap.SERVICE)
        self.r2 = Roadmap.objects.create(name='R2', roadmap_type=Roadmap.SERVICE)

    def test_same_scoped_name_allowed_on_different_roadmaps(self):
        Tag.objects.create(name='Licensing', tag_type=Tag.ORGANISATION, roadmap=self.r1)
        # Same team name on a different roadmap must be allowed.
        Tag.objects.create(name='Licensing', tag_type=Tag.ORGANISATION, roadmap=self.r2)
        self.assertEqual(Tag.objects.filter(name='Licensing').count(), 2)

    def test_duplicate_scoped_tag_same_roadmap_rejected(self):
        Tag.objects.create(name='Ops', tag_type=Tag.ORGANISATION, roadmap=self.r1)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Tag.objects.create(name='Ops', tag_type=Tag.ORGANISATION, roadmap=self.r1)

    def test_central_tags_have_no_roadmap(self):
        tag = Tag.objects.create(name='Grow Revenue', tag_type=Tag.OUTCOME)
        self.assertIsNone(tag.roadmap_id)

    def test_scoped_types_constant(self):
        self.assertEqual(set(Tag.SCOPED_TYPES), {Tag.ORGANISATION, Tag.OBJECTIVE})


class TagColourTests(TestCase):
    def test_random_colour_in_palette(self):
        for _ in range(20):
            self.assertIn(random_tag_colour(), TAG_COLOUR_PALETTE)

    def test_default_colour_assigned_from_palette(self):
        # Created without an explicit colour -> field default fires.
        tag = Tag.objects.create(name='Auto', tag_type=Tag.OUTCOME)
        self.assertIn(tag.colour, TAG_COLOUR_PALETTE)

    def test_explicit_colour_respected(self):
        tag = Tag.objects.create(name='Fixed', tag_type=Tag.OUTCOME, colour='#123456')
        self.assertEqual(tag.colour, '#123456')


class RoadmapModelTests(TestCase):
    def test_roadmap_type_display(self):
        group = Roadmap.objects.create(name='G', roadmap_type=Roadmap.GROUP)
        service = Roadmap.objects.create(name='S', roadmap_type=Roadmap.SERVICE)
        self.assertEqual(group.get_roadmap_type_display(), 'Group')
        self.assertEqual(service.get_roadmap_type_display(), 'Service/Product')

    def test_default_roadmap_type_is_group(self):
        self.assertEqual(Roadmap.objects.create(name='D').roadmap_type, Roadmap.GROUP)

    def test_organisations_m2m(self):
        rm = Roadmap.objects.create(name='RM')
        org = Organisation.objects.create(name='MMO', abbreviation='MMO')
        rm.organisations.add(org)
        self.assertEqual(list(rm.organisations.all()), [org])


class ItemPropertyTests(TestCase):
    def setUp(self):
        self.rm = Roadmap.objects.create(name='RM')
        self.outcome = Tag.objects.create(name='O', tag_type=Tag.OUTCOME)
        self.team = Tag.objects.create(name='T', tag_type=Tag.ORGANISATION, roadmap=self.rm)
        self.cat = Tag.objects.create(name='C', tag_type=Tag.CATEGORY)
        self.item = Item.objects.create(roadmap=self.rm, item_type=Item.ACTIVITY, title='A')
        self.item.tags.set([self.outcome, self.team, self.cat])

    def test_tag_type_properties_filter_correctly(self):
        self.assertEqual(list(self.item.outcome_tags), [self.outcome])
        self.assertEqual(list(self.item.organisation_tags), [self.team])
        self.assertEqual(list(self.item.category_tags), [self.cat])
