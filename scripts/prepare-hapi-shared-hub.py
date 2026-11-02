#!/usr/bin/env python3
"""Prepare a pinned shared Hub with tenant-bound credentials, without installing dependencies."""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

REPO = Path(__file__).resolve().parents[1]
INPUTS = REPO / 'scripts/hapi-shared-hub'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(source, output):
    pin = json.loads((INPUTS / 'upstream.json').read_text())
    for name, checksum in pin['files'].items():
        if sha(source / name) != checksum:
            raise ValueError('Pinned source mismatch: ' + name)
    if output.exists():
        raise ValueError('Refuse to overwrite a prepared source tree')
    shutil.copytree(source, output, symlinks=True,
                    ignore=shutil.ignore_patterns('node_modules', '.git', 'dist', 'dist-exe'))
    # The frontend's provenance JSON is retained in the build manifest, not
    # embedded as a module (TypeScript treats JSON imports as objects).
    web_metadata = None
    if (source / 'web/dist').is_dir():
        shutil.copytree(source / 'web/dist', output / 'web/dist', symlinks=True,
                        ignore=shutil.ignore_patterns('workspace-build.json'))
        metadata = source / 'web/dist/workspace-build.json'
        if metadata.is_file():
            web_metadata = json.loads(metadata.read_text())
    package = json.loads((source / 'package.json').read_text())
    folders = [source]
    for pattern in package['workspaces']:
        folders.extend(path for path in source.glob(pattern) if path.is_dir())
    for folder in folders:
        original = folder / 'node_modules'
        if not original.is_dir():
            continue
        target = output / folder.relative_to(source) / 'node_modules'
        target.mkdir()
        def link(old, new):
            resolved = old.resolve()
            try:
                relative = resolved.relative_to(source)
            except ValueError:
                relative = None
            destination = output / relative if relative is not None and 'node_modules' not in relative.parts else resolved
            new.symlink_to(destination, target_is_directory=resolved.is_dir())
        for child in original.iterdir():
            if child.name.startswith('@') and child.is_dir():
                scope = target / child.name; scope.mkdir()
                for item in child.iterdir():
                    link(item, scope / item.name)
            else:
                link(child, target / child.name)
    before = {name: (output / name).read_text() for name in pin['files']}

    def change(name, old, new):
        path = output / name
        text = path.read_text()
        if text.count(old) != 1:
            raise ValueError('Patch context mismatch: ' + name + ': ' + old[:70])
        path.write_text(text.replace(old, new))

    for path in (INPUTS / 'overlay').rglob('*'):
        if path.is_file():
            destination = output / path.relative_to(INPUTS / 'overlay')
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)

    auth = 'hub/src/web/routes/auth.ts'
    change(auth, "import { constantTimeEquals } from '../../utils/crypto'\nimport { parseAccessToken } from '../../utils/accessToken'",
           "import { resolveTenantCredential, tenantAuthEnabled, tenantClaims, type TenantAuthorization } from '../../utils/tenantAuth'")
    change(auth, 'let namespace: string', 'let namespace: string\n        let authorization: TenantAuthorization | undefined')
    change(auth, '''            const configuration = getConfiguration()
            const parsedToken = parseAccessToken(parsed.data.accessToken)
            if (!parsedToken || !constantTimeEquals(parsedToken.baseToken, configuration.cliApiToken)) {''',
           '''            const parsedToken = resolveTenantCredential(parsed.data.accessToken,
                c.req.header('X-Hapi-Expected-Namespace'), c.req.header('X-Hapi-Expected-Credential'))
            if (!parsedToken) {''')
    change(auth, 'namespace = parsedToken.namespace', 'namespace = parsedToken.namespace\n            authorization = parsedToken')
    change(auth, '''        } else {
            const configuration = getConfiguration()''', '''        } else {
            if (tenantAuthEnabled()) return c.json({ error: 'Tenant credentials required' }, 403)
            const configuration = getConfiguration()''')
    change(auth, 'new SignJWT({ uid: userId, ns: namespace })', 'new SignJWT({ uid: userId, ns: namespace, ...tenantClaims(authorization) })')

    cli = 'hub/src/web/routes/cli.ts'
    change(cli, "import { constantTimeEquals } from '../../utils/crypto'\nimport { parseAccessToken } from '../../utils/accessToken'",
           "import { resolveTenantCredential } from '../../utils/tenantAuth'")
    change(cli, '''        const configuration = getConfiguration()
        const parsedToken = parseAccessToken(token)
        if (!parsedToken || !constantTimeEquals(parsedToken.baseToken, configuration.cliApiToken)) {''',
           '''        const parsedToken = resolveTenantCredential(token,
            c.req.header('X-Hapi-Expected-Namespace'), c.req.header('X-Hapi-Expected-Credential'))
        if (!parsedToken) {''')

    bind = 'hub/src/web/routes/bind.ts'
    change(bind, "import { Hono } from 'hono'", "import { Hono } from 'hono'\nimport { tenantAuthEnabled } from '../../utils/tenantAuth'")
    change(bind, "    app.post('/bind', async (c) => {", "    app.post('/bind', async (c) => {\n        if (tenantAuthEnabled()) return c.json({ error: 'Tenant binding is managed by the control plane' }, 403)")

    middleware = 'hub/src/web/middleware/auth.ts'
    change(middleware, "import { jwtVerify } from 'jose'", "import { jwtVerify } from 'jose'\nimport { tenantJwtAuthorization, type TenantAuthorization } from '../../utils/tenantAuth'")
    change(middleware, '        namespace: string', '        namespace: string\n        tenantAuthorization?: TenantAuthorization')
    change(middleware, "            c.set('userId', parsed.data.uid)", '''            const authorization = tenantJwtAuthorization(verified.payload,
                c.req.header('X-Hapi-Expected-Namespace'), c.req.header('X-Hapi-Expected-Credential'))
            if (!authorization) {
                return c.json({ error: 'Tenant authorization failed' }, 403)
            }
            c.set('tenantAuthorization', authorization)
            c.set('userId', parsed.data.uid)''')

    socket = 'hub/src/socket/server.ts'
    change(socket, "import { constantTimeEquals } from '../utils/crypto'\nimport { parseAccessToken } from '../utils/accessToken'",
           "import { resolveTenantCredential, tenantJwtAuthorization, tenantAuthorizationCurrent, tenantAuthEnabled } from '../utils/tenantAuth'")
    change(socket, '''        const parsedToken = token ? parseAccessToken(token) : null
        if (!parsedToken || !constantTimeEquals(parsedToken.baseToken, configuration.cliApiToken)) {''',
           '''        const parsedToken = resolveTenantCredential(token,
            socket.handshake.headers['x-hapi-expected-namespace'], socket.handshake.headers['x-hapi-expected-credential'])
        if (!parsedToken) {''')
    change(socket, '        socket.data.namespace = parsedToken.namespace', '        socket.data.namespace = parsedToken.namespace\n        socket.data.tenantAuthorization = parsedToken')
    change(socket, "    cliNs.use((socket, next) => {", '''    io.use((_socket, next) => tenantAuthEnabled() ? next(new Error('Unsupported namespace')) : next())
    const watchAuthorization = (socket: import('./socketTypes').SocketWithData) => {
        const authorization = socket.data.tenantAuthorization
        if (!authorization?.credentialId) return
        socket.use((_packet, next) => {
            if (!tenantAuthorizationCurrent(authorization)) {
                socket.disconnect(true)
                return next(new Error('Tenant authorization revoked'))
            }
            next()
        })
        const timer = setInterval(() => {
            if (!tenantAuthorizationCurrent(authorization)) socket.disconnect(true)
        }, 500)
        timer.unref()
        socket.once('disconnect', () => clearInterval(timer))
    }
    cliNs.on('connection', watchAuthorization)
    terminalNs.on('connection', watchAuthorization)
    cliNs.use((socket, next) => {''')
    change(socket, '            socket.data.userId = parsed.data.uid', '''            const authorization = tenantJwtAuthorization(verified.payload,
                socket.handshake.headers['x-hapi-expected-namespace'], socket.handshake.headers['x-hapi-expected-credential'])
            if (!authorization) return next(new Error('Tenant authorization failed'))
            socket.data.tenantAuthorization = authorization
            socket.data.userId = parsed.data.uid''')
    types = 'hub/src/socket/socketTypes.ts'
    change(types, 'export type SocketData = {', "import type { TenantAuthorization } from '../utils/tenantAuth'\n\nexport type SocketData = {\n    tenantAuthorization?: TenantAuthorization")

    rpc = 'hub/src/sync/rpcGateway.ts'
    change(rpc, "import type { RpcRegistry } from '../socket/rpcRegistry'", "import type { RpcRegistry } from '../socket/rpcRegistry'\nimport { tenantAuthEnabled } from '../utils/tenantAuth'")
    change(rpc, 'private readonly rpcRegistry: RpcRegistry\n', "private readonly rpcRegistry: RpcRegistry,\n        private readonly namespaceForTarget?: (id: string, kind: 'session' | 'machine') => string | undefined\n")
    change(rpc, 'this.rpcCall(`${sessionId}:${method}`, params, timeoutMs)', "this.rpcCall(`${sessionId}:${method}`, params, timeoutMs, this.namespaceForTarget?.(sessionId, 'session'))")
    change(rpc, 'this.rpcCall(`${machineId}:${method}`, params, timeoutMs)', "this.rpcCall(`${machineId}:${method}`, params, timeoutMs, this.namespaceForTarget?.(machineId, 'machine'))")
    change(rpc, 'private async rpcCall(method: string, params: unknown, timeoutMs: number = DEFAULT_RPC_TIMEOUT_MS): Promise<unknown> {\n        const socketId = this.rpcRegistry.getSocketIdForMethod(method)',
           '''private async rpcCall(method: string, params: unknown, timeoutMs: number = DEFAULT_RPC_TIMEOUT_MS, namespace?: string): Promise<unknown> {
        if (!namespace && tenantAuthEnabled()) throw new RpcTargetMissingError(method, 'handler-not-registered')
        const socketId = this.rpcRegistry.getSocketIdForMethod(method, namespace ?? 'default')''')
    sync = 'hub/src/sync/syncEngine.ts'
    change(sync, 'new RpcGateway(io, rpcRegistry)', "new RpcGateway(io, rpcRegistry, (id, kind) => kind === 'session' ? store.sessions.getSession(id)?.namespace : store.machines.getMachine(id)?.namespace)")

    events = 'hub/src/web/routes/events.ts'
    change(events, "import { Hono", "import { tenantAuthorizationCurrent } from '../../utils/tenantAuth'\nimport { Hono")
    change(events, '''            try {
                // Verdict first''', '''            const authorization = c.get('tenantAuthorization')
            const timer = authorization?.credentialId ? setInterval(() => {
                if (!tenantAuthorizationCurrent(authorization)) stream.abort()
            }, 500) : null
            timer?.unref()
            try {
                // Verdict first''')
    change(events, '''            } finally {
                manager.unsubscribe(subscriptionId)''', '''            } finally {
                if (timer) clearInterval(timer)
                manager.unsubscribe(subscriptionId)''')

    server = 'hub/src/web/server.ts'
    change(server, "import { Hono } from 'hono'", "import { Hono } from 'hono'\nimport { tenantRequestAllowed, tenantAuthEnabled } from '../utils/tenantAuth'")
    change(server, "    app.use('*', logger())", '''    app.use('*', async (c, next) => {
        if (!tenantRequestAllowed(c.req.method, c.req.path)) return c.json({ error: 'Endpoint disabled in tenant mode' }, 403)
        if (tenantAuthEnabled()) return next()
        return logger()(c, next)
    })''')
    change(server, '''            const url = new URL(req.url)
            if (url.pathname.startsWith('/socket.io/'))''', '''            const url = new URL(req.url)
            if (!tenantRequestAllowed(req.method, url.pathname)) return new Response('Endpoint disabled in tenant mode', { status: 403 })
            if (url.pathname.startsWith('/socket.io/'))''')
    start = 'hub/src/startHub.ts'
    change(start, "import { createConfiguration, type ConfigSource } from './configuration'", "import { createConfiguration, type ConfigSource } from './configuration'\nimport { assertTenantConfiguration } from './utils/tenantAuth'")
    change(start, '    const config = await createConfiguration()', '    const config = await createConfiguration()\n    assertTenantConfiguration()')

    patch = ''.join(''.join(difflib.unified_diff(before[name].splitlines(True), (output / name).read_text().splitlines(True),
                                               fromfile='a/' + name, tofile='b/' + name)) for name in pin['files'])
    (output.parent / 'tenant-auth.patch').write_text(patch)
    manifest = {'upstream': pin['commit'], 'source_sha256': pin['files'],
                'patch_sha256': hashlib.sha256(patch.encode()).hexdigest(),
                'overlay_sha256': {str(p.relative_to(INPUTS / 'overlay')): sha(p) for p in (INPUTS / 'overlay').rglob('*') if p.is_file()}}
    manifest['frontend_provenance'] = web_metadata
    prepared = set(pin['files']) | {str(p.relative_to(INPUTS / 'overlay')) for p in (INPUTS / 'overlay').rglob('*') if p.is_file()}
    manifest['prepared_file_sha256'] = {name: sha(output / name) for name in sorted(prepared)}
    (output.parent / 'source-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    manifest = prepare(args.source.resolve(), args.output.resolve())
    print(json.dumps({'prepared_source': str(args.output), 'patch_sha256': manifest['patch_sha256']}))


if __name__ == '__main__':
    main()
