import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
    authenticateWorkspace, clearWorkspaceBrowserState, fetchWorkspaceIdentity,
    stripWorkspaceCredentialsFromUrl, WORKSPACE_INVALIDATED,
} from './workspace-auth'

const identity = { workspace_id: 'alice', generation: 1, identity: 'a'.repeat(64) }
const reply = { ...identity, csrf: 'c'.repeat(64) }
const ticket = { token: 'header.payload.signature', user: { id: 1 }, workspace: identity }
const fetchMock = vi.fn()
function response(body: unknown, status = 200) {
    return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

beforeEach(() => {
    vi.restoreAllMocks()
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
    localStorage.clear(); sessionStorage.clear()
    window.history.replaceState(null, '', '/sessions')
})

describe('automatic workspace authentication', () => {
    it('obtains a same-origin short ticket without sending or storing a base token', async () => {
        fetchMock.mockResolvedValueOnce(response(reply)).mockResolvedValueOnce(response(ticket))
        const result = await authenticateWorkspace(identity, window.location.origin)
        expect(result.token).toBe(ticket.token)
        expect(fetchMock.mock.calls.map(call => call[0])).toEqual(['/_workspace/identity', '/_workspace/session'])
        const request = fetchMock.mock.calls[1][1]
        expect(request).toMatchObject({ credentials: 'same-origin', cache: 'no-store', redirect: 'error', body: '{}' })
        expect(request.headers).toEqual({ 'Content-Type': 'application/json', 'X-Hapi-CSRF': reply.csrf })
        expect(localStorage.length).toBe(0)
        expect(sessionStorage.length).toBe(0)
    })
    it('never follows a user-supplied alternate Hub', async () => {
        await expect(authenticateWorkspace(identity, 'https://other.example.com')).rejects.toThrow('当前入口')
        expect(fetchMock).not.toHaveBeenCalled()
    })
    it('rejects an account change before exchange and a reassignment in the response', async () => {
        const invalidated = vi.fn(); window.addEventListener(WORKSPACE_INVALIDATED, invalidated)
        try {
            fetchMock.mockResolvedValueOnce(response({ ...reply, workspace_id: 'bob' }))
            await expect(authenticateWorkspace(identity, '')).rejects.toThrow('身份已变化')
            expect(fetchMock).toHaveBeenCalledTimes(1)
            fetchMock.mockResolvedValueOnce(response(reply)).mockResolvedValueOnce(response({
                ...ticket, workspace: { ...identity, generation: 2 },
            }))
            await expect(authenticateWorkspace(identity, '')).rejects.toThrow('身份已变化')
            expect(invalidated).toHaveBeenCalledTimes(2)
        } finally {
            window.removeEventListener(WORKSPACE_INVALIDATED, invalidated)
        }
    })
    it('refreshes CSRF once after a restart without prompting for another login', async () => {
        fetchMock.mockResolvedValueOnce(response(reply)).mockResolvedValueOnce(response({}, 403))
            .mockResolvedValueOnce(response({ ...reply, csrf: 'd'.repeat(64) })).mockResolvedValueOnce(response(ticket))
        await expect(authenticateWorkspace(identity, '')).resolves.toHaveProperty('token', ticket.token)
        expect(fetchMock).toHaveBeenCalledTimes(4)
        expect(fetchMock.mock.calls[3][1].headers['X-Hapi-CSRF']).toBe('d'.repeat(64))
    })
    it('does not retry ticket exchange into another account after a 403', async () => {
        fetchMock.mockResolvedValueOnce(response(reply)).mockResolvedValueOnce(response({}, 403))
            .mockResolvedValueOnce(response({ ...reply, identity: 'b'.repeat(64) }))
        await expect(authenticateWorkspace(identity, '')).rejects.toThrow('身份已变化')
        expect(fetchMock.mock.calls.filter(call => call[0] === '/_workspace/session')).toHaveLength(1)
    })
    it('fails closed on Access redirects, malformed responses and upstream failures', async () => {
        fetchMock.mockRejectedValueOnce(new TypeError('redirect disallowed'))
        await expect(fetchWorkspaceIdentity()).rejects.toThrow()
        fetchMock.mockResolvedValueOnce(response({ ...reply, generation: true }))
        await expect(fetchWorkspaceIdentity()).rejects.toThrow()
        fetchMock.mockResolvedValueOnce(response(reply)).mockResolvedValueOnce(response({ error: 'SECRET_SENTINEL' }, 503))
        await expect(authenticateWorkspace(identity, '')).rejects.not.toThrow('SECRET_SENTINEL')
    })
    it('removes legacy credentials and alternate-server URL parameters before app startup', () => {
        window.history.replaceState(null, '', '/sessions?token=secret&hub=https://evil.example&server=x&initData=x&tgWebAppData=x&safe=1')
        stripWorkspaceCredentialsFromUrl()
        expect(window.location.search).toBe('?safe=1')
        expect(window.location.pathname).toBe('/sessions')
    })
    it('clears application data and service workers while preserving Access cookies', async () => {
        localStorage.setItem('old-session', 'alice'); sessionStorage.setItem('old-message', 'alice')
        document.cookie = 'CF_Authorization=synthetic; Path=/'
        const unregister = vi.fn().mockResolvedValue(true)
        const removeCache = vi.fn().mockResolvedValue(true)
        const deleteDatabase = vi.fn().mockImplementation(() => {
            const request: { onsuccess?: () => void } = {}
            queueMicrotask(() => request.onsuccess?.())
            return request
        })
        vi.stubGlobal('caches', { keys: async () => ['old-hapi-cache'], delete: removeCache })
        vi.stubGlobal('indexedDB', { databases: async () => [{ name: 'old-private-share' }], deleteDatabase })
        Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: {
            controller: {}, getRegistrations: async () => [{ unregister }],
        } })
        expect(await clearWorkspaceBrowserState()).toBe(true)
        expect(localStorage.length).toBe(0); expect(sessionStorage.length).toBe(0)
        expect(unregister).toHaveBeenCalledTimes(1)
        expect(removeCache).toHaveBeenCalledWith('old-hapi-cache')
        expect(deleteDatabase).toHaveBeenCalledWith('old-private-share')
        expect(document.cookie).toContain('CF_Authorization=synthetic')
    })
})
