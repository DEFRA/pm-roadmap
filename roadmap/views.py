from django.shortcuts import render, get_object_or_404
from django.db import models
from django.views.decorators.csrf import ensure_csrf_cookie
from datetime import date, timedelta
import calendar
import json

from .models import Roadmap, Item, Tag, Organisation, Objective

# Virtual "units" per column type — compresses large periods so they don't
# dominate the visual width relative to monthly/quarterly columns.
_VIRT_UNITS = {'month': 30, 'quarter': 42, 'half': 54, 'year': 70}
_BASE_PX_PER_UNIT = 100 / 30  # keeps month columns at ~100 px minimum


@ensure_csrf_cookie
def roadmap_list(request):
    roadmaps = Roadmap.objects.prefetch_related('organisations', 'items').all()
    roadmap_data = [
        {
            'id': r.pk,
            'name': r.name,
            'description': r.description,
            'item_count': r.items.count(),
            'created': r.created_at.strftime('%d %b %Y'),
            'org_ids': [o.pk for o in r.organisations.all()],
            'org_badges': [o.abbreviation or o.name for o in r.organisations.all()],
        }
        for r in roadmaps
    ]
    organisations = Organisation.objects.all()
    return render(request, 'roadmap/roadmap_list.html', {
        'roadmaps': roadmaps,
        'roadmaps_json': json.dumps(roadmap_data),
        'organisations': organisations,
    })


def roadmap_tree(request, pk):
    """A tree-style infographic of a roadmap's initiatives. Under each Defra
    outcome the branches ladder up to it:
      • Objective → its Key results → the Activities assigned to each key result
        → each activity's Milestones
      • Activities not assigned to any key result hang directly off the outcome
        (still with their milestones).
    An activity is "assigned to a key result" via its direct key_results link
    (set in the roadmap item modal). Outcomes with nothing linked still appear;
    activities with no outcome collect under a placeholder."""
    from collections import OrderedDict

    roadmap = get_object_or_404(Roadmap, pk=pk)
    activities = list(
        roadmap.items.filter(item_type=Item.ACTIVITY)
        .prefetch_related(
            'tags', 'objective__key_results__objective_set', 'linked_milestones_metrics',
            'key_results',
        )
        .order_by('title', 'pk')
    )

    def _new_bucket():
        # `_objectives` is a pk-keyed dict while building (dedupes objectives that
        # several activities share); finalised into the `objectives` list below.
        return {'activities': [], '_objectives': OrderedDict(), '_entries': []}

    def _activity_entry(act):
        milestones = sorted(
            (m for m in act.linked_milestones_metrics.all() if m.item_type == Item.MILESTONE),
            key=lambda m: (m.start_date or date.max, m.title),
        )
        return {'activity': act, 'milestones': milestones,
                '_kr_pks': {kr.pk for kr in act.key_results.all()}}

    def _add_objective(bucket, obj):
        if obj is not None and obj.pk not in bucket['_objectives']:
            bucket['_objectives'][obj.pk] = {
                'objective': obj, 'key_results': list(obj.key_results.all()),
            }

    # Seed every outcome assigned to the roadmap so empty ones still show.
    outcome_nodes = OrderedDict(
        (tag.pk, {'outcome': tag, **_new_bucket()})
        for tag in roadmap.tags.all() if tag.tag_type == Tag.OUTCOME
    )
    no_outcome = _new_bucket()

    for act in activities:
        outs = [t for t in act.tags.all() if t.tag_type == Tag.OUTCOME]
        entry = _activity_entry(act)
        targets = ([no_outcome] if not outs else
                   [outcome_nodes.setdefault(t.pk, {'outcome': t, **_new_bucket()}) for t in outs])
        for bucket in targets:
            bucket['_entries'].append(entry)
            _add_objective(bucket, act.objective)

    def _finalise(bucket):
        entries = bucket.pop('_entries')
        objectives = sorted(
            bucket.pop('_objectives').values(), key=lambda o: o['objective'].title.lower())
        assigned = set()
        for o in objectives:
            krs = []
            for kr in o['key_results']:
                kr_acts = [e for e in entries if kr.pk in e['_kr_pks']]
                assigned.update(e['activity'].pk for e in kr_acts)
                krs.append({'kr': kr, 'activities': kr_acts})
            o['key_results'] = krs
        bucket['objectives'] = objectives
        # Fallback branch: activities not assigned to any displayed key result.
        bucket['activities'] = [e for e in entries if e['activity'].pk not in assigned]
    for node in outcome_nodes.values():
        _finalise(node)
    _finalise(no_outcome)

    outcome_tree = sorted(outcome_nodes.values(), key=lambda n: n['outcome'].name.lower())

    # The picker lets you view one outcome's tree at a time (?outcome=<pk>), all of
    # them (default), or just the activities with no outcome (?outcome=none).
    selected = request.GET.get('outcome') or 'all'
    if selected == 'none':
        display_tree, display_no_outcome = [], no_outcome
    elif selected.isdigit() and int(selected) in outcome_nodes:
        display_tree, display_no_outcome = [outcome_nodes[int(selected)]], None
    else:
        selected = 'all'
        display_tree, display_no_outcome = outcome_tree, no_outcome

    # Totals reflect what is currently on screen so they stay coherent per outcome.
    shown = list(display_tree) + ([display_no_outcome] if display_no_outcome else [])
    act_ids, obj_ids, kr_ids, ms_ids = set(), set(), set(), set()

    def _count_activity(a):
        act_ids.add(a['activity'].pk)
        ms_ids.update(m.pk for m in a['milestones'])

    for bucket in shown:
        for a in bucket['activities']:          # fallback (unassigned) activities
            _count_activity(a)
        for o in bucket['objectives']:
            obj_ids.add(o['objective'].pk)
            for k in o['key_results']:
                kr_ids.add(k['kr'].pk)
                for a in k['activities']:       # activities nested under a key result
                    _count_activity(a)

    has_no_outcome = bool(no_outcome['activities'] or no_outcome['objectives'])
    return render(request, 'roadmap/roadmap_tree.html', {
        'roadmap': roadmap,
        'team': roadmap.owning_team,
        'outcome_tree': display_tree,
        'no_outcome': display_no_outcome,
        'outcome_options': outcome_tree,      # every outcome, for the picker
        'has_no_outcome': has_no_outcome,     # whether to offer the "No outcome" option
        'selected': selected,
        'totals': {
            'outcomes': len(display_tree),
            'objectives': len(obj_ids),
            'key_results': len(kr_ids),
            'activities': len(act_ids),
            'milestones': len(ms_ids),
        },
    })


