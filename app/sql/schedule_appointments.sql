-- Schedule: Appointments for a given date
-- Parameter 1 (?): Target date in ISO format (yyyy-MM-dd). CAST to DATE for safe comparison.
--
-- Key differences from legacy query:
--   - No SET DATEFORMAT / SET CONCAT_NULL_YIELDS_NULL preamble (incompatible with
--     single-statement cursor.execute in Gen3 BaseRepository).
--   - Date comparison uses CAST(? AS DATE) with an ISO date string instead of DATEDIFF + dmy string.
--   - Nullable name concatenations wrapped in COALESCE to avoid NULL propagation.
--   - row_class column computed in SQL so Jinja can apply colours without JS logic.
--   - No ORDER BY or provider filter here; both appended by ScheduleRepository.

SELECT
    LEFT(CONVERT(varchar, DATEADD(second, APPOINTMENTS.APPOINTMENTTIME, APPOINTMENTS.APPOINTMENTDATE), 113), 17) AS APPT_TIME,
    COALESCE(LEFT(USERS.FIRSTNAME, 1), '') + COALESCE(LEFT(USERS.SURNAME, 1), '') +
        CASE WHEN RIGHT(RTRIM(COALESCE(USERS.SURNAME, '')), 3) = '(K)' THEN '(K)' ELSE '' END AS Provider,
    USERS.USERID                                                          AS provider_id,
    APPOINTMENTS.INTERNALID                                               AS internalid,
    RTRIM(LTRIM(COALESCE(PATIENTS.FIRSTNAME, ''))) + ' ' +
        RTRIM(LTRIM(COALESCE(PATIENTS.SURNAME, '')))                      AS patient_name,
    LEFT(CONVERT(varchar, PATIENTS.DOB, 103), 10)                        AS dob,
    ISNULL(PATIENTS.HOMEPHONE, '-')                                       AS home_phone,
    ISNULL(PATIENTS.MOBILEPHONE, '-')                                     AS mobile_phone,
    APPOINTMENTS.REASON                                                   AS reason,
    CAST(APPOINTMENTS.APPOINTMENTLENGTH / 60 AS VARCHAR(4)) + ' mins'    AS visit_length,
    APPOINTMENTS.APPOINTMENTCODE                                          AS appt_code,
    APPOINTMENTS.RECORDSTATUS                                             AS status_code,
    COALESCE(LEFT(U2.FIRSTNAME, 1), '') + COALESCE(LEFT(U2.SURNAME, 1), '') AS booker,
    CONVERT(VARCHAR, DATEDIFF(dd, APPOINTMENTS.CREATED, GETDATE())) + ' days ago' AS created_age,
    PATIENTS.PENSIONCODE                                                  AS pension_code,
    Eligibility.Status                                                    AS eligibility,
    CASE APPOINTMENTS.APPOINTMENTCODE
        WHEN 1  THEN 'appt-booked'
        WHEN 2  THEN 'appt-active'
        WHEN 3  THEN 'appt-active'
        WHEN 4  THEN 'appt-active'
        WHEN 5  THEN 'appt-done'
        WHEN 10 THEN 'appt-dna'
        WHEN 12 THEN 'appt-unavail'
        WHEN 13 THEN 'appt-unavail'
        ELSE ''
    END AS row_class
FROM APPOINTMENTS
INNER JOIN APPOINTMENTCODES
    ON APPOINTMENTS.APPOINTMENTCODE = APPOINTMENTCODES.APPOINTMENTCODE
LEFT OUTER JOIN PATIENTS
    ON APPOINTMENTS.INTERNALID = PATIENTS.INTERNALID
INNER JOIN USERS U2
    ON APPOINTMENTS.BOOKEDBY = U2.USERID
LEFT OUTER JOIN USERS
    ON APPOINTMENTS.USERID = USERS.USERID
OUTER APPLY (
    SELECT
        CASE
            WHEN APPOINTMENTS.INTERNALID <= 0 OR APPOINTMENTS.INTERNALID IS NULL THEN ''
            WHEN MaxDate721 IS NULL AND MaxDate965 IS NULL AND MaxDate967 IS NULL THEN 'None Prior'
            WHEN MaxDate965 > DATEADD(month, -3, GETDATE())
              OR MaxDate967 > DATEADD(month, -3, GETDATE()) THEN 'Neither'
            WHEN MaxDate721 > COALESCE(MaxDate965, '1900-01-01')
             AND MaxDate721 > COALESCE(MaxDate967, '1900-01-01') THEN '965'
            WHEN MaxDate965 <= DATEADD(month, -12, GETDATE()) THEN '965'
            WHEN MaxDate965 <= DATEADD(month, -3,  GETDATE()) THEN '967'
            ELSE 'None Prior'
        END AS Status
    FROM (
        SELECT
            MAX(CASE WHEN S.MBSITEM = '721' THEN S.SERVICEDATE END) AS MaxDate721,
            MAX(CASE WHEN S.MBSITEM IN ('392', '965') THEN S.SERVICEDATE END) AS MaxDate965,
            MAX(CASE WHEN S.MBSITEM IN ('393', '967') THEN S.SERVICEDATE END) AS MaxDate967
        FROM INVOICES I
        INNER JOIN SERVICES S ON I.INVOICEID = S.INVOICEID
        WHERE I.INTERNALID = APPOINTMENTS.INTERNALID
          AND S.SERVICEDATE > DATEADD(year, -10, GETDATE())
          AND S.MBSITEM IN ('721', '965', '967', '392', '393')
          AND I.RECORDSTATUS <> 2
    ) AS Summary
) AS Eligibility
WHERE CAST(APPOINTMENTS.APPOINTMENTDATE AS DATE) = CAST(? AS DATE)
  AND APPOINTMENTS.RECORDSTATUS = 1
