// Verify the compiled quarantined Hub through two actual worker network paths.
import assert from 'node:assert/strict'
import { execFileSync, spawn } from 'node:child_process'
import { createRequire } from 'node:module'
import { createServer, connect } from 'node:net'
import https from 'node:https'
import { join, resolve } from 'node:path'
import { writeFileSync } from 'node:fs'

const runtime = resolve(process.argv[2])
const repository = process.cwd()
const variables = JSON.parse(execFileSync('/opt/iac-venv/bin/ansible-vault', [
    'view', join(runtime, 'shared-hub-runtime.vault.json'),
    '--vault-password-file', join(repository, 'ansible/.vault_pass')], { encoding: 'utf8' }))
const registry = { version: 1, credentials: variables.vault_hapi_shared_hub_credentials }
const require = createRequire('/tmp/hapi-shared-hub-20261031-r3/source/cli/package.json')
const { io } = require('socket.io-client')
const known = join(runtime, 'migration-known-hosts')
const sshOptions = ['-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile=' + known, '-o', 'ConnectTimeout=8']
const processes = [], sockets = [], streams = [], results = []
let registryChanged = false
const disabled = structuredClone(registry)
disabled.credentials.find(row => row.id === 'test_alice').enabled = false
const pause = ms => new Promise(resolve => setTimeout(resolve, ms))
const bounded = (promise, ms = 4000) => Promise.race([promise, new Promise((_, reject) => setTimeout(() => reject(new Error('Live verification timeout')), ms).unref())])
const pass = label => { results.push(label); console.log('PASS ' + label) }

async function forward(address) {
    const port = await new Promise(resolve => {
        const reserve = createServer().listen(0, '127.0.0.1', () => {
            const port = reserve.address().port
            reserve.close(() => resolve(port))
        })
    })
    const process = spawn('ssh', [...sshOptions, '-N', '-o', 'ExitOnForwardFailure=yes', '-L', `127.0.0.1:${port}:192.168.1.140:9443`, 'ubuntu@' + address], { stdio: 'ignore' })
    processes.push(process)
    for (let attempt = 0; attempt < 50; attempt++) {
        assert.equal(process.exitCode, null, 'Worker forwarding exited')
        const ready = await new Promise(resolve => {
            const socket = connect(port, '127.0.0.1')
            socket.once('connect', () => { socket.destroy(); resolve(true) })
            socket.once('error', () => resolve(false))
        })
        if (ready) return port
        await pause(100)
    }
    throw new Error('Worker forwarding unavailable')
}

function options(worker) {
    return { hostname: '127.0.0.1', port: worker.port, servername: 'hapi-hub.internal',
        ca: variables.vault_hapi_shared_hub_ca, cert: worker.leaf.certificate, key: worker.leaf.private_key,
        rejectUnauthorized: true, agent: false }
}

function request(worker, path, token, method = 'GET', body, streaming = false) {
    return new Promise((resolve, reject) => {
        const headers = { Host: 'hapi-hub.internal', 'X-Hapi-Expected-Namespace': 'forged', 'X-Hapi-Expected-Credential': 'forged' }
        if (token) headers.Authorization = 'Bearer ' + token
        const raw = body === undefined ? undefined : JSON.stringify(body)
        if (raw) { headers['Content-Type'] = 'application/json'; headers['Content-Length'] = Buffer.byteLength(raw) }
        const outgoing = https.request({ ...options(worker), path, method, headers }, incoming => {
            if (streaming) { incoming.resume(); streams.push(incoming); resolve(incoming); return }
            const chunks = []
            incoming.on('data', chunk => chunks.push(chunk))
            incoming.on('end', () => resolve({ status: incoming.statusCode, body: Buffer.concat(chunks).toString() }))
        })
        outgoing.on('error', reject)
        outgoing.setTimeout(6000, () => outgoing.destroy(new Error('HTTPS timeout')))
        outgoing.end(raw)
    })
}

