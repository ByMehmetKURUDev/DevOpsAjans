"""Faz 3T — teklif (öneri) modülü ve kalem hesabı testleri.

Kapsam: Decimal/kuruş hesabı (istemci toplamı yok sayılır), yetki, numara,
girişsiz bağlantı (görüntüleme çoklu + sayaç, karar tek), ad soyad zorunluluğu,
gerekçeli ret, süresi dolmuş teklif, revizyon, kabulde otomatik kayıtlar
(peşinat faturası + ödeme bağlantısı, sözleşme taslağı, proje), fiyat
sihirbazından teklife çevirme, müşteri yalnız kendi teklifini görür, PDF'te
Türkçe harfler, genel `/islem` ucunun bu türü göstermemesi, denetim kaydı.
"""

import re
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

YONETIM = "/api/v1/teklif-yonetim"
ACIK = "/api/v1/teklif"
MUSTERI = "/api/v1/tekliflerim"

KALEMLER = [
    {"aciklama": "Kurumsal web sitesi — tasarım ve geliştirme", "adet": 3, "birim_fiyat": "333.335", "kdv_orani": 20, "indirim": 10},
    {"aciklama": "Barındırma (aylık)", "adet": 1, "birim_fiyat": 0.1, "kdv_orani": 20},
    {"aciklama": "Eğitim — Işıl & Gülşen", "adet": 1, "birim_fiyat": 0.2, "kdv_orani": 10},
]


def _eposta(on: str = "teklif") -> str:
    return f"{on}-{uuid.uuid4().hex[:10]}@test.dev"


@pytest.fixture(autouse=True)
def _sinir_sifirla():
    from routers import sozlesmeler, teklifler

    for r in (teklifler, sozlesmeler):
        r.hiz_siniri.temizle()
    yield


async def _olustur(istemci, baslik, beklenen=200, **govde):
    veri = {"baslik": "Kurumsal site teklifi — Işıklı Ğıda", "kalemler": KALEMLER, "para_birimi": "TRY", **govde}
    y = await istemci.post(YONETIM, json=veri, headers=baslik)
    assert y.status_code == beklenen, y.text
    return y.json()


async def _gonder(istemci, baslik, teklif_id):
    y = await istemci.post(f"{YONETIM}/{teklif_id}/gonder", json={}, headers=baslik)
    assert y.status_code == 200, y.text
    govde = y.json()
    assert govde["baglanti"].startswith("https://mehmetkuru.dev/teklif/")
    return govde["baglanti"].rsplit("/", 1)[1]


# ---------------------------------------------------------------------------
# Kalem hesabı (saf)
# ---------------------------------------------------------------------------
def test_kalem_hesabi_kurus_dogrulugu_ve_kdv_dokumu():
    from services.belge_hesap import belge_hesapla

    b = belge_hesapla(KALEMLER)
    # 3 × 333.335 = 1000.005 → 1000.01 (yarım yukarı); %10 indirim 100.00; matrah 900.01; KDV %20 = 180.00
    k = b.kalemler[0]
    assert (k.brut, k.indirim_tutari, k.matrah, k.kdv, k.toplam) == (
        Decimal("1000.01"), Decimal("100.00"), Decimal("900.01"), Decimal("180.00"), Decimal("1080.01"))
    # 0.1 ve 0.2: float hatası yok
    assert b.kalemler[1].kdv == Decimal("0.02") and b.kalemler[2].kdv == Decimal("0.02")
    assert b.ara_toplam == Decimal("900.31")
    assert b.indirim_toplam == Decimal("100.00")
    assert b.kdv_toplam == Decimal("180.04")
    assert b.genel_toplam == Decimal("1080.35")
    assert b.kdv_dokumu == [{"oran": 10.0, "matrah": 0.2, "kdv": 0.02}, {"oran": 20.0, "matrah": 900.11, "kdv": 180.02}]
    # Satırların toplamı alttaki toplamla birebir.
    assert sum(x.toplam for x in b.kalemler) == b.genel_toplam


