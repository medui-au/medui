-- The patient's past-history items, for the condition codes (ADR-108,
-- app/services/condition_codes.py): which items count as each condition is the
-- admin table condition_codes, so this query only lists the items.
-- Parameter: patient_id.
SELECT
    ITEMCODE,
    TRIM(ITEMTEXT) AS ITEMTEXT,
    YEAR,
    RECORDID,
    STATUSCODE
FROM PASTHISTORY
WHERE InternalId = ? AND RECORDSTATUS = 1 AND ITEMCODE > 0;
