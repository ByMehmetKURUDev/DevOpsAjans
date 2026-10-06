"""Faz 1 kapanış: elle "ödendi" faturada kredi ve kredi eşiğinin modül ayarı."""

import uuid

from sqlalchemy import select

YONETIM_KREDI = "/api/v1/kredi/yonetim"
MODULLER = "/api/v1/moduller"


def _eposta(on: str) -> str:
    return f"{on}-{uuid.uuid4().hex[:10]}@test.dev"


async def _kredi_satin_al(istemci, eposta, paket=25):
    from routers import fiyatlandirma

    fiyatlandirma.hiz_sinirlarini_temizle()  # Faz 7H: herkese açık uç IP başına sınırlı
    y = await istemci.post(
        "/api/v1/fiyat-satin-al", json={"kredi_paketi": paket, "musteri_eposta": eposta, "musteri_adi": "Test"}
    )
    assert y.status_code == 200, y.text
    return y.json()


async def _defter(db, eposta):
    from models.credit_ledger import CreditLedger

    db.expire_all()
    return (
        await db.execute(select(CreditLedger).where(CreditLedger.musteri_eposta == eposta).order_by(CreditLedger.id))
    ).scalars().all()


async def _bildirimler(db, eposta, olay):
    from models.notifications import Notifications

    db.expire_all()
    return (
        await db.execute(
            select(Notifications).where(
                Notifications.event_type == olay,
                Notifications.recipient_email == eposta,
                Notifications.channel == "inapp",
            )
        )
    ).scalars().all()


async def _durum(istemci, baslik, fatura_id, durum, toplu=False):
    if toplu:
        y = await istemci.put(
            "/api/v1/entities/invoices/batch",
            json={"items": [{"id": fatura_id, "updates": {"status": durum}}]},
            headers=baslik,
        )
    else:
        y = await istemci.put(f"/api/v1/entities/invoices/{fatura_id}", json={"status": durum}, headers=baslik)
    assert y.status_code == 200, y.text
    return y.json()


# ---------------------------------------------------------------------------
# 4) Elle "ödendi" işaretlenen fatura
# ---------------------------------------------------------------------------


