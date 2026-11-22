/* Compact pathology block for smaller AI context windows.
   Returns last 4 results for slower-changing analytes (TSH, eGFR, HbA1c,
   lipids, ferritin, PSA) and last 2 for all others, plus FIB-4 calculated
   from the same dataset.  FIB-4 is appended via UNION ALL.
   Parameter order: patient_id × 6 (AllValues ×2, AST_ALT_Results ×2, PLT_Results ×2)

   Harmonization stages 1-7 are materialized into #temp tables rather than
   chained CTEs.  SQL Server does not cache/share CTE evaluations across
   references — NameHarmonized alone was referenced three times downstream
   (directly, plus once each via MultiCodeNames and LatestCode), and it in
   turn re-evaluates AllValues three times, so the optimizer ends up with a
   nested-loop plan that reruns the upstream pipeline per outer row instead
   of once. On a patient with ~5k qualifying results that turned a <1s
   computation into 8+ minutes. #temp tables are session-scoped (tempdb
   only, never written to BPSDB) and force each stage to be computed once. */

/* ==================================================================
   1. Standard LOINC results + harmonization (materialized)
   ================================================================== */
SET NOCOUNT ON;

SELECT rv.INTERNALID, rv.REPORTDATE, rv.LOINCCODE, rv.RESULTNAME,
  rv.RESULTVALUE,
  rv.UNITS, rv.[RANGE], rv.ABNORMALFLAG
INTO #AllValues
FROM dbo.REPORTVALUES AS rv
WHERE rv.INTERNALID = ?
  AND TRIM(rv.LOINCCODE) IN (
    '14771-0','14768-6','14646-4','10334-1','10535-3','14631-6','14635-7','14647-2','14685-2',
    '14920-3','14928-6','14927-8','14933-6','1988-5','22748-8','2276-4','24108-3',
    '2601-3','2823-3','29265-6','2951-2','3016-3','32309-7','33914-3','43396-1',
    '4544-3','4548-4','59261-8','718-7','72160-5','777-3','9830-1','742-7','751-8',
    '789-8','787-2','731-0','711-2','6690-2','2885-2','2857-1','12841-3','2064-4',
    '50210-4','14804-9','1743-4','1920-8','2532-0','2324-2','6768-6','61152-5','2890-2',
    '32294-1','13965-9','2157-6','4537-7','70204-3','14334-7','39469-2','17856-6',
    '14913-8','14955-9','38445-3','1742-6','1744-2'
  )
  -- Admit results reported with a leading comparator (e.g. '<3', '>90') by
  -- casting the numeric remainder from the first digit onward; RESULTVALUE
  -- itself is left untouched above so the block still reports '<3'/'>90'
  -- verbatim, matching what the lab actually reported.
  AND TRY_CAST(
    CASE WHEN PATINDEX('%[0-9.-]%', rv.RESULTVALUE) > 0
      THEN SUBSTRING(rv.RESULTVALUE, PATINDEX('%[0-9.-]%', rv.RESULTVALUE), LEN(rv.RESULTVALUE))
      ELSE rv.RESULTVALUE
    END
    AS FLOAT
  ) IS NOT NULL;

INSERT INTO #AllValues
SELECT ir.INTERNALID, iv.REPORTDATE, iv.LOINCCODE, iv.RESULTNAME,
  iv.RESULTVALUE,
  iv.UNITS, iv.[RANGE], iv.ABNORMALFLAG
FROM dbo.INCOMINGVALUES AS iv JOIN dbo.INCOMINGREPORTS AS ir ON ir.ReportID = iv.ReportID
WHERE ir.INTERNALID = ?
  AND TRIM(iv.LOINCCODE) IN (
    '14771-0','14768-6','14646-4','10334-1','10535-3','14631-6','14635-7','14647-2','14685-2',
    '14920-3','14928-6','14927-8','14933-6','1988-5','22748-8','2276-4','24108-3',
    '2601-3','2823-3','29265-6','2951-2','3016-3','32309-7','33914-3','43396-1',
    '4544-3','4548-4','59261-8','718-7','72160-5','777-3','9830-1','742-7','751-8',
    '789-8','787-2','731-0','711-2','6690-2','2885-2','2857-1','12841-3','2064-4',
    '50210-4','14804-9','1743-4','1920-8','2532-0','2324-2','6768-6','61152-5','2890-2',
    '32294-1','13965-9','2157-6','4537-7','70204-3','14334-7','39469-2','17856-6',
    '14913-8','14955-9','38445-3','1742-6','1744-2'
  )
  AND TRY_CAST(
    CASE WHEN PATINDEX('%[0-9.-]%', iv.RESULTVALUE) > 0
      THEN SUBSTRING(iv.RESULTVALUE, PATINDEX('%[0-9.-]%', iv.RESULTVALUE), LEN(iv.RESULTVALUE))
      ELSE iv.RESULTVALUE
    END
    AS FLOAT
  ) IS NOT NULL;

