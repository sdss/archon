FROM ubuntu:20.04

LABEL maintainer="gallegoj@uw.edu"

WORKDIR /opt

COPY . archon

RUN apt-get -y update
RUN apt-get -y install python3 python3-pip build-essential libbz2-dev

RUN pip3 install -U pip setuptools wheel
RUN cd archon && pip3 install .

# Connect repo to package
LABEL org.opencontainers.image.source https://github.com/sdss/archon

ENTRYPOINT archon actor start --debug
