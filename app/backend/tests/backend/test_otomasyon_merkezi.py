"""Faz 7O — otomasyon merkezi: yeni zamanlı tetikleyiciler, hazır şablonlar, haftalık özet.

Kapsam: `teklif.yanitsiz` ve `aday.hareketsiz` üreticilerinin eşik / tek sefer / sıfırlanma davranışı
(zaman verilerek), kapalı-kabul edilmiş teklif ve kazanılmış-kaybedilmiş adayın olay üretmemesi,
şablonların (7 dildeki metinleriyle) kural doğrulamasından geçmesi, proje şablonunun gerçek aşama
anahtarıyla eşleşmesi, şablonların uçtan uca çalışması, haftalık özet (Pazartesi penceresi, hafta
başına bir kez, boşsa gönderilmez, matris kapalıysa gönderilmez, önizleme yalnız yönetici), zamanlı
iş listesinde yeni iş.
"""

import json
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select, update

from conftest import jeton_uret

Y = "/api/v1/otomasyon/yonetim"
UTC = timezone.utc
I18N = Path(__file__).resolve().parents[3] / "frontend" / "src" / "i18n" / "ek" / "otomasyon"
DILLER = ("tr", "en", "de", "ru", "zh", "hi", "ar")


def _e(on: str = "om") -> str:
    return f"{on}-{uuid.uuid4().hex[:8]}@om.dev"


def _b(eposta: str, rol: str = "user") -> dict:
    return {"Authorization": f"Bearer {jeton_uret(eposta, rol)}"}


class _Posta:
    def __init__(self):
        self.giden: list = []

    async def __call__(self, alici, baslik, govde, ek=None):
        self.giden.append({"alici": alici, "konu": baslik, "govde": govde, "ek": ek or {}})
        return ("sent", "test")


@pytest.fixture(autouse=True)
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


async def _sablondan(istemci, yb, anahtar: str) -> dict:
    y = await istemci.post(f"{Y}/kurallar/sablondan", json={"sablon": anahtar}, headers=yb)
    assert y.status_code == 200, y.text
    return y.json()


async def _calismalar(db, kural_id):
    from models.otomasyon import OtomasyonCalismalari

    return list((await db.execute(
        select(OtomasyonCalismalari).where(OtomasyonCalismalari.kural_id == kural_id)
        .order_by(OtomasyonCalismalari.id).execution_options(populate_existing=True)
    )).scalars().all())


async def _kimlikler(db, kural_id, onek: str) -> list:
    """Bu kuralın, verilen önekle başlayan olay kimlikleri (diğer test dosyalarının kayıtları karışmasın)."""
    return [c.olay_id for c in await _calismalar(db, kural_id) if c.olay_id.startswith(onek)]


async def _isle():
    from services import otomasyon

    return await otomasyon.bekleyenleri_isle()


async def _teklif(db, *, durum="gonderildi", gonderildi=None, hesap=None, aday_eposta=None, gecerlilik=None, goruntulenme=0):
    from models.teklifler import Teklifler

    return await _ekle(db, Teklifler(
        no=f"TKL-T-{uuid.uuid4().hex[:6]}", baslik="Kurumsal site", durum=durum, gonderildi_at=gonderildi,
        hesap_email=hesap, aday_ad="Ayşe", aday_eposta=aday_eposta, genel_toplam=48000, para_birimi="TRY",
        gecerlilik=gecerlilik, goruntulenme_sayisi=goruntulenme,
    ))


# ---------------------------------------------------------------------------
# Katalog, örnek bağlam, şablonlar
# ---------------------------------------------------------------------------
def test_katalogda_yeni_olaylar_ve_alanlar():
    from services import otomasyon_kural as k

    ajans = {o["anahtar"]: o for o in k.olay_katalogu(True)}
    musteri = {o["anahtar"] for o in k.olay_katalogu(False)}
    assert "teklif.yanitsiz" in ajans and "aday.hareketsiz" in ajans
    assert "teklif.yanitsiz" not in musteri and "aday.hareketsiz" not in musteri
    yollar = {a["yol"] for a in k.sema("teklif.yanitsiz", True)}
    assert {"teklif.yanitsiz_gun", "teklif.goruntulendi", "teklif.baglanti", "teklif.no", "teklif.aday_eposta"} <= yollar
    assert {"aday.hareketsiz_gun", "aday.son_hareket", "aday.sonraki_adim"} <= {a["yol"] for a in k.sema("aday.hareketsiz", True)}
    assert "icerik.yoneten" in {a["yol"] for a in k.sema("icerik.onaylandi", True)}
    # Webhook kataloğunda yok (yalnız otomasyon; durum değişikliği değil).
    from services import webhook

    assert "teklif.yanitsiz" not in webhook.OLAY_SOZLUGU and "aday.hareketsiz" not in webhook.OLAY_SOZLUGU


