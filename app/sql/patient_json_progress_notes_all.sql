SELECT
    CONVERT(VARCHAR(10), V.VisitDate, 23) AS VisitDate,
    -- Doctors keep their name, for the HCP pass to tokenise downstream. Everyone
    -- else is named by role: receptionists and nurses are not in the address
    -- book the HCP pass reads, so their names reached the model unredacted.
    -- UserId 0 is BP's blank user that notes imported from another practice
    -- are filed under (the outside author is in VISITS.DRNAME, not selected).
    -- Group names from BP's USERGROUPS table.
    CASE
        WHEN V.UserId = 0 THEN 'Previous Doctor'
        WHEN U.GroupCode IN (3, 4, 42) THEN TRIM(U.FirstName) + ' ' + TRIM(U.Surname)
        WHEN U.GroupCode = 28 THEN 'Nurse practitioner'
        WHEN U.GroupCode = 5 THEN 'Nurse'
        WHEN U.GroupCode IN (6, 7) THEN 'Receptionist'
        WHEN U.GroupCode = 1 THEN 'Practice manager'
        ELSE 'Staff'
    END AS Doctor,
    CASE WHEN U.GroupCode IN (3, 4, 42) THEN V.UserId END AS DoctorUserId,   -- doctors only: swapped for a preferred name, then dropped (ADR-106)
    CAST(V.VisitNotes AS VARCHAR(MAX)) AS VisitNotes,
    R.Reason
FROM VISITS V
INNER JOIN USERS U ON V.UserId = U.UserId
-- One row per visit: a visit with several reasons used to come back once per
-- reason, sending the whole note again each time (and leaving "TOP 5" with
-- fewer than five visits).
OUTER APPLY (
    SELECT STRING_AGG(TRIM(VR.Reason), '; ') AS Reason
    FROM VISITREASON VR
    WHERE VR.VISITID = V.VISITID
) R
WHERE V.InternalId = ?
    AND V.RecordStatus = 1
    AND V.VisitNotes IS NOT NULL
ORDER BY V.VisitDate DESC;
