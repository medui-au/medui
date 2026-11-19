-- Every eGFR result for one patient, oldest first, for the eGFR criterion
-- (ADR-104, app/services/egfr_criterion.py). Values are returned as the
-- laboratory wrote them ('52', '<5', '>90', '>^90'); the service reads them.
-- Parameters: patient_id x 2.
SELECT
    CAST(R.ReportDate AS DATE) AS ResultDate,
    TRIM(R.ResultValue)        AS ResultValue
FROM (
    SELECT IV.ReportDate, IV.ResultValue
    FROM INCOMINGVALUES IV
    INNER JOIN INCOMINGREPORTS IR ON IR.ReportId = IV.ReportId
    WHERE IR.InternalId = ?
      AND IV.LOINCCODE IN ('33914-3', '62238-1', '15423-7', '50210-4', 'AUSLAB^EGFR')
    UNION ALL
    SELECT RV.ReportDate, RV.ResultValue
    FROM REPORTVALUES RV
    WHERE RV.InternalId = ?
      AND RV.LOINCCODE IN ('33914-3', '62238-1', '15423-7', '50210-4', 'AUSLAB^EGFR')
) AS R
WHERE R.ReportDate IS NOT NULL
ORDER BY ResultDate;
