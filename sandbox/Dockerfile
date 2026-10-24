# Throw-away Linux box for running generated commands.
# The root file system is mounted read-only at run time; every run gets a fresh
# copy of /fixtures in a tmpfs at /home/sandbox/work.
FROM debian:bookworm-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends procps iproute2 net-tools psmisc lsof file \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 1000 sandbox

# Sample files, so commands like "count the lines in report.txt" have something to work on
RUN mkdir -p /fixtures/downloads /fixtures/logs /fixtures/src/pkg \
 && printf 'line one\nline two\nline three\n' > /fixtures/report.txt \
 && printf 'notes\n' > /fixtures/notes.txt \
 && printf 'todo\n' > /fixtures/todo.txt \
 && printf '.hidden\n' > /fixtures/.hidden \
 && printf '#!/bin/sh\necho hi\n' > /fixtures/script.sh \
 && head -c 500000 /dev/urandom > /fixtures/big.bin \
 && head -c 50000 /dev/urandom > /fixtures/medium.bin \
 && printf 'INFO start\nERROR disk full\nINFO done\nERROR timeout\n' > /fixtures/logs/app.log \
 && cp /fixtures/logs/app.log /fixtures/app.log \
 && printf 'old\n' > /fixtures/old.log \
 && printf 'tmp\n' > /fixtures/downloads/a.tmp \
 && printf 'tmp\n' > /fixtures/downloads/b.tmp \
 && printf 'raise Error("x")\n' > /fixtures/src/main.py \
 && printf 'print("error handling")\n' > /fixtures/src/pkg/util.py \
 && chown -R sandbox:sandbox /fixtures

USER sandbox
WORKDIR /home/sandbox
