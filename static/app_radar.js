/**
 * InReal dashboard: list of scraped internships with the n8n scam-check verdict for each.
 * Data: /api/internships (rows of internships.csv). Live updates: /api/moderation/status,
 * /api/scrape/status, /api/alerts. No frameworks: plain DOM, so it works offline except the font.
 */

let allInternships = [];
let activeLocation = 'all';
let activeStipend = 'all';
let activeSource = 'all';
let activeModeration = 'verified';   // default: only listings the scam check passed
let showBookmarkedOnly = false;
let bookmarks = readBookmarks();
let activeDrawerJob = null;
let lastFocus = null;

const $ = (id) => document.getElementById(id);

function readBookmarks() {
  try { return JSON.parse(localStorage.getItem('inreal_bookmarks') || '[]'); } catch (e) { return []; }
}
function writeBookmarks() {
  try { localStorage.setItem('inreal_bookmarks', JSON.stringify(bookmarks)); } catch (e) { /* private window */ }
}

document.addEventListener('DOMContentLoaded', () => {
  bindEventHandlers();
  loadData();
  pollScraperStatus();
  pollAlerts();
  pollModeration();
  updateBookmarkCounter();
});

// ─────────────────────────────────────────────
// 1. Data
// ─────────────────────────────────────────────
async function loadData() {
  try {
    const res = await fetch('/api/internships');
    allInternships = (await res.json()) || [];
    populateSourceFilter(allInternships);
    renderPipeline();
    applyFiltersAndRender();
  } catch (err) {
    console.error('Failed to load internships:', err);
  }
}

function populateSourceFilter(items) {
  const sel = $('source-filter');
  if (!sel) return;
  const sources = [...new Set(items.map(i => i.source_platform).filter(Boolean))].sort();
  if (activeSource !== 'all' && !sources.includes(activeSource)) sources.push(activeSource);
  sel.innerHTML = '<option value="all">All sites</option>' +
    sources.map(s => `<option value="${escapeHtml(s)}">${escapeHtml(shortSource(s))}</option>`).join('');
  sel.value = activeSource;   // the list reloads as verdicts arrive; keep the user's choice
}

function shortSource(s) {
  return String(s).replace(/ Internship Portal \(Govt of India\)/i, ' (Govt)');
}

// Counts of the whole collection, independent of the filters below it
function renderPipeline() {
  const st = (r) => r.moderation_status || '';
  $('pipe-all').textContent = allInternships.length;
  $('pipe-pass').textContent = allInternships.filter(r => st(r) === 'approved').length;
  $('pipe-look').textContent = allInternships.filter(r => st(r) === 'review').length;
  $('pipe-scam').textContent = allInternships.filter(r => st(r) === 'blocked').length;
  $('pipe-sites').textContent = new Set(allInternships.map(r => r.source_platform).filter(Boolean)).size;
  syncPipelineButtons();
}

function syncPipelineButtons() {
  document.querySelectorAll('.stage').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.show === activeModeration)));
}

// ─────────────────────────────────────────────
// 2. Filters
// ─────────────────────────────────────────────
function isPaid(item) {
  const num = Number(item.stipend_numeric || 0);
  return num > 0 || (!!item.stipend && !/unpaid/i.test(item.stipend));
}

function applyFiltersAndRender() {
  const q = ($('search-input')?.value || '').toLowerCase().trim();

  const filtered = allInternships.filter(item => {
    if (showBookmarkedOnly && !bookmarks.includes(item.id)) return false;

    const mod = item.moderation_status || '';
    if (activeModeration === 'verified' && mod !== 'approved') return false;
    if (activeModeration === 'verified_review' && mod !== 'approved' && mod !== 'review') return false;
    if (activeModeration === 'review' && mod !== 'review') return false;
    if (activeModeration === 'blocked' && mod !== 'blocked') return false;

    if (activeLocation !== 'all' && (item.location_type || '').toLowerCase() !== activeLocation.toLowerCase()) return false;
    if (activeSource !== 'all' && item.source_platform !== activeSource) return false;

    const pay = Number(item.stipend_numeric || 0);
    if (activeStipend === 'paid' && !isPaid(item)) return false;
    if (activeStipend === '20k' && pay < 20000) return false;
    if (activeStipend === '50k' && pay < 50000) return false;
    if (activeStipend === '100k' && pay < 100000) return false;

    if (q) {
      const text = `${item.role_title || ''} ${item.company_name || ''} ${item.required_skills || ''} ${item.location || ''}`.toLowerCase();
      if (!text.includes(q)) return false;
    }
    return true;
  });

  $('stat-total-jobs').textContent = filtered.length;
  $('stat-paid-jobs').textContent = filtered.filter(isPaid).length;
  $('stat-new-jobs').textContent = filtered.filter(isNewToday).length;
  renderListings(filtered);
}

