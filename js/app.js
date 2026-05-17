/* ═══════════════════════════════════════════════════════════════════════════
   COMPETITIVE INTELLIGENCE DASHBOARD — app.js
   4-panel layout | vanilla JS | no frameworks
   ═══════════════════════════════════════════════════════════════════════════ */

const app = {

  /* ─── Constants ─────────────────────────────────────────────────────────── */

  COMPETITORS: ['Coinbase','Binance','Bybit','OKX','Crypto.com','Coinhako','Revolut','MooMoo'],
  COUNTRIES:   ['Singapore','Australia'],      // geographic columns
  HMAP_COLS:   ['Singapore','Australia','Global','Total'],

  TYPES: {
    product_launch:   { label: 'Product Launch',   color: '#3B82F6' },
    market_expansion: { label: 'Market Expansion', color: '#A855F7' },
    regulatory:       { label: 'Regulatory',       color: '#F59E0B' },
    partnership:      { label: 'Partnership',       color: '#EC4899' },
    operational:      { label: 'Operational',       color: '#6B7280' },
    other:            { label: 'Other',             color: '#8B8FA8' },
    // industry_context is permanently hidden from UI
  },

  // The 4 strategic types shown by default (the curated view)
  DEFAULT_TYPES: ['product_launch','market_expansion','regulatory','partnership'],

  // All pill options shown in the left filter panel (operational + other are off by default)
  FILTER_TYPES: ['product_launch','market_expansion','regulatory','partnership','operational','other'],

  FLAGS: { Singapore: '🇸🇬', Australia: '🇦🇺' },
  COL_LABELS: { Singapore: '🇸🇬 SG', Australia: '🇦🇺 AU', Global: '🌐 Global', Total: 'Total' },

  PAGE_SIZE: 50,

  /* ─── State ──────────────────────────────────────────────────────────────── */

  data:     null,
  filtered: [],          // current filtered+sorted entries (cached)
  state: {
    signalTypes: ['product_launch','market_expansion','regulatory','partnership'],  // curated default
    competitors: [],     // [] = all 8 competitors
    country:    'all',   // 'all' | 'Singapore' | 'Australia' | 'Global'
    dateRange:  '90d',   // '30d' | '90d' | 'all'
    heatmapSel: null,    // null | { competitor, country }
    page:       1,
  },

  /* ─── Bootstrap ──────────────────────────────────────────────────────────── */

  async init() {
    try {
      const res = await fetch('./published_data/dashboard.json');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      this.data = await res.json();
    } catch (err) {
      document.getElementById('loading-screen').innerHTML =
        `<p style="color:#ef4444;font-size:14px;max-width:300px;text-align:center">
          Unable to load dashboard data.<br><small>${err.message}</small>
        </p>`;
      return;
    }

    this.attachListeners();
    this.renderAll();

    // Fade out loading screen
    const ls = document.getElementById('loading-screen');
    ls.classList.add('fade-out');
    setTimeout(() => ls.remove(), 350);
  },

  renderAll() {
    this.filtered = this.computeFiltered();
    this.renderTop();
    this.renderLeft();
    this.renderMiddle();
    this.renderRight();
    this.renderBottom();
  },

  /* Partial update (after a filter change) */
  update() {
    this.filtered = this.computeFiltered();
    this.state.page = 1;
    this.renderLeft();    // updates active states, reset button
    this.renderMiddle();  // updates selected heatmap cell
    this.renderRight();   // updates feed
  },

  /* ─── TOP PANEL ───────────────────────────────────────────────────────────── */

  renderTop() {
    const genAt = this.data.generated_at
      ? new Date(this.data.generated_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
      : '—';

    document.getElementById('panel-top').innerHTML = `
      <div class="top-inner">
        <div class="top-left-group">
          <span class="top-title">Competitive Intelligence Dashboard</span>
          <span class="top-sub">Crypto exchange signals: SG, AU, Global</span>
        </div>
        <div class="top-right-group">
          <span class="top-meta">Created by <strong>Richard Lesmana</strong></span>
          <span class="top-meta">Updated <strong>${genAt}</strong></span>
          <div class="info-anchor">
            <button class="info-icon-btn" id="info-btn" aria-label="About" aria-expanded="false">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <circle cx="12" cy="12" r="10"/>
                <line x1="12" y1="16" x2="12" y2="12"/>
                <line x1="12" y1="8" x2="12.01" y2="8"/>
              </svg>
            </button>
            <div class="info-tooltip" id="info-tip">
              Tracks competitor signals across 8 crypto exchanges via direct scrapers + multi-source news aggregator. Signals classified via Claude API. Refreshed monthly.
            </div>
          </div>
        </div>
      </div>
    `;
  },

  /* ─── LEFT PANEL (filters) ────────────────────────────────────────────────── */

  renderLeft() {
    const { signalTypes, competitors, country, dateRange } = this.state;

    // Static counts: total entries per signal type (ignores all filters)
    const typeCounts = {};
    this.FILTER_TYPES.forEach(t => { typeCounts[t] = 0; });
    this.data.entries.forEach(e => { if (typeCounts[e.signal_type] !== undefined) typeCounts[e.signal_type]++; });

    // Static counts: total entries per competitor
    const compCounts = {};
    this.COMPETITORS.forEach(c => { compCounts[c] = 0; });
    this.data.entries.forEach(e => e.competitors.forEach(c => { if (compCounts[c] !== undefined) compCounts[c]++; }));

    const hasFilter = this.hasActiveFilters();
    const lastScrape = this.data.generated_at
      ? new Date(this.data.generated_at).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })
      : '—';

    document.getElementById('panel-left').innerHTML = `
      <div class="filter-panel">

        <!-- Signal type pills -->
        <div class="filter-section">
          <div class="filter-label">Signal type</div>
          <div class="type-pills">
            ${this.FILTER_TYPES.map(t => {
              const info   = this.TYPES[t];
              const active = signalTypes.includes(t);
              const r      = this.hexCh(info.color, 0);
              const g      = this.hexCh(info.color, 1);
              const b      = this.hexCh(info.color, 2);
              const bgRgba = active ? info.color : `rgba(${r},${g},${b},0.12)`;
              const bdRgba = active ? info.color : `rgba(${r},${g},${b},0.35)`;
              const clr    = active ? '#fff'     : info.color;
              return `<div class="type-pill${active ? ' active' : ''}"
                           data-type="${t}"
                           style="background:${bgRgba};border-color:${bdRgba};color:${clr}">
                        <span style="flex:1">${info.label}</span>
                        <span class="type-count">${typeCounts[t]}</span>
                      </div>`;
            }).join('')}
          </div>
        </div>

        <!-- Competitor checkboxes -->
        <div class="filter-section">
          <div class="filter-label">Competitor</div>
          <div class="comp-rows">
            ${this.COMPETITORS.map(c => {
              const checked = competitors.includes(c);
              return `<div class="comp-row" data-comp-row="${c}">
                        <div class="check-box${checked ? ' checked' : ''}"></div>
                        <span class="comp-name">${this.esc(c)}</span>
                        <span class="comp-count">${compCounts[c]}</span>
                      </div>`;
            }).join('')}
          </div>
        </div>

        <!-- Country radio -->
        <div class="filter-section">
          <div class="filter-label">Country</div>
          <div class="radio-rows">
            ${[
              { val:'all',       label:'All countries' },
              { val:'Singapore', label:'🇸🇬 Singapore' },
              { val:'Australia', label:'🇦🇺 Australia' },
              { val:'Global',    label:'🌐 Global (no country tag)' },
            ].map(o => `
              <div class="radio-row" data-country="${o.val}">
                <div class="radio-dot${country === o.val ? ' checked' : ''}"></div>
                <span class="radio-label">${o.label}</span>
              </div>`).join('')}
          </div>
        </div>

        <!-- Date range radio -->
        <div class="filter-section">
          <div class="filter-label">Date range</div>
          <div class="radio-rows">
            ${[
              { val:'30d', label:'Last 30 days' },
              { val:'90d', label:'Last 90 days' },
              { val:'all', label:'All time' },
            ].map(o => `
              <div class="radio-row" data-range="${o.val}">
                <div class="radio-dot${dateRange === o.val ? ' checked' : ''}"></div>
                <span class="radio-label">${o.label}</span>
              </div>`).join('')}
          </div>
        </div>

        <!-- Scrape history -->
        <div class="filter-section">
          <div class="filter-label">Scrape history</div>
          <div class="scrape-entry">
            ${lastScrape}
            <span class="scrape-badge">latest</span>
          </div>
        </div>

        <!-- Reset (only when filters active) -->
        <button class="reset-btn${hasFilter ? '' : ' hidden'}" id="btn-reset">
          Reset all filters
        </button>

      </div>
    `;
  },

  /* ─── MIDDLE PANEL (heatmap) ──────────────────────────────────────────────── */

  renderMiddle() {
    const matrix = this.buildMatrix();
    const { heatmapSel } = this.state;

    // Row totals (already in matrix.Total)
    const colTotals = { Singapore: 0, Australia: 0, Global: 0, Total: 0 };
    this.COMPETITORS.forEach(comp => {
      ['Singapore','Australia','Global','Total'].forEach(k => { colTotals[k] += matrix[comp][k]; });
    });

    document.getElementById('panel-middle').innerHTML = `
      <div class="middle-inner">
        <div class="middle-header">
          <div class="middle-title">Signal density by market</div>
          <div class="middle-sub">Competitor mentions in the last 12 months — click a cell to filter the signal feed</div>
        </div>

        <div class="heatmap-scroll">
          <table class="heatmap-table" aria-label="Competitor signal density heatmap">
            <thead>
              <tr>
                <th class="hmap-corner" scope="col"></th>
                ${['Singapore','Australia','Global','Total'].map(col =>
                  `<th class="hmap-col-head" scope="col">${this.COL_LABELS[col]}</th>`
                ).join('')}
              </tr>
            </thead>
            <tbody>
              ${this.COMPETITORS.map(comp => {
                const row = matrix[comp];
                return `
                  <tr>
                    <th class="hmap-row-head" scope="row">${this.esc(comp)}</th>
                    ${['Singapore','Australia','Global'].map(col => {
                      const n   = row[col];
                      const sty = this.heatStyle(n);
                      const sel = heatmapSel && heatmapSel.competitor === comp && heatmapSel.country === col;
                      return `<td
                        class="hmap-cell${sel ? ' selected' : ''}"
                        style="background:${sty.bg};border-color:${sel ? '#34D399' : sty.border};color:${sty.text}"
                        data-comp="${comp}" data-hcol="${col}"
                        tabindex="0" role="button"
                        aria-label="${comp} ${col}: ${n}"
                        aria-pressed="${sel}"
                      >${n}</td>`;
                    }).join('')}
                    <td class="hmap-total-cell">${row.Total}</td>
                  </tr>
                `;
              }).join('')}
            </tbody>
            <tfoot>
              <tr>
                <th class="hmap-row-head" scope="row">Total</th>
                <td class="hmap-total-cell">${colTotals.Singapore}</td>
                <td class="hmap-total-cell">${colTotals.Australia}</td>
                <td class="hmap-total-cell">${colTotals.Global}</td>
                <td class="hmap-total-cell">${colTotals.Total}</td>
              </tr>
            </tfoot>
          </table>
        </div>

        <div class="middle-placeholder">
          App store ratings tracking — coming in v2
        </div>
      </div>
    `;
  },

  // Build competitor × country matrix from all entries in dashboard.json
  buildMatrix() {
    const matrix = {};
    this.COMPETITORS.forEach(c => {
      matrix[c] = { Singapore: 0, Australia: 0, Global: 0, Total: 0 };
    });
    this.data.entries.forEach(e => {
      e.competitors.forEach(comp => {
        if (!matrix[comp]) return;
        const countries = e.countries || [];
        if (countries.includes('Singapore')) matrix[comp].Singapore++;
        if (countries.includes('Australia')) matrix[comp].Australia++;
        if (countries.length === 0)          matrix[comp].Global++;
        matrix[comp].Total++;
      });
    });
    return matrix;
  },

  // Color scale: 0 → dim, 1-5 → very light, 6-20 → medium, 21+ → bright
  heatStyle(n) {
    if (n === 0)  return { bg:'#2A2D38', border:'#353945', text:'#6B7080' };
    if (n <= 5)   return { bg:'rgba(52,211,153,0.14)', border:'rgba(52,211,153,0.3)', text:'#34D399' };
    if (n <= 20)  return { bg:'rgba(52,211,153,0.30)', border:'rgba(52,211,153,0.5)', text:'#6ee7b7' };
    return              { bg:'rgba(52,211,153,0.60)', border:'#34D399',               text:'#022c22' };
  },

  /* ─── RIGHT PANEL (feed) ──────────────────────────────────────────────────── */

  renderRight() {
    const panel = document.getElementById('panel-right');

    const heading = this.getFeedHeading();
    const sub     = this.getFeedSub();
    const slice   = this.filtered.slice(0, this.state.page * this.PAGE_SIZE);

    let listHTML = '';
    if (this.filtered.length === 0) {
      listHTML = `
        <div class="feed-empty">
          <p>No signals match these filters.</p>
          <button class="btn-reset-inline" data-reset="1">Reset filters</button>
        </div>
      `;
    } else {
      listHTML = `<div class="feed-list">${slice.map(e => this.renderCard(e)).join('')}</div>`;
    }

    const remaining = this.filtered.length - slice.length;
    const loadMore  = remaining > 0
      ? `<div class="load-more-wrap">
           <button class="load-more-btn" id="btn-load-more">
             Load more <span class="load-more-remaining">(${remaining} remaining)</span>
           </button>
         </div>`
      : '';

    panel.innerHTML = `
      <div class="feed-header">
        <div class="feed-heading">${this.esc(heading)}</div>
        ${sub ? `<div class="feed-sub">${sub}</div>` : ''}
      </div>
      ${listHTML}
      ${loadMore}
    `;
  },

  appendMoreCards() {
    const start = (this.state.page - 1) * this.PAGE_SIZE;
    const slice = this.filtered.slice(start, this.state.page * this.PAGE_SIZE);
    if (!slice.length) return;

    let list = document.querySelector('#panel-right .feed-list');
    if (!list) {
      list = document.createElement('div');
      list.className = 'feed-list';
      document.getElementById('panel-right').appendChild(list);
    }

    const frag = document.createDocumentFragment();
    slice.forEach(e => {
      const div = document.createElement('div');
      div.innerHTML = this.renderCard(e);
      frag.appendChild(div.firstElementChild);
    });
    list.appendChild(frag);

    // Update load more button
    const remaining = this.filtered.length - this.state.page * this.PAGE_SIZE;
    const btn = document.getElementById('btn-load-more');
    if (remaining <= 0 && btn) {
      btn.closest('.load-more-wrap').remove();
    } else if (btn) {
      btn.querySelector('.load-more-remaining').textContent = `(${remaining} remaining)`;
    }
  },

  renderCard(entry) {
    const type    = this.TYPES[entry.signal_type] || this.TYPES.other;
    const r       = this.hexCh(type.color, 0), g = this.hexCh(type.color, 1), b = this.hexCh(type.color, 2);
    const badgeBg = `rgba(${r},${g},${b},0.15)`;
    const badgeBd = `rgba(${r},${g},${b},0.3)`;
    const summary = entry.summary ? entry.summary.slice(0, 200) + (entry.summary.length > 200 ? '…' : '') : '';

    const countryTags = entry.countries && entry.countries.length > 0
      ? entry.countries.map(c => `<span class="tag tag-country">${this.FLAGS[c] || ''}${c ? ' '+this.esc(c) : ''}</span>`).join('')
      : `<span class="tag tag-global">🌐 Global</span>`;

    return `
      <div class="signal-card" data-entry-id="${this.esc(entry.id)}">
        <div class="card-top-row">
          <span class="sig-badge" style="color:${type.color};background:${badgeBg};border:1px solid ${badgeBd}">${type.label}</span>
          <span class="card-dot">·</span>
          <span class="card-source">${this.esc(entry.source_name || '')}</span>
          <span class="card-date">${this.relTime(entry.published_date)}</span>
        </div>
        <div class="card-title">${this.esc(entry.title || 'Untitled')}</div>
        ${summary ? `<div class="card-summary">${this.esc(summary)}</div>` : ''}
        <div class="card-tags">
          ${entry.competitors.map(c => `<span class="tag tag-comp">${this.esc(c)}</span>`).join('')}
          ${countryTags}
        </div>
      </div>
    `;
  },

  getFeedHeading() {
    const { heatmapSel } = this.state;
    if (heatmapSel) {
      const flag = { Singapore:'🇸🇬', Australia:'🇦🇺', Global:'🌐' }[heatmapSel.country] || '';
      return `${heatmapSel.competitor} × ${flag} ${heatmapSel.country}`;
    }
    if (this.isDefaultView()) return 'Strategic signals';
    return 'Recent signals';
  },

  getFeedSub() {
    const { heatmapSel } = this.state;
    const total = this.data.entries.filter(e => e.signal_type !== 'industry_context').length;
    if (heatmapSel || !this.isDefaultView()) {
      return `Showing <strong>${this.filtered.length}</strong> of <strong>${total}</strong> signals`;
    }
    // Default curated view — explain what's being shown
    return 'Showing product launches, market expansion, regulatory, and partnership signals only.';
  },

  /* ─── BOTTOM PANEL ────────────────────────────────────────────────────────── */

  renderBottom() {
    document.getElementById('panel-bottom').innerHTML = `
      <div class="bottom-inner">
        <!-- TODO: update portfolio href when domain is known -->
        <a href="../">← Portfolio</a>
        <span class="bottom-sep">|</span>
        Built by Richard Lesmana
        <span class="bottom-sep">|</span>
        <a href="https://github.com/richardlesmana/cex-intel" target="_blank" rel="noopener">GitHub</a>
        <span class="bottom-sep">|</span>
        v1: SG, AU + Global coverage
        <span class="bottom-sep">|</span>
        <a href="./docs/coverage_notes.md" target="_blank">Coverage notes</a>
      </div>
    `;
  },

  /* ─── MODAL ───────────────────────────────────────────────────────────────── */

  openModal(entry) {
    const type  = this.TYPES[entry.signal_type] || this.TYPES.other;
    const r     = this.hexCh(type.color, 0), g = this.hexCh(type.color, 1), b = this.hexCh(type.color, 2);
    const date  = entry.published_date
      ? new Date(entry.published_date).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })
      : 'Unknown date';

    const countryTags = entry.countries && entry.countries.length > 0
      ? entry.countries.map(c => `<span class="tag tag-country">${this.FLAGS[c] || ''} ${this.esc(c)}</span>`).join('')
      : `<span class="tag tag-global">🌐 Global</span>`;

    document.getElementById('modal-box').innerHTML = `
      <div class="modal-top">
        <button class="modal-close" id="modal-close-btn" aria-label="Close">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>
      <span class="sig-badge" style="color:${type.color};background:rgba(${r},${g},${b},0.15);border:1px solid rgba(${r},${g},${b},0.3);align-self:flex-start">
        ${type.label}
      </span>
      <h2 class="modal-title">${this.esc(entry.title || 'Untitled')}</h2>
      <div class="modal-meta">
        <span>${this.esc(entry.source_name || '')}</span>
        <span class="card-dot">·</span>
        <span>${date}</span>
      </div>
      <div class="modal-tags">
        ${entry.competitors.map(c => `<span class="tag tag-comp">${this.esc(c)}</span>`).join('')}
        ${countryTags}
      </div>
      ${entry.summary
        ? `<div class="modal-summary">${this.esc(entry.summary)}</div>`
        : `<div class="modal-summary" style="color:var(--text-4);font-style:italic">No summary available.</div>`}
      ${entry.url
        ? `<button class="modal-open-btn" onclick="window.open('${this.esc(entry.url)}','_blank','noopener')">Open original →</button>`
        : ''}
    `;

    document.getElementById('modal-backdrop').classList.remove('hidden');
    document.getElementById('modal-box').classList.remove('hidden');
    document.body.style.overflow = 'hidden';
  },

  closeModal() {
    document.getElementById('modal-backdrop').classList.add('hidden');
    document.getElementById('modal-box').classList.add('hidden');
    document.body.style.overflow = '';
  },

  /* ─── Event delegation ────────────────────────────────────────────────────── */

  attachListeners() {
    // All click-based interactions via delegation
    document.addEventListener('click', e => {
      // Info tooltip toggle
      if (e.target.closest('#info-btn')) {
        const tip  = document.getElementById('info-tip');
        const btn  = document.getElementById('info-btn');
        const open = tip.classList.toggle('visible');
        btn && btn.setAttribute('aria-expanded', open);
        e.stopPropagation();
        return;
      }
      // Dismiss tooltip on outside click
      const tip = document.getElementById('info-tip');
      if (tip && !e.target.closest('.info-anchor')) tip.classList.remove('visible');

      // Modal backdrop click
      if (e.target.id === 'modal-backdrop')  { this.closeModal(); return; }
      if (e.target.closest('#modal-close-btn')) { this.closeModal(); return; }

      // Heatmap cell (data-hcol marks a clickable cell, not the total column)
      const hcell = e.target.closest('[data-hcol]');
      if (hcell) {
        this.onHeatmapClick(hcell.dataset.comp, hcell.dataset.hcol);
        return;
      }

      // Signal type pill
      const tpill = e.target.closest('[data-type]');
      if (tpill) { this.onTypePill(tpill.dataset.type); return; }

      // Competitor checkbox row
      const crow = e.target.closest('[data-comp-row]');
      if (crow) { this.onCompCheck(crow.dataset.compRow); return; }

      // Country radio row
      const cradio = e.target.closest('[data-country]');
      if (cradio) { this.onCountryRadio(cradio.dataset.country); return; }

      // Date range radio row
      const dradio = e.target.closest('[data-range]');
      if (dradio) { this.onDateRadio(dradio.dataset.range); return; }

      // Reset filters
      if (e.target.closest('#btn-reset') || e.target.closest('[data-reset]')) {
        this.reset();
        return;
      }

      // Load more
      if (e.target.closest('#btn-load-more')) { this.onLoadMore(); return; }

      // Signal card → open modal
      const scard = e.target.closest('[data-entry-id]');
      if (scard) {
        const entry = this.data.entries.find(en => en.id === scard.dataset.entryId);
        if (entry) this.openModal(entry);
        return;
      }
    });

    // Heatmap keyboard (Enter / Space activates a cell)
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') { this.closeModal(); return; }
      if ((e.key === 'Enter' || e.key === ' ') && e.target.dataset.hcol) {
        e.preventDefault();
        this.onHeatmapClick(e.target.dataset.comp, e.target.dataset.hcol);
      }
    });
  },

  /* ─── Interaction handlers ────────────────────────────────────────────────── */

  onHeatmapClick(comp, col) {
    if (col === 'Total') return;   // Total column is not clickable
    const cur = this.state.heatmapSel;
    this.state.heatmapSel = (cur && cur.competitor === comp && cur.country === col)
      ? null                                            // toggle off
      : { competitor: comp, country: col };             // set
    this.update();
  },

  onTypePill(type) {
    const idx = this.state.signalTypes.indexOf(type);
    if (idx >= 0) this.state.signalTypes.splice(idx, 1);
    else          this.state.signalTypes.push(type);
    this.state.heatmapSel = null;   // clear heatmap selection on regular filter change
    this.update();
  },

  onCompCheck(comp) {
    const idx = this.state.competitors.indexOf(comp);
    if (idx >= 0) this.state.competitors.splice(idx, 1);
    else          this.state.competitors.push(comp);
    this.state.heatmapSel = null;
    this.update();
  },

  onCountryRadio(country) {
    this.state.country    = country;
    this.state.heatmapSel = null;
    this.update();
  },

  onDateRadio(range) {
    this.state.dateRange  = range;
    this.state.heatmapSel = null;
    this.update();
  },

  onLoadMore() {
    this.state.page++;
    this.appendMoreCards();
  },

  reset() {
    this.state.signalTypes = [...this.DEFAULT_TYPES];   // reset to curated default, not empty
    this.state.competitors = [];
    this.state.country     = 'all';
    this.state.dateRange   = '90d';
    this.state.heatmapSel  = null;
    this.update();
  },

  /* ─── Filter logic ────────────────────────────────────────────────────────── */

  computeFiltered() {
    const { signalTypes, competitors, country, dateRange, heatmapSel } = this.state;
    const cutoff = this.cutoff(dateRange);

    return this.data.entries.filter(e => {
      // Always hide industry_context
      if (e.signal_type === 'industry_context') return false;

      // Date filter
      if (cutoff && e.published_date && new Date(e.published_date) < cutoff) return false;

      // Signal type filter (applies even when heatmap selection active)
      if (signalTypes.length > 0 && !signalTypes.includes(e.signal_type)) return false;

      // ── Heatmap selection overrides competitor + country filters ──
      if (heatmapSel) {
        if (!e.competitors.includes(heatmapSel.competitor)) return false;
        if      (heatmapSel.country === 'Global')    { if ((e.countries||[]).length > 0)              return false; }
        else if (heatmapSel.country === 'Singapore') { if (!(e.countries||[]).includes('Singapore'))  return false; }
        else if (heatmapSel.country === 'Australia') { if (!(e.countries||[]).includes('Australia'))  return false; }
        return true;
      }

      // ── Regular filters ──
      if (competitors.length > 0 && !e.competitors.some(c => competitors.includes(c))) return false;

      if      (country === 'Global')    { if ((e.countries||[]).length > 0)              return false; }
      else if (country === 'Singapore') { if (!(e.countries||[]).includes('Singapore'))  return false; }
      else if (country === 'Australia') { if (!(e.countries||[]).includes('Australia'))  return false; }

      return true;
    }).sort((a, b) => new Date(b.published_date || 0) - new Date(a.published_date || 0));
  },

  // True when state differs from the curated default (shows the Reset button)
  hasActiveFilters() { return !this.isDefaultView(); },

  // The curated default: 4 strategic types, no other filters, no heatmap selection
  isDefaultView() {
    const s = this.state;
    return this.arraysMatch(s.signalTypes, this.DEFAULT_TYPES)
        && s.competitors.length === 0
        && s.country    === 'all'
        && s.dateRange  === '90d'
        && s.heatmapSel === null;
  },

  arraysMatch(a, b) {
    if (a.length !== b.length) return false;
    const sa = [...a].sort(), sb = [...b].sort();
    return sa.every((v, i) => v === sb[i]);
  },

  cutoff(range) {
    if (range === '30d') return new Date(Date.now() - 30 * 86400000);
    if (range === '90d') return new Date(Date.now() - 90 * 86400000);
    return null;
  },

  /* ─── Utilities ───────────────────────────────────────────────────────────── */

  relTime(iso) {
    if (!iso) return '—';
    const d = Math.floor((Date.now() - new Date(iso)) / 86400000);
    if (d === 0)   return 'Today';
    if (d === 1)   return 'Yesterday';
    if (d < 7)     return `${d}d ago`;
    if (d < 30)    return `${Math.floor(d/7)}w ago`;
    if (d < 365)   return `${Math.floor(d/30)}mo ago`;
    return `${Math.floor(d/365)}y ago`;
  },

  // Parse one R/G/B channel from a hex color (channel: 0=R, 1=G, 2=B)
  hexCh(hex, ch) {
    return parseInt(hex.slice(1 + ch*2, 3 + ch*2), 16);
  },

  esc(str) {
    if (!str) return '';
    return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
              .replace(/"/g,'&quot;').replace(/'/g,'&#039;');
  },
};

document.addEventListener('DOMContentLoaded', () => app.init());
