WITH AST_ALT_Results AS (
    -- Select AST and ALT values performed on the same day
    SELECT
        CombinedResults.ReportDate,
        MAX(CASE WHEN CombinedResults.LOINCCODE = '1920-8' THEN RTRIM(CombinedResults.ResultValue) END) AS AST,
        MAX(CASE WHEN CombinedResults.LOINCCODE IN ('1744-2', '1742-6', '1743-4') THEN RTRIM(CombinedResults.ResultValue) END) AS ALT,
        Patients.DOB,
        FLOOR(DATEDIFF(day, Patients.DOB, CombinedResults.ReportDate) / 365.25) AS Age
    FROM (
        -- For IncomingValues table, join through IncomingReports to get InternalId
        SELECT
            iv.ReportDate,
            iv.LOINCCODE,
            RTRIM(iv.ResultValue) AS ResultValue,
            ir.InternalId
        FROM IncomingValues iv
        JOIN IncomingReports ir ON iv.ReportId = ir.ReportId
        WHERE ir.InternalId = ?
        AND iv.LOINCCODE IN ('777-3', 'AUSLAB^PLT', '1744-2', '1742-6', '1743-4', '1920-8')
        
        UNION
        
        -- For REPORTVALUES table, we can directly join by InternalId
        SELECT
            rv.ReportDate,
            rv.LOINCCODE,
            RTRIM(rv.ResultValue) AS ResultValue,
            rv.InternalId
        FROM REPORTVALUES rv
        WHERE rv.InternalId = ?
        AND rv.LOINCCODE IN ('777-3', 'AUSLAB^PLT', '1744-2', '1742-6', '1743-4', '1920-8')
    ) AS CombinedResults
    JOIN Patients ON CombinedResults.InternalId = Patients.InternalId
    GROUP BY CombinedResults.ReportDate, Patients.DOB
    HAVING MAX(CASE WHEN CombinedResults.LOINCCODE = '1920-8' THEN CombinedResults.ResultValue END) IS NOT NULL
    AND MAX(CASE WHEN CombinedResults.LOINCCODE IN ('1744-2', '1742-6', '1743-4') THEN CombinedResults.ResultValue END) IS NOT NULL
),
PLT_Results AS (
    -- Select PLT values from any date within 30 days of the AST/ALT date
    SELECT
        iv.ReportDate AS PLT_ReportDate,
        RTRIM(iv.ResultValue) AS PLT,
        ir.InternalId
    FROM IncomingValues iv
    JOIN IncomingReports ir ON iv.ReportId = ir.ReportId
    WHERE ir.InternalId = ?
    AND iv.LOINCCODE IN ('777-3', 'AUSLAB^PLT')
    UNION
    SELECT
        rv.ReportDate AS PLT_ReportDate,
        RTRIM(rv.ResultValue) AS PLT,
        rv.InternalId
    FROM REPORTVALUES rv
    WHERE rv.InternalId = ?
    AND rv.LOINCCODE IN ('777-3', 'AUSLAB^PLT')
),
Ranked_PLT_Results AS (
    SELECT
        PLT_Results.PLT_ReportDate,
        PLT_Results.PLT,
        AST_ALT_Results.ReportDate,
        ROW_NUMBER() OVER (
            PARTITION BY AST_ALT_Results.ReportDate
            ORDER BY
                CASE
                    WHEN PLT_Results.PLT_ReportDate = AST_ALT_Results.ReportDate THEN 0
                    ELSE ABS(DATEDIFF(day, PLT_Results.PLT_ReportDate, AST_ALT_Results.ReportDate))
                END ASC
        ) AS RN
    FROM PLT_Results
    JOIN AST_ALT_Results
        ON PLT_Results.InternalId = ?
        AND ABS(DATEDIFF(day, PLT_Results.PLT_ReportDate, AST_ALT_Results.ReportDate)) <= 30
)
SELECT
    '98491-4' AS LoincCode,
    'FIB4' AS ResultName,
    CASE
        WHEN TRY_CAST(AST_ALT_Results.Age AS INT) IS NULL OR
             TRY_CAST(Ranked_PLT_Results.PLT AS INT) IS NULL OR
             TRY_CAST(AST_ALT_Results.AST AS INT) IS NULL OR
             TRY_CAST(AST_ALT_Results.ALT AS INT) IS NULL
        THEN 'invalid'
        ELSE CAST(ROUND((AST_ALT_Results.Age * CAST(AST_ALT_Results.AST AS FLOAT)) /
                        (CAST(Ranked_PLT_Results.PLT AS FLOAT) * SQRT(CAST(AST_ALT_Results.ALT AS FLOAT))), 2) AS VARCHAR)
    END AS ResultValue,
    AST_ALT_Results.ReportDate AS ReportDate
FROM AST_ALT_Results
JOIN Ranked_PLT_Results ON AST_ALT_Results.ReportDate = Ranked_PLT_Results.ReportDate
WHERE Ranked_PLT_Results.RN = 1
ORDER BY AST_ALT_Results.ReportDate DESC;
