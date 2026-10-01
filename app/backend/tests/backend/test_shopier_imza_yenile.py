"""Shopier webhook imza token'ını yenileme (`webhook-kur?yenile=true`).

Token bir süre herkese açık okumada kaldı (c9ffd35 ile kapatıldı). Shopier
token'ı yalnız abonelik açılırken verdiği için yenileme = aboneliği silip
yeniden açmak. Shopier API'si burada sahte; ağa çıkılmıyor.
"""

import pytest
from sqlalchemy import select

from conftest import jeton_uret

UC = "/api/v1/odeme/shopier/webhook-kur"


class SahteShopier:
    def __init__(self, adres, mevcut_id="eski-1", yeni_token="yeni-token-123"):
        self.abonelikler = [{"id": mevcut_id, "url": adres, "event": "order.created"}] if mevcut_id else []
        self.silinen = []
        self.olusturulan = []
        self.yeni_token = yeni_token

    async def webhook_abonelikleri(self):
        return list(self.abonelikler)

    async def webhook_aboneligi_sil(self, abonelik_id):
        self.silinen.append(abonelik_id)
        self.abonelikler = [a for a in self.abonelikler if a["id"] != abonelik_id]
        return True

    async def webhook_aboneligi_olustur(self, *, olay, adres):
        self.olusturulan.append((olay, adres))
        cevap = {"id": "yeni-1", "url": adres, "event": olay}
        if self.yeni_token:
            cevap["token"] = self.yeni_token
        self.abonelikler.append(cevap)
        return cevap


@pytest.fixture
def sahte(monkeypatch):
    from core import shopier
    from routers import odemeler

    adres = f"{odemeler._site_adresi()}/api/v1/odeme/shopier/webhook"
    s = SahteShopier(adres)
    monkeypatch.setattr(shopier, "hazir_mi", lambda: True)
    monkeypatch.setattr(shopier, "webhook_abonelikleri", s.webhook_abonelikleri)
    monkeypatch.setattr(shopier, "webhook_aboneligi_sil", s.webhook_aboneligi_sil)
    monkeypatch.setattr(shopier, "webhook_aboneligi_olustur", s.webhook_aboneligi_olustur)
    return s


async def _token_yaz(db, deger):
    from models.site_settings import Site_settings

    sonuc = await db.execute(select(Site_settings).where(Site_settings.setting_key == "shopier_webhook_token"))
    kayit = sonuc.scalars().first()
    if kayit is None:
        db.add(Site_settings(setting_key="shopier_webhook_token", setting_value=deger, group_name="odeme"))
    else:
        kayit.setting_value = deger
    await db.commit()


async def _token_oku(db):
    from models.site_settings import Site_settings

    db.expire_all()
    sonuc = await db.execute(select(Site_settings).where(Site_settings.setting_key == "shopier_webhook_token"))
    kayit = sonuc.scalars().first()
    return kayit.setting_value if kayit else None


@pytest.mark.anyio
async def test_yenilemesiz_mevcut_abonelige_dokunmaz(istemci, yonetici_basligi, sahte, db_oturumu):
    await _token_yaz(db_oturumu, "eski-token")
    yanit = await istemci.post(UC, headers=yonetici_basligi)
    assert yanit.status_code == 200
    assert yanit.json()["yeni"] is False
    assert sahte.silinen == [] and sahte.olusturulan == []
    assert await _token_oku(db_oturumu) == "eski-token"


@pytest.mark.anyio
async def test_yenile_eskiyi_siler_yeni_tokeni_saklar(istemci, yonetici_basligi, sahte, db_oturumu):
    await _token_yaz(db_oturumu, "eski-token")
    yanit = await istemci.post(f"{UC}?yenile=true", headers=yonetici_basligi)
    assert yanit.status_code == 200, yanit.text
    govde = yanit.json()
    assert govde["yeni"] is True and govde["imza_saklandi"] is True
    assert "yenilendi" in govde["mesaj"]
    assert sahte.silinen == ["eski-1"]
    assert len(sahte.olusturulan) == 1
    assert await _token_oku(db_oturumu) == "yeni-token-123"
    # Yanıtta token yok (yalnız veritabanında).
    assert "yeni-token-123" not in yanit.text


@pytest.mark.anyio
async def test_yenilemede_token_gelmezse_eski_token_temizlenir(istemci, yonetici_basligi, sahte, db_oturumu):
    await _token_yaz(db_oturumu, "eski-token")
    sahte.yeni_token = ""
    yanit = await istemci.post(f"{UC}?yenile=true", headers=yonetici_basligi)
    assert yanit.status_code == 200
    assert await _token_oku(db_oturumu) == ""


@pytest.mark.anyio
async def test_eski_abonelik_silinemezse_yenisi_acilmaz(istemci, yonetici_basligi, sahte, monkeypatch, db_oturumu):
    from core import shopier

    async def silinemez(_id):
        return False

    monkeypatch.setattr(shopier, "webhook_aboneligi_sil", silinemez)
    await _token_yaz(db_oturumu, "eski-token")
    yanit = await istemci.post(f"{UC}?yenile=true", headers=yonetici_basligi)
    assert yanit.status_code == 502
    assert sahte.olusturulan == []
    assert await _token_oku(db_oturumu) == "eski-token"


@pytest.mark.anyio
async def test_musteri_yenileyemez(istemci, sahte):
    baslik = {"Authorization": f"Bearer {jeton_uret('musteri-shopier@test.dev')}"}
    yanit = await istemci.post(f"{UC}?yenile=true", headers=baslik)
    assert yanit.status_code in (401, 403)
    assert sahte.silinen == [] and sahte.olusturulan == []
