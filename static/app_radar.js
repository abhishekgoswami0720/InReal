/**
 * InReal Dashboard
 * Corporate Polished UI with Genuine Company Logos, Consistent Actions, and Robust Filtering
 */

let allInternships = [];
let activeLocation = 'all';
let activeStipend = 'all';
let activeSource = 'all';
let activeRoleType = 'all';
let activeModeration = 'verified';   // scam check: show only listings it passed
let showBookmarkedOnly = false;
// One dashboard, two doors. /admin: this laptop, no sign-in. /app: the same dashboard (search,
// Load 5 more, scam check) behind Google sign-in; the account comes from Supabase.
const CFG = window.INREAL || {};
const USER_MODE = CFG.mode === 'user';
let sbUserId = null;   // the signed-in account on /app (set by requireSignIn)
const sb = (USER_MODE && window.supabase && CFG.supabaseUrl && CFG.supabaseKey)
  ? window.supabase.createClient(CFG.supabaseUrl, CFG.supabaseKey) : null;
// /app keeps each account's saved posts apart (requireSignIn switches the key to the account's)
let BOOKMARK_KEY = 'inreal_bookmarks';
let bookmarks = JSON.parse(localStorage.getItem(BOOKMARK_KEY) || '[]');
let activeDrawerJob = null;
let hiddenByProfile = 0;   // posts the profile's rules hide right now (applyFiltersAndRender)
let scrapeRunning = false;   // a search is scraping the sites right now (/api/scrape/status)
let canEdit = true;
// The search on screen: Search Internships starts a new one and the list shows only its results
const VIEW_KEY = 'inreal_view_run';
let viewRun = (() => { try { return localStorage.getItem(VIEW_KEY) || ''; } catch (e) { return ''; } })();
let showAllSaved = false;
// Each visit starts with an empty list: the shared list on the laptop is no longer wiped on refresh
// (that lost verdicts still being saved, and other people's results), so the page itself
// shows nothing until a search starts. "Show recent results" shows everything checked lately.
let freshVisit = true;
// The search on screen, exactly as it was asked for: "Search more" repeats it on the same sites only
let lastSearch = null;
let restoredRun = '';   // the search remembered from an earlier visit, until the first loadData checks it
// 30 Oct: a visit two days later still opened on that old search, as if its posts were current.
// A search older than this is not put back on screen; the page offers to run it again instead.
const STALE_HOURS = 6;
let staleRun = '';      // the old search that was not restored (for the "search again" offer)
function runTime(tag) {
  const m = (tag || '').match(/^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})/);
  return m ? new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]) : null;
}
function runAgeHours(tag) {
  const t = runTime(tag);
  return t ? (Date.now() - t.getTime()) / 3600000 : 0;
}
function runWhen(tag) {
  const t = runTime(tag);
  if (!t) return '';
  const hm = t.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false });
  const days = Math.floor((new Date().setHours(0, 0, 0, 0) - new Date(t).setHours(0, 0, 0, 0)) / 86400000);
  if (days <= 0) return `today at ${hm}`;
  if (days === 1) return `yesterday at ${hm}`;
  return `${days} days ago (${t.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}, ${hm})`;
}
function dropStaleView() {
  if (!viewRun || scrapeRunning || runAgeHours(viewRun) < STALE_HOURS) return false;
  staleRun = viewRun;
  viewRun = ''; freshVisit = true; lastSearch = null; restoredRun = '';
  try { localStorage.removeItem(VIEW_KEY); } catch (e) {}
  displayOrder.clear(); renderedIds.clear();
  return true;
}
function startNewView(tag) {
  if (!tag) return;
  viewRun = tag; showAllSaved = false; freshVisit = false;
  try { localStorage.setItem(VIEW_KEY, tag); } catch (e) { /* private window */ }
  displayOrder.clear(); renderedIds.clear(); verifiedSeen = null;
  applyFiltersAndRender(); updateViewNote();
}
const displayOrder = new Map();   // id -> position the card was first shown at
const renderedIds = new Set();    // cards already on screen: only new ones play the slide-in
let verifiedSeen = null;          // ids that had passed the check at the last reload

// Profile from the sign-up form, kept in this browser: field, experience, preferred companies, sites
const PROFILE_KEY = 'inreal_profile';
let profile = readProfile();
let fieldLabels = { ai_ml: 'AI / Machine Learning' };
function readProfile() {
  try { return JSON.parse(localStorage.getItem(PROFILE_KEY) || 'null'); } catch (e) { return null; }
}
function writeProfile(p) {
  // on /app the copy in this browser is marked with its account, so the next account to sign in
  // here never takes it for its own (19 Oct: a new account skipped the profile form)
  if (USER_MODE && sbUserId) p = { ...p, owner: sbUserId };
  profile = p;
  try { localStorage.setItem(PROFILE_KEY, JSON.stringify(p)); } catch (e) { /* private window: kept for this visit */ }
}
const isUnpaid = (item) => /unpaid/i.test(String(item.stipend || ''));

// ---- What the profile changes in the list ----
// Filters (section 4) hide a post only when the post states the thing: no stated stipend, mode or
// duration means it stays. Roles (2) and skills (3) never hide anything; they decide the order.
const isRemotePost = (item) => String(item.location_type || '').toLowerCase() === 'remote'
  || /\b(remote|work from home|wfh)\b/i.test(String(item.location || ''));
function durationMonths(item) {
  const m = String(item.duration || '').match(/(\d+(?:\.\d+)?)\s*(month|week|mo\b)/i);
  if (!m) return null;
  return /week/i.test(m[2]) ? Number(m[1]) / 4.3 : Number(m[1]);
}
// The profile's rules show up as chips under Filters (26 Oct: they hid 34 of 36 posts while the
// Filters panel said nothing was on). A chip's ✕ switches that rule off for this visit only.
const prefsOff = { stipend: false, mode: false, duration: false, paid: false };
function profileRules(p) {
  if (!p) return [];
  const out = [];
  if (p.experience && p.experience !== '0') out.push({ key: 'paid', label: 'Paid only' });
  if (Number(p.min_stipend || 0) > 0) out.push({ key: 'stipend', label: `₹${Number(p.min_stipend).toLocaleString('en-IN')}+ a month` });
  if (p.work_mode === 'remote') out.push({ key: 'mode', label: 'Remote only' });
  if (p.work_mode === 'office') out.push({ key: 'mode', label: 'Office / hybrid only' });
  if (p.max_duration && p.max_duration !== 'any') out.push({ key: 'duration', label: `Up to ${p.max_duration} months` });
  return out;
}
const activeProfileRules = () => profileRules(profile).filter(r => !prefsOff[r.key]);

function failsPreferences(item, p) {
  const min = prefsOff.stipend ? 0 : Number(p.min_stipend || 0);
  if (min > 0) {
    if (isUnpaid(item)) return true;
    const num = Number(item.stipend_numeric || 0);
    const inr = !item.stipend_currency || /inr|₹|rs/i.test(String(item.stipend_currency));
    if (num > 0 && inr && num < min) return true;
  }
  if (!prefsOff.mode && p.work_mode === 'remote' && !isRemotePost(item)) return true;
  if (!prefsOff.mode && p.work_mode === 'office' && isRemotePost(item)) return true;
  if (!prefsOff.duration && p.max_duration && p.max_duration !== 'any') {
    const months = durationMonths(item);
    if (months && months > Number(p.max_duration) + 0.01) return true;
  }
  return false;
}
function escapeRe(x) { return x.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }
// skills the post asks for (its skill list, title and text) that are in the profile
function matchedSkills(item, p) {
  const skills = (p && p.skills) || [];
  if (!skills.length) return [];
  const listed = String(item.required_skills || '').toLowerCase().split(/\s*[,;|]\s*/).filter(Boolean);
  const text = `${item.required_skills || ''} ${item.role_title || ''} ${item.description || ''}`.toLowerCase();
  return skills.filter(sk => {
    const s = sk.toLowerCase();
    if (listed.includes(s)) return true;
    if (s.length <= 2) return false;   // "R", "C": only from the post's own skill list
    return new RegExp(`(^|[^a-z0-9+#])${escapeRe(s)}($|[^a-z0-9+#])`).test(text);
  });
}
function roleHit(item, p) {
  const roles = (p && p.roles) || [];
  if (!roles.length) return false;
  const defs = ((window.PROFILE_ROLES || {})[p.field] || []).filter(r => roles.includes(r.key));
  const title = ` ${String(item.role_title || '').toLowerCase()} `;
  return defs.some(r => r.words.some(w => title.includes(w)));
}
function matchScore(item) {
  if (!profile) return 0;
  return (isPreferred(item) ? 1000 : 0) + (roleHit(item, profile) ? 100 : 0) + 10 * matchedSkills(item, profile).length;
}
function isPreferred(item) {
  if (!profile || !profile.companies || !profile.companies.length) return false;
  const name = String(item.company_name || '').toLowerCase();
  return profile.companies.some(c => c.length >= 2 && name.includes(c.toLowerCase()));
}

// Genuine SVGs for company/organization logos
const companyLogos = {
  anthropic: `<svg viewBox="0 0 24 24" width="24" height="24" fill="#0F172A"><path d="M14.05 3.5h3.45L10.95 20.5H7.5L14.05 3.5zm-4.1 0h3.45L6.85 20.5H3.4L9.95 3.5z"/></svg>`,
  deepmind: `<svg viewBox="0 0 24 24" width="24" height="24"><path fill="#4285F4" d="M12 2L15 9L22 12L15 15L12 22L9 15L2 12L9 9Z"/></svg>`,
  maxplanck: `<svg viewBox="0 0 24 24" width="24" height="24" fill="#0F172A"><circle cx="12" cy="12" r="9" stroke="#0F172A" stroke-width="1.8" fill="none"/><circle cx="12" cy="12" r="4" fill="#0F172A"/></svg>`,
  mistral: `<svg viewBox="0 0 24 24" width="24" height="24"><rect x="3" y="4" width="5" height="16" fill="#F97316"/><rect x="10" y="4" width="5" height="10" fill="#EA580C"/><rect x="17" y="4" width="5" height="16" fill="#C2410C"/></svg>`,
  iisc: `<svg viewBox="0 0 24 24" width="24" height="24" fill="#0D9488"><path d="M12 3L2 9l10 6 10-6-10-6zm0 14l-8-4.8v3.6L12 21l8-5.2v-3.6L12 17z"/></svg>`,
  cohere: `<svg viewBox="0 0 24 24" width="24" height="24"><circle cx="8" cy="12" r="5" fill="#39594C"/><circle cx="16" cy="12" r="5" fill="#FF7759"/></svg>`,
  default: `<svg viewBox="0 0 24 24" width="24" height="24" fill="#64748B"><path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 3c1.66 0 3 1.34 3 3s-1.34 3-3 3-3-1.34-3-3 1.34-3 3-3zm6 12H6v-1.4c0-2 4-3.1 6-3.1s6 1.1 6 3.1V18z"/></svg>`
};

function getCompanyLogoSvg(companyName) {
  const norm = (companyName || '').toLowerCase();
  if (norm.includes('anthropic')) return companyLogos.anthropic;
  if (norm.includes('deepmind') || norm.includes('google')) return companyLogos.deepmind;
  if (norm.includes('max planck') || norm.includes('mpi')) return companyLogos.maxplanck;
  if (norm.includes('mistral')) return companyLogos.mistral;
  if (norm.includes('iisc') || norm.includes('bangalore')) return companyLogos.iisc;
  if (norm.includes('cohere')) return companyLogos.cohere;
  return companyLogos.default;
}

document.addEventListener('DOMContentLoaded', () => {
  initGlassTranslucentBackground();
  bindEventHandlers();
  if (USER_MODE) { requireSignIn().then(ok => { if (ok) startDashboard(); }); return; }
  startDashboard();
});

function startDashboard() {
  initProfile();
  // a refresh keeps the last search of this browser on screen (26 Oct: the list went empty and the
  // results were only under "Last 3 days"); loadData drops it if it has been pruned
  dropStaleView();
  freshVisit = !viewRun;
  restoredRun = viewRun;   // checked once, by the first loadData
  if (viewRun && profile) lastSearch = { field: profile.field, sources: (profile.sources || []).slice(), regions: (profile.regions || []).slice(), run_tag: viewRun };
  updateViewNote();
  startSession();
  pollScraperStatus();
  pollAlerts();
  pollModeration();
  updateBookmarkCounter();
  loadApplications();
  loadReports();
}

// ==========================================
// 1. Subtle Translucent 3D Ambient Mesh
// ==========================================
// ==========================================
// 2. Data Fetching & Overview Metrics
// ==========================================
async function loadData() {
  try {
    const res = await fetch('/api/internships');
    const data = await res.json();
    allInternships = data || [];
    // A search remembered from an earlier visit may have been pruned: forget it. Only on the first
    // load after the page opens (26 Oct: this ran during a new search too, before its first site was
    // saved, so the page forgot the search and stayed on "Nothing searched yet" the whole time)
    if (restoredRun) {
      if (viewRun === restoredRun && !allInternships.some(r => r.last_run === viewRun) && !scrapeRunning) {
        viewRun = ''; freshVisit = true; lastSearch = null;
        try { localStorage.removeItem(VIEW_KEY); } catch (e) {}
        updateViewNote();
      }
      restoredRun = '';
    }
    announceNewlyVerified(allInternships);
    setTimeout(remindClosingSaved, 1500);   // after bookmarks and applications have loaded

    populateSourceFilter(allInternships);
    applyFiltersAndRender();
  } catch (err) {
    console.error('Failed to load internships:', err);
  }
}

function populateSourceFilter(internships) {
  const sourceSelect = document.getElementById('source-filter');
  if (!sourceSelect) return;
  const sources = new Set(internships.map(i => i.source_platform).filter(Boolean));
  if (activeSource !== 'all') sources.add(activeSource);
  sourceSelect.innerHTML = '<option value="all">Source: All</option>';
  sources.forEach(src => {
    const opt = document.createElement('option');
    opt.value = src;
    opt.textContent = `Source: ${src}`;
    sourceSelect.appendChild(opt);
  });
  sourceSelect.value = activeSource;   // the list reloads as verdicts arrive; keep the user's choice
}

function renderOverviewStats(shown, base) {
  // Headline numbers = the cards currently shown (all filters applied, incl. the scam-check filter)
  shown = shown || [];
  base = base || shown;
  const verified = shown;
  const total = shown.length;
  const paidCount = verified.filter(i => {
    const val = Number(i.stipend_numeric || 0);
    return val > 0 || (i.stipend && !i.stipend.toLowerCase().includes('unpaid'));
  }).length;
  const newCount = verified.filter(isNewToday).length;

  const totalEl = document.getElementById('stat-total-jobs');
  const paidEl = document.getElementById('stat-paid-jobs');
  const newEl = document.getElementById('stat-new-jobs');

  if (totalEl) totalEl.innerText = total;
  if (paidEl) paidEl.innerText = paidCount;
  if (newEl) newEl.innerText = newCount || '0';
  document.getElementById('stat-new-wrap')?.classList.toggle('hidden', !newCount);
  const countLine = document.getElementById('list-count');
  if (countLine) countLine.parentElement.classList.toggle('invisible', !total);

  const countAll = document.getElementById('count-all');
  const countIndia = document.getElementById('count-india');
  const countRemote = document.getElementById('count-remote');
  const countGlobal = document.getElementById('count-global');

  if (countAll) countAll.innerText = base.length;
  if (countIndia) countIndia.innerText = base.filter(i => (i.location_type || '').toLowerCase() === 'india').length;
  if (countRemote) countRemote.innerText = base.filter(i => (i.location_type || '').toLowerCase() === 'remote').length;
  if (countGlobal) countGlobal.innerText = base.filter(i => (i.location_type || '').toLowerCase() === 'international').length;
}

// ==========================================
// 3. Card Grid Rendering with Corporate Polish & Real Logos
// ==========================================
function applyFiltersAndRender() {
  const searchInput = document.getElementById('search-input');
  const searchQuery = (searchInput ? searchInput.value : '').toLowerCase().trim();

  const matches = (item, ignoreLocation, ignoreProfile) => {
    // only this visit's search (saved posts are always reachable through "Saved")
    if (!showAllSaved && !showBookmarkedOnly) {
      if (freshVisit) return false;
      if (viewRun && item.last_run !== viewRun) return false;
    }
    if (showBookmarkedOnly && !bookmarks.includes(item.id)) return false;
    if (reported.has(item.id)) return false;   // you reported it: gone from your list

    // The student's profile: only their field, and unpaid posts only for 0 years of experience
    if (profile && !ignoreProfile) {
      if (profile.experience !== '0' && !prefsOff.paid && isUnpaid(item)) return false;
      if (failsPreferences(item, profile)) return false;
    }

    // Scam check verdict. Default: only what the check passed.
    const mod = item.moderation_status || '';
    if (activeModeration === 'verified' && mod !== 'approved') return false;
    if (activeModeration === 'verified_review' && mod !== 'approved' && mod !== 'review') return false;
    if (activeModeration === 'hide_blocked' && mod === 'blocked') return false;
    if (activeModeration === 'blocked' && mod !== 'blocked') return false;

    // Location filter (from segmented tabs or dropdown)
    if (!ignoreLocation && activeLocation !== 'all') {
      if ((item.location_type || '').toLowerCase() !== activeLocation.toLowerCase()) {
        return false;
      }
    }

    // Role Type filter
    if (activeRoleType !== 'all') {
      const roleStr = `${item.role_title || ''} ${item.role_type || ''}`.toLowerCase();
      if (!roleStr.includes(activeRoleType.toLowerCase())) {
        return false;
      }
    }

    // Source platform filter
    if (activeSource !== 'all' && item.source_platform !== activeSource) {
      return false;
    }

    // Stipend filter
    if (activeStipend === 'paid') {
      const num = Number(item.stipend_numeric || 0);
      if (num <= 0 && (!item.stipend || item.stipend.toLowerCase().includes('unpaid'))) return false;
    } else if (activeStipend === '20k') {
      if (Number(item.stipend_numeric || 0) < 20000) return false;
    } else if (activeStipend === '50k') {
      if (Number(item.stipend_numeric || 0) < 50000) return false;
    } else if (activeStipend === '100k') {
      if (Number(item.stipend_numeric || 0) < 100000) return false;
    }

    // Text search
    if (searchQuery) {
      const text = `${item.role_title || ''} ${item.company_name || ''} ${item.required_skills || ''} ${item.location || ''}`.toLowerCase();
      if (!text.includes(searchQuery)) return false;
    }

    return true;
  };

  // Every number on the page follows the filters (the location tabs count everything else that matches)
  const base = allInternships.filter(item => matches(item, true));
  const filtered = base.filter(item => matches(item, false));
  // Cards keep their place while verdicts arrive: anything not shown before goes to the end
  filtered.forEach(item => { if (!displayOrder.has(item.id)) displayOrder.set(item.id, displayOrder.size); });
  // preferred companies, then your roles, then the most matching skills; ties keep their place
  const score = new Map(filtered.map(item => [item.id, matchScore(item)]));
  filtered.sort((a, b) => (score.get(b.id) - score.get(a.id))
                          || (displayOrder.get(a.id) - displayOrder.get(b.id)));
  hiddenByProfile = profile ? allInternships.filter(item => matches(item, false, true)).length - filtered.length : 0;
  renderOverviewStats(filtered, base);
  renderProfileRules();
  updateFilterCount();
  renderListings(filtered);
}

// Company initials in a colour picked from the name, so each company looks the same everywhere
const LOGO_COLORS = ['#F97316', '#0EA5E9', '#10B981', '#8B5CF6', '#E11D48', '#F59E0B', '#14B8A6', '#6366F1', '#EC4899', '#0F766E'];
function logoFor(name) {
  const clean = String(name || '').replace(/<[^>]*>/g, '').trim();
  const words = clean.split(/\s+/).filter(w => /[a-z0-9]/i.test(w));
  const initials = (words.length > 1 ? words[0][0] + words[1][0] : (words[0] || '?').slice(0, 2)).toUpperCase();
  let h = 0;
  for (const ch of clean.toLowerCase()) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return { initials: escapeHtml(initials), color: LOGO_COLORS[h % LOGO_COLORS.length] };
}
// The company's logo over its initials (1 Nov). Only InReal's own copy (/static/logos/, made by
// logos.py from the logo the source site showed); while it loads, or if it fails, the initials show.
function logoImg(src) {
  return /^\/static\/logos\/[a-f0-9]{20}\.webp$/.test(String(src || '')) ? `<img src="${src}" alt="" loading="lazy" decoding="async">` : '';
}
function logoHtml(name, src, extra = '') {
  const lg = logoFor(name);
  return `<div class="jb-logo${extra ? ' ' + extra : ''}" style="background:${lg.color}" aria-hidden="true">${lg.initials}${logoImg(src)}</div>`;
}
document.addEventListener('error', (e) => {
  if (e.target && e.target.tagName === 'IMG' && e.target.parentElement?.classList.contains('jb-logo')) e.target.remove();
}, true);
const isWide = () => window.matchMedia('(min-width: 1280px)').matches;

