"""Faz 7H — sağlamlaştırma.

Kapsam
------
1. Otomasyon: "bekle"den sonra koşulların yeniden denetimi (yeni kuralda varsayılan açık, eski kuralda
   NULL = kapalı, müşteri modu), taze bağlam (aşama), `fatura.acik` / `fatura.vadeye_kalan_gun`, vade öncesi
   hatırlatma şablonu (yerleşik vade sonrası hatırlatmalarla çakışmıyor), sözleşme → teklif → proje görevi.
2. Kalıcı hız sınırı: sınır aşılınca 429, pencere dolunca yeniden izin, iki "örnek" (yeni sınırlayıcı nesnesi,
   yeni bağlantı) arasında sayacın kalıcılığı, veritabanı hatası / yavaşlığında belleğe düşüş (istek 500 olmuyor),
   anahtarda ham IP yok, süresi geçen sayaçların temizliği.
3. Analiz saklama süresi: 13 aydan eski ham olaylar silinirken tüm zamanlar toplamı (QR, kartvizit, kampanya
   tıklaması) değişmiyor; dönem sayıları hamdan; menü/randevu olayları yalnız siliniyor; yetim özetler.
"""

import asyncio
import json
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, func, select, update

from conftest import jeton_uret

Y = "/api/v1/otomasyon/yonetim"
M = "/api/v1/otomasyonlarim"
MODUL = "/api/v1/moduller"


def _e(on: str = "h7") -> str:
    return f"{on}-{uuid.uuid4().hex[:8]}@h7.dev"


def _b(eposta: str) -> dict:
    return {"Authorization": f"Bearer {jeton_uret(eposta)}"}


def _kod(y) -> str:
    try:
        d = y.json().get("detail")
    except Exception:  # noqa: BLE001
        return ""
    return d.get("kod", "") if isinstance(d, dict) else ""


class _Posta:
    def __init__(self):
        self.giden: list = []

    async def __call__(self, alici, baslik, govde, ek=None):
        self.giden.append({"alici": alici, "konu": baslik, "govde": govde})
        return ("sent", "test")


@pytest.fixture
async def posta(monkeypatch, db_oturumu):
    from models.otomasyon import OtomasyonCalismalari, OtomasyonKurallari
    from routers import otomasyon as r
    from services import notify, otomasyon, webhook

    r.hiz_sinirlarini_temizle()
    otomasyon.onbellegi_temizle()
    monkeypatch.setattr(otomasyon, "ANLIK_ISLEME", False)
    monkeypatch.setattr(otomasyon, "POMPA_GECIKMESI_SN", 0)
    monkeypatch.setattr(webhook, "ANLIK_TESLIMAT", False)
    p = _Posta()
    monkeypatch.setattr(notify, "_eposta_gonder", p)
    yield p
    for model in (OtomasyonCalismalari, OtomasyonKurallari):
        await db_oturumu.execute(delete(model))
    await db_oturumu.commit()
    otomasyon.onbellegi_temizle()
    r.hiz_sinirlarini_temizle()


async def _ekle(db, nesne):
    db.add(nesne)
    await db.commit()
    await db.refresh(nesne)
    return nesne


async def _kural(istemci, basliklar, yol=Y, **govde) -> dict:
    govde.setdefault("ad", "7H kuralı")
    y = await istemci.post(f"{yol}/kurallar", json=govde, headers=basliklar)
    assert y.status_code == 200, y.text
    return y.json()


async def _isle():
    from services import otomasyon

    return await otomasyon.bekleyenleri_isle()


async def _calismalar(db, kural_id):
    from models.otomasyon import OtomasyonCalismalari

    return list((await db.execute(
        select(OtomasyonCalismalari).where(OtomasyonCalismalari.kural_id == kural_id).order_by(OtomasyonCalismalari.id)
        .execution_options(populate_existing=True)
    )).scalars().all())


async def _beklemeyi_bitir(db, kural_id):
    from models.otomasyon import OtomasyonCalismalari

    await db.execute(update(OtomasyonCalismalari).where(OtomasyonCalismalari.kural_id == kural_id,
                                                        OtomasyonCalismalari.durum == "bekliyor")
                     .values(sonraki_zaman=datetime.now(timezone.utc) - timedelta(minutes=1)))
    await db.commit()


async def _fatura(db, eposta, vade_gun=7, durum="unpaid"):
    from models.invoices import Invoices
    from services.faturalar import tr_bugun

    return await _ekle(db, Invoices(invoice_no=f"F7H-{uuid.uuid4().hex[:6]}", client_email=eposta, amount=1200.0,
                                    currency="TRY", status=durum, due_date=(tr_bugun() + timedelta(days=vade_gun)).isoformat()))


