# PM-Roadmap — onboarding

A one-page orientation for new contributors: how the application is built, how to
run it, how it ships to the platform, and the rules that keep it steady while we
host unrelated internal prototypes alongside it.

| | |
|---|---|
| **Framework** | Django 5.2 · Python 3.13 |
| **Database** | SQLite + Litestream → S3 |
| **Front end** | Server-rendered + Alpine.js (no build step) |
| **Hosting** | Defra Core Development Platform (Docker) |
| **Repo** | `DEFRA/pm-roadmap` |
| **Tests** | 196 · `python manage.py test` |

---

## 1. What it is

PM-Roadmap is a roadmap and OKR visualisation tool for planning and communicating
delivery across Defra. Teams build a gantt-style timeline of **activities**,
**milestones** and **key results**, grouped into swim lanes by Defra Outcome,
Objective or squad.

- **Two roadmap kinds.** *Group* roadmaps track central Government Objectives;
  *service* roadmaps track a team's own Objectives.
- **Durable OKRs.** An Objective is owned by a team and reused across quarters;
  each Key Result carries its own planning period (its `ObjectiveSet`), so one
  objective is a single lane spanning many quarters.
- **Edit in place.** Items are created, dragged, resized and reordered on the
  chart; there's no separate admin round-trip for day-to-day work.
- **No user accounts.** The app has no auth of its own — access is controlled by
  the CDP network boundary. The Django admin manages reference data.
