WITH
AllValues AS
(
  SELECT
    rv.INTERNALID,
    rv.REPORTDATE,
    rv.LOINCCODE,
    rv.RESULTNAME,
    rv.RESULTVALUE,
    rv.UNITS,
    rv.[RANGE],
    rv.ABNORMALFLAG
  FROM dbo.REPORTVALUES AS rv
  WHERE rv.INTERNALID = ?
    AND rv.LOINCCODE <> ''
    -- Admit results reported with a leading comparator (e.g. '<3', '>90') by
    -- casting the numeric remainder from the first digit onward; RESULTVALUE
    -- itself stays untouched here — the comparator-strip for charting happens
    -- once, in the final SELECT below.
    AND TRY_CAST(
          CASE WHEN PATINDEX('%[0-9.-]%', rv.RESULTVALUE) > 0
            THEN SUBSTRING(rv.RESULTVALUE, PATINDEX('%[0-9.-]%', rv.RESULTVALUE), LEN(rv.RESULTVALUE))
            ELSE rv.RESULTVALUE
          END
          AS FLOAT
        ) IS NOT NULL
  UNION ALL
  SELECT
    ir.INTERNALID,
    iv.REPORTDATE,
    iv.LOINCCODE,
    iv.RESULTNAME,
    iv.RESULTVALUE,
    iv.UNITS,
    iv.[RANGE],
    iv.ABNORMALFLAG
  FROM dbo.INCOMINGVALUES  AS iv
  JOIN dbo.INCOMINGREPORTS AS ir
    ON ir.ReportID = iv.ReportID
  WHERE ir.INTERNALID = ?
    AND iv.LOINCCODE <> ''
    AND TRY_CAST(
          CASE WHEN PATINDEX('%[0-9.-]%', iv.RESULTVALUE) > 0
            THEN SUBSTRING(iv.RESULTVALUE, PATINDEX('%[0-9.-]%', iv.RESULTVALUE), LEN(iv.RESULTVALUE))
            ELSE iv.RESULTVALUE
          END
          AS FLOAT
        ) IS NOT NULL
),
/* ==== PASS 1: Harmonize RESULTNAME for LOINC codes that have multiple names ==== */
MultiNameCodes AS
(
  SELECT INTERNALID, LOINCCODE
  FROM AllValues
  GROUP BY INTERNALID, LOINCCODE
  HAVING COUNT(DISTINCT RESULTNAME) > 1
),
LatestName AS
(
  SELECT INTERNALID
       , LOINCCODE
       , RESULTNAME AS MostRecentResultName
  FROM
  (
    SELECT
      INTERNALID,
      LOINCCODE,
      RESULTNAME,
      ROW_NUMBER() OVER(
        PARTITION BY INTERNALID, LOINCCODE
        ORDER BY REPORTDATE DESC
      ) AS rn
    FROM AllValues
  ) x
  WHERE rn = 1
),
NameHarmonized AS
(
  SELECT
    a.INTERNALID,
    a.REPORTDATE,
    a.LOINCCODE,
    CASE
      WHEN m.LOINCCODE IS NOT NULL THEN ln.MostRecentResultName
      ELSE a.RESULTNAME
    END AS RESULTNAME,
    a.RESULTVALUE,
    a.UNITS,
    a.[RANGE],
    a.ABNORMALFLAG,
    -- Pass 2's key: the name, with percentages apart from counts ("Monocytes" as
    -- 5905-5 % and as 742-7 x10*9/L are two tests). One column keeps the plan.
    CASE
      WHEN m.LOINCCODE IS NOT NULL THEN ln.MostRecentResultName
      ELSE a.RESULTNAME
    END + CASE WHEN a.UNITS LIKE '%[%]%' THEN N' [%]' ELSE N'' END AS CODEKEY
  FROM AllValues AS a
  LEFT JOIN MultiNameCodes AS m
    ON a.INTERNALID = m.INTERNALID
   AND a.LOINCCODE  = m.LOINCCODE
  LEFT JOIN LatestName AS ln
    ON a.INTERNALID = ln.INTERNALID
   AND a.LOINCCODE  = ln.LOINCCODE
),
/* ==== PASS 2: Harmonize LOINCCODE for RESULTNAMEs that have multiple codes
        (keyed on CODEKEY, so percentages and counts stay apart) ==== */
MultiCodeNames AS
(
  SELECT INTERNALID, CODEKEY
  FROM NameHarmonized
  GROUP BY INTERNALID, CODEKEY
  HAVING COUNT(DISTINCT LOINCCODE) > 1
),
LatestCode AS
(
  SELECT INTERNALID
       , CODEKEY
       , LOINCCODE AS MostRecentLoincCode
  FROM
  (
    SELECT
      INTERNALID,
      CODEKEY,
      LOINCCODE,
      ROW_NUMBER() OVER(
        PARTITION BY INTERNALID, CODEKEY
        ORDER BY REPORTDATE DESC
      ) AS rn
    FROM NameHarmonized
  ) y
  WHERE rn = 1
)
/* ==== FINAL SELECT ==== */
SELECT
  nh.INTERNALID,
  nh.REPORTDATE                                                          AS ReportDate,
  CASE
    WHEN mc.CODEKEY IS NOT NULL THEN RTRIM(lc.MostRecentLoincCode)
    ELSE RTRIM(nh.LOINCCODE)
  END                                                                    AS LoincCode,
  RTRIM(nh.RESULTNAME)                                                   AS ResultName,
  -- Charting needs a plain float: strip a leading comparator ('<3' -> '3',
  -- '>90' -> '90') so the numeric remainder can be plotted, same technique
  -- already used for the curated /charts page (patient_charts_pathology.sql).
  RTRIM(
    CASE WHEN nh.RESULTVALUE LIKE '%<%' OR nh.RESULTVALUE LIKE '%>%'
      THEN SUBSTRING(nh.RESULTVALUE, PATINDEX('%[0-9.-]%', nh.RESULTVALUE), LEN(nh.RESULTVALUE) - PATINDEX('%[0-9.-]%', nh.RESULTVALUE) + 1)
      ELSE nh.RESULTVALUE
    END
  )                                                                       AS ResultValue,
  RTRIM(nh.UNITS)                                                        AS Units,
  RTRIM(nh.[RANGE])                                                      AS Range,
  RTRIM(nh.ABNORMALFLAG)                                                 AS AbnormalFlag
FROM NameHarmonized AS nh
LEFT JOIN MultiCodeNames AS mc
  ON nh.INTERNALID = mc.INTERNALID
AND nh.CODEKEY    = mc.CODEKEY
LEFT JOIN LatestCode     AS lc
  ON nh.INTERNALID = lc.INTERNALID
AND nh.CODEKEY    = lc.CODEKEY
WHERE NOT (
  LTRIM(RTRIM(nh.LOINCCODE)) IN ('704-7' ,'711-2', '713-8', '731-0', '736-9','742-7', '751-8', '770-8', '5905-5')
  AND LTRIM(RTRIM(nh.UNITS)) LIKE '%[\\]%'
)
ORDER BY nh.RESULTNAME;
