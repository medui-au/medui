-- The Recalls context block. Internal keys (REMINDERID, INTERNALID, USERID)
-- and BP's numeric status codes are not sent: the model cannot use them.
-- STATUS reads the codes with the patient screen's own rule
-- (patient_recalls.sql IS_STRUCK): closed once sent, or when either the record
-- or the reminder status is anything but 1.
SELECT TRIM(REMINDERS.REASONTEXT) AS REASONTEXT, REMINDERS.REMINDERDUE, REMINDERSSENT.SENTDATE,
CASE
    WHEN (REMINDERSSENT.SENTDATE IS NOT NULL) OR (REMINDERS.RECORDSTATUS <> 1) OR (REMINDERS.REMINDERSTATUS <> 1)
    THEN 'closed'
    ELSE 'outstanding'
END AS STATUS
FROM REMINDERS
LEFT OUTER JOIN REMINDERSSENT ON REMINDERS.REMINDERID = REMINDERSSENT.REMINDERID
WHERE Reminders.InternalId = ?
ORDER BY REMINDERDUE DESC;
