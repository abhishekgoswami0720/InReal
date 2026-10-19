/**
 * InReal Dashboard
 * Corporate Polished UI with Genuine Company Logos, Consistent Actions, and Robust Filtering
 */

let allInternships = [];
let activeLocation = 'all';
let activeStipend = 'all';
let activeSource = 'all';
let activeRoleType = 'all';
let activeModeration = 'verified';   // n8n scam check: show only listings it passed
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
let canEdit = true;
// The search on screen: Search Internships starts a new one and the list shows only its results
const VIEW_KEY = 'inreal_view_run';
let viewRun = (() => { try { return localStorage.getItem(VIEW_KEY) || ''; } catch (e) { return ''; } })();
let showAllSaved = false;
// Each visit starts with an empty list: the shared list on the laptop is no longer wiped on refresh
// (that lost verdicts still on their way from n8n, and other people's results), so the page itself
// shows nothing until a search starts. "Show recent results" shows everything checked lately.
let freshVisit = true;
// The search on screen, exactly as it was asked for: "Search more" repeats it on the same sites only
let lastSearch = null;
function startNewView(tag) {
  if (!tag) return;
  viewRun = tag; showAllSaved = false; freshVisit = false;
  try { localStorage.setItem(VIEW_KEY, tag); } catch (e) { /* private window */ }
  displayOrder.clear(); verifiedSeen = null;
  applyFiltersAndRender(); updateViewNote();
}
const displayOrder = new Map();   // id -> position the card was first shown at
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
function failsPreferences(item, p) {
  const min = Number(p.min_stipend || 0);
  if (min > 0) {
    if (isUnpaid(item)) return true;
    const num = Number(item.stipend_numeric || 0);
    const inr = !item.stipend_currency || /inr|₹|rs/i.test(String(item.stipend_currency));
    if (num > 0 && inr && num < min) return true;
  }
  if (p.work_mode === 'remote' && !isRemotePost(item)) return true;
  if (p.work_mode === 'office' && isRemotePost(item)) return true;
  if (p.max_duration && p.max_duration !== 'any') {
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
  try { localStorage.removeItem('inreal_view_run'); } catch (e) {}
  viewRun = '';
  startSession();
  pollScraperStatus();
  pollAlerts();
  pollModeration();
  updateBookmarkCounter();
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
    announceNewlyVerified(allInternships);

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
  sourceSelect.value = activeSource;   // the list reloads as n8n verdicts arrive; keep the user's choice
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

  const matches = (item, ignoreLocation) => {
    // only this visit's search (saved posts are always reachable through "Saved")
    if (!showAllSaved && !showBookmarkedOnly) {
      if (freshVisit) return false;
      if (viewRun && item.last_run !== viewRun) return false;
    }
    if (showBookmarkedOnly && !bookmarks.includes(item.id)) return false;

    // The student's profile: only their field, and unpaid posts only for 0 years of experience
    if (profile) {
      if (profile.experience !== '0' && isUnpaid(item)) return false;
      if (failsPreferences(item, profile)) return false;
    }

    // Scam check verdict (n8n). Default: only what n8n checked and passed.
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
  renderOverviewStats(filtered, base);
  updateFilterCount();
  renderListings(filtered);
}

function skillChip(item) {
  const hits = matchedSkills(item, profile);
  if (!hits.length) return '';
  const all = (profile.skills || []).length;
  return `<span class="px-1.5 py-0.2 bg-orange-50 text-orange-700 font-bold border border-orange-200 rounded text-[10px] ml-1 flex items-center gap-0.5" title="Your skills in this post: ${escapeHtml(hits.join(', '))}"><i class="ph ph-lightning"></i> ${hits.length}/${all} SKILLS</span>`;
}

function renderListings(items) {
  const container = document.getElementById('listings-container');
  const emptyState = document.getElementById('empty-state');
  if (!container) return;

  if (items.length === 0) {
    container.innerHTML = '';
    const h = document.querySelector('#empty-state h3'), t = document.querySelector('#empty-state p');
    if (freshVisit && !showAllSaved && !showBookmarkedOnly) {
      if (h) h.textContent = 'Start a search';
      if (t) t.textContent = 'Click "Search Internships" to search the sites for your field. Results appear as each site finishes. To see what was already checked in the last few days, click "Show recent results" above the list.';
      if (emptyState) { emptyState.classList.remove('hidden'); emptyState.classList.add('flex'); }
      return;
    }
    const fieldEmpty = profile && !allInternships.some(r => String(r.field || 'ai_ml').split(';').includes(profile.field));
    if (false) {
      const inView = allInternships.filter(r => r.last_run === viewRun);
      if (h) h.textContent = inView.length ? 'Nothing verified from this search yet' : 'New search started';
      if (t) t.textContent = inView.length
        ? `${inView.filter(r => r.moderation_status === 'held').length} found and waiting. Click "Load 5 more" below to scam-check the next 5.`
        : 'Internships appear here as each site finishes. Then click "Load 5 more" to scam-check them.';
      return;
    }
    // Say so when posts were checked but the Scam check filter (Verified only) is hiding them
    const inScope = (viewRun && !showAllSaved) ? allInternships.filter(r => r.last_run === viewRun) : allInternships;
    const inReview = inScope.filter(r => r.moderation_status === 'review').length;
    if (activeModeration === 'verified' && inReview && !fieldEmpty) {
      const waiting = inScope.filter(r => r.moderation_status === 'held').length;
      if (h) h.textContent = 'None verified yet: the checked posts need a second look';
      if (t) t.textContent = `${inReview} post${inReview === 1 ? ' was' : 's were'} checked and put in Review, so the Verified-only filter hides ${inReview === 1 ? 'it' : 'them'}. `
        + `To see ${inReview === 1 ? 'it' : 'them'}, open Filters and set Scam check to "Verified + needs a look". The reason is in each post's View Details.`
        + (waiting ? ` ${waiting} more are waiting for "Load 5 more".` : '');
      if (emptyState) { emptyState.classList.remove('hidden'); emptyState.classList.add('flex'); }
      return;
    }
    if (h) h.textContent = fieldEmpty ? `No ${fieldLabels[profile.field] || profile.field} internships yet` : 'No Matching Opportunities Found';
    if (t) t.textContent = fieldEmpty ? 'Search the sites for your field with "Search Internships". New ones appear as each site finishes.'
                                      : 'Try broadening your search keywords or resetting region and stipend filters.';
    if (emptyState) {
      emptyState.classList.remove('hidden');
      emptyState.classList.add('flex');
    }
    return;
  }

  if (emptyState) {
    emptyState.classList.add('hidden');
    emptyState.classList.remove('flex');
  }

  container.innerHTML = items.map((item) => {
    const isBookmarked = bookmarks.includes(item.id);
    const skills = (item.required_skills || '').split(',').map(s => s.trim()).filter(Boolean).slice(0, 3);
    const logoSvg = getCompanyLogoSvg(item.company_name);

    return `
      <article 
        class="glass-card p-5 sm:p-6 flex flex-col justify-between cursor-pointer group"
        onclick="openDetailDrawer('${escapeHtml(item.id)}')"
      >
        <div>
          <!-- Top Row: Real Company Logo + Subtle Source Tag with colored dot + Bookmark -->
          <div class="flex items-start justify-between gap-3 mb-3.5">
            <div class="flex items-center gap-3 min-w-0 flex-1">
              <!-- Genuine Square-Rounded Company Logo -->
              <div class="company-logo-box shrink-0" title="${escapeHtml(item.company_name || 'Organization')}">
                ${logoSvg}
              </div>

              <div class="min-w-0">
                <!-- Subtle Source Badge with colored dot (wraps instead of running under the bookmark) -->
                <div class="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[11px] font-semibold text-slate-500">
                  <span class="w-1.5 h-1.5 rounded-full ${dotColor(item)}"></span>
                  <span>${escapeHtml(item.source_platform || 'Direct Portal')}</span>
                  ${isNewToday(item) ? '<span class="px-1.5 py-0.2 bg-emerald-50 text-emerald-700 font-bold border border-emerald-200 rounded text-[10px] ml-1">NEW</span>' : ''}
                  ${moderationChip(item)}
                  ${isPreferred(item) ? '<span class="px-1.5 py-0.2 bg-violet-50 text-violet-700 font-bold border border-violet-200 rounded text-[10px] ml-1 flex items-center gap-0.5"><i class="ph ph-star"></i> YOUR PICK</span>' : ''}
                  ${skillChip(item)}
                  ${item.trust_flags ? `<span class="px-1.5 py-0.2 bg-amber-50 text-amber-700 font-bold border border-amber-200 rounded text-[10px] ml-1 flex items-center gap-0.5" title="${escapeHtml(item.trust_flags)}"><i class="ph ph-warning"></i> NOTE</span>` : ''}
                </div>
                <div class="text-xs font-bold text-slate-800 mt-0.5">${escapeHtml(item.company_name || 'Company')}</div>
              </div>
            </div>

            <button 
              type="button" 
              class="w-8 h-8 shrink-0 rounded-lg bg-slate-50 hover:bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-400 hover:text-rose-500 transition"
              onclick="event.stopPropagation(); toggleBookmark('${escapeHtml(item.id)}')"
              title="Bookmark opportunity"
            >
              <i class="ph ${isBookmarked ? 'ph-fill ph-bookmark text-rose-500' : 'ph-bookmark'} text-base"></i>
            </button>
          </div>

          <!-- Role Title -->
          <h3 class="text-base font-bold text-slate-900 leading-snug line-clamp-2 group-hover:text-orange-600 transition-colors mt-2">
            ${escapeHtml(item.role_title || 'Internship Opportunity')}
          </h3>
          
          <!-- Location and Duration -->
          <div class="text-xs text-slate-500 mt-1.5 flex items-center gap-2 font-medium">
            <span class="flex items-center gap-1"><i class="ph ph-map-pin text-slate-400"></i> ${escapeHtml(item.location || 'Location not stated')}</span>
            <span>&bull;</span>
            <span>${escapeHtml(item.duration || 'Duration not stated')}</span>
          </div>

          <!-- Uniform Neutral Tech Stack Pills -->
          <div class="flex flex-wrap gap-1.5 mt-4">
            ${skills.map(skill => `<span class="px-2.5 py-0.5 bg-slate-100 text-slate-700 rounded-md text-[11px] font-semibold border border-slate-200/60">${escapeHtml(skill)}</span>`).join('')}
          </div>
        </div>

        <!-- Footer: Clean Stipend Readout & Consistent Dark CTA -->
        <div class="pt-4 mt-5 border-t border-slate-100 flex items-center justify-between text-xs">
          <div>
            <div class="text-[10px] text-slate-400 uppercase font-bold tracking-wider">Stipend</div>
            <div class="font-extrabold text-slate-900 text-sm mt-0.5">${escapeHtml(item.stipend || 'Not stated')}</div>
          </div>
          <div>
            <!-- Consistent Sleek Dark Slate Button Across All Cards -->
            <span class="px-3 py-1.5 bg-slate-900 text-white font-semibold rounded-lg group-hover:bg-orange-600 transition flex items-center gap-1 text-xs">
              <span>View Details</span>
              <i class="ph ph-arrow-right text-xs"></i>
            </span>
          </div>
        </div>
      </article>
    `;
  }).join('');
}

// ==========================================
// 4. Slide-Over Detail Drawer
// ==========================================
function openDetailDrawer(id) {
  const item = allInternships.find(i => i.id === id);
  if (!item) return;

  activeDrawerJob = item;
  document.getElementById('drawer-role-title').innerText = item.role_title || 'Opportunity';
  document.getElementById('drawer-company-name').innerText = item.company_name || '';
  document.getElementById('drawer-location').innerText = item.location || 'Location not stated';
  document.getElementById('drawer-duration').innerText = item.duration || 'Duration not stated';
  document.getElementById('drawer-stipend').innerText = item.stipend || 'Not stated';
  document.getElementById('drawer-deadline').innerText = item.application_deadline || 'Not stated';
  document.getElementById('drawer-source').innerText = item.source_platform || '';
  document.getElementById('drawer-date').innerText = item.date_scraped || '';
  document.getElementById('drawer-org-badge').innerText = item.org_type || 'Company';

  const applyLink = document.getElementById('drawer-apply-link');
  applyLink.href = safeUrl(item.apply_link);

  // n8n verdict with its reasons
  const modBox = document.getElementById('drawer-mod-box');
  const view = MOD_VIEWS[item.moderation_status || ''] || MOD_VIEWS[''];
  modBox.className = `p-3 rounded-lg border text-xs ${view.box}`;
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
  btn.innerHTML = `<i class="ph ${isBookmarked ? 'ph-fill ph-bookmark text-rose-500' : 'ph-bookmark text-slate-600'} text-base"></i>`;
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

  // Saved Bookmarks Button
  document.getElementById('filter-bookmarks-btn')?.addEventListener('click', () => {
    showBookmarkedOnly = !showBookmarkedOnly;
    const btn = document.getElementById('filter-bookmarks-btn');
    if (showBookmarkedOnly) {
      btn.classList.add('bg-rose-50', 'text-rose-600', 'border-rose-200');
    } else {
      btn.classList.remove('bg-rose-50', 'text-rose-600', 'border-rose-200');
    }
    applyFiltersAndRender();
  });

  // Reset Filters Function
  const resetAll = () => {
    const searchInput = document.getElementById('search-input');
    if (searchInput) searchInput.value = '';
    activeLocation = 'all';
    activeStipend = 'all';
    activeSource = 'all';
    activeRoleType = 'all';
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
    
    const bookmarkBtn = document.getElementById('filter-bookmarks-btn');
    if (bookmarkBtn) bookmarkBtn.classList.remove('bg-rose-50', 'text-rose-600', 'border-rose-200');

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
    document.getElementById('filter-menu')?.classList.add('hidden');
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
    modal.classList.remove('hidden');
  });
  document.getElementById('close-config-btn')?.addEventListener('click', () => {
    modal.classList.add('hidden');
  });
  closeOnBackdrop(modal, () => modal.classList.add('hidden'));
  closeOnBackdrop(document.getElementById('profile-modal'), closeProfileModal);   // not on the first visit

  document.getElementById('scrape-config-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    modal.classList.add('hidden');

    const checkedValues = (name) => Array.from(document.querySelectorAll(`input[name="${name}"]:checked`)).map(cb => cb.value);
    const config = {
      regions: checkedValues('regions'),
      sources: checkedValues('sources'),
      field: document.getElementById('scrape-field')?.value || (profile && profile.field) || 'ai_ml',
      limit: FIRST_BATCH
    };
    if (!config.sources.length) { showToast('error', 'Pick at least one site', 'Choose the sites to search, then start again.'); modal.classList.remove('hidden'); return; }

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
      closeDetailDrawer();
      modal?.classList.add('hidden');
      closeProfileModal();
    }
  });
}

