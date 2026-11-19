# Portable seed data

Seed assets live in `app/seed_assets/`. `manifest.json` records the format version,
SHA-256 checksums, counts and provenance. They are included in the app image.
The installer reads only these packaged files, never `.legacy/` or its database.

| Package | Contents |
| --- | --- |
| Starter | 12 system prompts, 17 user prompts, 4 data bundles, 12 draft pipelines, 6 inactive message templates |
| Optional reference | 402 unapproved drug mappings, 57 vaccine mappings, 2 NIP risk mappings |
| Admin lists | 17 identifier labels (`identifier_labels`), installed with the starter package |

The source is a read-only extraction of legacy MedUI reference/configuration
records on 1 October 2026. No patients, users, run history, credentials, AI accounts,
models, practice settings or author/approval identities are included. Internal
prompt IDs are resolved by name in the destination database. BP product/vaccine
identifiers are retained because they are the lookup keys; check them against the
receiving practice's BP dictionary before use.

## Install or preview

Apply schema migrations and installation defaults first. In the host venv:

```bash
.venv/bin/flask --app wsgi install seeds --dry-run
.venv/bin/flask --app wsgi install seeds
```

To include the reference tables after reviewing `reference.json`:

```bash
.venv/bin/flask --app wsgi install seeds --include-reference-data --dry-run
.venv/bin/flask --app wsgi install seeds --include-reference-data
```

For Docker, rebuild the app image to include the assets, then use the equivalent
command (add `--include-reference-data` when wanted):

```bash
docker compose --profile app build app
docker compose --profile app run --rm app flask --app wsgi install seeds --dry-run
docker compose --profile app run --rm app flask --app wsgi install seeds
```

Installation is insert-only: existing names and BP identifiers are skipped,
including customised or disabled records. Existing bundles and pipelines are
preserved as a whole; missing children are not inserted into an existing parent.
It does not set default workflows, enable AI/messaging, or select an AI model.
Repeated runs add no duplicates. Errors roll back the entire transaction, including
new mapping tables. Dry runs exercise the writes and roll them all back. Existing
mapping tables with incompatible columns or a missing registry entry cause a
rollback rather than being overwritten. Back up the database before installation.

## After an upgrade: seed resync

Installation never changes what is already there, so after `git pull` and a rebuild
the database still holds the previous release's seeded prompts and workflows,
including any the release has dropped. The resync brings them up to the release:

```bash
.venv/bin/flask --app wsgi install resync-seeds --dry-run     # list what would change
.venv/bin/flask --app wsgi install resync-seeds               # apply
```

(Docker: `docker compose --profile app run --rm app flask --app wsgi install resync-seeds …`
after rebuilding the image and running `db upgrade`.)

- **Updated:** seeded system prompts, prompts and workflows that are still exactly as
  an earlier release seeded them. Each release's seeds are fingerprinted in
  `app/seed_assets/seed_history.json`.
- **Kept:** each workflow's model, data bundle, status (draft or active) and other step
  settings; each prompt's model, assistant listing and active flag; everything the
  practice created.
- **Edited here:** a seeded item the practice has changed is listed and left alone.
  To take the release version anyway: `--replace "<name>"` (repeatable).
- **Added:** seeded items new in the release, as `install seeds` would.
- **Given new settings:** a setting a release adds (a system prompt's scope, a workflow's
  notice) is filled only where the item has none; a choice already made is kept.
- **Dropped from the release:** listed. With `--archive-dropped`, workflows are archived
  and prompts made inactive, never deleted. A dropped prompt still used by one of the
  practice's own workflows, or a system prompt still named by an active prompt, is kept.
- **Reverting:** a replaced prompt's earlier text is kept in `user_prompt_versions`; a
  replaced system prompt stays as its inactive earlier version. Back up the database
  first all the same.

Data bundles and message templates are not changed by the resync. One transaction:
any error rolls back everything.

## AI scope and notices (seed format 4)