- **Now also a prototype host.** The same deployment hosts small internal
  prototypes under sub-paths (e.g. `/prototype`), so a new idea doesn't need its
  own platform set-up. See [§9 Ground rules](#9-ground-rules-for-prototypes).

## 2. Architecture

One Django project (`config`) with a single application (`roadmap`). It's
deliberately simple: server-rendered HTML, a thin JSON API for the in-page
editing, and a single SQLite file kept durable by Litestream.

- **Server.** Django templates render every page; the gantt is built server-side
  in `views.py` on a compressed "virtual timeline". `/api/…` returns JSON and is
  CSRF-protected; it backs the create/edit modals and drag-to-save. `access.py`
  centralises visibility logic — which objectives and key results a roadmap shows.
- **Browser.** No build step. Alpine.js loads from a CDN for modal state and
  panels. Small vanilla-JS modules handle gantt drag/resize (`item-drag.js`),
  lane reorder (`reorder.js`) and PNG/PDF export (`export.js`). Static assets are
  served by Django with cache-busting query strings (`?v=…`).
- **Data.** One SQLite file, `data/db.sqlite3` (WAL mode). **Litestream**
  continuously replicates it to S3; on boot the container restores the latest
  copy, so the single file survives restarts. Spreadsheet import/export via
  `openpyxl`.
- **Platform.** Packaged as a Docker image and run on the Defra Core Development
  Platform. `ecs-logging` emits structured JSON logs the platform collects.
  Hostnames are `pm-roadmap.<env>.cdp-int.defra.cloud` per environment.

> **Known caveat.** The container currently starts Django's development server
> (`runserver` on port 8085) rather than a production WSGI server — there's a
> `TODO` in `start-service.sh` to replace it. Keep that in mind before relying on
> it for anything heavy.

## 3. How a request flows

`config/urls.py` sends `/admin/` to the Django admin and everything else into
`roadmap.urls` (namespace `roadmap`). A page view renders a template; an in-page
edit posts JSON to the API.

```
Browser ──▶ config/urls.py ──▶ views · api ──▶ models ──▶ SQLite
(GET a roadmap,   (admin ·      (build gantt /   (Litestream mirrors
 POST/PUT edit)    roadmap)      read-write)       to S3)
```

Page views (`views.py`, `views_okr.py`, `views_team.py`) compute swim lanes and
bar positions and hand them to templates. The gantt's drag, resize and reorder
call `/api/…` to persist a change, then the page re-reads. Objective/key-result
visibility always runs through `access.py`, so one rule set governs what appears
where.

## 4. Database schema

Eight models in `roadmap/models.py`. A **Team** (inside an **Organisation**) owns
its roadmaps and objectives; **Items** sit on a roadmap; **Objectives** hold
**Key Results** that are time-boxed by **Objective Sets**.

| Model | Purpose / key fields |
|---|---|
| **Organisation** | A delivery org — `name`, abbreviation, description. |
| **Team** | `organisation` → · `name`, members. Owns roadmaps, sets & objectives. |
| **Tag** | `tag_type`: outcome · gov_objective · objective · organisation (squad) · category. Scoped (roadmap FK) *or* central. |
| **Roadmap** | `roadmap_type`: group · service · `owning_team` → · M2M organisations, tags, objective_sets, objectives, hidden_objectives · `sync_okrs` · `archived`. |
| **Item** | `item_type`: activity · milestone · metric · `roadmap` → · `objective` → · start/end dates · row · M2M tags, linked_activities, key_results. |
| **ObjectiveSet** | An OKR cycle (planning period). `scope`: group · team · organisation → · team → · start/end · `archived`. |
| **Objective** | `team` → · `sets` (M2M) · title · sort_order · `archived`. Durable — reused across periods. |
| **KeyResult** | `objective` → · `objective_set` → (the period) · start/target/current · direction · status · dates · `archived`. |

**Relationships**

```
Organisation 1─∗ Team 1─∗ Roadmap · ObjectiveSet · Objective
Roadmap      1─∗ Item        Item      ∗─1 Objective (optional)
Objective    1─∗ KeyResult   Objective ∗─∗ ObjectiveSet (set membership)
KeyResult    ∗─1 ObjectiveSet (the period it plots in)
```

Schema changes are ordinary Django migrations — 32 so far. There's a 2-step
dry-run convention for *data* migrations against the live DB: see
[`docs/dry-run.md`](dry-run.md).

## 5. File structure

The whole application lives in the `roadmap` app (~6,000 lines of Python). Project
config is thin.

```
config/              # Django project: settings, urls, wsgi/asgi
roadmap/             # the single application
  models.py          # the 8 models above
  views.py           # list + detail pages, the gantt builder
  views_okr.py       # objective / set / key-result pages
  views_team.py      # team pages
  api.py             # JSON endpoints behind the modals (/api/…)
  access.py          # visibility rules (what shows on a roadmap)
  forms.py           # objective + key-result forms
  importers.py       # .xlsx import / template generator
  okr_periods.py     # quarter / period helpers
  admin.py urls.py apps.py
  management/        # manage.py commands (e.g. promote_objective_tags)
  migrations/        # 32 migrations
  templates/roadmap/ # server-rendered pages + partials
  tests/             # 196 tests
static/              # css + js (Alpine, item-drag, reorder, export)
data/db.sqlite3      # the database (demo data committed)
docs/dry-run.md      # data-migration safety guide
Dockerfile  entrypoint.sh  start-service.sh  litestream.yml
requirements.txt   .github/workflows/   # CI: build on PR, publish on merge
```

## 6. Dependencies

Intentionally lean. No front-end build toolchain, no bundler, no Node. Everything
pinned in `requirements.txt`.

**Python**

- **Django 5.2.14** — web framework (with asgiref, sqlparse).
- **openpyxl** + et_xmlfile — spreadsheet import/export.
- **ecs-logging** — structured JSON logs for the platform.
- **PyYAML** — config / data handling.

**Runtime & front end**

- **Python 3.13** in the container (3.11+ to develop).
- **Litestream** — SQLite → S3 replication (installed in the image).
- **Alpine.js** — via CDN, no install, no build.

## 7. Install & run locally

You'll need Python 3.11+ and write access to the DEFRA repo (push over SSH). The
repo ships a populated `db.sqlite3`, so it runs with demo data immediately — no
external services needed to develop.

```bash
# clone (SSH — you'll need your key added to the DEFRA org)
git clone git@github.com:DEFRA/pm-roadmap.git
cd pm-roadmap

# isolated environment + dependencies
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# apply migrations and start the dev server
python manage.py migrate
python manage.py runserver        # → http://localhost:8000/

# optional: an admin login for /admin/
python manage.py createsuperuser

# run the test suite (keep it green)
python manage.py test
```

> **Don't commit the dev database.** `data/db.sqlite3` is demo data; a real
> production copy is live government data and must never be committed, shared, or
> pasted into a chat.

## 8. How we deploy

Everything goes through GitHub and the Core Development Platform. `main` is
protected — you ship by merging a reviewed pull request, never by pushing.

```
branch → PR ──▶ PR check ──▶ merge to main ──▶ CDP portal
             (Docker image   (Publish workflow   (deploy to
              builds, must    → CDP image)        dev / test / prod)
              pass)
```

**What runs in the container** (`entrypoint.sh`):

1. Litestream restores the DB from S3.
2. `python manage.py migrate`.
3. Litestream replicates while the server runs on port 8085.

The `ENVIRONMENT` variable sets the allowed host and CSRF origin to
`pm-roadmap.<env>.cdp-int.defra.cloud`.

> **Migrations gate the deploy.** `migrate` runs *before* the server starts. A
> migration that fails stops the whole site from coming up — so a broken
> migration from *any* code (prototype included) takes PM-Roadmap down with it.
> Treat migrations as production-critical.

## 9. Ground rules for prototypes

Prototypes are welcome on this deployment, mounted under their own sub-path (e.g.
`/my-prototype`). The deal is simple: a prototype must be able to come and go
without ever disturbing PM-Roadmap. These rules keep that true. The test for any
change is — **could I delete this prototype by removing its app, its URL line and
its migrations, and leave `roadmap` untouched?**

1. **One Django app per prototype.** Run `manage.py startapp <name>` and add it
   to `INSTALLED_APPS`. All of your code lives there. **Never edit the `roadmap`
   app.**
2. **Mount under your own URL prefix.** Add one line to `config/urls.py`:
   `path('<name>/', include('<name>.urls'))`, with a unique app namespace. Don't
   change the roadmap root include or its routes.
3. **Never touch roadmap's models or migrations.** Your app owns its own tables
   and migration history. Don't edit `roadmap/models.py` or anything in
   `roadmap/migrations/`. **No shared tables.**
4. **Treat migrations as production-critical.** They run on every deploy, before
   the server starts — a failure takes the whole site down. Keep them additive
   and reversible, test them, and dry-run data migrations on a copy of the real
   DB (`docs/dry-run.md`). It's one shared SQLite file replicated by Litestream,
   so keep prototype tables modest and avoid heavy write loads.
5. **Isolate templates & static.** Put templates under `<app>/templates/<name>/…`
   and assets under `static/<name>/…`. Give your prototype its own base template.
   **Don't override roadmap's `base.html` or shared files.**
6. **Touch shared settings additively only.** `config/settings.py` is shared.
   Adding your app to `INSTALLED_APPS` is fine. Don't change `DATABASES`,
   `DEBUG`, the `ALLOWED_HOSTS`/`CSRF` logic or `STATIC` settings, and **add no
   site-wide middleware** that intercepts every request.
7. **Keep the build and the tests green.** The PR check builds the Docker image
   and it must pass. Keep `manage.py test` green — put your tests in your own
   app. Pin any new dependency in `requirements.txt` and keep it light; a
   dependency that breaks Django or the image breaks everyone.
8. **Branch → PR → review → merge.** Small pull requests, reviewed before merge.
   **Never push to `main`** — it's protected, and a merge auto-deploys.
9. **Don't assume auth — and don't add it globally.** The site has no user
   accounts; access is the CDP network boundary. If your prototype needs sign-in,
   scope it to your own views. **No global auth middleware** — it would lock
   everyone out of roadmap.
10. **Stay removable.** Design so the prototype can be retired cleanly: its app,
    one URL line, its own migrations and assets — gone, with roadmap unaffected.
    If something you're about to do can't be undone that cleanly, it belongs in a
    conversation first.

## 10. Data & assets for prototypes

A common first question: *can my prototype have its own database and its own CSS?*

**CSS, templates and static files — yes, keep them fully separate.** These are
just files served by the one Django process. Put CSS/JS under `static/<name>/…`
and templates under `<app>/templates/<name>/…` with your own base template.
Nothing collides as long as you namespace under your app's name and don't
override roadmap's files (ground rules 2 and 5). No infra involved.

**Database — "your own tables" yes; "your own separate database" has a catch.**
There are two things people mean:

- **Your own tables, isolated from roadmap's.** This is automatic: every app's
  models create their own `<app>_<model>` tables in the shared DB. Your prototype
  never touches `roadmap_*` and roadmap never sees yours. In practice this is the
  isolation you want, and it's free — this is ground rule 3. **This is the
  recommended model: share the one SQLite database, keep your own tables.**

- **A genuinely separate database (a second file or server).** Possible in Django
  (multi-`DATABASES` + a router), but **it won't persist here**, for a reason
  specific to this app:
  - The whole app is one SQLite file (`data/db.sqlite3`), and **Litestream
    replicates only that one path** (see `litestream.yml`).
  - The CDP container filesystem is **ephemeral** — on every restart/redeploy
    Litestream restores that one file and nothing else.
  - So a *second* SQLite file would have its data **silently lost on the next
    deploy**, and wiring it up would mean editing the shared `DATABASES` setting,
    which ground rule 6 says to leave alone.

**If a prototype genuinely needs its own datastore** (large data, a different
shape, real separation), that's a deliberate step to agree with whoever owns the
CDP tenant — not a solo change. The platform can provision backing services (the
local compose already wires up MongoDB, Redis and S3/localstack), so the clean
route is a **CDP-provisioned database the prototype talks to directly**, keeping
it out of PM-Roadmap's SQLite file and Litestream entirely.

> **In short:** separate CSS/templates — always. Separate *tables* — by default.
> A separate *persistent* database — only via a CDP-provisioned service agreed
> with the platform owner; never bolt a second SQLite file onto the shared one.

---

*Questions → ask in the team channel before changing anything shared (settings,
migrations, the `roadmap` app, or `main`).*
