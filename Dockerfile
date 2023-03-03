FROM python:3.11-slim-bullseye

LABEL maintainer="gallegoj@uw.edu"

WORKDIR /opt

COPY . archon

RUN pip3 install -U pip setuptools wheel
RUN cd archon && pip3 install .

# Connect repo to package
LABEL org.opencontainers.image.source https://github.com/sdss/archon

ENTRYPOINT archon actor start --debug
