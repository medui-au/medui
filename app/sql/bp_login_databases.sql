-- ADR-139: the user databases the MedUI login can open (system databases excluded).
SELECT name
FROM sys.databases
WHERE database_id > 4
  AND state_desc = 'ONLINE'
  AND HAS_DBACCESS(name) = 1
ORDER BY name
