# Other ways to install

**For:** IT staff who need something the four recipes don't do. **Most installations should use a
[recipe](README.md):** one script, tested end to end, and upgraded with `./upgrade.sh`. The routes
below are for particular needs, and they leave more to you. Every route uses Docker: MedUI
without Docker isn't supported, so ask the maintainers if the practice's IT needs that.

| Route | When you might want it | Notes |
|---|---|---|
| [An Ubuntu WSL2 instance you already have](ubuntu-live.md) | You made the WSL2 instance yourself, or want to use one you have | The Ubuntu recipe, as on any Ubuntu: clone, then `./install.sh`. The instance gets none of the Windows side (mirrored networking, keep-alive task, firewall rules); the [Windows recipe](windows-live.md) arranges those for you. |
| [Docker Compose by hand](../technical.md#installing-by-hand) | Seeing or controlling each step that `install.sh` takes | The same result as the Ubuntu recipe, one command at a time. |
| [Every installer switch](../cheatsheet.md) | Ports, names, folders, HTTPS names and certificates, unattended installs (`--yes`) for scripts and coding agents | `./install.sh --help` lists them too. |

Whichever route you take, the [Administrator setup guide](../setup-guide.md) comes next.

[Back to installing MedUI](README.md)
