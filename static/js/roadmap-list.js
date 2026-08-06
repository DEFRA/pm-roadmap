/* Roadmap list page: name search (3+ chars) + organisation filter.
 * Roadmaps are created from a team's page, so there is no create modal here. */

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
  };
}
