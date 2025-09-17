FROM debian:13-slim AS install
LABEL maintainer="Hans Christian Winther-Sørensen <docker@wsh.no>"
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install --no-install-recommends --assume-yes nginx reprepro expect nano && apt-get clean
