# Roadmap POC — Requirements and Scope Document

**Project:** Strategic Roadmap Visualization Tool  
**Status:** Active Development  
**Last Updated:** June 2, 2026

---

## 1. PROJECT OVERVIEW

A Django-based web application for visualizing organizational roadmaps with interactive Gantt charts, swimlane grouping, timeline filtering, and bulk item management via spreadsheet upload.

**Target Users:**
- Government/public sector strategy teams
- Roadmap administrators (manage items, tags, categories)
- Stakeholders viewing roadmaps (filter, group, inspect items)

---

## 2. CORE FEATURES IMPLEMENTED

### 2.1 Roadmap Management
- ✅ Create/edit roadmaps with name, organization, description, mission, vision
- ✅ Assign outcome and team tags directly to roadmaps
- ✅ View list of all roadmaps
- ✅ Detailed roadmap view with header panel showing metadata

### 2.2 Item Management
- ✅ Three item types: Activities, Milestones, Metrics
- ✅ Item fields:
  - Title (required), Description
  - Start date, End date (optional)
  - Priority (Low/Medium/High/Critical — activities only)
  - Size (S/M/L/XL/XXL — activities only)
  - PRD Link, Backlog Link (URLs — activities only)
  - Tags (many-to-many, multiple types)
  - Linked Activities (milestones/metrics can link to activities)

### 2.3 Tag System
Four tag types support flexible categorization:

| Tag Type | Display Name | Use Case | Example Values |
|----------|--------------|----------|-----------------|
| **Outcome** | Defra Outcomes | Strategic outcomes/goals | Thriving Places, Grow Revenue, Reduce Churn |
| **Gov Objective** | Gov Objectives | Government alignment | Productive & Regenerative Land |
| **Organisation** | Teams | Team/org ownership | Growth Team, Platform Team, Directorate |
| **Category** | Item Category | Workstream classification | Development, Discovery, Policy, Contracts |

**Tag Features:**
- Default colour: `#595959` (accessible grey)
- Assigned to items (many-to-many)
- Can be assigned to roadmaps for context
- Admin-created; no user creation in UI
- Imported via spreadsheet uploader

### 2.4 Gantt Chart Visualization

#### Timeline Modes
1. **Months** — Month-by-month columns
2. **Quarters** — Quarterly columns
3. **Hybrid** — Adaptive zones:
   - Quarterly view for dates 6+ months past
   - Monthly view for ±6 months from today
   - Quarterly view for 6–18 months future
   - Half-yearly for 18–42 months future
   - Yearly for 42+ months future

#### Timeline Logic
- Always starts at current month/quarter (not earliest item date)
- Ends at latest item end_date or +1 year from start
- Virtual timeline system compresses large periods for proportional display
- Columns: 180px sticky label column + dynamic width timeline

#### Swimlanes
**Grouping by:**
- Gov Objectives (group items by selected gov objective tag)
- Defra Outcomes (group items by selected outcome tag)
- Teams (group items by selected organization/team tag)

**Sub-tracks within each swimlane:**
- Activities (teal bars with priority border)
- Milestones (orange diamonds with labels)
- Metrics (green bars)

**Bar Styling:**
- Activities: Teal `#28a197`, white text
- Milestones: Orange `#f46a25`, white text
- Metrics: Green `#00af41`, white text
- Priority borders: Low (green), Medium (orange), High (magenta), Critical (red)

### 2.5 Filtering and Grouping

#### Item Category Filter (Multi-select)
- Toggle pill buttons to add/remove category filters
- Shows items matching ANY selected category
- Preserved when switching time scales/groupings
- URL parameter: `?categories=1,2,3`

#### Swimlane Grouping Selector
- Dropdown in gantt header (top-left "Swim lane" cell)
- Switch between Gov Objectives, Defra Outcomes, Teams
- Preserves time scale and category filters

#### Tag Exploration
- Click tag pills in header to view tag details/description
- Modal overlay showing tag metadata

### 2.6 Spreadsheet Uploader

**Template Features:**
- Downloadable `.xlsx` template from admin
- Pre-formatted with examples
- Includes Notes tab documenting columns

