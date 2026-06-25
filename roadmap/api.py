"""JSON endpoints backing the in-page modals (the Django equivalent of the
Node REST API). Same-origin fetch calls from the rendered pages; CSRF is
enforced via the X-CSRFToken header sent by the frontend.
"""
import json
from datetime import datetime

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from .models import Roadmap, Item, Tag, Organisation


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
        'prd_link': i.prd_link,
        'backlog_link': i.backlog_link,
        'tags': [tag_to_dict(t) for t in i.tags.all()],
        'linked_activities': [{'id': a.pk, 'title': a.title} for a in i.linked_activities.all()],
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
    if 'name' in data and data['name']:
        tag.name = data['name'].strip()
    if 'colour' in data and data['colour']:
        tag.colour = data['colour']
    if 'description' in data:
        tag.description = (data['description'] or '').strip()
    tag.save()
    return JsonResponse(tag_to_dict(tag))


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
    if 'linked_activities' in data:
        item.linked_activities.set([int(i) for i in data['linked_activities'] or []])
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
    if 'linked_activities' in data:
        item.linked_activities.set([int(i) for i in data['linked_activities'] or []])
    return JsonResponse(item_to_dict(item))


@require_http_methods(['GET'])
def health(request):
    return JsonResponse({"ok": True})
