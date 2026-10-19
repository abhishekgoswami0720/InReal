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
