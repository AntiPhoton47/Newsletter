(function () {
  const input = document.getElementById('newsletter-search-input');
  const results = document.getElementById('newsletter-search-results');
  const status = document.getElementById('newsletter-search-status');
  const categorySelect = document.getElementById('newsletter-category-select');
  const sortSelect = document.getElementById('newsletter-sort-select');
  const tagInput = document.getElementById('newsletter-tag-input');
  const archiveList = document.getElementById('newsletter-archive-list');
  if (!input || !results || !status) return;

  const baseUrl = (window.frontierThreadsConfig && window.frontierThreadsConfig.baseUrl) || '';
  const searchUrl = `${baseUrl}/search.json`;
  let items = [];
  let bootstrapped = false;

  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function readParams() {
    const url = new URL(window.location.href);
    return {
      q: url.searchParams.get('q') || '',
      category: url.searchParams.get('category') || '',
      tag: url.searchParams.get('tag') || '',
      sort: url.searchParams.get('sort') || '',
    };
  }

  function writeParams() {
    const url = new URL(window.location.href);
    const params = {
      q: input.value.trim(),
      category: categorySelect ? categorySelect.value : '',
      tag: tagInput ? tagInput.value.trim() : '',
      sort: sortSelect ? sortSelect.value : '',
    };
    Object.entries(params).forEach(([key, value]) => {
      if (value) {
        url.searchParams.set(key, value);
      } else {
        url.searchParams.delete(key);
      }
    });
    window.history.replaceState({}, '', url.toString());
  }

  function metaLine(item) {
    if (item.kind === 'page') return 'Site page';
    return `${item.published_label || item.display_date} · ${item.reading_time} min read`;
  }

  function badgeMarkup(item) {
    const badges = [];
    if (item.pinned) badges.push('<span class="result-badge">Pinned</span>');
    if (item.featured) badges.push('<span class="result-badge result-badge--accent">Featured</span>');
    return badges.length ? `<div class="card-badges">${badges.join('')}</div>` : '';
  }

  function chips(item) {
    const tags = Array.isArray(item.tags) ? item.tags.slice(0, 4) : [];
    const category = item.primary_category ? `<span class="taxonomy-chip taxonomy-chip--category">${escapeHtml(item.primary_category)}</span>` : '';
    return `<div class="card-tags">${category}${tags.map((tag) => `<span class="taxonomy-chip">${escapeHtml(tag)}</span>`).join('')}</div>`;
  }

  function snippetFor(item, terms) {
    const haystack = item.search_text || '';
    const lower = haystack.toLowerCase();
    let index = -1;
    for (const term of terms) {
      index = lower.indexOf(term);
      if (index !== -1) break;
    }
    if (index === -1) return '';
    const start = Math.max(0, index - 70);
    const end = Math.min(haystack.length, index + 170);
    let snippet = haystack.slice(start, end).trim();
    if (start > 0) snippet = `...${snippet}`;
    if (end < haystack.length) snippet = `${snippet}...`;
    let rendered = escapeHtml(snippet);
    for (const term of terms) {
      const pattern = new RegExp(term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'ig');
      rendered = rendered.replace(pattern, (match) => `<span class="search-hit">${match}</span>`);
    }
    return rendered;
  }

  function renderResults(matches, hasFilters, terms) {
    if (!hasFilters) {
      results.innerHTML = '';
      status.textContent = `Search ${items.length} indexed pages and issues.`;
      return;
    }
    status.textContent = `${matches.length} result${matches.length === 1 ? '' : 's'}.`;
    if (!matches.length) {
      results.innerHTML = '<div class="search-empty">No matches yet. Try a broader keyword, a different tag, or clear one of the filters.</div>';
      return;
    }
    results.innerHTML = matches.slice(0, 50).map((item) => {
      const snippet = snippetFor(item, terms);
      return `
        <article class="search-result">
          ${badgeMarkup(item)}
          <div class="search-section">${escapeHtml(item.primary_category || item.date)}</div>
          <h3><a href="${baseUrl}${item.url}">${escapeHtml(item.title)}</a></h3>
          <p class="card-meta">${escapeHtml(metaLine(item))}</p>
          <p>${escapeHtml(item.summary)}</p>
          ${chips(item)}
          ${snippet ? `<div class="search-result-snippet">${snippet}</div>` : ''}
        </article>
      `;
    }).join('');
  }

  function renderArchive(matches) {
    if (!archiveList) return;
    const issueMatches = matches.filter((item) => item.kind === 'issue');
    if (!issueMatches.length) {
      archiveList.innerHTML = '<div class="search-empty">No issues match these filters yet.</div>';
      return;
    }
    archiveList.innerHTML = issueMatches.map((item) => `
      <article class="archive-item ${item.featured ? 'archive-item--featured' : ''}" data-date="${escapeHtml(item.date)}" data-category="${escapeHtml(item.primary_category || '')}" data-tags="${escapeHtml((item.tags || []).join(','))}" data-reading-time="${escapeHtml(item.reading_time)}" data-title="${escapeHtml(item.title)}">
        ${badgeMarkup(item)}
        <div class="search-section">${escapeHtml(item.primary_category || 'Issue')}</div>
        <h3><a href="${baseUrl}${item.url}">${escapeHtml(item.title)}</a></h3>
        <p class="card-meta">${escapeHtml(metaLine(item))}</p>
        <p>${escapeHtml(item.summary)}</p>
        ${chips(item)}
      </article>
    `).join('');
  }

  function sortMatches(matches) {
    const sortValue = sortSelect ? sortSelect.value : (archiveList ? 'newest' : 'relevance');
    const sorted = matches.slice();
    if (sortValue === 'title') {
      sorted.sort((a, b) => a.title.localeCompare(b.title));
    } else if (sortValue === 'oldest') {
      sorted.sort((a, b) => (a.date || '').localeCompare(b.date || ''));
    } else if (sortValue === 'reading') {
      sorted.sort((a, b) => (b.reading_time || 0) - (a.reading_time || 0) || (b.date || '').localeCompare(a.date || ''));
    } else if (sortValue === 'newest') {
      sorted.sort((a, b) => (b.date || '').localeCompare(a.date || ''));
    } else {
      sorted.sort((a, b) => (b.score || 0) - (a.score || 0) || (b.date || '').localeCompare(a.date || ''));
    }
    return sorted;
  }

  function filterItems() {
    const query = input.value.trim().toLowerCase().replace(/\s+/g, ' ');
    const terms = query ? query.split(' ').filter(Boolean) : [];
    const selectedCategory = categorySelect ? categorySelect.value.toLowerCase() : '';
    const tagTerm = tagInput ? tagInput.value.trim().toLowerCase() : '';
    const pool = archiveList ? items.filter((item) => item.kind === 'issue') : items;
    const hasFilters = Boolean(query || selectedCategory || tagTerm);

    const matches = pool.map((item) => {
      const title = (item.title || '').toLowerCase();
      const summary = (item.summary || '').toLowerCase();
      const text = (item.search_text || '').toLowerCase();
      const categories = (item.categories || []).map((value) => value.toLowerCase());
      const tags = (item.tags || []).map((value) => value.toLowerCase());
      if (selectedCategory && !categories.includes(selectedCategory) && (item.primary_category || '').toLowerCase() !== selectedCategory) {
        return null;
      }
      if (tagTerm && !tags.some((tag) => tag.includes(tagTerm))) {
        return null;
      }

      let score = 0;
      if (terms.length) {
        let matched = 0;
        for (const term of terms) {
          let termScore = 0;
          if (title.includes(term)) termScore += 12;
          if (summary.includes(term)) termScore += 6;
          if (tags.some((tag) => tag.includes(term))) termScore += 7;
          if (categories.some((category) => category.includes(term))) termScore += 4;
          if (text.includes(term)) termScore += 2;
          if (termScore > 0) matched += 1;
          score += termScore;
        }
        if (!score) return null;
        if (matched === terms.length) score += 20;
      } else {
        score = 1;
      }

      if (item.featured) score += 4;
      if (item.pinned) score += 2;
      return { ...item, score };
    }).filter(Boolean);

    const sorted = sortMatches(matches);
    renderResults(sorted, hasFilters, terms);
    renderArchive(sorted);
  }

  function populateControls() {
    const pool = archiveList ? items.filter((item) => item.kind === 'issue') : items;
    const categories = Array.from(new Set(pool.flatMap((item) => item.categories || []))).sort();
    if (categorySelect) {
      const selected = categorySelect.value;
      categorySelect.innerHTML = '<option value="">All categories</option>' + categories.map((category) => `<option value="${escapeHtml(category)}">${escapeHtml(category)}</option>`).join('');
      categorySelect.value = categories.includes(selected) ? selected : selected || '';
    }
  }

  function applyInitialState() {
    const params = readParams();
    if (params.q) input.value = params.q;
    if (tagInput && params.tag) tagInput.value = params.tag;
    if (sortSelect && params.sort) sortSelect.value = params.sort;
    if (categorySelect && params.category) categorySelect.value = params.category;
    bootstrapped = true;
    filterItems();
  }

  function applyShortcut(dataset) {
    if (dataset.searchQuery) input.value = dataset.searchQuery;
    if (dataset.searchTag && tagInput) tagInput.value = dataset.searchTag;
    if (dataset.searchCategory && categorySelect) categorySelect.value = dataset.searchCategory;
    if (dataset.searchSort && sortSelect) sortSelect.value = dataset.searchSort;
    if (bootstrapped) writeParams();
    filterItems();
  }

  fetch(searchUrl)
    .then((response) => response.json())
    .then((data) => {
      items = Array.isArray(data) ? data : [];
      populateControls();
      applyInitialState();
    })
    .catch(() => {
      status.textContent = 'Search index failed to load.';
      if (archiveList) archiveList.innerHTML = '<div class="search-empty">Search index failed to load.</div>';
    });

  [input, categorySelect, sortSelect, tagInput].forEach((element) => {
    if (!element) return;
    element.addEventListener('input', function () {
      if (bootstrapped) writeParams();
      filterItems();
    });
    element.addEventListener('change', function () {
      if (bootstrapped) writeParams();
      filterItems();
    });
  });

  function scrollCarousel(id, direction) {
    const track = document.querySelector(`[data-carousel-track="${id}"]`);
    if (!track) return;
    const step = Math.max(track.clientWidth * 0.82, 280);
    track.scrollBy({ left: direction * step, behavior: 'smooth' });
  }

  document.addEventListener('click', function (event) {
    const prev = event.target.closest('[data-carousel-prev]');
    const next = event.target.closest('[data-carousel-next]');
    const shortcut = event.target.closest('[data-search-query], [data-search-tag], [data-search-category], [data-search-sort]');

    if (prev) scrollCarousel(prev.getAttribute('data-carousel-prev'), -1);
    if (next) scrollCarousel(next.getAttribute('data-carousel-next'), 1);
    if (shortcut) applyShortcut(shortcut.dataset);
  });
})();
