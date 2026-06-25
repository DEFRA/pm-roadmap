# Roadmap (Django)

A roadmap visualisation tool for planning and communicating delivery across
objectives, outcomes, and teams. Built with Django + SQLite, server-rendered
with Alpine.js for in-page interactivity.

This is the **Django proof of concept**. A separate Node.js/Express rebuild
exists; this app has been brought up to the same feature scope.

> ⚠️ **Proprietary — all rights reserved.** Work-in-progress proof of concept,
> not licensed for public or third-party use. See [LICENSE](LICENSE).

---

## Features

- **Gantt timeline** — months / quarters / hybrid scales, with a virtual
  timeline that compresses long periods so near-term detail stays readable.
- **Swimlanes** — group the timeline by Defra Outcome, Objective, or Team.
- **Group vs Service roadmaps** — group roadmaps use central **Government
  Objectives**; service roadmaps use roadmap-specific **Objectives**.
- **In-page editing** (no admin round-trip):
  - Create / edit roadmaps and items in modals
  - Manage tags — click chips to add/remove; create scoped Objectives & Teams;
    select-only for central Outcomes & Gov Objectives
  - Click any chip to view and edit its description
- **Roadmap list** — search by name + filter by organisation.
- **Per-roadmap tag scoping** — Teams and service Objectives are unique to a
  roadmap; Outcomes, Gov Objectives, and Categories are central (admin-defined).
- **Coloured tag chips** — auto-assigned from an accessible palette.
- **Export** — download the current view as PNG or PDF.
- **Spreadsheet import** — bulk-create items from an `.xlsx` template
  (downloadable from the admin).

---

## Tech stack

| Layer | Choice |
|-------|--------|
| Backend | Django 5.2 |
| Database | SQLite |
| Templating | Django templates |
| Interactivity | Alpine.js |
| Data layer | JSON endpoints under `/api/` (CSRF-protected) |
| Import/export | openpyxl · html2canvas + jsPDF |

---

## Getting started

Requires Python 3.11+.

```bash
git clone https://github.com/MarkJYoung/roadmap-django.git
cd roadmap-django

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

python manage.py migrate
python manage.py runserver
```

Then open <http://localhost:8000/>.

The repository ships with a populated `db.sqlite3` containing demo data, so the
app is usable immediately. To explore the admin, create a superuser:

```bash
python manage.py createsuperuser
```

…then sign in at <http://localhost:8000/admin/>.

---

## Data model

| Model | Purpose |
|-------|---------|
| **Roadmap** | `name`, `team`, `organisations` (M2M), `roadmap_type` (group/service), `mission`, `vision`, `tags` |
| **Organisation** | Delivery organisation (`name`, `abbreviation`, `description`) |
| **Item** | Activity / milestone / metric with dates, priority, size, links, tags, linked activities |
| **Tag** | `outcome` · `gov_objective` · `objective` · `organisation` (Team) · `category`. Scoped types carry a `roadmap` FK; central types are global. |

`roadmap.tags` is the single source of truth for which objectives / outcomes /
teams appear in a roadmap's header.

---

## JSON API

Same-origin endpoints backing the modals (CSRF token sent via `X-CSRFToken`):

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/organisations/` | List organisations |
| `GET` `POST` | `/api/tags/` | List (filter by `?type=` & `?roadmap=`) / create |
| `PUT` `DELETE` | `/api/tags/<id>/` | Update / delete a tag |
| `POST` | `/api/roadmaps/` | Create a roadmap |
| `PUT` `DELETE` | `/api/roadmaps/<id>/` | Update (incl. tag membership) / delete |
| `POST` | `/api/roadmaps/<id>/items/` | Create an item |
| `PUT` `DELETE` | `/api/items/<id>/` | Update / delete an item |

---

## Tests

A Django `TestCase` suite (no extra dependencies) covers models, the JSON API,
the gantt/view logic, and the spreadsheet importer:

```bash
python manage.py test
```

Tests run against a throwaway test database — the committed `db.sqlite3` is left
untouched. Modules live in `roadmap/tests/` (`test_models.py`, `test_api.py`,
`test_views.py`, `test_importer.py`).

---

## Project layout

```
config/             Django project settings & URLs
roadmap/
  models.py         Roadmap, Organisation, Item, Tag
  views.py          List + detail pages, gantt builder
  api.py            JSON endpoints
  importers.py      Spreadsheet import + template generator
  admin.py          Django admin
  migrations/       Schema + data migrations
  templates/
static/             CSS + JS (Alpine component, export)
```

---

## Notes

- `DEBUG = True` and a development `SECRET_KEY` are committed for convenience —
  set real values via environment before any non-local deployment.
- The committed `db.sqlite3` is demo data, not production data.
