FROM python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337 AS installer
COPY micromamba /tmp/micromamba
COPY packages/ /archives/
RUN mkdir -p /tmp/mamba/pkgs && chmod 755 /tmp/micromamba && CONDA_PKGS_DIRS=/tmp/mamba/pkgs /tmp/micromamba create --no-rc --offline -y -r /tmp/mamba -p /opt/poppler /archives/*

FROM python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337
COPY --from=installer /opt/poppler /opt/poppler
COPY worker.py /opt/geek-work/worker.py
ENV HOME=/tmp LC_ALL=C FONTCONFIG_FILE=/opt/poppler/etc/fonts/fonts.conf
USER 1000:1000
WORKDIR /tmp
ENTRYPOINT ["python3", "-I", "/opt/geek-work/worker.py"]
