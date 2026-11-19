SELECT
    s.MBSItem               AS mbs_item,
    COUNT(s.MBSItem)        AS item_count,
    SUM(s.Fee) / 100.0      AS total_fee,
    MAX(s.Description)      AS description
FROM SERVICES s
INNER JOIN INVOICES i ON s.InvoiceID = i.InvoiceID
WHERE s.ServiceDate >= ?
  AND s.ServiceDate <= ?
  AND s.RecordStatus = 1
  AND i.RecordStatus <> 2
  AND (? IS NULL OR i.UserID = ?)
GROUP BY s.MBSItem
ORDER BY SUM(s.Fee) DESC

