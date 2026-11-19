SELECT
    FORMAT(CollectionDate, 'dd/MM/yy') AS CollectionDate,
    TestName,
    ReportID,
    IsInBox
FROM (
    SELECT
        Max(CollectionDate) AS CollectionDate,
        TestName,
        MAX(ReportID) AS ReportID,
        0 AS IsInBox
    FROM INVESTIGATIONS
    GROUP BY InternalId, TestName
    HAVING (InternalID = ?)
    UNION ALL
    SELECT
        Max(CollectionDate) AS CollectionDate,
        TestName,
        MAX(ReportID) AS ReportID,
        1 AS IsInBox
    FROM INCOMINGREPORTS
    GROUP BY InternalId, TestName
    HAVING (InternalID = ?)
) AS CombinedData
ORDER BY CAST(CollectionDate AS DATETIME) DESC;
