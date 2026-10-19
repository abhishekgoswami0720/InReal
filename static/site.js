// InReal public site: landing page when signed out, the internship list when signed in.
// Everything that decides who sees what lives in the database (Supabase row-level security,
// supabase/schema.sql): this page only asks. Signed out it can call just two functions,
// teaser_listings() (6 posts, no text, no apply link) and listing_stats() (counts).
'use strict';

const CFG = window.INREAL || {};
const db = (window.supabase && CFG.supabaseUrl && CFG.supabaseKey)
  ? window.supabase.createClient(CFG.supabaseUrl, CFG.supabaseKey)
  : null;

const state = { session: null, profile: null, listings: [], saved: new Set(), open: null };
const $ = (id) => document.getElementById(id);
const FIELD_LABELS = Object.fromEntries((CFG.fields || []).map(f => [f.key, f.label]));

// ---------- small helpers ----------
function escapeHtml(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function safeUrl(u) { return /^https?:\/\//i.test(String(u || '')) ? u : '#'; }
function toast(msg) {
  const t = $('toast');
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { t.hidden = true; }, 4200);
}
function ago(iso) {
  if (!iso) return '';
  const min = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (min < 60) return `${min} min ago`;
  const h = Math.round(min / 60);
  return h < 48 ? `${h} h ago` : `${Math.round(h / 24)} days ago`;
}
function plural(n, word) { return `${n.toLocaleString('en-IN')} ${word}${n === 1 ? '' : 's'}`; }

// One line per paragraph / heading / "• " point (sites/_common.html_to_text) -> readable HTML
function describeHtml(desc) {
  const BULLET = /^[•·▪●◦\-*]\s+/;
  const lines = String(desc || '').split(/\n+/).map(l => l.trim()).filter(Boolean);
  const words = (l) => l.split(/\s+/).length;
  const titleCase = (l) => l.split(/\s+/).every(w => /^[A-Z0-9&(]/.test(w) || /^(and|or|of|the|to|for|in|on|at|a|an|we|you)$/i.test(w));
  const isHeading = (l, next) => {
    if (l.length > 60 || BULLET.test(l) || /[.,;!?]$/.test(l) || !/^[A-Z]/.test(l) || words(l) > 6) return false;
    if (/:\s/.test(l)) return false;
    if (/:$/.test(l)) return titleCase(l.replace(/:$/, ''));
    if (!next) return false;
    return BULLET.test(next) || next.length > 60 || /:$/.test(next) || (words(l) >= 2 && titleCase(l));
  };
  let html = '', list = false;
  lines.forEach((l, i) => {
    if (BULLET.test(l)) {
      if (!list) { html += '<ul class="list-disc pl-5 space-y-0.5">'; list = true; }
      html += `<li>${escapeHtml(l.replace(BULLET, ''))}</li>`;
      return;
    }
    if (list) { html += '</ul>'; list = false; }
    const label = l.match(/^([A-Z][^:]{1,35}):\s+(.{1,120})$/);
    if (isHeading(l, lines[i + 1])) html += `<h4 class="font-bold text-slate-900 ${i ? 'pt-2' : ''}">${escapeHtml(l.replace(/:$/, ''))}</h4>`;
    else if (/:$/.test(l)) html += `<p class="font-medium text-slate-800">${escapeHtml(l)}</p>`;
    else if (label && !/[.!?]\s/.test(label[1])) html += `<p><span class="font-semibold text-slate-800">${escapeHtml(label[1])}:</span> ${escapeHtml(label[2])}</p>`;
    else html += `<p>${escapeHtml(l)}</p>`;
  });
  if (list) html += '</ul>';
  return html;
}

// The scam check's reasons, in plain words (the raw ones come from n8n)
function plainReason(r) {
  let m;
  if ((m = r.match(/^LLM:\s*(\w+),\s*probability\s*([\d.]+)\s*[—-]\s*(.*)$/i))) {
    const word = { genuine: 'looks genuine', suspicious: 'is unsure', scam: 'thinks it is a scam' }[m[1].toLowerCase()] || m[1];
    return `AI reviewer ${word}: ${m[3]}`;
  }
  if ((m = r.match(/^Vector match,\s*(.*?)\s*\(similarity\s*([\d.]+)[^)]*\):\s*"?(.*?)"?$/i))) return `Wording close to a known scam (${m[1]}): "${m[3]}"`;
  if (/disagree/i.test(r)) return 'The AI reviewer and the wording check disagree, so this one needs a look.';
  if ((m = r.match(/^Scraper warnings?:\s*(.*)$/i))) return `Note: ${m[1]}`;
  if (/^Judged in an earlier/i.test(r)) return '';
  if (/[{}]|Error|stack/.test(r)) return '';
  return r;
}

// ---------- signed out ----------
function sitesText(n) { return n ? `${n}` : 'many'; }

async function showPublic() {
  $('view-public').hidden = false;
  $('view-app').hidden = true;
  $('nav-public').hidden = false;
  $('nav-app').hidden = true;
  document.querySelectorAll('[data-sites]').forEach(el => { el.textContent = sitesText(CFG.liveSites); });
  if (!db) { $('teaser-empty').hidden = false; return; }
  const [teaser, stats] = await Promise.all([db.rpc('teaser_listings'), db.rpc('listing_stats')]);
  const rows = teaser.data || [];
  $('teaser-grid').innerHTML = rows.map(teaserCard).join('');
  $('teaser-empty').hidden = rows.length > 0;
  const s = stats.data || {};
  document.querySelectorAll('[data-stat]').forEach(el => {
    const v = s[el.dataset.stat];
    el.textContent = typeof v === 'number' ? v.toLocaleString('en-IN') : '–';
  });
  const more = Math.max(0, (s.verified_total || 0) - rows.length);
  $('locked-count').textContent = more ? `${plural(more, 'more verified internship')}` : 'More verified internships';
  if (s.updated_at) { $('updated-at').textContent = `Updated ${ago(s.updated_at)}`; $('updated-at').hidden = false; }
}

function teaserCard(j) {
  return `<button type="button" data-signin class="job text-left flex flex-col gap-3 p-5 rounded-2xl bg-white border border-slate-200">
    <div class="flex items-center gap-2 flex-wrap"><span class="text-xs font-bold text-slate-600">${escapeHtml(j.source_platform)}</span>${verifiedChip()}</div>
    <div class="text-sm font-bold text-slate-700">${escapeHtml(j.company_name || '')}</div>
    <div class="text-lg font-extrabold leading-snug">${escapeHtml(j.role_title)}</div>
    <div class="text-sm text-slate-600">${escapeHtml(j.location || 'Location not stated')}</div>
    <div class="flex justify-between items-end border-t border-slate-100 pt-3 mt-auto w-full">
      <div><div class="text-[11px] font-bold tracking-wider text-slate-500">STIPEND</div><div class="font-extrabold">${escapeHtml(j.stipend || 'Not stated')}</div></div>
      <span class="text-sm font-bold text-orange-700">Sign in to view →</span>
    </div></button>`;
}
function verifiedChip() {
  return '<span class="inline-flex items-center gap-1 text-[11px] font-extrabold text-green-800 bg-green-50 border border-green-200 rounded-full px-2 py-0.5">✓ VERIFIED</span>';
}
function reviewChip() {
  return '<span class="inline-flex items-center gap-1 text-[11px] font-extrabold text-amber-800 bg-amber-50 border border-amber-200 rounded-full px-2 py-0.5">NEEDS A LOOK</span>';
}

async function signIn() {
  if (!db) { toast('Sign-in is not set up yet (Supabase keys missing).'); return; }
  const { error } = await db.auth.signInWithOAuth({ provider: 'google', options: { redirectTo: location.origin + '/' } });
  if (error) { $('signin-error').textContent = `Google sign-in did not start: ${error.message}`; $('signin-error').hidden = false; }
}

// ---------- signed in ----------
async function showApp() {
  $('view-public').hidden = true;
  $('view-app').hidden = false;
  $('nav-public').hidden = true;
  $('nav-app').hidden = false;
  const user = state.session.user;
  const { data: profile, error } = await db.from('profiles').select('*').eq('id', user.id).maybeSingle();
  if (error) { toast(`Could not load your profile: ${error.message}`); return; }
  state.profile = profile || { field: null, plan: 'free' };
  const meta = user.user_metadata || {};
  $('account-name').textContent = state.profile.name || meta.full_name || user.email;
  $('account-email').textContent = user.email || '';
  $('account-avatar').src = state.profile.avatar_url || meta.avatar_url || '/static/favicon.svg';
  const pro = state.profile.plan === 'pro' || state.profile.is_admin;
  const badge = $('plan-badge');
  badge.textContent = state.profile.is_admin ? 'Admin' : pro ? 'Pro' : 'Free plan';
  badge.className = `hidden sm:inline-flex px-2.5 py-1 rounded-full text-xs font-bold border ${pro ? 'bg-slate-900 text-white border-slate-900' : 'bg-white text-slate-700 border-slate-300'}`;
  $('free-note').hidden = pro;
  $('admin-link').hidden = !state.profile.is_admin;   // the dashboard itself opens only on the laptop
  if (!state.profile.field) { openProfile(true); return; }
  await loadListings();
}

async function loadListings() {
  const field = state.profile.field;
  $('app-title').textContent = `${FIELD_LABELS[field] || 'Verified'} internships`;
  const [lst, bm] = await Promise.all([
    db.from('listings')
      .select('id,source_platform,company_name,role_title,location,location_type,duration,stipend,stipend_numeric,apply_link,description,fields,trust_flags,status,moderation_reasons,verified_at')
      .order('verified_at', { ascending: false, nullsFirst: false }).limit(600),
    db.from('bookmarks').select('listing_id'),
  ]);
  if (lst.error) { toast(`Could not load internships: ${lst.error.message}`); return; }
  state.listings = lst.data || [];
  state.saved = new Set((bm.data || []).map(b => b.listing_id));
  render();
}

function visible() {
  const q = $('q').value.trim().toLowerCase();
  const loc = $('loc').value, paidOnly = $('paid').checked, savedOnly = $('saved-only').checked;
  const exp = state.profile.experience || '0';
  return state.listings.filter(j => {
    if (savedOnly && !state.saved.has(j.id)) return false;
    if (loc !== 'all' && j.location_type !== loc) return false;
    const unpaid = /unpaid/i.test(j.stipend || '');
    if (paidOnly && (unpaid || !(Number(j.stipend_numeric) > 0))) return false;
    if (exp !== '0' && unpaid) return false;           // unpaid only for students with no experience
    if (q && !`${j.role_title} ${j.company_name} ${j.description || ''}`.toLowerCase().includes(q)) return false;
    return true;
  });
}

function render() {
  const rows = visible();
  const n = state.listings.length;
  $('app-sub').textContent = `${plural(rows.length, 'internship')} shown of ${n.toLocaleString('en-IN')} you can see`;
  $('list').innerHTML = rows.map(card).join('');
  const empty = $('list-empty');
  empty.hidden = rows.length > 0;
  if (!rows.length) {
    empty.textContent = n
      ? 'Nothing matches these filters. Clear the search or the filters to see more.'
      : (state.profile.plan === 'pro' || state.profile.is_admin)
        ? 'No verified internships in the list yet. They appear after the next automatic update.'
        : 'No internships in your field are older than 24 hours yet. New ones show here a day after they are verified.';
  }
}

function card(j) {
  const saved = state.saved.has(j.id);
  return `<article class="job flex flex-col gap-3 p-5 rounded-2xl bg-white border border-slate-200">
    <div class="flex items-center gap-2 flex-wrap justify-between">
      <div class="flex items-center gap-2 flex-wrap"><span class="text-xs font-bold text-slate-600">${escapeHtml(j.source_platform)}</span>${j.status === 'review' ? reviewChip() : verifiedChip()}</div>
      <button type="button" data-save="${escapeHtml(j.id)}" aria-pressed="${saved}" aria-label="${saved ? 'Remove from saved' : 'Save'}" class="w-10 h-10 rounded-lg border border-slate-200 hover:bg-slate-50 flex items-center justify-center">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="${saved ? '#f97316' : 'none'}" stroke="${saved ? '#ea580c' : '#475569'}" stroke-width="2" stroke-linejoin="round" aria-hidden="true"><path d="M6 3h12v18l-6-4-6 4Z"/></svg>
      </button>
    </div>
    <div class="text-sm font-bold text-slate-700">${escapeHtml(j.company_name || '')}</div>
    <h3 class="text-lg font-extrabold leading-snug">${escapeHtml(j.role_title)}</h3>
    <div class="text-sm text-slate-600">${escapeHtml(j.location || 'Location not stated')}${j.duration ? ' · ' + escapeHtml(j.duration) : ''}</div>
    <div class="flex justify-between items-end border-t border-slate-100 pt-3 mt-auto">
      <div><div class="text-[11px] font-bold tracking-wider text-slate-500">STIPEND</div><div class="font-extrabold">${escapeHtml(j.stipend || 'Not stated')}</div></div>
      <button type="button" data-open="${escapeHtml(j.id)}" class="px-4 py-2.5 rounded-xl bg-slate-900 text-white text-sm font-bold hover:bg-slate-800">View details</button>
    </div></article>`;
}

function openDetails(id) {
  const j = state.listings.find(x => x.id === id);
  if (!j) return;
  state.open = j;
  $('d-source').textContent = j.source_platform;
  $('d-status').innerHTML = j.status === 'review' ? reviewChip() : verifiedChip();
  $('d-title').textContent = j.role_title;
  $('d-company').textContent = j.company_name || '';
  $('d-meta').textContent = [j.location || 'Location not stated', j.duration].filter(Boolean).join(' · ');
  $('d-stipend').textContent = j.stipend || 'Not stated';
  const reasons = String(j.moderation_reasons || '').split(' | ').map(s => s.trim()).filter(Boolean).map(plainReason).filter(Boolean);
  const notes = String(j.trust_flags || '').split(';').map(s => s.trim()).filter(Boolean);
  const box = $('d-check');
  box.className = `p-4 rounded-xl border text-sm ${j.status === 'review' ? 'bg-amber-50 border-amber-200 text-amber-900' : 'bg-green-50 border-green-200 text-green-900'}`;
  box.innerHTML = `<div class="font-extrabold mb-1.5">${j.status === 'review' ? 'Needs a look: check these before you apply' : 'Passed the scam check'}</div>`
    + `<ul class="list-disc pl-5 space-y-1">${reasons.concat(notes.map(n => `Note: ${n}`)).map(r => `<li>${escapeHtml(r)}</li>`).join('') || '<li>No warning signs found.</li>'}</ul>`;
  $('d-desc').innerHTML = describeHtml(j.description);
  $('d-desc-box').hidden = !j.description;
  $('d-apply').href = safeUrl(j.apply_link);
  updateSaveButton();
  $('drawer-overlay').hidden = false;
}
function updateSaveButton() {
  if (!state.open) return;
  const saved = state.saved.has(state.open.id);
  $('d-save').textContent = saved ? 'Saved ✓' : 'Save';
  $('d-save').setAttribute('aria-pressed', String(saved));
}

async function toggleSave(id) {
  const uid = state.session.user.id;
  if (state.saved.has(id)) {
    const { error } = await db.from('bookmarks').delete().eq('user_id', uid).eq('listing_id', id);
    if (error) { toast(`Could not remove: ${error.message}`); return; }
    state.saved.delete(id);
  } else {
    const { error } = await db.from('bookmarks').insert({ user_id: uid, listing_id: id });
    if (error) {
      toast(/row-level security/i.test(error.message)
        ? 'The free plan saves up to 10 internships. Remove one, or get Pro (coming soon).'
        : `Could not save: ${error.message}`);
      return;
    }
    state.saved.add(id);
  }
  render();
  updateSaveButton();
}

function openProfile(first) {
  const sel = $('profile-field');
  sel.innerHTML = '<option value="">Choose a field</option>' + (CFG.fields || []).map(f => `<option value="${escapeHtml(f.key)}">${escapeHtml(f.label)}</option>`).join('');
  sel.value = (state.profile && state.profile.field) || '';
  const exp = (state.profile && state.profile.experience) || '0';
  document.querySelectorAll('input[name="exp"]').forEach(r => { r.checked = r.value === exp; });
  $('profile-modal').dataset.required = first ? '1' : '';
  $('profile-modal').hidden = false;
  sel.focus();
}

async function saveProfile(e) {
  e.preventDefault();
  const field = $('profile-field').value;
  if (!field) { toast('Choose a field first.'); return; }
  const experience = (document.querySelector('input[name="exp"]:checked') || {}).value || '0';
  const { error } = await db.from('profiles').update({ field, experience }).eq('id', state.session.user.id);
  if (error) { toast(`Could not save: ${error.message}`); return; }
  Object.assign(state.profile, { field, experience });
  $('profile-modal').hidden = true;
  await loadListings();
}

// ---------- wiring ----------
function closeOnBackdrop(backdrop, close) {
  let down = false;
  backdrop.addEventListener('mousedown', e => { down = e.target === backdrop; });
  backdrop.addEventListener('click', e => { if (down && e.target === backdrop) close(); down = false; });
}
function closeProfileIfAllowed() { if (!$('profile-modal').dataset.required) $('profile-modal').hidden = true; }

document.addEventListener('click', (e) => {
  const t = e.target.closest('button, a');
  if (!t) {
    if (!e.target.closest('#account-menu, #account-btn')) $('account-menu').classList.add('hidden');
    return;
  }
  if (t.matches('[data-signin]')) { $('signin-error').hidden = true; $('signin-modal').hidden = false; $('google-btn').focus(); }
  else if (t.matches('[data-pro]')) toast('Pro (₹79/month) is coming soon. Everything free stays free.');
  else if (t.matches('[data-close]')) { $('signin-modal').hidden = true; $('drawer-overlay').hidden = true; }
  else if (t.dataset.open) openDetails(t.dataset.open);
  else if (t.dataset.save) toggleSave(t.dataset.save);
  if (!t.closest('#account-menu') && t.id !== 'account-btn') $('account-menu').classList.add('hidden');
});
$('google-btn').addEventListener('click', signIn);
$('account-btn').addEventListener('click', () => {
  const m = $('account-menu');
  m.classList.toggle('hidden');
  $('account-btn').setAttribute('aria-expanded', String(!m.classList.contains('hidden')));
});
$('sign-out').addEventListener('click', async () => { await db.auth.signOut(); location.href = '/'; });
$('edit-profile').addEventListener('click', () => openProfile(false));
$('change-field').addEventListener('click', () => openProfile(false));
$('profile-form').addEventListener('submit', saveProfile);
$('d-save').addEventListener('click', () => state.open && toggleSave(state.open.id));
['q', 'loc', 'paid', 'saved-only'].forEach(id => $(id).addEventListener('input', render));
closeOnBackdrop($('signin-modal'), () => { $('signin-modal').hidden = true; });
closeOnBackdrop($('drawer-overlay'), () => { $('drawer-overlay').hidden = true; });
closeOnBackdrop($('profile-modal'), closeProfileIfAllowed);
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape') return;
  $('signin-modal').hidden = true;
  $('drawer-overlay').hidden = true;
  $('account-menu').classList.add('hidden');
  closeProfileIfAllowed();
});
$('brand-home').addEventListener('click', e => {
  if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
  e.preventDefault();
  $('drawer-overlay').hidden = true;
  window.scrollTo({ top: 0, behavior: 'smooth' });
});

async function route() {
  if (state.session && db) await showApp();
  else await showPublic();
}

(async function start() {
  if (!db) { await showPublic(); return; }
  const { data } = await db.auth.getSession();
  state.session = data.session;
  await route();
  db.auth.onAuthStateChange((event, session) => {
    const was = !!state.session;
    state.session = session;
    if (!!session !== was) route();
  });
})();
