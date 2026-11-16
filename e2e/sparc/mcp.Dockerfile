# The MCP server (mcp_server.py) on top of a lab image: a venv with its pinned, hash-checked
# dependencies (mcp-requirements.txt) in /opt/wsh-lab-mcp, and `wsh-lab-mcp` in PATH. Optional: the lab
# images themselves don't change. See README.md, "MCP server".
#
# Build context: e2e/sparc. BASE is the lab image (Dockerfile) or the PVE node with the lab (pve.Dockerfile):
#   docker build -f e2e/sparc/mcp.Dockerfile -t wsh-lab-mcp e2e/sparc                                  # lab
#   docker build -f e2e/sparc/mcp.Dockerfile --build-arg BASE=wsh-pve-lab -t wsh-pve-lab-mcp e2e/sparc  # PVE
ARG BASE=wsh-sparc-lab
FROM ${BASE}
RUN apt-get update \
    && apt-get install --no-install-recommends --assume-yes python3-venv \
    && rm -rf /var/lib/apt/lists/*
COPY mcp-requirements.txt /tmp/mcp-requirements.txt
RUN python3 -m venv /opt/wsh-lab-mcp \
    && /opt/wsh-lab-mcp/bin/pip install --no-cache-dir --disable-pip-version-check --require-hashes \
        -r /tmp/mcp-requirements.txt \
    && rm /tmp/mcp-requirements.txt \
    && printf '#!/bin/sh\nexec /opt/wsh-lab-mcp/bin/python /lab/mcp_server.py "$@"\n' > /usr/local/bin/wsh-lab-mcp \
    && chmod 755 /usr/local/bin/wsh-lab-mcp
