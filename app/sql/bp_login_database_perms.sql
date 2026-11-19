-- ADR-139: what the MedUI login may do in the current database. Reads permissions only.
-- Run inside each database by bp_login_service (EXEC <db>.sys.sp_executesql).
-- writable_tables counts tables with an INSERT, UPDATE or DELETE grant, so permissions
-- granted table by table are caught as well as the write roles.
SELECT IS_ROLEMEMBER('db_owner')                              AS db_owner,
       IS_ROLEMEMBER('db_datawriter')                         AS db_datawriter,
       IS_ROLEMEMBER('db_ddladmin')                           AS db_ddladmin,
       HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'CREATE TABLE') AS create_table,
       HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'ALTER')        AS alter_database,
       (SELECT COUNT(*) FROM sys.tables t
         WHERE HAS_PERMS_BY_NAME(QUOTENAME(SCHEMA_NAME(t.schema_id)) + '.' + QUOTENAME(t.name), 'OBJECT', 'INSERT') = 1
            OR HAS_PERMS_BY_NAME(QUOTENAME(SCHEMA_NAME(t.schema_id)) + '.' + QUOTENAME(t.name), 'OBJECT', 'UPDATE') = 1
            OR HAS_PERMS_BY_NAME(QUOTENAME(SCHEMA_NAME(t.schema_id)) + '.' + QUOTENAME(t.name), 'OBJECT', 'DELETE') = 1
       )                                                      AS writable_tables,
       (SELECT COUNT(*) FROM sys.procedures p
         WHERE HAS_PERMS_BY_NAME(QUOTENAME(SCHEMA_NAME(p.schema_id)) + '.' + QUOTENAME(p.name), 'OBJECT', 'EXECUTE') = 1
       )                                                      AS executable_procedures
