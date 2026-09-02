"""JSON endpoints backing the in-page modals (the Django equivalent of the
Node REST API). Same-origin fetch calls from the rendered pages; CSRF is
enforced via the X-CSRFToken header sent by the frontend.
"""
import json
from datetime import datetime

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from .models import Roadmap, Item, Tag, Organisation, Objective, KeyResult
from . import access
from .access import objective_assignable_to_roadmap


# ── Serialisers ───────────────────────────────────────────────────────────────

def org_to_dict(o):
    return {'id': o.pk, 'name': o.name, 'abbreviation': o.abbreviation, 'description': o.description}


def tag_to_dict(t):
    return {
        'id': t.pk,
        'name': t.name,
        'tag_type': t.tag_type,
        'tag_type_display': t.get_tag_type_display(),
        'colour': t.colour,
        'description': t.description,
        'link': t.link,
        'roadmap': t.roadmap_id,
    }


def item_to_dict(i):
    return {
        'id': i.pk,
        'roadmap': i.roadmap_id,
        'item_type': i.item_type,
        'item_type_display': i.get_item_type_display(),
        'title': i.title,
        'description': i.description,
        'priority': i.priority,
        'size': i.size,
        'start_date': i.start_date.isoformat() if i.start_date else '',
        'end_date': i.end_date.isoformat() if i.end_date else '',
        'row': i.row,
        'prd_link': i.prd_link,
        'backlog_link': i.backlog_link,
        'objective': i.objective_id,
        'tags': [tag_to_dict(t) for t in i.tags.all()],
        'linked_activities': [{'id': a.pk, 'title': a.title} for a in i.linked_activities.all()],
        'key_results': [{'id': kr.pk, 'title': kr.title} for kr in i.key_results.all()],
    }


