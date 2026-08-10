"""B2: durable objectives — one persistent lane across quarters.

The objective is owned by a team and reused across planning periods; the period
now lives on the KeyResult (kr.objective_set). Team roadmaps show all the team's
objectives (minus any hidden), and a single objective's KRs plot in their own
periods within one lane.
"""
import json
from datetime import date

from django.test import TestCase, Client

from roadmap import access
from roadmap.models import (
    Organisation, Team, ObjectiveSet, Objective, KeyResult, Roadmap,
)
from roadmap.views import _build_objective_swimlanes, _build_months, _build_virtual_timeline


class DurableSyncTests(TestCase):
    def setUp(self):
        self.org = Organisation.objects.create(name='MMO')
        self.team = Team.objects.create(organisation=self.org, name='Licensing')
        self.q3 = ObjectiveSet.objects.create(
            organisation=self.org, scope=ObjectiveSet.TEAM, team=self.team, name='FY26 Q3',
            start_date=date(2026, 7, 1), end_date=date(2026, 9, 30),
        )
        self.q4 = ObjectiveSet.objects.create(
            organisation=self.org, scope=ObjectiveSet.TEAM, team=self.team, name='FY26 Q4',
            start_date=date(2026, 10, 1), end_date=date(2026, 12, 31),
        )
        # One durable objective; its deprecated set is Q3 but it carries KRs in both.
        self.obj = Objective.objects.create(objective_set=self.q3, team=self.team, title='Speed up licensing')
        self.kr_q3 = KeyResult.objects.create(objective=self.obj, objective_set=self.q3, title='Q3 wait')
        self.kr_q4 = KeyResult.objects.create(objective=self.obj, objective_set=self.q4, title='Q4 wait')
        self.rm = Roadmap.objects.create(name='Licensing RM', owning_team=self.team, sync_okrs=True)
        self.rm.organisations.add(self.org)

    def test_team_roadmap_shows_all_team_objectives(self):
        # A second objective with no roadmap link at all still shows (durable).
        other = Objective.objects.create(objective_set=self.q4, team=self.team, title='Cut backlog')
        ids = access.roadmap_objective_ids(self.rm)
        self.assertIn(self.obj.pk, ids)
        self.assertIn(other.pk, ids)

    def test_hidden_objective_is_removed(self):
        self.rm.hidden_objectives.add(self.obj)
        self.assertNotIn(self.obj.pk, access.roadmap_objective_ids(self.rm))

    def test_one_objective_one_lane_with_both_periods(self):
        cols = _build_months(date(2026, 7, 1), date(2026, 12, 31))
        total_v = _build_virtual_timeline(cols)
        lanes = _build_objective_swimlanes(self.rm, [], cols, total_v)
        obj_lanes = [ln for ln in lanes if ln['name'] == 'Speed up licensing']
        self.assertEqual(len(obj_lanes), 1)  # one lane, not one-per-quarter
        bars = obj_lanes[0]['tracks']['metrics']['bars']
        starts = sorted(b['kr_start_iso'] for b in bars)
        self.assertEqual(starts, ['2026-07-01', '2026-10-01'])  # Q3 + Q4 windows

    def test_hidden_objective_absent_from_lanes(self):
        self.rm.hidden_objectives.add(self.obj)
        cols = _build_months(date(2026, 7, 1), date(2026, 12, 31))
        total_v = _build_virtual_timeline(cols)
        lanes = _build_objective_swimlanes(self.rm, [], cols, total_v)
        self.assertNotIn('Speed up licensing', [ln['name'] for ln in lanes])


class VisibilityApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.org = Organisation.objects.create(name='MMO')
        self.team = Team.objects.create(organisation=self.org, name='Licensing')
        self.set = ObjectiveSet.objects.create(
            organisation=self.org, scope=ObjectiveSet.TEAM, team=self.team, name='FY26 Q3',
            start_date=date(2026, 7, 1), end_date=date(2026, 9, 30),
        )
        self.a = Objective.objects.create(objective_set=self.set, team=self.team, title='A')
        self.b = Objective.objects.create(objective_set=self.set, team=self.team, title='B')
        self.rm = Roadmap.objects.create(name='RM', owning_team=self.team, sync_okrs=True)
        self.rm.organisations.add(self.org)

    def put(self, body):
        return self.client.put(
            f'/api/roadmaps/{self.rm.pk}/objectives-visibility/',
            data=json.dumps(body), content_type='application/json',
        )

    def test_hide_then_show(self):
        res = self.put({'hidden': [self.a.pk]})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(set(self.rm.hidden_objectives.values_list('pk', flat=True)), {self.a.pk})
        # Empty list shows everything again (deselect-all / select-all).
        self.put({'hidden': []})
        self.assertEqual(self.rm.hidden_objectives.count(), 0)

    def test_foreign_objective_ignored(self):
        other_team = Team.objects.create(organisation=self.org, name='Other')
        foreign = Objective.objects.create(team=other_team, title='Not mine')
        res = self.put({'hidden': [foreign.pk]})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.rm.hidden_objectives.count(), 0)  # stray id dropped

    def test_bad_body(self):
        self.assertEqual(self.put({'hidden': 'nope'}).status_code, 400)


class ReuseObjectiveTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.org = Organisation.objects.create(name='MMO')
        self.team = Team.objects.create(organisation=self.org, name='Licensing')
        self.q3 = ObjectiveSet.objects.create(
            organisation=self.org, scope=ObjectiveSet.TEAM, team=self.team, name='FY26 Q3',
            start_date=date(2026, 7, 1), end_date=date(2026, 9, 30),
        )
        self.q4 = ObjectiveSet.objects.create(
            organisation=self.org, scope=ObjectiveSet.TEAM, team=self.team, name='FY26 Q4',
            start_date=date(2026, 10, 1), end_date=date(2026, 12, 31),
        )
        self.obj = Objective.objects.create(objective_set=self.q3, team=self.team, title='Speed up')

    def _kr_formset_blank(self, prefix='key_results'):
        return {
            f'{prefix}-TOTAL_FORMS': '1', f'{prefix}-INITIAL_FORMS': '0',
            f'{prefix}-MIN_NUM_FORMS': '0', f'{prefix}-MAX_NUM_FORMS': '1000',
        }

    def test_reuse_existing_objective_tags_kr_with_authored_set(self):
        data = {
            'existing_objective': str(self.obj.pk),
            'objective_set': str(self.q4.pk),
            'title': '',
            'description': '',
            **self._kr_formset_blank(),
            'key_results-0-title': 'Q4 target',
            'key_results-0-start_value': '45',
            'key_results-0-target_value': '20',
            'key_results-0-current_value': '30',
            'key_results-0-direction': KeyResult.DECREASE,
            'key_results-0-status': KeyResult.ON_TRACK,
        }
        res = self.client.post(f'/objectives/new/?set={self.q4.pk}', data)
        self.assertEqual(res.status_code, 302)
        # No new objective was created — the existing one was reused.
        self.assertEqual(Objective.objects.filter(team=self.team).count(), 1)
        kr = KeyResult.objects.get(title='Q4 target')
        self.assertEqual(kr.objective, self.obj)
        self.assertEqual(kr.objective_set, self.q4)  # tagged with the authored period

    def test_set_page_shows_only_that_sets_key_results(self):
        # One durable objective with a KR in each set.
        kr_q3 = KeyResult.objects.create(objective=self.obj, objective_set=self.q3, title='Q3 KR')
        kr_q4 = KeyResult.objects.create(objective=self.obj, objective_set=self.q4, title='Q4 KR')

        res_q4 = self.client.get(f'/objectives/sets/{self.q4.pk}/')
        card_krs = {o.pk: o.card_key_results for o in res_q4.context['objectives']}
        self.assertEqual([k.pk for k in card_krs[self.obj.pk]], [kr_q4.pk])
        self.assertContains(res_q4, 'Q4 KR')
        self.assertNotContains(res_q4, 'Q3 KR')  # the other set's KR doesn't leak in

        res_q3 = self.client.get(f'/objectives/sets/{self.q3.pk}/')
        self.assertContains(res_q3, 'Q3 KR')
        self.assertNotContains(res_q3, 'Q4 KR')

    def test_reused_objective_counts_on_team_page_set_card(self):
        # obj's deprecated set is Q3; give it a KR in Q4 (as reuse does).
        KeyResult.objects.create(objective=self.obj, objective_set=self.q4, title='Q4 KR')
        res = self.client.get(f'/teams/{self.team.pk}/')
        counts = {s.name: s.durable_objective_count for s in res.context['team_sets']}
        self.assertEqual(counts['FY26 Q4'], 1)  # reused objective now counts under Q4
        self.assertEqual(counts['FY26 Q3'], 1)  # still counts under its original set


class MigrationBackfillTests(TestCase):
    """0026 copies each objective's (deprecated) set down onto its key results.

    Runs the migration's `forward` against the current schema (SQLite can't
    reverse the schema migration mid-transaction), seeding a prod-shape objective
    whose KR has no period yet.
    """

    def test_backfill_sets_kr_objective_set(self):
        import importlib
        from django.apps import apps
        migration = importlib.import_module('roadmap.migrations.0026_backfill_kr_objective_set')

        org = Organisation.objects.create(name='MMO')
        team = Team.objects.create(organisation=org, name='Licensing')
        oset = ObjectiveSet.objects.create(
            organisation=org, scope=ObjectiveSet.TEAM, team=team, name='Q3')
        obj = Objective.objects.create(objective_set=oset, team=team, title='Speed up')
        # A key result with no period yet (pre-B2 shape).
        kr = KeyResult.objects.create(objective=obj, title='wait')
        self.assertIsNone(kr.objective_set_id)

        migration.forward(apps, None)

        kr.refresh_from_db()
        self.assertEqual(kr.objective_set_id, oset.pk)

    def test_backfill_adopts_set_team_for_teamless_objective(self):
        import importlib
        from django.apps import apps
        migration = importlib.import_module('roadmap.migrations.0026_backfill_kr_objective_set')

        org = Organisation.objects.create(name='MMO')
        team = Team.objects.create(organisation=org, name='Data & Digital')
        oset = ObjectiveSet.objects.create(
            organisation=org, scope=ObjectiveSet.TEAM, team=team, name='Q3')
        # Legacy shape: an objective in a team set but with no team of its own.
        in_set = Objective.objects.create(objective_set=oset, team=None, title='obj 1')
        # A genuinely standalone objective (no set) must stay team-less.
        standalone = Objective.objects.create(objective_set=None, team=None, title='loose')

        migration.forward(apps, None)

        in_set.refresh_from_db()
        standalone.refresh_from_db()
        self.assertEqual(in_set.team_id, team.pk)   # adopted the set's team
        self.assertIsNone(standalone.team_id)       # left alone
