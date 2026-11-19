-- Criterion review (ADR-109): the cohort's HbA1c results (as patient_hba1c_series; LOINC trimmed).
WITH Cohort AS (
    -- Active patients with a visit in the last 24 months.
    SELECT P.INTERNALID
    FROM PATIENTS P
    WHERE P.PATIENTSTATUS = 1
      AND EXISTS (SELECT 1 FROM VISITS V WHERE V.INTERNALID = P.INTERNALID AND V.RECORDSTATUS = 1
                  AND V.VISITDATE >= DATEADD(MONTH, -24, GETDATE()))
)
SELECT R.patient_id, CAST(R.ReportDate AS DATE) AS ResultDate, RTRIM(LTRIM(R.LoincCode)) AS Loinc,
       TRIM(R.ResultValue) AS ResultValue
FROM (
    SELECT IR.InternalId AS patient_id, IV.ReportDate, IV.LoincCode, IV.ResultValue
    FROM INCOMINGVALUES IV
    JOIN INCOMINGREPORTS IR ON IR.ReportId = IV.ReportId
    JOIN Cohort C ON C.INTERNALID = IR.InternalId
    WHERE RTRIM(LTRIM(IV.LOINCCODE)) IN ('59261-8', '4548-4', '17856-6', 'AUSLAB^A1C')
    UNION ALL
    SELECT RV.InternalId, RV.ReportDate, RV.LoincCode, RV.ResultValue
    FROM REPORTVALUES RV
    JOIN Cohort C ON C.INTERNALID = RV.InternalId
    WHERE RTRIM(LTRIM(RV.LOINCCODE)) IN ('59261-8', '4548-4', '17856-6', 'AUSLAB^A1C')
) R
WHERE R.ReportDate IS NOT NULL;
