// ════════════════════════════════════════════════════════════════════
//  CONFIG HELPERS
// ════════════════════════════════════════════════════════════════════

function getModelTargetLangCode(film, transModel) {
  const m = App.allConfigs?.[film]?.models?.[transModel];
  if (!m) return 'eng';
  if (m.target_langs?.length) return m.target_langs[0].lang_code;
  return m.target_lang_code || 'eng';
}

function getModelTargetLangs(film, transModel) {
  const m = App.allConfigs?.[film]?.models?.[transModel];
  if (!m) return [{ lang: 'English', lang_code: 'eng' }];
  if (m.target_langs?.length) return m.target_langs;
  if (m.target_lang) return [{ lang: m.target_lang, lang_code: m.target_lang_code || 'eng' }];
  return [{ lang: 'English', lang_code: 'eng' }];
}

function formatAnalysis(analysis, langCode, showNb) {
  if (!analysis) return '';
  if (typeof analysis === 'string') return analysis;
  const g = analysis.general;
  const generalText = g ? (g.text ?? g) : '';
  const generalNb   = (showNb && g && g.nb) ? g.nb : '';
  const ls = (analysis.language_specific || {})[langCode];
  const langText = ls ? (ls.text ?? ls) : '';
  const langNb   = (showNb && ls && ls.nb) ? ls.nb : '';
  return [generalText, generalNb, langText, langNb].filter(Boolean).join('\n\n');
}

function srcLangProficiency() {
  const fields = App.srcLangFields;
  if (!fields || fields.length === 0) return 'no';
  return (App.evaluatorMeta || {})[fields[0]] || 'no';
}

// ════════════════════════════════════════════════════════════════════
//  PRNG — sfc32 seeded from FNV-1a hash of evaluator ID
// ════════════════════════════════════════════════════════════════════

function fnv1a32(str) {
  let h = 0x811c9dc5 >>> 0;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h;
}

function makeSFC32(seed) {
  let a = seed >>> 0, b = (seed ^ 0xdeadbeef) >>> 0,
      c = (seed ^ 0x12345678) >>> 0, d = 1 >>> 0;
  return function rng() {
    let t = (a + b + d++) >>> 0;
    a = b ^ (b >>> 9);
    b = (c + (c << 3)) >>> 0;
    c = ((c << 21) | (c >>> 11)) >>> 0;
    c = (c + t) >>> 0;
    return t / 4294967296;
  };
}

function makeRNG(evaluatorId) {
  return makeSFC32(fnv1a32(evaluatorId));
}

function shuffle(arr, rng) {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

function sample(arr, k, rng) {
  const copy = arr.slice();
  shuffle(copy, rng);
  return copy.slice(0, k);
}

function randInt(lo, hi, rng) {
  return lo + Math.floor(rng() * (hi - lo + 1));
}


// ════════════════════════════════════════════════════════════════════
//  MQM SCORING
// ════════════════════════════════════════════════════════════════════

const SEVERITY_WEIGHTS = { major: 5, minor: 1 };

function scoreIssues(issues) {
  const pts = issues.reduce((s, iss) => {
    if (iss.category === 'no-issue') return s;
    return s + (SEVERITY_WEIGHTS[iss.severity] || 0);
  }, 0);
  return pts / SEVERITY_WEIGHTS.major;
}


// ════════════════════════════════════════════════════════════════════
//  SESSION BUILDING
// ════════════════════════════════════════════════════════════════════

function sampleRuns(methodRuns, maxRuns, rng) {
  const result = {};
  const methods = Object.keys(methodRuns).sort();
  for (const method of methods) {
    let runs = [...methodRuns[method]].sort((a, b) =>
      a.length - b.length || a.localeCompare(b));
    if (runs.length > maxRuns) {
      runs = sample(runs, maxRuns, rng)
        .sort((a, b) => a.length - b.length || a.localeCompare(b));
    }
    result[method] = runs;
  }
  return result;
}

function baseRecordsForFilm(film, transModel, data, methodFilter, maxRuns, rng, targetLangCode) {
  const tgtCode = targetLangCode || getModelTargetLangCode(film, transModel);
  const items = data.items;
  const methodRuns = {};

  for (const item of items) {
    const trans = (item.translations || {})[tgtCode] || {};
    for (const [method, runs] of Object.entries(trans)) {
      if (methodFilter && !methodFilter.has(method)) continue;
      if (!methodRuns[method]) methodRuns[method] = new Set();
      for (const run of Object.keys(runs)) methodRuns[method].add(run);
    }
  }

  const sampled = sampleRuns(methodRuns, maxRuns, rng);
  const records = [];

  for (const [method, runs] of Object.entries(sampled)) {
    for (const run of runs) {
      const missing = items.filter(item => {
        const trans = (item.translations || {})[tgtCode] || {};
        return !(trans[method] && trans[method][run] !== undefined);
      });
      if (missing.length > 0) {
        console.warn(`Missing items for ${film}/${transModel}/${method}/run${run}:`,
          missing.map(i => i.id));
        continue;
      }
      for (const item of items) {
        records.push({ film, transModel, itemId: item.id, method, run, tgtCode });
      }
    }
  }
  return records;
}

function buildSessionTasks(filmsModelsData, methodFilter, maxRuns, repeatFraction, rng, targetLangCode) {
  const base = [];
  for (const { film, transModel, data } of filmsModelsData) {
    base.push(...baseRecordsForFilm(film, transModel, data, methodFilter, maxRuns, rng, targetLangCode));
  }

  shuffle(base, rng);

  const tasks = base.map(r => ({
    film: r.film, trans_model: r.transModel,
    item_id: r.itemId, method: r.method, run: r.run,
    target_lang_code: r.tgtCode,
    is_repeat: false,
  }));

  const nRepeats = base.length > 0 && repeatFraction > 0
    ? Math.max(1, Math.round(base.length * repeatFraction))
    : 0;
  const repeatSrcs = sample([...Array(base.length).keys()],
    Math.min(nRepeats, base.length), rng);

  const repeats = repeatSrcs.map(i => ({
    film: base[i].film, trans_model: base[i].transModel,
    item_id: base[i].itemId, method: base[i].method, run: base[i].run,
    target_lang_code: base[i].tgtCode,
    is_repeat: true,
  }));

  shuffle(repeats, rng);

  const half = Math.floor(tasks.length / 2);
  for (const rt of repeats) {
    const pos = randInt(half, tasks.length, rng);
    tasks.splice(pos, 0, rt);
  }

  return tasks;
}


// ════════════════════════════════════════════════════════════════════
//  INCONSISTENCY DETECTION
// ════════════════════════════════════════════════════════════════════

function getTranslationText(task, itemsByFilm) {
  const item    = (itemsByFilm[task.film] || {})[task.trans_model] || {};
  const it      = item[task.item_id] || {};
  const tgtCode = task.target_lang_code || getModelTargetLangCode(task.film, task.trans_model);
  return ((it.translations || {})[tgtCode] || {})[task.method]?.[task.run] ?? '';
}

function findInconsistencies(session, itemsByFilm) {
  const tasks     = session.tasks;
  const judgments = session.judgments;
  const result    = [];

  // Group judged tasks by exact translation text
  const byText = {};
  tasks.forEach((t, i) => {
    if (!judgments[String(i)]) return;
    const text = getTranslationText(t, itemsByFilm);
    if (!text) return;
    const key = `${t.film}\x00${text}`;
    (byText[key] = byText[key] || []).push(i);
  });

  for (const [key, indices] of Object.entries(byText)) {
    const text = key.split('\x00').slice(1).join('\x00');
    if (indices.length < 2) continue;
    const scores = indices.map(i => scoreIssues(judgments[String(i)].issues));
    if (scores.every(s => s === scores[0])) continue;
    const t = tasks[indices[0]];
    result.push({
      film: t.film, trans_model: t.trans_model, item_id: t.item_id,
      translation_text: text,
      task_indices: indices,
    });
  }

  return result;
}


// ════════════════════════════════════════════════════════════════════
//  APP STATE
// ════════════════════════════════════════════════════════════════════

const App = {
  evaluatorId:   null,
  session:       null,
  itemsByFilm:   null,
  subsByFilm:      {},
  transSubsByFilm: {},
  navSequence:   [],
  totalTasks:    0,
  sliderPos:     1,
  lastSaved:     null,
  currentIssues: [],
  viewedAnalysis: false,
  incons:        [],
  inconPos:      0,
  reEvalIssues:  [],
  allConfigs:              null,
  selectedFilm:            null,
  selectedTargetLangCode:  null,
  selectedTargetLang:      null,
  targetLang:              null,
  srcLangFields:           null,
  regState:                {},
};

function storageKey(id, film, langCode) {
  return `subtitle-eval-${id}-${film}-${langCode}`;
}

function saveSession() {
  localStorage.setItem(
    storageKey(App.evaluatorId, App.selectedFilm, App.selectedTargetLangCode),
    JSON.stringify(App.session));
}

function buildNavSequence() {
  const { tasks, skipped } = App.session;
  const skippedSet = new Set(skipped);
  App.navSequence = tasks
    .map((task, i) => ({ taskIdx: i, task }))
    .filter(({ taskIdx }) => !skippedSet.has(taskIdx));
  App.totalTasks = App.navSequence.length;
  App.sliderPos  = Math.min(getFrontier(), App.totalTasks);
}

function getFrontier() {
  const judgments = App.session.judgments;
  const idx = App.navSequence.findIndex(({ taskIdx }) => !judgments[String(taskIdx)]);
  return idx === -1 ? App.navSequence.length + 1 : idx + 1;
}


// ════════════════════════════════════════════════════════════════════
//  SCREEN MANAGEMENT
// ════════════════════════════════════════════════════════════════════

function showScreen(id) {
  document.querySelectorAll('.screen').forEach(el => el.classList.remove('active'));
  document.getElementById(id).classList.add('active');
}

function setLoading(msg) {
  document.getElementById('loading-msg').textContent = msg;
}


// ════════════════════════════════════════════════════════════════════
//  DATA LOADING
// ════════════════════════════════════════════════════════════════════

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`HTTP ${r.status}: ${url}`);
  return r.json();
}

