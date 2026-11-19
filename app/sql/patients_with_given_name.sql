-- How many patients carry a given name as their first or middle name — the
-- reach of a name-variant entry, shown before an administrator adds it
-- (ADR-049). Parameter: '% name %' (lower case, padded with spaces).
SELECT COUNT(*) AS n
FROM PATIENTS
WHERE RecordStatus = 1
  AND (' ' + LOWER(LTRIM(RTRIM(REPLACE(ISNULL(FirstName, ''), '-', ' ')))) + ' '
       + LOWER(LTRIM(RTRIM(REPLACE(ISNULL(MiddleName, ''), '-', ' ')))) + ' ') LIKE ?;
