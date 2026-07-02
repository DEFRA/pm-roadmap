from django.shortcuts import render, get_object_or_404
from django.db import models
from django.views.decorators.csrf import ensure_csrf_cookie
from datetime import date, timedelta
import calendar
import json

from .models import Roadmap, Item, Tag, Organisation

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


@ensure_csrf_cookie
def roadmap_detail(request, pk):
    roadmap = get_object_or_404(Roadmap, pk=pk)
    # Default swimlane view is resolved after the roadmap type is known (below):
    # group roadmaps default to Defra Outcomes, service roadmaps to Objectives.
    group_by = request.GET.get('group_by')
    time_scale = request.GET.get('time_scale', 'months')
    selected_categories_str = request.GET.get('categories', '')

    items = roadmap.items.prefetch_related('tags', 'linked_activities').all()

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

    # Timeline always starts at the current month (or quarter start for quarters view)
    today = date.today()
    if time_scale == 'quarters':
        q_start_month = ((today.month - 1) // 3) * 3 + 1
        timeline_start = today.replace(month=q_start_month, day=1)
    else:
        timeline_start = today.replace(day=1)

    # Timeline end comes from the latest item end_date
    dated_items = [i for i in items if i.start_date and i.end_date]
    if dated_items:
        max_date = max(i.end_date for i in dated_items)
        last_day = calendar.monthrange(max_date.year, max_date.month)[1]
        timeline_end = max_date.replace(day=last_day)
    else:
        timeline_end = (timeline_start + timedelta(days=365)).replace(day=1) - timedelta(days=1)

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
    tag_type = tag_type_map.get(group_by, Tag.OUTCOME)
    if group_by not in tag_type_map and group_by != 'outcome':
        group_by = 'outcome'
    lanes = _build_swimlanes(items, tag_type, columns, total_v)

    item_data = _serialise_items(lanes)

    # Minimum gantt width: 100 px per 30 virtual units
    gantt_min_width_px = 180 + int(total_v * _BASE_PX_PER_UNIT)

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
        # JSON seeds for the modals
        'manage_json': json.dumps({
            'objective_type': objective_type,
            'objective_label': objective_label,
            'objective_creatable': objective_creatable,
            'pools': {
                objective_type: [tag_min(t) for t in objective_pool],
                'outcome': [tag_min(t) for t in outcome_pool],
                'organisation': [tag_min(t) for t in org_pool],
            },
            'selected': selected_tag_ids,
        }),
        'item_tag_pools_json': json.dumps({
            'outcome': [tag_min(t) for t in outcome_pool],
            objective_type: [tag_min(t) for t in objective_pool],
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


# ── Bar / swimlane helpers ────────────────────────────────────────────────────

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


def _serialise_items(lanes):
    seen = set()
    data = {}
    for lane in lanes:
        for track in lane['tracks'].values():
            for bar in track['bars']:
                item = bar['item']
                if item.pk in seen:
                    continue
                seen.add(item.pk)
                data[item.pk] = {
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
    return data


def _make_lane(name, item_list, columns, total_v, tag_id=None):
    tracks = {'activities': [], 'milestones': [], 'metrics': []}
    for item in item_list:
        bar = _item_to_bar(item, columns, total_v)
        if bar is None:
            continue
        if item.item_type == Item.ACTIVITY:
            tracks['activities'].append(bar)
        elif item.item_type == Item.MILESTONE:
            tracks['milestones'].append(bar)
        elif item.item_type == Item.METRIC:
            tracks['metrics'].append(bar)

    # Timeline width in px (at the gantt's minimum width) — the conservative
    # case for label overlap, since a wider viewport only spreads things out.
    timeline_px = total_v * _BASE_PX_PER_UNIT

    stacked_tracks = {}
    for track_name, bars in tracks.items():
        if track_name == 'milestones':
            stacked, row_count = _stack_milestones(bars, timeline_px)
        else:
            stacked, row_count = _stack_bars(bars)
        stacked_tracks[track_name] = {'bars': stacked, 'row_count': max(row_count, 1)}

    return {'name': name, 'tag_id': tag_id, 'tracks': stacked_tracks}
