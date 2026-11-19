SELECT
    RecordId,
    Stored,
    INTERNALID,
    TRIM(Subject)      AS Subject,
    TRIM(ContactName)  AS Recipient,
    TRIM(Sendername)   AS Sender,
    CONVERT(VARCHAR(10), CORRESPONDENCEDATE, 103) AS CorrespondenceDate
FROM CORRESPONDENCEOUT
WHERE RecordId = ?
