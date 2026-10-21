# Execution image for generated analysis code. Built once; runs with --network none.
FROM python@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-compile -r /tmp/requirements.txt \
    && pip uninstall -y pip setuptools wheel \
    && rm -rf /tmp/requirements.txt /root/.cache \
    && groupadd --gid 10001 sandbox \
    && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /tmp --shell /usr/sbin/nologin sandbox
USER 10001:10001
WORKDIR /tmp
