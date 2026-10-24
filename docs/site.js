/* Progressive enhancement: documentation and package links work without JavaScript. */
(() => {
  const base = document.body.dataset.base || '';
  const q = document.querySelector('#q');
  const search = document.querySelector('.search');
  const filters = document.querySelector('#filters');
  const sort = document.querySelector('#sort');
  const labels = {native: 'Native', web: 'Web', node: 'Node.js'};
  let packages = null;

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function stateFromURL() {
    const params = new URLSearchParams(location.search);
    q.value = params.get('q') || '';
    if (!filters) return;
    const selected = params.getAll('platform');
    filters.querySelectorAll('[name="platform"]').forEach(input => { input.checked = selected.includes(input.value); });
    const type = params.get('type') || '';
    filters.querySelectorAll('[name="type"]').forEach(input => { input.checked = input.value === type; });
    if (!filters.querySelector('[name="type"]:checked')) filters.querySelector('[name="type"]').checked = true;
    filters.querySelector('[name="prerelease"]').checked = params.get('prerelease') === '1';
    sort.value = params.get('sort') === 'name' ? 'name' : 'relevance';
  }

  function updateURL(mode) {
    const params = new URLSearchParams(new FormData(filters));
    const query = q.value.trim();
    if (query) params.set('q', query);
    if (!params.get('type')) params.delete('type');
    if (sort.value !== 'relevance') params.set('sort', sort.value);
    const url = `${base}/${params.size ? '?' + params.toString() : ''}`;
    if (location.pathname + location.search !== url) history[mode + 'State'](null, '', url);
    render();
  }

  function score(pkg, query) {
    if (!query) return 1;
    const name = pkg.name.toLowerCase();
    const words = query.split(/\s+/);
    const searchable = `${name} ${pkg.description || ''} ${(pkg.keywords || []).join(' ')} ${(pkg.authors || []).join(' ')}`.toLowerCase();
    if (!words.every(word => searchable.includes(word))) return 0;
    return name === query ? 100 : name.startsWith(query) ? 80 : name.includes(query) ? 60 : (pkg.keywords || []).some(k => k.toLowerCase() === query) ? 40 : 10;
  }

  function result(pkg) {
    const article = element('article', 'package-result');
    const icon = element('div', 'package-icon', pkg.name.slice(0, 2));
    icon.setAttribute('aria-hidden', 'true');
    const summary = element('div', 'package-summary');
    const title = element('div', 'result-title');
    const h2 = element('h2');
    const link = element('a', '', pkg.name);
    // Stable results use the package's unversioned canonical entry point.
    link.href = pkg.prerelease ? pkg.url : `${base}/packages/${encodeURIComponent(pkg.name)}/`;
    h2.append(link);
    title.append(h2, element('span', 'version', pkg.vers));
    const badges = element('div', 'badges');
    (pkg.targets || []).forEach(target => badges.append(element('span', 'badge', labels[target] || target)));
    if (!pkg.targets?.length) badges.append(element('span', 'badge', 'Cross-platform'));
    if (pkg.prerelease) badges.append(element('span', 'badge prerelease', 'Prerelease'));
    const keywords = element('div', 'keywords');
    (pkg.keywords || []).forEach(keyword => keywords.append(element('span', '', keyword)));
    summary.append(title, badges,
      element('p', 'result-authors', `by ${pkg.authors?.join(', ') || 'Unknown author'}`),
      element('p', 'description', pkg.description || 'No description provided.'), keywords);
    article.append(icon, summary);
    return article;
  }

  function render() {
    if (!packages) return;
    const query = q.value.trim().toLowerCase();
    const data = new FormData(filters);
    const targets = data.getAll('platform');
    const type = data.get('type');
    const prerelease = data.has('prerelease');
    // Build emits releases in descending SemVer order per package.
    const latest = new Map();
    for (const pkg of packages) {
      if ((!prerelease && pkg.prerelease) || latest.has(pkg.name)) continue;
      latest.set(pkg.name, pkg);
    }
    const matches = [...latest.values()].map(pkg => ({pkg, score: score(pkg, query)})).filter(({pkg, score}) =>
      score > 0 && (!type || pkg.type === type) && (!targets.length || !pkg.targets.length || targets.some(t => pkg.targets.includes(t))));
    matches.sort((a, b) => (sort.value === 'relevance' ? b.score - a.score : 0) || a.pkg.name.localeCompare(b.pkg.name));
    document.querySelector('#results-title').textContent = `${matches.length} ${matches.length === 1 ? 'package' : 'packages'}${query ? ` returned for “${q.value.trim()}”` : ''}`;
    document.querySelector('#results-caption').textContent = query || targets.length || type ? 'Discover your next building block.' : 'Small building blocks. Endless possibilities.';
    document.querySelector('#search-status').textContent = '';
    const root = document.querySelector('#results');
    root.replaceChildren(...matches.map(({pkg}) => result(pkg)));
    if (!matches.length) root.append(element('p', 'empty', 'No packages match your search. Try another term or reset your filters.'));
  }

  stateFromURL();
  if (filters) {
    let timer;
    q.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => updateURL('replace'), 150); });
    search.addEventListener('submit', event => { event.preventDefault(); clearTimeout(timer); updateURL('push'); });
    filters.addEventListener('change', () => updateURL('push'));
    filters.addEventListener('reset', () => {
      // Wait for the browser's native form reset before reading values.
      setTimeout(() => { sort.value = 'relevance'; updateURL('push'); }, 0);
    });
    sort.addEventListener('change', () => updateURL('push'));
    window.addEventListener('popstate', () => { stateFromURL(); render(); });
    fetch(`${base}/search.json`).then(response => {
      if (!response.ok) throw new Error('Search data could not be loaded.');
      return response.json();
    }).then(data => { packages = data; render(); }).catch(() => {
      document.querySelector('#search-status').textContent = 'Search is unavailable. Reload to retry; you can still browse all packages below.';
    });
  }

  const tabs = [...document.querySelectorAll('.tabs a')];
  if (tabs.length) {
    document.body.classList.add('tabs-ready');
    document.querySelector('.tabs').setAttribute('role', 'tablist');
    const selectTab = () => {
      const selected = tabs.find(tab => tab.hash === location.hash) || tabs[0];
      tabs.forEach((tab, i) => {
        const active = tab === selected;
        const panel = document.querySelector(tab.hash);
        tab.id = `package-tab-${i}`;
        tab.setAttribute('role', 'tab');
        tab.setAttribute('aria-controls', panel.id);
        tab.setAttribute('aria-selected', String(active));
        tab.tabIndex = active ? 0 : -1;
        panel.setAttribute('role', 'tabpanel');
        panel.setAttribute('aria-labelledby', tab.id);
        panel.tabIndex = 0;
        panel.hidden = !active;
      });
    };
    tabs.forEach((tab, i) => {
      tab.addEventListener('click', event => {
        event.preventDefault();
        if (location.hash !== tab.hash) history.pushState(null, '', tab.hash);
        selectTab();
      });
      tab.addEventListener('keydown', event => {
        let next;
        if (event.key === 'ArrowRight') next = tabs[(i + 1) % tabs.length];
        if (event.key === 'ArrowLeft') next = tabs[(i + tabs.length - 1) % tabs.length];
        if (event.key === 'Home') next = tabs[0];
        if (event.key === 'End') next = tabs[tabs.length - 1];
        if (next) { event.preventDefault(); next.click(); next.focus(); }
      });
    });
    window.addEventListener('hashchange', selectTab);
    window.addEventListener('popstate', selectTab);
    selectTab();
  }

  document.querySelector('#copy-command')?.addEventListener('click', async event => {
    const button = event.currentTarget;
    try {
      await navigator.clipboard.writeText(document.querySelector('#install-command').textContent);
      button.textContent = 'Copied';
      document.querySelector('#copy-status').textContent = 'Install command copied.';
    } catch {
      button.textContent = 'Select command';
      const range = document.createRange();
      range.selectNodeContents(document.querySelector('#install-command'));
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      document.querySelector('#copy-status').textContent = 'Clipboard unavailable. Command selected; copy it manually.';
    }
    setTimeout(() => { button.textContent = 'Copy'; }, 2200);
  });
})();
