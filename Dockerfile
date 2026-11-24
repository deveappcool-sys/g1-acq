# G1 ACQ sidecar — optional container image.
#
#   docker build -t g1-acq .
#   docker run -d --name g1-acq -p 8080:8080 -v g1-data:/data g1-acq
#
# HOME is pinned to the volume so mitmproxy keeps the same CA across restarts.
# Regenerating that CA would invalidate the certificate the phone already trusts.
FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir "mitmproxy>=12,<13"

COPY g1_addon.py ./
COPY g1acq ./g1acq
COPY clash ./clash
COPY README.md ./

ENV HOME=/data \
    PYTHONUNBUFFERED=1

RUN mkdir -p /data

VOLUME ["/data"]
EXPOSE 8080

ENTRYPOINT ["python", "-m", "g1acq", "serve", "--bind", "0.0.0.0"]
CMD ["--port", "8080", "--state", "/data/.g1-acq/state.json"]
