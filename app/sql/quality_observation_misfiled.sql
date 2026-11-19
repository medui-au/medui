-- OBSERVATIONS rows whose DATANAME isn't Best Practice's own name for their
-- DATACODE: pulse filed as diastolic, cardiac-exam fields (RHYTHM, JVP, HS…) as
-- weight, and so on. Nearly all come from importing another practice's export
-- (CREATEDBY 0, one batch per patient). Queries that read observations by code
-- take them for the measurement the code means, so an imported pulse shows as a
-- diastolic blood pressure. Deleting one in BP sets RECORDSTATUS 3, which every
-- MedUI query excludes; it then drops off this list.
--
-- Names are compared without case, spaces, full stops or hyphens ("Head Circ."
-- = "HeadCirc"). Code 0 has no native measurement, so every row under it is
-- listed. A code not in the list below is listed too.
WITH native (code, name) AS (
    SELECT code, name FROM (VALUES
        (1, 'TEMP'), (2, 'PULSE'), (3, 'SYSTOLIC'), (4, 'DIASTOLIC'), (5, 'RESP'),
        (6, 'BSL'), (7, 'HEIGHT'), (8, 'WEIGHT'), (9, 'BMI'), (10, 'HEADCIRC'),
        (17, 'WAIST'), (18, 'HIP'), (19, 'INSPIRATION'), (20, 'EXPIRATION'),
        (21, 'WHRATIO'), (22, 'MMSE'), (23, 'MMSE'), (24, 'K10'), (26, 'DIABRISK'),
        (27, 'O2SAT'), (27, 'O2SATURATION'), (28, 'PEFR'), (29, 'CVRISK'),
        (30, 'AUDITC'), (31, 'DASS21DEPRESSION'), (31, 'PND'),
        (32, 'DASS21ANXIETY'), (33, 'DASS21STRESS')
    ) AS v (code, name)
)
SELECT
    o.RECORDID                         AS record_id,
    o.INTERNALID                       AS patient_id,
    RTRIM(p.FIRSTNAME)                 AS firstname,
    RTRIM(p.SURNAME)                   AS surname,
    o.DATACODE                         AS datacode,
    RTRIM(o.DATANAME)                  AS dataname,
    o.DATAVALUE                        AS datavalue,
    o.OBSDATE                          AS obs_date,
    o.CREATED                          AS created,
    o.CREATEDBY                        AS created_by,
    o.RECORDSTATUS                     AS record_status,
    RTRIM(ISNULL(u.FIRSTNAME, '')) + ' ' + RTRIM(ISNULL(u.SURNAME, '')) AS entered_by,
    u.USERID AS entered_by_id
FROM OBSERVATIONS o
LEFT JOIN native n
       ON n.code = o.DATACODE
      AND n.name = UPPER(REPLACE(REPLACE(REPLACE(RTRIM(o.DATANAME), ' ', ''), '.', ''), '-', ''))
LEFT JOIN PATIENTS p ON p.INTERNALID = o.INTERNALID
LEFT JOIN USERS u ON u.USERID = o.CREATEDBY
WHERE o.RECORDSTATUS < 2
  AND n.code IS NULL
ORDER BY o.INTERNALID, o.CREATED, o.DATACODE