// The post text keeps one line per paragraph, heading or "• " point (sites/_common.html_to_text).
// Short title-like lines followed by a paragraph or a list become headings; "Label: value" lines get
// a bold label; "• " lines become a list. Posts saved as one long line still show as one paragraph.
function describeHtml(desc) {
  const BULLET = /^[•·▪●◦\-*]\s+/;
  const lines = String(desc || '').split(/\n+/).map(l => l.trim()).filter(Boolean);
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
// 8. n8n scam check (moderation) — verdict chips and live queue
// ==========================================
const MOD_VIEWS = {
  '':        { label: 'Scam check pending', chip: 'bg-slate-50 text-slate-500 border-slate-200', dot: 'bg-slate-400', box: 'bg-slate-50 border-slate-200 text-slate-600', icon: 'ph-hourglass' },
  held:      { label: 'Scraped, waiting for Load more', chip: 'bg-slate-50 text-slate-500 border-slate-200', dot: 'bg-slate-300', box: 'bg-slate-50 border-slate-200 text-slate-600', icon: 'ph-tray' },
  checking:  { label: 'Being checked by n8n', chip: 'bg-slate-50 text-slate-500 border-slate-200', dot: 'bg-slate-400', box: 'bg-slate-50 border-slate-200 text-slate-600', icon: 'ph-hourglass' },
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

// Reload the cards whenever n8n has judged more listings (it runs while scraping continues)
let lastJudged = -1;
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
  } catch (e) { /* app restarting */ }
  setTimeout(pollModeration, 5000);
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

  document.getElementById('edit-profile-btn')?.addEventListener('click', () => openProfileModal(false));
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
  if (!requiredDone(profile)) openProfileModal(true);   // right away, before anything else on the page
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
  document.getElementById('profile-skill-input').addEventListener('keydown', e => {
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
    btn.toggleAttribute('disabled', k > reachableUpTo(draft) || (profileMandatory && k > 2));
    btn.classList.toggle('done', sectionDone(draft, k));
    if (k === profileStep) btn.setAttribute('aria-current', 'step'); else btn.removeAttribute('aria-current');
    btn.querySelector('.pstep-dot').textContent = sectionDone(draft, k) ? '✓' : String(k);
  });
  document.getElementById('profile-back').classList.toggle('invisible', profileStep === 1);
  document.getElementById('profile-skip').classList.toggle('hidden', profileMandatory);
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
  modal.classList.remove('hidden');
  (profileStep === 1 ? document.getElementById('profile-name') : null)?.focus();
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
  document.getElementById('profile-modal').classList.add('hidden');
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
  displayOrder.clear();
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
  document.getElementById('profile-modal').classList.add('hidden');
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
  btn.setAttribute('aria-label', tip);
}

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
  const avatar = document.getElementById('profile-avatar');
  const initials = (profile.name || '').split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join('');
  if (avatar && !avatar.dataset.photo) avatar.innerHTML = initials ? escapeHtml(initials) : '<i class="ph ph-user text-lg"></i>';
  if (box) {
    const exp = { '0': '0 years experience (unpaid shown)', '1-2': '1–2 years experience (paid only)', '3+': '3+ years experience (paid only)' }[profile.experience] || '';
    const picks = (profile.companies || []).length ? ` · Preferred: ${profile.companies.map(escapeHtml).join(', ')}` : '';
    const prefs = [
      Number(profile.min_stipend) > 0 ? `₹${Number(profile.min_stipend).toLocaleString('en-IN')}+ / month` : '',
      profile.work_mode === 'remote' ? 'remote only' : profile.work_mode === 'office' ? 'office / hybrid' : '',
      profile.max_duration && profile.max_duration !== 'any' ? `up to ${profile.max_duration} months` : '',
      (profile.skills || []).length ? `ranked by your ${profile.skills.length} skills` : '',
    ].filter(Boolean).map(t => ` · ${t}`).join('');
    box.innerHTML = `<i class="ph ph-user-focus text-base text-orange-500"></i>
      <span>Showing <b class="text-slate-900">${escapeHtml(field)}</b> internships · ${exp}${prefs}${picks}</span>
      <button type="button" class="ml-auto text-orange-600 hover:underline" onclick="openProfileModal(false)">Edit profile</button>`;
    box.classList.remove('hidden');
  }
}