function buildItemsByFilm(filmsModelsData) {
  const byFilm = {};
  for (const { film, transModel, data } of filmsModelsData) {
    if (!byFilm[film]) byFilm[film] = {};
    if (!byFilm[film][transModel]) byFilm[film][transModel] = {};
    for (const item of data.items) {
      byFilm[film][transModel][item.id] = item;
    }
  }
  return byFilm;
}

async function loadSubsForFilms(films) {
  for (const film of films) {
    if (App.subsByFilm[film]) continue;
    try {
      const subs = await fetchJSON(`data/${film}/subs.json`);
      App.subsByFilm[film] = subs;
    } catch (_) {
      // subs.json is optional; context feature simply won't show for this film
    }
  }
}

async function loadTransSubsForSession(tasks) {
  // Collect unique (film, transModel, method) combos from all tasks
  const seen = new Set();
  for (const t of tasks) {
    seen.add(`${t.film}\x00${t.trans_model}\x00${t.method}`);
  }
  for (const key of seen) {
    const [film, transModel, method] = key.split('\x00');
    if ((App.transSubsByFilm[film] || {})[transModel]?.[method]) continue;
    try {
      const subs = await fetchJSON(`data/${film}/${transModel}-${method}-subs.json`);
      if (!App.transSubsByFilm[film]) App.transSubsByFilm[film] = {};
      if (!App.transSubsByFilm[film][transModel]) App.transSubsByFilm[film][transModel] = {};
      App.transSubsByFilm[film][transModel][method] = subs;
    } catch (_) {
      // optional; context button will be hidden for this method
    }
  }
}

async function loadFilmDataForSession(session) {
  const pairs = new Map();
  for (const t of session.tasks) {
    const key = `${t.film}/${t.trans_model}`;
    if (!pairs.has(key)) pairs.set(key, { film: t.film, transModel: t.trans_model });
  }
  const filmsModelsData = [];
  for (const { film, transModel } of pairs.values()) {
    setLoading(`Loading ${film} / ${transModel}…`);
    const data = await fetchJSON(`data/${film}/${transModel}.json`);
    filmsModelsData.push({ film, transModel, data });
  }
  return filmsModelsData;
}

async function startOrResume(evaluatorId) {
  showScreen('loading-screen');
  try {
    const newKey = storageKey(evaluatorId, App.selectedFilm, App.selectedTargetLangCode);
    let stored = localStorage.getItem(newKey);

    if (stored) {
      App.session = JSON.parse(stored);
      // Derive selection state from stored session
      App.selectedFilm           = App.session.tasks[0]?.film           || App.selectedFilm;
      App.selectedTargetLangCode = App.session.tasks[0]?.target_lang_code || App.selectedTargetLangCode;
      const filmsModelsData = await loadFilmDataForSession(App.session);
      App.itemsByFilm = buildItemsByFilm(filmsModelsData);
    } else {
      // Fresh session: build tasks for selected film only
      const film    = App.selectedFilm;
      const tgtCode = App.selectedTargetLangCode;
      const filmCfg = App.allConfigs[film];
      if (!filmCfg) throw new Error(`No config for film "${film}"`);

      const filmsModelsData = [];
      const tasks = [];
      const rng = makeRNG(evaluatorId);

      for (const [model, modelCfg] of Object.entries(filmCfg.models || {})) {
        // Only include models that have the selected target language
        const modelLangs = getModelTargetLangs(film, model);
        const hasLang = modelLangs.some(tl => tl.lang_code === tgtCode);
        if (!hasLang) continue;

        setLoading(`Loading ${film} / ${model}…`);
        const data = await fetchJSON(`data/${film}/${model}.json`);
        filmsModelsData.push({ film, transModel: model, data });
        const runsRequested  = modelCfg.runs_requested  || 3;
        const repeatFraction = modelCfg.repeat_fraction || 0.1;
        const filmTasks = buildSessionTasks(
          [{ film, transModel: model, data }], null, runsRequested, repeatFraction, rng, tgtCode
        );
        tasks.push(...filmTasks);
      }

      // Shuffle all tasks together
      for (let i = tasks.length - 1; i > 0; i--) {
        const j = Math.floor(rng() * (i + 1));
        [tasks[i], tasks[j]] = [tasks[j], tasks[i]];
      }

      App.session = {
        evaluator_id:              evaluatorId,
        evaluator_meta:            App.evaluatorMeta || null,
        created:                   new Date().toISOString(),
        tasks,
        judgments:                 {},
        skipped:                   [],
        inconsistency_resolutions: {},
      };

      App.itemsByFilm = buildItemsByFilm(filmsModelsData);
      saveSession();
    }

    // Load subtitle context data (optional; silently skipped if missing)
    const uniqueFilms = [...new Set(App.session.tasks.map(t => t.film))];
    await loadSubsForFilms(uniqueFilms);
    await loadTransSubsForSession(App.session.tasks);

    buildNavSequence();
    App.lastSaved     = null;
    App.currentIssues = [];

    if (getFrontier() > App.navSequence.length) {
      startReview();
    } else {
      showEvalScreen();
    }
  } catch (err) {
    showScreen('film-screen');
    showLoginError(err.message);
  }
}


