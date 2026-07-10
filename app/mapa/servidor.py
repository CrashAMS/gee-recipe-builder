"""Mini servidor HTTP en 127.0.0.1 para servir el HTML/assets del mapa (DEC-F3b)."""
import http.server
import threading
from functools import partial
from pathlib import Path


class _Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # silenciar el log ruidoso por request
        pass


class ServidorMapa:
    def __init__(self, directorio: Path):
        handler = partial(_Handler, directory=str(directorio))
        # puerto 0 → el SO asigna uno libre (decisión #12)
        self._httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    @property
    def puerto(self) -> int:
        return self._httpd.server_address[1]

    def iniciar(self) -> None:
        self._thread.start()

    def detener(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
