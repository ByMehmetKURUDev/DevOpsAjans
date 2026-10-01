"""Bağlantı jetonlarını şifreleyen Fernet anahtarını üretir (Faz 3B).

Kullanım (yalnız kendi bilgisayarınızda):
    python scripts/baglanti_anahtari_uret.py

Anahtar yalnız EKRANA basılır; hiçbir dosyaya, günlüğe ya da veritabanına
yazılmaz. Satırı kopyalayıp Render › mehmetkuru-api › Environment'a
`BAGLANTI_SIFRE_ANAHTARI` olarak ekleyin, sonra terminali kapatın.

Bu anahtar değişirse kayıtlı Google bağlantısının yenileme jetonu okunamaz;
panelden "Yeniden bağlan" demeniz gerekir (veri kaybı yok).
"""

import sys

from cryptography.fernet import Fernet


def anahtar_uret() -> str:
    """32 baytlık rastgele anahtar, Fernet'in beklediği base64url biçiminde (44 karakter)."""
    return Fernet.generate_key().decode("ascii")


def main() -> int:
    print("# Render › Environment'a ekleyin; bu satırı başka yere kaydetmeyin.")
    print(f"BAGLANTI_SIFRE_ANAHTARI={anahtar_uret()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
