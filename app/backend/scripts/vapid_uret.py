"""Web Push için yeni bir VAPID anahtar çifti üretir.

Kullanım:
    python scripts/vapid_uret.py /yol/vapid.env

Anahtarlar EKRANA YAZILMAZ (terminal geçmişine, ekran paylaşımına ya da
günlüklere düşmesin diye); verilen dosyaya `AD=değer` satırları olarak
yazılır, dosya yalnız sahibinin okuyabileceği izinle (600) oluşturulur.
Dosya zaten varsa üzerine yazılmaz.

Sonra:
  1. Dosyadaki üç satırı Render › Environment'a ekleyin
     (VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_SUBJECT).
  2. Dosyayı silin.

Anahtar çifti değişirse mevcut tarayıcı abonelikleri geçersiz olur;
kullanıcıların panelden bildirimleri yeniden açması gerekir.
"""

import base64
import os
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64(veri: bytes) -> str:
    return base64.urlsafe_b64encode(veri).rstrip(b"=").decode("ascii")


def anahtar_cifti_uret() -> tuple[str, str]:
    """(açık, gizli) — ikisi de base64url, dolgusuz.

    Açık anahtar P-256 sıkıştırılmamış nokta (65 bayt): tarayıcıdaki
    `applicationServerKey`. Gizli anahtar 32 baytlık ham skaler: pywebpush
    bunu doğrudan kabul ediyor.
    """
    gizli = ec.generate_private_key(ec.SECP256R1())
    ham_gizli = gizli.private_numbers().private_value.to_bytes(32, "big")
    ham_acik = gizli.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return _b64(ham_acik), _b64(ham_gizli)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Kullanım: python scripts/vapid_uret.py /yol/vapid.env", file=sys.stderr)
        return 2
    hedef = argv[1]
    if os.path.exists(hedef):
        print(f"{hedef} zaten var; üzerine yazılmadı.", file=sys.stderr)
        return 1

    acik, gizli = anahtar_cifti_uret()
    konu = os.environ.get("VAPID_SUBJECT") or "mailto:by@mehmetkuru.dev"
    icerik = (
        "# Web Push (VAPID) — Render › Environment'a girin, sonra bu dosyayı silin.\n"
        f"VAPID_PUBLIC_KEY={acik}\n"
        f"VAPID_PRIVATE_KEY={gizli}\n"
        f"VAPID_SUBJECT={konu}\n"
    )
    tanitici = os.open(hedef, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(tanitici, "w", encoding="utf-8") as dosya:
        dosya.write(icerik)
    print(f"VAPID anahtar çifti {hedef} dosyasına yazıldı (izin 600).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
