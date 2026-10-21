// First-time profile, one question per screen (like a Typeform): the 5 required questions, then an
// offer of 6 optional ones. Uses the profile helpers of app_radar.js (loaded before this file).
// "Edit profile" later opens the tabbed form in app_radar.js, which is quicker for one change.
'use strict';

const OB = { i: 0, answers: {}, phase: 'required', locked: false };

function obQuestions() {
  const a = OB.answers;
  const roles = ((window.PROFILE_ROLES || {})[a.field] || []).map(r => ({ v: r.key, t: r.label }));
  const fields = Object.entries(fieldLabels || {}).map(([v, t]) => ({ v, t }));
  return [
    { key: 'name', part: 'required', kind: 'text', q: "First, what's your name?", hint: 'Only you see it.', placeholder: 'Type your name' },
    { key: 'study_year', part: 'required', kind: 'one', q: `Nice to meet you${a.name ? ', ' + a.name.split(/\s+/)[0] : ''}. Where are you right now?`,
      options: [{ v: '1', t: '1st year' }, { v: '2', t: '2nd year' }, { v: '3', t: '3rd year' }, { v: '4', t: '4th year' }, { v: 'grad', t: 'Graduated' }] },
    { key: 'experience', part: 'required', kind: 'one', q: 'How much work experience do you have?', hint: 'Unpaid internships are shown only with 0 years.',
      options: [{ v: '0', t: '0 years' }, { v: '1-2', t: '1–2 years' }, { v: '3+', t: '3+ years' }] },
    { key: 'field', part: 'required', kind: 'one', q: 'Which field do you want an internship in?', options: fields },
    { key: 'roles', part: 'required', kind: 'many', q: 'Which roles? Pick all that fit.', hint: 'Posts for these roles come first in your list.', options: roles },
    { key: 'skills', part: 'optional', kind: 'skills', q: 'What are your skills?', hint: 'Pick at least 3. Each card shows how many of them the post asks for.' },
    { key: 'work_mode', part: 'optional', kind: 'one', q: 'How do you want to work?',
      options: [{ v: 'any', t: 'Any' }, { v: 'remote', t: 'Remote only' }, { v: 'office', t: 'Office / hybrid' }] },
    { key: 'min_stipend', part: 'optional', kind: 'one', q: 'Lowest stipend you would take (per month)?', hint: 'Posts that state no stipend are still shown.',
      options: [{ v: '0', t: 'Any' }, { v: '5000', t: '₹5,000+' }, { v: '10000', t: '₹10,000+' }, { v: '20000', t: '₹20,000+' }] },
    { key: 'max_duration', part: 'optional', kind: 'one', q: 'Longest internship you can do?',
      options: [{ v: 'any', t: 'Any' }, { v: '2', t: 'Up to 2 months' }, { v: '3', t: 'Up to 3 months' }, { v: '6', t: 'Up to 6 months' }] },
    { key: 'companies', part: 'optional', kind: 'text', q: 'Any companies you would love to work at?', hint: 'Separate with commas. Their posts come first. Leave empty to skip.', placeholder: 'e.g. Google, Zomato, Apollo Hospitals', optional: true },
    { key: 'regions', part: 'optional', kind: 'many', q: 'Where should we look?',
      options: [{ v: 'india', t: 'India' }, { v: 'usa', t: 'USA' }, { v: 'europe', t: 'Europe' }, { v: 'remote', t: 'Remote' }, { v: 'worldwide', t: 'Global' }] },
  ];
}
const OB_REQUIRED = 5;

function obValue(key) {
  const v = OB.answers[key];
  if (key === 'min_stipend') return v == null || v === '' ? null : String(v);
  return v;
}
function obValid(q) {
  const v = obValue(q.key);
  if (q.optional) return true;
  if (q.kind === 'text') return !!String(v || '').trim();
  if (q.kind === 'one') return v != null && v !== '';
  if (q.kind === 'many') return Array.isArray(v) && v.length > 0;
  if (q.kind === 'skills') return Array.isArray(v) && v.length >= 3;
  return true;
}

function obEl() { return document.getElementById('onboarding'); }

function openOnboarding() {
  const p = profile || {};
  OB.answers = {
    name: p.name || document.getElementById('profile-name')?.value || '',
    study_year: p.study_year || null, experience: p.experience || null, field: p.field || null,
    roles: (p.roles || []).slice(), skills: (p.skills || []).slice(0, SKILL_LIMIT),
    work_mode: p.work_mode || null, min_stipend: p.min_stipend ?? null, max_duration: p.max_duration || null,
    companies: (p.companies || []).join(', '), regions: (p.regions && p.regions.length) ? p.regions.slice() : ['india', 'usa', 'europe', 'remote', 'worldwide'],
  };
  const qs = obQuestions();
  const allRequired = qs.slice(0, OB_REQUIRED).every(obValid);
  // always from question 1 (the name, filled in from Google: one Enter), never from the middle
  OB.phase = allRequired ? 'offer' : 'required';
  OB.i = allRequired ? OB_REQUIRED : 0;
  OB.locked = !requiredDone(profile);
  obEl().hidden = false;
  document.body.style.overflow = 'hidden';
  obRender('none');
}

