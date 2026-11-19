-- Every HbA1c result for one patient, oldest first, for the HbA1c criterion
-- (ADR-107, app/services/hba1c_criterion.py). Values as the laboratory wrote them.
-- BP pads LOINC codes with spaces: trimmed here, so 59261-8 (mmol/mol) is told
-- apart from the percentage codes. Parameters: patient_id x 2.
SELECT
    CAST(R.ReportDate AS DATE)        AS ResultDate,
    RTRIM(LTRIM(R.LoincCode))         AS Loinc,
    TRIM(R.ResultValue)               AS ResultValue
FROM (
    SELECT IV.ReportDate, IV.LoincCode, IV.ResultValue
    FROM INCOMINGVALUES IV
    INNER JOIN INCOMINGREPORTS IR ON IR.ReportId = IV.ReportId
    WHERE IR.InternalId = ?
      AND RTRIM(LTRIM(IV.LOINCCODE)) IN ('59261-8', '4548-4', '17856-6', 'AUSLAB^A1C')
    UNION ALL
    SELECT RV.ReportDate, RV.LoincCode, RV.ResultValue
    FROM REPORTVALUES RV
    WHERE RV.InternalId = ?
      AND RTRIM(LTRIM(RV.LOINCCODE)) IN ('59261-8', '4548-4', '17856-6', 'AUSLAB^A1C')
) AS R
WHERE R.ReportDate IS NOT NULL
ORDER BY ResultDate;
