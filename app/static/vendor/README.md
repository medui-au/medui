# Vendored front-end libraries

These are served from MedUI itself, so a workstation never loads code from a third-party
server. Each file is exactly as published on npm. The package tarball was checked against
npm's published sha512 integrity before the file was copied. Each library's licence is kept
beside it.

| Library | Version | File | Licence |
|---|---|---|---|
| Chart.js | 4.6.1 | `chartjs-4.6.1/chart.umd.min.js` | MIT |
| chartjs-adapter-moment | 1.0.1 | `chartjs-adapter-moment-1.0.1/chartjs-adapter-moment.min.js` | MIT |
| Moment.js | 2.29.4 | `moment-2.29.4/moment.min.js` | MIT |

- **Chart.js and the adapter** are the versions the pages already used: the CDN served them for the unversioned URLs on 2026-11-08, byte for byte.
- **Moment.js** went from 2.29.1 to 2.29.4, which fixes CVE-2022-31129 (slow parsing of long date strings). The API is unchanged.

**To update one:**
1. Download the new version's npm tarball.
2. Check its integrity against `registry.npmjs.org/<name>/<version>`.
3. Copy the file into a new folder named with the version.
4. Change the templates and this table.

`tests/test_no_external_scripts.py` fails if a template loads a script or stylesheet from another server.
