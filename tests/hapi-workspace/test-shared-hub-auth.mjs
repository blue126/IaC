// Exercise actual patched Hub HTTP, Socket.IO, SSE, store and RPC isolation.
import assert from 'node:assert/strict'
import { mkdtempSync, writeFileSync, renameSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { createRequire } from 'node:module'
import { randomBytes } from 'node:crypto'

assert(process.argv[2], 'Supply the prepared pinned Hub source')
const source = resolve(process.argv[2])
const scratch = mkdtempSync(join(tmpdir(), 'hapi-tenant-auth-test-'))
const file = join(scratch, 'credentials.json')
const secret = () => randomBytes(32).toString('hex')
const master = secret(), legacy = secret(), alice = secret(), bob = secret()
const portReservation = Bun.serve({ hostname: '127.0.0.1', port: 0, fetch: () => new Response('test port reservation') })
const testPort = portReservation.port
portReservation.stop(true)
let registry = { version: 1, credentials: [
    { id: 'legacy', token: legacy, namespace: 'default', generation: 1, enabled: true },
    { id: 'alice', token: alice, namespace: 'alice', generation: 1, enabled: true },
    { id: 'bob', token: bob, namespace: 'bob', generation: 1, enabled: true }
] }
function publish(value = registry) {
    writeFileSync(file + '.candidate', JSON.stringify(value), { mode: 0o600 })
    renameSync(file + '.candidate', file)
}
publish()
Object.assign(process.env, { HAPI_HOME: scratch, CLI_API_TOKEN: master, HAPI_TENANT_CREDENTIALS_FILE: file,
    HAPI_LISTEN_HOST: '127.0.0.1', HAPI_LISTEN_PORT: String(testPort),
    TELEGRAM_BOT_TOKEN: '', TELEGRAM_NOTIFICATION: 'false', SERVERCHAN_NOTIFICATION: 'false',
    HAPI_IOS_PUSH: 'off', HAPI_ANDROID_PUSH: 'off', OPENAI_API_KEY: '', ANTHROPIC_API_KEY: '', GEMINI_API_KEY: '' })
const load = name => import(pathToFileURL(join(source, name)).href)
const requireHub = createRequire(join(source, 'hub/package.json'))
const requireCli = createRequire(join(source, 'cli/package.json'))
const { jwtVerify, SignJWT } = await import(pathToFileURL(requireHub.resolve('jose')).href)
const { io: clientIo } = await import(pathToFileURL(requireCli.resolve('socket.io-client')).href)
const { RPC_METHODS } = await import(pathToFileURL(requireHub.resolve('@hapi/protocol/rpcMethods')).href)
const { createConfiguration } = await load('hub/src/configuration.ts')
const { Store } = await load('hub/src/store/index.ts')
const { createSocketServer } = await load('hub/src/socket/server.ts')
const { SyncEngine } = await load('hub/src/sync/syncEngine.ts')
const { SSEManager } = await load('hub/src/sse/sseManager.ts')
const { VisibilityTracker } = await load('hub/src/visibility/visibilityTracker.ts')
const { startWebServer } = await load('hub/src/web/server.ts')
const { assertTenantConfiguration } = await load('hub/src/utils/tenantAuth.ts')
await createConfiguration()
assertTenantConfiguration()
const store = new Store(':memory:')
const key = randomBytes(32)
const { io, engine, rpcRegistry } = createSocketServer({ store, jwtSecret: key, corsOrigins: ['http://localhost'] })
const visibility = new VisibilityTracker()
const sse = new SSEManager(1000, visibility)
const sync = new SyncEngine(store, io, rpcRegistry, sse)
const server = await startWebServer({ getSyncEngine: () => sync, getSseManager: () => sse,
    getVisibilityTracker: () => visibility, jwtSecret: key, store, vapidPublicKey: '', socketEngine: engine })
const base = `http://127.0.0.1:${server.port}`
const results = [], clients = [], readers = []
function pass(name) { results.push(name); console.log('PASS ' + name) }
async function request(path, namespace, token, method = 'GET', body) {
    const headers = { 'content-type': 'application/json' }
    if (namespace !== null) headers['X-Hapi-Expected-Namespace'] = namespace
    if (token) headers.Authorization = 'Bearer ' + token
    return fetch(base + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) })
}
async function auth(token, namespace, status = 200) {
    const response = await request('/api/auth', namespace, null, 'POST', { accessToken: token })
    assert.equal(response.status, status)
    if (status !== 200) return null
    const body = await response.json()
    const verified = await jwtVerify(body.token, key, { algorithms: ['HS256'] })
    assert.equal(verified.payload.ns, namespace)
    assert(verified.payload.cid && verified.payload.cver)
    return body.token
}
async function socket(path, token, namespace, rejection = false, transports = ['websocket']) {
    const client = clientIo(base + path, { auth: { token }, extraHeaders: { 'X-Hapi-Expected-Namespace': namespace },
        transports, reconnection: false, forceNew: true, timeout: 3000 })
    clients.push(client)
    let error = null
    try {
        await new Promise((resolve, reject) => {
            client.once('connect', resolve); client.once('connect_error', reject)
            setTimeout(() => reject(new Error('unexpected timeout')), 4000).unref()
        })
    } catch (caught) { error = caught }
    if (rejection) {
        assert(error && error.message !== 'unexpected timeout', 'Must receive an actual authentication denial')
        client.disconnect(); return null
    }
    assert.equal(error, null)
    return client
}
async function bounded(promise, milliseconds = 2500) {
    return Promise.race([promise, new Promise((_, reject) => setTimeout(() => reject(new Error('verification timeout')), milliseconds).unref())])
}
try {
    const jwtLegacy = await auth(legacy, 'default')
    pass('legacy credential remains fixed to existing default namespace')
    const jwtA = await auth(alice, 'alice'), jwtB = await auth(bob, 'bob')
    pass('opaque independent credentials derive the server-side namespace')
    await auth(alice + ':alice', 'alice')
    pass('matching legacy namespace hint is accepted')
    await auth(alice + ':bob', 'alice', 401)
    await auth(alice + ':default', 'alice', 401)
    await auth(legacy + ':bob', 'default', 401)
    pass('changing or dropping a namespace hint never selects another tenant')
    await auth(alice, 'bob', 401)
    await auth(alice, null, 401)
    pass('trusted ingress namespace must match the credential')
    await auth(master + ':bob', 'bob', 401)
    await auth(master, 'default', 401)
    pass('server base token is not a tenant-mode fallback')
    sync.getOrCreateMachine('machine-alice', {}, null, 'alice')
    sync.getOrCreateMachine('machine-bob', {}, null, 'bob')
    sync.handleMachineAlive({ machineId: 'machine-alice', time: Date.now() })
    sync.handleMachineAlive({ machineId: 'machine-bob', time: Date.now() })
    const sa = sync.getOrCreateSession('tag-alice', {}, null, 'alice')
    const sb = sync.getOrCreateSession('tag-bob', {}, null, 'bob')
    for (const [namespace, token, own, other] of [['alice', jwtA, sa, sb], ['bob', jwtB, sb, sa]]) {
        const response = await request('/api/sessions', namespace, token)
        assert.equal(response.status, 200)
        const body = await response.json()
        assert(body.sessions.some(row => row.id === own.id))
        assert(!body.sessions.some(row => row.id === other.id))
        assert([403, 404].includes((await request('/api/sessions/' + other.id, namespace, token)).status))
    }
    pass('actual session list and object access remain tenant-scoped')
    const machines = await (await request('/api/machines', 'alice', jwtA)).json()
    assert(machines.machines.some(row => row.id === 'machine-alice'))
    assert(!machines.machines.some(row => row.id === 'machine-bob'))
    pass('actual online machine list is tenant-scoped')
    assert.equal((await request('/api/sessions', 'alice', jwtB)).status, 403)
    assert.equal((await request('/api/sessions', null, jwtA)).status, 403)
    pass('valid foreign JWT and missing ingress identity are rejected')
    assert.equal((await request('/cli/machines', 'alice', alice + ':bob', 'POST', { id: 'forged', metadata: {} })).status, 401)
    pass('CLI HTTP authentication also rejects namespace suffix switching')
    for (const path of ['/api/bind', '/api/storage/sqlite', '/api/codex/desktop/restart', '/api/voice/gemini-ws']) {
        assert.equal((await request(path, 'default', jwtLegacy, path === '/api/bind' ? 'POST' : 'GET', {}.body)).status, 403)
    }
    assert.equal((await request('/api/hub-settings', 'default', jwtLegacy, 'PUT', {})).status, 403)
    pass('binding, global storage/config mutation and Hub-local execution surfaces are closed')
    const a = await socket('/cli', alice, 'alice')
    const b = await socket('/cli', bob, 'bob')
    assert.equal(io.of('/cli').sockets.get(a.id).data.namespace, 'alice')
    assert.equal(io.of('/cli').sockets.get(b.id).data.namespace, 'bob')
    pass('actual Runner sockets receive fixed server namespaces')
    await socket('/cli', alice + ':bob', 'alice', true)
    await socket('/cli', alice, 'bob', true)
    pass('Runner sockets reject cross-namespace hints and ingress identity')
    const polling = await socket('/cli', bob + ':bob', 'bob', false, ['polling'])
    polling.disconnect()
    pass('Socket.IO HTTP polling uses the same tenant authentication')
    const terminalA = await socket('/terminal', jwtA, 'alice')
    await socket('/terminal', jwtB, 'alice', true)
    pass('browser terminal sockets bind JWT namespace to the ingress identity')
    let wrongRpc = 0, rightRpc = 0
    const method = 'machine-bob:' + RPC_METHODS.PathExists
    b.on('rpc-request', (_value, ack) => { rightRpc++; ack(JSON.stringify({ exists: { '/bob-only': true } })) })
    a.on('rpc-request', (_value, ack) => { wrongRpc++; ack(JSON.stringify({ exists: { '/bob-only': false } })) })
    b.emit('rpc-register', { method }); a.emit('rpc-register', { method })
    await new Promise(resolve => setTimeout(resolve, 60))
    assert.equal(rpcRegistry.getSocketIdForMethod(method, 'bob'), b.id)
    assert.equal(rpcRegistry.getSocketIdForMethod(method, 'alice'), a.id)
    const rpc = await request('/api/machines/machine-bob/paths/exists', 'bob', jwtB, 'POST', { paths: ['/bob-only'] })
    assert.equal(rpc.status, 200)
    assert.equal((await rpc.json()).exists['/bob-only'], true)
    assert.equal(rightRpc, 1); assert.equal(wrongRpc, 0)
    pass('malicious RPC registration cannot shadow another namespace target')
    const controller = new AbortController()
    const response = await fetch(base + '/api/events?all=true&token=' + encodeURIComponent(jwtA), {
        headers: { 'X-Hapi-Expected-Namespace': 'alice' }, signal: controller.signal })
    assert.equal(response.status, 200)
    const reader = response.body.getReader(); readers.push(reader)
    await bounded(reader.read())
    registry.credentials.find(row => row.id === 'alice').enabled = false; publish()
    await auth(alice, 'alice', 401)
    assert.equal((await request('/api/sessions', 'alice', jwtA)).status, 403)
    pass('disabled credentials revoke new authentication and already issued JWTs')
    await bounded(new Promise(resolve => { if (!a.connected) resolve(); else a.once('disconnect', resolve) }))
    await bounded(new Promise(resolve => { if (!terminalA.connected) resolve(); else terminalA.once('disconnect', resolve) }))
    pass('revocation disconnects existing Runner and terminal sockets')
    await bounded((async () => { while (!(await reader.read()).done) {} })())
    controller.abort()
    pass('revocation closes an already open SSE response')
    assert(b.connected)
    assert.equal((await request('/api/sessions', 'bob', jwtB)).status, 200)
    pass('revoking one credential preserves the other tenant')
    registry.credentials.find(row => row.id === 'alice').enabled = true
    registry.credentials.find(row => row.id === 'alice').generation++
    publish()
    assert.equal((await request('/api/sessions', 'alice', jwtA)).status, 403)
    await auth(alice, 'alice')
    pass('explicit reenable with new generation does not resurrect old JWTs')
    const short = await new SignJWT((await jwtVerify(jwtB, key)).payload).setProtectedHeader({ alg: 'HS256' })
        .setExpirationTime(Math.floor(Date.now() / 1000) + 1).sign(key)
    const shortSocket = await socket('/terminal', short, 'bob')
    await bounded(new Promise(resolve => shortSocket.once('disconnect', resolve)), 3000)
    pass('JWT expiry also disconnects an existing terminal socket')
    publish({ version: 1, credentials: [{ invalid: true }] })
    await auth(bob, 'bob', 401)
    assert.equal((await request('/api/sessions', 'bob', jwtB)).status, 403)
    await bounded(new Promise(resolve => { if (!b.connected) resolve(); else b.once('disconnect', resolve) }))
    pass('invalid registry fails closed without falling back to the base token')
    publish()
    console.log(JSON.stringify({ passed: results.length, scope: 'actual patched Hub auth/store/RPC/streams; synthetic credentials', production_changed: false }))
} finally {
    for (const client of clients) client.disconnect()
    for (const reader of readers) try { await reader.cancel() } catch {}
    sync.stop(); sse.stop(); await io.close(); server.stop(true); store.close()
}
