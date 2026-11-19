-- Criterion review (ADR-109): the cohort's eGFR results (as patient_egfr_series).
WITH Cohort AS (
    -- Active patients with a visit in the last 24 months.
    SELECT P.INTERNALID
    FROM PATIENTS P
    WHERE P.PATIENTSTATUS = 1
      AND EXISTS (SELECT 1 FROM VISITS V WHERE V.INTERNALID = P.INTERNALID AND V.RECORDSTATUS = 1
                  AND V.VISITDATE >= DATEADD(MONTH, -24, GETDATE()))
)
SELECT R.patient_id, CAST(R.ReportDate AS DATE) AS ResultDate, TRIM(R.ResultValue) AS ResultValue
FROM (
    SELECT IR.InternalId AS patient_id, IV.ReportDate, IV.ResultValue
    FROM INCOMINGVALUES IV
    JOIN INCOMINGREPORTS IR ON IR.ReportId = IV.ReportId
    JOIN Cohort C ON C.INTERNALID = IR.InternalId
    WHERE IV.LOINCCODE IN ('33914-3', '62238-1', '15423-7', '50210-4', 'AUSLAB^EGFR')
    UNION ALL
    SELECT RV.InternalId, RV.ReportDate, RV.ResultValue
    FROM REPORTVALUES RV
    JOIN Cohort C ON C.INTERNALID = RV.InternalId
    WHERE RV.LOINCCODE IN ('33914-3', '62238-1', '15423-7', '50210-4', 'AUSLAB^EGFR')
) R
WHERE R.ReportDate IS NOT NULL;
