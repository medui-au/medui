WITH RankedData AS (
    SELECT
        InternalId,
        DataCode,
        DataName,
        DataValue,
        ISNULL(CONVERT(VARCHAR(10), ObsDate, 23), '') AS DateName,
        ObsDate,
        ROW_NUMBER() OVER (PARTITION BY InternalId, DataCode ORDER BY ObsDate DESC) AS RowNum
    FROM Observations
    WHERE DataValue IS NOT NULL AND RECORDSTATUS < 2
),
NextAppointment AS (
    SELECT
        A.InternalId,
        ISNULL(
            FORMAT(DATEADD(second, A.APPOINTMENTTIME, A.APPOINTMENTDATE), 'yyyy-MM-dd HH:mm') + ' ' +
            RTRIM(LEFT(U.FIRSTNAME, 1) + LEFT(U.SURNAME, 1)) + ' ' +
            CAST(DATEDIFF(dd, A.Created, GETDATE()) AS VARCHAR) + 'd ago' +
            ' ' + TRIM(A.REASON),
        '') AS NEXT_APPOINTMENT_VALUE,
        ROW_NUMBER() OVER (PARTITION BY A.InternalId ORDER BY A.AppointmentDate, A.AppointmentTime) AS rn
    FROM APPOINTMENTS AS A
    INNER JOIN USERS AS U ON A.USERID = U.USERID
    WHERE A.RECORDStatus = 1 AND DATEDIFF(dd, GETDATE(), A.AppointmentDate) > -1
),
TopNOK AS (
    SELECT
        NK.InternalId,
        TRIM(NK.FIRSTNAME) + ' ' +
        TRIM(NK.SURNAME) + ' ' +
        REPLACE(NK.CONTACTPHONE, ' ', '') + ' ' +
        REPLACE(NK.CONTACTPHONE2, ' ', '') + ' ' +
        TRIM(NK.RELATIONSHIP) AS NOK_VALUE,
        ROW_NUMBER() OVER (PARTITION BY NK.InternalId ORDER BY NK.NextofKinid DESC) AS rn_nok
    FROM NEXTOFKIN AS NK
    WHERE NK.recordstatus = 1
),
LatesteGFR AS (
    SELECT
        CombinedResults.InternalId,
        -- As the laboratory wrote it ('52', '>90'), not stripped to a number (ADR-104).
        TRIM(CombinedResults.RESULTVALUE) AS LAST_eGFR,
        ISNULL(CONVERT(VARCHAR(10), CombinedResults.REPORTDATE, 23), '') AS LAST_eGFR_DATE,
        ROW_NUMBER() OVER (PARTITION BY CombinedResults.InternalId ORDER BY CombinedResults.REPORTDATE DESC) AS rn_egfr
    FROM (
        SELECT
            IR.INTERNALID,
            IV.RESULTVALUE,
            IV.REPORTDATE
        FROM INCOMINGREPORTS IR
        INNER JOIN INCOMINGVALUES IV ON IR.REPORTID = IV.REPORTID
        WHERE (IR.INTERNALID = ?)
        AND (IV.LOINCCODE IN ('33914-3', '15423-7', '62238-1', '50210-4', 'AUSLAB^EGFR'))
        UNION ALL
        SELECT
            internalid,
            Resultvalue,
            reportdate
        FROM REPORTVALUES
        WHERE internalid = ?
        AND (LOINCCODE IN ('33914-3', '15423-7', '62238-1', '50210-4', 'AUSLAB^EGFR'))
    ) AS CombinedResults
),
ATSIFlag AS (
    SELECT
        InternalId,
        CASE
            WHEN MAX(CASE WHEN Ethniccode IN (1,2,3) THEN 1 ELSE 0 END) = 1 THEN 'True'
            WHEN MAX(CASE WHEN Ethniccode = 999      THEN 1 ELSE 0 END) = 1 THEN 'False'
            ELSE NULL
        END AS Is_ATSI
    FROM PatientEthnicity
    WHERE InternalId = ?
    GROUP BY InternalId
)
SELECT
    P.InternalId AS INTERNALID,
    TRIM(P.FirstName) AS FIRSTNAME,
    TRIM(P.MiddleName) AS MIDDLENAME,
    TRIM(P.Surname) AS SURNAME,
    ISNULL(CONVERT(VARCHAR(10), P.DOB, 23), '') AS DOB,
    TRIM(PS.StatusText) AS STATUSTEXT,
    CASE WHEN SexCode = 1 THEN 'Female' WHEN SexCode = 2 then 'Male' ELSE 'Unknown' END AS GENDER,
    (TRIM(P.MEDICARENO) + ' ' + P.MEDICARELINENO + ' ' + TRIM(ISNULL(P.MEDICAREEXPIRY, ''))) AS MEDICARENO,
    TRIM(P.PensionNo) AS PENSIONNO,
    TRIM(P.DVANO) AS DVANO,
    P.IHI AS IHI,
    TRIM(P.ADDRESS1) + CASE WHEN LEN(TRIM(P.ADDRESS2)) > 0 THEN ' ' + TRIM(P.ADDRESS2) ELSE '' END +
    ', ' + TRIM(P.CITY) + ' ' + TRIM(P.POSTCODE) AS ADDRESS,
    '(H) ' + REPLACE(TRIM(P.HOMEPHONE), ' ', '') AS PHONE_HOME,
    '(M) ' + REPLACE(TRIM(P.MOBILEPHONE), ' ', '') AS PHONE_MOBILE,
    '(W) ' + REPLACE(TRIM(P.WORKPHONE), ' ', '') AS PHONE_WORK,
    CASE WHEN P.PreferredName IS NULL THEN TRIM(P.FirstName) + ' ' + TRIM(P.Surname) ELSE TRIM(P.FirstName) + ' "' + TRIM(P.PreferredName) + '" ' + TRIM(P.Surname) END AS NAME,
    DATEDIFF(YEAR, P.DOB, GETDATE()) - CASE WHEN MONTH(P.DOB) > MONTH(GETDATE()) OR (MONTH(P.DOB) = MONTH(GETDATE()) AND DAY(P.DOB) > DAY(GETDATE())) THEN 1 ELSE 0 END AS AGE,
    PE.EMail AS EMAIL,
    MAX(CASE WHEN RD.DataCode = '7' AND RD.DataValue IS NOT NULL THEN CAST(TRY_CAST(TRIM(RD.DataValue) AS DECIMAL(6,2)) / 100.00 AS DECIMAL(5,2)) ELSE NULL END) AS HEIGHTVALUE,  -- TRY_CAST: a malformed value is blank, not an error (ADR-145)
    ISNULL(MAX(CASE WHEN RD.DataCode = '7' THEN RD.DateName END), '') AS HEIGHT_DATE,
    -- The patient's age when that height was measured: a height from childhood is not
    -- used for an adult's BMI (app/utils/bmi.py). The height itself is shown at any age.
    MAX(CASE WHEN RD.DataCode = '7' AND RD.DataValue IS NOT NULL THEN
        DATEDIFF(YEAR, P.DOB, RD.ObsDate) - CASE WHEN MONTH(P.DOB) > MONTH(RD.ObsDate) OR (MONTH(P.DOB) = MONTH(RD.ObsDate) AND DAY(P.DOB) > DAY(RD.ObsDate)) THEN 1 ELSE 0 END
    END) AS HEIGHT_AGE,
    MAX(CASE WHEN RD.DataCode = '8' AND RD.DataValue IS NOT NULL THEN TRY_CAST(TRIM(RD.DataValue) AS DECIMAL(5,1)) ELSE NULL END) AS WEIGHTVALUE,  -- one decimal (was whole kg); malformed is blank (ADR-145)
    ISNULL(MAX(CASE WHEN RD.DataCode = '8' THEN RD.DateName END), '') AS WEIGHT_DATE,
    ISNULL(MAX(CASE WHEN RD.DataCode = '3' THEN TRIM(RD.DataValue) END), '') AS SYSTOLICBP,
    ISNULL(MAX(CASE WHEN RD.DataCode = '3' THEN RD.DateName END), '') AS SYSTOLICBP_DATE,
    ISNULL(MAX(CASE WHEN RD.DataCode = '4' THEN TRIM(RD.DataValue) END), '') AS DIASTOLICBP,
    ISNULL(MAX(CASE WHEN RD.DataCode = '4' THEN RD.DateName END), '') AS DIASTOLICBP_DATE,
    ISNULL(NA.NEXT_APPOINTMENT_VALUE, '') AS NEXT_APPOINTMENT,
    TNK.NOK_VALUE AS NOK,
    ISNULL(CAST(LE.LAST_eGFR AS VARCHAR(10)), '') AS LAST_eGFR,
    ISNULL(LE.LAST_eGFR_DATE, '') AS LAST_eGFR_DATE,
    ISNULL(CAST(AF.Is_ATSI AS VARCHAR(20)), 'Not recorded') AS Is_ATSI,
    P.MyMedicare,
    P.MyMedicareRegisteredLocation,
    P.MyMedicareRegistrationDate