**Upload Columns:**
| Column | Required | Notes |
|--------|----------|-------|
| Roadmap ID (B1) | Yes | Single roadmap per upload |
| Row ID | Recommended | Helper for linking activities |
| Item Type | Yes | activity \| milestone \| metric |
| Title | Yes | Updates on match |
| Description | Optional | Free text |
| Start Date | Optional | DD/MM/YYYY, YYYY-MM-DD, DD-MM-YYYY, MM/DD/YYYY |
| End Date | Optional | DD/MM/YYYY, YYYY-MM-DD, DD-MM-YYYY, MM/DD/YYYY |
| Priority | Optional | low \| medium \| high \| critical |
| Size | Optional | S \| M \| L \| XL \| XXL |
| PRD Link | Optional | Full URL |
| Backlog Link | Optional | Full URL |
| Defra Outcomes | Optional | Comma-separated tag names (pre-create tags) |
| Gov Objectives | Optional | Comma-separated tag names (pre-create tags) |
| Teams | Optional | Comma-separated tag names (pre-create tags) |
| Categories | Optional | Comma-separated tag names (pre-create tags) |
| Linked Activities | Optional | Comma-separated Row IDs of activities in same upload |

**Upload Logic:**
- Match on roadmap ID + title (updates if exists, creates if new)
- Auto-detect header row (scans rows 2–5 for "Title")
- Non-fatal tag errors (item saved without bad tags)
- Non-fatal date parse errors (left blank)
- Second pass wires linked activities using Row ID mapping
- Results summary: created, updated, skipped counts + error/warning logs

### 2.7 Admin Interface

**Django Admin Features:**
- Tag management (CRUD, filter by type)
- Roadmap management (list, edit, inline items)
- Item management (list, edit, filter by type/priority/size/roadmap/tags)
- Upload items page: `/admin/roadmap/upload-items/`
- Template download: `/admin/roadmap/upload-items/template/`
- Item admin password: `admin` / `admin`

---

## 3. DATA MODEL

### Tag
```
- id (PK)
- name (CharField, 100 chars)
- tag_type (CharField, choices: outcome | gov_objective | organisation | category)
- colour (CharField, hex code, default: #595959)
- description (TextField, optional)
```

### Roadmap
```
- id (PK)
- name (CharField, 200 chars)
- description (TextField, optional)
- organisation (CharField, 200 chars, optional)
- mission (TextField, optional)
- vision (TextField, optional)
- tags (M2M to Tag, optional)
- created_at (DateTimeField, auto)
```

### Item
```
- id (PK)
- roadmap (FK to Roadmap)
- item_type (CharField, choices: activity | milestone | metric)
- title (CharField, 200 chars)
- description (TextField, optional)
- priority (CharField, choices: low | medium | high | critical, optional)
- size (CharField, choices: S | M | L | XL | XXL, optional)
- prd_link (URLField, optional)
- backlog_link (URLField, optional)
- start_date (DateField, optional)
- end_date (DateField, optional)
- tags (M2M to Tag, optional)
- linked_activities (M2M to self, optional, limited to activities)
```

**Item Properties:**
- `outcome_tags` — filters tags by OUTCOME type
- `organisation_tags` — filters tags by ORGANISATION type
- `category_tags` — filters tags by CATEGORY type

---

## 4. USER FLOWS

### Admin: Create/Upload Items
1. Admin goes to `/admin/roadmap/upload-items/`
2. Downloads template spreadsheet
3. Fills in items (title, dates, type, tags, links)
4. Pre-creates any new tags in admin
5. Uploads spreadsheet (roadmap ID must be in B1)
6. Sees results: created/updated/skipped counts
7. Errors/warnings display (e.g., missing tags, date parse failures)
8. Items appear on roadmap immediately

### Stakeholder: Explore Roadmap
1. Navigate to roadmap detail page
2. View header: mission, vision, outcome/objective/team tags
3. Select time scale: Months / Quarters / Hybrid
4. Select swimlane grouping: Gov Objectives / Defra Outcomes / Teams
5. Toggle item categories: multi-select category filters
6. See items grouped and filtered accordingly
7. Click item bar/milestone to see full details in modal
8. Click tag pills to view tag description/metadata

### Admin: Link Milestones to Activities
1. Create Activity with title
2. Create Milestone with Row ID reference to Activity
3. Upload spreadsheet with linked activity Row IDs in "Linked Activities" column
4. System wires relationship automatically

---

## 5. TECHNICAL STACK

### Backend
- **Framework:** Django 5.2.14
- **Database:** SQLite (default, can be swapped)
- **Package Manager:** pip
- **Key Dependencies:**
  - `openpyxl==3.1.5` — Excel import/export
  - Django ORM for data persistence

