-- ADR-139: what the MedUI login may do on the whole server. Reads permissions only.
SELECT IS_SRVROLEMEMBER('sysadmin')                 AS is_sysadmin,
       HAS_PERMS_BY_NAME(NULL, NULL, 'CONTROL SERVER') AS control_server
