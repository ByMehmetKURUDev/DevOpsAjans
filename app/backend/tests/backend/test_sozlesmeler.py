"""Faz 3T — sözleşme şablonları, basit elektronik imza ve sürümler.

Kapsam: şablon + yer tutucular, gönderim (bağlantı bir kez), imza kaydı (ad,
zaman, IP özeti, tarayıcı, metnin SHA-256 özeti, PNG imza), metin değişince
imza reddi, imza sonrası metin değişikliği yeni sürüm, gönderilmiş sözleşmede
metin değişirse bağlantı iptali, imzalı sözleşme silinemez, PDF'te imza bloğu +
5070 notu + Türkçe harfler, bitiş hatırlatması eşik başına bir kez, müşteri
yalnız kendi sözleşmesini görür ve panelden imzalayabilir.
"""

import base64
import hashlib
import io
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select

YONETIM = "/api/v1/sozlesme-yonetim"
ACIK = "/api/v1/sozlesme"
MUSTERI = "/api/v1/sozlesmelerim"

GOVDE = "# Taraflar\nBu sözleşme **{{ajans_unvani}}** ile {{musteri_adi}} arasındadır.\n\n- Kapsam: web sitesi\n- Süre: {{baslangic}} – {{bitis}}"


def _eposta(on: str = "sozlesme") -> str:
    return f"{on}-{uuid.uuid4().hex[:10]}@test.dev"


@pytest.fixture(autouse=True)
def _sinir_sifirla():
    from routers import sozlesmeler, teklifler

    for r in (teklifler, sozlesmeler):
        r.hiz_siniri.temizle()
    yield


def _png(gen=300, yuk=100, bos=False) -> str:
    from PIL import Image, ImageDraw

    g = Image.new("RGBA", (gen, yuk), (255, 255, 255, 0))
    if not bos:
        ImageDraw.Draw(g).line([(10, 80), (80, 20), (150, 90), (280, 30)], fill=(20, 20, 60, 255), width=4)
    tampon = io.BytesIO()
    g.save(tampon, "PNG")
    return "data:image/png;base64," + base64.b64encode(tampon.getvalue()).decode()


async def _olustur(istemci, basliklar, **govde):
    veri = {"baslik": "Hizmet Sözleşmesi — Işıklı Ğıda", "govde": GOVDE, "taraf_ad": "Ayşe Yılmaz",
            "taraf_eposta": _eposta(), **govde}
    y = await istemci.post(YONETIM, json=veri, headers=basliklar)
    assert y.status_code == 200, y.text
    return y.json()


async def _gonder(istemci, baslik, sozlesme_id):
    y = await istemci.post(f"{YONETIM}/{sozlesme_id}/gonder", json={}, headers=baslik)
    assert y.status_code == 200, y.text
    assert y.json()["baglanti"].startswith("https://mehmetkuru.dev/sozlesme/")
    return y.json()["baglanti"].rsplit("/", 1)[1]


def _ozet(baslik, govde):
    return hashlib.sha256(f"{baslik.strip()}\n\n{govde.strip()}".encode()).hexdigest()


@pytest.mark.parametrize(
    "metot,yol",
    [("GET", YONETIM), ("POST", YONETIM), ("GET", f"{YONETIM}/sablonlar"), ("POST", f"{YONETIM}/sablonlar"),
     ("PUT", f"{YONETIM}/1"), ("DELETE", f"{YONETIM}/1"), ("POST", f"{YONETIM}/1/gonder"), ("POST", f"{YONETIM}/1/iptal"),
     ("GET", f"{YONETIM}/1/pdf"), ("GET", f"{YONETIM}/1/surumler"), ("GET", f"{YONETIM}/1/imza-gorseli")],
)
async def test_yonetici_uclari_anonime_401_musteriye_403(istemci, musteri_basligi, metot, yol):
    govde = {} if metot in ("POST", "PUT") else None
    assert (await istemci.request(metot, yol, json=govde)).status_code == 401
    assert (await istemci.request(metot, yol, json=govde, headers=musteri_basligi())).status_code == 403


