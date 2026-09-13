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


def sahibine_daralt(
    query_dict: Optional[Dict[str, Any]],
    request: Request,
    alan: str,
) -> Optional[Dict[str, Any]]:
    """Liste sorgusunu, yönetici değilse kullanıcının kendi kayıtlarına daraltır.

    `alan` tabloya göre değişiyor: faturalarda ve destek taleplerinde
    `client_email`, iletişim mesajlarında `email`.
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

    daraltilmis = dict(query_dict or {})
    # Kullanıcının gönderdiği koşulun üzerine yazıyoruz: kendi e-postasından
    # başka bir değer vermesi mümkün olmasın.
    daraltilmis[alan] = kullanici.email
    return daraltilmis


def sahiplik_dogrula(kayit: Any, request: Request, alan: str) -> None:
    """Tekil kayıt uçları için: kayıt kullanıcıya ait değilse 404."""
    _, yonetici = _yonetici_mi(request)
    if yonetici:
        return

    kullanici = istekteki_kullanici(request)
    sahip = _alan_degeri(kayit, alan)

    if not kullanici or not kullanici.email or sahip != kullanici.email:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kayıt bulunamadı")


def kendi_kaydi_mi(kayit: Any, request: Request, alan: str) -> bool:
    """Kayıt isteği yapana mı ait? Yönetici için her zaman doğru sayılıyor."""
    kullanici, yonetici = _yonetici_mi(request)
    if yonetici:
        return True
    if kullanici is None or not kullanici.email:
        return False
    return _alan_degeri(kayit, alan) == kullanici.email


def gorunur_proje_kosulu(request: Request, model: Any):
    """Projeler için görünürlük koşulu; kısıt gerekmiyorsa None.

    Projeler tablosu iki işi birden görüyor: sitedeki halka açık vaka
    çalışmaları ve müşteri panelindeki devam eden işler. Bu yüzden uç
    girişsiz okunabilir olmak zorunda — ama devam eden bir müşteri işinin
    başlığı, aşaması ve müşteri e-postası herkese açık olmamalı.

    Kural: yayında olan her kayıt herkese görünür; yayında olmayan kayıt
    yalnızca sahibine ve yöneticiye görünür.
    """
    _, yonetici = _yonetici_mi(request)
    if yonetici:
        return None

    kullanici = istekteki_kullanici(request)
    eposta = kullanici.email if kullanici and kullanici.email else None
    if eposta:
        return or_(model.published.is_(True), model.client_email == eposta)
    return model.published.is_(True)


def proje_gorunur_mu(kayit: Any, request: Request) -> None:
    """Tekil proje ucu için: görünmemesi gereken kayıt "bulunamadı" sayılıyor."""
    _, yonetici = _yonetici_mi(request)
    if yonetici:
        return
    if _alan_degeri(kayit, "published") is True:
        return
    if kendi_kaydi_mi(kayit, request, "client_email"):
        return
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kayıt bulunamadı")
