"""Faz 5C — Cüzdan ve bakiye (müşteri avansı).

Kapsam: yetki (anonim 401, müşteri yalnız kendi bakiyesi, yönetici uçlarına müşteri 403), eksi bakiye reddi, eşzamanlı
harcama (aynı anda iki istek → biri reddedilir; SQLite'ta da koşullu güncelleme), idempotent harcama, para birimi
uyuşmazlığı reddi, kısmi ödeme → `kismi_odendi`, tam ödeme → `paid` + `fatura.odendi` olayı + ortaklık komisyonu BİR
kez, ödeme silinince ters kayıt, iade faturası etkisi, yükleme talebi onay/ret (gelen kutusu kaynağı), ön muhasebede
ÇİFT SAYIM YOK (yükleme tahsilat — gelir değil; bakiyeden ödeme vadeli gelir — nakit yok; iade ödeme — gider değil),
otomatik ödeme ayarı, düşük bakiye bildirimi bir kez, ekstre PDF/CSV, kataloglar ve 7 dil etiketleri.

Hukuki dayanak (bilgilendirme amaçlıdır, hukuki danışmanlık değildir): bakiye yalnız ajansın kendi hizmetleri için
verilmiş avans — 6493 sayılı Kanun anlamında elektronik para / ödeme hizmeti değil (üçüncü kişiye ödeme yok, faiz yok,
devredilemez); kullanılmayan bakiye talep üzerine iade edilir (elle).
"""

import asyncio
import io
import json
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

Y = "/api/v1/cuzdan-yonetim"
M = "/api/v1/cuzdanim"
ENTITY = "/api/v1/entities/invoices"
FATURA_YON = "/api/v1/fatura-yonetim"
MUH = "/api/v1/muhasebe-yonetim"
DILLER = ("tr", "en", "de", "ru", "zh", "hi", "ar")
EK = Path(__file__).resolve().parents[3] / "frontend" / "src" / "i18n" / "ek"
DEKONT = ("dekont.pdf", b"%PDF-1.4\n% deneme dekont\n", "application/pdf")


def _e(on: str = "cz") -> str:
    return f"{on}-{uuid.uuid4().hex[:10]}@test.dev"


def _kod(y) -> str:
    try:
        d = y.json().get("detail")
        return d.get("kod") if isinstance(d, dict) else str(d)
    except Exception:  # noqa: BLE001
        return ""


async def _fatura(istemci, yb, musteri, tutar, pb="TRY", **ek):
    veri = {"invoice_no": f"CZ-{uuid.uuid4().hex[:6]}", "client_email": musteri, "currency": pb, "status": "unpaid",
            "amount": tutar, **ek}
    y = await istemci.post(ENTITY, json=veri, headers=yb)
    assert y.status_code == 201, y.text
    return y.json()


async def _yukle(istemci, yb, musteri, tutar, pb="TRY", yontem="havale", beklenen=200, **ek):
    veri = {"hesap_email": musteri, "tutar": str(tutar), "para_birimi": pb, "yontem": yontem, **ek}
    y = await istemci.post(f"{Y}/yukle", data=veri, headers=yb)
    assert y.status_code == beklenen, y.text
    return y.json()


async def _ode(istemci, baslik, fatura_id, beklenen=200, **govde):
    y = await istemci.post(f"{M}/faturalar/{fatura_id}/ode", json=govde, headers=baslik)
    assert y.status_code == beklenen, y.text
    return y.json()


async def _bakiye(istemci, baslik, pb="TRY") -> float:
    o = (await istemci.get(M, headers=baslik)).json()
    return next((b["bakiye"] for b in o["bakiyeler"] if b["para_birimi"] == pb), 0.0)


async def _bildirimler(db, eposta, olay):
    from models.notifications import Notifications

    db.expire_all()
    return list((await db.execute(select(Notifications).where(Notifications.recipient_email == eposta,
                                                              Notifications.event_type == olay,
                                                              Notifications.channel == "inapp"))).scalars().all())


async def _odemeler(db, fatura_id):
    from models.payments import Payments

    db.expire_all()
    return list((await db.execute(select(Payments).where(Payments.invoice_id == fatura_id).order_by(Payments.id))).scalars().all())


# ---------------------------------------------------------------------------
# Yetki
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("metot,yol", [("GET", f"{Y}/hesaplar"), ("GET", f"{Y}/talepler"), ("POST", f"{Y}/iade"),
                                       ("POST", f"{Y}/duzeltme"), ("GET", f"{Y}/ayarlar"), ("POST", f"{Y}/faturalar/1/uygula")])
async def test_yonetici_uclari_anonim_401_musteri_403(istemci, musteri_basligi, metot, yol):
    y = await istemci.request(metot, yol, **({} if metot == "GET" else {"json": {}}))
    assert y.status_code == 401
    y = await istemci.request(metot, yol, headers=musteri_basligi(_e()), **({} if metot == "GET" else {"json": {}}))
    assert y.status_code == 403


async def test_musteri_yalniz_kendi_bakiyesi(istemci, yonetici_basligi, musteri_basligi):
    a, b = _e("a"), _e("b")
    assert (await istemci.get(M)).status_code == 401
    await _yukle(istemci, yonetici_basligi, a, "1000")
    assert await _bakiye(istemci, musteri_basligi(a)) == 1000.0
    assert await _bakiye(istemci, musteri_basligi(b)) == 0.0
    h = (await istemci.get(f"{M}/hareketler", headers=musteri_basligi(b))).json()
    assert h["items"] == [] and h["toplam"] == 0
    # B, A'nın faturasını ödeyemez / göremez (404 — varlığı bile sızmaz).
    f = await _fatura(istemci, yonetici_basligi, a, 300)
    y = await istemci.post(f"{M}/faturalar/{f['id']}/ode", json={}, headers=musteri_basligi(b))
    assert y.status_code == 404
    # Müşterinin hareket sözlüğünde yönetici alanları yok.
    x = (await istemci.get(f"{M}/hareketler", headers=musteri_basligi(a))).json()["items"][0]
    assert x["tur"] == "yukleme" and x["tutar"] == 1000.0 and "yazan" not in x and "hesap_email" not in x
    # Elle "bakiye" yöntemiyle ödeme yazılamaz (cüzdana dokunmadan fatura kapanmasın).
    y = await istemci.post(f"{FATURA_YON}/{f['id']}/odemeler", data={"tutar": "100", "yontem": "bakiye"}, headers=yonetici_basligi)
    assert y.status_code == 400 and _kod(y) == "yontem_gecersiz"


