/* Warn before leaving a page with unsaved changes (ADR-177). A form opts in with
 * data-unsaved-guard; any change to it marks the page unsaved, and submitting it clears that. */
(function () {
  'use strict';
  let dirty = false;
  document.querySelectorAll('form[data-unsaved-guard]').forEach((form) => {
    form.addEventListener('input', () => { dirty = true; });
    form.addEventListener('change', () => { dirty = true; });
    form.addEventListener('submit', () => { dirty = false; });
  });
  document.querySelectorAll('form:not([data-unsaved-guard])').forEach((form) => {
    // Another form on the page (e.g. Discard) leaves on purpose.
    form.addEventListener('submit', () => { dirty = false; });
  });
  window.addEventListener('beforeunload', (e) => {
    if (!dirty) return;
    e.preventDefault();
    e.returnValue = '';   // the browser shows its own "leave page?" message
  });
}());
