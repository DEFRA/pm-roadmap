/* Detail-page Alpine component: item view/edit, manage-tags, edit-roadmap,
 * editable tag descriptions, and PNG/PDF export. Talks to the Django JSON API
 * at /api, sending the CSRF token on writes. Seed data comes from window.* set
 * in the template. */

function getCookie(name) {
  const m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
  return m ? decodeURIComponent(m.pop()) : '';
}

async function apiFetch(url, method, body) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
  };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(url, opts);
  if (!res.ok) {
    let msg = res.status;
    try { msg = (await res.json()).error || msg; } catch (e) { /* ignore */ }
    throw new Error(msg);
  }
  return res.status === 204 ? null : res.json();
}

function blankItemForm() {
  return {
    id: null, item_type: 'activity', title: '', description: '',
    priority: '', size: '', start_date: '', end_date: '',
    prd_link: '', backlog_link: '', tags: [], linked_activities: [],
    objective: '', key_results: [],
  };
}

function roadmapApp() {
  return {
    // ── seed ──
    roadmap: window.ROADMAP || {},
    manage: window.MANAGE || { pools: {}, selected: [], objective_type: 'gov_objective' },
    itemTagPools: window.ITEM_TAG_POOLS || {},
    objectiveType: window.OBJECTIVE_TYPE || 'gov_objective',
    activities: window.ACTIVITIES || [],
    roadmapObjectives: window.ROADMAP_OBJECTIVES || [],
    orgOptions: window.ORG_OPTIONS || [],
    init() {
      this.roadmapObjectives = window.ROADMAP_OBJECTIVES || [];
    },

    // ── item view modal ──
    activeItem: null,
    openModal(id) {
      this.activeTag = null;
      this.activeItem = window.ITEM_DATA[id] || null;
    },
    closeModal() { this.activeItem = null; },

    // ── tag info modal (view by default; edit on pencil) ──
    activeTag: null,
    activeTagId: null,
    tagEditing: false,
    tagInfoDraft: '',
    tagLinkDraft: '',
    tagNameDraft: '',
    tagInfoSaving: false,
    openTagModal(id) {
      this.activeItem = null;
      this.activeTag = window.TAG_INFO[id] || null;
      this.activeTagId = id;
      this.tagEditing = false;
      this._resetTagDrafts();
    },
    _resetTagDrafts() {
      const t = this.activeTag || {};
      this.tagInfoDraft = t.description || '';
      this.tagLinkDraft = t.link || '';
      this.tagNameDraft = t.name || '';
      this.tagInfoSaving = false;
    },
    startTagEdit() { this._resetTagDrafts(); this.tagEditing = true; },
    cancelTagEdit() { this.tagEditing = false; this._resetTagDrafts(); },
    closeTagModal() { this.activeTag = null; this.tagEditing = false; },
    async saveTagInfo() {
      this.tagInfoSaving = true;
      const payload = {
        description: this.tagInfoDraft.trim(),
        link: this.tagLinkDraft.trim(),
      };
      // Name is only sent (and only honoured server-side) for scoped types.
      if (this.activeTag && this.activeTag.name_editable) {
        payload.name = this.tagNameDraft.trim();
      }
      try {
        await apiFetch(`/api/tags/${this.activeTagId}/`, 'PUT', payload);
        window.location.reload();
      } catch (e) {
        alert('Failed to save: ' + e.message);
        this.tagInfoSaving = false;
      }
    },

    // ── edit roadmap modal ──
    showEditRoadmap: false,
    roadmapForm: {},
    openEditRoadmap() {
      const r = this.roadmap;
      this.roadmapForm = {
        name: r.name || '', team: r.team || '', mission: r.mission || '',
        vision: r.vision || '', description: r.description || '',
        organisations: [...(r.organisations || [])].map(String),
      };
      this.showEditRoadmap = true;
    },
    closeEditRoadmap() { this.showEditRoadmap = false; },
    async saveEditRoadmap() {
      try {
        await apiFetch(`/api/roadmaps/${this.roadmap.id}/`, 'PUT', {
          name: this.roadmapForm.name,
          team: this.roadmapForm.team,
          mission: this.roadmapForm.mission,
          vision: this.roadmapForm.vision,
          description: this.roadmapForm.description,
          organisations: this.roadmapForm.organisations.map(Number),
        });
        window.location.reload();
      } catch (e) { alert('Failed to save roadmap: ' + e.message); }
    },

    // ── manage tags modal ──
    showManage: false,
    managePool: {},
    manageSelected: [],
    manageInputs: {},
    openManage() {
      this.managePool = {};
      Object.keys(this.manage.pools || {}).forEach((t) => {
        this.managePool[t] = (this.manage.pools[t] || []).map((x) => ({ ...x }));
      });
      this.manageSelected = [...(this.manage.selected || [])];
      this.manageInputs = {};
      this.showManage = true;
    },
    closeManage() { this.showManage = false; },
    isManageSelected(id) { return this.manageSelected.includes(id); },
    toggleManage(id) {
      const i = this.manageSelected.indexOf(id);
      if (i === -1) this.manageSelected.push(id); else this.manageSelected.splice(i, 1);
    },
    async manageAdd(tagType) {
      const name = (this.manageInputs[tagType] || '').trim();
      if (!name) { alert('Please enter a name'); return; }
      try {
        const tag = await apiFetch('/api/tags/', 'POST', {
          name, tag_type: tagType, roadmap: this.roadmap.id,
        });
        if (!this.managePool[tagType]) this.managePool[tagType] = [];
        this.managePool[tagType].push({ id: tag.id, name: tag.name, colour: tag.colour, tag_type: tag.tag_type });
        this.manageSelected.push(tag.id);
        this.manageInputs[tagType] = '';
      } catch (e) { alert('Failed to add: ' + e.message); }
    },
    async saveManage() {
      try {
        await apiFetch(`/api/roadmaps/${this.roadmap.id}/`, 'PUT', { tags: this.manageSelected });
        window.location.reload();
      } catch (e) { alert('Failed to save tags: ' + e.message); }
    },

    // ── manage which objectives show as swim lanes (B2 visibility tickbox) ──
    // Each entry is {id, title, shown}; shown=false hides the lane on this roadmap.
    manageObjectives: (window.MANAGE_OBJECTIVES || []).map((o) => ({
      id: o.id, title: o.title, shown: !o.hidden,
    })),
    showObjPanel: false,
    objSaving: false,
    openObjPanel() {
      // Re-seed from the server state each time the panel opens.
      this.manageObjectives = (window.MANAGE_OBJECTIVES || []).map((o) => ({
        id: o.id, title: o.title, shown: !o.hidden,
      }));
      this.showObjPanel = true;
    },
    closeObjPanel() { this.showObjPanel = false; },
    objSelectAll() { this.manageObjectives.forEach((o) => { o.shown = true; }); },
    objDeselectAll() { this.manageObjectives.forEach((o) => { o.shown = false; }); },
    async saveObjectiveVisibility() {
      this.objSaving = true;
      const hidden = this.manageObjectives.filter((o) => !o.shown).map((o) => o.id);
      try {
        await apiFetch(`/api/roadmaps/${this.roadmap.id}/objectives-visibility/`, 'PUT', { hidden });
        window.location.reload();
      } catch (e) {
        this.objSaving = false;
        alert('Failed to save: ' + e.message);
      }
    },

    // ── item create / edit modal ──
    showItemForm: false,
    itemForm: blankItemForm(),
    itemFormMode: 'create',
    itemPool: {},          // clone of itemTagPools, so created tags append
    itemInputs: {},
    openNewItem() {
      this.itemForm = blankItemForm();
      this.itemFormMode = 'create';
      this._resetItemPool();
      this.showItemForm = true;
    },
    editActiveItem() {
      const it = this.activeItem;
      this.itemForm = {
        id: it.id, item_type: it.item_type, title: it.title, description: it.description || '',
        priority: it.priority || '', size: it.size || '',
        start_date: this._isoDate(it), end_date: this._isoDateEnd(it),
        prd_link: it.prd_link || '', backlog_link: it.backlog_link || '',
        tags: (it.tags || []).map((t) => t.id),
        linked_activities: (it.linked_activities || []).map((a) => a.id),
        objective: it.objective ? String(it.objective) : '',
        key_results: (it.key_results || []).map((k) => k.id),
      };
      this.itemFormMode = 'edit';
      this._resetItemPool();
      this.activeItem = null;
      this.showItemForm = true;
    },
    _isoDate(it) { return it._start_iso || ''; },
    _isoDateEnd(it) { return it._end_iso || ''; },
    _resetItemPool() {
      this.itemPool = {};
      Object.keys(this.itemTagPools || {}).forEach((t) => {
        this.itemPool[t] = (this.itemTagPools[t] || []).map((x) => ({ ...x }));
      });
      this.itemInputs = {};
    },
    closeItemForm() { this.showItemForm = false; },
    isItemTagSelected(id) { return this.itemForm.tags.includes(id); },
    selectObjective(id) {
      const next = String(id);
      const newVal = String(this.itemForm.objective) === next ? '' : next;
      // Key results belong to the previously chosen objective — clear on change.
      if (newVal !== String(this.itemForm.objective)) this.itemForm.key_results = [];
      this.itemForm.objective = newVal;
    },
    objectiveKeyResults() {
      const obj = (this.roadmapObjectives || []).find(
        (o) => String(o.id) === String(this.itemForm.objective));
      return (obj && obj.key_results) || [];
    },
    toggleItemKeyResult(id) {
      const i = this.itemForm.key_results.indexOf(id);
      if (i === -1) this.itemForm.key_results.push(id); else this.itemForm.key_results.splice(i, 1);
    },
    toggleItemTag(id) {
      const i = this.itemForm.tags.indexOf(id);
      if (i === -1) this.itemForm.tags.push(id); else this.itemForm.tags.splice(i, 1);
    },
    async itemAddTag(tagType) {
      const name = (this.itemInputs[tagType] || '').trim();
      if (!name) { alert('Please enter a name'); return; }
      try {
        const roadmap = (tagType === 'organisation' || tagType === 'objective') ? this.roadmap.id : null;
        const tag = await apiFetch('/api/tags/', 'POST', { name, tag_type: tagType, colour: '#595959', roadmap });
        if (!this.itemPool[tagType]) this.itemPool[tagType] = [];
        this.itemPool[tagType].push({ id: tag.id, name: tag.name, colour: tag.colour, tag_type: tag.tag_type });
        this.itemForm.tags.push(tag.id);
        this.itemInputs[tagType] = '';
      } catch (e) { alert('Failed to add tag: ' + e.message); }
    },
    async saveItem() {
      if (!this.itemForm.title.trim()) { alert('Title is required'); return; }
      const payload = {
        item_type: this.itemForm.item_type, title: this.itemForm.title,
        description: this.itemForm.description, priority: this.itemForm.priority,
        size: this.itemForm.size, start_date: this.itemForm.start_date,
        end_date: this.itemForm.end_date, prd_link: this.itemForm.prd_link,
        backlog_link: this.itemForm.backlog_link, tags: this.itemForm.tags,
        linked_activities: this.itemForm.linked_activities,
        objective: this.itemForm.objective ? Number(this.itemForm.objective) : '',
        key_results: this.itemForm.key_results,
      };
      try {
        if (this.itemFormMode === 'edit') {
          await apiFetch(`/api/items/${this.itemForm.id}/`, 'PUT', payload);
        } else {
          await apiFetch(`/api/roadmaps/${this.roadmap.id}/items/`, 'POST', payload);
        }
        window.location.reload();
      } catch (e) { alert('Failed to save item: ' + e.message); }
    },
    async deleteActiveItem() {
      if (!confirm('Delete this item?')) return;
      try {
        await apiFetch(`/api/items/${this.activeItem.id}/`, 'DELETE');
        window.location.reload();
      } catch (e) { alert('Failed to delete: ' + e.message); }
    },

    // ── export ──
    showExport: false,
    openExport() { this.showExport = true; },
    closeExport() { this.showExport = false; },
    doExport(format) {
      this.showExport = false;
      exportRoadmap(format);
    },
  };
}