FROM Patients AS P
LEFT JOIN Email AS PE ON P.InternalId = PE.InternalId
LEFT JOIN RankedData AS RD ON P.InternalId = RD.InternalId AND RD.RowNum = 1
LEFT JOIN PatientStatus AS PS ON P.PatientStatus = PS.StatusCode
LEFT JOIN NextAppointment AS NA ON P.InternalId = NA.InternalId AND NA.rn = 1
LEFT JOIN TopNOK AS TNK ON P.InternalId = TNK.InternalId AND TNK.rn_nok = 1
LEFT JOIN LatesteGFR AS LE ON P.InternalId = LE.InternalId AND LE.rn_egfr = 1
LEFT JOIN ATSIFlag AS AF ON P.InternalId = AF.InternalId
WHERE P.InternalId = ?
GROUP BY
    P.InternalId,
    P.FirstName,
    P.MiddleName,
    P.Surname,
    P.DOB,
    PS.StatusText,
    SEXCODE,
    P.MEDICARENO,
    P.MEDICARELINENO,
    P.MEDICAREEXPIRY,
    P.PensionNo,
    P.ADDRESS1,
    P.ADDRESS2,
    P.CITY,
    P.POSTCODE,
    P.HOMEPHONE,
    P.MOBILEPHONE,
    P.WORKPHONE,
    P.IHI,
    P.PREFERREDNAME,
    P.DVANO,
    PE.EMAIL,
    P.MyMedicare,
    P.MyMedicareRegisteredLocation,
    P.MyMedicareRegistrationDate,
    NA.NEXT_APPOINTMENT_VALUE,
    TNK.NOK_VALUE,
    LE.LAST_eGFR,
    LE.LAST_eGFR_DATE,
    AF.Is_ATSI;
