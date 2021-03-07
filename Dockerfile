FROM ubuntu:20.04

LABEL maintainer="gallegoj@uw.edu"

WORKDIR /opt

RUN apt-get -y update
RUN apt-get -y install python3 python3-pip

RUN pip3 install -U pip setuptools wheel
RUN pip3 install .

ENTRYPOINT archon actor --debug
