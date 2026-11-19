-- Snapshot of each doctor's pending (unfiled) inbox: RECORDSTATUS = 1 means
-- still awaiting action — 0 is filed/actioned. Age buckets use REPORTDATE
-- (when the result became available to review), not COLLECTIONDATE (when
-- the specimen was taken) — the former is what "how long has this sat
-- unactioned" actually means.
SELECT
    USERID AS bpsdb_userid,
    COUNT(*) AS total,
    COUNT(DISTINCT INTERNALID) AS patients,
    SUM(CASE WHEN DATEDIFF(day, REPORTDATE, GETDATE()) < 90 THEN 1 ELSE 0 END) AS age_lt_3m,
    SUM(CASE WHEN DATEDIFF(day, REPORTDATE, GETDATE()) BETWEEN 90 AND 179 THEN 1 ELSE 0 END) AS age_3_6m,
    SUM(CASE WHEN DATEDIFF(day, REPORTDATE, GETDATE()) BETWEEN 180 AND 269 THEN 1 ELSE 0 END) AS age_6_9m,
    SUM(CASE WHEN DATEDIFF(day, REPORTDATE, GETDATE()) BETWEEN 270 AND 364 THEN 1 ELSE 0 END) AS age_9_12m,
    SUM(CASE WHEN DATEDIFF(day, REPORTDATE, GETDATE()) >= 365 THEN 1 ELSE 0 END) AS age_gt_12m
FROM INCOMINGREPORTS
WHERE RECORDSTATUS = 1
GROUP BY USERID