async def test_sablon_crud_ve_yer_tutucular(istemci, yonetici_basligi):
    y = await istemci.post(f"{YONETIM}/sablonlar", json={"baslik": "Bakım sözleşmesi", "govde": GOVDE,
                                                           "govde_en": "Agreement with {{musteri_adi}}"},
                           headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    sablon = y.json()
    y = await istemci.put(f"{YONETIM}/sablonlar/{sablon['id']}", json={"baslik": "Bakım sözleşmesi v2"}, headers=yonetici_basligi)
    assert y.json()["baslik"] == "Bakım sözleşmesi v2" and y.json()["govde"] == GOVDE
    liste = (await istemci.get(f"{YONETIM}/sablonlar", headers=yonetici_basligi)).json()
    assert any(s["id"] == sablon["id"] for s in liste["sablonlar"]) and "teklif_no" in liste["yer_tutucular"]
    assert (await istemci.post(f"{YONETIM}/sablonlar", json={"baslik": "", "govde": "x"}, headers=yonetici_basligi)).status_code == 400

    s = await _olustur(istemci, yonetici_basligi, sablon_id=sablon["id"], baslik=None, govde=None,
                       baslangic="2026-01-01", bitis="2026-12-31")
    assert "Ayşe Yılmaz" in s["govde"] and "By Mehmet KURU Dev" in s["govde"] and "01.01.2026 – 31.12.2026" in s["govde"]
    assert s["baslik"] == "Bakım sözleşmesi v2" and s["durum"] == "taslak" and s["surum"] == 1
    assert s["no"].startswith(f"SZL-{date.today().year}-")
    en = await _olustur(istemci, yonetici_basligi, sablon_id=sablon["id"], baslik=None, govde=None, dil="en")
    assert en["govde"] == "Agreement with Ayşe Yılmaz"
    y = await istemci.post(YONETIM, json={"govde": "x", "baslik": "x", "taraf_eposta": _eposta(), "bitis": "2025-01-01",
                                          "baslangic": "2026-01-01"}, headers=yonetici_basligi)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "bitis_once"
    assert (await istemci.delete(f"{YONETIM}/sablonlar/{sablon['id']}", headers=yonetici_basligi)).status_code == 200


async def test_imza_kaydi_metin_ozeti_ve_tek_kullanim(istemci, yonetici_basligi, db_oturumu):
    from models.audit_log import AuditLog
    from models.sozlesmeler import Sozlesmeler

    s = await _olustur(istemci, yonetici_basligi)
    jeton = await _gonder(istemci, yonetici_basligi, s["id"])
    acik = (await istemci.get(f"{ACIK}/{jeton}")).json()
    beklenen_ozet = _ozet(acik["baslik"], acik["govde"])
    assert acik["metin_ozeti"] == beklenen_ozet and acik["imzalanabilir"] is True and acik["durum"] == "gonderildi"
    assert s["taraf_ad"] == acik["taraf_ad"] and "***@" in acik["alici"]
    # Görüntüleme bağlantıyı tüketmez.
    assert (await istemci.get(f"{ACIK}/{jeton}")).status_code == 200

    def g(**ek):
        return {"ad_soyad": "Ayşe Yılmaz", "onay": True, "metin_ozeti": beklenen_ozet, **ek}

    for govde, kod in ((g(onay=False), "onay_gerekli"), (g(ad_soyad="A"), "ad_gerekli"),
                       (g(metin_ozeti="0" * 64), "metin_degisti"), (g(imza_png="data:image/png;base64,QUJD"), "imza_gorseli_gecersiz"),
                       (g(imza_png="data:image/svg+xml;base64,PHN2Zz4="), "imza_gorseli_gecersiz")):
        y = await istemci.post(f"{ACIK}/{jeton}/imza", json=govde)
        assert y.status_code in (400, 409) and y.json()["detail"]["kod"] == kod, (kod, y.text)

    y = await istemci.post(f"{ACIK}/{jeton}/imza", json=g(imza_png=_png()), headers={"User-Agent": "TestTarayici/1.0 (Linux)"})
    assert y.status_code == 200, y.text
    imzali = y.json()
    assert imzali["durum"] == "imzalandi" and imzali["imza_ad"] == "Ayşe Yılmaz" and imzali["imzalanabilir"] is False
    assert imzali["imza_metin_ozeti"] == beklenen_ozet and imzali["imza_gorseli_var"] is True

    kayit = (await db_oturumu.execute(select(Sozlesmeler).where(Sozlesmeler.id == s["id"]))).scalar_one()
    assert kayit.imza_at is not None and kayit.imza_tarayici == "TestTarayici/1.0 (Linux)"
    assert kayit.imza_ip_ozeti and len(kayit.imza_ip_ozeti) == 64 and kayit.imza_kanali == "baglanti"
    assert kayit.imza_metin_ozeti == kayit.metin_ozeti == beklenen_ozet
    # İkinci imza reddedilir.
    y = await istemci.post(f"{ACIK}/{jeton}/imza", json=g())
    assert y.status_code == 409
    # Yönetici imza görselini PNG olarak alır.
    y = await istemci.get(f"{YONETIM}/{s['id']}/imza-gorseli", headers=yonetici_basligi)
    assert y.status_code == 200 and y.content.startswith(b"\x89PNG")
    # Denetim: imza "onay" satırı; görsel anahtarı maskeli.
    satirlar = (await db_oturumu.execute(select(AuditLog).where(AuditLog.tablo.in_(("signed_actions", "sozlesmeler"))))).scalars().all()
    assert any(x.islem == "onay" and "sozlesme_imza: onay" in (x.ozet or "") for x in satirlar)
    for x in satirlar:
        if x.tablo == "sozlesmeler" and x.kayit_id == str(s["id"]) and x.degisiklik_json and "imza_gorsel_anahtari" in x.degisiklik_json:
            assert "sozlesmeler/imza/" not in x.degisiklik_json


async def test_imza_sonrasi_metin_degisikligi_yeni_surum(istemci, yonetici_basligi, db_oturumu):
    from models.sozlesmeler import Sozlesmeler

    s = await _olustur(istemci, yonetici_basligi)
    jeton = await _gonder(istemci, yonetici_basligi, s["id"])
    acik = (await istemci.get(f"{ACIK}/{jeton}")).json()
    await istemci.post(f"{ACIK}/{jeton}/imza", json={"ad_soyad": "Ayşe Yılmaz", "onay": True, "metin_ozeti": acik["metin_ozeti"]})

    # Yalnız bitiş (meta veri) imzalı sürümde değişebilir: yeni sürüm yok.
    y = await istemci.put(f"{YONETIM}/{s['id']}", json={"bitis": "2027-06-30"}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["yeni_surum"] is False and y.json()["id"] == s["id"]
    # Metin değişikliği → yeni sürüm, eskisi olduğu gibi.
    y = await istemci.put(f"{YONETIM}/{s['id']}", json={"govde": acik["govde"] + "\n\nEk madde: gizlilik."},
                          headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    yeni = y.json()
    assert yeni["yeni_surum"] is True and yeni["surum"] == 2 and yeni["no"] == s["no"] and yeni["onceki_id"] == s["id"]
    assert yeni["durum"] == "taslak" and yeni["imza_ad"] is None and "Ek madde" in yeni["govde"]
    eski = (await db_oturumu.execute(select(Sozlesmeler).where(Sozlesmeler.id == s["id"]))).scalar_one()
    await db_oturumu.refresh(eski)
    assert eski.durum == "imzalandi" and "Ek madde" not in eski.govde
    assert _ozet(eski.baslik, eski.govde) == eski.imza_metin_ozeti
    surumler = (await istemci.get(f"{YONETIM}/{s['id']}/surumler", headers=yonetici_basligi)).json()
    assert [x["surum"] for x in surumler] == [1, 2]


async def test_gonderilmis_sozlesmede_metin_degisirse_baglanti_iptal(istemci, yonetici_basligi):
    s = await _olustur(istemci, yonetici_basligi)
    jeton = await _gonder(istemci, yonetici_basligi, s["id"])
    acik = (await istemci.get(f"{ACIK}/{jeton}")).json()
    y = await istemci.put(f"{YONETIM}/{s['id']}", json={"govde": "Tamamen farklı metin"}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["durum"] == "taslak" and y.json()["yeni_surum"] is False
    acik2 = (await istemci.get(f"{ACIK}/{jeton}")).json()
    assert acik2["imzalanabilir"] is False and acik2["baglanti_durumu"] == "iptal"
    y = await istemci.post(f"{ACIK}/{jeton}/imza", json={"ad_soyad": "Ayşe Yılmaz", "onay": True, "metin_ozeti": acik["metin_ozeti"]})
    assert y.status_code in (409, 410)
    # Yeniden gönderilen bağlantı yeni metnin özetini taşır.
    jeton2 = await _gonder(istemci, yonetici_basligi, s["id"])
    acik3 = (await istemci.get(f"{ACIK}/{jeton2}")).json()
    assert acik3["metin_ozeti"] == _ozet(acik3["baslik"], "Tamamen farklı metin")


async def test_imzali_silinemez_iptal_ve_pdf_imza_blogu(istemci, yonetici_basligi):
    pytest.importorskip("pypdf")
    from services.pdf_belge import pdf_metni

    s = await _olustur(istemci, yonetici_basligi)
    jeton = await _gonder(istemci, yonetici_basligi, s["id"])
    # İmzasız PDF: "Henüz imzalanmadı."
    y = await istemci.get(f"{ACIK}/{jeton}/pdf")
    assert y.status_code == 200 and "Henüz imzalanmadı" in pdf_metni(y.content)
    acik = (await istemci.get(f"{ACIK}/{jeton}")).json()
    await istemci.post(f"{ACIK}/{jeton}/imza", json={"ad_soyad": "Ayşe Yılmaz", "onay": True,
                                                     "metin_ozeti": acik["metin_ozeti"], "imza_png": _png()})
    y = await istemci.delete(f"{YONETIM}/{s['id']}", headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "imzali_silinemez"
    y = await istemci.get(f"{ACIK}/{jeton}/pdf")
    assert y.status_code == 200 and y.headers["content-type"] == "application/pdf"
    metin = pdf_metni(y.content)
    for parca in ("SÖZLEŞME", s["no"], "Işıklı Ğıda", "Ayşe Yılmaz", "5070 sayılı", "güvenli elektronik imza değildir",
                  acik["metin_ozeti"], "İmzalayan", "Taraflar"):
        assert parca in metin, (parca, metin[:800])
    # İptal: imzalı sözleşme iptal edilebilir (silinmez).
    y = await istemci.post(f"{YONETIM}/{s['id']}/iptal", headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["durum"] == "iptal"
    # İmzasız taslak silinir.
    t = await _olustur(istemci, yonetici_basligi)
    assert (await istemci.delete(f"{YONETIM}/{t['id']}", headers=yonetici_basligi)).status_code == 200


async def test_bos_tuval_imza_sayilmaz(istemci, yonetici_basligi, db_oturumu):
    from models.sozlesmeler import Sozlesmeler

    s = await _olustur(istemci, yonetici_basligi)
    jeton = await _gonder(istemci, yonetici_basligi, s["id"])
    acik = (await istemci.get(f"{ACIK}/{jeton}")).json()
    y = await istemci.post(f"{ACIK}/{jeton}/imza", json={"ad_soyad": "Ali Veli", "onay": True, "metin_ozeti": acik["metin_ozeti"],
                                                         "imza_png": _png(bos=True)})
    assert y.status_code == 200 and y.json()["imza_gorseli_var"] is False
    kayit = (await db_oturumu.execute(select(Sozlesmeler).where(Sozlesmeler.id == s["id"]))).scalar_one()
    assert kayit.imza_gorsel_anahtari is None


async def test_bitis_hatirlatmasi_esik_basina_bir_kez(istemci, yonetici_basligi, db_oturumu):
    from models.notifications import Notifications
    from services.sozlesmeler import bitis_hatirlatmalari

    musteri = _eposta("bitis")
    bugun = date.today()
    s = await _olustur(istemci, yonetici_basligi, hesap_email=musteri, taraf_eposta=musteri,
                       bitis=(bugun + timedelta(days=25)).isoformat())
    jeton = await _gonder(istemci, yonetici_basligi, s["id"])
    acik = (await istemci.get(f"{ACIK}/{jeton}")).json()
    await istemci.post(f"{ACIK}/{jeton}/imza", json={"ad_soyad": "Ali Veli", "onay": True, "metin_ozeti": acik["metin_ozeti"]})

    async def musteri_bildirimleri():
        return (await db_oturumu.execute(select(Notifications).where(
            Notifications.event_type == "sozlesme_bitis", Notifications.recipient_email == musteri,
            Notifications.channel == "inapp"))).scalars().all()

    await bitis_hatirlatmalari(db_oturumu, bugun)
    assert len(await musteri_bildirimleri()) == 1
    await bitis_hatirlatmalari(db_oturumu, bugun)  # aynı gün ikinci tur: yeni bildirim yok
    assert len(await musteri_bildirimleri()) == 1
    await bitis_hatirlatmalari(db_oturumu, bugun + timedelta(days=19))  # 6 gün kala → 7 eşiği
    assert len(await musteri_bildirimleri()) == 2
    await bitis_hatirlatmalari(db_oturumu, bugun + timedelta(days=20))
    assert len(await musteri_bildirimleri()) == 2


async def test_musteri_sozlesmeleri_ve_panelden_imza(istemci, yonetici_basligi, musteri_basligi):
    a, b = _eposta("a"), _eposta("b")
    taslak = await _olustur(istemci, yonetici_basligi, hesap_email=a, taraf_eposta=a)
    s = await _olustur(istemci, yonetici_basligi, hesap_email=a, taraf_eposta=a)
    await _gonder(istemci, yonetici_basligi, s["id"])
    liste = (await istemci.get(MUSTERI, headers=musteri_basligi(a))).json()
    assert [x["id"] for x in liste] == [s["id"]] and taslak["id"] not in [x["id"] for x in liste]
    assert "imza_ip_ozeti" not in liste[0] and "hesap_email" not in liste[0]
    assert (await istemci.get(f"{MUSTERI}/{s['id']}", headers=musteri_basligi(b))).status_code == 404
    assert (await istemci.get(MUSTERI)).status_code == 401
    y = await istemci.post(f"{MUSTERI}/{s['id']}/imza", json={"ad_soyad": "Panel İmzacı", "onay": True,
                                                             "metin_ozeti": liste[0]["metin_ozeti"], "imza_png": _png()},
                           headers=musteri_basligi(a))
    assert y.status_code == 200, y.text
    assert y.json()["durum"] == "imzalandi" and y.json()["imza_ad"] == "Panel İmzacı"
    y = await istemci.get(f"{MUSTERI}/{s['id']}/pdf", headers=musteri_basligi(a))
    assert y.status_code == 200 and y.content.startswith(b"%PDF")


async def test_genel_islem_ucu_sozlesme_turunu_gostermez(istemci, yonetici_basligi):
    s = await _olustur(istemci, yonetici_basligi)
    jeton = await _gonder(istemci, yonetici_basligi, s["id"])
    assert (await istemci.get(f"/api/v1/islem/{jeton}")).status_code == 404
    # Teklif jetonu sözleşme ucunda (ve tersi) çalışmaz.
    assert (await istemci.get(f"/api/v1/teklif/{jeton}")).status_code == 404
