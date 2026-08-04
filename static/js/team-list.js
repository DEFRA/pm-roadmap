/* Teams list page: name search (3+ chars) + organisation filter, mirroring the
 * roadmaps list page. Data comes from window.TEAMS (serialised in the template). */

function teamList() {
  return {
    teams: window.TEAMS || [],
    searchName: '',
    selectedOrg: '',

    get filteredTeams() {
      let list = this.teams;
      const q = this.searchName.trim().toLowerCase();
      // Only filter by name once 3+ characters are entered.
      if (q.length >= 3) list = list.filter((t) => t.name.toLowerCase().includes(q));
      if (this.selectedOrg) list = list.filter((t) => String(t.org_id) === this.selectedOrg);
      return list;
    },
    clearFilters() { this.searchName = ''; this.selectedOrg = ''; },
  };
}
