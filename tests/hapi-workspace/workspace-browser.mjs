// Run the compiled workspace frontend against a loopback-only simulated gateway.
import assert from 'node:assert/strict'
import { createHmac } from 'node:crypto'
import { readFile, stat, mkdir } from 'node:fs/promises'
import http from 'node:http'
import path from 'node:path'
import { createRequire } from 'node:module'

const [distArg, dependencyRoot, evidenceArg] = process.argv.slice(2)
if (!distArg || !dependencyRoot || !evidenceArg) {
    throw new Error('Use the approved Sandbox: node workspace-browser.mjs DIST UPSTREAM_ROOT EVIDENCE_DIR')
}
const dist = path.resolve(distArg)
const require = createRequire(path.join(path.resolve(dependencyRoot), 'package.json'))
const { chromium } = require('playwright')
const records = []
let owner = 'alice', denied = false
const flows = new Map()
const flow = () => { if (!flows.has(owner)) flows.set(owner, { state: 'idle', authenticated: false, viewer_ready: false, codes: [] }); return flows.get(owner) }
const connections = new Set()
const identity = () => ({ workspace_id: owner, generation: 1, identity: (owner === 'alice' ? 'a' : 'b').repeat(64) })
function ticket() {
    const first = Buffer.from(JSON.stringify({ alg: 'HS256' })).toString('base64url')
    const second = Buffer.from(JSON.stringify({ uid: 1, ns: owner, iat: Math.floor(Date.now()/1000), exp: Math.floor(Date.now()/1000)+14400 })).toString('base64url')
    return first+'.'+second+'.'+createHmac('sha256', 'synthetic-only').update(first+'.'+second).digest('base64url')
}
function json(response, status, value) {
    response.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' })
    response.end(JSON.stringify(value))
}
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json',
    '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon', '.woff2': 'font/woff2', '.woff': 'font/woff' }
