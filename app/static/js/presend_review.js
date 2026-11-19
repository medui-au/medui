/* Pre-send review (ADR-090, ADR-091, ADR-094) — one component for the AI assistant,
 * both chatbots and the scribe (ADR-096).
 *
 * A reply bubble gets a 4th inner tab beside Raw / Rendered / Edit: "Sending" while a
 * request is held for review, "Sent" once it has gone. The tab shows the prompt exactly
 * as it goes to the AI: redaction tokens shaded, privacy-check hits marked and listed
 * with Remove, an Edit text mode re-checked as you type, Send and Cancel. The server
 * checks the text again before sending — nothing here is trusted. Once sent, the tab
 * shows the check's marks and lets the user report text that got through (ADR-115).
 *
 * The page's own tab code (switchChatInner) is left alone: this tab hides its panel
 * whenever another inner tab is clicked.
 */
(function () {
  'use strict';
  const TOKEN_RE = /\[Redacted [A-Za-z]+: [A-Z]+-[0-9a-f]+\]/g;

  const css = `
.chat-sent-panel { font-size:0.75rem; }
.psr-banner { padding:0.35rem 0.6rem; border-radius:3px; border-left:4px solid var(--accent-primary, #64748b);
  background:var(--bg-secondary); margin-bottom:0.4rem; }
.psr-banner.blocking { border-left-color:var(--danger); background:var(--danger-light, rgba(220,53,69,0.08)); color:var(--danger); }
.psr-summary { color:var(--text-muted); font-size:0.7rem; margin-bottom:0.3rem; }
.psr-hits { margin:0 0 0.4rem; padding-left:1.1rem; }
.psr-hits li { margin:0.1rem 0; }
.psr-hits a { cursor:pointer; text-decoration:underline; }
.psr-hits .t0, .psr-hits .t1 { color:var(--danger); }
.psr-hits .t2 { color:var(--warning, #b45309); }
.psr-view { white-space:pre-wrap; line-height:1.5; border:1px solid var(--border-color); border-radius:4px;
  padding:0.4rem 0.55rem; background:var(--bg-primary); max-height:45vh; overflow-y:auto; }
.psr-view .psr-tok { background:var(--bg-secondary); color:var(--text-muted); border-radius:3px; padding:0 0.15rem; }
.psr-view mark { border-radius:3px; padding:0 0.1rem; }
.psr-view mark.t0, .psr-view mark.t1 { background:rgba(220,53,69,0.25); outline:1px solid var(--danger); }
.psr-view mark.t2 { background:rgba(245,158,11,0.25); }
.psr-view mark.flash { outline:2px solid var(--accent-primary, #2563eb); }
.psr-edit { width:100%; box-sizing:border-box; min-height:30vh; font:inherit; font-size:0.75rem; }
.psr-toolbar { display:flex; gap:0.4rem; align-items:center; margin-top:0.45rem; flex-wrap:wrap; }
.psr-send { font-size:0.8rem; padding:0.25rem 0.9rem; }
.psr-status { font-size:0.7rem; color:var(--text-muted); }
.chat-inner-tab[disabled] { opacity:0.4; cursor:default; }
.psr-instr { margin:0 0 0.4rem; font-size:0.72rem; }
.psr-instr summary { cursor:pointer; color:var(--text-muted); }
.psr-instr pre { white-space:pre-wrap; font:inherit; margin:0.3rem 0 0; padding:0.4rem 0.55rem; max-height:30vh;
  overflow-y:auto; border:1px solid var(--border-color); border-radius:4px; background:var(--bg-secondary); }
.psr-btn { font-size:0.65rem; padding:0.05rem 0.35rem; border:1px solid currentColor; border-radius:0.2rem;
  background:none; color:inherit; cursor:pointer; }
`;
  const style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);

  function esc(t) { return t.replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c])); }
  function shade(t) { return esc(t).replace(TOKEN_RE, m => `<span class="psr-tok">${m}</span>`); }
  function hitLabel(h) {
    const who = h.tier === 0 ? 'the patient’s own identifier'
      : h.tier === 1 ? 'a practitioner or the practice' : 'looks like an identifier';
    return `${(h.type || '').replace(/_/g, ' ')} — ${who}`;
  }
  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  // The system prompt that goes with the prompt — always collapsed, read-only
  // ("Instructions given to the AI", as in ADR-086). Nothing when there is none.
  function instructions(system) {
    if (!system) return null;
    const d = el('details', 'psr-instr');
    d.appendChild(el('summary', null, 'Instructions given to the AI'));
    d.appendChild(el('pre', null, system));
    return d;
  }

  // ── The tab ────────────────────────────────────────────────────────────────

  function addTab(turnEl, label) {
    let tabs = turnEl.querySelector('.chat-inner-tabs');
    if (!tabs) { tabs = el('div', 'chat-inner-tabs'); turnEl.prepend(tabs); }
    const btn = el('button', 'chat-inner-tab', label);
    btn.type = 'button';
    btn.dataset.tab = 'sent';
    tabs.appendChild(btn);
    const panel = el('div', 'chat-inner-panel chat-sent-panel');
    const panels = turnEl.querySelectorAll('.chat-inner-panel');
    if (panels.length) panels[panels.length - 1].after(panel); else tabs.after(panel);
    btn.onclick = () => showTab(turnEl, btn, panel);
    // Another inner tab clicked: switchChatInner shows its panel; hide ours.
    turnEl.addEventListener('click', e => {
      const t = e.target.closest && e.target.closest('.chat-inner-tab');
      if (t && t !== btn && t.parentElement === tabs) panel.classList.remove('active');
    }, true);
    return {btn, panel};
  }

  function showTab(turnEl, btn, panel) {
    turnEl.querySelectorAll('.chat-inner-tab').forEach(t => t.classList.remove('active'));
    turnEl.querySelectorAll('.chat-inner-panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    panel.classList.add('active');
    if (panel._load) { const f = panel._load; panel._load = null; f(); }
  }

  // local: the run used a model inside the practice (ADR-113), shown for transparency.
  // opts (ADR-115): {check, runId, csrf}. check: the pre-send check's positions and types,
  // shown in the prompt; runId: the run, so the user can report text that got through.
  function renderSent(panel, text, review, system, local, opts) {
    opts = opts || {};
    text = text || '';
    panel.innerHTML = '';
    const note = el('div', 'psr-banner', local
      ? 'Sent to a local model as shown. The model runs inside the practice: nothing was sent outside it.'
      : 'Sent to the AI as shown.' + (review && review.paused
        ? (review.edited ? ` Reviewed and edited before sending${review.removed ? ` (${review.removed} removed)` : ''}.`
                         : ' Reviewed before sending.') : ''));
    panel.appendChild(note);
    const hits = (!local && opts.check && Array.isArray(opts.check.hits))
      ? opts.check.hits.filter(h => Number.isInteger(h.start) && Number.isInteger(h.end)
                                    && 0 <= h.start && h.start < h.end && h.end <= text.length)
                       .sort((a, b) => a.start - b.start)
      : [];
    if (!local) panel.appendChild(el('div', 'psr-summary', checkLine(opts.check, hits)));
    const instr = instructions(system);
    if (instr) panel.appendChild(instr);
    const view = el('div', 'psr-view');
    let html = '', pos = 0;
    hits.forEach(h => {
      if (h.start < pos) return;
      html += shade(text.slice(pos, h.start));
      html += `<mark class="t${h.tier}" title="${esc(hitLabel(h))}">${esc(text.slice(h.start, h.end))}</mark>`;
      pos = h.end;
    });
    view.innerHTML = html + shade(text.slice(pos));
    panel.appendChild(view);
    if (!local && opts.runId) panel.appendChild(reportBar(view, text, opts));
  }

  // What the check found, worded as what it looked for: it can't know every name.
  function checkLine(check, hits) {
    if (!check) return 'The privacy check result is not available for this request.';
    const named = hits.filter(h => h.tier === 0 || h.tier === 1).length;
    const possible = hits.length - named;
    const found = named || possible
      ? `The privacy check marked ${[named ? `${named} identifier${named === 1 ? '' : 's'} (red)` : '',
                                     possible ? `${possible} possible identifier${possible === 1 ? '' : 's'} to look at (yellow)` : '']
                                    .filter(Boolean).join(' and ')}.`
      : 'The privacy check found no names, addresses or numbers it recognises.';
    return found + ' It cannot know every name: if you see something identifying, select it and report it.';
  }

  // Report text that got through (ADR-115): the selection's positions in the prompt.
  function reportBar(view, text, opts) {
    const bar = el('div', 'psr-toolbar');
    const btn = el('button', 'psr-btn', 'Report something that got through'); btn.type = 'button';
    btn.title = 'Select the text in the prompt above, then report it: an administrator can add it to the redactions';
    const noteIn = el('input'); noteIn.type = 'text'; noteIn.maxLength = 200;
    noteIn.placeholder = 'What is it? (optional)';
    noteIn.style.cssText = 'font-size:0.7rem; padding:0.1rem 0.35rem; min-width:12rem;';
    const status = el('span', 'psr-status');
    bar.append(btn, noteIn, status);
    function offset(node, off) {
      const r = document.createRange();
      r.selectNodeContents(view);
      r.setEnd(node, off);
      return r.toString().length;
    }
    btn.onclick = () => {
      const sel = window.getSelection();
      const range = sel && sel.rangeCount ? sel.getRangeAt(0) : null;
      if (!range || range.collapsed || !view.contains(range.commonAncestorContainer)) {
        status.textContent = 'Select the text in the prompt first.';
        return;
      }
      let start = offset(range.startContainer, range.startOffset);
      let end = offset(range.endContainer, range.endOffset);
      while (start < end && /\s/.test(text[start])) start++;      // trim a loose selection
      while (end > start && /\s/.test(text[end - 1])) end--;
      btn.disabled = true;
      status.textContent = 'Reporting…';
      fetch(`/pipeline/runs/${opts.runId}/privacy-report`, {
        method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': opts.csrf},
        body: JSON.stringify({start, end, note: noteIn.value}),
      }).then(r => r.json()).then(r => {
        status.textContent = r.message || (r.ok ? 'Reported.' : 'Not reported.');
        if (r.ok) { noteIn.value = ''; sel.removeAllRanges(); }
      }).catch(() => { status.textContent = 'Could not reach the server — try again'; })
        .finally(() => { btn.disabled = false; });
    };
    return bar;
  }

  /** A "Sent" tab on a finished reply. text: the prompt as sent, or a function
   *  returning a Promise of {prompt, review, system_prompt} (loaded when the tab is
   *  first opened). system: the system prompt sent with it. */
  function attachSent(turnEl, text, review, system) {
    const {panel} = addTab(turnEl, 'Sent');
    if (typeof text === 'function') {
      panel.textContent = 'Loading…';
      panel._load = () => text().then(d => {
        if (d && d.prompt) renderSent(panel, d.prompt, d.review, d.system_prompt);
        else panel.textContent = (d && d.error) || 'Nothing was sent to a cloud AI for this reply.';
      }).catch(() => { panel.textContent = 'Could not load what was sent.'; });
    } else {
      renderSent(panel, text, review, system);
    }
  }

  // ── Review of a held request ───────────────────────────────────────────────

  /** A placeholder reply bubble, open on "Sending", for a request held for review. */
  function pendingTurn(transcriptEl) {
    const turn = el('div', 'chat-turn chat-turn-assistant chat-turn-pending');
    const tabs = el('div', 'chat-inner-tabs');
    ['Raw', 'Rendered', 'Edit'].forEach(n => {
      const b = el('button', 'chat-inner-tab', n);
      b.type = 'button'; b.disabled = true; b.title = 'The reply appears here once the request is sent';
      tabs.appendChild(b);
    });
    turn.appendChild(tabs);
    const t = addTab(turn, 'Sending');
    turn._psr = t;
    transcriptEl.appendChild(turn);
    showTab(turn, t.btn, t.panel);
    return turn;
  }

  /** Show the review in a pending bubble. opts: {runId, data, csrf}. */
  function mountReview(turn, opts) {
    const {btn, panel} = turn._psr;
    btn.textContent = 'Sending';
    showTab(turn, btn, panel);
    mountInto(panel, btn, opts);
  }

  /** Show the review in a page's own tab pane (the scribe, the AI assistant); the page
   *  shows the pane. btn: the tab button, relabelled "Sending" now and "Sent" once it
   *  has gone (opts.labels = {sending, sent} to word them otherwise). */
  function mountReviewPanel(panel, btn, opts) {
    btn.textContent = (opts.labels && opts.labels.sending) || 'Sending';
    mountInto(panel, btn, opts);
  }

  /** opts: {runId, data, csrf, labels?, onAnswer?(action)} — onAnswer runs once the
   *  server has accepted Send or Cancel, for a page that moves on (the AI assistant). */
  function mountInto(panel, btn, opts) {
    const d = opts.data || {};
    const labels = opts.labels || {};
    const state = {text: d.prompt || '', hits: d.hits || [], blocking: !!d.blocking, timer: null};
    panel.innerHTML = '';
    const banner = el('div', 'psr-banner' + (d.blocking ? ' blocking' : ''),
      d.message ? d.message
        : d.blocking ? 'The privacy check found an identifier that redaction missed. Remove it (or reword it) before this is sent — nothing has gone to the AI yet.'
        : 'This is exactly what will be sent to the AI. Nothing has gone yet.');
    // Help on this tab (ADR-102): the side panel opens it.
    const helpBtn = el('button', 'help-btn', '?'); helpBtn.type = 'button';
    helpBtn.dataset.help = 'ai-drafts.sending';
    helpBtn.title = 'Help: The Sending tab'; helpBtn.setAttribute('aria-label', helpBtn.title);
    banner.appendChild(helpBtn);
    const summary = el('div', 'psr-summary');
    const list = el('ol', 'psr-hits');
    const view = el('div', 'psr-view');
    const edit = el('textarea', 'psr-edit');
    edit.style.display = 'none';
    const bar = el('div', 'psr-toolbar');
    const send = el('button', 'btn btn-primary psr-send', 'Send to AI'); send.type = 'button';
    const cancel = el('button', 'btn btn-outline', 'Cancel'); cancel.type = 'button';
    cancel.style.cssText = 'font-size:0.72rem; padding:0.2rem 0.55rem;';
    const editBtn = el('button', 'psr-btn', 'Edit text'); editBtn.type = 'button';
    const status = el('span', 'psr-status');
    bar.append(send, cancel, editBtn, status);
    const instr = instructions(d.system_prompt);
    panel.append(...[banner, summary, list, instr, view, edit, bar].filter(Boolean));

    function render() {
      const nTok = (state.text.match(TOKEN_RE) || []).length;
      const nBlock = state.hits.filter(h => h.tier === 0 || h.tier === 1).length;
      summary.textContent = `${nTok} redaction${nTok === 1 ? '' : 's'} · ${nBlock} identifier${nBlock === 1 ? '' : 's'} to remove`
        + (state.hits.length > nBlock ? ` · ${state.hits.length - nBlock} to check` : '');
      list.innerHTML = '';
      state.hits.forEach((h, i) => {
        const li = el('li', 't' + h.tier);
        const a = el('a', null, hitLabel(h)); a.tabIndex = 0;
        a.onclick = () => jump(i);
        a.onkeydown = e => { if (e.key === 'Enter') jump(i); };
        const rm = el('button', 'psr-btn', 'Remove'); rm.type = 'button';
        rm.title = 'Replace this with [Redacted] — every copy of the same text in the prompt';
        rm.onclick = () => remove(i);
        li.append(a, document.createTextNode(' '), rm);
        list.appendChild(li);
      });
      if (edit.style.display === 'none') {
        let html = '', pos = 0;
        state.hits.forEach((h, i) => {
          if (h.start < pos) return;
          html += shade(state.text.slice(pos, h.start));
          html += `<mark data-hit="${i}" class="t${h.tier}" title="${esc(hitLabel(h))}">${esc(state.text.slice(h.start, h.end))}</mark>`;
          pos = h.end;
        });
        view.innerHTML = html + shade(state.text.slice(pos));
      }
      send.disabled = state.blocking;
      send.title = state.blocking ? 'Remove the identifiers marked in red first' : '';
    }
    function jump(i) {
      const h = state.hits[i]; if (!h) return;
      if (edit.style.display !== 'none') { edit.focus(); edit.setSelectionRange(h.start, h.end); return; }
      const m = view.querySelector(`mark[data-hit="${i}"]`);
      if (m) { m.scrollIntoView({block: 'center'}); m.classList.add('flash'); setTimeout(() => m.classList.remove('flash'), 1500); }
    }
    function remove(i) {
      const h = state.hits[i]; if (!h) return;
      // Every copy of the same text goes — the same name found twice needs one click.
      state.text = state.text.split(state.text.slice(h.start, h.end)).join('[Redacted]');
      if (edit.style.display !== 'none') edit.value = state.text;
      recheck(0);
    }
    function recheck(delay) {
      clearTimeout(state.timer);
      status.textContent = 'Checking…';
      send.disabled = true;
      state.timer = setTimeout(() => {
        fetch(`/pipeline/run/${opts.runId}/review/check`, {
          method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': opts.csrf},
          body: JSON.stringify({prompt: state.text}),
        }).then(r => r.json()).then(r => {
          if (r.error) { status.textContent = r.error; return; }
          state.hits = r.hits || []; state.blocking = !!r.blocking;
          status.textContent = r.blocking ? '' : '✓ Nothing left to remove';
          render();
        }).catch(() => { status.textContent = 'Check failed — try again'; });
      }, delay);
    }
    function answer(action) {
      fetch(`/pipeline/run/${opts.runId}/review`, {
        method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': opts.csrf},
        body: JSON.stringify({action, prompt: state.text}),
      }).then(r => r.json()).then(r => {
        if (r.error) { status.textContent = r.error; return; }
        if (action === 'send') {
          btn.textContent = labels.sent || 'Sent';
          bar.remove(); list.remove(); summary.remove(); edit.remove();
          banner.className = 'psr-banner';
          banner.textContent = 'Sent — waiting for the reply…';
          view.style.display = '';
          view.innerHTML = shade(state.text);
        } else {
          status.textContent = 'Cancelling…';
        }
        if (opts.onAnswer) opts.onAnswer(action);
      }).catch(() => { status.textContent = 'Could not reach the server — try again'; });
    }
    editBtn.onclick = () => {
      if (edit.style.display === 'none') {
        edit.value = state.text; edit.style.display = ''; view.style.display = 'none';
        editBtn.textContent = 'Show highlights'; edit.focus();
      } else {
        state.text = edit.value; edit.style.display = 'none'; view.style.display = '';
        editBtn.textContent = 'Edit text'; render();
      }
    };
    edit.addEventListener('input', () => { state.text = edit.value; recheck(500); });
    send.onclick = () => { if (!state.blocking) answer('send'); };
    cancel.onclick = () => answer('cancel');
    render();
    // Enter sends — unless there is a hit: focus it, so a reflexive Enter doesn't send past it.
    (list.querySelector('a') || send).focus();
  }

  /** A tab whose panel is filled by fill(panel) when first opened (the admin Debug tab).
   *  One per turn and label; returns the existing one if already there. */
  function attachTab(turnEl, label, fill) {
    const existing = turnEl.querySelector(`.chat-inner-tab[data-tab="${label.toLowerCase()}"]`);
    if (existing) return existing;
    const {btn, panel} = addTab(turnEl, label);
    btn.dataset.tab = label.toLowerCase();
    panel._load = () => fill(panel);
    return btn;
  }

  window.PresendReview = {attachSent, pendingTurn, mountReview, mountReviewPanel, attachTab,
                          showSent: renderSent};
})();
