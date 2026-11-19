-- Prescriptions (CURRENTRX) created per doctor in [?, ?) — the denominator
-- for "medications ceased as a % of prescriptions created".
SELECT
    CREATEDBY AS bpsdb_userid,
    COUNT(*) AS created
FROM CURRENTRX
WHERE CREATED >= ?
  AND CREATED < ?
GROUP BY CREATEDBY
