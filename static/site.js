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

const landing = { stats: null, more: 0 };

async function showLanding() {
  document.querySelectorAll('[data-sites]').forEach(el => { el.textContent = CFG.liveSites ? String(CFG.liveSites) : 'many'; });
  if (!db) { $('teaser-empty').hidden = false; return; }
  const [teaser, stats] = await Promise.all([db.rpc('teaser_listings'), db.rpc('listing_stats')]);
  const rows = teaser.data || [];
  renderTicker(rows);
  $('teaser-empty').hidden = rows.length > 0;
  $('teaser-marquee').hidden = rows.length === 0;
  const s = stats.data || {};
  landing.stats = s; landing.more = Math.max(0, (s.verified_total || 0) - rows.length);
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

// One row moving right to left. The cards are repeated until the row is wider than a big screen,
// then the whole set is doubled so the loop has no seam (the track moves by exactly half).
function renderTicker(rows) {
  if (!rows.length) { $('teaser-grid').innerHTML = ''; return; }
  let set = rows.slice();
  while (set.length < 8) set = set.concat(rows);
  const once = set.map(teaserCard).join('');
  const track = $('teaser-grid');
  track.innerHTML = once + once;
  [...track.children].slice(set.length).forEach(el => el.setAttribute('aria-hidden', 'true'));   // read the copy once
  track.style.setProperty('--marquee-s', `${set.length * 8}s`);   // about 40 px a second: readable
}

// ---------- Spot the scam (made-up posts, built from the patterns the check catches) ----------
const SPOT_PAIRS = [
  {
    real: { title: 'Python Developer Intern', org: 'Nimbus Softworks', meta: 'Pune · ₹12,000 / month · 3 months',
            text: 'Build internal tools in Django with our backend team. Weekly code reviews with a senior developer. Apply through our careers page.' },
    scam: { title: 'Python Intern (Work From Home)', org: 'SkillRise Career Academy', meta: 'Remote · ₹25,000 / month',
            text: 'Certificate guaranteed! Pay a one-time ₹999 registration fee to confirm your seat. Contact HR on WhatsApp only.',
            flags: ['Pay a one-time ₹999 registration fee', 'WhatsApp only'],
            why: ['Asks you to pay to join. Real internships pay you, not the other way round.', 'Contact only on WhatsApp, no company email or careers page.'] },
  },
  {
    real: { title: 'Data Analyst Intern', org: 'Orbitline Retail', meta: 'Bengaluru (hybrid) · ₹10,000 / month · 6 months',
            text: 'Clean sales data in Excel and SQL, build a weekly dashboard, and present it to the category team.' },
    scam: { title: 'Online Data Task Intern', org: 'QuickEarn Digital', meta: 'Remote · Earn ₹500 per task',
            text: 'Like videos and rate products from home. Deposit ₹2,000 to unlock premium tasks with double pay. Withdraw daily!',
            flags: ['Deposit ₹2,000 to unlock premium tasks', 'Like videos and rate products'],
            why: ['A "deposit" to unlock better tasks is the classic task scam.', 'Paid likes and ratings is not an internship.'] },
  },
  {
    real: { title: 'UI/UX Design Intern', org: 'Kestrel Studio', meta: 'Remote · ₹8,000 / month · 3 months',
            text: 'Design app screens in Figma with our product designer. Share a portfolio link when you apply; a short design task follows.' },
    scam: { title: 'Graphic Design Intern', org: 'Vertex Global Solutions', meta: 'Delhi · ₹18,000 / month',
            text: 'Selected directly, no interview! Send your Aadhaar, PAN and a photo of your bank passbook to finalise your offer today.',
            flags: ['Send your Aadhaar, PAN and a photo of your bank passbook', 'no interview'],
            why: ['Asks for ID and bank documents before any interview.', 'An offer with no interview and a rush ("today") is a pressure tactic.'] },
  },
];
const spot = { i: 0, right: 0, played: 0, scamSide: 0, done: false };

function highlight(text, flags) {
  let html = escapeHtml(text);
  (flags || []).forEach(f => { html = html.replace(escapeHtml(f), `<mark>${escapeHtml(f)}</mark>`); });
  return html;
}
function spotCard(post, side, reveal) {
  const isScam = side === spot.scamSide;
  const ring = !reveal ? 'border-slate-200' : isScam ? 'border-rose-400 bg-rose-50/60' : 'border-emerald-400 bg-emerald-50/60';
  const badge = !reveal ? '' : isScam
    ? '<span class="px-2 py-0.5 rounded-full bg-rose-600 text-white text-[11px] font-bold flex items-center gap-1"><i class="ph ph-warning"></i> SCAM</span>'
    : '<span class="px-2 py-0.5 rounded-full bg-emerald-600 text-white text-[11px] font-bold flex items-center gap-1"><i class="ph ph-shield-check"></i> REAL</span>';
  return `<button type="button" class="spot-card text-left glass-card p-5 flex flex-col gap-2 border-2 ${ring}" data-side="${side}" ${spot.done ? 'disabled' : ''}>
    <div class="flex items-start justify-between gap-2"><div class="font-bold text-slate-900">${escapeHtml(post.title)}</div>${badge}</div>
    <div class="text-xs font-bold text-slate-700">${escapeHtml(post.org)}</div>
    <div class="text-xs text-slate-500 font-medium">${escapeHtml(post.meta)}</div>
    <p class="text-sm text-slate-700 leading-relaxed mt-1">${reveal && isScam ? highlight(post.text, post.flags) : escapeHtml(post.text)}</p>
    ${spot.done ? '' : '<span class="mt-auto pt-2 text-xs font-bold text-orange-700">This one is the scam →</span>'}
  </button>`;
}
function renderSpot() {
  const pair = SPOT_PAIRS[spot.i % SPOT_PAIRS.length];
  const posts = spot.scamSide === 0 ? [pair.scam, pair.real] : [pair.real, pair.scam];
  $('spot-cards').innerHTML = posts.map((p, side) => spotCard(p, side, spot.done)).join('');
  $('spot-score').textContent = `Your score: ${spot.right} / ${spot.played}`;
}
function newSpotRound() {
  spot.scamSide = Math.random() < .5 ? 0 : 1;
  spot.done = false;
  $('spot-result').classList.add('hidden');
  $('spot-next').classList.add('hidden');
  renderSpot();
}
function guessSpot(side) {
  if (spot.done) return;
  const pair = SPOT_PAIRS[spot.i % SPOT_PAIRS.length];
  const ok = side === spot.scamSide;
  spot.done = true; spot.played += 1; if (ok) spot.right += 1;
  renderSpot();
  const box = $('spot-result');
  box.className = `rounded-2xl border p-4 text-sm ${ok ? 'bg-emerald-50 border-emerald-200 text-emerald-900' : 'bg-rose-50 border-rose-200 text-rose-900'}`;
  box.innerHTML = `<div class="font-extrabold mb-1.5">${ok ? 'Correct, you spotted it.' : 'Not quite: the other one is the scam.'}</div>
    <ul class="list-disc pl-5 space-y-1 font-medium">${pair.scam.why.map(w => `<li>${escapeHtml(w)}</li>`).join('')}</ul>`;
  if (!ok) { const card = document.querySelector(`.spot-card[data-side="${side}"]`); card && card.classList.add('shake'); }
  const next = $('spot-next');
  next.classList.remove('hidden');
  next.innerHTML = spot.played >= SPOT_PAIRS.length && (spot.i + 1) % SPOT_PAIRS.length === 0
    ? '<i class="ph ph-arrows-clockwise"></i> Play again' : '<i class="ph ph-arrows-clockwise"></i> Try another pair';
}
$('spot-cards').addEventListener('click', e => {
  const card = e.target.closest('.spot-card');
  if (card) guessSpot(Number(card.dataset.side));
});
$('spot-next').addEventListener('click', () => { spot.i += 1; newSpotRound(); });

const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
// ---------- How the check works: one post's journey, scrubbed by your scroll ----------
// The section is tall and its inner box sticks; how far you have scrolled through it (0 to 1)
// sets every position on the stage, so scrolling back plays the story in reverse.
function watchSteps() {
  const sec = $('how'), stage = $('how-stage');
  if (!sec || !stage) return;
  const wrap = stage.parentElement, sticky = sec.querySelector('.how-sticky'), head = sec.querySelector('.how-head');
  const q = s => stage.querySelector(s), qa = s => [...stage.querySelectorAll(s)];
  const chips = qa('.hs-chip'), A = q('[data-card="a"]'), B = q('[data-card="b"]'), C = q('[data-card="c"]');
  const scan = q('.hs-scan'), flag = q('.hs-flag'), quote = q('.hs-quote'), hiddenTag = q('.hs-hidden');
  const pillsBox = q('.hs-pills'), pills = qa('.hs-pill'), stamp = q('.hs-stamp'), burst = q('.hs-burst');
  const sparks = qa('.hs-spark'), apply = q('.hs-apply'), status = q('.hs-status-text'), hint = q('.hs-hint');
  const items = [...sec.querySelectorAll('.how-steps li')], rail = sec.querySelector('.how-rail');
  const mobileDesc = sec.querySelector('.how-mobile-desc');
  const W = 520, H = 420;

  const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
  const seg = (t, a, b) => clamp((t - a) / (b - a));
  const out = t => 1 - Math.pow(1 - t, 3);
  const back = t => { const c = 1.9; return 1 + (c + 1) * Math.pow(t - 1, 3) + c * Math.pow(t - 1, 2); };
  const lerp = (a, b, t) => a + (b - a) * t;
  const pose = (el, x, y, r, s, o) => { el.style.transform = `translate(${x}px, ${y}px) rotate(${r}deg) scale(${s})`; el.style.opacity = o; };
  const sites = Number(CFG.liveSites) || 0;

  const LABEL = ['Scam wording', 'Links & contacts', 'AI reviewer'];
  const BAD = [['bad', 'Known scam wording'], ['ok', 'Links look normal'], ['bad', 'AI quoted: asks for money']];
  const GOOD = ['No scam wording', 'Links look normal', 'Nothing to object to'];
  const setPill = (i, state, text) => {
    const p = pills[i];
    if (p.dataset.state !== state) p.dataset.state = state;
    const b = p.querySelector('b');
    if (b.textContent !== text) b.textContent = text;
  };
  // fan of the three cards once collected: [x, y, rotate, scale]
  const FAN = { c: [-30, -16, -7, .92], b: [26, -8, 5, .96], a: [0, 0, 0, 1] };

  function fit() {
    const avail = wrap.clientWidth;
    // big screens may grow the stage up to 1.3x; phones share the screen with the steps above it
    const room = sticky.clientHeight - (window.innerWidth < 1024 ? head.offsetHeight + 40 : 48);
    let s = Math.min(1.3, avail / W, room / H);
    s = Math.max(.45, s);
    stage.style.transform = `scale(${s})`;
    stage.style.left = Math.max(0, (wrap.clientWidth - W * s) / 2) + 'px';
    wrap.style.height = H * s + 'px';
  }

  let lastStep = 0;
  function frame() {
    ticking = false;
    const run = sec.offsetHeight - sticky.offsetHeight;
    let p = clamp((72 - sec.getBoundingClientRect().top) / Math.max(1, run));
    if (reduceMotion) p = p < .34 ? .33 : p < .7 ? .69 : 1;   // jump between finished scenes, no motion in between

    const s1 = seg(p, .02, .32), s2 = seg(p, .36, .68), s3 = seg(p, .72, .96);
    const step = p < .34 ? 1 : p < .7 ? 2 : 3;

    // left column: which step is on, and the orange rail
    if (step !== lastStep) {
      items.forEach((li, i) => { li.classList.toggle('on', i + 1 === step); li.classList.toggle('done', i + 1 < step); });
      if (mobileDesc) mobileDesc.textContent = items[step - 1].querySelector('.how-desc').textContent;
      stage.dataset.scene = step;
      lastStep = step;
    }
    rail.style.setProperty('--rail', p.toFixed(3));
    hint.style.opacity = 1 - seg(p, .01, .06);

    // 1 · Collect: site chips orbit, then get pulled into the middle and become posts
    chips.forEach((el, i) => {
      const a = (i / chips.length) * Math.PI * 2 - Math.PI / 2 + .2 + p * 1.4;
      const e = out(seg(s1, .04 + i * .045, .48 + i * .045));
      const x = lerp(260 + Math.cos(a) * 212, 260, e), y = lerp(205 + Math.sin(a) * 150, 160, e);
      el.style.transform = `translate(${x}px, ${y}px) translate(-50%, -50%) scale(${1 - .8 * e})`;
      el.style.opacity = 1 - seg(e, .7, 1);
    });
    const arrive = (t) => [out(t), (1 - out(t)) * 60, .8 + .2 * out(t)];
    const [tc, yc, kc] = arrive(seg(s1, .5, .8)), [tb, yb, kb] = arrive(seg(s1, .6, .9)), [ta, ya, ka] = arrive(seg(s1, .7, 1));

    // 3 · Apply (computed early: it moves B and C)
    const m = out(seg(s3, 0, .3));
    pose(C, lerp(FAN.c[0], -14, m), lerp(FAN.c[1], -26, m) + yc, lerp(FAN.c[2], -3, m), lerp(FAN.c[3], .88, m) * kc, tc * (1 - .55 * m));
    const k = seg(s3, .5, .62), shake = k > 0 && k < 1 ? Math.sin(k * Math.PI * 7) * 6 * (1 - k) : 0;
    pose(B, lerp(FAN.b[0], 0, m) + shake, lerp(FAN.b[1], 0, m) + yb, lerp(FAN.b[2], 0, m), lerp(FAN.b[3], 1.05, m) * kb, tb);
    B.style.zIndex = s3 > 0 ? 6 : 3;
    B.classList.toggle('passed', s3 >= .5);

    // 2 · Check: scanner sweeps the front post, the fee line lights up, the quote pops, the post drops out
    const d = seg(s2, .72, 1);
    pose(A, -50 * d, ya + 320 * d * d, -18 * d, ka, ta * (1 - seg(d, .55, 1)));
    A.style.filter = d > 0 ? `grayscale(${d})` : '';
    A.classList.toggle('flagged', s2 >= .42);
    const sc = seg(s2, .04, .46);
    scan.style.top = (sc * 112) + '%';
    scan.style.opacity = sc > 0 && sc < 1 ? 1 : 0;
    flag.style.setProperty('--flag', (seg(s2, .3, .42) * 100).toFixed(1) + '%');
    const qt = seg(s2, .44, .58), qb = back(qt);
    quote.style.opacity = seg(qt, 0, .4) * (1 - seg(s2, .74, .86));
    quote.style.transform = `translate(${(1 - qb) * -30}px, ${(1 - qb) * 30}px) scale(${.5 + .5 * qb})`;
    hiddenTag.style.opacity = seg(s2, .6, .68);

    // the three check pills
    pillsBox.style.opacity = seg(p, .3, .36);
    pillsBox.style.transform = `translateY(${(1 - out(seg(p, .3, .36))) * 20}px)`;
    if (s3 > 0) {
      pills.forEach((_, i) => {
        const a = .08 + i * .08;
        setPill(i, s3 < a ? '' : s3 < a + .07 ? 'run' : 'ok', s3 < a + .07 ? LABEL[i] : GOOD[i]);
      });
    } else {
      const at = [.2, .3, .5];
      pills.forEach((_, i) => {
        if (s2 < at[i] - .09) setPill(i, '', LABEL[i]);
        else if (s2 < at[i]) setPill(i, 'run', LABEL[i]);
        else setPill(i, BAD[i][0], BAD[i][1]);
      });
    }

    // the stamp slams, the card shakes, a ring and sparks burst out, then the apply button
    const st = seg(s3, .38, .5), so = out(st);
    stamp.style.opacity = seg(st, 0, .25);
    stamp.style.transform = `scale(${2.8 - 1.8 * so}) rotate(${-24 + 16 * so}deg)`;
    const b = out(seg(s3, .5, .78)), live = b > 0 && b < 1;
    burst.style.opacity = live ? 1 - b : 0;
    burst.style.transform = `scale(${.3 + 2.4 * b})`;
    sparks.forEach((el, i) => {
      const ang = (i / sparks.length) * Math.PI * 2 + .3, dist = 14 + 96 * b;
      el.style.opacity = live ? 1 - b : 0;
      el.style.transform = `translate(${Math.cos(ang) * dist}px, ${Math.sin(ang) * dist}px) rotate(${b * 260}deg)`;
    });
    const ap = seg(s3, .66, .8);
    apply.style.opacity = seg(ap, 0, .4);
    apply.style.transform = `scale(${.6 + .4 * back(ap)})`;
    apply.classList.toggle('glow', s3 >= .86);

    // status line
    let text;
    if (step === 1) text = sites ? `Reading ${Math.round(sites * seg(s1, .04, .9))} of ${sites} job sites` : 'Reading job sites';
    else if (step === 2) text = s2 < .44 ? 'Running three checks' : s2 < .72 ? 'Evidence found in the post' : 'Hidden: it asks for money';
    else text = s3 < .5 ? 'Checking the next post' : 'Passed. Linked to the original post';
    if (status.textContent !== text) status.textContent = text;
  }

  let ticking = false;
  const request = () => { if (!ticking) { ticking = true; requestAnimationFrame(frame); } };
  window.addEventListener('scroll', request, { passive: true });
  window.addEventListener('resize', () => { fit(); request(); });
  fit();
  frame();
}

// Header links: glide to the section, then a glow ring shows where you landed
function arriveAt(section) {
  const target = section.id === 'how' ? section.querySelector('h2') || section : section;
  const ring = section.id === 'how' ? section.querySelector('.how-head') || section : section;
  const top = section.getBoundingClientRect().top + window.scrollY - 88;   // below the sticky header
  window.scrollTo({ top, behavior: reduceMotion ? 'auto' : 'smooth' });
  let last = -1, still = 0;
  const wait = () => {                       // play the glow once the scroll has stopped
    const y = Math.round(window.scrollY);
    still = y === last ? still + 1 : 0;
    last = y;
    if (still < 3) return requestAnimationFrame(wait);
    ring.classList.remove('arrive'); void ring.offsetWidth; ring.classList.add('arrive');
    ring.addEventListener('animationend', () => ring.classList.remove('arrive'), { once: true });
    if (target.focus) { target.setAttribute('tabindex', '-1'); target.focus({ preventScroll: true }); }
  };
  requestAnimationFrame(wait);
}
document.querySelectorAll('a[data-nav]').forEach(a => a.addEventListener('click', e => {
  const section = document.querySelector(a.getAttribute('href'));
  if (!section || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
  e.preventDefault();
  history.replaceState(null, '', a.getAttribute('href'));
  arriveAt(section);
}));
// the link of the section you are in stays orange
if ('IntersectionObserver' in window) {
  const navFor = id => document.querySelector(`a[data-nav][href="#${id}"]`);
  new IntersectionObserver(entries => entries.forEach(en => {
    const link = navFor(en.target.id);
    if (link) link.classList.toggle('active', en.isIntersecting);
  }), { rootMargin: '-45% 0px -45% 0px' }).observe($('spot'));
  new IntersectionObserver(entries => entries.forEach(en => {
    const link = navFor(en.target.id);
    if (link) link.classList.toggle('active', en.isIntersecting);
  }), { rootMargin: '-45% 0px -45% 0px' }).observe($('how'));
}

// Logo: on this page, a spin and a glide back to the top instead of a reload
$('brand-home').addEventListener('click', e => {
  if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
  e.preventDefault();
  closeSignIn();
  goHome();
});

async function signIn() {
  if (!db) { toast('Sign-in is not set up yet (Supabase keys missing).'); return; }
  // back to this page, which forwards a signed-in visitor to /app (only this origin is allow-listed in Supabase)
  const { error } = await db.auth.signInWithOAuth({ provider: 'google', options: { redirectTo: location.origin + '/' } });
  if (error) { $('signin-error').textContent = `Google sign-in did not start: ${error.message}`; $('signin-error').hidden = false; }
}

// Open: show it, then add .open on the next frame so the fade and rise play (site.html styles).
// Close: remove .open and hide it once the fade has finished.
// The box speaks to the button that opened it, and shows the real numbers once they have loaded
const SIGNIN_TEXT = {
  login:  { title: 'Welcome back', sub: 'Log in with the Google account you used before.', btn: 'Log in with Google' },
  signup: { title: 'Create your free account', sub: 'One click with Google. No password to remember.', btn: 'Sign up with Google' },
  lock:   { title: null, sub: 'Free. One click with Google, no password.', btn: 'Unlock with Google' },
};
function fillSignIn(source) {
  const t = SIGNIN_TEXT[source] || SIGNIN_TEXT.signup;
  $('signin-title').textContent = t.title
    || (landing.more ? `Unlock ${plural(landing.more, 'more verified internship')}` : 'Unlock every verified internship');
  $('signin-sub').textContent = t.sub;
  $('google-btn-label').textContent = t.btn;
  const s = landing.stats || {};
  const ok = typeof s.verified_week === 'number' && typeof s.hidden_scams === 'number' && (s.verified_week || s.hidden_scams);
  $('signin-proof').hidden = !ok;
  if (ok) {
    $('proof-week').textContent = s.verified_week.toLocaleString('en-IN');
    $('proof-hidden').textContent = s.hidden_scams.toLocaleString('en-IN');
  }
}

function openSignIn(source) {
  const m = $('signin-modal');
  clearTimeout(m.closeTimer);
  fillSignIn(source);
  $('signin-error').hidden = true;
  m.hidden = false;
  requestAnimationFrame(() => requestAnimationFrame(() => m.classList.add('open')));
  $('google-btn').focus({ preventScroll: true });
}
function closeSignIn() {
  const m = $('signin-modal');
  if (m.hidden) return;
  m.classList.remove('open');
  clearTimeout(m.closeTimer);
  m.closeTimer = setTimeout(() => { m.hidden = true; }, reduceMotion ? 0 : 280);
}

document.addEventListener('click', (e) => {
  const t = e.target.closest('button, a');
  if (!t) return;
  if (t.matches('[data-signin]')) openSignIn(t.dataset.signin);
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
  newSpotRound();
  watchSteps();
  if (db) {
    const { data } = await db.auth.getSession();
    if (data.session) { location.replace('/app'); return; }
    db.auth.onAuthStateChange((event, session) => { if (session) location.replace('/app'); });
  }
  await showLanding();
})();
