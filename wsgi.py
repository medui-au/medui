import os

from app import create_app

app = create_app('production')

# Behind an HTTPS reverse proxy (Caddy in compose.yaml, or nginx on the native route),
# TRUSTED_PROXIES=1 takes the client's address and https from the proxy's X-Forwarded-*
# headers, so each workstation is recorded by its own address and links use https.
# Only set it when MedUI's own port is reachable from the proxy alone (127.0.0.1 or the
# Compose network): otherwise anyone could forge those headers.
_proxies = int(os.environ.get('TRUSTED_PROXIES') or 0)
if _proxies > 0:
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=_proxies, x_proto=_proxies, x_host=_proxies)
