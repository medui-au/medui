-- A user's provider numbers, each with its site's name (ADR-125).
SELECT
    RTRIM(LTRIM(pl.PROVIDERNUMBER))           AS provider_no,
    RTRIM(LTRIM(ISNULL(l.LOCATIONNAME, '')))  AS site
FROM PROVIDER_LOCATION pl
LEFT JOIN LOCATIONS l ON l.LOCATIONID = pl.LOCATIONID
WHERE pl.USERID = ? AND pl.RECORDSTATUS = 1
ORDER BY site, provider_no
