FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

# 立即替换为澳大利亚镜像源（在安装任何东西之前）
#
# 两个上游都要替换：arm64 走 ports.ubuntu.com，x86_64 走 archive.ubuntu.com。
# 只替换其中一个的话，在另一种架构的机器上会静默失配 —— 不报错，只是回落到
# 默认源，慢得莫名其妙。
RUN for f in /etc/apt/sources.list.d/ubuntu.sources /etc/apt/sources.list; do \
        [ -f "$f" ] && sed -i \
            -e 's|http://ports.ubuntu.com|http://mirror.aarnet.edu.au|g' \
            -e 's|http://archive.ubuntu.com|http://mirror.aarnet.edu.au|g' \
            "$f"; \
    done; true

# 更新包列表
RUN apt-get update