function stipendTag(item) {
  const s = String(item.stipend || '').trim();
  if (!s) return '';
  if (isUnpaid(item)) return '<span class="jb-tag jb-tag-unpaid">Unpaid</span>';
  return `<span class="jb-tag jb-tag-money"><i class="ph ph-currency-inr"></i>${escapeHtml(s.replace(/\s*a month$/i, ' / month'))}</span>`;
}
function verdictTag(item) {
  const st = item.moderation_status || '';
  if (st === 'approved') return '<span class="jb-tag jb-tag-ok"><i class="ph ph-shield-check"></i>Verified</span>';
  if (st === 'review') return '<span class="jb-tag jb-tag-warn"><i class="ph ph-eye"></i>Needs a look</span>';
  if (st === 'blocked') return '<span class="jb-tag jb-tag-bad"><i class="ph ph-prohibit"></i>Likely scam</span>';
  if (st === 'expired') return '<span class="jb-tag jb-tag-wait"><i class="ph ph-link-break"></i>Closed</span>';
  return '<span class="jb-tag jb-tag-wait"><i class="ph ph-hourglass"></i>Being checked</span>';
}
function skillTag(item) {
  if (!profile) return '';
  const hits = matchedSkills(item, profile);
  if (!hits.length) return '';
  return `<span class="jb-tag jb-tag-skill" title="Your skills in this post: ${escapeHtml(hits.join(', '))}"><i class="ph ph-lightning"></i>${hits.length} of your skills</span>`;
}
function skillChip(item) { return skillTag(item); }

// the empty state's "Search Internships": the main button, or "Pick other sites" beside "Search the same sites again"
function setSearchBtn(main) {
  const b = document.getElementById('empty-search-btn');
  if (!b) return;
  b.classList.toggle('glass-btn-primary', main);
  b.lastChild.textContent = main ? 'Search Internships' : 'Pick other sites';
}

function renderListings(items) {
  const container = document.getElementById('listings-container');
  const emptyState = document.getElementById('empty-state');
  if (!container) return;

  if (items.length === 0) {
    container.innerHTML = '';
    renderedIds.clear();
    showDetailPlaceholder();
    const h = document.querySelector('#empty-state h3'), t = document.querySelector('#empty-state p');
    const btn = (id, on) => document.getElementById(id)?.classList.toggle('hidden', !on);
    const filtersOn = activeRoleType !== 'all' || activeLocation !== 'all' || activeStipend !== 'all' || activeSource !== 'all'
      || activeModeration !== 'verified' || !!(document.getElementById('search-input')?.value || '').trim();
    let title, text, search = false, recent = false, reset = false;
    const inScope = (viewRun && !showAllSaved) ? allInternships.filter(r => r.last_run === viewRun) : allInternships;
    const inReview = inScope.filter(r => r.moderation_status === 'review').length;
    const fieldEmpty = profile && !allInternships.some(r => String(r.field || 'ai_ml').split(';').includes(profile.field));
    const runRows = (viewRun && !showAllSaved && !showBookmarkedOnly) ? allInternships.filter(r => r.last_run === viewRun) : [];
    const runChecked = runRows.filter(r => ['approved', 'review', 'blocked', 'expired'].includes(r.moderation_status)).length;
    const runChecking = runRows.filter(r => ['', 'checking'].includes(r.moderation_status || '')).length;
    const runHeld = runRows.filter(r => r.moderation_status === 'held').length;
    if (viewRun && !showAllSaved && !showBookmarkedOnly && !freshVisit && !runChecked) {
      // nothing judged yet in this search: the filters are not the reason, say what is happening
      if (runChecking) {
        title = `Checking ${runChecking} internship${runChecking === 1 ? '' : 's'} for scams…`;
        text = scrapeRunning ? 'They show up here in a few seconds. The slower sites are still being searched.'
                             : 'They show up here in a few seconds.';
      } else if (scrapeRunning) {
        title = 'Searching the sites…';
        text = 'The first internships show up here as soon as the fastest sites finish and pass the scam check.';
      } else if (runHeld) {
        title = `${runHeld} found, not checked yet`;
        text = 'Use "Load 5 more" below to put them through the scam check.';
      } else {
        title = 'No new internships this time';
        text = 'The sites had nothing new for this field. Try more sites, another region or another field.';
        search = canEdit;
      }
      if (h) h.textContent = title;
      if (t) t.textContent = text;
      btn('empty-again-btn', false); btn('empty-search-btn', search); btn('empty-recent-btn', false); btn('empty-reset-btn', false);
      if (emptyState) { emptyState.classList.remove('hidden'); emptyState.classList.add('flex'); }
      return;
    }
    let again = false;
    if (freshVisit && staleRun && !showAllSaved && !showBookmarkedOnly) {
      title = `Your last search was ${runWhen(staleRun)}`;
      text = 'Internships change every day and older posts may already be closed. Search the same sites again for live results, or pick new ones.';
      again = canEdit; search = canEdit; recent = true;
      if (h) h.textContent = title;
      if (t) t.textContent = text;
      btn('empty-again-btn', again); btn('empty-search-btn', search); btn('empty-recent-btn', recent); btn('empty-reset-btn', false);
      setSearchBtn(!again);
      if (emptyState) { emptyState.classList.remove('hidden'); emptyState.classList.add('flex'); }
      return;
    }
    btn('empty-again-btn', false);
    setSearchBtn(true);
    if (showBookmarkedOnly) {
      title = 'No saved internships yet';
      text = 'Tap the bookmark on any post to keep it here.';
    } else if (freshVisit && !showAllSaved) {
      title = 'Start a search';
      text = 'Pick the sites to search. Posts show up here as each site finishes and passes the scam check.';
      search = canEdit; recent = true;
    } else if (activeModeration === 'verified' && inReview && !filtersOn) {
      title = 'Nothing verified yet';
      text = `${inReview} post${inReview === 1 ? ' was' : 's were'} checked but need${inReview === 1 ? 's' : ''} a second look. Set "Scam check" in Filters to "Verified + needs a look" to see ${inReview === 1 ? 'it' : 'them'}.`;
    } else if (hiddenByProfile && !filtersOn) {
      title = `Your profile hides all ${hiddenByProfile} of them`;
      text = `Your preferences (${activeProfileRules().map(r => r.label).join(', ')}) leave nothing to show. Turn them off here for now, or change them in your profile.`;
      reset = true;
    } else if (filtersOn) {
      title = 'Nothing matches these filters';
      text = 'Try another location or stipend, or clear the filters.';
      reset = true;
    } else if (viewRun && !showAllSaved) {
      const waiting = inScope.filter(r => r.moderation_status === 'held').length;
      title = inScope.length ? 'Nothing verified from this search yet' : 'Searching…';
      text = inScope.length
        ? (waiting ? 'Use "Load 5 more" below to put the next posts through the scam check.' : 'The posts found are still being checked. This list fills in by itself.')
        : 'Posts show up here as each site finishes.';
      recent = true;
    } else {
      title = fieldEmpty ? `No ${fieldLabels[profile.field] || profile.field} internships yet` : 'Nothing here yet';
      text = 'Search the sites for your field. New posts show up as each site finishes.';
      search = canEdit;
    }
    if (h) h.textContent = title;
    if (t) t.textContent = text;
    btn('empty-search-btn', search); btn('empty-recent-btn', recent); btn('empty-reset-btn', reset);
    if (emptyState) { emptyState.classList.remove('hidden'); emptyState.classList.add('flex'); }
    return;
  }

  if (emptyState) { emptyState.classList.add('hidden'); emptyState.classList.remove('flex'); }

  const selected = activeDrawerJob && activeDrawerJob.id;
  let fresh = 0;
  container.innerHTML = items.map((item) => {
    const enter = !renderedIds.has(item.id);
    const delay = enter ? Math.min(fresh++, 10) : 0;
    const saved = bookmarks.includes(item.id);
    const id = escapeHtml(item.id);
    const meta = [
      item.company_name ? `<span class="font-bold text-slate-700">${escapeHtml(item.company_name)}</span>` : '',
      `<span><i class="ph ph-map-pin"></i>${escapeHtml(item.location || 'Location not stated')}</span>`,
      item.duration ? `<span><i class="ph ph-clock"></i>${escapeHtml(item.duration)}</span>` : '',
    ].filter(Boolean).join('');
    return `
      <article class="jb-card${selected === item.id ? ' is-selected' : ''}${enter ? ' jb-enter' : ''}"${enter ? ` style="--i:${delay}"` : ''} data-id="${id}" tabindex="0" role="button"
        aria-label="${escapeHtml(item.role_title || 'Internship')} at ${escapeHtml(item.company_name || 'company')}">
        ${logoHtml(item.company_name, item.logo)}
        <div class="min-w-0">
          <h3 class="jb-card-title">${escapeHtml(item.role_title || 'Internship')}</h3>
          <div class="jb-card-meta">${meta}</div>
          <div class="jb-tags">
            ${isNewToday(item) ? '<span class="jb-tag jb-tag-new">New</span>' : ''}
            ${stipendTag(item)}
            ${verdictTag(item)}
            ${isPreferred(item) ? '<span class="jb-tag jb-tag-pick"><i class="ph ph-star"></i>Your pick</span>' : ''}
            ${appliedTag(item)}
            ${closingTag(item)}
            ${skillTag(item)}
            ${item.trust_flags ? `<span class="jb-tag jb-tag-warn" title="${escapeHtml(item.trust_flags)}"><i class="ph ph-warning"></i>Note</span>` : ''}
          </div>
          <div class="jb-source">${escapeHtml(item.source_platform || '')}</div>
        </div>
        <button type="button" class="jb-save${saved ? ' on' : ''}" aria-pressed="${saved}" aria-label="${saved ? 'Remove from saved' : 'Save'}" data-save>
          <i class="ph ${saved ? 'ph-fill ph-bookmark-simple' : 'ph-bookmark-simple'}"></i>
        </button>
      </article>`;
  }).join('');
  items.forEach(i => renderedIds.add(i.id));
  // after the slide-in, drop the class so a later re-render of the same card doesn't replay it
  setTimeout(() => container.querySelectorAll('.jb-card.jb-enter').forEach(c => c.classList.remove('jb-enter')), 1200);

  // wide screens: the panel always shows a post (the one open, else the best match)
  if (isWide()) {
    const keep = selected && items.some(i => i.id === selected);
    if (!keep) openDetailDrawer(items[0].id, { quiet: true });
  }
}

// Cards open and save through one listener reading data-id. (26 Oct security pass: the id used to be
// pasted into onclick="openDetailDrawer('…')", and the browser turns &#39; back into a quote before
// running it, so a post id with a quote in it could run its own script.)
document.addEventListener('click', (e) => {
  const card = e.target.closest('.jb-card[data-id]');
  if (!card) return;
  if (e.target.closest('[data-save]')) { e.stopPropagation(); toggleBookmark(card.dataset.id); return; }
  openDetailDrawer(card.dataset.id);
});
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Enter' && e.key !== ' ') return;
  const card = e.target.closest && e.target.closest('.jb-card[data-id]');
  if (!card || e.target !== card) return;
  e.preventDefault();
  openDetailDrawer(card.dataset.id);
});

function renderProfileRules() {
  const box = document.getElementById('profile-rules');
  const rules = profileRules(profile);
  if (box) {
    box.classList.toggle('hidden', !rules.length);
    document.getElementById('profile-rule-chips').innerHTML = rules.map(r => prefsOff[r.key]
      ? `<button type="button" class="jb-rule off" data-rule="${r.key}" title="Turn this back on">${escapeHtml(r.label)}</button>`
      : `<button type="button" class="jb-rule" data-rule="${r.key}" title="Turn off for now (your profile stays the same)">${escapeHtml(r.label)}<i class="ph ph-x"></i></button>`).join('');
  }
  const note = document.getElementById('hidden-note');
  if (note) {
    note.classList.toggle('hidden', !hiddenByProfile);
    note.innerHTML = hiddenByProfile
      ? ` · <b class="text-slate-700">${hiddenByProfile}</b> hidden by your profile <button type="button" class="text-orange-600 font-bold hover:underline" data-show-all-rules>Show them</button>` : '';
  }
}
function setProfileRules(off) {
  profileRules(profile).forEach(r => { prefsOff[r.key] = off; });
  displayOrder.clear(); renderedIds.clear();
  applyFiltersAndRender();
}
document.addEventListener('click', (e) => {
  const chip = e.target.closest('[data-rule]');
  if (chip) { prefsOff[chip.dataset.rule] = !prefsOff[chip.dataset.rule]; displayOrder.clear(); renderedIds.clear(); applyFiltersAndRender(); return; }
  if (e.target.closest('[data-show-all-rules]')) setProfileRules(true);
});

// ---- Folding side panels (wide screens), remembered in this browser ----
const PANELS_KEY = 'inreal_panels';
const panels = (() => { try { return JSON.parse(localStorage.getItem(PANELS_KEY)) || {}; } catch (e) { return {}; } })();
function applyPanels() {
  const main = document.querySelector('main.jb');
  if (!main) return;
  main.classList.toggle('side-collapsed', !!panels.side);
  main.classList.toggle('detail-collapsed', !!panels.detail);
  document.querySelectorAll('[data-panel-toggle]').forEach(b => b.setAttribute('aria-expanded', String(!panels[b.dataset.panelToggle])));
}
function setPanel(key, folded) {
  panels[key] = folded;
  try { localStorage.setItem(PANELS_KEY, JSON.stringify(panels)); } catch (e) { /* private window */ }
  applyPanels();
  if (key === 'detail' && !folded && !activeDrawerJob) applyFiltersAndRender();   // fill it with the best match
}
document.addEventListener('click', (e) => {
  const b = e.target.closest('[data-panel-toggle]');
  if (b) setPanel(b.dataset.panelToggle, !panels[b.dataset.panelToggle]);
});
document.addEventListener('DOMContentLoaded', applyPanels);

function showDetailPlaceholder() {
  activeDrawerJob = null;
  document.getElementById('detail-empty')?.classList.remove('hidden');
}

// ==========================================
// 4. Slide-Over Detail Drawer
// ==========================================
function openDetailDrawer(id, opts) {
  const item = allInternships.find(i => i.id === id);
  if (!item) return;
  const quiet = opts && opts.quiet;

  activeDrawerJob = item;
  document.getElementById('detail-empty')?.classList.add('hidden');
  if (!quiet && isWide() && panels.detail) setPanel('detail', false);   // a click on a card unfolds the panel
  document.querySelectorAll('.jb-card.is-selected').forEach(c => c.classList.remove('is-selected'));
  document.querySelector(`.jb-card[data-id="${CSS.escape(String(id))}"]`)?.classList.add('is-selected');
  const logoBox = document.getElementById('drawer-logo');
  if (logoBox) { const lg = logoFor(item.company_name); logoBox.innerHTML = lg.initials + logoImg(item.logo); logoBox.style.background = lg.color; }
  const body = document.getElementById('detail-body');
  if (body) {
    body.scrollTop = 0;
    if (!quiet) { body.classList.remove('jb-swap'); void body.offsetWidth; body.classList.add('jb-swap'); }   // the new post fades in
  }
  document.getElementById('drawer-role-title').innerText = item.role_title || 'Opportunity';
  document.getElementById('drawer-company-name').innerText = item.company_name || '';
  document.getElementById('drawer-location').innerText = item.location || 'Location not stated';
  document.getElementById('drawer-duration').innerText = item.duration || 'Duration not stated';
  document.getElementById('drawer-stipend').innerText = item.stipend || 'Not stated';
  document.getElementById('drawer-deadline').innerText = item.application_deadline || 'Not stated';
  document.getElementById('drawer-source').innerText = item.source_platform || '';
  document.getElementById('drawer-date').innerText = item.date_scraped || '';
  document.getElementById('drawer-org-badge').innerText = item.org_type || (item.source_platform ? `Posted on ${item.source_platform}` : '');

  const applyLink = document.getElementById('drawer-apply-link');
  applyLink.href = safeUrl(item.apply_link);

  // scam-check verdict with its reasons
  const modBox = document.getElementById('drawer-mod-box');
  const view = MOD_VIEWS[item.moderation_status || ''] || MOD_VIEWS[''];
  modBox.className = `p-3.5 rounded-xl border text-xs ${view.box}`;
  const risk = item.scam_risk !== '' && item.scam_risk != null && !isNaN(Number(item.scam_risk)) ? ` · scam risk ${Math.round(Number(item.scam_risk) * 100)}%` : '';
  document.getElementById('drawer-mod-title').innerText = `${view.label}${risk}`;
  const reasons = String(item.moderation_reasons || '').split(' | ').map(r => r.trim()).filter(Boolean);
  document.getElementById('drawer-mod-reasons').innerHTML = reasons.map(plainReason).filter(Boolean).map(r => `<li>${escapeHtml(r)}</li>`).join('');
  // A wrong block can be undone by hand: the post goes to "needs a look", never straight to verified
  const unblock = document.getElementById('drawer-unblock-btn');
  if (unblock) {
    unblock.classList.toggle('hidden', item.moderation_status !== 'blocked');
    unblock.disabled = false;
    unblock.onclick = async () => {
      unblock.disabled = true;
      try {
        const res = await fetch('/api/moderation/unblock', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: item.id }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        await loadData();
        openDetailDrawer(item.id);
      } catch (e) {
        unblock.disabled = false;
        console.error('Unblock failed:', e);
      }
    };
  }

  const desc = String(item.description || '').trim();
  document.getElementById('drawer-desc-box').classList.toggle('hidden', !desc);
  document.getElementById('drawer-description').innerHTML = describeHtml(desc);

  const skillsContainer = document.getElementById('drawer-skills-list');
  const skills = (item.required_skills || '').split(',').map(s => s.trim()).filter(Boolean);
  skillsContainer.innerHTML = skills.length
    ? skills.map(s => `<span class="px-2.5 py-1 bg-slate-100 border border-slate-200 text-slate-700 rounded-md text-xs font-semibold">${escapeHtml(s)}</span>`).join('')
    : '<span class="text-xs text-slate-500">The post does not list skills.</span>';

  const trustBox = document.getElementById('drawer-trust-box');
  const trustText = document.getElementById('drawer-trust-flags');
  if (trustBox && trustText) {
    if (item.trust_flags) {
      trustText.innerHTML = String(item.trust_flags).split(';').map(f => f.trim()).filter(Boolean)
        .map(f => `<li>${escapeHtml(f)}</li>`).join('');
      trustBox.classList.remove('hidden');
    } else {
      trustBox.classList.add('hidden');
    }
  }

  updateDrawerBookmarkIcon();
  updateDrawerApplied();
  if (quiet || isWide()) return;   // wide screens: the panel is already beside the list

  const overlay = document.getElementById('detail-drawer-overlay');
  const drawer = document.getElementById('detail-drawer');
  overlay.classList.remove('hidden');
  setTimeout(() => drawer.classList.remove('translate-x-full'), 10);
}

function closeDetailDrawer() {
  const overlay = document.getElementById('detail-drawer-overlay');
  const drawer = document.getElementById('detail-drawer');
  drawer.classList.add('translate-x-full');
  setTimeout(() => overlay.classList.add('hidden'), 200);
}

function updateDrawerBookmarkIcon() {
  const btn = document.getElementById('drawer-bookmark-btn');
  if (!btn || !activeDrawerJob) return;
  const isBookmarked = bookmarks.includes(activeDrawerJob.id);
  btn.innerHTML = `<i class="ph ${isBookmarked ? 'ph-fill ph-bookmark-simple text-rose-500' : 'ph-bookmark-simple'} text-lg"></i>`;
  btn.setAttribute('aria-label', isBookmarked ? 'Remove from saved' : 'Save');
}

// ==========================================
// 5. Bookmarks & Local Storage
// ==========================================
function toggleBookmark(id) {
  if (bookmarks.includes(id)) {
    bookmarks = bookmarks.filter(b => b !== id);
  } else {
    bookmarks.push(id);
  }
  try { localStorage.setItem(BOOKMARK_KEY, JSON.stringify(bookmarks)); } catch (e) { /* private window */ }
  updateBookmarkCounter();
  applyFiltersAndRender();
  if (activeDrawerJob && activeDrawerJob.id === id) {
    updateDrawerBookmarkIcon();
  }
}

function updateBookmarkCounter() {
  const count = bookmarks.length;
  const counter = document.getElementById('bookmark-count');
  if (counter) counter.innerText = count;
}

// ==========================================
// 6. Scraper Status & Activity Feeds
// ==========================================
async function pollScraperStatus() {
  try {
    const res = await fetch('/api/scrape/status');
    const data = await res.json();
    const isRunning = data.status === 'running' || data.status === 'queued';
    if (isRunning !== scrapeRunning) {
      scrapeRunning = isRunning;
      applyFiltersAndRender();
      updateHeldUI(lastModCounts || {});
    }
    handleScrapeProgress(data.progress, isRunning);

    const dot = document.getElementById('ping-dot');
    const text = document.getElementById('scraper-status-text');

    setSearchMoreBusy(isRunning);
    if (isRunning) {
      if (dot) dot.className = 'w-2 h-2 rounded-full bg-orange-500 animate-pulse';
      if (text) text.innerText = data.status === 'queued' ? 'Queued...' : 'Scanning...';
    } else {
      if (dot) dot.className = 'w-2 h-2 rounded-full bg-emerald-500';
      if (text) text.innerText = 'System Ready';
    }
  } catch (e) {}

  setTimeout(pollScraperStatus, 3500);
}

async function pollAlerts() {
  try {
    const res = await fetch('/api/alerts');
    const data = await res.json();
    const banner = document.getElementById('action-banner');

    if (data.alert) {
      document.getElementById('action-title').innerText = data.alert.title || `Action Required: ${data.alert.source || 'Scraper'}`;
      document.getElementById('action-message').innerText = data.alert.message || 'Action required in browser window.';
      banner.classList.remove('hidden');
    } else {
      banner.classList.add('hidden');
    }
  } catch (e) {}
  setTimeout(pollAlerts, 3000);
}

