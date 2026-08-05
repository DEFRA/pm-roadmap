"""The OKR backfill (migration 0020 / roadmap.okr_backfill.run_okr_backfill).

Seeds old-shape tag data on the real models and runs the backfill directly — the
final schema is non-destructive (all tag fields still exist), so the real models
stand in for the historical ones.
"""
from django.apps import apps as global_apps
from django.test import TestCase

from roadmap.okr_backfill import run_okr_backfill
from roadmap.models import (
    Organisation, Team, Roadmap, Tag, Item, Objective, KeyResult,
)


def _backfill():
    run_okr_backfill(lambda name: global_apps.get_model('roadmap', name))


class OKRBackfillTests(TestCase):
    def setUp(self):
        self.org = Organisation.objects.create(name='Marine Management Org')
        self.rm = Roadmap.objects.create(name='Licensing RM', roadmap_type=Roadmap.SERVICE)
        self.rm.organisations.add(self.org)
        # Old-shape objectives + squads as tags, scoped to the roadmap.
        self.obj_tag = Tag.objects.create(name='Reduce wait times', tag_type=Tag.OBJECTIVE,
                                          roadmap=self.rm, description='faster licences')
        self.squad_tag = Tag.objects.create(name='Ops squad', tag_type=Tag.ORGANISATION, roadmap=self.rm)
        # A metric item (key result) + an activity, both tagged to the objective.
        self.metric = Item.objects.create(roadmap=self.rm, item_type=Item.METRIC, title='Median wait (days)')
        self.metric.tags.add(self.obj_tag)
        self.activity = Item.objects.create(roadmap=self.rm, item_type=Item.ACTIVITY, title='Build portal')
        self.activity.tags.add(self.obj_tag, self.squad_tag)

    def test_backfill_creates_team_objective_and_key_result(self):
        _backfill()

        # 1. One team per org, roadmap owned by it.
        team = Team.objects.get(organisation=self.org)
        self.rm.refresh_from_db()
        self.assertEqual(self.rm.owning_team, team)

        # 2. Objective tag -> Objective entity, owned by the team, on the roadmap.
        obj = Objective.objects.get(title='Reduce wait times')
        self.assertEqual(obj.team, team)
        self.assertEqual(obj.description, 'faster licences')
        self.assertIn(obj, self.rm.objectives.all())

        # 3. Both items linked to the objective; only the metric backed by a KR.
        self.metric.refresh_from_db(); self.activity.refresh_from_db()
        self.assertEqual(self.metric.objective, obj)
        self.assertEqual(self.activity.objective, obj)
        krs = list(KeyResult.objects.filter(objective=obj))
        self.assertEqual(len(krs), 1)
        self.assertEqual(krs[0].title, 'Median wait (days)')

        # 4. Squad tag linked to the team; original tags untouched (non-destructive).
        self.squad_tag.refresh_from_db()
        self.assertEqual(self.squad_tag.team, team)
        self.assertEqual(Tag.objects.filter(tag_type=Tag.OBJECTIVE).count(), 1)

    def test_gov_objectives_left_untouched(self):
        gov = Tag.objects.create(name='Clean growth', tag_type=Tag.GOV_OBJECTIVE)
        _backfill()
        gov.refresh_from_db()
        self.assertIsNone(gov.team_id)
        # No Objective entity was created for the gov objective.
        self.assertFalse(Objective.objects.filter(title='Clean growth').exists())

    def test_backfill_is_safe_with_no_data(self):
        Tag.objects.all().delete(); Item.objects.all().delete(); self.rm.delete()
        _backfill()  # should not raise
        self.assertEqual(Objective.objects.count(), 0)


