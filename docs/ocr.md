# OCR (LiteParse)

OCR reads the text of scanned documents and images, so they can be searched, summarised and
shown as text. MedUI uses **LiteParse**, which runs in a container on the MedUI computer:
nothing is sent elsewhere.

## Nothing to set up

The installer builds and starts the LiteParse container and sets `OCR_ENABLED=true` in `.env`.
MedUI finds it by itself, at `http://liteparse:5707` inside Docker. There is no entry to add in
Setup: **Application Setup → External Sources** says the installation's own LiteParse is in
use, and the home page's installation status shows it as answering.

## Switching it off or on

| | |
|---|---|
| At installation | `./install.sh --no-ocr` doesn't build the container and sets `OCR_ENABLED=false` |
| Afterwards | `./medui.sh features OCR_ENABLED=off` removes the container (its image is kept); `=on` builds it if needed and starts it |
| Stop or start it for a while | `./medui.sh ocr stop` / `./medui.sh ocr start` (the switch stays as it is) |

`OCR_ENABLED=false` turns OCR off completely, including any service saved in Setup. An `.env`
from before 0.50.0 has no `OCR_ENABLED` line: MedUI treats that as on, and `./upgrade.sh` adds the
line once, `true` if the installation has the LiteParse container and `false` if not.

## A different OCR server

A practice that already runs a compatible LiteParse server can use it instead: in **External
Sources → + Add Service**, choose type OCR and enter its address as MedUI sees it. Inside the app
container `127.0.0.1` is the app itself, and the host's LAN address doesn't reach the built-in
LiteParse, because its port is published on localhost only. A saved service replaces the
built-in one; disabling it turns OCR off; deleting it goes back to the built-in one. Only the
first saved OCR service is used. Keep `OCR_ENABLED=true` (with `--no-ocr` at installation, set
it back with `./medui.sh features OCR_ENABLED=on`, or edit `.env` and run `./medui.sh reload`
if you don't want the built-in container).

## Technical details

The `ocr` Compose profile builds the upstream
[LiteParse REST server](https://github.com/run-llama/liteparse-server) at commit
`70cee35fb429f531d657d3328dc9939c89c0312b`, using its slim Dockerfile and lockfile.
`OCR_CONTAINER_URL` (default `http://liteparse:5707`) is the address the app container uses;
`OCR_SERVICE_URL` is the one for MedUI run outside Docker.

The adapter sends the document as multipart `file` to `POST /parse?text=true`
and accepts `text/plain`, following the
[upstream API](https://github.com/run-llama/liteparse-server/blob/70cee35fb429f531d657d3328dc9939c89c0312b/API_SPEC.md).
The previous custom asynchronous litocr `/submit`/`status` protocol is not supported.
Image uploads are wrapped in a PDF locally (including all TIFF frames), avoiding
the upstream ImageMagick image-to-PDF policy restriction. A failed OCR request yields a visible extraction-unavailable placeholder; the
original PDF/image remains available in the viewer.

The upstream slim server does not supply an authentication layer. The supplied
Compose file therefore publishes it only on localhost. An existing remote service
can be placed behind an authenticated HTTPS proxy; configure `OCR_API_KEY` or the
Setup service key. TLS verification stays enabled. For a private CA, mount its
certificate into the app container and set `OCR_CA_BUNDLE` to that path.

The health probe submits no document and expects HTTP 400 for the missing file;
it establishes server reachability, not OCR accuracy. Test with synthetic scanned
pages before relying on a new installation.
