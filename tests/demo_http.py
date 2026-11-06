"""Servidores HTTP de demostración del comparador MEC/Cloud (solo localhost)."""

import argparse
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Lock, Thread
import time


HEALTH_PATH = '/api/iot/health'
VARIACION_MS = (0, 4, -3, 7, -5, 2, -1, 5, -2, 1)


def servidor(port, destino, demora_ms, fallo_cada):
    contador = 0
    lock = Lock()

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            nonlocal contador
            if self.path != HEALTH_PATH:
                self.send_error(404)
                return

            with lock:
                contador += 1
                intento = contador

            demora = max(0, demora_ms + VARIACION_MS[(intento - 1) % len(VARIACION_MS)])
            time.sleep(demora / 1000)
            fallo = fallo_cada > 0 and intento % fallo_cada == 0
            codigo = 503 if fallo else 200
            cuerpo = json.dumps({
                'status': 'error' if fallo else 'ok',
                'service': f'IoT {destino}',
                'origen': 'demostracion-local',
            }).encode('utf-8')
            try:
                self.send_response(codigo)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(cuerpo)))
                self.send_header('Connection', 'close')
                self.end_headers()
                self.wfile.write(cuerpo)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_request(self, code='-', size='-'):
            print(f'[DEMO {destino}] {self.command} {self.path} -> HTTP {code}', flush=True)

    return ThreadingHTTPServer(('127.0.0.1', port), HealthHandler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cloud-503-cada', type=int, default=0, metavar='N',
                        help='Devuelve HTTP 503 en cada N peticiones de Cloud. 0 desactiva los fallos.')
    args = parser.parse_args()
    if args.cloud_503_cada < 0:
        parser.error('--cloud-503-cada debe ser 0 o un entero positivo')

    try:
        with ExitStack() as stack:
            mec = stack.enter_context(servidor(18091, 'MEC', 25, 0))
            cloud = stack.enter_context(servidor(18092, 'Cloud', 125, args.cloud_503_cada))
            for server in (mec, cloud):
                hilo = Thread(target=server.serve_forever, daemon=True)
                hilo.start()
                stack.callback(hilo.join)
                stack.callback(server.shutdown)

            print('DEMO LOCAL | Demoras programadas | Sin equipos MEC/Cloud reales', flush=True)
            print(f'MEC:   http://127.0.0.1:18091{HEALTH_PATH}', flush=True)
            print(f'Cloud: http://127.0.0.1:18092{HEALTH_PATH}', flush=True)
            print('Mantén esta ventana abierta. Pulsa Ctrl+C al finalizar.', flush=True)
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        print('\nDemostración finalizada.')
    except OSError as exc:
        parser.exit(1, f'No se pudieron abrir los puertos locales 18091 y 18092. {exc}\n')


if __name__ == '__main__':
    main()