// ==========================================
// 11. One "Filters" dropdown holding every filter
// ==========================================
function updateFilterCount() {
  const n = [activeRoleType !== 'all', activeLocation !== 'all', activeStipend !== 'all',
             activeSource !== 'all', activeModeration !== 'verified'].filter(Boolean).length;
  const badge = document.getElementById('filter-count');
  if (!badge) return;
  badge.textContent = n;
  badge.classList.toggle('hidden', n === 0);
}

function setFilterMenu(open) {
  const menu = document.getElementById('filter-menu');
  const btn = document.getElementById('filter-menu-btn');
  if (!menu || !btn) return;
  menu.classList.toggle('hidden', !open);
  btn.setAttribute('aria-expanded', String(open));
  if (open) menu.querySelector('select')?.focus();
}

document.addEventListener('DOMContentLoaded', () => {
  const wrap = document.getElementById('filter-menu-wrap');
  document.getElementById('filter-menu-btn')?.addEventListener('click', () =>
    setFilterMenu(document.getElementById('filter-menu').classList.contains('hidden')));
  document.getElementById('filter-done-btn')?.addEventListener('click', () => {
    setFilterMenu(false);
    document.getElementById('filter-menu-btn')?.focus();
  });
  document.addEventListener('click', (e) => { if (wrap && !wrap.contains(e.target)) setFilterMenu(false); });
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
  icon.innerHTML = finished ? '<i class="ph ph-check-circle text-xl"></i>' : '<i class="ph ph-radar text-xl animate-spin" style="animation-duration:2.5s"></i>';
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
    const left = lastModCounts.pending + lastModCounts.checking;
    const waiting = lastModCounts.held ? ` ${lastModCounts.held} more saved: use "Load 5 more" under the list.` : '';
    check.innerHTML = left
      ? `<span class="flex items-start gap-2 text-amber-700"><i class="ph ph-shield-checkered text-base"></i> Scam check: ${left} being checked now.${waiting}</span>`
      : (lastModCounts.held
          ? `<span class="flex items-start gap-2 text-slate-700"><i class="ph ph-tray text-base"></i> ${lastModCounts.held} internships scraped and saved. Click "Load 5 more" under the list to scam-check the next 5.</span>`
          : `<span class="flex items-start gap-2 text-emerald-700"><i class="ph ph-shield-check text-base"></i> All checked.</span>`);
    check.classList.remove('hidden');
  } else if (finished && !total) {
    check.innerHTML = '<span class="text-slate-500">No new internships this time. Try more sites or another field.</span>';
    check.classList.remove('hidden');
  } else {
    check.classList.add('hidden');
  }
}

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
  if (!btn) return;
  // only this search's posts: the automatic update's posts go through the same check in the background
  const inFlight = viewRun
    ? allInternships.filter(r => r.last_run === viewRun && ['', 'checking'].includes(r.moderation_status || '')).length
    : (c.pending || 0) + (c.checking || 0);
  if (loadMoreBusy && inFlight === 0) loadMoreBusy = false;   // the 5 have been judged
  const label = btn.querySelector('span');
  btn.disabled = loadMoreBusy || held === 0;
  btn.classList.toggle('opacity-60', btn.disabled);
  label.textContent = loadMoreBusy ? `Checking ${inFlight}…` : (held ? 'Load 5 more' : 'Nothing waiting');
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('load-more-btn')?.addEventListener('click', async () => {
    try {
      const res = await fetch('/api/moderation/load-more', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ count: 5, run_tag: viewRun }) });
      if (res.status === 403) { showToast('info', 'View-only link', 'Load more works on the host laptop.'); return; }
      const d = await res.json();
      if (!d.released) { showToast('info', 'Nothing waiting', 'Use "Search more" to scrape the sites again.'); return; }
      loadMoreBusy = true;
      updateHeldUI({ held: d.held_left, pending: d.released, checking: 0 });
      showToast('info', `${d.released} sent to the scam check`, 'Verified ones appear at the end of the list in about half a minute.');
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
function updateViewNote() {
  const el = document.getElementById('view-note');
  if (!el) return;
  if (!viewRun && !freshVisit) { el.classList.add('hidden'); return; }
  const m = viewRun.match(/^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})/);
  const when = m ? `${m[4]}:${m[5]}` : '';
  const back = freshVisit ? 'Hide them' : 'Back to my latest search';
  const now = freshVisit ? 'Nothing searched in this visit yet.' : `Showing results of your latest search${when ? ` (started ${when})` : ''}.`;
  el.innerHTML = showAllSaved
    ? `<span>Showing <b class="text-slate-900">every result checked in the last few days</b>, from all searches.</span> <button type="button" class="text-orange-600 hover:underline font-bold" id="view-toggle">${back}</button>`
    : `<span>${now}</span> <button type="button" class="text-orange-600 hover:underline font-bold" id="view-toggle">Show recent results</button>`;
  el.classList.remove('hidden');
  document.getElementById('view-toggle').onclick = () => {
    showAllSaved = !showAllSaved; displayOrder.clear();
    applyFiltersAndRender(); updateViewNote();
  };
}
document.addEventListener('DOMContentLoaded', updateViewNote);


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
  sb.from('profiles').update(row).eq('id', sbUserId).then(({ error }) => {
    if (error) showToast('error', 'Profile saved only in this browser', error.message);
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

  const meta = user.user_metadata || {};
  sbUserId = user.id;
  const { data: account } = await sb.from('profiles')
    .select('name,avatar_url,is_admin,field,experience,companies,sources,regions,study_year,roles,skills,work_mode,min_stipend,max_duration')
    .eq('id', user.id).maybeSingle();
  // The profile lives in the account: a new browser or an incognito window gets it back instead
  // of the first-visit form (19 Oct). A profile only in this browser is copied up once.
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
  } else if (profile && profile.owner === user.id) {
    saveProfileToAccount(profile);          // filled in this browser before the account had it
  } else {
    profile = null;                         // another account's, or none: this one fills the form
    try { localStorage.removeItem(PROFILE_KEY); } catch (e) { /* private window */ }
  }
  BOOKMARK_KEY = `inreal_bookmarks:${user.id}`;
  try { bookmarks = JSON.parse(localStorage.getItem(BOOKMARK_KEY) || '[]'); } catch (e) { bookmarks = []; }
  const photo = (account && account.avatar_url) || meta.avatar_url;
  const avatar = document.getElementById('profile-avatar');
  if (avatar && photo && /^https:\/\//.test(photo)) {
    avatar.innerHTML = `<img src="${escapeHtml(photo)}" alt="" referrerpolicy="no-referrer" class="w-full h-full rounded-full object-cover">`;
    avatar.dataset.photo = '1';
  }
  const admin = document.getElementById('admin-link');
  if (admin && account && account.is_admin) { admin.classList.remove('hidden'); admin.classList.add('inline-flex'); }
  // first visit: the profile form starts with the Google name
  if (!profile) {
    const name = document.getElementById('profile-name');
    if (name && !name.value) name.value = (account && account.name) || meta.full_name || '';
  }
  return true;
}

