"""Faz 4W — otomasyon kuralları ve özel alanlar.

Kapsam: koşul değerlendirici (her işleç, VE/VEYA, eksik alan), yer tutucu çözücü (HTML
kaçışı, bilinmeyen değişken, enjeksiyon denemesi), kural doğrulama, CRUD + modül kapısı,
olay → kuyruk → çalıştırma (e-posta, bildirim, görev, CRM, destek, webhook), pazarlama
izni yokken e-postanın atlanması, döngü ve derinlik koruması, hız sınırı, idempotency,
"bekle" → zamanlı uçta devam, kuru çalıştırmanın eylem yapmaması, müşteri izolasyonu,
`fatura.gecikti`, hazır şablonlar, özel alan CRUD + doğrulama + müşteriye görünürlük,
form → özel alan eşlemesi, herkese açık API'de `ozel_alanlar`.
"""

import json
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select, update

from conftest import jeton_uret

Y = "/api/v1/otomasyon/yonetim"
M = "/api/v1/otomasyonlarim"
OZ = "/api/v1/ozel-alanlar/yonetim"
OZM = "/api/v1/ozel-alanlarim"
MODUL = "/api/v1/moduller"


def _e(on: str = "oto") -> str:
    return f"{on}-{uuid.uuid4().hex[:8]}@oto.dev"


def _b(eposta: str, hesap: str | None = None, rol: str = "user") -> dict:
    h = {"Authorization": f"Bearer {jeton_uret(eposta, rol)}"}
    if hesap:
        h["X-MK-Hesap"] = hesap
    return h


def _kod(y) -> str:
    try:
        d = y.json().get("detail")
    except Exception:  # noqa: BLE001
        return ""
    return d.get("kod", "") if isinstance(d, dict) else ""


class _Posta:
    """Sahte e-posta gönderici: gönderimleri kaydeder."""

    def __init__(self):
        self.giden: list = []
        self.durum = ("sent", "test")

    async def __call__(self, alici, baslik, govde, ek=None):
        self.giden.append({"alici": alici, "konu": baslik, "govde": govde, "ek": ek or {}})
        return self.durum


@pytest.fixture(autouse=True)
async def _ortam(monkeypatch, db_oturumu):
    from models.otomasyon import OtomasyonCalismalari, OtomasyonKurallari, OzelAlanDegerleri, OzelAlanlar
    from routers import otomasyon as r
    from services import hesap_ekibi, notify, otomasyon, webhook

    r.hiz_sinirlarini_temizle()
    hesap_ekibi.onbellegi_temizle()
    otomasyon.onbellegi_temizle()
    monkeypatch.setattr(otomasyon, "ANLIK_ISLEME", False)
    monkeypatch.setattr(otomasyon, "POMPA_GECIKMESI_SN", 0)
    monkeypatch.setattr(webhook, "ANLIK_TESLIMAT", False)
    posta = _Posta()
    monkeypatch.setattr(notify, "_eposta_gonder", posta)
    yield posta
    # Bu dosyanın kuralları diğer testlerin olaylarında çalışmasın.
    for model in (OtomasyonCalismalari, OtomasyonKurallari, OzelAlanDegerleri, OzelAlanlar):
        await db_oturumu.execute(delete(model))
    await db_oturumu.commit()
    otomasyon.onbellegi_temizle()
    r.hiz_sinirlarini_temizle()


@pytest.fixture
def posta(_ortam):
    return _ortam


async def _modul_ac(istemci, yb, eposta, acik=True, **ayarlar):
    govde = {"acik": acik}
    if ayarlar:
        govde["ayarlar"] = ayarlar
    y = await istemci.put(f"{MODUL}/musteri/{eposta}/otomasyon", json=govde, headers=yb)
    assert y.status_code == 200, y.text


async def _musteri(istemci, yb, **ayarlar) -> str:
    e = _e("musteri")
    await _modul_ac(istemci, yb, e, **ayarlar)
    return e


async def _ekle(db, nesne):
    db.add(nesne)
    await db.commit()
    await db.refresh(nesne)
    return nesne


async def _proje(db, eposta, baslik="Proje"):
    from models.projects import Projects

    return await _ekle(db, Projects(title=baslik, description="d", category="Web", client_email=eposta, published=False,
                                    status="in_progress", stage="kesif", progress=0))


async def _kural(istemci, basliklar, yol=Y, **govde) -> dict:
    govde.setdefault("ad", "Test kuralı")
    y = await istemci.post(f"{yol}/kurallar", json=govde, headers=basliklar)
    assert y.status_code == 200, y.text
    return y.json()


async def _isle():
    from services import otomasyon

    return await otomasyon.bekleyenleri_isle()


async def _calismalar(db, kural_id=None):
    from models.otomasyon import OtomasyonCalismalari

    sorgu = select(OtomasyonCalismalari).order_by(OtomasyonCalismalari.id).execution_options(populate_existing=True)
    if kural_id is not None:
        sorgu = sorgu.where(OtomasyonCalismalari.kural_id == kural_id)
    return list((await db.execute(sorgu)).scalars().all())


EPOSTA_EYLEMI = {"tur": "eposta", "nitelik": "bilgilendirme", "alici": "kisi", "konu": "Merhaba {{aday.ad}}",
                 "govde": "Sayın {{aday.ad}},\nkaynak: {{aday.kaynak}}"}


# ---------------------------------------------------------------------------
# Saf: koşul değerlendirici
# ---------------------------------------------------------------------------
def test_kosul_isleçleri_ve_baglaclar():
    from services.otomasyon_kural import kosul_tek, kosullari_degerlendir

    b = {
        "aday": {"ad": "Ayşe Yılmaz", "deger_tahmini": 25000, "etiketler": ["web", "seo"], "sorumlu": None,
                 "asama": "teklif", "pazarlama_izni": True, "ozel": {"butce": "orta"}},
        "fatura": {"vade_tarihi": "2026-09-28", "gecikme_gun": 3},
        "_onceki": {"aday.asama": "yeni"},
    }

    def k(alan, islec, deger=None):
        return kosul_tek(b, {"alan": alan, "islec": islec, "deger": deger})[0]

    assert k("aday.ad", "esittir", "ayşe  yılmaz") and not k("aday.ad", "esittir", "Ayşe")
    assert k("aday.ad", "esit_degil", "Ali") and not k("aday.ad", "esit_degil", "AYŞE YILMAZ")
    assert k("aday.ad", "icerir", "yıl") and k("aday.ad", "icermez", "Kaya")
    assert k("aday.etiketler", "icerir", "SEO") and k("aday.etiketler", "esittir", "web") and k("aday.etiketler", "icermez", "ads")
    assert k("aday.deger_tahmini", "buyuktur", "20000") and not k("aday.deger_tahmini", "kucuktur", "20000")
    assert k("aday.deger_tahmini", "esittir", "25000.0")
    assert k("fatura.vade_tarihi", "kucuktur", "2026-10-01") and k("fatura.vade_tarihi", "buyuktur", "2026-09-01T00:00:00Z")
    assert not k("aday.ad", "buyuktur", "abc")  # karşılaştırılamaz → yanlış
    assert k("aday.sorumlu", "bos") and not k("aday.sorumlu", "dolu") and k("aday.ad", "dolu")
    assert k("aday.pazarlama_izni", "esittir", "evet") and not k("aday.pazarlama_izni", "esittir", "false")
    assert k("aday.ozel.butce", "esittir", "orta")
    assert k("aday.asama", "degisti") and not k("aday.ad", "degisti")
    # Eksik alan: hata değil; boş doğru, diğerleri yanlış.
    assert k("aday.yok", "bos") and not k("aday.yok", "dolu") and not k("aday.yok", "esittir", "x")
    assert not k("aday.yok", "esit_degil", "x") and not k("talep.konu", "icerir", "x")
    # Öznitelik/özel ad erişimi yok.
    assert k("aday.__class__", "bos") and k("_onceki.aday", "bos")

    ve = {"baglac": "ve", "kosullar": [{"alan": "aday.ad", "islec": "dolu"}, {"alan": "aday.sorumlu", "islec": "dolu"}]}
    veya = {**ve, "baglac": "veya"}
    assert kosullari_degerlendir(ve, b)[0] is False
    sonuc, ayrinti = kosullari_degerlendir(veya, b)
    assert sonuc is True and [a["sonuc"] for a in ayrinti] == [True, False]
    assert kosullari_degerlendir({"baglac": "ve", "kosullar": []}, b) == (True, [])
    assert kosullari_degerlendir(None, b)[0] is True


