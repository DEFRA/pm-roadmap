/* Drag items on the gantt: along the timeline (dates), between rows, and in/out
 * of the parking lot. Activity bars can also be resized from either end. Key
 * result bars (data-kr-id) drag/resize the same way but persist to the
 * key-results endpoint and never park (they belong to a planning period).
 * Drops outside the bar's swimlane + track are ignored.
 *
 * Touch/mobile is intentionally not handled yet (same as lane reorder).
 */
(function () {
  const THRESHOLD_PX = 5;
  const EDGE_PX = 10;
  const MIN_WIDTH_PCT = 0.4;
  const DEFAULT_UNPARK_DAYS = 29; // start + 29 days ≈ 30-day span inclusive
  const TRACK_PAD = 6;            // --gantt-track-pad
  const ROW_GAP = 4;
  const ROW_H = { activity: 28, metric: 28, milestone: 52 };

  function getCookie(name) {
    const m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return m ? decodeURIComponent(m.pop()) : '';
  }

  function isoToDate(iso) {
    if (!iso) return null;
    const [y, m, d] = iso.split('-').map(Number);
    return new Date(y, m - 1, d);
  }

  function dateToIso(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  }

  function addDays(d, n) {
    const x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    x.setDate(x.getDate() + n);
    return x;
  }

  function dayDiff(a, b) {
    return Math.round((b - a) / 86400000);
  }

  function pctToDate(pct, timeline) {
    const cols = timeline.columns || [];
    if (!cols.length) return null;
    pct = Math.max(0, Math.min(100, pct));
    const vPos = (pct / 100) * timeline.total_v;
    for (let i = 0; i < cols.length; i++) {
      const col = cols[i];
      const isLast = i === cols.length - 1;
      if (vPos >= col.v_start && (vPos < col.v_end || (isLast && vPos <= col.v_end))) {
        const frac = col.virt_days ? (vPos - col.v_start) / col.virt_days : 0;
        const start = isoToDate(col.start);
        const end = isoToDate(col.end);
        const span = dayDiff(start, end);
        return addDays(start, Math.round(frac * span));
      }
    }
    return isoToDate(cols[cols.length - 1].end);
  }

  function rowFromY(zone, clientY, itemType) {
    const rect = zone.getBoundingClientRect();
    const rowH = ROW_H[itemType] || ROW_H.activity;
    const y = clientY - rect.top - TRACK_PAD;
    return Math.max(0, Math.round(y / (rowH + ROW_GAP)));
  }

  // Two bars overlap when their date spans (left%..left+width%) intersect.
  function spansOverlap(l1, w1, l2, w2) {
    return l1 < l2 + w2 && l2 < l1 + w1;
  }

  // The row a bar should land on: the caller's target row if its date span is
  // free there, otherwise the NEAREST free row — checking upward before downward
  // at each distance, so an empty line above (e.g. an empty top row) is easy to
  // drop onto rather than skipping past it to a new line below. Guarantees a
  // dropped bar never overlaps another. `excludeEl` is the bar being dragged.
  function freeRow(zone, excludeEl, leftPct, widthPct, targetRow) {
    const occupied = {};
    zone.querySelectorAll('.gantt-bar, .gantt-milestone-marker').forEach((b) => {
      if (b === excludeEl || b.dataset.parked === '1' || b.dataset.left == null) return;
      const r = parseInt(b.dataset.row || '0', 10);
      (occupied[r] = occupied[r] || []).push([
        parseFloat(b.dataset.left || '0'), parseFloat(b.dataset.width || '0'),
      ]);
    });
    const isFree = (r) =>
      r >= 0 && !(occupied[r] || []).some(([l, w]) => spansOverlap(leftPct, widthPct, l, w));
    const target = Math.max(0, targetRow);
    if (isFree(target)) return target;
    for (let d = 1; d < 500; d += 1) {
      if (isFree(target - d)) return target - d;   // prefer an empty line above
      if (isFree(target + d)) return target + d;
    }
    return target;
  }

  function findZone(x, y, laneKey, track, allowParking) {
    const els = document.elementsFromPoint(x, y);
    for (const el of els) {
      const zone = el.closest ? el.closest('[data-zone][data-lane-key][data-track]') : null;
      if (!zone) continue;
      if (zone.dataset.laneKey !== laneKey || zone.dataset.track !== track) continue;
      if (zone.dataset.zone === 'parking' && !allowParking) continue;
      return zone;
    }
    return null;
  }

  function resizeEdge(el, clientX) {
    // Activities and key results can be resized from either end.
    if (!el.classList.contains('gantt-bar--activity') && !el.classList.contains('gantt-bar--kr')) return null;
    if (el.dataset.parked === '1') return null;
    const zone = el.closest('[data-zone]');
    if (!zone || zone.dataset.zone !== 'track') return null;
    const rect = el.getBoundingClientRect();
    if (rect.width < 4) return null;
    const edge = Math.min(EDGE_PX, Math.max(4, rect.width / 3));
    if (clientX - rect.left <= edge) return 'start';
    if (rect.right - clientX <= edge) return 'end';
    return null;
  }

  function init() {
    const gantt = document.querySelector('.gantt');
    const timeline = window.TIMELINE;
    if (!gantt || !timeline) return;

    let drag = null;
    let suppressClick = false;

    window.addEventListener('click', (e) => {
      if (!suppressClick) return;
      e.preventDefault();
      e.stopImmediatePropagation();
      suppressClick = false;
    }, true);

    async function persist(state, payload) {
      const url = state.kind === 'kr'
        ? `/api/key-results/${state.entityId}/`
        : `/api/items/${state.entityId}/`;
      const res = await fetch(url, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(await res.text());
    }

    gantt.addEventListener('pointermove', (e) => {
      if (drag) return;
      gantt.querySelectorAll('.gantt-bar--resize-edge').forEach((b) => b.classList.remove('gantt-bar--resize-edge'));
      const el = e.target.closest('.gantt-bar--draggable');
      if (!el) return;
      if (resizeEdge(el, e.clientX)) el.classList.add('gantt-bar--resize-edge');
    });

    function onPointerMove(e) {
      if (!drag) return;
      const dx = e.clientX - drag.startX;
      const dy = e.clientY - drag.startY;
      if (!drag.active) {
        if (Math.hypot(dx, dy) < THRESHOLD_PX) return;
        drag.active = true;
        document.body.classList.add(drag.mode === 'move' ? 'gantt-item-dragging' : 'gantt-item-resizing');
        drag.el.classList.add(drag.mode === 'move' ? 'gantt-bar--dragging' : 'gantt-bar--resizing');
        if (drag.mode === 'move') {
          drag.ghost = drag.el.cloneNode(true);
          drag.ghost.classList.add('gantt-drag-ghost');
          drag.ghost.style.position = 'fixed';
          drag.ghost.style.margin = '0';
          drag.ghost.style.pointerEvents = 'none';
          drag.ghost.style.zIndex = '1000';
          drag.ghost.style.width = `${drag.rect.width}px`;
          drag.ghost.style.height = `${drag.rect.height}px`;
          drag.ghost.style.left = `${drag.rect.left}px`;
          drag.ghost.style.top = `${drag.rect.top}px`;
          document.body.appendChild(drag.ghost);
          drag.el.style.opacity = '0.35';
        }
      }

      if (drag.mode === 'resize-start' || drag.mode === 'resize-end') {
        const track = drag.homeTrack;
        if (!track) return;
        const trackRect = track.getBoundingClientRect();
        const xPct = ((e.clientX - trackRect.left) / trackRect.width) * 100;
        const rightPct = drag.leftPct + drag.widthPct;
        let leftPct = drag.leftPct;
        let widthPct = drag.widthPct;
        if (drag.mode === 'resize-start') {
          leftPct = Math.max(0, Math.min(rightPct - MIN_WIDTH_PCT, xPct));
          widthPct = rightPct - leftPct;
        } else {
          const newRight = Math.max(drag.leftPct + MIN_WIDTH_PCT, Math.min(100, xPct));
          widthPct = newRight - drag.leftPct;
        }
        drag.el.style.left = `${leftPct}%`;
        drag.el.style.width = `${widthPct}%`;
        drag.newLeft = leftPct;
        drag.newWidth = widthPct;
        return;
      }

      const allowParking = drag.itemType !== 'metric';
      const zone = findZone(e.clientX, e.clientY, drag.laneKey, drag.track, allowParking);
      gantt.querySelectorAll('.gantt-drop-ok').forEach((z) => z.classList.remove('gantt-drop-ok'));
      if (zone) zone.classList.add('gantt-drop-ok');

      if (drag.ghost) {
        drag.ghost.style.left = `${drag.rect.left + dx}px`;
        drag.ghost.style.top = `${drag.rect.top + dy}px`;
      }
      drag.zone = zone;
    }

    async function onPointerUp(e) {
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', onPointerUp);
      if (!drag) return;

      const state = drag;
      drag = null;
      document.body.classList.remove('gantt-item-dragging', 'gantt-item-resizing');
      gantt.querySelectorAll('.gantt-drop-ok').forEach((z) => z.classList.remove('gantt-drop-ok'));
      if (state.ghost) state.ghost.remove();
      state.el.classList.remove('gantt-bar--dragging', 'gantt-bar--resizing', 'gantt-bar--resize-edge');
      state.el.style.opacity = '';

      if (!state.active) return;
      suppressClick = true;

      try {
        if (state.mode === 'resize-start' || state.mode === 'resize-end') {
          const left = state.newLeft != null ? state.newLeft : state.leftPct;
          const width = state.newWidth != null ? state.newWidth : state.widthPct;
          const start = pctToDate(left, timeline);
          const end = pctToDate(left + width, timeline);
          if (!start || !end) return;
          const startIso = dateToIso(start);
          const endIso = dateToIso(end < start ? start : end);
          await persist(state, { start_date: startIso, end_date: endIso });
          window.location.reload();
          return;
        }

        if (!state.zone) return;
        const zone = state.zone;
        const targetRow = rowFromY(zone, e.clientY, state.itemType);
        const payload = {};

        if (zone.dataset.zone === 'parking') {
          payload.row = targetRow;
          payload.start_date = '';
          payload.end_date = '';
        } else {
          const trackRect = zone.getBoundingClientRect();
          let leftPct;
          if (state.parked) {
            leftPct = ((e.clientX - trackRect.left) / trackRect.width) * 100;
          } else {
            const dx = e.clientX - state.startX;
            leftPct = state.leftPct + (dx / trackRect.width) * 100;
          }
          const widthPct = state.widthPct || 0;
          leftPct = Math.max(0, Math.min(100 - Math.max(widthPct, 0.5), leftPct));
          const start = pctToDate(leftPct, timeline);
          if (!start) return;
          if (state.itemType === 'milestone') {
            payload.start_date = dateToIso(start);
            payload.end_date = dateToIso(start);
          } else if (state.parked) {
            payload.start_date = dateToIso(start);
            payload.end_date = dateToIso(addDays(start, DEFAULT_UNPARK_DAYS));
          } else {
            payload.start_date = dateToIso(start);
            payload.end_date = dateToIso(addDays(start, state.durationDays));
          }
          // Never overlap another bar on the same row — drop onto the next free line.
          payload.row = freeRow(zone, state.el, leftPct, widthPct, targetRow);
        }

        await persist(state, payload);
        window.location.reload();
      } catch (err) {
        console.error('Failed to move bar:', err);
        alert('Could not update.');
        state.el.style.left = `${state.leftPct}%`;
        state.el.style.width = `${state.widthPct}%`;
      }
    }

    gantt.addEventListener('pointerdown', (e) => {
      if (e.button !== 0) return;
      if (e.target.closest('.gantt-lane__handle')) return;
      const el = e.target.closest('[data-item-id].gantt-bar--draggable, [data-kr-id].gantt-bar--draggable');
      if (!el) return;
      const zone = el.closest('[data-zone][data-lane-key][data-track]');
      if (!zone) return;

      const isKr = el.dataset.krId != null;
      const startIso = el.dataset.start || '';
      const endIso = el.dataset.end || '';
      const start = isoToDate(startIso);
      const end = isoToDate(endIso);
      const edge = resizeEdge(el, e.clientX);

      drag = {
        el,
        mode: edge ? `resize-${edge}` : 'move',
        kind: isKr ? 'kr' : 'item',
        entityId: isKr ? el.dataset.krId : el.dataset.itemId,
        itemType: isKr ? 'metric' : el.dataset.itemType,   // KR bars live in the metrics track
        laneKey: zone.dataset.laneKey,
        track: zone.dataset.track,
        homeTrack: zone.dataset.zone === 'track' ? zone : null,
        parked: el.dataset.parked === '1' || zone.dataset.zone === 'parking',
        leftPct: parseFloat(el.dataset.left || '0'),
        widthPct: parseFloat(el.dataset.width || '0'),
        durationDays: start && end ? dayDiff(start, end) : DEFAULT_UNPARK_DAYS,
        startX: e.clientX,
        startY: e.clientY,
        rect: el.getBoundingClientRect(),
        active: false,
        ghost: null,
        zone: null,
        newLeft: null,
        newWidth: null,
      };
      try { el.setPointerCapture(e.pointerId); } catch (err) { /* ignore */ }
      window.addEventListener('pointermove', onPointerMove);
      window.addEventListener('pointerup', onPointerUp);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