async function socket(worker, path, token, rejectExpected = false, transports = ['websocket']) {
    // XMLHttpRequest overwrites extraHeaders.Host with the loopback URL. Match
    // the production worker proxy's fixed private authority at the HTTP agent.
    class HubAgent extends https.Agent {
        addRequest(request, options) {
            request.setHeader('Host', 'hapi-hub.internal')
            super.addRequest(request, { ...options, servername: 'hapi-hub.internal' })
        }
    }
    const client = io(`https://127.0.0.1:${worker.port}${path}`, {
        auth: { token }, transports, reconnection: false, forceNew: true, timeout: 4000,
        ca: variables.vault_hapi_shared_hub_ca, cert: worker.leaf.certificate, key: worker.leaf.private_key,
        servername: 'hapi-hub.internal', rejectUnauthorized: true,
        agent: new HubAgent({ servername: 'hapi-hub.internal',
            ca: variables.vault_hapi_shared_hub_ca, cert: worker.leaf.certificate, key: worker.leaf.private_key,
            rejectUnauthorized: true, keepAlive: false }),
        extraHeaders: { Host: 'hapi-hub.internal', 'X-Hapi-Expected-Namespace': 'forged' }
    })
    sockets.push(client)
    let error
    try { await bounded(new Promise((resolve, reject) => { client.once('connect', resolve); client.once('connect_error', reject) }), 6000) }
    catch (caught) { error = caught }
    if (rejectExpected) { assert(error && !/timeout/i.test(error.message), 'Expected an actual authentication denial'); client.disconnect(); return null }
    if (error) {
        console.error(JSON.stringify({ socket_error: error.message, status: typeof error.description === 'number' ? error.description : null,
            http_status: error.context?.status ?? null, tls_code: error.context?.response?.code ?? null }))
        throw new Error('Actual Socket.IO transport failed: ' + error.message)
    }
    return client
}

function publish(expected, next) {
    const code = `import json,sys,os,tempfile,grp
from pathlib import Path
v=json.load(sys.stdin);p=Path('/etc/hapi-shared-hub/credentials.json')
assert json.loads(p.read_bytes())==v['expected'], 'Concurrent credential policy change'
fd,name=tempfile.mkstemp(dir=p.parent,prefix='.hapi-validation-')
os.fchmod(fd,0o640);os.fchown(fd,0,grp.getgrnam('hapi-hub').gr_gid)
with os.fdopen(fd,'w') as output:json.dump(v['next'],output);output.flush();os.fsync(output.fileno())
os.replace(name,p)
`
    const quote = value => "'" + value.replaceAll("'", "'\\''") + "'"
    execFileSync('ssh', [...sshOptions, 'ubuntu@192.168.1.140', 'sudo -n python3 -c ' + quote(code)],
        { input: JSON.stringify({ expected, next }), stdio: ['pipe', 'pipe', 'pipe'] })
}

