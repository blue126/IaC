import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { StrictMode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
const h = vi.hoisted(() => ({ fetchIdentity: vi.fn() }))
vi.mock('@/lib/workspace-auth', async importOriginal => ({
    ...await importOriginal<typeof import('@/lib/workspace-auth')>(), fetchWorkspaceIdentity: h.fetchIdentity,
}))
import { WorkspaceGate } from './WorkspaceGate'
import { WORKSPACE_MARKER, WORKSPACE_INVALIDATED, workspaceKey } from '@/lib/workspace-auth'
const alice = { workspace_id: 'alice', generation: 1, identity: 'a'.repeat(64), csrf: 'c'.repeat(64) }
const bob = { ...alice, workspace_id: 'bob', identity: 'b'.repeat(64) }
let tick: () => void
beforeEach(() => {
    localStorage.clear(); sessionStorage.clear()
    h.fetchIdentity.mockReset().mockResolvedValue(alice)
    const intervals = vi.spyOn(window, 'setInterval')
    tick = () => {
        const call = [...intervals.mock.calls].reverse().find(([, delay]) => delay === 15_000)
        if (typeof call?.[0] !== 'function') throw new Error('Identity timer not registered')
        call[0]()
    }
})
afterEach(() => { cleanup(); vi.restoreAllMocks() })
function mount(initial = true) {
    if (initial) localStorage.setItem(WORKSPACE_MARKER, workspaceKey(alice))
    const reset = vi.fn(async () => { localStorage.clear(); return false })
    const reload = vi.fn()
    render(<WorkspaceGate reset={reset} reload={reload}><div>private work area</div></WorkspaceGate>)
    return { reset, reload }
}

describe('workspace identity gate', () => {
    it('keeps the app hidden until identity is confirmed and clears old state on first use', async () => {
        let resolve!: (value: typeof alice) => void
        h.fetchIdentity.mockReturnValueOnce(new Promise(done => { resolve = done }))
        const { reset, reload } = mount(false)
        expect(screen.queryByText('private work area')).not.toBeInTheDocument()
        await act(async () => resolve(alice))
        expect(await screen.findByText('private work area')).toBeInTheDocument()
        expect(reset).toHaveBeenCalledTimes(1); expect(reload).not.toHaveBeenCalled()
    })
    it('does not reset or remount the app for unchanged periodic identity checks', async () => {
        const { reset, reload } = mount()
        const element = await screen.findByText('private work area')
        await act(async () => tick())
        expect(screen.getByText('private work area')).toBe(element)
        expect(reset).not.toHaveBeenCalled(); expect(reload).not.toHaveBeenCalled()
    })
    it('keeps the same application mounted when focus returns to the same identity', async () => {
        const { reset, reload } = mount()
        const element = await screen.findByText('private work area')
        fireEvent.blur(window)
        expect(element).not.toBeVisible()
        fireEvent.focus(window)
        await waitFor(() => expect(element).toBeVisible())
        expect(screen.getByText('private work area')).toBe(element)
        expect(reset).not.toHaveBeenCalled(); expect(reload).not.toHaveBeenCalled()
    })
    it('hides on blur and clears state before navigating after an account change', async () => {
        const { reset, reload } = mount()
        await screen.findByText('private work area')
        localStorage.setItem('private-old-cache', 'alice')
        fireEvent.blur(window)
        expect(screen.getByText('private work area')).not.toBeVisible()
        h.fetchIdentity.mockResolvedValueOnce(bob)
        fireEvent.focus(window)
        await waitFor(() => expect(reload).toHaveBeenCalledTimes(1))
        expect(reset).toHaveBeenCalledTimes(1)
        expect(localStorage.getItem('private-old-cache')).toBeNull()
        expect(localStorage.getItem(WORKSPACE_MARKER)).toBe(workspaceKey(bob))
        expect(screen.queryByText('private work area')).not.toBeInTheDocument()
    })
    it('requires a clean navigation for a route generation change', async () => {
        const { reload } = mount()
        await screen.findByText('private work area')
        h.fetchIdentity.mockResolvedValueOnce({ ...alice, generation: 2 })
        await act(async () => tick())
        expect(reload).toHaveBeenCalledTimes(1)
        expect(screen.queryByText('private work area')).not.toBeInTheDocument()
    })
    it('never shows a token input when Access expires or a workspace is denied', async () => {
        h.fetchIdentity.mockRejectedValueOnce(new Error('SECRET_SENTINEL'))
        const { reload } = mount()
        const button = await screen.findByRole('button', { name: '重新验证入口' })
        expect(screen.queryByText('private work area')).not.toBeInTheDocument()
        expect(document.querySelector('input')).toBeNull()
        expect(document.body.textContent).not.toContain('SECRET_SENTINEL')
        fireEvent.click(button); expect(reload).toHaveBeenCalledTimes(1)
    })
    it('discards a late old-identity response after focus revalidation', async () => {
        let resolve!: (value: typeof alice) => void
        h.fetchIdentity.mockReturnValueOnce(new Promise(done => { resolve = done })).mockResolvedValueOnce(bob)
        const { reload } = mount()
        fireEvent.blur(window); fireEvent.focus(window)
        await waitFor(() => expect(reload).toHaveBeenCalledTimes(1))
        await act(async () => resolve(alice))
        expect(screen.queryByText('private work area')).not.toBeInTheDocument()
    })
    it('removes the old app on a failed ticket refresh', async () => {
        mount(); await screen.findByText('private work area')
        fireEvent(window, new Event(WORKSPACE_INVALIDATED))
        expect(screen.queryByText('private work area')).not.toBeInTheDocument()
        expect(screen.getByRole('button', { name: '重新验证入口' })).toBeInTheDocument()
    })
    it('is safe under React StrictMode setup and cleanup', async () => {
        const reset = vi.fn(async () => false), reload = vi.fn()
        render(<StrictMode><WorkspaceGate reset={reset} reload={reload}><div>private work area</div></WorkspaceGate></StrictMode>)
        await screen.findByText('private work area')
        expect(reset).toHaveBeenCalledTimes(1); expect(reload).not.toHaveBeenCalled()
    })
})