# ---------------------------------------------------------------------------
# Saf: yer tutucu çözücü
# ---------------------------------------------------------------------------
def test_yer_tutucu_kacis_bilinmeyen_ve_enjeksiyon():
    from services.otomasyon_kural import yer_tutuculari_coz

    b = {"aday": {"ad": "<script>alert(1)</script> & \"Ali\"", "firma": "{{hesap.email}}", "puan": 40.0,
                  "etiketler": ["a", "b"], "bos": ""},
         "hesap": {"email": "gizli@ornek.com"}}
    html, bilinmeyen = yer_tutuculari_coz("Merhaba <b>{{aday.ad}}</b> {{ aday.puan }}", b, "html")
    assert "<script>" not in html and "&lt;script&gt;" in html and "&amp; &quot;Ali&quot;" in html
    assert "&lt;b&gt;" in html  # şablonun kendi metni de kaçışlı (HTML yazılamaz)
    assert "40" in html and bilinmeyen == []
    # Tek geçiş: değerin içindeki yer tutucu çözülmez.
    metin, _ = yer_tutuculari_coz("Firma: {{aday.firma}}", b, "metin")
    assert metin == "Firma: {{hesap.email}}" and "gizli@" not in metin
    # Bilinmeyen değişken boşa döner ve raporlanır; varsayılan kullanılır.
    metin, bilinmeyen = yer_tutuculari_coz("[{{aday.yok}}][{{aday.bos|Değerli müşterimiz}}][{{aday.etiketler}}]", b)
    assert metin == "[][Değerli müşterimiz][a, b]" and bilinmeyen == ["aday.yok"]
    # Jinja benzeri ifadeler / öznitelik erişimi yer tutucu sayılmaz.
    for sablon in ("{{ aday.__class__ }}", "{{ 7*7 }}", "{% for x in y %}", "{{aday.ad.upper()}}"):
        cikti, _ = yer_tutuculari_coz(sablon, b)
        assert "49" not in cikti and "class" not in cikti.replace("__class__", "") and "<script>" not in yer_tutuculari_coz(sablon, b, "html")[0]
    # Konu: satır sonu/denetim karakteri yok (başlık enjeksiyonu).
    b2 = {"aday": {"ad": "Ali\r\nBcc: kotu@ornek.com\x00"}}
    konu, _ = yer_tutuculari_coz("Hoş geldin {{aday.ad}}", b2, "konu")
    assert "\n" not in konu and "\r" not in konu and "\x00" not in konu and konu.startswith("Hoş geldin Ali Bcc:")


# ---------------------------------------------------------------------------
# Doğrulama ve CRUD
# ---------------------------------------------------------------------------
async def test_kural_dogrulama_hatalari(istemci, yonetici_basligi):
    async def dene(govde, kod):
        y = await istemci.post(f"{Y}/kurallar", json={"ad": "x", **govde}, headers=yonetici_basligi)
        assert y.status_code == 400 and _kod(y) == kod, (kod, y.text)

    await dene({"tetik": "yok.boyle", "eylemler": [EPOSTA_EYLEMI]}, "tetik_gecersiz")
    await dene({"tetik": "aday.olusturuldu", "eylemler": []}, "eylem_gerekli")
    await dene({"tetik": "aday.olusturuldu", "eylemler": [{**EPOSTA_EYLEMI, "nitelik": None}]}, "nitelik_gerekli")
    await dene({"tetik": "aday.olusturuldu", "eylemler": [{**EPOSTA_EYLEMI, "konu": "{{fatura.no}}"}]}, "degisken_bilinmiyor")
    await dene({"tetik": "aday.olusturuldu", "eylemler": [EPOSTA_EYLEMI] * 6}, "eylem_sayisi")
    await dene({"tetik": "aday.olusturuldu", "eylemler": [EPOSTA_EYLEMI, {"tur": "bekle", "miktar": 1, "birim": "saat"}]},
               "bekle_son_eylem_olamaz")
    await dene({"tetik": "aday.olusturuldu", "kosullar": {"baglac": "ve", "kosullar": [{"alan": "fatura.no", "islec": "dolu"}]},
                "eylemler": [EPOSTA_EYLEMI]}, "kosul_alani_bilinmiyor")
    await dene({"tetik": "aday.olusturuldu", "kosullar": {"kosullar": [{"alan": "aday.ad", "islec": "esittir"}]},
                "eylemler": [EPOSTA_EYLEMI]}, "kosul_degeri_gerekli")
    await dene({"tetik": "aday.olusturuldu", "kosullar": {"kosullar": [{"alan": "aday.ad", "islec": "degisti"}]},
                "eylemler": [EPOSTA_EYLEMI]}, "degisti_desteklenmiyor")
    await dene({"tetik": "aday.olusturuldu", "eylemler": [{"tur": "destek", "oncelik": "acil"}]}, "olayda_talep_yok")
    await dene({"tetik": "aday.olusturuldu", "eylemler": [{"tur": "gorev", "proje": "olay", "baslik": "x"}]}, "olayda_proje_yok")
    await dene({"tetik": "aday.olusturuldu", "eylemler": [{"tur": "gorev", "proje": 99999999, "baslik": "x"}]}, "proje_yok")
    await dene({"tetik": "aday.olusturuldu", "eylemler": [{"tur": "webhook", "uc_id": 99999999}]}, "webhook_yok")
    await dene({"tetik": "aday.olusturuldu", "eylemler": [{"tur": "crm_asama", "asama": "olmayan"}]}, "asama_yok")


