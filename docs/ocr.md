# Recommended local LiteParse OCR

The `ocr` Compose profile builds the upstream
[LiteParse REST server](https://github.com/run-llama/liteparse-server) at commit
`70cee35fb429f531d657d3328dc9939c89c0312b`, using its slim Dockerfile and lockfile.
It runs alongside PostgreSQL on the practice host. No separate summarisation
server, cloud API key or local language model is required for this integration.

```bash
docker compose --profile ocr up -d --build --wait liteparse
```

- Flask in a host venv: `OCR_SERVICE_URL=http://127.0.0.1:5707`.
- Flask in Compose: `OCR_CONTAINER_URL=http://liteparse:5707` (default).
- Existing OCR installation: set both URLs for the corresponding network location.
- A saved OCR service in Setup overrides environment defaults; disabling that saved
  service also disables the environment fallback. Only one OCR configuration is
  selected (the first saved record).
- In Setup → External services, enter the address as MedUI sees it. With MedUI in
  Compose that is `http://liteparse:5707`: inside the app container `127.0.0.1` is
  the app container itself, and the host's LAN address isn't published.

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
