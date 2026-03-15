(function () {
  const input = document.getElementById('newsletter-search-input');
  const results = document.getElementById('newsletter-search-results');
  const status = document.getElementById('newsletter-search-status');
  if (!input || !results || !status) return;

  const baseUrl = (window.frontierThreadsConfig && window.frontierThreadsConfig.baseUrl) || '';
  const searchUrl = `${baseUrl}/search.json`;
  let items = [];

  function render(matches, query) {
    if (!query) {
      results.innerHTML = '';
      status.textContent = 'Type to search all archived issues.';
      return;
    }

    status.textContent = `${matches.length} result${matches.length === 1 ? '' : 's'} for "${query}".`;
    results.innerHTML = matches.slice(0, 50).map((item) => {
      return `
        <article class="search-result">
          <div class="search-section">${item.date}</div>
          <h3><a href="${baseUrl}${item.url}">${item.display_date}</a></h3>
          <p>${item.summary}</p>
        </article>
      `;
    }).join('');
  }

  function search(query) {
    const normalized = query.trim().toLowerCase();
    if (!normalized) {
      render([], '');
      return;
    }
    const matches = items.filter((item) => item.search_text.toLowerCase().includes(normalized));
    render(matches, normalized);
  }

  fetch(searchUrl)
    .then((response) => response.json())
    .then((data) => {
      items = Array.isArray(data) ? data : [];
      status.textContent = `Search ${items.length} archived issue${items.length === 1 ? '' : 's'}.`;
    })
    .catch(() => {
      status.textContent = 'Search index failed to load.';
    });

  input.addEventListener('input', function () {
    search(input.value);
  });
})();
