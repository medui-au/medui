---
title: The scribe
area: AI functions
roles: [doctor]
requires_ai: true
reviewed: 2026-11-16
related: [ai-drafts]
---

The **scribe** turns a consultation into a transcript as you talk, then writes a draft note
from it. Follow the practice's policy on telling the patient and asking their consent before
you record.

## Recording {#recording}

- **● Record** starts and stops recording. The audio is turned into text a piece at a time
  (**Chunk interval**) by the speech-to-text model chosen under **ASR Model**, and the
  transcript grows as you go.
- **Who said what** comes one of two ways, and the line under **ASR Model** says which:
  - **Speaker turns from Deepgram**, when the practice has switched them on for that model:
    the transcript shows **[Speaker 1]** / **[Speaker 2]**. Deepgram numbers the speakers
    afresh in each chunk and doesn't know which is the doctor, so check the note says who
    said what correctly.
  - **Speaker labels from a local model** (**[Doctor]** / **[Patient]**), for any other
    model. This step sends the transcript as it was heard, before anything is removed, so
    it only runs on the practice's own equipment; without a local model there are no
    labels, and nothing is sent to a cloud service for this.
- The **ASR Model** list names the speech-to-text service. If it is a cloud service, the
  recording itself goes to that service to be transcribed: audio can't have names removed the
  way text can. The practice decides which services are offered.
- You can also type or paste into the transcript, or correct it, before writing the note.

## Writing the note {#write-up}

- **Pipeline:** the write-up workflow. The **Instructions** line under it shows what that
  workflow tells the AI; click it to read them in full.
- **Verbosity:** Brief, Normal or Detailed.
- **✦ Recompose** writes the draft note from the transcript. You can press it while still
  recording, even before the first chunk has come back: it stops the recording, waits for
  the last chunk's text, then writes the note. With a cloud model, the
  transcript has the patient's identifiers and practitioners' names removed first, and the
  request may stop on the **Sending** tab (see [the Sending tab](help:ai-drafts.sending)).
  Your own first name is removed too, however the transcript spells its capitals ("thanks
  sam"), except a first name that is also an everyday word, such as Will or Mark, which is
  removed only with a capital.
  No redaction is perfect: a name spoken differently from how it is recorded can get
  through, so check the Sending tab when it appears.

The note is a draft: check it against what was said and what you examined, and edit it
(see [AI drafts](help:ai-drafts.drafts)).

## Saving and filing {#saving}

- **💾 Save to Chart** keeps the transcript in MedUI, encrypted, for **30 days**, so you can
  come back to it. It doesn't put anything in Best Practice.
- **BP →** files the note in the patient's Best Practice record.
- **Print**, **Copy**, and **Clear** to start again.