// ==========================================
// 7. Event Handlers & Corporate Filter Bindings
// ==========================================
function bindEventHandlers() {
  document.getElementById('search-input')?.addEventListener('input', applyFiltersAndRender);
  document.getElementById('mod-filter')?.addEventListener('change', (e) => {
    activeModeration = e.target.value;
    applyFiltersAndRender();
    updateViewNote();
  });

  // Dropdown 1: Role Type
  document.getElementById('role-type-filter')?.addEventListener('change', (e) => {
    activeRoleType = e.target.value;
    applyFiltersAndRender();
  });

  // Dropdown 2: Location Select
  document.getElementById('location-select-filter')?.addEventListener('change', (e) => {
    activeLocation = e.target.value;
    // Sync segmented tabs
    document.querySelectorAll('#location-tabs .pill-segmented-item').forEach(b => {
      b.classList.toggle('active', b.getAttribute('data-val') === activeLocation);
    });
    applyFiltersAndRender();
  });

  // Dropdown 3: Min. Stipend
  document.getElementById('stipend-select-filter')?.addEventListener('change', (e) => {
    activeStipend = e.target.value;
    // Sync segmented tabs
    document.querySelectorAll('#stipend-filters .pill-segmented-item').forEach(b => {
      b.classList.toggle('active', b.getAttribute('data-val') === activeStipend);
    });
    applyFiltersAndRender();
  });

  // Dropdown 4: Source Filter
  document.getElementById('source-filter')?.addEventListener('change', (e) => {
    activeSource = e.target.value;
    applyFiltersAndRender();
  });

  // Segmented Region Buttons
  document.querySelectorAll('#location-tabs .pill-segmented-item').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#location-tabs .pill-segmented-item').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      activeLocation = btn.getAttribute('data-val');
      const locSelect = document.getElementById('location-select-filter');
      if (locSelect) locSelect.value = activeLocation;
      applyFiltersAndRender();
    });
  });

  // Segmented Stipend Buttons
  document.querySelectorAll('#stipend-filters .pill-segmented-item').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#stipend-filters .pill-segmented-item').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      activeStipend = btn.getAttribute('data-val');
      const stpSelect = document.getElementById('stipend-select-filter');
      if (stpSelect) stpSelect.value = activeStipend;
      applyFiltersAndRender();
    });
  });

  // Show: this search / last 3 days / saved
  document.querySelectorAll('.jb-view').forEach(btn => btn.addEventListener('click', () => setView(btn.dataset.view)));
  document.getElementById('empty-recent-btn')?.addEventListener('click', () => setView('recent'));
  document.getElementById('empty-search-btn')?.addEventListener('click', () => document.getElementById('trigger-scrape-btn')?.click());
  document.getElementById('empty-again-btn')?.addEventListener('click', searchAgain);

  // Reset Filters Function
  const resetAll = () => {
    const searchInput = document.getElementById('search-input');
    if (searchInput) searchInput.value = '';
    activeLocation = 'all';
    activeStipend = 'all';
    activeSource = 'all';
    activeRoleType = 'all';
    profileRules(profile).forEach(r => { prefsOff[r.key] = true; });   // shows everything; the profile itself is unchanged
    showBookmarkedOnly = false;
    
    const roleSelect = document.getElementById('role-type-filter');
    if (roleSelect) roleSelect.value = 'all';

    const locSelect = document.getElementById('location-select-filter');
    if (locSelect) locSelect.value = 'all';

    const stpSelect = document.getElementById('stipend-select-filter');
    if (stpSelect) stpSelect.value = 'all';

    const sourceSelect = document.getElementById('source-filter');
    if (sourceSelect) sourceSelect.value = 'all';
    activeModeration = 'verified';
    const modSelect = document.getElementById('mod-filter');
    if (modSelect) modSelect.value = 'verified';
    

    const allTab = document.querySelector('#location-tabs [data-val="all"]');
    if (allTab) {
      document.querySelectorAll('#location-tabs .pill-segmented-item').forEach(b => b.classList.remove('active'));
      allTab.classList.add('active');
    }

    const allStipend = document.querySelector('#stipend-filters [data-val="all"]');
    if (allStipend) {
      document.querySelectorAll('#stipend-filters .pill-segmented-item').forEach(b => b.classList.remove('active'));
      allStipend.classList.add('active');
    }

    applyFiltersAndRender();
    updateViewNote();
  };

  document.getElementById('reset-filters-btn')?.addEventListener('click', resetAll);
  document.getElementById('empty-reset-btn')?.addEventListener('click', resetAll);

  // Detail Drawer Interactions
  document.getElementById('close-drawer-btn')?.addEventListener('click', closeDetailDrawer);
  // Logo = home. Already on the home page: back to the top with panels closed, WITHOUT a reload
  // (a page load starts a new session and would empty the list of the current search).
  document.getElementById('brand-home')?.addEventListener('click', (e) => {
    const link = e.currentTarget;
    if (location.pathname !== link.pathname || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault();
    closeDetailDrawer();
    setFilterMenu(false);
    goHome();
  });
  document.getElementById('detail-drawer-overlay')?.addEventListener('click', (e) => {
    if (e.target === document.getElementById('detail-drawer-overlay')) {
      closeDetailDrawer();
    }
  });
  document.getElementById('drawer-bookmark-btn')?.addEventListener('click', () => {
    if (activeDrawerJob) toggleBookmark(activeDrawerJob.id);
  });

  // Opportunity Modal (Triggered by "Search Internships")
  const modal = document.getElementById('scrape-config-modal');
  document.getElementById('trigger-scrape-btn')?.addEventListener('click', () => {
    // Ticked: only the sites of your last search. None the first time: you pick every site yourself
    // (19 Oct: the dialog opened with all 23 sites ticked, one click searched them all)
    if (profile) {
      const f = document.getElementById('scrape-field');
      if (f) f.value = profile.field;
      setChecked('sources', profile.sources || []);
      setChecked('regions', profile.regions);
    } else {
      setChecked('sources', []);
    }
    syncSelectAll(modal);
    openModal(modal);
  });
  document.getElementById('close-config-btn')?.addEventListener('click', () => closeModal(modal));
  closeOnBackdrop(modal, () => closeModal(modal));
  closeOnBackdrop(document.getElementById('profile-modal'), closeProfileModal);   // not on the first visit

  document.getElementById('scrape-config-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    closeModal(modal);

    const checkedValues = (name) => Array.from(document.querySelectorAll(`input[name="${name}"]:checked`)).map(cb => cb.value);
    const config = {
      regions: checkedValues('regions'),
      sources: checkedValues('sources'),
      field: document.getElementById('scrape-field')?.value || (profile && profile.field) || 'ai_ml',
      limit: FIRST_BATCH
    };
    if (!config.sources.length) { showToast('error', 'Pick at least one site', 'Choose the sites to search, then start again.'); openModal(modal); return; }

    try {
      const res = await fetch('/api/scrape', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
      });
      if (res.status === 403) showToast('info', 'View-only link', 'Scraping can only be started on the host laptop.');
      const data = await res.json().catch(() => ({}));
      if (data.status === 'running') showToast('info', 'Already searching', 'Wait for the current search to finish.');
      else if (data.run_tag) {
        if (data.status === 'queued') showToast('info', 'Search queued', 'The automatic update is finishing the site it is on. Your search starts right after, by itself; results appear here.');
        startNewView(data.run_tag);   // the list clears and fills with this search
        lastSearch = { field: config.field, sources: config.sources.slice(), regions: config.regions.slice(), run_tag: data.run_tag };
        // Remember this search's choices: the next "Search Internships" and "Search more" start from them
        // (19 Oct: the window kept showing only the sites picked once in the profile form)
        if (profile) {
          writeProfile({ ...profile, field: config.field, sources: config.sources, regions: config.regions });
          saveProfileToAccount(profile);
          updateProfileUI();
          applyFiltersAndRender();   // the list shows the field just searched
        }
      }
    } catch (err) {
      console.error(err);
    }
  });

  // Public (tunnel) visitors get a read-only dashboard: hide the scrape button for them
  fetch('/api/whoami').then(r => r.json()).then(w => {
    canEdit = !!w.can_edit;
    if (!w.can_edit) {
      document.getElementById('trigger-scrape-btn')?.classList.add('hidden');
      document.getElementById('profile-scrape-row')?.classList.add('hidden');
      document.getElementById('search-more-bar')?.classList.add('hidden');
    }
  }).catch(() => {});

  document.getElementById('action-dismiss-btn')?.addEventListener('click', async () => {
    document.getElementById('action-banner').classList.add('hidden');
    try {
      await fetch('/api/alerts/dismiss', { method: 'POST' });
    } catch (e) {}
  });

  // Keyboard navigation
  window.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
      e.preventDefault();
      document.getElementById('search-input')?.focus();
    }
    if (e.key === 'Escape') {
      // the photo editor sits on top of My profile: Esc closes only the editor
      if (!document.getElementById('crop-modal')?.classList.contains('hidden')) { closeCropper(); return; }
      closeDetailDrawer();
      closeModal(modal);
      closeModal(document.getElementById('me-modal'));
      closeModal(document.getElementById('report-modal'));
      closeProfileModal();
    }
  });
}

