# Releasing

How a MedUI release is numbered, checked and published. Written for the maintainers of this
repository; practices and IT providers only need [operations](../operations.md) for upgrades.

## Version numbers

One number, in `app/version.py`, using semantic versioning: `MAJOR.MINOR.PATCH`.

- **0.x** — pre-release. **1.0.0** is the first public release.
- **MINOR** — new functions, and **any change to a seeded AI prompt or workflow**: a prompt states
  what an AI function is for, so changing one changes the intended purpose.
- **PATCH** — fixes that don't change what a function is for.
- **MAJOR** — changes that need practices to act, such as a database step that can't be undone.

The version shows at the foot of every page and in `/health` (`"version": "…"`), so a practice can
always say which release it runs.

## Release checklist

1. **AI functions and intended purpose**
   - Every shipped function fits the [intended purpose](../intended_purpose.md). If a function or its
     wording no longer fits, change the function, or change the statement deliberately as a MINOR
     release.
   - The statement paragraph is the same in `docs/intended_purpose.md`, `README.md` and `AGENTS.md`
     (`test_intended_purpose_statement_matches` checks), and on medui.com.au (check by hand). The
     About page renders the docs file directly.
   - New UI text, prompts, docs, release notes and website copy keep to the
     [wording below](#wording).
   - **In-app help** (`app/help/`, the [?] buttons and `/help`) is part of the instructions for
     use: it matches what each screen does, `flask help check` passes (`test_help_check`), and
     sections whose `reviewed:` date is over a year old are checked again.
   - Every seeded AI prompt and workflow is reviewed by a clinician against the TGA boundary: does it
     generate a diagnosis or differential, a treatment recommendation, a prognosis, or advice to
     patients? Anything that does is not shipped without TGA advice.
   - The AI information sheet lists every shipped AI function, its purpose, limits and regulatory
     status, and matches the seeds.
2. **Redaction**
   - Regression tests pass, and any rule change has been replayed against recorded runs with no
     newly visible identifiers.
3. **Licences**
   - No GPL or AGPL dependency without a recorded decision (`test_dependency_licences`).
   - LICENSE is the GNU AGPL v3, unchanged; NOTICE names the copyright holder and lists the
     third-party components; the vendored redaction core wheel carries its own LICENSE and NOTICE.
4. **Tests and installation**
   - `pytest` passes, including the database tests against a throwaway PostgreSQL.
   - A fresh install with `install.sh` and, for Windows, `scripts/windows/create_medui_wsl2.ps1`
     reaches a working login.
5. **Seeds**
   - If `app/seed_assets/starter.json` changed, run `python scripts/build_seed_history.py`
     and commit `seed_history.json` and `manifest.json` with it. The seed resync can only
     update installations whose seeds it recognises; `test_seed_history_covers_current_seeds`
     fails until this is done.
6. **Records**
   - `app/version.py` bumped and `CHANGELOG.md` updated in the same commit.
   - Known limitations stated in the changelog or the information sheet.
   - [Release status](../release-status.md): its version line, what is in place and what is
     left, at least at each MINOR release.
7. **Making the repository public** (the first public release only)
   - The public home is the `medui-au` organisation: this repository becomes `medui-au/medui`,
     a fresh copy with one first commit, and the demo databases `medui-au/medui_demodata`.
   - Point every address at it. The scripts keep theirs in one variable each (`$RepoUrl` and
     `$DemoRepoUrl` in `scripts/windows/create_medui_wsl2.ps1`, `$RepoUrl` in
     `upgrade_medui_wsl2.ps1`, `DEMO_REPO` in `scripts/demo_data.sh`); the docs and `medui.sh`
     have them in the text. `grep -rn 'github.com/' --exclude-dir=.git .` lists them all.
   - The "while the repository is private" token steps were removed in 0.61.3: a public clone
     needs no token. The scripts still accept one, for a private copy.
   - Make [medui_demodata](https://github.com/medui-au/medui_demodata) public at the same time,
     or first: the setup guide, cheat sheet and `./medui.sh bp` point test and demo installations
     to it. Check again that every row in it is invented.
   - Turn on private vulnerability reporting for the new repository ([SECURITY.md](../../SECURITY.md)).
   - Point existing installations at the new address (`git remote set-url origin …`) before
     their next upgrade.

## Wording

The TGA reads intended purpose from everything we say about MedUI — the app, its help, its prompts, docs,
release notes and website — and identical functions can become a medical device through claims
alone. In all of these:

- **Avoid:** "clinical decision support", "insights", "key/significant issues", "abnormal",
  "critical", "overdue", "consider repeating", "improves patient outcomes", "supports diagnosis",
  "detects", "explains your results".
- **Say instead** what MedUI saves, organises or shows: "saves documentation time", "keeps the
  record in one place", "outside the laboratory's reference range", "draft for review".
- **Describe AI output as a draft** for the health professional to review, edit and approve.
- **Nothing is aimed at patients or the public**; MedUI drafts communication, a person sends it.

## Publishing

The maintainers work in a private repository, and `medui-au/medui` holds the releases: each
release is published there as one commit. After the release commit is merged to `main` in the
working repository:

1. **Build the public copy.** In a clone of `medui-au/medui`, remove everything except `.git`,
   then unpack the working repository's `main` into it:
   `git -C <working repository> archive main | tar -x`.
2. **Point the addresses at the public repositories.** Replace the working repository's GitHub
   addresses with `medui-au/medui` and `medui-au/medui_demodata` (`grep -rn 'github.com/'
   --exclude-dir=.git .` lists them all). Change nothing else in the copy: a fix goes into the
   working repository first, then into the next release.
3. **Scan it** for internal addresses and hostnames, practice and staff names, personal emails,
   home paths, key-shaped strings and real-looking patient values (names, Medicare and phone
   numbers, dates of birth). Compare the hits with the last release's: each new one is either
   invented or removed.
4. **Test it:** the full test suite, with the database tests on an empty, disposable PostgreSQL
   database (`MEDUI_TEST_DATABASE_URL`, a name ending in `_test`).
5. **Commit and push** as one commit, with author and committer `MedUI <github@medui.com.au>` and
   the message `MedUI x.y.z`. Never force-push: installations follow `main`.
6. **Tag it** `vx.y.z` and push the tag. The tag must match `app/version.py`:

   ```bash
   git tag -a v0.61.4 -m "MedUI 0.61.4"
   git push origin main v0.61.4
   ```

Practices upgrade with `./upgrade.sh`, which follows `main`, or go to one release with
`./upgrade.sh --to vx.y.z` ([operations → upgrades](../operations.md#upgrades)).

The demo databases (`medui-au/medui_demodata`, built by its `tools/make_public_copy.sh`) and the
redaction core (`medui-au/redaction-core`, tagged at each core version) are published the same
way from their own working repositories, when they change.
