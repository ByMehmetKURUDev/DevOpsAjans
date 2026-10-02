"""Faz 5M — E-posta pazarlama: bülten, kampanya ve damla dizileri.

Kapsam: izin kuralları (bireysel izinsiz → gönderilmez; kurumsal → ret bağlantısıyla gönderilir),
bastırma listesi, çift onaylı abonelik (jeton süresi, tekrar kullanım, bal küpü, süre jetonu),
ret bağlantısı (tek tık POST + GET yönlendirme + tercih sayfası, imza), `List-Unsubscribe` +
`List-Unsubscribe-Post` başlıkları, alt bilgide gönderen kimliği, CSV içe aktarma (izin kaynağı
yok → izinsiz), segment değerlendirme, blok → HTML/düz metin (kaçış, enjeksiyon), zamanlanmış ve
parçalı gönderim + hız sınırı (Resend taklit), Svix imzalı teslimat webhook'u → geri dönüş/şikâyet
bastırma, A/B seçimi, damla dizisi zamanlaması + çıkış, müşteri izolasyonu + modül kapalıyken 403,
kota, gönderen kimliği eksik, açılma/tıklama takibi, otomatik askıya alma.
"""

import base64
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from conftest import jeton_uret

Y = "/api/v1/eposta-pazarlama/yonetim"
M = "/api/v1/eposta-pazarlamam"
A = "/api/v1/bulten"
MODUL = "/api/v1/moduller"
UTC = timezone.utc
WEBHOOK_GIZLI = "whsec_" + base64.b64encode(b"test-pazarlama-imza-anahtari-32b!").decode()


def _e(on: str = "kisi") -> str:
    return f"{on}-{uuid.uuid4().hex[:8]}@ornek.com"


def _b(eposta: str, hesap: str | None = None) -> dict:
    h = {"Authorization": f"Bearer {jeton_uret(eposta)}"}
    if hesap:
        h["X-MK-Hesap"] = hesap
    return h


def _kod(y) -> str:
    try:
        d = y.json().get("detail")
    except Exception:  # noqa: BLE001
        return ""
    return d.get("kod", "") if isinstance(d, dict) else ""


def _ip() -> dict:
    return {"X-MK-Istemci-IP": f"198.51.100.{uuid.uuid4().int % 250 + 1}"}


@pytest.fixture(autouse=True)
def _ortam(monkeypatch):
    from routers import eposta_pazarlama as r
    from services import eposta_gonderim as eg
    from services import hesap_ekibi

    r.hiz_sinirlarini_temizle()
    hesap_ekibi.onbellegi_temizle()
    eg.sahte_kutuyu_temizle()
    # Hız sınırlayıcı testlerde beklemesin (kendi testinde sahte saatle ayrıca sınanıyor).
    monkeypatch.setattr(eg, "_HIZ", eg.AsyncHizSinirlayici(1000.0))
    yield
    r.hiz_sinirlarini_temizle()


@pytest.fixture
def resend(monkeypatch):
    """Resend taklidi: `RESEND_API_KEY` tanımlı; ağ çağrısı yakalanıyor."""
    from services import eposta_gonderim as eg

    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    kayit = {"toplu": [], "tekil": [], "yanit": None}

    async def _sahte(yol, govde, basliklar):
        if kayit["yanit"] is not None:
            return kayit["yanit"]
        if yol == "/emails/batch":
            kayit["toplu"].append({"iletiler": govde, "basliklar": basliklar})
            return 200, {"data": [{"id": f"re-{uuid.uuid4().hex[:12]}"} for _ in govde]}
        kayit["tekil"].append(govde)
        return 200, {"id": f"re-{uuid.uuid4().hex[:12]}"}

    monkeypatch.setattr(eg, "_resend_cagir", _sahte)

    def iletiler():
        return [i for t in kayit["toplu"] for i in t["iletiler"]]

    kayit["iletiler"] = iletiler
    return kayit


@pytest.fixture
async def yasal(db_oturumu):
    """Ajansın gönderen kimliği (Site Ayarları › Yasal bilgiler)."""
    from models.site_settings import Site_settings

    degerler = {"yasal_unvan": "Mehmet KURU Dev", "yasal_adres": "Örnek Mah. 1. Sok. No:1 Kadıköy/İstanbul",
                "yasal_eposta": "by@mehmetkuru.dev"}
    onceki: dict[str, str | None] = {}
    for anahtar, deger in degerler.items():
        satir = (await db_oturumu.execute(select(Site_settings).where(Site_settings.setting_key == anahtar))).scalars().first()
        if satir is None:
            onceki[anahtar] = None
            db_oturumu.add(Site_settings(setting_key=anahtar, setting_value=deger, group_name="yasal", label=anahtar))
        else:
            onceki[anahtar] = satir.setting_value
            satir.setting_value = deger
    await db_oturumu.commit()
    yield degerler
    # Paylaşılan test veritabanında başka dosyaların yasal ayar testlerini bozmamak için geri al.
    for anahtar, deger in onceki.items():
        satir = (await db_oturumu.execute(select(Site_settings).where(Site_settings.setting_key == anahtar))).scalars().first()
        if satir is None:
            continue
        if deger is None:
            await db_oturumu.delete(satir)
        else:
            satir.setting_value = deger
    await db_oturumu.commit()


async def _modul(istemci, yonetici_basligi, eposta, acik=True, **ayarlar):
    govde = {"acik": acik}
    if ayarlar:
        govde["ayarlar"] = ayarlar
    y = await istemci.put(f"{MODUL}/musteri/{eposta}/eposta_pazarlama", json=govde, headers=yonetici_basligi)
    assert y.status_code == 200, y.text


async def _liste(istemci, basliklar, yol=Y, ad=None):
    y = await istemci.post(f"{yol}/listeler", json={"ad": ad or f"Liste {uuid.uuid4().hex[:5]}"}, headers=basliklar)
    assert y.status_code == 200, y.text
    return y.json()


async def _kisi(istemci, basliklar, yol=Y, **govde):
    govde.setdefault("eposta", _e())
    y = await istemci.post(f"{yol}/kisiler", json=govde, headers=basliklar)
    assert y.status_code == 200, y.text
    return y.json()


IZIN = {"durum": "izinli", "kaynak": "fuar standı formu", "zaman": "2026-01-10T10:00:00Z", "kanit": "Islak imzalı form"}
BLOKLAR = [
    {"tur": "logo"},
    {"tur": "baslik", "metin": "Merhaba {{ad|okurumuz}}!"},
    {"tur": "metin", "metin": "Yeni **kampanya** başladı. Ayrıntılar [sitemizde](https://ornek.com/kampanya?a=1&b=2)."},
    {"tur": "dugme", "metin": "İncele", "url": "https://ornek.com/incele"},
]


async def _kampanya(istemci, basliklar, liste_id, yol=Y, **ek):
    govde = {"ad": "Ekim bülteni", "konu": "Ekim fırsatları {{ad}}", "onizleme_metni": "Kısa özet", "bloklar": BLOKLAR,
             "hedef": {"listeler": [liste_id]}, **ek}
    y = await istemci.post(f"{yol}/kampanyalar", json=govde, headers=basliklar)
    assert y.status_code == 200, y.text
    return y.json()


# ---------------------------------------------------------------------------
# İzin kuralları (saf)
# ---------------------------------------------------------------------------
class _K:
    def __init__(self, **kw):
        self.eposta = kw.get("eposta", "a@ornek.com")
        self.alici_turu = kw.get("alici_turu", "bireysel")
        self.izin_durumu = kw.get("izin_durumu", "izinsiz")
        self.ret_zamani = kw.get("ret_zamani")


def test_gonderim_karari_izin_kurallari():
    from services.eposta_pazarlama import gonderim_karari as k

    assert k(_K(), bastirilmis=False) == "izin_yok"  # bireysel izinsiz → asla
    assert k(_K(izin_durumu="bekliyor"), bastirilmis=False) == "izin_yok"  # çift onay bekleyen
    assert k(_K(izin_durumu="izinli"), bastirilmis=False) is None
    assert k(_K(alici_turu="kurumsal"), bastirilmis=False) is None  # tacir/esnaf: ret hakkıyla gönderilir
    assert k(_K(alici_turu="kurumsal", izin_durumu="reddetti"), bastirilmis=False) == "ret"
    assert k(_K(izin_durumu="izinli", ret_zamani=datetime.now(UTC)), bastirilmis=False) == "ret"
    assert k(_K(izin_durumu="izinli"), bastirilmis=True) == "bastirildi"
    assert k(_K(eposta="gecersiz"), bastirilmis=False) == "gecersiz_adres"
    assert k(_K(izin_durumu="izinli"), bastirilmis=False, son_24_saat=1, gunluk_sinir=1) == "siklik_siniri"
    assert k(_K(izin_durumu="izinli"), bastirilmis=False, son_24_saat=1, gunluk_sinir=2) is None


def test_ab_orneklem_ve_kazanan():
    from services.eposta_pazarlama import ab_kazanan, ab_orneklem

    assert ab_orneklem(100, 20) == (10, 10)
    assert ab_orneklem(11, 20) == (2, 1)
    assert sum(ab_orneklem(1000, 30)) == 300
    assert ab_kazanan({"gonderilen": 10, "acilan": 3}, {"gonderilen": 10, "acilan": 5}) == "b"
    assert ab_kazanan({"gonderilen": 10, "acilan": 5}, {"gonderilen": 10, "acilan": 5}) == "a"  # eşitlikte A
    assert ab_kazanan({"gonderilen": 10, "tiklayan": 1, "acilan": 9}, {"gonderilen": 10, "tiklayan": 2, "acilan": 1}, "tiklama") == "b"
    assert ab_kazanan({"gonderilen": 0}, {"gonderilen": 0}) == "a"


