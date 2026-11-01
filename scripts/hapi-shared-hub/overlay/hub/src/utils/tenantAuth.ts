import { readFileSync, statSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { getConfiguration } from '../configuration'
import { parseAccessToken } from './accessToken'
import { constantTimeEquals } from './crypto'

export type TenantAuthorization = { namespace: string; credentialId?: string; credentialVersion?: string; expiresAt?: number }
type Credential = { id: string; token: string; namespace: string; generation: number; enabled: boolean }

export function tenantAuthEnabled(): boolean {
    return !!process.env.HAPI_TENANT_CREDENTIALS_FILE
}

function credentials(): Credential[] {
    const path = process.env.HAPI_TENANT_CREDENTIALS_FILE
    if (!path) throw new Error('Tenant credentials are not configured')
    const info = statSync(path)
    if (!info.isFile() || (info.mode & 0o007) !== 0 || info.size > 131072) throw new Error('Invalid tenant registry')
    const value = JSON.parse(readFileSync(path, 'utf8'))
    if (Object.keys(value).sort().join(',') !== 'credentials,version' || value.version !== 1 ||
        !Array.isArray(value.credentials) || value.credentials.length < 1 || value.credentials.length > 256) {
        throw new Error('Invalid tenant registry')
    }
    const ids = new Set<string>(), tokens = new Set<string>()
    for (const row of value.credentials) {
        if (Object.keys(row).sort().join(',') !== 'enabled,generation,id,namespace,token' ||
            typeof row.id !== 'string' || !/^[a-z][a-z0-9_-]{0,63}$/.test(row.id) ||
            typeof row.token !== 'string' || !/^[A-Za-z0-9_-]{32,256}$/.test(row.token) ||
            typeof row.namespace !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/.test(row.namespace) ||
            !Number.isSafeInteger(row.generation) || row.generation < 1 || typeof row.enabled !== 'boolean' ||
            ids.has(row.id) || tokens.has(row.token)) throw new Error('Invalid tenant registry')
        ids.add(row.id); tokens.add(row.token)
    }
    return value.credentials
}

export function assertTenantConfiguration(): void {
    if (tenantAuthEnabled()) credentials()
}

function authorization(row: Credential): TenantAuthorization {
    return { namespace: row.namespace, credentialId: row.id,
        credentialVersion: createHash('sha256').update(JSON.stringify([row.id, row.namespace, row.token, row.generation])).digest('hex') }
}

function ingressMatches(row: Credential, namespace: unknown, credential: unknown): boolean {
    return typeof namespace === 'string' && namespace === row.namespace &&
        (credential === undefined || credential === null || credential === '' || credential === row.id)
}

export function resolveTenantCredential(raw: unknown, expectedNamespace?: unknown, expectedCredential?: unknown): TenantAuthorization | null {
    if (typeof raw !== 'string' || raw.length > 1024) return null
    const parsed = parseAccessToken(raw)
    if (!parsed) return null
    if (!tenantAuthEnabled()) {
        return constantTimeEquals(parsed.baseToken, getConfiguration().cliApiToken) ? { namespace: parsed.namespace } : null
    }
    try {
        const row = credentials().find(item => constantTimeEquals(parsed.baseToken, item.token))
        if (!row || !row.enabled || !ingressMatches(row, expectedNamespace, expectedCredential)) return null
        if (raw.trim().includes(':') && parsed.namespace !== row.namespace) return null
        return authorization(row)
    } catch { return null }
}

export function tenantClaims(value?: TenantAuthorization): Record<string, string> {
    return value?.credentialId && value.credentialVersion ? { cid: value.credentialId, cver: value.credentialVersion } : {}
}

export function tenantJwtAuthorization(payload: Record<string, unknown>, expectedNamespace?: unknown, expectedCredential?: unknown): TenantAuthorization | null {
    if (!tenantAuthEnabled()) return typeof payload.ns === 'string' ? { namespace: payload.ns } : null
    try {
        const row = credentials().find(item => item.id === payload.cid)
        if (!row || !row.enabled || row.namespace !== payload.ns || !ingressMatches(row, expectedNamespace, expectedCredential)) return null
        const current = authorization(row)
        if (typeof payload.exp !== 'number' || payload.exp <= Date.now() / 1000) return null
        return typeof payload.cver === 'string' && constantTimeEquals(payload.cver, current.credentialVersion!) ? { ...current, expiresAt: payload.exp } : null
    } catch { return null }
}

export function tenantAuthorizationCurrent(value: TenantAuthorization): boolean {
    if (value.expiresAt !== undefined && value.expiresAt <= Date.now() / 1000) return false
    if (!tenantAuthEnabled()) return !value.credentialId
    try {
        const row = credentials().find(item => item.id === value.credentialId)
        return !!row?.enabled && row.namespace === value.namespace && authorization(row).credentialVersion === value.credentialVersion
    } catch { return false }
}

export function tenantRequestAllowed(method: string, path: string): boolean {
    if (!tenantAuthEnabled()) return true
    if (path === '/health' || path.startsWith('/socket.io/')) return true
    if (!path.startsWith('/api/') && !path.startsWith('/cli/')) return true
    if (path === '/api/auth') return method === 'POST' || method === 'OPTIONS'
    if (path === '/api/hub-settings') return method === 'GET' || method === 'OPTIONS'
    return ['/cli/', '/api/sessions', '/api/machines', '/api/events', '/api/visibility', '/api/usage', '/api/activity', '/api/work-graph']
        .some(prefix => path === prefix || path.startsWith(prefix.endsWith('/') ? prefix : prefix + '/'))
}
