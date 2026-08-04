"""Standalone OKR + team pages (views_okr, views_team, forms)."""
from django.test import TestCase
from django.urls import reverse

from roadmap.models import Organisation, Team, ObjectiveSet, Objective, KeyResult


class TeamPageTests(TestCase):
    def setUp(self):
        self.org = Organisation.objects.create(name='MMO')

    def test_team_list_and_create(self):
        self.assertEqual(self.client.get(reverse('roadmap:team_list')).status_code, 200)
        res = self.client.post(reverse('roadmap:team_create'), {
            'organisation': self.org.pk, 'name': 'Licensing', 'mission': 'Do good', 'vision': '',
        })
        self.assertEqual(res.status_code, 302)
        team = Team.objects.get(name='Licensing')
        self.assertEqual(team.organisation, self.org)
        self.assertEqual(res.url, reverse('roadmap:team_home', args=[team.pk]))

    def test_create_team_without_org_uses_no_org_placeholder(self):
        res = self.client.post(reverse('roadmap:team_create'), {'organisation': '', 'name': 'Nomads'})
        self.assertEqual(res.status_code, 302)
        team = Team.objects.get(name='Nomads')
        self.assertEqual(team.organisation.name, 'No org')
        # A second org-less team reuses the same placeholder, not a duplicate.
        self.client.post(reverse('roadmap:team_create'), {'organisation': '', 'name': 'Drifters'})
        self.assertEqual(Organisation.objects.filter(name='No org').count(), 1)

    def test_team_home_renders(self):
        team = Team.objects.create(organisation=self.org, name='Licensing')
        res = self.client.get(reverse('roadmap:team_home', args=[team.pk]))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Licensing')

    def test_team_creates_roadmap_it_owns_with_okr_sync(self):
        from roadmap.models import Roadmap
        team = Team.objects.create(organisation=self.org, name='Licensing')
        res = self.client.post(reverse('roadmap:team_roadmap_create', args=[team.pk]), {
            'name': 'Licensing Service Roadmap', 'roadmap_type': Roadmap.SERVICE, 'sync_okrs': 'on',
        })
        rm = Roadmap.objects.get(name='Licensing Service Roadmap')
        self.assertEqual(rm.owning_team, team)
        self.assertIn(self.org, rm.organisations.all())
        self.assertTrue(rm.sync_okrs)
        self.assertRedirects(res, reverse('roadmap:detail', args=[rm.pk]), fetch_redirect_response=False)

    def test_team_roadmap_sync_can_be_turned_off(self):
        from roadmap.models import Roadmap
        team = Team.objects.create(organisation=self.org, name='Licensing')
        self.client.post(reverse('roadmap:team_roadmap_create', args=[team.pk]), {
            'name': 'No sync RM', 'roadmap_type': Roadmap.SERVICE,  # checkbox absent = off
        })
        self.assertFalse(Roadmap.objects.get(name='No sync RM').sync_okrs)


class ObjectiveSetPageTests(TestCase):
    def setUp(self):
        self.org = Organisation.objects.create(name='MMO')
        self.team = Team.objects.create(organisation=self.org, name='Licensing')

    def test_team_set_create_with_preset_fills_dates(self):
        res = self.client.post(reverse('roadmap:team_set_create', args=[self.team.pk]), {
            'name': '', 'period_preset': 'current_quarter', 'start_date': '', 'end_date': '',
        })
        self.assertEqual(res.status_code, 302)
        s = ObjectiveSet.objects.get()
        # Scope/team/org are taken from the team, not the form.
        self.assertEqual(s.scope, ObjectiveSet.TEAM)
        self.assertEqual(s.team, self.team)
        self.assertEqual(s.organisation, self.org)
        self.assertEqual(s.period, ObjectiveSet.QUARTERLY)
        self.assertTrue(s.start_date and s.end_date)  # preset auto-filled
        self.assertTrue(s.name)  # suggested name filled
        self.assertRedirects(res, reverse('roadmap:objective_set_detail', args=[s.pk]),
                             fetch_redirect_response=False)

    def test_team_set_create_custom_name(self):
        res = self.client.post(reverse('roadmap:team_set_create', args=[self.team.pk]), {
            'name': 'FY26 Q1', 'period_preset': 'custom', 'start_date': '', 'end_date': '',
        })
        self.assertEqual(res.status_code, 302)
        self.assertEqual(ObjectiveSet.objects.get().name, 'FY26 Q1')

    def test_archive_unarchive_and_delete(self):
        s = ObjectiveSet.objects.create(organisation=self.org, scope=ObjectiveSet.GROUP, name='X')
        self.client.post(reverse('roadmap:objective_set_archive', args=[s.pk]))
        s.refresh_from_db(); self.assertTrue(s.archived)
        self.client.post(reverse('roadmap:objective_set_unarchive', args=[s.pk]))
        s.refresh_from_db(); self.assertFalse(s.archived)
        self.client.post(reverse('roadmap:objective_set_delete', args=[s.pk]))
        self.assertEqual(ObjectiveSet.objects.count(), 0)