// ─────────────────────────────────────────────
// 3. Listing rows
// ─────────────────────────────────────────────
const VERDICT = {
  approved: { cls: 'pass', short: 'Passed', long: 'Passed the check' },
  review:   { cls: 'look', short: 'Look closer', long: 'Needs a closer look' },
  blocked:  { cls: 'scam', short: 'Likely scam', long: 'Likely scam' },
  expired:  { cls: 'closed', short: 'Link closed', long: 'Apply link is closed' },
  checking: { cls: 'wait', short: 'Checking…', long: 'Being checked now' },
  '':       { cls: 'wait', short: 'Not checked', long: 'Not checked yet' },
};
const verdictOf = (item) => VERDICT[item.moderation_status || ''] || VERDICT[''];

const SAVE_ICON = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M6 3h12v18l-6-4-6 4z"/></svg>';

function renderListings(items) {
  const box = $('listings-container');
  const empty = $('empty-state');
  if (!box) return;
  empty.classList.toggle('hidden', items.length > 0);

  box.innerHTML = items.map(item => {
    const v = verdictOf(item);
    const saved = bookmarks.includes(item.id);
    const skills = uniqueSkills(item.required_skills).slice(0, 4);
    const flags = String(item.trust_flags || '').split(';').map(f => f.trim()).filter(Boolean);
    const meta = [
      `<span class="co">${escapeHtml(item.company_name || 'Company not named')}</span>`,
      `<span>${escapeHtml(item.location || 'Location not stated')}</span>`,
      `<span>${escapeHtml(shortSource(item.source_platform || ''))}</span>`,
    ].join('');
    const tags = [
      isNewToday(item) ? '<span class="tag new">Added today</span>' : '',
      flags.length ? `<span class="tag warn" title="${escapeHtml(flags.join('; '))}">${flags.length} note${flags.length > 1 ? 's' : ''}</span>` : '',
      ...skills.map(s => `<span class="tag">${escapeHtml(s)}</span>`),
    ].join('');

    return `
      <div class="row ${v.cls}" role="button" tabindex="0" data-id="${escapeHtml(item.id)}"
           aria-label="${escapeHtml(`${item.role_title || 'Internship'} at ${item.company_name || 'unnamed company'}, ${v.long}`)}">
        <span class="bar" aria-hidden="true"></span>
        <div class="main">
          <h3>${escapeHtml(item.role_title || 'Internship')}</h3>
          <div class="meta">${meta}</div>
          <div class="tags">${tags}</div>
        </div>
        <div class="side">
          <div class="pay"><b title="${escapeHtml(item.stipend || '')}">${escapeHtml(tidyStipend(item.stipend) || 'Stipend not stated')}</b>${item.duration ? `<span>${escapeHtml(item.duration)}</span>` : ''}</div>
          <div><span class="verdict ${v.cls}">${v.short}</span></div>
        </div>
        <button class="save" type="button" data-save="${escapeHtml(item.id)}" aria-pressed="${saved}"
                aria-label="${saved ? 'Remove from saved' : 'Save'}">${SAVE_ICON}</button>
      </div>`;
  }).join('');
}

function uniqueSkills(str) {
  const seen = new Set();
  return String(str || '').split(',').map(s => s.trim()).filter(s => {
    const k = s.toLowerCase();
    if (!s || seen.has(k)) return false;
    seen.add(k);
    return true;
  });
}

