"""Faz 2E — müşteri uçlarının TEK ortak yardımcısı: etkin hesap + kişi + izin.

Bütün müşteri uçları müşterinin e-postasını buradan alıyor:

* `musteri_baglami(request)` → `HesapBaglami(kisi_email, hesap_email, rol, izinler)`
* `musteri_eposta(request)` → `hesap_email` (kayıtların sahiplik alanı)
* `kisi_eposta(request)` → jetondaki kişi (yazar, oy, okundu, tercih…)
* `izin_iste(request, "faturalar")` → izin yoksa 403 `hesap_izni_yok`
* `izin_gerekli("faturalar", ...)` → router/uç bağımlılığı (izinlerden biri yeterli)

Kural
-----
* Başlık yok ya da kişinin kendi e-postası → kendi hesabı, tam yetki
  (rol `sahip`). Başlıksız istek bugünkü davranışın aynısı.
* `X-MK-Hesap: <hesap>` ve kişi o hesapta AKTİF üye → etkin hesap o; rol ve
  izinler üyelikten (karar ara katmanda: `middlewares/hesap_baglami.py`).
* Üye değilse (pasif, silinmiş, davet bekliyor, hiç yok) → 403
  `hesap_uyesi_degil`. Sessizce kişinin kendi hesabına düşülmüyor.
* Yönetici (role=admin) için başlık yok sayılıyor.

Yazma işlemlerinde kayıt sahibi `hesap_email`, "kim yazdı" bilgisi
`kisi_email` (talep mesajı yazarı, yorum, oy…) — ekipte kimin ne yaptığı görünsün.
"""

from typing import Optional

from dependencies.kayit_sahipligi import _yonetici_mi
from fastapi import HTTPException, Request, status
from middlewares.hesap_baglami import KAPSAM_ANAHTARI
from services.hesap_ekibi import HesapBaglami, eposta_duzelt, tam_baglam

BASLIK = "x-mk-hesap"


def _uye_degil() -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"kod": "hesap_uyesi_degil"})


def hesap_baglami(request: Request) -> Optional[HesapBaglami]:
    """Etkin hesap; oturum yoksa (ya da jetonda e-posta yoksa) None.

    Başlık geçersizse 403 fırlatır (oturum yoksa fırlatmaz: uç kendi 401'ini versin).
    """
    kullanici, yonetici = _yonetici_mi(request)
    if kullanici is None:
        return None
    kisi = eposta_duzelt(kullanici.email)
    if not kisi:
        return None
    if yonetici:
        return tam_baglam(kisi, yonetici=True)
    try:
        istenen = eposta_duzelt(request.headers.get(BASLIK))
    except Exception:  # noqa: BLE001
        istenen = ""
    if not istenen or istenen == kisi:
        return tam_baglam(kisi)
    try:
        karar = request.scope.get(KAPSAM_ANAHTARI)
    except Exception:  # noqa: BLE001
        karar = None
    # Ara katman çalışmadıysa (karar yok) da kapalı: başkasının hesabına
    # doğrulanmamış erişim yok.
    if not karar or karar.get("hata") or karar.get("hesap_email") != istenen or karar.get("kisi_email") != kisi:
        raise _uye_degil()
    return HesapBaglami(
        kisi_email=kisi,
        hesap_email=istenen,
        rol=karar["rol"],
        izinler=tuple(karar.get("izinler") or ()),
        uye_id=karar.get("uye_id"),
    )


def musteri_baglami(request: Request) -> HesapBaglami:
    """Oturum zorunlu: yoksa 401, jetonda e-posta yoksa 403."""
    kullanici, _ = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"kod": "oturum_gerekli"})
    baglam = hesap_baglami(request)
    if baglam is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"kod": "eposta_yok"})
    return baglam


def musteri_eposta(request: Request) -> str:
    """Kayıtların sahiplik alanında kullanılacak e-posta (= etkin hesap)."""
    return musteri_baglami(request).hesap_email


def kisi_eposta(request: Request) -> str:
    """İsteği yapan kişinin kendi e-postası (başlıktan bağımsız)."""
    return musteri_baglami(request).kisi_email


def izin_hatasi(izin: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"kod": "hesap_izni_yok", "izin": izin})


def izin_iste(request: Request, *izinler: str) -> HesapBaglami:
    """İzinlerden en az biri yoksa 403 `hesap_izni_yok`."""
    baglam = musteri_baglami(request)
    if izinler and not any(baglam.izin_var(i) for i in izinler):
        raise izin_hatasi(izinler[0])
    return baglam


def izin_gerekli(*izinler: str):
    """Router/uç bağımlılığı. Oturumsuz istekte hiçbir şey yapmaz (uç kendi 401'ini verir)."""
    from services.hesap_ekibi import IZINLER

    for i in izinler:
        if i not in IZINLER:  # yazım hatası sessizce "her şey açık" olmasın
            raise ValueError(f"Bilinmeyen hesap izni: {i}")

    async def _bekci(request: Request) -> None:
        baglam = hesap_baglami(request)
        if baglam is None:
            return
        if izinler and not any(baglam.izin_var(i) for i in izinler):
            raise izin_hatasi(izinler[0])

    _bekci.__name__ = f"izin_gerekli_{'_'.join(izinler) or 'uye'}"
    return _bekci
