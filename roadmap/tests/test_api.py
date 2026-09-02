import json

from django.test import TestCase, Client

from roadmap.models import (
    Organisation, Roadmap, Item, Tag, Objective, KeyResult, TAG_COLOUR_PALETTE,
)


class ApiTestCase(TestCase):
    """Base: a client that skips CSRF so endpoint logic can be tested directly."""

    def setUp(self):
        self.client = Client()
        self.group = Roadmap.objects.create(name='Group RM', roadmap_type=Roadmap.GROUP)
        self.service = Roadmap.objects.create(name='Service RM', roadmap_type=Roadmap.SERVICE)
        self.outcome = Tag.objects.create(name='Grow Revenue', tag_type=Tag.OUTCOME)
        self.team = Tag.objects.create(name='Ops', tag_type=Tag.ORGANISATION, roadmap=self.group)
        self.org = Organisation.objects.create(name='MMO', abbreviation='MMO')

    def post(self, url, payload):
        return self.client.post(url, data=json.dumps(payload), content_type='application/json')

    def put(self, url, payload):
        return self.client.put(url, data=json.dumps(payload), content_type='application/json')


class TagApiTests(ApiTestCase):
    def test_list_central_outcomes(self):
        res = self.client.get('/api/tags/?type=outcome')
        self.assertEqual(res.status_code, 200)
        names = [t['name'] for t in res.json()]
        self.assertIn('Grow Revenue', names)

    def test_list_scoped_by_roadmap(self):
        res = self.client.get(f'/api/tags/?type=organisation&roadmap={self.group.pk}')
        self.assertEqual([t['name'] for t in res.json()], ['Ops'])
        # Other roadmap has no scoped teams.
        res2 = self.client.get(f'/api/tags/?type=organisation&roadmap={self.service.pk}')
        self.assertEqual(res2.json(), [])

    def test_create_scoped_tag_keeps_roadmap(self):
        res = self.post('/api/tags/', {'name': 'Marine', 'tag_type': 'organisation', 'roadmap': self.service.pk})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()['roadmap'], self.service.pk)

    def test_create_central_tag_ignores_roadmap(self):
        # A roadmap sent for a central type must be nulled out.
        res = self.post('/api/tags/', {'name': 'Thriving', 'tag_type': 'outcome', 'roadmap': self.service.pk})
        self.assertEqual(res.status_code, 201)
        self.assertIsNone(res.json()['roadmap'])

    def test_create_assigns_palette_colour(self):
        res = self.post('/api/tags/', {'name': 'NoColour', 'tag_type': 'outcome'})
        self.assertIn(res.json()['colour'], TAG_COLOUR_PALETTE)

    def test_duplicate_central_tag_returns_409(self):
        res = self.post('/api/tags/', {'name': 'Grow Revenue', 'tag_type': 'outcome'})
        self.assertEqual(res.status_code, 409)

    def test_invalid_tag_type_400(self):
        res = self.post('/api/tags/', {'name': 'X', 'tag_type': 'nonsense'})
        self.assertEqual(res.status_code, 400)

    def test_update_description(self):
        res = self.put(f'/api/tags/{self.outcome.pk}/', {'description': 'hello'})
        self.assertEqual(res.status_code, 200)
        self.outcome.refresh_from_db()
        self.assertEqual(self.outcome.description, 'hello')

    def test_update_link(self):
        res = self.put(f'/api/tags/{self.outcome.pk}/', {'link': 'https://example.com'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['link'], 'https://example.com')
        self.outcome.refresh_from_db()
        self.assertEqual(self.outcome.link, 'https://example.com')

    def test_scoped_tag_name_editable(self):
        res = self.put(f'/api/tags/{self.team.pk}/', {'name': 'Renamed Team'})
        self.assertEqual(res.status_code, 200)
        self.team.refresh_from_db()
        self.assertEqual(self.team.name, 'Renamed Team')

    def test_central_tag_name_locked(self):
        # Sending a name for a central (outcome) tag must be ignored.
        res = self.put(f'/api/tags/{self.outcome.pk}/', {'name': 'Hacked Name'})
        self.assertEqual(res.status_code, 200)
        self.outcome.refresh_from_db()
        self.assertEqual(self.outcome.name, 'Grow Revenue')

    def test_delete_tag(self):
        res = self.client.delete(f'/api/tags/{self.team.pk}/')
        self.assertEqual(res.status_code, 204)
        self.assertFalse(Tag.objects.filter(pk=self.team.pk).exists())

    def test_reorder_sets_sort_order(self):
        a = Tag.objects.create(name='A out', tag_type=Tag.OUTCOME)
        b = Tag.objects.create(name='B out', tag_type=Tag.OUTCOME)
        c = Tag.objects.create(name='C out', tag_type=Tag.OUTCOME)
        res = self.post('/api/tags/reorder/', {'ids': [c.pk, a.pk, b.pk]})
        self.assertEqual(res.status_code, 200)
        c.refresh_from_db(); a.refresh_from_db(); b.refresh_from_db()
        self.assertEqual((c.sort_order, a.sort_order, b.sort_order), (0, 1, 2))

    def test_reorder_requires_list(self):
        self.assertEqual(self.post('/api/tags/reorder/', {'ids': 'nope'}).status_code, 400)


class RoadmapApiTests(ApiTestCase):
    def test_create_roadmap_with_orgs(self):
        res = self.post('/api/roadmaps/', {
            'name': 'New', 'roadmap_type': 'service', 'team': 'Delivery',
            'organisations': [self.org.pk],
        })
        self.assertEqual(res.status_code, 201)
        body = res.json()
        self.assertEqual(body['roadmap_type'], 'service')
        self.assertEqual([o['id'] for o in body['organisations']], [self.org.pk])

    def test_create_roadmap_requires_name(self):
        self.assertEqual(self.post('/api/roadmaps/', {'name': ''}).status_code, 400)

    def test_update_replaces_tag_membership(self):
        self.group.tags.set([self.outcome])
        res = self.put(f'/api/roadmaps/{self.group.pk}/', {'tags': [self.team.pk]})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(set(self.group.tags.values_list('pk', flat=True)), {self.team.pk})

    def test_update_invalid_tag_id_400(self):
        res = self.put(f'/api/roadmaps/{self.group.pk}/', {'tags': [999999]})
        self.assertEqual(res.status_code, 400)


class ItemApiTests(ApiTestCase):
    def test_create_item(self):
        res = self.post(f'/api/roadmaps/{self.group.pk}/items/', {
            'item_type': 'activity', 'title': 'Build', 'start_date': '2026-07-01',
            'end_date': '2026-09-30', 'priority': 'high', 'tags': [self.outcome.pk],
        })
        self.assertEqual(res.status_code, 201)
        item = Item.objects.get(title='Build')
        self.assertEqual(item.priority, 'high')
        self.assertEqual(list(item.tags.all()), [self.outcome])

    def test_create_item_requires_title(self):
        res = self.post(f'/api/roadmaps/{self.group.pk}/items/', {'item_type': 'activity', 'title': ''})
        self.assertEqual(res.status_code, 400)

    def test_create_item_invalid_type(self):
        res = self.post(f'/api/roadmaps/{self.group.pk}/items/', {'item_type': 'bogus', 'title': 'X'})
        self.assertEqual(res.status_code, 400)

    def test_assign_key_results_to_activity(self):
        obj = Objective.objects.create(title='Faster licensing')
        self.group.objectives.add(obj)
        kr1 = KeyResult.objects.create(objective=obj, title='KR1')
        kr2 = KeyResult.objects.create(objective=obj, title='KR2')
        res = self.post(f'/api/roadmaps/{self.group.pk}/items/', {
            'item_type': 'activity', 'title': 'Rebuild', 'objective': obj.pk,
            'key_results': [kr1.pk, kr2.pk],
        })
        self.assertEqual(res.status_code, 201)
        item = Item.objects.get(title='Rebuild')
        self.assertEqual(set(item.key_results.values_list('pk', flat=True)), {kr1.pk, kr2.pk})
        self.assertEqual({k['id'] for k in res.json()['key_results']}, {kr1.pk, kr2.pk})

    def test_key_results_must_belong_to_the_objective(self):
        obj = Objective.objects.create(title='A'); self.group.objectives.add(obj)
        other = Objective.objects.create(title='B'); self.group.objectives.add(other)
        kr_a = KeyResult.objects.create(objective=obj, title='KR-A')
        kr_b = KeyResult.objects.create(objective=other, title='KR-B')
        res = self.post(f'/api/roadmaps/{self.group.pk}/items/', {
            'item_type': 'activity', 'title': 'X', 'objective': obj.pk,
            'key_results': [kr_a.pk, kr_b.pk],   # kr_b is under a different objective
        })
        item = Item.objects.get(title='X')
        self.assertEqual(list(item.key_results.values_list('pk', flat=True)), [kr_a.pk])

    def test_changing_objective_drops_stale_key_results(self):
        obj = Objective.objects.create(title='A'); self.group.objectives.add(obj)
        other = Objective.objects.create(title='B'); self.group.objectives.add(other)
        kr_a = KeyResult.objects.create(objective=obj, title='KR-A')
        item = Item.objects.create(roadmap=self.group, item_type=Item.ACTIVITY, title='X', objective=obj)
        item.key_results.add(kr_a)
        # Reassign to another objective without resending key_results.
        res = self.put(f'/api/items/{item.pk}/', {'objective': other.pk})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(list(item.key_results.all()), [])

    def test_update_item(self):
        item = Item.objects.create(roadmap=self.group, item_type=Item.ACTIVITY, title='Old')
        res = self.put(f'/api/items/{item.pk}/', {'title': 'New', 'size': 'L'})
        self.assertEqual(res.status_code, 200)
        item.refresh_from_db()
        self.assertEqual((item.title, item.size), ('New', 'L'))

    def test_update_item_dates_and_row(self):
        item = Item.objects.create(roadmap=self.group, item_type=Item.ACTIVITY, title='Move me',
                                   start_date='2026-08-01', end_date='2026-08-15')
        res = self.put(f'/api/items/{item.pk}/', {
            'start_date': '2026-09-01', 'end_date': '2026-09-20', 'row': 2,
        })
        self.assertEqual(res.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.start_date.isoformat(), '2026-09-01')
        self.assertEqual(item.end_date.isoformat(), '2026-09-20')
        self.assertEqual(item.row, 2)

    def test_clear_dates_parks_item(self):
        item = Item.objects.create(roadmap=self.group, item_type=Item.ACTIVITY, title='Park me',
                                   start_date='2026-08-01', end_date='2026-08-15')
        res = self.put(f'/api/items/{item.pk}/', {'start_date': '', 'end_date': '', 'row': 1})
        self.assertEqual(res.status_code, 200)
        item.refresh_from_db()
        self.assertIsNone(item.start_date)
        self.assertIsNone(item.end_date)
        self.assertEqual(item.row, 1)

    def test_bad_date_returns_400(self):
        res = self.post(f'/api/roadmaps/{self.group.pk}/items/', {
            'item_type': 'activity', 'title': 'BadDate', 'start_date': '01-07-2026',
        })
        self.assertEqual(res.status_code, 400)

    def test_delete_item(self):
        item = Item.objects.create(roadmap=self.group, item_type=Item.ACTIVITY, title='Del')
        self.assertEqual(self.client.delete(f'/api/items/{item.pk}/').status_code, 204)

    def test_item_tags_join_roadmap_membership_excluding_categories(self):
        category = Tag.objects.create(name='Discovery', tag_type=Tag.CATEGORY)
        self.assertEqual(self.group.tags.count(), 0)
        self.post(f'/api/roadmaps/{self.group.pk}/items/', {
            'item_type': 'activity', 'title': 'Tagged',
            'tags': [self.outcome.pk, self.team.pk, category.pk],
        })
        member_ids = set(self.group.tags.values_list('pk', flat=True))
        # Outcome + team join the header; the category does not.
        self.assertIn(self.outcome.pk, member_ids)
        self.assertIn(self.team.pk, member_ids)
        self.assertNotIn(category.pk, member_ids)

    def test_updating_item_tags_adds_to_membership(self):
        item = Item.objects.create(roadmap=self.group, item_type=Item.ACTIVITY, title='U')
        self.put(f'/api/items/{item.pk}/', {'tags': [self.outcome.pk]})
        self.assertIn(self.outcome.pk, set(self.group.tags.values_list('pk', flat=True)))


class CsrfTests(TestCase):
    """The pages set the CSRF cookie; the API rejects writes without the token."""

    def setUp(self):
        self.rm = Roadmap.objects.create(name='RM')

    def test_post_without_csrf_is_forbidden(self):
        client = Client(enforce_csrf_checks=True)
        res = client.post('/api/tags/', data=json.dumps({'name': 'X', 'tag_type': 'outcome'}),
                          content_type='application/json')
        self.assertEqual(res.status_code, 403)

    def test_detail_page_sets_csrf_cookie_and_token_works(self):
        client = Client(enforce_csrf_checks=True)
        page = client.get(f'/{self.rm.pk}/')
        self.assertIn('csrftoken', page.cookies)
        token = page.cookies['csrftoken'].value
        res = client.post('/api/tags/', data=json.dumps({'name': 'CsrfOk', 'tag_type': 'outcome'}),
                          content_type='application/json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(res.status_code, 201)
