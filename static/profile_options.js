// Choices for the profile form (static/app_radar.js), per field (keys of fields.py).
//   roles : chips in section 2; a post whose title has any of a role's words ranks higher
//   skills: suggestions in section 3; matched against the post's skills, title and text
'use strict';

window.PROFILE_ROLES = {
  ai_ml: [
    { key: 'ml', label: 'Machine Learning', words: ['machine learning', 'ml '] },
    { key: 'ds', label: 'Data Science', words: ['data science', 'data scientist'] },
    { key: 'genai', label: 'GenAI / LLM', words: ['genai', 'generative', 'llm', 'gpt', 'langchain'] },
    { key: 'cv', label: 'Computer Vision', words: ['computer vision', 'vision', 'image'] },
    { key: 'nlp', label: 'NLP', words: ['nlp', 'natural language'] },
    { key: 'research', label: 'AI Research', words: ['research'] },
  ],
  software: [
    { key: 'web', label: 'Web / Frontend', words: ['web', 'frontend', 'front end', 'front-end', 'react', 'angular', 'ui developer'] },
    { key: 'backend', label: 'Backend', words: ['backend', 'back end', 'back-end', 'node', 'django', 'spring', 'api'] },
    { key: 'fullstack', label: 'Full Stack', words: ['full stack', 'fullstack', 'full-stack', 'mern', 'mean'] },
    { key: 'mobile', label: 'Mobile Apps', words: ['android', 'ios', 'flutter', 'react native', 'mobile', 'app develop'] },
    { key: 'testing', label: 'Testing / QA', words: ['test', 'qa', 'quality assurance', 'sdet'] },
    { key: 'devops', label: 'DevOps / Cloud', words: ['devops', 'cloud', 'aws', 'azure', 'sre'] },
  ],
  data: [
    { key: 'analyst', label: 'Data Analyst', words: ['data analyst', 'data analytics', 'analytics'] },
    { key: 'business', label: 'Business Analyst', words: ['business analyst', 'business analytics'] },
    { key: 'bi', label: 'BI / Dashboards', words: ['power bi', 'tableau', 'dashboard', 'business intelligence'] },
    { key: 'engineering', label: 'Data Engineering', words: ['data engineer', 'etl', 'pipeline'] },
  ],
  medical: [
    { key: 'clinical', label: 'Clinical / Hospital', words: ['clinical', 'hospital', 'clinic', 'patient'] },
    { key: 'research', label: 'Clinical Research', words: ['research', 'trial'] },
    { key: 'public', label: 'Public Health', words: ['public health', 'community'] },
    { key: 'nutrition', label: 'Nutrition', words: ['nutrition', 'dietitian', 'diet'] },
    { key: 'coding', label: 'Medical Coding', words: ['medical coding', 'coder', 'billing'] },
  ],
  pharma_bio: [
    { key: 'pharmacy', label: 'Pharmacy', words: ['pharmacy', 'pharmacist'] },
    { key: 'qc', label: 'Quality Control / QA', words: ['quality', 'qc', 'qa'] },
    { key: 'regulatory', label: 'Regulatory Affairs', words: ['regulatory'] },
    { key: 'lab', label: 'Lab / Research', words: ['lab', 'research', 'microbiology', 'biotech'] },
    { key: 'bioinfo', label: 'Bioinformatics', words: ['bioinformatics', 'genomics'] },
  ],
  core_eng: [
    { key: 'mechanical', label: 'Mechanical', words: ['mechanical', 'automobile', 'automotive', 'manufacturing'] },
    { key: 'electrical', label: 'Electrical', words: ['electrical', 'power', 'plc'] },
    { key: 'electronics', label: 'Electronics / Embedded', words: ['electronics', 'embedded', 'vlsi', 'iot'] },
    { key: 'civil', label: 'Civil', words: ['civil', 'construction', 'structural', 'site engineer'] },
    { key: 'robotics', label: 'Robotics', words: ['robotics', 'robot'] },
  ],
  finance: [
    { key: 'accounts', label: 'Accounts', words: ['account', 'tally', 'bookkeeping'] },
    { key: 'analyst', label: 'Financial Analyst', words: ['financial analyst', 'finance analyst', 'equity', 'valuation'] },
    { key: 'tax', label: 'Tax / Audit', words: ['tax', 'audit', 'gst'] },
    { key: 'banking', label: 'Banking / Investment', words: ['bank', 'investment', 'credit'] },
  ],
  marketing: [
    { key: 'digital', label: 'Digital Marketing', words: ['digital marketing', 'seo', 'sem', 'ads'] },
    { key: 'social', label: 'Social Media', words: ['social media', 'instagram'] },
    { key: 'brand', label: 'Brand / PR', words: ['brand', 'pr ', 'public relations'] },
    { key: 'sales', label: 'Sales / BD', words: ['sales', 'business development'] },
  ],
  design: [
    { key: 'uiux', label: 'UI / UX', words: ['ui', 'ux', 'product design'] },
    { key: 'graphic', label: 'Graphic Design', words: ['graphic'] },
    { key: 'motion', label: 'Motion / Video', words: ['motion', 'video', 'animation'] },
    { key: 'fashion', label: 'Fashion / Interior', words: ['fashion', 'interior'] },
  ],
  content: [
    { key: 'writing', label: 'Content Writing', words: ['content writ', 'writer', 'blog'] },
    { key: 'copy', label: 'Copywriting', words: ['copywrit'] },
    { key: 'journalism', label: 'Journalism', words: ['journalis', 'reporter', 'news'] },
    { key: 'video', label: 'Video / Creator', words: ['video', 'youtube', 'creator'] },
  ],
  hr_ops: [
    { key: 'recruit', label: 'Recruitment', words: ['recruit', 'talent acquisition', 'hiring'] },
    { key: 'hr', label: 'HR Generalist', words: ['hr ', 'human resource', 'people'] },
    { key: 'ops', label: 'Operations', words: ['operations', 'ops'] },
  ],
  law: [
    { key: 'corporate', label: 'Corporate Law', words: ['corporate'] },
    { key: 'litigation', label: 'Litigation', words: ['litigation', 'court'] },
    { key: 'research', label: 'Legal Research', words: ['research', 'drafting'] },
    { key: 'ip', label: 'IP / Policy', words: ['intellectual property', 'ip ', 'policy'] },
  ],
};

