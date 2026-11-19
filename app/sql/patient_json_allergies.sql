SELECT TRIM(ItemName) AS ItemName, TRIM(Reaction) AS Reaction, TRIM(Severity) AS Severity 
FROM BPS_REACTIONS WHERE InternalID = ?;
