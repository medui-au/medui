-- OBSERVATIONS rows whose value is not a plain number, for the measurements
-- Best Practice doesn't check at entry: systolic (3), diastolic (4), height (7),
-- weight (8), BMI (9, named 'BMI'; pulse shares the code) and head
-- circumference (10). A stray character there ("72kg", "1.6 m", "120/") makes
-- any query that converts the value fail, and the demographics query that loads
-- a patient's identifiers for redaction is one of them.
--
-- Every row under codes 3, 4, 7, 8 and 10 is checked whatever its DATANAME:
-- a few other observations are filed under those codes, and the queries that
-- read them select by code alone. RECORDSTATUS 0 is included because those
-- queries read RECORDSTATUS < 2.
--
-- "Not a plain number" is tested by pattern, not TRY_CONVERT: the BP database
-- runs at compatibility level 100, which doesn't have it. A value is flagged when
-- it holds anything but digits and a decimal point, or more than one point.
SELECT
    o.RECORDID                         AS record_id,
    o.INTERNALID                       AS patient_id,
    RTRIM(p.FIRSTNAME)                 AS firstname,
    RTRIM(p.SURNAME)                   AS surname,
    o.DATACODE                         AS datacode,
    RTRIM(o.DATANAME)                  AS dataname,
    o.DATAVALUE                        AS datavalue,
    o.OBSDATE                          AS obs_date,
    o.RECORDSTATUS                     AS record_status,
    RTRIM(ISNULL(u.FIRSTNAME, '')) + ' ' + RTRIM(ISNULL(u.SURNAME, '')) AS entered_by,
    u.USERID AS entered_by_id
FROM OBSERVATIONS o
LEFT JOIN PATIENTS p ON p.INTERNALID = o.INTERNALID
LEFT JOIN USERS u ON u.USERID = o.USERID
WHERE o.RECORDSTATUS < 2
  AND (o.DATACODE IN (3, 4, 7, 8, 10)
       OR (o.DATACODE = 9 AND RTRIM(o.DATANAME) = 'BMI'))
  AND o.DATAVALUE IS NOT NULL
  AND LTRIM(RTRIM(o.DATAVALUE)) <> ''
  AND (LTRIM(RTRIM(o.DATAVALUE)) LIKE '%[^0-9.]%'
       OR LTRIM(RTRIM(o.DATAVALUE)) LIKE '%.%.%'
       OR LTRIM(RTRIM(o.DATAVALUE)) = '.')
ORDER BY o.DATACODE, o.OBSDATE DESC
