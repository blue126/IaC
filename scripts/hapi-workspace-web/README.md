# HAPI自动登录前端构建

本目录保存HAPI v0.33.2锁定源码的最小补丁及新增前端模块，不修改现有VM502官方二进制。新工作VM代理提供定制静态页面，Hub／Runner仍使用固定官方可执行文件。

`upstream.json`绑定原始源码archive、commit和六个待修改文件的SHA256。构建器先验证输入，再把补丁应用到Sandbox内新建临时源码目录，复制overlay；不修改下载原包或用户checkout，不运行发布脚本。

## 受管构建

仅在已批准依赖安装的任务Sandbox中执行。提供已下载且通过manifest校验的源码archive和Bun 1.4.4；本轮使用Linux arm64发行包，其官方release digest为`baa6bb36f51d6e58561e02bbea825038a9df454f673d6d776e8bbf86f8c7850e`。其他平台需核对对应官方发行资产，不能沿用该digest。

```bash
python3 scripts/build-hapi-workspace-web.py \
  --archive /tmp/hapi-upstream-workspace-auth.tar.gz \
  --bun /tmp/hapi-web-tools/bun-linux-aarch64/bun \
  --output /tmp/hapi-workspace-web-artifact-20261030
```

源码archive来自固定commit `730dfcb22e31ec5572446d066cbb5e92d6a6254d` 的GitHub API tarball；完整预期校验和在`upstream.json`。输出目录必须尚不存在，避免覆盖既有产物。失败保留构建目录和日志，不删除未知缓存或重写锁文件。

Bun使用`--frozen-lockfile --ignore-scripts`安装原有依赖，随后运行21项相关前端测试、完整`tsc --noEmit`和`vite build`。锁文件中的npm mirror及CDN需要在任务Sandbox下载allowlist中；不能因403移除完整性验证、变更依赖版本或关闭代理。构建flag为`VITE_HAPI_WORKSPACE_AUTH=1`，禁止注册离线service worker，以免复用不同身份的缓存。

输出`hapi-workspace-web.tar.gz`及`manifest.json`，包含源码commit、补丁／overlay摘要及artifact校验和；Web包内的`workspace-build.json`不含秘密。工作VM角色要求controller本地archive路径、精确SHA256，并在远端解包前再次校验，不接受缺产物时回退token登录。

## 浏览器回归

已装Chromium验证依赖后，用当前构建目录的真实dist和原锁定Playwright依赖运行：

```bash
node tests/hapi-workspace/workspace-browser.mjs \
  /tmp/BUILD_DIRECTORY/tiann-hapi-730dfcb/web/dist \
  /tmp/BUILD_DIRECTORY/tiann-hapi-730dfcb \
  /tmp/hapi-workspace-web-browser-20261030
```

回归只启动loopback模拟网关，阻止浏览器访问外部origin；不使用真实Cloudflare／HAPI／Claude账号。它打开生产构建页面，检查自动会话、账号切换、Access失效后的恢复、Cookie保留和无token输入；不能代替线上Access或个人Claude授权验收。

协议和部署输入见[原型说明](../../docs/guides/hapi-control-plane-prototype.md)。
