"""Convert a roadmap's legacy objective *tags* into durable Objective entities.

Older roadmaps recorded objectives as Tags (tag_type=objective / gov_objective) —
just a name, shown as header pills, with items linked via Item.tags. The durable
model (B2) uses real Objective records owned by a team, with items linked via
Item.objective. This command promotes the tag-style objectives on one roadmap to
durable objectives and moves the item links across, so the roadmap runs entirely
on the new system (and the "Manage objectives" panel can see them).

Safe to preview with --dry-run (wraps everything in a transaction and rolls back).
Idempotent: an existing durable objective with the same title is reused, so a
second run is a no-op. By default the tag records are kept (just detached from the
roadmap and its items); pass --delete-tags to also delete roadmap-scoped tags.

    python manage.py promote_objective_tags --roadmap 12 --dry-run
    python manage.py promote_objective_tags --roadmap 12
    python manage.py promote_objective_tags --roadmap 12 --delete-tags
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from roadmap.models import Roadmap, Tag, Objective


class Command(BaseCommand):
    help = "Promote a roadmap's legacy objective tags to durable Objective entities."

    def add_arguments(self, parser):
        parser.add_argument('--roadmap', type=int, required=True, help='Roadmap pk to convert.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Report the plan without saving (rolls back).')
        parser.add_argument('--delete-tags', action='store_true',
                            help='Also delete roadmap-scoped objective tags once converted '
                                 '(central/shared tags are only detached, never deleted).')

    def handle(self, *args, **opts):
        roadmap = Roadmap.objects.filter(pk=opts['roadmap']).first()
        if roadmap is None:
            raise CommandError(f"Roadmap {opts['roadmap']} not found.")

        is_service = roadmap.roadmap_type == Roadmap.SERVICE
        objective_type = Tag.OBJECTIVE if is_service else Tag.GOV_OBJECTIVE
        tags = [t for t in roadmap.tags.all() if t.tag_type == objective_type]

        dry = opts['dry_run']
        team = roadmap.owning_team
        self.stdout.write(
            f"Roadmap {roadmap.pk} '{roadmap.name}' ({roadmap.roadmap_type}) — "
            f"team {team.name if team else 'none'} — {len(tags)} objective tag(s) "
            f"of type '{objective_type}'." + (" [DRY RUN]" if dry else ""))
        if not tags:
            self.stdout.write("Nothing to convert.")
            return

        with transaction.atomic():
            created = reused = items_moved = tags_deleted = 0
            for tag in tags:
                # Reuse a durable objective with the same title (idempotent), else create.
                if team is not None:
                    obj = Objective.objects.filter(team=team, title=tag.name).first()
                else:
                    obj = roadmap.objectives.filter(title=tag.name).first()
                if obj is None:
                    obj = Objective.objects.create(team=team, title=tag.name)
                    if team is None:
                        roadmap.objectives.add(obj)   # teamless: direct link
                    created += 1
                    verb = 'would create' if dry else 'created'
                else:
                    reused += 1
                    verb = 'reuse'

                # Move each item tagged with this objective tag onto the objective.
                tagged_items = list(roadmap.items.filter(tags=tag))
                for item in tagged_items:
                    if item.objective_id is None:
                        item.objective = obj
                        item.save(update_fields=['objective'])
                    item.tags.remove(tag)
                items_moved += len(tagged_items)

                roadmap.tags.remove(tag)   # stop the header showing it as a tag

                deleted_note = ''
                # Only delete tags scoped to THIS roadmap; never central/shared ones.
                if opts['delete_tags'] and tag.roadmap_id == roadmap.pk:
                    tag.delete()
                    tags_deleted += 1
                    deleted_note = ' + tag deleted'
                elif opts['delete_tags']:
                    deleted_note = ' (central tag kept)'

                self.stdout.write(
                    f"  {verb} objective '{tag.name}' ← {len(tagged_items)} item(s){deleted_note}")

            self.stdout.write(self.style.SUCCESS(
                f"Objectives: {created} created, {reused} reused | "
                f"item links moved: {items_moved} | tags deleted: {tags_deleted}"))

            if dry:
                self.stdout.write(self.style.WARNING("DRY RUN — rolling back, nothing saved."))
                transaction.set_rollback(True)
