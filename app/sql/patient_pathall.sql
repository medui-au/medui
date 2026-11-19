SELECT TOP 500
    FORMAT(CollectionDate, 'dd/MM/yy') AS CollectionDate,
    TestName,
    ReportID,
    IsInBox
FROM (
    SELECT CollectionDate, TestName, ReportID, 0 AS IsInBox
    FROM INVESTIGATIONS
    WHERE InternalID = ?
    UNION ALL
    SELECT CollectionDate, TestName, ReportID, 1 AS IsInBox
    FROM INCOMINGREPORTS
    WHERE InternalID = ?
) AS CombinedData
ORDER BY CAST(CollectionDate AS DATETIME) DESC;