@pytest.mark.parametrize(
    "kalem,kod",
    [
        ({"aciklama": "", "adet": 1, "birim_fiyat": 1}, "aciklama_gerekli"),
        ({"aciklama": "x", "adet": 0, "birim_fiyat": 1}, "adet_gecersiz"),
        ({"aciklama": "x", "adet": -1, "birim_fiyat": 1}, "adet_gecersiz"),
        ({"aciklama": "x", "adet": 1, "birim_fiyat": -5}, "birim_fiyat_gecersiz"),
        ({"aciklama": "x", "adet": 1, "birim_fiyat": "abc"}, "birim_fiyat_gecersiz"),
        ({"aciklama": "x", "adet": 1, "birim_fiyat": 1, "kdv_orani": 120}, "kdv_gecersiz"),
        ({"aciklama": "x", "adet": 1, "birim_fiyat": 1, "indirim": 101}, "indirim_gecersiz"),
        ({"aciklama": "x", "adet": True, "birim_fiyat": 1}, "adet_gecersiz"),
    ],
)
def test_gecersiz_kalemler(kalem, kod):
    from services.belge_hesap import HesapHatasi, belge_hesapla

    with pytest.raises(HesapHatasi) as h:
        belge_hesapla([kalem])
    assert h.value.kod == kod and h.value.sira == 0


# ---------------------------------------------------------------------------
# Yetki ve oluşturma
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "metot,yol",
    [("GET", YONETIM), ("POST", YONETIM), ("GET", f"{YONETIM}/1"), ("PUT", f"{YONETIM}/1"), ("DELETE", f"{YONETIM}/1"),
     ("POST", f"{YONETIM}/1/gonder"), ("POST", f"{YONETIM}/1/revize"), ("GET", f"{YONETIM}/1/pdf"),
     ("POST", f"{YONETIM}/hesapla"), ("GET", f"{YONETIM}/fiyat-talepleri"), ("POST", f"{YONETIM}/fiyat-talebinden/1")],
)
async def test_yonetici_uclari_anonime_401_musteriye_403(istemci, musteri_basligi, metot, yol):
    govde = {} if metot in ("POST", "PUT") else None
    assert (await istemci.request(metot, yol, json=govde)).status_code == 401
    assert (await istemci.request(metot, yol, json=govde, headers=musteri_basligi())).status_code == 403


async def test_olustur_sunucu_toplami_ve_numara(istemci, yonetici_basligi):
    musteri = _eposta()
    t1 = await _olustur(istemci, yonetici_basligi, hesap_email=musteri.upper(),
                        ara_toplam=1, genel_toplam=1, kdv_toplam=999)  # istemci toplamı yok sayılır
    assert t1["ozet"]["genel_toplam"] == 1080.35 and t1["ozet"]["ara_toplam"] == 900.31
    assert t1["ozet"]["kdv_toplam"] == 180.04 and t1["ozet"]["indirim_toplam"] == 100.0
    assert t1["kalemler"][0]["matrah"] == 900.01
    assert t1["hesap_email"] == musteri and t1["durum"] == "taslak"
    yil = date.today().year
    assert re.match(rf"^TKL-{yil}-\d{{4}}$", t1["no"]), t1["no"]
    t2 = await _olustur(istemci, yonetici_basligi, aday_ad="Aday Kişi", aday_eposta=_eposta("aday"))
    assert int(t2["no"].rsplit("-", 1)[1]) == int(t1["no"].rsplit("-", 1)[1]) + 1
    # Geçerlilik verilmezse +30 gün (Türkiye günü).
    from services.belge_ortak import tr_bugun

    assert t2["gecerlilik"] == (tr_bugun() + timedelta(days=30)).isoformat()
    # Önizleme ucu aynı kuralı kullanıyor.
    y = await istemci.post(f"{YONETIM}/hesapla", json={"kalemler": KALEMLER}, headers=yonetici_basligi)
    assert y.json()["genel_toplam"] == 1080.35


