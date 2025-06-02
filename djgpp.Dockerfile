# syntax=docker/dockerfile:1
FROM alpine:3.22 AS watcom
WORKDIR /watcom
RUN apk update && apk add wget xz
RUN wget https://github.com/open-watcom/open-watcom-v2/releases/download/2023-12-01-Build/ow-snapshot.tar.xz
RUN tar -xvf ow-snapshot.tar.xz ./binl64

# This build process is borrows heavily from revive9x:qemu-3dfx-wrappers
FROM debian:bookworm-slim AS build-base
RUN apt-get update && apt install git build-essential mingw-w64-tools unzip bison flex texinfo curl wget zlib1g-dev -y

FROM build-base AS djgpp
WORKDIR /djgpp
RUN git clone https://github.com/hwinther/build-djgpp
RUN cd build-djgpp && DJGPP_PREFIX=`pwd`/i686 bash build-djgpp.sh 12.1.0-i686

FROM build-base AS build-extended
RUN apt-get install mingw-w64 xxd -y

FROM build-extended AS wrapper-build
WORKDIR /build
# COPY . .
COPY --from=watcom /watcom/binl64 /opt/watcom11/binl64
COPY --from=djgpp /djgpp/build-djgpp/i686 /opt/djgpp-i686
ENV PATH="${PATH}:/opt/watcom11/binl64:/opt/djgpp-i686/bin:/opt/djgpp-i686/i686-pc-msdosdjgpp/bin"
# RUN git clone https://github.com/hwinther/qemu-3dfx
# RUN cd qemu-3dfx/wrappers/3dfx && mkdir build && cd build && bash ../../../scripts/conf_wrapper && make && make clean
# RUN cd qemu-3dfx/wrappers/mesa && mkdir build && cd build && bash ../../../scripts/conf_wrapper && make && make clean
CMD [ "bash" ]

# FROM alpine:latest AS final
# WORKDIR final
# COPY --from=wrapper-build /build/wrappers/3dfx/build/* .
# COPY --from=wrapper-build /build/wrappers/mesa/build/* .
# CMD [ "ash" ]