SELECT INTERNALID, LOINCCODE
INTO #MultiNameCodes
FROM #AllValues
GROUP BY INTERNALID, LOINCCODE HAVING COUNT(DISTINCT RESULTNAME) > 1;

SELECT INTERNALID, LOINCCODE, RESULTNAME AS MostRecentResultName
INTO #LatestName
FROM (
  SELECT INTERNALID, LOINCCODE, RESULTNAME,
    ROW_NUMBER() OVER(PARTITION BY INTERNALID, LOINCCODE ORDER BY REPORTDATE DESC) AS rn
  FROM #AllValues
) x WHERE rn = 1;

SELECT a.INTERNALID, a.REPORTDATE, a.LOINCCODE,
  CASE WHEN m.LOINCCODE IS NOT NULL THEN ln.MostRecentResultName ELSE a.RESULTNAME END AS RESULTNAME,
  a.RESULTVALUE, a.UNITS, a.[RANGE], a.ABNORMALFLAG
INTO #NameHarmonized
FROM #AllValues AS a
LEFT JOIN #MultiNameCodes AS m  ON a.INTERNALID = m.INTERNALID AND a.LOINCCODE = m.LOINCCODE
LEFT JOIN #LatestName AS ln     ON a.INTERNALID = ln.INTERNALID AND a.LOINCCODE = ln.LOINCCODE;

SELECT INTERNALID, RESULTNAME
INTO #MultiCodeNames
FROM #NameHarmonized
GROUP BY INTERNALID, RESULTNAME HAVING COUNT(DISTINCT LOINCCODE) > 1;

SELECT INTERNALID, RESULTNAME, LOINCCODE AS MostRecentLoincCode
INTO #LatestCode
FROM (
  SELECT INTERNALID, RESULTNAME, LOINCCODE,
    ROW_NUMBER() OVER(PARTITION BY INTERNALID, RESULTNAME ORDER BY REPORTDATE DESC) AS rn
  FROM #NameHarmonized
) y WHERE rn = 1;

SELECT DISTINCT nh.INTERNALID, nh.REPORTDATE,
  CASE WHEN mc.RESULTNAME IS NOT NULL THEN lc.MostRecentLoincCode ELSE nh.LOINCCODE END AS LOINCCODE,
  nh.RESULTNAME, nh.RESULTVALUE, nh.UNITS, nh.[RANGE], nh.ABNORMALFLAG
INTO #FinalProcessed
FROM #NameHarmonized AS nh
LEFT JOIN #MultiCodeNames AS mc ON nh.INTERNALID = mc.INTERNALID AND nh.RESULTNAME = mc.RESULTNAME
LEFT JOIN #LatestCode AS lc     ON nh.INTERNALID = lc.INTERNALID AND nh.RESULTNAME = lc.RESULTNAME
WHERE NOT (
  LTRIM(RTRIM(nh.LOINCCODE)) IN ('704-7','711-2','713-8','731-0','736-9','742-7','751-8','770-8','5905-5')
  AND nh.UNITS LIKE '%\%'
);

/* ==================================================================
   2. FIB-4 calculation + 3. Final merged output
   ================================================================== */
