import json

from django.test import TestCase, Client

from roadmap.models import Organisation, Roadmap, Item, Tag, TAG_COLOUR_PALETTE


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

    def test_delete_tag(self):
        res = self.client.delete(f'/api/tags/{self.team.pk}/')
        self.assertEqual(res.status_code, 204)
        self.assertFalse(Tag.objects.filter(pk=self.team.pk).exists())


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

    def test_update_item(self):
        item = Item.objects.create(roadmap=self.group, item_type=Item.ACTIVITY, title='Old')
        res = self.put(f'/api/items/{item.pk}/', {'title': 'New', 'size': 'L'})
        self.assertEqual(res.status_code, 200)
        item.refresh_from_db()
        self.assertEqual((item.title, item.size), ('New', 'L'))

    def test_bad_date_returns_400(self):
        res = self.post(f'/api/roadmaps/{self.group.pk}/items/', {
            'item_type': 'activity', 'title': 'BadDate', 'start_date': '01-07-2026',
        })
        self.assertEqual(res.status_code, 400)

    def test_delete_item(self):
        item = Item.objects.create(roadmap=self.group, item_type=Item.ACTIVITY, title='Del')
        self.assertEqual(self.client.delete(f'/api/items/{item.pk}/').status_code, 204)


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
