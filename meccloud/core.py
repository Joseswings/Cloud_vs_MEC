from __future__ import annotations

import csv
import http.client
import json
import math
import queue
import socket
import statistics
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from urllib.parse import urlsplit

FIELDS = ('session_id', 'condicion', 'ronda', 'destino', 'url', 'inicio_utc',
          'http_status', 'resultado', 'duracion_ms', 'detalle_error')
DEFAULT_URLS = {'MEC': 'http://192.168.88.252:8090/api/iot/health',
                'Cloud': 'http://192.168.88.250:8090/api/iot/health'}


@dataclass(frozen=True)
class Sample:
    session_id: str
    condicion: str
    ronda: int
    destino: str
    url: str
    inicio_utc: str
    http_status: int | None
    resultado: str
    duracion_ms: float | None
    detalle_error: str


def validate_url(url):
    p = urlsplit(url)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password or p.fragment:
        raise ValueError('Use una URL http(s) sin credenciales ni fragmento.')
    _ = p.port
    return p


def summary(samples):
    values = sorted(s.duracion_ms for s in samples
                    if s.resultado == 'correcto' and s.duracion_ms is not None)
    n = len(values)
    return {'muestras': len(samples), 'correctas': n, 'fallidas': len(samples) - n,
            'mediana': statistics.median(values) if n else None,
            'p95': values[math.ceil(.95 * n) - 1] if n else None,
            'minimo': values[0] if n else None, 'maximo': values[-1] if n else None}


def measure(session_id, condition, round_no, destination, url, timeout, suspended=None):
    p = validate_url(url)
    cls = http.client.HTTPSConnection if p.scheme == 'https' else http.client.HTTPConnection
    conn = cls(p.hostname, p.port, timeout=timeout)
    expired = threading.Event()
    active_socket = [None]

    def expire():
        expired.set()
        sock = active_socket[0] or conn.sock
        if sock:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
    timer = threading.Timer(timeout, expire)
    timer.daemon = True
    status, result, error = None, 'error_conexion', ''
    start_utc = datetime.now(timezone.utc).isoformat(timespec='milliseconds')
    start = time.perf_counter_ns()
    timer.start()
    try:
        # Explicit new connection. http.client never consults system proxies.
        conn.connect()
        active_socket[0] = conn.sock
        if expired.is_set():
            raise TimeoutError('Se agotó el timeout del intento.')
        path = p.path or '/'
        if p.query:
            path += '?' + p.query
        conn.request('GET', path, headers={'Connection': 'close', 'Accept': 'application/json'})
        response = conn.getresponse()
        status = response.status
        # Keep socket attached until full body read so the deadline can interrupt it.
        body_parts = []
        while True:
            chunk = response.read1(65536)
            if not chunk:
                break
            body_parts.append(chunk)
        body = b''.join(body_parts)
        end = time.perf_counter_ns()
        if response.length not in (None, 0):
            raise http.client.IncompleteRead(body, response.length)
        if expired.is_set():
            raise TimeoutError('Se agotó el timeout del intento.')
        if status != 200:
            result, error = 'http_error', f'HTTP {status} {response.reason}'
        else:
            try:
                payload = json.loads(body)
            except (ValueError, UnicodeError) as exc:
                result, error = 'json_invalido', str(exc)
            else:
                expected = 'IoT ' + destination
                if isinstance(payload, dict) and payload.get('status') == 'ok' and payload.get('service') == expected:
                    result = 'correcto'
                else:
                    result, error = 'respuesta_incorrecta', f'Se esperaba status="ok" y service="{expected}".'
    except (socket.timeout, TimeoutError) as exc:
        end = time.perf_counter_ns()
        result, error = 'timeout', str(exc) or 'Timeout'
    except (OSError, http.client.HTTPException, ValueError) as exc:
        end = time.perf_counter_ns()
        result = 'timeout' if expired.is_set() else 'error_conexion'
        error = f'{type(exc).__name__}: {exc}'
    finally:
        timer.cancel()
        conn.close()
    duration = (end - start) / 1_000_000
    if suspended is not None and suspended.is_set():
        result, duration, error = 'suspension', None, 'Intento atravesado por suspensión de Windows; tiempo descartado.'
    return Sample(session_id, condition, round_no, destination, url, start_utc,
                  status, result, duration, error)


def export_csv(path, samples, overwrite=False):
    # Exclusive creation prevents silent overwrite, including races after the dialog.
    with open(path, 'w' if overwrite else 'x', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for s in samples:
            row = asdict(s)
            row['duracion_ms'] = '' if s.duracion_ms is None else format(s.duracion_ms, '.6f')
            writer.writerow(row)


class Runner:
    """One sequential worker: no overlapping requests, including across restarts."""
    def __init__(self, session_id, condition, urls, interval, limit, timeout,
                 out: queue.Queue, round_start=0, counts=None):
        self.session_id, self.condition, self.urls = session_id, condition, dict(urls)
        self.interval, self.limit, self.timeout, self.out = interval, limit, timeout, out
        self.round_no = round_start
        self.counts = dict(counts or {'MEC': 0, 'Cloud': 0})
        self.stop = threading.Event()
        self.suspended = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self):
        try:
            while not self.stop.is_set() and any(v < self.limit for v in self.counts.values()):
                started = time.perf_counter()
                self.round_no += 1
                order = ('MEC', 'Cloud') if self.round_no % 2 else ('Cloud', 'MEC')
                for dest in order:
                    if self.stop.is_set():
                        break
                    if self.counts[dest] >= self.limit:
                        continue
                    self.counts[dest] += 1
                    sample = measure(self.session_id, self.condition, self.round_no,
                                     dest, self.urls[dest], self.timeout, self.suspended)
                    self.out.put(('sample', self, sample))
                self.stop.wait(max(0, self.interval - (time.perf_counter() - started)))
        except Exception as exc:
            self.out.put(('error', self, str(exc)))
        finally:
            self.out.put(('done', self, None))