function closeOnboarding() {
  if (!requiredDone(profile)) return;   // the 5 required answers come first
  obEl().hidden = true;
  document.body.style.overflow = '';
}

// Saves what has been answered so far into the profile (same storage as the tabbed form)
function obSave() {
  const a = OB.answers;
  const next = {
    ...(profile || {}),
    name: String(a.name || '').trim(), study_year: a.study_year, experience: a.experience || '0', field: a.field,
    roles: a.roles || [], skills: (a.skills || []).slice(0, SKILL_LIMIT),
    work_mode: a.work_mode || null, max_duration: a.max_duration || null,
    min_stipend: a.min_stipend == null || a.min_stipend === '' ? null : Number(a.min_stipend),
    companies: String(a.companies || '').split(',').map(c => c.trim()).filter(Boolean),
    regions: a.regions || [], sources: (profile && profile.sources) || [],
  };
  writeProfile(next);
  saveProfileToAccount(next);
  displayOrder.clear();
  updateProfileUI();
  applyFiltersAndRender();
}

function obRender(dir) {
  const box = obEl();
  const qs = obQuestions();
  const stage = box.querySelector('[data-ob-stage]');
  const total = qs.length;
  let html = '';
  if (OB.phase === 'offer') {
    html = `<div class="ob-screen">
      <div class="w-14 h-14 rounded-2xl bg-emerald-100 text-emerald-700 flex items-center justify-center text-3xl mb-5">✓</div>
      <h2 class="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900">You're in${OB.answers.name ? ', ' + escapeHtml(OB.answers.name.split(/\s+/)[0]) : ''}. Your list is ready.</h2>
      <p class="text-slate-600 mt-3 text-base">Six more quick questions (about a minute) make it much sharper: your skills, stipend, work mode and more.</p>
      <div class="flex flex-wrap gap-3 mt-7">
        <button type="button" data-ob="more" class="glass-btn glass-btn-primary px-6 py-3.5 text-sm">Sharpen my matches →</button>
        <button type="button" data-ob="finish" class="glass-btn px-6 py-3.5 text-sm">Go to my internships</button>
      </div></div>`;
  } else if (OB.phase === 'done') {
    html = `<div class="ob-screen">
      <div class="w-14 h-14 rounded-2xl bg-orange-100 text-orange-600 flex items-center justify-center text-3xl mb-5">★</div>
      <h2 class="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900">All set. Your profile is complete.</h2>
      <p class="text-slate-600 mt-3 text-base">Click <b>Search Internships</b>, pick the sites, and we'll check every post for scams before it reaches you.</p>
      <button type="button" data-ob="finish" class="glass-btn glass-btn-primary px-6 py-3.5 text-sm mt-7">Go to my internships</button></div>`;
  } else {
    const q = qs[OB.i];
    const v = obValue(q.key);
    const letters = 'ABCDEFGHIJKLMNOP';
    let input = '';
    if (q.kind === 'text') {
      input = `<input data-ob-text type="text" maxlength="${q.key === 'companies' ? 200 : 80}" value="${escapeHtml(v || '')}" placeholder="${escapeHtml(q.placeholder || '')}"
        class="w-full bg-transparent border-0 border-b-2 border-slate-300 focus:border-orange-500 focus:outline-none text-xl sm:text-2xl py-2 text-slate-900 placeholder:text-slate-300">`;
    } else if (q.kind === 'one' || q.kind === 'many') {
      const sel = q.kind === 'one' ? [String(v ?? '')] : (v || []);
      input = `<div class="grid gap-2 ${q.options.length > 6 ? 'sm:grid-cols-2' : ''} max-w-xl">` + q.options.map((o, k) => {
        const on = sel.includes(String(o.v));
        return `<button type="button" data-ob-choice="${escapeHtml(String(o.v))}" class="ob-choice ${on ? 'on' : ''} flex items-center gap-3 text-left px-4 py-3 rounded-xl border text-base font-semibold">
          <span class="ob-key">${letters[k]}</span><span class="flex-1">${escapeHtml(o.t)}</span>${on ? '<span class="text-orange-600">✓</span>' : ''}</button>`;
      }).join('') + '</div>' + (q.options.length ? '' : '<p class="text-slate-500">No role choices for this field yet.</p>');
    } else if (q.kind === 'skills') {
      const have = (v || []);
      const lower = have.map(x => x.toLowerCase());
      const sugg = ((window.PROFILE_SKILLS || {})[OB.answers.field] || []).filter(s => !lower.includes(s.toLowerCase()));
      input = `<div class="flex flex-wrap gap-2 min-h-[44px] mb-3">${have.map((s, k) => `<span class="inline-flex items-center gap-1 pl-3 pr-1 py-1.5 rounded-full bg-orange-500 text-white text-sm font-bold">${escapeHtml(s)}<button type="button" data-ob-skill-rm="${k}" class="w-6 h-6 rounded-full hover:bg-white/20" aria-label="Remove ${escapeHtml(s)}">×</button></span>`).join('') || '<span class="text-slate-400 py-1.5">No skills yet.</span>'}</div>
        <input data-ob-skill type="text" maxlength="40" placeholder="Type a skill and press Enter" class="w-full bg-transparent border-0 border-b-2 border-slate-300 focus:border-orange-500 focus:outline-none text-lg py-2 text-slate-900 placeholder:text-slate-300">
        <div class="flex flex-wrap gap-2 mt-4">${sugg.map(s => `<button type="button" data-ob-skill-add="${escapeHtml(s)}" class="px-3 py-1.5 rounded-full border border-slate-300 bg-white text-sm font-bold text-slate-700 hover:border-orange-400 hover:text-orange-700">+ ${escapeHtml(s)}</button>`).join('')}</div>
        <div class="text-xs text-slate-500 mt-3">${have.length} / ${SKILL_LIMIT}</div>`;
    }
    const valid = obValid(q);
    const multi = q.kind === 'many' || q.kind === 'skills';
    html = `<div class="ob-screen">
      <div class="text-sm font-bold text-orange-600 mb-3 flex items-center gap-2">${OB.i + 1} <span class="text-slate-400">→</span> <span class="text-slate-400 font-semibold">${q.part === 'required' ? 'Required' : 'Optional'}</span></div>
      <h2 id="ob-q" class="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900 leading-tight">${escapeHtml(q.q)}${q.part === 'required' ? ' <span class="text-orange-500">*</span>' : ''}</h2>
      ${q.hint ? `<p class="text-slate-500 mt-2 text-base">${escapeHtml(q.hint)}</p>` : ''}
      ${multi && q.kind === 'many' ? '<p class="text-slate-500 mt-1 text-sm">Choose as many as you like</p>' : ''}
      <div class="mt-6">${input}</div>
      <div class="flex items-center gap-3 mt-7">
        <button type="button" data-ob="next" class="glass-btn glass-btn-primary px-5 py-3 text-sm ${valid ? '' : 'opacity-50'}">${q.part === 'optional' && OB.i === total - 1 ? 'Finish' : 'OK'} ✓</button>
        <span class="text-xs text-slate-500 hidden sm:inline">press <b>Enter ↵</b></span>
        ${q.part === 'optional' ? '<button type="button" data-ob="skipq" class="ml-auto text-sm font-bold text-slate-500 hover:text-slate-800">Skip this question</button>' : ''}
      </div></div>`;
  }
  stage.innerHTML = html;
  const card = stage.firstElementChild;
  if (card && dir !== 'none') card.classList.add(dir === 'back' ? 'ob-in-back' : 'ob-in');
  // progress: answered required + optional questions
  const answered = qs.filter((q, k) => obValid(q) && !(q.optional && !String(obValue(q.key) || '').trim()) && (k < OB_REQUIRED || OB.phase !== 'required')).length;
  box.querySelector('[data-ob-bar]').style.width = `${Math.round(100 * (OB.phase === 'done' ? total : Math.min(answered, total)) / total)}%`;
  box.querySelector('[data-ob="close"]').hidden = !requiredDone(profile);
  box.querySelector('[data-ob="prev"]').disabled = OB.phase !== 'required' && OB.phase !== 'optional' || OB.i === 0;
  box.querySelector('[data-ob="down"]').disabled = OB.phase !== 'required' && OB.phase !== 'optional';
  const focus = stage.querySelector('[data-ob-text], [data-ob-skill]');
  if (focus) setTimeout(() => focus.focus(), 50); else stage.querySelector('#ob-q')?.setAttribute('tabindex', '-1');
}

