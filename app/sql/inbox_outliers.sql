WITH
FilteredIncomingReports AS
(
  SELECT
      IR.REPORTID,
      IR.INTERNALID,
      IR.USERID
  FROM dbo.INCOMINGREPORTS AS IR
  WHERE IR.INTERNALID IS NOT NULL
    AND IR.INTERNALID != 0
    -- One patient (results page, ADR-097) or everyone (0, the list).
    AND (? = 0 OR IR.INTERNALID = ?)
),
RelevantIncomingValues AS
(
    SELECT
        FR.INTERNALID,
        FR.REPORTID,
        FR.USERID,
        TRIM(IV.LOINCCODE) AS LOINCCODE,
        TRIM(IV.DATATYPE) AS DATATYPE,
        IV.REPORTDATE AS REPORTDATE,
        TRIM(IV.RESULTNAME) AS RESULTNAME,
        TRIM(IV.RESULTVALUE) AS RESULTVALUE,
        TRIM(IV.UNITS) AS UNITS,
        TRIM(IV.[RANGE]) AS [RANGE],
        TRIM(IV.ABNORMALFLAG) AS ABNORMALFLAG
    FROM dbo.INCOMINGVALUES AS IV
    INNER JOIN FilteredIncomingReports AS FR
        ON IV.REPORTID = FR.REPORTID
    WHERE TRIM(IV.LOINCCODE) IS NOT NULL
      AND TRIM(IV.LOINCCODE) <> ''
),
RankedIncomingValues AS
(
    SELECT
        INTERNALID,
        REPORTID,
        USERID,
        LOINCCODE,
        DATATYPE,
        REPORTDATE,
        RESULTNAME,
        RESULTVALUE,
        UNITS,
        [RANGE],
        ABNORMALFLAG,
        ROW_NUMBER() OVER(
            PARTITION BY INTERNALID, REPORTDATE, LOINCCODE, RESULTVALUE
            ORDER BY REPORTID
        ) AS rn
    FROM RelevantIncomingValues
),
DedupedIncomingValues AS
(
    SELECT
        INTERNALID,
        REPORTID,
        USERID,
        LOINCCODE,
        DATATYPE,
        REPORTDATE,
        RESULTNAME,
        RESULTVALUE,
        UNITS,
        [RANGE],
        ABNORMALFLAG
    FROM RankedIncomingValues
    WHERE rn = 1
),
IncomingValueLoinccodes AS
(
    SELECT DISTINCT INTERNALID, LOINCCODE
    FROM DedupedIncomingValues
    WHERE LOINCCODE IS NOT NULL AND LOINCCODE <> ''
),
ReportValuesRelevant AS
(
    SELECT
        RV.INTERNALID,
        RV.REPORTDATE,
        TRIM(RV.LOINCCODE) AS LOINCCODE,
        TRIM(RV.RESULTNAME) AS RESULTNAME,
        TRIM(RV.RESULTVALUE) AS RESULTVALUE,
        TRIM(RV.UNITS) AS UNITS,
        TRIM(RV.[RANGE]) AS [RANGE],
        TRIM(RV.ABNORMALFLAG) AS ABNORMALFLAG
    FROM dbo.REPORTVALUES AS RV
    INNER JOIN IncomingValueLoinccodes AS IVL
        ON RV.INTERNALID = IVL.InternalId
       AND TRIM(RV.LOINCCODE) = IVL.LOINCCODE
    WHERE TRIM(RV.LOINCCODE) IS NOT NULL
      AND TRIM(RV.LOINCCODE) <> ''
),
ReportValuesRanked AS
(
    SELECT
        INTERNALID,
        REPORTDATE,
        LOINCCODE,
        RESULTNAME,
        RESULTVALUE,
        UNITS,
        [RANGE],
        ABNORMALFLAG,
        ROW_NUMBER() OVER(
            PARTITION BY INTERNALID, LOINCCODE
            ORDER BY REPORTDATE DESC
        ) AS rn
    FROM ReportValuesRelevant
),
Top2ReportValues AS
(
    SELECT
        INTERNALID,
        REPORTDATE,
        LOINCCODE,
        RESULTNAME,
        RESULTVALUE,
        UNITS,
        [RANGE],
        ABNORMALFLAG
    FROM ReportValuesRanked
    WHERE rn <= 2
),
AllValuesCombined AS
(
    SELECT INTERNALID, LOINCCODE, REPORTDATE, RESULTNAME, RESULTVALUE, UNITS, [RANGE], ABNORMALFLAG
    FROM DedupedIncomingValues
    UNION ALL
    SELECT INTERNALID, LOINCCODE, REPORTDATE, RESULTNAME, RESULTVALUE, UNITS, [RANGE], ABNORMALFLAG
    FROM Top2ReportValues
),
PatientsInScope AS
(
    SELECT DISTINCT
        FR.InternalId,
        TRIM(P.FIRSTNAME) + ' ' + TRIM(P.SURNAME) AS PATIENTNAME
    FROM FilteredIncomingReports AS FR
    INNER JOIN dbo.PATIENTS AS P
      ON FR.InternalId = P.InternalId
    WHERE P.InternalId IS NOT NULL
)
SELECT
    P.PATIENTNAME,
    AVC.INTERNALID,
    AVC.LOINCCODE,
    AVC.REPORTDATE,
    AVC.RESULTNAME,
    AVC.RESULTVALUE,
    AVC.UNITS,
    AVC.[RANGE],                 -- as the lab reports it (ADR-097)
    AVC.ABNORMALFLAG
FROM AllValuesCombined AS AVC
INNER JOIN PatientsInScope AS P
    ON AVC.InternalId = P.InternalId
ORDER BY AVC.INTERNALID, AVC.LOINCCODE, AVC.REPORTDATE;
