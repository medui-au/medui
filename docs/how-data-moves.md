# How data moves

**For:** anyone who wants to see, without the technical detail, where a practice's data goes when
MedUI uses AI, and what guards it. **You'll know:** what stays inside the practice, what reaches a
cloud service, and which checks and switches a request passes.

**Where data goes.** MedUI runs inside the practice and reads Best Practice through a read-only
login. Full text goes only to models on the practice's own equipment. A cloud model gets redacted
text; a cloud speech-to-text service gets the audio as recorded. A draft reaches Best Practice only
when the user pastes it or files it as a PIT file.

![Where data goes: MedUI inside the practice reads Best Practice read-only; local models get full
text, a cloud model redacted text, cloud speech-to-text the audio as recorded; drafts reach Best
Practice through the user.](images/medui-where-data-goes.svg)

**The guards on one AI request.** The security pre-check refuses a cloud model for anything not
fully redacted, or when the patient's identifiers couldn't be loaded. The privacy check looks at the
prompt exactly as it will be sent; on the screens that can show it, a request that still holds the
patient's or a practitioner's details waits until the user removes them. Names are restored inside
MedUI. The run record holds patient details and is removed with Purge after the practice's period;
the usage record holds none.

![The guards on one AI request, in order: start, assemble and redact, security pre-check (refuses
a cloud model unless fully redacted), privacy check, model, restore names, draft for
review.](images/medui-guards-on-a-request.svg)

**Switches and fixed guards.** A cloud request passes switches that IT, Best Practice's user
groups, the practice's administrators and each user set, and guards that no setting turns off. No
switch sends text that isn't fully redacted to a cloud model.

![Switches and fixed guards: AI on (IT), AI allowed (BP user group), model and workflow
(administrator), then the pre-check, redaction and privacy check (always on), and review first (each
user).](images/medui-switches-and-guards.svg)

The rules behind these diagrams are in the [intended purpose](intended_purpose.md) and the
[AI information sheet](ai-information-sheet.md); the technical detail is in
[how MedUI is built](technical.md).
