"""Faz 3T — fatura geliştirmeleri: kalemler, kısmi ödeme, iade, tekrarlayan, vade, yaşlandırma, PDF.

Kapsam: eski tek tutarlı faturalar bozulmadı; kalemli faturada toplam sunucuda
(istemci toplamı yok sayılır); kısmi ödeme bakiye/durum + dekont + denetim;
bekleyen ödeme bağlantısı kalana uyuyor; iade faturası; tekrarlayan fatura
idempotent (aynı dönem iki kez kesilmez) ve yenileme yöneticisiyle çakışmıyor;
vade hatırlatması eşik başına bir kez; yaşlandırma dilimleri; müşteri yalnız
kendi faturasını görür; PDF'te Türkçe harfler, ajans bilgileri (boşsa yok) ve
"e-Fatura yerine geçmez" notu.
"""

import io
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select

ENTITY = "/api/v1/entities/invoices"
YONETIM = "/api/v1/fatura-yonetim"
MUSTERI = "/api/v1/faturalarim"


def _eposta(on: str = "fatura") -> str:
    return f"{on}-{uuid.uuid4().hex[:10]}@test.dev"


async def _fatura(istemci, baslik, beklenen=201, **govde):
    veri = {"invoice_no": f"INV-{uuid.uuid4().hex[:6]}", "client_email": _eposta(), "currency": "TRY", "status": "unpaid", **govde}
    y = await istemci.post(ENTITY, json=veri, headers=baslik)
    assert y.status_code == beklenen, y.text
    return y.json()


async def _odeme(istemci, baslik, fatura_id, tutar, beklenen=200, dekont=None, **form):
    veri = {"tutar": str(tutar), "yontem": "havale", **{k: str(v) for k, v in form.items()}}
    dosyalar = {"dekont": dekont} if dekont else None
    y = await istemci.post(f"{YONETIM}/{fatura_id}/odemeler", data=veri, files=dosyalar, headers=baslik)
    assert y.status_code == beklenen, y.text
    return y.json()