def roadmap_to_dict(r):
    return {
        'id': r.pk,
        'name': r.name,
        'description': r.description,
        'team': r.team,
        'roadmap_type': r.roadmap_type,
        'mission': r.mission,
        'vision': r.vision,
        'organisations': [org_to_dict(o) for o in r.organisations.all()],
        'tags': [tag_to_dict(t) for t in r.tags.all()],
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _json_body(request):
    try:
        return json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return None


def _error(message, status=400):
    return JsonResponse({'error': message}, status=status)


def _parse_date(value):
    """Accept 'YYYY-MM-DD' (or empty) and return a date or None."""
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        raise ValueError(f'Invalid date: {value!r} (expected YYYY-MM-DD)')


def _valid_tag_ids(ids):
    """Return cleaned list of existing tag ids, or raise if any are invalid."""
    ids = [int(i) for i in (ids or [])]
    if not ids:
        return []
    found = set(Tag.objects.filter(pk__in=ids).values_list('pk', flat=True))
    missing = [i for i in ids if i not in found]
    if missing:
        raise ValueError(f'Invalid tag id(s): {missing}')
    return ids


def _sync_roadmap_membership(item):
    """Tags assigned to an item also join the roadmap's header membership
    (objectives / gov objectives / outcomes / teams), so the header reflects
    what's actually in use. Categories are item-only filters and are excluded.
    Additive only — removing a tag from an item never removes it from the
    roadmap (use the manage-tags modal for that)."""
    member_tags = list(item.tags.exclude(tag_type=Tag.CATEGORY))
    if member_tags:
        item.roadmap.tags.add(*member_tags)


# ── Organisations ─────────────────────────────────────────────────────────────

@require_http_methods(['GET'])
def organisations(request):
    return JsonResponse([org_to_dict(o) for o in Organisation.objects.all()], safe=False)


# ── Tags ──────────────────────────────────────────────────────────────────────

@require_http_methods(['GET', 'POST'])
def tags_collection(request):
    if request.method == 'GET':
        qs = Tag.objects.all()
        tag_type = request.GET.get('type')
        roadmap_id = request.GET.get('roadmap')
        if tag_type:
            qs = qs.filter(tag_type=tag_type)
        # Roadmap-scoped types (Teams, Objectives) are filtered by roadmap.
        if roadmap_id:
            qs = qs.filter(roadmap_id=roadmap_id)
        return JsonResponse([tag_to_dict(t) for t in qs], safe=False)

    # POST — create
    data = _json_body(request)
    if data is None:
        return _error('Invalid JSON body')
    name = (data.get('name') or '').strip()
    tag_type = data.get('tag_type')
    if not name or not tag_type:
        return _error('Tag name and tag_type are required')
    if tag_type not in dict(Tag.TAG_TYPE_CHOICES):
        return _error(f'Invalid tag_type: {tag_type}')

    # Central types ignore any roadmap that might be sent.
    roadmap_id = data.get('roadmap') if tag_type in Tag.SCOPED_TYPES else None

    if Tag.objects.filter(name=name, tag_type=tag_type, roadmap_id=roadmap_id).exists():
        return _error(f'Tag "{name}" of type "{tag_type}" already exists', status=409)

    create_kwargs = dict(
        name=name,
        tag_type=tag_type,
        description=(data.get('description') or '').strip(),
        roadmap_id=roadmap_id,
    )
    # Only pin a colour if one was supplied; otherwise the model assigns a
    # random palette colour (default=random_tag_colour).
    if data.get('colour'):
        create_kwargs['colour'] = data['colour']
    tag = Tag.objects.create(**create_kwargs)
    return JsonResponse(tag_to_dict(tag), status=201)


@require_http_methods(['PUT', 'DELETE'])
def tag_detail(request, pk):
    tag = get_object_or_404(Tag, pk=pk)

    if request.method == 'DELETE':
        tag.delete()
        return JsonResponse({}, status=204)

    data = _json_body(request)
    if data is None:
        return _error('Invalid JSON body')
    # Names are only editable for roadmap-scoped tags (Teams, Objectives).
    # Central tags (Defra Outcomes, Gov Objectives, Categories) are shared and
    # admin-defined, so their names are locked even if a name is sent.
    if 'name' in data and data['name'] and tag.tag_type in Tag.SCOPED_TYPES:
        tag.name = data['name'].strip()
    if 'colour' in data and data['colour']:
        tag.colour = data['colour']
    if 'description' in data:
        tag.description = (data['description'] or '').strip()
    if 'link' in data:
        tag.link = (data['link'] or '').strip()
    tag.save()
    return JsonResponse(tag_to_dict(tag))


@require_http_methods(['POST'])
def tags_reorder(request):
    """Persist a new swim-lane order. Body: {"ids": [tagId, ...]} in the desired
    top-to-bottom order; each tag's sort_order is set to its index."""
    data = _json_body(request)
    if data is None:
        return _error('Invalid JSON body')
    ids = data.get('ids')
    if not isinstance(ids, list):
        return _error('"ids" must be a list of tag ids')
    for index, tag_id in enumerate(ids):
        Tag.objects.filter(pk=tag_id).update(sort_order=index)
    return JsonResponse({'ok': True, 'count': len(ids)})


# ── Roadmaps ──────────────────────────────────────────────────────────────────

def _apply_roadmap_fields(roadmap, data):
    if 'name' in data:
        roadmap.name = (data['name'] or '').strip()
    if 'description' in data:
        roadmap.description = data['description'] or ''
    if 'team' in data:
        roadmap.team = (data['team'] or '').strip()
    if 'mission' in data:
        roadmap.mission = data['mission'] or ''
    if 'vision' in data:
        roadmap.vision = data['vision'] or ''
    if 'roadmap_type' in data and data['roadmap_type'] in dict(Roadmap.ROADMAP_TYPE_CHOICES):
        roadmap.roadmap_type = data['roadmap_type']


@require_http_methods(['POST'])
def roadmaps_collection(request):
    data = _json_body(request)
    if data is None:
        return _error('Invalid JSON body')
    if not (data.get('name') or '').strip():
        return _error('Roadmap name is required')

    roadmap = Roadmap()
    _apply_roadmap_fields(roadmap, data)
    roadmap.save()
    if 'organisations' in data:
        roadmap.organisations.set([int(i) for i in data['organisations'] or []])
    return JsonResponse(roadmap_to_dict(roadmap), status=201)


@require_http_methods(['PUT', 'DELETE'])
def roadmap_detail(request, pk):
    roadmap = get_object_or_404(Roadmap, pk=pk)

    if request.method == 'DELETE':
        roadmap.delete()
        return JsonResponse({}, status=204)

    data = _json_body(request)
    if data is None:
        return _error('Invalid JSON body')
    _apply_roadmap_fields(roadmap, data)
    roadmap.save()

    if 'organisations' in data:
        roadmap.organisations.set([int(i) for i in data['organisations'] or []])
    # roadmap.tags is the single source of truth for which objectives / outcomes
    # / teams are "on" this roadmap; the manage modal sends the complete set.
    if 'tags' in data:
        try:
            roadmap.tags.set(_valid_tag_ids(data['tags']))
        except ValueError as exc:
            return _error(str(exc))
    return JsonResponse(roadmap_to_dict(roadmap))


# ── Items ─────────────────────────────────────────────────────────────────────

def _apply_item_fields(item, data):
    if 'item_type' in data:
        item.item_type = (data['item_type'] or '').lower()
    if 'title' in data:
        item.title = (data['title'] or '').strip()
    if 'description' in data:
        item.description = data['description'] or ''
    if 'priority' in data:
        item.priority = (data['priority'] or '').lower()
    if 'size' in data:
        item.size = (data['size'] or '').upper()
    if 'prd_link' in data:
        item.prd_link = (data['prd_link'] or '').strip()
    if 'backlog_link' in data:
        item.backlog_link = (data['backlog_link'] or '').strip()
    if 'start_date' in data:
        item.start_date = _parse_date(data['start_date'])
    if 'end_date' in data:
        item.end_date = _parse_date(data['end_date'])
    if 'row' in data:
        row = data['row']
        if row in (None, ''):
            item.row = None
        else:
            item.row = max(0, int(row))
    # Assign to an objective on this roadmap; empty unassigns. Validated against
    # the item's roadmap so only assignable objectives can be linked.
    if 'objective' in data:
        obj_id = data['objective']
        if obj_id in (None, '', 0):
            item.objective = None
        else:
            objective = Objective.objects.filter(pk=obj_id).first()
            if objective is None or not objective_assignable_to_roadmap(objective, item.roadmap):
                raise ValueError('Invalid objective for this roadmap')
            item.objective = objective


def _reconcile_key_results(item, data):
    """Set the activity's related key results, keeping only those that belong to
    its objective. Runs on every save so changing the objective drops key results
    that no longer apply, even when the client doesn't resend the selection."""
    if 'key_results' in data:
        ids = {int(i) for i in (data['key_results'] or [])}
    else:
        ids = set(item.key_results.values_list('pk', flat=True))
    if item.objective_id and ids:
        item.key_results.set(KeyResult.objects.filter(objective_id=item.objective_id, pk__in=ids))
    else:
        item.key_results.clear()


def _next_kr_sort_order(objective):
    last = objective.key_results.order_by('-sort_order').first()
    return (last.sort_order + 1) if last else 0


def _ensure_key_result(item, previous_title=None):
    """Create or update the KeyResult backing a metric item on an objective.

    The metric *is* the key result: the item keeps its timeline placement while
    a KeyResult under the objective carries the measurable values. Matched by
    title so renaming the item renames its key result rather than orphaning it.
    """
    objective = item.objective
    if objective is None:
        return None
    lookup_title = previous_title or item.title
    kr = KeyResult.objects.filter(objective=objective, title=lookup_title).first()
    # A roadmap-authored metric isn't tied to a planning period, so its key result
    # carries the item's own dates (B2) — the KR bar sits exactly where the metric
    # is on the timeline, rather than spanning a set it doesn't belong to.
    if kr is None:
        kr = KeyResult.objects.create(
            objective=objective, title=item.title, sort_order=_next_kr_sort_order(objective),
            start_date=item.start_date, end_date=item.end_date,
        )
    else:
        updates = []
        if kr.title != item.title:
            kr.title = item.title
            updates.append('title')
        if (kr.start_date, kr.end_date) != (item.start_date, item.end_date):
            kr.start_date, kr.end_date = item.start_date, item.end_date
            updates += ['start_date', 'end_date']
        if updates:
            kr.save(update_fields=updates)
    return kr


@require_http_methods(['POST'])
def items_collection(request, roadmap_pk):
    roadmap = get_object_or_404(Roadmap, pk=roadmap_pk)
    data = _json_body(request)
    if data is None:
        return _error('Invalid JSON body')
    if not data.get('item_type') or not (data.get('title') or '').strip():
        return _error('item_type and title are required')
    if data['item_type'].lower() not in dict(Item.ITEM_TYPE_CHOICES):
        return _error(f"Invalid item_type: {data['item_type']}")

    item = Item(roadmap=roadmap)
    try:
        _apply_item_fields(item, data)
    except ValueError as exc:
        return _error(str(exc))
    item.save()
    try:
        item.tags.set(_valid_tag_ids(data.get('tags')))
    except ValueError as exc:
        item.delete()
        return _error(str(exc))
    _sync_roadmap_membership(item)
    if 'linked_activities' in data:
        item.linked_activities.set([int(i) for i in data['linked_activities'] or []])
    _reconcile_key_results(item, data)
    # A metric assigned to an objective is a key result — back it with one.
    if item.item_type == Item.METRIC and item.objective_id:
        _ensure_key_result(item)
    return JsonResponse(item_to_dict(item), status=201)


@require_http_methods(['PUT', 'DELETE'])
def item_detail(request, pk):
    item = get_object_or_404(Item, pk=pk)

    if request.method == 'DELETE':
        item.delete()
        return JsonResponse({}, status=204)

    data = _json_body(request)
    if data is None:
        return _error('Invalid JSON body')
    previous_title = item.title
    try:
        _apply_item_fields(item, data)
    except ValueError as exc:
        return _error(str(exc))
    item.save()
    if 'tags' in data:
        try:
            item.tags.set(_valid_tag_ids(data['tags']))
        except ValueError as exc:
            return _error(str(exc))
        _sync_roadmap_membership(item)
    if 'linked_activities' in data:
        item.linked_activities.set([int(i) for i in data['linked_activities'] or []])
    _reconcile_key_results(item, data)
    # Keep the backing key result in step with a metric on an objective.
    if item.item_type == Item.METRIC and item.objective_id:
        _ensure_key_result(item, previous_title=previous_title)
    return JsonResponse(item_to_dict(item))


def _apply_kr_fields(kr, data):
    if 'start_date' in data:
        kr.start_date = _parse_date(data['start_date'])   # '' or invalid → None (inherit set)
    if 'end_date' in data:
        kr.end_date = _parse_date(data['end_date'])
    if 'row' in data:
        row = data['row']
        kr.row = None if row in (None, '') else max(0, int(row))


def key_result_dict(kr):
    return {
        'id': kr.pk,
        'objective': kr.objective_id,
        'title': kr.title,
        'start_date': kr.start_date.isoformat() if kr.start_date else '',
        'end_date': kr.end_date.isoformat() if kr.end_date else '',
        'row': kr.row,
    }


@require_http_methods(['PUT'])
def key_result_detail(request, pk):
    """Update a key result's timeline placement (dragged/resized on the roadmap):
    start_date / end_date (empty clears → inherit the set period) and row."""
    kr = get_object_or_404(KeyResult, pk=pk)
    data = _json_body(request)
    if data is None:
        return _error('Invalid JSON body')
    try:
        _apply_kr_fields(kr, data)
    except (ValueError, TypeError) as exc:
        return _error(str(exc))
    kr.save()
    return JsonResponse(key_result_dict(kr))


@require_http_methods(['PUT'])
def roadmap_objectives_visibility(request, pk):
    """Set which of the roadmap's objectives are hidden (deselected in the Manage
    objectives panel). Body: {"hidden": [objId, ...]}. Everything not listed is
    shown; an empty list shows all. Only objectives available to this roadmap can
    be hidden — stray ids are ignored."""
    roadmap = get_object_or_404(Roadmap, pk=pk)
    data = _json_body(request)
    if data is None:
        return _error('Invalid JSON body')
    hidden = data.get('hidden', [])
    if not isinstance(hidden, list):
        return _error('hidden must be a list of objective ids')
    try:
        requested = {int(i) for i in hidden}
    except (ValueError, TypeError):
        return _error('hidden must be a list of objective ids')
    # Guard: only hide objectives that actually belong to this roadmap's team.
    available = set(access.roadmap_objective_ids(roadmap)) | set(roadmap.hidden_objectives.values_list('pk', flat=True))
    roadmap.hidden_objectives.set(requested & available)
    return JsonResponse({'hidden': sorted(roadmap.hidden_objectives.values_list('pk', flat=True))})


@require_http_methods(['GET'])
def health(request):
    return JsonResponse({"ok": True})
