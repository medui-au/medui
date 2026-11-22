# [Practice name]: request for read-only database access (EDBA)

*Template from the MedUI release. A practice that wants to use MedUI applies to Best Practice
Software for an Elevated Database Access Agreement (EDBA), using BP's own process and forms.
Best Practice Software decides whether to grant access and on what terms. Below is suggested
wording for the part that describes what the access is for. Replace everything in square brackets
and adapt it to your practice.*

## Before you apply

- Decide how the practice will use AI, and adopt the [AI-use policy](practice-ai-use-policy.md).
- Read the permitted purpose and exclusions in the agreement BP sends you. The access may be used
  only for what the agreement permits.

## Databases to request (read-only)

| Database | What MedUI reads it for |
|---|---|
| `BPSPatients` | The patient record: demographics, history, results, medications, appointments |
| `BPSDocumentsInbox` | Documents and results waiting in clinicians' inboxes |
| `BPSDocuments` (each numbered store, e.g. `BPSDocuments1`) | The contents of filed documents |

## Suggested wording

> [Practice name] requests read-only access to its Bp Premier databases (`BPSPatients`,
> `BPSDocumentsInbox` and the `BPSDocuments` databases) for use with MedUI, open-source software
> that the practice runs on its own premises.
>
> The access would be used to:
> - read and summarise information in the practice's own records, including documents in
>   clinicians' inboxes, [with AI that runs on the practice's own computers / with AI services,
>   after patient and practitioner identifiers have been removed];
> - produce reports for the practice's own administration and quality improvement.
>
> The application only reads the databases and does not change anything in Bp Premier. It is used
> only by the practice's own staff. AI output is a draft that a clinician reviews. The practice
> will use the access only as the agreement permits.

## After access is granted

- Keep the signed agreement with the practice's records. If the practice's use changes (for
  example, starting to use a cloud AI service), check that the agreement still covers it first.
- The [Administrator setup guide](../setup-guide.md#what-the-administrator-needs) explains where the
  login goes in MedUI.
