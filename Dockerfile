# G1 ACQ sidecar — optional container image.
#
#   docker build -t g1-acq .
#   docker run -d --name g1-acq -p 8080:8080 -v g1-data:/data g1-acq \
#     serve --bind 0.0.0.0 --port 8080 --auth g1:change-me \
#     --state /data/.g1-acq/state.json
#
# HOME is pinned to the volume so mitmproxy keeps the same CA across restarts.
# Regenerating that CA would invalidate the certificate the phone already trusts.
FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir "mitmproxy>=12,<13"

COPY g1_addon.py ./
COPY g1acq ./g1acq

# Run unprivileged: the CA private key lives in this volume.
RUN useradd --create-home --uid 1000 g1 \
    && mkdir -p /data \
    && chown -R g1:g1 /data /app

ENV HOME=/data \
    PYTHONUNBUFFERED=1

USER g1

VOLUME ["/data"]
EXPOSE 8080

# Override the subcommand for one-off commands, e.g.
#   docker run --rm -v g1-data:/data g1-acq report --state /data/.g1-acq/state.json
ENTRYPOINT ["python", "-m", "g1acq"]
CMD ["serve", "--bind", "0.0.0.0", "--port", "8080", "--state", "/data/.g1-acq/state.json"]
