/**
 * sortable-table.js
 * Adds column sorting to any <table data-sortable> element.
 * Click a <th> to sort asc; click again for desc. A ▲/▼ indicator and
 * aria-sort attribute track the active column.
 */
(function () {
    'use strict';

    function cellValue(row, colIndex) {
        const cell = row.cells[colIndex];
        return cell ? (cell.dataset.sort || cell.textContent).trim() : '';
    }

    function compareValues(a, b) {
        const na = parseFloat(a);
        const nb = parseFloat(b);
        if (!isNaN(na) && !isNaN(nb)) return na - nb;
        return a.localeCompare(b, undefined, { sensitivity: 'base' });
    }

    function sortTable(table, colIndex, asc) {
        const tbody = table.tBodies[0];
        if (!tbody) return;
        const rows = Array.from(tbody.rows);
        rows.sort(function (ra, rb) {
            const cmp = compareValues(cellValue(ra, colIndex), cellValue(rb, colIndex));
            return asc ? cmp : -cmp;
        });
        rows.forEach(function (r) { tbody.appendChild(r); });
    }

    function initTable(table) {
        const headers = table.tHead ? Array.from(table.tHead.rows[0].cells) : [];
        headers.forEach(function (th, i) {
            th.style.cursor = 'pointer';
            th.style.userSelect = 'none';
            th.dataset.sortDir = '';

            th.addEventListener('click', function () {
                const asc = th.dataset.sortDir !== 'asc';
                // Reset all headers
                headers.forEach(function (h) {
                    h.dataset.sortDir = '';
                    h.removeAttribute('aria-sort');
                    h.querySelector('.sort-indicator') && (h.querySelector('.sort-indicator').textContent = '');
                });
                th.dataset.sortDir = asc ? 'asc' : 'desc';
                th.setAttribute('aria-sort', asc ? 'ascending' : 'descending');
                let indicator = th.querySelector('.sort-indicator');
                if (!indicator) {
                    indicator = document.createElement('span');
                    indicator.className = 'sort-indicator';
                    indicator.style.cssText = 'margin-left:0.3em;font-size:0.7em;opacity:0.7;';
                    th.appendChild(indicator);
                }
                indicator.textContent = asc ? ' ▲' : ' ▼';
                sortTable(table, i, asc);
            });
        });
    }

    function initSortableTables() {
        document.querySelectorAll('table[data-sortable]').forEach(initTable);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initSortableTables);
    } else {
        initSortableTables();
    }

    // Expose so dynamic pages can call it after injecting new tables
    window.initSortableTables = initSortableTables;
}());
