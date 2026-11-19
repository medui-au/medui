-- A user's patient visits (ADR-125): every visit type except BP's "Non visit" (12) and
-- the blank type (0). Counts and the first date only.
SELECT
    COUNT(*)                    AS visits,
    COUNT(DISTINCT v.INTERNALID) AS patients,
    MIN(v.VISITDATE)            AS first_visit
FROM VISITS v
WHERE v.USERID = ? AND v.RECORDSTATUS = 1 AND v.VISITCODE NOT IN (0, 12)
