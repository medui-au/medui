-- Ferritin, haemoglobin, B12 and serum folate results for one patient, newest first,
-- for the results an influence row names (ADR-108, app/services/influences.py).
-- Values, units, range and flag as the laboratory reported them. Parameters: patient_id x 2.
SELECT
    CASE
        WHEN RTRIM(LTRIM(R.LoincCode)) IN ('2276-4', '14723-1') THEN 'ferritin'
        WHEN RTRIM(LTRIM(R.LoincCode)) IN ('14685-2', '2132-9', '5271-2', '2170-9') THEN 'b12'
        WHEN RTRIM(LTRIM(R.LoincCode)) IN ('14732-2', '2284-8') THEN 'folate'
        ELSE 'haemoglobin'
    END AS Marker,
    CAST(R.ReportDate AS DATE)  AS ResultDate,
    TRIM(R.ResultValue)         AS ResultValue,
    TRIM(R.Units)               AS Units,
    TRIM(R.[Range])             AS RefRange,
    TRIM(R.AbnormalFlag)        AS Flag
FROM (
    SELECT IV.ReportDate, IV.LoincCode, IV.ResultValue, IV.Units, IV.[Range], IV.AbnormalFlag
    FROM INCOMINGVALUES IV
    INNER JOIN INCOMINGREPORTS IR ON IR.ReportId = IV.ReportId
    WHERE IR.InternalId = ?
      AND RTRIM(LTRIM(IV.LOINCCODE)) IN ('2276-4', '14723-1', '718-7', '14775-1', '30313-1', '14685-2', '2132-9', '5271-2', '2170-9', '14732-2', '2284-8')
    UNION ALL
    SELECT RV.ReportDate, RV.LoincCode, RV.ResultValue, RV.Units, RV.[Range], RV.AbnormalFlag
    FROM REPORTVALUES RV
    WHERE RV.InternalId = ?
      AND RTRIM(LTRIM(RV.LOINCCODE)) IN ('2276-4', '14723-1', '718-7', '14775-1', '30313-1', '14685-2', '2132-9', '5271-2', '2170-9', '14732-2', '2284-8')
) AS R
WHERE R.ReportDate IS NOT NULL
ORDER BY ResultDate DESC;
