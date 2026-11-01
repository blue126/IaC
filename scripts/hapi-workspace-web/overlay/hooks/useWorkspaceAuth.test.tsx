import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
const h = vi.hoisted(() => {
    vi.stubEnv('VITE_HAPI_WORKSPACE_AUTH', '1')
    const exchange = vi.fn()
    const legacy = vi.fn()
    class Client {
        constructor(readonly token: string, readonly options?: { getToken?: () => string | null; onUnauthorized?: () => unknown }) {}
        authenticate = legacy
    }
    return { exchange, legacy, Client }
})
vi.mock('@/api/client', () => ({ ApiClient: h.Client, ApiError: class extends Error {} }))
vi.mock('@/lib/workspace-auth', async importOriginal => ({
    ...await importOriginal<typeof import('@/lib/workspace-auth')>(), authenticateWorkspace: h.exchange,
}))
import { useAuthSource } from './useAuthSource'
import { useServerUrl } from './useServerUrl'
import { useAuth, type AuthSource } from './useAuth'
import { WorkspaceIdentityContext } from '@/lib/workspace-auth'
const identity = { workspace_id: 'alice', generation: 1, identity: 'a'.repeat(64) }
const source: AuthSource = { type: 'workspace', workspace: identity }
beforeEach(() => {
    localStorage.clear(); sessionStorage.clear()
    h.exchange.mockReset(); h.legacy.mockReset()
    window.history.replaceState(null, '', '/')
})
afterEach(() => cleanup())

describe('HAPI hooks with automatic workspace login', () => {
    it('ignores legacy tokens, Telegram parameters and alternate Hub addresses', async () => {
        localStorage.setItem('hapi_access_token::'+window.location.origin, 'LONG_TOKEN_SENTINEL')
        localStorage.setItem('hapi_hub_url', 'https://other.example.com')
        window.history.replaceState(null, '', '/?token=URL_TOKEN_SENTINEL&hub=https://evil.example&initData=telegram')
        const wrapper = ({ children }: { children: ReactNode }) =>
            <WorkspaceIdentityContext.Provider value={identity}>{children}</WorkspaceIdentityContext.Provider>
        const { result } = renderHook(() => {
            const server = useServerUrl()
            return { ...server, ...useAuthSource(server.baseUrl) }
        }, { wrapper })
        await waitFor(() => expect(result.current.authSource?.type).toBe('workspace'))
        expect(result.current.baseUrl).toBe(window.location.origin)
        expect(result.current.isTelegram).toBe(false)
        expect(localStorage.getItem('hapi_access_token::'+window.location.origin)).toBeNull()
        act(() => result.current.setAccessToken('NEW_LONG_TOKEN_SENTINEL'))
        expect(result.current.authSource?.type).toBe('workspace')
        expect(JSON.stringify([...Array(localStorage.length)].map((_, i) => localStorage.getItem(localStorage.key(i)!))))
            .not.toContain('LONG_TOKEN_SENTINEL')
    })
    it('uses the gateway for initial auth and renewal while keeping the ApiClient stable', async () => {
        h.exchange.mockResolvedValueOnce({ token: 'short-1', user: { id: 1 } })
            .mockResolvedValueOnce({ token: 'short-2', user: { id: 1 } })
        const { result } = renderHook(() => useAuth(source, window.location.origin))
        await waitFor(() => expect(result.current.token).toBe('short-1'))
        const client = result.current.api as unknown as InstanceType<typeof h.Client>
        await act(async () => { await client.options?.onUnauthorized?.() })
        expect(result.current.token).toBe('short-2')
        expect(result.current.api).toBe(client)
        expect(client.options?.getToken?.()).toBe('short-2')
        expect(h.exchange).toHaveBeenCalledTimes(2)
        expect(h.legacy).not.toHaveBeenCalled()
        expect(localStorage.length).toBe(0)
    })
    it('does not overwrite a newer identity with a late old refresh', async () => {
        let resolve!: (value: unknown) => void
        h.exchange.mockResolvedValueOnce({ token: 'short-a', user: { id: 1 } })
            .mockReturnValueOnce(new Promise(done => { resolve = done }))
            .mockResolvedValueOnce({ token: 'short-b', user: { id: 2 } })
        const { result, rerender } = renderHook(({ authSource }) => useAuth(authSource, window.location.origin), {
            initialProps: { authSource: source },
        })
        await waitFor(() => expect(result.current.token).toBe('short-a'))
        const oldClient = result.current.api as unknown as InstanceType<typeof h.Client>
        let refresh: unknown
        act(() => { refresh = oldClient.options?.onUnauthorized?.() })
        const bob: AuthSource = { type: 'workspace', workspace: { ...identity, workspace_id: 'bob' } }
        rerender({ authSource: bob })
        await waitFor(() => expect(result.current.token).toBe('short-b'))
        await act(async () => { resolve({ token: 'late-a', user: { id: 1 } }); await refresh })
        expect(result.current.token).toBe('short-b')
    })
})