Every seeded system prompt names its **scope instruction** (`scope_key`): `record`
for prompts that work from the record, `scribe` for the consultation write-ups,
`general` for the generic chatbot and the Library assistant, and `none` only for
the two utilities whose output is processed text (PII eraser, text formatting
cleanup). A workflow can override it on its prompt step (Diabetes Education uses
`general`, as it works from no record), and chooses its on-screen **notice** on its
inference step (`summary` for the summary workflows, `scribe` for the write-ups;
otherwise the page's default). The wordings themselves are installed by
`db upgrade` and edited in Application Setup → AI scope. On an existing install
the seed resync fills a scope or notice only where none has been chosen.

## Review before use

System/user prompts are available for selection, but are not global defaults and
are not added to assistant quick-select menus. Workflows are drafts with
`redact_all` (except PII Erasure, below); review their prompts and bundle contents, configure a provider/model,
and activate only the workflows the practice wants. Some standalone prompts are
provided as library material without a corresponding workflow. Clinical wording
is inherited and has not been clinically validated by the packaging tests.

Message templates are inactive. Review their text and configure this practice's
identity and delivery settings before activating them. Practice-specific phone,
website and facility references have been removed or generalised.

Drug approvals are deliberately reset. Review and approve mappings through the
application before they are used by its approved-mapping lookup. Existing local
approvals are preserved on reruns.

Vaccine/risk tables have no approval flag in the existing app. **Importing the
optional reference package makes those tables available to the eligibility
service immediately.** These two risk rows are a legacy snapshot, not a complete
or current NIP schedule. Validate both identifiers and the application's clinical
rules before relying on eligibility output. Five vaccine rows with no numeric BP
identifier were omitted. Without reference installation, missing tables continue
to report that eligibility has not been assessed.

Private summary-server blocks and workflows, experimental workflows, duplicate
local workflows, unredacted pipelines and the old external screening chain are
excluded. Document explanation prompts remain usable with the preserved OCR
functions; they do not require the old summary server. Old bundle placeholders
were converted to `{{data.blocks}}`, and the transcript placeholder to
`{{input.raw_transcript}}`. A caller must supply the inputs required by its prompt.

## Admin lists

`admin_lists.json` holds starting rows for admin-managed lists. Each list's table
is created, with its rows, **only if it doesn't exist yet**. After that the list
belongs to the practice: a later `install seeds` run never adds, changes or
restores rows in it, so a label switched off or deleted stays that way. An
installation made before this list existed gets it on its next `install seeds` run.

The one list so far is `identifier_labels`: labels such as UR, URN, MRN,
Accession and Patient ID, all switched on. The value written after one becomes
`[ID Removed]` in AI prompts. See [redaction-lists.md](redaction-lists.md) for
what they catch, and review them in Admin → Mapping Tables.

## Maintaining the package

Edit the JSON assets intentionally and update their SHA-256 values and counts in
`manifest.json` in the same change. Do not export an entire installation database
into the package. Tests verify checksums, graph references, supported blocks,
transaction rollback and preservation of local edits. Package updates do not
replace existing prompts or mappings; changes to installed content need a separate
reviewed update process.

## Generic chatbot

The Chatbot page (questions without a patient) uses two of the seeded workflows, found
by their classifiers. Activate Chatbot Generic to use it; activate PII Erasure as well
if the practice has a local model:

| Workflow | Steps | Redaction | Model |
| --- | --- | --- | --- |
| PII Erasure (`[chatbot_generic_pii]`) | prompt → inference | `redact_none` | Default local model |
| Chatbot Generic (`[chatbot_generic]`) | prompt → inference → de-redaction | `redact_all` | Default chatbot model |

PII Erasure sends the question unredacted, so it must use a local model: choose one as
the default local model in Setup → AI Providers. Should a cloud model be selected
instead, the pipeline's security check refuses the run. Chatbot Generic applies
rule-based redaction to the question before its model sees it.

**Without a local model** (PII Erasure left as draft), the chatbot still works: on the
first message in each chat the user confirms a warning that there is no AI erasure step,
a banner stays on the page, and questions get the rule-based redaction only, which can
miss names typed in free text. Each such message is counted in the usage record
(`chatbot.message_no_erasure`). To refuse instead, set Setup → AI scope → "General
chatbot without the PII Erasure workflow" to **Not allowed**. While PII Erasure is
active it always runs first, and a failure refuses the message rather than falling back.
A pipeline's editor has **Activate** / **Deactivate** beside its status.

Common first names that are also English words (John, Peter, Mark…) are left out of
the first-name sweep; add the ones your practice wants caught to the `first_names`
mapping table with `include` true ([redaction lists](redaction-lists.md)).

Seed format 3 added `admin_lists.json` (above). Seed format 2 added what these need: an optional `redaction_policy` per workflow
(absent means `redact_all`), the two prompt-only step sequences, and an inference
step's `model_default` (`local` or `chatbot`), which names the kind of default model
rather than a model.
