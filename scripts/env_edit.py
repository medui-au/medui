#!/usr/bin/env python3
"""Change settings in an installation's .env safely (used by medui.sh).

    python3 scripts/env_edit.py set KEY [KEY ...]     values from the environment: MEDUI_SET_<KEY>
    python3 scripts/env_edit.py get KEY               prints the value (never use for secrets)
    python3 scripts/env_edit.py has KEY [KEY ...]     exit 0 when every key has a non-blank value

Values come from environment variables, never the command line, so a password doesn't show
in the process list or shell history. Before writing, the current file is copied to
.env.bak (mode 600); the new file is written beside it and moved into place (mode 600).

Quoting follows both readers of .env: Docker Compose (env_file, which expands $ outside
single quotes) and python-dotenv. A value with anything beyond letters, digits and
\\ . _ - : / @ + , is written in single quotes, which both take literally. A value with a
single quote or a line break can't be written safely, and is refused.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

SAFE = re.compile(r'^[A-Za-z0-9_.\-:/@+,\\]*$')
KEY = re.compile(r'^[A-Z][A-Z0-9_]*$')


class EnvError(ValueError):
    pass


def quote(value: str) -> str:
    if "'" in value or '\n' in value or '\r' in value:
        raise EnvError("contains a single quote or a line break, which .env can't hold safely")
    return value if SAFE.match(value) else f"'{value}'"


def unquote(raw: str) -> str:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
        return raw[1:-1]
    return raw.split(' #', 1)[0].strip()


def read_values(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k, v = line.split('=', 1)
            values[k.strip()] = unquote(v)
    return values


def set_values(path: Path, updates: dict[str, str]) -> None:
    for k in updates:
        if not KEY.match(k):
            raise EnvError(f'{k}: not a setting name')
    rendered = {}
    for k, v in updates.items():
        try:
            rendered[k] = quote(v)
        except EnvError as e:
            raise EnvError(f'{k} {e}') from None
    old = path.read_text()
    lines, done = [], set()
    for line in old.splitlines():
        k = line.split('=', 1)[0].strip() if '=' in line and not line.lstrip().startswith('#') else None
        if k in rendered:
            if k not in done:
                lines.append(f'{k}={rendered[k]}')
                done.add(k)
            continue                     # a repeated key: keep only the one just written
        lines.append(line)
    lines += [f'{k}={rendered[k]}' for k in rendered if k not in done]
    backup = path.with_name(path.name + '.bak')
    _write_private(backup, old)
    tmp = path.with_name(path.name + '.new')
    _write_private(tmp, '\n'.join(lines) + '\n')
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def _write_private(path: Path, text: str) -> None:
    if path.exists():
        path.unlink()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write(text)


def main(argv: list[str]) -> int:
    path = Path(os.environ.get('MEDUI_ENV_FILE', Path(__file__).resolve().parents[1] / '.env'))
    if len(argv) < 2 or argv[0] not in ('set', 'get', 'has'):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    if not path.exists():
        print(f'No .env at {path}: MedUI is not installed in this folder.', file=sys.stderr)
        return 1
    cmd, keys = argv[0], argv[1:]
    if cmd == 'get':
        print(read_values(path).get(keys[0], ''))
        return 0
    if cmd == 'has':
        values = read_values(path)
        return 0 if all(values.get(k, '').strip() for k in keys) else 1
    try:
        set_values(path, {k: os.environ.get(f'MEDUI_SET_{k}', '') for k in keys})
    except EnvError as e:
        print(f'Not changed: {e}.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
