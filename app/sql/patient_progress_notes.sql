-- Current visits only: RecordStatus 2 and 3 are notes deleted or replaced in BP.
SELECT
    CONVERT(VARCHAR(10), v.VisitDate, 103) AS VisitDateFormatted,
    v.VisitDate                            AS VisitDateRaw,
    v.StartTime,
    COALESCE(TRIM(v.DrName), '')           AS DrName,
    v.VisitNotes
FROM VISITS v
WHERE v.INTERNALID = ?
AND   v.RecordStatus = 1
AND   v.VisitDate IS NOT NULL
ORDER BY v.VisitDate DESC, v.StartTime DESC
