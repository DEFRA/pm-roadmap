# Data migrations & the dry-run process

Some changes to the data can't be expressed as an ordinary Django schema
migration — they reshape *existing rows* according to logic (e.g. "turn every
legacy objective **tag** into a durable **Objective** and move the item links
across"). We do these as **management commands** rather than `RunPython`
migrations, because they need to be:

- **targeted** — run for one roadmap/team at a time, not blindly across the DB;
- **inspectable** — print exactly what they *would* do before touching anything;
- **re-runnable** — safe to run again if interrupted.

Production is a **live government database**. There is no "undo" once a command
has written. So the rule is simple and non-negotiable:

> **Never run a data-changing command against production without first running
> it with `--dry-run` and reading the plan.** Rehearse it against a *copy* of
> the real production database before it ever runs for real.

---

## What `--dry-run` is

`--dry-run` runs the command's full logic — reads the same rows, builds the same
plan, prints the same per-item report and summary — but **saves nothing**. You
see precisely what would change, with zero risk.

It is not a separate "preview" code path that might drift from the real thing:
it runs *the same code*, then throws the writes away. So a clean dry-run is
strong evidence the real run will behave identically (barring the data changing
underneath you between the two runs).

## How it works

The command wraps all its writes in a single database transaction and, at the
end of a dry run, forces a rollback:

```python
from django.db import transaction

with transaction.atomic():
    ...  # create objectives, re-point items, detach tags — all real ORM writes

    if dry_run:
        self.stdout.write("DRY RUN — rolling back, nothing saved.")
        transaction.set_rollback(True)   # abandon everything written above
```

Because SQLite honours the transaction, every insert/update/delete inside the
block is discarded together. Nothing is committed; the database is byte-for-byte
unchanged.

Two more properties make these commands safe to rehearse and repeat:

- **Idempotent** — running twice is a no-op the second time. `promote_objective_tags`,
  for example, reuses an existing durable objective with the same title instead
  of creating a duplicate, and skips items that already have an objective.
- **Non-destructive by default** — it detaches old tags rather than deleting
  them; deletion is opt-in (`--delete-tags`) and only ever touches
  roadmap-scoped tags, never central/shared ones.

## Commands that use it today

| Command | What it changes | Flags |
|---------|-----------------|-------|
| `promote_objective_tags` | Legacy objective **tags** on a roadmap → durable **Objective** entities; moves `Item.tags` → `Item.objective` | `--roadmap <pk>` (required), `--dry-run`, `--delete-tags` |

New data commands should follow the same pattern: `--dry-run` that rolls back, a
printed plan, a summary line of counts, and idempotent writes.

---

## Practical steps

There are two places you'll run these, and the dry-run comes first in both.

### A. Rehearse locally against a *copy* of production

This is the important one — do it before you ever touch the live environment.

1. **Get a fresh copy of the production database.** Production replicates its
   SQLite file to S3 via [litestream](../litestream.yml). Restore a snapshot to
   a scratch location (do **not** overwrite your working copy):

   ```bash
   litestream restore -o /tmp/prod-copy.sqlite3 <replica-url>
   ```

   (Use the bucket/endpoint for the CDP environment you're rehearsing against.
   If you can't restore directly, ask an admin for a recent snapshot.)

2. **Point a throwaway checkout at that copy.** The DB path is hardcoded to
   `data/db.sqlite3` (see `config/settings.py`), so work in a clone or a copied
   working tree and drop the snapshot in — never over the committed demo DB:

   ```bash
   cp /tmp/prod-copy.sqlite3 data/db.sqlite3
   ```

3. **Find the roadmap you're targeting** and note its pk (from the roadmap URL,
   the admin, or the shell):

   ```bash
   python manage.py shell -c "from roadmap.models import Roadmap; \
     [print(r.pk, r.name) for r in Roadmap.objects.all()]"
   ```

4. **Dry-run it and read the plan:**

   ```bash
   python manage.py promote_objective_tags --roadmap <pk> --dry-run
   ```

5. **Check the output** (see "How to check it" below). If it looks right, run it
   for real *against the copy* and re-verify — this proves the real path works
   end to end on production-shaped data:

   ```bash
   python manage.py promote_objective_tags --roadmap <pk>
   ```

6. Throw the copy away when you're done. It contains real government data —
   don't commit it, don't share it, delete it.

### B. Run it against production (on the CDP container)

Only after a clean local rehearsal. Because `--dry-run` rolls back, it is safe
to run **directly on the live container** — that's the whole point:

1. Open a shell on the running CDP container (where `data/db.sqlite3` is the
   live, litestream-backed database).
2. **Dry-run against the live data first:**

   ```bash
   python manage.py promote_objective_tags --roadmap <pk> --dry-run
   ```

   This reads the real rows and prints the real plan, but writes nothing.
3. Confirm the plan matches what you saw in rehearsal (same counts, same
   roadmap, same objective names).
4. **Run it for real:**

   ```bash
   python manage.py promote_objective_tags --roadmap <pk>
   ```

5. Verify in the app (the "Manage objectives" panel should now show the
   promoted objectives) and spot-check as below.

---

## How to check the output

A run prints one line per objective plus a summary. A dry run is tagged so you
can't mistake it for the real thing:

```
Roadmap 12 'Licensing service' (service) — team Licensing — 3 objective tag(s) of type 'objective'. [DRY RUN]
  would create objective 'Speed up appeals' ← 4 item(s)
  reuse objective 'Reduce backlog' ← 2 item(s)
  would create objective 'Improve first-response time' ← 0 item(s)
Objectives: 2 created, 1 reused | item links moved: 6 | tags deleted: 0
DRY RUN — rolling back, nothing saved.
```

What to check:

- **The header line** names the right roadmap, type, team, and the *number of
  objective tags* it found. Zero tags → "Nothing to convert" (the roadmap is
  probably already on durable objectives, or uses a different tag type).
- **Per-objective lines** — one per tag. `would create` / `created` = new
  durable objective; `reuse` = an existing objective with that title was found
  (idempotent). The `← N item(s)` count is how many items get re-pointed.
- **The summary counts** should add up to what you expect for that roadmap. If
  "created" is higher than the number of objectives you know the team has, or
  "item links moved" is wildly off, stop and investigate before running for real.
- **`DRY RUN — rolling back`** must be present on a dry run. If it isn't, you
  ran the real command.

Spot-check the result after a real run:

```bash
python manage.py shell -c "from roadmap.models import Roadmap; r=Roadmap.objects.get(pk=<pk>); \
  print('durable objectives:', list(r.owning_team.objectives.values_list('title', flat=True))); \
  print('remaining objective tags on roadmap:', [t.name for t in r.tags.all() if t.tag_type in ('objective','gov_objective')])"
```

After a successful promotion the roadmap should have durable objectives and no
remaining objective *tags* in its header.

---

## Rules of the road

- **The assistant (Claude) never runs these against production** and never
  handles production credentials or a production DB copy. A human contributor
  runs the CDP steps; the assistant can help read and sanity-check the dry-run
  output you paste back.
- **When cleaning up test data you created, delete by primary key, never by
  title** — a title match can hit a real record you didn't mean to touch.
- **Merges to `main` go through GitHub PRs.** These commands ship on a feature
  branch, get reviewed, merged, and released before you run them anywhere.
- **The copy is real data.** Treat any restored production snapshot as
  sensitive: keep it local, don't commit it, delete it when done.
