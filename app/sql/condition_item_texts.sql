-- How this practice records each past-history item (ADR-183): for each item code, each
-- text it is recorded with and how many entries use it. Only texts used by at least 3
-- entries, so one patient's own wording never comes back. Code, text and count only: no
-- patient columns. Used only to fill condition_codes.practice_item, for reading. No parameters.
SELECT ITEMCODE, TRIM(ITEMTEXT) AS ITEMTEXT, COUNT(*) AS N
FROM BPSPatients.dbo.PASTHISTORY
WHERE ITEMCODE > 0 AND ITEMTEXT IS NOT NULL AND LTRIM(RTRIM(ITEMTEXT)) <> ''
GROUP BY ITEMCODE, TRIM(ITEMTEXT)
HAVING COUNT(*) >= 3;
