WITH MinResultName AS (
    SELECT LoincCode,
           MIN(ResultName) AS ResultName
    FROM (
        -- Existing data from ReportValues
        SELECT LoincCode,
               TRIM(ResultName) AS ResultName,
               ROW_NUMBER() OVER (PARTITION BY LoincCode ORDER BY LEN(ResultName), ResultName) AS rn
        FROM ReportValues
        WHERE InternalId = ?
        AND (LoincCode IN ('39469-2', '14749-6', '14647-2', '14646-4', '22748-8', '33914-3', '1754-1', '4548-4', '3016-3', '2857-1', '2276-4', '17856-6'))
        UNION ALL
        -- Additional rows from IncomingValues
        SELECT LoincCode,
               TRIM(ResultName) AS ResultName,
               ROW_NUMBER() OVER (PARTITION BY LoincCode ORDER BY LEN(ResultName), ResultName) AS rn
        FROM IncomingValues
        WHERE IncomingValues.REPORTID IN (SELECT ReportId FROM IncomingReports WHERE InternalId = ?)
        AND (LoincCode IN ('39469-2', '14749-6', '14647-2', '14646-4', '22748-8', '33914-3', '1754-1', '4548-4', '3016-3', '2857-1', '2276-4', '17856-6'))
    ) AS sub
    WHERE rn = 1
    GROUP BY LOINCCODE
)
SELECT DISTINCT RTRIM(rv.LoincCode) AS LoincCode,
       RTRIM(
           CASE
               WHEN minrn.ResultName = 'Blood HbA1c Fraction' THEN 'HbA1c'
               WHEN minrn.ResultName = 'HbA1c (NGSP)' THEN 'HbA1c'
               WHEN minrn.ResultName = 'Thyroid Stimulating Hormone' THEN 'TSH'
               WHEN minrn.ResultName = 'Chol.' THEN 'Cholesterol- Total'
               WHEN minrn.ResultName = 'Cholesterol' THEN 'Cholesterol- Total'
               WHEN minrn.ResultName = 'HDL' THEN 'Cholesterol-HDL'
               WHEN minrn.ResultName = 'LDL' THEN 'Cholesterol-LDL'
               WHEN minrn.ResultName = 'LDL (calculated)' THEN 'Cholesterol-LDL'
               WHEN minrn.ResultName = 'LDL (atherogenic)' THEN 'Cholesterol-LDL'
               WHEN minrn.ResultName = 'Serum Ferritin Assay' THEN 'Ferritin'
               WHEN minrn.ResultName = 'Prostate Specific Antigen' THEN 'PSA'
               WHEN minrn.ResultName = 'Total PSA' THEN 'PSA'
               WHEN minrn.ResultName = 'Random Glucose' THEN 'Glucose'
               WHEN minrn.ResultName = 'Urine Albumin' THEN 'R U-Albumin'
               ELSE minrn.ResultName
           END
       ) AS ResultName,
       RTRIM(
           CASE
               WHEN rv.ResultValue LIKE '%<%' THEN SUBSTRING(rv.ResultValue, PATINDEX('%[0-9.-]%', rv.ResultValue), LEN(rv.ResultValue) - PATINDEX('%[0-9.-]%', rv.ResultValue) + 1)
               WHEN rv.ResultValue LIKE '%>%' THEN SUBSTRING(rv.ResultValue, PATINDEX('%[0-9.-]%', rv.ResultValue), LEN(rv.ResultValue) - PATINDEX('%[0-9.-]%', rv.ResultValue) + 1)
               ELSE rv.ResultValue
           END
       ) AS ResultValue,
       ReportDate,
       RTRIM(rv.[RANGE]) AS Range   -- the laboratory's range for this result (ADR-105)
FROM   ReportValues rv
JOIN   MinResultName minrn ON rv.LoincCode = minrn.LoincCode
WHERE  rv.InternalId = ?
AND    (rv.LoincCode IN ('39469-2', '14749-6', '14647-2', '14646-4', '22748-8', '33914-3', '1754-1', '4548-4', '3016-3', '2857-1', '2276-4', '17856-6'))

UNION ALL

-- Bring in data from IncomingValues as well
SELECT DISTINCT RTRIM(iv.LoincCode) AS LoincCode,
       RTRIM(
           CASE
               WHEN minrn.ResultName = 'Blood HbA1c Fraction' THEN 'HbA1c'
               WHEN minrn.ResultName = 'HbA1c (NGSP)' THEN 'HbA1c'
               WHEN minrn.ResultName = 'Thyroid Stimulating Hormone' THEN 'TSH'
               WHEN minrn.ResultName = 'Chol.' THEN 'Cholesterol- Total'
               WHEN minrn.ResultName = 'Cholesterol' THEN 'Cholesterol- Total'
               WHEN minrn.ResultName = 'HDL' THEN 'Cholesterol-HDL'
               WHEN minrn.ResultName = 'LDL' THEN 'Cholesterol-LDL'
               WHEN minrn.ResultName = 'LDL (calculated)' THEN 'Cholesterol-LDL'
               WHEN minrn.ResultName = 'LDL (atherogenic)' THEN 'Cholesterol-LDL'
               WHEN minrn.ResultName = 'Serum Ferritin Assay' THEN 'Ferritin'
               WHEN minrn.ResultName = 'Prostate Specific Antigen' THEN 'PSA'
               WHEN minrn.ResultName = 'Total PSA' THEN 'PSA'
               WHEN minrn.ResultName = 'Random Glucose' THEN 'Glucose'
               WHEN minrn.ResultName = 'Urine Albumin' THEN 'R U-Albumin'
               ELSE minrn.ResultName
           END
       ) AS ResultName,
       RTRIM(
           CASE
               WHEN iv.ResultValue LIKE '%<%' THEN SUBSTRING(iv.ResultValue, PATINDEX('%[0-9.-]%', iv.ResultValue), LEN(iv.ResultValue) - PATINDEX('%[0-9.-]%', iv.ResultValue) + 1)
               WHEN iv.ResultValue LIKE '%>%' THEN SUBSTRING(iv.ResultValue, PATINDEX('%[0-9.-]%', iv.ResultValue), LEN(iv.ResultValue) - PATINDEX('%[0-9.-]%', iv.ResultValue) + 1)
               ELSE iv.ResultValue
           END
       ) AS ResultValue,
       iv.ReportDate,
       RTRIM(iv.[RANGE]) AS Range
FROM   IncomingValues iv
JOIN   IncomingReports ir ON iv.ReportId = ir.ReportId
JOIN   MinResultName minrn ON iv.LoincCode = minrn.LoincCode
WHERE  ir.InternalId = ?
AND    (iv.LoincCode IN ('39469-2', '14749-6', '14647-2', '14646-4', '22748-8', '33914-3', '1754-1', '4548-4', '3016-3', '2857-1', '2276-4', '17856-6'))
ORDER BY Resultname, ReportDate;
