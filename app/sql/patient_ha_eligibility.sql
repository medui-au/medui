SELECT
    CASE
        WHEN UPPER(LatestHA.ACTIONTEXT) LIKE '%DECLINED%' THEN ''
        WHEN CAST(LatestHA.DUEDATE AS DATE) > CAST(GETDATE() AS DATE) THEN ''
        WHEN (
            SELECT (DATEDIFF(hour, p.DOB, GETDATE()) / 8766) 
            FROM PATIENTS p 
            WHERE p.InternalID = ?
        ) < 75 THEN ''
        WHEN EXISTS (
            SELECT 1
            FROM Invoices i
            INNER JOIN SERVICES s ON i.InvoiceID = s.InvoiceID
            WHERE i.Internalid = ?
              AND s.MBSItem = '707'
              AND s.RecordStatus < 10
              AND s.ServiceDate >= DATEADD(month, -12, GETDATE())
        ) THEN ''
        ELSE '707'
    END AS Result
FROM (
    SELECT TOP 1 ACTIONTEXT, DUEDATE
    FROM ACTIONS
    WHERE INTERNALID = ?
      AND (UPPER([ACTIONTEXT]) LIKE '%HA%' OR UPPER([ACTIONTEXT]) LIKE '%HEALTH ASSESSMENT%')
    ORDER BY ADDED DESC, DUEDATE DESC
) AS LatestHA;
