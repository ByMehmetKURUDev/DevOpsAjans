"""Müşteri kayıtlarını sahibine göre daraltır.

Sorun
-----
`entity_guard` okumalar için "oturum açmış olmak yeterli" diyor; müşteri
panelinin çalışabilmesi için gerekli bir kural. Ama fatura, destek talebi ve
iletişim mesajı gibi tablolarda bu yetmiyor: giriş yapmış herhangi bir
müşteri, başka bir müşterinin faturasını da çekebiliyordu. Ön yüz kendi
kayıtlarını tarayıcıda süzüyordu — yani süzgeç istemcideydi, oysa veri
sunucudan olduğu gibi geliyordu.

Yaklaşım
--------
Süzgeç sunucuya taşınıyor. Yönetici olmayan kullanıcılar için sorguya, kendi
e-posta adresi zorunlu bir koşul olarak ekleniyor; tekil kayıt uçlarında ise
sahibi olmadığı kayıt "bulunamadı" sayılıyor (403 yerine 404 — kaydın var
olup olmadığı da sızmasın diye).

Yönetici için hiçbir şey değişmiyor.

Faz 2E: "kendi e-postası" artık etkin hesap (`X-MK-Hesap` ile seçilen ve
kişinin üyesi olduğu hesap; bkz. `dependencies/hesap_baglami.py`). Başlıksız
istekte davranış aynı. Üyede rolün ilgili izni de aranıyor.
"""

import logging
from typing import Any, Dict, Optional

from dependencies.entity_guard import _istekteki_kullanici as istekteki_kullanici
from fastapi import HTTPException, Request, status
from sqlalchemy import or_

logger = logging.getLogger(__name__)


def _yonetici_mi(request: Request):
    """(kullanıcı, yönetici_mi) ikilisini döndürür."""
    kullanici = istekteki_kullanici(request)
    return kullanici, bool(kullanici and kullanici.role == "admin")


def _alan_degeri(kayit: Any, alan: str) -> Any:
    """Kayıt sözlük de olabilir ORM nesnesi de; alanı ikisinden de okur."""
    if isinstance(kayit, dict):
        return kayit.get(alan)
    return getattr(kayit, alan, None)


def _baglam(request: Request):
    """Faz 2E: etkin hesap (başlık geçersizse 403). Döngüsel içe aktarma olmasın diye içeride."""
    from dependencies.hesap_baglami import hesap_baglami

    return hesap_baglami(request)


def _izin_denetle(baglam, izin: Optional[str]) -> None:
    if izin and baglam is not None and not baglam.izin_var(izin):
        from dependencies.hesap_baglami import izin_hatasi

        raise izin_hatasi(izin)


def _sahip_degeri(kullanici, baglam) -> str:
    """Kendi hesabında jetondaki e-posta (eski davranış, harf duyarlı); üyede hesap e-postası."""
    if baglam is None or baglam.kendi_hesabi:
        return kullanici.email
    return baglam.hesap_email


def sahibine_daralt(
    query_dict: Optional[Dict[str, Any]],
    request: Request,
    alan: str,
    izin: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Liste sorgusunu, yönetici değilse etkin hesabın kayıtlarına daraltır.

    `alan` tabloya göre değişiyor: faturalarda ve destek taleplerinde
    `client_email`, iletişim mesajlarında `email`. Faz 2E: `izin` verilmişse
    (ör. "faturalar") etkin hesaptaki rolün o izni olmalı, yoksa 403.
    """
    kullanici, yonetici = _yonetici_mi(request)
    if yonetici:
        return query_dict

    if kullanici is None or not kullanici.email:
        # entity_guard buraya oturumsuz istek bırakmıyor; yine de e-postasız
        # bir jeton gelirse hiçbir kaydı görmemeli.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu kayıtları görmek için hesabınızda e-posta adresi tanımlı olmalı",
        )

    baglam = _baglam(request)
    _izin_denetle(baglam, izin)

    daraltilmis = dict(query_dict or {})
    # Kullanıcının gönderdiği koşulun üzerine yazıyoruz: etkin hesaptan
    # başka bir değer vermesi mümkün olmasın.
    daraltilmis[alan] = _sahip_degeri(kullanici, baglam)
    return daraltilmis


def _ayni_sahip_mi(sahip: Any, kullanici, baglam) -> bool:
    if baglam is None or baglam.kendi_hesabi:
        return sahip == kullanici.email
    return isinstance(sahip, str) and sahip.strip().lower() == baglam.hesap_email


def sahiplik_dogrula(kayit: Any, request: Request, alan: str, izin: Optional[str] = None) -> None:
    """Tekil kayıt uçları için: kayıt etkin hesaba ait değilse 404 (izin yoksa 403)."""
    _, yonetici = _yonetici_mi(request)
    if yonetici:
        return

    kullanici = istekteki_kullanici(request)
    if not kullanici or not kullanici.email:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kayıt bulunamadı")
    baglam = _baglam(request)
    _izin_denetle(baglam, izin)
    if not _ayni_sahip_mi(_alan_degeri(kayit, alan), kullanici, baglam):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kayıt bulunamadı")


def kendi_kaydi_mi(kayit: Any, request: Request, alan: str, izin: Optional[str] = None) -> bool:
    """Kayıt etkin hesaba mı ait? Yönetici için her zaman doğru. Hata fırlatmaz."""
    kullanici, yonetici = _yonetici_mi(request)
    if yonetici:
        return True
    if kullanici is None or not kullanici.email:
        return False
    try:
        baglam = _baglam(request)
    except HTTPException:
        return False
    if izin and baglam is not None and not baglam.izin_var(izin):
        return False
    return _ayni_sahip_mi(_alan_degeri(kayit, alan), kullanici, baglam)


def gorunur_proje_kosulu(request: Request, model: Any):
    """Projeler için görünürlük koşulu; kısıt gerekmiyorsa None.

    Projeler tablosu iki işi birden görüyor: sitedeki halka açık vaka
    çalışmaları ve müşteri panelindeki devam eden işler. Bu yüzden uç
    girişsiz okunabilir olmak zorunda — ama devam eden bir müşteri işinin
    başlığı, aşaması ve müşteri e-postası herkese açık olmamalı.

    Kural: yayında olan her kayıt herkese görünür; yayında olmayan kayıt
    yalnızca sahibine (etkin hesap) ve yöneticiye görünür. Faz 2E: başka
    bir hesapta çalışan üyenin `projeler` izni yoksa 403.
    """
    _, yonetici = _yonetici_mi(request)
    if yonetici:
        return None

    kullanici = istekteki_kullanici(request)
    eposta = kullanici.email if kullanici and kullanici.email else None
    if eposta:
        baglam = _baglam(request)
        _izin_denetle(baglam, "projeler")
        return or_(model.published.is_(True), model.client_email == _sahip_degeri(kullanici, baglam))
    return model.published.is_(True)


def proje_gorunur_mu(kayit: Any, request: Request) -> None:
    """Tekil proje ucu için: görünmemesi gereken kayıt "bulunamadı" sayılıyor."""
    _, yonetici = _yonetici_mi(request)
    if yonetici:
        return
    kullanici = istekteki_kullanici(request)
    if kullanici is not None and kullanici.email:
        _izin_denetle(_baglam(request), "projeler")
    if _alan_degeri(kayit, "published") is True:
        return
    if kendi_kaydi_mi(kayit, request, "client_email"):
        return
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kayıt bulunamadı")
