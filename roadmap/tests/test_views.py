from datetime import date

from django.test import TestCase, Client

from roadmap.models import Organisation, Roadmap, Item, Tag
from roadmap.views import (
    _build_months, _build_quarters, _build_hybrid, _build_virtual_timeline,
    _date_to_virtual_pct, _item_to_bar, _stack_milestones,
)


class _FakeItem:
    def __init__(self, title):
        self.title = title


def _ms(title, left_pct):
    return {'item': _FakeItem(title), 'left_pct': left_pct}


class MilestoneStackingTests(TestCase):
    TIMELINE_PX = 1200  # ~12 months at 100px

    def test_close_milestones_stack_on_separate_rows(self):
        bars, rows = _stack_milestones(
            [_ms('Alpha Release Candidate', 40), _ms('Beta Release Candidate', 42)],
            self.TIMELINE_PX,
        )
        self.assertEqual(rows, 2)
        self.assertEqual({b['row'] for b in bars}, {0, 1})

    def test_distant_milestones_share_a_row(self):
        bars, rows = _stack_milestones(
            [_ms('Q1 Review', 5), _ms('Q4 Review', 95)],
            self.TIMELINE_PX,
        )
        self.assertEqual(rows, 1)
        self.assertTrue(all(b['row'] == 0 for b in bars))

    def test_row_count_never_zero_for_empty(self):
        bars, rows = _stack_milestones([], self.TIMELINE_PX)
        self.assertEqual((bars, rows), ([], 0))


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

    def test_group_roadmap_defaults_to_outcome(self):
        ctx = self.client.get(f'/{self.group.pk}/').context
        self.assertEqual(ctx['group_by'], 'outcome')

    def test_service_roadmap_defaults_to_objectives(self):
        ctx = self.client.get(f'/{self.service.pk}/').context
        self.assertEqual(ctx['group_by'], 'objective')

    def test_explicit_group_by_overrides_default_on_service(self):
        ctx = self.client.get(f'/{self.service.pk}/?group_by=outcome').context
        self.assertEqual(ctx['group_by'], 'outcome')

    def test_group_by_organisation_respected(self):
        ctx = self.client.get(f'/{self.group.pk}/?group_by=organisation').context
        self.assertEqual(ctx['group_by'], 'organisation')

    def test_header_pills_reflect_membership(self):
        outcome = Tag.objects.create(name='Grow', tag_type=Tag.OUTCOME)
        self.group.tags.add(outcome)
        ctx = self.client.get(f'/{self.group.pk}/').context
        self.assertEqual([t.name for t in ctx['roadmap_outcome_tags']], ['Grow'])

    def test_lanes_ordered_by_sort_order(self):
        from datetime import date
        zeta = Tag.objects.create(name='Zeta', tag_type=Tag.OUTCOME, sort_order=0)
        alpha = Tag.objects.create(name='Alpha', tag_type=Tag.OUTCOME, sort_order=1)
        for tag in (zeta, alpha):
            item = Item.objects.create(
                roadmap=self.group, item_type=Item.ACTIVITY, title=f'{tag.name} item',
                start_date=date(2026, 7, 1), end_date=date(2026, 8, 1),
            )
            item.tags.add(tag)
        lanes = self.client.get(f'/{self.group.pk}/?group_by=outcome').context['lanes']
        names = [l['name'] for l in lanes]
        # Zeta (sort_order 0) comes before Alpha (sort_order 1), despite the name.
        self.assertLess(names.index('Zeta'), names.index('Alpha'))


class ListViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        Roadmap.objects.create(name='Alpha')
        Roadmap.objects.create(name='Beta')

    def test_list_renders_with_context(self):
        res = self.client.get('/roadmaps/')
        self.assertEqual(res.status_code, 200)
        self.assertIn('roadmaps_json', res.context)
        self.assertIn('organisations', res.context)

    def test_root_redirects_to_teams(self):
        res = self.client.get('/')
        self.assertRedirects(res, '/teams/', fetch_redirect_response=False)


class DetailFilterTests(TestCase):
    """Date-window + item-type (track) filters on the roadmap detail view."""

    def setUp(self):
        self.client = Client()
        self.rm = Roadmap.objects.create(name='Filters RM', roadmap_type=Roadmap.SERVICE)
        Item.objects.create(roadmap=self.rm, item_type=Item.ACTIVITY, title='A1',
                            start_date=date(2026, 8, 1), end_date=date(2026, 9, 30))

    def test_track_filter_limits_visible_tracks(self):
        res = self.client.get(f'/{self.rm.pk}/?tracks=activity')
        self.assertEqual(res.context['visible_tracks'], {'activity'})
        self.assertEqual(res.context['selected_tracks_str'], 'activity')
        self.assertEqual(res.context['first_visible_track'], 'activity')

    def test_all_tracks_selected_is_no_filter(self):
        res = self.client.get(f'/{self.rm.pk}/?tracks=activity,milestone,metric')
        self.assertEqual(res.context['visible_tracks'], {'activity', 'milestone', 'metric'})
        self.assertEqual(res.context['selected_tracks_str'], '')  # all == no filter

    def test_no_track_param_shows_all(self):
        res = self.client.get(f'/{self.rm.pk}/')
        self.assertEqual(res.context['visible_tracks'], {'activity', 'milestone', 'metric'})

    def test_custom_date_window_applied(self):
        res = self.client.get(f'/{self.rm.pk}/?start=2027-01-01&end=2027-06-30')
        self.assertEqual(res.context['range_start_iso'], '2027-01-01')
        self.assertEqual(res.context['range_end_iso'], '2027-06-30')
        self.assertTrue(res.context['custom_range'])

    def test_date_window_clamped_to_range(self):
        # 1990 is far before range_min (today-1yr); it clamps up to range_min's
        # month (start snaps to day 1, so compare at month granularity).
        res = self.client.get(f'/{self.rm.pk}/?start=1990-01-01')
        self.assertEqual(res.context['range_start_iso'][:7], res.context['range_min_iso'][:7])