async def test_elle_odendi_kredi_yukler_sonra_tahsilat_ikinci_kez_yuklemez(istemci, yonetici_basligi, db_oturumu):
    e = _eposta("elle-paid")
    satin = await _kredi_satin_al(istemci, e, 25)
    fid = satin["invoice_id"]
    assert await _defter(db_oturumu, e) == []

    fatura = await _durum(istemci, yonetici_basligi, fid, "paid")
    assert fatura["status"] == "paid"
    satirlar = await _defter(db_oturumu, e)
    assert [(s.tur, s.miktar) for s in satirlar] == [("satin_alma", 25), ("bonus", 2)]
    assert satirlar[0].kaynak_ref == f"fatura:{fid}:kredi" and satirlar[0].fatura_id == fid
    assert len(await _bildirimler(db_oturumu, e, "kredi_yuklendi")) == 1

    # Ardından tahsilat da girilse (ör. havale sonradan kaydedildi) ikinci yükleme yok.
    y = await istemci.post("/api/v1/odeme/elle", json={"invoice_id": fid, "kanal": "havale"}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    assert len(await _defter(db_oturumu, e)) == 2
    assert len(await _bildirimler(db_oturumu, e, "kredi_yuklendi")) == 1


async def test_paid_unpaid_paid_tek_yukleme(istemci, yonetici_basligi, db_oturumu):
    e = _eposta("gidip-gelen")
    fid = (await _kredi_satin_al(istemci, e, 10))["invoice_id"]
    await _durum(istemci, yonetici_basligi, fid, "paid")
    await _durum(istemci, yonetici_basligi, fid, "unpaid")
    await _durum(istemci, yonetici_basligi, fid, "paid")
    await _durum(istemci, yonetici_basligi, fid, "paid")  # aynı değerle tekrar kaydetmek de
    assert [(s.tur, s.miktar) for s in await _defter(db_oturumu, e)] == [("satin_alma", 10)]
    assert len(await _bildirimler(db_oturumu, e, "kredi_yuklendi")) == 1


async def test_toplu_guncelleme_de_kredi_yukler(istemci, yonetici_basligi, db_oturumu):
    e = _eposta("toplu-paid")
    fid = (await _kredi_satin_al(istemci, e, 100))["invoice_id"]
    await _durum(istemci, yonetici_basligi, fid, "paid", toplu=True)
    assert [(s.tur, s.miktar) for s in await _defter(db_oturumu, e)] == [("satin_alma", 100), ("bonus", 15)]
    await _durum(istemci, yonetici_basligi, fid, "paid", toplu=True)
    assert len(await _defter(db_oturumu, e)) == 2


async def test_once_tahsilat_sonra_elle_paid_ikinci_kez_yuklemez(istemci, yonetici_basligi, db_oturumu):
    e = _eposta("once-tahsilat")
    fid = (await _kredi_satin_al(istemci, e, 10))["invoice_id"]
    y = await istemci.post("/api/v1/odeme/elle", json={"invoice_id": fid, "kanal": "eft"}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    assert len(await _defter(db_oturumu, e)) == 1
    await _durum(istemci, yonetici_basligi, fid, "unpaid")
    await _durum(istemci, yonetici_basligi, fid, "paid")
    assert len(await _defter(db_oturumu, e)) == 1


async def test_kredisiz_ve_odenmemis_fatura_deftere_yazmaz(istemci, yonetici_basligi, db_oturumu):
    from models.credit_ledger import CreditLedger
    from sqlalchemy import func

    once = (await db_oturumu.execute(select(func.count(CreditLedger.id)))).scalar()
    y = await istemci.post(
        "/api/v1/entities/invoices",
        json={"invoice_no": f"INV-{uuid.uuid4().hex[:6]}", "amount": 50.0, "client_email": _eposta("x"), "status": "unpaid"},
        headers=yonetici_basligi,
    )
    fid = y.json()["id"]
    await _durum(istemci, yonetici_basligi, fid, "paid")
    # Kredi paketi faturası ama ödenmemiş (başka alan güncellendi): yükleme yok.
    e = _eposta("odenmemis")
    fid2 = (await _kredi_satin_al(istemci, e, 25))["invoice_id"]
    y = await istemci.put(f"/api/v1/entities/invoices/{fid2}", json={"notes": "not"}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    db_oturumu.expire_all()
    assert (await db_oturumu.execute(select(func.count(CreditLedger.id)))).scalar() == once


async def test_musteri_fatura_durumunu_degistiremez(istemci, musteri_basligi, db_oturumu):
    e = _eposta("kurnaz")
    fid = (await _kredi_satin_al(istemci, e, 25))["invoice_id"]
    y = await istemci.put(f"/api/v1/entities/invoices/{fid}", json={"status": "paid"}, headers=musteri_basligi(e))
    assert y.status_code == 403
    y = await istemci.put(f"/api/v1/entities/invoices/{fid}", json={"status": "paid"})
    assert y.status_code == 401
    assert await _defter(db_oturumu, e) == []


# ---------------------------------------------------------------------------
# 5) Kredi eşiği: müşteri modül ayarı → site ayarı → 2
# ---------------------------------------------------------------------------


async def _yukle(istemci, baslik, eposta, saat):
    y = await istemci.post(
        f"{YONETIM_KREDI}/yukle", json={"eposta": eposta, "saat": saat, "tur": "hediye", "aciklama": "x"}, headers=baslik
    )
    assert y.status_code == 200, y.text


async def _harca(istemci, baslik, eposta, saat):
    y = await istemci.post(f"{YONETIM_KREDI}/harca", json={"eposta": eposta, "saat": saat, "aciklama": "iş"}, headers=baslik)
    assert y.status_code == 200, y.text


async def test_esik_oncelik_sirasi(istemci, yonetici_basligi, db_oturumu):
    from models.site_settings import Site_settings
    from services import kredi

    ozel = _eposta("esik-ozel")
    genel = _eposta("esik-genel")

    # Hiçbiri yok → 2.
    assert await kredi.esik_degeri(db_oturumu, genel) == 2.0

    ayar = Site_settings(setting_key="kredi_esik_saat", setting_value="10", group_name="kredi")
    db_oturumu.add(ayar)
    await db_oturumu.commit()
    try:
        # Site ayarı var, müşteri ayarı yok → 10.
        assert await kredi.esik_degeri(db_oturumu, genel) == 10.0
        # Müşteri ayarı var → o (site ayarından küçük de olsa).
        y = await istemci.put(
            f"{MODULLER}/musteri/{ozel}/krediler", json={"ayarlar": {"esik_saat": 5}}, headers=yonetici_basligi
        )
        assert y.status_code == 200, y.text
        assert await kredi.esik_degeri(db_oturumu, ozel) == 5.0
        assert await kredi.esik_degeri(db_oturumu, ozel.upper()) == 5.0  # e-posta büyük/küçük harf
        # Müşteri ayarı 0: bildirim yalnız bakiye sıfırlanınca.
        await istemci.put(f"{MODULLER}/musteri/{ozel}/krediler", json={"ayarlar": {"esik_saat": 0}}, headers=yonetici_basligi)
        assert await kredi.esik_degeri(db_oturumu, ozel) == 0.0
        # Boşa çekilince site ayarına döner.
        y = await istemci.put(
            f"{MODULLER}/musteri/{ozel}/krediler", json={"ayarlar": {"esik_saat": None}}, headers=yonetici_basligi
        )
        assert y.status_code == 200, y.text
        assert await kredi.esik_degeri(db_oturumu, ozel) == 10.0
    finally:
        await db_oturumu.delete(ayar)
        await db_oturumu.commit()


async def test_esik_bildirimi_musteri_ayarini_kullanir(istemci, yonetici_basligi, db_oturumu):
    e = _eposta("esik-bildirim")
    y = await istemci.put(f"{MODULLER}/musteri/{e}/krediler", json={"ayarlar": {"esik_saat": 6}}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    await _yukle(istemci, yonetici_basligi, e, 10)
    await _harca(istemci, yonetici_basligi, e, 3)  # 7 > 6: bildirim yok (varsayılan 2 ile de yoktu)
    assert await _bildirimler(db_oturumu, e, "kredi_azaldi") == []
    await _harca(istemci, yonetici_basligi, e, 2)  # 5 ≤ 6: bildirim (varsayılan 2 olsaydı yoktu)
    bildirim = await _bildirimler(db_oturumu, e, "kredi_azaldi")
    assert len(bildirim) == 1 and "6" in bildirim[0].body


async def test_manifest_alanlari_ve_ayar_ucu(istemci, yonetici_basligi):
    y = await istemci.get(MODULLER, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    govde = y.json()
    moduller = {m["anahtar"]: m for m in (govde["moduller"] if isinstance(govde, dict) else govde)}
    esik = moduller["krediler"]["ayarlar"][0]
    assert esik["anahtar"] == "esik_saat" and esik["varsayilan"] is None and esik["bos_olabilir"] is True
    sinir = moduller["site_analizi"]["ayarlar"][0]
    assert sinir["anahtar"] == "gunluk_sinir" and sinir["varsayilan"] == 10 and sinir["bos_olabilir"] is False
