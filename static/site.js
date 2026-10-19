// InReal landing page (/) and Google sign-in. A signed-in visitor goes straight to the dashboard
// at /app (static/app_radar.js in user mode). Signed out, this page can call just two database
// functions: teaser_listings() (6 posts, no text, no apply link) and listing_stats() (counts).
// Who may read what is decided by Supabase row-level security (supabase/schema.sql).
'use strict';

const CFG = window.INREAL || {};
const db = (window.supabase && CFG.supabaseUrl && CFG.supabaseKey)
  ? window.supabase.createClient(CFG.supabaseUrl, CFG.supabaseKey)
  : null;
const $ = (id) => document.getElementById(id);

function escapeHtml(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
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

// Demo cards: the dashboard's card look, hover only (nothing to open until you sign in)
function teaserCard(j) {
  return `<article class="teaser glass-card p-5 sm:p-6 flex flex-col justify-between group">
    <div>
      <div class="flex items-center gap-3 mb-3.5">
        <div class="company-logo-box shrink-0"><i class="ph ph-buildings text-xl text-slate-500"></i></div>
        <div class="min-w-0">
          <div class="flex flex-wrap items-center gap-1.5 text-[11px] font-semibold text-slate-500">
            <span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
            <span>${escapeHtml(j.source_platform)}</span>
            <span class="px-1.5 font-bold border rounded text-[10px] ml-1 flex items-center gap-0.5 bg-emerald-50 text-emerald-700 border-emerald-200"><i class="ph ph-shield-check"></i> VERIFIED</span>
          </div>
          <div class="text-xs font-bold text-slate-800 mt-0.5 truncate">${escapeHtml(j.company_name || 'Company')}</div>
        </div>
      </div>
      <h3 class="text-base font-bold text-slate-900 leading-snug line-clamp-2 group-hover:text-orange-600 transition-colors">${escapeHtml(j.role_title)}</h3>
      <div class="text-xs text-slate-500 mt-1.5 flex items-center gap-1 font-medium"><i class="ph ph-map-pin text-slate-400"></i> ${escapeHtml(j.location || 'Location not stated')}</div>
    </div>
    <div class="pt-4 mt-5 border-t border-slate-100 flex items-center justify-between text-xs">
      <div>
        <div class="text-[10px] text-slate-400 uppercase font-bold tracking-wider">Stipend</div>
        <div class="font-extrabold text-slate-900 text-sm mt-0.5">${escapeHtml(j.stipend || 'Not stated')}</div>
      </div>
      <span class="px-3 py-1.5 bg-slate-100 text-slate-500 font-semibold rounded-lg flex items-center gap-1"><i class="ph ph-lock-simple"></i> Sign in to view</span>
    </div>
  </article>`;
}

async function showLanding() {
  document.querySelectorAll('[data-sites]').forEach(el => { el.textContent = CFG.liveSites ? String(CFG.liveSites) : 'many'; });
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
  $('locked-count').textContent = more ? plural(more, 'more verified internship') : 'More verified internships';
  if (s.updated_at) {
    $('updated-at').innerHTML = `<i class="ph ph-clock-clockwise"></i> Updated ${escapeHtml(ago(s.updated_at))}`;
    $('updated-at').hidden = false;
  }
}

async function signIn() {
  if (!db) { toast('Sign-in is not set up yet (Supabase keys missing).'); return; }
  // back to this page, which forwards a signed-in visitor to /app (only this origin is allow-listed in Supabase)
  const { error } = await db.auth.signInWithOAuth({ provider: 'google', options: { redirectTo: location.origin + '/' } });
  if (error) { $('signin-error').textContent = `Google sign-in did not start: ${error.message}`; $('signin-error').hidden = false; }
}

function openSignIn() { $('signin-error').hidden = true; $('signin-modal').hidden = false; $('google-btn').focus(); }
function closeSignIn() { $('signin-modal').hidden = true; }

document.addEventListener('click', (e) => {
  const t = e.target.closest('button, a');
  if (!t) return;
  if (t.matches('[data-signin]')) openSignIn();
  else if (t.matches('[data-pro]')) toast('Pro (₹79/month) is coming soon. Everything free stays free.');
  else if (t.matches('[data-close]')) closeSignIn();
});
$('google-btn').addEventListener('click', signIn);
(function closeOnBackdrop(backdrop) {
  let down = false;
  backdrop.addEventListener('mousedown', e => { down = e.target === backdrop; });
  backdrop.addEventListener('click', e => { if (down && e.target === backdrop) closeSignIn(); down = false; });
})($('signin-modal'));
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeSignIn(); });

(async function start() {
  initGlassTranslucentBackground();
  if (db) {
    const { data } = await db.auth.getSession();
    if (data.session) { location.replace('/app'); return; }
    db.auth.onAuthStateChange((event, session) => { if (session) location.replace('/app'); });
  }
  await showLanding();
})();