@ensure_csrf_cookie
def roadmap_detail(request, pk):
    roadmap = get_object_or_404(Roadmap, pk=pk)
    # Default swimlane view is resolved after the roadmap type is known (below):
    # group roadmaps default to Defra Outcomes, service roadmaps to Objectives.
    group_by = request.GET.get('group_by')
    time_scale = request.GET.get('time_scale', 'months')
    selected_categories_str = request.GET.get('categories', '')

    # Item-type (sub-lane) visibility filter. Absent / all three selected = show all.
    ALL_TRACKS = ['metric', 'milestone', 'activity']
    selected_tracks = [t for t in request.GET.get('tracks', '').split(',') if t in ALL_TRACKS]
    if len(set(selected_tracks)) == len(ALL_TRACKS):
        selected_tracks = []  # all selected == no filter
    selected_tracks_str = ','.join(selected_tracks)
    visible_tracks = set(selected_tracks) if selected_tracks else set(ALL_TRACKS)
    # Sub-lanes render in this order; the lane name/handle sits on the first
    # visible one and the lane-separator border on the last visible one.
    _track_order = ['metric', 'milestone', 'activity']
    first_visible_track = next((t for t in _track_order if t in visible_tracks), None)
    last_visible_track = next((t for t in reversed(_track_order) if t in visible_tracks), None)

    items = roadmap.items.select_related('objective').prefetch_related('tags', 'linked_activities').all()

    # Parse and filter by multiple categories if selected (comma-separated IDs)
    selected_category_ids = []
    if selected_categories_str:
        try:
            selected_category_ids = [int(cid) for cid in selected_categories_str.split(',') if cid.strip()]
            if selected_category_ids:
                # Filter items that have ANY of the selected categories (OR logic)
                items = items.filter(tags__in=Tag.objects.filter(pk__in=selected_category_ids, tag_type=Tag.CATEGORY)).distinct()
        except (ValueError, Tag.DoesNotExist):
            selected_category_ids = []

    # ── Timeline window ──────────────────────────────────────────────────────
    # Default: start of the current quarter → end of the quarter containing the
    # last-ending item (or synced set). The user can override with ?start / ?end,
    # constrained to one year back and ten years forward from today.
    today = date.today()

    def _quarter_start(d):
        return d.replace(month=((d.month - 1) // 3) * 3 + 1, day=1)

    def _quarter_end(d):
        m = ((d.month - 1) // 3) * 3 + 3
        return d.replace(month=m, day=calendar.monthrange(d.year, m)[1])

    def _shift_years(d, years):
        try:
            return d.replace(year=d.year + years)
        except ValueError:  # 29 Feb in a non-leap target year
            return d.replace(year=d.year + years, day=28)

    def _parse_iso(s):
        try:
            return date.fromisoformat(s)
        except (TypeError, ValueError):
            return None

    range_min = _shift_years(today, -1)
    range_max = _shift_years(today, 10)

    from . import access
    applied_sets = list(access.applied_objective_sets(roadmap))
    dated_items = [i for i in items if i.start_date and i.end_date]
    end_candidates = [i.end_date for i in dated_items]
    end_candidates += [s.end_date for s in applied_sets if s.end_date]

    default_start = _quarter_start(today)
    default_end = _quarter_end(max(end_candidates)) if end_candidates \
        else _quarter_end(_shift_years(default_start, 1) - timedelta(days=1))
    if default_end < default_start:
        default_end = _quarter_end(default_start)

    custom_start = _parse_iso(request.GET.get('start'))
    custom_end = _parse_iso(request.GET.get('end'))
    timeline_start = custom_start or default_start
    timeline_end = custom_end or default_end

    # Clamp to the selectable window and snap to whole months (gantt columns).
    timeline_start = min(max(timeline_start, range_min), range_max).replace(day=1)
    timeline_end = min(max(timeline_end, range_min), range_max)
    timeline_end = timeline_end.replace(day=calendar.monthrange(timeline_end.year, timeline_end.month)[1])
    if timeline_end < timeline_start:
        timeline_end = _quarter_end(timeline_start)

    # Query-string fragment so toolbar links keep a custom window.
    date_qs = ''
    if custom_start:
        date_qs += f'&start={custom_start.isoformat()}'
    if custom_end:
        date_qs += f'&end={custom_end.isoformat()}'

    if time_scale == 'quarters':
        columns = _build_quarters(timeline_start, timeline_end)
    elif time_scale == 'hybrid':
        columns = _build_hybrid(timeline_start, timeline_end)
    else:
        time_scale = 'months'
        columns = _build_months(timeline_start, timeline_end)

    # Assign virtual positions and width_pct to all columns
    total_v = _build_virtual_timeline(columns)

    # Roadmap type drives which objectives are shown:
    #   group   → Government Objectives (gov_objective) — central, admin-defined
    #   service → Objectives (objective) — unique to this roadmap
    is_service = roadmap.roadmap_type == Roadmap.SERVICE
    objective_type = Tag.OBJECTIVE if is_service else Tag.GOV_OBJECTIVE
    objective_label = 'Objectives' if is_service else 'Gov Objectives'
    objective_creatable = is_service

    # Default view when none is requested: service roadmaps open on Objectives,
    # group roadmaps on Defra Outcomes.
    if not group_by:
        group_by = objective_type if is_service else Tag.OUTCOME

    # Build swimlanes using the virtual timeline for bar positioning
    tag_type_map = {
        'organisation': Tag.ORGANISATION,
        'gov_objective': Tag.GOV_OBJECTIVE,
        'objective': Tag.OBJECTIVE,
    }
    if group_by not in tag_type_map and group_by != 'outcome':
        group_by = 'outcome'
    if group_by == 'objective':
        # Objectives are first-class entities (not tags): lanes come from the
        # objectives synced/linked to this roadmap; items sit under item.objective.
        lanes = _build_objective_swimlanes(roadmap, items, columns, total_v)
    else:
        tag_type = tag_type_map.get(group_by, Tag.OUTCOME)
        lanes = _build_swimlanes(items, tag_type, columns, total_v)

    item_data = _serialise_items(lanes)

    # Parking lot column (undated activities/milestones) — always shown; it is
    # roughly one month wide beside the timeline.
    show_parking = True
    timeline_px = int(total_v * _BASE_PX_PER_UNIT)
    parking_col_px = int(timeline_px / len(columns)) if (show_parking and columns) else 0
    # Minimum gantt width: label col + optional parking col + timeline.
    gantt_min_width_px = 180 + parking_col_px + timeline_px

    # roadmap.tags is the single source of truth for what is "on" this roadmap.
    # Header pills + manage-tags selection both derive from it.
    roadmap_tags = list(roadmap.tags.all())
    by_type = lambda tt: [t for t in roadmap_tags if t.tag_type == tt]
    selected_tag_ids = [t.pk for t in roadmap_tags]

    # Selectable pools for the manage-tags modal. Scoped types (service
    # objectives, teams) are limited to this roadmap; central types are shared.
    if is_service:
        objective_pool = Tag.objects.filter(tag_type=Tag.OBJECTIVE, roadmap=roadmap)
    else:
        objective_pool = Tag.objects.filter(tag_type=Tag.GOV_OBJECTIVE, roadmap__isnull=True)
    outcome_pool = Tag.objects.filter(tag_type=Tag.OUTCOME, roadmap__isnull=True)
    org_pool = Tag.objects.filter(tag_type=Tag.ORGANISATION, roadmap=roadmap)
    category_pool = Tag.objects.filter(tag_type=Tag.CATEGORY, roadmap__isnull=True)

    # Objective entities on this roadmap (synced sets + directly-linked), for the
    # header "Objectives" pills. Falls back to objective tags when there are none.
    _direct_objectives = list(roadmap.objectives.prefetch_related('key_results'))
    _set_objective_ids = {o.pk for s in applied_sets for o in s.objectives.all()}
    standalone_objectives = [o for o in _direct_objectives if o.pk not in _set_objective_ids]
    has_roadmap_objectives = bool(applied_sets or standalone_objectives)
    modal_objectives = [obj for s in applied_sets for obj in s.objectives.all()] + standalone_objectives

    # Manage-objectives panel (B2): every objective available to this roadmap —
    # shown or hidden — so each can be toggled. Team roadmaps list the whole
    # team's durable objectives; only offered when OKR sync is on.
    hidden_objective_ids = set(roadmap.hidden_objectives.values_list('pk', flat=True))
    if roadmap.owning_team_id:
        manage_objectives = list(
            Objective.objects.filter(team_id=roadmap.owning_team_id).order_by('sort_order', 'title')
        )
    else:
        manage_objectives = list(modal_objectives)
    can_manage_objectives = bool(roadmap.sync_okrs and roadmap.owning_team_id and manage_objectives)
    manage_objectives_json = json.dumps([
        {'id': o.pk, 'title': o.title, 'hidden': o.pk in hidden_objective_ids}
        for o in manage_objectives
    ])

    def tag_min(t):
        return {'id': t.pk, 'name': t.name, 'colour': t.colour, 'tag_type': t.tag_type}

    type_labels = {
        Tag.OUTCOME: 'Defra Outcome',
        Tag.GOV_OBJECTIVE: 'Government Objective',
        Tag.OBJECTIVE: 'Objective',
        Tag.ORGANISATION: 'Team',
        Tag.CATEGORY: 'Item Category',
    }

    # Existing activities can be linked from milestones/metrics in the item modal.
    activities = [
        {'id': i.pk, 'title': i.title}
        for i in roadmap.items.filter(item_type=Item.ACTIVITY).order_by('title')
    ]

    context = {
        'roadmap': roadmap,
        'group_by': group_by,
        'time_scale': time_scale,
        'months': columns,
        'lanes': lanes,
        'gantt_min_width_px': gantt_min_width_px,
        'item_data_json': json.dumps(item_data),
        # Header pills (membership-based, by type)
        'objective_type': objective_type,
        'objective_label': objective_label,
        'roadmap_objective_tags': sorted(by_type(objective_type), key=lambda t: t.name),
        'roadmap_outcome_tags': sorted(by_type(Tag.OUTCOME), key=lambda t: t.name),
        'roadmap_org_tags': sorted(by_type(Tag.ORGANISATION), key=lambda t: t.name),
        'roadmap_category_tags': category_pool.filter(items__roadmap=roadmap).distinct().order_by('name'),
        'selected_category_ids': selected_category_ids,
        'selected_categories_str': selected_categories_str,
        # Item-type (sub-lane) visibility filter
        'visible_tracks': visible_tracks,
        'selected_tracks_str': selected_tracks_str,
        'track_filter_labels': [('activity', 'Activity'), ('milestone', 'Milestone'), ('metric', 'Key Result')],
        'first_visible_track': first_visible_track,
        'last_visible_track': last_visible_track,
        'show_parking': show_parking,
        'custom_range': bool(custom_start or custom_end),
        # Header "Objectives" pills sourced from the objective entities on the roadmap.
        'applied_sets': applied_sets,
        'standalone_objectives': standalone_objectives,
        'has_roadmap_objectives': has_roadmap_objectives,
        'modal_objectives': modal_objectives,
        'can_manage_objectives': can_manage_objectives,
        'manage_objectives_json': manage_objectives_json,
        'objectives_json': json.dumps([
            {
                'id': o.pk,
                'title': o.title,
                'set_name': o.objective_set.name if o.objective_set_id else '',
                # The objective's key results, for the item modal's KR picker.
                'key_results': [{'id': kr.pk, 'title': kr.title} for kr in o.key_results.all()],
            }
            for o in modal_objectives
        ]),
        # Date-window filter (values + selectable range for the toolbar inputs)
        'range_start_iso': timeline_start.isoformat(),
        'range_end_iso': timeline_end.isoformat(),
        'range_min_iso': range_min.isoformat(),
        'range_max_iso': range_max.isoformat(),
        'date_qs': date_qs,
        'timeline_json': json.dumps({
            'total_v': total_v,
            'columns': [
                {
                    'start': c['start'].isoformat(),
                    'end': c['end'].isoformat(),
                    'v_start': c['v_start'],
                    'v_end': c['v_end'],
                    'virt_days': c['virt_days'],
                    'width_pct': c['width_pct'],
                }
                for c in columns
            ],
        }),
        # JSON seeds for the modals
        'manage_json': json.dumps({
            'objective_type': objective_type,
            'objective_label': objective_label,
            'objective_creatable': objective_creatable,
            'pools': {
                'outcome': [tag_min(t) for t in outcome_pool],
                'organisation': [tag_min(t) for t in org_pool],
            },
            'selected': selected_tag_ids,
        }),
        'item_tag_pools_json': json.dumps({
            'outcome': [tag_min(t) for t in outcome_pool],
            'organisation': [tag_min(t) for t in org_pool],
            'category': [tag_min(t) for t in category_pool],
        }),
        'objective_type_json': json.dumps(objective_type),
        'activities_json': json.dumps(activities),
        'roadmap_json': json.dumps({
            'id': roadmap.pk,
            'name': roadmap.name,
            'team': roadmap.team,
            'mission': roadmap.mission,
            'vision': roadmap.vision,
            'description': roadmap.description,
            'roadmap_type': roadmap.roadmap_type,
            'roadmap_type_display': roadmap.get_roadmap_type_display(),
            'organisations': [o.pk for o in roadmap.organisations.all()],
        }),
        'organisations': Organisation.objects.all(),
        'tag_data_json': json.dumps({
            t.pk: {
                'id': t.pk,
                'name': t.name,
                'tag_type': t.tag_type,
                'type_label': type_labels.get(t.tag_type, t.tag_type),
                'colour': t.colour,
                'description': t.description,
                'link': t.link,
                'name_editable': t.tag_type in Tag.SCOPED_TYPES,
            }
            for t in roadmap_tags
        }),
    }
    return render(request, 'roadmap/roadmap_detail.html', context)


# ── Column builders ───────────────────────────────────────────────────────────
# Each builder returns a list of column dicts with keys:
#   label, start, end, col_type, virt_days
# width_pct is filled in later by _build_virtual_timeline.

def _build_months(start, end):
    columns = []
    current = start.replace(day=1)
    while current <= end:
        full_days = calendar.monthrange(current.year, current.month)[1]
        col_end = min(current.replace(day=full_days), end)
        days_in_col = (col_end - current).days + 1
        columns.append({
            'label': current.strftime('%b %Y'),
            'start': current,
            'end': col_end,
            'col_type': 'month',
            'virt_days': round(_VIRT_UNITS['month'] * days_in_col / full_days, 3),
        })
        current = current.replace(year=current.year + 1, month=1) if current.month == 12 \
                  else current.replace(month=current.month + 1)
    return columns


def _build_quarters(start, end):
    columns = []
    q_start_month = ((start.month - 1) // 3) * 3 + 1
    current = start.replace(month=q_start_month, day=1)

    while current <= end:
        q_num = (current.month - 1) // 3 + 1
        q_end_month = q_num * 3
        last_day = calendar.monthrange(current.year, q_end_month)[1]
        quarter_end = current.replace(month=q_end_month, day=last_day)

        full_days = (quarter_end - current).days + 1
        col_start = max(current, start)
        col_end = min(quarter_end, end)
        days_in_col = (col_end - col_start).days + 1
        columns.append({
            'label': f'Q{q_num} {current.year}',
            'start': col_start,
            'end': col_end,
            'col_type': 'quarter',
            'virt_days': round(_VIRT_UNITS['quarter'] * days_in_col / full_days, 3),
        })

        current = current.replace(year=current.year + 1, month=1, day=1) if q_end_month == 12 \
                  else current.replace(month=q_end_month + 1, day=1)

    return columns


def _add_months(d, months):
    total = d.year * 12 + (d.month - 1) + months
    return date(total // 12, total % 12 + 1, 1)


def _build_halves(start, end):
    columns = []
    current = start.replace(month=1 if start.month <= 6 else 7, day=1)

    while current <= end:
        h_num = 1 if current.month == 1 else 2
        h_end_month = 6 if h_num == 1 else 12
        last_day = calendar.monthrange(current.year, h_end_month)[1]
        half_end = current.replace(month=h_end_month, day=last_day)

        full_days = (half_end - current).days + 1
        col_start = max(current, start)
        col_end = min(half_end, end)
        days_in_col = (col_end - col_start).days + 1
        columns.append({
            'label': f'H{h_num} {current.year}',
            'start': col_start,
            'end': col_end,
            'col_type': 'half',
            'virt_days': round(_VIRT_UNITS['half'] * days_in_col / full_days, 3),
        })
        current = current.replace(month=7) if h_num == 1 else date(current.year + 1, 1, 1)

    return columns


def _build_years(start, end):
    columns = []
    current = start.replace(month=1, day=1)

    while current <= end:
        year_end = current.replace(month=12, day=31)
        full_days = (year_end - current).days + 1
        col_start = max(current, start)
        col_end = min(year_end, end)
        days_in_col = (col_end - col_start).days + 1
        columns.append({
            'label': str(current.year),
            'start': col_start,
            'end': col_end,
            'col_type': 'year',
            'virt_days': round(_VIRT_UNITS['year'] * days_in_col / full_days, 3),
        })
        current = date(current.year + 1, 1, 1)

    return columns


def _build_hybrid(start, end):
    today_start = date.today().replace(day=1)

    b_months   = _add_months(today_start, -6)
    b_quarters = _add_months(today_start, 6)
    b_halves   = _add_months(today_start, 18)
    b_years    = _add_months(today_start, 42)

    columns = []

    def _extend(builder, zone_s, zone_e):
        if zone_s <= zone_e:
            columns.extend(builder(zone_s, zone_e))

    _extend(_build_quarters, start,                   min(b_months - timedelta(days=1), end))
    _extend(_build_months,   max(start, b_months),    min(b_quarters - timedelta(days=1), end))
    _extend(_build_quarters, max(start, b_quarters),  min(b_halves - timedelta(days=1), end))
    _extend(_build_halves,   max(start, b_halves),    min(b_years - timedelta(days=1), end))
    _extend(_build_years,    max(start, b_years),     end)

    return columns


# ── Virtual timeline ──────────────────────────────────────────────────────────

def _build_virtual_timeline(columns):
    """Set v_start, v_end, width_pct on each column; return total virtual units."""
    total_v = sum(c['virt_days'] for c in columns)
    if not total_v:
        return 1
    v_pos = 0.0
    for col in columns:
        col['v_start'] = v_pos
        col['v_end'] = v_pos + col['virt_days']
        col['width_pct'] = round(col['virt_days'] / total_v * 100, 3)
        v_pos += col['virt_days']
    return total_v


def _date_to_virtual_pct(d, columns, total_v):
    """Map a calendar date to a % position within the virtual timeline."""
    for col in columns:
        if col['start'] <= d <= col['end']:
            col_days = (col['end'] - col['start']).days + 1
            frac = (d - col['start']).days / col_days if col_days else 0
            v_pos = col['v_start'] + frac * col['virt_days']
            return v_pos / total_v * 100
    return 0.0 if (not columns or d < columns[0]['start']) else 100.0


def _pct_to_date(pct, columns, total_v):
    """Inverse of _date_to_virtual_pct: map a % position back to a calendar date."""
    if not columns:
        return None
    pct = max(0.0, min(100.0, float(pct)))
    v_pos = pct / 100.0 * total_v
    for i, col in enumerate(columns):
        is_last = i == len(columns) - 1
        if col['v_start'] <= v_pos < col['v_end'] or (is_last and v_pos <= col['v_end']):
            frac = (v_pos - col['v_start']) / col['virt_days'] if col['virt_days'] else 0
            span = (col['end'] - col['start']).days
            return col['start'] + timedelta(days=round(frac * span))
    return columns[-1]['end']


# ── Bar / swimlane helpers ────────────────────────────────────────────────────

def _is_parking_item(item):
    """Activity or milestone missing a start or end date — shown in the parking
    lot beside the timeline rather than dropped."""
    if item.item_type not in (Item.ACTIVITY, Item.MILESTONE):
        return False
    return not item.start_date or not item.end_date


def _parking_entries(items):
    return [{'item': item, 'row': i} for i, item in enumerate(items)]


def _item_to_bar(item, columns, total_v):
    if not item.start_date or not item.end_date:
        return None
    left_pct  = _date_to_virtual_pct(item.start_date, columns, total_v)
    right_pct = _date_to_virtual_pct(item.end_date,   columns, total_v)
    width_pct = right_pct - left_pct
    left_pct  = max(0, min(left_pct, 100))
    width_pct = max(0.5, min(width_pct, 100 - left_pct))
    return {
        'item': item,
        'left_pct': round(left_pct, 3),
        'width_pct': round(width_pct, 3),
    }


def _stack_bars(bars):
    """Assign a row index to each bar so overlapping bars stack vertically."""
    bars = sorted(bars, key=lambda b: b['left_pct'])
    rows = []
    for bar in bars:
        right = bar['left_pct'] + bar['width_pct']
        placed = False
        for i, row_right in enumerate(rows):
            if bar['left_pct'] >= row_right:
                bar['row'] = i
                rows[i] = right
                placed = True
                break
        if not placed:
            bar['row'] = len(rows)
            rows.append(right)
    return bars, len(rows)


# Milestone label geometry — used to detect label overlap. Milestones are a
# single point, so their diamonds rarely overlap, but the labels beneath them
# (centred on the date) do. We estimate each label's footprint from its
# character count and stack overlapping ones onto separate rows.
_MS_LABEL_MAX_CHARS = 24          # keep in sync with truncatechars in the template
_MS_LABEL_PX_PER_CHAR = 5.6       # ~average glyph width at the 9px label font
_MS_LABEL_MIN_PX = 16             # diamond width floor
_MS_LABEL_GAP_PCT = 0.4           # small breathing gap between labels on a row


def _stack_milestones(bars, timeline_px):
    """Stack milestones so their (centred) labels don't overlap.

    Each label's horizontal footprint is estimated from its truncated length and
    converted to a percentage of the timeline width, then treated as centred on
    the milestone's date. Overlapping footprints are pushed to a new row — the
    same idea as _stack_bars, but using the label width rather than the (tiny)
    diamond width.
    """
    if timeline_px <= 0:
        timeline_px = 1
    for bar in bars:
        chars = min(len(bar['item'].title.strip()), _MS_LABEL_MAX_CHARS)
        label_px = max(_MS_LABEL_MIN_PX, chars * _MS_LABEL_PX_PER_CHAR)
        half = (label_px / timeline_px * 100) / 2
        bar['fp_left'] = bar['left_pct'] - half
        bar['fp_right'] = bar['left_pct'] + half

    bars = sorted(bars, key=lambda b: b['fp_left'])
    rows = []  # right edge (%) currently occupied by each row
    for bar in bars:
        placed = False
        for i, row_right in enumerate(rows):
            if bar['fp_left'] >= row_right + _MS_LABEL_GAP_PCT:
                bar['row'] = i
                rows[i] = bar['fp_right']
                placed = True
                break
        if not placed:
            bar['row'] = len(rows)
            rows.append(bar['fp_right'])
    return bars, len(rows)


def _build_swimlanes(items, tag_type, columns, total_v):
    tag_items: dict[Tag, list] = {}
    untagged = []

    # Only create lanes for tags that appear on at least one item in this roadmap
    relevant_tag_ids = set()
    for item in items:
        for t in item.tags.all():
            if t.tag_type == tag_type:
                relevant_tag_ids.add(t.pk)

    all_tags = Tag.objects.filter(tag_type=tag_type, pk__in=relevant_tag_ids).order_by('sort_order', 'name')
    for tag in all_tags:
        tag_items[tag] = []

    for item in items:
        item_tags = [t for t in item.tags.all() if t.tag_type == tag_type]
        if item_tags:
            for tag in item_tags:
                if tag in tag_items:
                    tag_items[tag].append(item)
        else:
            untagged.append(item)

    lanes = []
    for tag, tag_item_list in tag_items.items():
        lanes.append(_make_lane(tag.name, tag_item_list, columns, total_v, tag_id=tag.pk))
    if untagged:
        lanes.append(_make_lane('Untagged', untagged, columns, total_v, tag_id=None))
    return lanes


class _KrSpan:
    """Minimal date-range adapter so a key result can be placed via _item_to_bar."""
    def __init__(self, start_date, end_date):
        self.start_date = start_date
        self.end_date = end_date


def _kr_bar(kr, obj_set, columns, total_v):
    """A key result's timeline bar. Uses the KR's own dates when set (e.g. dragged
    on the roadmap); otherwise spans its objective's set period (the default)."""
    if kr.start_date and kr.end_date:
        span = _KrSpan(kr.start_date, kr.end_date)
    elif obj_set is not None:
        span = _KrSpan(obj_set.start_date, obj_set.end_date)
    else:
        return None
    bar = _item_to_bar(span, columns, total_v)
    if bar is None:
        return None  # no timeframe — the key result can't be placed
    return {'kr_title': kr.title, 'kr_id': kr.pk, 'kr_progress': kr.progress,
            'kr_objective_id': kr.objective_id, 'kr_row': kr.row,
            'kr_start_iso': span.start_date.isoformat() if span.start_date else '',
            'kr_end_iso': span.end_date.isoformat() if span.end_date else '',
            'left_pct': bar['left_pct'], 'width_pct': bar['width_pct']}


def _make_objective_lane(name, objective, obj_items, linkable_set_ids, columns, total_v):
    """A lane for one durable roadmap objective. The objective persists across
    quarters; each of its key results spans *its own* period (kr.objective_set),
    so Q1 and Q2 KRs plot in their own windows within the one lane. A KR plots if
    it has its own B1 dates, or belongs to a linkable (team, non-archived) set.
    Metric items assigned to the objective also plot on the metrics track;
    activities/milestones plot on their own tracks as usual."""
    tracks = {'activities': [], 'milestones': [], 'metrics': []}
    parking_by_type = {'activities': [], 'milestones': [], 'metrics': []}

    kr_titles = set()
    if objective is not None:
        for kr in objective.key_results.all():
            has_own_dates = kr.start_date and kr.end_date
            kr_set = kr.objective_set
            if not has_own_dates and (kr_set is None or kr_set.pk not in linkable_set_ids):
                continue  # a KR in a non-linkable/archived period with no own dates
            kr_titles.add(kr.title)
            bar = _kr_bar(kr, kr_set, columns, total_v)
            if bar is not None:
                tracks['metrics'].append(bar)

    for item in obj_items:
        if _is_parking_item(item):
            if item.item_type == Item.ACTIVITY:
                parking_by_type['activities'].append(item)
            elif item.item_type == Item.MILESTONE:
                parking_by_type['milestones'].append(item)
            continue
        bar = _item_to_bar(item, columns, total_v)
        if bar is None:
            continue
        if item.item_type == Item.ACTIVITY:
            tracks['activities'].append(bar)
        elif item.item_type == Item.MILESTONE:
            tracks['milestones'].append(bar)
        elif item.item_type == Item.METRIC:
            # In a set lane a metric item that backs a key result is already
            # drawn as the KeyResult bar — don't double it.
            if item.title in kr_titles:
                continue
            tracks['metrics'].append(bar)

    return _stack_tracks(tracks, parking_by_type, total_v, name,
                         objective_id=objective.pk if objective else None)


def _build_objective_swimlanes(roadmap, items, columns, total_v):
    """Swim lanes grouped by durable Objective entity. Objectives shown on this
    roadmap come from access.roadmap_objective_ids (a team roadmap's own team
    objectives minus any hidden, plus directly-linked objectives). Each objective
    is one persistent lane; its key results plot across their own periods
    (kr.objective_set), and items sit in the lane of their item.objective.
    Unassigned items (or items whose objective isn't shown) fall into an
    'Unassigned' lane."""
    from . import access
    from .models import Objective

    obj_ids = access.roadmap_objective_ids(roadmap)
    objectives = list(
        Objective.objects.filter(pk__in=obj_ids)
        .prefetch_related('key_results__objective_set')
        .order_by('sort_order', 'title')
    )
    # KRs may plot for periods this roadmap actually syncs; KRs with their own B1
    # dates plot regardless (handled inside _make_objective_lane).
    if roadmap.sync_okrs:
        linkable_set_ids = set(access.linkable_sets(roadmap).values_list('pk', flat=True))
    else:
        linkable_set_ids = set()

    lanes = []
    shown_ids = set()
    for objective in objectives:
        shown_ids.add(objective.pk)
        obj_items = [i for i in items if i.objective_id == objective.pk]
        lanes.append(_make_objective_lane(
            objective.title, objective, obj_items, linkable_set_ids, columns, total_v))

    unassigned = [i for i in items if i.objective_id is None or i.objective_id not in shown_ids]
    if unassigned:
        lanes.append(_make_objective_lane('Unassigned', None, unassigned, linkable_set_ids, columns, total_v))
    return lanes


def _item_modal_dict(item):
    return {
        'id': item.pk,
        'title': item.title,
        'item_type': item.item_type,
        'item_type_display': item.get_item_type_display(),
        'description': item.description,
        'priority': item.priority,
        'priority_display': item.get_priority_display() if item.priority else '',
        'size': item.size,
        'start_date': item.start_date.strftime('%d %b %Y') if item.start_date else '',
        'end_date': item.end_date.strftime('%d %b %Y') if item.end_date else '',
        '_start_iso': item.start_date.isoformat() if item.start_date else '',
        '_end_iso': item.end_date.isoformat() if item.end_date else '',
        'objective': item.objective_id,
        'objective_title': item.objective.title if item.objective_id else '',
        'row': item.row,
        'prd_link': item.prd_link,
        'backlog_link': item.backlog_link,
        'tags': [
            {'id': t.pk, 'name': t.name, 'tag_type': t.tag_type, 'colour': t.colour}
            for t in item.tags.all()
        ],
        'linked_activities': [
            {'id': a.pk, 'title': a.title}
            for a in item.linked_activities.all()
        ],
    }


def _serialise_items(lanes):
    seen = set()
    data = {}
    for lane in lanes:
        for track in lane['tracks'].values():
            for bar in track['bars']:
                item = bar.get('item')
                if item is None or item.pk in seen:  # key-result bars have no item
                    continue
                seen.add(item.pk)
                data[item.pk] = _item_modal_dict(item)
            for entry in track['parking']:
                item = entry['item']
                if item.pk in seen:
                    continue
                seen.add(item.pk)
                data[item.pk] = _item_modal_dict(item)
    return data


def _manual_row(bar):
    """The explicit row a bar was pinned to (Item.row for item bars, KeyResult.row
    for key-result bars), or None when it should be auto-stacked."""
    item = bar.get('item')
    if item is not None:
        return item.row
    return bar.get('kr_row')  # key-result bars have no item


def _apply_manual_rows(stacked, parking):
    """Honour a manual row when set, then re-flow the auto-stacked bars around
    those claims so a pinned bar never ends up sharing a row (and hiding) an
    auto-placed one. Returns the resulting row_count."""
    # 1. Pinned bars claim their row for their horizontal span.
    occupied = {}  # row index -> list of (left, right) spans already taken
    auto = []
    for bar in stacked:
        row = _manual_row(bar)
        left = bar.get('left_pct', 0)
        if row is not None:
            bar['row'] = row
            occupied.setdefault(row, []).append((left, left + bar.get('width_pct', 0)))
        else:
            auto.append(bar)

    # 2. Auto bars drop into the lowest row whose span is free.
    def _overlaps(spans, left, right):
        return any(left < e and right > s for s, e in spans)

    for bar in sorted(auto, key=lambda b: b.get('left_pct', 0)):
        left = bar.get('left_pct', 0)
        right = left + bar.get('width_pct', 0)
        row = 0
        while _overlaps(occupied.get(row, []), left, right):
            row += 1
        bar['row'] = row
        occupied.setdefault(row, []).append((left, right))

    for entry in parking:
        if entry['item'].row is not None:
            entry['row'] = entry['item'].row
    rows = [b.get('row', 0) for b in stacked] + [e.get('row', 0) for e in parking]
    return max(rows) + 1 if rows else 1


def _stack_tracks(tracks, parking_by_type, total_v, name, tag_id=None, objective_id=None):
    """Stack each track's bars into rows and attach its parking-lot entries.
    Shared by the tag-based and objective-based lane builders."""
    timeline_px = total_v * _BASE_PX_PER_UNIT
    stacked_tracks = {}
    for track_name, bars in tracks.items():
        if track_name == 'milestones':
            stacked, _auto_rows = _stack_milestones(bars, timeline_px)
        else:
            stacked, _auto_rows = _stack_bars(bars)
        parking = _parking_entries(parking_by_type.get(track_name, []))
        row_count = _apply_manual_rows(stacked, parking)
        stacked_tracks[track_name] = {'bars': stacked, 'parking': parking, 'row_count': max(row_count, 1)}
    if objective_id:
        lane_key = f'obj-{objective_id}'
    elif tag_id:
        lane_key = f'tag-{tag_id}'
    else:
        slug = ''.join(ch if ch.isalnum() else '-' for ch in name).strip('-').lower() or 'lane'
        lane_key = f'none-{slug}'
    return {
        'name': name, 'tag_id': tag_id, 'objective_id': objective_id,
        'lane_key': lane_key, 'tracks': stacked_tracks,
    }


def _make_lane(name, item_list, columns, total_v, tag_id=None):
    tracks = {'activities': [], 'milestones': [], 'metrics': []}
    parking_by_type = {'activities': [], 'milestones': [], 'metrics': []}
    for item in item_list:
        if _is_parking_item(item):
            if item.item_type == Item.ACTIVITY:
                parking_by_type['activities'].append(item)
            elif item.item_type == Item.MILESTONE:
                parking_by_type['milestones'].append(item)
            continue
        bar = _item_to_bar(item, columns, total_v)
        if bar is None:
            continue
        if item.item_type == Item.ACTIVITY:
            tracks['activities'].append(bar)
        elif item.item_type == Item.MILESTONE:
            tracks['milestones'].append(bar)
        elif item.item_type == Item.METRIC:
            tracks['metrics'].append(bar)

    return _stack_tracks(tracks, parking_by_type, total_v, name, tag_id=tag_id)