@pytest.mark.parametrize(
    "govde,kod",
    [
        ({"kalemler": []}, "kalem_gerekli"),
        ({"baslik": ""}, "baslik_gerekli"),
        ({"hesap_email": None, "aday_eposta": None}, "alici_gerekli"),
        ({"aday_eposta": "bozuk"}, "eposta_gecersiz"),
        ({"para_birimi": "XYZ"}, "para_birimi_gecersiz"),
        ({"gecerlilik": "31-12-2026"}, "gecerlilik_gecersiz"),
        ({"pesinat_yuzde": 150}, "pesinat_gecersiz"),
        ({"otomatik_sozlesme": True, "sozlesme_sablon_id": 999999}, "sablon_yok"),
    ],
)
async def test_gecersiz_teklif(istemci, yonetici_basligi, govde, kod):
    veri = {"baslik": "T", "kalemler": KALEMLER, "hesap_email": _eposta(), **govde}
    y = await istemci.post(YONETIM, json=veri, headers=yonetici_basligi)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == kod, y.text


# ---------------------------------------------------------------------------
# Bağlantı: görüntüleme çoklu, karar tek
# ---------------------------------------------------------------------------
async def test_goruntuleme_sayaci_maske_ve_tek_karar(istemci, yonetici_basligi, db_oturumu):
    from models.audit_log import AuditLog

    musteri = _eposta()
    t = await _olustur(istemci, yonetici_basligi, hesap_email=musteri)
    jeton = await _gonder(istemci, yonetici_basligi, t["id"])

    for beklenen in (1, 2, 3):
        y = await istemci.get(f"{ACIK}/{jeton}")
        assert y.status_code == 200, y.text
        assert musteri not in y.text and "hesap_email" not in y.json()
    acik = y.json()
    assert acik["alici"].startswith(musteri[0]) and "***@" in acik["alici"]
    assert acik["karar_verilebilir"] is True and acik["durum"] == "goruntulendi"
    yon = (await istemci.get(f"{YONETIM}/{t['id']}", headers=yonetici_basligi)).json()
    assert yon["goruntulenme_sayisi"] == 3
    assert yon["ilk_goruntulenme"] and yon["son_goruntulenme"] and yon["ilk_goruntulenme"] <= yon["son_goruntulenme"]

    # Kabul ad soyad ister — ve başarısız deneme bağlantıyı tüketmez.
    y = await istemci.post(f"{ACIK}/{jeton}/karar", json={"sonuc": "kabul"})
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "ad_gerekli"
    y = await istemci.post(f"{ACIK}/{jeton}/karar", json={"sonuc": "kabul", "ad_soyad": "  Ayşe   Yılmaz "})
    assert y.status_code == 200, y.text
    assert y.json()["durum"] == "kabul" and y.json()["karar_ad"] == "Ayşe Yılmaz"
    assert y.json()["karar_verilebilir"] is False
    # İkinci karar (kabul ya da ret) reddedilir.
    for g in ({"sonuc": "red", "not": "vazgeçtim"}, {"sonuc": "kabul", "ad_soyad": "Ayşe Yılmaz"}):
        y = await istemci.post(f"{ACIK}/{jeton}/karar", json=g)
        assert y.status_code == 409, y.text
    # Görüntüleme kabulden sonra da çalışıyor (PDF dahil).
    assert (await istemci.get(f"{ACIK}/{jeton}")).status_code == 200
    yon = (await istemci.get(f"{YONETIM}/{t['id']}", headers=yonetici_basligi)).json()
    assert yon["karar_at"] and yon["karar_ip_ozeti"] and len(yon["karar_ip_ozeti"]) == 16
    # Denetim: bağlantı kullanımı ("onay") ve teklifin güncellenmesi alıcı adına.
    satirlar = (await db_oturumu.execute(select(AuditLog).where(AuditLog.tablo.in_(("signed_actions", "teklifler"))))).scalars().all()
    assert any(s.islem == "onay" and "teklif_onay: kabul" in (s.ozet or "") for s in satirlar)
    assert any(s.tablo == "teklifler" and s.kayit_id == str(t["id"]) and s.aktor_eposta == musteri for s in satirlar)