class ObjectivePageTests(TestCase):
    def setUp(self):
        self.org = Organisation.objects.create(name='MMO')
        self.team = Team.objects.create(organisation=self.org, name='Licensing')
        self.set = ObjectiveSet.objects.create(
            organisation=self.org, scope=ObjectiveSet.TEAM, team=self.team, name='FY26 Q1',
        )

    def _kr_formset_blank(self, **overrides):
        data = {
            'key_results-TOTAL_FORMS': '1', 'key_results-INITIAL_FORMS': '0',
            'key_results-MIN_NUM_FORMS': '0', 'key_results-MAX_NUM_FORMS': '1000',
        }
        data.update(overrides)
        return data

    def test_create_objective_with_key_result(self):
        data = {
            'objective_set': self.set.pk, 'team': self.team.pk,
            'title': 'Reduce wait times', 'description': 'faster',
            'key_results-0-title': 'Median wait (days)',
            'key_results-0-unit': 'days', 'key_results-0-start_value': '30',
            'key_results-0-target_value': '10', 'key_results-0-current_value': '20',
            'key_results-0-direction': KeyResult.DECREASE, 'key_results-0-status': KeyResult.ON_TRACK,
        }
        data.update(self._kr_formset_blank())
        res = self.client.post(reverse('roadmap:objective_create'), data)
        self.assertEqual(res.status_code, 302)
        obj = Objective.objects.get(title='Reduce wait times')
        self.assertEqual(obj.objective_set, self.set)
        self.assertEqual(obj.key_results.count(), 1)
        self.assertEqual(res.url, reverse('roadmap:objective_set_detail', args=[self.set.pk]))

    def test_key_result_direction_validation(self):
        data = {
            'objective_set': '', 'team': '', 'title': 'Grow', 'description': '',
            # Increase but target below start ⇒ invalid.
            'key_results-0-title': 'Users', 'key_results-0-unit': '',
            'key_results-0-start_value': '100', 'key_results-0-target_value': '50',
            'key_results-0-current_value': '80', 'key_results-0-direction': KeyResult.INCREASE,
            'key_results-0-status': KeyResult.ON_TRACK,
        }
        data.update(self._kr_formset_blank())
        res = self.client.post(reverse('roadmap:objective_create'), data)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(Objective.objects.count(), 0)

    def test_objective_create_prefills_set_from_query(self):
        res = self.client.get(reverse('roadmap:objective_create') + f'?set={self.set.pk}')
        self.assertEqual(res.status_code, 200)

    def test_delete_objective_returns_to_set(self):
        obj = Objective.objects.create(objective_set=self.set, team=self.team, title='Temp')
        res = self.client.post(reverse('roadmap:objective_delete', args=[obj.pk]))
        self.assertEqual(res.url, reverse('roadmap:objective_set_detail', args=[self.set.pk]))
        self.assertEqual(Objective.objects.count(), 0)

    def test_objective_list_and_set_detail_render(self):
        Objective.objects.create(objective_set=self.set, team=self.team, title='Shown')
        self.assertEqual(self.client.get(reverse('roadmap:objective_list')).status_code, 200)
        res = self.client.get(reverse('roadmap:objective_set_detail', args=[self.set.pk]))
        self.assertContains(res, 'Shown')
