-- Fetches a list of active users for the login dropdown.
-- Groups: auth_service.LOGIN_GROUP_LEVELS.
SELECT
    LTRIM(RTRIM(Firstname)) + ' ' + LTRIM(RTRIM(Surname)) AS Name,
    USERID as UserId
FROM USERS
WHERE Groupcode IN (1, 3, 4, 5, 7, 42)
  AND recordstatus = 1
  AND userstatus IN (1, 2)
ORDER BY Surname
