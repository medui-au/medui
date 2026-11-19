-- Schedule: Daysheet (completed services/attendances) for a given date
-- Parameter 1 (?): Target date in ISO format (yyyy-MM-dd). CAST to DATE for safe comparison.
--
-- Key differences from legacy query:
--   - No SET DATEFORMAT preamble.
--   - Date comparison uses CAST(? AS DATE) instead of DATEDIFF + dmy string.
--   - Nullable name concatenations use COALESCE.
--   - row_class computed in SQL for Jinja colour coding.
--   - No ORDER BY or provider filter; both appended by ScheduleRepository.

SELECT
    COALESCE(LEFT(USERS.FIRSTNAME, 1), '') + COALESCE(LEFT(USERS.SURNAME, 1), '') +
        CASE WHEN RIGHT(RTRIM(COALESCE(USERS.SURNAME, '')), 3) = '(K)' THEN '(K)' ELSE '' END AS UserName,
    USERS.USERID                                                    AS provider_id,
    LEFT(CONVERT(varchar, SERVICES.CREATED, 113), 17)              AS DateofService,
    INVOICES.INTERNALID                                             AS internalid,
    RTRIM(LTRIM(COALESCE(PATIENTS.FIRSTNAME, ''))) + ' ' +
        RTRIM(LTRIM(COALESCE(PATIENTS.SURNAME, '')))               AS patient_name,
    LEFT(CONVERT(varchar, PATIENTS.DOB, 103), 10)                  AS dob,
    SERVICES.MBSITEM                                               AS mbs_item,
    CAST(SERVICES.FEE AS FLOAT) / 100                              AS fee,
    INVOICES.INVOICEID                                             AS invoice_id,
    INVOICES.RECORDSTATUS                                          AS invoice_status,
    SERVICES.SERVICESTATUS                                         AS service_status,
    CASE SERVICES.SERVICESTATUS
        WHEN 1 THEN 'appt-done'
        ELSE ''
    END AS row_class
FROM INVOICES
INNER JOIN SERVICES ON INVOICES.INVOICEID = SERVICES.INVOICEID
INNER JOIN PATIENTS ON INVOICES.INTERNALID = PATIENTS.INTERNALID
INNER JOIN USERS    ON INVOICES.USERID = USERS.USERID
WHERE CAST(SERVICES.SERVICEDATE AS DATE) = CAST(? AS DATE)
  AND INVOICES.RECORDSTATUS <> 2
  AND SERVICES.RECORDSTATUS = 1
