// Probe the pinned upstream authentication handlers with synthetic credentials.
import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'
import { randomBytes, createHash } from 'node:crypto'

assert(process.argv[2], 'Supply the already verified upstream source directory')
const source = resolve(process.argv[2])
const expectedFiles = {
    'hub/src/utils/accessToken.ts': '47804c6fb281c4e5e3dc5a65bb1b45f51ca07e48248999c03fd1abda04ce9dec',
    'hub/src/web/routes/auth.ts': '172a7760db89fef4b064fe43a87a23454585c5a2c03f4be88a6ecebc826cb856',
    'hub/src/socket/server.ts': '0637276839e52300311c9c7f35dc91ad37a7780d75602aa93b68f0c0a9958fe0',
    'docs/guide/namespace.md': '74d751543584358ca9e0560f5c00ed28dfcd42b951c9541f68326dc016b84fe5'
}
for (const [path, expected] of Object.entries(expectedFiles)) {
    assert.equal(createHash('sha256').update(readFileSync(join(source, path))).digest('hex'), expected,
        'The probe requires the verified, unmodified pinned upstream auth source: ' + path)
}
const scratch = mkdtempSync(join(tmpdir(), 'hapi-shared-hub-auth-'))
const base = randomBytes(32).toString('hex')
process.env.HAPI_HOME = scratch
process.env.CLI_API_TOKEN = base
process.env.TELEGRAM_BOT_TOKEN = ''
process.env.TELEGRAM_NOTIFICATION = 'false'
process.env.SERVERCHAN_NOTIFICATION = 'false'
process.env.HAPI_IOS_PUSH = 'off'
process.env.HAPI_ANDROID_PUSH = 'off'
const load = path => import(pathToFileURL(join(source, path)).href)
const hubRequire = createRequire(join(source, 'hub/package.json'))
const cliRequire = createRequire(join(source, 'cli/package.json'))
const { jwtVerify } = await import(pathToFileURL(hubRequire.resolve('jose')).href)
const { io: clientIo } = await import(pathToFileURL(cliRequire.resolve('socket.io-client')).href)
const { createConfiguration } = await load('hub/src/configuration.ts')
const { Store } = await load('hub/src/store/index.ts')
const { createAuthRoutes } = await load('hub/src/web/routes/auth.ts')
const { createSocketServer } = await load('hub/src/socket/server.ts')
await createConfiguration()
const store = new Store(':memory:')
const key = randomBytes(32)
const app = createAuthRoutes(key, store)
const { io, engine } = createSocketServer({ store, jwtSecret: key, corsOrigins: ['http://localhost'] })
const handler = engine.handler()
const server = Bun.serve({ ...handler, hostname: '127.0.0.1', port: 0,
    fetch(request, server) {
        if (new URL(request.url).pathname.startsWith('/socket.io/')) return engine.handleRequest(request, server)
        return app.fetch(request)
    }
})
const results = []
const clients = []
try {
    for (const [name, token, expectedStatus, expectedNamespace] of [
        ['alice-original', base + ':alice', 200, 'alice'],
        ['alice-credential-with-bob-suffix', base + ':bob', 200, 'bob'],
        ['alice-credential-without-suffix', base, 200, 'default'],
        ['wrong-base-rejected', 'not-the-shared-base:bob', 401, null]
    ]) {
        const response = await fetch(`http://127.0.0.1:${server.port}/auth`, {
            method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ accessToken: token })
        })
        assert.equal(response.status, expectedStatus, name)
        let ns = null
        if (response.status === 200) {
            const json = await response.json()
            ns = (await jwtVerify(json.token, key, { algorithms: ['HS256'] })).payload.ns
            assert.equal(ns, expectedNamespace, name)
        }
        results.push({ channel: 'actual-http-auth', case: name, status: response.status, namespace: ns })
    }
    for (const [name, token, expectedNamespace] of [
        ['runner-alice', base + ':alice', 'alice'],
        ['runner-alice-credential-with-bob-suffix', base + ':bob', 'bob'],
        ['runner-wrong-base-rejected', 'not-the-shared-base:bob', null]
    ]) {
        const client = clientIo(`http://127.0.0.1:${server.port}/cli`, {
            auth: { token }, transports: ['websocket'], reconnection: false, forceNew: true, timeout: 3000
        })
        clients.push(client)
        let error = null
        try {
            await new Promise((resolve, reject) => {
                client.once('connect', resolve)
                client.once('connect_error', reject)
                setTimeout(() => reject(new Error('Socket connection timed out')), 4000).unref()
            })
        } catch (caught) { error = caught }
        if (expectedNamespace === null) {
            assert.equal(error?.message, 'Invalid token', name)
            results.push({ channel: 'actual-runner-socket-auth', case: name, rejected: true })
            client.disconnect()
            continue
        }
        assert.equal(error, null, name)
        const ns = io.of('/cli').sockets.get(client.id)?.data.namespace
        assert.equal(ns, expectedNamespace, name)
        results.push({ channel: 'actual-runner-socket-auth', case: name, namespace: ns })
        client.disconnect()
    }
    console.log(JSON.stringify({
        pinned_source_commit: '730dfcb22e31ec5572446d066cbb5e92d6a6254d',
        source_file_sha256: expectedFiles,
        upstream_native_shared_token_allows_namespace_selection: true,
        separate_tenant_credentials_verified: false,
        production_changed: false,
        results
    }, null, 2))
} finally {
    for (const client of clients) client.disconnect()
    await io.close()
    server.stop(true)
    store.close()
}
