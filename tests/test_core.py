import csv
import dataclasses
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import queue
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from meccloud.core import Sample, Runner, export_csv, measure, summary, validate_url


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    peers = []

    def log_message(self, *args):
        pass

    def do_GET(self):
        self.peers.append(self.client_address)
        if self.path == '/disconnect':
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            return
        if self.path == '/timeout':
            time.sleep(.35)
        status = 503 if self.path == '/http-error' else 200
        body = {
            '/invalid': b'{broken',
            '/identity': b'{"status":"ok","service":"IoT Cloud"}',
            '/status': b'{"status":"down","service":"IoT MEC"}',
            '/array': b'[]',
        }.get(self.path, b'{"status":"ok","service":"IoT MEC"}')
        self.send_response(status)
        self.send_header('Content-Length', str(len(body) + (10 if self.path == '/truncated' else 0)))
        self.send_header('Connection', 'close')
        self.end_headers()
        try:
            if self.path == '/slowbody':
                self.wfile.write(body[:5])
                self.wfile.flush()
                time.sleep(.12)
                self.wfile.write(body[5:])
            elif self.path == '/dribble':
                for byte in body:
                    self.wfile.write(bytes([byte]))
                    self.wfile.flush()
                    time.sleep(.025)
            else:
                self.wfile.write(body)
        except (OSError, ConnectionError):
            pass


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def get(self, path='/', timeout=1, suspended=None):
        return measure('test', 'Base · serie 1', 1, 'MEC', self.url+path, timeout, suspended)

    def test_correct(self):
        s = self.get()
        self.assertEqual((s.http_status, s.resultado), (200, 'correcto'))
        self.assertGreater(s.duracion_ms, 0)
        self.assertTrue(s.inicio_utc.endswith('+00:00'))

    def test_validation_failures(self):
        for path, result in [('/invalid', 'json_invalido'), ('/identity', 'respuesta_incorrecta'),
                             ('/status', 'respuesta_incorrecta'), ('/array', 'respuesta_incorrecta'),
                             ('/http-error', 'http_error'), ('/disconnect', 'error_conexion'),
                             ('/truncated', 'error_conexion')]:
            with self.subTest(path=path):
                s = self.get(path)
                self.assertEqual(s.resultado, result)
                self.assertTrue(s.detalle_error)
                self.assertGreater(s.duracion_ms, 0)

    def test_timeout(self):
        s = self.get('/timeout', .07)
        self.assertEqual(s.resultado, 'timeout')
        self.assertLess(s.duracion_ms, 300)

    def test_total_deadline_for_trickling_body(self):
        s = self.get('/dribble', .12)
        self.assertEqual(s.resultado, 'timeout')
        self.assertLess(s.duracion_ms, 350)

    def test_reads_complete_body(self):
        s = self.get('/slowbody')
        self.assertEqual(s.resultado, 'correcto')
        self.assertGreaterEqual(s.duracion_ms, 100)

    def test_new_connections_and_no_proxy(self):
        before = len(Handler.peers)
        with patch.dict(os.environ, {'HTTP_PROXY': 'http://127.0.0.1:1', 'http_proxy': 'http://127.0.0.1:1', 'NO_PROXY': ''}):
            self.assertEqual(self.get().resultado, 'correcto')
            self.assertEqual(self.get().resultado, 'correcto')
        peers = Handler.peers[before:]
        self.assertEqual(len(peers), 2)
        self.assertNotEqual(peers[0], peers[1])

    def test_refused_connection(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            # Bound but not listening: port cannot be taken by another test server.
            s = measure('x', 'Base', 1, 'MEC', f'http://127.0.0.1:{sock.getsockname()[1]}', 3)
        self.assertEqual(s.resultado, 'error_conexion')

    def test_suspend_discards_duration(self):
        event = threading.Event()
        timer = threading.Timer(.04, event.set)
        timer.start()
        s = self.get('/slowbody', suspended=event)
        timer.join()
        self.assertEqual(s.resultado, 'suspension')
        self.assertIsNone(s.duracion_ms)


def sample(value, result='correcto'):
    return Sample('session', 'Base · serie 1', 1, 'MEC', 'http://localhost/',
                  '2026-01-01T00:00:00+00:00', 200, result, value, '')


class StatisticsTests(unittest.TestCase):
    def test_empty(self):
        st = summary([])
        self.assertIsNone(st['mediana'])
        self.assertIsNone(st['p95'])

    def test_even_median_and_nearest_rank(self):
        st = summary([sample(x) for x in range(1, 21)])
        self.assertEqual(st['mediana'], 10.5)
        self.assertEqual(st['p95'], 19)
        self.assertEqual((st['minimo'], st['maximo']), (1, 20))

    def test_odd_median_and_single(self):
        self.assertEqual(summary([sample(9), sample(1), sample(2)])['mediana'], 2)
        self.assertEqual(summary([sample(7)])['p95'], 7)

    def test_failures_are_not_zero(self):
        st = summary([sample(10), sample(10000, 'timeout'), sample(None, 'suspension')])
        self.assertEqual((st['muestras'], st['correctas'], st['fallidas']), (3, 1, 2))
        self.assertEqual(st['mediana'], 10)
        self.assertIsNone(summary([sample(1, 'timeout')])['p95'])

    def test_export_numeric_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.csv'
            export_csv(path, [sample(1.25), sample(200.5, 'timeout'), sample(None, 'suspension')])
            with path.open(encoding='utf-8-sig', newline='') as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(rows[0]['duracion_ms'], '1.250000')
            self.assertEqual(rows[1]['resultado'], 'timeout')
            self.assertEqual(rows[2]['duracion_ms'], '')
            with self.assertRaises(FileExistsError):
                export_csv(path, [])

    def test_invalid_urls(self):
        for url in ('ftp://host', 'http://', 'http://a:bad', 'http://u:p@host', 'http://a/#fragment'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_url(url)


class RunnerTests(unittest.TestCase):
    def test_order_limits_and_no_overlap(self):
        calls = []
        def fake(sid, condition, round_no, dest, *args):
            calls.append((round_no, dest))
            return dataclasses.replace(sample(1), destino=dest, ronda=round_no)
        out = queue.Queue()
        runner = Runner('s', 'Base', {'MEC': 'http://x', 'Cloud': 'http://y'}, .001, 3, 1, out)
        with patch('meccloud.core.measure', side_effect=fake):
            runner.thread.start()
            runner.thread.join(2)
        self.assertFalse(runner.thread.is_alive())
        self.assertEqual(calls, [(1, 'MEC'), (1, 'Cloud'), (2, 'Cloud'), (2, 'MEC'), (3, 'MEC'), (3, 'Cloud')])

    def test_stop_allows_only_inflight(self):
        entered, release = threading.Event(), threading.Event()
        out = queue.Queue()
        calls = []
        def fake(*args):
            calls.append(args[3])
            entered.set()
            release.wait(1)
            return sample(2)
        runner = Runner('s', 'Base', {'MEC': 'http://x', 'Cloud': 'http://y'}, .001, 100, 1, out)
        with patch('meccloud.core.measure', side_effect=fake):
            runner.thread.start()
            self.assertTrue(entered.wait(1))
            runner.stop.set()
            release.set()
            runner.thread.join(2)
        self.assertEqual(calls, ['MEC'])
        self.assertEqual(out.get_nowait()[0], 'sample')
        self.assertEqual(out.get_nowait()[0], 'done')

    def test_failure_does_not_stop_other_destination(self):
        out = queue.Queue()
        runner = Runner('s', 'Base', {'MEC': 'http://x', 'Cloud': 'http://y'}, .001, 1, 1, out)
        with patch('meccloud.core.measure', return_value=sample(5, 'timeout')) as fn:
            runner.thread.start()
            runner.thread.join(2)
        self.assertEqual(fn.call_count, 2)


if __name__ == '__main__':
    unittest.main()