// The post text keeps one line per paragraph, heading or "• " point (sites/_common.html_to_text).
// Short title-like lines followed by a paragraph or a list become headings; "Label: value" lines get
// a bold label; "• " lines become a list. Posts saved as one long line still show as one paragraph.
// Posts that arrive as one long paragraph (no line breaks, headings or points — AICTE and some
// company pages) are split into sentences and grouped by what each sentence is about. Only the
// post's own words are used: nothing is added or reworded, just the order and the layout.
const PROSE_SECTIONS = [
  ['work', 'What you\'ll do', /\b(interns? will|you will|you'll|will (contribute|work|assist|help|develop|build|design|be (responsible|working|involved))|work (may|will) (involve|include)|responsibilit|day[- ]to[- ]day|your (role|tasks?)|tasks? (include|involve))/i],
  ['who', 'Who can apply', /\b(eligib|candidates? (should|must|need|with)|applicants? (should|must)|must (have|be)|should (be|have)|familiar(ity)? with|knowledge of|proficien|required|requirements?|qualifications?|pursuing|degree in|currently enrolled|skills? (in|required)|experience (in|with) )/i],
  ['perks', 'Stipend & perks', /\b(stipend|certificate|ppo|pre[- ]placement|perks?|benefits?|salary|allowance|paid|letter of recommendation|lor)\b/i],
  ['notes', 'Good to know', /\b(access to|approval|security procedures?|please note|note:|disclaimer|is intended for|not (an? )?offensive|confidential|subject to)\b/i],
];
const LIST_LEAD = /^(.{0,80}?\b(?:involve|involves|include|includes|including|familiar with|familiarity with|knowledge of|such as|skills in|experience (?:with|in)|proficiency in|exposure to|combines))\s+(.+?)[.!]?$/i;

function splitSentences(text) {
  const safe = String(text).replace(/\b(e\.g|i\.e|etc|vs|Pvt|Ltd|Inc|Co|No|Dr|Mr|Ms|Mrs|St|approx)\./gi, m => m.replace('.', '\u0000'));
  return safe.split(/(?<=[.!?])\s+(?=["“(]?[A-Z0-9])/).map(s => s.replace(/\u0000/g, '.').trim()).filter(Boolean);
}

function sentenceAsList(s) {
  const m = s.match(LIST_LEAD);
  if (!m) return null;
  let items = m[2].split(/,\s*/);
  if (items.length < 2) return null;
  const last = items.pop();
  const tail = last.split(/\s+(?:and|&)\s+(?!.*\s+(?:and|&)\s+)/);
  items = items.concat(tail.length === 2 && items.length >= 1 ? tail : [last]);
  items = items.map(x => x.replace(/^(and|or)\s+/i, '').trim()).filter(Boolean);
  // a list of things, not a sentence that goes on ("…, Git and REST APIs is required")
  if (items.length < 3 || items.some(x => x.split(/\s+/).length > 9 || /\b(is|are|was|were|will|should|must|can)\b/i.test(x))) return null;
  const cap = x => x.charAt(0).toUpperCase() + x.slice(1);
  return `<p class="font-medium text-slate-700">${escapeHtml(m[1])}:</p><ul class="list-disc pl-4 space-y-0.5">${items.map(x => `<li>${escapeHtml(cap(x))}</li>`).join('')}</ul>`;
}

function structureProse(text) {
  const sentences = splitSentences(text);
  if (sentences.length < 3) return null;
  const groups = { intro: [], work: [], who: [], perks: [], notes: [] };
  sentences.forEach(s => {
    const hit = PROSE_SECTIONS.find(([, , re]) => re.test(s));
    groups[hit ? hit[0] : 'intro'].push(s);
  });
  const filled = Object.values(groups).filter(g => g.length).length;
  if (filled < 2) {   // nothing to group: short paragraphs of two sentences each are still easier to read
    let html = '';
    for (let i = 0; i < sentences.length; i += 2) html += `<p>${escapeHtml(sentences.slice(i, i + 2).join(' '))}</p>`;
    return html;
  }
  const block = (list, asPoints) => {
    if (asPoints && list.length > 1) {
      return `<ul class="list-disc pl-4 space-y-1">${list.map(s => `<li>${sentenceAsList(s) ? sentenceAsList(s) : escapeHtml(s)}</li>`).join('')}</ul>`;
    }
    return list.map(s => sentenceAsList(s) || `<p>${escapeHtml(s)}</p>`).join('');
  };
  let html = '';
  if (groups.intro.length) {
    for (let i = 0; i < groups.intro.length; i += 2) html += `<p>${escapeHtml(groups.intro.slice(i, i + 2).join(' '))}</p>`;
  }
  PROSE_SECTIONS.forEach(([key, title]) => {
    if (!groups[key].length) return;
    html += `<h5 class="font-bold text-slate-800 pt-2">${title}</h5>` + block(groups[key], key === 'work' || key === 'who');
  });
  return html;
}

function describeHtml(desc) {
  const BULLET = /^[•·▪●◦\-*]\s+/;
  const lines = String(desc || '').split(/\n+/).map(l => l.trim()).filter(Boolean);
  // one block of prose with no points: group its sentences (see structureProse)
  const prose = lines.filter(l => !BULLET.test(l));
  if (lines.length <= 3 && !lines.some(l => BULLET.test(l)) && prose.join(' ').length > 350) {
    const html = structureProse(prose.join(' '));
    if (html) return html;
  }
  const words = (line) => line.split(/\s+/).length;
  const titleCase = (line) => line.split(/\s+/).every(w => /^[A-Z0-9&(]/.test(w) || /^(and|or|of|the|to|for|in|on|at|a|an|we|you)$/i.test(w));
  const isHeading = (line, next) => {
    if (line.length > 60 || BULLET.test(line) || /[.,;!?]$/.test(line) || !/^[A-Z]/.test(line) || words(line) > 6) return false;
    if (/:\s/.test(line)) return false;                              // "Job ID: 0490" is a label line
    if (/:$/.test(line)) return titleCase(line.replace(/:$/, ''));   // "Requirements:" yes, "…who:" no
    if (!next) return false;
    return BULLET.test(next) || next.length > 60 || /:$/.test(next) || (words(line) >= 2 && titleCase(line));
  };
  let html = '', list = false;
  lines.forEach((line, i) => {
    if (BULLET.test(line)) {
      if (!list) { html += '<ul class="list-disc pl-4 space-y-0.5">'; list = true; }
      html += `<li>${escapeHtml(line.replace(BULLET, ''))}</li>`;
      return;
    }
    if (list) { html += '</ul>'; list = false; }
    const label = line.match(/^([A-Z][^:]{1,35}):\s+(.{1,120})$/);
    if (isHeading(line, lines[i + 1])) {
      html += `<h5 class="font-bold text-slate-800 ${i ? 'pt-2' : ''}">${escapeHtml(line.replace(/:$/, ''))}</h5>`;
    } else if (/:$/.test(line)) {   // a lead-in sentence such as "We are looking for candidates who:"
      html += `<p class="font-medium text-slate-700">${escapeHtml(line)}</p>`;
    } else if (label && !/[.!?]\s/.test(label[1])) {
      html += `<p><span class="font-semibold text-slate-700">${escapeHtml(label[1])}:</span> ${escapeHtml(label[2])}</p>`;
    } else if (line.length > 420) {
      const parts = splitSentences(line);
      for (let k = 0; k < parts.length; k += 2) html += `<p>${escapeHtml(parts.slice(k, k + 2).join(' '))}</p>`;
    } else {
      html += `<p>${escapeHtml(line)}</p>`;
    }
  });
  if (list) html += '</ul>';
  return html;
}

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

// ==========================================
// 8. Scam check (moderation) — verdict chips and live queue
// ==========================================
const MOD_VIEWS = {
  '':        { label: 'Scam check pending', chip: 'bg-slate-50 text-slate-500 border-slate-200', dot: 'bg-slate-400', box: 'bg-slate-50 border-slate-200 text-slate-600', icon: 'ph-hourglass' },
  held:      { label: 'Scraped, waiting for Load more', chip: 'bg-slate-50 text-slate-500 border-slate-200', dot: 'bg-slate-300', box: 'bg-slate-50 border-slate-200 text-slate-600', icon: 'ph-tray' },
  checking:  { label: 'Being checked', chip: 'bg-slate-50 text-slate-500 border-slate-200', dot: 'bg-slate-400', box: 'bg-slate-50 border-slate-200 text-slate-600', icon: 'ph-hourglass' },
  approved:  { label: 'Verified by scam check', chip: 'bg-emerald-50 text-emerald-700 border-emerald-200', dot: 'bg-emerald-500', box: 'bg-emerald-50 border-emerald-200 text-emerald-800', icon: 'ph-shield-check' },
  review:    { label: 'Needs a human look', chip: 'bg-amber-50 text-amber-700 border-amber-200', dot: 'bg-amber-500', box: 'bg-amber-50 border-amber-200 text-amber-800', icon: 'ph-eye' },
  blocked:   { label: 'Likely scam', chip: 'bg-rose-50 text-rose-700 border-rose-200', dot: 'bg-rose-500', box: 'bg-rose-50 border-rose-200 text-rose-800', icon: 'ph-prohibit' },
  expired:   { label: 'Apply link closed', chip: 'bg-slate-100 text-slate-500 border-slate-200', dot: 'bg-slate-400', box: 'bg-slate-50 border-slate-200 text-slate-600', icon: 'ph-link-break' },
};

function moderationChip(item) {
  const v = MOD_VIEWS[item.moderation_status || ''] || MOD_VIEWS[''];
  const short = { approved: 'VERIFIED', review: 'CHECK', blocked: 'SCAM?', expired: 'CLOSED', checking: 'CHECKING', held: 'QUEUED', '': 'PENDING' }[item.moderation_status || ''] || 'PENDING';
  return `<span class="px-1.5 py-0.2 font-bold border rounded text-[10px] ml-1 flex items-center gap-0.5 ${v.chip}" title="${escapeHtml(v.label)}"><i class="ph ${v.icon}"></i> ${short}</span>`;
}

function dotColor(item) {
  const st = item.moderation_status || '';
  if (st && st !== 'checking' && st !== 'approved') return (MOD_VIEWS[st] || MOD_VIEWS['']).dot;
  return item.trust_flags ? 'bg-amber-500' : (st === 'approved' ? 'bg-emerald-500' : 'bg-slate-400');
}

// Reload the cards whenever the scam check has judged more listings (it runs while scraping continues)
let lastJudged = -1;
let modPollMs = 5000;
async function pollModeration() {
  try {
    const c = await fetch('/api/moderation/status').then(r => r.json());
    lastModCounts = c;
    updateHeldUI(c);
    const judged = c.approved + c.review + c.blocked + c.expired;
    const waiting = c.pending + c.checking;
    const q = document.getElementById('mod-queue');
    if (q) q.innerText = waiting ? `${c.checking} being checked · ${c.pending} waiting` : '';
    if (judged !== lastJudged) { lastJudged = judged; loadData(); }
    // verdicts on their way (or a Load 5 more still filling): look often so they show up at once
    modPollMs = waiting || (c.load_more && c.load_more.running) ? 1500 : 5000;
  } catch (e) { /* app restarting */ }
  setTimeout(pollModeration, modPollMs);
}


// ==========================================
// 9. Scrape popups: one per finished site, one summary at the end
// ==========================================
let seenRunId = null, seenSites = 0, runAnnounced = true;

function handleScrapeProgress(progress, isRunning) {
  if (!progress) return;
  renderScanPanel(progress, isRunning);
  if (seenRunId === null) {            // page just opened: don't replay an old run
    seenRunId = progress.run_id; seenSites = progress.sites.length; runAnnounced = progress.finished;
    return;
  }
  if (progress.run_id !== seenRunId) { seenRunId = progress.run_id; seenSites = 0; runAnnounced = false; }
  if (progress.sites.length > seenSites) loadData();   // new rows from a finished site
  seenSites = progress.sites.length;
  if (progress.finished && !runAnnounced && !isRunning) {
    runAnnounced = true;
    const failed = progress.failed.length ? ` · ${progress.failed.length} site(s) failed` : '';
    const held = progress.total_held ? ` ${progress.total_held} more are waiting: use "Search more" below the list.` : '';
    const h = document.getElementById('search-more-held');
    if (h) h.textContent = progress.total_held ? `${progress.total_held} more found last time.` : '';
  }
}

function showToast(kind, title, message) {
  let box = document.getElementById('toast-stack');
  if (!box) {
    box = document.createElement('div');
    box.id = 'toast-stack';
    document.body.appendChild(box);
  }
  // with the profile form open, messages go to the top so they never cover its buttons
  const formOpen = !document.getElementById('profile-modal')?.classList.contains('hidden');
  box.className = formOpen
    ? 'fixed top-4 left-1/2 -translate-x-1/2 z-[60] flex flex-col gap-2 max-w-sm w-[calc(100%-2rem)]'
    : 'fixed bottom-6 right-6 z-[60] flex flex-col gap-2 max-w-sm w-[calc(100%-3rem)]';
  while (box.children.length >= 2) box.firstElementChild.remove();   // the newest two only
  const colors = { success: 'border-l-emerald-500', info: 'border-l-slate-400', error: 'border-l-rose-500' };
  const icons = { success: 'ph-check-circle text-emerald-600', info: 'ph-info text-slate-500', error: 'ph-warning-circle text-rose-600' };
  const t = document.createElement('div');
  t.className = `glass-panel p-3.5 shadow-xl border-l-4 ${colors[kind] || colors.info} flex gap-3 items-start transition-opacity duration-300`;
  t.setAttribute('role', 'status');
  t.innerHTML = `<i class="ph ${icons[kind] || icons.info} text-xl mt-0.5"></i>
    <div class="flex-1"><div class="text-sm font-bold text-slate-900">${escapeHtml(title)}</div>
    <div class="text-xs text-slate-600 mt-0.5">${escapeHtml(message)}</div></div>
    <button class="text-slate-400 hover:text-slate-700" aria-label="Close"><i class="ph ph-x"></i></button>`;
  t.querySelector('button').onclick = () => t.remove();
  box.appendChild(t);
  setTimeout(() => { t.style.opacity = '0'; setTimeout(() => t.remove(), 300); }, 7000);
}


// ==========================================
// 10. Sign-up profile and "Select all" checkboxes
// ==========================================
// The site checkboxes in both forms come from sites/registry.py (GET /api/sites)
let SITE_REGISTRY = null;
let DEFAULT_SOURCES = ['internshala', 'unstop', 'naukri', 'linkedin', 'shine', 'foundit', 'apna', 'government'];
const HOW_LABELS = { api: 'Public API', rss: 'Feed', page: 'Web page', browser: 'Chrome window', search: 'Web search' };

async function loadSites() {
  try { SITE_REGISTRY = await fetch('/api/sites').then(r => r.json()); } catch (e) { return; }
  Object.assign(SITE_NAMES, SITE_REGISTRY.scraper_labels || {});
  DEFAULT_SOURCES = SITE_REGISTRY.sites.filter(s => s.status === 'tested').map(s => s.key);
  document.querySelectorAll('[data-site-list]').forEach(renderSiteList);
}

function renderSiteList(box) {
  const name = box.dataset.siteList;
  const { regions, sites } = SITE_REGISTRY;
  box.innerHTML = regions.map(r => {
    const list = sites.filter(s => s.region === r.key);
    if (!list.length) return '';
    const live = list.filter(s => s.status !== 'planned').length;
    const cards = list.map(s => {
      const soon = s.status === 'planned';
      const tag = soon ? '<span class="ml-auto shrink-0 text-[9px] font-bold text-slate-500 bg-slate-100 px-1.5 py-0.5 rounded">Soon</span>'
        : s.status === 'basic' ? '<span class="ml-auto shrink-0 text-[9px] font-bold text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded">Basic</span>' : '';
      const tip = `${HOW_LABELS[s.how] || s.how}${soon ? ' · not built yet' : s.status === 'basic' ? ' · older scraper, not rebuilt yet' : ' · tested'}`;
      return `<label class="flex items-center gap-2 p-2 border border-slate-200 rounded-lg ${soon ? 'bg-slate-50/60 text-slate-400 cursor-not-allowed' : 'bg-slate-50 hover:bg-white cursor-pointer'}" title="${escapeHtml(tip)}">
        <input type="checkbox" name="${name}" value="${escapeHtml(s.key)}"${soon ? ' disabled' : ''}${s.status === 'tested' ? ' checked' : ''}>
        <span class="truncate">${escapeHtml(s.name)}</span>${tag}</label>`;
    }).join('');
    return `<div data-site-region="${escapeHtml(r.key)}">
      <div class="text-[10px] font-bold text-slate-500 uppercase tracking-wide mb-1.5">${escapeHtml(r.label)} · ${live} of ${list.length} live</div>
      <div class="grid grid-cols-2 gap-2">${cards}</div></div>`;
  }).join('');
  const live = sites.filter(s => s.status !== 'planned').length;
  const count = box.parentElement.querySelector('[data-site-count]');
  if (count) count.textContent = `(${live} live, ${sites.length - live} coming soon)`;
  applyRegionFilter(box);
}

// A site list shows only the regions ticked in the same form; sites in hidden regions are unticked
function applyRegionFilter(box) {
  const form = box.closest('form');
  if (!form) return;
  const on = new Set([...form.querySelectorAll(`input[name="${box.dataset.regionName}"]:checked`)].map(cb => cb.value));
  box.querySelectorAll('[data-site-region]').forEach(g => {
    const show = on.has(g.dataset.siteRegion);
    g.classList.toggle('hidden', !show);
    if (!show) g.querySelectorAll('input').forEach(cb => { cb.checked = false; });
  });
}

// Checkboxes a "Select all" may touch: not disabled ("Soon") and not in a hidden region
function selectableBoxes(root, name) {
  return [...root.querySelectorAll(`input[name="${name}"]`)]
    .filter(cb => !cb.disabled && !(cb.closest('[data-site-region]') || {classList: {contains: () => false}}).classList.contains('hidden'));
}

async function initProfile() {
  await loadSites();
  try {
    const list = await fetch('/api/fields').then(r => r.json());
    fieldLabels = Object.fromEntries(list.map(f => [f.key, f.label]));
    const options = list.map(f => `<option value="${escapeHtml(f.key)}">${escapeHtml(f.label)}</option>`).join('');
    ['profile-field', 'scrape-field'].forEach(id => { const el = document.getElementById(id); if (el) el.innerHTML = options; });
  } catch (e) { /* app restarting: the defaults still work */ }

  document.getElementById('edit-profile-btn')?.addEventListener('click', (e) => { e.stopPropagation(); toggleProfileMenu(); });
  document.getElementById('close-profile-btn')?.addEventListener('click', closeProfileModal);
  bindProfileForm();

  // "Select all" boxes: one per group of checkboxes, in both forms
  document.addEventListener('change', (e) => {
    const t = e.target;
    if (t.dataset && t.dataset.selectAll) {
      selectableBoxes(t.form, t.dataset.selectAll).forEach(cb => { cb.checked = t.checked; });
      syncSelectAll(t.form);
    } else if (t.type === 'checkbox' && t.name && t.form) {
      syncSelectAll(t.form);
    }
  });

  updateProfileUI();
  // right away, before anything else on the page: one question per screen (onboarding.js)
  if (!requiredDone(profile)) (typeof openOnboarding === 'function' ? openOnboarding() : openProfileModal(true));
}

function bindProfileForm() {
  const form = document.getElementById('profile-form');
  if (!form || form.dataset.bound) return;
  form.dataset.bound = '1';
  form.addEventListener('submit', e => { e.preventDefault(); onProfileNext(); });   // Enter in a text box
  document.getElementById('profile-next').addEventListener('click', onProfileNext);
  document.getElementById('profile-back').addEventListener('click', () => showProfileStep(profileStep - 1));
  document.getElementById('profile-skip').addEventListener('click', () => { closeProfileModal(); showToast('info', 'Saved what you filled', 'Finish your profile any time from your photo, top right.'); });
  document.getElementById('profile-steps').addEventListener('click', e => {
    const btn = e.target.closest('.pstep');
    if (btn && !btn.disabled) showProfileStep(Number(btn.dataset.step));
  });
  document.getElementById('profile-field').addEventListener('change', e => {
    renderRoleChips(e.target.value, collectProfile().roles);
    renderSkills();
  });
  form.addEventListener('change', () => showProfileStep(profileStep));   // ticks follow the answers
  document.getElementById('profile-skill-add').addEventListener('click', () => {
    const inp = document.getElementById('profile-skill-input'); addSkill(inp.value); inp.value = ''; inp.focus(); showProfileStep(3);
  });
  if (window.attachSkillAutocomplete) {
    attachSkillAutocomplete(document.getElementById('profile-skill-input'), {
      have: () => draftSkills,
      pick: (s) => { addSkill(s); const inp = document.getElementById('profile-skill-input'); inp.value = ''; inp.focus(); showProfileStep(3); },
    });
  }
  document.getElementById('profile-skill-input').addEventListener('keydown', e => {
    if (e.target.acHandleKey && e.target.acHandleKey(e)) { e.preventDefault(); e.stopPropagation(); return; }
    if (e.key !== 'Enter') return;
    e.preventDefault(); e.stopPropagation();
    addSkill(e.target.value); e.target.value = ''; showProfileStep(3);
  });
  form.addEventListener('click', e => {
    const add = e.target.closest('[data-skill-add]');
    const rm = e.target.closest('[data-skill-remove]');
    if (add) { addSkill(add.dataset.skillAdd); showProfileStep(3); }
    if (rm) { draftSkills.splice(Number(rm.dataset.skillRemove), 1); renderSkills(); showProfileStep(3); }
  });
}

function setChecked(name, values) {
  if (!Array.isArray(values)) return;
  document.querySelectorAll(`input[name="${name}"]`).forEach(cb => { cb.checked = values.includes(cb.value); });
}

function syncSelectAll(root) {
  root.querySelectorAll('[data-site-list]').forEach(applyRegionFilter);
  root.querySelectorAll('[data-select-all]').forEach(all => {
    const boxes = selectableBoxes(root, all.dataset.selectAll);
    const on = boxes.filter(b => b.checked).length;
    all.checked = boxes.length > 0 && on === boxes.length;
    all.indeterminate = on > 0 && on < boxes.length;
  });
}

// ==========================================
// Profile: five sections (About you, What you want, Skills, Preferences, Search).
// First visit: sections 1 and 2 are required and the form can't be closed until they are saved;
// then 3-5 are offered and can be skipped. Every "Save & next" saves, so nothing is lost on close.
// ==========================================
const SKILL_LIMIT = 10;
const PROFILE_STEPS = 5;
let profileStep = 1;
let profileMandatory = false;
let draftSkills = [];

function sectionDone(p, n) {
  if (!p) return false;
  switch (n) {
    case 1: return !!(String(p.name || '').trim() && p.study_year && p.experience);
    case 2: return !!(p.field && (p.roles || []).length);
    case 3: return (p.skills || []).length >= 3;
    case 4: return !!(p.work_mode && p.min_stipend != null && p.min_stipend !== '' && p.max_duration);
    case 5: return (p.regions || []).length > 0;
    default: return false;
  }
}
const SECTION_NAMES = ['', 'about you', 'your roles', 'at least 3 skills', 'your preferences', 'search settings'];
// Sections 1 and 2 are required: until both are complete the form opens by itself and can't be closed
const requiredDone = (p) => sectionDone(p, 1) && sectionDone(p, 2);
// Sections open one after another: a section can be opened only when every section before it is complete
const reachableUpTo = (p) => ([1, 2, 3, 4].find(k => !sectionDone(p, k)) || PROFILE_STEPS);
const SECTION_TODO = {
  1: ['Finish "About you"', 'Add your name and pick where you are right now.'],
  2: ['Finish "What you want"', 'Choose your field and at least one role.'],
  3: ['Add at least 3 skills', 'Pick from the suggestions or type your own. Or "Skip for now".'],
  4: ['Answer all three', 'Pick a work mode, a minimum stipend and a duration ("Any" is fine). Or "Skip for now".'],
  5: ['Pick your regions', 'Choose at least one region.'],
};

function renderRoleChips(field, selected) {
  const box = document.getElementById('profile-roles');
  if (!box) return;
  const roles = (window.PROFILE_ROLES || {})[field] || [];
  box.innerHTML = roles.length ? roles.map(r => `<label class="flex items-center gap-2 px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg cursor-pointer hover:bg-white has-[:checked]:bg-orange-50 has-[:checked]:border-orange-300 has-[:checked]:text-orange-900">
      <input type="checkbox" name="p_roles" value="${escapeHtml(r.key)}" ${(selected || []).includes(r.key) ? 'checked' : ''}> ${escapeHtml(r.label)}</label>`).join('')
    : '<p class="text-slate-500 col-span-2">No role choices for this field yet.</p>';
}

function renderSkills() {
  const field = document.getElementById('profile-field')?.value;
  const chosen = document.getElementById('profile-skills');
  const lower = draftSkills.map(x => x.toLowerCase());
  if (chosen) chosen.innerHTML = draftSkills.length
    ? draftSkills.map((sk, i) => `<span class="inline-flex items-center gap-1 pl-2.5 pr-1 py-1 rounded-full bg-orange-500 text-white text-[11px] font-bold">${escapeHtml(sk)}
        <button type="button" data-skill-remove="${i}" class="w-5 h-5 rounded-full hover:bg-white/20 flex items-center justify-center" aria-label="Remove ${escapeHtml(sk)}">×</button></span>`).join('')
    : '<span class="text-slate-400 px-1 py-1">No skills yet. Pick from the suggestions or type your own.</span>';
  const suggest = document.getElementById('profile-skill-suggest');
  const list = ((window.PROFILE_SKILLS || {})[field] || []).filter(sk => !lower.includes(sk.toLowerCase()));
  if (suggest) suggest.innerHTML = list.map(sk => `<button type="button" data-skill-add="${escapeHtml(sk)}" class="px-2.5 py-1 rounded-full border border-slate-300 bg-white text-[11px] font-bold text-slate-700 hover:border-orange-400 hover:text-orange-700">+ ${escapeHtml(sk)}</button>`).join('')
    || '<span class="text-slate-400">All suggestions added.</span>';
  const count = document.getElementById('profile-skill-count');
  if (count) count.textContent = `${draftSkills.length} / ${SKILL_LIMIT}`;
}
function addSkill(raw) {
  const sk = String(raw || '').replace(/\s+/g, ' ').trim().slice(0, 40);
  if (!sk) return;
  if (draftSkills.some(x => x.toLowerCase() === sk.toLowerCase())) return;
  if (draftSkills.length >= SKILL_LIMIT) { showToast('info', `Up to ${SKILL_LIMIT} skills`, 'Remove one to add another.'); return; }
  draftSkills.push(sk);
  renderSkills();
}

function setRadio(name, value) {
  document.querySelectorAll(`input[name="${name}"]`).forEach(r => { r.checked = value != null && String(r.value) === String(value); });
}

function collectProfile() {
  const form = document.getElementById('profile-form');
  const checked = name => [...form.querySelectorAll(`input[name="${name}"]:checked`)].map(cb => cb.value);
  const radio = name => (form.querySelector(`input[name="${name}"]:checked`) || {}).value || null;
  const minStipend = radio('min_stipend');
  return {
    name: document.getElementById('profile-name').value.trim(),
    study_year: radio('study_year'),
    experience: radio('experience') || '0',
    field: document.getElementById('profile-field').value || '',
    roles: checked('p_roles'),
    skills: draftSkills.slice(),
    work_mode: radio('work_mode'),
    min_stipend: minStipend == null ? null : Number(minStipend),
    max_duration: radio('max_duration'),
    companies: document.getElementById('profile-companies').value.split(',').map(c => c.trim()).filter(Boolean),
    sources: (profile && profile.sources) || [],   // set by Search Internships, never by this form
    regions: checked('p_regions'),
  };
}

function showProfileStep(n) {
  const target = Math.max(1, Math.min(PROFILE_STEPS, n, reachableUpTo(collectProfile())));
  const moved = target !== profileStep;
  profileStep = target;
  const draft = collectProfile();
  document.querySelectorAll('#profile-form > section').forEach(sec => { sec.hidden = Number(sec.dataset.section) !== profileStep; });
  document.querySelectorAll('#profile-steps .pstep').forEach(btn => {
    const k = Number(btn.dataset.step);
    const locked = k > reachableUpTo(draft) || (profileMandatory && k > 2);
    const done = !locked && sectionDone(draft, k);   // a locked section shows its number, never a tick
    btn.toggleAttribute('disabled', locked);
    btn.classList.toggle('done', done);
    if (k === profileStep) btn.setAttribute('aria-current', 'step'); else btn.removeAttribute('aria-current');
    btn.querySelector('.pstep-dot').textContent = done ? '✓' : String(k);
  });
  document.getElementById('profile-back').classList.toggle('invisible', profileStep === 1);
  // "Skip for now" belongs to the optional sections (3-5) only; 1 and 2 are never skipped
  document.getElementById('profile-skip').classList.toggle('hidden', profileMandatory || profileStep <= 2);
  const next = document.getElementById('profile-next');
  next.textContent = profileMandatory
    ? (profileStep === 1 ? 'Next' : 'Save and continue')
    : (profileStep === PROFILE_STEPS ? 'Save and finish' : 'Save and next');
  document.getElementById('profile-title').textContent = profileMandatory ? 'Set up your profile' : 'Your profile';
  if (moved) document.getElementById('profile-form').scrollTop = 0;
}

function openProfileModal(firstVisit, step) {
  const modal = document.getElementById('profile-modal');
  if (!modal) return;
  profileMandatory = !!firstVisit || !requiredDone(profile);
  const p = profile || {};
  document.getElementById('profile-name').value = p.name || document.getElementById('profile-name').value || '';
  if (p.field) document.getElementById('profile-field').value = p.field;
  setRadio('study_year', p.study_year);
  setRadio('experience', p.experience || '0');
  renderRoleChips(document.getElementById('profile-field').value, p.roles);
  draftSkills = (p.skills || []).slice(0, SKILL_LIMIT);
  renderSkills();
  setRadio('work_mode', p.work_mode);
  setRadio('min_stipend', p.min_stipend);
  setRadio('max_duration', p.max_duration);
  document.getElementById('profile-companies').value = (p.companies || []).join(', ');
  if (profile) setChecked('p_regions', profile.regions);
  document.getElementById('close-profile-btn').classList.toggle('hidden', profileMandatory);
  syncSelectAll(modal);
  // open on the first section that still needs something, unless one was asked for
  const first = step || (profileMandatory ? (sectionDone(profile, 1) ? 2 : 1)
                                          : ([1, 2, 3, 4, 5].find(k => !sectionDone(profile, k)) || 1));
  profileStep = 0;   // so the first showProfileStep counts as a move
  showProfileStep(first);
  openModal(modal);
  (profileStep === 1 ? document.getElementById('profile-name') : null)?.focus();
}

// Dialogs open and close with a short animation (theme.css); hidden is set after the closing one.
function openModal(el) {
  if (!el) return;
  clearTimeout(el._closeTimer);
  el.classList.remove('closing', 'hidden');
}
function closeModal(el) {
  if (!el || el.classList.contains('hidden') || el.classList.contains('closing')) return;
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { el.classList.add('hidden'); return; }
  el.classList.add('closing');
  const done = () => {
    clearTimeout(el._closeTimer);
    el.removeEventListener('animationend', onEnd);
    if (el.classList.contains('closing')) { el.classList.add('hidden'); el.classList.remove('closing'); }
  };
  const onEnd = (e) => { if (e.target === el) done(); };
  el.addEventListener('animationend', onEnd);
  el._closeTimer = setTimeout(done, 400);   // in case the animation never runs (hidden tab)
}

// A click on the dimmed area around a dialog closes it. Both the press and the release must be
// on the backdrop, so selecting text in the dialog and letting go outside does not close it.
function closeOnBackdrop(backdrop, close) {
  if (!backdrop) return;
  let pressedOnBackdrop = false;
  backdrop.addEventListener('mousedown', (e) => { pressedOnBackdrop = e.target === backdrop; });
  backdrop.addEventListener('click', (e) => {
    if (pressedOnBackdrop && e.target === backdrop) close();
    pressedOnBackdrop = false;
  });
}

function closeProfileModal() {
  if (profileMandatory || !requiredDone(profile)) return;   // sections 1 and 2 must be saved first
  closeModal(document.getElementById('profile-modal'));
}

// "Next" / "Save and next" / "Save and finish"
async function onProfileNext() {
  const draft = collectProfile();
  if (!sectionDone(draft, profileStep)) {            // no moving on until this section is filled
    const [title, msg] = SECTION_TODO[profileStep];
    showToast('error', title, msg);
    return;
  }
  if (profileMandatory && profileStep === 1) { showProfileStep(2); return; }
  if (!draft.field) { showProfileStep(2); showToast('error', 'Choose a field', 'Pick the field you want an internship in.'); return; }
  const hasRoles = ((window.PROFILE_ROLES || {})[draft.field] || []).length > 0;
  if (profileMandatory && hasRoles && !draft.roles.length) {
    showToast('error', 'Pick at least one role', 'Choose the roles you want, so the right posts come first.');
    return;
  }
  const finishing = !profileMandatory && profileStep === PROFILE_STEPS;

  writeProfile(draft);
  saveProfileToAccount(draft);
  displayOrder.clear(); renderedIds.clear();
  updateProfileUI();
  applyFiltersAndRender();

  if (profileMandatory) {   // sections 1 and 2 saved: the rest is optional from here
    profileMandatory = false;
    document.getElementById('close-profile-btn').classList.remove('hidden');
    showProfileStep(3);
    showToast('success', 'Profile saved', 'Three short optional sections make your list sharper. Or "Skip for now" and click Search Internships.');
    return;
  }
  if (!finishing) { showProfileStep(profileStep + 1); return; }
  closeModal(document.getElementById('profile-modal'));
  // Saving the profile never starts a search: only "Search Internships" does (19 Oct)
  showToast('success', 'Profile saved', 'Your list now follows your profile. Click "Search Internships" to look for new posts.');
}

// How complete the profile is: the five sections, 20% each. Shown as the orange ring around the avatar.
function profileCompletion(p) {
  const done = [1, 2, 3, 4, 5].filter(k => sectionDone(p, k));
  return { pct: done.length * 20, missing: [1, 2, 3, 4, 5].filter(k => !sectionDone(p, k)).map(k => SECTION_NAMES[k]) };
}

function updateProfileRing() {
  const btn = document.getElementById('edit-profile-btn');
  const badge = document.getElementById('profile-pct');
  if (!btn) return;
  const { pct, missing } = profileCompletion(profile);
  requestAnimationFrame(() => btn.style.setProperty('--pct', pct));   // next frame: the ring fills up
  btn.classList.toggle('done', pct === 100);
  if (badge) { badge.textContent = `${pct}%`; badge.classList.toggle('hidden', pct === 100); }
  const tip = pct === 100 ? 'Profile complete · Edit profile'
    : `Profile ${pct}% complete · add ${missing.join(', ')}`;
  btn.title = tip;
  btn.setAttribute('aria-label', `Your account · ${tip}`);
}

// ---- Account menu under the avatar (1 Nov): profile level, a few numbers, and the account actions ----
let sbUserEmail = '';
const PROFILE_LEVELS = ['Newbie', 'Newbie', 'Explorer', 'Scout', 'Hunter', 'Internship Pro'];   // by sections done (0-5)
function fillProfileMenu() {
  // a missing element must never stop the menu from opening (1 Nov: an old page + new script did)
  const set = (id, text) => { const el = document.getElementById(id); if (el) el.textContent = text; };
  const { pct, missing } = profileCompletion(profile);
  const done = pct / 20;
  const p = profile || {};
  set('pm-name', p.name || 'You');
  set('pm-email', sbUserEmail || (USER_MODE ? '' : 'This laptop'));
  const av = document.getElementById('pm-avatar'), src = document.getElementById('profile-avatar');
  if (av && src) av.innerHTML = avatarHtml();   // the photo or the initials, same as the button
  requestAnimationFrame(sharpenAvatars);
  set('pm-level', PROFILE_LEVELS[done]);
  set('pm-pct', `${pct}%`);
  requestAnimationFrame(() => { const bar = document.getElementById('pm-bar-fill'); if (bar) bar.style.width = `${pct}%`; });
  set('pm-next', missing.length
    ? `Add ${missing[0]} to reach ${PROFILE_LEVELS[done + 1]}.`
    : 'Profile complete. Your list is matched as well as it can be.');
  // the numbers come from the posts on this laptop (the last 3 days of searches)
  const count = (st) => allInternships.filter(r => r.moderation_status === st).length;
  set('pm-verified', count('approved'));
  set('pm-scams', count('blocked'));
  set('pm-applied', applications.size);
  set('pm-apps-count', applications.size);
  set('pm-saved-count', bookmarks.length);
  const dark = document.documentElement.classList.contains('dark');
  set('pm-theme-label', dark ? 'Light theme' : 'Dark theme');
  const ti = document.querySelector('[data-pm="theme"] i');
  if (ti) ti.className = `ph ${dark ? 'ph-sun' : 'ph-moon'}`;
}
function profileMenuOpen() { return !document.getElementById('profile-menu')?.classList.contains('hidden'); }
function toggleProfileMenu(force) {
  const menu = document.getElementById('profile-menu'), btn = document.getElementById('edit-profile-btn');
  if (!menu) return;
  const open = force === undefined ? !profileMenuOpen() : force;
  if (open) {
    fillProfileMenu();
    menu.classList.remove('hidden', 'pm-closing');
    menu.querySelector('[role="menuitem"]')?.focus({ preventScroll: true });
  } else if (profileMenuOpen()) {
    menu.classList.add('pm-closing');
    setTimeout(() => { if (menu.classList.contains('pm-closing')) menu.classList.add('hidden'); menu.classList.remove('pm-closing'); }, 150);
  }
  btn?.setAttribute('aria-expanded', String(open));
}
document.addEventListener('click', (e) => {
  if (!profileMenuOpen()) return;
  const item = e.target.closest('#profile-menu [data-pm]');
  if (item) {
    const what = item.dataset.pm;
    if (what === 'theme') return;   // theme.js switches it; the menu stays open and updates below
    toggleProfileMenu(false);
    if (what === 'apps') showAppsPage();
    else if (what === 'profile') openMeModal();
    else if (what === 'saved' || what === 'recent') setView(what);
    return;
  }
  if (!e.target.closest('#profile-menu')) toggleProfileMenu(false);   // a click anywhere else closes it
});
// the theme changes a moment after the click (theme.js animates it): relabel the menu item when it does
new MutationObserver(() => { if (profileMenuOpen()) fillProfileMenu(); })
  .observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
document.addEventListener('keydown', (e) => {
  if (!profileMenuOpen()) return;
  const items = [...document.querySelectorAll('#profile-menu [role="menuitem"]')].filter(i => !i.classList.contains('hidden'));
  const at = items.indexOf(document.activeElement);
  if (e.key === 'Escape') { toggleProfileMenu(false); document.getElementById('edit-profile-btn')?.focus(); }
  else if (e.key === 'ArrowDown') { e.preventDefault(); items[(at + 1) % items.length]?.focus(); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); items[(at - 1 + items.length) % items.length]?.focus(); }
});

function updateProfileUI() {
  const label = document.getElementById('profile-btn-label');
  const box = document.getElementById('profile-summary');
  updateProfileRing();
  if (!profile) {
    if (label) label.textContent = 'Set up profile';
    if (box) box.classList.add('hidden');
    return;
  }
  const field = fieldLabels[profile.field] || profile.field;
  if (label) label.textContent = profile.name ? `${profile.name} · ${field}` : field;
  renderAvatars();
  if (box) {
    const year = profile.study_year === 'grad' ? 'Graduated' : profile.study_year ? `${escapeHtml(profile.study_year)}${{ 1: 'st', 2: 'nd', 3: 'rd' }[profile.study_year] || 'th'} year` : '';
    const exp = { '0': 'No experience yet', '1-2': '1–2 years experience', '3+': '3+ years experience' }[profile.experience] || '';
    const lines = [
      (profile.roles || []).length ? `Roles: ${profile.roles.slice(0, 3).map(escapeHtml).join(', ')}${profile.roles.length > 3 ? '…' : ''}` : '',
      (profile.skills || []).length ? `${profile.skills.length} skills used for ranking` : 'Add skills to rank posts better',
      Number(profile.min_stipend) > 0 ? `₹${Number(profile.min_stipend).toLocaleString('en-IN')}+ a month` : '',
      profile.work_mode === 'remote' ? 'Remote only' : profile.work_mode === 'office' ? 'Office / hybrid' : '',
      profile.max_duration && profile.max_duration !== 'any' ? `Up to ${escapeHtml(profile.max_duration)} months` : '',
      (profile.companies || []).length ? `Preferred: ${profile.companies.slice(0, 3).map(escapeHtml).join(', ')}` : '',
    ].filter(Boolean);
    box.innerHTML = `<div class="jb-label">Ranked for you</div>
      <div class="text-sm font-extrabold text-slate-900 leading-snug">${escapeHtml(field)}</div>
      <div class="text-xs text-slate-500 font-semibold mt-0.5">${[year, exp].filter(Boolean).join(' · ')}</div>
      <ul class="mt-2.5 space-y-1 text-xs text-slate-600 font-medium">${lines.map(l => `<li class="flex gap-1.5"><i class="ph ph-check text-orange-500 mt-0.5"></i><span>${l}</span></li>`).join('')}</ul>
      <button type="button" class="mt-3 w-full glass-btn py-2 text-xs flex items-center justify-center gap-1.5" onclick="openProfileModal(false)"><i class="ph ph-pencil-simple"></i>Edit profile</button>`;
    box.classList.remove('hidden');
  }
}


// ==========================================
// 11. One "Filters" dropdown holding every filter
// ==========================================
function updateFilterCount() {
  const n = [activeRoleType !== 'all', activeLocation !== 'all', activeStipend !== 'all',
             activeSource !== 'all', activeModeration !== 'verified'].filter(Boolean).length + activeProfileRules().length;
  const badge = document.getElementById('filter-count');
  if (!badge) return;
  badge.textContent = n;
  badge.classList.toggle('hidden', n === 0);
  const rail = document.getElementById('rail-filter-count');
  if (rail) { rail.textContent = n; rail.classList.toggle('hidden', n === 0); }
}

function setFilterMenu(open) {
  const menu = document.getElementById('filter-menu');
  const btn = document.getElementById('filter-menu-btn');
  if (!menu || !btn) return;
  menu.classList.toggle('hidden', !open);
  btn.setAttribute('aria-expanded', String(open));
  if (open) menu.querySelector('button, select')?.focus();
}

document.addEventListener('DOMContentLoaded', () => {
  const wrap = document.getElementById('filter-menu-wrap');
  document.getElementById('filter-menu-btn')?.addEventListener('click', () =>
    setFilterMenu(document.getElementById('filter-menu').classList.contains('hidden')));
  document.getElementById('filter-done-btn')?.addEventListener('click', () => {
    setFilterMenu(false);
    document.getElementById('filter-menu-btn')?.focus();
  });
  document.addEventListener('click', (e) => {
    if (wrap && !wrap.contains(e.target) && !e.target.closest('#filter-menu-btn')) setFilterMenu(false);
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') setFilterMenu(false); });
  updateFilterCount();
});


// ==========================================
// 12. Small batches: first search ~30 new internships, "Search more" for the next batch
// ==========================================
const FIRST_BATCH = 120;   // a search saves up to this many; only 5 at a time go to the scam check

function setSearchMoreBusy(busy) {
  const btn = document.getElementById('search-more-btn');
  if (!btn) return;
  btn.disabled = busy;
  btn.classList.toggle('opacity-60', busy);
  btn.querySelector('span').textContent = busy ? 'Searching…' : 'Search more';
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('search-more-btn')?.addEventListener('click', async () => {
    const limit = Number(document.getElementById('search-more-count')?.value || FIRST_BATCH);
    // Only the sites of the search on screen; never the profile's list (19 Oct: that was all 23)
    if (!lastSearch || !viewRun || lastSearch.run_tag !== viewRun) {
      showToast('info', 'Start a search first', 'Click "Search Internships" and pick the sites. "Search more" then looks for more on those same sites.');
      return;
    }
    const config = {
      field: lastSearch.field,
      sources: lastSearch.sources.slice(),
      regions: lastSearch.regions.slice(),
      limit,
      run_tag: viewRun,   // adds to the search on screen
    };
    setSearchMoreBusy(true);
    try {
      const res = await fetch('/api/scrape', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(config) });
      const data = await res.json().catch(() => ({}));
      if (data.run_tag && !viewRun) startNewView(data.run_tag);
      if (res.status === 403) { showToast('info', 'View-only link', 'Searching can only be started on the host laptop.'); setSearchMoreBusy(false); }
      else if (data.status === 'running') showToast('info', 'Already searching', 'Wait for the current search to finish.');
      else if (data.status === 'queued') showToast('info', 'Search queued', 'The automatic update is finishing the site it is on. Your search starts right after, by itself; results appear here.');
      else showToast('info', 'Searching for more', `Up to ${limit} new ${fieldLabels[config.field] || ''} internships from ${config.sources.length} site(s). A popup appears as each site finishes.`);
    } catch (e) {
      showToast('error', 'Search did not start', 'The app is not answering. Is python app.py running?');
      setSearchMoreBusy(false);
    }
  });
});


// The old search's sites again, as a new search (the person clicks it: nothing is scraped on its own)
async function searchAgain() {
  const p = profile || {};
  if (!(p.sources || []).length) { document.getElementById('trigger-scrape-btn')?.click(); return; }
  const config = { field: p.field || 'ai_ml', sources: p.sources.slice(), regions: (p.regions || []).slice(), limit: FIRST_BATCH };
  try {
    const res = await fetch('/api/scrape', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(config) });
    const data = await res.json().catch(() => ({}));
    if (res.status === 403) { showToast('info', 'View-only link', 'Searching can only be started on the host laptop.'); return; }
    if (data.status === 'running') { showToast('info', 'Already searching', 'Wait for the current search to finish.'); return; }
    if (data.run_tag) {
      staleRun = '';
      startNewView(data.run_tag);
      lastSearch = { ...config, run_tag: data.run_tag };
      showToast('info', 'Searching again', `${config.sources.length} site(s), the same as last time. Results show up as each site finishes.`);
    }
  } catch (e) {
    showToast('error', 'Search did not start', 'The app is not answering. Is python app.py running?');
  }
}

// ==========================================
// 13. Live scan panel: each site's state while a search runs, then the scam check
// ==========================================
let lastModCounts = null, panelRunId = null, closedRunId = null;
const frozenSecs = {};
const SITE_NAMES = { internshala: 'Internshala', unstop: 'Unstop', naukri: 'Naukri', linkedin: 'LinkedIn', shine: 'Shine',
  foundit: 'Foundit', apna: 'Apna', government: 'AICTE (Govt)', cutshort: 'Cutshort', remotive: 'Remote boards', universities: 'University pages' };

function renderScanPanel(progress, isRunning) {
  const panel = document.getElementById('scan-panel');
  if (!panel) return;
  if (isRunning && !progress.finished) panelRunId = progress.run_id;
  const show = panelRunId !== null && panelRunId === progress.run_id && closedRunId !== progress.run_id;
  panel.classList.toggle('hidden', !show);
  if (!show) return;

  const planned = progress.planned && progress.planned.length ? progress.planned : progress.sites.map(s => s.source);
  const done = Object.fromEntries(progress.sites.map(s => [s.source, s]));
  const running = new Set(progress.running || []);
  const finished = progress.finished && !isRunning;
  let secs = progress.started_at ? Math.max(0, Math.round(Date.now() / 1000 - progress.started_at)) : 0;
  if (finished) { if (frozenSecs[progress.run_id] === undefined) frozenSecs[progress.run_id] = secs; secs = frozenSecs[progress.run_id]; }
  const clock = `${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, '0')}`;

  document.getElementById('scan-title').textContent = finished ? 'Search finished' : 'Searching internships';
  document.getElementById('scan-sub').textContent =
    `${progress.field || ''}${progress.field ? ' · ' : ''}${progress.sites.length}/${planned.length} sites · ${clock}`;
  document.getElementById('scan-bar').style.width = `${planned.length ? Math.round(100 * progress.sites.length / planned.length) : 0}%`;
  const icon = document.getElementById('scan-icon');
  icon.innerHTML = finished ? '<i class="ph ph-check-circle text-xl"></i>' : '<i class="ph ph-spinner-gap text-xl animate-spin" style="animation-duration:1.6s"></i>';
  icon.className = `w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${finished ? 'bg-emerald-100 text-emerald-600' : 'bg-orange-100 text-orange-600'}`;

  document.getElementById('scan-sites').innerHTML = planned.map(src => {
    const name = escapeHtml(SITE_NAMES[src] || src);
    const d = done[src];
    let ic, txt, cls;
    if (d && !d.ok) { ic = 'ph-x-circle text-rose-500'; txt = 'Failed'; cls = 'text-rose-600'; }
    else if (d) {
      ic = 'ph-check-circle text-emerald-500';
      txt = d.added ? `${d.added} new` : 'Nothing new';
      if (d.held) txt += ` · ${d.held} more later`;
      cls = d.added ? 'text-emerald-700' : 'text-slate-500';
    } else if (running.has(src)) { ic = 'ph-circle-notch animate-spin text-orange-500'; txt = 'Scanning…'; cls = 'text-orange-600'; }
    else { ic = 'ph-circle text-slate-300'; txt = 'Waiting'; cls = 'text-slate-400'; }
    return `<li class="flex items-center gap-2"><i class="ph ${ic} text-base"></i>
      <span class="flex-1 font-semibold text-slate-700">${name}</span><span class="${cls} font-semibold">${txt}</span></li>`;
  }).join('');

  const check = document.getElementById('scan-check');
  const total = progress.sites.reduce((n, s) => n + (s.added || 0), 0);
  if (progress.sites.length && total && lastModCounts) {
    // this search's posts only (26 Oct: it counted every search's waiting posts, "281 scraped")
    const mine = viewRun ? allInternships.filter(r => r.last_run === viewRun) : [];
    const held = viewRun ? mine.filter(r => r.moderation_status === 'held').length : lastModCounts.held;
    const left = viewRun ? mine.filter(r => ['', 'checking'].includes(r.moderation_status || '')).length
                         : lastModCounts.pending + lastModCounts.checking;
    const waiting = held ? ` ${held} more found: they're checked when you click "Load 5 more" under the list.` : '';
    check.innerHTML = left
      ? `<span class="flex items-start gap-2 text-amber-700"><i class="ph ph-shield-checkered text-base"></i> Scam check: ${left} being checked now.${waiting}</span>`
      : (held
          ? `<span class="flex items-start gap-2 text-slate-700"><i class="ph ph-tray text-base"></i> ${held} more found. Click "Load 5 more" under the list to check the next 5.</span>`
          : `<span class="flex items-start gap-2 text-emerald-700"><i class="ph ph-shield-check text-base"></i> All checked.</span>`);
    check.classList.remove('hidden');
  } else if (finished && !total) {
    check.innerHTML = '<span class="text-slate-500">No new internships this time. Try more sites or another field.</span>';
    check.classList.remove('hidden');
  } else {
    check.classList.add('hidden');
  }
}

// The panel's size (dragged at its top-right corner) and folded state, remembered in this browser
const SCAN_SIZE_KEY = 'inreal_scan_panel';
function scanSize(save) {
  try {
    if (save) localStorage.setItem(SCAN_SIZE_KEY, JSON.stringify(save));
    return JSON.parse(localStorage.getItem(SCAN_SIZE_KEY)) || {};
  } catch (e) { return save || {}; }
}
function applyScanSize(size) {
  const panel = document.getElementById('scan-panel');
  if (!panel) return;
  panel.style.width = size.w ? `${size.w}px` : '';
  panel.style.height = size.h ? `${size.h}px` : '';
  panel.classList.toggle('scan-min', !!size.min);
  const b = document.getElementById('scan-min');
  if (b) { b.title = size.min ? 'Show all sites' : 'Make smaller'; b.setAttribute('aria-label', b.title); }
}
document.addEventListener('DOMContentLoaded', () => {
  const panel = document.getElementById('scan-panel'), grip = document.getElementById('scan-resize');
  if (!panel || !grip) return;
  applyScanSize(scanSize());
  document.getElementById('scan-min')?.addEventListener('click', () => {
    const size = scanSize();
    applyScanSize(scanSize({ ...size, min: !size.min }));
  });
  // anchored bottom-left, so the top-right corner grows it up and to the right
  grip.addEventListener('pointerdown', (e) => {
    e.preventDefault();
    grip.setPointerCapture(e.pointerId);
    const r = panel.getBoundingClientRect(), x0 = e.clientX, y0 = e.clientY;
    panel.classList.add('resizing');
    const move = (ev) => {
      const w = Math.round(Math.min(window.innerWidth - 48, Math.max(260, r.width + ev.clientX - x0)));
      const h = Math.round(Math.min(window.innerHeight - 48, Math.max(150, r.height - (ev.clientY - y0))));
      applyScanSize({ w, h, min: false });
    };
    const up = () => {
      grip.removeEventListener('pointermove', move);
      panel.classList.remove('resizing');
      const b = panel.getBoundingClientRect();
      scanSize({ w: Math.round(b.width), h: Math.round(b.height), min: false });
    };
    grip.addEventListener('pointermove', move);
    grip.addEventListener('pointerup', up, { once: true });
  });
  grip.addEventListener('dblclick', () => applyScanSize(scanSize({})));
});

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('scan-close')?.addEventListener('click', () => {
    closedRunId = panelRunId;
    document.getElementById('scan-panel').classList.add('hidden');
  });
});


// ==========================================
// 14. Newly verified internships join the end of the list, with a short notice
// ==========================================
function announceNewlyVerified(rows) {
  const mine = rows.filter(r => r.moderation_status === 'approved' &&
    !freshVisit && (!viewRun || r.last_run === viewRun) &&
    (!profile || String(r.field || 'ai_ml').split(';').includes(profile.field)) &&
    !(profile && profile.experience !== '0' && isUnpaid(r)));
  const ids = new Set(mine.map(r => r.id));
  if (verifiedSeen) {
    const fresh = [...ids].filter(id => !verifiedSeen.has(id)).length;
    if (fresh) showToast('success', `${fresh} new verified internship${fresh > 1 ? 's' : ''}`,
      'Added at the end of the list. The cards above stay where they are.');
  }
  verifiedSeen = ids;
}


// ==========================================
// 15. Load more: release the next 5 scraped internships to the scam check
// ==========================================
let loadMoreBusy = false;
function updateHeldUI(c) {
  const held = viewRun
    ? allInternships.filter(r => r.moderation_status === 'held' && r.last_run === viewRun).length
    : (freshVisit ? 0 : ((c && c.held) || 0));
  const n = document.getElementById('held-count');
  if (n) n.textContent = held;
  const btn = document.getElementById('load-more-btn');
  const bar = document.getElementById('search-more-bar');
  if (!btn) return;
  // only this search's posts: the automatic update's posts go through the same check in the background
  const inFlight = viewRun
    ? allInternships.filter(r => r.last_run === viewRun && ['', 'checking'].includes(r.moderation_status || '')).length
    : (c.pending || 0) + (c.checking || 0);
  // a click is followed on the server until 5 are on screen (moderation/load_more.py)
  const job = c && c.load_more;
  const wasBusy = loadMoreBusy;
  if (job && job.run_tag === viewRun) loadMoreBusy = !!job.running;
  else if (loadMoreBusy && inFlight === 0) loadMoreBusy = false;   // the 5 have been judged
  if (wasBusy && !loadMoreBusy && job && job.run_tag === viewRun && job.shown < job.want) {
    // fewer than 5: say why, so an empty click doesn't look broken
    const why = job.done_reason === 'limit'
      ? `${job.checked} posts were checked and most did not pass. Click again to check the next ones.`
      : job.done_reason === 'none_left' ? 'Nothing else is waiting from this search. Use "Search more" for newer posts.'
      : 'The scam check did not answer in time. Try again in a minute.';
    showToast('info', `${job.shown} more on screen`, why);
  }
  // the bar belongs to a search on screen; it stays out of the way otherwise
  // first the search, then the automatic first 10; the button comes after (25 Oct)
  const runRows = viewRun ? allInternships.filter(r => r.last_run === viewRun) : [];
  const firstBatchBusy = !loadMoreBusy && inFlight > 0;
  // 28 Oct: the slow sites (LinkedIn, university boards) can search for minutes after the first 10
  // are shown; the button must not wait for them, so while they run it shows as soon as posts are held
  const showBar = canEdit && !showBookmarkedOnly && !showAllSaved && !!viewRun && !freshVisit
    && !firstBatchBusy && runRows.length > 0 && (!scrapeRunning || held > 0 || loadMoreBusy);
  if (bar) bar.classList.toggle('hidden', !showBar);
  const title = document.getElementById('queue-title'), sub = document.getElementById('queue-sub');
  if (title && sub) {
    if (loadMoreBusy) {
      const got = job && job.running ? job.shown : 0, want = (job && job.want) || 5;
      title.innerHTML = `Finding ${want} more for you… <span class="text-orange-600">${got} of ${want}</span>`;
      sub.textContent = 'Each post is checked for scams first. The ones that don\'t pass are replaced by the next ones.';
    }
    else if (held) { title.innerHTML = `<span id="held-count">${held}</span> more found`; sub.textContent = scrapeRunning ? 'They join the list after the scam check. The slower sites are still being searched.' : 'They join the list after the scam check.'; }
    else { title.innerHTML = 'That\'s everything found'; sub.textContent = 'Search the same sites again for newer posts.'; }
  }
  btn.classList.toggle('hidden', !held && !loadMoreBusy);
  const label = btn.querySelector('span');
  btn.disabled = loadMoreBusy || held === 0;
  btn.classList.toggle('opacity-60', btn.disabled);
  label.textContent = loadMoreBusy ? 'Checking…' : 'Load 5 more';
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('load-more-btn')?.addEventListener('click', async () => {
    try {
      const res = await fetch('/api/moderation/load-more', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ count: 5, run_tag: viewRun, show: activeModeration }) });
      if (res.status === 403) { showToast('info', 'View-only link', 'Load more works on the host laptop.'); return; }
      if (res.status === 409) return;   // the last click is still being filled
      const d = await res.json();
      if (!d.released) { showToast('info', 'Nothing waiting', 'Use "Search more" to scrape the sites again.'); return; }
      loadMoreBusy = true;
      updateHeldUI({ ...(lastModCounts || {}), held: d.held_left, pending: d.released, checking: 0, load_more: d.load_more });
      modPollMs = 1500;
    } catch (e) {
      showToast('error', 'Load more failed', 'The app is not answering. Is python app.py running?');
    }
  });
});


