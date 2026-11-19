-- Population-level patient cohort for the scatter chart.
-- Returns one row per patient (all statuses 1/2/3) with latest clinical values.
-- BMI and ExcessWeight are calculated in the Python service layer.
-- Height/weight observations taken before the patient turned 18 are excluded.
-- Ages are exact, to one decimal (ADR-147).

WITH
-- Latest Height, Weight, Systolic BP, Diastolic BP per patient.
-- Weight/height rows where the patient was under 18 at observation time are excluded.
Obs AS (
    SELECT r.InternalId,
        MAX(CASE WHEN r.DataCode = '7' AND r.RowNum = 1 THEN TRY_CAST(r.DataValue AS FLOAT) END) AS Height,
        MAX(CASE WHEN r.DataCode = '8' AND r.RowNum = 1 THEN TRY_CAST(r.DataValue AS FLOAT) END) AS Weight,
        MAX(CASE WHEN r.DataCode = '3' AND r.RowNum = 1 THEN TRY_CAST(r.DataValue AS INT)   END) AS SystolicBP,
        MAX(CASE WHEN r.DataCode = '4' AND r.RowNum = 1 THEN TRY_CAST(r.DataValue AS INT)   END) AS DiastolicBP,
        MAX(CASE WHEN r.DataCode = '8' AND r.RowNum = 1 THEN r.ObsDate                      END) AS WeightDate
    FROM (
        SELECT o.InternalId, o.DataCode, o.DataValue, o.ObsDate,
               ROW_NUMBER() OVER (PARTITION BY o.InternalId, o.DataCode ORDER BY o.ObsDate DESC) AS RowNum
        FROM BPSPATIENTS.dbo.Observations o
        JOIN BPSPATIENTS.dbo.PATIENTS p ON o.InternalId = p.InternalId
        WHERE o.DataValue IS NOT NULL
          AND o.RecordStatus = 1
          AND o.DataCode IN ('3', '4', '7', '8')
          -- Exclude height/weight recorded before the patient turned 18 (exact age:
          -- DATEDIFF(year) alone counts year changes, a year early before the birthday)
          AND (o.DataCode NOT IN ('7', '8')
               OR (p.DOB IS NOT NULL
                   AND DATEDIFF(year, p.DOB, o.ObsDate)
                       - CASE WHEN MONTH(p.DOB) > MONTH(o.ObsDate)
                                OR (MONTH(p.DOB) = MONTH(o.ObsDate) AND DAY(p.DOB) > DAY(o.ObsDate))
                              THEN 1 ELSE 0 END >= 18))
    ) r
    GROUP BY r.InternalId
),

-- Latest PSA (2857-1), eGFR (33914-3), HbA1c (4548-4) per patient
Labs AS (
    SELECT InternalId,
        MAX(CASE WHEN LoincCode = '2857-1'  THEN TRY_CAST(TRIM('<>^ ' FROM ResultValue) AS FLOAT) END) AS LastPSA,
        MAX(CASE WHEN LoincCode = '33914-3' THEN TRY_CAST(TRIM('<>^ ' FROM ResultValue) AS FLOAT) END) AS LasteGFR,
        MAX(CASE WHEN LoincCode = '4548-4'  THEN TRY_CAST(TRIM('<>^ ' FROM ResultValue) AS FLOAT) END) AS LastHbA1c
    FROM (
        SELECT InternalId, LoincCode, ResultValue,
               ROW_NUMBER() OVER (PARTITION BY InternalId, LoincCode ORDER BY ReportDate DESC) AS RowNum
        FROM BPSPATIENTS.dbo.REPORTVALUES
        WHERE ResultValue IS NOT NULL
          AND LoincCode IN ('2857-1', '33914-3', '4548-4')
    ) r
    WHERE RowNum = 1
    GROUP BY InternalId
),

-- Each patient's live, active, coded past-history items, as a comma list. The flags
-- (IsAF, IsDiabetic, ...) are worked out in scatter_service from the practice's
-- condition_codes table, as the Disease Profile badges are (ADR-146). Active is
-- STATUSCODE 1, or 0: a coded Reason for visit copied to Past History (ADR-145).
Conds AS (
    SELECT h.InternalId,
        STRING_AGG(CAST(h.ItemCode AS VARCHAR(MAX)), ',') AS ActiveCodes
    FROM (
        SELECT DISTINCT InternalId, ItemCode
        FROM BPSPATIENTS.dbo.PASTHISTORY
        WHERE RecordStatus = 1 AND ItemCode > 0 AND StatusCode IN (0, 1)
    ) h
    GROUP BY h.InternalId
),

-- Smoking — flag if any record indicates current smoker (SmokingCode = 3)
Tobacco AS (
    SELECT InternalId,
        MAX(CASE WHEN SmokingCode = 3 THEN 1 ELSE 0 END) AS IsSmoker
    FROM BPSPATIENTS.dbo.TOBACCO
    GROUP BY InternalId
),

-- Weekly alcohol units (most recent / max record per patient)
Alcohol AS (
    SELECT InternalId,
        MAX(ISNULL(DAYSPERWEEK, 0) * ISNULL(DRINKSPERDAY, 0)) AS WeeklyAlcohol
    FROM BPSPATIENTS.dbo.ALCOHOL
    GROUP BY InternalId
),

-- Next future appointment
NextAppt AS (
    SELECT InternalId,
        MIN(CAST(DATEADD(second, ISNULL(AppointmentTime, 0), AppointmentDate) AS DATETIME)) AS NextApptDate
    FROM BPSPATIENTS.dbo.Appointments
    WHERE AppointmentDate >= CAST(GETDATE() AS DATE)
      AND RecordStatus = 1
    GROUP BY InternalId
)

SELECT
    p.InternalId,
    TRIM(p.FirstName) + ' ' + TRIM(p.Surname)    AS PatientName,
    -- Exact age in years to one decimal (ADR-147), not whole years
    CAST(DATEDIFF(day, p.DOB, GETDATE()) / 365.25 AS DECIMAL(5,1)) AS Age,
    CASE p.SexCode WHEN 1 THEN 'Female' WHEN 2 THEN 'Male' ELSE NULL END AS Gender,
    p.PatientStatus,
    o.Height,
    o.Weight,
    CONVERT(VARCHAR(10), o.WeightDate, 23)                               AS WeightDate,
    CASE
        WHEN o.WeightDate IS NOT NULL AND p.DOB IS NOT NULL
        THEN CAST(DATEDIFF(day, p.DOB, o.WeightDate) / 365.25 AS DECIMAL(5,1))
        ELSE NULL
    END                                                                  AS AgeAtWeight,
    o.SystolicBP,
    o.DiastolicBP,
    l.LastPSA,
    l.LasteGFR,
    l.LastHbA1c,
    TRY_CAST(alc.WeeklyAlcohol AS INT)       AS WeeklyAlcohol,
    c.ActiveCodes,
    COALESCE(tob.IsSmoker,           0)      AS IsSmoker,
    na.NextApptDate
FROM BPSPATIENTS.dbo.PATIENTS p
LEFT JOIN Obs     o   ON p.InternalId = o.InternalId
LEFT JOIN Labs    l   ON p.InternalId = l.InternalId
LEFT JOIN Conds   c   ON p.InternalId = c.InternalId
LEFT JOIN Tobacco tob ON p.InternalId = tob.InternalId
LEFT JOIN Alcohol alc ON p.InternalId = alc.InternalId
LEFT JOIN NextAppt na ON p.InternalId = na.InternalId
WHERE p.PatientStatus IN (1, 2, 3)
ORDER BY p.InternalId
