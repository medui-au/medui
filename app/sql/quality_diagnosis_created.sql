-- Diagnoses (PASTHISTORY) created per doctor in [?, ?), among currently-active
-- (RECORDSTATUS=1) rows. ITEMCODE = 0 is the "no coded item selected"
-- sentinel (free text only, not NULL); DETAILS is the free-text clarification
-- field (a deprecated `text` column, hence the cast to check emptiness).
SELECT
    CREATEDBY AS bpsdb_userid,
    COUNT(*) AS created,
    SUM(CASE WHEN ITEMCODE > 0 THEN 1 ELSE 0 END) AS created_with_itemcode,
    SUM(CASE WHEN CAST(DETAILS AS VARCHAR(MAX)) IS NOT NULL
              AND LEN(CAST(DETAILS AS VARCHAR(MAX))) > 0 THEN 1 ELSE 0 END) AS created_with_details
FROM PASTHISTORY
WHERE RECORDSTATUS = 1
  AND CREATED >= ?
  AND CREATED < ?
GROUP BY CREATEDBY