// ════════════════════════════════════════════════════════════════════
//  EVALUATION SCREEN
// ════════════════════════════════════════════════════════════════════

function showEvalScreen() {
  showScreen('eval-screen');
  renderCurrentItem();
}

function renderContextSegments(film, item, windowBefore = 3, windowAfter = 2) {
  const listEl = document.getElementById('context-segments');
  const btnEl  = document.getElementById('btn-show-context');
  const subs   = App.subsByFilm[film];
  const segs   = item.segment_number;

  if (!subs || !segs || segs.length === 0) {
    btnEl.style.display = 'none';
    listEl.innerHTML = '';
    return;
  }
  btnEl.style.display = '';

  const itemSegs = new Set(segs);
  const min = Math.min(...segs);
  const max = Math.max(...segs);

  listEl.innerHTML = '';
  for (let n = min - windowBefore; n <= max + windowAfter; n++) {
    const text = subs[String(n)];
    if (text === undefined) continue;
    const li = document.createElement('li');
    li.className = 'context-seg' + (itemSegs.has(n) ? ' current' : '');
    li.innerHTML =
      `<span class="context-seg-num">${n}</span>` +
      `<span>${esc(text.replace(/\n/g, ' / '))}</span>`;
    listEl.appendChild(li);
  }
}

function renderTranslationContext(film, transModel, method, run, item, windowBefore = 3, windowAfter = 2) {
  const listEl = document.getElementById('trans-context-segments');
  const btnEl  = document.getElementById('btn-show-trans-context');
  const subs   = (App.transSubsByFilm[film] || {})[transModel]?.[method];
  const segs   = item.segment_number;

  if (!subs || !segs || segs.length === 0) {
    btnEl.style.display = 'none';
    listEl.innerHTML = '';
    return;
  }
  btnEl.style.display = '';

  const itemSegs = new Set(segs);
  const min = Math.min(...segs);
  const max = Math.max(...segs);

  listEl.innerHTML = '';
  for (let n = min - windowBefore; n <= max + windowAfter; n++) {
    const text = subs[String(n)];
    if (text === undefined) continue;
    const li = document.createElement('li');
    li.className = 'context-seg' + (itemSegs.has(n) ? ' current' : '');
    li.innerHTML =
      `<span class="context-seg-num">${n}</span>` +
      `<span>${esc(text.replace(/\n/g, ' / '))}</span>`;
    listEl.appendChild(li);
  }
}

function renderCurrentItem() {
  if (getFrontier() > App.navSequence.length) {
    startReview();
    return;
  }

  const { taskIdx, task } = App.navSequence[App.sliderPos - 1];
  const judgment = App.session.judgments[String(taskIdx)];
  const isReview = !!judgment;

  const film   = task.film;
  const tModel = task.trans_model;
  const itemId = task.item_id;
  const item   = App.itemsByFilm[film]?.[tModel]?.[itemId];

  if (!item) {
    console.error('Item not found:', film, tModel, itemId);
    App.sliderPos = getFrontier();
    renderCurrentItem();
    return;
  }

  // Slider + label
  const frontier = getFrontier();
  const slider   = document.getElementById('progress-slider');
  slider.min   = 1;
  slider.max   = App.totalTasks;
  slider.value = App.sliderPos;
  // Fill judged zone in accent colour, remaining in border colour
  const filledPct = ((frontier - 1) / App.totalTasks) * 100;
  slider.style.background =
    `linear-gradient(to right, var(--accent) ${filledPct}%, var(--border) ${filledPct}%)`;
  const nAuto = countAutoFilled();
  document.getElementById('progress-label').textContent =
    nAuto > 0
      ? `${App.sliderPos} / ${App.totalTasks} · ${nAuto} auto`
      : `${App.sliderPos} / ${App.totalTasks}`;

  // Meta
  const filmDisplay = film.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  document.getElementById('item-meta').innerHTML =
    `<span><strong>Film:</strong> ${esc(filmDisplay)}</span>` +
    `<span><strong>Character:</strong> ${esc(item.character || '—')}</span>`;

  // Texts
  const srcCode = App.allConfigs?.[film]?.source_lang_code || 'rus';
  const tgtCode = task.target_lang_code || getModelTargetLangCode(film, tModel);
  document.getElementById('original-text').textContent = (item.original || {})[srcCode] || '';
  const trans = ((item.translations || {})[tgtCode] || {})[task.method]?.[task.run] || '';
  document.getElementById('translation-text').textContent = trans;

  // Context
  document.getElementById('context-body').classList.remove('open');
  document.getElementById('btn-show-context').textContent = 'Show context';
  document.getElementById('trans-context-body').classList.remove('open');
  document.getElementById('btn-show-trans-context').textContent = 'Show context';
  renderContextSegments(film, item);
  renderTranslationContext(film, tModel, task.method, task.run, item);

  // Analysis
  App.viewedAnalysis = isReview ? (judgment.viewed_analysis || false) : false;
  document.getElementById('analysis-body').classList.remove('open');
  document.getElementById('btn-show-analysis').textContent = "Don't remember why this was funny? Show analysis.";
  document.getElementById('analysis-text').textContent = formatAnalysis(item.analysis, task.target_lang_code, srcLangProficiency() === 'no');

  // Issues: pre-populate from saved judgment when reviewing
  App.currentIssues = isReview ? judgment.issues.slice() : [];
  renderCurrentIssueList();

  // Banner
  const prevDiv = document.getElementById('prev-summary');
  if (isReview) {
    document.getElementById('prev-summary-text').textContent =
      'Editing a saved judgment — save to update.';
    prevDiv.style.display = '';
  } else if (App.lastSaved) {
    document.getElementById('prev-summary-text').textContent =
      formatIssuesBrief(App.lastSaved.issues);
    prevDiv.style.display = '';
  } else {
    prevDiv.style.display = 'none';
  }

  // Clear add-issue form
  clearGroup('sev-group');
  clearGroup('cat-group');
  document.getElementById('just-input').value = '';
}

function renderCurrentIssueList() {
  renderIssueList(
    document.getElementById('issue-list'),
    document.getElementById('no-issues-note'),
    App.currentIssues,
    i => { App.currentIssues.splice(i, 1); renderCurrentIssueList(); }
  );
}

function renderIssueList(listEl, noteEl, issues, onRemove) {
  listEl.innerHTML = '';
  if (issues.length === 0) {
    noteEl.style.display = '';
    return;
  }
  noteEl.style.display = 'none';
  for (let i = 0; i < issues.length; i++) {
    const iss = issues[i];
    const li  = document.createElement('li');
    li.className = 'issue-item';
    li.innerHTML = `
      <span class="badge badge-${esc(iss.severity)}">${esc(iss.severity)}</span>
      <span class="issue-desc"><strong>${esc(iss.category)}</strong>${iss.justification ? ': ' + esc(iss.justification) : ''}</span>
      <button class="btn-remove" title="Remove" data-i="${i}">&times;</button>`;
    li.querySelector('.btn-remove').addEventListener('click', () => onRemove(i));
    listEl.appendChild(li);
  }
}

function formatIssuesBrief(issues) {
  if (!issues || issues.length === 0) return 'No issues';
  return issues.map(iss => {
    const j = iss.justification ? ': ' + iss.justification.slice(0, 40) : '';
    return `${iss.severity}/${iss.category}${j}`;
  }).join(' · ');
}

function getGroupValue(groupId) {
  const active = document.querySelector(`#${groupId} .btn-toggle.active-major, #${groupId} .btn-toggle.active-minor, #${groupId} .btn-toggle.active-cat`);
  return active ? active.dataset.value : '';
}

