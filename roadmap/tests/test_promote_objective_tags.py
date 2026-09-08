"""promote_objective_tags management command: legacy objective tags → durable
Objective entities, moving item links across."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from roadmap.models import Organisation, Team, Roadmap, Item, Tag, Objective


class PromoteObjectiveTagsTests(TestCase):
    def setUp(self):
        self.org = Organisation.objects.create(name='MMO')
        self.team = Team.objects.create(organisation=self.org, name='Licensing')
        self.rm = Roadmap.objects.create(
            name='Licensing RM', roadmap_type=Roadmap.SERVICE, owning_team=self.team)
        # Legacy objective tag (roadmap-scoped) on the roadmap, plus a tagged item.
        self.tag = Tag.objects.create(name='Speed up appeals', tag_type=Tag.OBJECTIVE, roadmap=self.rm)
        self.rm.tags.add(self.tag)
        self.item = Item.objects.create(roadmap=self.rm, item_type=Item.ACTIVITY, title='Rebuild')
        self.item.tags.add(self.tag)

    def _run(self, *args):
        out = StringIO()
        call_command('promote_objective_tags', '--roadmap', str(self.rm.pk), *args, stdout=out)
        return out.getvalue()

    def test_promotes_tag_to_objective_and_moves_item(self):
        self._run()
        obj = Objective.objects.get(title='Speed up appeals')
        self.assertEqual(obj.team, self.team)                 # durable, team-owned
        self.item.refresh_from_db()
        self.assertEqual(self.item.objective, obj)            # item re-pointed
        self.assertNotIn(self.tag, self.item.tags.all())      # tag removed from item
        self.assertNotIn(self.tag, self.rm.tags.all())        # detached from the roadmap
        self.assertTrue(Tag.objects.filter(pk=self.tag.pk).exists())  # kept by default

    def test_dry_run_changes_nothing(self):
        self._run('--dry-run')
        self.assertFalse(Objective.objects.filter(title='Speed up appeals').exists())
        self.item.refresh_from_db()
        self.assertIsNone(self.item.objective_id)
        self.assertIn(self.tag, self.rm.tags.all())

    def test_idempotent_reuses_existing_objective(self):
        self._run()
        self._run()   # second pass: nothing new to convert
        self.assertEqual(Objective.objects.filter(title='Speed up appeals').count(), 1)

    def test_does_not_clobber_an_existing_objective_link(self):
        other = Objective.objects.create(team=self.team, title='Already set')
        self.item.objective = other
        self.item.save(update_fields=['objective'])
        self._run()
        self.item.refresh_from_db()
        self.assertEqual(self.item.objective, other)          # existing link preserved
        self.assertNotIn(self.tag, self.item.tags.all())      # tag still removed

    def test_delete_tags_removes_roadmap_scoped_tag(self):
        self._run('--delete-tags')
        self.assertFalse(Tag.objects.filter(pk=self.tag.pk).exists())

    def test_delete_tags_keeps_central_tags(self):
        central = Tag.objects.create(name='Gov aim', tag_type=Tag.GOV_OBJECTIVE)  # no roadmap = central
        group_rm = Roadmap.objects.create(name='Group RM', roadmap_type=Roadmap.GROUP, owning_team=self.team)
        group_rm.tags.add(central)
        out = StringIO()
        call_command('promote_objective_tags', '--roadmap', str(group_rm.pk), '--delete-tags', stdout=out)
        self.assertTrue(Tag.objects.filter(pk=central.pk).exists())   # central tag never deleted
        self.assertNotIn(central, group_rm.tags.all())                # only detached
