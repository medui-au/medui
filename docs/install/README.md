# Installing MedUI

**For:** whoever installs MedUI for the practice: comfortable with a command line, no Linux
expertise needed. **You'll know:** which recipe to follow, and what comes after it.

## Two questions

1. **Where will MedUI run?** On a Windows PC (it makes its own Ubuntu inside Windows, with WSL2),
   or on a computer that already runs Ubuntu.
2. **What is it for?** The practice's real use (**live**, reading the practice's BP), or trying it
   out (**demo**, with invented patients in a database of its own, never BP).

| | Live | Demo |
|---|---|---|
| **Windows PC** | [Windows PC, live](windows-live.md): run `create_medui_wsl2.ps1`, answer `L` | [Windows PC, demo](windows-demo.md): the same script, answer `d` |
| **Ubuntu** | [Ubuntu, live](ubuntu-live.md): run `./install.sh` | [Ubuntu, demo](ubuntu-demo.md): run `./install.sh --demo` |

Each recipe is one script, and the only difference between live and demo is one answer or one
switch. "Ubuntu" (tested on 24.04 and 26.10; any recent version should work) covers a bare-metal
or virtual server, an Ubuntu WSL2 instance you already have, and a second installation beside a
first one (a demo next to a live one, in its own folder). A demo can sit beside a live installation on the same computer, with ports of its own.

Each recipe page lists what to have ready, the one command, every question it asks and how to
choose, and how to check it worked.

## What to have ready for a live installation

- **The BP read-only password.** Best Practice Software supplies it under an Elevated Database
  Access Agreement (EDBA) with the practice. The practice applies to BP, and BP decides whether to
  grant it. MedUI installs and runs without it while you set up, using its own administrator
  login.
- **AI provider keys, only if you will use AI.** Nothing AI is on until you turn it on.
- **For workstations:** the computer's name on the practice network, and a fixed address, for
  HTTPS.

More on each: [what the administrator needs](../setup-guide.md#what-the-administrator-needs).

## After any recipe

The [Administrator setup guide](../setup-guide.md) is the same for every installation: connect
Best Practice, set up the workstations (HTTPS), OCR and AI, and back up. It is also in MedUI, at
**Admin → Application Setup → Administrator setup guide**.

Everyday tasks: `./medui.sh` in the installation's folder gives a menu.
[Backups, upgrades and removing MedUI](../operations.md).

## Other ways to install

With Docker Compose by hand, or in an Ubuntu WSL2 instance you already have: [other ways to install](other-ways.md),
for IT staff.

[Back to MedUI](../../README.md)