window.PROFILE_SKILLS = {
  ai_ml: ['Python', 'Machine Learning', 'Deep Learning', 'TensorFlow', 'PyTorch', 'NLP', 'Computer Vision', 'SQL', 'Pandas', 'LangChain', 'Statistics'],
  software: ['JavaScript', 'React', 'Node.js', 'Python', 'Java', 'HTML', 'CSS', 'SQL', 'Git', 'REST API', 'Flutter', 'C++', 'MongoDB', 'AWS'],
  data: ['Excel', 'SQL', 'Python', 'Power BI', 'Tableau', 'Statistics', 'Pandas', 'Data Visualization', 'R'],
  medical: ['Patient Care', 'Clinical Research', 'Medical Coding', 'First Aid', 'Nutrition', 'Public Health', 'MS Office'],
  pharma_bio: ['Microbiology', 'Quality Control', 'Regulatory Affairs', 'Lab Techniques', 'Bioinformatics', 'GMP', 'Documentation'],
  core_eng: ['AutoCAD', 'SolidWorks', 'CATIA', 'MATLAB', 'PLC', 'Embedded C', 'Arduino', 'ANSYS', 'IoT'],
  finance: ['Excel', 'Tally', 'Accounting', 'Financial Modelling', 'GST', 'Valuation', 'Power BI'],
  marketing: ['SEO', 'Social Media Marketing', 'Google Ads', 'Content Marketing', 'Canva', 'Email Marketing', 'Sales'],
  design: ['Figma', 'Adobe Photoshop', 'Adobe Illustrator', 'Canva', 'UI/UX Design', 'Video Editing', 'After Effects'],
  content: ['Content Writing', 'Copywriting', 'SEO', 'Blogging', 'Video Editing', 'Social Media', 'English Proficiency'],
  hr_ops: ['Recruitment', 'MS Excel', 'Communication', 'Onboarding', 'HR Operations', 'Sourcing'],
  law: ['Legal Research', 'Drafting', 'Corporate Law', 'Contract Law', 'Litigation', 'MS Word'],
};

// Every skill the form can suggest while typing: each field's list plus common extras
window.ALL_SKILLS = (() => {
  const extra = ['Artificial Intelligence', 'Data Science', 'Generative AI', 'Large Language Models', 'Prompt Engineering',
    'Scikit-learn', 'Keras', 'Hugging Face', 'OpenCV', 'NumPy', 'Matplotlib', 'Data Analysis', 'Data Cleaning', 'Machine Learning Ops',
    'TypeScript', 'Next.js', 'Express.js', 'Django', 'Flask', 'FastAPI', 'Spring Boot', 'Kotlin', 'Swift', 'Android', 'iOS',
    'React Native', 'Firebase', 'PostgreSQL', 'MySQL', 'Redis', 'Docker', 'Kubernetes', 'Linux', 'Google Cloud', 'Azure', 'DevOps',
    'CI/CD', 'Go', 'Rust', 'C', 'C#', '.NET', 'PHP', 'Laravel', 'Angular', 'Vue.js', 'Redux', 'Tailwind CSS', 'Bootstrap', 'GraphQL',
    'Selenium', 'Manual Testing', 'Automation Testing', 'Jest', 'Cybersecurity', 'Ethical Hacking', 'Networking', 'Blockchain',
    'Solidity', 'Unity', 'Game Development', 'Data Structures', 'Algorithms', 'Object-Oriented Programming', 'System Design',
    'Excel VBA', 'Google Sheets', 'Looker Studio', 'Business Analysis', 'Product Management', 'Communication', 'Public Speaking',
    'Leadership', 'Teamwork', 'Problem Solving', 'Market Research', 'Copy Editing', 'Adobe Premiere Pro', 'Blender', '3D Modelling',
    'Adobe XD', 'Sketch', 'Photography', 'Lab Safety', 'PCR', 'Cell Culture', 'HPLC', 'Clinical Trials', 'Pharmacovigilance',
    'Revit', 'STAAD Pro', 'Ansys Fluent', 'Verilog', 'VHDL', 'Raspberry Pi', 'Power Systems', 'SAP', 'Zoho', 'Payroll',
    'Negotiation', 'Customer Service', 'Data Entry', 'Content Strategy', 'Instagram Marketing', 'Performance Marketing', 'Google Analytics'];
  const seen = new Map();
  Object.values(window.PROFILE_SKILLS).flat().concat(extra).forEach(s => { if (!seen.has(s.toLowerCase())) seen.set(s.toLowerCase(), s); });
  return [...seen.values()];
})();