HATIRLATMA = [{"tur": "bekle", "miktar": 1, "birim": "gun"},
              {"tur": "eposta", "nitelik": "bilgilendirme", "alici": "kisi", "konu": "Hatırlatma {{fatura.no}}",
               "govde": "Vade {{fatura.vade_tarihi}}, kalan {{fatura.vadeye_kalan_gun}} gün."}]
ACIK_KOSULU = {"baglac": "ve", "kosullar": [{"alan": "fatura.acik", "islec": "esittir", "deger": "true"}]}


# ---------------------------------------------------------------------------
# 1. Otomasyon — bekleme sonrası koşul denetimi
# ---------------------------------------------------------------------------
async def test_yeni_kuralda_varsayilan_acik_eski_kuralda_kapali(istemci, yonetici_basligi, db_oturumu, posta):
    from models.otomasyon import OtomasyonKurallari

    k = await _kural(istemci, yonetici_basligi, tetik="fatura.olusturuldu", kosullar=ACIK_KOSULU, eylemler=HATIRLATMA)
    assert k["bekleme_sonrasi_denetim"] is True
    y = await istemci.put(f"{Y}/kurallar/{k['id']}", json={"bekleme_sonrasi_denetim": False}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["bekleme_sonrasi_denetim"] is False
    # Kısmi güncelleme (yalnız aç/kapa) ayarı değiştirmez.
    y = await istemci.put(f"{Y}/kurallar/{k['id']}", json={"aktif": False}, headers=yonetici_basligi)
    assert y.json()["bekleme_sonrasi_denetim"] is False
    # Sütun sonradan eklendi: eski kurallarda NULL → kapalı görünür.
    await db_oturumu.execute(update(OtomasyonKurallari).where(OtomasyonKurallari.id == k["id"]).values(bekleme_sonrasi_denetim=None))
    await db_oturumu.commit()
    assert (await istemci.get(f"{Y}/kurallar/{k['id']}", headers=yonetici_basligi)).json()["bekleme_sonrasi_denetim"] is False
    # Şablondan kurulan da yeni kural: açık.
    y = await istemci.post(f"{Y}/kurallar/sablondan", json={"sablon": "fatura_vade_oncesi_hatirlatma"}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["bekleme_sonrasi_denetim"] is True


async def test_bekleme_sonrasi_kosul_artik_saglanmiyorsa_durur(istemci, yonetici_basligi, db_oturumu, posta):
    e = _e("odedi")
    k = await _kural(istemci, yonetici_basligi, tetik="fatura.olusturuldu", kosullar=ACIK_KOSULU, eylemler=HATIRLATMA)
    f = await _fatura(db_oturumu, e)
    await _isle()
    c = (await _calismalar(db_oturumu, k["id"]))[0]
    assert c.durum == "bekliyor" and c.kosul_sonucu is True
    # Bekleme sırasında fatura ödendi.
    f.status = "paid"
    await db_oturumu.commit()
    await _beklemeyi_bitir(db_oturumu, k["id"])
    await _isle()
    c = (await _calismalar(db_oturumu, k["id"]))[0]
    assert (c.durum, c.neden, c.kosul_sonucu) == ("kosul_tutmadi", "kosul_artik_saglanmiyor", False)
    assert json.loads(c.kosul_ayrinti)[0]["gercek"] is False
    assert [s["tur"] for s in json.loads(c.eylem_sonuclari)] == ["bekle"]  # e-posta adımına gelinmedi
    assert not [g for g in posta.giden if g["alici"] == e]
    # Çalıştırma günlüğünde görünür.
    y = await istemci.get(f"{Y}/gunluk", params={"kural_id": k["id"]}, headers=yonetici_basligi)
    satir = y.json()["items"][0]
    assert satir["durum"] == "kosul_tutmadi" and satir["neden"] == "kosul_artik_saglanmiyor"


async def test_bekleme_sonrasi_kosul_tutuyorsa_devam_eder_ve_taze_veri_kullanir(istemci, yonetici_basligi, db_oturumu, posta):
    e = _e("acik")
    k = await _kural(istemci, yonetici_basligi, tetik="fatura.olusturuldu", kosullar=ACIK_KOSULU, eylemler=HATIRLATMA)
    f = await _fatura(db_oturumu, e, vade_gun=7)
    await _isle()
    # "5 gün geçti": vadeye 2 gün kaldı.
    from services.faturalar import tr_bugun

    f.due_date = (tr_bugun() + timedelta(days=2)).isoformat()
    await db_oturumu.commit()
    await _beklemeyi_bitir(db_oturumu, k["id"])
    await _isle()
    c = (await _calismalar(db_oturumu, k["id"]))[0]
    assert c.durum == "tamam" and c.neden is None
    giden = [g for g in posta.giden if g["alici"] == e]
    assert len(giden) == 1 and "kalan 2 gün" in giden[0]["govde"]


async def test_eski_kuralda_davranis_degismez(istemci, yonetici_basligi, db_oturumu, posta):
    from models.otomasyon import OtomasyonKurallari

    e = _e("eski")
    k = await _kural(istemci, yonetici_basligi, tetik="fatura.olusturuldu", kosullar=ACIK_KOSULU, eylemler=HATIRLATMA)
    await db_oturumu.execute(update(OtomasyonKurallari).where(OtomasyonKurallari.id == k["id"]).values(bekleme_sonrasi_denetim=None))
    await db_oturumu.commit()
    from services import otomasyon

    otomasyon.onbellegi_temizle()
    f = await _fatura(db_oturumu, e)
    await _isle()
    f.status = "paid"
    await db_oturumu.commit()
    await _beklemeyi_bitir(db_oturumu, k["id"])
    await _isle()
    c = (await _calismalar(db_oturumu, k["id"]))[0]
    assert c.durum == "tamam"  # Faz 4W davranışı: koşul yalnız başta
    assert len([g for g in posta.giden if g["alici"] == e]) == 1


async def test_musteri_modunda_da_calisir(istemci, yonetici_basligi, db_oturumu, posta):
    e = _e("musteri")
    y = await istemci.put(f"{MODUL}/musteri/{e}/otomasyon", json={"acik": True}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    eylemler = [{"tur": "bekle", "miktar": 2, "birim": "saat"},
                {"tur": "bildirim", "alici": "hesap", "baslik": "Fatura hâlâ açık: {{fatura.no}}"}]
    k = await _kural(istemci, _b(e), M, tetik="fatura.olusturuldu", kosullar=ACIK_KOSULU, eylemler=eylemler)
    assert k["bekleme_sonrasi_denetim"] is True
    k2 = await _kural(istemci, _b(e), M, tetik="fatura.olusturuldu", kosullar=ACIK_KOSULU, eylemler=eylemler,
                      bekleme_sonrasi_denetim=False)
    assert k2["bekleme_sonrasi_denetim"] is False
    f = await _fatura(db_oturumu, e)
    await _isle()
    f.status = "cancelled"
    await db_oturumu.commit()
    for kid in (k["id"], k2["id"]):
        await _beklemeyi_bitir(db_oturumu, kid)
    await _isle()
    assert [(c.durum, c.neden) for c in await _calismalar(db_oturumu, k["id"])] == [("kosul_tutmadi", "kosul_artik_saglanmiyor")]
    assert [c.durum for c in await _calismalar(db_oturumu, k2["id"])] == ["tamam"]
    y = await istemci.get(f"{M}/gunluk", params={"kural_id": k["id"]}, headers=_b(e))
    assert y.json()["items"][0]["neden"] == "kosul_artik_saglanmiyor"


async def test_taze_baglam_guncel_asamayi_okur(db_oturumu):
    from models.projects import Projects
    from services import otomasyon

    p = await _ekle(db_oturumu, Projects(title="Taze", description="d", category="Web", client_email=_e("p"),
                                         published=False, status="in_progress", stage="build", progress=10))
    veri = {"proje_id": p.id, "asama": "design", "onceki_asama": "discovery"}
    olay_ani = await otomasyon.baglam_kur(db_oturumu, "proje.asama_degisti", veri, None, True)
    taze = await otomasyon.baglam_kur(db_oturumu, "proje.asama_degisti", veri, None, True, taze=True)
    assert olay_ani["proje"]["asama"] == "design" and taze["proje"]["asama"] == "build"
    assert taze["_onceki"] == {"proje.asama": "discovery"}


async def test_fatura_baglami_acik_ve_vadeye_kalan(db_oturumu):
    from services import otomasyon

    e = _e("baglam")
    for durum, beklenen in (("unpaid", True), ("overdue", True), ("kismi_odendi", True), ("paid", False),
                            ("cancelled", False), ("iptal", False), ("iade", False)):
        f = await _fatura(db_oturumu, e, vade_gun=-3, durum=durum)
        b = await otomasyon.baglam_kur(db_oturumu, "fatura.olusturuldu", {"fatura_id": f.id}, e, True)
        assert b["fatura"]["acik"] is beklenen, durum
        assert b["fatura"]["vadeye_kalan_gun"] == -3


async def test_vade_oncesi_hatirlatma_sablonu_cift_eposta_yaratmaz(istemci, yonetici_basligi, db_oturumu, posta):
    from services import otomasyon_kural as kk
    from services.faturalar import VADE_ESIKLERI, tr_bugun

    s = kk.SABLON_SOZLUGU["fatura_vade_oncesi_hatirlatma"]
    assert s.yalniz_ajans and [e["tur"] for e in s.eylemler] == ["bekle", "eposta"]
    assert min(VADE_ESIKLERI) >= 1  # yerleşikler vadeden SONRA; bu şablon vadeye ≥2 gün kala
    assert kk.kosullari_degerlendir(s.kosullar, kk.ornek_baglam("fatura.olusturuldu", True))[0] is True
    y = await istemci.post(f"{Y}/kurallar/sablondan", json={"sablon": "fatura_vade_oncesi_hatirlatma"}, headers=yonetici_basligi)
    k = y.json()
    uzun, kisa, odenen = _e("uzun"), _e("kisa"), _e("odenen")
    f_uzun = await _fatura(db_oturumu, uzun, vade_gun=7)
    f_kisa = await _fatura(db_oturumu, kisa, vade_gun=3)
    f_odenen = await _fatura(db_oturumu, odenen, vade_gun=7)
    await _fatura(db_oturumu, _e("vadesiz"), vade_gun=1)  # başta bile tutmaz (vadeye 1 gün)
    await _isle()
    durumlar = sorted(c.durum for c in await _calismalar(db_oturumu, k["id"]))
    assert durumlar == ["bekliyor", "bekliyor", "bekliyor", "kosul_tutmadi"]
    # 5 gün sonrası: uzun vadede 2 gün kaldı (gider); kısa vadenin vadesi 2 gün GEÇTİ (yerleşikler devralır,
    # bu şablon göndermez); ödenen fatura hiç gönderilmez.
    f_uzun.due_date = (tr_bugun() + timedelta(days=2)).isoformat()
    f_kisa.due_date = (tr_bugun() - timedelta(days=2)).isoformat()
    f_odenen.due_date = (tr_bugun() + timedelta(days=2)).isoformat()
    f_odenen.status = "paid"
    await db_oturumu.commit()
    await _beklemeyi_bitir(db_oturumu, k["id"])
    await _isle()
    alicilar = [g["alici"] for g in posta.giden]
    assert alicilar.count(uzun) == 1 and kisa not in alicilar and odenen not in alicilar
    giden = next(g for g in posta.giden if g["alici"] == uzun)
    assert f_uzun.invoice_no in giden["konu"] and f_uzun.due_date in giden["konu"]
    sonuc = {json.loads(c.veri)["fatura_id"]: (c.durum, c.neden) for c in await _calismalar(db_oturumu, k["id"])}
    assert sonuc[f_kisa.id] == ("kosul_tutmadi", "kosul_artik_saglanmiyor")
    assert sonuc[f_odenen.id] == ("kosul_tutmadi", "kosul_artik_saglanmiyor")
    assert sonuc[f_uzun.id] == ("tamam", None)


async def _teklif_sozlesme(db, eposta, proje_id):
    from models.sozlesmeler import Sozlesmeler
    from models.teklifler import Teklifler

    t = await _ekle(db, Teklifler(no=f"T7H-{uuid.uuid4().hex[:6]}", baslik="Teklif", ara_toplam=1, indirim_toplam=0,
                                   kdv_toplam=0, genel_toplam=1, para_birimi="TRY", durum="kabul", goruntulenme_sayisi=0,
                                   otomatik_sozlesme=False, otomatik_fatura=False, otomatik_proje=False, surum=1,
                                   hesap_email=eposta, proje_id=proje_id))
    s = await _ekle(db, Sozlesmeler(no=f"S7H-{uuid.uuid4().hex[:6]}", surum=1, baslik="Web sitesi sözleşmesi", govde="g",
                                     dil="tr", durum="gonderildi", hesap_email=eposta, teklif_id=t.id))
    return t, s


async def test_sozlesme_imzalaninca_teklifin_projesine_gorev(istemci, yonetici_basligi, db_oturumu, posta):
    from models.proje_gorevleri import ProjectTasks
    from models.projects import Projects

    y = await istemci.post(f"{Y}/kurallar/sablondan", json={"sablon": "sozlesme_imzalandi_bildirim"}, headers=yonetici_basligi)
    k = y.json()
    e = _e("szl")
    p = await _ekle(db_oturumu, Projects(title="Sözleşmeli proje", description="d", category="Web", client_email=e,
                                         published=False, status="planning", stage="discovery", progress=0))
    _, s = await _teklif_sozlesme(db_oturumu, e, p.id)
    _, s2 = await _teklif_sozlesme(db_oturumu, e, None)  # teklifinden proje açılmamış
    for x in (s, s2):
        x.durum = "imzalandi"
    await db_oturumu.commit()
    await _isle()
    sonuc = {json.loads(c.veri)["sozlesme_id"]: c for c in await _calismalar(db_oturumu, k["id"])}
    eylem = [(r["tur"], r["durum"], r.get("neden")) for r in json.loads(sonuc[s.id].eylem_sonuclari)]
    assert eylem == [("bildirim", "basarili", None), ("gorev", "basarili", None)]
    gorev = (await db_oturumu.execute(select(ProjectTasks).where(ProjectTasks.proje_id == p.id))).scalars().all()
    assert [g.baslik for g in gorev] == ["Belge ve erişimleri iste: Web sitesi sözleşmesi"]
    eylem2 = [(r["tur"], r["durum"], r.get("neden")) for r in json.loads(sonuc[s2.id].eylem_sonuclari)]
    assert eylem2 == [("bildirim", "basarili", None), ("gorev", "atlandi", "proje_yok")]
    assert sonuc[s2.id].durum == "tamam"


async def test_sozlesme_olayinda_musteri_baskasinin_projesini_goremez(db_oturumu):
    from models.projects import Projects
    from services import otomasyon

    a, b = _e("a"), _e("b")
    pb = await _ekle(db_oturumu, Projects(title="B", description="d", category="Web", client_email=b, published=False,
                                          status="planning", stage="discovery", progress=0))
    _, s = await _teklif_sozlesme(db_oturumu, a, pb.id)
    musteri = await otomasyon.baglam_kur(db_oturumu, "sozlesme.imzalandi", {"sozlesme_id": s.id}, a, False)
    assert "proje" not in musteri
    ajans = await otomasyon.baglam_kur(db_oturumu, "sozlesme.imzalandi", {"sozlesme_id": s.id}, a, True)
    assert ajans["proje"]["id"] == pb.id


# ---------------------------------------------------------------------------
# 2. Kalıcı hız sınırı
# ---------------------------------------------------------------------------
@pytest.fixture
def iletisim_sifir():
    from routers import fiyatlandirma, inquiries

    inquiries.hiz_sinirlarini_temizle()
    fiyatlandirma.hiz_sinirlarini_temizle()
    yield
    inquiries.hiz_sinirlarini_temizle()
    fiyatlandirma.hiz_sinirlarini_temizle()


def _iletisim(i: int) -> dict:
    return {"name": "Ziyaretçi", "email": f"z{i}-{uuid.uuid4().hex[:6]}@ornek.com", "message": "Merhaba", "status": "new"}


async def test_iletisim_formu_sinir_asilinca_429_pencere_dolunca_izin(istemci, yonetici_basligi, monkeypatch, iletisim_sifir):
    from utils import hiz_siniri

    ip = {"X-MK-Istemci-IP": "198.51.100.71"}
    durumlar = [(await istemci.post("/api/v1/entities/inquiries", json=_iletisim(i), headers=ip)).status_code for i in range(6)]
    assert durumlar == [201] * 5 + [429]
    y = await istemci.post("/api/v1/entities/inquiries", json=_iletisim(9), headers=ip)
    assert y.status_code == 429 and _kod(y) == "cok_hizli"
    # Başka IP etkilenmez; yönetici muaf.
    assert (await istemci.post("/api/v1/entities/inquiries", json=_iletisim(10), headers={"X-MK-Istemci-IP": "198.51.100.72"})).status_code == 201
    assert (await istemci.post("/api/v1/entities/inquiries", json=_iletisim(11), headers={**ip, **yonetici_basligi})).status_code == 201
    # 10 dakikalık pencere dolunca yeniden izin.
    gercek = hiz_siniri.simdi_ms
    monkeypatch.setattr(hiz_siniri, "simdi_ms", lambda: gercek() + 601_000)
    assert (await istemci.post("/api/v1/entities/inquiries", json=_iletisim(12), headers=ip)).status_code == 201
    assert hiz_siniri.yedek_sayisi() == 0


async def test_fiyat_teklifi_ve_satin_al_ortak_sinir(istemci, iletisim_sifir):
    ip = {"X-MK-Istemci-IP": "198.51.100.81"}
    for i in range(10):
        y = await istemci.post("/api/v1/fiyat-teklif", json={"kredi_paketi": 10, "musteri_eposta": _e(f"f{i}"),
                                                             "musteri_adi": "Can"}, headers=ip)
        assert y.status_code == 200, y.text
    y = await istemci.post("/api/v1/fiyat-satin-al", json={"kredi_paketi": 10, "musteri_eposta": _e("son"), "musteri_adi": "Can"},
                           headers=ip)
    assert y.status_code == 429 and _kod(y) == "cok_hizli"


async def test_sayac_ornekler_arasinda_kalici(uygulama):
    """Sunucu uyuyup kalkınca süreç belleği sıfırlanır: aynı adlı yeni sınırlayıcı nesnesi + yeni bağlantılar
    (motor havuzu boşaltılıyor) sayaca kaldığı yerden devam eder; bellek içi sınırlayıcı sıfırdan başlardı."""
    from core.database import db_manager
    from utils.hiz_siniri import HizSiniri, KaliciHizSiniri, izin_ver

    ad = f"deneme-{uuid.uuid4().hex[:6]}"
    birinci = KaliciHizSiniri(ad, 3, 60.0)
    assert [await izin_ver((birinci, "anahtar")) for _ in range(2)] == [True, True]
    await db_manager.engine.dispose()
    ikinci = KaliciHizSiniri(ad, 3, 60.0)  # yeni "örnek": belleği boş
    assert [await izin_ver((ikinci, "anahtar")) for _ in range(2)] == [True, False]
    bellek = HizSiniri(3, 60.0)
    assert bellek.izin_var_mi("anahtar")  # karşılaştırma: bellek içi sayaç sıfırdan başlar
    # Başka sınırlayıcı adı ayrı sayılır.
    assert await izin_ver((KaliciHizSiniri(ad + "-b", 3, 60.0), "anahtar")) is True


async def test_veritabani_hatasinda_bellege_duser(istemci, monkeypatch, iletisim_sifir):
    from utils import hiz_siniri

    async def _bozuk(*a, **k):
        raise RuntimeError("veritabanı yok")

    monkeypatch.setattr(hiz_siniri, "_veritabaninda", _bozuk)
    once = hiz_siniri.yedek_sayisi()
    s = hiz_siniri.KaliciHizSiniri(f"bozuk-{uuid.uuid4().hex[:6]}", 2, 60.0)
    assert [await hiz_siniri.izin_ver((s, "x")) for _ in range(3)] == [True, True, False]
    assert hiz_siniri.yedek_sayisi() == once + 3
    # Uçta: istek 500 olmuyor, sınır bellekte uygulanıyor.
    ip = {"X-MK-Istemci-IP": "198.51.100.91"}
    durumlar = [(await istemci.post("/api/v1/entities/inquiries", json=_iletisim(i), headers=ip)).status_code for i in range(6)]
    assert durumlar == [201] * 5 + [429]


async def test_veritabani_yavassa_zaman_asimiyla_bellege_duser(monkeypatch):
    from utils import hiz_siniri

    async def _yavas(*a, **k):
        await asyncio.sleep(5)
        return True

    monkeypatch.setattr(hiz_siniri, "_veritabaninda", _yavas)
    monkeypatch.setattr(hiz_siniri, "ZAMAN_ASIMI_SN", 0.05)
    s = hiz_siniri.KaliciHizSiniri(f"yavas-{uuid.uuid4().hex[:6]}", 1, 60.0)
    basla = asyncio.get_running_loop().time()
    assert await hiz_siniri.izin_ver((s, "x")) is True
    assert await hiz_siniri.izin_ver((s, "x")) is False
    assert asyncio.get_running_loop().time() - basla < 2


async def test_bellek_ici_sinirlayici_karisik_verilebilir(uygulama):
    """Testler sınırlayıcıyı bellek içiyle değiştirebiliyor; sırayla denetlenir, ilk reddeden durdurur."""
    from utils.hiz_siniri import HizSiniri, KaliciHizSiniri, izin_ver

    bellek = HizSiniri(1, 60.0)
    kalici = KaliciHizSiniri(f"karisik-{uuid.uuid4().hex[:6]}", 5, 60.0)
    assert await izin_ver((bellek, "a"), (kalici, "a")) is True
    assert await izin_ver((bellek, "a"), (kalici, "a")) is False  # bellek reddetti; kalıcı sayılmadı
    assert [await izin_ver((kalici, "a")) for _ in range(4)] == [True, True, True, True]
    assert await izin_ver((kalici, "a")) is False


async def test_anahtarda_ham_ip_yok_ve_suresi_gecenler_silinir(istemci, db_oturumu, iletisim_sifir):
    from models.hiz_sayaclari import HizSayaclari
    from utils import hiz_siniri

    ip = "203.0.113.177"
    assert (await istemci.post("/api/v1/entities/inquiries", json=_iletisim(1), headers={"X-MK-Istemci-IP": ip})).status_code == 201
    satirlar = (await db_oturumu.execute(select(HizSayaclari))).scalars().all()
    assert satirlar and all(len(s.anahtar) == 64 and ip not in s.anahtar for s in satirlar)
    eski = hiz_siniri.simdi_ms() - 3 * 86400_000
    db_oturumu.add(HizSayaclari(anahtar="e" * 64, pencere_bas=eski - 60_000, bitis=eski, sayac=3))
    await db_oturumu.commit()
    silinen = await hiz_siniri.suresi_gecenleri_sil(db_oturumu)
    assert silinen >= 1
    kalan = {s.anahtar for s in (await db_oturumu.execute(select(HizSayaclari))).scalars().all()}
    assert "e" * 64 not in kalan and kalan  # süren pencereler duruyor


# ---------------------------------------------------------------------------
# 3. Analiz saklama süresi
# ---------------------------------------------------------------------------
def _gun(once: int) -> str:
    return (datetime.now(timezone.utc).date() - timedelta(days=once)).isoformat()


def _an(gun: str) -> datetime:
    return datetime.fromisoformat(gun + "T10:00:00+00:00")


async def test_qr_eski_taramalar_ozete_iner_toplamlar_degismez(istemci, yonetici_basligi, db_oturumu):
    from models.dinamik_qr import DinamikQrTaramalari as T
    from models.hiz_sayaclari import AnalizGunlukOzetleri as O
    from services import analiz_saklama

    y = await istemci.post("/api/v1/dinamik-qr/yonetim", json={"ad": "7H", "tur": "url", "alanlar": {"url": "https://a.com"}},
                           headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    qr = y.json()
    eski1, eski2, yeni = _gun(420), _gun(400), _gun(10)

    def tarama(gun, ip, bot=False, qr_id=qr["id"]):
        return T(qr_id=qr_id, zaman=_an(gun), gun=gun, ulke="TR", cihaz="mobil", isletim="ios", ip_ozeti=ip, bot=bot)

    db_oturumu.add_all([tarama(eski1, "a"), tarama(eski1, "a"), tarama(eski1, "b"), tarama(eski1, "x", bot=True),
                        tarama(eski2, "c"), tarama(yeni, "d"), tarama(yeni, "d"), tarama(yeni, "y", bot=True),
                        tarama(eski1, "z", qr_id=987654)])  # kaydı olmayan QR (yetim)
    await db_oturumu.commit()

    async def analiz():
        return (await istemci.get(f"/api/v1/dinamik-qr/yonetim/{qr['id']}/analiz", params={"gun": 365},
                                  headers=yonetici_basligi)).json()

    once = await analiz()
    assert (once["toplam"], once["tekil"], once["bot"]) == (6, 4, 2)
    sonuc = await analiz_saklama.saklama_temizligi(db_oturumu)
    assert sonuc["qr"]["silinen"] == 6 and sonuc["silinen"] >= 6
    sonra = await analiz()
    assert (sonra["toplam"], sonra["tekil"], sonra["bot"]) == (6, 4, 2)
    assert sonra["donem"] == once["donem"] and sonra["gunluk"] == once["gunluk"]
    kalan = (await db_oturumu.execute(select(func.count(T.id)).where(T.gun < analiz_saklama.kesim_gunu().isoformat()))).scalar()
    assert kalan == 0
    ozetler = (await db_oturumu.execute(select(O).where(O.kaynak == "qr"))).scalars().all()
    assert {o.nesne_id for o in ozetler} == {qr["id"]}  # yetim QR'ın özeti yazılmadı
    # İkinci çalıştırma bir şey değiştirmez (idempotent).
    await analiz_saklama.saklama_temizligi(db_oturumu)
    assert (await analiz())["toplam"] == 6


async def test_kartvizit_eski_olaylar_ozete_iner_toplamlar_degismez(istemci, yonetici_basligi, db_oturumu):
    from models.kartvizit import KartvizitOlaylari as T
    from services import analiz_saklama

    from test_kartvizit import _icerik

    y = await istemci.post("/api/v1/kartvizit/yonetim", json={"icerik": _icerik()}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    kart = y.json()
    eski, yeni = _gun(500), _gun(3)

    def olay(gun, tur, ip, kanal=None, bot=False, hedef=None):
        return T(sahip_tur="kart", sahip_id=kart["id"], olay=tur, hedef=hedef, kanal=kanal, zaman=_an(gun), gun=gun,
                 ip_ozeti=ip, cihaz="mobil", bot=bot)

    db_oturumu.add_all([olay(eski, "goruntulenme", "a", kanal="qr"), olay(eski, "goruntulenme", "a"),
                        olay(eski, "goruntulenme", "b"), olay(eski, "tik", "a", hedef="wa"), olay(eski, "rehber", "b"),
                        olay(eski, "goruntulenme", "bot", bot=True),
                        olay(yeni, "goruntulenme", "c", kanal="qr"), olay(yeni, "tik", "c", hedef="wa")])
    await db_oturumu.commit()

    async def analiz():
        return (await istemci.get(f"/api/v1/kartvizit/yonetim/{kart['id']}/analiz", params={"gun": 30},
                                  headers=yonetici_basligi)).json()

    once = await analiz()
    await analiz_saklama.saklama_temizligi(db_oturumu)
    sonra = await analiz()
    for alan in ("toplam", "tekil", "qr", "bot", "donem", "gunluk", "hedefler"):
        assert sonra[alan] == once[alan], alan
    assert once["toplam"]["goruntulenme"] == 4 and once["tekil"] == 3 and once["qr"] == 2 and once["bot"] == 1
    assert (await db_oturumu.execute(select(func.count(T.id)).where(T.sahip_id == kart["id"]))).scalar() == 2


async def test_kampanya_tiklamalari_ozete_iner_rapor_degismez(db_oturumu):
    from models.eposta_pazarlama import EpKampanyalar, EpTiklamalar
    from routers.eposta_pazarlama import _rapor
    from services import analiz_saklama

    k = await _ekle(db_oturumu, EpKampanyalar(ad="7H kampanyası", dil="tr", durum="tamamlandi", takip_acilma=True,
                                               takip_tiklama=True, hedef_sayisi=0,
                                               baglantilar=json.dumps(["https://a.com", "https://b.com"])))
    eski, yeni = _an(_gun(450)), _an(_gun(5))
    db_oturumu.add_all([EpTiklamalar(kampanya_id=k.id, gonderim_id=1, indeks=0, zaman=eski),
                        EpTiklamalar(kampanya_id=k.id, gonderim_id=2, indeks=0, zaman=eski),
                        EpTiklamalar(kampanya_id=k.id, gonderim_id=2, indeks=1, zaman=eski),
                        EpTiklamalar(kampanya_id=k.id, gonderim_id=3, indeks=0, zaman=yeni),
                        EpTiklamalar(kampanya_id=None, gonderim_id=4, indeks=0, zaman=eski)])
    await db_oturumu.commit()
    once = (await _rapor(db_oturumu, k))["baglantilar"]
    sonuc = await analiz_saklama.saklama_temizligi(db_oturumu)
    assert sonuc["eposta_tiklama"]["silinen"] == 4
    sonra = (await _rapor(db_oturumu, k))["baglantilar"]
    assert sonra == once and [b["tiklama"] for b in sonra] == [3, 1]


async def test_menu_ve_randevu_olaylari_yalniz_silinir(db_oturumu):
    from models.hiz_sayaclari import AnalizGunlukOzetleri as O
    from models.qr_menu import MenuOlaylari
    from models.randevu import RandevuOlaylari
    from services import analiz_saklama

    eski, yeni = _gun(400), _gun(364)  # dönem en çok 365 gün: 364 gün önce hâlâ dönemde
    db_oturumu.add_all([MenuOlaylari(magaza_id=777001, tur="goruntuleme", zaman=_an(eski), gun=eski, ip_ozeti="a", bot=False),
                        MenuOlaylari(magaza_id=777001, tur="goruntuleme", zaman=_an(yeni), gun=yeni, ip_ozeti="a", bot=False),
                        RandevuOlaylari(sayfa_id=777001, tur="sayfa", zaman=_an(eski), gun=eski, ip_ozeti="a", bot=False),
                        RandevuOlaylari(sayfa_id=777001, tur="sayfa", zaman=_an(yeni), gun=yeni, ip_ozeti="a", bot=False)])
    await db_oturumu.commit()
    await analiz_saklama.saklama_temizligi(db_oturumu)
    assert [r.gun for r in (await db_oturumu.execute(select(MenuOlaylari).where(MenuOlaylari.magaza_id == 777001))).scalars()] == [yeni]
    assert [r.gun for r in (await db_oturumu.execute(select(RandevuOlaylari).where(RandevuOlaylari.sayfa_id == 777001))).scalars()] == [yeni]
    assert (await db_oturumu.execute(select(func.count(O.id)).where(O.nesne_id == 777001))).scalar() == 0


async def test_saklama_suresi_panel_donemini_kapsar():
    from services import analiz_saklama

    # Panellerin dönem seçimi en çok 365 gün (Query le=365); saklama bundan uzun olmalı.
    assert analiz_saklama.SAKLAMA_GUN > 365 and analiz_saklama.SAKLAMA_AY == 13


async def test_zamanli_gorevde_ve_sistem_listesinde(istemci, yonetici_basligi):
    from services.zamanli import GOREV_ADLARI

    assert "saklama_temizligi" in GOREV_ADLARI
    y = await istemci.post("/api/v1/zamanli/yonetim/calistir", headers=yonetici_basligi)
    assert y.status_code == 200
    gorev = next(g for g in y.json()["gorevler"] if g["gorev"] == "saklama_temizligi")
    assert gorev["son_calisma"] and gorev["hata"] is None and "kesim" in (gorev["sonuc"] or {}), gorev
    durum = (await istemci.get("/api/v1/zamanli/yonetim", headers=yonetici_basligi)).json()
    assert any(g["gorev"] == "saklama_temizligi" and g["siklik_dk"] == 1200 for g in durum["gorevler"])
