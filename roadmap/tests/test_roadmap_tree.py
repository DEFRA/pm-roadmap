"""Initiative tree page. Under each Defra outcome, two branches ladder up to it:
Objective → Key results, and Activity → Milestones."""
from django.test import TestCase, Client

from roadmap.models import (
    Organisation, Team, Roadmap, Item, Tag, Objective, KeyResult, ObjectiveSet,
)


class RoadmapTreeTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.org = Organisation.objects.create(name='MMO')
        self.team = Team.objects.create(organisation=self.org, name='Data & Digital')
        self.rm = Roadmap.objects.create(name='Licensing RM', owning_team=self.team)
        self.rm.organisations.add(self.org)

        self.outcome = Tag.objects.create(name='Cleaner seas', tag_type=Tag.OUTCOME, colour='#4c2c92')
        self.rm.tags.add(self.outcome)
        self.oset = ObjectiveSet.objects.create(
            organisation=self.org, scope=ObjectiveSet.TEAM, team=self.team, name='FY26 Q3')
        self.obj = Objective.objects.create(objective_set=self.oset, team=self.team, title='Speed up licensing')
        self.kr = KeyResult.objects.create(
            objective=self.obj, objective_set=self.oset, title='Median wait (days)',
            start_value=45, target_value=20, current_value=30)

        self.act = Item.objects.create(
            roadmap=self.rm, item_type=Item.ACTIVITY, title='Rebuild the portal', objective=self.obj)
        self.act.tags.add(self.outcome)
        # A milestone linked to the activity.
        self.ms = Item.objects.create(roadmap=self.rm, item_type=Item.MILESTONE, title='Beta launched')
        self.ms.linked_activities.add(self.act)

    def _node(self, res, outcome):
        return next(n for n in res.context['outcome_tree'] if n['outcome'] == outcome)

    def test_activity_nests_under_its_assigned_key_result(self):
        self.act.key_results.add(self.kr)   # direct activity → key result link
        res = self.client.get(f'/{self.rm.pk}/tree/')
        node = self._node(res, self.outcome)

        # Objective → key result, and the activity nests under the key result.
        self.assertEqual([o['objective'] for o in node['objectives']], [self.obj])
        kr_entry = node['objectives'][0]['key_results'][0]
        self.assertEqual(kr_entry['kr'], self.kr)
        self.assertEqual([a['activity'] for a in kr_entry['activities']], [self.act])
        self.assertEqual(kr_entry['activities'][0]['milestones'], [self.ms])
        # It is NOT also in the outcome-level fallback branch.
        self.assertEqual(node['activities'], [])

        for text in ('Cleaner seas', 'Speed up licensing', 'Median wait (days)',
                     'Rebuild the portal', 'Beta launched'):
            self.assertContains(res, text)
        self.assertEqual(res.context['totals'],
                         {'outcomes': 1, 'objectives': 1, 'key_results': 1,
                          'activities': 1, 'milestones': 1})

    def test_unassigned_activity_falls_back_to_outcome_branch(self):
        # No metric links the activity to a KR → it hangs off the outcome directly.
        res = self.client.get(f'/{self.rm.pk}/tree/')
        node = self._node(res, self.outcome)
        self.assertEqual([a['activity'] for a in node['activities']], [self.act])
        # And it is not under any key result.
        self.assertEqual(node['objectives'][0]['key_results'][0]['activities'], [])

    def test_activity_without_outcome_falls_into_no_outcome(self):
        Item.objects.create(
            roadmap=self.rm, item_type=Item.ACTIVITY, title='Loose activity', objective=self.obj)
        res = self.client.get(f'/{self.rm.pk}/tree/')
        titles = [a['activity'].title for a in res.context['no_outcome']['activities']]
        self.assertIn('Loose activity', titles)
        self.assertNotIn('Rebuild the portal', titles)

    def test_roadmap_outcome_with_nothing_linked_still_shown(self):
        empty = Tag.objects.create(name='Net zero', tag_type=Tag.OUTCOME, colour='#912b88')
        self.rm.tags.add(empty)
        res = self.client.get(f'/{self.rm.pk}/tree/')
        node = self._node(res, empty)
        self.assertEqual(node['objectives'], [])
        self.assertEqual(node['activities'], [])
        self.assertContains(res, 'Net zero')
        self.assertContains(res, 'Nothing linked to this outcome yet')

    def test_picker_filters_to_one_outcome(self):
        second = Tag.objects.create(name='Thriving coasts', tag_type=Tag.OUTCOME, colour='#00703c')
        self.rm.tags.add(second)
        other = Item.objects.create(roadmap=self.rm, item_type=Item.ACTIVITY, title='Coastal survey')
        other.tags.add(second)
        res = self.client.get(f'/{self.rm.pk}/tree/?outcome={self.outcome.pk}')
        self.assertEqual([n['outcome'].name for n in res.context['outcome_tree']], ['Cleaner seas'])
        self.assertEqual(res.context['selected'], str(self.outcome.pk))
        self.assertContains(res, 'Rebuild the portal')
        self.assertNotContains(res, 'Coastal survey')
        self.assertEqual({n['outcome'].name for n in res.context['outcome_options']},
                         {'Cleaner seas', 'Thriving coasts'})

    def test_picker_none_shows_only_unlinked(self):
        Item.objects.create(roadmap=self.rm, item_type=Item.ACTIVITY, title='Loose activity')
        res = self.client.get(f'/{self.rm.pk}/tree/?outcome=none')
        self.assertEqual(res.context['outcome_tree'], [])
        titles = [a['activity'].title for a in res.context['no_outcome']['activities']]
        self.assertEqual(titles, ['Loose activity'])
        self.assertNotContains(res, 'Rebuild the portal')

    def test_only_linked_milestones_appear(self):
        # A milestone not linked to the activity must not show under it.
        Item.objects.create(roadmap=self.rm, item_type=Item.MILESTONE, title='Unlinked milestone')
        node = self._node(self.client.get(f'/{self.rm.pk}/tree/'), self.outcome)
        self.assertEqual(node['activities'][0]['milestones'], [self.ms])
