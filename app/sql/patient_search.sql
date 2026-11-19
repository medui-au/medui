SELECT TOP (50)
    InternalId,
    TRIM(Firstname)
        + CASE WHEN LEN(TRIM(ISNULL(MiddleName,''))) > 0 THEN ' ' + TRIM(MiddleName) ELSE '' END
        + ' ' + TRIM(Surname) AS Name,
    ISNULL(CONVERT(VARCHAR(10), DOB, 103), 'N/A') AS DOB,
    DATEDIFF(YEAR, DOB, GETDATE()) - CASE
        WHEN MONTH(DOB) > MONTH(GETDATE())
          OR (MONTH(DOB) = MONTH(GETDATE()) AND DAY(DOB) > DAY(GETDATE())) THEN 1 ELSE 0
    END AS Age,
    CASE WHEN SexCode = 1 THEN 'F' WHEN SexCode = 2 THEN 'M' ELSE '?' END AS Gender,
    CASE
        WHEN LEN(TRIM(ISNULL(MOBILEPHONE,''))) > 0 THEN REPLACE(TRIM(MOBILEPHONE), ' ', '')
        WHEN LEN(TRIM(ISNULL(HOMEPHONE,''))) > 0 THEN REPLACE(TRIM(HOMEPHONE), ' ', '')
        ELSE ''
    END AS Phone,
    ISNULL(TRIM(ADDRESS1)
        + CASE WHEN LEN(TRIM(ISNULL(ADDRESS2,''))) > 0 THEN ' ' + TRIM(ADDRESS2) ELSE '' END
        + ' ' + TRIM(CITY) + ' ' + TRIM(POSTCODE), '') AS Address,
    CASE WHEN PatientStatus = 1 THEN 'Active'
         WHEN PatientStatus = 2 THEN 'Inactive'
         WHEN PatientStatus = 3 THEN 'Deceased'
         ELSE 'Unknown' END AS Status
FROM PATIENTS
WHERE Surname LIKE ?
ORDER BY Surname, Firstname;