try {
    const workers = []
    for (const [id, address, leafId] of [['test_alice', '192.168.1.148', 'test-alice'], ['test_bob', '192.168.1.149', 'test-bob']]) {
        const credential = registry.credentials.find(row => row.id === id)
        const worker = { ...credential, leaf: variables.vault_hapi_hub_clients[leafId], port: await forward(address) }
        const auth = await request(worker, '/api/auth', null, 'POST', { accessToken: worker.token })
        assert.equal(auth.status, 200)
        worker.jwt = JSON.parse(auth.body).token
        const claims = JSON.parse(Buffer.from(worker.jwt.split('.')[1], 'base64url'))
        assert.equal(claims.ns, worker.namespace); assert.equal(claims.cid, id)
        worker.machine = 'hapi-migration-' + id
        assert.equal((await request(worker, '/cli/machines', worker.token, 'POST', { id: worker.machine, metadata: {} })).status, 200)
        const session = await request(worker, '/cli/sessions', worker.token, 'POST', { tag: 'hapi-migration-' + id, metadata: {} })
        assert.equal(session.status, 200); worker.session = JSON.parse(session.body).session.id
        workers.push(worker)
    }
    const [alice, bob] = workers
    pass('actual worker mTLS credentials create resources only in fixed namespaces')
    assert([401, 403].includes((await request(alice, '/api/sessions', bob.jwt)).status))
    assert([403, 404].includes((await request(alice, '/api/sessions/' + bob.session, alice.jwt)).status))
    assert([401, 403].includes((await request(alice, '/api/auth', null, 'POST', { accessToken: alice.token + ':test_bob' })).status))
    pass('foreign JWT resource access and namespace suffix escalation are denied over the real transport')
    const a = await socket(alice, '/cli', alice.token), b = await socket(bob, '/cli', bob.token)
    a.emit('machine-alive', { machineId: alice.machine, time: Date.now() })
    b.emit('machine-alive', { machineId: bob.machine, time: Date.now() })
    pass('two real Socket.IO Runner channels connect over worker mTLS')
    await socket(alice, '/cli', alice.token + ':test_bob', true)
    await socket(bob, '/cli', bob.token, false, ['polling'])
    pass('Runner namespace escalation is denied and HTTP polling works')
    const terminal = await socket(alice, '/terminal', alice.jwt)
    await socket(alice, '/terminal', bob.jwt, true)
    pass('terminal sockets reject a foreign namespace JWT')
    let wrong = 0, right = 0
    b.on('rpc-request', (_value, ack) => { right++; ack(JSON.stringify({ exists: { '/bob-only': true } })) })
    a.on('rpc-request', (_value, ack) => { wrong++; ack(JSON.stringify({ exists: { '/bob-only': false } })) })
    b.emit('rpc-register', { method: bob.machine + ':path-exists' }); a.emit('rpc-register', { method: bob.machine + ':path-exists' })
    await pause(100)
    const rpc = await request(bob, '/api/machines/' + bob.machine + '/paths/exists', bob.jwt, 'POST', { paths: ['/bob-only'] })
    assert.equal(rpc.status, 200); assert.equal(JSON.parse(rpc.body).exists['/bob-only'], true)
    assert.equal(right, 1); assert.equal(wrong, 0)
    pass('actual malicious RPC registration cannot shadow the other worker namespace')
    const stream = await request(alice, '/api/events?all=true&token=' + encodeURIComponent(alice.jwt), null, 'GET', undefined, true)
    assert.equal(stream.statusCode, 200); assert.match(stream.headers['content-type'], /text\/event-stream/)
    const runnerClosed = new Promise(resolve => a.once('disconnect', resolve))
    const terminalClosed = new Promise(resolve => terminal.once('disconnect', resolve))
    const streamClosed = new Promise(resolve => { stream.once('close', resolve); stream.once('end', resolve); stream.once('aborted', resolve) })
    publish(registry, disabled); registryChanged = true
    await bounded(Promise.all([runnerClosed, terminalClosed, streamClosed]))
    assert(b.connected)
    assert([401, 403].includes((await request(alice, '/api/sessions', alice.jwt)).status))
    assert.equal((await request(bob, '/api/sessions', bob.jwt)).status, 200)
    pass('real Runner terminal and SSE streams revoke without interrupting the other worker')
    publish(disabled, registry); registryChanged = false
    const report = { passed: results.length, scope: 'compiled quarantined Hub over actual worker mTLS paths',
        production_data_accessed: false, production_hub_cut: false, cases: results }
    writeFileSync(join(runtime, 'live-hub-transport-regression.json'), JSON.stringify(report, null, 2) + '\n', { mode: 0o600 })
    console.log(JSON.stringify({ passed: results.length, scope: report.scope, production_hub_cut: false }))
} finally {
    if (registryChanged) publish(disabled, registry)
    for (const stream of streams) stream.destroy()
    for (const socket of sockets) socket.disconnect()
    for (const process of processes) process.kill('SIGTERM')
}
