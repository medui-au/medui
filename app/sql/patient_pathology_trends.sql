/* ==================================================================
   1. CTEs FROM QUERY 1 (Standard LOINC Results & Harmonization)
   ================================================================== */
WITH AllValues AS (
  SELECT rv.INTERNALID, rv.REPORTDATE, rv.LOINCCODE, rv.RESULTNAME,
    CASE WHEN TRIM(rv.LOINCCODE) = '33914-3' AND rv.RESULTVALUE LIKE '%90%' THEN '90' ELSE rv.RESULTVALUE END AS RESULTVALUE,
    CASE
        WHEN TRIM(rv.ABNORMALFLAG) = 'H' THEN '+'
        WHEN TRIM(rv.ABNORMALFLAG) = 'L' THEN '-'
        ELSE TRIM(rv.ABNORMALFLAG)
    END AS ABNORMALFLAG
  FROM dbo.REPORTVALUES AS rv
  WHERE rv.INTERNALID = ?
    AND TRIM(rv.LOINCCODE) IN ('14771-0','14768-6','14646-4','10334-1','10535-3','14647-2','14685-2','14920-3','14927-8','14933-6','1988-5','2276-4','24108-3','2601-3','2823-3','2951-2','3016-3','32309-7','33914-3','43396-1','4544-3','4548-4','718-7','777-3','9830-1','2885-2','2857-1','12841-3','2064-4','50210-4','14804-9','1743-4','1920-8','2324-2','6768-6','61152-5','32294-1','13965-9','2157-6','4537-7','70204-3','14334-7','39469-2','17856-6')
    AND TRY_CAST(CASE WHEN TRIM(rv.LOINCCODE) = '33914-3' AND rv.RESULTVALUE LIKE '%90%' THEN '90' ELSE rv.RESULTVALUE END AS FLOAT) IS NOT NULL
  UNION ALL
  SELECT ir.INTERNALID, iv.REPORTDATE, iv.LOINCCODE, iv.RESULTNAME,
    CASE WHEN TRIM(iv.LOINCCODE) = '33914-3' AND iv.RESULTVALUE LIKE '%90%' THEN '90' ELSE iv.RESULTVALUE END AS RESULTVALUE,
    CASE
        WHEN TRIM(iv.ABNORMALFLAG) = 'H' THEN '+'
        WHEN TRIM(iv.ABNORMALFLAG) = 'L' THEN '-'
        ELSE TRIM(iv.ABNORMALFLAG)
    END AS ABNORMALFLAG
  FROM dbo.INCOMINGVALUES AS iv JOIN dbo.INCOMINGREPORTS AS ir ON ir.ReportID = iv.ReportID
  WHERE ir.INTERNALID = ?
    AND TRIM(iv.LOINCCODE) IN ('14771-0','14768-6','14646-4','10334-1','10535-3','14647-2','14685-2','14920-3','14927-8','14933-6','1988-5','2276-4','24108-3','2601-3','2823-3','2951-2','3016-3','32309-7','33914-3','43396-1','4544-3','4548-4','718-7','777-3','9830-1','2885-2','2857-1','12841-3','2064-4','50210-4','14804-9','1743-4','1920-8','2324-2','6768-6','61152-5','32294-1','13965-9','2157-6','4537-7','70204-3','14334-7','39469-2','17856-6')
    AND TRY_CAST(CASE WHEN TRIM(iv.LOINCCODE) = '33914-3' AND iv.RESULTVALUE LIKE '%90%' THEN '90' ELSE iv.RESULTVALUE END AS FLOAT) IS NOT NULL
),
LatestName AS (SELECT INTERNALID, LOINCCODE, RESULTNAME FROM (SELECT INTERNALID, LOINCCODE, RESULTNAME, ROW_NUMBER() OVER(PARTITION BY INTERNALID, LOINCCODE ORDER BY REPORTDATE DESC) AS rn FROM AllValues) x WHERE rn = 1),
FinalProcessed AS (
    SELECT a.REPORTDATE, a.LOINCCODE, ln.RESULTNAME, a.RESULTVALUE, a.ABNORMALFLAG
    FROM AllValues AS a
    JOIN LatestName AS ln ON a.INTERNALID = ln.INTERNALID AND a.LOINCCODE = ln.LOINCCODE
),
RankedHistory AS (SELECT REPORTDATE, RESULTNAME, RESULTVALUE, ABNORMALFLAG, ROW_NUMBER() OVER (PARTITION BY RESULTNAME ORDER BY REPORTDATE DESC) AS RecencyRank FROM FinalProcessed),