WITH RankedHistory AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY RESULTNAME ORDER BY REPORTDATE DESC) AS RecencyRank
  FROM #FinalProcessed
),
AST_ALT_Results AS (
  SELECT CombinedResults.ReportDate,
    FLOOR(DATEDIFF(day, Patients.DOB, CombinedResults.ReportDate) / 365.25) AS Age,
    MAX(CASE WHEN CombinedResults.LOINCCODE = '1920-8' THEN RTRIM(CombinedResults.ResultValue) END) AS AST,
    MAX(CASE WHEN CombinedResults.LOINCCODE IN ('1744-2','1742-6','1743-4') THEN RTRIM(CombinedResults.ResultValue) END) AS ALT,
    CombinedResults.InternalId
  FROM (
    SELECT iv.ReportDate, iv.LOINCCODE, RTRIM(iv.ResultValue) AS ResultValue, ir.InternalId
    FROM IncomingValues iv JOIN IncomingReports ir ON iv.ReportId = ir.ReportId
    WHERE ir.InternalId = ?
      AND iv.LOINCCODE IN ('777-3','AUSLAB^PLT','1744-2','1742-6','1743-4','1920-8')
    UNION
    SELECT rv.ReportDate, rv.LOINCCODE, RTRIM(rv.ResultValue) AS ResultValue, rv.InternalId
    FROM REPORTVALUES rv
    WHERE rv.InternalId = ?
      AND rv.LOINCCODE IN ('777-3','AUSLAB^PLT','1744-2','1742-6','1743-4','1920-8')
  ) AS CombinedResults
  JOIN Patients ON CombinedResults.InternalId = Patients.InternalId
  GROUP BY CombinedResults.ReportDate, Patients.DOB, CombinedResults.InternalId
  HAVING
    MAX(CASE WHEN CombinedResults.LOINCCODE = '1920-8' THEN CombinedResults.ResultValue END) IS NOT NULL
    AND MAX(CASE WHEN CombinedResults.LOINCCODE IN ('1744-2','1742-6','1743-4') THEN CombinedResults.ResultValue END) IS NOT NULL
),
PLT_Results AS (
  SELECT iv.ReportDate AS PLT_ReportDate, RTRIM(iv.ResultValue) AS PLT, ir.InternalId
  FROM IncomingValues iv JOIN IncomingReports ir ON iv.ReportId = ir.ReportId
  WHERE ir.InternalId = ?
    AND iv.LOINCCODE IN ('777-3','AUSLAB^PLT')
  UNION
  SELECT rv.ReportDate AS PLT_ReportDate, RTRIM(rv.ResultValue) AS PLT, rv.InternalId
  FROM REPORTVALUES rv
  WHERE rv.InternalId = ?
    AND rv.LOINCCODE IN ('777-3','AUSLAB^PLT')
),
Ranked_PLT_Results AS (
  SELECT p.PLT_ReportDate, p.PLT, a.ReportDate,
    ROW_NUMBER() OVER (
      PARTITION BY a.ReportDate
      ORDER BY
        CASE WHEN p.PLT_ReportDate = a.ReportDate THEN 0 ELSE ABS(DATEDIFF(day, p.PLT_ReportDate, a.ReportDate)) END,
        TRY_CAST(p.PLT AS FLOAT) DESC  -- tie-break: same distance -> prefer the higher PLT result
    ) AS RN
  FROM PLT_Results p
  JOIN AST_ALT_Results a ON p.InternalId = a.InternalId
    AND ABS(DATEDIFF(day, p.PLT_ReportDate, a.ReportDate)) <= 30
),
FIB4_Final AS (
  SELECT
    a.InternalId AS INTERNALID,
    a.ReportDate AS REPORTDATE,
    'FIB-4'      AS LOINCCODE,
    -- ADR-168: calculated by MedUI, labelled as such, with its inputs and formula; no
    -- cut-off, range or flag of MedUI's own.
    'FIB-4 (calculated by MedUI, not a laboratory result)' AS RESULTNAME,
    CAST(ROUND(
      (CAST(a.Age AS FLOAT) * CAST(a.AST AS FLOAT))
      / (CAST(r.PLT AS FLOAT) * SQRT(CAST(a.ALT AS FLOAT))),
      2
    ) AS varchar(10)) AS RESULTVALUE,
    CONCAT('from age ', CAST(a.Age AS VARCHAR(10)), ', AST ', a.AST, ', ALT ', a.ALT,
           ', platelets ', r.PLT, ' (', CONVERT(VARCHAR(10), r.PLT_ReportDate, 23), '); age x AST / (platelets x sqrt(ALT)), Sterling et al., Hepatology 2006; AST and ALT from the same day, platelets from the nearest result within 30 days') AS UNITS,
    ''       AS [RANGE],
    ''       AS ABNORMALFLAG
  FROM AST_ALT_Results a
  JOIN Ranked_PLT_Results r ON a.ReportDate = r.ReportDate
  WHERE r.RN = 1
    AND TRY_CAST(a.Age AS FLOAT) IS NOT NULL
    AND TRY_CAST(a.AST AS FLOAT) IS NOT NULL
    AND TRY_CAST(a.ALT AS FLOAT) IS NOT NULL
    AND TRY_CAST(r.PLT AS FLOAT) IS NOT NULL
)
SELECT
  INTERNALID,
  CAST(REPORTDATE AS DATE)  AS REPORTDATE,
  TRIM(LOINCCODE)           AS LOINCCODE,
  TRIM(RESULTNAME)          AS RESULTNAME,
  TRIM(RESULTVALUE)         AS RESULTVALUE,
  TRIM(UNITS)               AS UNITS,
  TRIM([RANGE])             AS RANGE,
  TRIM(ABNORMALFLAG)        AS ABNORMALFLAG
FROM RankedHistory
WHERE
  -- Slower-changing analytes: keep last 4
  (TRIM(LOINCCODE) IN ('3016-3','14928-6','14920-3','4548-4','718-7','14771-0','14768-6','2276-4','33914-3') AND RecencyRank <= 4)
  OR
  -- All other LOINCs: keep last 2
  (TRIM(LOINCCODE) NOT IN ('3016-3','14928-6','14920-3','4548-4','718-7','14771-0','14768-6','2276-4','33914-3') AND RecencyRank <= 2)

UNION ALL

SELECT
  INTERNALID,
  CAST(REPORTDATE AS DATE)  AS REPORTDATE,
  TRIM(LOINCCODE)           AS LOINCCODE,
  TRIM(RESULTNAME)          AS RESULTNAME,
  TRIM(RESULTVALUE)         AS RESULTVALUE,
  TRIM(UNITS)               AS UNITS,
  TRIM([RANGE])             AS RANGE,
  TRIM(ABNORMALFLAG)        AS ABNORMALFLAG
FROM FIB4_Final

ORDER BY RESULTNAME, REPORTDATE DESC;
