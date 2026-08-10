"""B1: key results get their own dates + drag/resize + snap-to-set + warning."""
import json
from datetime import date

from django.test import TestCase, Client

from roadmap.models import (
    Organisation, Team, ObjectiveSet, Objective, KeyResult, Roadmap,
)
from roadmap.views import _kr_bar, _build_months, _build_virtual_timeline


class KrBarPlacementTests(TestCase):
    def setUp(self):
        self.org = Organisation.objects.create(name='MMO')
        self.team = Team.objects.create(organisation=self.org, name='Licensing')
        self.set = ObjectiveSet.objects.create(
            organisation=self.org, scope=ObjectiveSet.TEAM, team=self.team, name='FY26 Q3',
            start_date=date(2026, 7, 1), end_date=date(2026, 9, 30),
        )
        self.obj = Objective.objects.create(objective_set=self.set, team=self.team, title='Speed up')
        self.cols = _build_months(date(2026, 7, 1), date(2026, 12, 31))
        self.total_v = _build_virtual_timeline(self.cols)

    def test_kr_without_dates_spans_set_period(self):
        kr = KeyResult.objects.create(objective=self.obj, title='KR')
        bar = _kr_bar(kr, self.set, self.cols, self.total_v)
        self.assertEqual(bar['kr_start_iso'], '2026-07-01')
        self.assertEqual(bar['kr_end_iso'], '2026-09-30')

    def test_kr_with_own_dates_uses_them(self):
        kr = KeyResult.objects.create(objective=self.obj, title='KR',
                                      start_date=date(2026, 10, 1), end_date=date(2026, 11, 30))
        bar = _kr_bar(kr, self.set, self.cols, self.total_v)
        self.assertEqual(bar['kr_start_iso'], '2026-10-01')
        self.assertEqual(bar['kr_end_iso'], '2026-11-30')
        # left is further right than the set-period bar
        self.assertGreater(bar['left_pct'], 0)


class KrApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.obj = Objective.objects.create(title='O')
        self.kr = KeyResult.objects.create(objective=self.obj, title='KR')

    def put(self, url, payload):
        return self.client.put(url, data=json.dumps(payload), content_type='application/json')

    def test_put_sets_dates_and_row(self):
        res = self.put(f'/api/key-results/{self.kr.pk}/',
                       {'start_date': '2026-10-01', 'end_date': '2026-11-30', 'row': 2})
        self.assertEqual(res.status_code, 200)
        self.kr.refresh_from_db()
        self.assertEqual((self.kr.start_date, self.kr.end_date, self.kr.row),
                         (date(2026, 10, 1), date(2026, 11, 30), 2))

    def test_put_empty_dates_clears_to_inherit(self):
        self.kr.start_date = date(2026, 10, 1); self.kr.end_date = date(2026, 11, 30); self.kr.save()
        self.put(f'/api/key-results/{self.kr.pk}/', {'start_date': '', 'end_date': ''})
        self.kr.refresh_from_db()
        self.assertIsNone(self.kr.start_date)
        self.assertIsNone(self.kr.end_date)


class KrWarningAndSnapTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.org = Organisation.objects.create(name='MMO')
        self.team = Team.objects.create(organisation=self.org, name='Licensing')
        self.set = ObjectiveSet.objects.create(
            organisation=self.org, scope=ObjectiveSet.TEAM, team=self.team, name='FY26 Q3',
            start_date=date(2026, 7, 1), end_date=date(2026, 9, 30),
        )
        self.obj = Objective.objects.create(objective_set=self.set, team=self.team, title='Speed up')

    def test_aligned_kr_not_flagged(self):
        KeyResult.objects.create(objective=self.obj, objective_set=self.set, title='In window',
                                 start_date=date(2026, 7, 15), end_date=date(2026, 8, 15))
        res = self.client.get(f'/objectives/sets/{self.set.pk}/')
        self.assertEqual(res.context['misaligned_krs'], [])

    def test_misaligned_kr_flagged_and_snap_clears_it(self):
        kr = KeyResult.objects.create(objective=self.obj, objective_set=self.set, title='Drifted',
                                      start_date=date(2026, 10, 1), end_date=date(2026, 11, 30))
        res = self.client.get(f'/objectives/sets/{self.set.pk}/')
        self.assertIn(kr, res.context['misaligned_krs'])
        self.assertContains(res, 'Snap to set dates')
        # snap-back clears the custom dates
        self.client.post(f'/key-results/{kr.pk}/snap-to-set/')
        kr.refresh_from_db()
        self.assertIsNone(kr.start_date)
        self.assertIsNone(kr.end_date)