// ─────────────────────────────────────────────
// 4. Detail drawer, with the scam check explained step by step
// ─────────────────────────────────────────────
function openDetailDrawer(id) {
  const item = allInternships.find(i => i.id === id);
  if (!item) return;
  activeDrawerJob = item;
  lastFocus = document.activeElement;

  $('drawer-role-title').textContent = item.role_title || 'Internship';
  $('drawer-company-name').textContent = item.company_name || 'Company not named';
  $('drawer-stipend').textContent = tidyStipend(item.stipend) || 'Not stated';
  $('drawer-duration').textContent = item.duration || 'Not stated';
  $('drawer-deadline').textContent = formatDate(item.application_deadline) || 'Not stated';
  $('drawer-location').textContent = item.location || 'Not stated';
  $('drawer-source').textContent = shortSource(item.source_platform || '–');
  $('drawer-org-badge').textContent = item.org_type || 'Company';
  $('drawer-date').textContent = `${shortSource(item.source_platform || 'the site')} on ${formatDate(item.date_scraped) || 'an earlier run'}`;
  $('drawer-apply-link').href = safeUrl(item.apply_link);

  renderCheck(item);

  const skills = uniqueSkills(item.required_skills);
  $('drawer-skills-box').classList.toggle('hidden', !skills.length);
  $('drawer-skills-list').innerHTML = skills.map(s => `<span class="tag">${escapeHtml(s)}</span>`).join('');

  const desc = String(item.description || '').trim();
  $('drawer-desc-box').classList.toggle('hidden', !desc);
  $('drawer-description').textContent = desc;

  updateDrawerBookmarkIcon();
  $('detail-drawer-overlay').classList.remove('hidden');
  requestAnimationFrame(() => $('detail-drawer').classList.add('open'));
  $('detail-drawer').querySelector('.d-body').scrollTop = 0;
  $('close-drawer-btn').focus();
}

function closeDetailDrawer() {
  const overlay = $('detail-drawer-overlay');
  if (overlay.classList.contains('hidden')) return;
  $('detail-drawer').classList.remove('open');
  setTimeout(() => overlay.classList.add('hidden'), 220);
  activeDrawerJob = null;
  if (lastFocus && document.contains(lastFocus)) lastFocus.focus();
}

// Turns the pipeline's reason strings into three plain-language steps
function explainCheck(item) {
  const reasons = String(item.moderation_reasons || '').split(' | ').map(r => r.trim()).filter(Boolean);
  const judged = ['approved', 'review', 'blocked'].includes(item.moderation_status || '');
  const rules = String(item.trust_flags || '').split(';').map(f => f.trim()).filter(Boolean);
  const wording = [];
  let wordingSkipped = false, ai = null, aiSkipped = false, note = '';

  for (const r of reasons) {
    let m;
    if ((m = r.match(/^LLM:\s*(\w+),\s*probability\s*([\d.]+)\s*[—-]\s*(.*)$/i))) {
      ai = { verdict: m[1].toLowerCase(), p: Number(m[2]), summary: m[3] };
    } else if (/^LLM judge unavailable/i.test(r)) {
      aiSkipped = true;
    } else if (/^Embedding failed/i.test(r)) {
      wordingSkipped = true;
    } else if ((m = r.match(/^Vector match,\s*(.*?)\s*\(similarity\s*([\d.]+)\):\s*"?(.*?)"?$/i))) {
      wording.push({ label: m[1], quote: m[3] });
    } else if (/^Near-copy of a known scam/i.test(r)) {
      wording.push({ label: r.replace(/^Near-copy of a known scam:\s*/i, 'Near copy of a known scam: '), quote: '' });
    } else if (/disagree/i.test(r)) {
      note = 'The AI reviewer and the wording check disagree, so a person should look at this one.';
    } else if ((m = r.match(/^Scraper warnings?:\s*(.*)$/i))) {
      m[1].split(';').map(s => s.trim()).filter(Boolean).forEach(s => { if (!rules.includes(s)) rules.push(s); });
    } else if (r.length < 160 && !/[{}]/.test(r)) {
      if (!rules.includes(r)) rules.push(r);
    }
  }

  const steps = [];
  steps.push(rules.length
    ? { ic: 'flag', t: 'Link and details', d: `<ul>${rules.map(f => `<li>${escapeHtml(f)}</li>`).join('')}</ul>` }
    : { ic: judged ? 'ok' : 'skip', t: 'Link and details', d: judged ? 'No warning signs in the apply link, contact details or the post.' : 'Not run yet.' });

  if (wording.length) {
    const strong = item.moderation_status === 'blocked';
    steps.push({ ic: strong ? 'bad' : 'flag', t: 'Scam wording',
      d: wording.map(w => `${escapeHtml(w.label)}${w.quote ? `: <q>${escapeHtml(w.quote)}</q>` : ''}`).join('<br>') });
  } else if (wordingSkipped) {
    steps.push({ ic: 'skip', t: 'Scam wording', d: 'Skipped: the similarity service did not answer in time. The other two steps decided.' });
  } else {
    steps.push({ ic: judged ? 'ok' : 'skip', t: 'Scam wording', d: judged ? 'Not close to the wording of any known scam post.' : 'Not run yet.' });
  }

  if (ai) {
    const ic = ai.verdict === 'genuine' ? 'ok' : ai.verdict === 'scam' ? 'bad' : 'flag';
    const word = { genuine: 'Looks genuine', suspicious: 'Unsure', scam: 'Looks like a scam' }[ai.verdict] || ai.verdict;
    steps.push({ ic, t: 'AI reviewer', d: `${word} (${Math.round(ai.p * 100)}% scam chance). ${escapeHtml(ai.summary)}` });
  } else if (aiSkipped) {
    steps.push({ ic: 'skip', t: 'AI reviewer', d: 'Did not answer, so the first two steps decided.' });
  } else if (item.moderation_status === 'blocked' && wording.length) {
    steps.push({ ic: 'skip', t: 'AI reviewer', d: 'Not needed: the wording check was conclusive.' });
  } else {
    steps.push({ ic: 'skip', t: 'AI reviewer', d: judged ? 'Not run.' : 'Not run yet.' });
  }
  return { steps, note };
}

