-- Fetches provider numbers for a given user across multiple locations
SELECT PROVIDERNUMBER 
FROM PROVIDER_LOCATION 
WHERE USERID = ? AND RECORDSTATUS = 1
