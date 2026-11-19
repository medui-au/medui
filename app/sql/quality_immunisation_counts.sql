-- Per-doctor, per-vaccine active immunisation counts in [?, ?). VACCINEID is
-- mapped to a disease category in Python (see app/indicators/immunisation_activity.py,
-- backed by the mapdata_vaccine_mapping table) rather than in SQL, since BPSDB
-- has no vaccine-category lookup table of its own. USERID (not ADMINISTEREDBY)
-- is used for attribution, consistent with every other indicator — the two
-- agree 99.8% of the time in this data.
SELECT
    USERID    AS bpsdb_userid,
    VACCINEID AS vaccineid,
    COUNT(*)  AS cnt
FROM IMMUNISATIONS
WHERE RECORDSTATUS = 1
  AND GIVENDATE >= ?
  AND GIVENDATE < ?
GROUP BY USERID, VACCINEID