function clearGroup(groupId) {
  document.querySelectorAll(`#${groupId} .btn-toggle`).forEach(b =>
    b.classList.remove('active-major', 'active-minor', 'active-cat'));
}

function wireToggleGroup(groupId, activeClass) {
  document.querySelectorAll(`#${groupId} .btn-toggle`).forEach(btn => {
    btn.addEventListener('click', () => {
      clearGroup(groupId);
      btn.classList.add(activeClass);
    });
  });
}

function addIssueFromForm(sevGroupId, catGroupId, justId, targetArr, rerender) {
  const sev  = getGroupValue(sevGroupId);
  const cat  = getGroupValue(catGroupId);
  const just = document.getElementById(justId).value.trim();
  if (!sev || !cat) return;
  targetArr.push({ severity: sev, category: cat, span: '', justification: just });
  clearGroup(sevGroupId);
  clearGroup(catGroupId);
  document.getElementById(justId).value = '';
  rerender();
}

function issuesSignature(issues) {
  return JSON.stringify(
    issues
      .filter(iss => iss.category !== 'no-issue')
      .map(iss => `${iss.severity}:${iss.category}`)
      .sort()
  );
}

function autoFillFromConsensus() {
  const tasks     = App.session.tasks;
  const judgments = App.session.judgments;

  // Build text → {sig: {count, issues}} from human (non-auto) judgments
  const textSigs = {};
  tasks.forEach((task, i) => {
    const j = judgments[String(i)];
    if (!j || j.auto_filled) return;
    const text = getTranslationText(task, App.itemsByFilm);
    if (!text) return;
    const sig = issuesSignature(j.issues);
    if (!textSigs[text]) textSigs[text] = {};
    if (!textSigs[text][sig]) textSigs[text][sig] = { count: 0, issues: j.issues };
    textSigs[text][sig].count++;
  });

  // Find texts with 3+ identical signatures
  const consensus = {};
  for (const [text, sigs] of Object.entries(textSigs)) {
    for (const { count, issues } of Object.values(sigs)) {
      if (count >= 3) { consensus[text] = issues; break; }
    }
  }

  if (Object.keys(consensus).length === 0) return 0;

  // Auto-fill pending tasks; record indices in a permanent set
  if (!App.session.auto_filled_set) App.session.auto_filled_set = [];
  const autoSet = new Set(App.session.auto_filled_set);
  let nFilled = 0;
  tasks.forEach((task, i) => {
    if (judgments[String(i)]) return;
    const text = getTranslationText(task, App.itemsByFilm);
    if (consensus[text] !== undefined) {
      judgments[String(i)] = { issues: consensus[text], auto_filled: true };
      autoSet.add(i);
      nFilled++;
    }
  });
  App.session.auto_filled_set = [...autoSet];
  return nFilled;
}

function countAutoFilled() {
  return (App.session.auto_filled_set || []).length;
}

function saveJudgment(issues) {
  const { taskIdx } = App.navSequence[App.sliderPos - 1];
  const wasReview = !!App.session.judgments[String(taskIdx)];
  App.session.judgments[String(taskIdx)] = { issues, viewed_analysis: App.viewedAnalysis };
  autoFillFromConsensus();
  saveSession();
  App.lastSaved = { taskIdx, issues };
  if (wasReview) {
    // editing a past item: go to N+1, capped at frontier
    App.sliderPos = Math.min(App.sliderPos + 1, getFrontier());
  } else {
    // new judgment: advance to new frontier
    App.sliderPos = getFrontier();
  }
  if (App.sliderPos > App.navSequence.length) {
    startReview();
    return;
  }
  renderCurrentItem();
}


// ════════════════════════════════════════════════════════════════════
//  INCONSISTENCY REVIEW
// ════════════════════════════════════════════════════════════════════

function startReview() {
  App.incons   = findInconsistencies(App.session, App.itemsByFilm);
  const resolutions = App.session.inconsistency_resolutions || {};
  App.incons = App.incons.filter(inc => !resolutions[String(inc.task_indices[0])]);
  App.inconPos = 0;

  if (App.incons.length === 0) {
    showComplete();
    return;
  }

  showScreen('review-screen');
  document.getElementById('review-subtitle').textContent =
    `${App.incons.length} inconsistenc${App.incons.length === 1 ? 'y' : 'ies'} found — please review.`;
  renderIncon();
}

function renderIncon() {
  const inconDiv = document.getElementById('review-body');
  const navDiv   = document.getElementById('review-nav');
  const rePanel  = document.getElementById('re-eval-panel');
  rePanel.style.display = 'none';
  App.reEvalIssues = [];

  if (App.inconPos >= App.incons.length) {
    showComplete();
    return;
  }

  const inc = App.incons[App.inconPos];
  navDiv.style.display = '';
  document.getElementById('btn-review-prev').disabled = App.inconPos === 0;
  document.getElementById('btn-review-next').textContent =
    App.inconPos === App.incons.length - 1 ? 'Finish ✓' : 'Next →';

  const item       = App.itemsByFilm[inc.film]?.[inc.trans_model]?.[inc.item_id] || {};
  const srcCode    = App.allConfigs?.[inc.film]?.source_lang_code || 'rus';
  const srcLang    = App.allConfigs?.[inc.film]?.source_lang || 'Russian';
  const original   = (item.original || {})[srcCode] || '';
  const analysis   = formatAnalysis(item.analysis, inc.task_indices[0] != null ? App.session.tasks[inc.task_indices[0]]?.target_lang_code : null, srcLangProficiency() === 'no');
  const filmDisplay = inc.film.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

  // Group judgments by issues signature
  const groups = [];
  inc.task_indices.forEach(idx => {
    const j   = App.session.judgments[String(idx)];
    const sig = issuesSignature(j.issues);
    let group = groups.find(g => g.sig === sig);
    if (!group) {
      group = { sig, issues: j.issues, score: scoreIssues(j.issues), firstIdx: idx };
      groups.push(group);
    }
  });

  const translationsHTML = `<div class="text-block" style="font-size:0.9rem;margin-bottom:6px;">${esc(inc.translation_text)}</div>`;

  let judgmentsHTML = '';
  groups.forEach((group, k) => {
    const label = String.fromCharCode(65 + k);
    judgmentsHTML += `
      <div class="judgment-box">
        <span class="j-score">score: ${group.score.toFixed(2)}</span>
        <strong>Judgment ${esc(label)}</strong>
        ${renderIssuesHTML(group.issues)}
        <button class="btn btn-secondary btn-sm" style="margin-top:8px;" data-use-idx="${group.firstIdx}">Use judgment ${esc(label)}</button>
      </div>`;
  });

  inconDiv.innerHTML = `
    <div class="card">
      <div class="incon-meta">
        ${App.inconPos + 1} of ${App.incons.length} &nbsp;·&nbsp;
        <strong>${esc(filmDisplay)}</strong> &nbsp;·&nbsp; ${esc(item.character || '—')}
      </div>
      <div class="card-label">Original (${esc(srcLang)})</div>
      <div class="text-block" style="margin-bottom:10px;">${esc(original)}</div>
      <div class="card-label" style="margin-top:10px;">Translation</div>
      ${translationsHTML}
      <button class="btn btn-ghost btn-sm" id="btn-review-analysis" style="padding:3px 8px;font-size:0.78rem;">Don't remember why this was funny? Show analysis.</button>
      <div class="analysis-body" id="review-analysis-body">
        <p class="analysis-note">Generated by AI and reviewed by a person.</p>
        <div>${esc(analysis)}</div>
      </div>
    </div>
    ${judgmentsHTML}
    <div class="action-row" style="margin-top:4px;">
      <button class="btn btn-ghost" id="btn-re-eval">Re-evaluate</button>
    </div>`;

  document.getElementById('btn-review-analysis').addEventListener('click', () => {
    const body = document.getElementById('review-analysis-body');
    const btn  = document.getElementById('btn-review-analysis');
    const isOpen = body.classList.toggle('open');
    btn.textContent = isOpen ? 'Hide analysis.' : "Don't remember why this was funny? Show analysis.";
  });

  inconDiv.querySelectorAll('[data-use-idx]').forEach(btn => {
    btn.addEventListener('click', () => {
      const idx = parseInt(btn.dataset.useIdx);
      resolveIncon(App.session.judgments[String(idx)].issues);
    });
  });

  document.getElementById('btn-re-eval').addEventListener('click', () => {
    rePanel.style.display = '';
    App.reEvalIssues = [];
    renderReEvalIssueList();
  });
}