/* ==================================================================
   2. CTEs FROM QUERY 2 (FIB-4 Calculation)
   ================================================================== */
AST_ALT_Results AS (
    SELECT CombinedResults.ReportDate, FLOOR(DATEDIFF(day, Patients.DOB, CombinedResults.ReportDate) / 365.25) AS Age,
        MAX(CASE WHEN CombinedResults.LOINCCODE = '1920-8' THEN CombinedResults.ResultValue END) AS AST,
        MAX(CASE WHEN CombinedResults.LOINCCODE IN ('1744-2','1742-6','1743-4') THEN CombinedResults.ResultValue END) AS ALT,
        CombinedResults.InternalId
    FROM (
        SELECT iv.ReportDate, iv.LOINCCODE, RTRIM(iv.ResultValue) AS ResultValue, ir.InternalId
        FROM IncomingValues iv JOIN IncomingReports ir ON iv.ReportId = ir.ReportId
        WHERE ir.InternalId = ? AND iv.LOINCCODE IN ('777-3','AUSLAB^PLT','1744-2','1742-6','1743-4','1920-8')
        UNION
        SELECT rv.ReportDate, rv.LOINCCODE, RTRIM(rv.ResultValue) AS ResultValue, rv.InternalId
        FROM REPORTVALUES rv
        WHERE rv.InternalId = ? AND rv.LOINCCODE IN ('777-3','AUSLAB^PLT','1744-2','1742-6','1743-4','1920-8')
    ) AS CombinedResults
    JOIN Patients ON CombinedResults.InternalId = Patients.InternalId
    GROUP BY CombinedResults.ReportDate, Patients.DOB, CombinedResults.InternalId
    HAVING MAX(CASE WHEN CombinedResults.LOINCCODE = '1920-8' THEN CombinedResults.ResultValue END) IS NOT NULL
       AND MAX(CASE WHEN CombinedResults.LOINCCODE IN ('1744-2','1742-6','1743-4') THEN CombinedResults.ResultValue END) IS NOT NULL
),
PLT_Results AS (
    SELECT iv.ReportDate AS PLT_ReportDate, RTRIM(iv.ResultValue) AS PLT, ir.InternalId
    FROM IncomingValues iv JOIN IncomingReports ir ON iv.ReportId = ir.ReportId
    WHERE ir.InternalId = ? AND iv.LOINCCODE IN ('777-3','AUSLAB^PLT')
    UNION
    SELECT rv.ReportDate AS PLT_ReportDate, RTRIM(rv.ResultValue) AS PLT, rv.InternalId
    FROM REPORTVALUES rv
    WHERE rv.InternalId = ? AND rv.LOINCCODE IN ('777-3','AUSLAB^PLT')
),
Ranked_PLT_Results AS (
    SELECT p.PLT_ReportDate, p.PLT, a.ReportDate,
        ROW_NUMBER() OVER (PARTITION BY a.ReportDate ORDER BY ABS(DATEDIFF(day, p.PLT_ReportDate, a.ReportDate))) AS RN
    FROM PLT_Results p JOIN AST_ALT_Results a ON p.InternalId = a.InternalId
    WHERE ABS(DATEDIFF(day, p.PLT_ReportDate, a.ReportDate)) <= 30
),
FIB4_Ranked AS (
    SELECT
        CAST(a.ReportDate AS DATE) AS REPORTDATE,
        'FIB-4' AS RESULTNAME,
        CAST(ROUND((CAST(a.Age AS FLOAT) * CAST(a.AST AS FLOAT)) / (CAST(r.PLT AS FLOAT) * SQRT(CAST(a.ALT AS FLOAT))), 2) AS varchar(10)) AS RESULTVALUE,
        CASE WHEN (CAST(a.Age AS FLOAT) * CAST(a.AST AS FLOAT)) / (CAST(r.PLT AS FLOAT) * SQRT(CAST(a.ALT AS FLOAT))) > 1.45 THEN '+' ELSE '' END AS ABNORMALFLAG,
        ROW_NUMBER() OVER (ORDER BY a.ReportDate DESC) AS FibRank
    FROM AST_ALT_Results a
    JOIN Ranked_PLT_Results r ON a.ReportDate = r.ReportDate
    WHERE r.RN = 1
)

/* ==================================================================
   3. FINAL MERGED OUTPUT WITH CLINICAL GROUPING & CONCATENATED VALUE
   ================================================================== */
SELECT
    f.REPORTDATE                                      AS PerformedDate,
    f.MappedName                                      AS ResultName,
    TRIM(f.RawValue + ' ' + ISNULL(f.RawFlag, ''))   AS ResultValue