function obGo(delta) {
  const qs = obQuestions();
  if (delta < 0) {
    if (OB.phase === 'optional' && OB.i === OB_REQUIRED) { OB.phase = 'offer'; obRender('back'); return; }
    if (OB.i > 0 && (OB.phase === 'required' || OB.phase === 'optional')) { OB.i -= 1; obRender('back'); }
    return;
  }
  const q = qs[OB.i];
  if (!obValid(q)) {
    const card = obEl().querySelector('.ob-screen');
    card?.classList.remove('shake'); void card?.offsetWidth; card?.classList.add('shake');
    showToast('error', q.kind === 'skills' ? 'Add at least 3 skills' : 'Please answer this one', q.kind === 'skills' ? 'Or "Skip this question".' : 'It is needed to build your list.');
    return;
  }
  if (OB.phase === 'required' && OB.i === OB_REQUIRED - 1) {   // the 5 required answers are in: save them
    obSave();
    OB.phase = 'offer';
    obRender('next');
    return;
  }
  if (OB.phase === 'optional') obSave();
  if (OB.i === qs.length - 1) { OB.phase = 'done'; obRender('next'); return; }
  OB.i += 1;
  obRender('next');
}

function obChoose(val) {
  const q = obQuestions()[OB.i];
  if (q.kind === 'one') {
    OB.answers[q.key] = val;
    if (q.key === 'field') OB.answers.roles = (OB.answers.roles || []).filter(r => ((window.PROFILE_ROLES || {})[val] || []).some(x => x.key === r));
    obRender('none');
    setTimeout(() => obGo(1), 280);   // a single choice moves on by itself
  } else if (q.kind === 'many') {
    const cur = new Set(OB.answers[q.key] || []);
    cur.has(val) ? cur.delete(val) : cur.add(val);
    OB.answers[q.key] = [...cur];
    obRender('none');
  }
}
function obAddSkill(raw) {
  const s = String(raw || '').replace(/\s+/g, ' ').trim().slice(0, 40);
  const have = OB.answers.skills || (OB.answers.skills = []);
  if (!s || have.some(x => x.toLowerCase() === s.toLowerCase())) return;
  if (have.length >= SKILL_LIMIT) { showToast('info', `Up to ${SKILL_LIMIT} skills`, 'Remove one to add another.'); return; }
  have.push(s);
  obRender('none');
}