async def test_ornek_baglam_butun_olaylar_ve_icerik_duzeltmesi(istemci, yonetici_basligi):
    from services import otomasyon_kural as k

    for o in k.OLAYLAR:
        k.ornek_baglam(o.anahtar, True)
    # Önceden ORNEK'te "icerik" yoktu: içerik olaylarında "Test et" 500 veriyordu.
    y = await istemci.get(f"{Y}/ornek-baglam", params={"tetik": "icerik.onaylandi"}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["baglam"]["icerik"]["yoneten"] == "ajans"
    b = k.ornek_baglam("proje.asama_degisti", True)
    from routers.project_events import STAGES

    assert b["proje"]["asama"] in STAGES and b["_onceki"]["proje.asama"] in STAGES
    assert k.ORNEK["proje"]["asama"] in STAGES


def test_proje_sablonu_gercek_asama_anahtariyla():
    from routers.project_events import STAGES
    from services.otomasyon_kural import SABLON_SOZLUGU, kosullari_degerlendir, ornek_baglam

    s = SABLON_SOZLUGU["proje_yayinda_geri_bildirim"]
    deger = s.kosullar["kosullar"][0]["deger"]
    assert deger == "launch" and deger in STAGES
    assert kosullari_degerlendir(s.kosullar, ornek_baglam("proje.asama_degisti", True))[0] is True
    # Gönderilen e-posta memnuniyete göre değişmiyor (review gating yok): koşulda puan/memnuniyet yok,
    # tek e-posta eylemi.
    assert [e["tur"] for e in s.eylemler] == ["eposta"]
    assert all(not str(kk.get("alan", "")).endswith(("puan", "memnuniyet")) for kk in s.kosullar["kosullar"])


def _metinler(dil: str, anahtar: str) -> dict:
    veri = json.loads((I18N / f"{dil}.json").read_text(encoding="utf-8"))["otomasyon"]["sablon"][anahtar]
    return {k: re.sub(r"\[\[([^\]]+)\]\]", r"{{\1}}", v) for k, v in veri.items() if k != "aciklama"}


@pytest.mark.parametrize("dil", DILLER)
def test_butun_sablonlar_ceviri_metinleriyle_dogrulamadan_gecer(dil):
    """Panel şablonu kullanıcının dilindeki metinlerle kuruyor: her dilin yer tutucuları şemada olmalı."""
    from services import otomasyon_kural as k

    for s in k.SABLONLAR:
        metinler = _metinler(dil, s.anahtar)
        assert set(s.metinler) <= set(metinler), (dil, s.anahtar, set(s.metinler) - set(metinler))
        taslak = k.sablondan_kural(s.anahtar, True, metinler)
        temiz = k.kural_dogrula(taslak, k.DogrulamaBaglami(ajans=True))
        assert temiz["tetik"] == s.tetik
        if not s.yalniz_ajans:
            k.kural_dogrula(k.sablondan_kural(s.anahtar, False, metinler), k.DogrulamaBaglami(ajans=False))


async def test_yeni_sablonlar_ajansta_kurulur_musteride_yok(istemci, yonetici_basligi):
    yeni = ("teklif_yanitsiz_hatirlatma", "aday_hareketsiz_hatirlatma", "proje_yayinda_geri_bildirim",
            "sozlesme_imzalandi_bildirim", "icerik_onaylandi_gorev")
    meta = (await istemci.get(f"{Y}/meta", headers=yonetici_basligi)).json()
    assert set(yeni) <= {s["anahtar"] for s in meta["sablonlar"]}
    assert {"teklif.yanitsiz", "aday.hareketsiz"} <= {o["anahtar"] for o in meta["olaylar"]}
    for a in yeni:
        k = await _sablondan(istemci, yonetici_basligi, a)
        assert k["aktif"] and k["sablon"] == a
    fatura = await _sablondan(istemci, yonetici_basligi, "fatura_gecikti_hatirlatma")
    assert fatura["kosullar"]["kosullar"][0] == {"alan": "fatura.gecikme_gun", "islec": "esittir", "deger": "30"}
    assert [e["tur"] for e in fatura["eylemler"]] == ["bildirim", "crm_aktivite"]  # müşteriye e-posta YOK
    assert fatura["eylemler"][0]["alici"] == "yoneticiler"


async def test_sorumlu_yonetici_alicisi_dogrulama(istemci, yonetici_basligi):
    govde = {"ad": "x", "tetik": "aday.olusturuldu",
             "eylemler": [{"tur": "bildirim", "alici": "sorumlu_yonetici", "baslik": "Yeni: {{aday.ad}}"}]}
    assert (await istemci.post(f"{Y}/kurallar", json=govde, headers=yonetici_basligi)).status_code == 200


# ---------------------------------------------------------------------------
# teklif.yanitsiz
# ---------------------------------------------------------------------------
async def test_teklif_yanitsiz_esik_tek_sefer_ve_yeniden_gonderim(istemci, yonetici_basligi, db_oturumu):
    from services import otomasyon

    an = datetime.now(UTC).replace(microsecond=0)
    gonderim = an - timedelta(days=3, hours=1)
    # Kural yokken hiç üretmez (sorgu bile yok).
    t = await _teklif(db_oturumu, gonderildi=gonderim, aday_eposta="ayse@musteri.dev")
    assert (await otomasyon.teklif_yanitsizlarini_uret(db_oturumu, an)) == {"uretilen": 0}

    k = await _sablondan(istemci, yonetici_basligi, "teklif_yanitsiz_hatirlatma")
    kabul = await _teklif(db_oturumu, durum="kabul", gonderildi=gonderim, aday_eposta="k@musteri.dev")
    ret = await _teklif(db_oturumu, durum="ret", gonderildi=gonderim, aday_eposta="r@musteri.dev")
    dolmus = await _teklif(db_oturumu, gonderildi=gonderim, aday_eposta="d@musteri.dev",
                           gecerlilik=(date.today() - timedelta(days=2)).isoformat())
    taslak = await _teklif(db_oturumu, durum="taslak", gonderildi=None, aday_eposta="t@musteri.dev")
    yeni = await _teklif(db_oturumu, gonderildi=an - timedelta(days=2, hours=23), aday_eposta="y@musteri.dev")

    s1 = await otomasyon.teklif_yanitsizlarini_uret(db_oturumu, an)
    await otomasyon.teklif_yanitsizlarini_uret(db_oturumu, an + timedelta(minutes=10))  # ikinci tur
    assert s1["uretilen"] >= 1
    onek = f"tyanitsiz-{t.id}-"
    assert await _kimlikler(db_oturumu, k["id"], onek) == [f"tyanitsiz-{t.id}-{int(gonderim.timestamp())}-3"]
    satirlar = await _calismalar(db_oturumu, k["id"])
    kimlikler = [c.olay_id for c in satirlar]
    for x in (kabul, ret, dolmus, taslak, yeni):
        assert not any(i.startswith(f"tyanitsiz-{x.id}-") for i in kimlikler), x.durum
    veri = json.loads(next(c.veri for c in satirlar if c.olay_id.startswith(f"tyanitsiz-{t.id}-")))
    assert veri["gun"] == 3 and veri["no"] == t.no and veri["goruntulendi"] is False and veri["baglanti"] is None

    # 7. gün: ikinci eşik bir kez; aradaki günlerde bir şey yok.
    await otomasyon.teklif_yanitsizlarini_uret(db_oturumu, an + timedelta(days=2))
    assert len(await _kimlikler(db_oturumu, k["id"], onek)) == 1
    await otomasyon.teklif_yanitsizlarini_uret(db_oturumu, an + timedelta(days=4))
    await otomasyon.teklif_yanitsizlarini_uret(db_oturumu, an + timedelta(days=4, hours=1))
    kimlikler = await _kimlikler(db_oturumu, k["id"], onek)
    assert sorted(i.rsplit("-", 1)[1] for i in kimlikler) == ["3", "7"]
    # Çok geç (son eşikten 7 günden fazla sonra) susar.
    await otomasyon.teklif_yanitsizlarini_uret(db_oturumu, an + timedelta(days=13))
    assert len(await _kimlikler(db_oturumu, k["id"], onek)) == 2

    # Yeniden gönderim (yeni gonderildi_at) sayacı sıfırlar.
    yeniden = an + timedelta(days=5)
    t.gonderildi_at = yeniden
    await db_oturumu.commit()
    await otomasyon.teklif_yanitsizlarini_uret(db_oturumu, yeniden + timedelta(days=3, minutes=5))
    assert f"tyanitsiz-{t.id}-{int(yeniden.timestamp())}-3" in await _kimlikler(db_oturumu, k["id"], onek)
    # Kabul edilince artık üretilmez.
    t.durum = "kabul"
    await db_oturumu.commit()
    await otomasyon.teklif_yanitsizlarini_uret(db_oturumu, yeniden + timedelta(days=7, minutes=5))
    assert len(await _kimlikler(db_oturumu, k["id"], onek)) == 3


async def test_teklif_yanitsiz_sablonu_uctan_uca(istemci, yonetici_basligi, db_oturumu, posta):
    from services import otomasyon

    k = await _sablondan(istemci, yonetici_basligi, "teklif_yanitsiz_hatirlatma")
    an = datetime.now(UTC)
    hesapli = await _teklif(db_oturumu, gonderildi=an - timedelta(days=3, hours=2), hesap=_e("hesap"), goruntulenme=2)
    hesapsiz = await _teklif(db_oturumu, gonderildi=an - timedelta(days=3, hours=2), aday_eposta="aday@musteri.dev")
    await otomasyon.teklif_yanitsizlarini_uret(db_oturumu, an)
    await _isle()
    satirlar = {json.loads(c.veri)["teklif_id"]: c for c in await _calismalar(db_oturumu, k["id"])}
    assert satirlar[hesapsiz.id].durum == "tamam" and satirlar[hesapli.id].durum == "tamam"
    giden = {g["alici"]: g for g in posta.giden if "hatırlatma" in g["konu"]}
    # Hesapsız: kişiye (aday e-postası), bağlantı varsayılan metniyle; hesaplı: panel bağlantısı.
    assert "ilk e-postadaki bağlantı" in giden["aday@musteri.dev"]["govde"]
    assert hesapsiz.no in giden["aday@musteri.dev"]["govde"]
    assert "/client?sekme=invoices" in giden[hesapli.hesap_email]["govde"]
    eylemler = json.loads(satirlar[hesapsiz.id].eylem_sonuclari)
    assert [e["tur"] for e in eylemler] == ["eposta", "bildirim"] and eylemler[1]["durum"] == "basarili"
    # 7. gün olayı şablonun koşulunu (gun=3) tutmaz.
    await otomasyon.teklif_yanitsizlarini_uret(db_oturumu, an + timedelta(days=4))
    await _isle()
    durumlar = [c.durum for c in await _calismalar(db_oturumu, k["id"])
                if json.loads(c.veri)["gun"] == 7 and json.loads(c.veri)["teklif_id"] in (hesapli.id, hesapsiz.id)]
    assert durumlar == ["kosul_tutmadi", "kosul_tutmadi"]


# ---------------------------------------------------------------------------
# aday.hareketsiz
# ---------------------------------------------------------------------------
async def _aday(db, *, asama="yeni", zaman=None, sorumlu=None, ad="Hareketsiz Aday"):
    from models.crm import CrmAdaylari
    from services import crm

    await crm.asamalari_hazirla(db)
    return await _ekle(db, CrmAdaylari(ad=ad, email=_e("aday"), kaynak="manuel", asama=asama, para_birimi="TRY",
                                       puan=0, sorumlu=sorumlu, created_at=zaman, updated_at=zaman, asama_degisme_at=zaman))


async def test_aday_hareketsiz_esik_tek_sefer_ve_sifirlanma(istemci, yonetici_basligi, db_oturumu):
    from models.crm import CrmAktiviteler
    from services import otomasyon

    an = datetime.now(UTC).replace(microsecond=0)
    bas = an - timedelta(days=7, hours=1)
    a = await _aday(db_oturumu, zaman=bas)
    kazanildi = await _aday(db_oturumu, asama="kazanildi", zaman=bas)
    kaybedildi = await _aday(db_oturumu, asama="kaybedildi", zaman=bas)
    taze = await _aday(db_oturumu, zaman=an - timedelta(days=6))
    assert (await otomasyon.aday_hareketsizlerini_uret(db_oturumu, an)) == {"uretilen": 0}  # kural yok

    k = await _sablondan(istemci, yonetici_basligi, "aday_hareketsiz_hatirlatma")
    assert (await otomasyon.aday_hareketsizlerini_uret(db_oturumu, an))["uretilen"] >= 1
    await otomasyon.aday_hareketsizlerini_uret(db_oturumu, an + timedelta(minutes=10))
    onek = f"ahareketsiz-{a.id}-"
    assert await _kimlikler(db_oturumu, k["id"], onek) == [f"ahareketsiz-{a.id}-{int(bas.timestamp())}-7"]
    kimlikler = [c.olay_id for c in await _calismalar(db_oturumu, k["id"])]
    for x in (kazanildi, kaybedildi, taze):
        assert not any(i.startswith(f"ahareketsiz-{x.id}-") for i in kimlikler)

    # Şablon: sorumlu yok → yöneticilere bildirim + CRM notu (yapan "otomasyon").
    await _isle()
    c = next(c for c in await _calismalar(db_oturumu, k["id"]) if c.olay_id.startswith(f"ahareketsiz-{a.id}-"))
    eylemler = json.loads(c.eylem_sonuclari)
    assert c.durum == "tamam" and [e["durum"] for e in eylemler] == ["basarili", "basarili"], eylemler
    assert eylemler[0]["ozet"]["alici_sayisi"] >= 1
    notlar = (await db_oturumu.execute(select(CrmAktiviteler).where(CrmAktiviteler.aday_id == a.id))).scalars().all()
    assert [n.yapan for n in notlar] == ["otomasyon"]

    # Otomasyonun kendi notu hareket sayılmaz: 14. gün eşiği yine aynı dönemden gelir.
    on_dort = bas + timedelta(days=14, minutes=5)
    await otomasyon.aday_hareketsizlerini_uret(db_oturumu, on_dort)
    assert f"ahareketsiz-{a.id}-{int(bas.timestamp())}-14" in await _kimlikler(db_oturumu, k["id"], onek)

    # Kullanıcının etkinliği sayacı sıfırlar: yeni dönemde 7. gün yeniden.
    hareket = on_dort + timedelta(hours=1)
    await _ekle(db_oturumu, CrmAktiviteler(aday_id=a.id, tur="arama", metin="Arandı", yapan="satis@ajans.dev", zaman=hareket))
    await otomasyon.aday_hareketsizlerini_uret(db_oturumu, hareket + timedelta(days=3))
    assert len(await _kimlikler(db_oturumu, k["id"], onek)) == 2
    await otomasyon.aday_hareketsizlerini_uret(db_oturumu, hareket + timedelta(days=7, minutes=1))
    assert await _kimlikler(db_oturumu, k["id"], onek) == [
        f"ahareketsiz-{a.id}-{int(bas.timestamp())}-7", f"ahareketsiz-{a.id}-{int(bas.timestamp())}-14",
        f"ahareketsiz-{a.id}-{int(hareket.timestamp())}-7"]


async def test_aday_hareketsiz_sorumluya_gider(istemci, yonetici_basligi, db_oturumu):
    from models.notifications import Notifications
    from services import otomasyon

    an = datetime.now(UTC)
    a = await _aday(db_oturumu, zaman=an - timedelta(days=8), sorumlu="satisci@ajans.dev", ad=f"Sorumlu {uuid.uuid4().hex[:6]}")
    await _sablondan(istemci, yonetici_basligi, "aday_hareketsiz_hatirlatma")
    await otomasyon.aday_hareketsizlerini_uret(db_oturumu, an)
    await _isle()
    n = (await db_oturumu.execute(select(Notifications).where(
        Notifications.event_type == "otomasyon_bildirimi", Notifications.title.like(f"%{a.ad}%"),
        Notifications.channel == "inapp"))).scalars().all()
    assert {x.recipient_email for x in n} == {"satisci@ajans.dev"} and n[0].link == "/admin?sekme=crm"


# ---------------------------------------------------------------------------
# Diğer şablonlar uçtan uca
# ---------------------------------------------------------------------------
async def test_proje_yayinda_sablonu_eposta_gonderir(istemci, yonetici_basligi, db_oturumu, posta):
    from models.projects import Projects

    k = await _sablondan(istemci, yonetici_basligi, "proje_yayinda_geri_bildirim")
    e = _e("proje")
    p = await _ekle(db_oturumu, Projects(title="Kafe sitesi", description="d", category="Web", client_email=e, published=False,
                                         status="in_progress", stage="review", progress=60))
    for asama in ("build", "launch"):
        y = await istemci.post("/api/v1/entities/project_events/stage", json={"project_id": p.id, "stage": asama},
                               headers=yonetici_basligi)
        assert y.status_code == 200, y.text
    await _isle()
    # İki aşama değişimi işlenmeden önce art arda geldi: koşul OLAY ANINDAKİ aşamayı okumalı (kayıttaki son
    # aşama "launch" olsa da "build" olayı e-posta göndermemeli → çift e-posta yok).
    durumlar = {json.loads(c.veri)["asama"]: c.durum for c in await _calismalar(db_oturumu, k["id"])}
    assert durumlar == {"build": "kosul_tutmadi", "launch": "tamam"}
    # (Yerleşik "aşama değişti" bildirimleri ayrıca gidiyor; şablonun e-postası tek.)
    giden = [g for g in posta.giden if g["alici"] == e and "yayında" in g["konu"]]
    assert len(giden) == 1 and "teşekkür" in giden[0]["govde"] and giden[0]["ek"].get("html")


async def test_fatura_30_gun_sablonu_kazanilmis_adaya_not_yazar(istemci, yonetici_basligi, db_oturumu, posta):
    from models.crm import CrmAktiviteler
    from models.invoices import Invoices
    from services import otomasyon

    k = await _sablondan(istemci, yonetici_basligi, "fatura_gecikti_hatirlatma")
    e = _e("fatura")
    aday = await _aday(db_oturumu, asama="kazanildi", zaman=datetime.now(UTC) - timedelta(days=90))
    aday.musteri_email = e
    await db_oturumu.commit()
    vade = (date.today() - timedelta(days=31)).isoformat()
    f = await _ekle(db_oturumu, Invoices(invoice_no=f"F-{uuid.uuid4().hex[:5]}", client_email=e, amount=2500.0,
                                         currency="TRY", status="unpaid", due_date=vade))
    await otomasyon.fatura_gecikmelerini_uret(db_oturumu)
    await _isle()
    c = next(c for c in await _calismalar(db_oturumu, k["id"]) if c.olay_id == f"fgecikti-{f.id}-30")
    eylemler = json.loads(c.eylem_sonuclari)
    assert c.durum == "tamam" and [x["durum"] for x in eylemler] == ["basarili", "basarili"], eylemler
    assert not [g for g in posta.giden if g["alici"] == e]  # müşteriye otomasyondan e-posta gitmez
    notlar = (await db_oturumu.execute(select(CrmAktiviteler).where(CrmAktiviteler.aday_id == aday.id))).scalars().all()
    assert any(f.invoice_no in (n.metin or "") for n in notlar)


async def test_icerik_onaylandi_sablonu_yalniz_ajans_icerigi(istemci, yonetici_basligi, db_oturumu):
    from models.content_posts import Content_posts

    k = await _sablondan(istemci, yonetici_basligi, "icerik_onaylandi_gorev")
    ajans = await _ekle(db_oturumu, Content_posts(title="Ekim duyurusu", status="taslak", yoneten="ajans",
                                                 sorumlu_eposta="icerikci@ajans.dev"))
    musteri = await _ekle(db_oturumu, Content_posts(title="Müşterinin gönderisi", status="taslak", yoneten="musteri",
                                                   hesap_email=_e("icerik")))
    for g in (ajans, musteri):
        g.status = "onaylandi"
    await db_oturumu.commit()
    await _isle()
    durumlar = {json.loads(c.veri)["gonderi_id"]: c.durum for c in await _calismalar(db_oturumu, k["id"])}
    assert durumlar == {ajans.id: "tamam", musteri.id: "kosul_tutmadi"}
    c = next(c for c in await _calismalar(db_oturumu, k["id"]) if json.loads(c.veri)["gonderi_id"] == ajans.id)
    assert json.loads(c.eylem_sonuclari)[0]["ozet"]["baslik"] == "Paylaş: Ekim duyurusu"


async def test_icerik_onaylandi_projeli_gonderi_gorev_acar(istemci, yonetici_basligi, db_oturumu):
    """Faz 7K: gönderiye proje bağlıysa şablon projeye "Paylaş" görevi açar (+ bildirim); bağlı değilse görev
    adımı "proje_yok" ile atlanır, bildirim bugünkü gibi gider."""
    from models.content_posts import Content_posts
    from models.proje_gorevleri import ProjectTasks
    from models.projects import Projects
    from services import otomasyon_kural as kk

    s = kk.SABLON_SOZLUGU["icerik_onaylandi_gorev"]
    assert kk.OLAY_SOZLUGU["icerik.onaylandi"].proje_var and [e["tur"] for e in s.eylemler] == ["bildirim", "gorev"]
    k = await _sablondan(istemci, yonetici_basligi, "icerik_onaylandi_gorev")
    hesap = _e("icp")
    p = await _ekle(db_oturumu, Projects(title="Sosyal medya yönetimi", description="-", category="sosyal",
                                         client_email=hesap, status="active"))
    projeli = await _ekle(db_oturumu, Content_posts(title="Kasım kampanyası", status="taslak", yoneten="ajans",
                                                   hesap_email=hesap, proje_id=p.id, sorumlu_eposta="icerikci@ajans.dev"))
    projesiz = await _ekle(db_oturumu, Content_posts(title="Projesiz gönderi", status="taslak", yoneten="ajans",
                                                    hesap_email=hesap))
    for g in (projeli, projesiz):
        g.status = "onaylandi"
    await db_oturumu.commit()
    await _isle()
    calismalar = {json.loads(c.veri)["gonderi_id"]: c for c in await _calismalar(db_oturumu, k["id"])}
    assert json.loads(calismalar[projeli.id].veri)["proje_id"] == p.id  # olay verisinde proje kimliği
    sonuc = json.loads(calismalar[projeli.id].eylem_sonuclari)
    assert calismalar[projeli.id].durum == "tamam" and [x["durum"] for x in sonuc] == ["basarili", "basarili"], sonuc
    gorevler = (await db_oturumu.execute(select(ProjectTasks).where(ProjectTasks.proje_id == p.id))).scalars().all()
    assert [g.baslik for g in gorevler] == ["Paylaş: Kasım kampanyası"]
    assert gorevler[0].bitis_tarihi == date.today() + timedelta(days=1) and "otomasyon" in gorevler[0].etiketler
    sonuc = json.loads(calismalar[projesiz.id].eylem_sonuclari)
    assert calismalar[projesiz.id].durum == "tamam"
    assert sonuc[0]["durum"] == "basarili" and sonuc[0]["ozet"]["baslik"] == "Paylaş: Projesiz gönderi"
    assert sonuc[1]["durum"] == "atlandi" and sonuc[1]["neden"] == "proje_yok", sonuc


async def test_sozlesme_imzalandi_sablonu_bildirim(istemci, yonetici_basligi, db_oturumu):
    from services import otomasyon_kural as k

    s = k.SABLON_SOZLUGU["sozlesme_imzalandi_bildirim"]
    # Faz 7H: olayda sözleşmenin teklifinden açılan proje var (teklif → proje) → bildirim + "olaydaki proje"ye
    # görev (proje yoksa görev adımı "proje_yok" ile atlanır; ayrıntı test_saglamlastirma.py).
    assert k.OLAY_SOZLUGU["sozlesme.imzalandi"].proje_var and [e["tur"] for e in s.eylemler] == ["bildirim", "gorev"]
    kural = await _sablondan(istemci, yonetici_basligi, "sozlesme_imzalandi_bildirim")
    y = await istemci.post(f"{Y}/kurallar/{kural['id']}/test", json={}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["eylemler"][0]["durum"] == "yapilacak"
    assert y.json()["eylemler"][0]["ozet"]["baslik"].startswith("İşe başlama zamanı")
    assert y.json()["eylemler"][1]["durum"] == "yapilacak"


# ---------------------------------------------------------------------------
# Haftalık özet
# ---------------------------------------------------------------------------
def _pazartesi(yil: int, ay: int) -> date:
    g = date(yil, ay, 1)
    return g + timedelta(days=(7 - g.weekday()) % 7)


def _tr(gun: date, saat: int, dakika: int = 0) -> datetime:
    """İstanbul saati (UTC+3) → UTC."""
    return datetime(gun.year, gun.month, gun.day, saat, dakika, tzinfo=UTC) - timedelta(hours=3)


async def _ozet_bildirimleri(db) -> int:
    from models.notifications import Notifications

    return int((await db.execute(select(func.count(Notifications.id)).where(
        Notifications.event_type == "haftalik_ozet", Notifications.channel == "inapp"))).scalar() or 0)


async def test_haftalik_ozet_pencere_hafta_kilidi_bos_ve_matris(db_oturumu, monkeypatch, posta):
    from models.invoices import Invoices
    from services import haftalik_ozet as ho
    from services.notify import admin_recipients

    await ho.ac_kapat(db_oturumu, True)
    yoneticiler = len(await admin_recipients(db_oturumu))
    assert yoneticiler >= 1
    pzt = _pazartesi(2031, 3)
    await _ekle(db_oturumu, Invoices(invoice_no=f"HO-{uuid.uuid4().hex[:5]}", client_email=_e("ho"), amount=900.0,
                                     currency="EUR", status="unpaid", due_date=(pzt - timedelta(days=10)).isoformat()))
    once = await _ozet_bildirimleri(db_oturumu)
    # Pazartesi 07:59 (İstanbul): pencere kapalı.
    assert (await ho.gonder(db_oturumu, _tr(pzt, 7, 59))) == {"atlandi": "pencere_disi"}
    # 08:05: gönderilir.
    r = await ho.gonder(db_oturumu, _tr(pzt, 8, 5))
    assert r["gonderildi"] is True and r["bolum"] >= 1, r
    assert await _ozet_bildirimleri(db_oturumu) == once + yoneticiler
    eposta = [g for g in posta.giden if g["konu"].startswith("Haftalık özet")]
    assert eposta and "Vadesi geçmiş faturalar" in eposta[-1]["govde"] and "/admin?sekme=invoices" in eposta[-1]["govde"]
    assert "<a href=" in eposta[-1]["ek"]["html"] and "<script" not in eposta[-1]["ek"]["html"]
    # Aynı hafta (öğleden sonra, Cumartesi, "Şimdi çalıştır") ikinci kez gitmez.
    for an in (_tr(pzt, 14), _tr(pzt + timedelta(days=5), 10)):
        assert (await ho.gonder(db_oturumu, an))["atlandi"] == "bu_hafta_yapildi"
    assert await _ozet_bildirimleri(db_oturumu) == once + yoneticiler
    # Sonraki Pazartesi yeniden.
    assert (await ho.gonder(db_oturumu, _tr(pzt + timedelta(days=7), 8, 1)))["gonderildi"] is True
    assert await _ozet_bildirimleri(db_oturumu) == once + 2 * yoneticiler

    # Matris kapalı → gönderilmez ve hafta işaretlenmez (açılınca aynı hafta gelir).
    ucuncu = pzt + timedelta(days=14)
    await ho.ac_kapat(db_oturumu, False)
    assert (await ho.gonder(db_oturumu, _tr(ucuncu, 9)))["atlandi"] == "kapali"
    assert await _ozet_bildirimleri(db_oturumu) == once + 2 * yoneticiler
    await ho.ac_kapat(db_oturumu, True)
    assert (await ho.gonder(db_oturumu, _tr(ucuncu, 11)))["gonderildi"] is True

    # Hepsi sıfırsa gönderilmez (ama hafta işaretlenir: Perşembe bir şey çıktı diye gelmez).
    dorduncu = pzt + timedelta(days=21)
    eski_bolumler = ho.BOLUMLER
    monkeypatch.setattr(ho, "BOLUMLER", (lambda db, an: _bos_bolum(),))
    sayi = await _ozet_bildirimleri(db_oturumu)
    assert (await ho.gonder(db_oturumu, _tr(dorduncu, 8, 30))) == {"gonderildi": False, "bos": True,
                                                                     "hafta": ho.hafta_etiketi(_tr(dorduncu, 8, 30))}
    monkeypatch.setattr(ho, "BOLUMLER", eski_bolumler)
    assert (await ho.gonder(db_oturumu, _tr(dorduncu + timedelta(days=3), 9)))["atlandi"] == "bu_hafta_yapildi"
    assert await _ozet_bildirimleri(db_oturumu) == sayi


async def _bos_bolum():
    from services import haftalik_ozet as ho

    return ho._bolum("faturalar", "invoices", 0, [])


async def test_haftalik_ozet_icerik_butun_bolumler(db_oturumu, istemci, yonetici_basligi):
    from models.client_sites import Client_sites
    from models.content_posts import Content_posts
    from models.dosyalar import BelgeTalepleri
    from models.invoices import Invoices
    from models.site_izleme import SiteIzleme, UptimeKesintisi
    from models.support_tickets import Support_tickets
    from services import haftalik_ozet as ho

    an = datetime.now(UTC)
    e = _e("bolum")
    await _ekle(db_oturumu, Invoices(invoice_no=f"B-{uuid.uuid4().hex[:5]}", client_email=e, amount=100.0, currency="USD",
                                     status="unpaid", due_date=(date.today() - timedelta(days=3)).isoformat()))
    await _ekle(db_oturumu, Support_tickets(subject="Site yavaş", message="m", status="open", client_email=e))
    # Faz 5G: gelen kutusunda yanıt bekleyen (destek dışı) bir öğe.
    from models.kartvizit import KartvizitMesajlari

    await _ekle(db_oturumu, KartvizitMesajlari(sahip_tur="kart", sahip_id=1, hesap_email=None, ad="Kartçı", eposta=e,
                                               mesaj="Merhaba", okundu=False, created_at=an))
    aday = await _aday(db_oturumu, zaman=an - timedelta(days=2))
    aday.sonraki_adim, aday.sonraki_adim_tarihi = "Ara", date.today() - timedelta(days=1)
    await _aday(db_oturumu, zaman=an - timedelta(days=9), ad="Uyuyan Aday")
    await db_oturumu.commit()
    await _teklif(db_oturumu, gonderildi=an - timedelta(days=4), aday_eposta="tk@musteri.dev")
    await _ekle(db_oturumu, Content_posts(title="Onay bekleyen", status="musteri_onayi", yoneten="ajans", hesap_email=e))
    await _ekle(db_oturumu, BelgeTalepleri(client_email=e, baslik="Vergi levhası", durum="bekliyor",
                                           son_tarih=(date.today() - timedelta(days=1)).isoformat()))
    site = await _ekle(db_oturumu, Client_sites(client_email=e, ad="ornek-kafe.com", adres="https://ornek-kafe.com"))
    await _ekle(db_oturumu, SiteIzleme(site_id=site.id, alan_adi="ornek-kafe.com", alan_bitis=an + timedelta(days=10)))
    await _ekle(db_oturumu, UptimeKesintisi(kontrol_id=0, site_id=site.id, baslangic=an - timedelta(hours=2)))
    # Faz 6P: POS'u açık bir müşteride kritik stok uyarısı gitmiş ürün.
    from models.stok_pos import StokUrunleri

    y = await istemci.put(f"/api/v1/moduller/musteri/{e}/stok_pos", json={"acik": True}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    await _ekle(db_oturumu, StokUrunleri(hesap_email=e, ad="Filtre kahve", barkod="2000000000008", satis_fiyati=100,
                                         kritik_esik=2000, kritik_at=an - timedelta(days=1)))
    # Faz 6I: ajansın kendi personelinin bekleyen izin talebi (gelen kutusu bölümünde sayılmaz, kendi bölümünde).
    from models.ik import IkIzinler, IkPersonel

    ikp = await _ekle(db_oturumu, IkPersonel(hesap_email=None, ad="Özet Personeli", ise_giris=date(2020, 1, 1), durum="aktif"))
    await _ekle(db_oturumu, IkIzinler(hesap_email=None, personel_id=ikp.id, tur="yillik", baslangic=date.today(),
                                      bitis=date.today(), gun=1, durum="beklemede", kaynak="portal", created_at=an - timedelta(days=2)))
    # Faz 6M: ajansın kendi ön muhasebesinde vadesi geçmiş cari alacak.
    from models.muhasebe import MuhasebeCariler, MuhasebeHareketleri

    mc = await _ekle(db_oturumu, MuhasebeCariler(kapsam="@ajans", hesap_email=None, tur="musteri", ad="Özet Carisi", para_birimi="TRY",
                                                 acilis_bakiyesi=0))
    await _ekle(db_oturumu, MuhasebeHareketleri(kapsam="@ajans", hesap_email=None, tur="gelir", tarih=date.today() - timedelta(days=40),
                                                vade_tarihi=date.today() - timedelta(days=30), tutar=500000, para_birimi="TRY",
                                                kdv_tutari=0, cari_id=mc.id, kaynak="manuel"))

    # Faz 5K: bekleyen ortaklık başvurusu (kendi bölümünde; gelen kutusu bölümünde sayılmaz).
    from models.ortaklik import Ortaklar

    await _ekle(db_oturumu, Ortaklar(eposta=_e("ortak"), ad="Özet Ortağı", durum="beklemede", basvuru_at=an - timedelta(days=1)))

    from models.sozlesmeler import HatirlatmaIzleri

    iz_sayisi = select(func.count(HatirlatmaIzleri.id)).where(HatirlatmaIzleri.tur == "haftalik_ozet")
    iz_once = (await db_oturumu.execute(iz_sayisi)).scalar()
    y = await istemci.get(f"{Y}/haftalik-ozet/onizle", headers=yonetici_basligi)
    assert y.status_code == 200
    o = y.json()
    bolumler = {b["anahtar"]: b for b in o["bolumler"]}
    assert list(bolumler) == ["faturalar", "destek", "gelen_kutusu", "crm", "teklifler", "icerik", "belgeler",
                              "yenilemeler", "siteler", "stok_kritik", "ik_izin", "muhasebe", "ortaklik"]
    for b in bolumler.values():
        assert b["sayi"] >= 1 and len(b["ornekler"]) <= ho.ORNEK_SINIRI, b
    assert any(t["para_birimi"] == "USD" for t in bolumler["faturalar"]["ek"]["toplamlar"])
    assert bolumler["crm"]["ek"]["sonraki_adim"] >= 1 and bolumler["crm"]["ek"]["hareketsiz"] >= 1
    assert bolumler["belgeler"]["ek"]["geciken"] >= 1
    assert any(s["ad"] == "ornek-kafe.com" and s["tur"] == "alan" for s in bolumler["yenilemeler"]["ornekler"])
    assert any(s["ad"] == "ornek-kafe.com" for s in bolumler["siteler"]["ornekler"])
    assert {b["sekme"] for b in o["bolumler"]} <= {"invoices", "tickets", "gelenKutusu", "crm", "teklifler", "icerik",
                                                   "dosyalar", "siteler", "stokPos", "ik", "onMuhasebe", "ortaklik"}
    assert bolumler["gelen_kutusu"]["ek"]["kaynaklar"].get("kartvizit", 0) >= 1
    assert "izin_talebi" not in bolumler["gelen_kutusu"]["ek"]["kaynaklar"]
    assert any(s["ad"] == "Özet Personeli" and s["tur"] == "izin_bekliyor" for s in bolumler["ik_izin"]["ornekler"]) or \
        bolumler["ik_izin"]["sayi"] > len(bolumler["ik_izin"]["ornekler"])
    assert bolumler["muhasebe"]["ek"]["alacak"] >= 1 and any(s["tur"] == "cari_gecikme" for s in bolumler["muhasebe"]["ornekler"])
    assert o["bos"] is False and o["eposta"]["konu"].startswith("Haftalık özet")
    # Önizleme gönderim izi yazmaz.
    assert (await db_oturumu.execute(iz_sayisi)).scalar() == iz_once


async def test_haftalik_ozet_uclari_yalniz_yonetici(istemci, yonetici_basligi, db_oturumu):
    from services import bildirim_tercih as bt

    for yontem, yol, govde in (("GET", "/haftalik-ozet", None), ("GET", "/haftalik-ozet/onizle", None),
                               ("PUT", "/haftalik-ozet", {"acik": False})):
        assert (await istemci.request(yontem, Y + yol, json=govde)).status_code == 401
        assert (await istemci.request(yontem, Y + yol, json=govde, headers=_b(_e("m")))).status_code == 403
    assert (await istemci.put(f"{Y}/haftalik-ozet", json={"acik": "evet"}, headers=yonetici_basligi)).status_code == 400
    y = await istemci.put(f"{Y}/haftalik-ozet", json={"acik": False}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["acik"] is False
    assert (await bt.matris_oku(db_oturumu))["admin"]["haftalik_ozet"]["email"] is False
    # Matristen açılınca kart da açık görür (tek kaynak).
    matris = await bt.matris_oku(db_oturumu)
    matris["admin"]["haftalik_ozet"]["email"] = True
    await bt.matris_yaz(db_oturumu, matris)
    d = (await istemci.get(f"{Y}/haftalik-ozet", headers=yonetici_basligi)).json()
    assert d["acik"] is True and set(d) >= {"son_gonderim", "bu_hafta", "sonraki", "eposta_kanali", "alici_sayisi"}
    assert "haftalik_ozet" in bt.olay_listesi("admin") and "haftalik_ozet" not in bt.olay_listesi("client")


async def test_zamanli_is_listesinde_haftalik_ozet(istemci, yonetici_basligi):
    from services import zamanli

    assert "haftalik_ozet" in zamanli.GOREV_ADLARI
    assert zamanli.GOREV_ADLARI[-1] == "aylik_site_analizi"  # yavaş iş hâlâ en sonda
    y = await istemci.get("/api/v1/zamanli/yonetim", headers=yonetici_basligi)
    g = next(g for g in y.json()["gorevler"] if g["gorev"] == "haftalik_ozet")
    assert g["plan"] == "haftalik_pazartesi"
    assert next(g for g in y.json()["gorevler"] if g["gorev"] == "uptime")["plan"] is None
