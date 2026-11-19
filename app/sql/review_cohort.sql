-- Criterion review (ADR-109): the cohort, with name, age and the last visit.
WITH Cohort AS (
    -- Active patients with a visit in the last 24 months.
    SELECT P.INTERNALID
    FROM PATIENTS P
    WHERE P.PATIENTSTATUS = 1
      AND EXISTS (SELECT 1 FROM VISITS V WHERE V.INTERNALID = P.INTERNALID AND V.RECORDSTATUS = 1
                  AND V.VISITDATE >= DATEADD(MONTH, -24, GETDATE()))
)
SELECT
    P.INTERNALID                                             AS patient_id,
    TRIM(P.SURNAME) + ', ' + TRIM(P.FIRSTNAME)               AS patient,
    DATEDIFF(YEAR, P.DOB, GETDATE()) - CASE WHEN MONTH(P.DOB) > MONTH(GETDATE())
        OR (MONTH(P.DOB) = MONTH(GETDATE()) AND DAY(P.DOB) > DAY(GETDATE())) THEN 1 ELSE 0 END AS age,
    LV.VISITDATE                                             AS last_visit,
    LV.USERID                                                AS last_doctor_id,
    TRIM(U.FIRSTNAME) + ' ' + TRIM(U.SURNAME)                AS last_doctor
FROM Cohort C
JOIN PATIENTS P ON P.INTERNALID = C.INTERNALID
OUTER APPLY (SELECT TOP 1 V.VISITDATE, V.USERID FROM VISITS V
             WHERE V.INTERNALID = C.INTERNALID AND V.RECORDSTATUS = 1
             ORDER BY V.VISITDATE DESC) LV
LEFT JOIN USERS U ON U.USERID = LV.USERID;