// Suggestions under a skill text box while typing. opts.have() lists the skills already picked,
// opts.pick(name) adds one. Returns nothing; the box gets acHandleKey(e) -> true when the
// dropdown used the key (arrows, Enter on a suggestion, Escape), so other key handlers skip it.
window.attachSkillAutocomplete = function (input, opts) {
  if (!input || input.dataset.ac) return;
  input.dataset.ac = '1';
  input.setAttribute('autocomplete', 'off');
  input.setAttribute('role', 'combobox');
  input.setAttribute('aria-autocomplete', 'list');
  const wrap = document.createElement('div');
  wrap.style.position = 'relative';
  input.parentNode.insertBefore(wrap, input);
  wrap.appendChild(input);
  const list = document.createElement('div');
  list.className = 'ac-list';
  list.setAttribute('role', 'listbox');
  list.hidden = true;
  wrap.appendChild(list);
  let items = [], active = -1;
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const mark = (s, q) => {
    const i = s.toLowerCase().indexOf(q.toLowerCase());
    return i < 0 ? esc(s) : esc(s.slice(0, i)) + '<b>' + esc(s.slice(i, i + q.length)) + '</b>' + esc(s.slice(i + q.length));
  };
  function update() {
    const q = input.value.trim();
    if (!q) { list.hidden = true; items = []; active = -1; return; }
    const ql = q.toLowerCase();
    const have = new Set((opts.have() || []).map(x => x.toLowerCase()));
    // starts with it, then a word starts with it, then (3+ letters typed) contains it: "py" -> Python, not Copywriting
    const rank = s => { const l = s.toLowerCase(); return l.startsWith(ql) ? 0 : l.split(/[\s./-]+/).some(w => w.startsWith(ql)) ? 1 : (ql.length >= 3 && l.includes(ql)) ? 2 : 9; };
    const found = window.ALL_SKILLS.filter(s => !have.has(s.toLowerCase()) && rank(s) < 9)
      .sort((a, b) => rank(a) - rank(b) || a.length - b.length).slice(0, 6);
    items = found.map(s => ({ name: s, html: mark(s, q) }));
    if (!found.some(s => s.toLowerCase() === ql) && !have.has(ql)) items.push({ name: q, html: `Add “${esc(q)}”`, custom: true });
    active = items.length ? 0 : -1;
    render();
  }
  function render() {
    list.innerHTML = items.map((it, k) => `<button type="button" role="option" data-k="${k}" aria-selected="${k === active}" class="ac-item${k === active ? ' on' : ''}${it.custom ? ' custom' : ''}">${it.html}</button>`).join('');
    list.hidden = !items.length;
  }
  function choose(k) {
    const it = items[k];
    if (!it) return false;
    list.hidden = true; items = []; active = -1;
    opts.pick(it.name);
    return true;
  }
  input.addEventListener('input', update);
  input.addEventListener('focus', update);
  input.addEventListener('blur', () => setTimeout(() => { list.hidden = true; }, 150));
  list.addEventListener('mousedown', e => {   // mousedown: before the box loses focus
    const b = e.target.closest('[data-k]');
    if (b) { e.preventDefault(); choose(Number(b.dataset.k)); }
  });
  input.acHandleKey = (e) => {
    if (list.hidden || !items.length) return false;
    if (e.key === 'ArrowDown') { active = (active + 1) % items.length; render(); return true; }
    if (e.key === 'ArrowUp') { active = (active - 1 + items.length) % items.length; render(); return true; }
    if (e.key === 'Enter' && active >= 0) return choose(active);
    if (e.key === 'Escape') { list.hidden = true; return true; }
    return false;
  };
};
