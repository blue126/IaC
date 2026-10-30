import { useEffect, useRef, useState, type ReactNode } from 'react'
import {
    fetchWorkspaceIdentity, workspaceKey, WorkspaceIdentityContext, WORKSPACE_INVALIDATED,
    WORKSPACE_MARKER, type WorkspaceIdentity,
} from '@/lib/workspace-auth'

type Props = {
    children: ReactNode
    reset: () => Promise<boolean>
    reload: () => void
}

export function WorkspaceGate({ children, reset, reload }: Props) {
    const [identity, setIdentity] = useState<WorkspaceIdentity | null>(null)
    const [error, setError] = useState(false)
    const [checking, setChecking] = useState(true)
    const currentKey = useRef<string | null>(null)
    useEffect(() => {
        let stopped = false
        let epoch = 0
        let controller: AbortController | null = null
        let switching = false
        let foregroundAllowed = document.visibilityState !== 'hidden'
        const hide = () => {
            epoch++
            controller?.abort()
            controller = null
            setChecking(true)
        }
        const check = async (foreground = false) => {
            if (stopped || switching || !foregroundAllowed || (controller && !foreground)) return
            if (foreground) hide()
            const requestEpoch = ++epoch
            controller = new AbortController()
            setError(false)
            try {
                const next = await fetchWorkspaceIdentity(controller.signal)
                if (stopped || epoch !== requestEpoch) return
                const key = workspaceKey(next)
                const stored = window.localStorage.getItem(WORKSPACE_MARKER)
                const previous = currentKey.current ?? stored
                if (previous !== key) {
                    switching = true
                    setIdentity(null)
                    const needsReload = await reset()
                    if (stopped || epoch !== requestEpoch) return
                    window.localStorage.setItem(WORKSPACE_MARKER, key)
                    if (previous !== null || needsReload) {
                        // A full document navigation discards module-level message
                        // caches and all old terminal/SSE connections before new auth.
                        reload()
                        return
                    }
                    switching = false
                }
                currentKey.current = key
                setChecking(false)
                setIdentity(previousIdentity => previousIdentity && workspaceKey(previousIdentity) === key
                    ? previousIdentity
                    : { workspace_id: next.workspace_id, generation: next.generation, identity: next.identity })
            } catch {
                if (!stopped && epoch === requestEpoch) {
                    setIdentity(null)
                    setError(true)
                    setChecking(false)
                }
            } finally {
                if (epoch === requestEpoch) controller = null
                else switching = false
            }
        }
        const foreground = () => { foregroundAllowed = true; void check(true) }
        const background = () => { foregroundAllowed = false; hide() }
        const visibility = () => {
            if (document.visibilityState === 'hidden') background()
            else foreground()
        }
        const invalidated = () => { hide(); setIdentity(null); setChecking(false); setError(true) }
        const storage = () => { void check(true) }
        window.addEventListener('focus', foreground)
        window.addEventListener('blur', background)
        window.addEventListener('pageshow', foreground)
        window.addEventListener('storage', storage)
        window.addEventListener(WORKSPACE_INVALIDATED, invalidated)
        document.addEventListener('visibilitychange', visibility)
        const timer = window.setInterval(() => { void check() }, 15_000)
        void check()
        return () => {
            stopped = true
            epoch++
            controller?.abort()
            window.clearInterval(timer)
            window.removeEventListener('focus', foreground)
            window.removeEventListener('blur', background)
            window.removeEventListener('pageshow', foreground)
            window.removeEventListener('storage', storage)
            window.removeEventListener(WORKSPACE_INVALIDATED, invalidated)
            document.removeEventListener('visibilitychange', visibility)
        }
    }, [reset, reload])

    return <>
        {(!identity || checking) && <div role="status" className="h-full flex flex-col items-center justify-center gap-4 p-4">
            <p>{error ? '无法确认工作区身份，请刷新入口重新验证或联系管理员。' : '正在进入你的工作区…'}</p>
            {error && <button type="button" onClick={reload}>重新验证入口</button>}
        </div>}
        {identity && <div className="h-full" hidden={checking}>
            <div className="h-full flex flex-col">
                <nav aria-label="工作区导航" className="shrink-0 border-b px-3 py-1 text-sm text-right">
                    <a href="/_workspace/login/">Claude 登录</a>
                </nav>
                <div className="min-h-0 flex-1">
                    <WorkspaceIdentityContext.Provider value={identity}>{children}</WorkspaceIdentityContext.Provider>
                </div>
            </div>
        </div>}
    </>
}