// ==========================================
// 16. Scam-check reasons in plain words (no raw API errors in the drawer)
// ==========================================
function plainReason(r) {
  let m;
  if ((m = r.match(/^LLM:\s*(\w+),\s*probability\s*([\d.]+)\s*[—-]\s*(.*)$/i))) {
    const word = { genuine: 'looks genuine', suspicious: 'is unsure', scam: 'thinks it is a scam' }[m[1].toLowerCase()] || m[1];
    return `AI reviewer ${word} (${Math.round(Number(m[2]) * 100)}% scam chance): ${m[3]}`;
  }
  if (/^Embedding failed/i.test(r)) return 'Wording check skipped: the similarity service did not answer in time. The AI reviewer and the rules decided.';
  if (/^LLM judge unavailable/i.test(r)) return 'AI reviewer did not answer, so the wording check and the rules decided.';
  if ((m = r.match(/^Vector match,\s*(.*?)\s*\(similarity\s*([\d.]+)\):\s*"?(.*?)"?$/i))) return `Wording close to a known scam (${m[1]}): "${m[3]}"`;
  if (/disagree/i.test(r)) return 'The AI reviewer and the wording check disagree, so a person should look at this one.';
  if ((m = r.match(/^Scraper warnings?:\s*(.*)$/i))) return `Note from the listing: ${m[1]}`;
  if (/[{}]|AxiosError|stack/.test(r)) return '';   // any other raw error text
  return r;
}


