WITH RawData AS (
    SELECT 
        ReportDate,
        LOINCCODE,
        TRY_CAST(ResultValue AS FLOAT) AS Val,
        InternalId
    FROM (
        SELECT iv.ReportDate, iv.LOINCCODE, iv.ResultValue, ir.InternalId
        FROM IncomingValues iv
        JOIN IncomingReports ir ON iv.ReportId = ir.ReportId
        WHERE ir.InternalId = ?
          AND iv.LOINCCODE IN ('777-3','AUSLAB^PLT','1744-2','1742-6','1743-4','1920-8')
        UNION ALL
        SELECT rv.ReportDate, rv.LOINCCODE, rv.ResultValue, rv.InternalId
        FROM REPORTVALUES rv
        WHERE rv.InternalId = ?
          AND rv.LOINCCODE IN ('777-3','AUSLAB^PLT','1744-2','1742-6','1743-4','1920-8')
    ) t
),
PivotResults AS (
    SELECT
        d.InternalId,
        d.ReportDate,
        FLOOR(DATEDIFF(DAY, p.DOB, d.ReportDate) / 365.25) AS Age,
        MAX(CASE WHEN d.LOINCCODE = '1920-8' THEN d.Val END) AS AST,
        MAX(CASE WHEN d.LOINCCODE IN ('1744-2','1742-6','1743-4') THEN d.Val END) AS ALT
    FROM RawData d
    JOIN Patients p ON d.InternalId = p.InternalId
    GROUP BY d.InternalId, d.ReportDate, p.DOB
    HAVING MAX(CASE WHEN d.LOINCCODE = '1920-8' THEN d.Val END) > 0
       AND MAX(CASE WHEN d.LOINCCODE IN ('1744-2','1742-6','1743-4') THEN d.Val END) > 0
),
RankedPLT AS (
    SELECT 
        a.InternalId, a.ReportDate, a.Age, a.AST, a.ALT, plt.Val AS PLT,
        ROW_NUMBER() OVER (PARTITION BY a.ReportDate ORDER BY ABS(DATEDIFF(DAY, plt.ReportDate, a.ReportDate)) ASC) AS rn
    FROM PivotResults a
    JOIN RawData plt ON a.InternalId = plt.InternalId 
        AND plt.LOINCCODE IN ('777-3','AUSLAB^PLT')
        AND ABS(DATEDIFF(DAY, plt.ReportDate, a.ReportDate)) <= 30
)
SELECT TOP(4)
    r.InternalId AS INTERNALID,
    CONVERT(VARCHAR(10), r.ReportDate, 23) AS REPORTDATE,
    '98488-0' AS LOINCCODE,
    'FIB-4' AS RESULTNAME,
    CAST(Calc.Score AS VARCHAR(10)) AS RESULTVALUE,
    '' AS UNITS,
    '0-1.45' AS [RANGE],
    CASE WHEN Calc.Score > 1.45 THEN '+' ELSE '' END AS ABNORMALFLAG
FROM RankedPLT r
CROSS APPLY (
    SELECT ROUND((r.Age * r.AST) / (NULLIF(r.PLT, 0) * SQRT(NULLIF(r.ALT, 0))), 2) AS Score
) Calc
WHERE r.rn = 1 
  AND Calc.Score IS NOT NULL
ORDER BY r.ReportDate DESC;
