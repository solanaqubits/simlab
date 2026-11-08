import {FLAGS, ROLES, STATES, requireThat, falseAssurances, rejectPromotions, strictJSON, bytes, decode, sha, b64, unb64, span, selectionSpan, readyReasons, renderStatuses} from './core.js';

const $ = id => document.getElementById(id);
const copy = x => structuredClone(x);
let token = '', contextId = '', context = null, ledger = null, source = '', sourceBytes = null;
let record = null, recordBytes = null, generation = 0, saved = null, currentJob = null;
let matched = false, fatal = false, busy = false, selection = null, lastRequest = 0;
let requestQueue = Promise.resolve();
const history = [], identities = new Map(), boundDrafts = new Map();
const signature = a => JSON.stringify([a.text_raw, a.text_sha256, a.quote_span?.start_char, a.quote_span?.end_char, a.quote_span?.quote]);
function node(tag, text, cls) { const el = document.createElement(tag); if (text !== undefined) el.textContent = text; if (cls) el.className = cls; return el; }
function say(text, error = false) { $('message').textContent = text; $('message').className = error ? 'error' : ''; }
function fail(error) {
  const code = error.message || 'local_error';
  if (/assurance|binding_mismatch|source_dom_changed|invalid_validator|invalid_response|artifact_integrity/.test(code)) { fatal = true; token = ''; }
  say(code, true); controls();
}
function on(el, event, fn) { el.addEventListener(event, e => Promise.resolve().then(() => fn(e)).catch(fail)); }
async function boundedResponse(response) {
  const reader = response.body.getReader(); const chunks = []; let size = 0;
  for (;;) { const {done, value} = await reader.read(); if (done) break; size += value.length; if (size > 2097152) { await reader.cancel(); throw new Error('invalid_response_size'); } chunks.push(value); }
  const raw = new Uint8Array(size); let offset = 0; for (const part of chunks) { raw.set(part, offset); offset += part.length; } return raw;
}
function api(operation, fields = {}) {
  const request = {schema: 'claim-review-api-request-1', operation, request_id: crypto.randomUUID(), context_id: contextId, ...fields};
  const run = async () => {
    requireThat(token && !fatal, 'session_not_connected');
    await new Promise(resolve => setTimeout(resolve, Math.max(0, lastRequest + 150 - performance.now()))); lastRequest = performance.now();
    const response = await fetch('/v1/' + operation, {method: 'POST', headers: {'Content-Type': 'application/json', Authorization: 'Bearer ' + token}, body: JSON.stringify(request), credentials: 'omit', cache: 'no-store', redirect: 'error'});
    requireThat(response.headers.get('Cache-Control') === 'no-store' && response.headers.get('Content-Type')?.startsWith('application/json'), 'invalid_response_headers');
    const body = strictJSON(decode(await boundedResponse(response)));
    falseAssurances(body.assurances); rejectPromotions(body);
    requireThat(body.schema === 'claim-review-api-response-1', 'invalid_response_schema');
    if (!body.ok) {
      requireThat(body.error && typeof body.error.code === 'string', 'invalid_response_error');
      throw new Error(body.error.code);
    }
    requireThat(response.ok && ['operation','request_id','context_id'].every(k => body[k] === request[k]), 'response_binding_mismatch');
    return body.data;
  };
  const result = requestQueue.then(run); requestQueue = result.catch(() => {}); return result;
}
async function artifact(ref) {
  requireThat(ref && Number.isSafeInteger(ref.size_bytes) && ref.size_bytes >= 0 && ref.size_bytes <= 16777216, 'artifact_integrity_failure');
  const out = new Uint8Array(ref.size_bytes); let offset = 0;
  do {
    const part = await api('artifacts/read', {artifact_id: ref.artifact_id, artifact_sha256: ref.sha256, offset, max_bytes: 65536});
    const raw = unb64(part.chunk_base64);
    requireThat(part.artifact_id === ref.artifact_id && part.artifact_sha256 === ref.sha256 && part.total_size_bytes === out.length && part.offset === offset && part.returned_bytes === raw.length && offset + raw.length <= out.length, 'artifact_integrity_failure');
    out.set(raw, offset); offset += raw.length;
    requireThat(part.eof === (offset === out.length) && (raw.length > 0 || part.eof), 'artifact_integrity_failure');
  } while (offset < out.length);
  requireThat(await sha(out) === ref.sha256, 'artifact_integrity_failure'); return out;
}
function paintAnchors() {
  $('anchors').replaceChildren(); matched = true;
  for (const [key, row] of Object.entries(context.anchors)) {
    const ok = row.state === 'matched' && row.expected_sha256 === row.observed_sha256;
    matched &&= ok;
    const div = node('div', undefined, 'anchor' + (ok ? '' : ' bad'));
    div.append(node('strong', key + ' · ' + row.state));
    const hashes = node('div'); hashes.append(node('code', 'expected: ' + row.expected_sha256), node('br'), node('code', 'observed: ' + (row.observed_sha256 || 'unavailable'))); div.append(hashes); $('anchors').append(div);
  }
}
async function refresh() {
  const value = await api('context');
  if (context) requireThat(value.context_fingerprint === context.context_fingerprint, 'context_binding_mismatch');
  context = value; paintAnchors(); controls(); return matched;
}
function controls() {
  const loaded = !!record && !!context && !fatal;
  $('save').disabled = !loaded || busy || pending;
  $('check').disabled = !loaded || busy || !saved || saved.generation !== generation || !matched || pending;
  // Adapter remains authoritative. A needs_context record can be submitted to see its precise refusal.
  $('build').disabled = !loaded || busy || !saved || saved.generation !== generation || !matched || pending;
  $('add-atom').disabled = !loaded || busy || !selection;
  $('download-record').disabled = !record || fatal;
  $('editorial').disabled = !loaded;
  if (record) {
    const reasons = readyReasons(record, ledger, matched);
    $('editorial').querySelector('[value="ready_for_transport"]').disabled = fatal || reasons.length > 0;
    $('gate').textContent = reasons.length ? 'Переход в ready_for_transport закрыт: ' + reasons.join(', ') + '. Сборка повторно проверит допуск.' : 'Редакторские вопросы закрыты. Окончательный допуск проверяет адаптер.';
  }
  renderStatuses($('statuses'), record, currentJob, fatal ? 'contract_error' : currentJob ? (currentJob.ui_generation === generation ? 'current' : 'stale') : 'not_run');
}
function changed(reason) {
  $('artifacts').replaceChildren();
  generation++; recordBytes = bytes(JSON.stringify(record, null, 2) + '\n');
  history.push({event: reason, generation}); paintHistory(); controls();
  $('record-meta').textContent = `${record.extraction_id || 'draft'} · редакция ${record.revision ?? '?'} · локальная версия ${generation} · требуется сохранение`;
}
function field(label, value, handler, options) {
  const labelNode = node('label', label), input = document.createElement(options ? 'select' : 'input');
  if (options) for (const option of options) input.append(new Option(option, option));
  input.value = value ?? ''; if (!options) input.autocomplete = 'off';
  on(input, options ? 'change' : 'input', () => handler(input.value)); labelNode.append(input); return labelNode;
}
function showSpan(quote) {
  const q = span(source, quote.start_char, quote.end_char); const cp = Array.from(source);
  $('source').replaceChildren(document.createTextNode(cp.slice(0, q.start_char).join('')), node('mark', q.quote), document.createTextNode(cp.slice(q.end_char).join('')));
}
function paintAtoms() {
  $('atoms').replaceChildren();
  for (const role of ROLES) for (const [index, atom] of (record.contract?.[role] || []).entries()) {
    const card = node('div', undefined, 'atom'); const head = node('div', undefined, 'atom-head');
    const show = node('button', 'Показать цитату'); on(show, 'click', () => showSpan(atom.quote_span));
    head.append(node('span', atom.atom_id, 'atom-id'), show); card.append(head);
    card.append(field('Роль', role, value => { requireThat(!pending, 'apply_pending_edits_first'); record.contract[role].splice(index, 1); record.contract[value].push(atom); changed('atom_role_changed'); paintAtoms(); }, ROLES));
    const text = document.createElement('textarea'); text.value = atom.text_raw; text.readOnly = true; text.setAttribute('aria-label', 'Буквальный текст атома'); card.append(text);
    const bounds = node('div', undefined, 'bounds'); const editKey = role + ':' + atom.atom_id; let {start, end} = boundDrafts.get(editKey) || {start: atom.quote_span.start_char, end: atom.quote_span.end_char};
    bounds.append(field('start_char', start, value => { start = Number(value); boundDrafts.set(editKey, {start, end}); invalidatePending(editKey); }), field('end_char', end, value => { end = Number(value); boundDrafts.set(editKey, {start, end}); invalidatePending(editKey); }));
    const apply = node('button', 'Новый диапазон');
    on(apply, 'click', async () => {
      const q = span(source, start, end), version = generation, hash = await sha(bytes(q.quote));
      requireThat(version === generation, 'draft_changed_retry');
      boundDrafts.delete(editKey); pendingFields.delete(editKey); pending = pendingFields.size > 0;
      if (q.start_char === atom.quote_span.start_char && q.end_char === atom.quote_span.end_char && q.quote === atom.text_raw) { controls(); return; }
      atom.atom_id = 'atom-' + crypto.randomUUID(); atom.text_raw = q.quote; atom.text_sha256 = hash; atom.quote_span = q;
      identities.set(atom.atom_id, signature(atom)); changed('atom_rebound_new_id'); paintAtoms(); say('Новый atom_id создан. Связи покрытия требуют отдельного редакторского пересмотра.');
    }); bounds.append(apply); card.append(bounds, node('div', atom.text_sha256, 'hash'));
    const remove = node('button', 'Удалить из роли'); on(remove, 'click', () => { requireThat(!pending, 'apply_pending_edits_first'); record.contract[role].splice(index, 1); changed('atom_removed'); paintAtoms(); }); card.append(remove); $('atoms').append(card);
  }
}
// Even unapplied edits invalidate reports. Save/check wait for a deliberate apply or reload.
let pending = false; const pendingFields = new Set();
function invalidatePending(key) { pendingFields.add(key); pending = true; generation++; controls(); $('save').disabled = true; $('check').disabled = true; $('build').disabled = true; say('Есть незавершённое редактирование. Примените поля или загрузите запись заново.'); }
function paintCoverage() {
  $('coverage').replaceChildren();
  for (const row of record.coverage_checks || []) {
    const div = node('div', undefined, 'coverage-row'); div.append(node('strong', row.check_id + ' · ' + row.expected_condition_editorial_text, 'wide'));
    const expected = ledger.coverage_checks?.find(x => x.check_id === row.check_id);
    div.append(node('span', 'Ведомость: ' + (expected?.source_observation || 'нет строки'), 'wide'));
    div.append(field('Наблюдение источника', row.source_observation, value => { row.source_observation = value; changed('coverage_observation'); }, ['condition_present','condition_absent','condition_not_inspected']));
    div.append(field('Finding (отдельно)', row.finding || '', value => { row.finding = value || null; changed('coverage_finding'); paintCoverage(); }, ['','missing_extracted_atom']));
    div.append(field('ID извлечённых атомов (через запятую)', (row.extracted_atom_ids || []).join(','), value => { row.extracted_atom_ids = value.split(',').map(x => x.trim()).filter(Boolean); changed('coverage_ids'); }));
    if (row.finding) div.append(node('div', row.finding, 'finding'));
    $('coverage').append(div);
  }
}
function paintQuantities() {
  $('quantities').replaceChildren();
  for (const quantity of record.contract?.quantities || []) {
    const div = node('div', undefined, 'quantity'); div.append(node('strong', quantity.quantity_id));
    for (const key of ['exact_literal','unit_raw','unit_interpretation','unit_canonical','unit_mapping_basis']) {
      div.append(field(key, quantity[key], value => { quantity[key] = value === '' && key !== 'exact_literal' && key !== 'unit_interpretation' ? null : value; changed('quantity_' + key); }));
    }
    div.append(node('code', 'literal_span: ' + JSON.stringify(quantity.literal_span)));
    $('quantities').append(div);
  }
}
function paintEditors() {
  $('editors').replaceChildren();
  const specs = [
    ['scope', () => record.contract.scope, v => { record.contract.scope = v; }],
    ['quantities / literal_span', () => record.contract.quantities, v => { record.contract.quantities = v; }],
    ['coverage_checks / диапазоны', () => record.coverage_checks, v => { record.coverage_checks = v; }],
    ['unresolved_questions', () => record.unresolved_questions, v => { record.unresolved_questions = v; }],
    ['checklist (10 пунктов)', () => record.checklist, v => { record.checklist = v; }],
    ['review', () => record.review, v => { record.review = v; }],
    ['non_claims', () => record.contract.non_claims, v => { record.contract.non_claims = v; }],
    ['open_obligations', () => record.contract.open_obligations, v => { record.contract.open_obligations = v; }]
  ];
  for (const [name, get, set] of specs) {
    const div = node('div'), label = node('label', name + ' · JSON'), area = document.createElement('textarea');
    let baseline = JSON.stringify(get());
    area.value = JSON.stringify(get(), null, 2); area.dataset.editor = name; label.append(area); div.append(label);
    on(area, 'input', () => invalidatePending(name));
    const apply = node('button', 'Применить ' + name);
    on(apply, 'click', () => {
      requireThat(JSON.stringify(get()) === baseline, 'section_changed_reload_editor');
      const value = strictJSON(area.value); rejectPromotions(value);
      requireThat(Array.isArray(get()) ? Array.isArray(value) : typeof value === typeof get() && value !== null, 'section_shape_required');
      if (['quantities / literal_span','coverage_checks / диапазоны','unresolved_questions','checklist (10 пунктов)'].includes(name)) requireThat(value.every(x => x && typeof x === 'object' && !Array.isArray(x)), 'section_rows_required');
      if (name === 'coverage_checks / диапазоны') requireThat(value.every(x => Array.isArray(x.extracted_atom_ids)), 'coverage_ids_required');
      set(value); baseline = JSON.stringify(value); pendingFields.delete(name); pending = pendingFields.size > 0;
      changed('edit_' + name); paintCoverage(); paintQuantities();
    });
    const reload = node('button', 'Перечитать поле');
    on(reload, 'click', () => { baseline = JSON.stringify(get()); area.value = JSON.stringify(get(), null, 2); pendingFields.delete(name); pending = pendingFields.size > 0; controls(); });
    div.append(apply, reload); $('editors').append(div);
  }
}
function paintHistory() {
  $('history').replaceChildren();
  for (const entry of history.slice().reverse()) {
    const d = node('details'); const historic = entry.job && entry.generation !== generation;
    d.append(node('summary', `${entry.event} · версия ${entry.generation}${historic ? ' · historical' : ''}`), node('pre', JSON.stringify(entry, null, 2))); $('history').append(d);
  }
}
function paint() { if (!record) return; $('editorial').value = record.editorial_state; paintAtoms(); paintCoverage(); paintQuantities(); paintEditors(); paintHistory(); controls(); }
function download(raw, name) { const url = URL.createObjectURL(new Blob([raw], {type: 'application/json'})); const a = node('a'); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }

on($('connect'), 'click', async () => {
  requireThat(!context, 'reload_to_change_context');
  const input = $('token').value; $('token').value = '';
  requireThat(/^[A-Za-z0-9_-]{43}$/.test(input), 'invalid_token');
  contextId = $('context-id').value.trim(); requireThat(/^[0-9a-f-]{36}$/.test(contextId), 'invalid_context_id'); token = input;
  try {
    await refresh();
    sourceBytes = await artifact(context.source_snapshot); source = decode(sourceBytes);
    ledger = strictJSON(decode(await artifact(context.expectations))); rejectPromotions(ledger);
    const manifest = strictJSON(decode(await artifact(context.claim_map_manifest)));
    requireThat(await sha(sourceBytes) === context.anchors.source.expected_sha256, 'source_binding_mismatch');
    for (const role of ROLES) for (const atom of ledger.contract[role]) identities.set(atom.atom_id, signature(atom));
    $('source').textContent = source; $('ledger').textContent = JSON.stringify(ledger, null, 2); $('manifest').textContent = JSON.stringify(manifest, null, 2);
    $('workspace').hidden = false; $('login').hidden = true; say('Контекст закреплён. Загрузите редакторскую запись.'); controls();
  } catch (error) { token = ''; context = null; throw error; }
});
on($('refresh'), 'click', async () => { await refresh(); say(matched ? 'Все внешние якоря совпадают.' : 'anchor_mismatch: сборка заблокирована.', !matched); });
on($('record-file'), 'change', async e => {
  const file = e.target.files[0]; requireThat(file && file.size <= 1048576, 'record_size_limit');
  const raw = new Uint8Array(await file.arrayBuffer()), value = strictJSON(decode(raw));
  requireThat(value && typeof value === 'object' && !Array.isArray(value), 'invalid_record'); falseAssurances(value.assurances); rejectPromotions(value);
  requireThat(value.contract && ROLES.every(role => Array.isArray(value.contract[role])), 'record_roles_required');
  let rebound = false;
  for (const role of ROLES) for (const atom of value.contract[role]) {
    if (identities.has(atom.atom_id) && identities.get(atom.atom_id) !== signature(atom)) { atom.atom_id = 'atom-' + crypto.randomUUID(); rebound = true; }
    identities.set(atom.atom_id, signature(atom));
  }
  record = value; saved = null; boundDrafts.clear(); pendingFields.clear(); pending = false; changed('record_imported'); if (!rebound) recordBytes = raw;
  paint(); say(rebound ? 'Изменённые атомы получили новые ID. Проверьте ссылки покрытия.' : 'Запись загружена. Логический статус не повышен.');
});
on($('editorial'), 'change', () => {
  const value = $('editorial').value;
  if (value === 'ready_for_transport') { const reasons = readyReasons(record, ledger, matched); requireThat(!reasons.length, reasons.join(', ')); }
  record.editorial_state = value; changed('editorial_state_changed'); controls();
});
on(document, 'selectionchange', () => {
  try { selection = selectionSpan($('source'), source); $('selection').textContent = `[${selection.start_char}, ${selection.end_char}) · ${selection.quote}`; }
  catch (error) {
    const selected = window.getSelection();
    if (selected?.anchorNode && $('source').contains(selected.anchorNode)) { selection = null; if (error.message === 'surrogate_boundary_rejected') say(error.message, true); }
  }
  controls();
});
on($('add-atom'), 'click', async () => {
  const q = selection; const role = $('new-role').value, version = generation;
  requireThat(q && ROLES.includes(role), 'select_source_and_explicit_role');
  const hash = await sha(bytes(q.quote)); requireThat(version === generation, 'draft_changed_retry');
  const atom = {atom_id: 'atom-' + crypto.randomUUID(), text_raw: q.quote, text_sha256: hash, quote_span: q};
  record.contract[role].push(atom); identities.set(atom.atom_id, signature(atom)); changed('atom_added'); paintAtoms();
});
on($('save'), 'click', async () => {
  requireThat(record && !pending && !fatal, 'apply_pending_edits_first');
  busy = true; controls(); const version = generation, raw = recordBytes;
  try {
    const hash = await sha(raw), parent = saved?.draft_id || null;
    const result = await api('drafts', {parent_draft_id: parent, record_sha256: hash, record_base64: b64(raw)});
    requireThat(result.draft_sha256 === hash && result.size_bytes === raw.length, 'draft_binding_mismatch');
    const binding = {...result, generation: version}; if (version === generation) saved = binding;
    history.push({event: 'draft_saved', generation: version, ...result}); paintHistory(); say('Черновик сохранён: ' + result.draft_id);
    if (version === generation) $('record-meta').textContent = `${record.extraction_id} · ${result.draft_id} · SHA-256 ${hash}`;
  } finally { busy = false; controls(); }
});
async function runJob(operation) {
  requireThat(saved && saved.generation === generation && !pending, 'save_current_draft_first');
  busy = true; controls(); const binding = {...saved}, version = generation, snapshot = copy(record);
  try {
    requireThat(await refresh(), 'anchor_mismatch');
    const accepted = await api(operation, {draft_id: binding.draft_id, draft_sha256: binding.draft_sha256, context_fingerprint: context.context_fingerprint});
    const deadline = performance.now() + 200000; let job;
    for (;;) {
      requireThat(performance.now() < deadline, 'job_poll_timeout');
      await new Promise(resolve => setTimeout(resolve, 500)); job = await api('jobs/status', {job_id: accepted.job_id});
      requireThat(job.job_id === accepted.job_id && job.draft_id === binding.draft_id && job.draft_sha256 === binding.draft_sha256 && job.context_fingerprint === context.context_fingerprint, 'job_binding_mismatch');
      requireThat(['queued','running','completed','failed'].includes(job.state), 'invalid_response_job_state');
      if (job.state === 'completed' || job.state === 'failed') break;
      say('Задача ' + job.state + ' · ' + job.job_id);
    }
    const detail = [];
    for (const summary of job.reports) {
      const result = strictJSON(decode(await artifact(summary.artifact))); falseAssurances(result); rejectPromotions(result);
      requireThat(result.status === summary.status && STATES[summary.validator]?.includes(summary.status), 'invalid_validator_status');
      if (result.record_sha256) requireThat(result.record_sha256 === binding.draft_sha256, 'report_binding_mismatch');
      detail.push(result);
    }
    const completed = {...job, ui_generation: version};
    // Validate all enums even for a historical response; never make it current after an edit.
    renderStatuses(document.createElement('div'), snapshot, completed, 'historical');
    history.push({event: operation, generation: version, job, reports: detail});
    if (version === generation) currentJob = completed;
    paintHistory(); controls();
    $('artifacts').replaceChildren();
    if (job.package_available && version === generation) {
      // This server registers the package manifest last; verify it before naming downloads.
      const manifestRef = job.artifacts.at(-1), manifest = strictJSON(decode(await artifact(manifestRef)));
      falseAssurances(manifest); rejectPromotions(manifest);
      requireThat(manifest.schema === 'geek-work-claim-adapter-package-1' && manifest.status === 'built' && manifest.files && typeof manifest.files === 'object', 'invalid_response_package_manifest');
      for (const [name, hash] of Object.entries(manifest.files)) requireThat(/^[a-z0-9][a-z0-9.-]{0,100}$/.test(name) && job.artifacts.some(r => r.sha256 === hash), 'artifact_integrity_failure');
      if (version === generation) for (const ref of job.artifacts) {
        const names = ref.artifact_id === manifestRef.artifact_id ? ['manifest.json'] : Object.keys(manifest.files).filter(name => manifest.files[name] === ref.sha256);
        requireThat(names.length > 0, 'artifact_integrity_failure');
        for (const name of names) {
          const button = node('button', 'Скачать ' + name);
          on(button, 'click', async () => download(await artifact(ref), name)); $('artifacts').append(button);
        }
      }
    }
    const reasons = detail.map(x => x.reason).filter(Boolean);
    say(version !== generation ? 'historical: результат сохранён для прежней версии.' : `${job.state}: ${job.reports.map(x => x.validator + '=' + x.status).join(' · ')}${reasons.length ? ' · ' + reasons.join(' · ') : ''}${job.failure ? ' · ' + job.failure.code : ''}`, !!job.failure || reasons.length > 0);
  } finally { busy = false; controls(); }
}
on($('check'), 'click', () => runJob('checks'));
on($('build'), 'click', () => runJob('builds'));
on($('download-record'), 'click', () => { requireThat(!pending, 'apply_pending_edits_first'); download(recordBytes, 'claim-extraction-record.json'); });
on($('download-history'), 'click', () => download(bytes(JSON.stringify({schema: 'claim-review-editor-journal-1', context_fingerprint: context?.context_fingerprint || null, entries: history, ...Object.fromEntries(FLAGS.map(f => [f, false]))}, null, 2) + '\n'), 'claim-review-journal-' + crypto.randomUUID() + '.json'));
for (const flag of FLAGS) { const item = node('code', flag + ' = false'); item.dataset.assurance = flag; $('assurances').append(item); }
controls();