function renderCheck(item) {
  const v = verdictOf(item);
  const box = $('drawer-mod-box');
  box.className = `check ${v.cls}`;
  $('drawer-mod-title').textContent = v.long;
  const risk = item.scam_risk !== '' && item.scam_risk != null && !isNaN(Number(item.scam_risk))
    ? `Scam risk ${Math.round(Number(item.scam_risk) * 100)}%` : '';
  $('drawer-mod-risk').textContent = risk;

  const { steps, note } = explainCheck(item);
  $('drawer-mod-note').textContent = note;
  $('drawer-mod-note').classList.toggle('hidden', !note);
  const mark = { ok: '✓', flag: '!', bad: '✕', skip: '–' };
  $('drawer-mod-reasons').innerHTML = steps.map(s => `
    <li><span class="ic ${s.ic}" aria-hidden="true">${mark[s.ic]}</span>
      <div><div class="t">${s.t}</div><div class="d">${s.d}</div></div></li>`).join('');
}

function updateDrawerBookmarkIcon() {
  const btn = $('drawer-bookmark-btn');
  if (!btn || !activeDrawerJob) return;
  const saved = bookmarks.includes(activeDrawerJob.id);
  btn.textContent = saved ? 'Saved' : 'Save';
  btn.setAttribute('aria-pressed', String(saved));
}

// ─────────────────────────────────────────────
// 5. Saved listings (this browser only)
// ─────────────────────────────────────────────
function toggleBookmark(id) {
  bookmarks = bookmarks.includes(id) ? bookmarks.filter(b => b !== id) : [...bookmarks, id];
  writeBookmarks();
  updateBookmarkCounter();
  applyFiltersAndRender();
  if (activeDrawerJob && activeDrawerJob.id === id) updateDrawerBookmarkIcon();
}

function updateBookmarkCounter() {
  const c = $('bookmark-count');
  if (c) c.textContent = bookmarks.length;
}

// ─────────────────────────────────────────────
// 6. Live status: scraper, alerts, scam-check queue
// ─────────────────────────────────────────────
async function pollScraperStatus() {
  try {
    const data = await fetch('/api/scrape/status').then(r => r.json());
    const running = data.status === 'running';
    handleScrapeProgress(data.progress, running);
    $('ping-dot').classList.toggle('busy', running);
    $('scraper-status-text').textContent = running ? 'Scraping…' : 'Ready';
  } catch (e) { /* app restarting */ }
  setTimeout(pollScraperStatus, 3500);
}

async function pollAlerts() {
  try {
    const data = await fetch('/api/alerts').then(r => r.json());
    if (data.alert) {
      $('action-title').textContent = data.alert.title || `${data.alert.source || 'A site'} needs you`;
      $('action-message').textContent = data.alert.message || 'Finish the check in its browser window.';
      $('action-banner').classList.remove('hidden');
    } else {
      $('action-banner').classList.add('hidden');
    }
  } catch (e) { /* app restarting */ }
  setTimeout(pollAlerts, 3000);
}