async def test_ret_gerekce_zorunlu_ve_yoneticiye_bildirim(istemci, yonetici_basligi, db_oturumu):
    from models.notifications import Notifications

    t = await _olustur(istemci, yonetici_basligi, aday_ad="Aday", aday_eposta=_eposta("aday"))
    jeton = await _gonder(istemci, yonetici_basligi, t["id"])
    y = await istemci.post(f"{ACIK}/{jeton}/karar", json={"sonuc": "red"})
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "not_gerekli"
    y = await istemci.post(f"{ACIK}/{jeton}/karar", json={"sonuc": "red", "not": "Bütçe yetersiz"})
    assert y.status_code == 200 and y.json()["durum"] == "ret" and y.json()["karar_notu"] == "Bütçe yetersiz"
    satir = (await db_oturumu.execute(
        select(Notifications).where(Notifications.event_type == "teklif_karar", Notifications.ref_id == t["id"])
    )).scalars().first()
    assert satir is not None and "reddedildi" in satir.title and satir.recipient_role == "admin"


async def test_suresi_dolmus_teklif_kabul_edilemez(istemci, yonetici_basligi, db_oturumu):
    from models.teklifler import Teklifler

    t = await _olustur(istemci, yonetici_basligi, hesap_email=_eposta())
    jeton = await _gonder(istemci, yonetici_basligi, t["id"])
    kayit = (await db_oturumu.execute(select(Teklifler).where(Teklifler.id == t["id"]))).scalar_one()
    kayit.gecerlilik = (date.today() - timedelta(days=2)).isoformat()
    await db_oturumu.commit()
    y = await istemci.post(f"{ACIK}/{jeton}/karar", json={"sonuc": "kabul", "ad_soyad": "Ali Veli"})
    assert y.status_code == 410 and y.json()["detail"]["kod"] == "suresi_doldu"
    acik = (await istemci.get(f"{ACIK}/{jeton}")).json()
    assert acik["durum"] == "suresi_doldu" and acik["karar_verilebilir"] is False
    # Geçerliliği geçmiş teklif gönderilemez de.
    y = await istemci.post(f"{YONETIM}/{t['id']}/gonder", json={}, headers=yonetici_basligi)
    assert y.status_code == 409


