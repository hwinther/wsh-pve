FROM debian:12-slim AS install
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y curl libicu72 sudo wget apt-utils
RUN curl -sSL https://dot.net/v1/dotnet-install.sh | sudo bash /dev/stdin --channel STS --install-dir /opt/dotnet
RUN curl -sSL https://dot.net/v1/dotnet-install.sh | sudo bash /dev/stdin --channel LTS --install-dir /opt/dotnet
ENV PATH="/opt/dotnet:${PATH}"
ENV DOTNET_CLI_TELEMETRY_OPTOUT=1
RUN dotnet --list-sdks
RUN curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
RUN . /etc/os-release \
    && wget -q https://packages.microsoft.com/config/debian/$VERSION_ID/packages-microsoft-prod.deb \
    && sudo dpkg -i packages-microsoft-prod.deb \
    && rm packages-microsoft-prod.deb
RUN apt-get update && apt-get install -y powershell
RUN apt-get clean
CMD ["bash"]