// Reload when n8n has judged more listings (it runs while scraping continues)
let lastJudged = -1;
async function pollModeration() {
  try {
    const c = await fetch('/api/moderation/status').then(r => r.json());
    const judged = c.approved + c.review + c.blocked + c.expired;
    const waiting = c.pending + c.checking;
    $('mod-queue').textContent = waiting ? `${waiting} still being checked` : '';
    const notes = [];
    if (waiting) notes.push(`${waiting} still being checked`);
    if (c.expired) notes.push(`${c.expired} with a closed apply link`);
    $('pipe-note').textContent = notes.join(' · ');
    if (judged !== lastJudged) { lastJudged = judged; loadData(); }
  } catch (e) { /* app restarting */ }
  setTimeout(pollModeration, 5000);
}

// One popup per finished site, one summary at the end
let seenRunId = null, seenSites = 0, runAnnounced = true;
function handleScrapeProgress(progress, isRunning) {
  if (!progress) return;
  if (seenRunId === null) {            // page just opened: don't replay an old run
    seenRunId = progress.run_id; seenSites = progress.sites.length; runAnnounced = progress.finished;
    return;
  }
  if (progress.run_id !== seenRunId) { seenRunId = progress.run_id; seenSites = 0; runAnnounced = false; }
  for (const site of progress.sites.slice(seenSites)) {
    const name = site.source.charAt(0).toUpperCase() + site.source.slice(1);
    if (site.ok) {
      showToast(site.added ? 'success' : 'info', `${name} done`,
        site.added ? `${site.added} new internship${site.added > 1 ? 's' : ''} saved. Checking them for scams now.`
                   : 'No new internships this time.');
    } else {
      showToast('error', `${name} failed`, site.error || 'See scraper_run.log for details.');
    }
    loadData();
  }
  seenSites = progress.sites.length;
  if (progress.finished && !runAnnounced && !isRunning) {
    runAnnounced = true;
    const failed = progress.failed.length ? ` ${progress.failed.length} site${progress.failed.length > 1 ? 's' : ''} failed.` : '';
    showToast('success', 'Scraping finished',
      `${progress.total_added} new internship${progress.total_added === 1 ? '' : 's'} from ${progress.sites.length} site${progress.sites.length === 1 ? '' : 's'}.${failed} They appear in the list once they pass the check.`);
  }
}

function showToast(kind, title, message) {
  let stack = $('toast-stack');
  if (!stack) {
    stack = document.createElement('div');
    stack.id = 'toast-stack';
    stack.setAttribute('aria-live', 'polite');
    document.body.appendChild(stack);
  }
  const t = document.createElement('div');
  t.className = `toast ${kind}`;
  t.setAttribute('role', 'status');
  t.innerHTML = `<div><b>${escapeHtml(title)}</b><span>${escapeHtml(message)}</span></div><button type="button" aria-label="Dismiss">×</button>`;
  t.querySelector('button').onclick = () => t.remove();
  stack.appendChild(t);
  setTimeout(() => { t.style.opacity = '0'; setTimeout(() => t.remove(), 300); }, 7000);
}

// ─────────────────────────────────────────────
// 7. Events
// ─────────────────────────────────────────────
function setModeration(value) {
  activeModeration = value;
  const sel = $('mod-filter');
  if (sel) sel.value = value;
  syncPipelineButtons();
  applyFiltersAndRender();
}