### Frontend
- **Templating:** Django Templates (Jinja2-like)
- **Interactivity:** Alpine.js 3.x (CDN)
- **Styling:** Custom CSS + CSS Variables (design tokens)
- **Build System:** None (no npm, no compilation)

### Deployment
- Development server: `python manage.py runserver`
- Project root: `/Users/mark/Documents/MARK/DEV/roadmap-poc/`
- Settings: `config/settings.py`
- App: `roadmap/`

---

## 6. DESIGN & STYLING

### Colour Palette (Accessibility-focused)
| Purpose | Colour | Hex |
|---------|--------|-----|
| Background | White | `#ffffff` |
| Surface (cards) | Near-white | `#f8f9fa` |
| Elevated (headers) | Light grey | `#edf0f4` |
| Text (main) | Near-black | `#111111` |
| Text (muted/labels) | Grey | `#595959` |
| Border (subtle) | Light grey | `#e2e8f0` |
| Border (medium) | Medium grey | `#94a3b8` |
| Accent (primary) | Magenta | `#801650` |
| Accent (hover) | Dark magenta | `#5e0f3b` |
| Activity bars | Teal | `#28a197` |
| Milestone bars | Orange | `#f46a25` |
| Metric bars | Green | `#00af41` |
| Nav background | Dark grey | `#111827` |

### Typography
- **Headlines:** Outfit (700 weight) — geometric, strong at display sizes
- **Body/Labels:** Lexend (400 weight) — accessibility-optimized, reduces reading fatigue
- Both from Google Fonts (CDN)

### Layout
- Sticky sidebar (180px) for swimlane labels
- Horizontal scrolling for timeline
- CSS Grid for gantt structure
- Responsive but primarily desktop-focused

---

## 7. VIRTUAL TIMELINE SYSTEM

**Why?** Proportional month columns would make year columns 12× wider; virtual units compress large periods.

**How:**
- Assign "virtual days" to each column type:
  - Month: 30 virt days
  - Quarter: 42 virt days
  - Half: 54 virt days
  - Year: 70 virt days
- `_date_to_virtual_pct()` maps calendar dates → % position in virtual timeline
- `_item_to_bar()` uses virtual % for bar `left_pct` and `width_pct`
- Result: all column types display proportionally on screen

**Hybrid Example:**
- Past 6m (before today): Quarterly
- ±6m (around today): Monthly
- 6–18m future: Quarterly
- 18–42m future: Half-yearly
- 42m+ future: Yearly

---

## 8. ADMIN FEATURES (Not Accessible to Stakeholders)

### Create/Edit Tags
- `/admin/roadmap/tag/`
- Set: name, type, colour, description
- Filter by type

### Create/Edit Roadmaps
- `/admin/roadmap/roadmap/`
- Set: name, org, description, mission, vision
- Assign tags
- Inline: add/edit items

### Create/Edit Items
- `/admin/roadmap/item/`
- Set all fields (title, dates, priority, size, links, tags)
- Filter by type, priority, size, roadmap, tags
- Search by title/description

### Bulk Upload
- `/admin/roadmap/upload-items/`
- Download template
- Upload spreadsheet
- View results (created/updated/skipped/errors/warnings)

---

## 9. CURRENT CONSTRAINTS & LIMITATIONS

### By Design
- ✅ Single roadmap per upload (Roadmap ID in B1)
- ✅ Tags must pre-exist (no user creation in uploader)
- ✅ Dates parsed in 4 formats; invalid dates left blank
- ✅ Match on roadmap + title for updates
- ✅ No user authentication/authorization (admin-only via Django)
- ✅ SQLite database (single-user dev, not production-ready)

