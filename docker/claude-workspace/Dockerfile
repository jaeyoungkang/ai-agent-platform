# AI Agent Platform - Claude Code CLI Workspace Container
# This container provides isolated environments for users to interact with Claude Code CLI
FROM node:18-bullseye

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    git \
    curl \
    bash \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI (official installation method)
RUN npm install -g @anthropic-ai/claude-code

# Create symbolic link for python command
RUN ln -s /usr/bin/python3 /usr/bin/python

# Install common Python packages for AI agents
RUN pip3 install --no-cache-dir \
    pandas \
    numpy \
    requests \
    beautifulsoup4 \
    matplotlib \
    seaborn \
    jupyter \
    scikit-learn \
    plotly \
    openpyxl \
    python-dotenv

# Create user for security (non-root execution)
RUN useradd -m -s /bin/bash claude
RUN mkdir -p /workspace && chown claude:claude /workspace

# Set working directory
WORKDIR /workspace

# Switch to non-root user
USER claude

# Keep container running in background
CMD ["tail", "-f", "/dev/null"]