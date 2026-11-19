-- Medications ceased (DELETIONDATE populated) per doctor in [?, ?), plus how
-- many have a documented DELETIONREASON. Attributed to UPDATEDBY — ceasing a
-- medication is implemented as an update that sets DELETIONDATE/REASON, and
-- UPDATED/UPDATEDBY track that action (confirmed against DELETIONDATE via
-- schema introspection: same user, UPDATED a few hours after DELETIONDATE's
-- midnight timestamp).
SELECT
    UPDATEDBY AS bpsdb_userid,
    COUNT(*) AS ceased,
    SUM(CASE WHEN DELETIONREASON IS NOT NULL AND LEN(TRIM(DELETIONREASON)) > 0 THEN 1 ELSE 0 END) AS ceased_with_reason
FROM CURRENTRX
WHERE DELETIONDATE IS NOT NULL
  AND DELETIONDATE >= ?
  AND DELETIONDATE < ?
GROUP BY UPDATEDBY
