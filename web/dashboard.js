(() => {
  'use strict';
  const data = JSON.parse(document.getElementById('dashboard-data').textContent);
  const $ = id => document.getElementById(id);
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const weeks = [...(data.weeks || [])].sort((a, b) => String(b.start_date).localeCompare(String(a.start_date)));
  const series = [...(data.series || [])].sort((a, b) => new Set(b.observations.map(o => o.week_id)).size - new Set(a.observations.map(o => o.week_id)).size || String(a.item).localeCompare(String(b.item)));
  const state = {week: weeks[0], aisle: null, historyAisle: null, view: 'offers'};
  const money = value => Number.isFinite(Number(value)) && value !== null ? '$' + Number(value).toFixed(2) : 'Not parsed';
  const date = value => {
    if (!value) return 'Unknown date';
    const parsed = new Date(String(value).slice(0, 10) + 'T12:00:00');
    return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleDateString('en-US', {month: 'short', day: 'numeric', year: 'numeric'});
  };
  const weekLabel = week => `${date(week.start_date)} – ${date(week.end_date)}`;
  const element = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text !== undefined && text !== null) node.textContent = String(text);
    if (className) node.className = className;
    return node;
  };
  const option = (value, label) => {
    const node = element('option', label);
    node.value = value;
    return node;
  };
  const setText = (id, text) => { $(id).textContent = text; };
  const clear = id => $(id).replaceChildren();
  const category = offer => offer.category || 'Uncategorized';
  const flagged = offer => (offer._issues || []).length > 0 || ['low', 'medium'].includes(offer.confidence) || !(offer.prices || []).some(p => p.price_n !== null && p.price_n !== undefined) && (offer.price_n === null || offer.price_n === undefined);
  const prettyIssue = issue => String(issue).replaceAll('_', ' ');
  const rawPrice = value => {
    if (value === null || value === undefined || value === '') return 'See price options';
    const text = String(value);
    return /^\d+(?:\.\d+)?$/.test(text) ? money(text) : text;
  };
  const pricedOptions = offer => (offer.prices || []).filter(p => p.price || p.price_n !== null && p.price_n !== undefined);
  const sourceHref = (week, page) => {
    const value = week?.source?.pdf_href || week?.source?.pdf_url;
    if (!value) return null;
    // Keep relative archive links and local file links usable in offline reports.
    // Reject executable and data protocols even when source metadata is untrusted.
    try {
      const url = new URL(String(value), document.baseURI);
      if (!['http:', 'https:', 'file:'].includes(url.protocol)) return null;
      return String(value).split('#')[0] + (Number.isInteger(page) ? '#page=' + (page + 1) : '');
    } catch { return null; }
  };
  const externalHref = value => {
    try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) ? url.href : null; }
    catch { return null; }
  };
  const link = (label, href, className) => {
    if (!href) return element('span', label + ' (source unavailable)', className);
    const node = element('a', label, className);
    node.href = href; node.target = '_blank'; node.rel = 'noopener noreferrer';
    return node;
  };
  // A presentation layer only: original department names stay on each offer.
  const aisles = [
    {id: 'produce', name: 'Fruit & veg', description: 'Fresh picks for the week', categories: ['Produce'], icon: 'carrot'},
    {id: 'protein', name: 'Meat & seafood', description: 'Build a meal around these', categories: ['Meat', 'Seafood'], icon: 'fish'},
    {id: 'dairy', name: 'Dairy, cheese & frozen', description: 'Fridge and freezer favorites', categories: ['Dairy & Frozen Foods', 'Cheese Shoppe'], icon: 'cheese'},
    {id: 'bakery', name: 'From the bakery', description: 'Something warm. Something sweet.', categories: ['Bakery'], icon: 'bread'},
    {id: 'pantry', name: 'Pantry & drinks', description: 'Stock up on everyday favorites', categories: ['Grocery'], icon: 'jar'},
    {id: 'ready', name: 'Deli & ready to eat', description: 'Good food, a little less prep', categories: ['Delicatessen', 'Prepared Foods', 'Sushi', 'Café'], icon: 'bowl'},
    {id: 'wine', name: 'Beer & wine', description: 'Check the flyer for store availability', categories: ['Beer & Wine'], icon: 'bottle'},
    {id: 'home', name: 'Home, pets & flowers', description: 'For the rest of your basket', categories: ['Household & Pet', 'Floral'], icon: 'flower'},
    {id: 'more', name: 'More from the flyer', description: 'Offers still needing a category', categories: [], icon: 'bag'},
  ];
  const aisleFor = offer => aisles.find(a => a.categories.includes(category(offer))) || aisles.at(-1);
  const share = (count, total) => { const n = count / (total || 1) * 100; return n > 0 && n < 1 ? '<1%' : Math.round(n) + '%'; };
  const offerLabel = offer => rawPrice(offer.price) + (offer.unit ? '/' + offer.unit : '');
  const iconPaths = {
    carrot: ['M29 25C10 20 9 32 11 43L19 65Q22 71 27 64L44 44C54 32 43 22 29 25Z', 'M34 24Q28 6 38 6Q44 7 40 23M42 27Q60 10 62 20Q63 26 46 31M18 36L28 40M23 51L31 53'],
    fish: ['M12 39Q30 12 54 35L68 25L65 42L68 57L54 48Q30 70 12 39Z', 'M39 26Q50 40 40 55M25 37L25 38M31 25L39 17L43 26M29 55L37 63L41 55'],
    cheese: ['M10 39L43 14Q62 20 67 38L10 39V64L67 58V38', 'M10 39L43 14M22 48A4 4 0 1 0 23 48M43 45A3 3 0 1 0 44 45M54 51A3 3 0 1 0 55 51M37 31L46 28'],
    bread: ['M12 40Q8 29 18 25Q20 13 33 18Q44 10 52 21Q66 19 67 34L62 57Q39 68 16 57Z', 'M27 27L23 39M42 24L36 39M55 29L49 41M17 53Q40 62 62 50'],
    jar: ['M25 10H55V20H25ZM29 20V26Q20 28 20 38V62Q20 67 27 67H53Q61 67 61 60V37Q60 28 51 26V20', 'M21 39H60V56H21M35 42Q44 42 47 48Q44 55 35 53ZM39 44L42 39'],
    bowl: ['M10 38H68Q63 63 39 65Q17 63 10 38ZM23 66H55', 'M20 31Q13 22 27 18M37 31Q30 21 43 12M55 30Q49 21 60 17'],
    bottle: ['M31 8H46V25L55 38V65H23V38L31 25ZM31 18H46M24 44H54V58H24', 'M39 47V54M35 50H43M58 11L68 20M61 25H70'],
    flower: ['M38 45V70M38 60Q18 63 19 48Q33 46 38 60M39 63Q62 64 61 49Q48 48 39 63', 'M30 30Q12 29 17 17Q22 8 32 19Q32 2 43 8Q50 12 46 23Q63 12 65 26Q64 36 50 33Q62 47 48 49Q38 48 39 37Q31 53 24 43Q20 35 30 30Z', 'M38 24A7 7 0 1 0 39 24'],
    bag: ['M17 27H62L66 67H12ZM28 29V21Q28 6 40 9Q52 9 52 22V29', 'M27 47L34 54L51 38'],
  };
  function illustration(kind) {
    const svg = svgNode('svg', {viewBox: '0 0 80 80', 'aria-hidden': 'true', class: 'aisle-art'});
    (iconPaths[kind] || iconPaths.bag).forEach((d, i) => svg.append(svgNode('path', {d, fill: i === 0 ? 'currentColor' : 'none', 'fill-opacity': '.12', stroke: 'currentColor', 'stroke-width': '2.5', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'})));
    return svg;
  }
  function filteredOffers() {
    const query = $('search').value.trim().toLocaleLowerCase();
    const review = $('review-filter').value;
    return (state.week?.offers || []).filter(offer =>
      (!query || [offer.item, offer.details, category(offer), ...offer.package_sizes || [], ...pricedOptions(offer).map(p => p.label)].filter(Boolean).join(' ').toLocaleLowerCase().includes(query)) &&
      (review === 'all' || flagged(offer) === (review === 'review')));
  }
  // Prefer clear examples and show distinct departments within a broad aisle.
  // This does not rank savings or imply that an example is the cheapest offer.
  function examples(offers) {
    const rank = offer => Number(flagged(offer)) * 2 + Number(pricedOptions(offer).length > 1);
    const sorted = [...offers].sort((a, b) => rank(a) - rank(b));
    const first = sorted[0];
    const second = sorted.find(o => o !== first && category(o) !== category(first)) || sorted[1];
    return [first, second].filter(Boolean);
  }
  function showView(view, updateLocation = false) {
    if (!['offers', 'history', 'seasonal'].includes(view)) view = 'offers';
    state.view = view;
    document.querySelectorAll('[data-view-panel]').forEach(panel => { panel.hidden = panel.dataset.viewPanel !== view; });
    document.querySelectorAll('[data-view]').forEach(button => {
      const selected = button.dataset.view === view;
      button.setAttribute('aria-selected', String(selected));
      button.tabIndex = selected ? 0 : -1;
    });
    if (updateLocation && location.hash !== '#' + view) history.pushState({view}, '', '#' + view);
  }
  function renderWeekStatus(week) {
    const parts = new Intl.DateTimeFormat('en-US', {timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit'}).formatToParts(new Date());
    const part = type => parts.find(p => p.type === type)?.value;
    const today = `${part('year')}-${part('month')}-${part('day')}`;
    const kind = !week ? 'empty' : week.end_date < today ? 'past' : week.start_date > today ? 'future' : 'current';
    setText('week-status', {empty: 'No flyer yet', past: 'Past flyer', future: 'Upcoming flyer', current: 'Current week'}[kind]);
    $('week-status').className = 'week-status ' + kind;
    $('week-status').title = 'Based on the printed sale dates in New York time. This is a saved flyer snapshot.';
  }
  function renderWeek() {
    const week = state.week;
    const offers = week?.offers || [];
    setText('hero-date', week ? weekLabel(week) : 'No captured flyers yet');
    setText('week-message', 'A dated snapshot. Confirm availability, sizes and purchase conditions in the original flyer.');
    const href = sourceHref(week);
    $('flyer-link').hidden = !href;
    if (href) $('flyer-link').href = href;
    setText('offer-count', offers.length.toLocaleString());
    setText('category-count', aisles.filter(a => offers.some(o => aisleFor(o).id === a.id)).length);
    setText('week-count', weeks.length);
    renderWeekStatus(week);
    setText('review-count', offers.filter(flagged).length);
    const sourceIssues = week?.source?.issues || [];
    $('source-issues').hidden = !sourceIssues.length;
    setText('source-issues', sourceIssues.length ? 'Flyer coverage note: ' + sourceIssues.join(' ') : '');
    // A known omission stays visible without expanding the methodology.
    const summary = document.querySelector('.coverage-note summary');
    summary.setAttribute('aria-label', `About these offers. ${offers.filter(flagged).length} flagged for review.${sourceIssues.length ? ' Known flyer coverage limitations.' : ''}`);
    summary.classList.toggle('has-issues', sourceIssues.length > 0);
    document.querySelector('.coverage-note').open = sourceIssues.length > 0;
    renderOffers(); renderSeasonality();
  }
  function selectAisle(id) {
    state.aisle = id;
    renderOffers();
    $('all-aisles').focus({preventScroll: true});
    $('browser-title').scrollIntoView({block: 'nearest'});
  }
  function renderOffers() {
    const all = state.week?.offers || [];
    const matches = filteredOffers();
    const query = $('search').value.trim();
    const browsing = !state.aisle && !query && $('review-filter').value === 'all';
    const current = aisles.find(a => a.id === state.aisle);
    $('search').placeholder = current ? `Search ${current.name.toLowerCase()}…` : 'Search apples, coffee, chicken…';
    $('search').setAttribute('aria-label', current ? `Find an item in ${current.name}` : 'Find an item');
    const offers = current ? matches.filter(o => aisleFor(o).id === current.id) : matches;
    $('category-board').hidden = !browsing;
    $('offer-grid').hidden = browsing;
    $('all-aisles').hidden = browsing;
    $('reset-filters').hidden = browsing;
    $('aisle-shortcuts').hidden = browsing;
    setText('browser-title', browsing ? 'Pick a category. Get inspired.' : current?.name || (query ? 'Found in the flyer' : $('review-filter').value === 'clear' ? 'Offers without extraction flags' : 'Offers to review'));
    setText('result-count', browsing ? 'The whole flyer, at a glance' : `${offers.length} ${offers.length === 1 ? 'offer' : 'offers'}${query ? ` matching “${query}”` : ''}`);
    setText('browser-note', browsing ? 'A few examples in each category. Open one to explore every offer.' : 'Every matching offer is shown. Select a card for sizes, price options and its source PDF.');
    clear('aisle-mix'); clear('category-board'); clear('offer-grid'); clear('aisle-shortcuts');
    aisles.forEach(aisle => {
      const members = all.filter(o => aisleFor(o).id === aisle.id);
      if (!members.length) return;
      const segment = element('button', null, `mix-segment theme-${aisle.id}`);
      segment.type = 'button'; segment.style.flexGrow = members.length;
      segment.title = `${aisle.name}: ${members.length} offers · ${share(members.length, all.length)} of flyer`;
      segment.setAttribute('aria-label', segment.title); segment.addEventListener('click', () => selectAisle(aisle.id)); $('aisle-mix').append(segment);
      const shortcut = element('button', aisle.name, `aisle-chip theme-${aisle.id}`);
      shortcut.type = 'button'; shortcut.setAttribute('aria-pressed', String(state.aisle === aisle.id));
      shortcut.addEventListener('click', () => selectAisle(aisle.id)); $('aisle-shortcuts').append(shortcut);
      if (!browsing) return;
      const tile = element('button', null, `category-tile theme-${aisle.id}`);
      tile.type = 'button'; tile.dataset.aisle = aisle.id;
      tile.setAttribute('aria-label', `${aisle.name}, ${members.length} offers. Explore category.`);
      const heading = element('span', null, 'tile-top');
      heading.append(element('span', `${members.length} offers`, 'tile-count'), element('span', `${share(members.length, all.length)} of flyer`, 'tile-share'));
      const title = element('span', null, 'tile-title'); title.append(element('span', aisle.name), illustration(aisle.icon));
      const preview = element('span', null, 'tile-examples');
      examples(members).forEach(o => {
        const example = element('span', null, 'tile-example');
        const display = offerLabel(o) + (pricedOptions(o).length > 1 ? ' + options' : '');
        example.append(element('span', o.item, 'preview-name'), element('strong', display, 'preview-price'));
        example.title = `${o.item} · ${display}`;
        preview.append(example);
      });
      const foot = element('span', null, 'tile-foot'); foot.append(element('span', aisle.description), element('span', '↗', 'tile-arrow'));
      tile.append(heading, title, preview, foot); tile.addEventListener('click', () => selectAisle(aisle.id)); $('category-board').append(tile);
    });
    if (browsing && !all.length) $('category-board').append(element('p', 'Your first flyer will bring these categories to life.', 'empty-state'));
    if (browsing) return;
    offers.forEach(offer => {
      const aisle = aisleFor(offer);
      const card = element('button', null, `deal-card theme-${aisle.id}`);
      card.type = 'button'; card.dataset.offerId = offer.id;
      card.setAttribute('aria-label', `${offer.item || 'Unnamed offer'}, ${offerLabel(offer)}. View details and source.`);
      const top = element('span', null, 'deal-top'); top.append(element('span', category(offer), 'deal-category'));
      if (flagged(offer)) top.append(element('span', 'Check flyer', 'tag review'));
      card.append(top, element('span', offer.item || 'Unnamed offer', 'deal-name'));
      const details = offer.details || (offer.package_sizes || []).join(' · ');
      if (details) card.append(element('span', details, 'deal-description'));
      const variants = pricedOptions(offer);
      if (variants.length > 1) card.append(element('span', `${variants.length} price options`, 'tag'));
      const price = element('span', null, 'deal-bottom');
      const amount = element('span', offer.price ? rawPrice(offer.price) : 'See options', 'deal-price');
      if (offer.unit) amount.append(element('span', '/' + offer.unit, 'price-unit'));
      price.append(amount, element('span', '↗'));
      card.append(price);
      if (offer.savings) card.append(element('span', offer.savings, 'deal-saving'));
      card.addEventListener('click', () => openOffer(offer, state.week)); $('offer-grid').append(card);
    });
    if (!offers.length) $('offer-grid').append(element('p', current ? 'No matching offers in this category. Try another category or reset your search.' : 'No matching offers in this flyer. Try another item name or reset your search.', 'empty-state'));
  }

  function openOffer(offer, week) {
    setText('dialog-title', offer.item || 'Unnamed offer');
    clear('dialog-content');
    const body = $('dialog-content');
    const price = element('div', rawPrice(offer.price) + (offer.unit ? ' / ' + offer.unit : ''), 'dialog-prices');
    pricedOptions(offer).forEach(p => {
      if (pricedOptions(offer).length > 1 || p.label) price.append(element('div', [p.label, rawPrice(p.price), p.unit ? '/ ' + p.unit : ''].filter(Boolean).join(' · '), 'dialog-price-option'));
    });
    body.append(price);
    if (offer.details) body.append(element('p', 'Offer details', 'detail-label'), element('p', offer.details, 'dialog-copy'));
    if ((offer.package_sizes || []).length) body.append(element('p', 'Printed sizes', 'detail-label'), element('p', offer.package_sizes.join(' · '), 'dialog-copy'));
    if (offer.savings) body.append(element('p', 'Printed savings', 'detail-label'), element('p', offer.savings, 'dialog-copy'));
    if (offer.quantity > 1) body.append(element('p', `The advertised offer is ${offer.quantity} for ${money(offer.amount)} (${money(offer.unit_price)} per advertised unit). This calculation does not establish single-item purchase eligibility.`, 'small'));
    body.append(element('p', 'Source & review', 'detail-label'));
    body.append(element('p', `${weekLabel(week)} · Flyer page ${Number.isInteger(offer.page) ? offer.page + 1 : 'unknown'} · ${category(offer)}`, 'dialog-copy'));
    if (week.source?.issues?.length) body.append(element('p', 'Flyer coverage: ' + week.source.issues.join(' '), 'small'));
    if (offer.category_source) body.append(element('p', 'Category basis: ' + offer.category_source, 'small'));
    const issues = offer._issues || [];
    if (issues.length) {
      const list = element('ul', null, 'detail-list');
      issues.forEach(issue => list.append(element('li', prettyIssue(issue)))); body.append(list);
    } else body.append(element('p', 'No automated extraction flags. This is not a manual verification of the offer.', 'small'));
    body.append(element('p', offer.history_eligible ? 'Included in comparable-price history.' : `Excluded from comparable-price history: ${offer.history_reason || 'identity, package or price terms are not sufficiently clear'}.`, 'small'));
    body.append(link('Open this page in the original PDF ↗', sourceHref(week, offer.page), 'provenance-link'));
    if (offer._bbox) body.append(element('p', 'PDF coordinates (points): ' + offer._bbox.map(n => Number(n).toFixed(1)).join(', '), 'small'));
    const pdfHash = week.source?.pdf?.sha256 || week.source?.sha256 || week.source?.pdf_sha256;
    if (pdfHash) body.append(element('p', 'PDF SHA-256: ' + pdfHash, 'source-text'));
    if (offer._source_text) {
      const details = element('details', null, 'sources'); details.append(element('summary', 'Inspect extracted source text'), element('pre', offer._source_text, 'source-text')); body.append(details);
    }
    $('offer-dialog').showModal();
  }

  function svgNode(tag, attrs = {}, text) {
    const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function renderHistoryCategories() {
    setText('history-scope', `Across all ${weeks.length} saved ${weeks.length === 1 ? 'week' : 'weeks'}`);
    const groups = [{id: null, name: 'All categories', icon: 'bag'}, ...aisles];
    groups.forEach(aisle => {
      const count = series.filter(entry => !aisle.id || aisleFor(entry).id === aisle.id).length;
      const button = element('button', null, `history-category theme-${aisle.id || 'all'}`);
      button.type = 'button';
      button.dataset.historyAisle = aisle.id || '';
      button.setAttribute('aria-controls', 'product-select');
      button.setAttribute('aria-pressed', String(state.historyAisle === aisle.id));
      button.disabled = Boolean(aisle.id && !count);
      const label = element('span', null, 'history-category-label');
      label.append(element('strong', aisle.name), element('small', `${count} tracked ${count === 1 ? 'product' : 'products'}`));
      button.append(illustration(aisle.icon), label);
      button.addEventListener('click', () => {
        state.historyAisle = aisle.id;
        renderProductOptions();
      });
      $('history-categories').append(button);
    });
  }

  function renderProductOptions() {
    const query = $('history-search').value.trim().toLocaleLowerCase();
    const previous = $('product-select').value;
    const aisle = aisles.find(a => a.id === state.historyAisle);
    const inCategory = series.filter(entry => !aisle || aisleFor(entry).id === aisle.id);
    const filtered = inCategory.filter(entry => !query || [entry.item, entry.package_label, entry.unit, category(entry)].filter(Boolean).join(' ').toLocaleLowerCase().includes(query));
    document.querySelectorAll('[data-history-aisle]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.historyAisle === (state.historyAisle || ''))));
    setText('history-search-label', aisle ? `Find a product in ${aisle.name}` : 'Find a product in your price history');
    $('history-search').placeholder = aisle ? `Search ${aisle.name.toLocaleLowerCase()}…` : 'Search a product name or package size…';
    setText('history-result-count', `${filtered.length}${query ? ' of ' + inCategory.length : ''} tracked ${(query ? inCategory.length : filtered.length) === 1 ? 'product' : 'products'} · ${aisle?.name || 'All categories'}`);
    $('reset-history').hidden = !query && !aisle;
    $('product-select').replaceChildren();
    filtered.forEach(entry => $('product-select').append(option(entry.product_key, `${entry.item} · ${entry.package_label || entry.unit || 'advertised unit'} · ${new Set(entry.observations.map(o => o.week_id)).size} wk`)));
    if (filtered.some(entry => entry.product_key === previous)) $('product-select').value = previous;
    if (!filtered.length) $('product-select').append(option('', query || aisle ? 'No matching products' : 'No comparable product observations'));
    $('product-select').disabled = !filtered.length;
    renderHistory();
  }

  function renderHistory() {
    const entry = series.find(item => item.product_key === $('product-select').value);
    clear('price-chart'); clear('history-table');
    const aisle = entry ? aisleFor(entry) : aisles.find(a => a.id === state.historyAisle);
    $('history-chart-card').className = `history-chart-card theme-${aisle?.id || 'all'}`;
    setText('history-department', entry ? category(entry) : '');
    $('history-department').hidden = !entry;
    if (!entry) {
      const filtering = $('history-search').value.trim() || state.historyAisle;
      setText('history-product', filtering ? 'No matching product' : 'Your first comparison is ahead'); setText('history-package', 'Only sufficiently clear product observations can be compared.'); setText('history-price', '—'); setText('history-note', filtering ? 'Try another name, choose another category, or clear the history filters.' : 'Capture more flyers to build a useful price record.');
      $('price-chart').append(element('p', filtering ? 'No recorded product matches these filters.' : 'Comparable advertised prices will appear here as dated flyers are added.', 'empty-state')); return;
    }
    const observations = [...entry.observations].filter(o => o.unit_price !== null && o.unit_price !== undefined && Number.isFinite(Number(o.unit_price))).sort((a, b) => String(a.start_date).localeCompare(String(b.start_date)));
    setText('history-product', entry.item);
    setText('history-package', [entry.package_label, entry.unit ? 'Per ' + entry.unit : 'Per advertised unit', entry.quantity > 1 ? `${entry.quantity}-item offer` : ''].filter(Boolean).join(' · '));
    setText('history-price', observations.length ? money(observations.at(-1).unit_price) : '—');
    const distinctWeeks = new Set(observations.map(o => o.week_id));
    setText('history-note', distinctWeeks.size < 2 ? 'One captured week. There is not enough history to establish a price change or seasonal pattern.' : `${distinctWeeks.size} captured weeks. Dots are actual advertised observations; gaps are unobserved. The derived per-unit amount does not establish single-item purchase eligibility.`);
    if (observations.length) drawPriceChart(observations, entry);
    observations.forEach(o => {
      const row = element('tr');
      row.append(element('td', date(o.start_date)), element('td', rawPrice(o.price || o.amount)), element('td', money(o.unit_price)));
      const cell = element('td'); const week = weeks.find(w => w.id === o.week_id);
      cell.append(link(Number.isInteger(o.page) ? 'PDF p. ' + (o.page + 1) : 'PDF', sourceHref(week, o.page))); row.append(cell); $('history-table').append(row);
    });
  }

  function drawPriceChart(observations, entry) {
    const width = 640, height = 235, left = 54, right = 22, top = 22, bottom = 47;
    const values = observations.map(o => Number(o.unit_price));
    const low = Math.min(...values), high = Math.max(...values), pad = Math.max((high - low) * .35, high * .08, .15);
    const minY = Math.max(0, low - pad), maxY = high + pad;
    const times = observations.map(o => new Date(String(o.start_date).slice(0, 10) + 'T12:00:00').getTime());
    const minX = Math.min(...times), maxX = Math.max(...times);
    const x = time => minX === maxX ? (width + left - right) / 2 : left + (time - minX) / (maxX - minX) * (width - left - right);
    const y = value => top + (maxY - value) / (maxY - minY) * (height - top - bottom);
    const svg = svgNode('svg', {viewBox: `0 0 ${width} ${height}`, role: 'img', 'aria-label': `${entry.item}: ${observations.length} captured advertised price observations. The exact values are available in the observations table.`});
    svg.append(svgNode('title', {}, `${entry.item} advertised price history`));
    for (let i = 0; i < 4; i++) {
      const value = minY + (maxY - minY) * i / 3;
      svg.append(svgNode('line', {x1: left, x2: width - right, y1: y(value), y2: y(value), stroke: '#e2e5d8', 'stroke-dasharray': '3 5'}));
      svg.append(svgNode('text', {x: left - 10, y: y(value) + 4, 'text-anchor': 'end', fill: '#687361', 'font-size': 11, 'font-family': 'Arial, sans-serif'}, money(value)));
    }
    // Unconnected dots avoid implying observations in the missing weeks.
    observations.forEach((o, index) => {
      const point = svgNode('circle', {cx: x(times[index]), cy: y(Number(o.unit_price)), r: 6, fill: 'var(--accent)', stroke: '#fffef9', 'stroke-width': 2});
      point.append(svgNode('title', {}, `${date(o.start_date)}: ${money(o.unit_price)} per advertised unit`)); svg.append(point);
    });
    const labelIndices = [...new Set([0, Math.floor((observations.length - 1) / 2), observations.length - 1])];
    labelIndices.forEach(index => {
      const when = new Date(times[index]).toLocaleDateString('en-US', {month: 'short', day: 'numeric'});
      svg.append(svgNode('text', {x: x(times[index]), y: height - 19, 'text-anchor': index === 0 && minX !== maxX ? 'start' : index === observations.length - 1 && minX !== maxX ? 'end' : 'middle', fill: '#687361', 'font-size': 11, 'font-family': 'Arial, sans-serif'}, when));
    });
    $('price-chart').append(svg);
  }

  function renderCoverage() {
    const years = [...new Set(weeks.map(w => String(w.start_date).slice(0, 4)))].sort();
    const recordedMonths = new Set(weeks.map(w => String(w.start_date).slice(0, 7)));
    setText('coverage-note', `${weeks.length} captured ${weeks.length === 1 ? 'week' : 'weeks'} across ${recordedMonths.size} ${recordedMonths.size === 1 ? 'month' : 'months'}. ${recordedMonths.size < 12 ? 'Annual deal seasonality is not established by this archive.' : 'Coverage is growing; individual products may still have sparse observations.'}`);
    clear('month-coverage');
    years.forEach(year => {
      $('month-coverage').append(element('div', year, 'coverage-year'));
      months.forEach((month, index) => {
        const key = `${year}-${String(index + 1).padStart(2, '0')}`;
        const count = weeks.filter(w => String(w.start_date).startsWith(key)).length;
        const cell = element('div', month, 'coverage-month' + (count ? ' recorded' : ''));
        cell.append(element('strong', count || '—')); cell.title = count ? `${month} ${year}: ${count} captured weeks` : `${month} ${year}: no observations`; $('month-coverage').append(cell);
      });
    });
    const allCategories = [...new Set(weeks.flatMap(w => (w.offers || []).map(category)))].sort();
    $('trend-category').replaceChildren(option('', 'All advertised offers'));
    allCategories.forEach(name => $('trend-category').append(option(name, name)));
    renderTrend();
  }

  function renderTrend() {
    clear('category-trend');
    const selected = $('trend-category').value;
    const monthKeys = [...new Set(weeks.map(w => String(w.start_date).slice(0, 7)))].sort();
    const observations = monthKeys.map(key => {
      const captured = weeks.filter(w => String(w.start_date).startsWith(key));
      const count = captured.reduce((sum, week) => sum + (week.offers || []).filter(o => !selected || category(o) === selected).length, 0);
      return {key, value: count / captured.length, weeks: captured.length};
    });
    const max = Math.max(1, ...observations.map(o => o.value));
    observations.forEach(o => {
      const row = element('div', null, 'trend-row');
      row.append(element('span', months[Number(o.key.slice(5)) - 1] + ' ' + o.key.slice(0, 4)));
      const track = element('span', null, 'bar-track'); const fill = element('span', null, 'bar-fill'); fill.style.width = `${o.value / max * 100}%`; track.append(fill);
      row.append(track, element('span', o.value.toFixed(1))); row.title = `${o.value.toFixed(1)} offers per week across ${o.weeks} captured weeks`; $('category-trend').append(row);
    });
  }

  function renderSeasonality() {
    const seasonality = data.seasonality || {};
    const region = $('season-region').value;
    const selectedMonth = Number(String(state.week?.start_date || '').slice(5, 7));
    const useLocal = region === 'new_england';
    setText('season-note', seasonality.note || 'Typical U.S. produce seasons offer shopping context. Actual availability varies by growing region, weather, storage and imports. These windows are not a prediction of Market Basket discounts.');
    setText('regional-note', useLocal ? 'New England notes describe typical regional harvest windows where a cited local source is available. An empty regional row means no local window was supplied; it does not mean the item is unavailable.' : 'U.S. overview with New England notes. National seasonal availability and local harvest timing differ; select New England above for the regional view.');
    setText('season-caption', `${useLocal ? 'New England harvest notes' : 'U.S. typical seasonal availability'}; these are seasonal context, not observed deal predictions.`);
    clear('season-head'); clear('season-body');
    const header = element('tr'); header.append(element('th', 'FROM THE PRODUCE AISLE')); header.firstChild.scope = 'col';
    months.forEach((month, index) => { const th = element('th', month, index + 1 === selectedMonth ? 'current' : ''); th.scope = 'col'; header.append(th); }); $('season-head').append(header);
    (seasonality.items || []).forEach(item => {
      const row = element('tr'); const title = element('th', item.name); title.scope = 'row';
      const seasonMonths = useLocal ? item.new_england_months || [] : item.months || [];
      if (useLocal && !seasonMonths.length) title.append(element('small', 'Local window not supplied'));
      if (item.note) title.title = item.note;
      row.append(title);
      months.forEach((month, index) => {
        const active = seasonMonths.includes(index + 1); const current = index + 1 === selectedMonth;
        const cell = element('td', null, (active ? 'active ' : '') + (current ? 'current' : ''));
        cell.append(element('span', active ? null : '·', active ? 'season-pill' : 'no-season'));
        cell.append(element('span', `${month}: ${active ? 'typical seasonal window' : 'not included in this guide’s window'}`, 'sr-only'));
        if (item.note) cell.title = item.note;
        row.append(cell);
      });
      $('season-body').append(row);
    });
    clear('season-sources');
    (seasonality.sources || []).forEach(source => {
      const li = element('li'); li.append(link(source.title || 'Source', externalHref(source.url)));
      if (source.note) li.append(document.createTextNode(' — ' + source.note)); $('season-sources').append(li);
    });
    setText('source-note', 'This calendar is a sourced seasonal guide, not a national grocery pricing standard. Reference seasons and harvest windows are separate from observed flyer history. No annual discount pattern is inferred from a few captured weeks.');
  }

  weeks.forEach(week => $('week-select').append(option(week.id, weekLabel(week))));
  if (!weeks.length) { $('week-select').append(option('', 'No captured flyers')); $('week-select').disabled = true; }
  $('week-select').addEventListener('change', () => { state.week = weeks.find(w => w.id === $('week-select').value); renderWeek(); });
  ['search', 'review-filter'].forEach(id => $(id).addEventListener(id === 'search' ? 'input' : 'change', renderOffers));
  function resetBrowser() { state.aisle = null; $('search').value = ''; $('review-filter').value = 'all'; renderOffers(); }
  $('reset-filters').addEventListener('click', resetBrowser);
  $('all-aisles').addEventListener('click', () => { const old = state.aisle; resetBrowser(); $('offers').scrollIntoView({block: 'start'}); const tile = document.querySelector(`[data-aisle="${old}"]`); if (tile) tile.focus({preventScroll: true}); });
  const viewTabs = [...document.querySelectorAll('[data-view]')];
  viewTabs.forEach((button, index) => {
    button.addEventListener('click', () => showView(button.dataset.view, true));
    button.addEventListener('keydown', event => {
      const next = {ArrowRight: (index + 1) % viewTabs.length, ArrowLeft: (index + viewTabs.length - 1) % viewTabs.length, Home: 0, End: viewTabs.length - 1}[event.key];
      if (next === undefined) return;
      event.preventDefault(); viewTabs[next].focus(); showView(viewTabs[next].dataset.view, true);
    });
  });
  const restoreView = () => showView(location.hash.slice(1) || 'offers');
  window.addEventListener('popstate', restoreView);
  window.addEventListener('hashchange', restoreView);
  document.querySelector('.brand').addEventListener('click', () => showView('offers'));
  document.querySelector('.skip-link').addEventListener('click', () => showView('offers'));
  $('history-search').addEventListener('input', renderProductOptions);
  $('reset-history').addEventListener('click', () => {
    state.historyAisle = null; $('history-search').value = ''; renderProductOptions(); $('history-search').focus();
  });
  $('product-select').addEventListener('change', renderHistory);
  $('trend-category').addEventListener('change', renderTrend);
  $('season-region').addEventListener('change', renderSeasonality);
  $('close-dialog').addEventListener('click', () => $('offer-dialog').close());
  $('offer-dialog').addEventListener('click', event => { if (event.target === $('offer-dialog')) { const r = $('offer-dialog').getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) $('offer-dialog').close(); } });
  setText('generated-at', data.generated_at ? `Report generated ${date(data.generated_at)}. All charts use the archive embedded in this file.` : 'All charts use the archive embedded in this file.');
  (data.notes || []).forEach(note => $('report-notes').append(element('li', note)));
  renderWeek(); renderHistoryCategories(); renderProductOptions(); renderCoverage(); restoreView();
})();