const server = http.createServer(async (request, response) => {
    try {
        const url = new URL(request.url, 'http://localhost')
        records.push({ path: url.pathname, owner, method: request.method })
        if (url.pathname.startsWith('/_workspace/') && denied) return json(response, 403, {})
        if (url.pathname === '/_workspace/login/') {
            const file = await readFile(path.resolve('ansible/roles/hapi-control-plane/files/hapi-login-portal/index.html'), 'utf8')
            const encoded = JSON.stringify(identity()).replace(/&/g, '&amp;').replace(/"/g, '&quot;')
            response.writeHead(200, { 'Content-Type': 'text/html', 'Cache-Control': 'no-store' })
            return response.end(file.replace('{{workspace}}', encoded).replace('{{hapi_url}}', '/sessions'))
        }
        if (url.pathname === '/_workspace/login/guide.js' || url.pathname === '/_workspace/login/guide.css') {
            const file = path.resolve('ansible/roles/hapi-control-plane/files/hapi-login-portal', path.basename(url.pathname))
            response.writeHead(200, { 'Content-Type': url.pathname.endsWith('.js') ? 'text/javascript' : 'text/css' })
            return response.end(await readFile(file))
        }
        if (url.pathname === '/_workspace/login/kasm/index.html') {
            response.writeHead(200, { 'Content-Type': 'text/html' })
            return response.end('<!doctype html><title>synthetic Kasm client</title>')
        }
        if (url.pathname.startsWith('/_workspace/login/api/login/')) {
            const state = flow()
            if (request.method === 'POST') {
                assert.equal(request.headers['x-hapi-csrf'], 'c'.repeat(64)); assert.equal(request.headers.origin, origin)
                let raw = ''; for await (const chunk of request) raw += chunk
                const data = JSON.parse(raw)
                const action = url.pathname.split('/').at(-1)
                if (action === 'start') { state.state = state.authenticated ? 'success' : 'running'; state.viewer_ready = !state.authenticated }
                else if (action === 'code') { state.codes.push(data.code); state.state = 'success'; state.authenticated = true; state.viewer_ready = false }
                else if (action === 'cancel') { state.state = 'cancelled'; state.viewer_ready = false }
            }
            return json(response, 200, { state: state.state, authenticated: state.authenticated, viewer_ready: state.viewer_ready })
        }
        if (url.pathname === '/_workspace/identity') return json(response, 200, { ...identity(), csrf: 'c'.repeat(64) })
        if (url.pathname === '/_workspace/session') {
            let body = ''
            for await (const chunk of request) body += chunk
            assert.equal(body, '{}')
            assert.equal(request.headers['x-hapi-csrf'], 'c'.repeat(64))
            assert.equal(request.headers.origin, origin)
            return json(response, 200, { token: ticket(), user: { id: 1, firstName: 'Web User' }, workspace: identity() })
        }
        if (url.pathname === '/api/auth') return json(response, 403, {})
        if (url.pathname.startsWith('/api/')) {
            const token = request.headers.authorization?.replace(/^Bearer /, '') ?? url.searchParams.get('token')
            let claim
            try { claim = JSON.parse(Buffer.from(token.split('.')[1], 'base64url').toString()) } catch {}
            if (claim?.ns !== owner) return json(response, 401, {})
        }
        if (url.pathname === '/api/events') {
            response.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store' })
            response.write('data: {"type":"heartbeat"}\n\n')
            return
        }
        if (url.pathname === '/api/sessions') return json(response, 200, { sessions: [] })
        if (url.pathname === '/api/machines') return json(response, 200, { machines: [] })
        if (url.pathname === '/api/health') return json(response, 200, { status: 'ok', capabilities: {} })
        if (url.pathname.startsWith('/api/')) return json(response, 200, {})
        const candidate = path.resolve(dist, '.' + decodeURIComponent(url.pathname))
        if (!candidate.startsWith(dist + path.sep) && candidate !== dist) return json(response, 404, {})
        let file = candidate
        try { if (!(await stat(file)).isFile()) file = path.join(dist, 'index.html') }
        catch { file = path.join(dist, 'index.html') }
        response.writeHead(200, { 'Content-Type': mime[path.extname(file)] ?? 'application/octet-stream', 'Cache-Control': 'no-store' })
        response.end(await readFile(file))
    } catch {
        if (!response.headersSent) json(response, 500, {})
        else response.end()
    }
})
server.on('connection', socket => { connections.add(socket); socket.on('close', () => connections.delete(socket)) })
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
const origin = `http://127.0.0.1:${server.address().port}`
let browser
try {
    browser = await chromium.launch({ headless: true })
    const context = await browser.newContext()
    await context.route('**/*', route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort())
    await context.addCookies([{ name: 'CF_Authorization', value: 'synthetic-access-session', url: origin }])
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    const noTokenForm = async () => {
        assert.equal(await page.locator('input[type="password"], input[placeholder*="token" i]').count(), 0)
        assert.equal(await page.getByText('重新验证入口', { exact: true }).count(), 0)
    }
    await page.goto(origin + '/sessions?token=legacy-token-sentinel&hub=https://other.example.com', { waitUntil: 'domcontentloaded' })
    await page.waitForRequest(request => request.url().includes('/api/sessions'), { timeout: 15000 }).catch(async () => {
        if (!records.some(record => record.path === '/api/sessions' && record.owner === 'alice')) throw new Error('HAPI did not open after automatic login')
    })
    await noTokenForm()
    assert.equal(new URL(page.url()).searchParams.has('token'), false)
    assert.equal(records.filter(record => record.path === '/api/auth').length, 0)
    assert.equal(await page.evaluate(() => JSON.stringify(localStorage).includes('legacy-token-sentinel')), false)
    await mkdir(evidenceArg, { recursive: true })
    await page.screenshot({ path: path.join(evidenceArg, 'automatic-login.png') })
    await page.evaluate(() => { localStorage.setItem('private-old-cache', 'alice'); window.dispatchEvent(new Event('blur')) })
    owner = 'bob'
    await page.evaluate(() => window.dispatchEvent(new Event('focus')))
    await page.waitForFunction(() => location.pathname === '/sessions' && !localStorage.getItem('private-old-cache'))
    await page.waitForResponse(response => response.url().includes('/api/sessions') && response.status() === 200, { timeout: 15000 }).catch(() => {
        assert.ok(records.some(record => record.path === '/api/sessions' && record.owner === 'bob'))
    })
    await noTokenForm()
    assert.ok((await context.cookies()).some(cookie => cookie.name === 'CF_Authorization'))
    denied = true
    await page.evaluate(() => window.dispatchEvent(new Event('focus')))
    await page.getByRole('button', { name: '重新验证入口' }).waitFor()
    assert.equal(await page.locator('input[type="password"], input[placeholder*="token" i]').count(), 0)
    denied = false
    await page.getByRole('button', { name: '重新验证入口' }).click()
    await page.waitForResponse(response => response.url().includes('/_workspace/session') && response.status() === 200)
    await noTokenForm()
    await page.getByRole('link', { name: 'Claude 登录', exact: true }).click()
    await page.getByRole('button', { name: '开始 Claude 授权', exact: true }).click()
    await page.locator('#viewer-section').waitFor({ state: 'visible' })
    const viewerUrl = new URL(await page.locator('#screen iframe').getAttribute('src'), 'http://localhost')
    assert.equal(viewerUrl.pathname, '/_workspace/login/kasm/index.html')
    assert.equal(viewerUrl.searchParams.get('path'), '_workspace/login/websockify')
    await page.locator('#code').fill('synthetic-code')
    await page.getByRole('button', { name: '提交授权码', exact: true }).click()
    await page.getByRole('link', { name: '进入 HAPI', exact: true }).click()
    await page.getByRole('link', { name: 'Claude 登录', exact: true }).waitFor()
    assert.ok((await context.cookies()).some(cookie => cookie.name === 'CF_Authorization'))
    const bobFlow = flows.get('bob')
    bobFlow.authenticated = false; bobFlow.state = 'idle'
    await page.getByRole('link', { name: 'Claude 登录', exact: true }).click()
    await page.getByRole('button', { name: '开始 Claude 授权', exact: true }).click()
    await page.locator('#viewer-section').waitFor({ state: 'visible' })
    await page.evaluate(() => window.dispatchEvent(new Event('blur')))
    owner = 'alice'
    await page.evaluate(() => window.dispatchEvent(new Event('focus')))
    await page.locator('#error').filter({ hasText: '身份已变化' }).waitFor()
    assert.equal(await page.locator('#viewer-section').isVisible(), false)
    assert.equal(await page.locator('#screen').textContent(), '')
    assert.equal(await page.locator('#screen iframe').count(), 0)
    assert.deepEqual(bobFlow.codes, ['synthetic-code'])
    assert.equal(flows.get('alice')?.codes.length ?? 0, 0)
    assert.equal(errors.length, 0, errors.join('\n'))
    console.log(JSON.stringify({ passed: true, compiled_frontend: true, simulated_gateway: true,
        automatic_login: true, account_switch: true, expiry_recovery: true,
        claude_guide: true, guide_identity_change: true,
        base_token_requests: records.filter(record => record.path === '/api/auth').length }))
} finally {
    await browser?.close()
    for (const socket of connections) socket.destroy()
    await new Promise(resolve => server.close(resolve))
}