// ==========================================
// 17. One search at a time: note above the list, "Show all saved" toggle
// ==========================================
function setView(v) {
  showBookmarkedOnly = v === 'saved';
  showAllSaved = v === 'recent';
  displayOrder.clear(); renderedIds.clear();
  if (window.matchMedia('(max-width: 1023px)').matches) setFilterMenu(false);
  applyFiltersAndRender(); updateViewNote();
}

function updateViewNote() {
  const view = showBookmarkedOnly ? 'saved' : showAllSaved ? 'recent' : 'search';
  document.querySelectorAll('.jb-view').forEach(b => b.setAttribute('aria-selected', String(b.dataset.view === view)));
  const when = runWhen(viewRun);
  const title = { search: 'Internships for you', recent: 'Last 3 days', saved: 'Saved' }[view];
  const check = activeModeration === 'verified' ? ' Every post here passed the scam check.' : '';
  const sub = {
    search: freshVisit ? 'Nothing searched yet in this visit.' : `From your search ${when || 'on screen'}.${check}`,
    recent: `Everything checked in the last 3 days, from all searches.${check}`,
    saved: 'Posts you saved on this account.',
  }[view];
  const t = document.getElementById('list-title'), s2 = document.getElementById('list-sub');
  if (t) t.textContent = title;
  if (s2) s2.textContent = sub;
  updateHeldUI(lastModCounts || {});
}
// crossing 1280px: the side panel needs a post in it
let wasWide = isWide();
window.addEventListener('resize', () => {
  const wide = isWide();
  if (wide !== wasWide) { wasWide = wide; if (wide) applyFiltersAndRender(); }
});
document.addEventListener('DOMContentLoaded', updateViewNote);
// a tab left open for days: coming back to it drops the old search the same way a new visit does
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible' && !showAllSaved && !showBookmarkedOnly && dropStaleView()) {
    updateViewNote(); applyFiltersAndRender();
  }
});


// ==========================================
// 18. One session per page load: a refresh empties the list (internships.csv) on the laptop
// ==========================================
async function startSession() {
  try { await fetch('/api/session/new', { method: 'POST' }); } catch (e) { /* public link: 403, keep data */ }
  loadData();
}


// ==========================================
// 19. /app: Google sign-in in front of the dashboard
// ==========================================
// Signed out -> back to the landing page. Signed in -> the dashboard as above, with the Google
// photo on the avatar, a sign-out button, and the Admin link for accounts with is_admin.
function saveProfileToAccount(p) {
  if (!sb || !sbUserId || !p) return;
  const row = { name: p.name || null, field: p.field || null, experience: p.experience || '0',
                companies: p.companies || [], sources: p.sources || [], regions: p.regions || [],
                study_year: p.study_year || null, roles: p.roles || [], skills: (p.skills || []).slice(0, 15),
                work_mode: p.work_mode || null, max_duration: p.max_duration || null,
                min_stipend: (p.min_stipend === null || p.min_stipend === undefined || p.min_stipend === '') ? null : Number(p.min_stipend) };
  // .select() so a missing row (0 rows updated, which is not an error) is noticed: the row is
  // made again (ensure_profile) and the save repeated once (21 Oct: rows deleted by hand)
  const send = () => sb.from('profiles').update(row).eq('id', sbUserId).select('id');
  send().then(async ({ data, error }) => {
    if (!error && data && data.length) return;
    if (!error) {
      await sb.rpc('ensure_profile');
      ({ data, error } = await send());
      if (!error && data && data.length) return;
    }
    showToast('error', 'Profile saved only in this browser', error ? error.message : 'Your account could not be updated. Sign out and in again.');
  });
}

async function requireSignIn() {
  if (!sb) {
    showToast('error', 'Sign-in is not set up', 'SUPABASE_URL or SUPABASE_PUBLISHABLE_KEY is missing in .env.');
    return false;
  }
  const { data } = await sb.auth.getSession();
  if (!data.session) { location.replace('/'); return false; }
  const user = data.session.user;
  sb.auth.onAuthStateChange((event, session) => { if (!session) location.replace('/'); });
  document.getElementById('sign-out-btn')?.addEventListener('click', async () => {
    await sb.auth.signOut();
    location.replace('/');
  });
  const btn = document.getElementById('sign-out-btn');
  if (btn && user.email) btn.title = `Sign out (${user.email})`;
  sbUserEmail = user.email || '';

  const meta = user.user_metadata || {};
  sbUserId = user.id;
  const COLS = 'name,avatar_url,username,avatar_preset,banner_url,banner_preset,is_admin,field,experience,companies,sources,regions,study_year,roles,skills,work_mode,min_stipend,max_duration';
  let { data: account, error: accountError } = await sb.from('profiles').select(COLS).eq('id', user.id).maybeSingle();
  if (!accountError && !account) {   // the row is missing (deleted by hand): make it again
    await sb.rpc('ensure_profile');
    ({ data: account, error: accountError } = await sb.from('profiles').select(COLS).eq('id', user.id).maybeSingle());
  }
  // The account is the truth: what it says wins over the copy in this browser, also when it was
  // emptied (21 Oct: a reset account was refilled from the browser). The browser copy is used only
  // when the account could not be read at all.
  if (account && account.field) {
    writeProfile({
      name: account.name || meta.full_name || '',
      field: account.field,
      experience: account.experience || '0',
      companies: account.companies || [],
      sources: account.sources || [],
      regions: account.regions || [],
      study_year: account.study_year || null,
      roles: account.roles || [],
      skills: account.skills || [],
      work_mode: account.work_mode || null,
      min_stipend: account.min_stipend,
      max_duration: account.max_duration || null,
    });
  } else if (!account && profile && profile.owner === user.id) {
    // account unreachable right now: keep working from this browser's copy
  } else {
    profile = null;                         // another account's, or none: this one fills the form
    try { localStorage.removeItem(PROFILE_KEY); } catch (e) { /* private window */ }
  }
  BOOKMARK_KEY = `inreal_bookmarks:${user.id}`;
  try { bookmarks = JSON.parse(localStorage.getItem(BOOKMARK_KEY) || '[]'); } catch (e) { bookmarks = []; }
  identity.photo = (account && account.avatar_url) || '';
  identity.google = meta.avatar_url || meta.picture || '';
  identity.preset = (account && account.avatar_preset) || '';
  identity.username = (account && account.username) || '';
  identity.banner = (account && account.banner_url) || '';
  identity.bannerPreset = (account && account.banner_preset) || '';
  renderAvatars();
  const admin = document.getElementById('admin-link');
  if (admin && account && account.is_admin) { admin.classList.remove('hidden'); admin.classList.add('inline-flex'); }
  if (account && account.is_admin) document.getElementById('pm-admin')?.classList.remove('hidden');
  // first visit: the profile form starts with the Google name
  if (!profile) {
    const name = document.getElementById('profile-name');
    if (name && !name.value) name.value = (account && account.name) || meta.full_name || '';
  }
  return true;
}



// ==========================================
// 20. My applications (1 Nov): InReal can't see the other site, so it asks "did you apply?" when you
//     come back, keeps the answer in your account, and marks the post "Applied" wherever it shows up
// ==========================================
const applications = new Map();   // listing_id -> { listing_id, role_title, company_name, source_platform, apply_link, applied_at }
const appsKey = () => `inreal_applications:${sbUserId || 'laptop'}`;   // this browser, when there is no account (/admin)
const normKey = (t) => String(t || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
const shortDate = (iso) => { const d = new Date(iso); return isNaN(d) ? '' : d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' }); };

function saveAppsLocally() {
  try { localStorage.setItem(appsKey(), JSON.stringify([...applications.values()])); } catch (e) { /* private window */ }
}
async function loadApplications() {
  let rows = null;
  if (sb && sbUserId) {
    const { data, error } = await sb.from('applications')
      .select('listing_id,role_title,company_name,source_platform,apply_link,applied_at,status,status_at').order('applied_at', { ascending: false });
    if (!error && Array.isArray(data)) rows = data;
  }
  if (!rows) { try { rows = JSON.parse(localStorage.getItem(appsKey()) || '[]'); } catch (e) { rows = []; } }
  applications.clear();
  rows.forEach(r => applications.set(r.listing_id, r));
  refreshApplied();
}
// the same internship found again (same company and role, maybe on another site) counts as applied too
function appliedFor(item) {
  if (!item) return null;
  const direct = applications.get(item.id);
  if (direct) return direct;
  const co = normKey(item.company_name), role = normKey(item.role_title);
  if (!co || !role) return null;
  for (const a of applications.values()) if (normKey(a.company_name) === co && normKey(a.role_title) === role) return a;
  return null;
}
function appliedTag(item) {
  const a = appliedFor(item);
  return a ? `<span class="jb-tag jb-tag-applied"><i class="ph ph-check-circle"></i>Applied ${escapeHtml(shortDate(a.applied_at))}</span>` : '';
}
function refreshApplied() {
  applyFiltersAndRender();
  updateDrawerApplied();
  if (profileMenuOpen()) fillProfileMenu();
  if (appsPageOpen()) renderAppsList();
}

async function markApplied(item) {
  if (!item || applications.has(item.id)) return;
  const row = {
    listing_id: String(item.id).slice(0, 200),
    role_title: String(item.role_title || '').slice(0, 300),
    company_name: String(item.company_name || '').slice(0, 200),
    source_platform: String(item.source_platform || '').slice(0, 100),
    apply_link: /^https?:\/\//i.test(item.apply_link || '') ? String(item.apply_link).slice(0, 2000) : null,
    applied_at: new Date().toISOString(),
  };
  applications.set(row.listing_id, { ...row, status: 'applied' });
  refreshApplied();
  if (sb && sbUserId) {
    const { error } = await sb.from('applications').insert(row);
    if (error && error.code !== '23505') {   // 23505: already there
      applications.delete(row.listing_id); refreshApplied();
      showToast('error', 'Not saved', 'Your application could not be saved. Check the connection and try again.');
      return;
    }
  } else saveAppsLocally();
  showToast('success', 'Added to My applications', `${row.role_title || 'Internship'}${row.company_name ? ` at ${row.company_name}` : ''}. It's marked "Applied" if it shows up again.`);
}
async function unmarkApplied(id) {
  const row = applications.get(id);
  if (!row) return;
  applications.delete(id);
  refreshApplied();
  if (sb && sbUserId) {
    const { error } = await sb.from('applications').delete().eq('listing_id', id);
    if (error) { applications.set(id, row); refreshApplied(); showToast('error', 'Not removed', 'Try again in a moment.'); }
  } else saveAppsLocally();
}

// the line above Apply in the open post: "Applied on 1 Nov · Undo" or "Already applied? Mark it"
function updateDrawerApplied() {
  const box = document.getElementById('drawer-applied');
  if (!box) return;
  const item = activeDrawerJob;
  if (!item) { box.classList.add('hidden'); return; }
  const a = appliedFor(item);
  box.classList.remove('hidden');
  box.classList.toggle('is-applied', !!a);
  box.innerHTML = a
    ? `<i class="ph-fill ph-check-circle"></i><span>You applied on ${escapeHtml(shortDate(a.applied_at))}</span><span class="dot">·</span><button type="button" data-applied-undo>Undo</button>`
    : `<span>Already applied?</span><button type="button" data-applied-mark>Mark it</button>`;
}
document.addEventListener('click', (e) => {
  if (e.target.closest('[data-applied-mark]')) markApplied(activeDrawerJob);
  const undo = e.target.closest('[data-applied-undo]');
  if (undo && activeDrawerJob) { const a = appliedFor(activeDrawerJob); if (a) unmarkApplied(a.listing_id); }
});

// "Apply" opens the post's own site in a new tab; coming back to InReal asks if you applied.
// Coming back is noticed in every way a browser reports it: the tab shows again, the window gets the
// focus back, or (where neither fires) the first mouse move or key press after leaving (1 Nov: the
// card did not appear; a quick look also counted as "only glanced", now that is 1.5 s, not 4 s).
let pendingApply = null;
document.addEventListener('click', (e) => {
  if (!e.target.closest('#drawer-apply-link') || !activeDrawerJob) return;
  if (!/^https?:\/\//i.test(activeDrawerJob.apply_link || '') || appliedFor(activeDrawerJob)) return;
  pendingApply = { item: activeDrawerJob, at: Date.now(), away: false };
});
function wentAway() { if (pendingApply) pendingApply.away = true; }
function cameBack() {
  if (!pendingApply || document.visibilityState !== 'visible') return;
  if (!pendingApply.away && Date.now() - pendingApply.at < 1500) return;   // still the click itself
  const { item, at } = pendingApply;
  pendingApply = null;
  if (Date.now() - at < 1500) return;   // back at once: the page was only glanced at
  showApplyAsk(item);
}
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') wentAway(); else cameBack(); });
window.addEventListener('blur', wentAway);
window.addEventListener('focus', cameBack);
['pointermove', 'keydown'].forEach(t => document.addEventListener(t, () => { if (pendingApply && pendingApply.away) cameBack(); }, { passive: true }));

let askItem = null;
function showApplyAsk(item) {
  const box = document.getElementById('apply-ask');
  if (!box || appliedFor(item)) return;
  askItem = item;
  document.getElementById('apply-ask-q').textContent = 'Did you apply?';
  document.getElementById('apply-ask-sub').textContent = `${item.role_title || 'Internship'}${item.company_name ? ` at ${item.company_name}` : ''}`;
  box.classList.remove('hidden', 'leaving');
  setTimeout(() => document.getElementById('apply-ask-yes')?.focus({ preventScroll: true }), 50);
}
function hideApplyAsk() {
  const box = document.getElementById('apply-ask');
  if (!box || box.classList.contains('hidden')) return;
  box.classList.add('leaving');
  setTimeout(() => { box.classList.add('hidden'); box.classList.remove('leaving'); }, 180);
  askItem = null;
}
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('apply-ask-yes')?.addEventListener('click', () => { const it = askItem; hideApplyAsk(); markApplied(it); });
  document.getElementById('apply-ask-no')?.addEventListener('click', hideApplyAsk);
});

// the list, newest first
function renderAppsList() {
  const list = document.getElementById('apps-list'), sub = document.getElementById('apps-sub');
  if (!list) return;
  const rows = [...applications.values()].sort((a, b) => String(b.applied_at).localeCompare(String(a.applied_at)));
  if (sub) sub.textContent = rows.length
    ? `${rows.length} internship${rows.length === 1 ? '' : 's'} you applied to from InReal, newest first.`
    : 'Internships you applied to from InReal.';
  const stats = document.getElementById('apps-stats');
  if (stats) {
    const now = Date.now(), within = (days) => rows.filter(a => now - new Date(a.applied_at).getTime() < days * 864e5).length;
    const at = (st) => rows.filter(a => (a.status || 'applied') === st).length;
    stats.innerHTML = rows.length ? [['Total', rows.length], ['Last 7 days', within(7)], ['Interviews', at('interview')], ['Offers', at('offer')]]
      .map(([k, v]) => `<div class="apps-stat"><b>${v}</b><span>${k}</span></div>`).join('') : '';
  }
  list.innerHTML = rows.length ? rows.map(a => {
    const link = /^https?:\/\//i.test(a.apply_link || '') ? a.apply_link : '';
    const post = allInternships.find(r => r.id === a.listing_id);   // the logo, if the post is still in the list
    return `<li class="app-row">
      ${logoHtml(a.company_name, post && post.logo)}
      <div class="min-w-0 flex-1">
        <div class="app-title">${escapeHtml(a.role_title || 'Internship')}</div>
        <div class="app-meta">${escapeHtml(a.company_name || '')}${a.source_platform ? ` · ${escapeHtml(a.source_platform)}` : ''}</div>
        <div class="app-date"><i class="ph ph-check-circle"></i> Applied ${escapeHtml(shortDate(a.applied_at))}</div>
        <label class="app-status app-status-${escapeHtml(a.status || 'applied')}"><span class="sr-only">Status</span>
          <select data-app-status="${escapeHtml(a.listing_id)}">${APP_STATUSES.map(([v, t]) =>
            `<option value="${v}"${(a.status || 'applied') === v ? ' selected' : ''}>${t}</option>`).join('')}</select>
        </label>
      </div>
      <div class="flex flex-col gap-1.5 shrink-0">
        ${link ? `<a class="app-btn" href="${escapeHtml(link)}" target="_blank" rel="noopener noreferrer">Open <i class="ph ph-arrow-up-right"></i></a>` : ''}
        <button type="button" class="app-btn app-btn-quiet" data-app-remove="${escapeHtml(a.listing_id)}">Remove</button>
      </div>
    </li>`;
  }).join('') : `<li class="app-empty"><i class="ph ph-paper-plane-tilt"></i>
      <b>No applications yet</b>
      <span>Open a post and click "Apply on the original site". When you come back, InReal asks if you applied and keeps it here.</span></li>`;
}
// My applications is its own page: /app/applications (or /admin/applications). It is shown in place of
// the list in this same document, so Back (the link, the browser button or the logo) returns to the
// list with the current search still there; a page load would start a new session and empty it.
const HOME_PATH = USER_MODE ? '/app' : '/admin';
const APPS_PATH = HOME_PATH + '/applications';
let homeTitle = document.title, homeScroll = 0;
function appsPageOpen() { return document.body.classList.contains('page-apps'); }
function showAppsPage(push = true) {
  const page = document.getElementById('apps-page');
  if (!page) return;
  if (!appsPageOpen()) { homeScroll = window.scrollY; homeTitle = document.title; }
  closeDetailDrawer();
  if (typeof setFilterMenu === 'function') setFilterMenu(false);
  renderAppsList();
  document.body.classList.add('page-apps');
  page.classList.remove('hidden');
  if (push && location.pathname !== APPS_PATH) history.pushState({ page: 'apps' }, '', APPS_PATH);
  document.title = 'My applications · InReal';
  window.scrollTo(0, 0);
  document.getElementById('apps-title')?.focus({ preventScroll: true });
}
function hideAppsPage() {
  if (!appsPageOpen()) return;
  document.body.classList.remove('page-apps');
  document.getElementById('apps-page')?.classList.add('hidden');
  document.title = homeTitle;
  requestAnimationFrame(() => window.scrollTo(0, homeScroll));
}
function leaveAppsPage() {
  // opened from the menu: step back in history (the browser's Back stays in step); opened by link: replace
  if (history.state && history.state.page === 'apps') history.back();
  else { history.replaceState(null, '', HOME_PATH); hideAppsPage(); }
}
window.addEventListener('popstate', () => { if (location.pathname === APPS_PATH) showAppsPage(false); else hideAppsPage(); });
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('apps-back')?.addEventListener('click', (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault();
    leaveAppsPage();
  });
  // the logo goes home too: from this page that is the list, without a reload
  document.getElementById('brand-home')?.addEventListener('click', (e) => {
    if (!appsPageOpen() || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    leaveAppsPage();
  }, true);
  if (location.pathname === APPS_PATH) showAppsPage(false);   // opened at /app/applications (a refresh, a link)
});
// Where an application stands (2 Nov): set by the user, like "Applied" itself
const APP_STATUSES = [['applied', 'Applied, waiting'], ['interview', 'Interview'], ['offer', 'Offer'],
  ['rejected', 'Not selected'], ['no_reply', 'No reply']];
