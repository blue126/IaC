#!/usr/bin/env python3
"""Relay fixed Unix HTTP streams under signed, revocable workspace leases.

Nginx handles HTTP framing and TLS on both sides. This relay removes one private
lease header and moves bounded bytes between fixed local Unix endpoints only.
"""
import os
from pathlib import Path
import select
import socket
import socketserver
import threading


class StreamHandler(socketserver.BaseRequestHandler):
    def handle(self):
        upstream = None
        pair = None
        try:
            self.request.settimeout(5)
            header = b''
            while b'\r\n\r\n' not in header:
                chunk = self.request.recv(4096)
                if not chunk:
                    return
                header += chunk
                if len(header) > 65536:
                    return
            block, remainder = header.split(b'\r\n\r\n', 1)
            lines = block.split(b'\r\n')
            lease, forwarded = [], [lines[0]]
            for line in lines[1:]:
                if line[:1] in (b' ', b'\t') or b':' not in line:
                    return
                name, value = line.split(b':', 1)
                if name.lower() == b'x-hapi-stream-lease':
                    lease.append(value.strip().decode('ascii'))
                elif name.lower() != b'x-hapi-expected-route':
                    forwarded.append(line)
            if len(lease) != 1:
                return
            record = self.server.manager.policy.read_lease(lease[0], self.server.workspace)
            upstream = socket.socket(socket.AF_UNIX)
            upstream.settimeout(5)
            upstream.connect(str(self.server.manager.bridges / (self.server.workspace + '.sock')))
            pair = self.server.manager.attach(record, self.request, upstream)
            # Check the current allocation again after opening the fixed bridge.
            self.server.manager.policy.check_lease(record)
            forwarded.append(b'X-Hapi-Expected-Route: ' + record['route'].encode())
            upstream.sendall(b'\r\n'.join(forwarded) + b'\r\n\r\n' + remainder)
            self.request.setblocking(False)
            upstream.setblocking(False)
            pending = {self.request: bytearray(), upstream: bytearray()}
            closing = False
            while not pair['closed'].is_set():
                if closing and not any(pending.values()):
                    return
                readers = [] if closing else [peer for peer, other in [(self.request, upstream), (upstream, self.request)]
                           if len(pending[other]) < 1048576]
                writers = [peer for peer in pending if pending[peer]]
                ready, writable, _ = select.select(readers, writers, [], .25)
                for peer in writable:
                    try:
                        count = peer.send(pending[peer])
                        if count == 0:
                            return
                        del pending[peer][:count]
                    except BlockingIOError:
                        pass
                for peer in ready:
                    try:
                        data = peer.recv(65536)
                    except BlockingIOError:
                        continue
                    if not data:
                        closing = True
                        continue
                    other = upstream if peer is self.request else self.request
                    pending[other].extend(data)
        except Exception:
            # Deliberately do not print request bodies, OAuth codes or lease data.
            return
        finally:
            if pair is not None:
                self.server.manager.detach(pair)
            if upstream is not None:
                upstream.close()


class StreamServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    block_on_close = False

    def handle_error(self, request, client_address):
        pass


class StreamManager:
    def __init__(self, policy, sockets, bridges, interval=.25):
        self.policy, self.sockets, self.bridges = policy, Path(sockets), Path(bridges)
        self.interval = interval
        self.lock = threading.Lock()
        self.active = []
        self.servers = {}
        self.stopped = threading.Event()
        self.worker = None

    def attach(self, record, client, upstream):
        pair = {'record': record, 'client': client, 'upstream': upstream, 'closed': threading.Event()}
        with self.lock:
            if self.stopped.is_set():
                raise ValueError('Stream guard is stopping')
            self.active.append(pair)
        return pair

    def detach(self, pair):
        with self.lock:
            if pair in self.active:
                self.active.remove(pair)
        self.cut(pair)

    @staticmethod
    def cut(pair):
        pair['closed'].set()
        for name in ['client', 'upstream']:
            try:
                pair[name].shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def reconcile(self):
        config = self.policy.current_config()
        for route in config['routes']:
            wid = route['workspace_id']
            if wid not in self.servers:
                path = self.sockets / (wid + '.sock')
                if path.exists():
                    raise ValueError('Refuse to replace an unknown route socket')
                server = StreamServer(str(path), StreamHandler)
                server.manager, server.workspace = self, wid
                os.chmod(path, 0o660)
                self.servers[wid] = server
                threading.Thread(target=server.serve_forever, daemon=True).start()
        with self.lock:
            active = list(self.active)
        for pair in active:
            try:
                self.policy.check_lease(pair['record'], config)
            except Exception:
                self.cut(pair)

    def watch(self):
        while not self.stopped.wait(self.interval):
            try:
                self.reconcile()
            except Exception:
                # A missing, corrupt or conflicting registry must close existing streams.
                with self.lock:
                    active = list(self.active)
                for pair in active:
                    self.cut(pair)

    def start(self):
        self.sockets.mkdir(mode=0o750, parents=True, exist_ok=True)
        os.chmod(self.sockets, 0o750)  # The daemon umask must not hide routes from the proxy group.
        self.reconcile()
        self.worker = threading.Thread(target=self.watch, daemon=True)
        self.worker.start()

    def close(self):
        self.stopped.set()
        if self.worker:
            self.worker.join(timeout=2)
        with self.lock:
            active = list(self.active)
        for pair in active:
            self.cut(pair)
        for wid, server in self.servers.items():
            server.shutdown()
            server.server_close()
            (self.sockets / (wid + '.sock')).unlink(missing_ok=True)