# ---------------------------------------------------------------------------
# Defter kuralları
# ---------------------------------------------------------------------------
async def test_eksi_bakiye_reddi_duzeltme_ters_kayit(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    from models.cuzdan import CuzdanHareketleri

    yb, m = yonetici_basligi, _e("eksi")
    r = await _yukle(istemci, yb, m, "1000", yontem="eft", notu="İlk avans")
    assert r["bakiye"] == 1000.0 and r["hareket"]["yontem"] == "eft"
    y = await istemci.post(f"{Y}/iade", json={"hesap_email": m, "para_birimi": "TRY", "tutar": "1500", "yontem": "havale"}, headers=yb)
    assert y.status_code == 409 and _kod(y) == "bakiye_yetersiz" and y.json()["detail"]["bakiye"] == 1000.0
    y = await istemci.post(f"{Y}/duzeltme", json={"hesap_email": m, "para_birimi": "TRY", "tutar": "-2000", "gerekce": "x"}, headers=yb)
    assert y.status_code == 409 and _kod(y) == "bakiye_yetersiz"
    y = await istemci.post(f"{Y}/duzeltme", json={"hesap_email": m, "para_birimi": "TRY", "tutar": "50"}, headers=yb)
    assert y.status_code == 400 and _kod(y) == "gerekce_gerekli"
    for kotu in ("0", "-5", "abc", "20000000"):
        assert (await _yukle(istemci, yb, m, kotu, beklenen=400)) is not None
    y = await istemci.post(f"{Y}/duzeltme", json={"hesap_email": m, "para_birimi": "TRY", "tutar": "-100", "gerekce": "Hatalı tutar"},
                           headers=yb)
    assert y.status_code == 200 and y.json()["bakiye"] == 900.0
    y = await istemci.post(f"{Y}/iade", json={"hesap_email": m, "para_birimi": "TRY", "tutar": "200", "yontem": "havale",
                                               "notu": "Talep üzerine"}, headers=yb)
    assert y.status_code == 200 and y.json()["bakiye"] == 700.0
    assert len(await _bildirimler(db_oturumu, m, "bakiye_iade")) == 1
    # Ters kayıt: yükleme bir kez; harcama ve ters kaydın tersi olmaz; gerekçe zorunlu.
    yk = r["hareket"]["id"]
    y = await istemci.post(f"{Y}/hareketler/{yk}/ters", json={}, headers=yb)
    assert y.status_code == 400 and _kod(y) == "gerekce_gerekli"
    y = await istemci.post(f"{Y}/hareketler/{yk}/ters", json={"gerekce": "Yanlış hesaba"}, headers=yb)
    assert y.status_code == 409 and _kod(y) == "bakiye_yetersiz"  # 700 < 1000: eksiye düşmez
    await _yukle(istemci, yb, m, "300")
    y = await istemci.post(f"{Y}/hareketler/{yk}/ters", json={"gerekce": "Yanlış hesaba"}, headers=yb)
    assert y.status_code == 200 and y.json()["bakiye"] == 0.0 and y.json()["hareket"]["bagli_id"] == yk
    y = await istemci.post(f"{Y}/hareketler/{yk}/ters", json={"gerekce": "Tekrar"}, headers=yb)
    assert y.status_code == 409 and _kod(y) == "zaten_ters_cevrildi"
    tid = (await istemci.get(f"{Y}/hesap", params={"eposta": m}, headers=yb)).json()["hareketler"]["items"][0]["id"]
    y = await istemci.post(f"{Y}/hareketler/{tid}/ters", json={"gerekce": "x"}, headers=yb)
    assert y.status_code == 409 and _kod(y) == "ters_kaydin_tersi"
    # Defter: sonra = önceki + tutar zinciri; satırlar değişmedi (sıra id).
    satirlar = (await db_oturumu.execute(select(CuzdanHareketleri).where(CuzdanHareketleri.hesap_email == m)
                                         .order_by(CuzdanHareketleri.id))).scalars().all()
    bakiye = 0
    for s in satirlar:
        bakiye += s.tutar
        assert s.sonra == bakiye >= 0
    d = (await istemci.get(f"{Y}/hesap", params={"eposta": m}, headers=yb)).json()
    assert d["bakiyeler"][0]["bakiye"] == 0.0 and d["hareketler"]["toplam"] == 5
    asil = next(x for x in d["hareketler"]["items"] if x["id"] == yk)
    assert asil["ters_edildi"] and not asil["ters_edilebilir"]


async def test_eszamanli_harcama_biri_reddedilir(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    yb, m = yonetici_basligi, _e("eszaman")
    mb = musteri_basligi(m)
    await _yukle(istemci, yb, m, "1000")
    f1 = await _fatura(istemci, yb, m, 800)
    f2 = await _fatura(istemci, yb, m, 800)
    y1, y2 = await asyncio.gather(istemci.post(f"{M}/faturalar/{f1['id']}/ode", json={}, headers=mb),
                                  istemci.post(f"{M}/faturalar/{f2['id']}/ode", json={}, headers=mb))
    assert sorted([y1.status_code, y2.status_code]) == [200, 409], (y1.text, y2.text)
    red = y1 if y1.status_code == 409 else y2
    assert _kod(red) == "bakiye_yetersiz"
    assert await _bakiye(istemci, mb) == 200.0
    odenen = [(p.saglayici, p.tutar) for f in (f1, f2) for p in await _odemeler(db_oturumu, f["id"]) if p.saglayici == "bakiye"]
    assert odenen == [("bakiye", 800.0)]


async def test_idempotent_harcama_ayni_istek_tek_harcama(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    yb, m = yonetici_basligi, _e("idem")
    mb = musteri_basligi(m)
    await _yukle(istemci, yb, m, "1000")
    f = await _fatura(istemci, yb, m, 500)
    anahtar = uuid.uuid4().hex
    s1 = await _ode(istemci, mb, f["id"], tutar="200", istek_anahtari=anahtar)
    s2 = await _ode(istemci, mb, f["id"], tutar="200", istek_anahtari=anahtar)
    assert s1["tekrar"] is False and s2["tekrar"] is True and s1["hareket"]["id"] == s2["hareket"]["id"]
    assert s1["fatura"]["status"] == "kismi_odendi" and s2["bakiye"] == 800.0
    # Aynı anahtarla eşzamanlı iki istek de tek harcama.
    a2 = uuid.uuid4().hex
    y1, y2 = await asyncio.gather(istemci.post(f"{M}/faturalar/{f['id']}/ode", json={"tutar": "100", "istek_anahtari": a2}, headers=mb),
                                  istemci.post(f"{M}/faturalar/{f['id']}/ode", json={"tutar": "100", "istek_anahtari": a2}, headers=mb))
    assert y1.status_code == y2.status_code == 200, (y1.text, y2.text)
    assert {y1.json()["tekrar"], y2.json()["tekrar"]} == {False, True}
    assert await _bakiye(istemci, mb) == 700.0
    bakiyeden = [p for p in await _odemeler(db_oturumu, f["id"]) if p.saglayici == "bakiye"]
    assert [p.tutar for p in bakiyeden] == [200.0, 100.0]
    y = await istemci.post(f"{M}/faturalar/{f['id']}/ode", json={"istek_anahtari": "kisa"}, headers=mb)
    assert y.status_code == 400 and _kod(y) == "istek_anahtari_gecersiz"


async def test_para_birimi_uyusmazligi_ve_kalandan_fazla(istemci, yonetici_basligi, musteri_basligi):
    yb, m = yonetici_basligi, _e("pb")
    mb = musteri_basligi(m)
    await _yukle(istemci, yb, m, "1000", pb="TRY")
    f = await _fatura(istemci, yb, m, 100, pb="USD")
    y = await istemci.post(f"{M}/faturalar/{f['id']}/ode", json={}, headers=mb)
    assert y.status_code == 409 and _kod(y) == "para_birimi_uyusmuyor" and y.json()["detail"]["bakiye_para_birimleri"] == ["TRY"]
    ft = await _fatura(istemci, yb, m, 300)
    y = await istemci.post(f"{M}/faturalar/{ft['id']}/ode", json={"tutar": "301"}, headers=mb)
    assert y.status_code == 409 and _kod(y) == "tutar_kalandan_fazla" and y.json()["detail"]["kalan"] == 300.0
    # Taslak fatura müşteriye görünmez; iade faturası ödenmez.
    taslak = await _fatura(istemci, yb, m, 50, status="draft")
    assert (await istemci.post(f"{M}/faturalar/{taslak['id']}/ode", json={}, headers=mb)).status_code == 404
    y = await istemci.post(f"{Y}/faturalar/{taslak['id']}/uygula", json={}, headers=yb)
    assert y.status_code == 409 and _kod(y) == "fatura_taslak"


async def test_kismi_ve_tam_odeme_olay_komisyon_bir_kez(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    from models.api_erisimi import WebhookTeslimatlari, WebhookUcNoktalari
    from models.ortaklik import OrtakKomisyonlari, Ortaklar
    from routers import ortaklik as ortaklik_r
    from services import ortaklik as ortaklik_s
    from services import webhook

    yb = yonetici_basligi
    ortaklik_r.hiz_sinirlarini_temizle()
    ortaklik_s.onbellegi_temizle()
    ortak_eposta, m = _e("ortak"), _e("komisyon")
    y = await istemci.post("/api/v1/ortaklik/basvuru", json={"ad": "Can Yıldız", "eposta": ortak_eposta, "web": "can.dev",
                                                              "tanitim": "Blog", "kosullar_kabul": True, "dil": "tr"})
    assert y.status_code == 200, y.text
    o = (await db_oturumu.execute(select(Ortaklar).where(Ortaklar.eposta == ortak_eposta))).scalars().first()
    y = await istemci.post(f"/api/v1/ortaklik-yonetim/ortaklar/{o.id}/karar", json={"karar": "onay", "oran": 10}, headers=yb)
    assert y.status_code == 200, y.text
    kod = y.json()["kod"]
    await istemci.post("/api/v1/entities/inquiries", json={"name": "M", "email": m, "message": "x", "referans_kodu": kod})
    eski_ayar = (await istemci.get("/api/v1/ortaklik-yonetim/ayarlar", headers=yb)).json()
    await istemci.put("/api/v1/ortaklik-yonetim/ayarlar", json={"tum_faturalar": True, "bekleme_gun": 0}, headers=yb)
    uc = WebhookUcNoktalari(sahip_tur="ajans", hesap_email=None, url="https://kanca.ornek.com/cz",
                            olaylar='["fatura.odendi", "bakiye.harcandi", "bakiye.yuklendi"]', aktif=True,
                            gizli_anahtar="d1:whsec_x", ardisik_hata=0, tum_musteriler=True)
    db_oturumu.add(uc)
    await db_oturumu.commit()
    uc_id = uc.id
    webhook.onbellegi_temizle()
    try:
        await _yukle(istemci, yb, m, "2000")
        f = await _fatura(istemci, yb, m, 1000)
        s = await _ode(istemci, musteri_basligi(m), f["id"], tutar="400")
        assert s["fatura"]["status"] == "kismi_odendi" and s["fatura"]["bakiye"]["kalan"] == 600.0
        assert s["hareket"]["tur"] == "harcama" and s["hareket"]["tutar"] == -400.0 and s["bakiye"] == 1600.0
        # Yönetici de faturaya bakiye uygulayabilir (kalanın tamamı).
        bilgi = (await istemci.get(f"{Y}/faturalar/{f['id']}", headers=yb)).json()
        assert bilgi["uygulanabilir"] and bilgi["kalan"] == 600.0 and bilgi["onerilen"] == 600.0 and bilgi["bakiye"] == 1600.0
        y = await istemci.post(f"{Y}/faturalar/{f['id']}/uygula", json={}, headers=yb)
        assert y.status_code == 200 and y.json()["fatura"]["status"] == "paid" and y.json()["bakiye"] == 1000.0
        assert (await istemci.get(f"{Y}/faturalar/{f['id']}", headers=yb)).json()["neden"] == "fatura_kapali"
        # Ödendi: kalan ödeme ucu reddeder; fatura.odendi bir kez, komisyon bir kez (aynı tahsilat yolu).
        y = await istemci.post(f"{M}/faturalar/{f['id']}/ode", json={}, headers=musteri_basligi(m))
        assert y.status_code == 409 and _kod(y) == "fatura_kapali"
        db_oturumu.expire_all()
        t = (await db_oturumu.execute(select(WebhookTeslimatlari).where(WebhookTeslimatlari.uc_id == uc_id))).scalars().all()
        turler = [x.tur for x in t]
        assert turler.count("fatura.odendi") == 1 and turler.count("bakiye.harcandi") == 2 and turler.count("bakiye.yuklendi") == 1
        govde = json.loads(next(x.govde for x in t if x.tur == "bakiye.harcandi"))
        assert govde["veri"]["fatura_id"] == f["id"] and govde["veri"]["para_birimi"] == "TRY" and m not in json.dumps(govde["veri"])
        kom = (await db_oturumu.execute(select(OrtakKomisyonlari).where(OrtakKomisyonlari.fatura_id == f["id"],
                                                                         OrtakKomisyonlari.tur == "komisyon"))).scalars().all()
        assert len(kom) == 1 and Decimal(str(kom[0].tutar)) == Decimal("100")
        odemeler = await _odemeler(db_oturumu, f["id"])
        assert [(p.saglayici, p.durum, p.tutar) for p in odemeler if p.durum != "bekliyor" and p.durum != "iptal"] == [
            ("bakiye", "odendi", 400.0), ("bakiye", "odendi", 600.0)]
        assert len(await _bildirimler(db_oturumu, m, "bakiye_harcama")) == 2
    finally:
        await istemci.put("/api/v1/ortaklik-yonetim/ayarlar", json={k: eski_ayar[k] for k in ("tum_faturalar", "bekleme_gun")
                                                                     if k in eski_ayar}, headers=yb)
        from sqlalchemy import delete

        await db_oturumu.execute(delete(WebhookTeslimatlari).where(WebhookTeslimatlari.uc_id == uc_id))
        await db_oturumu.execute(delete(WebhookUcNoktalari).where(WebhookUcNoktalari.id == uc_id))
        await db_oturumu.commit()
        webhook.onbellegi_temizle()
        ortaklik_s.onbellegi_temizle()


async def test_odeme_silinince_bakiyeye_ters_kayit(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    yb, m = yonetici_basligi, _e("sil")
    mb = musteri_basligi(m)
    await _yukle(istemci, yb, m, "1000")
    f = await _fatura(istemci, yb, m, 600)
    s = await _ode(istemci, mb, f["id"])
    assert s["fatura"]["status"] == "paid" and s["bakiye"] == 400.0
    pid = next(p.id for p in await _odemeler(db_oturumu, f["id"]) if p.saglayici == "bakiye")
    y = await istemci.delete(f"{FATURA_YON}/odemeler/{pid}", headers=yb)
    assert y.status_code == 200 and y.json()["fatura"]["status"] == "unpaid"
    assert await _bakiye(istemci, mb) == 1000.0
    h = (await istemci.get(f"{M}/hareketler", headers=mb)).json()["items"][0]
    assert h["tur"] == "ters_kayit" and h["tutar"] == 600.0 and h["fatura_id"] == f["id"] and h["bagli_id"] == s["hareket"]["id"]
    # Tahsilat ekranındaki (Ödemeler) silme ucu da aynı kuralı izler.
    s = await _ode(istemci, mb, f["id"], tutar="250")
    pid = next(p.id for p in await _odemeler(db_oturumu, f["id"]) if p.saglayici == "bakiye")
    y = await istemci.delete(f"/api/v1/odeme/kayit/{pid}", headers=yb)
    assert y.status_code == 200, y.text
    assert await _bakiye(istemci, mb) == 1000.0


async def test_iade_faturasi_bakiyeden_odeneni_bakiyeye_dondurur(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    yb, m = yonetici_basligi, _e("iadefat")
    mb = musteri_basligi(m)
    await _yukle(istemci, yb, m, "1000")
    f = await _fatura(istemci, yb, m, 600)
    await _ode(istemci, mb, f["id"])
    y = await istemci.post(f"{FATURA_YON}/{f['id']}/iade", json={"tutar": "200", "neden": "Kapsam daraldı"}, headers=yb)
    assert y.status_code == 200, y.text
    ozet = y.json()["fatura"]
    assert ozet["status"] == "paid" and ozet["bakiye"]["kalan"] == 0.0 and ozet["bakiye"]["fazla"] == 0.0
    assert await _bakiye(istemci, mb) == 600.0
    iade = [p for p in await _odemeler(db_oturumu, f["id"]) if p.durum == "iade"]
    assert [(p.saglayici, p.tutar) for p in iade] == [("bakiye", 200.0)]
    h = (await istemci.get(f"{M}/hareketler", headers=mb)).json()["items"][0]
    assert h["tur"] == "ters_kayit" and h["tutar"] == 200.0
    # Bakiyeye iade satırı silinirse bakiyeden geri alınır (yetmezse silme olmaz).
    await istemci.post(f"{Y}/iade", json={"hesap_email": m, "para_birimi": "TRY", "tutar": "500", "yontem": "havale"}, headers=yb)
    y = await istemci.delete(f"{FATURA_YON}/odemeler/{iade[0].id}", headers=yb)
    assert y.status_code == 409 and _kod(y) == "bakiye_yetersiz"
    await _yukle(istemci, yb, m, "100")
    y = await istemci.delete(f"{FATURA_YON}/odemeler/{iade[0].id}", headers=yb)
    assert y.status_code == 200 and await _bakiye(istemci, mb) == 0.0
    assert y.json()["fatura"]["bakiye"]["fazla"] == 200.0


# ---------------------------------------------------------------------------
# Yükleme talebi (müşteri bildirir → yönetici onay/ret) ve gelen kutusu
# ---------------------------------------------------------------------------
async def test_yukleme_talebi_onay_ret_ve_gelen_kutusu(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    from services import gelen_kutusu as gk

    yb, m = yonetici_basligi, _e("talep")
    mb = musteri_basligi(m)
    o = (await istemci.get(M, headers=mb)).json()
    ref = o["ayarlar"]["referans"]
    assert ref.startswith("BKY-") and len(ref) == 10 and o["banka"]["var"] in (True, False)
    assert (await istemci.get(M, headers=mb)).json()["ayarlar"]["referans"] == ref  # kalıcı
    y = await istemci.post(f"{M}/yukleme-talepleri", data={"tutar": "1500.50", "para_birimi": "TRY", "yontem": "havale",
                                                           "odeme_tarihi": date.today().isoformat(), "notu": "Ekim avansı"},
                           files={"dekont": (DEKONT[0], io.BytesIO(DEKONT[1]), DEKONT[2])}, headers=mb)
    assert y.status_code == 200, y.text
    t = y.json()["talep"]
    assert t["durum"] == "beklemede" and t["tutar"] == 1500.5 and t["dekont_var"] and t["referans"] == ref
    assert "hesap_email" not in t
    assert len(await _bildirimler(db_oturumu, "yonetici@test.dev", "bakiye_talebi")) >= 1
    # Gelen kutusu: yeni kaynak, "Onayla" mevcut ucu çağırır.
    assert "bakiye_yukleme" in gk.KAYNAKLAR and len(gk.KAYNAKLAR) == 17 and gk.KAYNAK_TANIMI["bakiye_yukleme"]
    liste = (await istemci.get("/api/v1/gelen-kutusu", params={"kaynak": "bakiye_yukleme"}, headers=yb)).json()
    oge = next(x for x in liste["ogeler"] if x["kimlik"] == t["id"])
    assert oge["durum"] == "yeni" and oge["hesap_email"] == m and oge["ek"]["tutar"] == 1500.5
    assert [e["anahtar"] for e in oge["eylemler"]] == ["onayla", "bakiye_reddet"]
    sayac = (await istemci.get("/api/v1/gelen-kutusu/sayac", headers=yb)).json()
    assert sayac["kaynaklar"]["bakiye_yukleme"] >= 1
    # Dekont: yönetici imzalı adres alır; başka müşteri talebin dekontunu göremez.
    assert (await istemci.get(f"{Y}/talepler/{t['id']}/dekont", headers=yb)).json()["adres"]
    assert (await istemci.get(f"{M}/yukleme-talepleri/{t['id']}/dekont", headers=mb)).status_code == 200
    assert (await istemci.get(f"{M}/yukleme-talepleri/{t['id']}/dekont", headers=musteri_basligi(_e()))).status_code == 404
    istek = oge["eylemler"][0]["istek"]
    y = await istemci.request(istek["yontem"], istek["yol"], json=istek["govde"], headers=yb)
    assert y.status_code == 200, y.text
    assert y.json()["talep"]["durum"] == "onaylandi" and y.json()["bakiye"] == 1500.5
    assert await _bakiye(istemci, mb) == 1500.5
    y = await istemci.request(istek["yontem"], istek["yol"], json={}, headers=yb)
    assert y.status_code == 409 and _kod(y) == "talep_beklemede_degil"
    assert len(await _bildirimler(db_oturumu, m, "bakiye_yukleme")) == 1
    liste = (await istemci.get("/api/v1/gelen-kutusu", params={"kaynak": "bakiye_yukleme", "durum": "hepsi"}, headers=yb)).json()
    assert next(x for x in liste["ogeler"] if x["kimlik"] == t["id"])["durum"] == "kapandi"
    # Onaylanan tutar talepten farklı olabilir (ör. banka masrafı); ret nedeni zorunlu; müşteri kendi talebini iptal eder.
    t2 = (await istemci.post(f"{M}/yukleme-talepleri", data={"tutar": "100", "para_birimi": "TRY", "yontem": "nakit"}, headers=mb)).json()["talep"]
    y = await istemci.post(f"{Y}/talepler/{t2['id']}/reddet", json={}, headers=yb)
    assert y.status_code == 400 and _kod(y) == "neden_gerekli"
    y = await istemci.post(f"{Y}/talepler/{t2['id']}/reddet", json={"neden": "Hesaba ulaşmadı"}, headers=yb)
    assert y.status_code == 200 and y.json()["talep"]["durum"] == "reddedildi"
    assert len(await _bildirimler(db_oturumu, m, "bakiye_yukleme")) == 2 and await _bakiye(istemci, mb) == 1500.5
    t3 = (await istemci.post(f"{M}/yukleme-talepleri", data={"tutar": "300", "para_birimi": "USD"}, headers=mb)).json()["talep"]
    assert (await istemci.post(f"{M}/yukleme-talepleri/{t3['id']}/iptal", json={}, headers=musteri_basligi(_e()))).status_code == 404
    y = await istemci.post(f"{M}/yukleme-talepleri/{t3['id']}/iptal", json={}, headers=mb)
    assert y.status_code == 200 and y.json()["talep"]["durum"] == "iptal"
    t4 = (await istemci.post(f"{M}/yukleme-talepleri", data={"tutar": "250", "para_birimi": "TRY"}, headers=mb)).json()["talep"]
    y = await istemci.post(f"{Y}/talepler/{t4['id']}/onayla", json={"tutar": "245", "notu": "Masraf düşüldü"}, headers=yb)
    assert y.status_code == 200 and y.json()["hareket"]["tutar"] == 245.0 and y.json()["talep"]["tutar"] == 250.0
    # Bekleyen talep sınırı.
    for _ in range(5):
        await istemci.post(f"{M}/yukleme-talepleri", data={"tutar": "10"}, headers=mb)
    y = await istemci.post(f"{M}/yukleme-talepleri", data={"tutar": "10"}, headers=mb)
    assert y.status_code == 409 and _kod(y) == "cok_fazla_bekleyen"
    # Yönetici listesi: bekleyenler + hesap.
    lst = (await istemci.get(f"{Y}/hesaplar", params={"q": m.split("@")[0]}, headers=yb)).json()
    assert [h["hesap_email"] for h in lst["hesaplar"]] == [m] and lst["hesaplar"][0]["bakiye"] == 1745.5
    assert sum(1 for x in lst["bekleyen_talepler"] if x["hesap_email"] == m) == 5


# ---------------------------------------------------------------------------
# Ön muhasebe: çift sayım yok
# ---------------------------------------------------------------------------
async def test_on_muhasebe_cift_sayim_yok(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    """Aynı dönemde yükleme (1000) + bakiyeden ödeme (600) + müşteriye iade (300): nakit akışında giriş BİR kez (1000),
    çıkış 300; kâr-zararda gelir BİR kez (600), iade gider DEĞİL; cari: avans alacaklı → kapanır."""
    from services import muhasebe as ms
    from services import muhasebe_kayit as mk

    yb, m = yonetici_basligi, _e("muhasebe")
    mb = musteri_basligi(m)
    banka = (await istemci.post(f"{MUH}/hesaplar", json={"tur": "banka", "ad": f"Avans bankası {uuid.uuid4().hex[:4]}",
                                                            "para_birimi": "TRY"}, headers=yb)).json()
    kasa = (await istemci.post(f"{MUH}/hesaplar", json={"tur": "kasa", "ad": f"Avans kasası {uuid.uuid4().hex[:4]}",
                                                           "para_birimi": "TRY"}, headers=yb)).json()
    assert banka.get("id") and kasa.get("id"), (banka, kasa)
    # Aktarım ayarının ham hali (başlangıç tarihi dahil) sonda aynen geri yazılır: başka test dosyaları saati sabitliyor,
    # bu testin "bugün"üyle kalan başlangıç tarihi onların ödemelerini aralık dışına iterdi.
    eski_satir = await mk.ayar_satiri(db_oturumu, ms.AJANS_KAPSAMI)
    eski_aktarim = eski_satir.aktarim if eski_satir is not None else None
    y = await istemci.put(f"{MUH}/ayarlar", json={"aktarim": {"odeme": {"acik": True, "banka_hesap_id": banka["id"],
                                                                         "nakit_hesap_id": kasa["id"]}}}, headers=yb)
    assert y.status_code == 200, y.text
    bugun = ms.bugun()
    bas, bit = date(bugun.year, bugun.month, 1), bugun

    async def anlik():
        await istemci.post(f"{MUH}/esitle", json={}, headers=yb)
        nakit = await mk.nakit_akisi(db_oturumu, ms.AJANS_KAPSAMI)
        ay = next((p for p in nakit["para_birimleri"] if p["para_birimi"] == "TRY"), {"gecmis": [{"giris": 0, "cikis": 0}]})["gecmis"][-1]
        kz = await mk.kar_zarar(db_oturumu, ms.AJANS_KAPSAMI, bas, bit)
        tr = next((p for p in kz["para_birimleri"] if p["para_birimi"] == "TRY"), {"toplam_gelir": 0, "toplam_gider": 0})
        return ay["giris"], ay["cikis"], tr["toplam_gelir"], tr["toplam_gider"]

    try:
        once = await anlik()
        await _yukle(istemci, yb, m, "1000")
        f = await _fatura(istemci, yb, m, 600)
        await _ode(istemci, mb, f["id"])
        sonra = await anlik()
        assert (sonra[0] - once[0], sonra[1] - once[1]) == (100000, 0)  # nakit: yalnız yükleme
        assert (sonra[2] - once[2], sonra[3] - once[3]) == (60000, 0)  # gelir: yalnız fatura (bir kez)
        await istemci.post(f"{Y}/iade", json={"hesap_email": m, "para_birimi": "TRY", "tutar": "300", "yontem": "havale"}, headers=yb)
        son = await anlik()
        assert (son[0] - sonra[0], son[1] - sonra[1]) == (0, 30000)  # iade: nakit çıkışı
        assert (son[2] - sonra[2], son[3] - sonra[3]) == (0, 0)  # gider DEĞİL
        # Tekrar eşitleme yeni kayıt üretmez.
        assert await anlik() == son
        db_oturumu.expire_all()
        from models.muhasebe import MuhasebeCariler, MuhasebeHareketleri as H

        cari = (await db_oturumu.execute(select(MuhasebeCariler).where(MuhasebeCariler.bagli_tur == "musteri_hesabi",
                                                                         MuhasebeCariler.bagli_id == m))).scalars().one()
        hs = (await db_oturumu.execute(select(H).where(H.cari_id == cari.id).order_by(H.id))).scalars().all()
        assert sorted((h.kaynak, h.tur, h.tutar, h.hesap_id or 0) for h in hs) == sorted([
            ("avans", "tahsilat", 100000, banka["id"]), ("odeme", "gelir", 60000, 0), ("avans", "odeme", 30000, banka["id"])])
        assert (await mk.cari_bakiyeleri(db_oturumu, ms.AJANS_KAPSAMI, [cari.id]))[cari.id] == -10000  # 100 TL avans yükümlülüğü
        assert await _bakiye(istemci, mb) == 100.0
        # Ödenen faturaya "ödemesi kaydedilmemiş" önerisi açılmadı (ödeme kaydı var).
        oneriler = (await istemci.get(f"{MUH}/oneriler", headers=yb)).json()["items"]
        assert not [o for o in oneriler if o.get("belge_no") == f["invoice_no"]]
        # Düzeltme ÖNERİ olarak gelir (otomatik deftere yazılmaz).
        await istemci.post(f"{Y}/duzeltme", json={"hesap_email": m, "para_birimi": "TRY", "tutar": "20", "gerekce": "Jest"}, headers=yb)
        await anlik()
        oneriler = (await istemci.get(f"{MUH}/oneriler", headers=yb)).json()["items"]
        d = [o for o in oneriler if o["kaynak"] == "avans_duzeltme" and o.get("cari") == cari.ad]
        assert len(d) == 1 and d[0]["tur"] == "gider" and d[0]["tutar"] == 2000
        # Yüklemenin ters kaydı → defterdeki tahsilat da ters çevrilir.
        yk = next(x for x in (await istemci.get(f"{Y}/hesap", params={"eposta": m}, headers=yb)).json()["hareketler"]["items"]
                  if x["tur"] == "iade")
        await istemci.post(f"{Y}/hareketler/{yk['id']}/ters", json={"gerekce": "Havale geri döndü"}, headers=yb)
        son2 = await anlik()
        assert (son2[0] - son2[1]) - (son[0] - son[1]) == 30000  # iade çıkışı ters kayıtla geri (net)
    finally:
        await istemci.put(f"{MUH}/ayarlar", json={"aktarim": {"odeme": {"acik": False}}}, headers=yb)
        db_oturumu.expire_all()
        satir = await mk.ayar_satiri(db_oturumu, ms.AJANS_KAPSAMI)
        if satir is not None:
            satir.aktarim = eski_aktarim
            await db_oturumu.commit()


# ---------------------------------------------------------------------------
# Otomatik ödeme ve düşük bakiye
# ---------------------------------------------------------------------------
async def test_otomatik_odeme_ayari(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    from services import cuzdan

    yb, m = yonetici_basligi, _e("oto")
    mb = musteri_basligi(m)
    eski = await _fatura(istemci, yb, m, 100)  # açılmadan önce kesilen fatura otomatik ödenmez
    await _yukle(istemci, yb, m, "500")
    y = await istemci.put(f"{M}/ayarlar", json={"otomatik_odeme": True}, headers=mb)
    assert y.status_code == 400 and _kod(y) == "onay_gerekli"
    y = await istemci.put(f"{M}/ayarlar", json={"otomatik_odeme": True, "onay": True}, headers=mb)
    assert y.status_code == 200 and y.json()["otomatik_odeme"] and y.json()["onay_metni_surumu"] == cuzdan.ONAY_METNI_SURUMU
    assert (await istemci.put(f"{M}/ayarlar", json={"otomatik_zaman": "yarin"}, headers=mb)).status_code == 400
    f1 = await _fatura(istemci, yb, m, 300)
    assert f1["status"] == "paid"  # kesilir kesilmez bakiyeden
    assert await _bakiye(istemci, mb) == 200.0
    f2 = await _fatura(istemci, yb, m, 400)
    assert f2["status"] == "unpaid"  # yetersiz, kısmi kapalı → hiç uygulanmaz, bildirilir
    bild = await _bildirimler(db_oturumu, m, "bakiye_harcama")
    assert any("Otomatik ödeme yapılamadı" in b.title for b in bild)
    # Zamanlı iş yeniden denemez (fatura başına bir kez); eski fatura hiç denenmez.
    from models.cuzdan import CuzdanOtomatikIzleri

    async def izler():
        db_oturumu.expire_all()
        return {i.fatura_id: i.sonuc for i in (await db_oturumu.execute(select(CuzdanOtomatikIzleri).where(
            CuzdanOtomatikIzleri.hesap_email == m))).scalars().all()}

    assert await izler() == {f1["id"]: "odendi", f2["id"]: "yetersiz"}
    await cuzdan.otomatik_odemeler(db_oturumu)
    assert await izler() == {f1["id"]: "odendi", f2["id"]: "yetersiz"}
    assert len([b for b in await _bildirimler(db_oturumu, m, "bakiye_harcama") if "yapılamadı" in b.title]) == 1
    assert (await istemci.get(f"{ENTITY}/{eski['id']}", headers=yb)).json()["status"] == "unpaid"
    # Kısmi açık: olan kadarı uygulanır.
    await istemci.put(f"{M}/ayarlar", json={"otomatik_kismi": True}, headers=mb)
    f3 = await _fatura(istemci, yb, m, 500)
    assert f3["status"] == "kismi_odendi" and await _bakiye(istemci, mb) == 0.0
    # Vadesinde: vadesi gelmemiş fatura zamanlı işe kalır, vadesi gelince ödenir.
    await _yukle(istemci, yb, m, "1000")
    await istemci.put(f"{M}/ayarlar", json={"otomatik_zaman": "vadesinde"}, headers=mb)
    f4 = await _fatura(istemci, yb, m, 100, due_date=(date.today() + timedelta(days=10)).isoformat())
    assert f4["status"] == "unpaid"
    await cuzdan.otomatik_odemeler(db_oturumu)
    assert (await istemci.get(f"{ENTITY}/{f4['id']}", headers=yb)).json()["status"] == "unpaid"
    await istemci.put(f"{ENTITY}/{f4['id']}", json={"due_date": date.today().isoformat()}, headers=yb)
    assert (await istemci.get(f"{ENTITY}/{f4['id']}", headers=yb)).json()["status"] == "paid"
    # Kapatınca yeni fatura denenmez.
    await istemci.put(f"{M}/ayarlar", json={"otomatik_odeme": False}, headers=mb)
    f5 = await _fatura(istemci, yb, m, 10)
    assert f5["status"] == "unpaid"


async def test_dusuk_bakiye_bildirimi_bir_kez(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    yb, m = yonetici_basligi, _e("dusuk")
    mb = musteri_basligi(m)
    await _yukle(istemci, yb, m, "1000")
    y = await istemci.put(f"{M}/ayarlar", json={"dusuk_esikler": {"TRY": "500"}}, headers=mb)
    assert y.status_code == 200
    assert (await istemci.put(f"{M}/ayarlar", json={"dusuk_esikler": {"XYZ": "5"}}, headers=mb)).status_code == 400
    f = await _fatura(istemci, yb, m, 2000)
    await _ode(istemci, mb, f["id"], tutar="600")  # 400 < 500 → bildirim
    assert len(await _bildirimler(db_oturumu, m, "bakiye_dusuk")) == 1
    await _ode(istemci, mb, f["id"], tutar="100")  # hâlâ altında → yeni bildirim yok
    assert len(await _bildirimler(db_oturumu, m, "bakiye_dusuk")) == 1
    o = (await istemci.get(M, headers=mb)).json()["bakiyeler"][0]
    assert o["dusuk_esik"] == 500.0 and o["dusuk_uyari"] is True
    await _yukle(istemci, yb, m, "500")  # 800 ≥ 500 → işaret sıfırlanır
    await _ode(istemci, mb, f["id"], tutar="400")  # 400 < 500 → ikinci iniş, ikinci bildirim
    assert len(await _bildirimler(db_oturumu, m, "bakiye_dusuk")) == 2
    await istemci.put(f"{M}/ayarlar", json={"dusuk_esikler": {"TRY": None}}, headers=mb)
    await _ode(istemci, mb, f["id"], tutar="100")
    assert len(await _bildirimler(db_oturumu, m, "bakiye_dusuk")) == 2


# ---------------------------------------------------------------------------
# Ekstre, girişsiz ödeme sayfası, banka bilgisi
# ---------------------------------------------------------------------------
async def test_ekstre_pdf_csv_ve_odeme_sayfasi(istemci, yonetici_basligi, musteri_basligi):
    from services.pdf_belge import pdf_metni

    yb, m = yonetici_basligi, _e("ekstre")
    mb = musteri_basligi(m)
    await _yukle(istemci, yb, m, "1000")
    f = await _fatura(istemci, yb, m, 250)
    await _ode(istemci, mb, f["id"])
    y = await istemci.get(f"{M}/ekstre", params={"bicim": "pdf", "dil": "tr"}, headers=mb)
    assert y.status_code == 200 and y.headers["content-type"] == "application/pdf" and y.content[:4] == b"%PDF"
    metin = pdf_metni(y.content)
    assert "BAKİYE EKSTRESİ" in metin and f["invoice_no"] in metin and "hukuki danışmanlık" in metin
    y = await istemci.get(f"{M}/ekstre", params={"bicim": "pdf", "dil": "ar"}, headers=mb)
    assert y.status_code == 200 and y.content[:4] == b"%PDF"
    y = await istemci.get(f"{M}/ekstre", params={"bicim": "csv", "dil": "en"}, headers=mb)
    assert y.status_code == 200 and y.headers["content-type"].startswith("text/csv")
    satirlar = y.content.decode("utf-8").lstrip("﻿").splitlines()
    assert satirlar[0].startswith("Date,Transaction") and "Top-up" in satirlar[2] and "Invoice payment" in satirlar[3]
    assert satirlar[-1].endswith("750.00,TRY")
    assert (await istemci.get(f"{M}/ekstre", params={"bicim": "xls"}, headers=mb)).status_code == 400
    y = await istemci.get(f"{Y}/ekstre", params={"eposta": m, "bicim": "csv"}, headers=yb)
    assert y.status_code == 200 and "Yükleme" in y.content.decode("utf-8")
    # Girişsiz ödeme sayfası (oturum varsa): yalnız faturanın sahibi bakiyeyi görür.
    f2 = await _fatura(istemci, yb, m, 100)
    jeton = (await istemci.post(f"/api/v1/faturalarim/{f2['id']}/odeme-baglantisi", headers=mb)).json()["adres"].rsplit("/", 1)[1]
    b = (await istemci.get(f"{M}/odeme/{jeton}", headers=mb)).json()
    assert b["fatura_id"] == f2["id"] and b["bakiye"] == 750.0 and b["kalan"] == 100.0 and b["uygulanabilir"]
    assert (await istemci.get(f"{M}/odeme/{jeton}", headers=musteri_basligi(_e()))).status_code == 404
    assert (await istemci.get(f"{M}/odeme/{jeton}")).status_code == 401


async def test_banka_bilgisi_ayari(istemci, yonetici_basligi, musteri_basligi):
    yb = yonetici_basligi
    y = await istemci.put(f"{Y}/ayarlar", json={"iban": "TR00 1234"}, headers=yb)
    assert y.status_code == 400 and _kod(y) == "iban_gecersiz"
    eski = (await istemci.get(f"{Y}/ayarlar", headers=yb)).json()["kayitli"]
    try:
        y = await istemci.put(f"{Y}/ayarlar", json={"banka_adi": "Örnek Bankası", "aciklama": "Açıklamaya referans kodunu yazın"},
                              headers=yb)
        assert y.status_code == 200 and y.json()["kayitli"]["banka_adi"] == "Örnek Bankası"
        o = (await istemci.get(M, headers=musteri_basligi(_e()))).json()
        assert o["banka"]["banka_adi"] == "Örnek Bankası" and "referans" in o["banka"]["aciklama"]
    finally:
        await istemci.put(f"{Y}/ayarlar", json=eski, headers=yb)


# ---------------------------------------------------------------------------
# Kataloglar, otomasyon bağlamı, etiketler
# ---------------------------------------------------------------------------
def _duz(d, on=""):
    for k, v in d.items():
        if isinstance(v, dict):
            yield from _duz(v, f"{on}{k}.")
        else:
            yield f"{on}{k}", v


def _ek(ad):
    return {dil: json.loads((EK / ad / f"{dil}.json").read_text(encoding="utf-8")) for dil in DILLER}


def test_kataloglar_ve_etiketler():
    from services import bildirim_tercih as bt
    from services import hesap_ekibi as he
    from services import muhasebe as ms
    from services import otomasyon_kural as ok
    from services import webhook, zamanli

    for olay in ("bakiye_talebi", "bakiye_yukleme", "bakiye_harcama", "bakiye_dusuk", "bakiye_iade"):
        assert bt.OLAYLAR[olay]["tetikleniyor"] is True
        for dil, p in _ek("bildirim").items():
            assert p["bildirim"]["olay"][olay].strip(), (dil, olay)
    assert bt.OLAYLAR["bakiye_talebi"]["roller"] == ("admin",)
    assert all(he.OLAY_IZNI[o] == "faturalar" for o in ("bakiye_yukleme", "bakiye_harcama", "bakiye_dusuk", "bakiye_iade"))
    for olay in ("bakiye.yuklendi", "bakiye.harcandi"):
        assert olay in webhook.OLAY_SOZLUGU and webhook.OLAY_SOZLUGU[olay].musteri
        assert olay in ok.OLAY_SOZLUGU and ok.OLAY_SOZLUGU[olay].musteri
        for dil, p in _ek("otomasyon").items():
            assert p["otomasyon"]["olay"][olay.replace(".", "_")].strip() and p["otomasyon"]["olayAciklama"][olay.replace(".", "_")]
        for dil, p in _ek("apiErisimi").items():
            assert p["apiErisimi"]["olay"][olay.replace(".", "_")].strip(), dil
    assert ok.olay_nesneleri("bakiye.harcandi", False) == ("bakiye", "fatura", "hesap", "kisi", "olay")
    for dil, p in _ek("otomasyon").items():
        assert p["otomasyon"]["nesne"]["bakiye"] and all(p["otomasyon"]["alan"][a.ad] for a in ok.NESNELER["bakiye"]), dil
    assert "cuzdan_otomatik_odeme" in zamanli.GOREV_ADLARI and zamanli.GOREV_ADLARI[-1] == "aylik_site_analizi"
    for dil, p in _ek("siteBakim").items():
        assert p["siteBakim"]["zamanli"]["gorev"]["cuzdan_otomatik_odeme"] and p["siteBakim"]["zamanli"]["ne"]["cuzdan_otomatik_odeme"]
    assert {"avans", "avans_duzeltme"} <= set(ms.OTOMATIK_KAYNAKLAR) and "avans_duzeltme" in ms.HEP_ONERI_KAYNAKLARI
    for dil, p in _ek("onMuhasebe").items():
        assert p["onMuhasebe"]["kaynak"]["avans"] and p["onMuhasebe"]["kaynak"]["avans_duzeltme"], dil
    for dil, p in _ek("gelenKutusu").items():
        assert p["gelenKutusu"]["kaynak"]["bakiye_yukleme"] and p["gelenKutusu"]["eylem"]["bakiye_reddet"], dil
    for dil, p in _ek("fatura").items():
        assert p["fatura"]["yontem"]["bakiye"], dil
    for dil, p in _ek("denetim").items():
        assert all(p["denetim"]["tablo"][t] for t in ("cuzdan_hareketleri", "cuzdan_yukleme_talepleri", "cuzdan_ayarlari",
                                                      "cuzdan_hesaplari")), dil
    from services.haftalik_ozet import GELEN_KAYNAK_ADLARI

    assert GELEN_KAYNAK_ADLARI["bakiye_yukleme"]


def test_cuzdan_ek_paketi_yedi_dilde_ayni_anahtarlar_ve_hukuki_not():
    import re

    yt = re.compile(r"\{\{\s*(\w+)\s*\}\}")
    paketler = {dil: dict(_duz(p["cuzdan"])) for dil, p in _ek("cuzdan").items()}
    tr = paketler["tr"]
    for dil, p in paketler.items():
        assert set(p) == set(tr), (dil, sorted(set(tr) ^ set(p))[:5])
        assert all(isinstance(v, str) and v.strip() for v in p.values()), dil
        for k, v in p.items():
            assert set(yt.findall(v)) == set(yt.findall(tr[k])), (dil, k)
            assert "count" not in yt.findall(v), (dil, k)
    for dil in DILLER[1:]:
        ayni = [k for k, v in paketler[dil].items() if v == tr[k] and len(v) > 12 and "IBAN" not in v]
        assert not ayni, (dil, ayni[:5])
    assert "hukuki danışmanlık değildir" in tr["hukuki.not"] and "elektronik para" in tr["hukuki.metin"]
    assert "6493" not in tr["hukuki.metin"]  # kanun numarası arayüzde değil, belge başında (bilgilendirme)


async def test_otomasyon_baglami_bakiye_harcandi(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    from models.cuzdan import CuzdanHareketleri
    from services import otomasyon

    yb, m = yonetici_basligi, _e("baglam")
    await _yukle(istemci, yb, m, "100")
    f = await _fatura(istemci, yb, m, 40)
    s = await _ode(istemci, musteri_basligi(m), f["id"])
    h = (await db_oturumu.execute(select(CuzdanHareketleri).where(CuzdanHareketleri.id == s["hareket"]["id"]))).scalars().one()
    b = await otomasyon.baglam_kur(db_oturumu, "bakiye.harcandi", {"hareket_id": h.id, "fatura_id": f["id"]}, m, False)
    assert b["bakiye"]["tutar"] == 40.0 and b["bakiye"]["bakiye"] == 60.0 and b["fatura"]["durum"] == "paid"
    assert b["kisi"]["email"] == m
    # Başka hesabın kuralı bu hareketi göremez.
    assert await otomasyon.baglam_kur(db_oturumu, "bakiye.harcandi", {"hareket_id": h.id}, _e(), False) is None
    n = (await db_oturumu.execute(select(func.count(CuzdanHareketleri.id)).where(CuzdanHareketleri.hesap_email == m))).scalar()
    assert n == 2
