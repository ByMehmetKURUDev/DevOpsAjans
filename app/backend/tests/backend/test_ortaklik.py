"""Faz 5K — indirim kodları ve ortaklık (referans) programı.

Kapsam: kod biçimi (büyük/küçük harf, Türkçe İ/ı), geçerlilik (tarih, toplam ve kişi başı sınır, en az tutar,
kapsam, para birimi, pasif), teklif/fatura toplamı ve PDF satırı ("İndirim (KOD)" / "Discount (KOD)"), kodun
yeniden uygulanması ve kaldırılması, doğrulama ucunun hız sınırı; başvuru → onay → `?ref=` tıklaması → form →
CRM adayı + atıf → teklif kabul → fatura ödendi → komisyon (KDV hariç × oran, TEK) → iade → oranlı ters kayıt,
ödeme geri alınınca kalanın ters kaydı; kendi kendine referans reddi; ilk/son atıf ayarı; ödeme talebi (IBAN,
kart no reddi, en az tutar, ödendi + dekont, ret); yetkiler; gelen kutusu kaynağı, haftalık özet, olay katalogları;
komisyon kuralı (ilk satış %X — teklif / kod / sitedeki "Teklif al" akışı; N ay içindeki abonelik faturası %Y; sonraki
başka satış komisyonsuz); Site Analizi, modül talebi ve kayıt sonrası referans; bekleme süresinin zamanlı iş ve panel
açılışıyla olgunlaşması; CSV (formül enjeksiyonu, IBAN maskeli); denetim kaydında IBAN'ın tam değeri yok.
"""

import io
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

YON = "/api/v1/ortaklik-yonetim"
ACIK = "/api/v1/ortaklik"
BEN = "/api/v1/ortakligim"
KOD_YON = "/api/v1/indirim-kodu-yonetim"
KOD_ACIK = "/api/v1/indirim-kodu"
TEKLIF = "/api/v1/teklif-yonetim"
TEKLIF_ACIK = "/api/v1/teklif"
FATURA = "/api/v1/entities/invoices"
FATURA_YON = "/api/v1/fatura-yonetim"

KALEMLER = [
    {"aciklama": "Kurumsal web sitesi", "adet": 1, "birim_fiyat": 1000, "kdv_orani": 20},
    {"aciklama": "Eğitim", "adet": 1, "birim_fiyat": 200, "kdv_orani": 10},
]


def _e(on: str = "k") -> str:
    return f"{on}-{uuid.uuid4().hex[:10]}@test.dev"


def _kod(on: str = "YAZ") -> str:
    return f"{on}{uuid.uuid4().hex[:6].upper()}"


@pytest.fixture(autouse=True)
def _sinirlar():
    from routers import fiyatlandirma, indirim_kodlari, inquiries, ortaklik, teklifler
    from services import ortaklik as servis

    for r in (indirim_kodlari, inquiries, ortaklik, fiyatlandirma):
        r.hiz_sinirlarini_temizle()
    teklifler.hiz_siniri.temizle()
    servis.onbellegi_temizle()
    yield


async def _kod_ac(istemci, baslik, beklenen=200, **g):
    veri = {"kod": _kod(), "tur": "yuzde", "deger": 10, **g}
    y = await istemci.post(KOD_YON, json=veri, headers=baslik)
    assert y.status_code == beklenen, y.text
    return y.json()


async def _teklif(istemci, baslik, beklenen=200, **g):
    veri = {"baslik": "Web sitesi", "kalemler": KALEMLER, "para_birimi": "TRY", "hesap_email": _e("musteri"), **g}
    y = await istemci.post(TEKLIF, json=veri, headers=baslik)
    assert y.status_code == beklenen, y.text
    return y.json()


async def _ayar(istemci, baslik, **g):
    y = await istemci.put(f"{YON}/ayarlar", json=g, headers=baslik)
    assert y.status_code == 200, y.text
    return y.json()


async def _basvur(istemci, eposta, **g):
    veri = {"ad": "Can Yıldız", "eposta": eposta, "web": "canyildiz.dev", "tanitim": "Blog ve YouTube kanalımda.",
            "kosullar_kabul": True, "dil": "tr", **g}
    return await istemci.post(f"{ACIK}/basvuru", json=veri)


async def _onayli_ortak(istemci, baslik, db, **karar):
    from models.ortaklik import Ortaklar

    eposta = _e("ortak")
    y = await _basvur(istemci, eposta)
    assert y.status_code == 200 and y.json() == {"ok": True}, y.text
    o = (await db.execute(select(Ortaklar).where(Ortaklar.eposta == eposta))).scalars().first()
    y = await istemci.post(f"{YON}/ortaklar/{o.id}/karar", json={"karar": "onay", **karar}, headers=baslik)
    assert y.status_code == 200, y.text
    return y.json()


async def _kabul_ettir(istemci, baslik, teklif_id):
    y = await istemci.post(f"{TEKLIF}/{teklif_id}/gonder", json={}, headers=baslik)
    jeton = y.json()["baglanti"].rsplit("/", 1)[1]
    y = await istemci.post(f"{TEKLIF_ACIK}/{jeton}/karar", json={"sonuc": "kabul", "ad_soyad": "Ayşe Yılmaz"})
    assert y.status_code == 200 and y.json()["durum"] == "kabul", y.text
    return (await istemci.get(f"{TEKLIF}/{teklif_id}", headers=baslik)).json()


async def _ode(istemci, baslik, fatura_id, tutar):
    y = await istemci.post(f"{FATURA_YON}/{fatura_id}/odemeler", data={"tutar": str(tutar), "yontem": "havale"}, headers=baslik)
    assert y.status_code == 200, y.text
    return y.json()


async def _komisyonlar(db, ortak_id):
    from models.ortaklik import OrtakKomisyonlari

    db.expire_all()
    return list((await db.execute(select(OrtakKomisyonlari).where(OrtakKomisyonlari.ortak_id == ortak_id)
                                  .order_by(OrtakKomisyonlari.id))).scalars().all())


# ---------------------------------------------------------------------------
# Kod biçimi
# ---------------------------------------------------------------------------
def test_kod_anahtari_buyuk_kucuk_ve_turkce_i():
    from services.indirim_kodlari import bicim_gecerli, kod_anahtari, kod_gorunen

    assert kod_anahtari("kış2026") == kod_anahtari("KIŞ2026") == kod_anahtari("KİŞ2026") == kod_anahtari("kiş2026")
    assert kod_anahtari("kış2026") != kod_anahtari("kis2026")  # ş ≠ s
    assert kod_anahtari("İndirim") == kod_anahtari("INDIRIM") == kod_anahtari("indırım") == kod_anahtari("İNDİRİM".lower())
    assert kod_gorunen("indirim10") == "İNDİRİM10" and kod_gorunen("kış") == "KIŞ"
    assert kod_anahtari(" yaz 2026 ") == "YAZ2026"
    assert bicim_gecerli("YAZ-2026_A") and not bicim_gecerli("ab") and not bicim_gecerli("YAZ!2026") and not bicim_gecerli("x" * 33)


