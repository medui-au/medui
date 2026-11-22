/* Care plan Copy, Email and BP → (ADR-129, ADR-174). Buttons carry data-cp-send="copy|email|bp" and
 * data-export-url. Email opens Comms for the plan's patient with the plan filled in (the
 * comms_prefill hand-over the Library uses). BP → sends the plan to Best Practice as a PIT file
 * in place (data-bp-url) and shows a brief green tick, as the AI Assistant's BP → does.
 * A page with unsaved work sets window.cpBeforeSend to a function returning a promise. */
(function () {
  'use strict';
  const csrf = () => (document.querySelector('meta[name="csrf-token"]') || {}).content || '';

  function fetchPlan(url, channel) {
    const ready = window.cpBeforeSend ? window.cpBeforeSend() : Promise.resolve();
    return ready.then(() => fetch(url, {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf()},
      body: JSON.stringify({channel})})).then(r => r.json()).then(d => {
      if (d.error) throw new Error(d.error);
      return d;
    });
  }

  function flash(btn, label) {
    const orig = btn.textContent;
    btn.textContent = label;
    setTimeout(() => { btn.textContent = orig; }, 2000);
  }

  function copy(btn) {
    fetchPlan(btn.dataset.exportUrl, 'copy').then(d => {
      if (window.ClipboardItem && navigator.clipboard.write) {
        return navigator.clipboard.write([new ClipboardItem({
          'text/html': new Blob([d.html], {type: 'text/html'}),
          'text/plain': new Blob([d.text], {type: 'text/plain'})})]);
      }
      return navigator.clipboard.writeText(d.text);
    }).then(() => flash(btn, '✓ Copied')).catch(e => alert(e.message || 'Copy failed.'));
  }

  function toComms(btn, channel) {
    // Open the tab now (a tab opened after the fetch would be blocked) and fill it once ready.
    const w = window.open('', '_blank');
    fetchPlan(btn.dataset.exportUrl, channel).then(d => {
      const prefill = channel === 'bp' ? {channel: 'bp', body: d.markdown, label: d.label}
                                       : {channel: 'email', body: d.markdown, subject: d.label};
      if (!w) { alert('Allow pop-ups for this site to open Comms.'); return; }
      w.sessionStorage.setItem('comms_prefill', JSON.stringify(prefill));
      w.location = d.comms_url;
    }).catch(e => { if (w) w.close(); if (e.message !== 'conflict') alert(e.message || 'Could not open Comms.'); });
  }

  function toBp(btn) {
    const tick = btn.nextElementSibling && btn.nextElementSibling.classList.contains('cp-bp-tick')
      ? btn.nextElementSibling : null;
    btn.disabled = true;
    const ready = window.cpBeforeSend ? window.cpBeforeSend() : Promise.resolve();
    ready.then(() => fetch(btn.dataset.bpUrl, {method: 'POST', headers: {'X-CSRFToken': csrf()}}))
      .then(r => r.json()).then(d => {
        if (d.error) throw new Error(d.error);
        if (tick) { tick.style.display = ''; setTimeout(() => { tick.style.display = 'none'; }, 2500); }
      }).catch(e => { if (e.message !== 'conflict') alert(e.message || 'Sending to Best Practice failed.'); })
      .finally(() => { btn.disabled = false; });
  }

  document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-cp-send]');
    if (!btn) return;
    const ch = btn.dataset.cpSend;
    if (ch === 'copy') copy(btn);
    else if (ch === 'bp' && btn.dataset.bpUrl) toBp(btn);
    else toComms(btn, ch);
  });
}());