async def test_gonderilen_teklif_duzenlenmez_revize_yeni_surum(istemci, yonetici_basligi):
    t = await _olustur(istemci, yonetici_basligi, hesap_email=_eposta())
    jeton = await _gonder(istemci, yonetici_basligi, t["id"])
    y = await istemci.put(f"{YONETIM}/{t['id']}", json={"baslik": "Yeni"}, headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "revize_gerekli"
    y = await istemci.post(f"{YONETIM}/{t['id']}/revize", headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    yeni = y.json()
    assert yeni["no"] == f"{t['no']}-R2" and yeni["surum"] == 2 and yeni["durum"] == "taslak"
    assert yeni["onceki_id"] == t["id"] and yeni["kok_id"] == t["id"]
    eski = (await istemci.get(f"{YONETIM}/{t['id']}", headers=yonetici_basligi)).json()
    assert eski["durum"] == "revize"
    acik = (await istemci.get(f"{ACIK}/{jeton}")).json()
    assert acik["baglanti_durumu"] == "iptal" and acik["karar_verilebilir"] is False
    y = await istemci.post(f"{ACIK}/{jeton}/karar", json={"sonuc": "kabul", "ad_soyad": "Ali Veli"})
    assert y.status_code == 410
    # Yeni sürüm düzenlenebilir ve toplam yeniden hesaplanır.
    y = await istemci.put(f"{YONETIM}/{yeni['id']}", json={"kalemler": [{"aciklama": "Tek", "birim_fiyat": 100, "kdv_orani": 20}]},
                          headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["ozet"]["genel_toplam"] == 120.0


# ---------------------------------------------------------------------------
# Kabulde otomatik kayıtlar
# ---------------------------------------------------------------------------
async def test_kabul_otomatik_fatura_sozlesme_proje(istemci, yonetici_basligi, db_oturumu):
    from models.invoices import Invoices
    from models.payments import Payments
    from models.projects import Projects
    from models.sozlesmeler import Sozlesmeler

    y = await istemci.post(
        "/api/v1/sozlesme-yonetim/sablonlar",
        json={"baslik": "Hizmet Sözleşmesi — {{musteri_adi}}",
              "govde": "Teklif {{teklif_no}} toplamı {{toplam}}. Taraf: {{musteri_adi}} · {{bilinmeyen}}"},
        headers=yonetici_basligi,
    )
    sablon = y.json()
    musteri = _eposta()
    t = await _olustur(
        istemci, yonetici_basligi, aday_ad="Ayşe Yılmaz", aday_eposta=musteri, otomatik_fatura=True, pesinat_yuzde=50,
        otomatik_sozlesme=True, sozlesme_sablon_id=sablon["id"], otomatik_proje=True,
    )
    jeton = await _gonder(istemci, yonetici_basligi, t["id"])
    y = await istemci.post(f"{ACIK}/{jeton}/karar", json={"sonuc": "kabul", "ad_soyad": "Ayşe Yılmaz"})
    assert y.status_code == 200, y.text
    yon = (await istemci.get(f"{YONETIM}/{t['id']}", headers=yonetici_basligi)).json()
    assert yon["fatura_id"] and yon["sozlesme_id"] and yon["proje_id"]
    # Aday artık hesap: kayıtlar onun e-postasına bağlı.
    assert yon["hesap_email"] == musteri

    fatura = (await db_oturumu.execute(select(Invoices).where(Invoices.id == yon["fatura_id"]))).scalar_one()
    # Peşinat %50: KDV oranı başına matrahın yarısı (900.11/2=450.06 → %20; 0.2/2=0.10 → %10)
    # %20: 450.06 + 90.01 = 540.07; %10: 0.10 + 0.01 = 0.11 → 540.18
    assert fatura.amount == 540.18
    assert fatura.teklif_id == t["id"] and fatura.client_email == musteri and fatura.status == "unpaid"
    assert fatura.kalemler and "Peşinat %50" in fatura.kalemler
    bekleyen = (await db_oturumu.execute(
        select(Payments).where(Payments.invoice_id == fatura.id, Payments.durum == "bekliyor")
    )).scalars().all()
    assert len(bekleyen) == 1 and bekleyen[0].tutar == fatura.amount

    sozlesme = (await db_oturumu.execute(select(Sozlesmeler).where(Sozlesmeler.id == yon["sozlesme_id"]))).scalar_one()
    assert sozlesme.durum == "taslak" and sozlesme.teklif_id == t["id"]
    assert t["no"] in sozlesme.govde and "Ayşe Yılmaz" in sozlesme.baslik
    assert "1.080,35" in sozlesme.govde and "{{bilinmeyen}}" in sozlesme.govde
    proje = (await db_oturumu.execute(select(Projects).where(Projects.id == yon["proje_id"]))).scalar_one()
    assert proje.client_email == musteri and proje.published is False and proje.stage == "discovery"


async def test_kabul_otomasyonu_patlarsa_karar_geri_alinir(istemci, yonetici_basligi, db_oturumu, monkeypatch):
    """Otomatik kayıt oluşturulamazsa karar da yazılmaz; bağlantı yeniden denenebilir."""
    from services import teklifler as servis

    t = await _olustur(istemci, yonetici_basligi, hesap_email=_eposta(), otomatik_proje=True)
    jeton = await _gonder(istemci, yonetici_basligi, t["id"])

    async def _patla(db, teklif):
        raise RuntimeError("proje tablosu yok")

    monkeypatch.setattr(servis, "_kabul_otomasyonu", _patla)
    with pytest.raises(RuntimeError):
        await istemci.post(f"{ACIK}/{jeton}/karar", json={"sonuc": "kabul", "ad_soyad": "Ali Veli"})
    monkeypatch.undo()
    acik = (await istemci.get(f"{ACIK}/{jeton}")).json()
    assert acik["durum"] in ("gonderildi", "goruntulendi") and acik["karar_verilebilir"] is True
    y = await istemci.post(f"{ACIK}/{jeton}/karar", json={"sonuc": "kabul", "ad_soyad": "Ali Veli"})
    assert y.status_code == 200 and y.json()["durum"] == "kabul"


async def test_fiyat_sihirbazindan_teklife_cevir(istemci, yonetici_basligi, db_oturumu):
    from models.invoices import Invoices
    from models.pricing import Pricing_inquiries

    musteri = _eposta("sihirbaz")
    fatura = Invoices(invoice_no=f"FIY-{uuid.uuid4().hex[:6]}", client_email=musteri, amount=450.0, currency="USD",
                      status="pending")
    db_oturumu.add(fatura)
    await db_oturumu.commit()
    talep = Pricing_inquiries(scale_kod="BETA", profile_kod="kobi", period="aylik", addon_ids='["Blog"]',
                              hesaplanan_tutar=450.0, musteri_eposta=musteri, musteri_adi="Sihirbaz Müşteri",
                              kaynak="website", invoice_id=fatura.id)
    db_oturumu.add(talep)
    await db_oturumu.commit()

    liste = (await istemci.get(f"{YONETIM}/fiyat-talepleri", headers=yonetici_basligi)).json()
    assert any(x["id"] == talep.id and x["teklif"] is None for x in liste)
    y = await istemci.post(f"{YONETIM}/fiyat-talebinden/{talep.id}", headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    t = y.json()
    assert t["pricing_inquiry_id"] == talep.id and t["fatura_id"] == fatura.id and t["para_birimi"] == "USD"
    assert t["ozet"]["genel_toplam"] == 450.0 and "Blog" in t["kalemler"][0]["aciklama"]
    # İkinci çevirme reddedilir.
    y = await istemci.post(f"{YONETIM}/fiyat-talebinden/{talep.id}", headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "zaten_teklif"
    jeton = await _gonder(istemci, yonetici_basligi, t["id"])
    y = await istemci.post(f"{ACIK}/{jeton}/karar", json={"sonuc": "kabul", "ad_soyad": "Sihirbaz Müşteri"})
    assert y.status_code == 200, y.text
    await db_oturumu.refresh(talep)
    assert talep.durum == "kabul"
    # Sihirbazın faturası yeniden kullanıldı: ikinci fatura yok.
    sayi = (await db_oturumu.execute(select(Invoices).where(Invoices.teklif_id == t["id"]))).scalars().all()
    assert sayi == []


# ---------------------------------------------------------------------------
# Müşteri, PDF, genel uç
# ---------------------------------------------------------------------------
async def test_musteri_yalniz_kendi_teklifini_gorur_ve_panelden_karar(istemci, yonetici_basligi, musteri_basligi):
    a, b = _eposta("a"), _eposta("b")
    taslak = await _olustur(istemci, yonetici_basligi, hesap_email=a)
    t = await _olustur(istemci, yonetici_basligi, hesap_email=a)
    await _gonder(istemci, yonetici_basligi, t["id"])
    y = await istemci.get(MUSTERI, headers=musteri_basligi(a))
    assert y.status_code == 200
    kimlikler = [x["id"] for x in y.json()]
    assert t["id"] in kimlikler and taslak["id"] not in kimlikler  # taslak görünmez
    assert all("hesap_email" not in x and "goruntulenme_sayisi" not in x for x in y.json())
    assert (await istemci.get(MUSTERI, headers=musteri_basligi(b))).json() == []
    assert (await istemci.get(f"{MUSTERI}/{t['id']}", headers=musteri_basligi(b))).status_code == 404
    assert (await istemci.get(f"{MUSTERI}/{t['id']}/pdf", headers=musteri_basligi(b))).status_code == 404
    assert (await istemci.get(MUSTERI)).status_code == 401
    y = await istemci.post(f"{MUSTERI}/{t['id']}/karar", json={"sonuc": "kabul"}, headers=musteri_basligi(a))
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "ad_gerekli"
    y = await istemci.post(f"{MUSTERI}/{t['id']}/karar", json={"sonuc": "kabul", "ad_soyad": "Panel Kullanıcısı"},
                           headers=musteri_basligi(a))
    assert y.status_code == 200 and y.json()["durum"] == "kabul"
    y = await istemci.post(f"{MUSTERI}/{t['id']}/karar", json={"sonuc": "red", "not": "x"}, headers=musteri_basligi(a))
    assert y.status_code == 409


async def test_pdf_turkce_karakterler(istemci, yonetici_basligi):
    pytest.importorskip("pypdf")
    from services.pdf_belge import pdf_metni

    t = await _olustur(istemci, yonetici_basligi, hesap_email=_eposta(), notlar="Ödeme şartı: %50 peşin; İstanbul")
    jeton = await _gonder(istemci, yonetici_basligi, t["id"])
    y = await istemci.get(f"{ACIK}/{jeton}/pdf")
    assert y.status_code == 200 and y.headers["content-type"] == "application/pdf"
    assert "noindex" in y.headers.get("x-robots-tag", "") and "attachment" in y.headers["content-disposition"]
    metin = pdf_metni(y.content)
    for parca in ("TEKLİF", t["no"], "Işıklı Ğıda", "Eğitim — Işıl & Gülşen", "Ödeme şartı", "İstanbul",
                  "1.080,35", "e-Fatura/e-Arşiv"):
        assert parca in metin, (parca, metin[:500])
    y = await istemci.get(f"{YONETIM}/{t['id']}/pdf?dil=en", headers=yonetici_basligi)
    assert y.status_code == 200 and "QUOTE" in pdf_metni(y.content)


async def test_genel_islem_ucu_teklif_turunu_gostermez(istemci, yonetici_basligi):
    t = await _olustur(istemci, yonetici_basligi, hesap_email=_eposta())
    jeton = await _gonder(istemci, yonetici_basligi, t["id"])
    assert (await istemci.get(f"/api/v1/islem/{jeton}")).status_code == 404
    assert (await istemci.post(f"/api/v1/islem/{jeton}", json={"sonuc": "kabul"})).status_code == 404
    # Genel "bağlantı üret" de bu türü kabul etmiyor.
    y = await istemci.post("/api/v1/islem-yonetim/olustur", json={"tur": "teklif_onay", "hedef_id": t["id"]},
                           headers=yonetici_basligi)
    assert y.status_code == 400


async def test_kabul_edilen_teklif_silinemez_taslak_silinir(istemci, yonetici_basligi):
    t = await _olustur(istemci, yonetici_basligi, hesap_email=_eposta())
    jeton = await _gonder(istemci, yonetici_basligi, t["id"])
    await istemci.post(f"{ACIK}/{jeton}/karar", json={"sonuc": "kabul", "ad_soyad": "Ali Veli"})
    y = await istemci.delete(f"{YONETIM}/{t['id']}", headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "kabul_silinemez"
    t2 = await _olustur(istemci, yonetici_basligi, hesap_email=_eposta())
    assert (await istemci.delete(f"{YONETIM}/{t2['id']}", headers=yonetici_basligi)).status_code == 200


async def test_bilinmeyen_jeton_404_ve_hiz_siniri(istemci):
    from routers.teklifler import hiz_siniri

    assert (await istemci.get(f"{ACIK}/olmayan-jeton")).status_code == 404
    hiz_siniri.temizle()
    kodlar = [(await istemci.get(f"{ACIK}/olmayan-{i}")).status_code for i in range(22)]
    assert kodlar.count(429) >= 1
    hiz_siniri.temizle()
