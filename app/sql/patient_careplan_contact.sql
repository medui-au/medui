-- The one contact a care plan names (ADR-180): the most recently entered Emergency Contact
-- (TYPE 2), otherwise the most recent Next of Kin (TYPE 1). Active rows with a name only, as in
-- patient_get_demographics.sql. Parameter: patient_id.
SELECT TOP 1
    TRIM(FIRSTNAME)     AS FIRSTNAME,
    TRIM(SURNAME)       AS SURNAME,
    TRIM(RELATIONSHIP)  AS RELATIONSHIP,
    TRIM(CONTACTPHONE)  AS PHONE1,
    TRIM(CONTACTPHONE2) AS PHONE2,
    TYPE
FROM NEXTOFKIN
WHERE InternalId = ? AND recordstatus = 1 AND TYPE IN (1, 2)
  AND LEN(TRIM(ISNULL(FIRSTNAME, '')) + TRIM(ISNULL(SURNAME, ''))) > 0
ORDER BY TYPE DESC, NextofKinid DESC;
