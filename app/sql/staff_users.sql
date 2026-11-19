-- Every BP user's name and group, for naming document authors by role
-- (patient_json_service._relabel_staff_authors). GroupCode per USERGROUPS.
-- Deliberately no status filter (USERSTATUS / RECORDSTATUS): inactive and deleted users
-- still count. That includes "shadow" users a practice enters under a practitioner's
-- preferred name, so tools that read only BP redact and detect it too (upstream ADR-112).
-- Do not add an active-only filter.
SELECT UserId                  AS user_id,
       LOWER(TRIM(FirstName)) AS first_name,
       LOWER(TRIM(Surname))   AS surname,
       GroupCode              AS group_code
FROM USERS
WHERE Surname IS NOT NULL AND LEN(TRIM(Surname)) > 1;
