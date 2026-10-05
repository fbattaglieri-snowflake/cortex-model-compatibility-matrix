# Test harness only. Pin a reviewed base digest before a controlled release.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/probe
COPY model_probe /opt/probe/model_probe
COPY scripts/qualify.py /opt/probe/qualify.py
USER 1000:1000
ENTRYPOINT ["python", "-m", "model_probe.cli"]