function bindOnboarding() {
  const box = obEl();
  if (!box || box.dataset.bound) return;
  box.dataset.bound = '1';
  box.addEventListener('click', e => {
    const t = e.target.closest('button');
    if (!t) return;
    if (t.dataset.obChoice !== undefined) return obChoose(t.dataset.obChoice);
    if (t.dataset.obSkillAdd) return obAddSkill(t.dataset.obSkillAdd);
    if (t.dataset.obSkillRm !== undefined) { OB.answers.skills.splice(Number(t.dataset.obSkillRm), 1); return obRender('none'); }
    const act = t.dataset.ob;
    if (act === 'next') obGo(1);
    else if (act === 'prev') obGo(-1);
    else if (act === 'down') obGo(1);
    else if (act === 'skipq') { if (OB.i === obQuestions().length - 1) { OB.phase = 'done'; obRender('next'); } else { OB.i += 1; obRender('next'); } }
    else if (act === 'more') { OB.phase = 'optional'; OB.i = OB_REQUIRED; obRender('next'); }
    else if (act === 'finish' || act === 'close') { closeOnboarding(); if (requiredDone(profile)) showToast('success', 'Profile saved', 'Click "Search Internships" to look for new posts.'); }
  });
  box.addEventListener('input', e => {
    if (e.target.matches('[data-ob-text]')) {
      OB.answers[obQuestions()[OB.i].key] = e.target.value;
      box.querySelector('[data-ob="next"]')?.classList.toggle('opacity-50', !obValid(obQuestions()[OB.i]));
    }
  });
  document.addEventListener('keydown', e => {
    if (box.hidden) return;
    const typing = e.target.matches && e.target.matches('input');
    if (e.key === 'Enter') {
      e.preventDefault();
      if (e.target.matches('[data-ob-skill]')) { obAddSkill(e.target.value); return; }
      if (OB.phase === 'offer') { OB.phase = 'optional'; OB.i = OB_REQUIRED; obRender('next'); return; }
      if (OB.phase === 'done') { closeOnboarding(); return; }
      obGo(1);
      return;
    }
    if (e.key === 'Escape' && OB.phase !== 'required') { closeOnboarding(); return; }
    if (typing || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === 'ArrowUp') { e.preventDefault(); obGo(-1); return; }
    if (e.key === 'ArrowDown') { e.preventDefault(); obGo(1); return; }
    const k = 'ABCDEFGHIJKLMNOP'.indexOf(e.key.toUpperCase());
    if (k >= 0 && e.key.length === 1 && (OB.phase === 'required' || OB.phase === 'optional')) {
      const q = obQuestions()[OB.i];
      if (q.options && q.options[k]) obChoose(String(q.options[k].v));
    }
  }, true);
}
document.addEventListener('DOMContentLoaded', bindOnboarding);
