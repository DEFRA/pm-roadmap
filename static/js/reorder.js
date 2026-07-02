/* Swim-lane reordering (desktop / mouse).
 *
 * Each main swim lane is a `.gantt-lane` wrapper (display:contents) holding its
 * 6 grid cells. Grabbing the handle and dragging up/down live-reorders the lanes
 * — when the pointer passes the vertical midpoint of a neighbouring lane, the
 * dragged lane snaps into that slot. On drop, the new order is persisted via
 * POST /api/tags/reorder/. "Untagged" (no data-tag-id) is fixed and stays last.
 *
 * Touch/mobile is intentionally not handled yet.
 */
(function () {
  function getCookie(name) {
    const m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return m ? decodeURIComponent(m.pop()) : '';
  }

  function init() {
    const gantt = document.querySelector('.gantt');
    if (!gantt) return;

    const draggableLanes = () =>
      Array.from(gantt.querySelectorAll('.gantt-lane[data-tag-id]'));

    // How far the pointer must cross into a neighbouring lane before the order
    // snaps (fraction of that lane's height). 0.33 = a third; direction-aware so
    // it's a third whether dragging up or down, with a dead-zone in between.
    const THRESHOLD = 0.33;

    // Top / bottom / height of a lane, from its first and last grid cell (the
    // wrapper itself has no box because of display:contents).
    function laneBounds(lane) {
      const cells = lane.children;
      const top = cells[0].getBoundingClientRect().top;
      const bottom = cells[cells.length - 1].getBoundingClientRect().bottom;
      return { top, bottom, height: bottom - top };
    }

    let dragged = null;
    let startOrder = [];

    function onPointerMove(e) {
      if (!dragged) return;
      const y = e.clientY;
      const lanes = draggableLanes();
      const draggedIndex = lanes.indexOf(dragged);

      // Insert before the first lane whose trigger point is below the pointer.
      // The trigger sits THRESHOLD into the lane from the edge the dragged lane
      // approaches: 33% from the top for lanes below, 33% from the bottom for
      // lanes above. The gap between the two keeps the swap from flickering.
      let ref = null;
      for (let i = 0; i < lanes.length; i++) {
        const lane = lanes[i];
        if (lane === dragged) continue;
        const b = laneBounds(lane);
        const trigger = i < draggedIndex
          ? b.top + b.height * (1 - THRESHOLD)
          : b.top + b.height * THRESHOLD;
        if (y < trigger) { ref = lane; break; }
      }

      if (ref) {
        if (dragged.nextElementSibling !== ref) gantt.insertBefore(dragged, ref);
      } else {
        // Past all lanes → place last, but keep the Untagged lane trailing.
        const untagged = gantt.querySelector('.gantt-lane:not([data-tag-id])');
        if (untagged) {
          if (untagged.previousElementSibling !== dragged) gantt.insertBefore(dragged, untagged);
        } else if (gantt.lastElementChild !== dragged) {
          gantt.appendChild(dragged);
        }
      }
    }

    async function onPointerUp() {
      if (!dragged) return;
      dragged.classList.remove('gantt-lane--dragging');
      document.body.classList.remove('gantt-reordering');
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', onPointerUp);
      dragged = null;

      const ids = draggableLanes().map((l) => l.dataset.tagId);
      if (ids.join(',') === startOrder.join(',')) return;  // no change

      try {
        await fetch('/api/tags/reorder/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
          body: JSON.stringify({ ids: ids.map(Number) }),
        });
      } catch (err) {
        console.error('Failed to save lane order:', err);
      }
    }

    gantt.addEventListener('pointerdown', (e) => {
      const handle = e.target.closest('.gantt-lane__handle');
      if (!handle || e.button !== 0) return;
      const lane = handle.closest('.gantt-lane[data-tag-id]');
      if (!lane) return;

      e.preventDefault();
      dragged = lane;
      startOrder = draggableLanes().map((l) => l.dataset.tagId);
      lane.classList.add('gantt-lane--dragging');
      document.body.classList.add('gantt-reordering');
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
