from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from roadmap import access
from roadmap.models import (
    Organisation, Team, ObjectiveSet, Objective, KeyResult, Roadmap,
)


class TeamModelTests(TestCase):
    def setUp(self):
        self.org = Organisation.objects.create(name='MMO')

    def test_unique_team_name_per_org(self):
        Team.objects.create(organisation=self.org, name='Licensing')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Team.objects.create(organisation=self.org, name='Licensing')

    def test_same_team_name_allowed_in_different_orgs(self):
        other = Organisation.objects.create(name='EA')
        Team.objects.create(organisation=self.org, name='Licensing')
        Team.objects.create(organisation=other, name='Licensing')
        self.assertEqual(Team.objects.filter(name='Licensing').count(), 2)


class ObjectiveSetConstraintTests(TestCase):
    def setUp(self):
        self.org = Organisation.objects.create(name='MMO')
        self.team = Team.objects.create(organisation=self.org, name='Licensing')

    def test_group_set_must_have_no_team(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ObjectiveSet.objects.create(
                    organisation=self.org, scope=ObjectiveSet.GROUP, team=self.team, name='FY26',
                )

    def test_team_set_must_have_team(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ObjectiveSet.objects.create(
                    organisation=self.org, scope=ObjectiveSet.TEAM, team=None, name='FY26 Q1',
                )

    def test_valid_group_and_team_sets(self):
        ObjectiveSet.objects.create(organisation=self.org, scope=ObjectiveSet.GROUP, name='Company FY26')
        ObjectiveSet.objects.create(
            organisation=self.org, scope=ObjectiveSet.TEAM, team=self.team, name='FY26 Q1',
        )
        self.assertEqual(ObjectiveSet.objects.count(), 2)


class KeyResultProgressTests(TestCase):
    def setUp(self):
        self.org = Organisation.objects.create(name='MMO')
        self.obj = Objective.objects.create(title='Grow adoption')

    def _kr(self, **kw):
        defaults = dict(objective=self.obj, title='KR', start_value=0, target_value=100, current_value=50)
        defaults.update(kw)
        return KeyResult.objects.create(**defaults)

    def test_progress_halfway(self):
        self.assertEqual(self._kr().progress, 50)

    def test_progress_clamped_and_decrease_direction(self):
        # Decrease direction: start 100 → target 0, current 75 ⇒ 25% done.
        kr = self._kr(start_value=100, target_value=0, current_value=75, direction=KeyResult.DECREASE)
        self.assertEqual(kr.progress, 25)

    def test_progress_zero_span(self):
        kr = self._kr(start_value=10, target_value=10, current_value=10)
        self.assertEqual(kr.progress, 100)


class SyncScopingTests(TestCase):
    """access.py: which objective sets/objectives surface on which roadmaps."""

    def setUp(self):
        self.org = Organisation.objects.create(name='MMO')
        self.other_org = Organisation.objects.create(name='EA')
        self.team = Team.objects.create(organisation=self.org, name='Licensing')
        self.other_team = Team.objects.create(organisation=self.org, name='Permitting')

        # Team-scoped set with one objective, owned by self.team.
        self.team_set = ObjectiveSet.objects.create(
            organisation=self.org, scope=ObjectiveSet.TEAM, team=self.team, name='FY26 Q1',
        )
        self.team_obj = Objective.objects.create(objective_set=self.team_set, team=self.team, title='Reduce wait times')

        # Group-scoped set for the org.
        self.group_set = ObjectiveSet.objects.create(
            organisation=self.org, scope=ObjectiveSet.GROUP, name='Company FY26',
        )
        self.group_obj = Objective.objects.create(objective_set=self.group_set, title='Company goal')

        # A roadmap owned by self.team.
        self.team_roadmap = Roadmap.objects.create(name='Licensing RM', owning_team=self.team)
        self.team_roadmap.organisations.add(self.org)

        # A teamless (group) roadmap in the org.
        self.group_roadmap = Roadmap.objects.create(name='Group RM')
        self.group_roadmap.organisations.add(self.org)

    def test_team_roadmap_syncs_only_its_team_set(self):
        ids = access.roadmap_objective_ids(self.team_roadmap)
        self.assertIn(self.team_obj.pk, ids)
        self.assertNotIn(self.group_obj.pk, ids)

    def test_other_teams_set_does_not_sync(self):
        other_set = ObjectiveSet.objects.create(
            organisation=self.org, scope=ObjectiveSet.TEAM, team=self.other_team, name='Other Q1',
        )
        other_obj = Objective.objects.create(objective_set=other_set, team=self.other_team, title='Not mine')
        self.assertNotIn(other_obj.pk, access.roadmap_objective_ids(self.team_roadmap))

    def test_group_roadmap_syncs_group_set(self):
        ids = access.roadmap_objective_ids(self.group_roadmap)
        self.assertIn(self.group_obj.pk, ids)
        self.assertNotIn(self.team_obj.pk, ids)

    def test_archived_set_does_not_sync(self):
        self.team_set.archived = True
        self.team_set.save(update_fields=['archived'])
        self.assertNotIn(self.team_obj.pk, access.roadmap_objective_ids(self.team_roadmap))

    def test_sync_off_hides_synced_but_keeps_direct(self):
        self.team_roadmap.sync_okrs = False
        self.team_roadmap.save(update_fields=['sync_okrs'])
        self.assertNotIn(self.team_obj.pk, access.roadmap_objective_ids(self.team_roadmap))
        # A standalone objective linked directly still shows.
        standalone = Objective.objects.create(title='Standalone')
        self.team_roadmap.objectives.add(standalone)
        self.assertIn(standalone.pk, access.roadmap_objective_ids(self.team_roadmap))

    def test_group_objective_assignable_to_team_roadmap_without_syncing(self):
        # Not synced onto the team roadmap's lanes...
        self.assertNotIn(self.group_obj.pk, access.roadmap_objective_ids(self.team_roadmap))
        # ...but items on the team roadmap may still be assigned to it.
        self.assertTrue(access.objective_assignable_to_roadmap(self.group_obj, self.team_roadmap))

    def test_foreign_org_group_objective_not_assignable(self):
        foreign_set = ObjectiveSet.objects.create(
            organisation=self.other_org, scope=ObjectiveSet.GROUP, name='EA FY26',
        )
        foreign_obj = Objective.objects.create(objective_set=foreign_set, title='EA goal')
        self.assertFalse(access.objective_assignable_to_roadmap(foreign_obj, self.team_roadmap))
