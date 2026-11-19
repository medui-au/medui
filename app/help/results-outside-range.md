---
title: Results outside range
area: Day sheet and inbox
roles: [doctor, nurse]
reviewed: 2026-11-03
related: []
---

**Inbox → Results Outside Range** lists pathology results in the doctors' inboxes that are
outside their reference range, as the laboratory reported it, and opens a page of charts for
each patient. It shows what the laboratory sent; it doesn't grade, rank or interpret results.

## What is listed {#what-is-listed}

The most recent inbox result for each patient and test, when it is outside its reference
range in either of two ways:

- **Lab flag:** the laboratory flagged it. The flag is shown as sent, marked *(lab)*.
- **Above / below range:** the laboratory sent no flag, and the value is outside the range
  it reported with the result.

A result the laboratory sent without a flag or a range isn't listed, because there is nothing
to compare it with. So the list doesn't contain every result that matters: it is a way into
the inbox, not a replacement for reading it. The reports themselves remain the record.

## Reading the list {#reading-the-list}

| Column | Shows |
|---|---|
| Patient | Opens the patient's summary |
| Test | Opens the patient's charts page (below) |
| Value, Range | The result and the reference range, as the laboratory reported them |
| Date | The date of the result |
| Flag | The laboratory's flag *(lab)*, or *above / below range* |
| Previous | Earlier results for the same test, as reported |

The list is sorted by date, newest first, then by patient. It covers all doctors' inboxes.
Nothing on it is ordered by how far out of range a result is.

## The charts page {#charts}

Clicking a test opens **Results outside range** for that patient. Each chart shows all of the
patient's results for one test. A test the laboratory reported under more than one name or
code is drawn as one chart, but a percentage and a count are always separate charts, even
under the same name (monocytes as % and as ×10⁹/L, for example).

- **The shaded band** is the reference range the laboratory reported with the most recent
  result. Ranges can change between laboratories and over time, so older points may have
  had a different range.
- **The latest result** is marked, and the caption under the chart gives it with its range
  and date, then the previous results.

The charts come in three groups:

1. **In the inbox:** the test you clicked first, then the patient's other inbox results
   outside range.
2. **Outside range when last tested (not in the latest results):** tests that aren't in the
   inbox now, whose last result was outside range.
3. **Last tested more than 5 years ago:** the same, for tests last done more than five years
   ago, folded away until you open them.

Links at the top go back to the list, to the **Patient summary**, and to **All results
charts** for every test the patient has had.

## What it doesn't do {#limits}

- It doesn't decide what is urgent or what to do: there are no grades, scores or alerts of
  MedUI's own.
- It doesn't replace reading the report: comments, interpretive notes and results without a
  range are only in the report.
- It shows inbox results only; results filed elsewhere in the record appear in the charts,
  not in the list.
