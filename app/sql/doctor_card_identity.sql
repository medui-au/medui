-- The numbers on a user's details card (ADR-125). No password columns.
SELECT
    RTRIM(LTRIM(ISNULL(u.REGISTRATIONNO, '')))  AS registration_no,
    RTRIM(LTRIM(ISNULL(u.HPII, '')))            AS hpii,
    RTRIM(LTRIM(ISNULL(u.PROVIDERNO, '')))      AS provider_no,
    RTRIM(LTRIM(ISNULL(u.PRESCRIBERNO, '')))    AS prescriber_no
FROM USERS u
WHERE u.USERID = ?