async def test_ajans_crud_meta_ve_cop_kutusu(istemci, yonetici_basligi, db_oturumu):
    meta = (await istemci.get(f"{Y}/meta", headers=yonetici_basligi)).json()
    olaylar = {o["anahtar"]: o for o in meta["olaylar"]}
    assert {"aday.olusturuldu", "fatura.gecikti", "randevu.olusturuldu", "destek.olusturuldu"} <= set(olaylar)
    assert "qr.tarama" not in olaylar
    assert any(a["yol"] == "aday.ad" for a in olaylar["aday.olusturuldu"]["sema"])
    assert "crm_asama" in meta["eylemler"] and meta["sinirlar"]["eylem"] == 5
    k = await _kural(istemci, yonetici_basligi, tetik="aday.olusturuldu", eylemler=[EPOSTA_EYLEMI])
    assert k["sahip_tur"] == "ajans" and k["aktif"] is True and k["eylemler"][0]["nitelik"] == "bilgilendirme"
    y = await istemci.put(f"{Y}/kurallar/{k['id']}", json={"aktif": False, "ad": "Yeni ad"}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["aktif"] is False and y.json()["ad"] == "Yeni ad"
    # Tetik değişince eylemlerin yer tutucuları yeniden denetlenir.
    y = await istemci.put(f"{Y}/kurallar/{k['id']}", json={"tetik": "fatura.odendi"}, headers=yonetici_basligi)
    assert y.status_code == 400 and _kod(y) == "degisken_bilinmiyor"
    assert len((await istemci.get(f"{Y}/kurallar", headers=yonetici_basligi)).json()["items"]) == 1
    y = await istemci.delete(f"{Y}/kurallar/{k['id']}", headers=yonetici_basligi)
    assert y.status_code == 200
    from models.cop_kutusu import CopKutusu

    cop = (await db_oturumu.execute(select(CopKutusu).where(CopKutusu.tablo == "otomasyon_kurallari"))).scalars().all()
    assert any(int(c.kayit_id) == k["id"] for c in cop)
    assert (await istemci.get(f"{Y}/kurallar/{k['id']}", headers=yonetici_basligi)).status_code == 404


async def test_musteri_modul_kapali_403_acik_ve_kisitlar(istemci, yonetici_basligi):
    e = _e("kapali")
    y = await istemci.get(f"{M}/kurallar", headers=_b(e))
    assert y.status_code == 403 and _kod(y) == "modul_kapali"
    assert (await istemci.get(f"{M}/kurallar")).status_code == 401
    assert (await istemci.get(f"{Y}/kurallar", headers=_b(e))).status_code == 403
    await _modul_ac(istemci, yonetici_basligi, e)
    meta = (await istemci.get(f"{M}/meta", headers=_b(e))).json()
    assert meta["sahip_tur"] == "musteri"
    assert all(not o["anahtar"].startswith("aday.") for o in meta["olaylar"])
    assert "crm_asama" not in meta["eylemler"] and "destek" not in meta["eylemler"] and "eposta" in meta["eylemler"]
    assert {s["anahtar"] for s in meta["sablonlar"]} == {"teklif_kabul_gorev", "fatura_gecikti_hatirlatma", "destek_acil_bildirim"}
    y = await istemci.post(f"{M}/kurallar", json={"ad": "x", "tetik": "aday.olusturuldu", "eylemler": [EPOSTA_EYLEMI]}, headers=_b(e))
    assert y.status_code == 400 and _kod(y) == "tetik_yalniz_ajans"
    y = await istemci.post(f"{M}/kurallar", json={"ad": "x", "tetik": "destek.olusturuldu",
                                                  "eylemler": [{"tur": "crm_etiket", "etiket": "x"}]}, headers=_b(e))
    assert y.status_code == 400 and _kod(y) == "eylem_yalniz_ajans"
    y = await istemci.post(f"{M}/kurallar/sablondan", json={"sablon": "yeni_aday_hosgeldin"}, headers=_b(e))
    assert y.status_code == 404
    y = await istemci.post(f"{M}/kurallar/sablondan", json={"sablon": "destek_acil_bildirim"}, headers=_b(e))
    assert y.status_code == 200 and y.json()["eylemler"][0]["alici"] == "hesap"
    # Kural sınırı (modül ayarı).
    await _modul_ac(istemci, yonetici_basligi, e, kural_siniri=1)
    y = await istemci.post(f"{M}/kurallar/sablondan", json={"sablon": "destek_acil_bildirim"}, headers=_b(e))
    assert y.status_code == 409 and _kod(y) == "kural_siniri"


async def test_hazir_sablonlar_ajans(istemci, yonetici_basligi):
    from services.otomasyon_kural import SABLONLAR

    for s in SABLONLAR:
        y = await istemci.post(f"{Y}/kurallar/sablondan", json={"sablon": s.anahtar, "metinler": {"ad": f"Şablon {s.anahtar}"}},
                               headers=yonetici_basligi)
        assert y.status_code == 200, (s.anahtar, y.text)
        assert y.json()["sablon"] == s.anahtar and y.json()["ad"] == f"Şablon {s.anahtar}"


# ---------------------------------------------------------------------------
# Çalıştırma: olay → kuyruk → eylemler
# ---------------------------------------------------------------------------
async def test_yeni_aday_kurali_eposta_gonderir_ve_gunluge_yazar(istemci, yonetici_basligi, db_oturumu, posta):
    k = await _kural(istemci, yonetici_basligi, tetik="aday.olusturuldu", eylemler=[EPOSTA_EYLEMI])
    y = await istemci.post("/api/v1/crm/adaylar", json={"ad": "Ayşe <b>Y</b>", "email": "ayse-1@ornek.com"}, headers=yonetici_basligi)
    assert y.status_code == 201, y.text
    calismalar = await _calismalar(db_oturumu, k["id"])
    assert [c.durum for c in calismalar] == ["bekliyor"]  # istek yanıtı beklemedi
    ozet = await _isle()
    assert ozet["islenen"] == 1
    assert len(posta.giden) == 1
    g = posta.giden[0]
    assert g["alici"] == "ayse-1@ornek.com" and g["konu"] == "Merhaba Ayşe <b>Y</b>" and "kaynak: manuel" in g["govde"]
    assert "Ayşe &lt;b&gt;Y&lt;/b&gt;" in g["ek"]["html"] and "<b>Y</b>" not in g["ek"]["html"]
    gunluk = (await istemci.get(f"{Y}/gunluk?kural_id={k['id']}", headers=yonetici_basligi)).json()["items"]
    assert gunluk[0]["durum"] == "tamam" and gunluk[0]["eylem_sonuclari"][0]["durum"] == "basarili"
    assert (await istemci.get(f"{Y}/kurallar/{k['id']}", headers=yonetici_basligi)).json()["calisma_sayisi"] == 1
    # Gerçek bir olayla kuru çalıştırma: kayıt veritabanından okunur, yine hiçbir şey gönderilmez.
    y = await istemci.post(f"{Y}/kurallar/{k['id']}/test", json={"calisma_id": gunluk[0]["id"]}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["kaynak"] == "olay"
    assert y.json()["eylemler"][0]["ozet"]["alici"] == "ayse-1@ornek.com" and len(posta.giden) == 1
    # E-posta kanalı tanımlı değilse eylem atlanır (hata değil) ve nedeni yazılır.
    posta.durum = ("skipped", "RESEND_API_KEY ya da SMTP_HOST tanımlı değil")
    await istemci.post("/api/v1/crm/adaylar", json={"ad": "B", "email": "b-1@ornek.com"}, headers=yonetici_basligi)
    await _isle()
    son = (await istemci.get(f"{Y}/gunluk?kural_id={k['id']}", headers=yonetici_basligi)).json()["items"][0]
    assert son["eylem_sonuclari"][0]["durum"] == "atlandi" and son["eylem_sonuclari"][0]["neden"] == "eposta_kanali_yok"


async def test_pazarlama_epostasi_izin_yoksa_atlanir(istemci, yonetici_basligi, db_oturumu, posta):
    from models.crm import CrmAdaylari

    # Daha önce (Faz 4G formundan) pazarlama izni vermiş, kapanmış bir aday.
    await _ekle(db_oturumu, CrmAdaylari(ad="Eski", email="izinli@ornek.com", kaynak="form", asama="kazanildi",
                                         pazarlama_izni_at=datetime.now(timezone.utc), puan=0))
    k = await _kural(istemci, yonetici_basligi, tetik="aday.olusturuldu",
                     eylemler=[{**EPOSTA_EYLEMI, "nitelik": "pazarlama"}])
    await istemci.post("/api/v1/crm/adaylar", json={"ad": "İzinsiz", "email": "izinsiz@ornek.com"}, headers=yonetici_basligi)
    await _isle()
    assert posta.giden == []
    c = (await _calismalar(db_oturumu, k["id"]))[-1]
    sonuc = json.loads(c.eylem_sonuclari)[0]
    assert c.durum == "tamam" and sonuc["durum"] == "atlandi" and sonuc["neden"] == "pazarlama_izni_yok"
    # İzinli adayda gider.
    await istemci.post("/api/v1/crm/adaylar", json={"ad": "İzinli", "email": "izinli@ornek.com"}, headers=yonetici_basligi)
    await _isle()
    assert [g["alici"] for g in posta.giden] == ["izinli@ornek.com"]


async def test_kuru_calistirma_eylem_yapmaz(istemci, yonetici_basligi, db_oturumu, posta):
    from models.notifications import Notifications
    from models.proje_gorevleri import ProjectTasks

    p = await _proje(db_oturumu, _e("kuru"))
    k = await _kural(istemci, yonetici_basligi, tetik="aday.olusturuldu", eylemler=[
        EPOSTA_EYLEMI,
        {"tur": "bildirim", "alici": "yoneticiler", "baslik": "Yeni aday: {{aday.ad}}"},
        {"tur": "gorev", "proje": p.id, "baslik": "Ara: {{aday.ad}}", "son_tarih_gun": 2},
        {"tur": "crm_etiket", "islem": "ekle", "etiket": "sicak"},
    ])
    once_bildirim = len((await db_oturumu.execute(select(Notifications))).scalars().all())
    y = await istemci.post(f"{Y}/kurallar/{k['id']}/test", json={}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    d = y.json()
    assert d["kosul_sonucu"] is True and d["kaynak"] == "ornek"
    # Örnek veriyle olaydaki kayıt (aday) veritabanında aranmaz: ne yapılacağı bağlamdan anlatılır.
    assert [e["durum"] for e in d["eylemler"]] == ["yapilacak"] * 4
    assert d["eylemler"][3]["ozet"] == {"aday_id": 101, "islem": "ekle", "etiket": "sicak"}
    assert d["eylemler"][0]["ozet"]["konu"] == "Merhaba Ayşe Yılmaz" and d["eylemler"][0]["ozet"]["alici"] == "ayse@ornek.com"
    assert d["eylemler"][2]["ozet"]["baslik"] == "Ara: Ayşe Yılmaz"
    # Elle düzenlenmiş bağlam + koşul tutmazsa hiçbir eylem "yapılacak" değil.
    y = await istemci.post(f"{Y}/test", json={"kural": {"tetik": "aday.olusturuldu", "kosullar": {
        "kosullar": [{"alan": "aday.kaynak", "islec": "esittir", "deger": "form"}]}, "eylemler": [EPOSTA_EYLEMI]},
        "baglam": {"aday": {"ad": "Elle", "kaynak": "manuel", "email": "e@ornek.com"}}}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["kosul_sonucu"] is False and y.json()["eylemler"][0]["durum"] == "atlanacak"
    # Hiçbir yan etki yok.
    assert posta.giden == []
    assert len((await db_oturumu.execute(select(Notifications))).scalars().all()) == once_bildirim
    assert (await db_oturumu.execute(select(ProjectTasks).where(ProjectTasks.proje_id == p.id))).scalars().all() == []
    assert await _calismalar(db_oturumu, k["id"]) == []


async def test_gorev_bildirim_crm_ve_destek_eylemleri(istemci, yonetici_basligi, db_oturumu, posta):
    from models.crm import CrmAdaylari, CrmAktiviteler
    from models.notifications import Notifications
    from models.proje_gorevleri import ProjectTasks
    from models.support_tickets import Support_tickets

    e = _e("eylem")
    p = await _proje(db_oturumu, e)
    k1 = await _kural(istemci, yonetici_basligi, tetik="destek.olusturuldu",
                      kosullar={"baglac": "ve", "kosullar": [{"alan": "talep.oncelik", "islec": "esittir", "deger": "acil"}]},
                      eylemler=[{"tur": "destek", "etiket": "otomatik"},
                                {"tur": "gorev", "proje": "olay", "baslik": "İncele: {{talep.konu}}", "son_tarih_gun": 1,
                                 "oncelik": "acil"},
                                {"tur": "bildirim", "alici": "yoneticiler", "baslik": "Acil: {{talep.konu}}",
                                 "govde": "{{hesap.email}}"}])
    acil = await _ekle(db_oturumu, Support_tickets(client_email=e, subject="Site çöktü", message="m", status="open",
                                                    priority="acil", project_id=p.id))
    normal = await _ekle(db_oturumu, Support_tickets(client_email=e, subject="Soru", message="m", status="open",
                                                      priority="normal", project_id=p.id))
    await _isle()
    calismalar = await _calismalar(db_oturumu, k1["id"])
    assert sorted(c.durum for c in calismalar) == ["kosul_tutmadi", "tamam"]
    await db_oturumu.refresh(acil)
    assert "otomatik" in (acil.etiketler or "")
    gorevler = (await db_oturumu.execute(select(ProjectTasks).where(ProjectTasks.proje_id == p.id))).scalars().all()
    assert [g.baslik for g in gorevler] == ["İncele: Site çöktü"] and gorevler[0].oncelik == "acil"
    assert gorevler[0].olusturan_eposta == "otomasyon" and gorevler[0].bitis_tarihi == date.today() + timedelta(days=1)
    bildirim = (await db_oturumu.execute(select(Notifications).where(Notifications.event_type == "otomasyon_bildirimi",
                                                                     Notifications.title == "Acil: Site çöktü"))).scalars().all()
    assert bildirim and bildirim[0].body == e and bildirim[0].recipient_role == "admin"
    del normal

    # CRM eylemleri (aday olayında).
    k2 = await _kural(istemci, yonetici_basligi, tetik="aday.olusturuldu", eylemler=[
        {"tur": "crm_etiket", "islem": "ekle", "etiket": "oto"},
        {"tur": "crm_sahip", "sorumlu": "yonetici@test.dev"},
        {"tur": "crm_aktivite", "aktivite_tur": "not", "metin": "Kural notu: {{aday.ad}}"},
        {"tur": "crm_asama", "asama": "iletisim_kuruldu"},
    ])
    y = await istemci.post("/api/v1/crm/adaylar", json={"ad": "Crm Kişi", "email": "crm-k@ornek.com"}, headers=yonetici_basligi)
    aday_id = y.json()["id"]
    await _isle()
    db_oturumu.expire_all()
    a = (await db_oturumu.execute(select(CrmAdaylari).where(CrmAdaylari.id == aday_id))).scalars().one()
    assert "oto" in json.loads(a.etiketler) and a.sorumlu == "yonetici@test.dev"
    sonuc = json.loads((await _calismalar(db_oturumu, k2["id"]))[-1].eylem_sonuclari)
    assert [s["durum"] for s in sonuc[:3]] == ["basarili"] * 3
    assert sonuc[3]["durum"] == "basarili" and a.asama == "iletisim_kuruldu"
    notlar = (await db_oturumu.execute(select(CrmAktiviteler).where(CrmAktiviteler.aday_id == aday_id,
                                                                    CrmAktiviteler.yapan == "otomasyon"))).scalars().all()
    assert any(n.metin == "Kural notu: Crm Kişi" for n in notlar)


async def test_webhook_eylemi_teslimat_satiri_yazar(istemci, yonetici_basligi, db_oturumu):
    from models.api_erisimi import WebhookTeslimatlari, WebhookUcNoktalari

    uc = await _ekle(db_oturumu, WebhookUcNoktalari(sahip_tur="ajans", hesap_email=None, url="https://kanca.ornek.com/x",
                                                    olaylar='["fatura.odendi"]', aktif=True, gizli_anahtar="d1:whsec_x",
                                                    ardisik_hata=0))
    try:
        k = await _kural(istemci, yonetici_basligi, tetik="aday.olusturuldu",
                         eylemler=[{"tur": "webhook", "uc_id": uc.id, "etiket": "yeni_aday"}])
        await istemci.post("/api/v1/crm/adaylar", json={"ad": "Kanca", "email": "kanca@ornek.com"}, headers=yonetici_basligi)
        await _isle()
        t = (await db_oturumu.execute(select(WebhookTeslimatlari).where(WebhookTeslimatlari.uc_id == uc.id))).scalars().all()
        assert [x.tur for x in t] == ["otomasyon.yeni_aday"] and t[0].durum == "bekliyor"
        govde = json.loads(t[0].govde)
        assert govde["veri"]["kural_id"] == k["id"] and govde["veri"]["tetik"] == "aday.olusturuldu"
        assert "kanca@ornek.com" not in t[0].govde  # kişisel veri yok (yalnız kimlikler)
        # Uç noktası silinse de kural kapatılabilir (kısmi güncellemede saklı eylemler yeniden denetlenmez).
        await db_oturumu.execute(delete(WebhookTeslimatlari).where(WebhookTeslimatlari.uc_id == uc.id))
        await db_oturumu.execute(delete(WebhookUcNoktalari).where(WebhookUcNoktalari.id == uc.id))
        await db_oturumu.commit()
        y = await istemci.put(f"{Y}/kurallar/{k['id']}", json={"aktif": False}, headers=yonetici_basligi)
        assert y.status_code == 200 and y.json()["aktif"] is False
        y = await istemci.put(f"{Y}/kurallar/{k['id']}", json={"eylemler": k["eylemler"]}, headers=yonetici_basligi)
        assert y.status_code == 400 and _kod(y) == "webhook_yok"
    finally:
        await db_oturumu.execute(delete(WebhookTeslimatlari).where(WebhookTeslimatlari.uc_id == uc.id))
        await db_oturumu.execute(delete(WebhookUcNoktalari).where(WebhookUcNoktalari.id == uc.id))
        await db_oturumu.commit()
        from services import webhook

        webhook.onbellegi_temizle()


async def test_dongu_ve_derinlik_korumasi(istemci, yonetici_basligi, db_oturumu):
    from models.proje_gorevleri import ProjectTasks

    e = _e("dongu")
    p = await _proje(db_oturumu, e)

    def kural(harf, sonraki):
        return {"ad": f"{harf}→{sonraki}", "tetik": "gorev.olusturuldu",
                "kosullar": {"baglac": "ve", "kosullar": [{"alan": "gorev.baslik", "islec": "esittir", "deger": harf},
                                                          {"alan": "proje.id", "islec": "esittir", "deger": str(p.id)}]},
                "eylemler": [{"tur": "gorev", "proje": "olay", "baslik": sonraki}]}

    # Kendini tetikleyen kural: kendi açtığı görev onu yeniden çalıştırmaz.
    kendi = await _kural(istemci, yonetici_basligi, **{**kural("X", "X"), "ad": "kendi"})
    await _ekle(db_oturumu, ProjectTasks(proje_id=p.id, baslik="X", durum="yapilacak", oncelik="normal", sira=0,
                                         musteriye_gorunur=True, harcanan_saat=0.0))
    for _ in range(3):
        await _isle()
    durumlar = [(c.durum, c.neden) for c in await _calismalar(db_oturumu, kendi["id"])]
    assert durumlar == [("tamam", None), ("atlandi", "dongu")]
    await istemci.delete(f"{Y}/kurallar/{kendi['id']}", headers=yonetici_basligi)

    # Zincir: A→B→C→D→E; derinlik en çok 3 → D'yi açan olay (derinlik 4) E kuralını çalıştırmaz.
    kurallar = [await _kural(istemci, yonetici_basligi, **kural(a, b)) for a, b in (("A", "B"), ("B", "C"), ("C", "D"), ("D", "E"))]
    await _ekle(db_oturumu, ProjectTasks(proje_id=p.id, baslik="A", durum="yapilacak", oncelik="normal", sira=0,
                                         musteriye_gorunur=True, harcanan_saat=0.0))
    for _ in range(6):
        await _isle()
    basliklar = sorted(g.baslik for g in (await db_oturumu.execute(select(ProjectTasks).where(ProjectTasks.proje_id == p.id))).scalars().all())
    assert basliklar == ["A", "B", "C", "D", "X", "X"]
    son = await _calismalar(db_oturumu, kurallar[3]["id"])
    assert ("atlandi", "derinlik") in [(c.durum, c.neden) for c in son]
    assert max(c.derinlik for c in await _calismalar(db_oturumu)) == 4


async def test_hiz_siniri(istemci, yonetici_basligi, db_oturumu):
    from models.support_tickets import Support_tickets

    e = await _musteri(istemci, yonetici_basligi, calisma_dakika_siniri=2)
    k = await _kural(istemci, _b(e), M, tetik="destek.olusturuldu",
                     eylemler=[{"tur": "bildirim", "alici": "hesap", "baslik": "Talep: {{talep.konu}}"}])
    for i in range(3):
        await _ekle(db_oturumu, Support_tickets(client_email=e, subject=f"T{i}", message="m", status="open"))
    await _isle()
    durumlar = sorted((c.durum, c.neden) for c in await _calismalar(db_oturumu, k["id"]))
    assert durumlar == [("atlandi", "hiz_siniri_dakika"), ("tamam", None), ("tamam", None)]


async def test_idempotency_ve_kilit(istemci, yonetici_basligi, db_oturumu, posta):
    from services import otomasyon

    k = await _kural(istemci, yonetici_basligi, tetik="aday.olusturuldu", eylemler=[EPOSTA_EYLEMI])
    await istemci.post("/api/v1/crm/adaylar", json={"ad": "Tek", "email": "tek@ornek.com"}, headers=yonetici_basligi)
    c = (await _calismalar(db_oturumu, k["id"]))[0]
    from core.database import db_manager

    async with db_manager.async_session_maker() as o1:
        r1 = await otomasyon.calisma_isle(o1, c.id)
    async with db_manager.async_session_maker() as o2:
        r2 = await otomasyon.calisma_isle(o2, c.id)
    assert r1["durum"] == "tamam" and r2 == {"atlandi": "kilitli"}
    await _isle()
    assert len(posta.giden) == 1
    # Aynı (olay, kural) ikinci kez kuyruğa yazılamaz (belirlenimli kimlikli olay).
    from services import webhook

    olay = ("aday.olusturuldu", None, {"aday_id": 1, "_olay_id": "sabit-olay-1"}, False)
    async with db_manager.async_session_maker() as o3:
        for _ in range(2):
            await o3.run_sync(lambda s: webhook.olaylari_yayinla_sync(s.connection(), [olay]))
            await o3.commit()
    assert len([x for x in await _calismalar(db_oturumu, k["id"]) if x.olay_id == "sabit-olay-1"]) == 1


async def test_bekle_eylemi_zamanli_uctan_devam_eder(istemci, yonetici_basligi, db_oturumu):
    from models.notifications import Notifications
    from models.otomasyon import OtomasyonCalismalari

    k = await _kural(istemci, yonetici_basligi, tetik="aday.olusturuldu", eylemler=[
        {"tur": "bildirim", "alici": "yoneticiler", "baslik": "Önce {{aday.ad}}"},
        {"tur": "bekle", "miktar": 2, "birim": "saat"},
        {"tur": "bildirim", "alici": "yoneticiler", "baslik": "Sonra {{aday.ad}}"},
    ])
    await istemci.post("/api/v1/crm/adaylar", json={"ad": "Bekleyen", "email": "bekle@ornek.com"}, headers=yonetici_basligi)
    await _isle()
    c = (await _calismalar(db_oturumu, k["id"]))[0]
    assert c.durum == "bekliyor" and c.sonraki_eylem == 2
    kalan = (c.sonraki_zaman.replace(tzinfo=timezone.utc) if c.sonraki_zaman.tzinfo is None else c.sonraki_zaman) - datetime.now(timezone.utc)
    assert timedelta(hours=1, minutes=55) < kalan <= timedelta(hours=2)
    await _isle()  # zamanı gelmedi: bir şey olmaz
    assert (await _calismalar(db_oturumu, k["id"]))[0].durum == "bekliyor"
    await db_oturumu.execute(update(OtomasyonCalismalari).where(OtomasyonCalismalari.id == c.id)
                             .values(sonraki_zaman=datetime.now(timezone.utc) - timedelta(minutes=1)))
    await db_oturumu.commit()
    y = await istemci.post("/api/v1/zamanli/yonetim/calistir", headers=yonetici_basligi)
    assert y.status_code == 200
    gorev = next(g for g in y.json()["gorevler"] if g["gorev"] == "otomasyon")
    assert gorev["hata"] is None
    c = (await _calismalar(db_oturumu, k["id"]))[0]
    assert c.durum == "tamam" and [s["durum"] for s in json.loads(c.eylem_sonuclari)] == ["basarili"] * 3
    basliklar = {n.title for n in (await db_oturumu.execute(select(Notifications).where(Notifications.event_type == "otomasyon_bildirimi"))).scalars().all()}
    assert {"Önce Bekleyen", "Sonra Bekleyen"} <= basliklar


async def test_musteri_izolasyonu(istemci, yonetici_basligi, db_oturumu):
    from models.proje_gorevleri import ProjectTasks
    from models.support_tickets import Support_tickets

    a = await _musteri(istemci, yonetici_basligi)
    b = await _musteri(istemci, yonetici_basligi)
    ka = await _kural(istemci, _b(a), M, tetik="destek.olusturuldu",
                      eylemler=[{"tur": "bildirim", "alici": "hesap", "baslik": "Yeni talep"}])
    kb = await _kural(istemci, _b(b), M, tetik="gorev.olusturuldu",
                      eylemler=[{"tur": "bildirim", "alici": "hesap", "baslik": "Görev"}])
    await _ekle(db_oturumu, Support_tickets(client_email=b, subject="B'nin", message="m", status="open"))
    assert await _calismalar(db_oturumu, ka["id"]) == []
    await _ekle(db_oturumu, Support_tickets(client_email=a, subject="A'nın", message="m", status="open"))
    assert len(await _calismalar(db_oturumu, ka["id"])) == 1
    # Müşteriye görünmeyen görev müşteri kuralını tetiklemez.
    pb = await _proje(db_oturumu, b)
    await _ekle(db_oturumu, ProjectTasks(proje_id=pb.id, baslik="İç", durum="yapilacak", oncelik="normal", sira=0,
                                         musteriye_gorunur=False, harcanan_saat=0.0))
    assert await _calismalar(db_oturumu, kb["id"]) == []
    # Başka hesabın kuralı/günlüğü görünmez; başka hesabın projesi görev eyleminde seçilemez.
    assert (await istemci.get(f"{M}/kurallar/{ka['id']}", headers=_b(b))).status_code == 404
    assert (await istemci.get(f"{M}/gunluk", headers=_b(b))).json()["items"] == []
    pa = await _proje(db_oturumu, a)
    y = await istemci.post(f"{M}/kurallar", json={"ad": "x", "tetik": "destek.olusturuldu",
                                                  "eylemler": [{"tur": "gorev", "proje": pa.id, "baslik": "x"}]}, headers=_b(b))
    assert y.status_code == 400 and _kod(y) == "proje_yok"
    # Modül kapanınca bekleyen çalıştırma atlanır.
    await _modul_ac(istemci, yonetici_basligi, a, acik=False)
    await _isle()
    assert [(c.durum, c.neden) for c in await _calismalar(db_oturumu, ka["id"])] == [("atlandi", "modul_kapali")]


async def test_fatura_gecikti_olayi_esik_basina_bir_kez(istemci, yonetici_basligi, db_oturumu, posta):
    from models.invoices import Invoices
    from services import otomasyon

    e = await _musteri(istemci, yonetici_basligi)
    k = (await istemci.post(f"{M}/kurallar/sablondan", json={"sablon": "fatura_gecikti_hatirlatma"}, headers=_b(e))).json()
    vade = (date.today() - timedelta(days=4)).isoformat()
    f = await _ekle(db_oturumu, Invoices(invoice_no=f"F-{uuid.uuid4().hex[:5]}", client_email=e, amount=1500.0,
                                         currency="TRY", status="unpaid", due_date=vade))
    sonuc = await otomasyon.fatura_gecikmelerini_uret(db_oturumu)
    assert sonuc["uretilen"] >= 1
    await otomasyon.fatura_gecikmelerini_uret(db_oturumu)  # ikinci kez üretmez
    calismalar = await _calismalar(db_oturumu, k["id"])
    assert len(calismalar) == 1 and calismalar[0].olay_id == f"fgecikti-{f.id}-3"
    await _isle()
    giden = [g for g in posta.giden if g["konu"].startswith("Ödeme hatırlatması")]
    assert [g["alici"] for g in giden] == [e] and f.invoice_no in giden[0]["konu"]
    assert "3 gün" in giden[0]["govde"]


# ---------------------------------------------------------------------------
# Özel alanlar
# ---------------------------------------------------------------------------
async def test_ozel_alan_crud_ve_dogrulama(istemci, yonetici_basligi, db_oturumu):
    y = await istemci.post(OZ, json={"varlik": "crm_aday", "ad": "Bütçe Aralığı", "tur": "secim", "aktif": True, "sira": 5,
                                     "secenekler": ["Küçük", "Orta", "Büyük"], "zorunlu": True}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    alan = y.json()
    assert alan["anahtar"] == "butce_araligi" and alan["secenekler"] == ["Küçük", "Orta", "Büyük"]
    y = await istemci.post(OZ, json={"varlik": "crm_aday", "ad": "Bütçe aralığı", "tur": "metin"}, headers=yonetici_basligi)
    assert y.status_code == 409 and _kod(y) == "anahtar_kullanimda"
    for govde, kod in (({"varlik": "yok", "ad": "x"}, "varlik_gecersiz"), ({"varlik": "proje", "ad": "x", "tur": "renk"}, "tur_gecersiz"),
                       ({"varlik": "proje", "ad": "x", "tur": "secim"}, "secenek_gerekli"),
                       ({"varlik": "crm_aday", "ad": "x", "musteriye_gorunur": True}, "gorunurluk_desteklenmiyor"),
                       ({"varlik": "proje", "ad": "x", "anahtar": "1kotu"}, "anahtar_gecersiz")):
        y = await istemci.post(OZ, json=govde, headers=yonetici_basligi)
        assert y.status_code == 400 and _kod(y) == kod, (govde, y.text)
    turler = {}
    for tur in ("metin", "sayi", "tarih", "coklu_secim", "evet_hayir", "url"):
        govde = {"varlik": "crm_aday", "ad": f"Alan {tur}", "tur": tur}
        if tur == "coklu_secim":
            govde["secenekler"] = "a, b, c"
        y = await istemci.post(OZ, json=govde, headers=yonetici_basligi)
        assert y.status_code == 200, y.text
        turler[tur] = y.json()["anahtar"]
    y = await istemci.post("/api/v1/crm/adaylar", json={"ad": "Özel", "email": "ozel@ornek.com"}, headers=yonetici_basligi)
    aday_id = y.json()["id"]
    yol = f"{OZ}/deger/crm_aday/{aday_id}"
    # Zorunlu alan boş → 400; geçersiz değerler → 400.
    y = await istemci.put(yol, json={"degerler": {turler["metin"]: "x"}}, headers=yonetici_basligi)
    assert y.status_code == 400 and _kod(y) == "alan_gerekli"
    for anahtar, deger in ((turler["sayi"], "on iki"), (turler["tarih"], "2026-13-40"), ("butce_araligi", "Dev"),
                           (turler["coklu_secim"], ["a", "z"]), (turler["evet_hayir"], "evet"), (turler["url"], "javascript:alert(1)"),
                           ("olmayan", "x")):
        y = await istemci.put(yol, json={"degerler": {"butce_araligi": "Orta", anahtar: deger}}, headers=yonetici_basligi)
        assert y.status_code == 400, (anahtar, deger, y.text)
    y = await istemci.put(yol, json={"degerler": {
        "butce_araligi": "Orta", turler["metin"]: " Not ", turler["sayi"]: "12,5", turler["tarih"]: "2026-10-01",
        turler["coklu_secim"]: ["c", "a", "c"], turler["evet_hayir"]: True, turler["url"]: "https://ornek.com/a"}}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    d = y.json()["degerler"]
    assert d["butce_araligi"] == "Orta" and d[turler["metin"]] == "Not" and d[turler["sayi"]] == 12.5
    assert d[turler["coklu_secim"]] == ["c", "a"] and d[turler["evet_hayir"]] is True
    # Boş değer satırı siler; olmayan kayıt 404.
    y = await istemci.put(yol, json={"degerler": {turler["metin"]: ""}}, headers=yonetici_basligi)
    assert turler["metin"] not in y.json()["degerler"]
    assert (await istemci.get(f"{OZ}/deger/crm_aday/99999999", headers=yonetici_basligi)).status_code == 404
    # Güncelleme: tür uyumsuz değişemez; silme çöp kutusuna, değer kalır ama görünmez.
    y = await istemci.put(f"{OZ}/{alan['id']}", json={"tur": "sayi"}, headers=yonetici_basligi)
    assert y.status_code == 400 and _kod(y) == "tur_degistirilemez"
    assert (await istemci.delete(f"{OZ}/{alan['id']}", headers=yonetici_basligi)).status_code == 200
    assert "butce_araligi" not in (await istemci.get(yol, headers=yonetici_basligi)).json()["degerler"]
    # Müşteri yönetici uçlarına giremez.
    assert (await istemci.get(OZ, headers=_b(_e()))).status_code == 403


async def test_ozel_alan_musteriye_gorunurluk(istemci, yonetici_basligi, db_oturumu):
    from models.support_tickets import Support_tickets

    gorunur = (await istemci.post(OZ, json={"varlik": "proje", "ad": "Teslim haftası", "tur": "metin", "musteriye_gorunur": True},
                                  headers=yonetici_basligi)).json()
    gizli = (await istemci.post(OZ, json={"varlik": "proje", "ad": "İç maliyet", "tur": "sayi"}, headers=yonetici_basligi)).json()
    await istemci.post(OZ, json={"varlik": "hesap", "ad": "Segment", "tur": "metin"}, headers=yonetici_basligi)
    e, baska = _e("gor"), _e("baska")
    p = await _proje(db_oturumu, e)
    t = await _ekle(db_oturumu, Support_tickets(client_email=e, subject="K", message="m", status="open"))
    y = await istemci.put(f"{OZ}/deger/proje/{p.id}", json={"degerler": {gorunur["anahtar"]: "42. hafta", gizli["anahtar"]: 900}},
                          headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    y = await istemci.get(f"{OZM}/proje/{p.id}", headers=_b(e))
    assert y.status_code == 200
    assert y.json()["degerler"] == {gorunur["anahtar"]: "42. hafta"} and [a["anahtar"] for a in y.json()["alanlar"]] == [gorunur["anahtar"]]
    assert (await istemci.get(f"{OZM}/proje/{p.id}", headers=_b(baska))).status_code == 404
    assert (await istemci.get(f"{OZM}/destek/{t.id}", headers=_b(e))).status_code == 200
    assert (await istemci.get(f"{OZM}/hesap/1", headers=_b(e))).status_code == 404
    assert (await istemci.get(f"{OZM}/proje/{p.id}")).status_code == 401
    # Müşteri kuralının şemasında yalnız görünür özel alan; hesap alanı yok.
    await _modul_ac(istemci, yonetici_basligi, e)
    meta = (await istemci.get(f"{M}/meta", headers=_b(e))).json()
    yollar = {a["yol"] for o in meta["olaylar"] for a in o["sema"]}
    assert f"proje.ozel.{gorunur['anahtar']}" in yollar and f"proje.ozel.{gizli['anahtar']}" not in yollar
    assert not any(y_.startswith("hesap.ozel.") for y_ in yollar)
    ymeta = (await istemci.get(f"{Y}/meta", headers=yonetici_basligi)).json()
    yyollar = {a["yol"] for o in ymeta["olaylar"] for a in o["sema"]}
    assert f"proje.ozel.{gizli['anahtar']}" in yyollar and "hesap.ozel.segment" in yyollar


async def test_ozel_alan_kosulda_ve_yer_tutucuda(istemci, yonetici_basligi, db_oturumu, posta):
    await istemci.post(OZ, json={"varlik": "crm_aday", "ad": "Sektör", "tur": "secim", "secenekler": ["Sağlık", "Turizm"]},
                       headers=yonetici_basligi)
    await _kural(istemci, yonetici_basligi, tetik="aday.olusturuldu",
                 kosullar={"baglac": "ve", "kosullar": [{"alan": "aday.ozel.sektor", "islec": "esittir", "deger": "turizm"}]},
                 eylemler=[{**EPOSTA_EYLEMI, "konu": "{{aday.ozel.sektor}} paketi"}])
    for ad, sektor in (("Otel", "Turizm"), ("Klinik", "Sağlık")):
        y = await istemci.post("/api/v1/crm/adaylar", json={"ad": ad, "email": f"{ad.lower()}@ornek.com"}, headers=yonetici_basligi)
        r = await istemci.put(f"{OZ}/deger/crm_aday/{y.json()['id']}", json={"degerler": {"sektor": sektor}}, headers=yonetici_basligi)
        assert r.status_code == 200
    await _isle()
    assert [(g["alici"], g["konu"]) for g in posta.giden] == [("otel@ornek.com", "Turizm paketi")]


async def test_form_ozel_alan_eslemesi(istemci, yonetici_basligi, db_oturumu, posta, monkeypatch):
    from routers import crm as crm_router
    from services import crm_form

    crm_router.hiz_sinirlarini_temizle()
    sektor = (await istemci.post(OZ, json={"varlik": "crm_aday", "ad": "Sektör", "tur": "secim", "secenekler": ["Sağlık", "Turizm"]},
                                 headers=yonetici_basligi)).json()
    site = (await istemci.post(OZ, json={"varlik": "crm_aday", "ad": "Web sitesi", "tur": "url"}, headers=yonetici_basligi)).json()
    tarih = (await istemci.post(OZ, json={"varlik": "crm_aday", "ad": "Doğum", "tur": "tarih"}, headers=yonetici_basligi)).json()
    y = await istemci.post("/api/v1/crm/formlar", json={"ad": "Özel form", "ozel_alanlar": [{"alan_id": tarih["id"]}]},
                           headers=yonetici_basligi)
    assert y.status_code == 400 and _kod(y) == "ozel_alan_gecersiz"  # tarih formda sorulamaz
    y = await istemci.post("/api/v1/crm/formlar", json={"ad": "Özel form", "ozel_alanlar": [
        {"alan_id": sektor["id"], "zorunlu": True}, {"alan_id": site["id"]}]}, headers=yonetici_basligi)
    assert y.status_code == 201, y.text
    form = y.json()
    assert form["ozel_alanlar"] == [{"alan_id": sektor["id"], "zorunlu": True}, {"alan_id": site["id"], "zorunlu": False}]
    # Yalnız temel alanlar güncellenince eşleme korunur.
    y = await istemci.patch(f"/api/v1/crm/formlar/{form['id']}", json={"alanlar": {"telefon": {"acik": False}}}, headers=yonetici_basligi)
    assert y.json()["ozel_alanlar"] == form["ozel_alanlar"]
    tanim = (await istemci.get(f"/api/v1/crm/form/{form['genel_anahtar']}?dil=en")).json()
    ozel = {a["ad"]: a for a in tanim["alanlar"] if a["ad"].startswith("oz_")}
    assert ozel["oz_sektor"]["secenekler"] == ["Sağlık", "Turizm"] and ozel["oz_sektor"]["zorunlu"] is True
    assert ozel["oz_web_sitesi"]["tur"] == "url"

    k = await _kural(istemci, yonetici_basligi, tetik="aday.olusturuldu",
                     eylemler=[{**EPOSTA_EYLEMI, "konu": "{{aday.ozel.sektor}}: {{aday.ad}}"}])
    monkeypatch.setattr(crm_form, "EN_AZ_SURE_SN", 0)

    async def gonder(**alanlar):
        jeton = crm_form.jeton_uret(form["id"])
        govde = {"jeton": jeton, "ad": "Form Kişi", "email": alanlar.pop("email", "form-kisi@ornek.com"), **alanlar}
        return await istemci.post(f"/api/v1/crm/form/{form['genel_anahtar']}", content=json.dumps(govde),
                                  headers={"Content-Type": "text/plain"})

    y = await gonder()
    assert y.status_code == 400 and _kod(y) == "alan_gerekli"
    y = await gonder(oz_sektor="Uzay")
    assert y.status_code == 400 and _kod(y) == "alan_gecersiz"
    y = await gonder(oz_sektor="Turizm", oz_web_sitesi="https://otel.ornek.com")
    assert y.status_code == 200, y.text
    from models.crm import CrmAdaylari
    from services import ozel_alanlar

    db_oturumu.expire_all()
    a = (await db_oturumu.execute(select(CrmAdaylari).where(CrmAdaylari.email == "form-kisi@ornek.com"))).scalars().first()
    assert await ozel_alanlar.degerler(db_oturumu, "crm_aday", a.id) == {"sektor": "Turizm", "web_sitesi": "https://otel.ornek.com"}
    # Formdan gelen aday (Core yolu) kuralı tetikler ve özel alanı bağlamda görür.
    await _isle()
    assert [g["konu"] for g in posta.giden if g["alici"] == "form-kisi@ornek.com"] == ["Turizm: Form Kişi"]
    assert len(await _calismalar(db_oturumu, k["id"])) == 1


async def test_herkese_acik_api_ozel_alanlar(istemci, yonetici_basligi, db_oturumu):
    from services import public_api
    from services.api_erisimi import ApiKimlik

    gorunur = (await istemci.post(OZ, json={"varlik": "proje", "ad": "Hafta", "tur": "metin", "musteriye_gorunur": True},
                                  headers=yonetici_basligi)).json()
    gizli = (await istemci.post(OZ, json={"varlik": "proje", "ad": "Maliyet", "tur": "sayi"}, headers=yonetici_basligi)).json()
    e = _e("api")
    p = await _proje(db_oturumu, e)
    await istemci.put(f"{OZ}/deger/proje/{p.id}", json={"degerler": {gorunur["anahtar"]: "42", gizli["anahtar"]: 5}},
                      headers=yonetici_basligi)
    musteri = ApiKimlik(anahtar_id=1, onek="x", sahip_tur="musteri", hesap=e, kapsamlar=frozenset({"projeler:oku"}),
                        olusturan=e, dakika_siniri=60)
    ajans = ApiKimlik(anahtar_id=2, onek="y", sahip_tur="ajans", hesap=None, kapsamlar=frozenset({"projeler:oku"}),
                      olusturan=None, dakika_siniri=60)
    assert (await public_api.proje(db_oturumu, musteri, p.id))["ozel_alanlar"] == {gorunur["anahtar"]: "42"}
    assert (await public_api.proje(db_oturumu, ajans, p.id))["ozel_alanlar"] == {gorunur["anahtar"]: "42", gizli["anahtar"]: 5}
    sayfa = await public_api.projeler(db_oturumu, musteri)
    assert sayfa["veri"][0]["ozel_alanlar"] == {gorunur["anahtar"]: "42"}
    from schemas.public_api import Proje

    assert Proje(**sayfa["veri"][0]).ozel_alanlar == {gorunur["anahtar"]: "42"}


async def test_ekip_izni_otomasyon(istemci, yonetici_basligi, db_oturumu):
    from models.hesap_uyeleri import HesapUyeleri
    from services import hesap_ekibi

    assert "otomasyon" in hesap_ekibi.IZINLER and "otomasyon" not in hesap_ekibi.ROL_VARSAYILAN["uye"]
    assert hesap_ekibi.OLAY_IZNI["otomasyon_bildirimi"] == "otomasyon"
    sahip = await _musteri(istemci, yonetici_basligi)
    uye, izinli = _e("uye"), _e("izinli")
    for kisi, izinler in ((uye, ["projeler"]), (izinli, ["otomasyon"])):
        db_oturumu.add(HesapUyeleri(hesap_email=sahip, uye_email=kisi, rol="uye", izinler=json.dumps(izinler), durum="aktif",
                                    olusturma=hesap_ekibi.simdi()))
    await db_oturumu.commit()
    hesap_ekibi.onbellegi_temizle()
    y = await istemci.get(f"{M}/kurallar", headers=_b(uye, sahip))
    assert y.status_code == 403 and _kod(y) == "hesap_izni_yok"
    k = await _kural(istemci, _b(izinli, sahip), M, tetik="destek.olusturuldu",
                     eylemler=[{"tur": "bildirim", "alici": "hesap", "baslik": "x"}])
    assert k["hesap_email"] == sahip and k["olusturan"] == izinli
