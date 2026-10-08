"""Faz 4V — herkese açık modül vitrini uçları.

* `GET  /api/v1/modul-vitrini`        — vitrin yapısı (modül kaydından türetilmiş) +
  fiyatlandırma v5'ten ölçek başına başlangıç fiyatı. Girişsiz, 5 dk önbellek.
  Prerender derlemede bunu okuyor (fiyat için), sayfa da açılışta tazeliyor.
* `POST /api/v1/modul-vitrini/talep`  — "Bu modülü/paketi iste" formu. Yeni bir
  form altyapısı değil: kayıt `inquiries`e düşüyor (`source =
  modul_vitrini:<modul|paket>:<anahtar>`), CRM'in flush kancası adayı aynı
  işlemde açıyor, yöneticiye iletişim formuyla AYNI `inquiry` bildirimi
  gidiyor. İsteğe bağlı pazarlama izni Faz 4G deseniyle adaya yazılıyor.
  Hız sınırı herkese açık CRM formuyla aynı (IP başına 10 dakikada 5);
  bal küpü alanı (`web_sitesi`) doluysa "başarılı" dönüp hiçbir şey kaydetmiyor.
  Faz 5K: isteğe bağlı gizli `referans_kodu` (ortaklık bağlantısı) adaya ve ortak atfına işleniyor.

Yetki: ikisi de herkese açık (entity_guard'a bağlı değil); veri okuma uçu
yalnız kayıttan türeyen genel bilgiyi ve ölçek fiyatını döndürüyor.
"""

import json
import logging
from typing import Any, Dict

from core.database import get_db
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from services import modul_vitrini as servis
from services.notify import admin_recipients, dispatch, render
from sqlalchemy.ext.asyncio import AsyncSession
from utils.hiz_siniri import HizSiniri
from utils.istemci_ip import ip_ozeti, istemci_ip

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/modul-vitrini", tags=["modul-vitrini"])

#: IP başına 10 dakikada en çok 5 talep (herkese açık CRM formuyla aynı).
_talep_hizi = HizSiniri(5, 600.0)
#: Gövde üst sınırı (alan sınırlarının toplamından rahatça büyük).
GOVDE_SINIRI = 8 * 1024
#: Bal küpü: insan görmüyor, bot dolduruyor.
BAL_KUPU = "web_sitesi"


def hiz_sinirlarini_temizle() -> None:
    """Testler için."""
    _talep_hizi.temizle()


def _hata(durum: int, kod: str, **ek: Any) -> HTTPException:
    return HTTPException(status_code=durum, detail={"kod": kod, **ek})


@router.get("")
async def vitrin(db: AsyncSession = Depends(get_db)):
    veri = await servis.vitrin_verisi(db)
    return JSONResponse(veri, headers={"Cache-Control": "public, max-age=300"})


@router.post("/talep")
async def talep(request: Request, db: AsyncSession = Depends(get_db)):
    ip = ip_ozeti(istemci_ip(request))
    if not _talep_hizi.izin_var_mi(ip):
        raise _hata(429, "cok_fazla_istek")
    ham = await request.body()
    if len(ham) > GOVDE_SINIRI:
        raise _hata(413, "govde_buyuk")
    try:
        govde = json.loads(ham.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        raise _hata(400, "govde_gecersiz")
    if not isinstance(govde, dict):
        raise _hata(400, "govde_gecersiz")

    # Bal küpü: bot "başarılı" görsün, hiçbir şey kaydedilmesin.
    if str(govde.get(BAL_KUPU) or "").strip():
        logger.info("Modül vitrini: bal küpü dolu, talep yok sayıldı")
        return {"ok": True}

    try:
        sonuc = await servis.talep_olustur(db, govde)
    except servis.TalepHatasi as h:
        raise _hata(h.durum, h.kod, **h.ek)
    if sonuc["tekrar"]:
        return {"ok": True}

    g = sonuc["girdi"]
    if govde.get("referans_kodu") and sonuc.get("talep_id"):
        # Faz 5K: ortaklık bağlantısından gelen kod (gizli alan) adaya + ortak atfına; hata yutulur.
        from services import ortaklik

        await ortaklik.formdan_isle(db, tablo="inquiries", kayit_id=sonuc["talep_id"], eposta=g["eposta"],
                                    ham_kod=str(govde.get("referans_kodu"))[:64])
    # Yöneticiye iletişim formuyla aynı bildirim (şablon panelde düzenlenebiliyor).
    try:
        baslik, metin = await render(
            db,
            "inquiry",
            f"Yeni iletişim mesajı: {g['ad']}",
            (
                f"Ad: {g['ad']}\nE-posta: {g['eposta']}\nTelefon: {g['telefon'] or '—'}\n"
                f"Konu: {sonuc['konu']}\n\n{sonuc['mesaj']}"
            ),
            {"ad": g["ad"], "eposta": g["eposta"], "telefon": g["telefon"] or "—", "konu": sonuc["konu"], "mesaj": sonuc["mesaj"]},
        )
        await dispatch(
            db, event_type="inquiry", title=baslik, body=metin, recipients=await admin_recipients(db),
            link="/admin", ref_type="inquiry", ref_id=sonuc["talep_id"],
        )
    except Exception as exc:  # noqa: BLE001 - bildirim düşse de talep kaydedildi
        logger.error("Modül vitrini bildirimi gönderilemedi: %s", exc)
    return {"ok": True}