class ObjectiveSwimlaneRenderTests(TestCase):
    """The gantt groups metric items under their objective entity's lane."""

    def setUp(self):
        self.org = Organisation.objects.create(name='MMO')
        self.rm = Roadmap.objects.create(name='RM', roadmap_type=Roadmap.SERVICE)
        self.rm.organisations.add(self.org)
        self.team = Team.objects.create(organisation=self.org, name='MMO')
        self.rm.owning_team = self.team; self.rm.save()
        self.obj = Objective.objects.create(title='Grow adoption', team=self.team)
        self.rm.objectives.add(self.obj)
        self.metric = Item.objects.create(
            roadmap=self.rm, item_type=Item.METRIC, title='Signups', objective=self.obj,
            start_date='2026-08-01', end_date='2026-10-31',
        )

    def test_objective_lane_appears_on_gantt(self):
        res = self.client.get(f'/{self.rm.pk}/?group_by=objective')
        self.assertEqual(res.status_code, 200)
        # The objective entity's title heads a swim lane, and its metric renders.
        self.assertContains(res, 'Grow adoption')
        self.assertContains(res, 'Signups')


class SyncedKeyResultPlottingTests(TestCase):
    """A synced objective set's key results are plotted across the set's period."""

    def setUp(self):
        from roadmap.models import ObjectiveSet, KeyResult
        self.org = Organisation.objects.create(name='MMO')
        self.team = Team.objects.create(organisation=self.org, name='Licensing')
        self.set = ObjectiveSet.objects.create(
            organisation=self.org, scope=ObjectiveSet.TEAM, team=self.team, name='FY26 Q3',
            start_date='2026-07-01', end_date='2026-09-30',
        )
        self.obj = Objective.objects.create(objective_set=self.set, team=self.team, title='Speed up licensing')
        self.kr = KeyResult.objects.create(objective=self.obj, title='Median wait (days)',
                                           start_value=45, target_value=20, current_value=30)
        # Team roadmap with OKR sync on — no items of its own.
        self.rm = Roadmap.objects.create(name='Licensing RM', roadmap_type=Roadmap.SERVICE,
                                         owning_team=self.team, sync_okrs=True)
        self.rm.organisations.add(self.org)

    def test_synced_kr_is_plotted(self):
        res = self.client.get(f'/{self.rm.pk}/?group_by=objective')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Speed up licensing')       # objective lane
        self.assertContains(res, 'Median wait (days)')       # key result bar
        self.assertContains(res, 'gantt-bar--kr')            # rendered as a KR bar

    def test_sync_off_hides_the_kr(self):
        self.rm.sync_okrs = False
        self.rm.save(update_fields=['sync_okrs'])
        res = self.client.get(f'/{self.rm.pk}/?group_by=objective')
        self.assertNotContains(res, 'Median wait (days)')


class RoadmapObjectiveHeaderTests(TestCase):
    """Synced objectives appear in the header pills and KR bars link to the
    objective + key result view (objective_edit)."""

    def setUp(self):
        from roadmap.models import ObjectiveSet, KeyResult
        self.org = Organisation.objects.create(name='MMO')
        self.team = Team.objects.create(organisation=self.org, name='Licensing')
        self.set = ObjectiveSet.objects.create(
            organisation=self.org, scope=ObjectiveSet.TEAM, team=self.team, name='FY26 Q3',
            start_date='2026-07-01', end_date='2026-09-30',
        )
        self.obj = Objective.objects.create(objective_set=self.set, team=self.team, title='Speed up licensing')
        self.kr = KeyResult.objects.create(objective=self.obj, title='Median wait (days)',
                                           start_value=45, target_value=20, current_value=30)
        self.rm = Roadmap.objects.create(name='Licensing RM', roadmap_type=Roadmap.SERVICE,
                                         owning_team=self.team, sync_okrs=True)
        self.rm.organisations.add(self.org)

    def test_synced_objective_in_header_and_context(self):
        res = self.client.get(f'/{self.rm.pk}/?group_by=objective')
        self.assertTrue(res.context['has_roadmap_objectives'])
        self.assertIn(self.set, res.context['applied_sets'])
        # The objective title appears as a header pill linking to objective_edit.
        edit_url = f'/objectives/{self.obj.pk}/edit/'
        self.assertContains(res, f'href="{edit_url}"')
        self.assertContains(res, 'Speed up licensing')

    def test_kr_bar_links_to_objective_view(self):
        res = self.client.get(f'/{self.rm.pk}/?group_by=objective')
        # The key result bar is an anchor to the objective (edit) view.
        self.assertContains(res, f'/objectives/{self.obj.pk}/edit/')
        self.assertContains(res, 'gantt-bar--kr')
