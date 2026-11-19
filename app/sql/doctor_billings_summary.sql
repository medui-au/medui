SELECT
    COUNT(s.MBSItem)            AS total_items,
    SUM(s.Fee) / 100.0          AS total_fees,
    COUNT(DISTINCT s.InvoiceID) AS total_visits
FROM SERVICES s
INNER JOIN INVOICES i ON s.InvoiceID = i.InvoiceID
WHERE s.ServiceDate >= ?
  AND s.ServiceDate <= ?
  AND s.RecordStatus = 1
  AND i.RecordStatus <> 2
  AND (? IS NULL OR i.UserID = ?)

