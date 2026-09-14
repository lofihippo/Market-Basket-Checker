(() => {
  'use strict';
  const data = JSON.parse(document.getElementById('dashboard-data').textContent);
  const $ = id => document.getElementById(id);
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const weeks = [...(data.weeks || [])].sort((a, b) => String(b.start_date).localeCompare(String(a.start_date)));
  const series = [...(data.series || [])].sort((a, b) => new Set(b.observations.map(o => o.week_id)).size - new Set(a.observations.map(o => o.week_id)).size || String(a.item).localeCompare(String(b.item)));
  const state = {week: weeks[0], page: 0};
  const pageSize = 24;
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
  const countsFor = offers => {
    const counts = new Map();
    offers.forEach(offer => counts.set(category(offer), (counts.get(category(offer)) || 0) + 1));
    return [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  };

  function renderWeek() {
    const week = state.week;
    const offers = week?.offers || [];
    setText('hero-date', week ? weekLabel(week) : 'No captured flyers yet');
    setText('week-message', week ? 'A dated snapshot of the published flyer. Browse the original to verify availability, sizes and purchase conditions.' : 'Capture a weekly flyer to begin your archive.');
    const href = sourceHref(week);
    $('flyer-link').hidden = !href;
    if (href) $('flyer-link').href = href;
    setText('offer-count', offers.length.toLocaleString());
    const counts = countsFor(offers);
    setText('category-count', counts.length);
    setText('week-count', weeks.length);
    setText('review-count', offers.filter(flagged).length);
    const sourceIssues = week?.source?.issues || [];
    $('source-issues').hidden = !sourceIssues.length;
    setText('source-issues', sourceIssues.length ? 'Flyer coverage note: ' + sourceIssues.join(' ') : '');
    clear('category-bars');
    counts.forEach(([name, count]) => {
      const button = element('button', null, 'category-bar');
      button.type = 'button';
      button.setAttribute('aria-label', `${name}: ${count} offers, ${Math.round(count / (offers.length || 1) * 100)} percent of advertised offer groups. Filter offers.`);
      button.append(element('span', name));
      const track = element('span', null, 'bar-track');
      const fill = element('span', null, 'bar-fill');
      fill.style.width = `${count / (counts[0]?.[1] || 1) * 100}%`;
      track.append(fill); button.append(track, element('span', `${count} · ${Math.round(count / (offers.length || 1) * 100)}%`));
      button.addEventListener('click', () => {
        $('category-filter').value = name; state.page = 0; renderOffers(); $('offers').scrollIntoView({behavior: 'smooth'}); $('category-filter').focus({preventScroll: true});
      });
      $('category-bars').append(button);
    });
    if (!counts.length) $('category-bars').append(element('p', 'Category coverage will appear after the first flyer is captured.', 'empty-state'));
    const previousCategory = $('category-filter').value;
    $('category-filter').replaceChildren(option('', 'All categories'));
    counts.map(([name]) => name).sort().forEach(name => $('category-filter').append(option(name, name)));
    if (counts.some(([name]) => name === previousCategory)) $('category-filter').value = previousCategory;
    renderOffers(); renderSeasonality();
  }

  function renderOffers() {
    const query = $('search').value.trim().toLocaleLowerCase();
    const selectedCategory = $('category-filter').value;
    const reviewFilter = $('review-filter').value;
    const offers = (state.week?.offers || []).filter(offer => {
      return (!selectedCategory || category(offer) === selectedCategory) &&
        (!query || [offer.item, offer.details, ...(offer.package_sizes || []), ...pricedOptions(offer).map(p => p.label)].filter(Boolean).join(' ').toLocaleLowerCase().includes(query)) &&
        (reviewFilter === 'all' || flagged(offer) === (reviewFilter === 'review'));
    });
    const pageCount = Math.max(1, Math.ceil(offers.length / pageSize));
    state.page = Math.min(state.page, pageCount - 1);
    const first = state.page * pageSize;
    setText('result-count', offers.length ? `${first + 1}–${Math.min(first + pageSize, offers.length)} of ${offers.length} offers` : 'No matching offers');
    clear('offer-list');
    offers.slice(first, first + pageSize).forEach(offer => {
      const row = element('button', null, 'offer-row');
      row.type = 'button'; row.setAttribute('aria-label', `${offer.item || 'Unnamed offer'}, ${rawPrice(offer.price)}. View details and source.`);
      row.append(element('span', category(offer).split(/\s+/).map(x => x[0]).slice(0, 2).join(''), 'category-icon'));
      const description = element('span');
      description.append(element('span', offer.item || 'Unnamed offer', 'offer-name'));
      const detail = offer.details || (offer.package_sizes || []).join(' · ');
      if (detail) description.append(element('span', String(detail).length > 130 ? String(detail).slice(0, 127) + '…' : detail, 'offer-subtitle'));
      const meta = element('span', null, 'offer-meta');
      meta.append(element('span', category(offer), 'tag'));
      if (flagged(offer)) meta.append(element('span', 'Check flyer', 'tag review'));
      const variants = pricedOptions(offer);
      if (variants.length > 1) meta.append(element('span', `${variants.length} price options`, 'tag'));
      description.append(meta); row.append(description);
      const priceBlock = element('span', null, 'price-block');
      const priceNode = element('span', offer.price ? rawPrice(offer.price) : 'See options', 'offer-price' + (String(offer.price || '').includes('for') || !offer.price ? ' multi' : ''));
      if (offer.unit) priceNode.append(element('span', '/' + offer.unit, 'price-unit'));
      priceBlock.append(priceNode);
      if (offer.savings) priceBlock.append(element('span', offer.savings, 'offer-saving'));
      row.append(priceBlock, element('span', '↗', 'row-arrow'));
      row.addEventListener('click', () => openOffer(offer, state.week));
      $('offer-list').append(row);
    });
    if (!offers.length) $('offer-list').append(element('p', 'No offers match these filters. Try another search or reset the filters.', 'empty-state'));
    setText('pagination-label', `Page ${state.page + 1} of ${pageCount}`);
    $('previous-page').disabled = state.page === 0;
    $('next-page').disabled = state.page + 1 >= pageCount;
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
    if (week.source?.sha256 || week.source?.pdf_sha256) body.append(element('p', 'PDF SHA-256: ' + (week.source.sha256 || week.source.pdf_sha256), 'source-text'));
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

  function renderHistory() {
    const entry = series.find(item => item.product_key === $('product-select').value);
    clear('price-chart'); clear('history-table');
    if (!entry) {
      setText('history-product', 'Your first comparison is ahead'); setText('history-package', 'No sufficiently clear product observations yet.'); setText('history-price', '—'); setText('history-note', 'Capture more flyers to build a useful price record.');
      $('price-chart').append(element('p', 'Comparable advertised prices will appear here as dated flyers are added.', 'empty-state')); return;
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
      const point = svgNode('circle', {cx: x(times[index]), cy: y(Number(o.unit_price)), r: 6, fill: '#a24b32', stroke: '#fffef9', 'stroke-width': 2});
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
  series.forEach(entry => $('product-select').append(option(entry.product_key, `${entry.item} · ${entry.package_label || entry.unit || 'advertised unit'} · ${new Set(entry.observations.map(o => o.week_id)).size} wk`)));
  if (!series.length) { $('product-select').append(option('', 'No comparable product observations')); $('product-select').disabled = true; }
  $('week-select').addEventListener('change', () => { state.week = weeks.find(w => w.id === $('week-select').value); state.page = 0; renderWeek(); });
  ['search', 'category-filter', 'review-filter'].forEach(id => $(id).addEventListener(id === 'search' ? 'input' : 'change', () => { state.page = 0; renderOffers(); }));
  $('reset-filters').addEventListener('click', () => { $('search').value = ''; $('category-filter').value = ''; $('review-filter').value = 'all'; state.page = 0; renderOffers(); });
  $('previous-page').addEventListener('click', () => { state.page -= 1; renderOffers(); $('offers').scrollIntoView(); });
  $('next-page').addEventListener('click', () => { state.page += 1; renderOffers(); $('offers').scrollIntoView(); });
  $('product-select').addEventListener('change', renderHistory);
  $('trend-category').addEventListener('change', renderTrend);
  $('season-region').addEventListener('change', renderSeasonality);
  $('close-dialog').addEventListener('click', () => $('offer-dialog').close());
  $('offer-dialog').addEventListener('click', event => { if (event.target === $('offer-dialog')) { const r = $('offer-dialog').getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) $('offer-dialog').close(); } });
  setText('generated-at', data.generated_at ? `Report generated ${date(data.generated_at)}. All charts use the archive embedded in this file.` : 'All charts use the archive embedded in this file.');
  (data.notes || []).forEach(note => $('report-notes').append(element('li', note)));
  renderWeek(); renderHistory(); renderCoverage();
})();
