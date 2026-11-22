/* Care plan recipe editor (ADR-129): targets with citations, and the AI assistant.
 *
 * The assistant's reply only fills the form; the doctor edits, saves and approves. A JSON reply
 * ({"issue", "variant", "goals", "management", "providers", "targets": [...]}) fills each field;
 * any other reply goes to Management for the doctor to split.
 */
(function () {
  'use strict';
  const D = JSON.parse(document.getElementById('rc-data').textContent);
  const CSRF = document.querySelector('meta[name="csrf-token"]').content;
  const $ = (id) => document.getElementById(id);
  let authoringRun = null;

  function post(url, body) {
    return fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': CSRF},
                       body: JSON.stringify(body || {})}).then(r => r.json());
  }

  // ── Targets table ────────────────────────────────────────────────────────
  const FIELDS = ['token', 'target', 'guideline', 'edition', 'section', 'quote'];

  function addTarget(t) {
    t = t || {};
    const tr = document.createElement('tr');
    const tokenSel = document.createElement('select');
    tokenSel.name = 'token';
    tokenSel.append(new Option('— result —', ''));
    for (const [k, label] of Object.entries(D.tokens)) tokenSel.append(new Option(label, k, false, k === t.token));
    if (t.token && !(t.token in D.tokens)) tokenSel.append(new Option(`${t.token} (no such token)`, t.token, false, true));
    const cell = (node) => { const td = document.createElement('td'); td.append(node); return td; };
    const input = (name, ph) => { const i = document.createElement('input'); i.name = name; i.value = t[name] || ''; i.placeholder = ph || ''; return i; };
    const quote = document.createElement('textarea');
    quote.name = 'quote'; quote.value = t.quote || ''; quote.rows = 2;
    const url = input('url', 'https://…');
    const qcell = document.createElement('td'); qcell.append(quote, url);
    const del = document.createElement('button');
    del.type = 'button'; del.className = 'btn btn-outline btn-sm'; del.textContent = '✕';
    del.addEventListener('click', () => tr.remove());
    tr.append(cell(tokenSel), cell(input('target', '< 0.36 mmol/L')), cell(input('guideline', 'title')),
              cell(input('edition', '2025')), cell(input('section', '§ / page')), qcell, cell(del));
    $('rc-target-rows').append(tr);
  }

  function targets() {
    return [...$('rc-target-rows').querySelectorAll('tr')].map(tr => {
      const o = {};
      tr.querySelectorAll('[name]').forEach(i => o[i.name] = i.value.trim());
      return o;
    }).filter(o => o.token || o.target);
  }

  function modifiers() {
    const out = {};
    for (const part of $('rc-mods').value.split(';')) {
      const [k, ...v] = part.split(':');
      if (k && k.trim() && v.join(':').trim()) out[k.trim()] = v.join(':').trim();
    }
    return out;
  }

  (D.targets || []).forEach(addTarget);
  $('rc-add-target').addEventListener('click', () => addTarget());

  // ── Save and actions ─────────────────────────────────────────────────────
  $('rc-save')?.addEventListener('click', () => {
    const body = {
      id: D.id, issue_label: $('rc-issue').value, variant: $('rc-variant').value, modifiers: modifiers(),
      always_offer: $('rc-standing').checked, scope: $('rc-practice')?.checked ? 'practice' : 'personal',
      goals: $('rc-goals').value, management: $('rc-management').value, providers: $('rc-providers').value,
      review_due_on: $('rc-review').value || null, change_note: $('rc-note').value, targets: targets(),
      authoring_run: authoringRun,
    };
    post(D.save, body).then(d => { if (d.error) alert(d.error); else location.href = d.url; });
  });

  document.querySelectorAll('[data-action]').forEach(btn => btn.addEventListener('click', () => {
    const action = btn.dataset.action;
    const ask = {
      approve: 'Approve this version? You confirm you have checked each quoted guideline passage against its source. ' +
               'An approved version is fixed; later edits make a new version.',
      retire: 'Retire this recipe? It stops being offered; plans that used it keep their text.',
    }[action];
    if (ask && !confirm(ask)) return;
    post(D.action.replace('ACTION', action), {}).then(d => { if (d.error) alert(d.error); else location.href = d.url; });
  }));

  // ── AI assistance ────────────────────────────────────────────────────────
  function parseReply(text) {
    const m = text.match(/```(?:json)?\s*([\s\S]*?)```/);
    const raw = (m ? m[1] : text).trim();
    if (!raw.startsWith('{')) return null;
    try { return JSON.parse(raw); } catch (e) { return null; }
  }

  function applyReply(text) {
    if (!text.trim()) return 'The model returned no text. A reasoning model can spend its whole token limit thinking: raise Max tokens on the prompt, or choose another model.';
    const j = parseReply(text);
    const fill = (id, v) => { if (typeof v === 'string' && v.trim()) $(id).value = v.trim(); };
    if (!j) {
      $('rc-management').value = text.trim();
      // An opened fence with no closing one, or JSON that doesn't parse, is usually a reply cut off at the token limit.
      const cut = /```/.test(text) && (text.match(/```/g) || []).length % 2 === 1;
      return cut ? 'The reply looks cut off (token limit?): it is in Management. Raise Max tokens on the prompt and try again.'
                 : 'The reply was not JSON: it is in Management for you to split.';
    }
    fill('rc-goals', Array.isArray(j.goals) ? j.goals.join('\n') : j.goals);
    fill('rc-management', Array.isArray(j.management) ? j.management.join('\n') : j.management);
    fill('rc-providers', Array.isArray(j.providers) ? j.providers.join('\n') : j.providers);
    if (!$('rc-issue').value && typeof j.issue === 'string') $('rc-issue').value = j.issue;
    if (!$('rc-variant').value && typeof j.variant === 'string') $('rc-variant').value = j.variant;
    let unknown = 0;
    for (const t of j.targets || []) {
      if (t.token && !(t.token in D.tokens)) unknown++;
      addTarget(t);
    }
    return unknown ? `${unknown} target(s) name a result token that doesn't exist yet.` : 'Fields filled — check and edit before saving.';
  }

  $('rc-assist-run')?.addEventListener('click', () => {
    const text = $('rc-assist-text').value.trim();
    if (!text) return;
    const btn = $('rc-assist-run'), status = $('rc-assist-status'), out = $('rc-assist-out');
    btn.disabled = true; status.textContent = 'Starting…'; out.style.display = 'none'; out.textContent = '';
    const model = $('rc-model') ? $('rc-model').value : '';
    post(D.assist, {text, pipeline_id: parseInt($('rc-pipeline').value), model_id: model ? parseInt(model) : null}).then(d => {
      if (d.error) { status.textContent = d.error; btn.disabled = false; return; }
      authoringRun = d.run_id;
      // The run stream sends named events (event: complete …), so listen for each by name.
      const es = new EventSource(d.stream_url);
      let finished = false;
      const finish = (msg) => { finished = true; es.close(); btn.disabled = false; if (msg) status.textContent = msg; };
      const data = (e) => { try { return JSON.parse(e.data); } catch (_) { return {}; } };
      es.addEventListener('step_start', e => { status.textContent = '▸ ' + (data(e).message || ''); });
      es.addEventListener('complete', e => {
        const reply = data(e).output || '';
        if (reply) { out.style.display = 'block'; out.textContent = reply; }
        finish(applyReply(reply));
      });
      for (const type of ['step_error', 'cancelled']) es.addEventListener(type, e => finish(data(e).message || type));
      es.addEventListener('done', () => { if (!finished) finish(status.textContent || 'No reply.'); });
      es.addEventListener('error', e => {
        // A server 'error' event carries data; a dropped connection does not.
        if (e.data) return finish(data(e).message || 'The run failed.');
        if (!finished) finish('Stream connection lost.');
      });
    });
  });
})();
