# Test image: Linux + HA test harness. Build once, then run the suite by
# mounting the repository, e.g.
#   docker build -f docker/test.Dockerfile -t watering-project-tests .
#   docker run --rm -v "$PWD":/work -w /work watering-project-tests pytest -q
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work

COPY requirements_test_min.txt requirements_test_min.txt
RUN pip install --no-cache-dir -r requirements_test_min.txt ruff

CMD ["pytest", "-q"]
