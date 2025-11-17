ARG SUNSHINE_VERSION=latest
ARG SUNSHINE_OS=debian-trixie
#ARG SUNSHINE_OS=ubuntu-22.04
FROM lizardbyte/sunshine:${SUNSHINE_VERSION}-${SUNSHINE_OS} AS os

# install Steam, Wayland, etc.
# ENTRYPOINT steam && sunshine
FROM os AS install
USER root
RUN apt-get update && apt-get -y full-upgrade
#RUN apt-get -y install software-properties-common && apt-add-repository -y contrib non-free non-free-firmware && apt-get update
RUN sed -ri 's/main/main contrib non-free non-free-firmware/' /etc/apt/sources.list.d/debian.sources
# RUN apt-get update && apt-get install -y nvidia-smi
CMD ["bash"]

#FROM install AS run
#CMD ["sunshine"]
