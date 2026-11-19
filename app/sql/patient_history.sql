SELECT  
    CASE 
        WHEN YEAR = 0 THEN '' 
        ELSE CAST(YEAR AS VARCHAR(5)) 
    END AS YR, 
    UPPER(ITEMTEXT) + 
    CASE 
        WHEN LocationCode = 1 THEN ' (L)' 
        WHEN LocationCode = 2 THEN ' (R)' 
        WHEN LocationCode = 3 THEN ' (Bilateral)' 
        ELSE '' 
    END AS ItemText,
    CASE  
        WHEN DataLength(Details) > 0 THEN CAST(Details AS VARCHAR(Max))  
        ELSE ' ' 
    END AS DiagDetail, 
    CAST(ITEMCODE AS VarChar(8)) AS ItemCode
FROM 
    PASTHISTORY 
WHERE 
    InternalId = ? 
    AND recordstatus = 1 
    -- STATUSCODE 0 is a "Reason for visit" copied to Past History: kept when coded (ADR-145).
    AND NOT (STATUSCODE = 0 AND ITEMCODE = 0)
ORDER BY 
    Year DESC;
