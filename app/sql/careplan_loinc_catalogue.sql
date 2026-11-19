-- Every LOINC code in the practice's results from the last 5 years, filed and in the inbox, with
-- the names and units laboratories reported it under (ADR-129, the result token pick list).
-- Counts only: no patient columns. Grouped by code, name and unit; the service folds them by code.
WITH AllValues AS
(
  SELECT rv.LOINCCODE, rv.RESULTNAME, rv.UNITS, rv.REPORTDATE
  FROM dbo.REPORTVALUES AS rv
  WHERE rv.LOINCCODE <> '' AND rv.REPORTDATE >= DATEADD(year, -5, GETDATE())
  UNION ALL
  SELECT iv.LOINCCODE, iv.RESULTNAME, iv.UNITS, iv.REPORTDATE
  FROM dbo.INCOMINGVALUES AS iv
  WHERE iv.LOINCCODE <> '' AND iv.REPORTDATE >= DATEADD(year, -5, GETDATE())
)
SELECT
  LTRIM(RTRIM(LOINCCODE))  AS LoincCode,
  LTRIM(RTRIM(RESULTNAME)) AS ResultName,
  LTRIM(RTRIM(UNITS))      AS Units,
  COUNT(*)                 AS Results,
  MAX(REPORTDATE)          AS LastDate
FROM AllValues
GROUP BY LTRIM(RTRIM(LOINCCODE)), LTRIM(RTRIM(RESULTNAME)), LTRIM(RTRIM(UNITS));
