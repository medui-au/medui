-- One patient's numeric pathology results, filed and in the inbox, read once
-- (ADR-097, the results-outside-range page). Same rows as patient_pathatom.sql
-- before its name/code harmonisation, which repeats this scan several times;
-- the page harmonises in Python instead (inbox_outlier_service.harmonise).
-- Params: INTERNALID, INTERNALID.
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
)
SELECT
  REPORTDATE                                                             AS ReportDate,
  RTRIM(LOINCCODE)                                                       AS LoincCode,
  RTRIM(RESULTNAME)                                                      AS ResultName,
  RTRIM(RESULTVALUE)                                                     AS ResultValue,
  RTRIM(UNITS)                                                           AS Units,
  RTRIM([RANGE])                                                         AS Range,
  RTRIM(ABNORMALFLAG)                                                    AS AbnormalFlag
FROM AllValues
WHERE NOT (
  LTRIM(RTRIM(LOINCCODE)) IN ('704-7' ,'711-2', '713-8', '731-0', '736-9','742-7', '751-8', '770-8', '5905-5')
  AND LTRIM(RTRIM(UNITS)) LIKE '%[\\]%'
);