function bindEventHandlers() {
  $('search-input')?.addEventListener('input', applyFiltersAndRender);
  $('mod-filter')?.addEventListener('change', e => setModeration(e.target.value));
  $('source-filter')?.addEventListener('change', e => { activeSource = e.target.value; applyFiltersAndRender(); });
  $('location-select-filter')?.addEventListener('change', e => { activeLocation = e.target.value; applyFiltersAndRender(); });
  $('stipend-select-filter')?.addEventListener('change', e => { activeStipend = e.target.value; applyFiltersAndRender(); });
  document.querySelectorAll('.stage').forEach(b => b.addEventListener('click', () => {
    setModeration(b.dataset.show);
    document.querySelector('.filters').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }));

  $('filter-bookmarks-btn')?.addEventListener('click', () => {
    showBookmarkedOnly = !showBookmarkedOnly;
    const btn = $('filter-bookmarks-btn');
    btn.classList.toggle('on', showBookmarkedOnly);
    btn.setAttribute('aria-pressed', String(showBookmarkedOnly));
    applyFiltersAndRender();
  });

  const resetAll = () => {
    $('search-input').value = '';
    activeLocation = activeStipend = activeSource = 'all';
    showBookmarkedOnly = false;
    $('location-select-filter').value = 'all';
    $('stipend-select-filter').value = 'all';
    $('source-filter').value = 'all';
    $('filter-bookmarks-btn').classList.remove('on');
    $('filter-bookmarks-btn').setAttribute('aria-pressed', 'false');
    setModeration('verified');
  };
  $('reset-filters-btn')?.addEventListener('click', resetAll);
  $('empty-reset-btn')?.addEventListener('click', resetAll);

  // Rows: one listener for the whole list
  const list = $('listings-container');
  list.addEventListener('click', e => {
    const save = e.target.closest('[data-save]');
    if (save) { toggleBookmark(save.dataset.save); return; }
    const row = e.target.closest('.row');
    if (row) openDetailDrawer(row.dataset.id);
  });
  list.addEventListener('keydown', e => {
    if ((e.key === 'Enter' || e.key === ' ') && e.target.classList.contains('row')) {
      e.preventDefault();
      openDetailDrawer(e.target.dataset.id);
    }
  });

  $('close-drawer-btn')?.addEventListener('click', closeDetailDrawer);
  $('detail-drawer-overlay')?.addEventListener('click', e => { if (e.target === $('detail-drawer-overlay')) closeDetailDrawer(); });
  $('drawer-bookmark-btn')?.addEventListener('click', () => { if (activeDrawerJob) toggleBookmark(activeDrawerJob.id); });

  // Scrape dialog
  const modal = $('scrape-config-modal');
  const closeModal = () => { modal.classList.add('hidden'); $('trigger-scrape-btn').focus(); };
  $('trigger-scrape-btn')?.addEventListener('click', () => {
    modal.classList.remove('hidden');
    modal.querySelector('input')?.focus();
  });
  $('close-config-btn')?.addEventListener('click', closeModal);
  modal.addEventListener('click', e => { if (e.target === modal) closeModal(); });

  $('scrape-config-form')?.addEventListener('submit', async e => {
    e.preventDefault();
    const checked = name => [...document.querySelectorAll(`input[name="${name}"]:checked`)].map(cb => cb.value);
    const config = { regions: checked('regions'), sources: checked('sources') };
    if (!config.sources.length) { showToast('error', 'Pick at least one site', 'Choose the sites to scrape, then start again.'); return; }
    closeModal();
    try {
      const res = await fetch('/api/scrape', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(config),
      });
      const data = await res.json().catch(() => ({}));
      if (res.status === 403) showToast('info', 'View-only link', 'Scraping can only be started on the host laptop.');
      else if (data.status === 'running') showToast('info', 'Already scraping', 'Wait for the current run to finish.');
      else showToast('info', 'Scraping started', `${config.sources.length} site${config.sources.length > 1 ? 's' : ''}. A popup appears as each one finishes.`);
    } catch (err) {
      showToast('error', 'Could not start scraping', 'The app is not answering. Is python app.py still running?');
    }
  });

  // Public (tunnel) visitors get a read-only page: no scrape button
  fetch('/api/whoami').then(r => r.json()).then(w => {
    if (!w.can_edit) $('trigger-scrape-btn')?.classList.add('hidden');
  }).catch(() => {});

  $('action-dismiss-btn')?.addEventListener('click', async () => {
    $('action-banner').classList.add('hidden');
    try { await fetch('/api/alerts/dismiss', { method: 'POST' }); } catch (e) { /* ignore */ }
  });

  window.addEventListener('keydown', e => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); $('search-input')?.focus(); }
    if (e.key === 'Escape') {
      closeDetailDrawer();
      if (!modal.classList.contains('hidden')) closeModal();
    }
  });
}

// ─────────────────────────────────────────────
// 8. Helpers
// ─────────────────────────────────────────────
function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function safeUrl(url) {
  return /^https?:\/\//i.test(String(url || '')) ? url : '#';
}

function isNewToday(item) {
  const today = new Date().toISOString().slice(0, 10);
  return String(item.is_new).toLowerCase() === 'true' && String(item.date_scraped || '').slice(0, 10) === today;
}

function tidyStipend(s) {
  return String(s || '').replace(/₹\s+/g, '₹').replace(/\s*-\s*/g, '–').replace(/\s+\/\s*/g, '/').trim();
}

function formatDate(s) {
  const m = String(s || '').match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return String(s || '');
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${Number(m[3])} ${months[Number(m[2]) - 1]} ${m[1]}`;
}
