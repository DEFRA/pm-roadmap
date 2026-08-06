"""The metric-Item ↔ KeyResult bridge in the item API (api._ensure_key_result)."""
import json

from django.test import TestCase, Client

from roadmap.models import (
    Organisation, Team, ObjectiveSet, Objective, KeyResult, Roadmap, Item,
)


class KeyResultBridgeTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.org = Organisation.objects.create(name='MMO')
        self.team = Team.objects.create(organisation=self.org, name='Licensing')
        self.roadmap = Roadmap.objects.create(name='Licensing RM', owning_team=self.team)
        self.roadmap.organisations.add(self.org)
        # A team-scoped set + objective that syncs onto the team roadmap.
        self.set = ObjectiveSet.objects.create(
            organisation=self.org, scope=ObjectiveSet.TEAM, team=self.team, name='FY26 Q1',
        )
        self.objective = Objective.objects.create(objective_set=self.set, team=self.team, title='Reduce wait times')

    def post(self, url, payload):
        return self.client.post(url, data=json.dumps(payload), content_type='application/json')

    def put(self, url, payload):
        return self.client.put(url, data=json.dumps(payload), content_type='application/json')

    def _new_metric(self, **extra):
        payload = {'item_type': 'metric', 'title': 'Median wait (days)', 'objective': self.objective.pk}
        payload.update(extra)
        return self.post(f'/api/roadmaps/{self.roadmap.pk}/items/', payload)

    def test_metric_on_objective_creates_backing_key_result(self):
        res = self._new_metric()
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()['objective'], self.objective.pk)
        # The metric Item survives on the timeline...
        self.assertEqual(Item.objects.filter(item_type=Item.METRIC).count(), 1)
        # ...and a backing KeyResult now exists under the objective.
        kr = KeyResult.objects.get(objective=self.objective)
        self.assertEqual(kr.title, 'Median wait (days)')

    def test_renaming_metric_renames_key_result(self):
        item_id = self._new_metric().json()['id']
        self.put(f'/api/items/{item_id}/', {'title': 'Median wait (business days)'})
        kr = KeyResult.objects.get(objective=self.objective)
        self.assertEqual(kr.title, 'Median wait (business days)')
        self.assertEqual(KeyResult.objects.count(), 1)  # renamed, not duplicated

    def test_activity_on_objective_makes_no_key_result(self):
        res = self.post(f'/api/roadmaps/{self.roadmap.pk}/items/', {
            'item_type': 'activity', 'title': 'Build portal', 'objective': self.objective.pk,
        })
        self.assertEqual(res.status_code, 201)
        self.assertEqual(KeyResult.objects.count(), 0)  # only metrics become KRs

    def test_objective_not_on_roadmap_is_rejected(self):
        # An objective owned by a different team's set is not assignable here.
        other_team = Team.objects.create(organisation=self.org, name='Permitting')
        other_set = ObjectiveSet.objects.create(
            organisation=self.org, scope=ObjectiveSet.TEAM, team=other_team, name='Other',
        )
        other_obj = Objective.objects.create(objective_set=other_set, team=other_team, title='Nope')
        res = self._new_metric(objective=other_obj.pk)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(Item.objects.count(), 0)

    def test_empty_objective_unassigns(self):
        item_id = self._new_metric().json()['id']
        res = self.put(f'/api/items/{item_id}/', {'objective': ''})
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(Item.objects.get(pk=item_id).objective_id)
