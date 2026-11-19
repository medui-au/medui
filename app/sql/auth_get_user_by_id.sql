-- Attempts to authenticate a user against BPSDB using their USERID.
SELECT USERID, Firstname, Surname, RegistrationNo, ProviderNo, PrescriberNo, PasswordSalt, Password, GroupCode
FROM USERS
WHERE USERID = ? AND recordstatus = 1 AND userstatus IN (1, 2)
