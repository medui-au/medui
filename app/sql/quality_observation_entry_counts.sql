-- Count of OBSERVATIONS values entered per user, per datacode, in a date window.
-- Datacodes: 3=Systolic, 4=Diastolic, 7=Height, 8=Weight.
-- USERID (not CREATEDBY) is the clinician the observation was recorded under;
-- CREATEDBY is frequently 0 for bulk-imported legacy data.
SELECT
    o.USERID   AS bpsdb_userid,
    o.DATACODE AS datacode,
    COUNT(*)   AS entry_count
FROM OBSERVATIONS o
WHERE o.RECORDSTATUS = 1
  AND o.DATACODE IN (3, 4, 7, 8)
  AND o.OBSDATE >= ?
  AND o.OBSDATE < ?
GROUP BY o.USERID, o.DATACODE
ORDER BY o.USERID, o.DATACODE
