FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates unixodbc libodbc2 \
    && curl -fsSLo /tmp/msprod.deb https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb \
    && dpkg -i /tmp/msprod.deb && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && rm -rf /var/lib/apt/lists/* /tmp/msprod.deb
COPY requirements.txt ./
COPY vendor ./vendor
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd --create-home --uid 10001 medui && mkdir -p /app/instance && chown medui:medui /app/instance
COPY app ./app
COPY migrations ./migrations
COPY wsgi.py ./
COPY docs ./docs
# Pages the docs link to, for the in-app guide (app/services/guide_docs.py)
COPY README.md CHANGELOG.md SECURITY.md AGENTS.md CONTRIBUTING.md ./
COPY scripts/windows/README.md ./scripts/windows/README.md
# The files keep the checkout's permissions; a restrictive umask on the host (for
# example left over from a backup) would leave them unreadable to the app user.
RUN chmod -R a+rX /app/app /app/migrations /app/docs /app/wsgi.py
USER medui
EXPOSE 8000
# One worker, several threads: a pipeline run's progress queue lives in the worker's
# memory (PipelineEngine._RUN_QUEUES), so the request that starts a run and the browser's
# progress stream must reach the same process. With two workers they could land apart
# and the stream would never find its queue.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", "--timeout", "120", "wsgi:app"]
