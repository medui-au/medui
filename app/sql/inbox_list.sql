SELECT TOP 500
    ir.ReportID                                         AS report_id,
    ir.InternalId                                       AS internal_id,
    ir.UserId                                           AS user_id,
    FORMAT(ir.CollectionDate, 'dd/MM/yy')               AS collection_date,
    ir.CollectionDate                                   AS collection_date_raw,
    RTRIM(LTRIM(ir.FIRSTNAME)) + ' ' + RTRIM(LTRIM(ir.SURNAME)) AS patient_name,
    LEFT(COALESCE(NULLIF(TRIM(ir.TESTNAME), ''),
                  NULLIF(TRIM(ir.SUBJECT),  ''),
                  NULLIF(TRIM(ir.CATEGORY), ''), ''), 40) AS test_name,
    TRIM(u.FIRSTNAME) + ' ' + TRIM(u.SURNAME)          AS doctor_name,
    ir.STOREIN                                          AS store_in,
    COALESCE(
        (SELECT TOP 1 DATALENGTH(irp.CONTENT)
         FROM BPSDOCUMENTSINBOX.dbo.INCOMINGREPORTPAGES irp
         WHERE irp.REPORTID = ir.ReportID),
        DATALENGTH(ir.REPORTHEADER) + DATALENGTH(ir.REPORTBODY)
    )                                                    AS content_size
FROM   Incomingreports ir
LEFT   JOIN USERS u ON ir.USERID = u.USERID
WHERE  ir.Recordstatus = 1
ORDER  BY ir.ReportId DESC
