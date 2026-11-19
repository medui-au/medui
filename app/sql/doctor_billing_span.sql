SELECT
    MIN(CAST(s.ServiceDate AS DATE)) AS first_billing_day,
    MAX(CAST(s.ServiceDate AS DATE)) AS last_billing_day
FROM SERVICES s
INNER JOIN INVOICES i ON s.InvoiceID = i.InvoiceID
WHERE i.UserID = ?
  AND s.RecordStatus = 1
  AND i.RecordStatus <> 2
