FROM ubuntu:24.04
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ca-certificates curl git python3 libicu74 libssl3t64 libkrb5-3 zlib1g liblttng-ust1t64 && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1001 runner
WORKDIR /home/runner
RUN curl -fL --retry 2 https://github.com/actions/runner/releases/download/v2.338.2/actions-runner-linux-x64-2.338.2.tar.gz -o runner.tgz && echo 'baebf204307bac6193480852732f0aba2ae97b6c5597c244f4d5558390147c40  runner.tgz' | sha256sum -c - && tar xzf runner.tgz && rm runner.tgz && chown -R runner:runner /home/runner
USER runner
ENV PYTHONDONTWRITEBYTECODE=1
ENTRYPOINT ["/bin/bash"]
