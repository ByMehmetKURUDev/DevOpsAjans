"""Bellek içi hız sınırı (anahtar başına kayan pencere).

İlk kez imzalı işlem bağlantılarında (`routers/imzali_islemler.py`) yazıldı;
Faz 2D'de giriş uçları (`/auth/login`, `/auth/callback`,
`/auth/token/exchange`) da kullanınca buraya taşındı.

Tek süreçli ücretsiz sunucu için yeterli: sayaç süreç belleğinde, sunucu
uyuyup kalkınca sıfırlanıyor. Anahtar genellikle IP'nin tuzlu özeti
(`utils.istemci_ip.ip_ozeti`) — ham IP bellekte bile tutulmuyor.
"""

import threading
import time
from collections import deque
from typing import Deque, Dict


class HizSiniri:
    """`pencere` saniye içinde anahtar başına en çok `sinir` istek."""

    def __init__(self, sinir: int, pencere: float = 60.0):
        self.sinir = sinir
        self.pencere = pencere
        self._kayitlar: Dict[str, Deque[float]] = {}
        self._kilit = threading.Lock()

    def izin_var_mi(self, anahtar: str) -> bool:
        simdi = time.monotonic()
        with self._kilit:
            kuyruk = self._kayitlar.setdefault(anahtar, deque())
            while kuyruk and simdi - kuyruk[0] > self.pencere:
                kuyruk.popleft()
            if len(kuyruk) >= self.sinir:
                return False
            kuyruk.append(simdi)
            # Bellek büyümesin: çok anahtar birikince boşları at.
            if len(self._kayitlar) > 5000:
                for k in [k for k, v in self._kayitlar.items() if not v]:
                    self._kayitlar.pop(k, None)
            return True

    def temizle(self) -> None:
        with self._kilit:
            self._kayitlar.clear()
