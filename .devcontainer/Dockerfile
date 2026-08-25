FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

# ⚙️ PROJECT — 立即替换为澳大利亚镜像源（在安装任何东西之前）。换个地方用就把
# mirror.aarnet.edu.au 改成就近的镜像；不需要镜像的话整段连同下面的 grep 断言删掉。
#
# 三个上游都要替换。24.04 的 deb822 文件里有两段 URIs（主源 + noble-security）：
# arm64 上两段都是 ports.ubuntu.com，一条规则就够；x86_64 上主源是
# archive.ubuntu.com 而 security 是独立的 security.ubuntu.com —— 漏掉它的话，
# 安全更新仍然走默认源，而且不报错，只是慢得莫名其妙。
#
# 结尾不要用 `; true`：那会把"一个文件都没替换成功"也一起吞掉。下面用一条
# 独立的 grep 做断言，替换没生效就让构建直接失败。
RUN for f in /etc/apt/sources.list.d/ubuntu.sources /etc/apt/sources.list; do \
        [ -f "$f" ] && sed -i \
            -e 's|http://ports.ubuntu.com|http://mirror.aarnet.edu.au|g' \
            -e 's|http://archive.ubuntu.com|http://mirror.aarnet.edu.au|g' \
            -e 's|http://security.ubuntu.com|http://mirror.aarnet.edu.au|g' \
            "$f"; \
    done
RUN grep -q 'mirror.aarnet.edu.au' /etc/apt/sources.list.d/ubuntu.sources

# 更新包列表
RUN apt-get update

# 系统级依赖放这里，不放 post-create.sh：它们不随工作区内容变化，进了镜像层就能被
# 缓存，容器重建时不必再等一次 apt-get update —— 那是 post-create 里最慢的一步。
#
# bubblewrap —— Codex CLI 在 Linux 上做沙箱用的。
# libonig-dev —— 看不出来但确实必需，别当垃圾删掉：requirements.txt 里的
#   ansible-dev-tools 会拉进 ansible-navigator，后者依赖 onigurumacffi；arm64 上
#   没有预编译 wheel，pip 必须现场编译它的 cffi 扩展，要 oniguruma 的头文件。
#   删掉之后失败发生在 pip 的编译期，报错离根因很远。
RUN apt-get install -y --no-install-recommends \
        bubblewrap \
        libonig-dev
# ⚙️ PROJECT — libonig-dev 只是本项目的 ansible 依赖链需要；bubblewrap 是 Codex
#    的沙箱依赖，用 Codex 就留着。