### Known Limitations (Future Enhancements)
- No real-time sync (refresh page to see other users' changes)
- No user roles/permissions (all or nothing for admin access)
- No audit trail (no history of who changed what)
- No version control (overwrites on title match)
- No duplicate item prevention (same title on same roadmap = update)
- No bulk edit in UI (spreadsheet only)
- No export (data stuck in DB, manual spreadsheet export needed)
- No reminders/notifications

---

## 10. FILE STRUCTURE

```
roadmap-poc/
├── config/                          # Django project settings
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── roadmap/                         # Main app
│   ├── migrations/                  # Database migrations
│   ├── templates/roadmap/           # User-facing templates
│   │   ├── base.html                # Base layout + nav
│   │   ├── roadmap_list.html        # All roadmaps
│   │   └── roadmap_detail.html      # Gantt + filters + header
│   ├── templates/admin/roadmap/     # Admin templates
│   │   ├── upload_items.html
│   │   └── roadmap/change_list.html
│   ├── static/css/
│   │   ├── design-tokens.css        # Colour, spacing, fonts
│   │   └── style.css                # Components, layout
│   ├── static/fonts/                # Custom fonts (if used)
│   ├── models.py                    # Tag, Roadmap, Item
│   ├── views.py                     # Roadmap list/detail, gantt logic
│   ├── admin.py                     # Django admin config
│   ├── importers.py                 # Spreadsheet parsing/upload
│   └── urls.py                      # URL routing
├── manage.py                        # Django CLI
├── requirements.txt                 # Dependencies
└── venv/                            # Virtual environment

```

---

## 11. API & QUERY PARAMETERS

### Roadmap Detail View
**URL:** `/roadmap/<roadmap_id>/`

**Query Parameters:**
| Param | Values | Default | Effect |
|-------|--------|---------|--------|
| `group_by` | outcome, gov_objective, organisation | outcome | Swimlane grouping |
| `time_scale` | months, quarters, hybrid | months | Timeline columns |
| `categories` | Comma-separated tag IDs | (none) | Filter items by category |

**Example:** `/roadmap/1/?group_by=organisation&time_scale=hybrid&categories=1,3,5`

---

## 12. TESTING & QA

### Manual Testing Completed ✅
- Spreadsheet upload (create, update, date parsing, tag linking)
- Swimlane switching (Gov Objectives ↔ Teams ↔ Outcomes)
- Time scale switching (Months → Quarters → Hybrid)
- Multi-category filtering (toggle multiple categories)
- Item modal (details display, tag view)
- Header tag pills (click to view description)
- Linked activities (milestones linking to activities)

### Areas for Testing
- Edge cases: very long item titles, special characters in names
- Large datasets (100+ items, many swimlanes)
- Browser compatibility (desktop Firefox/Chrome/Safari)
- Mobile responsiveness (partial support, primarily desktop)
- Admin performance (bulk operations)

---

## 13. ROADMAP (Future Work)

### Short Term
- [ ] Export roadmap to PDF
- [ ] User authentication & role-based access
- [ ] Item search/global filter
- [ ] Bulk edit in UI (not just spreadsheet)
- [ ] Custom date formats per region

### Medium Term
- [ ] Roadmap templates (copy existing roadmap)
- [ ] Dependency graph (activity → activity links)
- [ ] Risk/status indicators on bars
- [ ] Comments/notes on items
- [ ] Audit trail (history of changes)

### Long Term
- [ ] Multi-team workspaces
- [ ] Real-time collaboration
- [ ] External integrations (Jira, Asana, GitHub)
- [ ] API for programmatic access
- [ ] Mobile app

---

## 14. INSTALLATION & SETUP

### Prerequisites
- Python 3.9+
- pip
- Virtual environment support

### Quick Start
```bash
# Clone/navigate to project
cd roadmap-poc

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Create superuser (admin account)
python manage.py createsuperuser

# Start development server
python manage.py runserver

# Access
# - Roadmaps: http://localhost:8000/
# - Admin: http://localhost:8000/admin/
```

### Default Credentials
- **Username:** admin
- **Password:** admin (change in production)

---

## 15. DEPLOYMENT NOTES

**Not Production-Ready:**
- SQLite is single-user, file-based
- Debug mode is enabled (security risk)
- No HTTPS
- No database backups configured
- No CDN/caching strategy

**For Production:**
- Switch to PostgreSQL or MySQL
- Set `DEBUG = False`
- Configure allowed hosts
- Use WhiteNoise or CDN for static files
- Add SSL/HTTPS
- Implement database backups
- Deploy to cloud (AWS/GCP/Heroku/etc.)

---

## APPENDIX: KEY FORMULAS

### Virtual Timeline Calculation
```python
total_v = sum(c['virt_days'] for c in columns)
v_pos = col['v_start'] + (date - col['start']).days / col_days * col['virt_days']
pct = v_pos / total_v * 100
```

### Item Update Logic
```python
Item.objects.update_or_create(
    roadmap=roadmap,
    title=title,  # <- match key
    defaults={...}  # <- upsert fields
)
```

### Multi-Category Filter
```python
items = items.filter(
    tags__in=Tag.objects.filter(
        pk__in=selected_ids,
        tag_type=Tag.CATEGORY
    )
).distinct()
```

---

**Document Version:** 1.0  
**Last Reviewed:** June 2, 2026  
**Owner:** Mark (Developer)
