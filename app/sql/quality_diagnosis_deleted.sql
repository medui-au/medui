-- Diagnoses (PASTHISTORY) deleted per doctor in [?, ?) — RECORDSTATUS=0 rows
-- whose UPDATED timestamp (the deletion time) falls in the window. BPSDB
-- retains UPDATED/UPDATEDBY on deleted rows, recording who deleted them and
-- when (deletion is implemented as an update that sets RECORDSTATUS=0).
SELECT
    UPDATEDBY AS bpsdb_userid,
    COUNT(*) AS deleted
FROM PASTHISTORY
WHERE RECORDSTATUS = 0
  AND UPDATED IS NOT NULL
  AND UPDATED >= ?
  AND UPDATED < ?
GROUP BY UPDATEDBY
