# Sandbox image for StructAgent: eve base + scientific Python baked in.
# Egress is deny-all at runtime, so ALL Python deps must be installed here.
# Build (Phase 7, after Docker Desktop install):
#   docker build -t structagent-sandbox:latest sandbox-image/
FROM ghcr.io/vercel/eve:latest

RUN pip3 install --no-cache-dir --break-system-packages numpy matplotlib \
    || pip3 install --no-cache-dir numpy matplotlib

ENV MPLBACKEND=Agg
