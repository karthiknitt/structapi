# Sandbox image for StructAgent: eve base + scientific Python baked in.
# Egress is deny-all at runtime, so ALL Python deps must be installed here.
# Build (Phase 7, after Docker Desktop install):
#   docker build -t structagent-sandbox:latest sandbox-image/
FROM ghcr.io/vercel/eve:latest

# The base image runs as non-root (vercel-sandbox) with a non-writable
# site-packages, so a user-mode pip install fails on later versions of this
# image (permission errors under ~/.local). Install system-wide as root,
# then drop back to the image's own runtime user.
USER root
RUN pip3 install --no-cache-dir --break-system-packages numpy matplotlib reportlab
USER vercel-sandbox

ENV MPLBACKEND=Agg
