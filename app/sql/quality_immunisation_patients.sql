-- Distinct patients vaccinated per doctor in [?, ?). Kept separate from the
-- per-vaccine count query — a patient can receive multiple vaccines in one
-- visit, so COUNT(DISTINCT INTERNALID) can't be derived from rows grouped by
-- VACCINEID without double-counting.
SELECT
    USERID AS bpsdb_userid,
    COUNT(DISTINCT INTERNALID) AS patients
FROM IMMUNISATIONS
WHERE RECORDSTATUS = 1
  AND GIVENDATE >= ?
  AND GIVENDATE < ?
GROUP BY USERID