# ---------------------------------------------------------------------------
# Eski faturalar ve kalemler
# ---------------------------------------------------------------------------
async def test_eski_tek_tutarli_fatura_bozulmadi(istemci, yonetici_basligi, musteri_basligi):
    musteri = _eposta()
    f = await _fatura(istemci, yonetici_basligi, amount=1250.0, client_email=musteri, description="Eski usul")
    assert f["amount"] == 1250.0 and f["kalemler"] is None and f["ara_toplam"] is None and f["tur"] is None
    y = await istemci.put(f"{ENTITY}/{f['id']}", json={"amount": 1300.0, "status": "paid"}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["amount"] == 1300.0 and y.json()["status"] == "paid"
    # Müşteri entity ucundan yine görüyor; yeni uçta da bakiye var.
    y = await istemci.get(ENTITY, headers=musteri_basligi(musteri))
    assert [x["id"] for x in y.json()["items"]] == [f["id"]]
    y = await istemci.get(f"{MUSTERI}/{f['id']}", headers=musteri_basligi(musteri))
    assert y.status_code == 200 and y.json()["kalemler"] == [] and y.json()["bakiye"]["toplam"] == 1300.0
    # Tutarsız fatura (kalem de tutar da yok) reddedilir.
    y = await istemci.post(ENTITY, json={"invoice_no": "X-1", "client_email": musteri}, headers=yonetici_basligi)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "tutar_gerekli"


async def test_kalemli_fatura_toplami_sunucuda(istemci, yonetici_basligi):
    kalemler = [{"aciklama": "Tasarım", "adet": 2, "birim_fiyat": "1500.005", "kdv_orani": 20, "indirim": 5},
                {"aciklama": "Eğitim", "adet": 1, "birim_fiyat": 1000, "kdv_orani": 10}]
    f = await _fatura(istemci, yonetici_basligi, amount=1, ara_toplam=999, kdv_toplam=999, kalemler=kalemler)
    # 2×1500.005=3000.01 −%5 (150.00)=2850.01 → KDV 570.00 ; 1000 → KDV 100 ; toplam 4520.01
    assert f["ara_toplam"] == 3850.01 and f["kdv_toplam"] == 670.0 and f["amount"] == 4520.01
    assert f["kalemler"][0]["matrah"] == 2850.01 and f["kalemler"][1]["kdv"] == 100.0
    # Kalemli faturada tek başına tutar yazılamaz.
    y = await istemci.put(f"{ENTITY}/{f['id']}", json={"amount": 5}, headers=yonetici_basligi)
    assert y.json()["amount"] == 4520.01
    # Kalem değişince yeniden hesaplanır; boş liste tek tutarlı moda döndürür.
    y = await istemci.put(f"{ENTITY}/{f['id']}", json={"kalemler": [{"aciklama": "Tek", "birim_fiyat": 100, "kdv_orani": 20}]},
                          headers=yonetici_basligi)
    assert y.json()["amount"] == 120.0
    y = await istemci.put(f"{ENTITY}/{f['id']}", json={"kalemler": [], "amount": 77}, headers=yonetici_basligi)
    assert y.json()["kalemler"] is None and y.json()["amount"] == 77.0 and y.json()["kdv_toplam"] is None
    y = await istemci.put(f"{ENTITY}/{f['id']}", json={"kalemler": [{"aciklama": "", "birim_fiyat": 1}]}, headers=yonetici_basligi)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "aciklama_gerekli"
    # Ayrıntı ucunda KDV dökümü.
    f2 = await _fatura(istemci, yonetici_basligi, kalemler=kalemler)
    ayr = (await istemci.get(f"{YONETIM}/{f2['id']}", headers=yonetici_basligi)).json()
    assert ayr["ozet"]["kdv_dokumu"] == [{"oran": 10.0, "matrah": 1000.0, "kdv": 100.0}, {"oran": 20.0, "matrah": 2850.01, "kdv": 570.0}]


# ---------------------------------------------------------------------------
# Kısmi ödeme
# ---------------------------------------------------------------------------
async def test_kismi_odeme_bakiye_durum_dekont_denetim(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    from models.audit_log import AuditLog
    from models.dosyalar import Dosyalar
    from models.payments import Payments

    musteri = _eposta("kismi")
    f = await _fatura(istemci, yonetici_basligi, amount=1000.0, client_email=musteri)
    # Bekleyen bağlantı (1000) — kısmi ödemeden sonra kalana inmeli.
    y = await istemci.post("/api/v1/odeme/baglanti", json={"invoice_id": f["id"]}, headers=yonetici_basligi)
    assert y.status_code == 200
    jeton = y.json()["jeton"]

    dekont = ("dekont.pdf", io.BytesIO(b"%PDF-1.4\n% deneme dekont\n"), "application/pdf")
    s = await _odeme(istemci, yonetici_basligi, f["id"], "400.10", dekont=dekont, notu="İlk taksit", tarih=date.today().isoformat())
    fatura = s["fatura"]
    assert fatura["status"] == "kismi_odendi"
    assert fatura["bakiye"] == {"toplam": 1000.0, "iade_toplam": 0.0, "net": 1000.0, "odenen": 400.1, "kalan": 599.9, "fazla": 0.0}
    odeme = next(o for o in fatura["odemeler"] if o["durum"] == "odendi")
    assert odeme["dekont_var"] and odeme["notu"] == "İlk taksit" and odeme["yontem_etiketi"] == "Havale/EFT"
    assert odeme["ekleyen_eposta"] == "yonetici@test.dev"
    # Dekont müşterinin "Dekontlar" klasöründe (dosya deposu).
    dosya = (await db_oturumu.execute(select(Dosyalar).where(Dosyalar.id == odeme["dekont_dosya_id"]))).scalar_one()
    assert dosya.klasor == "Dekontlar" and dosya.client_email == musteri and dosya.tur == "application/pdf"
    # Bağlantı kalana indi.
    bag = (await db_oturumu.execute(select(Payments).where(Payments.jeton == jeton))).scalar_one()
    await db_oturumu.refresh(bag)
    assert bag.durum == "bekliyor" and bag.tutar == 599.9
    assert (await istemci.get(f"/api/v1/odeme/{jeton}")).json()["tutar"] == 599.9

    # Kalandan fazla ödeme reddedilir; geçersiz yöntem/tutar da.
    y = await istemci.post(f"{YONETIM}/{f['id']}/odemeler", data={"tutar": "600", "yontem": "havale"}, headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "tutar_kalandan_fazla"
    for veri, kod in (({"tutar": "0", "yontem": "havale"}, "tutar_gecersiz"), ({"tutar": "1", "yontem": "kripto"}, "yontem_gecersiz"),
                      ({"tutar": "abc", "yontem": "nakit"}, "tutar_gecersiz")):
        y = await istemci.post(f"{YONETIM}/{f['id']}/odemeler", data=veri, headers=yonetici_basligi)
        assert y.status_code == 400 and y.json()["detail"]["kod"] == kod

    s = await _odeme(istemci, yonetici_basligi, f["id"], "599.90", yontem="nakit")
    assert s["fatura"]["status"] == "paid" and s["fatura"]["bakiye"]["kalan"] == 0.0
    await db_oturumu.refresh(bag)
    assert bag.durum == "iptal"
    # Müşteri dekontu kendi faturasından indirebilir; başkası göremez.
    y = await istemci.get(f"{MUSTERI}/{f['id']}/odemeler/{odeme['id']}/dekont", headers=musteri_basligi(musteri))
    assert y.status_code == 200 and y.json()["adres"].startswith("/api/v1/dosya-indir/")
    assert (await istemci.get(y.json()["adres"])).status_code in (200, 307)
    assert (await istemci.get(f"{MUSTERI}/{f['id']}", headers=musteri_basligi(_eposta("baska")))).status_code == 404

    # Ödeme silinince durum geri döner (kısmi), denetimde "odeme" satırları.
    nakit = next(o for o in s["fatura"]["odemeler"] if o["saglayici"] == "elden")
    y = await istemci.delete(f"{YONETIM}/odemeler/{nakit['id']}", headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["fatura"]["status"] == "kismi_odendi"
    satirlar = (await db_oturumu.execute(
        select(AuditLog).where(AuditLog.tablo == "invoices", AuditLog.kayit_id == str(f["id"]), AuditLog.islem == "odeme")
    )).scalars().all()
    ozetler = " | ".join(x.ozet or "" for x in satirlar)
    assert "ödeme 400.10" in ozetler and "ödeme 599.90" in ozetler and "ödeme silindi" in ozetler
    # Hepsi silinince ödenmedi.
    havale = next(o for o in y.json()["fatura"]["odemeler"] if o["saglayici"] == "havale")
    y = await istemci.delete(f"{YONETIM}/odemeler/{havale['id']}", headers=yonetici_basligi)
    assert y.json()["fatura"]["status"] == "unpaid"
    # Dekont dosyası da çöp kutusuna düştü.
    assert (await db_oturumu.execute(select(Dosyalar).where(Dosyalar.id == odeme["dekont_dosya_id"]))).scalar_one_or_none() is None


async def test_elle_tahsilat_ucu_da_kismi_durumu_yaziyor(istemci, yonetici_basligi):
    f = await _fatura(istemci, yonetici_basligi, amount=300.0)
    y = await istemci.post("/api/v1/odeme/elle", json={"invoice_id": f["id"], "tutar": 100, "kanal": "eft"}, headers=yonetici_basligi)
    assert y.status_code == 200
    ayr = (await istemci.get(f"{YONETIM}/{f['id']}", headers=yonetici_basligi)).json()
    assert ayr["status"] == "kismi_odendi" and ayr["bakiye"]["kalan"] == 200.0
    # Tutarsız elle tahsilat: kalan bakiye (tamamı değil).
    y = await istemci.post("/api/v1/odeme/elle", json={"invoice_id": f["id"], "kanal": "havale"}, headers=yonetici_basligi)
    assert y.json()["tutar"] == 200.0
    ayr = (await istemci.get(f"{YONETIM}/{f['id']}", headers=yonetici_basligi)).json()
    assert ayr["status"] == "paid"


# ---------------------------------------------------------------------------
# İade
# ---------------------------------------------------------------------------
async def test_iade_faturasi(istemci, yonetici_basligi):
    f = await _fatura(istemci, yonetici_basligi, amount=1000.0)
    await _odeme(istemci, yonetici_basligi, f["id"], 1000)
    y = await istemci.post(f"{YONETIM}/{f['id']}/iade", json={"tutar": 250, "neden": "Kapsam daraldı"}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    govde = y.json()
    assert govde["iade_fatura_no"] == f"{f['invoice_no']}-IADE"
    asil = govde["fatura"]
    assert asil["bakiye"]["iade_toplam"] == 250.0 and asil["bakiye"]["kalan"] == -250.0 and asil["bakiye"]["fazla"] == 250.0
    assert asil["status"] == "paid" and asil["iadeler"][0]["amount"] == -250.0
    iade = (await istemci.get(f"{ENTITY}/{govde['iade_fatura_id']}", headers=yonetici_basligi)).json()
    assert iade["tur"] == "iade" and iade["amount"] == -250.0 and iade["bagli_fatura_id"] == f["id"] and iade["status"] == "iade"
    # Fazla: geri ödeme kaydı → kalan 0.
    y = await istemci.post(f"{YONETIM}/{f['id']}/odemeler", data={"tutar": "300", "yontem": "havale", "geri_odeme": "1"},
                           headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "geri_odeme_fazla"
    s = await _odeme(istemci, yonetici_basligi, f["id"], 250, geri_odeme="1")
    assert s["fatura"]["bakiye"]["kalan"] == 0.0 and s["fatura"]["bakiye"]["odenen"] == 750.0
    # İade tutarı net borcu aşamaz; iade faturasının iadesi olmaz.
    y = await istemci.post(f"{YONETIM}/{f['id']}/iade", json={"tutar": 800}, headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "iade_tutari_fazla"
    y = await istemci.post(f"{YONETIM}/{govde['iade_fatura_id']}/iade", json={}, headers=yonetici_basligi)
    assert y.status_code == 409

    # Ödenmemiş faturanın tam iadesi (iptal) → cancelled; KDV'li kalem iadesi eksi toplam.
    f2 = await _fatura(istemci, yonetici_basligi, kalemler=[{"aciklama": "Paket", "adet": 2, "birim_fiyat": 100, "kdv_orani": 20}])
    y = await istemci.post(f"{YONETIM}/{f2['id']}/iade", json={"kalemler": [{"aciklama": "Paket iadesi", "adet": 1, "birim_fiyat": 100, "kdv_orani": 20}]},
                           headers=yonetici_basligi)
    assert y.json()["fatura"]["bakiye"]["net"] == 120.0 and y.json()["fatura"]["status"] == "unpaid"
    iade2 = (await istemci.get(f"{ENTITY}/{y.json()['iade_fatura_id']}", headers=yonetici_basligi)).json()
    assert iade2["amount"] == -120.0 and iade2["kalemler"][0]["adet"] == -1.0 and iade2["kdv_toplam"] == -20.0
    y = await istemci.post(f"{YONETIM}/{f2['id']}/iade", json={"neden": "İptal"}, headers=yonetici_basligi)
    assert y.json()["fatura"]["status"] == "cancelled" and y.json()["fatura"]["bakiye"]["net"] == 0.0


# ---------------------------------------------------------------------------
# Tekrarlayan fatura
# ---------------------------------------------------------------------------
def test_donem_hesabi():
    from services.faturalar import donemler

    bugun = date(2026, 10, 15)
    assert donemler("aylik", "2026-10", None, bugun) == ["2026-10"]
    assert donemler("aylik", "2026-08", None, bugun) == ["2026-08", "2026-09", "2026-10"]
    assert donemler("aylik", "2026-01", "2026-09", bugun) == ["2026-10"]
    assert donemler("aylik", "2026-01", "2026-10", bugun) == []
    assert donemler("aylik", "2025-01", None, bugun) == ["2026-08", "2026-09", "2026-10"]  # en çok 3 geriye
    assert donemler("aylik", "2026-11", None, bugun) == []  # henüz başlamadı
    assert donemler("yillik", "2025-03", None, bugun) == ["2025", "2026"]
    assert donemler("yillik", "2025-11", None, bugun) == ["2025"]
    assert donemler("yillik", "2025-03", "2026", bugun) == []


async def test_tekrarlayan_fatura_idempotent_ve_bildirim(istemci, yonetici_basligi, db_oturumu, musteri_basligi):
    from models.invoices import Invoices
    from models.notifications import Notifications
    from services.faturalar import tekrarlayan_faturalari_uret, tr_bugun

    musteri = _eposta("abone")
    bu_ay = tr_bugun().strftime("%Y-%m")
    y = await istemci.post(f"{YONETIM}/tekrarlayan", json={
        "client_email": musteri, "baslik": "Bakım paketi", "periyot": "aylik", "para_birimi": "TRY", "vade_gun": 10,
        "fatura_kalemleri": [{"aciklama": "Aylık bakım", "adet": 1, "birim_fiyat": 2500, "kdv_orani": 20}],
    }, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    a = y.json()
    assert a["fatura_otomatik"] and a["fatura_baslangic"] == bu_ay and a["tutar"] == 3000.0

    for _ in range(3):  # zamanlı görev üç kez çalışsa da tek fatura
        await tekrarlayan_faturalari_uret(db_oturumu)
    y = await istemci.post(f"{YONETIM}/tekrarlayan/calistir", headers=yonetici_basligi)  # "Şimdi çalıştır" da
    assert y.status_code == 200
    faturalar = (await db_oturumu.execute(select(Invoices).where(Invoices.tekrarlayan_id == a["id"]))).scalars().all()
    assert len(faturalar) == 1
    f = faturalar[0]
    assert f.donem == bu_ay and f.amount == 3000.0 and f.client_email == musteri and f.status == "unpaid"
    assert f.due_date == (tr_bugun() + timedelta(days=10)).isoformat() and f"({bu_ay[5:]}/{bu_ay[:4]})" in f.kalemler
    bildirim = (await db_oturumu.execute(select(Notifications).where(
        Notifications.event_type == "invoice", Notifications.recipient_email == musteri, Notifications.channel == "inapp"))).scalars().all()
    assert len(bildirim) == 1 and "/ode/" in (bildirim[0].link or "")
    liste = (await istemci.get(f"{YONETIM}/tekrarlayan", headers=yonetici_basligi)).json()
    satir = next(x for x in liste if x["id"] == a["id"])
    assert satir["fatura_sayisi"] == 1 and satir["son_fatura_donemi"] == bu_ay
    # Müşteri faturasını ve ödeme bağlantısını görüyor.
    y = await istemci.get(MUSTERI, headers=musteri_basligi(musteri))
    assert y.json()["faturalar"][0]["odeme_adresi"].startswith("/ode/")
    assert y.json()["ozet"] == [{"para_birimi": "TRY", "kalan": 3000.0, "adet": 1}]

    # Kapatılınca kesilmiyor.
    y = await istemci.put(f"{YONETIM}/tekrarlayan/{a['id']}", json={"fatura_otomatik": False}, headers=yonetici_basligi)
    assert y.json()["fatura_otomatik"] is False


async def test_yenileme_yoneticisi_otomatik_faturali_aboneligi_faturalamaz(istemci, yonetici_basligi):
    y = await istemci.post(f"{YONETIM}/tekrarlayan", json={
        "client_email": _eposta("yen"), "baslik": "SEO", "periyot": "aylik",
        "fatura_kalemleri": [{"aciklama": "SEO", "birim_fiyat": 100, "kdv_orani": 20}],
    }, headers=yonetici_basligi)
    a = y.json()
    y = await istemci.post("/api/v1/yenilemeler/fatura", json={"tur": "abonelik", "ref_id": a["id"], "tutar": 120},
                           headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "otomatik_faturali"
    liste = (await istemci.get("/api/v1/yenilemeler?gun=400", headers=yonetici_basligi)).json()["kalemler"]
    kalem = next((k for k in liste if k["tur"] == "abonelik" and k["ref_id"] == a["id"]), None)
    assert kalem is not None and kalem["otomatik_fatura"] is True


# ---------------------------------------------------------------------------
# Vade hatırlatması ve yaşlandırma
# ---------------------------------------------------------------------------
async def test_vade_hatirlatmasi_esik_basina_bir_kez(istemci, yonetici_basligi, db_oturumu):
    from models.invoices import Invoices
    from models.notifications import Notifications
    from services.faturalar import tr_bugun, vade_hatirlatmalari

    musteri = _eposta("vade")
    bugun = tr_bugun()
    f = await _fatura(istemci, yonetici_basligi, amount=500.0, client_email=musteri, due_date=(bugun - timedelta(days=2)).isoformat())
    odenmis = await _fatura(istemci, yonetici_basligi, amount=500.0, client_email=musteri, status="paid",
                            due_date=(bugun - timedelta(days=20)).isoformat())

    async def say():
        return len((await db_oturumu.execute(select(Notifications).where(
            Notifications.event_type == "fatura_gecikti", Notifications.recipient_email == musteri,
            Notifications.channel == "inapp"))).scalars().all())

    await vade_hatirlatmalari(db_oturumu, bugun)
    assert await say() == 1
    kayit = (await db_oturumu.execute(select(Invoices).where(Invoices.id == f["id"]))).scalar_one()
    await db_oturumu.refresh(kayit)
    assert kayit.status == "overdue"
    await vade_hatirlatmalari(db_oturumu, bugun)
    assert await say() == 1
    await vade_hatirlatmalari(db_oturumu, bugun + timedelta(days=4))  # 6 gün: yeni eşik yok
    assert await say() == 1
    await vade_hatirlatmalari(db_oturumu, bugun + timedelta(days=13))  # 15 gün: +7 ve +14 tek bildirimde
    assert await say() == 2
    await vade_hatirlatmalari(db_oturumu, bugun + timedelta(days=30))
    assert await say() == 2
    assert odenmis["id"] != f["id"]


async def test_vade_hatirlatmasi_musteri_tercihine_tabi(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    from models.notifications import Notifications
    from services.faturalar import tr_bugun, vade_hatirlatmalari

    musteri = _eposta("tercih")
    y = await istemci.put("/api/v1/bildirim/tercihlerim", json={"tercih": {"fatura_gecikti": {"email": False}}},
                          headers=musteri_basligi(musteri))
    assert y.status_code == 200, y.text
    await _fatura(istemci, yonetici_basligi, amount=10.0, client_email=musteri,
                  due_date=(tr_bugun() - timedelta(days=1)).isoformat())
    await vade_hatirlatmalari(db_oturumu)
    kanallar = {n.channel for n in (await db_oturumu.execute(select(Notifications).where(
        Notifications.event_type == "fatura_gecikti", Notifications.recipient_email == musteri))).scalars().all()}
    assert "inapp" in kanallar and "email" not in kanallar  # e-posta kişi tarafından kapatıldı


async def test_yaslandirma_dilimleri(istemci, yonetici_basligi):
    from services.faturalar import dilim, tr_bugun

    assert [dilim(g) for g in (-3, 0, 30, 31, 60, 61, 90, 91)] == [
        "vadesi_gelmemis", "g0_30", "g0_30", "g31_60", "g31_60", "g61_90", "g61_90", "g90_ustu"]
    musteri = _eposta("yas")
    bugun = tr_bugun()
    for gun, tutar in ((-5, 100), (10, 200), (45, 300), (75, 400), (120, 500)):
        await _fatura(istemci, yonetici_basligi, amount=float(tutar), client_email=musteri,
                      due_date=(bugun - timedelta(days=gun)).isoformat())
    kismi = await _fatura(istemci, yonetici_basligi, amount=1000.0, client_email=musteri, due_date=(bugun - timedelta(days=50)).isoformat())
    await _odeme(istemci, yonetici_basligi, kismi["id"], 600)
    await _fatura(istemci, yonetici_basligi, amount=999.0, client_email=musteri, status="paid", due_date="2020-01-01")
    await _fatura(istemci, yonetici_basligi, amount=50.0, client_email=musteri, currency="USD", due_date=(bugun - timedelta(days=5)).isoformat())
    rapor = (await istemci.get(f"{YONETIM}/yaslandirma", headers=yonetici_basligi)).json()
    satirlar = {(s["client_email"], s["para_birimi"]): s for s in rapor["satirlar"]}
    tl = satirlar[(musteri, "TRY")]
    assert (tl["vadesi_gelmemis"], tl["g0_30"], tl["g31_60"], tl["g61_90"], tl["g90_ustu"]) == (100.0, 200.0, 700.0, 400.0, 500.0)
    assert tl["toplam"] == 1900.0 and tl["fatura_sayisi"] == 6 and tl["en_eski_gecikme"] == 120
    usd = satirlar[(musteri, "USD")]
    assert usd["g0_30"] == 50.0 and usd["toplam"] == 50.0  # para birimleri toplanmıyor
    assert {t["para_birimi"] for t in rapor["toplamlar"]} >= {"TRY", "USD"}


# ---------------------------------------------------------------------------
# Müşteri ve PDF
# ---------------------------------------------------------------------------
async def test_musteri_faturalarim_ve_odeme_baglantisi(istemci, yonetici_basligi, musteri_basligi):
    a, b = _eposta("a"), _eposta("b")
    f = await _fatura(istemci, yonetici_basligi, amount=750.0, client_email=a.upper())
    y = await istemci.get(MUSTERI, headers=musteri_basligi(a))
    assert y.status_code == 200 and [x["id"] for x in y.json()["faturalar"]] == [f["id"]]
    assert (await istemci.get(MUSTERI, headers=musteri_basligi(b))).json()["faturalar"] == []
    assert (await istemci.get(f"{MUSTERI}/{f['id']}/pdf", headers=musteri_basligi(b))).status_code == 404
    assert (await istemci.get(MUSTERI)).status_code == 401
    y = await istemci.post(f"{MUSTERI}/{f['id']}/odeme-baglantisi", headers=musteri_basligi(a))
    assert y.status_code == 200 and y.json()["adres"].startswith("/ode/") and y.json()["tutar"] == 750.0
    y2 = await istemci.post(f"{MUSTERI}/{f['id']}/odeme-baglantisi", headers=musteri_basligi(a))
    assert y2.json()["adres"] == y.json()["adres"]  # aynı bekleyen bağlantı
    ayr = (await istemci.get(f"{MUSTERI}/{f['id']}", headers=musteri_basligi(a))).json()
    assert ayr["odeme_adresi"] == y.json()["adres"] and all("jeton" not in o for o in ayr["odemeler"])
    # Yönetici ödenmiş faturaya bağlantı üretemez.
    await _odeme(istemci, yonetici_basligi, f["id"], 750)
    y = await istemci.post(f"{MUSTERI}/{f['id']}/odeme-baglantisi", headers=musteri_basligi(a))
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "fatura_kapali"


async def test_fatura_pdf_turkce_ajans_bilgileri_ve_not(istemci, yonetici_basligi, musteri_basligi):
    pytest.importorskip("pypdf")
    from services.pdf_belge import pdf_metni

    musteri = _eposta("pdf")
    f = await _fatura(istemci, yonetici_basligi, client_email=musteri, client_name="Işıklı Ğıda A.Ş.",
                      kalemler=[{"aciklama": "Şablon uyarlama — İçerik girişi", "adet": 2, "birim_fiyat": 625, "kdv_orani": 20}],
                      notlar="Açıklamaya fatura numarasını yazınız.", due_date="2026-12-31")
    # Ajans bilgisi boş: başlıkta yalnız künye, vergi/IBAN satırı yok.
    await istemci.put(f"{YONETIM}/ajans", json={k: "" for k in ("unvan", "adres", "vergi_dairesi", "vergi_no", "iban", "eposta", "telefon")},
                      headers=yonetici_basligi)
    metin = pdf_metni((await istemci.get(f"{YONETIM}/{f['id']}/pdf", headers=yonetici_basligi)).content)
    assert "IBAN" not in metin and "Vergi dairesi" not in metin
    y = await istemci.put(f"{YONETIM}/ajans", json={"unvan": "Mehmet Kuru Yazılım Şti.", "vergi_dairesi": "Şişli",
                                                     "vergi_no": "1234567890", "iban": "tr00 0001 2345", "adres": "Büyükdere Cd. İstanbul"},
                          headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["kayitli"]["iban"] == "TR00 0001 2345"
    y = await istemci.get(f"{MUSTERI}/{f['id']}/pdf", headers=musteri_basligi(musteri))
    assert y.status_code == 200 and y.headers["content-type"] == "application/pdf"
    metin = pdf_metni(y.content)
    for parca in ("FATURA", f["invoice_no"], "Işıklı Ğıda A.Ş.", "Şablon uyarlama — İçerik girişi", "1.500,00",
                  "Mehmet Kuru Yazılım Şti.", "Şişli / 1234567890", "TR00 0001 2345", "Büyükdere Cd. İstanbul",
                  "Kalan bakiye", "e-Fatura/e-Arşiv fatura yerine geçmez", "31.12.2026"):
        assert parca in metin, (parca, metin[:900])
    # Eski tek tutarlı fatura da PDF olur.
    eski = await _fatura(istemci, yonetici_basligi, amount=99.5, description="Danışmanlık ücreti")
    metin = pdf_metni((await istemci.get(f"{YONETIM}/{eski['id']}/pdf", headers=yonetici_basligi)).content)
    assert "Danışmanlık ücreti" in metin and "99,50" in metin
    # Temizlik (diğer testler etkilenmesin).
    await istemci.put(f"{YONETIM}/ajans", json={k: "" for k in ("unvan", "adres", "vergi_dairesi", "vergi_no", "iban")},
                      headers=yonetici_basligi)


@pytest.mark.parametrize(
    "metot,yol",
    [("GET", f"{YONETIM}/yaslandirma"), ("GET", f"{YONETIM}/1"), ("POST", f"{YONETIM}/1/odemeler"),
     ("DELETE", f"{YONETIM}/odemeler/1"), ("POST", f"{YONETIM}/1/iade"), ("GET", f"{YONETIM}/1/pdf"),
     ("GET", f"{YONETIM}/tekrarlayan"), ("POST", f"{YONETIM}/tekrarlayan"), ("PUT", f"{YONETIM}/tekrarlayan/1"),
     ("POST", f"{YONETIM}/tekrarlayan/calistir"), ("GET", f"{YONETIM}/ajans"), ("PUT", f"{YONETIM}/ajans"),
     ("POST", f"{YONETIM}/hesapla"), ("GET", f"{YONETIM}/odemeler/1/dekont"), ("POST", f"{YONETIM}/1/odeme-baglantisi")],
)
async def test_yonetici_uclari_anonime_401_musteriye_403(istemci, musteri_basligi, metot, yol):
    govde = {} if metot in ("PUT",) or (metot == "POST" and not yol.endswith("odemeler")) else None
    assert (await istemci.request(metot, yol, json=govde)).status_code == 401
    assert (await istemci.request(metot, yol, json=govde, headers=musteri_basligi())).status_code == 403


def test_yeni_moduller_ve_olaylar_tanimli():
    from core.moduller import MODUL_SOZLUGU
    from services.bildirim_tercih import OLAYLAR
    from services.hesap_ekibi import OLAY_IZNI
    from services.zamanli import GOREV_ADLARI

    assert MODUL_SOZLUGU["teklifler"].bagimliliklar == ("faturalar",)
    assert MODUL_SOZLUGU["sozlesmeler"].yonetici_sekmesi == "sozlesmeler"
    for olay in ("teklif_gonderildi", "teklif_karar", "sozlesme_imza_bekliyor", "sozlesme_imzalandi", "sozlesme_bitis",
                 "fatura_gecikti", "invoice"):
        assert OLAYLAR[olay]["tetikleniyor"] is True
    # Bağlantı e-postaları ekip üyelerine genişlemez (bağlantı bir yetki belgesi).
    assert "teklif_gonderildi" not in OLAY_IZNI and "sozlesme_imza_bekliyor" not in OLAY_IZNI
    assert OLAY_IZNI["fatura_gecikti"] == "faturalar"
    for ad in ("tekrarlayan_faturalar", "fatura_hatirlatmalari", "teklif_ve_sozlesme"):
        assert ad in GOREV_ADLARI
    assert GOREV_ADLARI[-1] == "aylik_site_analizi"


DILLER = ("tr", "en", "de", "ru", "zh", "hi", "ar")
#: Marka adları her dilde aynı kalır (çeviri değil).
MARKALAR = {"Lemon Squeezy", "Shopier", "iyzico", "PayTR", "IBAN"}


def _ek_paketi(ad: str) -> dict:
    import json
    from pathlib import Path

    kok = Path(__file__).resolve().parents[3] / "frontend" / "src" / "i18n" / "ek" / ad

    def duz(d, on=""):
        for k, v in d.items():
            if isinstance(v, dict):
                yield from duz(v, f"{on}{k}.")
            else:
                yield f"{on}{k}", v

    return {dil: dict(duz(json.loads((kok / f"{dil}.json").read_text(encoding="utf-8"))[ad])) for dil in DILLER}


@pytest.mark.parametrize("ad", ["teklif", "sozlesme", "fatura"])
def test_ek_paketleri_yedi_dilde_ayni_anahtarlar_ve_gercek_ceviri(ad):
    import re

    yt = re.compile(r"\{\{\s*(\w+)\s*\}\}")
    paketler = _ek_paketi(ad)
    tr = paketler["tr"]
    for dil, p in paketler.items():
        assert set(p) == set(tr), (dil, sorted(set(tr) ^ set(p))[:5])
        assert all(isinstance(v, str) and v.strip() for v in p.values()), dil
        # Yer tutucular her dilde aynı; i18next çoğul sözcüğü `count` kullanılmıyor.
        for k, v in p.items():
            assert set(yt.findall(v)) == set(yt.findall(tr[k])), (dil, k)
            assert "count" not in yt.findall(v), (dil, k)
    for dil in ("en", "de", "ru", "zh", "hi", "ar"):
        ayni = [k for k, v in paketler[dil].items() if v == tr[k] and len(v) > 12 and v not in MARKALAR]
        assert not ayni, (dil, ayni[:5])
    if ad == "sozlesme":
        assert tr["hukukiNot"] == (
            "Bu, 5070 sayılı Kanun anlamında güvenli elektronik imza değildir; "
            "taraflar arasında basit elektronik onay kaydıdır."
        )
        assert "5070" in paketler["ar"]["hukukiNot"] and "5070" in paketler["en"]["hukukiNot"]
    if ad == "fatura":
        assert tr["musteri.eFaturaNotu"] == "Bu belge e-Fatura/e-Arşiv yerine geçmez."
        # Durum etiketleri sunucunun bildiği bütün fatura durumlarını karşılıyor.
        from services.faturalar import DILIMLER

        assert {"unpaid", "paid", "overdue", "kismi_odendi", "cancelled", "iade"} <= {
            k.split(".")[1] for k in tr if k.startswith("durum.")
        }
        assert {k.split(".")[1] for k in tr if k.startswith("yas.") and k.split(".")[1] in DILIMLER} == set(DILIMLER)


def test_yeni_olay_ve_tablo_etiketleri_yedi_dilde():
    import json
    from pathlib import Path

    ek = Path(__file__).resolve().parents[3] / "frontend" / "src" / "i18n" / "ek"
    for dil in DILLER:
        olay = json.loads((ek / "bildirim" / f"{dil}.json").read_text(encoding="utf-8"))["bildirim"]["olay"]
        for o in ("teklif_gonderildi", "teklif_karar", "sozlesme_imza_bekliyor", "sozlesme_imzalandi", "sozlesme_bitis",
                  "fatura_gecikti"):
            assert olay[o].strip(), (dil, o)
        for paket in ("denetim", "copKutusu"):
            tablo = json.loads((ek / paket / f"{dil}.json").read_text(encoding="utf-8"))[paket]["tablo"]
            for t in ("teklifler", "sozlesmeler", "sozlesme_sablonlari"):
                assert tablo[t].strip(), (dil, paket, t)
    ana = {dil: json.loads((ek.parent / f"{dil}.json").read_text(encoding="utf-8"))["ui"] for dil in DILLER}
    for dil, ui in ana.items():
        assert ui["tabTeklifler"] and ui["tabSozlesmeler"], dil
        for durum in ("kismi_odendi", "cancelled", "iade", "pending"):
            assert ui["status"][durum].strip(), (dil, durum)
        if dil != "tr":
            assert ui["tabSozlesmeler"] != ana["tr"]["tabSozlesmeler"], dil
