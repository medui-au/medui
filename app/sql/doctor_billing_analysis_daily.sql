SELECT
    CAST(s.ServiceDate AS DATE) AS service_day,
    i.UserID                    AS doctor_id,
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
  /*EXTRA_FILTERS*/
GROUP BY CAST(s.ServiceDate AS DATE), i.UserID
ORDER BY service_day
