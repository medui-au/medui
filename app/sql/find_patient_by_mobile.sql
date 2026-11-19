-- Finds other patients whose mobile number matches either of two candidate
-- numbers (typically an NOK/Emergency Contact's two contact phone fields,
-- since NEXTOFKIN doesn't label which of its two phone slots is a mobile).
-- Caller passes the same value twice when only one candidate is valid, and
-- normalizes both to digits-only (spaces stripped) before calling, matching
-- the normalization already applied here.
-- The LEN guard on this side is deliberate: without it, two blank/short
-- candidate values could both match a patient whose own MOBILEPHONE is
-- blank, producing false "matches" purely from comparing empty strings.
SELECT DISTINCT InternalId
FROM PATIENTS
WHERE InternalId <> ?
  AND LEN(REPLACE(TRIM(MOBILEPHONE), ' ', '')) >= 8
  AND REPLACE(TRIM(MOBILEPHONE), ' ', '') IN (?, ?)
