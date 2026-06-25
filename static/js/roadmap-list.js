/* Roadmap list page: name search (3+ chars) + organisation filter, and a
 * New Roadmap modal posting to the Django JSON API. */

function getCookie(name) {
  const m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
  return m ? decodeURIComponent(m.pop()) : '';
}

function roadmapList() {
  return {
    roadmaps: window.ROADMAPS || [],
    searchName: '',
    selectedOrg: '',

    get filteredRoadmaps() {
      let list = this.roadmaps;
      const q = this.searchName.trim().toLowerCase();
      // Only filter by name once 3+ characters are entered.
      if (q.length >= 3) list = list.filter((r) => r.name.toLowerCase().includes(q));
      if (this.selectedOrg) list = list.filter((r) => r.org_ids.map(String).includes(this.selectedOrg));
      return list;
    },
    clearFilters() { this.searchName = ''; this.selectedOrg = ''; },

    // ── New roadmap modal ──
    showNew: false,
    form: { name: '', roadmap_type: '', team: '', description: '', organisations: [] },
    openNew() {
      this.form = { name: '', roadmap_type: '', team: '', description: '', organisations: [] };
      this.showNew = true;
    },
    closeNew() { this.showNew = false; },
    async saveNew() {
      if (!this.form.name.trim()) { alert('Name is required'); return; }
      if (!this.form.roadmap_type) { alert('Please choose a roadmap type'); return; }
      try {
        const res = await fetch('/api/roadmaps/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
          body: JSON.stringify({
            name: this.form.name, roadmap_type: this.form.roadmap_type,
            team: this.form.team, description: this.form.description,
            organisations: this.form.organisations.map(Number),
          }),
        });
        if (!res.ok) throw new Error((await res.json()).error || res.status);
        const created = await res.json();
        window.location.href = '/' + created.id + '/';
      } catch (e) { alert('Failed to create roadmap: ' + e.message); }
    },
  };
}
