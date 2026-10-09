/* Roadmap list page: name search (3+ chars) + organisation filter.
 * Roadmaps are created from a team's page, so there is no create modal here. */

function roadmapList() {
  return {
    roadmaps: window.ROADMAPS || [],
    searchName: '',
    selectedOrg: '',
    showArchived: false,

    // Archived roadmaps are hidden by default; the toggle shows only the archived
    // ones so they can be reopened without cluttering the active list.
    get archivedCount() { return this.roadmaps.filter((r) => r.archived).length; },

    get filteredRoadmaps() {
      let list = this.roadmaps.filter((r) => !!r.archived === this.showArchived);
      const q = this.searchName.trim().toLowerCase();
      // Only filter by name once 3+ characters are entered.
      if (q.length >= 3) list = list.filter((r) => r.name.toLowerCase().includes(q));
      if (this.selectedOrg) list = list.filter((r) => r.org_ids.map(String).includes(this.selectedOrg));
      return list;
    },
    clearFilters() { this.searchName = ''; this.selectedOrg = ''; },
  };
}