function renderIssuesHTML(issues) {
  if (!issues || issues.length === 0) return '<p style="color:var(--muted);font-size:0.88rem;margin-top:4px;">(no issues)</p>';
  return '<ul style="margin-top:6px;list-style:none;">' +
    issues.map(iss =>
      `<li style="font-size:0.88rem;margin-bottom:2px;">
        <span class="badge badge-${esc(iss.severity)}">${esc(iss.severity)}</span>
        <strong>${esc(iss.category)}</strong>${iss.justification ? ': ' + esc(iss.justification) : ''}
      </li>`
    ).join('') + '</ul>';
}

function renderReEvalIssueList() {
  renderIssueList(
    document.getElementById('re-eval-issue-list'),
    document.getElementById('re-eval-no-issues-note'),
    App.reEvalIssues,
    i => { App.reEvalIssues.splice(i, 1); renderReEvalIssueList(); }
  );
}

function resolveIncon(issues) {
  const inc = App.incons[App.inconPos];
  const resolutions = App.session.inconsistency_resolutions;
  const resolution = { issues, source: 'human-review' };
  inc.task_indices.forEach(i => { resolutions[String(i)] = resolution; });
  saveSession();
  App.inconPos++;
  renderIncon();
}


// ════════════════════════════════════════════════════════════════════
//  COMPLETE SCREEN
// ════════════════════════════════════════════════════════════════════

function showComplete() {
  showScreen('complete-screen');
  const s = App.session;
  const total    = s.tasks.filter(t => !t.is_repeat).length;
  const judged   = Object.keys(s.judgments).length;
  const skipped  = s.skipped.length;
  document.getElementById('complete-stats').textContent =
    `${judged} items judged · ${skipped} skipped · session for evaluator "${s.evaluator_id}"`;

}

