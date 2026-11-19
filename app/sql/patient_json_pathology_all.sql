WITH AllValues AS (
    SELECT
        rv.INTERNALID,
        rv.REPORTDATE,
        rv.LOINCCODE,
        rv.RESULTNAME,
        CASE
            WHEN rv.LOINCCODE = '33914-3' AND rv.RESULTVALUE LIKE '%90%' THEN '90'
            ELSE rv.RESULTVALUE
        END AS RESULTVALUE,
        rv.UNITS,
        rv.[RANGE],
        rv.ABNORMALFLAG
    FROM dbo.REPORTVALUES AS rv
    WHERE rv.INTERNALID = ?
      AND rv.LOINCCODE IN (
            '10334-1','10535-3','12841-3','13965-9','14334-7','14631-6','14635-7','14646-4','14647-2','14648-0','14685-2',
            '14771-0','14804-9','14805-6','14920-3','14927-8','14928-6','14933-6','1742-6','1743-4','17856-6',
            '1920-8','1988-5','2064-4','2157-6','22748-8','2276-4','2324-2','24108-3','2532-0',
            '2601-3','2823-3','2857-1','2885-2','2890-2','29265-6','2951-2','3016-3','32294-1','32309-7',
            '33914-3','39469-2','43396-1','4537-7','4544-3','4548-4','50210-4','59261-8','61152-5','6690-2',
            '6768-6','70204-3','711-2','718-7','72160-5','731-0','742-7','751-8','777-3','787-2','789-8','9830-1',
            '14913-8','14955-9','38445-3'
        )
    UNION ALL
    SELECT
        ir.INTERNALID,
        iv.REPORTDATE,
        iv.LOINCCODE,
        iv.RESULTNAME,
        CASE
            WHEN iv.LOINCCODE = '33914-3' AND iv.RESULTVALUE LIKE '%90%' THEN '90'
            ELSE iv.RESULTVALUE
        END AS RESULTVALUE,
        iv.UNITS,
        iv.[RANGE],
        iv.ABNORMALFLAG
    FROM dbo.INCOMINGVALUES AS iv
    JOIN dbo.INCOMINGREPORTS AS ir ON ir.ReportID = iv.ReportID
    WHERE ir.INTERNALID = ?
      AND iv.LOINCCODE IN (
            '10334-1','10535-3','12841-3','13965-9','14334-7','14631-6','14635-7','14646-4','14647-2','14648-0','14685-2',
            '14771-0','14804-9','14805-6','14920-3','14927-8','14928-6','14933-6','1742-6','1743-4','17856-6',
            '1920-8','1988-5','2064-4','2157-6','22748-8','2276-4','2324-2','24108-3','2532-0',
            '2601-3','2823-3','2857-1','2885-2','2890-2','29265-6','2951-2','3016-3','32294-1','32309-7',
            '33914-3','39469-2','43396-1','4537-7','4544-3','4548-4','50210-4','59261-8','61152-5','6690-2',
            '6768-6','70204-3','711-2','718-7','72160-5','731-0','742-7','751-8','777-3','787-2','789-8','9830-1',
            '14913-8','14955-9','38445-3'
        )
),
Harmonized AS (
    SELECT
        INTERNALID,
        REPORTDATE,
        FIRST_VALUE(LOINCCODE) OVER (PARTITION BY RESULTNAME ORDER BY REPORTDATE DESC) AS LOINCCODE,
        FIRST_VALUE(RESULTNAME) OVER (PARTITION BY LOINCCODE ORDER BY REPORTDATE DESC) AS RESULTNAME,
        RESULTVALUE,
        UNITS,
        [RANGE],
        ABNORMALFLAG
    FROM AllValues
    WHERE NOT (
        LOINCCODE IN ('704-7','711-2','713-8','731-0','736-9','742-7','751-8','770-8','5905-5')
        AND UNITS LIKE '%\%'
    )
),
SampledResults AS (
    SELECT 
        *,
        -- Rank from Oldest (1) to Newest (TotalCount)
        ROW_NUMBER() OVER (PARTITION BY LOINCCODE ORDER BY REPORTDATE ASC) AS ChronoRank,
        -- Total items for this specific lab
        COUNT(*) OVER (PARTITION BY LOINCCODE) AS TotalCount
    FROM Harmonized
)
SELECT
    INTERNALID,
    CONVERT(VARCHAR(10), REPORTDATE, 23) AS REPORTDATE,
    RTRIM(LOINCCODE) AS LOINCCODE,
    RTRIM(RESULTNAME) AS RESULTNAME,
    RTRIM(RESULTVALUE) AS RESULTVALUE,
    RTRIM(UNITS) AS UNITS,
    RTRIM([RANGE]) AS [RANGE],
    RTRIM(ABNORMALFLAG) AS ABNORMALFLAG
FROM SampledResults
WHERE 
    -- If 6 or fewer results, keep everything
    TotalCount <= 6
    OR 
    (
        -- 1. The First Result
        ChronoRank = 1 
        OR 
        -- 2. The Last Three Results
        ChronoRank > (TotalCount - 3)
        OR 
        -- 3. Two evenly spaced "Nth" results between the 1st and (TotalCount - 2)
        -- This math picks the row at 1/3 and 2/3 of the way through the middle gap
        ChronoRank = FLOOR(1 + (TotalCount - 3) * 0.333)
        OR 
        ChronoRank = FLOOR(1 + (TotalCount - 3) * 0.666)
    )
ORDER BY RESULTNAME, REPORTDATE DESC;