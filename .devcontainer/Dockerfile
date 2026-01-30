FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

# 立即替换为澳大利亚镜像源（在安装任何东西之前）
RUN sed -i 's|http://ports.ubuntu.com|http://mirror.aarnet.edu.au|g' /etc/apt/sources.list.d/ubuntu.sources 2>/dev/null || \
    sed -i 's|http://ports.ubuntu.com|http://mirror.aarnet.edu.au|g' /etc/apt/sources.list 2>/dev/null || true

# 更新包列表
RUN apt-get update