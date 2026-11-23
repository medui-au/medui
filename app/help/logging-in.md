---
title: Logging in and access
area: Getting started
roles: [reception, nurse, doctor, admin]
reviewed: 2026-11-23
related: [patient-search]
---

You log in to MedUI with your **Best Practice** login: choose your name, then type your Best
Practice password. What you can do in MedUI follows your group in Best Practice.

## Who can log in {#who-can-log-in}

The list of names comes from Best Practice's users. A user appears when:

- their group is Practice Manager, Practice Owner, Doctor, Practice Nurse or Receptionist;
- their user record is active; and
- they are set up as **full time** or **part time**. Users set up as **locum** don't
  appear and can't log in.

If someone is missing, check their user in Best Practice (*Setup → Users*). A change there
shows in MedUI's list straight away.

There is also a **local administrator** account, made when MedUI was installed. It works even
when Best Practice can't be reached, for setting MedUI up and fixing problems.

If the Best Practice database connection hasn't been set in the installation's settings file
yet, an administrator who logs in is taken to **Application Setup → Database**, which says what
to add, with a notice at the top. This happens at each login until the connection is set; other
users log in as usual.

## What each person can use {#access}

Your access is set from your Best Practice group each time you log in:

| Best Practice group | In MedUI |
|---|---|
| Practice Manager, Practice Owner | Everything, including **Application Setup** and the administration pages |
| Doctor | Patient files, the day sheet and inbox, and the **AI functions** (AI assistant, scribe, chatbots) |
| Practice Nurse, Receptionist | Patient files, the day sheet and inbox; no AI functions |

To change someone's access, change their group in Best Practice; it applies at their next
login. Your name at the top right opens **My settings**, for your own preferences.

## Your password {#password}

MedUI checks your password against Best Practice and doesn't keep a copy of it. To change it,
change it in Best Practice. Sign out at the top right when you leave a shared computer.

## Help and About {#help-about}

**Help ▾** at the top right opens **Help** (this guide) and **About**, which shows which
version of MedUI is running. Give the version when you report a problem.
