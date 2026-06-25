from datetime import date

from django.test import TestCase, Client

from roadmap.models import Organisation, Roadmap, Item, Tag
from roadmap.views import (
    _build_months, _build_quarters, _build_hybrid, _build_virtual_timeline,
    _date_to_virtual_pct, _item_to_bar,
)


class ColumnBuilderTests(TestCase):
    def test_build_months_count_and_labels(self):
        cols = _build_months(date(2026, 1, 1), date(2026, 3, 31))
        self.assertEqual(len(cols), 3)
        self.assertEqual([c['label'] for c in cols], ['Jan 2026', 'Feb 2026', 'Mar 2026'])
        self.assertTrue(all(c['col_type'] == 'month' for c in cols))

    def test_build_quarters(self):
        cols = _build_quarters(date(2026, 1, 1), date(2026, 12, 31))
        self.assertEqual([c['label'] for c in cols], ['Q1 2026', 'Q2 2026', 'Q3 2026', 'Q4 2026'])

    def test_build_hybrid_nonempty(self):
        cols = _build_hybrid(date(2026, 1, 1), date(2028, 12, 31))
        self.assertGreater(len(cols), 0)

    def test_virtual_timeline_widths_sum_to_100(self):
        cols = _build_months(date(2026, 1, 1), date(2026, 6, 30))
        _build_virtual_timeline(cols)
        self.assertAlmostEqual(sum(c['width_pct'] for c in cols), 100, places=0)

    def test_item_to_bar_within_bounds(self):
        cols = _build_months(date(2026, 1, 1), date(2026, 12, 31))
        total_v = _build_virtual_timeline(cols)
        rm = Roadmap.objects.create(name='RM')
        item = Item.objects.create(
            roadmap=rm, item_type=Item.ACTIVITY, title='A',
            start_date=date(2026, 3, 1), end_date=date(2026, 6, 30),
        )
        bar = _item_to_bar(item, cols, total_v)
        self.assertGreaterEqual(bar['left_pct'], 0)
        self.assertLessEqual(bar['left_pct'] + bar['width_pct'], 100.01)

    def test_item_without_dates_has_no_bar(self):
        cols = _build_months(date(2026, 1, 1), date(2026, 12, 31))
        total_v = _build_virtual_timeline(cols)
        rm = Roadmap.objects.create(name='RM')
        item = Item.objects.create(roadmap=rm, item_type=Item.ACTIVITY, title='No dates')
        self.assertIsNone(_item_to_bar(item, cols, total_v))


class DetailContextTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.group = Roadmap.objects.create(name='Group', roadmap_type=Roadmap.GROUP)
        self.service = Roadmap.objects.create(name='Service', roadmap_type=Roadmap.SERVICE)

    def test_group_roadmap_uses_gov_objectives(self):
        ctx = self.client.get(f'/{self.group.pk}/').context
        self.assertEqual(ctx['objective_type'], 'gov_objective')
        self.assertEqual(ctx['objective_label'], 'Gov Objectives')

    def test_service_roadmap_uses_objectives(self):
        ctx = self.client.get(f'/{self.service.pk}/').context
        self.assertEqual(ctx['objective_type'], 'objective')
        self.assertEqual(ctx['objective_label'], 'Objectives')

    def test_group_by_falls_back_to_outcome(self):
        ctx = self.client.get(f'/{self.group.pk}/?group_by=nonsense').context
        self.assertEqual(ctx['group_by'], 'outcome')

    def test_group_by_organisation_respected(self):
        ctx = self.client.get(f'/{self.group.pk}/?group_by=organisation').context
        self.assertEqual(ctx['group_by'], 'organisation')

    def test_header_pills_reflect_membership(self):
        outcome = Tag.objects.create(name='Grow', tag_type=Tag.OUTCOME)
        self.group.tags.add(outcome)
        ctx = self.client.get(f'/{self.group.pk}/').context
        self.assertEqual([t.name for t in ctx['roadmap_outcome_tags']], ['Grow'])


class ListViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        Roadmap.objects.create(name='Alpha')
        Roadmap.objects.create(name='Beta')

    def test_list_renders_with_context(self):
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        self.assertIn('roadmaps_json', res.context)
        self.assertIn('organisations', res.context)
