import type { Socket } from 'socket.io'

export class RpcRegistry {
    private readonly methodToSocketId: Map<string, string> = new Map()
    private readonly socketIdToMethods: Map<string, Set<string>> = new Map()

    private key(method: string, namespace: string): string {
        return JSON.stringify([namespace, method])
    }

    register(socket: Socket, method: string): void {
        if (!method) return
        const key = this.key(method, socket.data?.namespace ?? 'default')
        this.methodToSocketId.set(key, socket.id)
        const existing = this.socketIdToMethods.get(socket.id)
        if (existing) existing.add(key)
        else this.socketIdToMethods.set(socket.id, new Set([key]))
    }

    unregister(socket: Socket, method: string): void {
        const key = this.key(method, socket.data?.namespace ?? 'default')
        if (this.methodToSocketId.get(key) === socket.id) this.methodToSocketId.delete(key)
        const methods = this.socketIdToMethods.get(socket.id)
        methods?.delete(key)
        if (methods?.size === 0) this.socketIdToMethods.delete(socket.id)
    }

    unregisterAll(socket: Socket): void {
        for (const key of this.socketIdToMethods.get(socket.id) ?? []) {
            if (this.methodToSocketId.get(key) === socket.id) this.methodToSocketId.delete(key)
        }
        this.socketIdToMethods.delete(socket.id)
    }

    getSocketIdForMethod(method: string, namespace = 'default'): string | null {
        return this.methodToSocketId.get(this.key(method, namespace)) ?? null
    }
}
