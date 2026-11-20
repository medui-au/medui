# [Practice name]: request for read-only database access (EDBA)

*Template from the MedUI release. A practice that wants to use MedUI applies to Best Practice
Software for an Elevated Database Access Agreement (EDBA), using BP's own process and forms. This
page suggests wording for the parts that describe what the access is for. Adapt it to your
practice, and replace everything in square brackets. Best Practice Software decides whether to
grant access and on what terms; follow whatever process and conditions it sets.*

## Before you apply

- **Read the agreement BP sends you,** in particular its permitted purpose and its exclusions. The
  access is for the practice's own use, on the practice's own systems.
- **Decide how the practice will use AI,** and adopt the [AI-use policy](practice-ai-use-policy.md)
  first. If you will use only AI that runs on the practice's own computers, say so: it is the
  simplest position to explain.
- **Know which databases to ask for** (below), and the name of the computer MedUI will run on.

## Databases to request (read-only)

| Database | What MedUI reads it for |
|---|---|
| `BPSPatients` | The patient record: demographics, history, results, medications, appointments |
| `BPSDocumentsInbox` | Documents and results waiting in clinicians' inboxes |
| `BPSDocuments` (each numbered store, e.g. `BPSDocuments1`) | The contents of filed documents |
| `BPSDrugs` (optional) | The names Best Practice uses for past-history items, so conditions are shown by name. MedUI works without it. |

## Suggested wording: purpose of access

> [Practice name] requests read-only access to its Bp Premier databases (`BPSPatients`,
> `BPSDocumentsInbox` and the `BPSDocuments` databases[, and `BPSDrugs` for condition names]) for
> use by MedUI, open-source software that the practice installs and runs on its own premises.
>
> The access would allow the practice's clinicians and staff to read and summarise information
> already in the practice's patient records, including documents and reports in clinicians'
> inboxes, through the practice's own on-site application, and to produce reports for the
> practice's own administration and quality improvement.

## Suggested wording: how the access will be used

> - **Read-only.** The application connects with the read-only login provided under the agreement.
>   It does not write to, alter or delete anything in Bp Premier. It is not a replacement for
>   Bp Premier, which remains the practice's clinical record.
> - **On site.** The application runs on [the practice's own server / a computer at the practice],
>   on the practice network, and is reached only by the practice's own staff.
> - **For the practice's own patients and purposes.** The information is used by [practice name]
>   in caring for its patients and running the practice, as part of the practice's existing
>   responsibilities for the records it holds. It is not sold, or provided to third parties for
>   their own use.
> - **Artificial intelligence.** [Choose one:]
>   - [The practice uses only AI that runs on its own computers. No record information leaves the
>     practice.]
>   - [Where the practice chooses to use a cloud AI service, the application removes patient and
>     practitioner identifiers before any text is sent, and restores them only within the practice.
>     The practice's use of AI is governed by its AI-use policy and its obligations under the
>     *Privacy Act 1988*.]
> - **Drafts for review.** AI output is a draft that a clinician reviews, edits and approves. The
>   application does not diagnose, recommend treatment or triage patients.
> - **Security.** Access to the application is limited to staff with a login, and the
>   database password is stored only on the server that uses it.

## Suggested wording: closing

> We appreciate Best Practice Software's role in protecting the integrity and security of the
> Bp Premier database, and we will keep to the terms and conditions of the agreement. We are happy
> to answer any questions about how the access will be used, or to adjust our request to meet
> Best Practice Software's requirements.

## After access is granted

- Keep the signed agreement with the practice's records, and note its renewal or review date.
- Use the login only for what the agreement permits. If the practice's use changes (for example,
  starting to use a cloud AI service), check that it is still covered before making the change.
- The [Administrator setup guide](../setup-guide.md#what-the-administrator-needs) explains where the
  login goes in MedUI.
