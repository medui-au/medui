-- Diagnoses (PASTHISTORY) edited (not deleted) per doctor in [?, ?) —
-- currently-active (RECORDSTATUS=1) rows whose UPDATED timestamp falls in
-- the window. Deletions (RECORDSTATUS=0) are excluded here deliberately —
-- BPSDB does retain UPDATED/UPDATEDBY on deleted rows too, so "who deleted
-- what, when" is tracked as a separate query (quality_diagnosis_deleted).
SELECT
    UPDATEDBY AS bpsdb_userid,
    COUNT(*) AS updated
FROM PASTHISTORY
WHERE RECORDSTATUS = 1
  AND UPDATED IS NOT NULL
  AND UPDATED >= ?
  AND UPDATED < ?
GROUP BY UPDATEDBY
