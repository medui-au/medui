// The [?] help buttons (ADR-102): open one help section in the side panel.
(function () {
  'use strict';
  var panel = document.getElementById('help-panel');
  if (!panel) return;
  var content = panel.querySelector('.help-panel-content');
  var opener = null;

  function close() {
    panel.hidden = true;
    if (opener) { opener.focus(); opener = null; }
  }

  function open(btn) {
    var ref = (btn.getAttribute('data-help') || '').split('.');
    if (ref.length !== 2) return;
    opener = btn;
    content.innerHTML = '<p class="muted">Loading…</p>';
    panel.hidden = false;
    fetch('/help/panel/' + encodeURIComponent(ref[0]) + '/' + encodeURIComponent(ref[1]),
          { credentials: 'same-origin' })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
      .then(function (html) { content.innerHTML = html; content.focus(); })
      .catch(function () { content.innerHTML = '<p class="muted">This help section couldn\'t be loaded.</p>'; });
  }

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.help-btn[data-help]');
    if (btn) { e.preventDefault(); open(btn); return; }
    if (e.target.closest('.help-panel-close')) close();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !panel.hidden) close();
  });
})();
