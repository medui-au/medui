-- Best Practice's dictionary names for past-history items (ADR-108): an item's
-- ITEMCODE is the term ID. A term has several names (synonyms); RECORDSTATUS 1 =
-- current. Used only to fill condition_codes.bp_item, for reading. No parameters.
SELECT TERMID, TRIM(TERMNAME) AS TERMNAME, RECORDSTATUS
FROM BPSDrugs.dbo.TERMNAMES
ORDER BY TERMID, TERMNAMEID;
