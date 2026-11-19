SELECT TOP 1000
    ReportID,
    RequestDate,
    FORMAT(CollectionDate, 'dd/MM/yy') AS CollectionDate,
    FORMAT(ReportDate, 'dd/MM/yy')     AS ReportDate,
    TRIM(ProviderName)                 AS ProviderName,
    TRIM(TestName)                     AS TestName,
    IsInBox
FROM (
    SELECT RequestDate, CollectionDate, ReportDate, ProviderName, TestName, ReportID, 0 AS IsInBox
    FROM INVESTIGATIONS
    WHERE InternalID = ?
    UNION ALL
    SELECT RequestDate, CollectionDate, ReportDate, ProviderName, TestName, ReportID, 1 AS IsInBox
    FROM INCOMINGREPORTS
    WHERE InternalID = ?
) AS CombinedData
ORDER BY CAST(ReportDate AS DATETIME) DESC;
