# syntax=docker/dockerfile:1
# MedUI's OCR server: run-llama/liteparse-server, pinned at commit 70cee35, built with LiteParse
# 2.20.0 instead of the 2.4.0 its own lockfile fixes. The server's code is unchanged: only
# package.json (the LiteParse version) and pnpm-lock.yaml in this folder replace upstream's.
# Everything else follows upstream's slim.Dockerfile at that commit. See docs/ocr.md.

ARG LITEPARSE_SERVER_COMMIT=70cee35fb429f531d657d3328dc9939c89c0312b

# ---------- Base ----------
FROM node:24-slim AS base
WORKDIR /workspace
ENV PNPM_HOME=/pnpm
ENV PATH="$PNPM_HOME:$PATH"
RUN corepack enable && corepack prepare pnpm@11.9.0 --activate

# ---------- Source: upstream at the pinned commit, with our manifest and lockfile ----------
FROM base AS source
ARG LITEPARSE_SERVER_COMMIT
ADD --keep-git-dir=false https://github.com/run-llama/liteparse-server.git#${LITEPARSE_SERVER_COMMIT} /workspace
COPY package.json pnpm-lock.yaml /workspace/

# ---------- Deps ----------
FROM base AS deps
COPY --from=source /workspace/pnpm-lock.yaml /workspace/pnpm-workspace.yaml /workspace/package.json ./
COPY --from=source /workspace/packages/liteparse-grpc/package.json ./packages/liteparse-grpc/
RUN --mount=type=cache,id=pnpm-store,target=/pnpm/store \
    pnpm install --frozen-lockfile

# ---------- Build ----------
FROM deps AS build
COPY --from=source /workspace/src ./src
COPY --from=source /workspace/buildscripts ./buildscripts
RUN pnpm run build:slim && chmod +x dist/slim.js
RUN --mount=type=cache,id=pnpm-store,target=/pnpm/store \
    pnpm deploy --filter @llamaindex/liteparse-rest --prod --legacy /out

# ---------- Runtime ----------
FROM node:24-slim AS runtime
WORKDIR /app
# As upstream: libreoffice for office documents, imagemagick kept although LiteParse 2.8+ no
# longer needs it for images (removing it waits until the comparison shows it is safe).
RUN apt-get update && apt-get install -y --no-install-recommends \
      libvips42 \
      ca-certificates \
      libreoffice \
      imagemagick \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/*
ENV NODE_ENV=production
COPY --from=build /out/node_modules ./node_modules
COPY --from=build /out/package.json ./package.json
COPY --from=build /workspace/dist ./dist
EXPOSE 5707
USER node
CMD ["node", "dist/slim.js"]
