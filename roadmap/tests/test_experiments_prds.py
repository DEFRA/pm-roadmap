"""Team experiment & PRD canvases + their sync onto roadmap activities."""
from datetime import date

from django.test import TestCase, Client

from roadmap.models import (
    Organisation, Team, Roadmap, Item, Experiment, ProductRequirement,
)


class ExperimentTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.org = Organisation.objects.create(name='MMO')
        self.team = Team.objects.create(organisation=self.org, name='Licensing')
        self.rm = Roadmap.objects.create(name='Team RM', owning_team=self.team, sync_experiments=True)

    def test_create_makes_experiment_and_syncs_an_activity(self):
        res = self.client.post(f'/teams/{self.team.pk}/experiments/new/', {'title': 'Speed test'})
        self.assertEqual(res.status_code, 302)
        exp = Experiment.objects.get(title='Speed test')
        self.assertEqual(exp.team, self.team)
        item = Item.objects.get(experiment=exp)                 # synced onto the roadmap
        self.assertEqual(item.roadmap, self.rm)
        self.assertEqual(item.item_type, Item.ACTIVITY)
        self.assertEqual(item.title, 'Speed test')

    def test_edit_updates_the_backing_activity(self):
        exp = Experiment.objects.create(team=self.team, title='Old')
        data = {
            'title': 'New name', 'objective': '',
            'start_date': '2026-03-01', 'end_date': '2026-04-01',
            'customer': '', 'segment_size': '', 'hypothesis': 'We believe X',
            'actions': '', 'metric': '', 'line_in_the_sand': '', 'result': '',
        }
        res = self.client.post(f'/teams/{self.team.pk}/experiments/{exp.pk}/', data)
        self.assertEqual(res.status_code, 302)
        item = Item.objects.get(experiment=exp)
        self.assertEqual(item.title, 'New name')
        self.assertEqual(item.start_date, date(2026, 3, 1))
        self.assertEqual(item.description, 'We believe X')      # description ← hypothesis

    def test_delete_removes_experiment_and_its_activity(self):
        exp = Experiment.objects.create(team=self.team, title='Temp')
        self.client.post(f'/teams/{self.team.pk}/experiments/{exp.pk}/', {'title': 'Temp', 'objective': ''})
        self.assertTrue(Item.objects.filter(experiment=exp).exists())      # sync created the item
        res = self.client.post(f'/teams/{self.team.pk}/experiments/{exp.pk}/delete/')
        self.assertEqual(res.status_code, 302)
        self.assertFalse(Experiment.objects.filter(pk=exp.pk).exists())
        self.assertFalse(Item.objects.filter(experiment=exp).exists())    # cascaded

    def test_no_sync_when_roadmap_opts_out(self):
        self.rm.sync_experiments = False
        self.rm.save(update_fields=['sync_experiments'])
        self.client.post(f'/teams/{self.team.pk}/experiments/new/', {'title': 'Quiet'})
        exp = Experiment.objects.get(title='Quiet')
        self.assertFalse(Item.objects.filter(experiment=exp).exists())


class PrdTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.org = Organisation.objects.create(name='MMO')
        self.team = Team.objects.create(organisation=self.org, name='Licensing')
        self.rm = Roadmap.objects.create(name='Team RM', owning_team=self.team, sync_prds=True)

    def test_create_makes_prd_and_syncs_an_activity(self):
        res = self.client.post(f'/teams/{self.team.pk}/prds/new/', {
            'name': 'Checkout revamp', 'title': 'Faster checkout',
            'start_date': '2026-05-01', 'end_date': '2026-07-01'})
        self.assertEqual(res.status_code, 302)
        prd = ProductRequirement.objects.get(name='Checkout revamp')
        item = Item.objects.get(product_requirement=prd)
        self.assertEqual(item.roadmap, self.rm)
        self.assertEqual(item.title, 'Checkout revamp')        # title ← name
        self.assertEqual(item.start_date, date(2026, 5, 1))

    def test_delete_removes_prd_and_its_activity(self):
        prd = ProductRequirement.objects.create(team=self.team, name='X', title='Y')
        self.client.post(f'/teams/{self.team.pk}/prds/{prd.pk}/', {
            'name': 'X', 'title': 'Y', 'objective': ''})
        self.assertTrue(Item.objects.filter(product_requirement=prd).exists())
        self.client.post(f'/teams/{self.team.pk}/prds/{prd.pk}/delete/')
        self.assertFalse(ProductRequirement.objects.filter(pk=prd.pk).exists())
        self.assertFalse(Item.objects.filter(product_requirement=prd).exists())


class SyncOntoNewRoadmapTests(TestCase):
    def test_new_team_roadmap_picks_up_existing_canvases(self):
        client = Client()
        org = Organisation.objects.create(name='MMO')
        team = Team.objects.create(organisation=org, name='Licensing')
        exp = Experiment.objects.create(team=team, title='Existing exp')
        prd = ProductRequirement.objects.create(team=team, name='Existing prd', title='t')
        res = client.post(f'/teams/{team.pk}/roadmaps/new/', {
            'name': 'Fresh', 'roadmap_type': 'service', 'sync_okrs': 'on'})
        self.assertEqual(res.status_code, 302)
        rm = Roadmap.objects.get(name='Fresh')
        self.assertTrue(Item.objects.filter(roadmap=rm, experiment=exp).exists())
        self.assertTrue(Item.objects.filter(roadmap=rm, product_requirement=prd).exists())
