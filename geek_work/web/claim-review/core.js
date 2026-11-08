// Pure contract and Unicode helpers, also exercised inside the real browser.
export const FLAGS = ['semantic_equivalence_verified', 'source_extraction_complete', 'kernel_replayed', 'publication_authorized'];
export const ROLES = ['premise_atoms', 'conclusion_atoms', 'domain_atoms', 'quantifier_atoms', 'negation_atoms'];
export const STATES = {
  extraction: ['record_consistent', 'needs_context', 'review_required', 'invalid_input'],
  evidence: ['source_only', 'hypothesis', 'formal_reported', 'empirical_reported', 'reference_only', 'open'],
  adapter: ['built', 'build_blocked', 'invalid_input'],
  transport: ['contract_preserved', 'review_required', 'invalid_input']
};
export function requireThat(ok, code) { if (!ok) throw new Error(code); }
export function falseAssurances(value) {
  requireThat(value && FLAGS.every(k => value[k] === false), 'assurance_contract_violation');
}
export function rejectPromotions(value) {
  if (!value || typeof value !== 'object') return;
  for (const [k, v] of Object.entries(value)) {
    if (FLAGS.includes(k)) requireThat(v === false, 'assurance_contract_violation');
    rejectPromotions(v);
  }
}
export function strictJSON(text) {
  requireThat(text.length <= 2097152 && !text.startsWith('\uFEFF'), 'invalid_json_size_or_bom');
  let i = 0;
  const ws = () => { while (/[ \r\n\t]/.test(text[i] || '\0')) i++; };
  function string() {
    const start = i++;
    while (i < text.length) {
      const c = text[i++];
      if (c === '\\') { i++; continue; }
      if (c === '"') {
        const s = JSON.parse(text.slice(start, i));
        for (const ch of s) { const n = ch.codePointAt(0); requireThat(n < 0xd800 || n > 0xdfff, 'unpaired_surrogate'); }
        return s;
      }
    }
    throw new Error('invalid_json');
  }
  function value(depth) {
    requireThat(depth <= 32, 'json_depth_limit'); ws();
    const c = text[i];
    if (c === '"') return string();
    if (c === '{' || c === '[') {
      i++; ws(); const object = c === '{', end = object ? '}' : ']';
      const out = object ? Object.create(null) : [];
      if (text[i] === end) { i++; return out; }
      for (;;) {
        if (object) {
          requireThat(text[i] === '"', 'invalid_json'); const key = string(); ws();
          requireThat(text[i++] === ':' && !Object.hasOwn(out, key), 'duplicate_key_or_invalid_json');
          out[key] = value(depth + 1);
        } else out.push(value(depth + 1));
        ws(); const token = text[i++]; if (token === end) return out;
        requireThat(token === ',', 'invalid_json'); ws();
      }
    }
    for (const [word, result] of [['true', true], ['false', false], ['null', null]]) {
      if (text.slice(i, i + word.length) === word) { i += word.length; return result; }
    }
    const match = text.slice(i).match(/^-?(0|[1-9][0-9]*)/);
    requireThat(match, 'invalid_json_number'); i += match[0].length;
    const n = Number(match[0]); requireThat(Number.isSafeInteger(n), 'unsafe_integer_not_supported_in_ui');
    return n;
  }
  const result = value(0); ws(); requireThat(i === text.length, 'invalid_json_trailing_or_float'); return result;
}
export const bytes = text => new TextEncoder().encode(text);
export const decode = raw => new TextDecoder('utf-8', {fatal: true, ignoreBOM: true}).decode(raw);
export async function sha(raw) { return [...new Uint8Array(await crypto.subtle.digest('SHA-256', raw))].map(x => x.toString(16).padStart(2, '0')).join(''); }
export function b64(raw) { let s = ''; for (const x of raw) s += String.fromCharCode(x); return btoa(s); }
export function unb64(s) { return Uint8Array.from(atob(s), c => c.charCodeAt(0)); }
export function cpOffset(text, offset) {
  requireThat(Number.isInteger(offset) && offset >= 0 && offset <= text.length, 'invalid_utf16_offset');
  if (offset > 0 && offset < text.length) {
    const a = text.charCodeAt(offset - 1), b = text.charCodeAt(offset);
    requireThat(!(a >= 0xd800 && a <= 0xdbff && b >= 0xdc00 && b <= 0xdfff), 'surrogate_boundary_rejected');
  }
  return Array.from(text.slice(0, offset)).length;
}
export function span(text, start, end) {
  const cp = Array.from(text);
  requireThat(Number.isInteger(start) && Number.isInteger(end) && 0 <= start && start < end && end <= cp.length, 'invalid_codepoint_span');
  return {start_char: start, end_char: end, quote: cp.slice(start, end).join('')};
}
function domOffset(root, node, offset) {
  requireThat(root === node || root.contains(node), 'selection_outside_source');
  let count = 0, found = false;
  function visit(current) {
    if (found) return;
    if (current === node) {
      if (node.nodeType === Node.TEXT_NODE) { cpOffset(node.data, offset); count += offset; }
      else { requireThat(offset >= 0 && offset <= node.childNodes.length, 'invalid_dom_offset'); for (let j = 0; j < offset; j++) count += node.childNodes[j].textContent.length; }
      found = true; return;
    }
    if (current.nodeType === Node.TEXT_NODE) count += current.data.length;
    else for (const child of current.childNodes) visit(child);
  }
  visit(root); requireThat(found, 'selection_outside_source'); return count;
}
export function selectionSpan(root, text, selection = window.getSelection()) {
  requireThat(selection && selection.rangeCount === 1 && !selection.isCollapsed, 'select_source_text');
  requireThat(root.textContent === text, 'source_dom_changed');
  const r = selection.getRangeAt(0);
  return span(text, cpOffset(text, domOffset(root, r.startContainer, r.startOffset)), cpOffset(text, domOffset(root, r.endContainer, r.endOffset)));
}
export function readyReasons(record, ledger, matched) {
  const reasons = [];
  if (!matched) reasons.push('anchor_mismatch');
  if (![record, ledger].every(x => Array.isArray(x?.unresolved_questions) && x.unresolved_questions.length === 0)) reasons.push('unresolved_questions_not_empty');
  if (!record?.checklist || record.checklist.length !== 10 || record.checklist.some(x => x.state !== 'checked')) reasons.push('incomplete_editorial_checks');
  if (record?.coverage_checks?.some(x => x.source_observation === 'condition_not_inspected' || x.finding !== null || (x.source_observation === 'condition_present' && !x.extracted_atom_ids?.length))) reasons.push('coverage_needs_context');
  return reasons;
}
export function statusRows(record, job) {
  const result = {editorial: record?.editorial_state || 'not_loaded', evidence: record?.reported_evidence_state || 'not_loaded', extraction: 'not_run', adapter: 'not_run', transport: 'not_run'};
  if (record) requireThat(STATES.evidence.includes(result.evidence), 'unknown_evidence_state');
  for (const report of job?.reports || []) {
    requireThat(STATES[report.validator]?.includes(report.status) && result[report.validator] === 'not_run', 'invalid_validator_status');
    result[report.validator] = report.status;
  }
  return result;
}
export function renderStatuses(container, record, job, freshness) {
  container.replaceChildren();
  for (const [name, value] of Object.entries({...statusRows(record, job), freshness})) {
    const item = document.createElement('div'); item.className = 'status-item';
    const label = document.createElement('span'); label.textContent = name;
    const output = document.createElement('strong'); output.textContent = value; output.dataset.status = name;
    item.append(label, output); container.append(item);
  }
}
