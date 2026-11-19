# Reporting a security problem

MedUI handles patient records, so please report a security problem privately, not in a public
issue.

**How:** use **Report a vulnerability** on this repository's **Security** tab. Only the maintainers
see the report.

**Include:** the MedUI version (at the foot of every page, or `/health`), what you did, what
happened, and what an attacker could gain. **Never include patient details**, passwords, API keys
or the contents of `.env`. If you need an example, make one up.

**What happens next:** we acknowledge the report, agree a fix and a time to publish it with you,
and credit you if you want. Please give us a reasonable time to fix it before telling others.

**In scope:** MedUI's code, its installer and scripts, and the redaction it applies before cloud
AI. A way for text to reach a cloud model without redaction, or for MedUI to write to Best
Practice, is always serious.

**Not in scope:** Best Practice itself, the AI providers, and an installation set up against the
[installation guide](docs/install/README.md), for example one opened to the internet.
