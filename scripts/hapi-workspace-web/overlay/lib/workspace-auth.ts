import { createContext, useContext } from 'react'
import type { AuthResponse } from '@/types/api'

export const WORKSPACE_AUTH = import.meta.env.VITE_HAPI_WORKSPACE_AUTH === '1'
export const WORKSPACE_INVALIDATED = 'hapi-workspace-invalidated'
export const WORKSPACE_MARKER = 'hapi_workspace_identity_v1'

export type WorkspaceIdentity = {
    workspace_id: string
    generation: number
    identity: string
}
export const WorkspaceIdentityContext = createContext<WorkspaceIdentity | null>(null)
export function useWorkspaceIdentity() {
    return useContext(WorkspaceIdentityContext)
}
export function workspaceKey(identity: WorkspaceIdentity): string {
    return `${identity.identity}:${identity.workspace_id}:${identity.generation}`
}
function identityFrom(value: unknown): WorkspaceIdentity {
    const item = value as Partial<WorkspaceIdentity> | null
    if (!item || typeof item.workspace_id !== 'string' || !/^[a-z][a-z0-9-]{0,31}$/.test(item.workspace_id)
        || !Number.isSafeInteger(item.generation) || (item.generation ?? 0) < 1
        || typeof item.identity !== 'string' || !/^[a-f0-9]{64}$/.test(item.identity)) {
        throw new Error('工作区身份响应无效，请重新验证入口。')
    }
    return { workspace_id: item.workspace_id, generation: item.generation!, identity: item.identity }
}

export class WorkspaceRequestError extends Error {
    constructor(readonly status: number) {
        super('工作区暂时不可用，请刷新入口或联系管理员。')
    }
}
async function request(path: string, init: RequestInit = {}): Promise<Record<string, unknown>> {
    const response = await fetch(path, {
        ...init, credentials: 'same-origin', cache: 'no-store', redirect: 'error',
        signal: init.signal ?? AbortSignal.timeout(15_000),
    })
    if (!response.ok) throw new WorkspaceRequestError(response.status)
    const value: unknown = await response.json()
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
        throw new Error('工作区响应无效。')
    }
    return value as Record<string, unknown>
}
export async function fetchWorkspaceIdentity(signal?: AbortSignal) {
    const value = await request('/_workspace/identity', { signal })
    const identity = identityFrom(value)
    if (typeof value.csrf !== 'string' || !/^[a-f0-9]{64}$/.test(value.csrf)) {
        throw new Error('工作区会话校验无效。')
    }
    return { ...identity, csrf: value.csrf }
}
export function invalidateWorkspace(): void {
    window.dispatchEvent(new Event(WORKSPACE_INVALIDATED))
}
export async function authenticateWorkspace(expected: WorkspaceIdentity, baseUrl: string): Promise<AuthResponse> {
    if (baseUrl && baseUrl !== window.location.origin) {
        throw new Error('工作区只允许使用当前入口。')
    }
    try {
        for (let attempt = 0; attempt < 2; attempt++) {
            const current = await fetchWorkspaceIdentity()
            if (workspaceKey(current) !== workspaceKey(expected)) {
                throw new Error('工作区身份已变化。')
            }
            let result: Record<string, unknown>
            try {
                result = await request('/_workspace/session', {
                    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Hapi-CSRF': current.csrf },
                    body: '{}',
                })
            } catch (error) {
                // A process restart or Access assertion refresh can invalidate CSRF.
                // Retrying ticket creation is safe, but identity is checked again first.
                if (attempt === 0 && error instanceof WorkspaceRequestError && error.status === 403) continue
                throw error
            }
            if (workspaceKey(identityFrom(result.workspace)) !== workspaceKey(expected)) {
                throw new Error('工作区身份已变化。')
            }
            if (typeof result.token !== 'string' || !/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(result.token)
                || !result.user || typeof result.user !== 'object' || Array.isArray(result.user)) {
                throw new Error('工作区会话响应无效。')
            }
            return { token: result.token, user: result.user as AuthResponse['user'] }
        }
        throw new Error('无法建立工作区会话。')
    } catch (error) {
        invalidateWorkspace()
        throw error
    }
}

export function stripWorkspaceCredentialsFromUrl(): void {
    const url = new URL(window.location.href)
    for (const field of ['token', 'hub', 'server', 'initData', 'tgWebAppData']) url.searchParams.delete(field)
    window.history.replaceState(null, '', url.pathname + url.search + url.hash)
}

export async function clearWorkspaceBrowserState(): Promise<boolean> {
    // This build is served only on the dedicated workspace origin. Access cookies
    // remain intact: clearing application state must not require another login.
    window.localStorage.clear()
    window.sessionStorage.clear()
    const controlled = Boolean(navigator.serviceWorker?.controller)
    if (navigator.serviceWorker) {
        const registrations = await navigator.serviceWorker.getRegistrations()
        await Promise.all(registrations.map(registration => registration.unregister()))
    }
    if ('caches' in window) {
        const keys = await window.caches.keys()
        await Promise.all(keys.map(key => window.caches.delete(key)))
    }
    if (window.indexedDB?.databases) {
        const databases = await window.indexedDB.databases()
        await Promise.all(databases.filter(database => database.name).map(database => new Promise<void>((resolve, reject) => {
            const request = window.indexedDB.deleteDatabase(database.name!)
            request.onsuccess = () => resolve()
            request.onerror = () => reject(new Error('无法清理工作区本地数据。'))
            request.onblocked = () => reject(new Error('请关闭旧工作区页面后重试。'))
        })))
    }
    return controlled
}
