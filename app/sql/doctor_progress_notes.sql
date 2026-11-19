-- Current visits only: RecordStatus 2 and 3 are notes deleted or replaced in BP.
SELECT TOP 200
    p.InternalId                                                         AS patient_id,
    RTRIM(LTRIM(p.FirstName)) + ' ' + RTRIM(LTRIM(p.Surname))           AS patient_name,
    CONVERT(VARCHAR(10), p.DOB, 103)                                     AS dob,
    CONVERT(VARCHAR(10), v.VisitDate, 103)                               AS visit_date,
    v.VisitDate                                                          AS visit_date_raw,
    v.StartTime                                                          AS start_time,
    COALESCE(RTRIM(LTRIM(v.DrName)), '')                                 AS dr_name,
    v.VisitNotes                                                         AS visit_notes
FROM VISITS v
INNER JOIN Patients p ON p.INTERNALID = v.INTERNALID
WHERE v.VisitDate >= ?
  AND v.VisitDate <= ?
  AND v.RecordStatus = 1
  AND v.VisitNotes IS NOT NULL
  AND (? IS NULL OR v.USERID = ?)
  AND (? IS NULL OR CAST(v.VisitNotes AS VARCHAR(MAX)) LIKE ?)
ORDER BY v.VisitDate DESC, v.StartTime DESC
