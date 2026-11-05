FROM python@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337
# Dependency preparation only. No manuscript is in this build context.
RUN rm -f /etc/apt/sources.list.d/debian.sources && \
    printf '%s\n' \
      'deb [check-valid-until=no] https://snapshot.debian.org/archive/debian/20261030T000000Z/ bookworm main' \
      'deb [check-valid-until=no] https://snapshot.debian.org/archive/debian-security/20261030T000000Z/ bookworm-security main' > /etc/apt/sources.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends texlive-latex-base=2022.20230122-3 lmodern && \
    dpkg-query -W -f='${Package}\t${Version}\n' > /opt/packages.tsv && \
    pdflatex --version > /opt/compiler-version.txt && \
    rm -rf /var/lib/apt/lists/*
COPY worker.py /opt/worker.py
ENTRYPOINT ["python", "-B", "/opt/worker.py"]
