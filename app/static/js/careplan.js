/* Care plan composition screen (ADR-129).
 *
 * The doctor composes; this page fills facts. It never picks an issue, a recipe variant or a target
 * for the patient, and never says whether a target is met. The draft is saved whole (debounced) with
 * a revision number; values change only through the confirmed Fetch values list.
 */
(function () {
  'use strict';

  const A = JSON.parse(document.getElementById('cp-asset').textContent);
  const CSRF = document.querySelector('meta[name="csrf-token"]').content;
  const TOKEN_RE = /\{([a-z][a-z0-9_]{0,39})\.(last|date|unit|target)\}/g;
  const state = A.draft;
  let revision = A.revision;
  let dirty = false, saving = false, saveTimer = null, conflict = false;

  const $ = (id) => document.getElementById(id);
  const el = (tag, attrs, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === 'class') n.className = v;
      else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
      else if (v !== null && v !== undefined && v !== false) n.setAttribute(k, v === true ? '' : v);
    }
    for (const kid of kids.flat()) if (kid !== null && kid !== undefined) n.append(kid);
    return n;
  };

  function post(url, body) {
    return fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': CSRF},
                       body: JSON.stringify(body || {})})
      .then(r => r.json().then(d => ({status: r.status, data: d})));
  }

  // Same rule as careplan_service.issue_key.
  function issueKey(label) {
    return (label || '').trim().toLowerCase().replace(/\((?:l|r|bilateral)\)\s*$/, '')
      .replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 80);
  }

  function tokensIn(...texts) {
    const keys = [];
    for (const t of texts) for (const m of (t || '').matchAll(TOKEN_RE)) if (!keys.includes(m[1])) keys.push(m[1]);
    return keys;
  }

  function fmtDate(iso) {
    if (!iso) return '';
    const [y, m, d] = iso.slice(0, 10).split('-');
    return `${d}/${m}/${y}`;
  }

  // ── Saving ───────────────────────────────────────────────────────────────
  function setSaveState(text) { $('cp-save-state').textContent = text; }

  function changed(soon) {
    dirty = true;
    setSaveState('Unsaved changes');
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveNow, soon ? 1000 : 20000);
  }

  function saveNow() {
    clearTimeout(saveTimer);
    if (conflict) return Promise.reject(new Error('conflict'));
    if (!dirty) return Promise.resolve();
    if (saving) return new Promise(res => setTimeout(() => res(saveNow()), 300));
    saving = true;
    setSaveState('Saving…');
    dirty = false;
    return post(A.urls.save, {revision, draft: state}).then(({status, data}) => {
      saving = false;
      if (status === 409) {
        conflict = true;
        setSaveState('Not saved');
        alert(data.error);
        throw new Error('conflict');
      }
      if (data.error) { dirty = true; setSaveState('Not saved: ' + data.error); throw new Error(data.error); }
      revision = data.revision;
      setSaveState(dirty ? 'Unsaved changes' : 'Saved');
    }, (e) => { saving = false; dirty = true; setSaveState('Not saved (connection)'); throw e; });
  }

  window.addEventListener('beforeunload', (e) => { if (dirty) { e.preventDefault(); e.returnValue = ''; } });

  // ── Issue and recipe options ─────────────────────────────────────────────
  const recipesByIssue = {};
  for (const r of A.recipes) (recipesByIssue[r.issue_key] = recipesByIssue[r.issue_key] || []).push(r);

  function issueOptions(row) {
    const sel = el('select', {'aria-label': 'Issue'});
    sel.append(el('option', {value: ''}, '— choose an issue —'));
    const groups = [];
    if (A.coded.length) groups.push(['Coded history', A.coded.map(c => ({label: c.label, source: 'coded', hint: c.year}))]);
    const standing = [], other = [], seen = new Set(A.coded.map(c => c.key));
    for (const r of A.recipes) {
      if (seen.has(r.issue_key)) continue;
      seen.add(r.issue_key);
      (r.always_offer ? standing : other).push({label: r.issue_label, source: 'standing'});
    }
    if (standing.length) groups.push(['Standing issues', standing]);
    if (other.length) groups.push(['Other recipes', other]);
    let found = !row.issue_label;
    for (const [name, items] of groups) {
      const g = el('optgroup', {label: name});
      for (const it of items) {
        const o = el('option', {value: JSON.stringify([it.label, it.source])}, it.label + (it.hint ? ` (${it.hint})` : ''));
        if (it.label === row.issue_label) { o.selected = true; found = true; }
        g.append(o);
      }
      sel.append(g);
    }
    if (!found) sel.append(el('option', {value: JSON.stringify([row.issue_label, row.issue_source]), selected: true}, row.issue_label));
    sel.append(el('option', {value: '__other'}, 'Other (type your own)…'));
    return sel;
  }

  function recipeSelect(row, onPick) {
    const list = recipesByIssue[issueKey(row.issue_label)] || [];
    const wrap = el('div', {class: 'cp-facts'});
    if (!list.length) return wrap;
    const sel = el('select', {'aria-label': 'Recipe'});
    sel.append(el('option', {value: ''}, list.length > 1 ? '— recipe: choose a variant —' : '— recipe —'));
    for (const r of list) {
      const mods = Object.entries(r.modifiers || {}).map(([k, v]) => `${k}: ${v}`).join(', ');
      const name = (r.variant ? r.variant : 'standard') + (mods ? ` [${mods}]` : '') +
                   (r.scope === 'personal' ? ' · mine' : '') + (r.status !== 'approved' ? ' · draft' : '');
      const o = el('option', {value: r.id}, name);
      if (r.id === row.recipe_id) o.selected = true;
      sel.append(o);
    }
    sel.addEventListener('change', () => onPick(list.find(r => String(r.id) === sel.value)));
    wrap.append(sel);
    if (list.length > 1 || list.some(r => Object.keys(r.modifiers || {}).length)) {
      // Plain facts beside the variants; nothing is pre-selected or filtered by them.
      wrap.append(el('div', {class: 'cp-muted'}, `Patient: ${A.patient_facts.age || '?'} · ${A.patient_facts.sex || '?'}`));
    }
    return wrap;
  }

  // ── Facts line under a row: token values, the target set, the previous plan's value ──
  function factsLine(row) {
    const keys = tokensIn(row.goals, row.management);
    for (const k of Object.keys(row.targets || {})) if (!keys.includes(k)) keys.push(k);
    if (!keys.length) return null;
    const box = el('div', {class: 'cp-facts'});
    for (const k of keys) {
      const t = A.tokens[k];
      const v = state.values[k];
      const prev = A.previous_values[k];
      const parts = [];
      parts.push(el('strong', {}, (t && t.label) || k));
      if (!t) parts.push(el('span', {class: 'cp-warn'}, ' unknown token'));
      else if (v && v.value) {
        parts.push(` ${v.value} ${v.unit || ''} · ${fmtDate(v.date)}`);
        if (v.status && v.status !== 'found') parts.push(el('span', {class: 'cp-warn'}, ` (${v.status.replace('_', ' ')})`));
      } else parts.push(el('span', {class: 'cp-muted'}, ' not fetched'));
      if (row.targets && row.targets[k]) parts.push(` · target set: ${row.targets[k]}`);
      if (prev && prev.value) parts.push(el('span', {class: 'cp-muted'}, ` · was ${prev.value} ${prev.unit || ''} (${fmtDate(prev.date)})`));
      box.append(el('div', {}, parts));
    }
    return box;
  }

  // ── Rows ─────────────────────────────────────────────────────────────────
  function blankRow() {
    return {issue_label: '', issue_source: 'free_text', recipe_id: null, recipe_version_id: null,
            goals: '', management: '', providers: '', targets: {}, edited: false};
  }

  function applyRecipe(row, r) {
    if (!r) { row.recipe_id = null; row.recipe_version_id = null; row.targets = {}; return true; }
    const has = (row.goals || row.management || row.providers).trim();
    if (has && !confirm('Replace this row\'s goals, management and providers with the recipe?')) return false;
    Object.assign(row, {recipe_id: r.id, recipe_version_id: r.version_id, goals: r.goals,
                        management: r.management, providers: r.providers, targets: {...r.targets}, edited: false});
    return true;
  }

  function insertAtCursor(ta, text) {
    const s = ta.selectionStart ?? ta.value.length, e = ta.selectionEnd ?? ta.value.length;
    ta.value = ta.value.slice(0, s) + text + ta.value.slice(e);
    ta.selectionStart = ta.selectionEnd = s + text.length;
    ta.dispatchEvent(new Event('input'));
    ta.focus();
  }

  function renderRows() {
    const body = $('cp-rows');
    body.replaceChildren();
    state.rows.forEach((row, i) => body.append(renderRow(row, i)));
  }

  function renderRow(row, i) {
    const tr = el('tr');
    // Issue
    const issueCell = el('td');
    const sel = issueOptions(row);
    sel.addEventListener('change', () => {
      if (sel.value === '__other') {
        const label = prompt('Issue, in your own words:', row.issue_label || '');
        if (label && label.trim()) { row.issue_label = label.trim(); row.issue_source = 'free_text'; }
      } else if (sel.value === '') {
        row.issue_label = ''; row.issue_source = 'free_text';
      } else {
        const [label, source] = JSON.parse(sel.value);
        row.issue_label = label; row.issue_source = source;
      }
      row.recipe_id = null; row.recipe_version_id = null;
      changed(true); renderRows();
    });
    issueCell.append(sel, recipeSelect(row, (r) => { if (applyRecipe(row, r)) { changed(true); } renderRows(); }));
    const tools = el('div', {class: 'cp-row-tools'});
    tools.append(
      el('button', {class: 'btn btn-outline', title: 'Move up', onclick: () => move(i, -1)}, '↑'),
      el('button', {class: 'btn btn-outline', title: 'Move down', onclick: () => move(i, 1)}, '↓'),
      el('button', {class: 'btn btn-outline', title: 'Remove row', onclick: () => {
        if ((row.issue_label || row.goals || row.management) && !confirm('Remove this row?')) return;
        state.rows.splice(i, 1); changed(true); renderRows(); }}, '✕'),
      el('button', {class: 'btn btn-outline', title: 'Save this row as one of your recipes', onclick: () => saveAsRecipe(row)}, 'Save as recipe'));
    issueCell.append(tools);
    tr.append(issueCell);

    // Goals / Management / Providers
    for (const f of ['goals', 'management', 'providers']) {
      const td = el('td');
      const ta = el('textarea', {'aria-label': f});
      ta.value = row[f] || '';
      ta.addEventListener('input', () => { row[f] = ta.value; if (row.recipe_id) row.edited = true; changed(false); });
      ta.addEventListener('change', () => { changed(true); refreshFacts(tr, row); });
      td.append(ta);
      if (f === 'management' && Object.keys(A.tokens).length) {
        const ins = el('select', {'aria-label': 'Insert a result', style: 'margin-top:0.25rem;font-size:0.72rem;'});
        ins.append(el('option', {value: ''}, '+ insert a result…'));
        for (const [k, t] of Object.entries(A.tokens)) ins.append(el('option', {value: k}, t.label));
        ins.addEventListener('change', () => {
          if (ins.value) insertAtCursor(ta, `${A.tokens[ins.value].label} {${ins.value}.last} ({${ins.value}.date})`);
          ins.value = ''; refreshFacts(tr, row);
        });
        td.append(ins);
      }
      tr.append(td);
    }
    refreshFacts(tr, row);
    return tr;
  }

  function refreshFacts(tr, row) {
    const cell = tr.children[0];
    cell.querySelector('.cp-facts-line')?.remove();
    const f = factsLine(row);
    if (f) { f.classList.add('cp-facts-line'); cell.append(f); }
  }

  function move(i, d) {
    const j = i + d;
    if (j < 0 || j >= state.rows.length) return;
    [state.rows[i], state.rows[j]] = [state.rows[j], state.rows[i]];
    changed(true); renderRows();
  }

  function saveAsRecipe(row) {
    if (!row.issue_label) { alert('Choose or type the issue first.'); return; }
    // The recipe keeps the text with its tokens, never this patient's values.
    showModal([
      el('h3', {style: 'margin-top:0'}, 'Save as one of your recipes'),
      el('p', {class: 'cp-muted'}, 'Check that the text below has nothing about this patient in it. Values stay as tokens; ' +
        'the recipe is saved as a draft for you to approve on the recipe screen.'),
      el('pre', {style: 'white-space:pre-wrap;font-size:0.8rem;background:var(--bg-secondary);padding:0.5rem;'},
         `Issue: ${row.issue_label}\n\nGoals:\n${row.goals}\n\nManagement:\n${row.management}\n\nProviders:\n${row.providers}`),
      el('div', {style: 'display:flex;gap:0.5rem;justify-content:flex-end'},
        el('button', {class: 'btn btn-outline btn-sm', onclick: hideModal}, 'Cancel'),
        el('button', {class: 'btn btn-primary btn-sm', onclick: () => post(A.urls.row_recipe, {row}).then(({data}) => {
          hideModal();
          if (data.error) alert(data.error);
          else if (confirm('Saved to your recipes as a draft. Open it in a new tab?')) window.open(data.url, '_blank');
        })}, 'Save recipe')),
    ]);
  }

  // ── Modal ────────────────────────────────────────────────────────────────
  function showModal(children) { $('cp-modal').replaceChildren(...children); $('cp-modal-back').style.display = 'flex'; }
  function hideModal() { $('cp-modal-back').style.display = 'none'; }
  $('cp-modal-back').addEventListener('click', (e) => { if (e.target.id === 'cp-modal-back') hideModal(); });

  // ── Fetch values ─────────────────────────────────────────────────────────
  function allTokens() {
    const keys = [];
    for (const r of state.rows) for (const k of tokensIn(r.goals, r.management)) if (!keys.includes(k)) keys.push(k);
    return keys;
  }

  $('cp-fetch').addEventListener('click', () => {
    const keys = allTokens();
    if (!keys.length) { alert('No result tokens in the plan. Use "+ insert a result…" under Management.'); return; }
    showModal([el('p', {}, 'Reading Best Practice…')]);
    post(A.urls.preview, {keys}).then(({data}) => {
      if (data.error) { showModal([el('p', {class: 'cp-warn'}, data.error), el('button', {class: 'btn btn-outline btn-sm', onclick: hideModal}, 'Close')]); return; }
      const tbody = el('tbody');
      for (const v of data.values) {
        const prev = A.previous_values[v.key] || state.values[v.key];
        const ok = ['found', 'stale', 'unit_mismatch'].includes(v.status);
        const tick = el('input', {type: 'checkbox', 'data-key': v.key});
        tick.checked = ok;
        tick.disabled = !ok;
        const manual = ok ? null : el('input', {type: 'text', placeholder: 'type a value', 'data-manual': v.key, style: 'width:7rem'});
        const statusText = {found: '✓ found', stale: '⚠ older than the set age', unit_mismatch: '⚠ unit differs from expected',
                            not_found: 'no result in Best Practice', unknown_token: 'unknown token'}[v.status] || v.status;
        tbody.append(el('tr', {},
          el('td', {}, tick), el('td', {}, v.label),
          el('td', {class: 'cp-muted'}, prev && prev.value ? `${prev.value} ${prev.unit || ''} · ${fmtDate(prev.date)}` : '—'),
          el('td', {}, ok ? `${v.value} ${v.unit || ''} · ${fmtDate(v.date)}` : (manual || '—')),
          el('td', {class: ok && v.status === 'found' ? '' : 'cp-warn'}, statusText)));
      }
      showModal([
        el('h3', {style: 'margin-top:0'}, 'Fetch values'),
        el('p', {class: 'cp-muted'}, 'The latest result for each token, as the laboratory reported it. Untick any you don\'t want used; ' +
          'type a value where Best Practice has none.'),
        el('table', {}, el('thead', {}, el('tr', {}, el('th', {}, ''), el('th', {}, 'Result'), el('th', {}, 'Previous'),
                                                         el('th', {}, 'Latest'), el('th', {}, 'Status'))), tbody),
        el('div', {style: 'display:flex;gap:0.5rem;justify-content:flex-end;margin-top:0.6rem'},
          el('button', {class: 'btn btn-outline btn-sm', onclick: hideModal}, 'Cancel'),
          el('button', {class: 'btn btn-primary btn-sm', onclick: () => confirmValues(tbody)}, 'Use these values')),
      ]);
    });
  });

  function confirmValues(tbody) {
    const keys = [...tbody.querySelectorAll('input[type=checkbox]:checked')].map(c => c.dataset.key);
    const manual = {};
    for (const m of tbody.querySelectorAll('input[data-manual]')) if (m.value.trim()) manual[m.dataset.manual] = m.value.trim();
    saveNow().then(() => post(A.urls.confirm, {keys, manual})).then(({data}) => {
      if (data.error) { alert(data.error); return; }
      state.values = data.values; revision = data.revision;
      hideModal(); renderRows();
    }).catch(() => {});
  }

  // ── Check and file ───────────────────────────────────────────────────────
  function checkNotes() {
    return saveNow().then(() => post(A.urls.check, {})).then(({data}) => data.notes || []);
  }

  $('cp-check').addEventListener('click', () => checkNotes().then(notes => showModal([
    el('h3', {style: 'margin-top:0'}, 'Check'),
    notes.length ? el('ul', {}, notes.map(n => el('li', {}, n))) : el('p', {}, 'Every row has an issue, goals, management and providers, and every result token has a value.'),
    el('button', {class: 'btn btn-outline btn-sm', onclick: hideModal}, 'Close'),
  ])).catch(() => {}));

  $('cp-file').addEventListener('click', () => checkNotes().then(notes => showModal([
    el('h3', {style: 'margin-top:0'}, 'File this plan'),
    el('p', {}, 'Filing freezes the plan as it is now, with the values shown. It can be voided later but not edited.'),
    notes.length ? el('div', {}, el('p', {class: 'cp-warn'}, 'Still to look at:'), el('ul', {}, notes.map(n => el('li', {}, n)))) : null,
    el('div', {style: 'display:flex;gap:0.5rem;justify-content:flex-end'},
      el('button', {class: 'btn btn-outline btn-sm', onclick: hideModal}, 'Back to the plan'),
      el('button', {class: 'btn btn-primary btn-sm', onclick: () => post(A.urls.file, {}).then(({data}) => {
        if (data.error) { alert(data.error); return; }
        dirty = false; location.href = data.url;
      })}, notes.length ? 'File anyway' : 'File plan')),
  ])).catch(() => {}));

  window.cpBeforeSend = () => saveNow();         // careplan_send.js: send what is saved

  $('cp-print').addEventListener('click', () => {
    // Open the window now (a popup opened after the save would be blocked), then load it once saved.
    const w = window.open('', '_blank');
    saveNow().then(() => { if (w) w.location = A.urls.print; else location.href = A.urls.print; })
      .catch(() => { if (w) w.close(); });
  });

  $('cp-discard').addEventListener('click', () => {
    if (!confirm('Discard this draft? It is kept in the record as void, not deleted.')) return;
    post(A.urls.void, {reason: 'Draft discarded'}).then(({data}) => {
      if (data.error) { alert(data.error); return; }
      dirty = false; location.href = data.url;
    });
  });

  // ── Header and start ─────────────────────────────────────────────────────
  $('cp-header').value = state.header || '';
  $('cp-header').addEventListener('input', () => { state.header = $('cp-header').value; changed(false); });
  $('cp-header').addEventListener('change', () => changed(true));
  $('cp-review').value = state.review_due_on || '';
  $('cp-review').addEventListener('change', () => { state.review_due_on = $('cp-review').value || null; changed(true); });
  $('cp-add-row').addEventListener('click', () => { state.rows.push(blankRow()); changed(true); renderRows(); });
  state.values = state.values || {};
  renderRows();
})();
