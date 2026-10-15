# syntax=docker/dockerfile:1
#
# The SARDASPORTS website, as a self-contained Next.js server.
#
# Built with `--experimental-build-mode compile`: the pages are compiled but NOT
# pre-rendered. Many pages read the engine (the home page, the leagues, the track
# record), and a Docker build has no engine to read from, so a normal build would bake
# "engine unreachable" pages into the image and serve them until each one's revalidate
# window passed. Rendered on first request instead, they always carry real data, and
# Next's data cache (the engine fetches' `revalidate`) keeps them quick after that.

FROM node:22-bookworm-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:22-bookworm-slim AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
# These three are baked into the browser bundle at build time, so they are build
# arguments. NEXT_PUBLIC_SITE_URL is also what switches indexing on: left empty, the
# site stays noindex and robots.txt disallows everything (a deliberate safeguard).
ARG NEXT_PUBLIC_SITE_URL=""
ARG NEXT_PUBLIC_OPERATOR_NAME=""
ARG NEXT_PUBLIC_CONTACT_EMAIL=""
ENV NEXT_PUBLIC_SITE_URL=$NEXT_PUBLIC_SITE_URL \
    NEXT_PUBLIC_OPERATOR_NAME=$NEXT_PUBLIC_OPERATOR_NAME \
    NEXT_PUBLIC_CONTACT_EMAIL=$NEXT_PUBLIC_CONTACT_EMAIL
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# The admin's rich-text editor is served from this site (public/ckeditor), copied out of
# node_modules. `next build` is called directly below, so npm's prebuild hook does not run.
RUN node scripts/copy-ckeditor.mjs
RUN npx next build --experimental-build-mode compile

FROM node:22-bookworm-slim AS run
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
COPY --from=build --chown=node:node /app/public ./public
USER node
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:3000/robots.txt >/dev/null || exit 1
CMD ["node", "server.js"]
