---
title: Application Usage
area: Administration
roles: [admin]
reviewed: 2026-11-10
related: [privacy-review, setup]
---

**Doctor Data → Application Usage** shows what MedUI was used for, by whom and how often. It
reads MedUI's own usage record: one entry for each task someone set out to do, and one for each
call to an AI model. The record holds no patient details: only whether a task was about a
patient, yes or no. Only an administrator can see this page.

## The two tabs {#overview}

- **AI** covers AI runs (each run of a text model, from the AI panel, document buttons, the
  chatbots, scribe issue lists, the library or care plans) and scribe sessions (speech-to-text).
  The figures across the top are *AI runs*, *Local share*, *Reported cost*, *Failure rate* and
  *Scribe sessions*.
- **Non-AI** covers everything else: opening charts, searching, the inbox, messages, exports to
  Best Practice, reports, sign-ins and administration. The figures are *Tasks*, *People
  active*, *Charts opened*, *Messages sent*, *Exports to BP* and *Sign-ins*.

The filters on the right are the ones for the open tab. Each one applies to **everything** on
the tab: every figure, the chart and the table. For example, choosing a provider narrows the
AI runs, the cost and the failure rate all together. The *Showing only* line above the figures
lists the filters in use; remove one with its ×.

A scribe session has no pipeline and no pre-send privacy check. So a pipeline or privacy-check
filter leaves no scribe sessions, and a note says so. A provider or model filter applies to both
kinds: choose a speech-to-text model to see its scribe sessions.

If usage from before live recording began was imported (`flask usage import-history`), the
notes under the table say from when each detail is recorded. Tasks taken from the web server's
log have no person, so they count in the totals but not under anyone's name. Tick or untick them
under *Include*. A new installation has no imported history: everything is recorded live.

## Looking inside a figure {#drill-down}

1. **Click a figure** to see it broken down: *AI runs* by feature, *Local share* by provider,
   *Reported cost* by model, *Failure rate* by reason, *Scribe sessions* by person, and so on.
2. **Choose what to break it down by** with the buttons above the table, for example Feature,
   Provider, Model, Pipeline, Person or Privacy check.
3. **Click a row** to look inside it. That row becomes a filter (shown under *Showing only*), and
   the table moves to the next useful breakdown, for example from a feature to its pipelines.
4. **Show the records** lists the entries themselves, newest first, 50 to a page.

The browser's Back button steps back through these views. The address of a view can be saved
as a bookmark.

Staff are shown by name. To show permanent labels ("Doctor 2") instead, for example while
sharing your screen, turn off **Show names**. That switch affects this screen only: exports
still use labels unless you choose to include names.

## Exports {#exports}

**CSV**, **Markdown** and **PDF** export what is on the screen: the current breakdown, or all
the records of the current list (up to 20,000), with the filters written at the top. Exports
use staff labels. To include names, tick *Include staff names* and confirm. A named export is
personal information about staff and should stay inside the practice. Every export is recorded,
including whether it had names.
