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
> that the practice runs on its own network.
>
> **Without AI**, the access would be used to:
> - find, organise and present information in the practice's own records, including results and
>   documents in clinicians' inboxes;
> - prepare documents from the record for a clinician to complete, such as care plans, handover
>   summaries, charts and consultation agendas;
> - produce reports for the practice's doctors, for quality improvement, continuing professional
>   development and accreditation;
> - support practice administration: staff rostering, reports, and notes on a patient's record
>   such as Medicare items they may be eligible for, or details that are missing or out of date.
>
> **With artificial intelligence (AI) services**, which may run on the practice's own computers or
> in the cloud, the access would also be used to:
> - summarise information in the record and draft the documents above. AI output is a draft that
>   a clinician reviews, edits and approves;
> - remove patient and practitioner identifiers from the text before any of it is sent to a cloud
>   AI service.
>
> The application only reads the databases and does not change anything in Bp Premier. It is used
> only by the practice's own staff. The practice is responsible for its use of the software,
> including its obligations under privacy law, and will use the access only as the agreement
> permits.

## After access is granted

- Keep the signed agreement with the practice's records. If the practice's use changes (for
  example, using the access for a purpose not described above), check that the agreement still
  covers it first.
- The [Administrator setup guide](../setup-guide.md#what-the-administrator-needs) explains where the
  login goes in MedUI.