async function setAppStatus(id, status) {
  const a = applications.get(id);
  if (!a || !APP_STATUSES.some(([v]) => v === status)) return;
  const before = a.status || 'applied';
  a.status = status; a.status_at = new Date().toISOString();
  renderAppsList();
  if (sb && sbUserId) {
    const { error } = await sb.from('applications').update({ status, status_at: a.status_at }).eq('listing_id', id);
    if (error) { a.status = before; renderAppsList(); showToast('error', 'Not saved', 'The status could not be saved. Try again.'); }
  } else saveAppsLocally();
}
document.addEventListener('change', (e) => {
  const sel = e.target.closest && e.target.closest('[data-app-status]');
  if (sel) setAppStatus(sel.dataset.appStatus, sel.value);
});

// Closing soon (2 Nov): "Apply by" within 3 days, on cards not applied to yet, and one reminder per
// visit for saved posts about to close. Only sites that give a date (AICTE, Unstop, Foundit, ...).
function daysLeft(item) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(item && item.application_deadline || ''));
  if (!m) return null;
  const end = new Date(+m[1], +m[2] - 1, +m[3], 23, 59, 59);
  const today = new Date(); today.setHours(0, 0, 0, 0);
  return Math.floor((end - today) / 864e5);
}
function closingTag(item) {
  const d = daysLeft(item);
  if (d === null || d < 0 || d > 3 || appliedFor(item)) return '';
  return `<span class="jb-tag jb-tag-closing"><i class="ph ph-hourglass-medium"></i>${d === 0 ? 'Closes today' : d === 1 ? 'Closes tomorrow' : `Closes in ${d} days`}</span>`;
}
let closingReminded = false;
function remindClosingSaved() {
  if (closingReminded || !allInternships.length) return;
  const soon = allInternships.filter(i => bookmarks.includes(i.id) && !appliedFor(i) && !reported.has(i.id)
    && (d => d !== null && d >= 0 && d <= 3)(daysLeft(i)));
  closingReminded = true;
  if (!soon.length) return;
  const first = soon.sort((a, b) => daysLeft(a) - daysLeft(b))[0];
  showToast('info', soon.length === 1 ? 'A saved internship closes soon' : `${soon.length} saved internships close soon`,
    `${first.role_title || 'Internship'}${first.company_name ? ' at ' + first.company_name : ''}: ${daysLeft(first) === 0 ? 'today is the last day' : `apply by ${shortDate(first.application_deadline)}`}. Open "Saved" to see ${soon.length === 1 ? 'it' : 'them'}.`);
}

document.addEventListener('click', (e) => {
  const rm = e.target.closest('[data-app-remove]');
  if (rm) unmarkApplied(rm.dataset.appRemove);
});


