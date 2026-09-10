#!/usr/bin/env python3
"""
Önizleme sunucusu — SPA fallback ile.

Sitede 99 sayfa gerçek HTML dosyası olarak duruyor ve doğrudan servis
ediliyor. Geri kalan yollar (/admin, /client, tanımsız adresler) dosya
olarak yok; bunların uygulamaya devredilmesi için sunucunun /index.html
döndürmesi gerekiyor.

Basit `python3 -m http.server` bunu yapmaz ve o adreslerde kendi düz
404'ünü gösterir. Yayına alırken host panelinde açmanız gereken ayar da
tam olarak budur ("SPA fallback" / "rewrite to index.html").

Çalıştırma:  python3 onizleme-sunucu.py
Adres:       http://localhost:4173
"""
import http.server
import os
import socketserver
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4173
ROOT = os.path.dirname(os.path.abspath(__file__))


class SpaHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def do_GET(self):
        path = self.translate_path(self.path)

        # Dosya ya da dizin indeksi varsa normal servis et.
        if os.path.isdir(path) and os.path.exists(os.path.join(path, "index.html")):
            return super().do_GET()
        if os.path.isfile(path):
            return super().do_GET()

        # Varlık uzantılı istekler gerçekten 404 dönmeli; yoksa eksik bir
        # görsel sessizce HTML olarak servis edilir ve hata gizlenir.
        _, ext = os.path.splitext(self.path.split("?")[0])
        if ext and ext.lower() not in (".html", ".htm"):
            return super().do_GET()

        # Geri kalan her yol uygulamaya devredilir.
        self.path = "/index.html"
        return super().do_GET()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", PORT), SpaHandler) as httpd:
        print(f"Önizleme hazır:  http://localhost:{PORT}")
        print("Durdurmak için Ctrl+C")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nkapatıldı")