FROM (
    SELECT
        CAST(REPORTDATE AS DATE) AS REPORTDATE,
        TRIM(RESULTVALUE) AS RawValue,
        TRIM(ABNORMALFLAG) AS RawFlag,
        CASE
            WHEN ShortName = 'Haemoglobin'                   THEN 'Haemoglobin'
            WHEN ShortName = 'Haematocrit'                   THEN 'Haematocrit'
            WHEN ShortName = 'Platelet Count'                THEN 'Platelets'
            WHEN ShortName = 'Erythrocyte Sedimentation Rate' THEN 'ESR'
            WHEN ShortName = 'Sodium'                        THEN 'Sodium'
            WHEN ShortName = 'Serum Potassium'               THEN 'Potassium'
            WHEN ShortName = 'Magnesium'                     THEN 'Magnesium'
            WHEN ShortName = 'eGFR'                          THEN 'eGFR'
            WHEN ShortName = 'Albumin/Creatinine Ratio'      THEN 'ACR'
            WHEN ShortName = 'Serum Uric Acid'               THEN 'Uric Acid'
            WHEN ShortName = 'Total Protein'                 THEN 'Total Protein'
            WHEN ShortName = 'Albumin'                       THEN 'Albumin'
            WHEN ShortName = 'Total Alk. Phosphatase'        THEN 'ALP'
            WHEN ShortName = 'ALT'                           THEN 'ALT'
            WHEN ShortName = 'AST'                           THEN 'AST'
            WHEN ShortName = 'Gamma G.T.'                    THEN 'Gamma G.T.'
            WHEN ShortName = 'LD'                            THEN 'LD'
            WHEN ShortName = 'FIB-4'                         THEN 'FIB-4'
            WHEN ShortName = 'Cholesterol'                   THEN 'Cholesterol'
            WHEN ShortName = 'HDL'                           THEN 'HDL'
            WHEN ShortName = 'LDL (calculated)'              THEN 'LDL (calc)'
            WHEN ShortName = 'Non-HDL Cholesterol'           THEN 'Non-HDL'
            WHEN ShortName = 'Total /HDL'                    THEN 'Total /HDL'
            WHEN ShortName = 'Triglycerides'                 THEN 'Triglycerides'
            WHEN ShortName = 'Glucose fasting'               THEN 'Glucose (f)'
            WHEN ShortName = 'Blood HbA1c Fraction'          THEN 'HbA1c'
            WHEN ShortName = 'C-Reactive Protein'            THEN 'CRP'
            WHEN ShortName = 'Serum Ferritin Assay'          THEN 'Ferritin'
            WHEN ShortName = 'Thyroid Stimulating Hormone'   THEN 'TSH'
            WHEN ShortName = 'free Thyroxine'                THEN 'fT4'
            WHEN ShortName = 'Prostate Specific Antigen'     THEN 'PSA'
            WHEN ShortName = 'PSA Percentage'                THEN 'PSA %'
            WHEN ShortName = 'Serum Vitamin B12'             THEN 'Vit B12'
            ELSE ShortName
        END AS MappedName,
        CASE
            WHEN ShortName IN ('Haemoglobin','Haematocrit','Platelet Count','Erythrocyte Sedimentation Rate') THEN 1
            WHEN ShortName IN ('Sodium','Serum Potassium','Magnesium','eGFR','Albumin/Creatinine Ratio','Serum Uric Acid') THEN 2
            WHEN ShortName IN ('Total Protein','Albumin','Total Alk. Phosphatase','ALT','AST','Gamma G.T.','LD','FIB-4') THEN 3
            WHEN ShortName IN ('Cholesterol','HDL','LDL (calculated)','Non-HDL Cholesterol','Total /HDL','Triglycerides') THEN 4
            WHEN ShortName IN ('Glucose fasting','Blood HbA1c Fraction','C-Reactive Protein','Serum Ferritin Assay') THEN 5
            WHEN ShortName IN ('Thyroid Stimulating Hormone','free Thyroxine','Prostate Specific Antigen','PSA Percentage','Serum Vitamin B12') THEN 6
            ELSE 9
        END AS GroupOrder
    FROM (
        SELECT REPORTDATE, RESULTNAME AS ShortName, RESULTVALUE, ABNORMALFLAG, RecencyRank
        FROM RankedHistory WHERE RecencyRank <= 2
        UNION ALL
        SELECT REPORTDATE, RESULTNAME, RESULTVALUE, ABNORMALFLAG, FibRank
        FROM FIB4_Ranked WHERE FibRank <= 2
    ) AS CombinedRows
) AS f
ORDER BY f.GroupOrder, f.MappedName, f.REPORTDATE DESC;
