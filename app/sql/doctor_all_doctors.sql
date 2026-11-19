SELECT
    u.UserId                                                     AS bpsdb_userid,
    RTRIM(LTRIM(u.FirstName)) + ' ' + RTRIM(LTRIM(u.Surname))   AS full_name
FROM USERS u
WHERE u.RecordStatus = 1
  AND u.PRESCRIBERNO IS NOT NULL
  AND LEN(RTRIM(LTRIM(u.PRESCRIBERNO))) > 0
ORDER BY u.Surname, u.FirstName