async def test_kod_crud_benzersiz_ad_alani_ve_dogrulamalar(istemci, yonetici_basligi):
    k = await _kod_ac(istemci, yonetici_basligi, kod="sonbahar" + uuid.uuid4().hex[:4])
    assert k["kod"].startswith("SONBAHAR") and k["kapsam"] == ["teklif", "fatura", "paket"] and k["kullanim"] == 0
    # Aynı anahtar (İ/ı katlanmış, küçük harf) ikinci kez açılamaz.
    y = await istemci.post(KOD_YON, json={"kod": k["kod"].lower(), "tur": "yuzde", "deger": 5}, headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "kod_kullaniliyor"
    for govde, kod in [
        ({"kod": _kod(), "tur": "yuzde", "deger": 120}, "deger_gecersiz"),
        ({"kod": _kod(), "tur": "sabit", "deger": 100}, "para_birimi_gerekli"),
        ({"kod": _kod(), "tur": "x", "deger": 1}, "tur_gecersiz"),
        ({"kod": _kod(), "tur": "yuzde", "deger": 5, "baslangic": "2026-10-10", "bitis": "2026-10-01"}, "tarih_gecersiz"),
        ({"kod": _kod(), "tur": "yuzde", "deger": 5, "kapsam": []}, "kapsam_gerekli"),
        ({"kod": "a!", "tur": "yuzde", "deger": 5}, "kod_gecersiz"),
    ]:
        y = await istemci.post(KOD_YON, json=govde, headers=yonetici_basligi)
        assert y.status_code == 400 and y.json()["detail"]["kod"] == kod, (govde, y.text)


# ---------------------------------------------------------------------------
# Teklif / fatura toplamı ve PDF satırı
# ---------------------------------------------------------------------------
async def test_teklif_yuzde_kod_toplam_ve_pdf_satiri(istemci, yonetici_basligi, db_oturumu):
    from services.pdf_belge import pdf_metni

    k = await _kod_ac(istemci, yonetici_basligi, deger=10)
    t = await _teklif(istemci, yonetici_basligi, indirim_kodu=k["kod"].lower())
    # Matrah: %20 → 1000, %10 → 200; indirim %10: 100 + 20 (oran başına).
    ozet = t["ozet"]
    assert ozet["ara_toplam"] == 1080.0 and ozet["indirim_toplam"] == 120.0
    assert ozet["kdv_toplam"] == 198.0 and ozet["genel_toplam"] == 1278.0
    assert ozet["kdv_dokumu"] == [{"oran": 10.0, "matrah": 180.0, "kdv": 18.0}, {"oran": 20.0, "matrah": 900.0, "kdv": 180.0}]
    satirlar = [x for x in t["kalemler"] if x.get("indirim_kodu")]
    assert [x["aciklama"] for x in satirlar] == [f"İndirim ({k['kod']}) — KDV %10", f"İndirim ({k['kod']}) — KDV %20"]
    assert t["indirim_kodu"] == k["kod"]
    pdf = await istemci.get(f"{TEKLIF}/{t['id']}/pdf", headers=yonetici_basligi)
    assert pdf.status_code == 200 and f"İndirim ({k['kod']})" in pdf_metni(pdf.content)
    pdf_en = await istemci.get(f"{TEKLIF}/{t['id']}/pdf?dil=en", headers=yonetici_basligi)
    assert f"Discount ({k['kod']})" in pdf_metni(pdf_en.content)
    # Kullanım sayıldı; istemcinin uydurduğu indirim satırı atılır, kod yeniden uygulanır.
    kod = next(x for x in (await istemci.get(KOD_YON, headers=yonetici_basligi)).json() if x["id"] == k["id"])
    assert kod["kullanim"] == 1
    sahte = KALEMLER[:1] + [{"aciklama": "İndirim (X)", "adet": 1, "birim_fiyat": -999, "kdv_orani": 20, "indirim_kodu": "X"}]
    y = await istemci.put(f"{TEKLIF}/{t['id']}", json={"kalemler": sahte}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["ozet"]["ara_toplam"] == 900.0  # 1000 − %10
    # Kodu kaldır: satır gider, kullanım silinir.
    y = await istemci.put(f"{TEKLIF}/{t['id']}", json={"indirim_kodu": ""}, headers=yonetici_basligi)
    assert y.json()["indirim_kodu"] is None and y.json()["ozet"]["genel_toplam"] == 1200.0
    kod = next(x for x in (await istemci.get(KOD_YON, headers=yonetici_basligi)).json() if x["id"] == k["id"])
    assert kod["kullanim"] == 0


async def test_fatura_sabit_kod_ve_yeniden_uygulama(istemci, yonetici_basligi):
    k = await _kod_ac(istemci, yonetici_basligi, tur="sabit", deger=300, para_birimi="TRY")
    musteri = _e("fatura")
    veri = {"invoice_no": f"INV-{uuid.uuid4().hex[:6]}", "client_email": musteri, "currency": "TRY", "status": "unpaid",
            "kalemler": KALEMLER, "indirim_kodu": k["kod"]}
    y = await istemci.post(FATURA, json=veri, headers=yonetici_basligi)
    assert y.status_code == 201, y.text
    f = y.json()
    # 300 TL (KDV hariç) matrah payıyla: 1000/1200 → 250, 200/1200 → 50.
    satirlar = {x["kdv_orani"]: x["birim_fiyat"] for x in f["kalemler"] if x.get("indirim_kodu")}
    assert satirlar == {10.0: -50.0, 20.0: -250.0} and f["ara_toplam"] == 900.0 and f["amount"] == 1065.0
    assert f["indirim_kodu"] == k["kod"]
    # Kalem düzenlemesi (kod gönderilmeden): kayıttaki kod yeni kalemlere uygulanır.
    y = await istemci.put(f"{FATURA}/{f['id']}", json={"kalemler": KALEMLER[:1]}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["ara_toplam"] == 700.0 and y.json()["amount"] == 840.0
    # Para birimi uymayan sabit kod uygulanmaz.
    k2 = await _kod_ac(istemci, yonetici_basligi, tur="sabit", deger=10, para_birimi="USD")
    y = await istemci.put(f"{FATURA}/{f['id']}", json={"indirim_kodu": k2["kod"]}, headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "kod_para_birimi"
    # Kalemsiz (tek tutarlı) faturaya kod uygulanamaz.
    y = await istemci.post(FATURA, json={"invoice_no": "TT-1", "client_email": musteri, "amount": 100, "indirim_kodu": k["kod"]},
                           headers=yonetici_basligi)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "kalem_gerekli"


async def test_kod_gecerliligi_tarih_sinir_en_az_kapsam_pasif(istemci, yonetici_basligi):
    bugun = date.today()
    gelecek = await _kod_ac(istemci, yonetici_basligi, baslangic=(bugun + timedelta(days=5)).isoformat())
    gecmis = await _kod_ac(istemci, yonetici_basligi, bitis=(bugun - timedelta(days=2)).isoformat())
    en_az = await _kod_ac(istemci, yonetici_basligi, en_az_tutar=5000, para_birimi="TRY")
    yalniz_fatura = await _kod_ac(istemci, yonetici_basligi, kapsam=["fatura"])
    pasif = await _kod_ac(istemci, yonetici_basligi, aktif=False)
    for k, kod in [(gelecek, "kod_baslamadi"), (gecmis, "kod_suresi_doldu"), (en_az, "kod_en_az_tutar"),
                   (yalniz_fatura, "kod_kapsam_disi"), (pasif, "kod_pasif")]:
        y = await istemci.post(TEKLIF, json={"baslik": "x", "kalemler": KALEMLER, "hesap_email": _e(), "indirim_kodu": k["kod"]},
                               headers=yonetici_basligi)
        assert y.status_code == 409 and y.json()["detail"]["kod"] == kod, (k["kod"], y.text)
    y = await istemci.post(TEKLIF, json={"baslik": "x", "kalemler": KALEMLER, "hesap_email": _e(), "indirim_kodu": "YOKBOYLE1"},
                           headers=yonetici_basligi)
    assert y.status_code == 404 and y.json()["detail"]["kod"] == "kod_yok"
    # En az tutar ara toplamla (KDV hariç) karşılaştırılır: 1200 < 5000; 6000 geçer.
    y = await istemci.post(TEKLIF, json={"baslik": "x", "kalemler": [{"aciklama": "Büyük iş", "adet": 1, "birim_fiyat": 6000}],
                                         "hesap_email": _e(), "indirim_kodu": en_az["kod"]}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["ozet"]["genel_toplam"] == 5400.0


async def test_toplam_ve_kisi_basi_sinir_ret_canli_sayim(istemci, yonetici_basligi):
    k = await _kod_ac(istemci, yonetici_basligi, toplam_sinir=2, kisi_basi_sinir=1)
    ayni = _e("ayni")
    t1 = await _teklif(istemci, yonetici_basligi, hesap_email=ayni, indirim_kodu=k["kod"])
    y = await istemci.post(TEKLIF, json={"baslik": "x", "kalemler": KALEMLER, "hesap_email": ayni.upper(), "indirim_kodu": k["kod"]},
                           headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "kod_kisi_siniri"
    await _teklif(istemci, yonetici_basligi, indirim_kodu=k["kod"])
    y = await istemci.post(TEKLIF, json={"baslik": "x", "kalemler": KALEMLER, "hesap_email": _e(), "indirim_kodu": k["kod"]},
                           headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "kod_tukendi"
    # Reddedilen teklif sayımdan düşer: kişi yeniden kullanabilir, toplamda da yer açılır.
    y = await istemci.post(f"{TEKLIF}/{t1['id']}/gonder", json={}, headers=yonetici_basligi)
    jeton = y.json()["baglanti"].rsplit("/", 1)[1]
    assert (await istemci.post(f"{TEKLIF_ACIK}/{jeton}/karar", json={"sonuc": "red", "not": "Bütçe yok"})).status_code == 200
    await _teklif(istemci, yonetici_basligi, hesap_email=ayni, indirim_kodu=k["kod"])


async def test_revizyon_kodu_tasir_kullanim_tek(istemci, yonetici_basligi):
    k = await _kod_ac(istemci, yonetici_basligi, toplam_sinir=1)
    t = await _teklif(istemci, yonetici_basligi, indirim_kodu=k["kod"])
    await istemci.post(f"{TEKLIF}/{t['id']}/gonder", json={}, headers=yonetici_basligi)
    y = await istemci.post(f"{TEKLIF}/{t['id']}/revize", headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["indirim_kodu"] == k["kod"]
    kod = next(x for x in (await istemci.get(KOD_YON, headers=yonetici_basligi)).json() if x["id"] == k["id"])
    assert kod["kullanim"] == 1
    # Sürüm düzenlenince kod (sınır dolu olsa da) kendi kullanımıyla yeniden uygulanır.
    y = await istemci.put(f"{TEKLIF}/{y.json()['id']}", json={"kalemler": KALEMLER[:1]}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["ozet"]["ara_toplam"] == 900.0


async def test_onizleme_ve_kullanilmis_kod_silinemez(istemci, yonetici_basligi):
    k = await _kod_ac(istemci, yonetici_basligi, deger=50)
    y = await istemci.post(f"{KOD_YON}/onizle", json={"kod": k["kod"], "kalemler": KALEMLER[:1], "para_birimi": "TRY"},
                           headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["indirim"] == 500.0 and y.json()["genel_toplam"] == 600.0
    await _teklif(istemci, yonetici_basligi, indirim_kodu=k["kod"])
    y = await istemci.delete(f"{KOD_YON}/{k['id']}", headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "kullanilmis_kod_silinemez"
    y = await istemci.put(f"{KOD_YON}/{k['id']}", json={"kod": _kod()}, headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "kullanilmis_kod_adi"
    y = await istemci.put(f"{KOD_YON}/{k['id']}", json={"aktif": False}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["durum"] == "pasif"


async def test_dogrulama_ucu_hiz_siniri_ve_asgari_bilgi(istemci, yonetici_basligi):
    k = await _kod_ac(istemci, yonetici_basligi, toplam_sinir=5)
    y = await istemci.post(f"{KOD_ACIK}/dogrula", json={"kod": k["kod"].lower()})
    assert y.status_code == 200 and y.json()["gecerli"] is True and y.json()["tur"] == "indirim"
    assert "toplam_sinir" not in json.dumps(y.json()) and "kullanim" not in y.json()["indirim"]
    for _ in range(9):
        y = await istemci.post(f"{KOD_ACIK}/dogrula", json={"kod": "TAHMIN" + uuid.uuid4().hex[:4]})
        assert y.status_code == 200 and y.json() == {"gecerli": False}
    y = await istemci.post(f"{KOD_ACIK}/dogrula", json={"kod": k["kod"]})
    assert y.status_code == 429 and y.json()["detail"]["kod"] == "cok_hizli"


# ---------------------------------------------------------------------------
# Ortaklık: başvuru, karar, referans, komisyon
# ---------------------------------------------------------------------------
async def test_program_ve_basvuru_dogrulamalari(istemci, yonetici_basligi, db_oturumu):
    from models.ortaklik import Ortaklar

    y = await istemci.get(f"{ACIK}/program?dil=en")
    assert y.status_code == 200 and y.json()["cerez_gun"] == 30 and y.json()["kosullar"] is None
    await _ayar(istemci, yonetici_basligi, kosullar={"tr": "Koşul metni: komisyon %10.", "en": "Terms: 10% commission."})
    g = (await istemci.get(f"{ACIK}/program?dil=en")).json()
    assert g["kosullar"] == "Terms: 10% commission." and g["kosullar_surumu"].startswith("k-")
    for govde, kod in [({"kosullar_kabul": False}, "kosullar_gerekli"), ({"eposta": "x"}, "eposta_gecersiz"),
                       ({"tanitim": ""}, "tanitim_gerekli"), ({"web": "bir site"}, "web_gecersiz")]:
        govde = dict(govde)
        y = await _basvur(istemci, govde.pop("eposta", _e()), **govde)
        assert y.status_code == 400 and y.json()["detail"]["kod"] == kod, govde
    eposta = _e("basvuru")
    assert (await _basvur(istemci, eposta.upper(), pazarlama_izni=True)).status_code == 200
    o = (await db_oturumu.execute(select(Ortaklar).where(Ortaklar.eposta == eposta))).scalars().first()
    assert o.durum == "beklemede" and o.web == "https://canyildiz.dev" and o.pazarlama_izni_at is not None
    assert o.kosullar_kabul_at is not None and o.kosullar_surumu.startswith("k-")
    # Bal küpü: kayıt yok.
    from routers import ortaklik as r

    r.hiz_sinirlarini_temizle()
    bot = _e("bot")
    assert (await _basvur(istemci, bot, web_sitesi="http://spam")).json() == {"ok": True}
    assert (await db_oturumu.execute(select(Ortaklar).where(Ortaklar.eposta == bot))).scalars().first() is None
    # Gelen kutusunda; yanıtlanabilir, eylemler onayla/reddet.
    y = await istemci.get(f"/api/v1/gelen-kutusu?kaynak=ortak_basvurusu", headers=yonetici_basligi)
    oge = next(x for x in y.json()["ogeler"] if x["kimlik"] == o.id)
    assert oge["durum"] == "yeni" and {e["anahtar"] for e in oge["eylemler"]} == {"onayla", "reddet"}
    # Ret → kapandı; e-posta bildirimi kaydı.
    y = await istemci.post(f"{YON}/ortaklar/{o.id}/karar", json={"karar": "ret", "neden": "Kitle uyumsuz"}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["durum"] == "reddedildi"
    y = await istemci.get(f"/api/v1/gelen-kutusu?kaynak=ortak_basvurusu&durum=hepsi", headers=yonetici_basligi)
    assert next(x for x in y.json()["ogeler"] if x["kimlik"] == o.id)["durum"] == "kapandi"
    await _ayar(istemci, yonetici_basligi, kosullar={})


async def test_basvuru_hiz_siniri(istemci):
    for _ in range(5):
        assert (await _basvur(istemci, _e())).status_code == 200
    y = await _basvur(istemci, _e())
    assert y.status_code == 429


async def test_onay_kod_uretimi_ve_ortak_paneli_yetkileri(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    o = await _onayli_ortak(istemci, yonetici_basligi, db_oturumu, oran=12.5)
    assert o["durum"] == "onaylandi" and o["kod"] and o["oran"] == 12.5 and o["baglanti"].endswith(f"/?ref={o['kod']}")
    # Ortak kendi panelini görür; başka biri görmez; oturumsuz 401.
    y = await istemci.get(BEN, headers=musteri_basligi(o["eposta"]))
    assert y.status_code == 200 and y.json()["durum"] == "onaylandi" and y.json()["ortak"]["kod"] == o["kod"]
    assert y.json()["tiklama"]["toplam"] == 0 and y.json()["bakiyeler"] == {}
    y = await istemci.get(BEN, headers=musteri_basligi(_e("yabanci")))
    assert y.status_code == 200 and y.json() == {"durum": None}
    assert (await istemci.get(BEN)).status_code == 401
    assert (await istemci.post(f"{BEN}/odeme-talebi", json={}, headers=musteri_basligi(_e()))).status_code == 404
    # Yönetici uçları: 401 / 403.
    for metot, yol in [("GET", f"{YON}/ortaklar"), ("POST", f"{YON}/ortaklar/1/karar"), ("GET", f"{YON}/komisyonlar"),
                       ("GET", f"{YON}/odeme-talepleri"), ("POST", f"{YON}/odeme-talepleri/1/odendi"), ("PUT", f"{YON}/ayarlar"),
                       ("GET", KOD_YON), ("POST", KOD_YON), ("POST", f"{KOD_YON}/onizle"), ("DELETE", f"{KOD_YON}/1")]:
        govde = {} if metot in ("POST", "PUT") else None
        assert (await istemci.request(metot, yol, json=govde)).status_code == 401, yol
        assert (await istemci.request(metot, yol, json=govde, headers=musteri_basligi(o["eposta"]))).status_code == 403, yol


async def test_referans_akisi_komisyon_tekil_iade_ve_geri_alma(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    from models.crm import CrmAdaylari
    from models.ortaklik import OrtakReferanslari, OrtakTiklamalari

    o = await _onayli_ortak(istemci, yonetici_basligi, db_oturumu, oran=10)
    # Tıklama: günlük toplam (kişi verisi yok); geçersiz kod sayılmaz.
    assert (await istemci.post(f"{ACIK}/tiklama", json={"kod": o["kod"].lower()})).json() == {"gecerli": True}
    assert (await istemci.post(f"{ACIK}/tiklama", json={"kod": o["kod"]})).json() == {"gecerli": True}
    assert (await istemci.post(f"{ACIK}/tiklama", json={"kod": "YOKKOD99"})).json() == {"gecerli": False}
    satir = (await db_oturumu.execute(select(OrtakTiklamalari).where(OrtakTiklamalari.ortak_id == o["id"]))).scalars().all()
    assert len(satir) == 1 and satir[0].sayi == 2 and set(OrtakTiklamalari.__table__.columns.keys()) == {"id", "ortak_id", "gun", "sayi"}

    # Ziyaretçi iletişim formunu kodla doldurur → CRM adayı + atıf.
    musteri = _e("referans")
    y = await istemci.post("/api/v1/entities/inquiries", json={
        "name": "Ayşe Yılmaz", "email": musteri, "message": "Web sitesi istiyoruz", "source": "iletisim-formu",
        "referans_kodu": o["kod"].lower()})
    assert y.status_code == 201, y.text
    aday = (await db_oturumu.execute(select(CrmAdaylari).where(CrmAdaylari.email == musteri))).scalars().first()
    assert aday.referans_kodu == o["kod"] and aday.indirim_kodu is None
    ref = (await db_oturumu.execute(select(OrtakReferanslari).where(OrtakReferanslari.musteri_eposta == musteri))).scalars().first()
    assert ref.ortak_id == o["id"] and ref.kaynak == "form" and ref.aday_id == aday.id

    # Teklif (aday e-postasına) kabul → fatura (peşinat %100) → ödendi → komisyon.
    t = await _teklif(istemci, yonetici_basligi, hesap_email=None, aday_eposta=musteri, otomatik_fatura=True, pesinat_yuzde=100)
    t = await _kabul_ettir(istemci, yonetici_basligi, t["id"])
    fatura_id = t["fatura_id"]
    f = (await istemci.get(f"{FATURA}/{fatura_id}", headers=yonetici_basligi)).json()
    assert f["amount"] == 1420.0 and f["ara_toplam"] == 1200.0
    await _ode(istemci, yonetici_basligi, fatura_id, 1420)
    k = await _komisyonlar(db_oturumu, o["id"])
    assert len(k) == 1 and k[0].tur == "komisyon" and k[0].tutar == 120.0 and k[0].matrah == 1200.0  # KDV hariç × %10
    assert k[0].durum == "beklemede" and k[0].para_birimi == "TRY" and k[0].tekil == f"k:{fatura_id}"
    # Tekil: durum yeniden "paid" yazılsa da ikinci komisyon yok.
    await istemci.put(f"{FATURA}/{fatura_id}", json={"status": "paid"}, headers=yonetici_basligi)
    assert len(await _komisyonlar(db_oturumu, o["id"])) == 1

    # İade faturası %25 → oranlı ters kayıt (beklemedeki aslıyla birlikte olgunlaşır).
    y = await istemci.post(f"{FATURA_YON}/{fatura_id}/iade", json={"tutar": 355, "neden": "Kapsam daraldı"}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    k = await _komisyonlar(db_oturumu, o["id"])
    assert len(k) == 2 and k[1].tur == "ters" and k[1].tutar == -30.0 and k[1].durum == "beklemede" and k[1].bagli_id == k[0].id

    # Ödeme silinince (geri alındı) kalan komisyonun tamamı ters kayıt.
    odeme = next(x for x in (await istemci.get(f"{FATURA_YON}/{fatura_id}", headers=yonetici_basligi)).json()["odemeler"]
                 if x["durum"] == "odendi")
    assert (await istemci.delete(f"{FATURA_YON}/odemeler/{odeme['id']}", headers=yonetici_basligi)).status_code == 200
    k = await _komisyonlar(db_oturumu, o["id"])
    assert len(k) == 3 and k[2].tutar == -90.0 and sum(x.tutar for x in k) == 0
    # Yeniden ödenince yeni (tek) komisyon.
    await _ode(istemci, yonetici_basligi, fatura_id, 1065)
    k = await _komisyonlar(db_oturumu, o["id"])
    assert len(k) == 4 and k[3].tur == "komisyon" and k[3].tekil == f"k:{fatura_id}:1"

    # Ortak paneli: tıklama, aday, satış, kazanç; müşteri e-postası maskeli.
    p = (await istemci.get(BEN, headers=musteri_basligi(o["eposta"]))).json()
    # Satış: komisyonlu FARKLI fatura (geri alınıp yeniden ödenen fatura tek satış).
    assert p["tiklama"]["toplam"] == 2 and p["aday"] == 1 and p["satis"] == 1
    assert p["bakiyeler"]["TRY"]["kazanc"] == 120.0 and p["bakiyeler"]["TRY"]["beklemede"] == 120.0
    assert musteri not in json.dumps(p) and p["komisyonlar"][0]["musteri"].startswith(musteri[0])


async def test_kendi_kendine_referans_reddi(istemci, yonetici_basligi, db_oturumu):
    from models.ortaklik import OrtakReferanslari, Ortaklar

    o = await _onayli_ortak(istemci, yonetici_basligi, db_oturumu)
    y = await istemci.post("/api/v1/entities/inquiries", json={
        "name": "Kendim", "email": o["eposta"], "message": "Merhaba", "referans_kodu": o["kod"]})
    assert y.status_code == 201
    assert (await db_oturumu.execute(select(OrtakReferanslari).where(OrtakReferanslari.musteri_eposta == o["eposta"]))).scalars().first() is None
    db_oturumu.expire_all()
    satir = (await db_oturumu.execute(select(Ortaklar).where(Ortaklar.id == o["id"]))).scalars().first()
    assert "kendi_referansi" in json.loads(satir.supheli)
    # Ortağa bağlı indirim kodu ortağın kendi e-postasına uygulanamaz; ödenen faturasında komisyon yok.
    k = await _kod_ac(istemci, yonetici_basligi, ortak_id=o["id"])
    y = await istemci.post(TEKLIF, json={"baslik": "x", "kalemler": KALEMLER, "hesap_email": o["eposta"], "indirim_kodu": k["kod"]},
                           headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "kendi_referansi"
    t = await _teklif(istemci, yonetici_basligi, hesap_email=o["eposta"], otomatik_fatura=True, pesinat_yuzde=100)
    t = await _kabul_ettir(istemci, yonetici_basligi, t["id"])
    await _ode(istemci, yonetici_basligi, t["fatura_id"], 1420)
    assert await _komisyonlar(db_oturumu, o["id"]) == []


async def test_ortak_kodlu_indirim_atif_ve_ilk_son_kurali(istemci, yonetici_basligi, db_oturumu):
    from models.ortaklik import OrtakReferanslari

    a = await _onayli_ortak(istemci, yonetici_basligi, db_oturumu)
    b = await _onayli_ortak(istemci, yonetici_basligi, db_oturumu)
    musteri = _e("ilk")
    for o in (a, b):
        y = await istemci.post("/api/v1/entities/inquiries", json={"name": "M", "email": musteri, "message": "x",
                                                                    "referans_kodu": o["kod"]})
        assert y.status_code == 201
    ref = (await db_oturumu.execute(select(OrtakReferanslari).where(OrtakReferanslari.musteri_eposta == musteri))).scalars().first()
    assert ref.ortak_id == a["id"]  # varsayılan: ilk referans
    await _ayar(istemci, yonetici_basligi, atif="son")
    await istemci.post("/api/v1/entities/inquiries", json={"name": "M", "email": musteri, "message": "y", "referans_kodu": b["kod"]})
    db_oturumu.expire_all()
    ref = (await db_oturumu.execute(select(OrtakReferanslari).where(OrtakReferanslari.musteri_eposta == musteri))).scalars().first()
    assert ref.ortak_id == b["id"]
    await _ayar(istemci, yonetici_basligi, atif="ilk")
    # Ortağa bağlı indirim kodu: atfı olmayan müşteride kodun ortağına komisyon (teklifsiz fatura da).
    k = await _kod_ac(istemci, yonetici_basligi, ortak_id=a["id"], deger=20)
    yeni = _e("kodlu")
    y = await istemci.post(FATURA, json={"invoice_no": f"K-{uuid.uuid4().hex[:5]}", "client_email": yeni, "currency": "EUR",
                                         "status": "unpaid", "kalemler": KALEMLER[:1], "indirim_kodu": k["kod"]},
                           headers=yonetici_basligi)
    assert y.status_code == 201, y.text
    await _ode(istemci, yonetici_basligi, y.json()["id"], y.json()["amount"])
    kom = [x for x in await _komisyonlar(db_oturumu, a["id"]) if x.musteri_eposta == yeni]
    assert len(kom) == 1 and kom[0].matrah == 800.0 and kom[0].para_birimi == "EUR"


async def test_teklifsiz_fatura_varsayilan_komisyonsuz_ayarla_komisyonlu(istemci, yonetici_basligi, db_oturumu):
    o = await _onayli_ortak(istemci, yonetici_basligi, db_oturumu)
    musteri = _e("tum")
    await istemci.post("/api/v1/entities/inquiries", json={"name": "M", "email": musteri, "message": "x", "referans_kodu": o["kod"]})
    y = await istemci.post(FATURA, json={"invoice_no": f"T-{uuid.uuid4().hex[:5]}", "client_email": musteri, "currency": "TRY",
                                         "status": "unpaid", "amount": 500}, headers=yonetici_basligi)
    await _ode(istemci, yonetici_basligi, y.json()["id"], 500)
    assert await _komisyonlar(db_oturumu, o["id"]) == []
    await _ayar(istemci, yonetici_basligi, tum_faturalar=True)
    y = await istemci.post(FATURA, json={"invoice_no": f"T-{uuid.uuid4().hex[:5]}", "client_email": musteri, "currency": "TRY",
                                         "status": "unpaid", "amount": 500}, headers=yonetici_basligi)
    await _ode(istemci, yonetici_basligi, y.json()["id"], 500)
    k = await _komisyonlar(db_oturumu, o["id"])
    assert len(k) == 1 and k[0].tutar == 50.0
    await _ayar(istemci, yonetici_basligi, tum_faturalar=False)


async def test_odeme_talebi_iban_en_az_tutar_odendi_ret(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    from models.ortaklik import OrtakKomisyonlari

    await _ayar(istemci, yonetici_basligi, odeme_en_az={"TRY": 150}, bekleme_gun=14)
    o = await _onayli_ortak(istemci, yonetici_basligi, db_oturumu, oran=10)
    b = musteri_basligi(o["eposta"])
    musteri = _e("odeme")
    await istemci.post("/api/v1/entities/inquiries", json={"name": "M", "email": musteri, "message": "x", "referans_kodu": o["kod"]})
    t = await _teklif(istemci, yonetici_basligi, hesap_email=musteri, otomatik_fatura=True, pesinat_yuzde=100)
    t = await _kabul_ettir(istemci, yonetici_basligi, t["id"])
    await _ode(istemci, yonetici_basligi, t["fatura_id"], 1420)
    # IBAN: kart numarası değil, mod-97.
    y = await istemci.put(f"{BEN}/iban", json={"iban": "4111 1111 1111 1111", "iban_ad": "Can"}, headers=b)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "kart_numarasi_degil"
    y = await istemci.put(f"{BEN}/iban", json={"iban": "TR33 0006 1005 1978 6457 8413 27", "iban_ad": "Can"}, headers=b)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "iban_gecersiz"
    y = await istemci.put(f"{BEN}/iban", json={"iban": "TR33 0006 1005 1978 6457 8413 26", "iban_ad": "Can Yıldız"}, headers=b)
    assert y.status_code == 200 and y.json()["iban"] == "TR33 •••• 1326"
    # Beklemede (iade süresi) — bakiye yok.
    y = await istemci.post(f"{BEN}/odeme-talebi", json={"para_birimi": "TRY"}, headers=b)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "en_az_tutar" and y.json()["detail"]["bakiye"] == 0.0
    # Süre dolunca onaylanır (zamanlı iş); 120 < 150 en az tutar.
    from services import ortaklik

    await ortaklik.olgunlasanlari_onayla(db_oturumu, datetime.now(timezone.utc) + timedelta(days=15))
    y = await istemci.post(f"{BEN}/odeme-talebi", json={"para_birimi": "TRY"}, headers=b)
    assert y.status_code == 409 and y.json()["detail"]["en_az"] == 150.0 and y.json()["detail"]["bakiye"] == 120.0
    await _ayar(istemci, yonetici_basligi, odeme_en_az={"TRY": 100})
    y = await istemci.post(f"{BEN}/odeme-talebi", json={"para_birimi": "TRY"}, headers=b)
    assert y.status_code == 200 and y.json()["tutar"] == 120.0 and y.json()["durum"] == "bekliyor"
    talep = y.json()
    y = await istemci.post(f"{BEN}/odeme-talebi", json={"para_birimi": "TRY"}, headers=b)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "bekleyen_talep_var"
    # Ret → bakiyeye döner; yeniden talep → ödendi + dekont.
    y = await istemci.post(f"{YON}/odeme-talepleri/{talep['id']}/reddet", json={"neden": "IBAN adı uyuşmuyor"}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["durum"] == "reddedildi"
    db_oturumu.expire_all()
    assert {k.durum for k in await _komisyonlar(db_oturumu, o["id"])} == {"onaylandi"}
    talep = (await istemci.post(f"{BEN}/odeme-talebi", json={"para_birimi": "TRY"}, headers=b)).json()
    liste = (await istemci.get(f"{YON}/odeme-talepleri?durum=bekliyor", headers=yonetici_basligi)).json()
    assert any(x["id"] == talep["id"] and x["iban"] == "TR330006100519786457841326" for x in liste)
    y = await istemci.post(f"{YON}/odeme-talepleri/{talep['id']}/odendi", data={"notu": "EFT 08.10"},
                           files={"dekont": ("dekont.pdf", io.BytesIO(b"%PDF-1.4 dekont"), "application/pdf")},
                           headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    assert y.json()["durum"] == "odendi" and y.json()["dekont_var"] is True
    k = await _komisyonlar(db_oturumu, o["id"])
    assert {x.durum for x in k} == {"odendi"}
    p = (await istemci.get(BEN, headers=b)).json()
    assert p["bakiyeler"]["TRY"]["odendi"] == 120.0 and p["bakiyeler"]["TRY"]["onaylandi"] == 0
    y = await istemci.get(f"{BEN}/odeme-talepleri/{talep['id']}/dekont", headers=b)
    assert y.status_code == 200 and y.json()["adres"].startswith("/api/v1/dosya-indir/")
    assert (await istemci.get(f"{BEN}/odeme-talepleri/{talep['id']}/dekont", headers=musteri_basligi(_e()))).status_code == 404
    # Ortağa e-posta (bildirim kaydı) gitti.
    from models.notifications import Notifications

    n = (await db_oturumu.execute(select(Notifications).where(Notifications.event_type == "ortaklik_durum",
                                                              Notifications.ref_type == "ortaklik_talep",  # ortak kimliğiyle çakışmasın
                                                              Notifications.ref_id == talep["id"]))).scalars().all()
    assert n and n[0].recipient_email.lower() == o["eposta"]
    await _ayar(istemci, yonetici_basligi, odeme_en_az={"TRY": 500})


async def test_supheli_ayni_alan_adi_ve_yonetici_iptali(istemci, yonetici_basligi, db_oturumu):
    from models.ortaklik import Ortaklar

    eposta = f"ortak-{uuid.uuid4().hex[:6]}@firma{uuid.uuid4().hex[:4]}.com.tr"
    await _basvur(istemci, eposta)
    oid = (await db_oturumu.execute(select(Ortaklar.id).where(Ortaklar.eposta == eposta))).scalar()
    o = (await istemci.post(f"{YON}/ortaklar/{oid}/karar", json={"karar": "onay"}, headers=yonetici_basligi)).json()
    musteri = "satin-" + eposta
    await istemci.post("/api/v1/entities/inquiries", json={"name": "M", "email": musteri, "message": "x", "referans_kodu": o["kod"]})
    t = await _teklif(istemci, yonetici_basligi, hesap_email=musteri, otomatik_fatura=True, pesinat_yuzde=100)
    t = await _kabul_ettir(istemci, yonetici_basligi, t["id"])
    await _ode(istemci, yonetici_basligi, t["fatura_id"], 1420)
    liste = (await istemci.get(f"{YON}/komisyonlar?durum=supheli", headers=yonetici_basligi)).json()
    kom = next(x for x in liste if x["ortak_id"] == o["id"])
    assert kom["supheli"] == ["ayni_alan_adi"] and kom["ortak_ad"] == "Can Yıldız"
    assert (await istemci.get(f"{YON}/ozet", headers=yonetici_basligi)).json()["supheli_komisyon"] >= 1
    y = await istemci.post(f"{YON}/komisyonlar/{kom['id']}/islem", json={"islem": "iptal", "not": "Aynı firma"}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["durum"] == "iptal"


async def test_ozet_gelen_kutusu_haftalik_ozet_ve_kataloglar(istemci, yonetici_basligi, db_oturumu):
    from services import gelen_kutusu, haftalik_ozet, otomasyon_kural, webhook
    from services.bildirim_tercih import OLAYLAR

    await _basvur(istemci, _e("ozet"))
    o = await haftalik_ozet.ozet_hazirla(db_oturumu)
    bolum = next(b for b in o["bolumler"] if b["anahtar"] == "ortaklik")
    assert bolum["sayi"] >= 1 and bolum["ek"]["basvuru"] >= 1 and bolum["sekme"] == "ortaklik"
    gk = next(b for b in o["bolumler"] if b["anahtar"] == "gelen_kutusu")
    assert "ortak_basvurusu" not in gk["ek"].get("kaynaklar", {})  # çift sayım yok
    assert "ortak_basvurusu" in gelen_kutusu.KAYNAKLAR
    for tur in ("ortaklik.basvuru", "ortaklik.komisyon", "ortaklik.odeme_talebi"):
        assert tur in webhook.OLAY_SOZLUGU and not webhook.OLAY_SOZLUGU[tur].musteri
        assert tur in otomasyon_kural.OLAY_SOZLUGU and not otomasyon_kural.OLAY_SOZLUGU[tur].musteri
    assert otomasyon_kural.kisi_sec("ortaklik.komisyon", otomasyon_kural.ornek_baglam("ortaklik.komisyon", True))["email"] == "can@ornek.com"
    assert OLAYLAR["ortaklik_basvuru"]["roller"] == ("admin",) and OLAYLAR["ortaklik_durum"]["roller"] == ("client",)
    from services.zamanli import GOREV_ADLARI

    assert "ortaklik_bakimi" in GOREV_ADLARI and GOREV_ADLARI[-1] == "aylik_site_analizi"


async def test_otomasyon_baglami_ve_webhook_olayi(istemci, yonetici_basligi, db_oturumu):
    from models.ortaklik import Ortaklar
    from services import otomasyon

    eposta = _e("oto")
    await _basvur(istemci, eposta)
    o = (await db_oturumu.execute(select(Ortaklar).where(Ortaklar.eposta == eposta))).scalars().first()
    b = await otomasyon.baglam_kur(db_oturumu, "ortaklik.basvuru", {"ortak_id": o.id}, None, True)
    assert b["ortak"]["email"] == eposta and b["kisi"]["email"] == eposta and "iban" not in json.dumps(b)


async def test_ayarlar_gizli_ve_dogrulanir(istemci, yonetici_basligi):
    a = await _ayar(istemci, yonetici_basligi, varsayilan_oran=999, bekleme_gun=-3, atif="baska", odeme_en_az={"XYZ": 1})
    assert a["varsayilan_oran"] != 999 and a["bekleme_gun"] >= 0 and a["atif"] in ("ilk", "son") and "XYZ" not in a["odeme_en_az"]
    y = await istemci.get("/api/v1/entities/site_settings/all?limit=500")
    assert "ortaklik_ayarlari" not in y.text


async def test_fiyat_teklifi_formu_kodu_adaya_ve_teklife_tasir(istemci, yonetici_basligi, db_oturumu):
    from models.crm import CrmAdaylari

    k = await _kod_ac(istemci, yonetici_basligi, kapsam=["paket"], deger=10)
    musteri = _e("fiyat")
    y = await istemci.post("/api/v1/fiyat-teklif", json={"kredi_paketi": 10, "musteri_eposta": musteri, "musteri_adi": "Ali",
                                                         "referans_kodu": k["kod"].lower()})
    assert y.status_code == 200, y.text
    aday = (await db_oturumu.execute(select(CrmAdaylari).where(CrmAdaylari.email == musteri))).scalars().first()
    assert aday.indirim_kodu == k["kod"]
    y = await istemci.post(f"{TEKLIF}/fiyat-talebinden/{y.json()['inquiry_id']}", headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    assert y.json()["indirim_kodu"] == k["kod"] and any(x.get("indirim_kodu") for x in y.json()["kalemler"])


def test_ek_paketler_yedi_dilde_esit_ve_pazarlama_metni_sunucudakiyle_ayni():
    """`ortaklik` ve `indirimKodu` ek paketleri 7 dilde aynı anahtarlarla; başvuru formunun pazarlama kutusu
    metni sunucunun kaydettiği metin sürümüyle AYNI; sunucunun döndürdüğü hata kodlarının metni var."""
    from pathlib import Path

    from services import pazarlama_izni

    on_yuz = Path(__file__).resolve().parents[3] / "frontend"
    diller = ("tr", "en", "de", "ru", "zh", "hi", "ar")

    def anahtarlar(d, on=""):
        if isinstance(d, dict):
            return set().union(*(anahtarlar(v, f"{on}.{k}") for k, v in d.items()))
        if isinstance(d, list):
            return {f"{on}[{len(d)}]"}.union(*(anahtarlar(v, f"{on}[{i}]") for i, v in enumerate(d)))
        assert isinstance(d, str) and d.strip(), on
        return {on}

    for ad in ("ortaklik", "indirimKodu"):
        paketler = {
            dil: json.loads((on_yuz / "src/i18n/ek" / ad / f"{dil}.json").read_text(encoding="utf-8"))[ad] for dil in diller
        }
        tr = anahtarlar(paketler["tr"])
        for dil, p in paketler.items():
            assert anahtarlar(p) == tr, (ad, dil)
    for dil in diller:
        p = json.loads((on_yuz / "src/i18n/ek/ortaklik" / f"{dil}.json").read_text(encoding="utf-8"))["ortaklik"]
        assert p["form"]["pazarlama"] == pazarlama_izni.METINLER[dil], dil
        kod = json.loads((on_yuz / "src/i18n/ek/indirimKodu" / f"{dil}.json").read_text(encoding="utf-8"))["indirimKodu"]
        for k in ("kod_yok", "kod_pasif", "kod_baslamadi", "kod_suresi_doldu", "kod_kapsam_disi", "kod_para_birimi",
                  "kod_en_az_tutar", "kod_tukendi", "kod_kisi_siniri", "kendi_referansi", "kalem_gerekli", "kod_paket_disi",
                  "paket_gecersiz"):
            assert k in kod["hata"], (dil, k)
        for k in ("iban_gecersiz", "kart_numarasi_degil", "en_az_tutar", "bekleyen_talep_var", "iban_gerekli"):
            assert k in p["panel"]["hata"], (dil, k)


# ---------------------------------------------------------------------------
# Komisyon kuralı: ilk satış (X) + tekrar eden abonelik (Y, N ay)
# ---------------------------------------------------------------------------
async def test_ilk_satis_ve_tekrar_eden_abonelik_komisyonu(istemci, yonetici_basligi, db_oturumu):
    """Kural (ayarlardan): ilk satış %X (ortağa özel oran), ilk satıştan sonraki N ay içinde ödenen TEKRARLAYAN
    (abonelik) faturası %Y; tekrarlamayan sonraki satış (ikinci teklif dahil) komisyonsuz; süre dolunca ya da
    N = 0 iken abonelik faturası komisyonsuz."""
    await _ayar(istemci, yonetici_basligi, tekrar_oran=5, tekrar_ay=2)
    o = await _onayli_ortak(istemci, yonetici_basligi, db_oturumu, oran=10)
    musteri = _e("abone")
    await istemci.post("/api/v1/entities/inquiries", json={"name": "M", "email": musteri, "message": "x", "referans_kodu": o["kod"]})
    t = await _teklif(istemci, yonetici_basligi, hesap_email=musteri, otomatik_fatura=True, pesinat_yuzde=100)
    t = await _kabul_ettir(istemci, yonetici_basligi, t["id"])
    await _ode(istemci, yonetici_basligi, t["fatura_id"], 1420)
    k = await _komisyonlar(db_oturumu, o["id"])
    assert [(x.kural, x.tutar, x.teklif_id) for x in k] == [("ilk", 120.0, t["id"])]

    async def fatura(**g):
        y = await istemci.post(FATURA, json={"invoice_no": f"A-{uuid.uuid4().hex[:6]}", "client_email": musteri,
                                             "currency": "TRY", "status": "unpaid", "amount": 1000, **g}, headers=yonetici_basligi)
        assert y.status_code == 201, y.text
        await _ode(istemci, yonetici_basligi, y.json()["id"], 1000)

    # Abonelik (tekrarlayan) faturası N ay içinde → %5 (tek tutarlı: tutar taban).
    await fatura(tekrarlayan_id=987, donem="2026-11")
    k = await _komisyonlar(db_oturumu, o["id"])
    assert len(k) == 2 and (k[1].kural, k[1].oran, k[1].tutar) == ("tekrar", 5.0, 50.0)
    # Tekrarlamayan sonraki satış ve ikinci kabul edilen teklif → komisyon yok (yalnız ilk satış).
    await fatura()
    t2 = await _teklif(istemci, yonetici_basligi, hesap_email=musteri, otomatik_fatura=True, pesinat_yuzde=100)
    t2 = await _kabul_ettir(istemci, yonetici_basligi, t2["id"])
    await _ode(istemci, yonetici_basligi, t2["fatura_id"], 1420)
    assert len(await _komisyonlar(db_oturumu, o["id"])) == 2
    # Süre doldu (ilk satış ~3 ay önce, N = 2) → abonelik faturası komisyonsuz.
    ilk = k[0]
    ilk.created_at = datetime.now(timezone.utc) - timedelta(days=95)
    await db_oturumu.commit()
    await fatura(tekrarlayan_id=987, donem="2026-12")
    assert len(await _komisyonlar(db_oturumu, o["id"])) == 2
    # N = 0 (kapalı): süre içinde de komisyon yok.
    ilk = (await _komisyonlar(db_oturumu, o["id"]))[0]
    ilk.created_at = datetime.now(timezone.utc)
    await db_oturumu.commit()
    await _ayar(istemci, yonetici_basligi, tekrar_ay=0)
    await fatura(tekrarlayan_id=987, donem="2027-01")
    assert len(await _komisyonlar(db_oturumu, o["id"])) == 2
    # Program bilgisi kuralı herkese açık gösteriyor; yönetici listesinde kural etiketi.
    g = (await istemci.get(f"{ACIK}/program")).json()
    assert g["tekrar_ay"] == 0 and g["tekrar_oran"] == 5.0 and g["bekleme_gun"] >= 0
    liste = (await istemci.get(f"{YON}/komisyonlar", params={"ortak_id": o["id"]}, headers=yonetici_basligi)).json()
    assert sorted(x["kural"] for x in liste) == ["ilk", "tekrar"]


def test_ay_ekle_takvim_ayi():
    from services.ortaklik import _ay_ekle

    assert _ay_ekle(datetime(2026, 1, 31, tzinfo=timezone.utc), 1) == datetime(2026, 2, 28, tzinfo=timezone.utc)
    assert _ay_ekle(datetime(2026, 11, 15, tzinfo=timezone.utc), 3) == datetime(2027, 2, 15, tzinfo=timezone.utc)


async def test_site_teklif_formundan_gelen_fatura_ilk_satis(istemci, yonetici_basligi, db_oturumu):
    """Sitedeki "Teklif al" akışından (fiyat talebi) doğan fatura, teklifsiz de olsa ilk satış sayılır."""
    o = await _onayli_ortak(istemci, yonetici_basligi, db_oturumu, oran=10)
    musteri = _e("site")
    y = await istemci.post("/api/v1/fiyat-teklif", json={"kredi_paketi": 10, "musteri_eposta": musteri, "musteri_adi": "Ali",
                                                         "referans_kodu": o["kod"]})
    assert y.status_code == 200, y.text
    fid = y.json()["invoice_id"]
    f = (await istemci.get(f"{FATURA}/{fid}", headers=yonetici_basligi)).json()
    await _ode(istemci, yonetici_basligi, fid, f["amount"])
    k = await _komisyonlar(db_oturumu, o["id"])
    assert len(k) == 1 and k[0].kural == "ilk" and k[0].musteri_eposta == musteri and k[0].teklif_id is None


# ---------------------------------------------------------------------------
# Referans: Site Analizi, modül talebi, kayıt
# ---------------------------------------------------------------------------
async def test_site_analizi_ve_modul_talebi_referans_kodunu_baglar(istemci, yonetici_basligi, db_oturumu):
    from models.crm import CrmAdaylari
    from models.ortaklik import OrtakReferanslari
    from models.site_analyses import Site_analyses

    o = await _onayli_ortak(istemci, yonetici_basligi, db_oturumu)
    # Modül talebi: gizli alan (küçük harf de olur).
    e1 = _e("modul")
    y = await istemci.post("/api/v1/modul-vitrini/talep", headers={"x-mk-istemci-ip": "203.0.113.151"}, json={
        "tur": "paket", "anahtar": "klinik_guzellik", "ad": "Ayşe", "eposta": e1, "dil": "tr", "referans_kodu": o["kod"].lower()})
    assert y.status_code == 200, y.text
    aday = (await db_oturumu.execute(select(CrmAdaylari).where(CrmAdaylari.email == e1))).scalars().first()
    assert aday is not None and aday.referans_kodu == o["kod"]
    ref = (await db_oturumu.execute(select(OrtakReferanslari).where(OrtakReferanslari.musteri_eposta == e1))).scalars().first()
    assert ref.ortak_id == o["id"] and ref.aday_id == aday.id
    # Site Analizi tam rapor isteği (analiz tamamlanmış kayıt).
    analiz = Site_analyses(alan_adi="ref-ornek.com", url="https://ref-ornek.com/", durum="tamam", puan=70,
                           ozet_json=json.dumps({"bolumler": []}), created_at=datetime.now(timezone.utc))
    db_oturumu.add(analiz)
    await db_oturumu.commit()
    e2 = _e("analiz")
    y = await istemci.post(f"/api/v1/site-analizi/{analiz.id}/tam-rapor", json={"eposta": e2, "referans_kodu": o["kod"]})
    assert y.status_code == 200 and y.json() == {"gonderildi": True}, y.text
    db_oturumu.expire_all()
    aday = (await db_oturumu.execute(select(CrmAdaylari).where(CrmAdaylari.email == e2))).scalars().first()
    assert aday is not None and aday.referans_kodu == o["kod"]
    assert (await db_oturumu.execute(select(OrtakReferanslari.ortak_id).where(OrtakReferanslari.musteri_eposta == e2))).scalar() == o["id"]
    # Bilinmeyen kod formu bozmaz (sessizce yok sayılır).
    e3 = _e("bilinmeyen")
    y = await istemci.post("/api/v1/modul-vitrini/talep", headers={"x-mk-istemci-ip": "203.0.113.152"}, json={
        "tur": "paket", "anahtar": "klinik_guzellik", "ad": "Ali", "eposta": e3, "dil": "tr", "referans_kodu": "YOKBOYLE77"})
    assert y.status_code == 200
    assert (await db_oturumu.execute(select(OrtakReferanslari).where(OrtakReferanslari.musteri_eposta == e3))).scalars().first() is None


async def test_kayit_referansi_yalniz_yeni_hesapta(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    """Bağlantıdan gelip hesap açan kişiye atıf; eski hesaba (pencere 48 saat) ve ortağın kendisine yok."""
    from models.auth import User
    from models.ortaklik import OrtakReferanslari

    o = await _onayli_ortak(istemci, yonetici_basligi, db_oturumu)
    yeni, eski = _e("kayit"), _e("eski")
    an = datetime.now(timezone.utc)
    db_oturumu.add(User(id=uuid.uuid4().hex, email=yeni, role="user", created_at=an))
    db_oturumu.add(User(id=uuid.uuid4().hex, email=eski, role="user", created_at=an - timedelta(days=10)))
    await db_oturumu.commit()
    Y = f"{BEN}/kayit-referansi"
    assert (await istemci.post(Y, json={"kod": o["kod"]})).status_code == 401
    y = await istemci.post(Y, json={"kod": o["kod"].lower()}, headers=musteri_basligi(yeni))
    assert y.status_code == 200 and y.json() == {"atif": True}, y.text
    ref = (await db_oturumu.execute(select(OrtakReferanslari).where(OrtakReferanslari.musteri_eposta == yeni))).scalars().first()
    assert ref.ortak_id == o["id"] and ref.kaynak == "kayit"
    assert (await istemci.post(Y, json={"kod": o["kod"]}, headers=musteri_basligi(eski))).json() == {"atif": False}
    assert (await db_oturumu.execute(select(OrtakReferanslari).where(OrtakReferanslari.musteri_eposta == eski))).scalars().first() is None
    assert (await istemci.post(Y, json={"kod": "YOKKOD42"}, headers=musteri_basligi(_e()))).json() == {"atif": False}
    db_oturumu.add(User(id=uuid.uuid4().hex, email=o["eposta"], role="user", created_at=an))
    await db_oturumu.commit()
    assert (await istemci.post(Y, json={"kod": o["kod"]}, headers=musteri_basligi(o["eposta"]))).json() == {"atif": False}


# ---------------------------------------------------------------------------
# Bekleme süresi: zamanlı iş + panel açılışı (istekle tetiklenen)
# ---------------------------------------------------------------------------
async def test_bekleme_suresi_zamanli_is_ve_panel_acilisiyla_onaylanir(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    from services import zamanli

    o = await _onayli_ortak(istemci, yonetici_basligi, db_oturumu)
    for _ in range(2):
        musteri = _e("olgun")
        await istemci.post("/api/v1/entities/inquiries", json={"name": "M", "email": musteri, "message": "x", "referans_kodu": o["kod"]})
        t = await _teklif(istemci, yonetici_basligi, hesap_email=musteri, otomatik_fatura=True, pesinat_yuzde=100)
        t = await _kabul_ettir(istemci, yonetici_basligi, t["id"])
        await _ode(istemci, yonetici_basligi, t["fatura_id"], 1420)
    k1, k2 = await _komisyonlar(db_oturumu, o["id"])
    assert k1.durum == k2.durum == "beklemede"
    # Süre doldu (k1): zamanlı iş ("ortaklik_bakimi", ücretsiz sunucuda istekle tetiklenen tur) onaylar.
    k1.bekleme_bitis = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db_oturumu.commit()
    gorev = next(g for g in zamanli.GOREVLER if g.ad == "ortaklik_bakimi")
    assert (await gorev.calistir(db_oturumu, True))["onaylanan"] >= 1
    k1, k2 = await _komisyonlar(db_oturumu, o["id"])
    assert (k1.durum, k2.durum) == ("onaylandi", "beklemede")
    # Ortağa "komisyonunuz onaylandı" bildirimi (tutarla).
    from models.notifications import Notifications

    n = (await db_oturumu.execute(select(Notifications).where(Notifications.event_type == "ortaklik_durum",
                                                              Notifications.recipient_email == o["eposta"]))).scalars().all()
    assert any("onaylandı" in (x.title or "") and "120" in (x.title or "") for x in n), [x.title for x in n]
    # Süre doldu (k2): ortağın panel açılışı da onaylar.
    k2.bekleme_bitis = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db_oturumu.commit()
    p = (await istemci.get(BEN, headers=musteri_basligi(o["eposta"]))).json()
    assert p["bakiyeler"]["TRY"]["onaylandi"] == 240.0 and p["bakiyeler"]["TRY"]["beklemede"] == 0


# ---------------------------------------------------------------------------
# CSV ve denetim kaydı
# ---------------------------------------------------------------------------
def test_csv_formul_enjeksiyonu():
    from services.ortaklik import csv_metni

    metin = csv_metni(["a", "b"], [["=HYPERLINK(1)", -5.0], ["+1", "-x"], ["@SUM", "normal"]])
    assert metin.startswith("\ufeff")
    satirlar = metin.lstrip("\ufeff").splitlines()
    assert satirlar[1] == "'=HYPERLINK(1),-5.0" and satirlar[2] == "'+1,'-x" and satirlar[3] == "'@SUM,normal"


async def test_csv_uclari_ve_denetimde_iban_maskeli(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    from models.audit_log import AuditLog
    from models.ortaklik import OrtakOdemeTalepleri

    o = await _onayli_ortak(istemci, yonetici_basligi, db_oturumu)
    tam = "TR330006100519786457841326"
    y = await istemci.put(f"{BEN}/iban", json={"iban": "TR33 0006 1005 1978 6457 8413 26", "iban_ad": "Can Yıldız"},
                          headers=musteri_basligi(o["eposta"]))
    assert y.status_code == 200
    # Denetim kaydı: IBAN alanının değiştiği yazılır, değeri yazılmaz.
    satirlar = (await db_oturumu.execute(select(AuditLog).where(AuditLog.tablo == "ortaklar",
                                                                AuditLog.kayit_id == str(o["id"])))).scalars().all()
    degisen = [json.loads(r.degisiklik_json) for r in satirlar if r.degisiklik_json and "iban" in json.loads(r.degisiklik_json)]
    assert degisen and degisen[-1]["iban"] == [None, "***"] and degisen[-1]["iban_ad"] == [None, "***"]
    assert not any(tam in (r.degisiklik_json or "") or tam in (r.ozet or "") for r in satirlar)
    # Ödeme talebi CSV'de IBAN maskeli; komisyon CSV başlığı.
    db_oturumu.add(OrtakOdemeTalepleri(ortak_id=o["id"], tutar=750.0, para_birimi="TRY", iban=tam, iban_ad="Can", durum="bekliyor"))
    await db_oturumu.commit()
    for yol in (f"{YON}/komisyonlar.csv", f"{YON}/odeme-talepleri.csv"):
        assert (await istemci.get(yol)).status_code == 401
        assert (await istemci.get(yol, headers=musteri_basligi(o["eposta"]))).status_code == 403
    y = await istemci.get(f"{YON}/odeme-talepleri.csv", headers=yonetici_basligi)
    assert y.status_code == 200 and y.headers["content-type"].startswith("text/csv")
    assert "attachment" in y.headers["content-disposition"]
    assert "TR33 •••• 1326" in y.text and tam not in y.text and o["eposta"] in y.text
    y = await istemci.get(f"{YON}/komisyonlar.csv", params={"durum": "onaylandi"}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.text.lstrip("\ufeff").splitlines()[0].startswith("id,tarih,ortak,ortak_eposta,kural")


# ---------------------------------------------------------------------------
# Geçerli paketler + "Teklif al" talebinin faturası teklifin indirimini taşır
# ---------------------------------------------------------------------------
async def test_paketle_sinirli_kod_ve_talep_faturasi_indirimi_tasir(istemci, yonetici_basligi, db_oturumu):
    kredi = await _kod_ac(istemci, yonetici_basligi, kapsam=["paket"], paketler=["kredi"], deger=10)
    assert kredi["paketler"] == ["KREDI"]
    beta = await _kod_ac(istemci, yonetici_basligi, paketler=["BETA"], deger=10)
    y = await istemci.post(KOD_YON, json={"kod": _kod(), "tur": "yuzde", "deger": 5, "paketler": ["x y"]}, headers=yonetici_basligi)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "paket_gecersiz"
    # Herkese açık doğrulama: seçili pakete uymayan kod (yanıt bilinmeyen kodla aynı) geçersiz görünür.
    assert (await istemci.post(f"{KOD_ACIK}/dogrula", json={"kod": beta["kod"], "paket": "KREDI"})).json() == {"gecerli": False}
    assert (await istemci.post(f"{KOD_ACIK}/dogrula", json={"kod": beta["kod"], "paket": "beta"})).json()["gecerli"] is True
    assert "paketler" not in json.dumps((await istemci.post(f"{KOD_ACIK}/dogrula", json={"kod": beta["kod"]})).json())
    # Elle açılan teklifte paket bilinmiyor: paketle sınırlı kod uygulanmaz.
    y = await istemci.post(TEKLIF, json={"baslik": "x", "kalemler": KALEMLER, "hesap_email": _e(), "indirim_kodu": beta["kod"]},
                           headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "kod_paket_disi"
    # "Teklif al" (kredi paketi) → teklif: KREDI kodu uygulanır; BETA kodu sessizce düşer (teklif kodsuz).
    for kod, beklenen in ((beta["kod"], None), (kredi["kod"], kredi["kod"])):
        musteri = _e("paket")
        y = await istemci.post("/api/v1/fiyat-teklif", json={"kredi_paketi": 10, "musteri_eposta": musteri, "musteri_adi": "Ali",
                                                             "referans_kodu": kod})
        assert y.status_code == 200, y.text
        talep = y.json()
        t = (await istemci.post(f"{TEKLIF}/fiyat-talebinden/{talep['inquiry_id']}", headers=yonetici_basligi)).json()
        assert t["indirim_kodu"] == beklenen, t
    f0 = (await istemci.get(f"{FATURA}/{talep['invoice_id']}", headers=yonetici_basligi)).json()
    assert f0["indirim_kodu"] is None
    # Kabul: talebin (ödenmemiş) faturası teklifin indirimli kalemlerini ve kodunu taşır.
    t = await _kabul_ettir(istemci, yonetici_basligi, t["id"])
    f = (await istemci.get(f"{FATURA}/{talep['invoice_id']}", headers=yonetici_basligi)).json()
    assert f["indirim_kodu"] == kredi["kod"] and f["teklif_id"] == t["id"]
    assert f["amount"] == t["ozet"]["genel_toplam"] < f0["amount"]
    assert any(k.get("indirim_kodu") == kredi["kod"] for k in f["kalemler"])


# ---------------------------------------------------------------------------
# Hesap bazlı tasarım: başka bir programın (ileride müşteriye açılırsa) kayıtları ajans sorgularına karışmaz
# ---------------------------------------------------------------------------
async def test_hesap_bazli_program_kayitlari_ajans_sorgularindan_ayri(istemci, yonetici_basligi, db_oturumu):
    from models.ortaklik import AJANS, IndirimKodlari, Ortaklar

    baska = f"musteri-{uuid.uuid4().hex[:6]}@test.dev"
    kod = _kod("MUS")
    eposta = _e("iki")
    db_oturumu.add(IndirimKodlari(hesap=baska, kod=kod, kod_anahtar=kod, tur="yuzde", deger=10, aktif=True))
    db_oturumu.add(Ortaklar(hesap=baska, eposta=eposta, ad="Başka program", durum="onaylandi", kod=kod + "R",
                            kod_anahtar=kod + "R"))
    await db_oturumu.commit()
    # Ajans formunda başka programın kodu geçersiz; ajans aynı kodu ve aynı e-postalı ortağı ayrı kayıt olarak açabilir.
    assert (await istemci.post(f"{KOD_ACIK}/dogrula", json={"kod": kod})).json() == {"gecerli": False}
    assert (await istemci.post(f"{ACIK}/tiklama", json={"kod": kod + "R"})).json() == {"gecerli": False}
    k = await _kod_ac(istemci, yonetici_basligi, kod=kod)
    assert k["kod"] == kod and all(x["kod"] != kod or x["id"] == k["id"] for x in (await istemci.get(KOD_YON, headers=yonetici_basligi)).json())
    assert (await _basvur(istemci, eposta)).status_code == 200
    satirlar = (await db_oturumu.execute(select(Ortaklar.hesap, Ortaklar.durum).where(Ortaklar.eposta == eposta))).all()
    assert sorted(satirlar) == sorted([(baska, "onaylandi"), (AJANS, "beklemede")])
    liste = (await istemci.get(f"{YON}/ortaklar", headers=yonetici_basligi)).json()
    assert [o["durum"] for o in liste if o["eposta"] == eposta] == ["beklemede"]
