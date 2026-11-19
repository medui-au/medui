-- Age-at-vaccination bands per doctor in [?, ?): <18, 19-50, 51+. Age is
-- computed from PATIENTS.DOB as at GIVENDATE (not today), using the same
-- month/day-adjusted DATEDIFF pattern used throughout MedUI for patient
-- age. A CTE is needed because SQL Server won't let a CASE expression in the
-- same SELECT reference another column's alias.
WITH Ages AS (
    SELECT
        I.USERID AS bpsdb_userid,
        DATEDIFF(YEAR, P.DOB, I.GIVENDATE)
            - CASE WHEN MONTH(P.DOB) > MONTH(I.GIVENDATE)
                     OR (MONTH(P.DOB) = MONTH(I.GIVENDATE) AND DAY(P.DOB) > DAY(I.GIVENDATE))
                   THEN 1 ELSE 0 END AS age
    FROM IMMUNISATIONS I
    INNER JOIN PATIENTS P ON I.INTERNALID = P.InternalId
    WHERE I.RECORDSTATUS = 1
      AND I.GIVENDATE >= ?
      AND I.GIVENDATE < ?
)
-- Band edges: age 18 counts as "<18" (i.e. <=18) so the three bands
-- partition every age with no gap.
SELECT
    bpsdb_userid,
    SUM(CASE WHEN age <= 18 THEN 1 ELSE 0 END) AS age_lt_18,
    SUM(CASE WHEN age BETWEEN 19 AND 50 THEN 1 ELSE 0 END) AS age_19_50,
    SUM(CASE WHEN age >= 51 THEN 1 ELSE 0 END) AS age_51_plus
FROM Ages
GROUP BY bpsdb_userid