def test_imzali_jetonlar():
    from services import eposta_pazarlama as ep

    j = ep.ret_jetonu(42)
    assert ep.jeton_coz("ret", j) == 42
    assert ep.jeton_coz("izle", j) is None  # amaç ayrı
    assert ep.jeton_coz("ret", j[:-1] + ("A" if j[-1] != "A" else "B")) is None
    assert ep.jeton_coz("ret", "43-" + j.split("-", 1)[1]) is None
    assert ep.jeton_coz("ret", "") is None
    basliklar = ep.ret_basliklari(42)
    assert basliklar["List-Unsubscribe"] == f"<https://mehmetkuru.dev/api/v1/bulten/ret/{j}>"
    assert basliklar["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"


# ---------------------------------------------------------------------------
# Blok → HTML / düz metin
# ---------------------------------------------------------------------------
def test_bloklar_html_ve_metin_kacis():
    from services import eposta_icerik as ic

    bloklar = ic.bloklari_dogrula([
        {"tur": "baslik", "metin": "<script>alert(1)</script> Başlık"},
        {"tur": "metin", "metin": 'Merhaba {{ad|dostum}}, **önemli** "tırnak" <b>kalın değil</b>\n\nİkinci [paragraf](https://ornek.com/a?x=1&y=2).'},
        {"tur": "gorsel", "url": "https://ornek.com/r.png", "alt": 'resim" onerror="x', "baglanti": "https://ornek.com/g"},
        {"tur": "dugme", "metin": "Tıkla", "url": "https://ornek.com/d"},
        {"tur": "ayirici"},
        {"tur": "iki_sutun", "sol": [{"tur": "metin", "metin": "Sol"}], "sag": [{"tur": "dugme", "metin": "Sağ", "url": "mailto:a@b.com"}]},
    ])
    html, baglantilar = ic.html_uret(bloklar, konu="Konu", onizleme="Önizleme", gonderen_adi="Ajans",
                                     alt_bilgi={"kimlik": "Unvan · Adres", "ret": "Abonelikten çık", "tercih": "Tercihler"})
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "<b>kalın değil</b>" not in html and "&lt;b&gt;" in html
    assert 'onerror="x' not in html and "resim&quot; onerror=&quot;x" in html
    assert "<strong>önemli</strong>" in html
    assert baglantilar == ["https://ornek.com/a?x=1&y=2", "https://ornek.com/g", "https://ornek.com/d", "mailto:a@b.com"]
    # Bağlantı adresleri şablona yazılmıyor: işaretler var.
    assert "<!--MK:L0-->" in html and "<!--MK:RET-->" in html and "<!--MK:NEDEN-->" in html and "<!--MK:PIKSEL-->" in html
    assert "Unvan · Adres" in html and "Önizleme" in html
    metin = ic.metin_uret(bloklar, gonderen_adi="Ajans", alt_bilgi={"kimlik": "Unvan · Adres", "ret": "Abonelikten çık", "tercih": "Tercihler"})
    assert "paragraf (<!--MK:L0-->)" in metin and "Tıkla: <!--MK:L2-->" in metin and "Abonelikten çık: <!--MK:RET-->" in metin
    assert "**" not in metin
    # Doldurma: HTML'de öznitelik kaçışlı; kişiselleştirme değeri kaçışlı ve işaret üretemez.
    dolu = ic.isaretleri_doldur(html, html=True, baglanti=lambda i: f"https://izle.dev/t/{i}?a=1&b=2", ret="https://r.dev/x",
                                tercih="https://r.dev/t", neden="Neden <b>", piksel="")
    assert 'href="https://izle.dev/t/0?a=1&amp;b=2"' in dolu and "Neden &lt;b&gt;" in dolu and "<!--MK:" not in dolu
    kisisel = ic.kisisellestir(dolu, {"ad": "<img src=x onerror=1><!--MK:RET-->"}, html=True)
    assert "<img src=x" not in kisisel and "&lt;img src=x onerror=1&gt;&lt;!--MK:RET--&gt;" in kisisel
    assert "Merhaba dostum" in ic.kisisellestir(dolu, {"ad": ""}, html=True)
    assert ic.konu_kisisellestir("Merhaba {{ad}}", {"ad": "Ali\r\nBcc: x@y.com"}) == "Merhaba Ali Bcc: x@y.com"


@pytest.mark.parametrize("blok,kod", [
    ({"tur": "dugme", "metin": "x", "url": "javascript:alert(1)"}, "adres_gecersiz"),
    ({"tur": "dugme", "metin": "x", "url": "data:text/html,<b>"}, "adres_gecersiz"),
    ({"tur": "gorsel", "url": "http://ornek.com/a.png"}, "adres_gecersiz"),  # e-postada yalnız https
    ({"tur": "dugme", "metin": "x", "url": 'https://ornek.com/"onmouseover="x'}, "adres_gecersiz"),
    ({"tur": "dugme", "metin": "x", "url": "https://ornek.com/{{ad}}"}, "adres_gecersiz"),
    ({"tur": "betik"}, "blok_turu"),
    ({"tur": "metin", "metin": ""}, "metin_gerekli"),
    ({"tur": "iki_sutun", "sol": [{"tur": "iki_sutun"}]}, "blok_turu"),
])
def test_bloklar_gecersiz(blok, kod):
    from services import eposta_icerik as ic

    with pytest.raises(ic.IcerikHatasi) as h:
        ic.bloklari_dogrula([blok])
    assert h.value.kod == kod


def test_metindeki_gecersiz_baglanti_baglanti_olmaz():
    from services import eposta_icerik as ic

    bloklar = ic.bloklari_dogrula([{"tur": "metin", "metin": "[tıkla](javascript:alert(1))"}])
    html, baglantilar = ic.html_uret(bloklar, konu="k")
    assert baglantilar == [] and "[tıkla](javascript:alert(1))" in html and "<!--MK:L" not in html


# ---------------------------------------------------------------------------
# Segment ve CSV (saf)
# ---------------------------------------------------------------------------
class _S:
    def __init__(self, i, **kw):
        self.id = i
        self.kaynak = kw.get("kaynak", "csv")
        self.alici_turu = kw.get("alici_turu", "bireysel")
        self.izin_durumu = kw.get("izin_durumu", "izinli")
        self.etiketler = json.dumps(kw.get("etiketler", []))
        self.ozel_alanlar = json.dumps(kw.get("ozel", {}))
        self.son_etkilesim_at = kw.get("son")
        self.created_at = kw.get("olusma", datetime(2026, 1, 1, tzinfo=UTC))
        self.crm_aday_id = kw.get("crm")


def test_segment_degerlendirme():
    from services import eposta_pazarlama as ep

    an = datetime(2026, 10, 1, tzinfo=UTC)
    kisiler = [
        _S(1, kaynak="form", etiketler=["vip"], son=an - timedelta(days=3), ozel={"sehir": "İzmir"}),
        _S(2, kaynak="csv", etiketler=["vip"], son=an - timedelta(days=90)),
        _S(3, kaynak="crm", alici_turu="kurumsal", crm=7),
        _S(4, kaynak="form", izin_durumu="izinsiz"),
    ]
    kural = ep.segment_duzelt({"kurallar": [{"alan": "etiket", "op": "icerir", "deger": "VIP"},
                                             {"alan": "son_etkilesim", "op": "son_gun", "deger": 30}]}, ajans=True)
    assert [k.id for k in ep.segment_degerlendir(kural, kisiler, {"simdi": an})] == [1]
    kural = ep.segment_duzelt({"birlesim": "veya", "kurallar": [{"alan": "kaynak", "op": "esit", "deger": "crm"},
                                                                 {"alan": "ozel", "anahtar": "sehir", "op": "esit", "deger": "izmir"}]}, ajans=True)
    assert [k.id for k in ep.segment_degerlendir(kural, kisiler, {"simdi": an})] == [1, 3]
    kural = ep.segment_duzelt({"kurallar": [{"alan": "son_etkilesim", "op": "hic"}]}, ajans=True)
    assert [k.id for k in ep.segment_degerlendir(kural, kisiler, {"simdi": an})] == [3, 4]
    kural = ep.segment_duzelt({"kurallar": [{"alan": "crm_asama", "op": "esit", "deger": "teklif"}]}, ajans=True)
    assert [k.id for k in ep.segment_degerlendir(kural, kisiler, {"simdi": an, "crm": {7: {"asama": "teklif"}}})] == [3]
    kural = ep.segment_duzelt({"kurallar": [{"alan": "liste", "op": "uye", "deger": 5}]}, ajans=True)
    assert [k.id for k in ep.segment_degerlendir(kural, kisiler, {"uyelikler": {2: {5}}})] == [2]
    # CRM alanları yalnız ajansta; bilinmeyen alan/op reddedilir.
    for kotu, ajans in (({"alan": "crm_asama", "op": "esit", "deger": "x"}, False), ({"alan": "sql", "op": "esit", "deger": "x"}, True),
                        ({"alan": "etiket", "op": "esit", "deger": "x"}, True), ({"alan": "son_etkilesim", "op": "son_gun", "deger": "x"}, True)):
        with pytest.raises(ep.PazarlamaHatasi):
            ep.segment_duzelt({"kurallar": [kotu]}, ajans=ajans)


def test_csv_coz_izin_kaynagi_yoksa_izinsiz():
    from services import eposta_pazarlama as ep

    csv = (
        "E-posta;Ad;Alici_turu;Izin_kaynagi;Izin_tarihi;Etiketler\n"
        "ayse@ornek.com;Ayşe;bireysel;Web formu;2026-02-01;vip, yeni\n"
        "ali@ornek.com;Ali;bireysel;;;\n"
        "firma@ornek.com;Firma;kurumsal;;;\n"
        "eksik@ornek.com;Tarihsiz;bireysel;Fuar;;\n"
        "gelecek@ornek.com;Gelecek;bireysel;Fuar;2099-01-01;\n"
        "bozuk-adres;X;;;;\n"
        "AYSE@ornek.com;Tekrar;;;;\n"
    ).encode("utf-8")
    s = ep.csv_coz(csv)
    satir = {x["eposta"]: x for x in s["satirlar"]}
    assert satir["ayse@ornek.com"]["izinli"] and satir["ayse@ornek.com"]["etiketler"] == ["vip", "yeni"]
    for e in ("ali@ornek.com", "firma@ornek.com", "eksik@ornek.com", "gelecek@ornek.com"):
        assert not satir[e]["izinli"], e
    assert satir["firma@ornek.com"]["alici_turu"] == "kurumsal"
    assert s["ozet"]["izinsiz_bireysel"] == 3 and s["ozet"]["hatali"] == 2
    assert {h["kod"] for h in s["hatalar"]} == {"eposta_gecersiz", "tekrar"}
    with pytest.raises(ep.PazarlamaHatasi) as h:
        ep.csv_coz(b"ad;telefon\nAli;123\n")
    assert h.value.kod == "eposta_sutunu_yok"


# ---------------------------------------------------------------------------
# Yetki, modül ve izolasyon
# ---------------------------------------------------------------------------
async def test_yetki_ve_modul_kapali(istemci, yonetici_basligi):
    assert (await istemci.get(f"{Y}/meta")).status_code == 401
    assert (await istemci.get(f"{Y}/meta", headers=_b(_e("m")))).status_code == 403
    musteri = _e("musteri")
    y = await istemci.get(f"{M}/listeler", headers=_b(musteri))
    assert y.status_code == 403 and _kod(y) == "modul_kapali"
    await _modul(istemci, yonetici_basligi, musteri)
    y = await istemci.get(f"{M}/listeler", headers=_b(musteri))
    assert y.status_code == 200 and y.json()["items"] == []
    y = await istemci.get(f"{M}/meta", headers=_b(musteri))
    assert y.status_code == 200 and y.json()["sinirlar"]["aylik"] == 10000 and "webhook" not in y.json()
    assert "crm_asama" not in y.json()["segment_alanlari"]
    # Yalnız yönetici uçları müşteri önekinde yok.
    assert (await istemci.post(f"{M}/kisiler/crm-aktar", json={}, headers=_b(musteri))).status_code in (404, 405)


async def test_musteri_izolasyonu(istemci, yonetici_basligi):
    a, b = _e("a"), _e("b")
    for x in (a, b):
        await _modul(istemci, yonetici_basligi, x)
    la = await _liste(istemci, _b(a), M)
    ka = await _kisi(istemci, _b(a), M, ad="A kişisi")
    kampanya = await _kampanya(istemci, _b(a), la["id"], M)
    # B, A'nın kayıtlarını göremez/değiştiremez.
    assert (await istemci.get(f"{M}/kisiler/{ka['id']}", headers=_b(b))).status_code == 404
    assert (await istemci.put(f"{M}/listeler/{la['id']}", json={"ad": "x"}, headers=_b(b))).status_code == 404
    assert (await istemci.get(f"{M}/kampanyalar/{kampanya['id']}", headers=_b(b))).status_code == 404
    assert (await istemci.get(f"{M}/kisiler", headers=_b(b))).json()["toplam"] == 0
    # Liste üyeliği başka hesabın kişisini almaz.
    lb = await _liste(istemci, _b(b), M)
    y = await istemci.post(f"{M}/listeler/{lb['id']}/uyeler", json={"kisi_idleri": [ka["id"]]}, headers=_b(b))
    assert y.json()["eklenen"] == 0
    # B'nin kampanyası A'nın listesini hedefleyemez (kitle boş).
    kb = await _kampanya(istemci, _b(b), la["id"], M)
    y = await istemci.post(f"{M}/kampanyalar/{kb['id']}/kitle", json={}, headers=_b(b))
    assert y.json()["toplam"] == 0
    # Yönetici (ajans hesabı) müşterinin kişisini kendi önekinde görmez.
    assert (await istemci.get(f"{Y}/kisiler/{ka['id']}", headers=yonetici_basligi)).status_code == 404


# ---------------------------------------------------------------------------
# Kampanya: izin kuralları uçtan uca + başlıklar + alt bilgi
# ---------------------------------------------------------------------------
async def test_kampanya_izin_kurallari_basliklar_ve_alt_bilgi(istemci, yonetici_basligi, resend, yasal, db_oturumu):
    from models.eposta_pazarlama import EpGonderimler

    l = await _liste(istemci, yonetici_basligi)
    izinli = await _kisi(istemci, yonetici_basligi, ad="İzinli <Ayşe>", izin=IZIN, listeler=[l["id"]])
    izinsiz = await _kisi(istemci, yonetici_basligi, ad="İzinsiz", listeler=[l["id"]])
    kurumsal = await _kisi(istemci, yonetici_basligi, ad="Firma", alici_turu="kurumsal", listeler=[l["id"]])
    bastirilan = await _kisi(istemci, yonetici_basligi, alici_turu="kurumsal", listeler=[l["id"]])
    y = await istemci.post(f"{Y}/bastirma", json={"eposta": bastirilan["eposta"]}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["eklendi"]
    k = await _kampanya(istemci, yonetici_basligi, l["id"])

    y = await istemci.post(f"{Y}/kampanyalar/{k['id']}/kitle", json={}, headers=yonetici_basligi)
    assert y.json()["toplam"] == 4 and y.json()["gonderilebilir"] == 2
    assert y.json()["atlanacak"] == {"izin_yok": 1, "bastirildi": 1}

    y = await istemci.post(f"{Y}/kampanyalar/{k['id']}/gonder", json={}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    assert y.json()["kampanya"]["durum"] == "tamamlandi"
    iletiler = {i["to"][0]: i for i in resend["iletiler"]()}
    assert set(iletiler) == {izinli["eposta"], kurumsal["eposta"]}  # bireysel izinsiz ve bastırılan GİTMEZ
    satirlar = {g.eposta: g for g in (await db_oturumu.execute(select(EpGonderimler).where(EpGonderimler.kampanya_id == k["id"]))).scalars().all()}
    assert satirlar[izinsiz["eposta"]].durum == "atlandi" and satirlar[izinsiz["eposta"]].neden == "izin_yok"
    assert satirlar[bastirilan["eposta"]].neden == "bastirildi"

    for kisi, neden in ((izinli, "kabul ettiğiniz için"), (kurumsal, "ticari iletişim kapsamında")):
        i = iletiler[kisi["eposta"]]
        from services import eposta_pazarlama as ep

        jeton = ep.ret_jetonu(kisi["id"])
        assert i["headers"]["List-Unsubscribe"] == f"<https://mehmetkuru.dev/api/v1/bulten/ret/{jeton}>"
        assert i["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
        assert f"https://mehmetkuru.dev/bulten/tercih/{jeton}?islem=ret" in i["html"]  # tek tıkla ret bağlantısı
        assert f"https://mehmetkuru.dev/bulten/tercih/{jeton}?islem=ret" in i["text"]
        assert "Mehmet KURU Dev · Örnek Mah. 1. Sok. No:1 Kadıköy/İstanbul" in i["html"]  # gönderen kimliği
        assert "Mehmet KURU Dev · Örnek Mah. 1. Sok. No:1 Kadıköy/İstanbul" in i["text"]
        assert neden in i["html"] and neden in i["text"]
        assert i["reply_to"] == "by@mehmetkuru.dev" and i["from"].endswith("<bulten@mehmetkuru.dev>")
        # Takip varsayılan KAPALI: piksel yok, bağlantılar doğrudan.
        assert "/api/v1/bulten/a/" not in i["html"] and 'href="https://ornek.com/incele"' in i["html"]
    assert iletiler[izinli["eposta"]]["subject"] == "Ekim fırsatları İzinli <Ayşe>"
    assert "İzinli &lt;Ayşe&gt;" in iletiler[izinli["eposta"]]["html"]
    # Toplu çağrı: Idempotency-Key ile.
    assert resend["toplu"][0]["basliklar"]["Idempotency-Key"].startswith("ep-")

    rapor = (await istemci.get(f"{Y}/kampanyalar/{k['id']}/rapor", headers=yonetici_basligi)).json()
    assert rapor["sayilar"]["gonderilen"] == 2 and rapor["sayilar"]["atlanan"] == 2
    assert rapor["atlama_nedenleri"] == {"izin_yok": 1, "bastirildi": 1}
    assert rapor["oranlar"]["acilma"] is None  # takip kapalı
    # Gönderilmiş kampanya silinemez ve düzenlenemez.
    assert (await istemci.delete(f"{Y}/kampanyalar/{k['id']}", headers=yonetici_basligi)).status_code == 409
    y = await istemci.put(f"{Y}/kampanyalar/{k['id']}", json={"konu": "x"}, headers=yonetici_basligi)
    assert y.status_code == 409, y.text
    # Aynı kampanya ikinci kez gönderilmez.
    y = await istemci.post(f"{Y}/kampanyalar/{k['id']}/gonder", json={}, headers=yonetici_basligi)
    assert y.status_code == 409 and _kod(y) == "zaten_gonderildi"


async def test_on_denetimler(istemci, yonetici_basligi, resend, monkeypatch):
    musteri = _e("kimliksiz")
    await _modul(istemci, yonetici_basligi, musteri, aylik_gonderim_siniri=1)
    l = await _liste(istemci, _b(musteri), M)
    for _ in range(2):
        await _kisi(istemci, _b(musteri), M, alici_turu="kurumsal", listeler=[l["id"]])
    k = await _kampanya(istemci, _b(musteri), l["id"], M)
    # Müşteride unvan/adres yoksa gönderim yok (her iletinin altında gönderen kimliği zorunlu).
    y = await istemci.post(f"{M}/kampanyalar/{k['id']}/gonder", json={}, headers=_b(musteri))
    assert y.status_code == 409 and _kod(y) == "gonderen_kimligi_eksik" and set(y.json()["detail"]["eksik"]) == {"unvan", "adres"}
    await istemci.put(f"{M}/ayarlar", json={"unvan": "Müşteri Ltd.", "adres": "Ankara"}, headers=_b(musteri))
    # Aylık sınır 1, gönderilebilir 2 → kota yetersiz.
    y = await istemci.post(f"{M}/kampanyalar/{k['id']}/gonder", json={}, headers=_b(musteri))
    assert y.status_code == 409 and _kod(y) == "kota_yetersiz" and y.json()["detail"]["kalan"] == 1
    # Resend kurulu değilse (ve sahte mod yoksa) gönderim yok.
    monkeypatch.delenv("RESEND_API_KEY")
    y = await istemci.post(f"{M}/kampanyalar/{k['id']}/gonder", json={}, headers=_b(musteri))
    assert y.status_code == 409 and _kod(y) == "resend_kurulu_degil"
    # Hedef yok / içerik boş.
    bos = (await istemci.post(f"{M}/kampanyalar", json={"ad": "Boş", "konu": "K"}, headers=_b(musteri))).json()
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    y = await istemci.post(f"{M}/kampanyalar/{bos['id']}/gonder", json={}, headers=_b(musteri))
    assert y.status_code == 400 and _kod(y) in ("icerik_bos", "hedef_gerekli")


async def test_musteri_gonderimi_via_ve_reply_to(istemci, yonetici_basligi, resend):
    musteri = _e("dukkan")
    await _modul(istemci, yonetici_basligi, musteri)
    await istemci.put(f"{M}/ayarlar", json={"unvan": "Dükkan Ltd. Şti.", "adres": "Bursa", "gonderen_adi": "Dükkan",
                                            "yanit_adresi": "info@dukkan.com"}, headers=_b(musteri))
    l = await _liste(istemci, _b(musteri), M)
    alici = await _kisi(istemci, _b(musteri), M, izin=IZIN, listeler=[l["id"]])
    k = await _kampanya(istemci, _b(musteri), l["id"], M)
    y = await istemci.post(f"{M}/kampanyalar/{k['id']}/gonder", json={}, headers=_b(musteri))
    assert y.status_code == 200, y.text
    i = resend["iletiler"]()[-1]
    assert i["to"] == [alici["eposta"]] and i["from"] == "Dükkan via mehmetkuru.dev <bulten@mehmetkuru.dev>"
    assert i["reply_to"] == "info@dukkan.com" and "Dükkan Ltd. Şti. · Bursa" in i["html"]
    meta = (await istemci.get(f"{M}/meta", headers=_b(musteri))).json()
    assert meta["sinirlar"]["kullanilan"] == 1


# ---------------------------------------------------------------------------
# Çift onaylı abonelik
# ---------------------------------------------------------------------------
async def _form(istemci, basliklar, liste_id, yol=Y, **ek):
    y = await istemci.post(f"{yol}/formlar", json={"ad": "Site bülteni", "liste_id": liste_id, "baslik": "Bültene katılın", **ek},
                           headers=basliklar)
    assert y.status_code == 200, y.text
    return y.json()


async def _abone_ol(istemci, anahtar, eposta, **ek):
    from services import eposta_pazarlama as ep

    tanim = (await istemci.get(f"{A}/form/{anahtar}?dil={ek.get('dil', 'tr')}")).json()
    form_id = int(tanim["jeton"].split(".")[0])
    govde = {"jeton": ep.form_jetonu(form_id, an=time.time() - 5), "eposta": eposta, "izin": True, "ad": "Zeynep", **ek}
    return await istemci.post(f"{A}/form/{anahtar}", content=json.dumps(govde), headers={"Content-Type": "text/plain", **_ip()})


async def test_cift_onayli_abonelik(istemci, yonetici_basligi, resend, yasal, db_oturumu, monkeypatch):
    from models.eposta_pazarlama import EpKisiler, EpListeUyelikleri
    from services import eposta_pazarlama as ep

    l = await _liste(istemci, yonetici_basligi, ad="Haftalık bülten")
    f = await _form(istemci, yonetici_basligi, l["id"], tur_sor=True)
    assert f["adres"] == f"https://mehmetkuru.dev/bulten/{f['genel_anahtar']}"
    assert 'data-mk-bulten="' in f["gomme_kodu"] and "/bulten-form.js" in f["gomme_kodu"]

    tanim = await istemci.get(f"{A}/form/{f['genel_anahtar']}?dil=ar")
    assert tanim.status_code == 200
    t = tanim.json()
    assert t["yon"] == "rtl" and t["izin"]["surum"] == "bulten-1/ar" and "Mehmet KURU Dev" in t["izin"]["metin"]
    assert t["aydinlatma"]["baglanti"] == "https://mehmetkuru.dev/ar/gizlilik" and t["kurumsal"]
    assert tanim.headers["cache-control"] == "no-store"

    # Süre jetonu: 2 sn dolmadan → cok_hizli; jetonsuz → jeton_gecersiz; izin kutusu şart.
    eposta = _e("abone")
    y = await istemci.post(f"{A}/form/{f['genel_anahtar']}", content=json.dumps({"jeton": t["jeton"], "eposta": eposta, "izin": True}),
                           headers={"Content-Type": "text/plain", **_ip()})
    assert y.status_code == 400 and _kod(y) == "cok_hizli"
    y = await istemci.post(f"{A}/form/{f['genel_anahtar']}", content=json.dumps({"eposta": eposta, "izin": True}), headers=_ip())
    assert y.status_code == 400 and _kod(y) == "jeton_gecersiz"
    y = await _abone_ol(istemci, f["genel_anahtar"], eposta, izin=False)
    assert y.status_code == 400 and _kod(y) == "izin_gerekli"
    # Bal küpü: başarılı görünür ama hiçbir şey kaydedilmez.
    bot = _e("bot")
    y = await _abone_ol(istemci, f["genel_anahtar"], bot, web_adresi="http://spam")
    assert y.status_code == 200 and "tesekkur" in y.json()
    assert (await db_oturumu.execute(select(EpKisiler).where(EpKisiler.eposta == bot))).scalars().first() is None

    y = await _abone_ol(istemci, f["genel_anahtar"], eposta, kurumsal=True)
    assert y.status_code == 200, y.text
    onay = resend["tekil"][-1]
    assert onay["to"] == [eposta] and "Aboneliğinizi onaylayın" in onay["subject"] and "Haftalık bülten" in onay["subject"]
    assert "List-Unsubscribe" not in (onay.get("headers") or {})  # işlem e-postası, pazarlama değil
    ham = onay["text"].split("/bulten/onay/")[1].split()[0]
    kisi = (await db_oturumu.execute(select(EpKisiler).where(EpKisiler.eposta == eposta))).scalars().first()
    assert kisi.izin_durumu == "bekliyor" and kisi.kaynak == "form"
    # Veritabanında ham jeton yok, yalnız özeti.
    u = (await db_oturumu.execute(select(EpListeUyelikleri).where(EpListeUyelikleri.kisi_id == kisi.id))).scalars().first()
    assert u.onay_ozeti == ep.onay_ozeti(ham) and ham not in (u.onay_ozeti or "") and u.durum == "bekliyor"

    bilgi = (await istemci.get(f"{A}/onay/{ham}")).json()
    assert bilgi["durum"] == "gecerli" and bilgi["eposta"].startswith(eposta[0] + "***@") and bilgi["liste"] == "Haftalık bülten"
    y = await istemci.post(f"{A}/onay/{ham}", headers=_ip())
    assert y.status_code == 200 and y.json()["durum"] == "onaylandi"
    await db_oturumu.refresh(kisi)
    assert kisi.izin_durumu == "izinli" and kisi.alici_turu == "kurumsal" and kisi.izin_kaynagi == f"form:{f['genel_anahtar']}"
    assert kisi.izin_metin_surumu == "bulten-1/tr" and kisi.onay_zamani is not None
    kanit = json.loads(kisi.izin_kaniti)
    assert kanit["yontem"] == "cift_onay" and kanit["metin_ozeti"]
    # Tekrar kullanım: 409 (ikinci kez işlenmez).
    y = await istemci.post(f"{A}/onay/{ham}", headers=_ip())
    assert y.status_code == 409 and _kod(y) == "kullanildi"
    assert (await istemci.get(f"{A}/onay/{ham}")).json()["durum"] == "kullanildi"
    # Zaten abone: ikinci form gönderimi yeni onay e-postası yollamaz.
    once = len(resend["tekil"])
    await _abone_ol(istemci, f["genel_anahtar"], eposta)
    assert len(resend["tekil"]) == once
    # Geçersiz jeton.
    assert (await istemci.get(f"{A}/onay/yok-boyle-bir-jeton")).status_code == 404

    # Süre: 72 saat sonra onay olmaz.
    eposta2 = _e("gec")
    await _abone_ol(istemci, f["genel_anahtar"], eposta2)
    ham2 = resend["tekil"][-1]["text"].split("/bulten/onay/")[1].split()[0]
    gercek = ep.simdi
    monkeypatch.setattr(ep, "simdi", lambda: gercek() + timedelta(hours=73))
    assert (await istemci.get(f"{A}/onay/{ham2}")).json()["durum"] == "suresi_doldu"
    y = await istemci.post(f"{A}/onay/{ham2}", headers=_ip())
    assert y.status_code == 410 and _kod(y) == "suresi_doldu"


async def test_abonelik_onay_epostasi_siniri_ve_koken(istemci, yonetici_basligi, resend, yasal):
    l = await _liste(istemci, yonetici_basligi)
    f = await _form(istemci, yonetici_basligi, l["id"], izinli_alanlar=["musteri-sitesi.com"])
    eposta = _e("bomba")
    for _ in range(4):
        y = await _abone_ol(istemci, f["genel_anahtar"], eposta)
        assert y.status_code == 200
    # Aynı adrese 24 saatte en çok 2 onay e-postası (abonelik bombardımanına karşı).
    assert len([i for i in resend["tekil"] if i["to"] == [eposta]]) == 2
    # Köken: izinli alan adı + site geçer; başka site 403.
    assert (await istemci.get(f"{A}/form/{f['genel_anahtar']}", headers={"Origin": "https://www.musteri-sitesi.com"})).status_code == 200
    assert (await istemci.get(f"{A}/form/{f['genel_anahtar']}", headers={"Origin": "https://mehmetkuru.dev"})).status_code == 200
    y = await istemci.get(f"{A}/form/{f['genel_anahtar']}", headers={"Origin": "https://kotu.example"})
    assert y.status_code == 403 and _kod(y) == "alan_adi_izinsiz"
    # Pasif form 404.
    await istemci.put(f"{Y}/formlar/{f['id']}", json={"aktif": False}, headers=yonetici_basligi)
    assert (await istemci.get(f"{A}/form/{f['genel_anahtar']}")).status_code == 404


async def test_musteri_formu_modul_kapaninca_410(istemci, yonetici_basligi, resend):
    musteri = _e("formcu")
    await _modul(istemci, yonetici_basligi, musteri)
    l = await _liste(istemci, _b(musteri), M)
    f = await _form(istemci, _b(musteri), l["id"], M, aydinlatma_baglantisi="https://formcu.example/gizlilik")
    t = (await istemci.get(f"{A}/form/{f['genel_anahtar']}")).json()
    assert t["aydinlatma"]["baglanti"] == "https://formcu.example/gizlilik"
    await _modul(istemci, yonetici_basligi, musteri, acik=False)
    assert (await istemci.get(f"{A}/form/{f['genel_anahtar']}")).status_code == 410


# ---------------------------------------------------------------------------
# Ret: tek tık + tercih sayfası
# ---------------------------------------------------------------------------
async def test_ret_tek_tik_ve_tercih(istemci, yonetici_basligi, resend, yasal, db_oturumu):
    from models.eposta_pazarlama import EpBastirma, EpGonderimler, EpKisiler
    from services import eposta_pazarlama as ep

    l1 = await _liste(istemci, yonetici_basligi, ad="Kampanyalar")
    l2 = await _liste(istemci, yonetici_basligi, ad="Haberler")
    kisi = await _kisi(istemci, yonetici_basligi, izin=IZIN, listeler=[l1["id"], l2["id"]])
    jeton = ep.ret_jetonu(kisi["id"])

    t = (await istemci.get(f"{A}/tercih/{jeton}")).json()
    assert t["abone"] and {x["ad"] for x in t["listeler"]} == {"Kampanyalar", "Haberler"} and "***@" in t["eposta"]
    # Tek listeden ayrıl (abonelik sürer).
    t = (await istemci.post(f"{A}/tercih/{jeton}", content=json.dumps({"listeler": {str(l2["id"]): False}}), headers=_ip())).json()
    assert t["abone"] and {x["ad"]: x["aktif"] for x in t["listeler"]} == {"Kampanyalar": True, "Haberler": False}
    # Yeniden katıl (izinli olduğu için).
    t = (await istemci.post(f"{A}/tercih/{jeton}", content=json.dumps({"listeler": {str(l2["id"]): True}}), headers=_ip())).json()
    assert all(x["aktif"] for x in t["listeler"])

    # GET durum değiştirmez: tercih sayfasına (tek tıkla ret) yönlendirir.
    y = await istemci.get(f"{A}/ret/{jeton}")
    assert y.status_code == 303 and y.headers["location"] == f"https://mehmetkuru.dev/bulten/tercih/{jeton}?islem=ret"
    k = (await db_oturumu.execute(select(EpKisiler).where(EpKisiler.id == kisi["id"]))).scalars().first()
    assert k.izin_durumu == "izinli"

    # Bekleyen bir kampanya iletisi ret anında düşer.
    kamp = await _kampanya(istemci, yonetici_basligi, l1["id"])
    db_oturumu.add(EpGonderimler(kapsam="@ajans", kampanya_id=kamp["id"], kisi_id=kisi["id"], eposta=kisi["eposta"], durum="kuyrukta"))
    await db_oturumu.commit()

    # RFC 8058 tek tık: POST (form gövdesi) → anında ret.
    y = await istemci.post(f"{A}/ret/{jeton}", content="List-Unsubscribe=One-Click",
                           headers={"Content-Type": "application/x-www-form-urlencoded", **_ip()})
    assert y.status_code == 200
    await db_oturumu.refresh(k)
    assert k.izin_durumu == "reddetti" and k.ret_kaynagi == "tek_tik" and k.ret_zamani is not None
    b = (await db_oturumu.execute(select(EpBastirma).where(EpBastirma.kapsam == "@ajans", EpBastirma.eposta == kisi["eposta"]))).scalars().first()
    assert b is not None and b.neden == "ret"
    g = (await db_oturumu.execute(select(EpGonderimler).where(EpGonderimler.kampanya_id == kamp["id"]))).scalars().first()
    await db_oturumu.refresh(g)
    assert g.durum == "atlandi" and g.neden == "ret"
    t = (await istemci.get(f"{A}/tercih/{jeton}")).json()
    assert not t["abone"] and not any(x["aktif"] for x in t["listeler"])
    # Ret kalıcı: panelden izin geri verilemez; liste tercihiyle de dönülemez; bastırma silinemez.
    y = await istemci.put(f"{Y}/kisiler/{kisi['id']}", json={"izin": IZIN}, headers=yonetici_basligi)
    assert y.status_code == 409 and _kod(y) == "ret_kalici"
    t = (await istemci.post(f"{A}/tercih/{jeton}", content=json.dumps({"listeler": {str(l1["id"]): True}}), headers=_ip())).json()
    assert not any(x["aktif"] for x in t["listeler"])
    y = await istemci.delete(f"{Y}/bastirma/{b.id}", headers=yonetici_basligi)
    assert y.status_code == 409 and _kod(y) == "bastirma_kalici"
    # İmza: başka kişinin kimliğiyle ya da bozuk jetonla olmaz.
    sahte = f"{kisi['id'] + 1}-{jeton.split('-', 1)[1]}"
    assert (await istemci.post(f"{A}/ret/{sahte}", content="List-Unsubscribe=One-Click", headers=_ip())).status_code == 404
    assert (await istemci.get(f"{A}/tercih/{jeton}x")).status_code == 404
    assert (await istemci.get(f"{A}/ret/bozuk")).status_code == 404


async def test_ret_eden_yeniden_cift_onayla_abone_olabilir(istemci, yonetici_basligi, resend, yasal, db_oturumu):
    from models.eposta_pazarlama import EpBastirma, EpKisiler
    from services import eposta_pazarlama as ep

    l = await _liste(istemci, yonetici_basligi)
    f = await _form(istemci, yonetici_basligi, l["id"])
    kisi = await _kisi(istemci, yonetici_basligi, izin=IZIN, listeler=[l["id"]])
    await istemci.post(f"{A}/ret/{ep.ret_jetonu(kisi['id'])}", content="List-Unsubscribe=One-Click", headers=_ip())
    y = await _abone_ol(istemci, f["genel_anahtar"], kisi["eposta"])
    assert y.status_code == 200
    ham = resend["tekil"][-1]["text"].split("/bulten/onay/")[1].split()[0]
    assert (await istemci.post(f"{A}/onay/{ham}", headers=_ip())).status_code == 200
    k = (await db_oturumu.execute(select(EpKisiler).where(EpKisiler.id == kisi["id"]))).scalars().first()
    await db_oturumu.refresh(k)
    assert k.izin_durumu == "izinli" and k.ret_zamani is None
    assert (await db_oturumu.execute(select(EpBastirma).where(EpBastirma.kapsam == "@ajans", EpBastirma.eposta == kisi["eposta"]))).scalars().first() is None


# ---------------------------------------------------------------------------
# CSV içe aktarma
# ---------------------------------------------------------------------------
async def test_csv_ice_aktarma_izinsiz_bireysel_gonderilmez(istemci, yonetici_basligi, resend, yasal, db_oturumu):
    from models.eposta_pazarlama import EpKisiler

    l = await _liste(istemci, yonetici_basligi)
    ek = uuid.uuid4().hex[:6]
    csv = (f"email,name,consent_source,consent_date,type\n"
           f"izinli-{ek}@ornek.com,İzinli,Web formu,2026-03-01,b2c\n"
           f"izinsiz-{ek}@ornek.com,İzinsiz,,,b2c\n"
           f"satin-{ek}@ornek.com,Satın alınmış,,,\n"
           f"tacir-{ek}@ornek.com,Tacir,,,b2b\n").encode()
    dosya = {"dosya": ("liste.csv", csv, "text/csv")}
    y = await istemci.post(f"{Y}/kisiler/ice-aktar/onizleme", files=dosya, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["ozet"]["izinsiz_bireysel"] == 2 and y.json()["ozet"]["izinli"] == 1
    y = await istemci.post(f"{Y}/kisiler/ice-aktar", files=dosya, data={"liste_id": str(l["id"]), "kaynak_notu": "Fuar 2026"},
                           headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    assert y.json()["sayilar"]["eklenen"] == 4 and y.json()["sayilar"]["izinli"] == 1 and y.json()["sayilar"]["listeye"] == 4
    k = (await db_oturumu.execute(select(EpKisiler).where(EpKisiler.eposta == f"izinli-{ek}@ornek.com"))).scalars().first()
    assert k.izin_durumu == "izinli" and k.izin_kaynagi == "csv:Web formu" and k.kaynak == "csv"
    assert json.loads(k.izin_kaniti)["not"] == "Fuar 2026"
    kamp = await _kampanya(istemci, yonetici_basligi, l["id"])
    await istemci.post(f"{Y}/kampanyalar/{kamp['id']}/gonder", json={}, headers=yonetici_basligi)
    giden = {i["to"][0] for i in resend["iletiler"]()}
    assert giden == {f"izinli-{ek}@ornek.com", f"tacir-{ek}@ornek.com"}
    # Ret etmiş kişinin izni CSV ile geri gelmez.
    tacir = (await db_oturumu.execute(select(EpKisiler).where(EpKisiler.eposta == f"tacir-{ek}@ornek.com"))).scalars().first()
    await istemci.post(f"{Y}/kisiler/{tacir.id}/ret", headers=yonetici_basligi)
    csv2 = f"email,consent_source,consent_date\ntacir-{ek}@ornek.com,Yeni form,2026-04-01\n".encode()
    y = await istemci.post(f"{Y}/kisiler/ice-aktar", files={"dosya": ("l.csv", csv2, "text/csv")}, headers=yonetici_basligi)
    assert y.json()["sayilar"]["ret_korundu"] == 1
    await db_oturumu.refresh(tacir)
    assert tacir.izin_durumu == "reddetti"


async def test_panelden_izin_kaniti_zorunlu(istemci, yonetici_basligi):
    y = await istemci.post(f"{Y}/kisiler", json={"eposta": _e(), "izin": {"durum": "izinli"}}, headers=yonetici_basligi)
    assert y.status_code == 400 and _kod(y) == "izin_kaynagi_gerekli"
    y = await istemci.post(f"{Y}/kisiler", json={"eposta": _e(), "izin": {"durum": "izinli", "kaynak": "telefon"}}, headers=yonetici_basligi)
    assert y.status_code == 400 and _kod(y) == "izin_tarihi_gerekli"
    y = await istemci.post(f"{Y}/kisiler", json={"eposta": _e(), "izin": {**IZIN, "zaman": "2099-01-01T00:00:00Z"}}, headers=yonetici_basligi)
    assert y.status_code == 400 and _kod(y) == "izin_tarihi_gerekli"
    k = await _kisi(istemci, yonetici_basligi, izin=IZIN)
    assert k["izin_durumu"] == "izinli" and k["izin_kaynagi"] == "manuel:fuar standı formu" and k["izin_kaniti"] == "Islak imzalı form"
    y = await istemci.post(f"{Y}/kisiler", json={"eposta": k["eposta"]}, headers=yonetici_basligi)
    assert y.status_code == 409 and _kod(y) == "kisi_var"
    y = await istemci.put(f"{Y}/kisiler/{k['id']}", json={"izin": {"durum": "izinsiz"}}, headers=yonetici_basligi)
    assert y.status_code == 400 and _kod(y) == "izin_geri_alma_ret_ile"


async def test_crm_aktarimi_izin_crmden(istemci, yonetici_basligi, db_oturumu):
    from models.crm import CrmAdaylari

    izinli, izinsiz = _e("crmizinli"), _e("crmizinsiz")
    db_oturumu.add(CrmAdaylari(ad="CRM İzinli", email=izinli, asama="yeni", kaynak="form", pazarlama_izni_at=datetime(2026, 5, 1, tzinfo=UTC),
                               pazarlama_izni_kaynak="form:3", pazarlama_metin_surumu="1/tr"))
    db_oturumu.add(CrmAdaylari(ad="CRM İzinsiz", email=izinsiz, asama="yeni", kaynak="form"))
    await db_oturumu.commit()
    l = await _liste(istemci, yonetici_basligi)
    y = await istemci.post(f"{Y}/kisiler/crm-aktar", json={"liste_id": l["id"], "yalniz_izinli": False}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    kisiler = {k["eposta"]: k for k in (await istemci.get(f"{Y}/kisiler?liste_id={l['id']}&sinir=200", headers=yonetici_basligi)).json()["items"]}
    assert kisiler[izinli]["izin_durumu"] == "izinli" and kisiler[izinli]["izin_metin_surumu"] == "1/tr" and kisiler[izinli]["kaynak"] == "crm"
    assert kisiler[izinsiz]["izin_durumu"] == "izinsiz"


# ---------------------------------------------------------------------------
# Segment (uç)
# ---------------------------------------------------------------------------
async def test_segment_hedefli_kampanya(istemci, yonetici_basligi, resend, yasal):
    etiket = f"seg{uuid.uuid4().hex[:5]}"
    a = await _kisi(istemci, yonetici_basligi, izin=IZIN, etiketler=[etiket])
    await _kisi(istemci, yonetici_basligi, etiketler=[etiket])  # izinsiz bireysel
    await _kisi(istemci, yonetici_basligi, izin=IZIN)
    kurallar = {"kurallar": [{"alan": "etiket", "op": "icerir", "deger": etiket}]}
    y = await istemci.post(f"{Y}/segmentler/onizleme", json={"kurallar": kurallar}, headers=yonetici_basligi)
    assert y.json()["sayi"] == 2
    s = (await istemci.post(f"{Y}/segmentler", json={"ad": "VIP", "kurallar": kurallar}, headers=yonetici_basligi)).json()
    assert s["sayi"] == 2
    y = await istemci.post(f"{Y}/kampanyalar", json={"ad": "Seg", "konu": "Seg", "bloklar": BLOKLAR, "hedef": {"segmentler": [s["id"]]}},
                           headers=yonetici_basligi)
    k = y.json()
    y = await istemci.post(f"{Y}/kampanyalar/{k['id']}/gonder", json={}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    assert [i["to"][0] for i in resend["iletiler"]()] == [a["eposta"]]


# ---------------------------------------------------------------------------
# Parçalı / zamanlanmış gönderim + hız sınırı
# ---------------------------------------------------------------------------
async def test_hiz_sinirlayici_sahte_saatle():
    from services.eposta_gonderim import AsyncHizSinirlayici

    saat = {"t": 100.0}
    uyunan = []

    async def uyku(s):
        uyunan.append(s)
        saat["t"] += s

    h = AsyncHizSinirlayici(2.0, saat=lambda: saat["t"], uyku=uyku)
    for _ in range(5):
        await h.bekle()
    # Saniyede 2 istek: 5 istek ≥ 2 sn sürer, ilk istek beklemez.
    assert len(uyunan) == 4 and abs(sum(uyunan) - 2.0) < 1e-9
    saat["t"] += 10
    assert await h.bekle() == 0.0


async def test_parcali_ve_zamanli_gonderim(istemci, yonetici_basligi, resend, yasal, db_oturumu, monkeypatch):
    from models.eposta_pazarlama import EpGonderimler, EpKampanyalar, EpKisiler, EpListeUyelikleri
    from services import eposta_gonderim as eg
    from services import eposta_pazarlama as ep

    l = await _liste(istemci, yonetici_basligi)
    on = uuid.uuid4().hex[:6]
    for i in range(250):
        k = EpKisiler(kapsam="@ajans", eposta=f"toplu{i}-{on}@ornek.com", alici_turu="kurumsal", izin_durumu="izinsiz", kaynak="csv",
                      etiketler="[]", ozel_alanlar="{}", dil="tr")
        db_oturumu.add(k)
        await db_oturumu.flush()
        db_oturumu.add(EpListeUyelikleri(liste_id=l["id"], kisi_id=k.id, durum="aktif"))
    await db_oturumu.commit()
    k = await _kampanya(istemci, yonetici_basligi, l["id"])
    # Zamanla: 2 saat sonra.
    zaman = (ep.simdi() + timedelta(hours=2)).isoformat()
    y = await istemci.post(f"{Y}/kampanyalar/{k['id']}/gonder", json={"zaman": zaman}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["kampanya"]["durum"] == "zamanlandi" and y.json()["kitle"]["gonderilebilir"] == 250
    sonuc = await eg.zamanli_isle(db_oturumu, en_cok=100)
    assert sonuc["baslatilan"] == 0 and not resend["toplu"]
    gercek = ep.simdi
    monkeypatch.setattr(ep, "simdi", lambda: gercek() + timedelta(hours=2, minutes=1))

    # Saniyede 2 istek sınırı (sahte saat): 3 parça → 2 bekleme.
    saat = {"t": 0.0}
    uyunan = []

    async def uyku(s):
        uyunan.append(s)
        saat["t"] += s

    hiz = eg.AsyncHizSinirlayici(2.0, saat=lambda: saat["t"], uyku=uyku)
    sonuc = await eg.zamanli_isle(db_oturumu, en_cok=150, hiz=hiz)
    assert sonuc["baslatilan"] == 1 and sonuc["gonderilen"] == 150
    assert [len(t["iletiler"]) for t in resend["toplu"]] == [100, 50]  # çağrı başına ≤ 100
    kamp = (await db_oturumu.execute(select(EpKampanyalar).where(EpKampanyalar.id == k["id"]))).scalars().first()
    await db_oturumu.refresh(kamp)
    assert kamp.durum == "gonderiliyor"
    sonuc = await eg.zamanli_isle(db_oturumu, en_cok=150, hiz=hiz)
    assert sonuc["gonderilen"] == 100 and len(uyunan) == 2 and abs(sum(uyunan) - 1.0) < 1e-9
    await db_oturumu.refresh(kamp)
    assert kamp.durum == "tamamlandi"
    adresler = [i["to"][0] for i in resend["iletiler"]()]
    assert len(adresler) == 250 and len(set(adresler)) == 250  # tekrar yok
    # Bir sonraki tur hiçbir şey göndermez.
    sonuc = await eg.zamanli_isle(db_oturumu, en_cok=150, hiz=hiz)
    assert sonuc["gonderilen"] == 0
    durumlar = {g.durum for g in (await db_oturumu.execute(select(EpGonderimler).where(EpGonderimler.kampanya_id == k["id"]))).scalars().all()}
    assert durumlar == {"gonderildi"}


async def test_gecici_resend_hatasi_satiri_kuyruga_geri_koyar(istemci, yonetici_basligi, resend, yasal, db_oturumu):
    from models.eposta_pazarlama import EpGonderimler

    l = await _liste(istemci, yonetici_basligi)
    await _kisi(istemci, yonetici_basligi, alici_turu="kurumsal", listeler=[l["id"]])
    k = await _kampanya(istemci, yonetici_basligi, l["id"])
    resend["yanit"] = (429, {"message": "rate limit"})
    y = await istemci.post(f"{Y}/kampanyalar/{k['id']}/gonder", json={}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["kampanya"]["durum"] == "gonderiliyor"
    g = (await db_oturumu.execute(select(EpGonderimler).where(EpGonderimler.kampanya_id == k["id"]))).scalars().first()
    await db_oturumu.refresh(g)
    assert g.durum == "kuyrukta" and g.deneme == 1
    resend["yanit"] = None
    from services import eposta_gonderim as eg

    await eg.zamanli_isle(db_oturumu)
    await db_oturumu.refresh(g)
    assert g.durum == "gonderildi"


async def test_siklik_siniri_gunluk_bir_ileti(istemci, yonetici_basligi, resend, yasal, db_oturumu):
    from models.eposta_pazarlama import EpGonderimler

    l = await _liste(istemci, yonetici_basligi)
    kisi = await _kisi(istemci, yonetici_basligi, izin=IZIN, listeler=[l["id"]])
    k1 = await _kampanya(istemci, yonetici_basligi, l["id"])
    k2 = await _kampanya(istemci, yonetici_basligi, l["id"])
    assert (await istemci.post(f"{Y}/kampanyalar/{k1['id']}/gonder", json={}, headers=yonetici_basligi)).status_code == 200
    # Panel önizlemesi sınırı şu anki duruma göre gösterir (onay penceresindeki sayı doğru olsun).
    kitle = (await istemci.post(f"{Y}/kampanyalar/{k2['id']}/kitle", json={}, headers=yonetici_basligi)).json()
    assert kitle["gonderilebilir"] == 0 and kitle["atlanacak"] == {"siklik_siniri": 1}
    assert (await istemci.post(f"{Y}/kampanyalar/{k2['id']}/gonder", json={}, headers=yonetici_basligi)).status_code == 200
    g = (await db_oturumu.execute(select(EpGonderimler).where(EpGonderimler.kampanya_id == k2["id"]))).scalars().first()
    assert g.durum == "atlandi" and g.neden == "siklik_siniri"
    assert [i["to"][0] for i in resend["iletiler"]()].count(kisi["eposta"]) == 1


# ---------------------------------------------------------------------------
# Webhook (Svix)
# ---------------------------------------------------------------------------
def _svix(govde: bytes, svix_id: str | None = None, zaman: int | None = None, gizli: str = WEBHOOK_GIZLI) -> dict:
    svix_id = svix_id or f"msg_{uuid.uuid4().hex}"
    zaman = zaman or int(time.time())
    anahtar = base64.b64decode(gizli.split("_", 1)[1])
    imza = base64.b64encode(hmac.new(anahtar, f"{svix_id}.{zaman}.".encode() + govde, hashlib.sha256).digest()).decode()
    return {"svix-id": svix_id, "svix-timestamp": str(zaman), "svix-signature": f"v1,{imza}", "Content-Type": "application/json"}


async def test_webhook_geri_donme_ve_sikayet_bastirma(istemci, yonetici_basligi, resend, yasal, db_oturumu, monkeypatch):
    from models.eposta_pazarlama import EpBastirma, EpGonderimler, EpKisiler

    l = await _liste(istemci, yonetici_basligi)
    sert = await _kisi(istemci, yonetici_basligi, izin=IZIN, listeler=[l["id"]])
    sikayet = await _kisi(istemci, yonetici_basligi, izin=IZIN, listeler=[l["id"]])
    teslim = await _kisi(istemci, yonetici_basligi, izin=IZIN, listeler=[l["id"]])
    k = await _kampanya(istemci, yonetici_basligi, l["id"])
    assert (await istemci.post(f"{Y}/kampanyalar/{k['id']}/gonder", json={}, headers=yonetici_basligi)).status_code == 200
    satirlar = {g.eposta: g for g in (await db_oturumu.execute(select(EpGonderimler).where(EpGonderimler.kampanya_id == k["id"]))).scalars().all()}

    def olay(tur, eposta, **veri):
        return json.dumps({"type": tur, "created_at": "2026-10-01T10:00:00Z",
                           "data": {"email_id": satirlar[eposta].resend_id, "to": [eposta], **veri}}).encode()

    U = f"{A}/resend-webhook"
    govde = olay("email.delivered", teslim["eposta"])
    assert (await istemci.post(U, content=govde, headers=_svix(govde))).status_code == 503  # anahtar tanımlı değil
    monkeypatch.setenv("RESEND_PAZARLAMA_IMZA_ANAHTARI", WEBHOOK_GIZLI)
    assert (await istemci.post(U, content=govde, headers=_svix(govde, gizli="whsec_" + base64.b64encode(b"baska").decode()))).status_code == 401
    assert (await istemci.post(U, content=govde, headers=_svix(govde, zaman=int(time.time()) - 3600))).status_code == 401
    basliklar = _svix(govde)
    y = await istemci.post(U, content=govde, headers=basliklar)
    assert y.status_code == 200 and y.json()["durum"] == "islendi"
    assert (await istemci.post(U, content=govde, headers=basliklar)).json()["durum"] == "tekrar"  # aynı svix-id

    govde = olay("email.bounced", sert["eposta"], bounce={"type": "Permanent", "subType": "General", "message": "no such user"})
    assert (await istemci.post(U, content=govde, headers=_svix(govde))).status_code == 200
    govde = olay("email.complained", sikayet["eposta"])
    assert (await istemci.post(U, content=govde, headers=_svix(govde))).status_code == 200
    # Takip kapalı: açılma olayı kaydedilmez.
    govde = olay("email.opened", teslim["eposta"])
    assert (await istemci.post(U, content=govde, headers=_svix(govde))).json()["neden"] == "takip_kapali"

    for g in satirlar.values():
        await db_oturumu.refresh(g)
    assert satirlar[teslim["eposta"]].durum == "teslim" and satirlar[teslim["eposta"]].acilma_at is None
    assert satirlar[sert["eposta"]].durum == "geri_dondu" and satirlar[sert["eposta"]].geri_donme_turu == "sert"
    assert satirlar[sikayet["eposta"]].durum == "sikayet"
    genel = (await db_oturumu.execute(select(EpBastirma).where(EpBastirma.kapsam == "*", EpBastirma.eposta == sert["eposta"]))).scalars().first()
    assert genel is not None and genel.neden == "sert_geri_donme"  # bütün hesaplarda
    hesap = (await db_oturumu.execute(select(EpBastirma).where(EpBastirma.kapsam == "@ajans", EpBastirma.eposta == sikayet["eposta"]))).scalars().first()
    assert hesap is not None and hesap.neden == "sikayet"
    ks = (await db_oturumu.execute(select(EpKisiler).where(EpKisiler.id == sikayet["id"]))).scalars().first()
    await db_oturumu.refresh(ks)
    assert ks.izin_durumu == "reddetti" and ks.ret_kaynagi == "sikayet"
    rapor = (await istemci.get(f"{Y}/kampanyalar/{k['id']}/rapor", headers=yonetici_basligi)).json()
    assert rapor["sayilar"]["teslim"] == 1 and rapor["sayilar"]["geri_donen"] == 1 and rapor["sayilar"]["sikayet"] == 1
    # Sert geri dönen adres başka bir hesabın kampanyasında da atlanır.
    musteri = _e("baska-hesap")
    await _modul(istemci, yonetici_basligi, musteri)
    await istemci.put(f"{M}/ayarlar", json={"unvan": "B", "adres": "C"}, headers=_b(musteri))
    lm = await _liste(istemci, _b(musteri), M)
    await _kisi(istemci, _b(musteri), M, eposta=sert["eposta"], alici_turu="kurumsal", listeler=[lm["id"]])
    km = await _kampanya(istemci, _b(musteri), lm["id"], M)
    y = await istemci.post(f"{M}/kampanyalar/{km['id']}/kitle", json={}, headers=_b(musteri))
    assert y.json()["atlanacak"] == {"bastirildi": 1}
    # Ajans hesabı bu oturumdaki toplu gönderimlerle şikâyet eşiğini aşmış olabilir: sonraki testler için kaldır.
    y = await istemci.put(f"{Y}/hesaplar/@ajans", json={"askida": False}, headers=yonetici_basligi)
    assert y.status_code == 200


async def test_otomatik_askiya_alma(istemci, yonetici_basligi, resend, db_oturumu):
    from models.eposta_pazarlama import EpGonderimler
    from services import eposta_gonderim as eg
    from services import eposta_pazarlama as ep

    musteri = _e("spamci")
    await _modul(istemci, yonetici_basligi, musteri)
    an = ep.simdi()
    for i in range(60):
        db_oturumu.add(EpGonderimler(kapsam=musteri, hesap_email=musteri, eposta=f"x{i}@ornek.com", durum="gonderildi", gonderim_at=an,
                                     sikayet_at=an if i == 0 else None))
    await db_oturumu.commit()
    neden = await eg.askiya_alma_denetimi(db_oturumu, musteri)  # 1/60 > %0,3
    await db_oturumu.commit()
    assert neden == "sikayet_orani"
    a = (await istemci.get(f"{M}/ayarlar", headers=_b(musteri))).json()
    assert a["askida"] and a["askida_neden"] == "sikayet_orani"
    hesaplar = (await istemci.get(f"{Y}/hesaplar", headers=yonetici_basligi)).json()["items"]
    satir = next(h for h in hesaplar if h["kapsam"] == musteri)
    assert satir["askida"] and satir["sikayet_30"] == 1
    l = await _liste(istemci, _b(musteri), M)
    k = await _kampanya(istemci, _b(musteri), l["id"], M)
    y = await istemci.post(f"{M}/kampanyalar/{k['id']}/gonder", json={}, headers=_b(musteri))
    assert y.status_code == 409 and _kod(y) == "hesap_askida"
    y = await istemci.put(f"{Y}/hesaplar/{musteri}", json={"askida": False}, headers=yonetici_basligi)
    assert y.status_code == 200 and not y.json()["askida"]


# ---------------------------------------------------------------------------
# Açılma / tıklama takibi (isteğe bağlı)
# ---------------------------------------------------------------------------
async def test_acilma_ve_tiklama_takibi(istemci, yonetici_basligi, resend, yasal, db_oturumu):
    from models.eposta_pazarlama import EpGonderimler
    from services import eposta_pazarlama as ep

    musteri = _e("takipci")
    await _modul(istemci, yonetici_basligi, musteri)
    await istemci.put(f"{M}/ayarlar", json={"unvan": "T", "adres": "A", "acilma_takibi": True, "tiklama_takibi": True}, headers=_b(musteri))
    l = await _liste(istemci, _b(musteri), M)
    kisi = await _kisi(istemci, _b(musteri), M, izin=IZIN, listeler=[l["id"]])
    k = await _kampanya(istemci, _b(musteri), l["id"], M)
    assert (await istemci.post(f"{M}/kampanyalar/{k['id']}/gonder", json={}, headers=_b(musteri))).status_code == 200
    i = resend["iletiler"]()[-1]
    g = (await db_oturumu.execute(select(EpGonderimler).where(EpGonderimler.kampanya_id == k["id"]))).scalars().first()
    jeton = ep.izleme_jetonu(g.id)
    assert f"/api/v1/bulten/a/{jeton}.gif" in i["html"] and f"/api/v1/bulten/t/{jeton}/1" in i["html"]
    assert "https://ornek.com/incele" not in i["html"]  # bağlantı yönlendirmeli
    assert f"/bulten/tercih/{ep.ret_jetonu(kisi['id'])}?islem=ret" in i["html"]  # ret bağlantısı yönlendirilmez
    y = await istemci.get(f"{A}/a/{jeton}.gif")
    assert y.status_code == 200 and y.headers["content-type"] == "image/gif" and y.content.startswith(b"GIF89a")
    y = await istemci.get(f"{A}/t/{jeton}/1")
    assert y.status_code == 302 and y.headers["location"] == "https://ornek.com/incele"
    y = await istemci.get(f"{A}/t/{jeton}/99")
    assert y.status_code == 302 and y.headers["location"] == "https://mehmetkuru.dev"  # açık yönlendirme yok
    y = await istemci.get(f"{A}/t/0-AAAAAAAAAAAAAAAAAAAAAA/0")
    assert y.headers["location"] == "https://mehmetkuru.dev"
    rapor = (await istemci.get(f"{M}/kampanyalar/{k['id']}/rapor", headers=_b(musteri))).json()
    assert rapor["sayilar"]["acilan"] == 1 and rapor["sayilar"]["tiklayan"] == 1 and rapor["oranlar"]["tiklama"] == 1.0
    assert next(b for b in rapor["baglantilar"] if b["indeks"] == 1)["tiklama"] == 1


# ---------------------------------------------------------------------------
# A/B konu testi
# ---------------------------------------------------------------------------
async def test_ab_konu_testi(istemci, yonetici_basligi, resend, yasal, db_oturumu, monkeypatch):
    from models.eposta_pazarlama import EpGonderimler, EpKampanyalar
    from services import eposta_gonderim as eg
    from services import eposta_pazarlama as ep

    await istemci.put(f"{Y}/ayarlar", json={"acilma_takibi": True}, headers=yonetici_basligi)
    try:
        l = await _liste(istemci, yonetici_basligi)
        for _ in range(20):
            await _kisi(istemci, yonetici_basligi, alici_turu="kurumsal", listeler=[l["id"]])
        k = await _kampanya(istemci, yonetici_basligi, l["id"], ab={"acik": True, "konu_b": "B konusu", "oran": 50, "bekleme_saat": 2})
        y = await istemci.post(f"{Y}/kampanyalar/{k['id']}/gonder", json={}, headers=yonetici_basligi)
        assert y.status_code == 200 and y.json()["kampanya"]["durum"] == "ab_test", y.text
        satirlar = (await db_oturumu.execute(select(EpGonderimler).where(EpGonderimler.kampanya_id == k["id"]))).scalars().all()
        say = {v: sum(1 for g in satirlar if g.varyant == v) for v in ("a", "b", None)}
        assert say == {"a": 5, "b": 5, None: 10}
        konular = sorted({i["subject"] for i in resend["iletiler"]()})
        assert konular == ["B konusu", "Ekim fırsatları"]
        # B daha çok açıldı.
        for g in satirlar:
            if g.varyant == "b":
                await istemci.get(f"{A}/a/{ep.izleme_jetonu(g.id)}.gif")
        assert await eg.ab_kararlari(db_oturumu) == 0  # bekleme süresi dolmadı
        gercek = ep.simdi
        monkeypatch.setattr(ep, "simdi", lambda: gercek() + timedelta(hours=2, minutes=5))
        await eg.zamanli_isle(db_oturumu)
        kamp = (await db_oturumu.execute(select(EpKampanyalar).where(EpKampanyalar.id == k["id"]))).scalars().first()
        await db_oturumu.refresh(kamp)
        assert kamp.kazanan == "b" and kamp.durum == "tamamlandi"
        son = [i for i in resend["iletiler"]()][10:]
        assert len(son) == 10 and {i["subject"] for i in son} == {"B konusu"}
        rapor = (await istemci.get(f"{Y}/kampanyalar/{k['id']}/rapor", headers=yonetici_basligi)).json()
        assert rapor["varyantlar"]["b"]["acilan"] == 5 and rapor["sayilar"]["gonderilen"] == 20
        # Küçük kitlede A/B yok.
        l2 = await _liste(istemci, yonetici_basligi)
        await _kisi(istemci, yonetici_basligi, alici_turu="kurumsal", listeler=[l2["id"]])
        k2 = await _kampanya(istemci, yonetici_basligi, l2["id"], ab={"acik": True, "konu_b": "B"})
        y = await istemci.post(f"{Y}/kampanyalar/{k2['id']}/gonder", json={}, headers=yonetici_basligi)
        assert y.status_code == 409 and _kod(y) == "ab_kitle_kucuk"
    finally:
        await istemci.put(f"{Y}/ayarlar", json={"acilma_takibi": False}, headers=yonetici_basligi)


# ---------------------------------------------------------------------------
# Damla dizisi
# ---------------------------------------------------------------------------
async def test_damla_dizisi_zamanlama_ve_cikis(istemci, yonetici_basligi, resend, yasal, db_oturumu, monkeypatch):
    from models.eposta_pazarlama import EpDiziKayitlari
    from services import eposta_gonderim as eg
    from services import eposta_pazarlama as ep

    l = await _liste(istemci, yonetici_basligi, ad="Hoş geldin listesi")
    f = await _form(istemci, yonetici_basligi, l["id"])
    adimlar = [
        {"bekle_gun": 0, "konu": "Hoş geldiniz {{ad}}", "bloklar": [{"tur": "metin", "metin": "Merhaba!"}]},
        {"bekle_gun": 2, "konu": "İkinci gün", "bloklar": [{"tur": "dugme", "metin": "Keşfet", "url": "https://ornek.com/k"}]},
        {"bekle_gun": 3, "konu": "Beşinci gün", "bloklar": [{"tur": "metin", "metin": "Son"}]},
    ]
    y = await istemci.post(f"{Y}/diziler", json={"ad": "Karşılama", "tetik": "abonelik_onaylandi", "liste_id": l["id"], "adimlar": adimlar,
                                                 "aktif": True, "cikis": {"hedef": {"tur": "etiket", "deger": "musteri"}}},
                           headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    d = y.json()
    assert d["aktif"] and len(d["adimlar"]) == 3 and d["cikis"]["hedef"] == {"tur": "etiket", "deger": "musteri"}

    # İki abone: biri dizi boyunca kalır, diğeri ret eder.
    epostalar = [_e("damla"), _e("damlaret")]
    kisiler = []
    for e in epostalar:
        await _abone_ol(istemci, f["genel_anahtar"], e)
        ham = resend["tekil"][-1]["text"].split("/bulten/onay/")[1].split()[0]
        assert (await istemci.post(f"{A}/onay/{ham}", headers=_ip())).status_code == 200
        kisiler.append((await istemci.get(f"{Y}/kisiler?ara={e}", headers=yonetici_basligi)).json()["items"][0])
    kayitlar = (await db_oturumu.execute(select(EpDiziKayitlari).where(EpDiziKayitlari.dizi_id == d["id"]))).scalars().all()
    assert len(kayitlar) == 2 and all(k.durum == "aktif" and k.sonraki_sira == 0 for k in kayitlar)

    def konular(e):
        return [i["subject"] for i in resend["iletiler"]() if i["to"] == [e]]

    await eg.zamanli_isle(db_oturumu)
    assert konular(epostalar[0]) == ["Hoş geldiniz Zeynep"] and konular(epostalar[1]) == ["Hoş geldiniz Zeynep"]
    await eg.zamanli_isle(db_oturumu)  # 2. adımın zamanı gelmedi
    assert len(konular(epostalar[0])) == 1
    # İkinci kişi ret eder → diziden çıkar.
    await istemci.post(f"{A}/ret/{ep.ret_jetonu(kisiler[1]['id'])}", content="List-Unsubscribe=One-Click", headers=_ip())
    gercek = ep.simdi
    monkeypatch.setattr(ep, "simdi", lambda: gercek() + timedelta(days=2, minutes=5))
    await eg.zamanli_isle(db_oturumu)
    assert konular(epostalar[0]) == ["Hoş geldiniz Zeynep", "İkinci gün"] and len(konular(epostalar[1])) == 1
    for k in kayitlar:
        await db_oturumu.refresh(k)
    durum = {k.kisi_id: (k.durum, k.cikis_nedeni) for k in kayitlar}
    assert durum[kisiler[1]["id"]] == ("cikti", "ret") and durum[kisiler[0]["id"]] == ("aktif", None)
    # Hedef: "musteri" etiketi alınca çıkar (3. adım gitmez).
    await istemci.put(f"{Y}/kisiler/{kisiler[0]['id']}", json={"etiketler": ["musteri"]}, headers=yonetici_basligi)
    monkeypatch.setattr(ep, "simdi", lambda: gercek() + timedelta(days=5, minutes=10))
    await eg.zamanli_isle(db_oturumu)
    assert len(konular(epostalar[0])) == 2
    for k in kayitlar:
        await db_oturumu.refresh(k)
    assert {k.kisi_id: (k.durum, k.cikis_nedeni) for k in kayitlar}[kisiler[0]["id"]] == ("cikti", "hedef")
    rapor = (await istemci.get(f"{Y}/diziler/{d['id']}/rapor", headers=yonetici_basligi)).json()
    assert [a["gonderilen"] for a in rapor["adimlar"]] == [2, 1, 0] and rapor["cikis"] == {"ret": 1, "hedef": 1}


async def test_dizi_liste_katildi_tetigi_ve_aktiflestirme_kurallari(istemci, yonetici_basligi, resend, yasal, db_oturumu):
    from models.eposta_pazarlama import EpDiziKayitlari

    l = await _liste(istemci, yonetici_basligi)
    y = await istemci.post(f"{Y}/diziler", json={"ad": "Boş", "liste_id": l["id"], "aktif": True}, headers=yonetici_basligi)
    assert y.status_code == 409 and _kod(y) == "adim_gerekli"
    y = await istemci.post(f"{Y}/diziler", json={"ad": "Liste", "tetik": "liste_katildi", "liste_id": l["id"], "aktif": True,
                                                 "adimlar": [{"konu": "Merhaba", "bloklar": [{"tur": "metin", "metin": "x"}]}]},
                           headers=yonetici_basligi)
    assert y.status_code == 200
    d = y.json()
    k = await _kisi(istemci, yonetici_basligi, alici_turu="kurumsal", listeler=[l["id"]])
    kayit = (await db_oturumu.execute(select(EpDiziKayitlari).where(EpDiziKayitlari.dizi_id == d["id"]))).scalars().all()
    assert [x.kisi_id for x in kayit] == [k["id"]]
    # Adım düzenleme: kimlik korunur, sıra güncellenir.
    adim = d["adimlar"][0]
    y = await istemci.put(f"{Y}/diziler/{d['id']}", json={"adimlar": [{"konu": "Önce", "bloklar": [{"tur": "metin", "metin": "a"}]},
                                                                      {**adim, "konu": "Sonra"}]}, headers=yonetici_basligi)
    assert y.status_code == 200 and [a["konu"] for a in y.json()["adimlar"]] == ["Önce", "Sonra"] and y.json()["adimlar"][1]["id"] == adim["id"]


# ---------------------------------------------------------------------------
# Test e-postası, önizleme, görsel, sahte kutu
# ---------------------------------------------------------------------------
async def test_test_epostasi_ve_onizleme(istemci, yonetici_basligi, resend, yasal):
    l = await _liste(istemci, yonetici_basligi)
    k = await _kampanya(istemci, yonetici_basligi, l["id"])
    y = await istemci.post(f"{Y}/kampanyalar/{k['id']}/test", json={"adresler": ["test@ornek.com"]}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["sonuc"][0]["durum"] == "gonderildi"
    i = resend["tekil"][-1]
    assert i["subject"].startswith("[TEST] ") and "Mehmet KURU Dev" in i["html"]
    y = await istemci.post(f"{Y}/kampanyalar/{k['id']}/test", json={"adresler": ["a@b.com"] * 6}, headers=yonetici_basligi)
    assert y.status_code == 400
    y = await istemci.post(f"{Y}/onizleme", json={"bloklar": BLOKLAR, "konu": "Merhaba {{ad}}", "dil": "ar"}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["konu"] == "Merhaba Ayşe" and 'dir="rtl"' in y.json()["html"]
    y = await istemci.post(f"{Y}/onizleme", json={"bloklar": [{"tur": "dugme", "metin": "x", "url": "javascript:1"}]}, headers=yonetici_basligi)
    assert y.status_code == 400 and _kod(y) == "adres_gecersiz"


async def test_gorsel_yukleme(istemci, yonetici_basligi):
    import io

    from PIL import Image

    tampon = io.BytesIO()
    Image.new("RGB", (2400, 800), (120, 40, 200)).save(tampon, format="PNG")
    y = await istemci.post(f"{Y}/gorseller", files={"dosya": ("a.png", tampon.getvalue(), "image/png")}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    v = y.json()
    assert v["url"].startswith("https://mehmetkuru.dev/api/v1/bulten/gorsel/") and v["genislik"] == 1200
    anahtar = v["url"].rsplit("/", 1)[1]
    y = await istemci.get(f"{A}/gorsel/{anahtar}")
    assert y.status_code == 200 and y.headers["content-type"] == "image/jpeg" and "immutable" in y.headers["cache-control"]
    y = await istemci.post(f"{Y}/gorseller", files={"dosya": ("a.txt", b"metin", "text/plain")}, headers=yonetici_basligi)
    assert y.status_code == 400
    # Yüklenen görsel blokta kullanılabilir (sitenin kendi https adresi).
    from services import eposta_icerik as ic

    assert ic.bloklari_dogrula([{"tur": "gorsel", "url": v["url"]}])[0]["url"] == v["url"]


async def test_sahte_kutu_yalniz_test_ortaminda(istemci, yonetici_basligi, monkeypatch, yasal):
    from services import eposta_gonderim as eg

    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    assert (await istemci.get(f"{Y}/sahte-kutu", headers=yonetici_basligi)).status_code == 404
    monkeypatch.setenv("ENVIRONMENT", "test")
    assert eg.sahte_mod() and eg.resend_kurulu()
    l = await _liste(istemci, yonetici_basligi)
    f = await _form(istemci, yonetici_basligi, l["id"])
    eposta = _e("sahte")
    assert (await _abone_ol(istemci, f["genel_anahtar"], eposta)).status_code == 200
    kutu = (await istemci.get(f"{Y}/sahte-kutu?eposta={eposta}", headers=yonetici_basligi)).json()["items"]
    assert len(kutu) == 1 and "/bulten/onay/" in kutu[0]["text"]
    monkeypatch.setenv("RENDER", "srv-123")  # Render'da asla
    assert not eg.sahte_mod()


async def test_kisi_silme_kalici_bastirma_kalir(istemci, yonetici_basligi, db_oturumu):
    from models.eposta_pazarlama import EpBastirma, EpKisiler

    k = await _kisi(istemci, yonetici_basligi, izin=IZIN)
    await istemci.post(f"{Y}/kisiler/{k['id']}/ret", headers=yonetici_basligi)
    assert (await istemci.delete(f"{Y}/kisiler/{k['id']}", headers=yonetici_basligi)).status_code == 200
    assert (await db_oturumu.execute(select(EpKisiler).where(EpKisiler.id == k["id"]))).scalars().first() is None
    assert (await db_oturumu.execute(select(EpBastirma).where(EpBastirma.eposta == k["eposta"]))).scalars().first() is not None


def test_modul_ve_izin_kaydi():
    from core import moduller as mf
    from services import hesap_ekibi as he
    from services.bildirim_tercih import OLAYLAR

    m = mf.MODUL_SOZLUGU["eposta_pazarlama"]
    assert not m.varsayilan_acik and m.musteri_sekmesi == m.yonetici_sekmesi == "epostaPazarlama"
    assert {a.anahtar for a in m.ayarlar} == {"aylik_gonderim_siniri", "kisi_siniri"}
    assert "pazarlama" in he.IZINLER and "pazarlama" in he.ROL_VARSAYILAN["yonetici"]
    assert "pazarlama" not in he.ROL_VARSAYILAN["uye"] and "pazarlama" not in he.ROL_VARSAYILAN["fatura"]
    # Eski (5M öncesi) varsayılan yönetici izinleri yeni izni kendiliğinden alır.
    eski = sorted(he.ESKI_VARSAYILANLAR["yonetici"][-1])
    assert "pazarlama" in he.izinleri_coz(json.dumps(eski), "yonetici")
    assert OLAYLAR["pazarlama_askiya_alindi"]["roller"] == ("admin", "client")
    assert he.OLAY_IZNI["pazarlama_askiya_alindi"] == "pazarlama"
    from services.zamanli import GOREV_ADLARI

    assert "eposta_pazarlama" in GOREV_ADLARI and GOREV_ADLARI[-1] == "aylik_site_analizi"
