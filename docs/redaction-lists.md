# Admin redaction lists

Redaction works from each patient's own record without any setup. Optional
lists, kept in **Admin → Mapping Tables**, add to it. Each is an
ordinary mapping table: create it with the name shown, then add rows in the
grid or import a CSV (`identifier_labels` is created for you by `install seeds`). Edits apply within a minute. While a table doesn't exist,
redaction carries on without it and the log notes that it's unavailable.

| Table | What it does | Columns |
|---|---|---|
| `identifier_labels` | The value after a listed label (`UR: 123456`, `Accession Number: …`) becomes `[ID Removed]`; the label stays. | `label`, `shape`, `active`, `note` |
| `always_redact` | A string redacted from every prompt: an outside specialist, an organisation, a place. | `string`, `label`, `fixed_text`, `active`, `note` |
| `name_variants` | A shortened form of a first or middle name (`Bec` for Rebecca, `Theo` for Theodore) that MedUI's built-in list of common short forms doesn't have: for every patient with that name, the form is redacted too. Privacy Review's **Add to future redactions** adds rows here. | `name`, `form`, `active`, `note` (also `added_by`, `added_at`, `source_run`, filled in when a row comes from Privacy Review) |
| `first_names` | Adds a first name to the common first-names sweep (`include` true) or takes one out (`include` false). Names that are also English words, such as John, Peter or Mark, are left out of the sweep unless added here. | `name`, `include`, `note` |
| `doc_exclusion_signatures` | Documents whose title contains the signature are left out of the document blocks and listed as filtered instead. | `signature`, `label`, `match_in`, `active` |

A blank `active` counts as on; `false`, `no`, `0` or `off` switch a row off.

## `identifier_labels`

Other services give the patient their own numbers: a hospital UR, a radiology
accession number, a lab's patient ID. They are found by the label written
before them. Admins enter **labels, not regular expressions**: the code adds
the matching around each label.

- The label matches in any case and with any spacing, as a whole word. It may
  be followed by `No`, `No.`, `Number`, `Num` or `#`, then a colon.
- Without a `shape`, the value is one run of letters, digits and hyphens, 4 to
  26 characters, with at least four digits. Dates, and a bare year straight
  after the label ("previous episode 2019"), are left alone.
- With a `shape`, the value must match it exactly: `9` is a digit, `A` a
  letter, `X` either, anything else as written (`AA-9999` matches `AB-1234`).
- Only the value is replaced, with the fixed text `[ID Removed]`. It is not
  restored in the output: an AI query almost never needs the number, and the
  document still holds it.

`install seeds` creates this table with 17 starting labels, all switched on
(UR, URN, MRN, Accession, Patient ID, Lab No, Specimen, Client ID and others),
if it doesn't exist yet; see [seed-data.md](seed-data.md#admin-lists). Review them
for the services your practice deals with. The same labels are in
[`identifier_labels_seed.csv`](identifier_labels_seed.csv), for importing into a
table you create yourself.

Known limits: a value written with spaces between digit groups
(`MRN: 1234 5678`) loses only its first group, and only the first value after a
label is taken.