function downloadSession() {
  const json = JSON.stringify(App.session, null, 2) + '\n';
  const blob = new Blob([json], { type: 'application/json' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = 'session.json';
  a.click();
  URL.revokeObjectURL(url);
}


// ════════════════════════════════════════════════════════════════════
//  UTILITY
// ════════════════════════════════════════════════════════════════════

function esc(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function showLoginError(msg) {
  const el = document.getElementById('login-error');
  el.textContent = msg;
  el.style.display = '';
}


// ════════════════════════════════════════════════════════════════════
//  FILM / LANGUAGE SELECTION SCREEN
// ════════════════════════════════════════════════════════════════════

function showFilmSelectionScreen() {
  const cfg = App.allConfigs;
  if (!cfg) { showScreen('login-screen'); return; }

  const pairMap = {};  // lang_code → lang name
  for (const filmCfg of Object.values(cfg)) {
    if (!filmCfg.models) continue;
    for (const modelCfg of Object.values(filmCfg.models)) {
      for (const tl of (modelCfg.target_langs || [])) {
        pairMap[tl.lang_code] = tl.lang;
      }
    }
  }

  const srcLangs = [...new Set(
    Object.values(cfg).filter(fc => fc.models).map(fc => fc.source_lang).filter(Boolean)
  )];
  const srcLabel = srcLangs.join('/') || 'Source';

  const container = document.getElementById('lang-pair-buttons');
  container.innerHTML = '';
  for (const [code, name] of Object.entries(pairMap)) {
    const btn = document.createElement('button');
    btn.className = 'btn btn-secondary btn-sm btn-toggle';
    btn.dataset.code = code;
    btn.textContent = `${srcLabel} → ${name}`;
    btn.addEventListener('click', () => {
      container.querySelectorAll('.btn-toggle').forEach(b => b.classList.remove('active-cat'));
      btn.classList.add('active-cat');
      App.selectedTargetLangCode = code;
      App.selectedTargetLang = name;
      showFilmsForPair(code);
    });
    container.appendChild(btn);
  }

  const pairs = Object.entries(pairMap);
  if (pairs.length === 1) {
    const [code, name] = pairs[0];
    App.selectedTargetLangCode = code;
    App.selectedTargetLang = name;
    container.querySelector('.btn-toggle').classList.add('active-cat');
    showFilmsForPair(code);
  }

  showScreen('film-screen');
}

function showFilmsForPair(langCode) {
  const cfg     = App.allConfigs;
  const listGroup = document.getElementById('film-list-group');
  const listDiv   = document.getElementById('film-list-buttons');
  const contBtn   = document.getElementById('btn-film-continue');

  listDiv.innerHTML = '';
  App.selectedFilm = null;
  contBtn.disabled = true;

  const films = [];
  for (const [filmKey, filmCfg] of Object.entries(cfg)) {
    if (!filmCfg.models) continue;
    const hasLang = Object.values(filmCfg.models).some(m =>
      (m.target_langs || []).some(tl => tl.lang_code === langCode)
    );
    if (!hasLang) continue;
    films.push({ key: filmKey, cfg: filmCfg });
  }

  for (const { key, cfg: fc } of films) {
    const btn = document.createElement('button');
    btn.className = 'btn btn-secondary film-select-btn';
    btn.dataset.film = key;
    const ytLink = fc.youtube
      ? ` &mdash; <a href="${esc(fc.youtube)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">YouTube</a>`
      : '';
    btn.innerHTML = `<strong>${esc(fc.title_en)}</strong>${ytLink ? ' ' + ytLink : ''}`;
    btn.addEventListener('click', () => {
      listDiv.querySelectorAll('.film-select-btn').forEach(b => b.classList.remove('selected'));
      btn.classList.add('selected');
      App.selectedFilm = key;
      contBtn.disabled = false;
    });
    listDiv.appendChild(btn);
  }

  listGroup.style.display = films.length ? '' : 'none';
}

function prepareLoginForSelectedFilm() {
  const film    = App.selectedFilm;
  const filmCfg = App.allConfigs?.[film];
  const tgtLang = App.selectedTargetLang || 'English';
  const srcLang = filmCfg?.source_lang   || 'Russian';

  // Show returning-user banner only if a session exists for this specific film+lang
  const lastId = localStorage.getItem('subtitle-eval-last-id');
  const existingRaw = lastId && localStorage.getItem(storageKey(lastId, film, App.selectedTargetLangCode));
  if (existingRaw) {
    const stored = JSON.parse(existingRaw);
    const name = (stored.evaluator_meta && stored.evaluator_meta.name) || lastId;
    document.getElementById('login-name-display').textContent = name;
    document.getElementById('login-returning').style.display = '';
    document.getElementById('login-new').style.display = 'none';
  } else {
    document.getElementById('login-returning').style.display = 'none';
    document.getElementById('login-new').style.display = '';
  }

  document.getElementById('original-lang-label').textContent = `Original (${srcLang})`;

  const tgtGroup = document.getElementById('reg-native-tgt-group');
  const tgtField = `native_${tgtLang.toLowerCase()}`;
  tgtGroup.innerHTML = `
    <div class="form-group">
      <label>Native speaker of ${esc(tgtLang)}?</label>
      <div class="btn-group">
        <button class="btn btn-secondary btn-sm btn-choice" id="${tgtField}-yes-btn">Yes</button>
        <button class="btn btn-secondary btn-sm btn-choice" id="${tgtField}-no-btn">No</button>
      </div>
    </div>`;
  document.getElementById(`${tgtField}-yes-btn`).addEventListener('click', () => {
    App.regState[tgtField] = 'yes';
    document.getElementById(`${tgtField}-yes-btn`).classList.add('active');
    document.getElementById(`${tgtField}-no-btn`).classList.remove('active');
  });
  document.getElementById(`${tgtField}-no-btn`).addEventListener('click', () => {
    App.regState[tgtField] = 'no';
    document.getElementById(`${tgtField}-no-btn`).classList.add('active');
    document.getElementById(`${tgtField}-yes-btn`).classList.remove('active');
  });

  const seenDiv = document.getElementById('reg-seen-films');
  seenDiv.innerHTML = `<label>Have you seen this film?</label>
    <div style="margin-bottom:6px;font-size:0.9rem;">${esc(filmCfg?.title_en || film)}
      <span class="btn-group" style="margin-left:8px;">
        <button class="btn btn-secondary btn-sm reg-opt" data-field="seen_${film}" data-val="yes">Yes</button>
        <button class="btn btn-secondary btn-sm reg-opt" data-field="seen_${film}" data-val="no">No</button>
        <button class="btn btn-secondary btn-sm reg-opt" data-field="seen_${film}" data-val="partially">Partially</button>
      </span>
    </div>`;
  seenDiv.querySelectorAll('.reg-opt').forEach(btn => {
    btn.addEventListener('click', () => {
      const field = btn.dataset.field;
      App.regState[field] = btn.dataset.val;
      seenDiv.querySelectorAll(`.reg-opt[data-field="${field}"]`).forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
    });
  });

  App.targetLang = tgtLang;
}

// ════════════════════════════════════════════════════════════════════
//  EVENT WIRING
// ════════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {

  // ── Instructions modal (per-item reference) ────────────────────
  fetch('instructions.html?v=' + Date.now())
    .then(r => r.text())
    .then(html => { document.getElementById('instructions-content').innerHTML = html; })
    .catch(err => { document.getElementById('instructions-content').textContent = 'Failed to load instructions: ' + err; });

  function openModal()  { document.getElementById('instructions-modal').classList.add('open'); }
  function closeModal() { document.getElementById('instructions-modal').classList.remove('open'); }

  document.getElementById('btn-help').addEventListener('click', openModal);
  document.getElementById('btn-modal-close').addEventListener('click', closeModal);
  document.getElementById('btn-modal-ok').addEventListener('click', closeModal);
  document.getElementById('instructions-modal').addEventListener('click', e => {
    if (e.target === e.currentTarget) closeModal();
  });

  // ── Onboarding modal (cover-page, 3-step) ──────────────────────
  const ONBOARDING_STEPS = 3;
  let onboardingStep = 0;
  const onboardingDots = document.querySelectorAll('#onboarding-modal .stepper-dot');

  function updateOnboardingStep() {
    for (let i = 0; i < ONBOARDING_STEPS; i++) {
      document.getElementById(`onboarding-step-${i}`).classList.toggle('active', i === onboardingStep);
      onboardingDots[i].classList.toggle('active', i === onboardingStep);
    }
    document.getElementById('btn-onboarding-back').style.visibility = onboardingStep > 0 ? 'visible' : 'hidden';
    document.getElementById('btn-onboarding-next').textContent = onboardingStep === ONBOARDING_STEPS - 1 ? 'Done' : 'Next';
  }

  function openOnboarding() {
    onboardingStep = 0;
    updateOnboardingStep();
    document.getElementById('onboarding-modal').classList.add('open');
  }
  function closeOnboarding() {
    document.getElementById('onboarding-modal').classList.remove('open');
  }

  document.getElementById('btn-onboarding-close').addEventListener('click', closeOnboarding);
  document.getElementById('onboarding-modal').addEventListener('click', e => {
    if (e.target === e.currentTarget) closeOnboarding();
  });
  document.getElementById('btn-onboarding-back').addEventListener('click', () => {
    if (onboardingStep > 0) { onboardingStep--; updateOnboardingStep(); }
  });
  document.getElementById('btn-onboarding-next').addEventListener('click', () => {
    if (onboardingStep < ONBOARDING_STEPS - 1) {
      onboardingStep++;
      updateOnboardingStep();
    } else {
      closeOnboarding();
      prepareLoginForSelectedFilm();
      showScreen('login-screen');
    }
  });

  // ── Walkthrough screen (post-registration) ──────────────────────
  // Version A: native Russian speaker (assess meaning, humor, voice)
  // Version B: otherwise (assess whether the English makes sense on its own)

  const WT_EXAMPLES = {
    A: [
      {
        ru: '«Свободу Юрию Деточкину!»',
        en: '"Freedom for Yuri Detochkin! Yura!"',
        issues: [],
        note: 'The protest-chant register is fully preserved. "Freedom for…" is idiomatic in English, and "Yura!" is present in the original. Mark this item with <strong>no issues</strong>.'
      },
      {
        ru: '— У кого нога?\n— У того, у кого надо нога.',
        en: '"Whose leg? — The leg! The right person\'s leg!"',
        issues: [{ sev: 'major', cat: 'accuracy' }, { sev: 'minor', cat: 'style' }],
        note: '«У того, у кого надо» means “the right person (has it)” — a deliberate deadpan evasion meaning the detective trusts the injured party. The translation takes it literally, making the exchange nonsensical. Mark this as <strong>major accuracy</strong> (meaning lost) and <strong>minor style</strong> (awkward result).'
      },
      {
        ru: '«Тебя посодют, а ты не воруй!»',
        en: '"You\'ll get locked up—so don\'t steal!"',
        issues: [{ sev: 'major', cat: 'style' }, { sev: 'major', cat: 'accuracy' }],
        note: 'The Russian is a blunt aphoristic verdict: “you should not have stolen — now face the consequences.” The translation turns it into a future warning and scolding imperative, losing both the finality and the comic punch. Mark this as <strong>major style</strong> and <strong>major accuracy</strong>.'
      }
    ],
    B: [
      {
        ru: '«Свободу Юрию Деточкину!»',
        en: '"Freedom for Yuri Detochkin! Yura!"',
        issues: [],
        note: 'This line is shouted in a crowded courtroom by someone supporting the defendant. "Freedom for Yuri Detochkin!" lands clearly as a protest-chant — natural, idiomatic English. Mark this item with <strong>no issues</strong>.'
      },
      {
        ru: '— У кого нога?\n— У того, у кого надо нога.',
        en: '"Whose leg? — The leg! The right person\'s leg!"',
        issues: [{ sev: 'major', cat: 'fluency' }, { sev: 'minor', cat: 'style' }],
        note: 'This exchange takes place at a crime scene. Even in English, "The leg! The right person\'s leg!" is hard to follow — it is unclear what the speaker means or what point is being made. A reader cannot make sense of the response. Mark this as <strong>major fluency</strong> (the line doesn\'t communicate) and <strong>minor style</strong> (awkward phrasing).'
      },
      {
        ru: '«Тебя посодют, а ты не воруй!»',
        en: '"You\'ll get locked up—so don\'t steal!"',
        issues: [{ sev: 'major', cat: 'style' }, { sev: 'major', cat: 'accuracy' }],
        note: 'Dima has just been caught. His father-in-law responds. "You\'ll get locked up—so don\'t steal!" reads as a warning or advice for the future — as if Dima were about to steal rather than already caught. The scene calls for a blunt verdict, not a scolding. Mark this as <strong>major style</strong> (wrong register) and <strong>major accuracy</strong> (wrong meaning in context).'
      }
    ]
  };

  let wtIdx = 0;
  let wtExamples = [];

  function renderWtCard() {
    const ex = wtExamples[wtIdx];
    const issueHTML = ex.issues.length === 0
      ? `<div style="margin-top:10px;font-size:0.85rem;color:var(--muted);">✓ No issues to mark.</div>`
      : '<div style="margin-top:10px;">' +
        ex.issues.map(i =>
          `<span class="sev-${i.sev}" style="margin-right:4px;">${i.sev.toUpperCase()}</span>` +
          `<span style="font-size:0.85rem;color:var(--muted);margin-right:14px;">${i.cat}</span>`
        ).join('') + '</div>';
    document.getElementById('wt-card').innerHTML =
      `<div style="font-size:0.88rem;white-space:pre-line;margin-bottom:6px;">${ex.ru}</div>` +
      `<div style="font-size:0.88rem;color:var(--muted);margin-bottom:10px;">${ex.en}</div>` +
      `<div style="font-size:0.85rem;line-height:1.6;">${ex.note}</div>` +
      issueHTML;
    document.getElementById('wt-counter').textContent = `Item ${wtIdx + 1} of ${wtExamples.length}`;
    const btn = document.getElementById('btn-wt-next');
    btn.textContent = wtIdx === wtExamples.length - 1 ? 'Start evaluation →' : 'Next';
  }

  function showWalkthrough() {
    // Determine source-lang proficiency from registration (first source-lang field found)
    const meta = App.evaluatorMeta || {};
    const srcField = (App.srcLangFields || ['native_russian'])[0];
    const proficiency = meta[srcField] || 'no'; // 'yes' | 'some' | 'no'
    const version = proficiency === 'no' ? 'B' : 'A'; // 'yes' and 'some' both get Version A
    wtExamples = WT_EXAMPLES[version];
    wtIdx = 0;
    const intros = {
      A: 'Before you start, here are three practice items from <em>Beware of the Car</em> (1966). ' +
         'Read each explanation, then proceed — this will help calibrate your judgments.',
      B: 'Before you start, here are three practice items from <em>Beware of the Car</em> (1966). ' +
         "Since you don't read the source language, focus on whether the English is clear, " +
         'natural, and appropriate for the scene. Read each explanation, then proceed.'
    };
    document.getElementById('wt-intro').innerHTML = intros[version];
    renderWtCard();
    showScreen('walkthrough-screen');
  }

  document.getElementById('btn-wt-next').addEventListener('click', () => {
    if (wtIdx < wtExamples.length - 1) {
      wtIdx++;
      renderWtCard();
    } else {
      startOrResume(App.evaluatorId).catch(err => {
        showScreen('login-screen');
        showLoginError(err.message);
      });
    }
  });

  // ── Context toggles ─────────────────────────────────────────────
  document.getElementById('btn-show-context').addEventListener('click', () => {
    const body   = document.getElementById('context-body');
    const btn    = document.getElementById('btn-show-context');
    const isOpen = body.classList.toggle('open');
    btn.textContent = isOpen ? 'Hide context' : 'Show context';
  });

  document.getElementById('btn-show-trans-context').addEventListener('click', () => {
    const body   = document.getElementById('trans-context-body');
    const btn    = document.getElementById('btn-show-trans-context');
    const isOpen = body.classList.toggle('open');
    btn.textContent = isOpen ? 'Hide context' : 'Show context';
  });

  // ── Analysis toggle ─────────────────────────────────────────────
  document.getElementById('btn-show-analysis').addEventListener('click', () => {
    const body   = document.getElementById('analysis-body');
    const btn    = document.getElementById('btn-show-analysis');
    const isOpen = body.classList.toggle('open');
    btn.textContent = isOpen ? 'Hide analysis.' : "Don't remember why this was funny? Show analysis.";
    if (isOpen) App.viewedAnalysis = true;
  });

  // ── Progress slider ─────────────────────────────────────────────
  document.getElementById('progress-slider').addEventListener('input', e => {
    const clamped = Math.min(parseInt(e.target.value), getFrontier());
    e.target.value = clamped;  // snap back if dragged past frontier
    App.sliderPos  = clamped;
    App.lastSaved  = null;
    renderCurrentItem();
  });

  // ── Keyboard shortcuts ──────────────────────────────────────────
  document.addEventListener('keydown', e => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    if (!document.getElementById('eval-screen').classList.contains('active')) return;
    const map = {
      'M': '#sev-group [data-value="major"]',
      'm': '#sev-group [data-value="minor"]',
      'a': '#cat-group [data-value="accuracy"]',
      'f': '#cat-group [data-value="fluency"]',
      's': '#cat-group [data-value="style"]',
      't': '#cat-group [data-value="terminology"]',
      'o': '#cat-group [data-value="other"]',
    };
    if (map[e.key]) { document.querySelector(map[e.key])?.click(); return; }
    if (e.key === '+') { document.getElementById('btn-add-issue').click(); return; }
    if (e.key === 'Enter') { document.getElementById('btn-save').click(); return; }
    if (e.key === '0')     { document.getElementById('btn-no-issues').click(); }
  });

  // ── Login ──────────────────────────────────────────────────────
  const LAST_ID_KEY = 'subtitle-eval-last-id';

  // Load all configs; populate cover language labels and source-lang reg question
  fetchJSON('data/configs-all.json').then(allConfigs => {
    App.allConfigs = allConfigs;
    const srcLangs = [...new Set(
      Object.values(allConfigs).filter(fc => fc.models).map(fc => fc.source_lang).filter(Boolean)
    )];
    const srcLangDisplay = srcLangs.join('/') || 'source language';
    document.querySelectorAll('.onb-src-lang').forEach(el => el.textContent = srcLangDisplay);

    // Build native source-language question(s)
    const srcGroup = document.getElementById('reg-native-src-group');
    srcGroup.innerHTML = srcLangs.map(lang => {
      const f = `native_${lang.toLowerCase()}`;
      return `
        <div class="form-group">
          <label>Native speaker of ${esc(lang)}?</label>
          <div class="btn-group">
            <button class="btn btn-secondary btn-sm btn-choice" id="${f}-yes-btn">Yes</button>
            <button class="btn btn-secondary btn-sm btn-choice" id="${f}-no-btn">No</button>
          </div>
        </div>
        <div class="form-group" id="${f}-secondary" style="display:none;">
          <label>How much ${esc(lang)} do you read?</label>
          <div class="btn-group">
            <button class="btn btn-secondary btn-sm btn-choice" id="${f}-noread-yes">I don't read ${esc(lang)} at all</button>
            <button class="btn btn-secondary btn-sm btn-choice" id="${f}-noread-no">I read some ${esc(lang)}</button>
          </div>
          <p id="${f}-partial-msg" style="display:none;margin-top:8px;font-size:0.88rem;color:var(--accent);">
            You read some ${esc(lang)} but are not a native speaker — great!
          </p>
        </div>`;
    }).join('');

    srcLangs.forEach(lang => {
      const f = `native_${lang.toLowerCase()}`;
      const yesBtn     = document.getElementById(`${f}-yes-btn`);
      const noBtn      = document.getElementById(`${f}-no-btn`);
      const secondary  = document.getElementById(`${f}-secondary`);
      const noreadYes  = document.getElementById(`${f}-noread-yes`);
      const noreadNo   = document.getElementById(`${f}-noread-no`);
      const partialMsg = document.getElementById(`${f}-partial-msg`);

      function setPrimary(btn) {
        [yesBtn, noBtn].forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
      }
      function setSecondary(btn) {
        [noreadYes, noreadNo].forEach(b => b.classList.remove('active'));
        if (btn) btn.classList.add('active');
      }

      yesBtn.addEventListener('click', () => {
        setPrimary(yesBtn);
        App.regState[f] = 'yes';
        secondary.style.display = 'none';
        setSecondary(null);
        partialMsg.style.display = 'none';
      });
      noBtn.addEventListener('click', () => {
        setPrimary(noBtn);
        delete App.regState[f];
        secondary.style.display = '';
      });
      noreadYes.addEventListener('click', () => {
        setSecondary(noreadYes);
        App.regState[f] = 'no';
        partialMsg.style.display = 'none';
      });
      noreadNo.addEventListener('click', () => {
        setSecondary(noreadNo);
        App.regState[f] = 'some';
        partialMsg.style.display = '';
      });
    });

    App.srcLangFields = srcLangs.map(lang => `native_${lang.toLowerCase()}`);
  }).catch(e => console.error('Could not load config: ' + e.message));

  document.getElementById('btn-cover-continue').addEventListener('click', () => {
    showFilmSelectionScreen();
  });

  document.getElementById('btn-film-continue').addEventListener('click', () => {
    const tgtLang = App.selectedTargetLang || 'English';
    document.querySelectorAll('.onb-tgt-lang').forEach(el => el.textContent = tgtLang);
    openOnboarding();
  });

  document.getElementById('btn-resume').addEventListener('click', () => {
    const lastId = localStorage.getItem(LAST_ID_KEY);
    App.evaluatorId = lastId;
    startOrResume(lastId).catch(err => { showScreen('film-screen'); showLoginError(err.message); });
  });

  document.getElementById('btn-new-user').addEventListener('click', () => {
    document.getElementById('login-returning').style.display = 'none';
    document.getElementById('login-new').style.display = '';
  });

  // Static reg-opt buttons (age, gender, professional — wired once at startup)
  document.querySelectorAll('.reg-opt').forEach(btn => {
    btn.addEventListener('click', () => {
      const field = btn.dataset.field;
      App.regState[field] = btn.dataset.val;
      document.querySelectorAll(`.reg-opt[data-field="${field}"]`).forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
    });
  });

  function doStart() {
    const name = document.getElementById('reg-name').value.trim();
    if (!name) { showLoginError('Please enter your name or initials.'); return; }
    const srcFields = App.srcLangFields || ['native_russian'];
    const nativeTgtField = 'native_' + (App.targetLang || 'English').toLowerCase();
    const required = ['age', 'gender', ...srcFields, nativeTgtField, 'professional'];
    for (const f of required) {
      if (!App.regState[f]) { showLoginError('Please answer all questions.'); return; }
    }
    if (App.selectedFilm && !App.regState[`seen_${App.selectedFilm}`]) {
      showLoginError('Please answer all questions.'); return;
    }
    document.getElementById('login-error').style.display = 'none';
    const safeName = name.toLowerCase().replace(/[^a-z0-9]/g, '').slice(0, 12) || 'user';
    const suffix   = Math.floor(Math.random() * 0x10000).toString(16).padStart(4, '0');
    const id       = `${safeName}-${suffix}`;
    localStorage.setItem(LAST_ID_KEY, id);
    App.evaluatorId = id;
    App.evaluatorMeta = { name, ...App.regState };
    showWalkthrough();
  }

  document.getElementById('btn-next-demographics').addEventListener('click', doStart);
  document.getElementById('reg-name').addEventListener('keydown', e => { if (e.key === 'Enter') doStart(); });

  // ── Eval: add issue ────────────────────────────────────────────
  ['sev-group', 're-sev-group'].forEach(groupId => {
    document.querySelectorAll(`#${groupId} .btn-toggle`).forEach(btn => {
      btn.addEventListener('click', () => {
        clearGroup(groupId);
        btn.classList.add(btn.dataset.value === 'major' ? 'active-major' : 'active-minor');
      });
    });
  });
  wireToggleGroup('cat-group', 'active-cat');
  wireToggleGroup('re-cat-group', 'active-cat');

  document.getElementById('btn-add-issue').addEventListener('click', () =>
    addIssueFromForm('sev-group', 'cat-group', 'just-input',
      App.currentIssues, renderCurrentIssueList));

  document.getElementById('just-input').addEventListener('keydown', e => {
    if (e.key === '+') { e.preventDefault(); document.getElementById('btn-add-issue').click(); }
  });

  // ── Eval: no issues ────────────────────────────────────────────
  document.getElementById('btn-no-issues').addEventListener('click', () => {
    App.currentIssues = [];
    saveJudgment([]);
  });

  // ── Eval: save & next ──────────────────────────────────────────
  document.getElementById('btn-save').addEventListener('click', () => {
    // auto-commit any partially-filled issue form
    const sev = getGroupValue('sev-group');
    const cat = getGroupValue('cat-group');
    if (sev && cat) {
      const just = document.getElementById('just-input').value.trim();
      App.currentIssues.push({ severity: sev, category: cat, span: '', justification: just });
      clearGroup('sev-group');
      clearGroup('cat-group');
      document.getElementById('just-input').value = '';
    }
    saveJudgment(App.currentIssues.slice());
  });

  // ── Eval: skip ─────────────────────────────────────────────────
  document.getElementById('btn-skip').addEventListener('click', () => {
    const { taskIdx } = App.navSequence[App.sliderPos - 1];
    if (App.session.judgments[String(taskIdx)]) return; // already judged, can't skip
    const skippedSet = new Set(App.session.skipped);
    skippedSet.add(taskIdx);
    App.session.skipped = [...skippedSet].sort((a, b) => a - b);
    saveSession();
    App.navSequence = App.navSequence.filter(n => n.taskIdx !== taskIdx);
    App.totalTasks  = App.navSequence.length;
    App.lastSaved   = null;
    if (App.sliderPos > App.navSequence.length) App.sliderPos = App.navSequence.length;
    if (App.navSequence.length === 0 || getFrontier() > App.navSequence.length) {
      startReview(); return;
    }
    renderCurrentItem();
  });

  // ── Eval: back ─────────────────────────────────────────────────
  document.getElementById('btn-back').addEventListener('click', () => {
    if (App.sliderPos <= 1) return;
    App.sliderPos--;
    App.lastSaved = null;
    renderCurrentItem();
  });

  // ── Review: re-evaluate add issue ──────────────────────────────
  document.getElementById('btn-re-add').addEventListener('click', () =>
    addIssueFromForm('re-sev-group', 're-cat-group', 're-just-input',
      App.reEvalIssues, renderReEvalIssueList));

  document.getElementById('re-just-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') document.getElementById('btn-re-add').click();
  });

  document.getElementById('btn-re-no-issues').addEventListener('click', () => {
    App.reEvalIssues = [];
    resolveIncon([]);
    document.getElementById('re-eval-panel').style.display = 'none';
  });

  document.getElementById('btn-re-save').addEventListener('click', () => {
    resolveIncon(App.reEvalIssues.slice());
    document.getElementById('re-eval-panel').style.display = 'none';
  });

  // ── Review: navigation ─────────────────────────────────────────
  document.getElementById('btn-review-prev').addEventListener('click', () => {
    if (App.inconPos > 0) { App.inconPos--; renderIncon(); }
  });

  document.getElementById('btn-review-next').addEventListener('click', () => {
    App.inconPos++;
    renderIncon();
  });

  // ── Complete: download ─────────────────────────────────────────
  document.getElementById('btn-download').addEventListener('click', downloadSession);
});