// ==========================================
// 21. My profile (1 Nov): name, @username, a photo or a drawn avatar, and what the list uses
// ==========================================
const identity = { photo: '', google: '', preset: '', username: '', banner: '', bannerPreset: '' };
// drawn avatars: an emoji on a gradient. Stored as "p:<key>" in profiles.avatar_preset
const AVATAR_PRESETS = [
  ['fox', '🦊', '#FB923C,#F43F5E'], ['owl', '🦉', '#A78BFA,#6366F1'], ['panda', '🐼', '#94A3B8,#334155'],
  ['tiger', '🐯', '#FBBF24,#F97316'], ['octo', '🐙', '#F472B6,#A855F7'], ['whale', '🐳', '#38BDF8,#2563EB'],
  ['rocket', '🚀', '#818CF8,#0EA5E9'], ['brain', '🧠', '#F9A8D4,#EC4899'], ['bolt', '⚡', '#FDE047,#F59E0B'],
  ['cactus', '🌵', '#86EFAC,#16A34A'], ['ufo', '🛸', '#5EEAD4,#0D9488'], ['game', '🎮', '#C4B5FD,#7C3AED'],
  ['music', '🎧', '#FDA4AF,#E11D48'], ['penguin', '🐧', '#BAE6FD,#0369A1'], ['unicorn', '🦄', '#F0ABFC,#818CF8'],
  ['sakura', '🌸', '#FBCFE8,#F472B6'], ['laptop', '💻', '#CBD5E1,#475569'], ['coffee', '☕', '#FCD34D,#92400E'],
];
const presetFor = (v) => { const k = String(v || '').replace(/^p:/, ''); return AVATAR_PRESETS.find(p => p[0] === k) || null; };
const initialsOf = (name) => (name || '').split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join('');
function avatarHtml() {
  const pre = presetFor(identity.preset);
  if (pre) {
    const [c1, c2] = pre[2].split(',');
    return `<span class="av-preset" style="background:linear-gradient(135deg,${c1},${c2})">${pre[1]}</span>`;
  }
  const photo = identity.preset === 'p:none' ? '' : (identity.photo || identity.google);
  if (/^https:\/\//i.test(photo)) return `<img src="${escapeHtml(photo)}" alt="" referrerpolicy="no-referrer" class="w-full h-full rounded-full object-cover">`;
  const ini = initialsOf(profile && profile.name);
  return ini ? `<span class="av-initials">${escapeHtml(ini)}</span>` : '<i class="ph ph-user text-lg"></i>';
}
function renderAvatars() {
  const html = avatarHtml();
  ['profile-avatar', 'pm-avatar', 'me-avatar'].forEach(id => { const el = document.getElementById(id); if (el) el.innerHTML = html; });
  sharpenAvatars();
}

// A 512 px photo shown at 40 px (less when the browser is zoomed out) is shrunk by the browser in one
// rough step, which looks blurred and jagged (1 Nov). Each slot gets its own copy, shrunk in halves
// to exactly the pixels it has, and made again when the zoom changes.
const avatarThumbs = new Map();   // "url|px" -> data URL (or the url itself when the picture can't be read)
function loadImg(src) {
  return new Promise((res, rej) => {
    const im = new Image();
    im.crossOrigin = 'anonymous';
    im.referrerPolicy = 'no-referrer';
    im.onload = () => res(im); im.onerror = rej;
    im.src = src;
  });
}
async function thumbFor(src, px) {
  const key = `${src}|${px}`;
  if (avatarThumbs.has(key)) return avatarThumbs.get(key);
  let out = src;
  try {
    const im = await loadImg(src);
    let canvas = document.createElement('canvas'), w = im.naturalWidth, h = im.naturalHeight;
    const side = Math.min(w, h);
    canvas.width = canvas.height = side;
    canvas.getContext('2d').drawImage(im, (w - side) / 2, (h - side) / 2, side, side, 0, 0, side, side);
    while (canvas.width / 2 >= px) {   // halve until one step from the size wanted
      const half = document.createElement('canvas');
      half.width = half.height = Math.floor(canvas.width / 2);
      const ctx = half.getContext('2d'); ctx.imageSmoothingQuality = 'high';
      ctx.drawImage(canvas, 0, 0, half.width, half.height);
      canvas = half;
    }
    const fin = document.createElement('canvas');
    fin.width = fin.height = px;
    const ctx = fin.getContext('2d'); ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(canvas, 0, 0, px, px);
    out = fin.toDataURL('image/png');
  } catch (e) { /* a picture that can't be read (no CORS): the browser shrinks it as before */ }
  avatarThumbs.set(key, out);
  return out;
}
function sharpenAvatars() {
  const src = (() => { const p = identity.preset === 'p:none' ? '' : (identity.photo || identity.google); return /^https:\/\//i.test(p) && !presetFor(identity.preset) ? p : ''; })();
  if (!src) return;
  const dpr = window.devicePixelRatio || 1;
  ['profile-avatar', 'pm-avatar', 'me-avatar'].forEach(async (id) => {
    const img = document.querySelector(`#${id} img`);
    if (!img) return;
    const cssSize = img.offsetWidth || img.parentElement?.offsetWidth || 0;   // layout size: ignores the opening animation's scale
    if (!cssSize) return;   // not on screen yet (menu closed): done when it opens
    // twice the pixels the slot has right now: the browser then only halves it (which stays sharp),
    // and zooming in up to 2x still has real pixels even before the copy is remade (1 Nov: exactly
    // 1x looked blurred after zooming in)
    const px = Math.max(32, Math.ceil(cssSize * dpr * 2));
    if (px >= 512) return;   // big enough to use the picture itself
    const thumb = await thumbFor(src, px);
    if (img.isConnected) img.src = thumb;
  });
}
// zooming the browser changes the pixels per slot
let lastDpr = window.devicePixelRatio;
function onZoom() { if (window.devicePixelRatio !== lastDpr) { lastDpr = window.devicePixelRatio; renderAvatars(); } }
window.addEventListener('resize', onZoom);
(function watchDpr() {   // also when the zoom changes without a resize event
  const mq = window.matchMedia(`(resolution: ${window.devicePixelRatio}dppx)`);
  mq.addEventListener('change', () => { onZoom(); watchDpr(); }, { once: true });
})();

async function saveIdentity(fields) {
  if (!sb || !sbUserId) { showToast('info', 'Sign in first', 'Your picture and username are saved to your account.'); return false; }
  const { error } = await sb.from('profiles').update(fields).eq('id', sbUserId);
  if (error) {
    const taken = /unique|duplicate/i.test(error.message || '');
    showToast('error', taken ? 'Username taken' : 'Not saved', taken ? 'Someone already has that username. Try another.' : 'Check the connection and try again.');
    return false;
  }
  return true;
}

function openMeModal() {
  fillMe();
  openModal(document.getElementById('me-modal'));
  requestAnimationFrame(sharpenAvatars);
}
function fillMe() {
  const p = profile || {};
  const set = (id, text) => { const el = document.getElementById(id); if (el) el.textContent = text; };
  const { pct } = profileCompletion(profile);
  set('me-title', p.name || 'You');
  set('me-username', identity.username ? `@${identity.username}` : '@pick-a-username');
  set('me-field', fieldLabels[p.field] || p.field || 'No field yet');
  set('me-level', PROFILE_LEVELS[pct / 20]);
  set('me-pct', `${pct}% profile`);
  const count = (st) => allInternships.filter(r => r.moderation_status === st).length;
  set('me-applied', applications.size); set('me-saved', bookmarks.length);
  set('me-verified', count('approved')); set('me-scams', count('blocked'));
  const nameIn = document.getElementById('me-name-input'), userIn = document.getElementById('me-username-input');
  if (nameIn && document.activeElement !== nameIn) nameIn.value = p.name || '';
  if (userIn && document.activeElement !== userIn) userIn.value = identity.username || '';
  usernameState('');
  document.getElementById('me-use-google')?.classList.toggle('hidden', !identity.google);
  renderAvatars();
  applyBanner();
  renderMeSummary();
}
function renderPresets() {
  const box = document.getElementById('me-presets');
  if (!box) return;
  box.innerHTML = AVATAR_PRESETS.map(([k, emoji, colors]) => {
    const [c1, c2] = colors.split(',');
    const on = identity.preset === `p:${k}`;
    return `<button type="button" class="me-preset${on ? ' on' : ''}" data-preset="${k}" aria-label="Avatar ${k}" aria-pressed="${on}" style="background:linear-gradient(135deg,${c1},${c2})">${emoji}</button>`;
  }).join('');
}
function renderMeSummary() {
  const box = document.getElementById('me-summary');
  if (!box) return;
  const p = profile || {};
  const roleLabels = Object.fromEntries(((window.PROFILE_ROLES || {})[p.field] || []).map(r => [r.key, r.label]));
  const chips = (list) => (list || []).length ? (list || []).map(x => `<span class="me-tag">${escapeHtml(x)}</span>`).join('') : '<span class="me-empty">Not set</span>';
  const year = p.study_year ? (p.study_year === 'grad' ? 'Graduated' : `${p.study_year}${{ 1: 'st', 2: 'nd', 3: 'rd' }[p.study_year] || 'th'} year`) : '';
  const exp = { '0': 'No experience yet', '1-2': '1–2 years', '3+': '3+ years' }[p.experience] || '';
  const mode = { remote: 'Remote only', office: 'Office / hybrid', any: 'Any work mode' }[p.work_mode] || '';
  const stipend = Number(p.min_stipend) > 0 ? `₹${Number(p.min_stipend).toLocaleString('en-IN')}+ a month` : (p.min_stipend === 0 || p.min_stipend === '0' ? 'Any stipend' : '');
  const dur = p.max_duration && p.max_duration !== 'any' ? `Up to ${p.max_duration} months` : (p.max_duration === 'any' ? 'Any length' : '');
  const parts = [
    [1, 'About you', chips([year, exp].filter(Boolean))],
    [2, 'What you want', chips([fieldLabels[p.field] || p.field, ...(p.roles || []).map(r => roleLabels[r] || r)].filter(Boolean))],
    [3, 'Skills', chips(p.skills)],
    [4, 'Preferences', chips([mode, stipend, dur, ...(p.companies || []).map(c => `★ ${c}`)].filter(Boolean))],
    [5, 'Search', chips((p.regions || []).map(r => r.charAt(0).toUpperCase() + r.slice(1)))],
  ];
  box.innerHTML = parts.map(([step, title, body]) => `<div class="me-row">
      <div class="me-row-head"><span>${sectionDone(p, step) ? '<i class="ph ph-check-circle me-ok"></i>' : '<i class="ph ph-circle-dashed me-todo"></i>'}${title}</span>
        <button type="button" class="me-link" data-me-edit="${step}">Edit</button></div>
      <div class="me-tags">${body}</div></div>`).join('');
}

// username: lowercase as you type, and ask the account if it's free
let usernameTimer = null, usernameOk = true;
function usernameState(kind, text) {
  const el = document.getElementById('me-username-state');
  if (!el) return;
  el.className = `me-note flex-1 ${kind ? 'me-' + kind : ''}`;
  el.textContent = text || '3 to 20 letters, numbers, _ or . (lowercase)';
}
function checkUsername() {
  const input = document.getElementById('me-username-input');
  const v = input.value.toLowerCase().replace(/[^a-z0-9_.]/g, '');
  if (input.value !== v) input.value = v;
  clearTimeout(usernameTimer);
  if (!v || v === identity.username) { usernameOk = true; usernameState(''); return; }
  if (v.length < 3) { usernameOk = false; usernameState('bad', 'At least 3 characters.'); return; }
  usernameOk = false;
  usernameState('', 'Checking…');
  usernameTimer = setTimeout(async () => {
    if (!sb) { usernameOk = true; usernameState(''); return; }
    const { data, error } = await sb.rpc('username_available', { name: v });
    if (input.value !== v) return;   // typed on meanwhile
    usernameOk = !error && data === true;
    usernameState(usernameOk ? 'good' : 'bad', error ? 'Could not check right now.' : usernameOk ? `@${v} is free` : `@${v} is taken`);
  }, 350);
}
async function saveNameAndUsername() {
  const name = (document.getElementById('me-name-input').value || '').trim().slice(0, 60);
  const username = document.getElementById('me-username-input').value.trim();
  if (!name) { showToast('error', 'Name is empty', 'Write the name you want on InReal.'); return; }
  if (username && (!/^[a-z0-9_.]{3,20}$/.test(username) || !usernameOk)) { showToast('error', 'Pick another username', 'It must be free and 3 to 20 characters.'); return; }
  const fields = { name, username: username || null };
  if (!(await saveIdentity(fields))) return;
  identity.username = username;
  if (profile) { writeProfile({ ...profile, name }); updateProfileUI(); }
  fillMe(); fillProfileMenu();
  showToast('success', 'Saved', username ? `You're @${username} on InReal.` : 'Your name is updated.');
}

async function choosePreset(key) {
  const before = identity.preset;
  identity.preset = `p:${key}`;
  renderAvatars(); renderPresets();
  if (!(await saveIdentity({ avatar_preset: identity.preset }))) { identity.preset = before; renderAvatars(); renderPresets(); }
}
async function useInitials() {
  const before = { ...identity };
  identity.preset = 'p:none'; identity.photo = '';
  renderAvatars(); renderPresets();
  if (!(await saveIdentity({ avatar_preset: 'p:none', avatar_url: null }))) { Object.assign(identity, before); renderAvatars(); }
}
async function useGooglePhoto() {
  const before = { ...identity };
  identity.preset = ''; identity.photo = identity.google;
  renderAvatars(); renderPresets();
  if (!(await saveIdentity({ avatar_preset: null, avatar_url: /^https:\/\//.test(identity.google) ? identity.google : null }))) { Object.assign(identity, before); renderAvatars(); }
}

// a photo: first the editor (move, zoom, turn), then it is drawn at 512 px and re-encoded in the
// browser (drops EXIF, like the place the photo was taken) and stored in the account's own folder;
// the old upload is removed
async function uploadPhoto(file) {
  if (!file) return;
  if (!sb || !sbUserId) { showToast('info', 'Sign in first', 'Your picture is saved to your account.'); return; }
  if (!/^image\/(png|jpe?g|webp)$/.test(file.type) || file.size > 15 * 1024 * 1024) {
    showToast('error', 'Pick another photo', 'Use a JPG, PNG or WebP photo under 15 MB.'); return;
  }
  let bmp;
  try { bmp = await createImageBitmap(file); } catch (e) { showToast('error', 'Pick another photo', 'This photo could not be opened.'); return; }
  openCropper(bmp);
}

async function savePhotoBlob(blob, what = 'photo') {
  const note = document.getElementById('me-photo-note');
  if (note) note.textContent = 'Uploading…';
  try {
    const path = `${sbUserId}/${Date.now()}.webp`;
    const up = await sb.storage.from('avatars').upload(path, blob, { contentType: 'image/webp', upsert: false });
    if (up.error) throw up.error;
    const url = sb.storage.from('avatars').getPublicUrl(path).data.publicUrl;
    const old = identity.photo;
    if (!(await saveIdentity({ avatar_url: url, avatar_preset: null }))) return;
    identity.photo = url; identity.preset = '';
    renderAvatars(); renderPresets();
    const mine = `/avatars/${sbUserId}/`;
    if (old && old.includes(mine)) sb.storage.from('avatars').remove([old.slice(old.indexOf(mine) + '/avatars/'.length)]);
    showToast('success', what === 'character' ? 'Avatar updated' : 'Photo updated', 'Your new picture is saved to your account.');
  } catch (e) {
    console.error('Photo upload failed:', e);   // the storage message is for the console, not the person
    showToast('error', 'Photo not uploaded', 'The upload did not go through. Try again in a moment, or pick another photo.');
  } finally {
    if (note) note.textContent = 'JPG, PNG or WebP. You can move, zoom and turn it before it is saved; the photo\'s hidden details (like location) are removed.';
  }
}

// ---- the photo editor: one canvas, a round window (picture) or a wide one (banner), drag / zoom / turn ----
const crop = { bmp: null, mode: 'avatar', rot: 0, zoom: 1, x: 0, y: 0, vw: 300, vh: 300, drag: null, pinch: null };
const BANNER_RATIO = 4;   // 1200 x 300, the same shape as the banner on the profile
function cropDims() {   // the photo's width and height after turning
  const b = crop.bmp, side = crop.rot % 180 === 0;
  return side ? [b.width, b.height] : [b.height, b.width];
}
function cropScale() {   // zoom 1 = the photo just covers the window
  const [w, h] = cropDims();
  return Math.max(crop.vw / w, crop.vh / h) * crop.zoom;
}
function clampCrop() {   // never show an empty edge inside the window
  const [w, h] = cropDims(), s = cropScale();
  const mx = Math.max(0, (w * s - crop.vw) / 2), my = Math.max(0, (h * s - crop.vh) / 2);
  crop.x = Math.min(mx, Math.max(-mx, crop.x));
  crop.y = Math.min(my, Math.max(-my, crop.y));
}
function paintCrop(ctx, W, H, withMask) {
  const k = W / crop.vw, s = cropScale() * k;
  ctx.save();
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = '#0F172A'; ctx.fillRect(0, 0, W, H);
  ctx.translate(W / 2 + crop.x * k, H / 2 + crop.y * k);
  ctx.rotate(crop.rot * Math.PI / 180);
  ctx.scale(s, s);
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(crop.bmp, -crop.bmp.width / 2, -crop.bmp.height / 2);
  ctx.restore();
  if (withMask && crop.mode === 'avatar') {   // dim everything outside the circle, then a thin ring
    ctx.save();
    ctx.fillStyle = 'rgba(15, 23, 42, .55)';
    ctx.beginPath(); ctx.rect(0, 0, W, H); ctx.arc(W / 2, H / 2, W / 2 - 2 * k, 0, Math.PI * 2, true); ctx.fill('evenodd');
    ctx.strokeStyle = 'rgba(255, 255, 255, .9)'; ctx.lineWidth = 2 * k;
    ctx.beginPath(); ctx.arc(W / 2, H / 2, W / 2 - 2 * k, 0, Math.PI * 2); ctx.stroke();
    ctx.restore();
  }
}
function drawCrop() {
  const c = document.getElementById('crop-canvas');
  if (!c || !crop.bmp) return;
  const dpr = window.devicePixelRatio || 1, pw = Math.round(crop.vw * dpr), ph = Math.round(crop.vh * dpr);
  if (c.width !== pw || c.height !== ph) { c.width = pw; c.height = ph; }   // a new canvas is 300 x 150: set both
  clampCrop();
  paintCrop(c.getContext('2d'), pw, ph, true);
}
function openCropper(bmp, mode = 'avatar') {
  Object.assign(crop, { bmp, mode, rot: 0, zoom: 1, x: 0, y: 0 });
  const z = document.getElementById('crop-zoom'); if (z) z.value = 1;
  const modal = document.getElementById('crop-modal');
  modal.classList.toggle('crop-banner', mode === 'banner');
  document.getElementById('crop-title').textContent = mode === 'banner' ? 'Adjust your banner' : 'Adjust your photo';
  const use = document.querySelector('#crop-save'); if (use) use.lastChild.textContent = mode === 'banner' ? 'Use banner' : 'Use photo';
  openModal(modal);
  const c = document.getElementById('crop-canvas');
  crop.vw = c.clientWidth || 300;
  crop.vh = mode === 'banner' ? crop.vw / BANNER_RATIO : crop.vw;
  drawCrop();
}
function setCropZoom(z, cx, cy) {   // zoom around a point (the cursor), so it doesn't jump
  const before = cropScale();
  crop.zoom = Math.min(4, Math.max(1, z));
  const ratio = cropScale() / before;
  if (cx !== undefined) { crop.x = cx - (cx - crop.x) * ratio; crop.y = cy - (cy - crop.y) * ratio; }
  else { crop.x *= ratio; crop.y *= ratio; }
  const zi = document.getElementById('crop-zoom'); if (zi) zi.value = crop.zoom;
  drawCrop();
}
function closeCropper() {
  closeModal(document.getElementById('crop-modal'));
  if (crop.bmp && crop.bmp.close) crop.bmp.close();
  crop.bmp = null;
}
async function saveCrop() {
  if (!crop.bmp) return;
  const banner = crop.mode === 'banner';
  const out = document.createElement('canvas');
  out.width = banner ? 1200 : 512; out.height = banner ? 1200 / BANNER_RATIO : 512;   // 512: sharp on big, high-density screens too
  paintCrop(out.getContext('2d'), out.width, out.height, false);
  const blob = await new Promise(res => out.toBlob(res, 'image/webp', banner ? 0.85 : 0.88));
  closeCropper();
  if (!blob) { showToast('error', 'Not saved', 'Try another picture.'); return; }
  if (banner) saveBannerBlob(blob); else savePhotoBlob(blob);
}
document.addEventListener('DOMContentLoaded', () => {
  const c = document.getElementById('crop-canvas');
  if (!c) return;
  const local = (e) => { const r = c.getBoundingClientRect(); return [e.clientX - r.left - r.width / 2, e.clientY - r.top - r.height / 2]; };
  const pointers = new Map();
  c.addEventListener('pointerdown', (e) => {
    c.setPointerCapture(e.pointerId);
    pointers.set(e.pointerId, [e.clientX, e.clientY]);
    crop.drag = { x: e.clientX, y: e.clientY, ox: crop.x, oy: crop.y };
    if (pointers.size === 2) {   // two fingers: pinch to zoom
      const [a, b] = [...pointers.values()];
      crop.pinch = { d: Math.hypot(a[0] - b[0], a[1] - b[1]), z: crop.zoom };
    }
  });
  c.addEventListener('pointermove', (e) => {
    if (!pointers.has(e.pointerId)) return;
    pointers.set(e.pointerId, [e.clientX, e.clientY]);
    if (crop.pinch && pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      setCropZoom(crop.pinch.z * Math.hypot(a[0] - b[0], a[1] - b[1]) / crop.pinch.d);
      return;
    }
    if (!crop.drag) return;
    crop.x = crop.drag.ox + (e.clientX - crop.drag.x);
    crop.y = crop.drag.oy + (e.clientY - crop.drag.y);
    drawCrop();
  });
  const up = (e) => { pointers.delete(e.pointerId); if (pointers.size < 2) crop.pinch = null; if (!pointers.size) crop.drag = null; };
  c.addEventListener('pointerup', up);
  c.addEventListener('pointercancel', up);
  c.addEventListener('wheel', (e) => { e.preventDefault(); const [x, y] = local(e); setCropZoom(crop.zoom * (e.deltaY < 0 ? 1.08 : 1 / 1.08), x, y); }, { passive: false });
  c.addEventListener('keydown', (e) => {   // arrows move, + / - zoom
    const step = e.shiftKey ? 20 : 6, moves = { ArrowLeft: [step, 0], ArrowRight: [-step, 0], ArrowUp: [0, step], ArrowDown: [0, -step] };
    if (moves[e.key]) { e.preventDefault(); crop.x += moves[e.key][0]; crop.y += moves[e.key][1]; drawCrop(); }
    if (e.key === '+' || e.key === '=') setCropZoom(crop.zoom * 1.1);
    if (e.key === '-') setCropZoom(crop.zoom / 1.1);
  });
  c.tabIndex = 0;
  document.getElementById('crop-zoom')?.addEventListener('input', (e) => setCropZoom(Number(e.target.value)));
  document.getElementById('crop-rotate')?.addEventListener('click', () => { crop.rot = (crop.rot + 90) % 360; crop.x = crop.y = 0; drawCrop(); });
  document.getElementById('crop-reset')?.addEventListener('click', () => { Object.assign(crop, { rot: 0, zoom: 1, x: 0, y: 0 }); document.getElementById('crop-zoom').value = 1; drawCrop(); });
  document.getElementById('crop-cancel')?.addEventListener('click', closeCropper);
  document.getElementById('crop-cancel-x')?.addEventListener('click', closeCropper);
  document.getElementById('crop-save')?.addEventListener('click', saveCrop);
  closeOnBackdrop(document.getElementById('crop-modal'), closeCropper);
});

document.addEventListener('DOMContentLoaded', () => {
  const m = document.getElementById('me-modal');
  document.getElementById('me-close')?.addEventListener('click', () => closeModal(m));
  closeOnBackdrop(m, () => closeModal(m));
  document.getElementById('me-avatar-btn')?.addEventListener('click', () => {
    const pk = document.getElementById('me-picker');
    pk?.classList.toggle('hidden');
    if (pk && !pk.classList.contains('hidden')) renderCharacters();
    if (pk && !pk.classList.contains('hidden')) pk.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  });
  document.getElementById('me-photo-input')?.addEventListener('change', (e) => { uploadPhoto(e.target.files[0]); e.target.value = ''; });
  document.getElementById('me-use-google')?.addEventListener('click', useGooglePhoto);
  document.getElementById('me-use-initials')?.addEventListener('click', useInitials);
  document.getElementById('me-username-input')?.addEventListener('input', checkUsername);
  document.getElementById('me-save-identity')?.addEventListener('click', saveNameAndUsername);
});
document.addEventListener('click', (e) => {
  const pre = e.target.closest('[data-preset]');
  if (pre) { choosePreset(pre.dataset.preset); return; }
  const st = e.target.closest('[data-char-style]');
  if (st) { charStyle = st.dataset.charStyle; charSeeds = []; renderCharacters(); return; }
  const ch = e.target.closest('[data-char]');
  if (ch) { chooseCharacter(ch.dataset.char, ch); return; }
  if (e.target.closest('#me-shuffle')) { charSeeds = []; renderCharacters(); return; }
  if (e.target.closest('[data-me-picker-close]')) { document.getElementById('me-picker')?.classList.add('hidden'); return; }
  const ed = e.target.closest('[data-me-edit]');
  if (ed) { closeModal(document.getElementById('me-modal')); openProfileModal(false, Number(ed.dataset.meEdit)); }
});


// ---- character avatars (1 Nov): drawn people, made in the browser with DiceBear (static/avatars.js,
// loaded only when the picker opens). The chosen one is saved as a 512 px picture, like a photo, so
// the rest of the page never needs the drawing code.
const CHAR_STYLES = [['adventurer', 'Adventurer'], ['avataaars', 'Avataaars'], ['lorelei', 'Lorelei'], ['notionists', 'Notionists'], ['open-peeps', 'Open Peeps']];
const CHAR_BG = ['ffd5dc', 'ffdfbf', 'fef3c7', 'd1fae5', 'c0aede', 'b6e3f4', 'dbeafe', 'fde68a', 'fbcfe8', 'ccfbf1', 'e9d5ff', 'fecaca'];
let charStyle = 'adventurer', charSeeds = [], avatarLib = null;
function loadAvatarLib() {
  if (window.InRealAvatars) return Promise.resolve(window.InRealAvatars);
  if (!avatarLib) avatarLib = new Promise((resolve, reject) => {
    const sc = document.createElement('script');
    sc.src = '/static/avatars.js';
    sc.onload = () => resolve(window.InRealAvatars);
    sc.onerror = () => { avatarLib = null; reject(new Error('avatars.js did not load')); };
    document.head.appendChild(sc);
  });
  return avatarLib;
}
const svgUri = (svg) => `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
async function renderCharacters() {
  const tabs = document.getElementById('me-styles'), grid = document.getElementById('me-chars');
  if (!tabs || !grid) return;
  tabs.innerHTML = CHAR_STYLES.map(([k, label]) =>
    `<button type="button" role="tab" class="me-style${k === charStyle ? ' on' : ''}" aria-selected="${k === charStyle}" data-char-style="${k}">${label}</button>`).join('');
  if (!charSeeds.length) charSeeds = Array.from({ length: 12 }, () => Math.random().toString(36).slice(2, 10));
  grid.innerHTML = charSeeds.map(() => '<span class="me-char me-char-wait"></span>').join('');
  let lib;
  try { lib = await loadAvatarLib(); } catch (e) {
    grid.innerHTML = '<p class="me-note">The characters could not load. Check the connection and open this again.</p>'; return;
  }
  grid.innerHTML = charSeeds.map((seed, i) => {
    const bg = CHAR_BG[i % CHAR_BG.length];
    return `<button type="button" class="me-char" data-char="${charStyle}|${seed}|${bg}" aria-label="Character ${i + 1}" style="animation-delay:${i * 30}ms">
      <img src="${svgUri(lib.svg(charStyle, seed, bg))}" alt=""></button>`;
  }).join('');
}
async function chooseCharacter(value, btn) {
  if (!sb || !sbUserId) { showToast('info', 'Sign in first', 'Your picture is saved to your account.'); return; }
  const [style, seed, bg] = value.split('|');
  document.querySelectorAll('.me-char.on').forEach(b => b.classList.remove('on'));
  btn?.classList.add('on');
  try {
    const lib = await loadAvatarLib();
    const img = new Image();
    await new Promise((res, rej) => { img.onload = res; img.onerror = rej; img.src = svgUri(lib.svg(style, seed, bg)); });
    const out = document.createElement('canvas');
    out.width = out.height = 512;
    out.getContext('2d').drawImage(img, 0, 0, 512, 512);
    const blob = await new Promise(res => out.toBlob(res, 'image/webp', 0.92));
    if (!blob) throw new Error('could not draw the character');
    await savePhotoBlob(blob, 'character');
  } catch (e) {
    console.error('Character avatar failed:', e);
    showToast('error', 'Avatar not saved', 'Try again in a moment.');
  }
}


// ---- banner (1 Nov): a picture of your own (1200 x 300, same editor as the photo) or a drawn one ----
const BANNERS = [
  ['sunset', 'linear-gradient(120deg, #F97316, #F59E0B 45%, #FB7185)'],
  ['ocean', 'linear-gradient(120deg, #0EA5E9, #6366F1)'],
  ['forest', 'linear-gradient(120deg, #34D399, #065F46)'],
  ['grape', 'linear-gradient(120deg, #8B5CF6, #EC4899)'],
  ['lava', 'linear-gradient(120deg, #7F1D1D, #DC2626 50%, #F97316)'],
  ['peach', 'linear-gradient(120deg, #FED7AA, #FDA4AF 60%, #F9A8D4)'],
  ['mint', 'linear-gradient(120deg, #99F6E4, #A7F3D0 50%, #D9F99D)'],
  ['night', 'radial-gradient(circle at 80% 20%, rgba(99,102,241,.55), transparent 45%), radial-gradient(circle at 15% 90%, rgba(236,72,153,.45), transparent 40%), linear-gradient(120deg, #0F172A, #1E293B)'],
  ['aurora', 'radial-gradient(circle at 20% 30%, rgba(52,211,153,.8), transparent 45%), radial-gradient(circle at 75% 70%, rgba(99,102,241,.8), transparent 45%), linear-gradient(120deg, #0B1120, #134E4A)'],
  ['dots', 'radial-gradient(circle, rgba(255,255,255,.35) 1.5px, transparent 1.8px) 0 0 / 16px 16px, linear-gradient(120deg, #F97316, #EA580C)'],
  ['stripes', 'repeating-linear-gradient(135deg, rgba(255,255,255,.14) 0 12px, transparent 12px 24px), linear-gradient(120deg, #2563EB, #7C3AED)'],
  ['paper', 'radial-gradient(circle at 10% 20%, #FDE68A, transparent 40%), radial-gradient(circle at 90% 80%, #FBCFE8, transparent 45%), #FFF7ED'],
];
const bannerCss = (key) => (BANNERS.find(b => b[0] === String(key || '').replace(/^b:/, '')) || BANNERS[0])[1];
function applyBanner() {
  const cover = document.getElementById('me-cover');
  if (!cover) return;
  if (/^https:\/\//i.test(identity.banner)) {
    cover.style.background = `center / cover no-repeat url(${JSON.stringify(identity.banner)})`;
    cover.classList.add('has-photo');
  } else {
    cover.style.background = bannerCss(identity.bannerPreset);
    cover.classList.remove('has-photo');
  }
}
function renderBanners() {
  const box = document.getElementById('me-banners');
  if (!box) return;
  const current = identity.banner ? '' : (identity.bannerPreset || 'b:sunset');
  box.innerHTML = BANNERS.map(([k, css], i) => `<button type="button" class="me-banner${current === 'b:' + k ? ' on' : ''}" data-banner="${k}"
      aria-label="Banner ${k}" aria-pressed="${current === 'b:' + k}" style="background:${css};animation-delay:${i * 25}ms"></button>`).join('');
}
async function chooseBanner(key) {
  const before = { banner: identity.banner, bannerPreset: identity.bannerPreset };
  const old = identity.banner;
  identity.banner = ''; identity.bannerPreset = `b:${key}`;
  applyBanner(); renderBanners();
  if (!(await saveIdentity({ banner_preset: identity.bannerPreset, banner_url: null }))) { Object.assign(identity, before); applyBanner(); renderBanners(); return; }
  removeOwnUpload(old);
}
function removeOwnUpload(url) {   // a picture we uploaded before and no longer use
  const mine = `/avatars/${sbUserId}/`;
  if (sb && url && url.includes(mine)) sb.storage.from('avatars').remove([url.slice(url.indexOf(mine) + '/avatars/'.length)]);
}
async function uploadBanner(file) {
  if (!file) return;
  if (!sb || !sbUserId) { showToast('info', 'Sign in first', 'Your banner is saved to your account.'); return; }
  if (!/^image\/(png|jpe?g|webp)$/.test(file.type) || file.size > 15 * 1024 * 1024) {
    showToast('error', 'Pick another picture', 'Use a JPG, PNG or WebP picture under 15 MB.'); return;
  }
  let bmp;
  try { bmp = await createImageBitmap(file); } catch (e) { showToast('error', 'Pick another picture', 'This picture could not be opened.'); return; }
  openCropper(bmp, 'banner');
}
async function saveBannerBlob(blob) {
  try {
    const path = `${sbUserId}/banner-${Date.now()}.webp`;
    const up = await sb.storage.from('avatars').upload(path, blob, { contentType: 'image/webp', upsert: false });
    if (up.error) throw up.error;
    const url = sb.storage.from('avatars').getPublicUrl(path).data.publicUrl;
    const old = identity.banner;
    if (!(await saveIdentity({ banner_url: url, banner_preset: null }))) return;
    identity.banner = url; identity.bannerPreset = '';
    applyBanner(); renderBanners();
    removeOwnUpload(old);
    showToast('success', 'Banner updated', 'Your new banner is saved to your account.');
  } catch (e) {
    console.error('Banner upload failed:', e);
    showToast('error', 'Banner not uploaded', 'The upload did not go through. Try again in a moment, or pick another picture.');
  }
}
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('me-banner-btn')?.addEventListener('click', () => {
    const pk = document.getElementById('me-banner-picker');
    pk?.classList.toggle('hidden');
    if (pk && !pk.classList.contains('hidden')) { renderBanners(); pk.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
  });
  document.getElementById('me-banner-input')?.addEventListener('change', (e) => { uploadBanner(e.target.files[0]); e.target.value = ''; });
  document.getElementById('me-banner-default')?.addEventListener('click', () => chooseBanner('sunset'));
});
document.addEventListener('click', (e) => {
  const b = e.target.closest('[data-banner]');
  if (b) { chooseBanner(b.dataset.banner); return; }
  if (e.target.closest('[data-me-banner-close]')) document.getElementById('me-banner-picker')?.classList.add('hidden');
});

// the question needs an answer: Esc and Tab stay inside it (1 Nov)
document.addEventListener('keydown', (e) => {
  const box = document.getElementById('apply-ask');
  if (!box || box.classList.contains('hidden')) return;
  if (e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); return; }
  if (e.key === 'Tab') {
    const btns = [document.getElementById('apply-ask-no'), document.getElementById('apply-ask-yes')];
    const at = btns.indexOf(document.activeElement);
    e.preventDefault();
    btns[(at + (e.shiftKey ? -1 : 1) + btns.length) % btns.length].focus();
  }
}, true);


// ==========================================
// 22. Report this post (2 Nov): hides it for you at once; the laptop moves a verified post to
//     "needs a look" when 2+ different people report it (output_handler.apply_reports).
// ==========================================
const reported = new Set();
let reportItem = null;
async function loadReports() {
  if (!sb || !sbUserId) return;
  const { data, error } = await sb.from('reports').select('listing_id');
  if (!error && Array.isArray(data)) { data.forEach(r => reported.add(r.listing_id)); if (data.length) applyFiltersAndRender(); }
}
function openReport() {
  if (!activeDrawerJob) return;
  reportItem = activeDrawerJob;
  const form = document.getElementById('report-form');
  form?.reset();
  const sub = document.getElementById('report-sub');
  if (sub) sub.textContent = `${reportItem.role_title || 'Internship'}${reportItem.company_name ? ' at ' + reportItem.company_name : ''}`;
  openModal(document.getElementById('report-modal'));
}
async function sendReport(e) {
  e.preventDefault();
  const item = reportItem;
  const reason = document.querySelector('input[name="report-reason"]:checked')?.value;
  if (!item || !reason || !sb) return;
  const note = (document.getElementById('report-note')?.value || '').trim().slice(0, 500);
  const { error } = await sb.from('reports').insert({ listing_id: String(item.id).slice(0, 200), reason, note: note || null });
  if (error && error.code !== '23505') {   // 23505: reported before, which is fine
    showToast('error', 'Not sent', error.code === '23503'
      ? "This post isn't on the shared list yet, so it can't be reported. Try again in a few minutes."
      : (/row-level security/i.test(error.message || '') ? 'You can report up to 20 posts a day.' : 'Check the connection and try again.'));
    return;
  }
  closeModal(document.getElementById('report-modal'));
  reported.add(item.id);
  closeDetailDrawer();
  applyFiltersAndRender();
  showToast('success', 'Thanks, reported', "It's hidden from your list. If others report it too, a person checks it.");
}
document.addEventListener('DOMContentLoaded', () => {
  const m = document.getElementById('report-modal');
  if (!m) return;
  document.getElementById('drawer-report-btn')?.addEventListener('click', openReport);
  document.getElementById('report-form')?.addEventListener('submit', sendReport);
  ['report-close', 'report-cancel'].forEach(id => document.getElementById(id)?.addEventListener('click', () => closeModal(m)));
  closeOnBackdrop(m, () => closeModal(m));
});
