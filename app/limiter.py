"""Protección contra fuerza bruta en el login (RN-48).

El contador es por ``(IP, email)`` y vive en memoria del proceso: alcanza para
un despliegue de una instancia y no agrega dependencias ni tablas. Si el
sistema escala a varias instancias, este estado debe moverse a Redis o a la
base (ver ``docs/dominio.md``).
"""

from __future__ import annotations

import math
import time
from collections import deque

MAX_INTENTOS = 5
VENTANA = 15 * 60
BLOQUEO = 15 * 60


class LimitadorLogin:
    """Cuenta fallos consecutivos y bloquea temporalmente el par IP/email."""

    def __init__(
        self,
        *,
        max_intentos: int = MAX_INTENTOS,
        ventana: float = VENTANA,
        bloqueo: float = BLOQUEO,
        reloj=None,
    ) -> None:
        if max_intentos < 1:
            raise ValueError("max_intentos debe ser al menos 1.")
        self.max_intentos = max_intentos
        self.ventana = float(ventana)
        self.bloqueo = float(bloqueo)
        self._reloj = reloj or time.monotonic
        self._fallos: dict[str, deque[float]] = {}
        self._bloqueos: dict[str, float] = {}

    @staticmethod
    def clave(ip: str | None, email: str | None) -> str:
        return f"{(ip or '').strip().lower()}|{(email or '').strip().lower()}"

    def segundos_bloqueado(self, ip: str | None, email: str | None) -> int:
        """Segundos que faltan para poder reintentar; 0 si no está bloqueado."""
        clave = self.clave(ip, email)
        hasta = self._bloqueos.get(clave)
        if hasta is None:
            return 0
        restante = hasta - self._reloj()
        if restante <= 0:
            self._bloqueos.pop(clave, None)
            self._fallos.pop(clave, None)
            return 0
        return max(1, math.ceil(restante))

    def registrar_fallo(self, ip: str | None, email: str | None) -> int:
        """Suma un fallo. Devuelve los segundos de bloqueo si se disparó."""
        clave = self.clave(ip, email)
        ahora = self._reloj()
        fallos = self._fallos.setdefault(clave, deque())
        while fallos and ahora - fallos[0] > self.ventana:
            fallos.popleft()
        fallos.append(ahora)
        if len(fallos) >= self.max_intentos:
            self._bloqueos[clave] = ahora + self.bloqueo
            fallos.clear()
            return max(1, math.ceil(self.bloqueo))
        return 0

    def registrar_exito(self, ip: str | None, email: str | None) -> None:
        clave = self.clave(ip, email)
        self._fallos.pop(clave, None)
        self._bloqueos.pop(clave, None)

    def limpiar(self) -> None:
        self._fallos.clear()
        self._bloqueos.clear()
