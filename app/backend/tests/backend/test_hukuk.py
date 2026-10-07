"""Faz 6H — Hukuk bürosu: müvekkil, dosya, süre takibi, masraf, müvekkil portalı.

Kapsam: saf kurallar (Türkçe ad normalleştirme ve çıkar çatışması eşleşmesi; SÜRE HESABI — her kuralın
dayanağı testin içinde yorumlu: HMK m.92 başlangıç günü sayılmaz / karşılık gelen gün / ay sonu, m.93 tatil
ve hafta sonu kaydırması, m.104 adli tatil uzatması, 2429 s. Kanun sabit tatilleri, kullanıcının eklediği dini
bayram, yarım gün); imzalı portal jetonu; yetki (anonim, modül kapalı, yönetici ucu), müşteri yalnız kendi
hesabı, ekip izni ve GİZLİ dosya; çıkar çatışması uyarıları (gizli dosyada ayrıntısız); YÖNETİCİ UÇLARINDA VE
DENETİM/BİLDİRİM SATIRLARINDA İÇERİK SIZMAMASI; dosya sınırı; silinenler (30 gün, geri alma, kalıcı silme);
saat + masraf + makbuz + PDF (Türkçe harfler); ICS (sorumlu başına); müvekkil portalı (yalnız işaretli alanlar,
yenile/iptal, modül kapalı 410, mesaj → büroya içeriksiz bildirim, gelen kutusuna düşmez); zamanlı hatırlatma
BİR KEZ (kaçırılan eşik sonradan gitmez, aynı gün sabah saatinden önce gitmez); sektör paketi (reklam yasağı)
ve Pages Function / rota / i18n denetimleri.
"""

import json
import re
import shutil
import subprocess
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import func, select

from conftest import jeton_uret

M = "/api/v1/hukukum"
Y = "/api/v1/hukuk/yonetim"
A = "/api/v1/hukuk"
MODUL = "/api/v1/moduller"
UTC = timezone.utc
ON_YUZ = Path(__file__).resolve().parents[3] / "frontend"
DILLER = ("tr", "en", "de", "ru", "zh", "hi", "ar")
#: Testlerin "şimdi"si: 5 Ekim 2026 Pazartesi 09:00 İstanbul (06:00 UTC).
SIMDI = datetime(2026, 10, 5, 6, 0, tzinfo=UTC)
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def _e(on: str = "buro") -> str:
    return f"{on}-{uuid.uuid4().hex[:8]}@hukuk.dev"


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


@pytest.fixture(autouse=True)
def _ortam(monkeypatch):
    from routers import hukuk as r
    from services import hesap_ekibi, hukuk as s

    r.hiz_sinirlarini_temizle()
    hesap_ekibi.onbellegi_temizle()
    saat = {"an": SIMDI}
    monkeypatch.setattr(s, "simdi", lambda: saat["an"])
    yield saat
    r.hiz_sinirlarini_temizle()


async def _modul(istemci, yb, eposta, acik=True, **ayarlar):
    govde = {"acik": acik}
    if ayarlar:
        govde["ayarlar"] = ayarlar
    y = await istemci.put(f"{MODUL}/musteri/{eposta}/hukuk_burosu", json=govde, headers=yb)
    assert y.status_code == 200, y.text


async def _uye(db, hesap, uye, izinler, rol="uye"):
    from models.hesap_uyeleri import HesapUyeleri
    from services import hesap_ekibi as he

    db.add(HesapUyeleri(hesap_email=hesap, uye_email=uye, rol=rol, izinler=json.dumps(list(izinler)), durum="aktif",
                        olusturma=he.simdi()))
    await db.commit()
    he.onbellegi_temizle()


async def _muvekkil(istemci, b, **g):
    g.setdefault("ad", f"Ayşe Yılmaz {uuid.uuid4().hex[:4]}")
    y = await istemci.post(f"{M}/muvekkiller", json=g, headers=b)
    assert y.status_code == 200, y.text
    return y.json()


async def _dosya(istemci, b, mid, **g):
    y = await istemci.post(f"{M}/dosyalar", json={"muvekkil_id": mid, **g}, headers=b)
    assert y.status_code == 200, y.text
    return y.json()


async def _buro(istemci, yb, **ayarlar):
    e = _e()
    await _modul(istemci, yb, e, **ayarlar)
    return e, _b(e)


# ===========================================================================
# Saf kurallar
# ===========================================================================
def test_ad_normalle_ve_benzerlik_turkce():
    from services import hukuk as s

    # Türkçe büyük/küçük: Python'un lower()'ı "İ"yi "i̇" yapar; normalleştirme bunu da, ı/İ/ş/ğ/ç/ö/ü'yü de düzler.
    assert s.ad_normalle("ŞAHİN İnşaat A.Ş.") == "sahin insaat"
    assert s.ad_normalle("IŞIK") == s.ad_normalle("Işık") == "isik"
    assert s.ad_normalle("Yılmaz Tekstil Ltd. Şti.") == "yilmaz tekstil"
    assert s.ad_normalle("  Çağrı   ÖZGÜR  ") == "cagri ozgur"
    assert s.benzerlik("yilmaz insaat", "yilmaz insaat") == "tam"
    assert s.benzerlik("yilmaz insaat", "yilmaz insaat taahhut") == "kismi"
    # Tek belirteçli kısa ad tek başına "kısmi" sayılmaz (her Yılmaz çatışma değil).
    assert s.benzerlik("yilmaz", "ahmet yilmaz") is None
    assert s.vergi_no_duzelt("123 456-7890") == "1234567890"
    with pytest.raises(s.HukukHatasi):
        s.vergi_no_duzelt("12")
    adaylar = [s.Aday("karsi_taraf", "ŞAHİN İNŞAAT", s.ad_normalle("ŞAHİN İNŞAAT"), "1111111111", 1, 9),
               s.Aday("muvekkil", "Başka", s.ad_normalle("Başka"), "2222222222", 2)]
    eslesen = s.eslesmeler("Şahin İnşaat A.Ş.", None, adaylar)
    assert [(a.rol, t) for a, t in eslesen] == [("karsi_taraf", "tam")]
    assert [(a.muvekkil_id, t) for a, t in s.eslesmeler("Kimse", "2222222222", adaylar)] == [(2, "vergi_no")]


def _sabit():
    """2429 sayılı Ulusal Bayram ve Genel Tatiller Hakkında Kanun — sabit günler (yıllık tekrar)."""
    from services import hukuk as s

    return [s.Tatil(ad, date(2000, int(ag[:2]), int(ag[3:])), tekrar=True, yarim=yarim) for ag, ad, yarim, _ in s.SABIT_TATILLER]


def test_sure_gun_baslangic_gunu_sayilmaz():
    from services import hukuk as s

    # HMK m.92/1: "Gün olarak belirlenen süre, başladığı günün sonundan itibaren hesaplanır." → tebliğ günü
    # sayılmaz; 5 Ekim (Pzt) + 7 gün = 12 Ekim (Pzt), iş günü → kaydırma yok.
    r = s.son_gun_hesapla(date(2026, 10, 5), 7, "gun", adli_tatil=True, tatiller=_sabit())
    assert r["ham_son_gun"] == r["son_gun"] == "2026-10-12"
    assert [a["kural"] for a in r["adimlar"]] == ["hmk92"]


def test_sure_hafta_sonu_kaymasi():
    from services import hukuk as s

    # HMK m.93: "Süre resmî tatil gününe rastlarsa, tatili izleyen ilk iş günü çalışma saati bitiminde sona erer."
    # Hafta sonu (Cumartesi/Pazar) adliyeler kapalı → aynı kural: 5 Ekim + 5 gün = 10 Ekim Cumartesi → 12 Ekim Pazartesi.
    r = s.son_gun_hesapla(date(2026, 10, 5), 5, "gun", adli_tatil=True, tatiller=_sabit())
    assert r["ham_son_gun"] == "2026-10-10" and r["son_gun"] == "2026-10-12"
    kaydirma = r["adimlar"][1]
    assert kaydirma["kural"] == "hmk93" and [x["neden"] for x in kaydirma["atlanan"]] == ["hafta_sonu", "hafta_sonu"]
    # Hafta: HMK m.92/2 "son haftada başladığı güne karşılık gelen gün" → Pzt + 2 hafta = Pzt.
    assert s.son_gun_hesapla(date(2026, 10, 5), 2, "hafta", adli_tatil=True)["son_gun"] == "2026-10-19"


def test_sure_resmi_tatil_ve_yarim_gun():
    from services import hukuk as s

    # HMK m.93 + 2429 s. Kanun m.1: 29 Ekim Cumhuriyet Bayramı resmî tatil. 22 Ekim + 7 gün = 29 Ekim (Per) →
    # izleyen ilk iş günü 30 Ekim (Cuma).
    r = s.son_gun_hesapla(date(2026, 10, 22), 7, "gun", adli_tatil=True, tatiller=_sabit())
    assert r["ham_son_gun"] == "2026-10-29" and r["son_gun"] == "2026-10-30"
    assert r["adimlar"][1]["atlanan"][0]["neden"] == "tatil" and "Cumhuriyet" in r["adimlar"][1]["atlanan"][0]["ad"]
    # 28 Ekim öğleden sonra YARIM gün: süreyi uzatmaz (gün resmî tatil sayılmaz), yalnız uyarı verir — kesin
    # değerlendirme avukatın (yarım gün tatilde sürenin öğlene kadar dolabileceği uygulaması).
    r = s.son_gun_hesapla(date(2026, 10, 21), 7, "gun", adli_tatil=True, tatiller=_sabit())
    assert r["son_gun"] == "2026-10-28" and r["uyarilar"] == ["yarim_gun"]
    # 1 Ocak 2027 (Cuma, Yılbaşı) → 4 Ocak (Pzt): tekrar eden sabit tatil yıl sınırını da tanır.
    assert s.son_gun_hesapla(date(2026, 12, 25), 7, "gun", adli_tatil=True, tatiller=_sabit())["son_gun"] == "2027-01-04"


def test_sure_dini_bayram_kullanici_ekler():
    from services import hukuk as s

    # Dini bayramlar ay takvimine göre değişir; tohumlanmaz, kullanıcı ekler (tarih aralığı). Eklenen bayram HMK
    # m.93 kaydırmasına girer: 13 Mart + 7 = 20 Mart (Cuma, bayram) → 21-22 hafta sonu → 23 Mart Pazartesi.
    bayram = s.Tatil("Ramazan Bayramı", date(2026, 3, 20), bitis=date(2026, 3, 22))
    r = s.son_gun_hesapla(date(2026, 3, 13), 7, "gun", adli_tatil=True, tatiller=_sabit() + [bayram])
    assert r["son_gun"] == "2026-03-23"
    assert [x["neden"] for x in r["adimlar"][1]["atlanan"]] == ["tatil", "tatil", "tatil"]
    # Eklenmemişse kaydırma yok (yalnız sabit günler bilinir) — arayüz bunu açıkça söylüyor.
    assert s.son_gun_hesapla(date(2026, 3, 13), 7, "gun", adli_tatil=True, tatiller=_sabit())["son_gun"] == "2026-03-20"


def test_sure_ay_sonu_kaymasi():
    from services import hukuk as s

    # HMK m.92/2: ay olarak belirlenen süre son ayda başladığı güne karşılık gelen günde biter; "Bu karşılık gelen
    # gün son ayda yoksa süre, o ayın son günü çalışma saati bitiminde sona erer."
    assert s.ham_son_gun(date(2026, 1, 31), 1, "ay") == date(2026, 2, 28)
    assert s.ham_son_gun(date(2024, 1, 31), 1, "ay") == date(2024, 2, 29)  # artık yıl
    assert s.ham_son_gun(date(2026, 3, 31), 1, "ay") == date(2026, 4, 30)
    assert s.ham_son_gun(date(2026, 11, 30), 3, "ay") == date(2027, 2, 28)
    # 28 Şubat 2026 Cumartesi → HMK m.93 ile 2 Mart Pazartesi.
    r = s.son_gun_hesapla(date(2026, 1, 31), 1, "ay", adli_tatil=True, tatiller=_sabit())
    assert r["ham_son_gun"] == "2026-02-28" and r["son_gun"] == "2026-03-02"


def test_sure_adli_tatil_uzatmasi():
    from services import hukuk as s

    # HMK m.102: adli tatil 20 Temmuz – 31 Ağustos. HMK m.104: adli tatile rastlayan süreler, tatilin bittiği
    # günden itibaren bir hafta uzatılmış sayılır → 31 Ağustos + 7 = 7 Eylül.
    r = s.son_gun_hesapla(date(2026, 7, 6), 14, "gun", adli_tatil=True, tatiller=_sabit())
    assert r["ham_son_gun"] == "2026-07-20" and r["son_gun"] == "2026-09-07"
    assert r["adimlar"][1] == {"kural": "hmk104", "tarih": "2026-09-07", "adli_tatil_bitis": "2026-08-31", "uzatma_gun": 7}
    # İş adli tatile tabi değilse (seçenek kapalı) uzatma yok, ama uyarı var.
    r = s.son_gun_hesapla(date(2026, 7, 6), 14, "gun", adli_tatil=False, tatiller=_sabit())
    assert r["son_gun"] == "2026-07-20" and r["uyarilar"] == ["adli_tatil_icinde"]
    # Uzatılmış gün hafta sonuna düşerse HMK m.93 yine uygulanır: 2025'te 7 Eylül Pazar → 8 Eylül Pazartesi.
    r = s.son_gun_hesapla(date(2025, 7, 1), 30, "gun", adli_tatil=True, tatiller=_sabit())
    assert r["son_gun"] == "2025-09-08" and [a["kural"] for a in r["adimlar"]] == ["hmk92", "hmk104", "hmk93"]
    # m.93 kaydırması adli tatile düşürürse de uzar: 18 Temmuz 2026 Cumartesi → 20 Temmuz (adli tatil) → 7 Eylül.
    r = s.son_gun_hesapla(date(2026, 7, 4), 14, "gun", adli_tatil=True, tatiller=_sabit())
    assert r["ham_son_gun"] == "2026-07-18" and r["son_gun"] == "2026-09-07"
    assert [a["kural"] for a in r["adimlar"]] == ["hmk92", "hmk93", "hmk104"]
    # Ayarlanabilir aralık/uzatma (mevzuat değişirse): 15 Temmuz–31 Ağustos, 10 gün.
    r = s.son_gun_hesapla(date(2026, 7, 6), 10, "gun", adli_tatil=True, adli_bas="07-15", uzatma_gun=10)
    assert r["son_gun"] == "2026-09-10"
    with pytest.raises(s.HukukHatasi):
        s.son_gun_hesapla(date(2026, 7, 6), 0, "gun", adli_tatil=True)


def test_portal_jetonu_imzali_ve_surume_bagli():
    from services import hukuk as s

    j = s.muvekkil_jetonu(42, 3)
    assert s.jeton_parcala(j) == (42, 3) and s.jeton_gecerli_mi(j, 42, 3)
    assert not s.jeton_gecerli_mi(j, 42, 4) and not s.jeton_gecerli_mi(j, 43, 3)
    assert not s.jeton_gecerli_mi(j[:-1] + ("0" if j[-1] != "0" else "1"), 42, 3)
    assert s.jeton_parcala("kotu") is None


# ===========================================================================
# Yetki, hesap izolasyonu, ekip izni, gizli dosya
# ===========================================================================
async def test_yetki_modul_kapali_ve_yonetici_ucu(istemci, yonetici_basligi):
    e = _e()
    assert (await istemci.get(f"{M}/dosyalar")).status_code == 401
    y = await istemci.get(f"{M}/dosyalar", headers=_b(e))
    assert y.status_code == 403 and y.json()["detail"] == {"kod": "modul_kapali", "modul": "hukuk_burosu"}
    assert (await istemci.get(f"{Y}/ozet")).status_code == 401
    assert (await istemci.get(f"{Y}/ozet", headers=_b(e))).status_code == 403
    await _modul(istemci, yonetici_basligi, e)
    y = await istemci.get(f"{M}/meta", headers=_b(e))
    assert y.status_code == 200 and y.json()["sahip"] is True and y.json()["uyap"] is False and y.json()["ai"] is False
    assert y.json()["dosya_siniri"] == 200


async def test_musteri_yalniz_kendi_hesabi(istemci, yonetici_basligi):
    a, ba = await _buro(istemci, yonetici_basligi)
    b_, bb = await _buro(istemci, yonetici_basligi)
    m = (await _muvekkil(istemci, ba, ad="Gizli Kişi"))["muvekkil"]
    d = (await _dosya(istemci, ba, m["id"], konu="Kira"))["dosya"]
    for yol in (f"{M}/muvekkiller/{m['id']}", f"{M}/dosyalar/{d['id']}", f"{M}/dosyalar/{d['id']}/masraflar"):
        assert (await istemci.get(yol, headers=bb)).status_code == 404, yol
    assert (await istemci.get(f"{M}/dosyalar", headers=bb)).json()["items"] == []
    assert (await istemci.get(f"{M}/muvekkiller", headers=bb)).json()["items"] == []
    # Başka hesabın müvekkiline dosya açılamaz.
    y = await istemci.post(f"{M}/dosyalar", json={"muvekkil_id": m["id"]}, headers=bb)
    assert y.status_code == 404


async def test_ekip_izni_ve_gizli_dosya(istemci, yonetici_basligi, db_oturumu):
    s, bs = await _buro(istemci, yonetici_basligi)
    avukat, katip, yabanci = _e("avukat"), _e("katip"), _e("izinsiz")
    await _uye(db_oturumu, s, avukat, ["hukuk"])
    await _uye(db_oturumu, s, katip, ["hukuk"])
    await _uye(db_oturumu, s, yabanci, ["projeler"])
    m = (await _muvekkil(istemci, bs))["muvekkil"]
    acik = (await _dosya(istemci, bs, m["id"], konu="Açık iş"))["dosya"]
    gizli = (await _dosya(istemci, bs, m["id"], konu="Gizli iş", sorumlu_email=avukat, gizli=True))["dosya"]
    y = await istemci.post(f"{M}/olaylar", json={"dosya_id": gizli["id"], "tur": "durusma", "tarih": "2026-10-20", "saat": "10:00"}, headers=bs)
    assert y.status_code == 200, y.text
    gizli_olay = y.json()["id"]
    # İzinsiz üye: 403 hesap_izni_yok.
    y = await istemci.get(f"{M}/dosyalar", headers=_b(yabanci, s))
    assert y.status_code == 403 and _kod(y) == "hesap_izni_yok"
    # Sorumlu avukat gizli dosyayı görür; katip (hukuk izni var, sorumlu değil) görmez — varlığı da sızmaz.
    gor = {d["id"] for d in (await istemci.get(f"{M}/dosyalar", headers=_b(avukat, s))).json()["items"]}
    assert gor == {acik["id"], gizli["id"]}
    gor = {d["id"] for d in (await istemci.get(f"{M}/dosyalar", headers=_b(katip, s))).json()["items"]}
    assert gor == {acik["id"]}
    for yol in (f"{M}/dosyalar/{gizli['id']}", f"{M}/dosyalar/{gizli['id']}/ekler", f"{M}/dosyalar/{gizli['id']}/zaman"):
        assert (await istemci.get(yol, headers=_b(katip, s))).status_code == 404, yol
    assert (await istemci.put(f"{M}/olaylar/{gizli_olay}", json={"tamamlandi": True}, headers=_b(katip, s))).status_code == 404
    olaylar = (await istemci.get(f"{M}/olaylar", headers=_b(katip, s))).json()["items"]
    assert all(o["id"] != gizli_olay for o in olaylar)
    assert (await istemci.get(f"{M}/muvekkiller/{m['id']}", headers=_b(katip, s))).json()["dosyalar"][0]["id"] == acik["id"]
    # Hesap sahibi her şeyi görür.
    assert len((await istemci.get(f"{M}/dosyalar", headers=bs)).json()["items"]) == 2
    # Katip bir dosyayı kendini sorumlu yapmadan gizleyemez (kendi erişimini kaybederdi).
    y = await istemci.put(f"{M}/dosyalar/{acik['id']}", json={"gizli": True}, headers=_b(katip, s))
    assert y.status_code == 409 and _kod(y) == "gizli_erisim_kaybi"
    y = await istemci.put(f"{M}/dosyalar/{acik['id']}", json={"gizli": True, "sorumlu_email": katip}, headers=_b(katip, s))
    assert y.status_code == 200 and y.json()["dosya"]["gizli"] is True
    # Sorumlu yalnız hukuk izni olan biri olabilir.
    y = await istemci.put(f"{M}/dosyalar/{acik['id']}", json={"sorumlu_email": yabanci}, headers=bs)
    assert y.status_code == 400 and _kod(y) == "sorumlu_gecersiz"


# ===========================================================================
# Çıkar çatışması
# ===========================================================================
async def test_cikar_catismasi_uyari_listesi(istemci, yonetici_basligi, db_oturumu):
    s, bs = await _buro(istemci, yonetici_basligi)
    katip = _e("katip")
    await _uye(db_oturumu, s, katip, ["hukuk"])
    m1 = (await _muvekkil(istemci, bs, ad="Yılmaz İnşaat A.Ş.", tur="sirket", vergi_no="1234567890"))["muvekkil"]
    r = await _dosya(istemci, bs, m1["id"], karsi_taraflar=[{"ad": "ŞAHİN TEKSTİL LTD. ŞTİ.", "vergi_no": "9876543210", "vekil": "Av. X"}])
    assert r["catisma"] == []
    # Yeni müvekkil eski bir dosyanın KARŞI TARAFI → olası çatışma (Türkçe harf + büyük/küçük + şirket eki normalize).
    r = await _muvekkil(istemci, bs, ad="Şahin Tekstil")
    assert [(c["rol"], c["eslesme"], c["onem"]) for c in r["catisma"]] == [("karsi_taraf", "tam", "catisma")]
    assert r["catisma"][0]["muvekkil_ad"] == "Yılmaz İnşaat A.Ş." and r["catisma"][0]["dosya_id"]
    # Vergi no eşleşmesi (ad farklı olsa da).
    r = (await istemci.post(f"{M}/catisma", json={"ad": "Başka Ad", "vergi_no": "987 654 3210", "rol": "muvekkil"}, headers=bs)).json()
    assert [(c["rol"], c["eslesme"]) for c in r["items"]] == [("karsi_taraf", "vergi_no")]
    # Yeni dosyada karşı taraf mevcut bir MÜVEKKİL → olası çatışma; kaydı engellemez.
    m2 = r2 = None
    m2 = (await _muvekkil(istemci, bs, ad="Ali Veli"))["muvekkil"]
    r2 = await _dosya(istemci, bs, m2["id"], karsi_taraflar=[{"ad": "YILMAZ İNŞAAT"}])
    assert r2["dosya"]["id"] and any(c["rol"] == "muvekkil" and c["onem"] == "catisma" and c["muvekkil_id"] == m1["id"]
                                     for c in r2["catisma"])
    # Eşleşme yoksa boş liste.
    assert (await istemci.post(f"{M}/catisma", json={"ad": "Kimsenin Adı", "rol": "muvekkil"}, headers=bs)).json()["items"] == []
    # Gizli dosyadaki karşı taraf: yetkisiz ekip üyesine eşleşme VAR ama ayrıntısız (sır sızmasın, çatışma kaçmasın).
    await _dosya(istemci, bs, m2["id"], gizli=True, karsi_taraflar=[{"ad": "Gizli Holding A.Ş."}])
    r = (await istemci.post(f"{M}/catisma", json={"ad": "Gizli Holding", "rol": "muvekkil"}, headers=_b(katip, s))).json()["items"]
    assert len(r) == 1 and r[0]["gizli"] is True and "ad" not in r[0] and "dosya_baslik" not in r[0]
    r = (await istemci.post(f"{M}/catisma", json={"ad": "Gizli Holding", "rol": "muvekkil"}, headers=bs)).json()["items"]
    assert r[0]["gizli"] is False and r[0]["ad"] == "Gizli Holding A.Ş."


# ===========================================================================
# Gizlilik: yönetici uçları, denetim, bildirim, çöp kutusu
# ===========================================================================
async def test_yonetici_uclari_icerik_dondurmez(istemci, yonetici_basligi, db_oturumu):
    from models.audit_log import AuditLog
    from models.cop_kutusu import CopKutusu
    from models.notifications import Notifications
    from services import hukuk_kayit as k

    s, bs = await _buro(istemci, yonetici_basligi)
    SIRLAR = ["Zeynep Sırlıoğlu", "SIR-NOTU-77", "2026/987 E.", "Karşı Taraf Gizlioğlu", "dilekce-sir.pdf",
              "11122233344", "zeynep@sir.example", "Boşanma ve velayet", "PORTAL-MESAJI-SIR"]
    m = (await _muvekkil(istemci, bs, ad=SIRLAR[0], vergi_no=SIRLAR[5], eposta=SIRLAR[6], notlar=SIRLAR[1]))["muvekkil"]
    d = (await _dosya(istemci, bs, m["id"], esas_no=SIRLAR[2], konu=SIRLAR[7], notlar=SIRLAR[1],
                      karsi_taraflar=[{"ad": SIRLAR[3]}], portal_acik=True))["dosya"]
    y = await istemci.post(f"{M}/dosyalar/{d['id']}/ekler", files={"dosya": (SIRLAR[4], PDF, "application/pdf")},
                           data={"muvekkile_gorunur": "true"}, headers=bs)
    assert y.status_code == 200, y.text
    await istemci.post(f"{M}/olaylar", json={"dosya_id": d["id"], "tur": "kesin_sure", "tarih": "2026-10-09", "baslik": SIRLAR[1]}, headers=bs)
    await istemci.post(f"{M}/dosyalar/{d['id']}/masraflar", json={"tur": "harc", "tutar": "100", "aciklama": SIRLAR[1]}, headers=bs)
    jeton = (await istemci.post(f"{M}/muvekkiller/{m['id']}/portal", headers=bs)).json()["baglanti"].rsplit("/", 1)[1]
    y = await istemci.post(f"{A}/muvekkil/{jeton}/mesaj", json={"metin": SIRLAR[8]}, headers={"X-MK-Istemci-IP": "198.51.100.9"})
    assert y.status_code == 200, y.text

    # 1) Yönetici uçları yalnız META: alanlar sabit, değerler sayı; hiçbir sır metni yok.
    for yol in (f"{Y}/ozet", f"{Y}/hesap/{s}"):
        y = await istemci.get(yol, headers=yonetici_basligi)
        assert y.status_code == 200, (yol, y.text)
        metin = y.text
        for sir in SIRLAR:
            assert sir not in metin, (yol, sir)
    oz = (await istemci.get(f"{Y}/hesap/{s}", headers=yonetici_basligi)).json()
    assert set(oz) == set(k.META_ALANLARI)
    assert (oz["muvekkil_sayisi"], oz["dosya_sayisi"], oz["acik_dosya"], oz["yaklasan_sure"], oz["ek_sayisi"],
            oz["portal_bagli_muvekkil"]) == (1, 1, 1, 1, 1, 1) and oz["depolama_bayt"] == len(PDF)
    tum = (await istemci.get(f"{Y}/ozet", headers=yonetici_basligi)).json()
    assert tum["gizlilik"] == "yalniz_meta" and any(h["hesap_email"] == s for h in tum["hesaplar"])
    # 2) Yönetici, müşteri uçlarında X-MK-Hesap ile müşterinin verisine ULAŞAMAZ (başlık yöneticide yok sayılır).
    y = await istemci.get(f"{M}/dosyalar", headers={**yonetici_basligi, "X-MK-Hesap": s})
    assert y.status_code == 200 and y.json()["items"] == []
    assert (await istemci.get(f"{M}/dosyalar/{d['id']}", headers={**yonetici_basligi, "X-MK-Hesap": s})).status_code == 404
    # 3) Denetim kaydı yazıldı (kim/ne zaman/hangi alan) ama değerler ve etiket maskeli; portal jetonu yolda yok.
    satirlar = (await db_oturumu.execute(select(AuditLog).where(AuditLog.tablo.like("hukuk_%")))).scalars().all()
    tablolar = {x.tablo for x in satirlar}
    assert {"hukuk_muvekkilleri", "hukuk_dosyalari", "hukuk_ekleri", "hukuk_olaylari", "hukuk_masraflari", "hukuk_mesajlari"} <= tablolar
    dosya_satiri = next(x for x in satirlar if x.tablo == "hukuk_dosyalari" and x.islem == "olustur" and x.kayit_id == str(d["id"]))
    assert "esas_no" in json.loads(dosya_satiri.degisiklik_json) and json.loads(dosya_satiri.degisiklik_json)["esas_no"] == [None, "***"]
    for x in satirlar:
        birlesik = " ".join(str(v or "") for v in (x.ozet, x.degisiklik_json, x.istek_yolu))
        for sir in SIRLAR:
            assert sir not in birlesik, (x.tablo, sir)
        assert jeton not in birlesik
    # 4) Bildirim satırları (yönetici de okuyabilir) içeriksiz.
    bild = (await db_oturumu.execute(select(Notifications).where(Notifications.event_type.like("hukuk_%")))).scalars().all()
    assert bild and all(sir not in f"{n.title} {n.body}" for n in bild for sir in SIRLAR)
    # 5) Silme ortak çöp kutusuna (yöneticinin tam kopya gördüğü yer) DÜŞMEZ; modül içi "silinenler".
    assert (await istemci.delete(f"{M}/dosyalar/{d['id']}", headers=bs)).status_code == 200
    assert (await db_oturumu.execute(select(func.count(CopKutusu.id)).where(CopKutusu.tablo.like("hukuk_%")))).scalar() == 0
    # 6) Ajansın gelen kutusunda müvekkil mesajı yok.
    y = await istemci.get("/api/v1/gelen-kutusu", headers=yonetici_basligi)
    assert y.status_code == 200 and SIRLAR[8] not in y.text and "hukuk" not in json.dumps(y.json().get("kaynaklar", {}))


# ===========================================================================
# Dosya sınırı, silinenler
# ===========================================================================
async def test_dosya_siniri_ve_silinenler(istemci, yonetici_basligi, db_oturumu, _ortam):
    from models.hukuk import HukukDosyalari, HukukMuvekkilleri, HukukZamanKayitlari
    from services import hukuk_kayit as k

    s, bs = await _buro(istemci, yonetici_basligi, dosya_siniri=1)
    m = (await _muvekkil(istemci, bs))["muvekkil"]
    d1 = (await _dosya(istemci, bs, m["id"]))["dosya"]
    y = await istemci.post(f"{M}/dosyalar", json={"muvekkil_id": m["id"]}, headers=bs)
    assert y.status_code == 409 and y.json()["detail"] == {"kod": "dosya_siniri", "sinir": 1}
    # Kapanan dosya sınırı tüketmez.
    await _dosya(istemci, bs, m["id"], durum="kapandi")
    assert (await istemci.put(f"{M}/dosyalar/{d1['id']}", json={"durum": "kapandi"}, headers=bs)).status_code == 200
    d3 = (await _dosya(istemci, bs, m["id"]))["dosya"]
    await istemci.post(f"{M}/dosyalar/{d3['id']}/zaman", json={"sure_dk": 30}, headers=bs)
    # Müvekkilin açık dosyası varken müvekkil silinmez.
    y = await istemci.delete(f"{M}/muvekkiller/{m['id']}", headers=bs)
    assert y.status_code == 409 and _kod(y) == "muvekkilin_dosyasi_var"
    # Dosya silinenlere düşer, listede yok; geri alınır.
    assert (await istemci.delete(f"{M}/dosyalar/{d3['id']}", headers=bs)).json()["geri_alinabilir_gun"] == 30
    assert all(x["id"] != d3["id"] for x in (await istemci.get(f"{M}/dosyalar", headers=bs)).json()["items"])
    assert [x["id"] for x in (await istemci.get(f"{M}/silinenler", headers=bs)).json()["dosyalar"]] == [d3["id"]]
    assert (await istemci.post(f"{M}/dosyalar/{d3['id']}/geri-al", headers=bs)).status_code == 200
    # Hepsini sil → müvekkil silinebilir; 30 gün sonra kalıcı silinir (bağlı kayıtlarla).
    for x in (await istemci.get(f"{M}/dosyalar", headers=bs)).json()["items"]:
        await istemci.delete(f"{M}/dosyalar/{x['id']}", headers=bs)
    assert (await istemci.delete(f"{M}/muvekkiller/{m['id']}", headers=bs)).status_code == 200
    # (Oturumdaki başka testlerin büroları da aynı veritabanında: sayımlar bu hesaba göre.)
    async def kalan():
        return ((await db_oturumu.execute(select(func.count(HukukDosyalari.id)).where(HukukDosyalari.hesap_email == s))).scalar(),
                (await db_oturumu.execute(select(func.count(HukukMuvekkilleri.id)).where(HukukMuvekkilleri.hesap_email == s))).scalar())

    await k.silinenleri_temizle(db_oturumu, SIMDI + timedelta(days=29))
    assert await kalan() == (3, 1)
    sonuc = await k.silinenleri_temizle(db_oturumu, SIMDI + timedelta(days=31))
    assert sonuc["dosya"] >= 3 and sonuc["muvekkil"] >= 1
    assert (await db_oturumu.execute(select(func.count(HukukDosyalari.id)).where(HukukDosyalari.hesap_email == s))).scalar() == 0
    assert (await db_oturumu.execute(select(func.count(HukukMuvekkilleri.id)).where(HukukMuvekkilleri.hesap_email == s))).scalar() == 0
    assert (await db_oturumu.execute(select(func.count(HukukZamanKayitlari.id)).where(HukukZamanKayitlari.hesap_email == s))).scalar() == 0


# ===========================================================================
# Takvim, süre hesaplayıcı ucu, ICS, tatiller
# ===========================================================================
async def test_tatiller_tohumlanir_ve_sure_ucu_hesabin_tatillerini_kullanir(istemci, yonetici_basligi):
    s, bs = await _buro(istemci, yonetici_basligi)
    t = (await istemci.get(f"{M}/tatiller", headers=bs)).json()["items"]
    assert len(t) == 8 and all(x["tur"] == "sabit" and x["tekrar"] for x in t)
    assert any(x["ay_gun"] == "10-29" for x in t) and next(x for x in t if x["ay_gun"] == "10-28")["yarim"] is True
    # Sabit tatil silinirse yeniden tohumlanmaz (kullanıcının kararı).
    yilbasi = next(x for x in t if x["ay_gun"] == "01-01")
    assert (await istemci.delete(f"{M}/tatiller/{yilbasi['id']}", headers=bs)).status_code == 200
    assert len((await istemci.get(f"{M}/tatiller", headers=bs)).json()["items"]) == 7
    # Uç hesabın tatillerini kullanır: 22 Ekim + 7 gün → 29 Ekim tatil → 30 Ekim.
    y = await istemci.post(f"{M}/sure-hesapla", json={"baslangic": "2026-10-22", "miktar": 7, "birim": "gun"}, headers=bs)
    assert y.status_code == 200 and y.json()["son_gun"] == "2026-10-30" and y.json()["adli_tatil"] is True
    # Kullanıcı dini bayram ekler (arayüz bunu söylüyor).
    y = await istemci.post(f"{M}/tatiller", json={"ad": "Kurban Bayramı", "tarih": "2027-05-16", "bitis": "2027-05-19", "tur": "dini"}, headers=bs)
    assert y.status_code == 200
    y = await istemci.post(f"{M}/sure-hesapla", json={"baslangic": "2027-05-10", "miktar": 7, "birim": "gun", "adli_tatil": False}, headers=bs)
    assert y.json()["son_gun"] == "2027-05-20"
    y = await istemci.post(f"{M}/sure-hesapla", json={"baslangic": "2027-05-10", "miktar": 0, "birim": "gun"}, headers=bs)
    assert y.status_code == 400 and _kod(y) == "aralik_disi"
    # Ayarlardan adli tatil varsayılanı ve aralığı değişir.
    y = await istemci.put(f"{M}/ayarlar", json={"adli_tatil_varsayilan": False, "adli_tatil_bas": "07-15", "buro_adi": "Şahin Hukuk"}, headers=bs)
    assert y.status_code == 200 and y.json()["adli_tatil_bas"] == "07-15"
    y = await istemci.post(f"{M}/sure-hesapla", json={"baslangic": "2026-07-06", "miktar": 14, "birim": "gun"}, headers=bs)
    assert y.json()["adli_tatil"] is False and y.json()["uyarilar"] == ["adli_tatil_icinde"]
    y = await istemci.put(f"{M}/ayarlar", json={"adli_tatil_bas": "13-40"}, headers=bs)
    assert y.status_code == 400 and _kod(y) == "tarih_gecersiz"


async def test_kesin_sure_olayi_sunucuda_hesaplanir_ve_ics(istemci, yonetici_basligi, db_oturumu):
    s, bs = await _buro(istemci, yonetici_basligi)
    avukat = _e("avukat")
    await _uye(db_oturumu, s, avukat, ["hukuk"])
    m = (await _muvekkil(istemci, bs))["muvekkil"]
    d = (await _dosya(istemci, bs, m["id"], esas_no="2026/55", mahkeme="İstanbul 3. Asliye Hukuk", sorumlu_email=avukat))["dosya"]
    # İstemcinin gönderdiği "adımlar"a güvenilmez: girdi sunucuda yeniden hesaplanır, tarih verilmezse son gün.
    y = await istemci.post(f"{M}/olaylar", json={"dosya_id": d["id"], "tur": "kesin_sure", "baslik": "Cevap dilekçesi",
                                                 "hesap": {"baslangic": "2026-10-22", "miktar": 7, "birim": "gun", "son_gun": "2099-01-01"}},
                           headers=bs)
    assert y.status_code == 200, y.text
    o = y.json()
    assert o["tarih"] == "2026-10-30" and o["hesap"]["son_gun"] == "2026-10-30" and o["kalan_gun"] == 25
    await istemci.post(f"{M}/olaylar", json={"dosya_id": d["id"], "tur": "durusma", "tarih": "2026-11-03", "saat": "10:30",
                                             "yer": "Salon 4"}, headers=bs)
    await istemci.post(f"{M}/olaylar", json={"tur": "gorev", "tarih": "2026-10-07", "baslik": "Sahibin işi"}, headers=bs)
    y = await istemci.get(f"{M}/olaylar", params={"bas": "2026-10-01", "bit": "2026-11-30"}, headers=bs)
    assert [x["tur"] for x in y.json()["items"]] == ["gorev", "kesin_sure", "durusma"]
    # Sorumlu avukat başına ICS: dosyanın sorumlusu avukat → iki olay; sahibin genel görevi yok.
    y = await istemci.get(f"{M}/takvim.ics", params={"sorumlu": avukat}, headers=bs)
    assert y.status_code == 200 and y.headers["content-type"].startswith("text/calendar")
    ics = y.text
    assert ics.count("BEGIN:VEVENT") == 2 and "Sahibin işi" not in ics and "Cevap dilekçesi" in ics
    assert "DTSTART;VALUE=DATE:20261030" in ics and "DTSTART:20261103T073000Z" in ics and "LOCATION:Salon 4" in ics
    y = await istemci.get(f"{M}/takvim.ics", params={"sorumlu": s}, headers=bs)
    assert y.text.count("BEGIN:VEVENT") == 1 and "Sahibin işi" in y.text


# ===========================================================================
# Zaman, masraf, makbuz, PDF
# ===========================================================================
async def test_zaman_masraf_ve_pdf_turkce(istemci, yonetici_basligi):
    from services.pdf_belge import pdf_metni

    s, bs = await _buro(istemci, yonetici_basligi)
    await istemci.put(f"{M}/ayarlar", json={"buro_adi": "Şahin & Güler Hukuk Bürosu"}, headers=bs)
    m = (await _muvekkil(istemci, bs, ad="Çağrı Öztürk"))["muvekkil"]
    d = (await _dosya(istemci, bs, m["id"], dosya_no="B-17", konu="İşçilik alacağı", mahkeme="İzmir 2. İş Mahkemesi"))["dosya"]
    for g in ({"sure_dk": 90, "aciklama": "Dilekçe hazırlığı", "faturalanabilir": True},
              {"sure_dk": 30, "aciklama": "Telefon görüşmesi", "faturalanabilir": False}):
        assert (await istemci.post(f"{M}/dosyalar/{d['id']}/zaman", json=g, headers=bs)).status_code == 200
    z = (await istemci.get(f"{M}/dosyalar/{d['id']}/zaman", headers=bs)).json()
    assert z["toplam_dk"] == 120 and z["faturalanabilir_dk"] == 90
    y = await istemci.post(f"{M}/dosyalar/{d['id']}/masraflar", json={"tur": "harc", "tutar": "1.250,50", "aciklama": "Başvuru harcı"}, headers=bs)
    assert y.status_code == 200 and y.json()["tutar_kurus"] == 125050
    harc = y.json()["id"]
    await istemci.post(f"{M}/dosyalar/{d['id']}/masraflar", json={"tur": "tebligat", "tutar": 49.5, "avanstan": True}, headers=bs)
    y = await istemci.post(f"{M}/dosyalar/{d['id']}/masraflar", json={"tur": "yol", "tutar": "-5"}, headers=bs)
    assert y.status_code == 400 and _kod(y) == "aralik_disi"
    y = await istemci.post(f"{M}/dosyalar/{d['id']}/masraflar/{harc}/makbuz", files={"dosya": ("makbuz.pdf", PDF, "application/pdf")}, headers=bs)
    assert y.status_code == 200 and y.json()["masraf"]["makbuz_ek_id"] == y.json()["ek"]["id"] and y.json()["ek"]["tip"] == "makbuz"
    ms_ = (await istemci.get(f"{M}/dosyalar/{d['id']}/masraflar", headers=bs)).json()
    assert ms_["toplamlar"] == [{"para_birimi": "TRY", "toplam_kurus": 130000, "avans_kurus": 4950}]
    y = await istemci.get(f"{M}/dosyalar/{d['id']}/dokum.pdf", headers=bs)
    assert y.status_code == 200 and y.content[:5] == b"%PDF-" and "dokum-B-17.pdf" in y.headers["content-disposition"]
    metin = pdf_metni(y.content)
    # Türkçe harfler (ş, ğ, ı, İ, ç, ö, ü) PDF'te doğru: sitenin Türkçe destekli yazı tipi gömülü.
    for parca in ("Şahin & Güler Hukuk Bürosu", "Çağrı Öztürk", "Masraf ve zaman dökümü", "Başvuru harcı", "İşçilik alacağı",
                  "1.250,50", "Zaman kayıtları", "Dilekçe hazırlığı", "Avanstan karşılanan"):
        assert parca in metin, parca
    # Silinen masrafın makbuzu da gider.
    assert (await istemci.delete(f"{M}/dosyalar/{d['id']}/masraflar/{harc}", headers=bs)).status_code == 200
    assert [e["tip"] for e in (await istemci.get(f"{M}/dosyalar/{d['id']}/ekler", headers=bs)).json()["items"]] == []


# ===========================================================================
# Müvekkil portalı
# ===========================================================================
async def test_muvekkil_portali_yalniz_isaretli_alanlar(istemci, yonetici_basligi, db_oturumu):
    from models.notifications import Notifications

    s, bs = await _buro(istemci, yonetici_basligi)
    await istemci.put(f"{M}/ayarlar", json={"buro_adi": "Yılmaz Hukuk"}, headers=bs)
    m = (await _muvekkil(istemci, bs, ad="Elif Kaya", notlar="İÇ-NOT-1"))["muvekkil"]
    d = (await _dosya(istemci, bs, m["id"], konu="Tazminat davası", esas_no="2026/321", mahkeme="Ankara 5. Asliye",
                      notlar="İÇ-NOT-2", karsi_taraflar=[{"ad": "Karşı Şirket A.Ş."}], portal_acik=True,
                      portal_alanlari={"konu": True, "durum": True, "durusma": True, "belgeler": True, "masraf": False, "not": True},
                      muvekkil_notu="Bilirkişi raporu bekleniyor."))["dosya"]
    gizli_kalan = (await _dosya(istemci, bs, m["id"], konu="Portalda olmayan dosya"))["dosya"]
    await istemci.post(f"{M}/olaylar", json={"dosya_id": d["id"], "tur": "durusma", "tarih": "2026-11-12", "saat": "09:40", "yer": "Salon 2",
                                             "notlar": "İÇ-NOT-3"}, headers=bs)
    paylasilan = (await istemci.post(f"{M}/dosyalar/{d['id']}/ekler", files={"dosya": ("bilirkisi.pdf", PDF, "application/pdf")},
                                     data={"muvekkile_gorunur": "true"}, headers=bs)).json()
    ic = (await istemci.post(f"{M}/dosyalar/{d['id']}/ekler", files={"dosya": ("ic-strateji.pdf", PDF, "application/pdf")}, headers=bs)).json()
    await istemci.post(f"{M}/dosyalar/{d['id']}/zaman", json={"sure_dk": 60, "aciklama": "İÇ-NOT-4"}, headers=bs)
    await istemci.post(f"{M}/dosyalar/{d['id']}/masraflar", json={"tur": "harc", "tutar": 100}, headers=bs)
    # Portal kapalıyken 404 (bağlantı yok) → oluştur.
    r = (await istemci.post(f"{M}/muvekkiller/{m['id']}/portal", headers=bs)).json()
    assert r["baglanti"].startswith("http") and "/hukuk/muvekkil/" in r["baglanti"]
    jeton = r["baglanti"].rsplit("/", 1)[1]
    y = await istemci.get(f"{A}/muvekkil/{jeton}")
    assert y.status_code == 200, y.text
    assert y.headers["x-robots-tag"] == "noindex, nofollow" and y.headers["referrer-policy"] == "no-referrer"
    assert y.headers["cache-control"] == "no-store"
    v = y.json()
    assert v["buro_adi"] == "Yılmaz Hukuk" and v["muvekkil"] == {"ad": "Elif Kaya"}
    assert [x["id"] for x in v["dosyalar"]] == [d["id"]]  # portalı kapalı dosya yok
    pd = v["dosyalar"][0]
    assert pd["konu"] == "Tazminat davası" and pd["durum"] == "acik" and pd["not"] == "Bilirkişi raporu bekleniyor."
    assert pd["sonraki_durusma"] == {"tarih": "2026-11-12", "saat": "09:40"}
    assert [b["id"] for b in pd["belgeler"]] == [paylasilan["id"]] and "masraf" not in pd
    metin = y.text
    for sir in ("İÇ-NOT", "2026/321", "Ankara 5. Asliye", "Karşı Şirket", "Salon 2", "ic-strateji", "Portalda olmayan"):
        assert sir not in metin, sir
    # Paylaşılan belge iner; paylaşılmayan 404.
    y = await istemci.get(f"{A}/muvekkil/{jeton}/dosya/{d['id']}/ek/{paylasilan['id']}")
    assert y.status_code == 200 and y.content == PDF and y.headers["x-robots-tag"] == "noindex, nofollow"
    assert (await istemci.get(f"{A}/muvekkil/{jeton}/dosya/{d['id']}/ek/{ic['id']}")).status_code == 404
    assert (await istemci.get(f"{A}/muvekkil/{jeton}/dosya/{gizli_kalan['id']}/ek/{paylasilan['id']}")).status_code == 404
    # Masraf alanı kapalı → PDF 404; açılınca yalnız masraf (zaman YOK).
    assert (await istemci.get(f"{A}/muvekkil/{jeton}/dosya/{d['id']}/masraf.pdf")).status_code == 404
    await istemci.put(f"{M}/dosyalar/{d['id']}", json={"portal_alanlari": {"masraf": True, "belgeler": False}}, headers=bs)
    v = (await istemci.get(f"{A}/muvekkil/{jeton}")).json()["dosyalar"][0]
    assert v["masraf"]["toplamlar"][0]["toplam_kurus"] == 10000 and "belgeler" not in v
    y = await istemci.get(f"{A}/muvekkil/{jeton}/dosya/{d['id']}/masraf.pdf")
    assert y.status_code == 200 and y.content[:5] == b"%PDF-"
    from services.pdf_belge import pdf_metni

    assert "Masraf dökümü" in pdf_metni(y.content) and "Zaman kayıtları" not in pdf_metni(y.content)
    # Mesaj: büroya İÇERİKSİZ panel bildirimi; panelde görünür, büro yanıtı portalda.
    y = await istemci.post(f"{A}/muvekkil/{jeton}/mesaj", json={"metin": "Duruşmaya gelmem gerekiyor mu?", "dosya_id": d["id"]},
                           headers={"X-MK-Istemci-IP": "198.51.100.20"})
    assert y.status_code == 200, y.text
    bild = (await db_oturumu.execute(select(Notifications).where(Notifications.recipient_email == s,
                                                                 Notifications.event_type == "hukuk_portal_mesaj"))).scalars().all()
    assert bild and "Duruşmaya" not in bild[0].body and "Elif" not in bild[0].title
    mesajlar = (await istemci.get(f"{M}/mesajlar", headers=bs)).json()["items"]
    assert mesajlar[-1]["metin"] == "Duruşmaya gelmem gerekiyor mu?" and mesajlar[-1]["okundu"] is False
    assert (await istemci.get(f"{M}/meta", headers=bs)).json()["okunmamis_mesaj"] == 1
    await istemci.post(f"{M}/mesajlar/okundu", json={"muvekkil_id": m["id"]}, headers=bs)
    await istemci.post(f"{M}/mesajlar", json={"muvekkil_id": m["id"], "metin": "Evet, saat 09:30'da adliyede olun."}, headers=bs)
    v = (await istemci.get(f"{A}/muvekkil/{jeton}")).json()
    assert [x["yon"] for x in v["mesajlar"]] == ["muvekkil", "buro"]
    # Yenile → eski bağlantı 404; iptal → 410; modül kapanınca 410.
    yeni = (await istemci.post(f"{M}/muvekkiller/{m['id']}/portal", headers=bs)).json()["baglanti"].rsplit("/", 1)[1]
    assert (await istemci.get(f"{A}/muvekkil/{jeton}")).status_code == 404
    assert (await istemci.get(f"{A}/muvekkil/{yeni}")).status_code == 200
    await _modul(istemci, yonetici_basligi, s, acik=False)
    assert (await istemci.get(f"{A}/muvekkil/{yeni}")).status_code == 410
    await _modul(istemci, yonetici_basligi, s)
    assert (await istemci.delete(f"{M}/muvekkiller/{m['id']}/portal", headers=bs)).status_code == 200
    y = await istemci.get(f"{A}/muvekkil/{yeni}")
    assert y.status_code == 410 and _kod(y) == "baglanti_kapali"
    y = await istemci.get(f"{A}/muvekkil/12-1-{'a' * 32}")
    assert y.status_code == 404
    # Hata yanıtları da dizine kapalı, Referer'sız, ara belleksiz.
    assert y.headers["x-robots-tag"] == "noindex, nofollow" and y.headers["referrer-policy"] == "no-referrer"
    assert "no-store" in y.headers["cache-control"]


async def test_portal_mesaj_hiz_siniri(istemci, yonetici_basligi):
    s, bs = await _buro(istemci, yonetici_basligi)
    m = (await _muvekkil(istemci, bs))["muvekkil"]
    jeton = (await istemci.post(f"{M}/muvekkiller/{m['id']}/portal", headers=bs)).json()["baglanti"].rsplit("/", 1)[1]
    kodlar = []
    for i in range(7):
        y = await istemci.post(f"{A}/muvekkil/{jeton}/mesaj", json={"metin": f"Mesaj {i}"}, headers={"X-MK-Istemci-IP": f"203.0.113.{i + 1}"})
        kodlar.append(y.status_code)
    assert kodlar[:5] == [200] * 5 and kodlar[5] == 429
    y = await istemci.post(f"{A}/muvekkil/{jeton}/mesaj", json={"metin": "  "}, headers={"X-MK-Istemci-IP": "203.0.113.99"})
    assert y.status_code in (400, 429)


# ===========================================================================
# Zamanlı hatırlatma — BİR KEZ
# ===========================================================================
async def test_zamanli_hatirlatma_bir_kez(istemci, yonetici_basligi, db_oturumu, _ortam):
    from models.hukuk import HukukHatirlatmalari
    from models.notifications import Notifications
    from services import hukuk_kayit as k
    from services import zamanli

    assert "hukuk_bakimi" in zamanli.GOREV_ADLARI
    s, bs = await _buro(istemci, yonetici_basligi)
    avukat = _e("avukat")
    await _uye(db_oturumu, s, avukat, ["hukuk"])
    m = (await _muvekkil(istemci, bs))["muvekkil"]
    d = (await _dosya(istemci, bs, m["id"], esas_no="2026/444", sorumlu_email=avukat))["dosya"]
    # 8 Ekim duruşma (3 gün kala) ve 7 Ekim kesin süre (2 gün kala: 7 günlük eşik kaçırılmış sayılır).
    o1 = (await istemci.post(f"{M}/olaylar", json={"dosya_id": d["id"], "tur": "durusma", "tarih": "2026-10-08", "saat": "10:00"}, headers=bs)).json()
    o2 = (await istemci.post(f"{M}/olaylar", json={"dosya_id": d["id"], "tur": "kesin_sure", "tarih": "2026-10-07"}, headers=bs)).json()

    async def bildirimler():
        # Oturumdaki başka testlerin büroları da aynı veritabanında: yalnız bu avukatın bildirimleri sayılır.
        return (await db_oturumu.execute(select(Notifications).where(Notifications.event_type == "hukuk_hatirlatma",
                                                                     Notifications.channel == "inapp",
                                                                     Notifications.recipient_email == avukat)
                                         .order_by(Notifications.id))).scalars().all()

    async def gonder(an):
        once = len(await bildirimler())
        await k.hatirlatmalari_gonder(db_oturumu, an)
        return len(await bildirimler()) - once

    assert await gonder(SIMDI) == 2
    b = await bildirimler()
    assert {x.title for x in b} == {"Yaklaşan duruşma: 3 gün kaldı", "Kesin süre yaklaşıyor: 2 gün kaldı"}
    # İçeriksiz: dosya no / müvekkil yok; bağlantı üyeye hesabıyla.
    assert all("2026/444" not in x.body and m["ad"] not in x.body for x in b) and "hesap=" in b[0].link
    # Aynı gün ikinci tur: yeni gönderim YOK (benzersiz kısıt + kayıt).
    assert await gonder(SIMDI + timedelta(hours=2)) == 0
    # Kesin sürede kaçırılmış 7 günlük eşik "geçildi" — sonradan gönderilmez.
    esikler = {(x.olay_id, x.esik): x.durum for x in (await db_oturumu.execute(select(HukukHatirlatmalari))).scalars().all()}
    assert esikler[(o2["id"], 3)] == "gonderildi" and esikler[(o2["id"], 7)] == "gecildi"
    # Ertesi gün (6 Ekim) — kesin süreye 1 gün: yeni eşik bir kez; duruşmaya 2 gün: 3'lük eşik zaten gitti.
    ertesi = SIMDI + timedelta(days=1)
    assert await gonder(ertesi) == 1
    assert await gonder(ertesi) == 0
    # 7 Ekim 07:00 İstanbul (sabah saatinden önce): aynı gün eşiği HENÜZ gitmez; 08:30'da bir kez gider.
    erken = datetime(2026, 10, 7, 4, 0, tzinfo=UTC)
    oncesi = len(await bildirimler())
    await k.hatirlatmalari_gonder(db_oturumu, erken)
    assert all("bugün" not in x.title for x in (await bildirimler())[oncesi:])
    gec = datetime(2026, 10, 7, 5, 30, tzinfo=UTC)
    await k.hatirlatmalari_gonder(db_oturumu, gec)
    await k.hatirlatmalari_gonder(db_oturumu, gec + timedelta(minutes=10))
    bugun = [x for x in await bildirimler() if x.title.endswith("bugün")]
    assert len(bugun) == 1 and bugun[0].ref_id == o2["id"]
    # Tamamlanan olaya hatırlatma gitmez; tarihi değişen olayın eşikleri sıfırlanır (yeni tarihe göre bir kez).
    await istemci.put(f"{M}/olaylar/{o1['id']}", json={"tamamlandi": True}, headers=bs)
    assert await gonder(datetime(2026, 10, 8, 6, 0, tzinfo=UTC)) == 0
    await istemci.put(f"{M}/olaylar/{o1['id']}", json={"tamamlandi": False, "tarih": "2026-10-15"}, headers=bs)
    assert await gonder(datetime(2026, 10, 8, 6, 0, tzinfo=UTC)) == 1
    # Modül kapalıysa hatırlatma yok.
    await _modul(istemci, yonetici_basligi, s, acik=False)
    assert await gonder(datetime(2026, 10, 12, 6, 0, tzinfo=UTC)) == 0


def test_hatirlatma_esigi_kurali():
    from services.hukuk_kayit import hatirlatma_esigi as e

    assert e(7, [7, 3, 1, 0], True) == 7
    assert e(5, [7, 3, 1, 0], True) == 7
    assert e(2, [7, 3, 1, 0], True) == 3
    assert e(0, [7, 3, 1, 0], False) is None
    assert e(0, [7, 3, 1, 0], True) == 0
    assert e(9, [7, 3, 1, 0], True) is None


# ===========================================================================
# Sektör paketi (reklam yasağı) + vitrin
# ===========================================================================
async def test_hukuk_sektor_paketi_hazir_ayarlar(istemci, yonetici_basligi, db_oturumu):
    from core import sektor_ayarlari as sa
    from core import sektor_paketleri as sp
    from models.belgeler import Belgeler
    from models.kartvizit import Kartvizitler, YorumSayfalari
    from models.randevu import RandevuSayfalari, RandevuTurleri

    p = sp.paket("hukuk_burosu")
    assert p.slug == "hukuk-burosu" and p.moduller == ("hukuk_burosu", "randevu", "dijital_kartvizit", "belgeler")
    assert "google_yorum_sayfasi" not in p.moduller and sa.paket_setleri("hukuk_burosu") == ["hukuk_burosu"]
    hs = sa.hazir_set("hukuk_burosu")
    assert hs.reklam_yasagi and sa.reklam_ifadeleri(hs) == [] and hs.yorum_tesekkur is None and hs.asistan is None
    # Tarayıcı gerçekten yakalıyor (kendini sınama).
    bozuk = sa.HazirSet("x", "hukuk_burosu", "Scale", reklam_yasagi=True,
                        belge=sa.BelgeSeti({"tr": "En iyi avukat", "en": "Best lawyer"}, {"tr": "Ücretsiz danışma, garanti", "en": "Free"}))
    assert len(sa.reklam_ifadeleri(bozuk)) >= 4
    e = _e("paket")
    y = await istemci.post(f"/api/v1/sektor-paketleri/musteri/{e}/uygula", json={
        "paket": "hukuk_burosu", "set": "hukuk_burosu", "dil": "tr", "isletme_adi": "Av. Deniz Ak", "adres": "Atatürk Cad. 10, Çankaya"},
        headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    assert "reklam_yasagi" in y.json()["uyarilar"] and "belge_taslak" in y.json()["uyarilar"]
    sayfa = (await db_oturumu.execute(select(RandevuSayfalari).where(RandevuSayfalari.hesap_email == e))).scalar_one()
    assert "dosya ayrıntısı" in sayfa.karsilama
    turler = (await db_oturumu.execute(select(RandevuTurleri).where(RandevuTurleri.sayfa_id == sayfa.id).order_by(RandevuTurleri.sira))).scalars().all()
    assert [(t.slug, t.sure_dk, t.konum_turu, t.aktif) for t in turler] == [
        ("ilk-gorusme", 30, "yuz_yuze", True), ("danismanlik", 60, "yuz_yuze", True), ("online-gorusme", 45, "jitsi", True)]
    kart = (await db_oturumu.execute(select(Kartvizitler).where(Kartvizitler.hesap_email == e))).scalar_one()
    assert kart.aktif is False and json.loads(kart.icerik)["hizmetler"] == []
    assert (await db_oturumu.execute(select(func.count(YorumSayfalari.id)).where(YorumSayfalari.hesap_email == e))).scalar() == 0
    belge = (await db_oturumu.execute(select(Belgeler).where(Belgeler.sahip_hesap == e))).scalar_one()
    assert belge.gorunurluk == "ekip" and belge.paylasildi_at is None and "Sık sorulan sorular" in belge.icerik
    # Müvekkil hukuk sekmesini kullanabiliyor (modül açıldı).
    assert (await istemci.get(f"{M}/meta", headers=_b(e))).status_code == 200
    # Hazır ayarları geri al: el değmemiş SSS taslağı silinir.
    uid = y.json()["uygulama"]["id"]
    y = await istemci.post(f"/api/v1/sektor-paketleri/uygulamalar/{uid}/hazir-geri-al", headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    assert (await db_oturumu.execute(select(func.count(Belgeler.id)).where(Belgeler.sahip_hesap == e))).scalar() == 0


def test_vitrin_metinleri_olgusal_ve_uyap_durust():
    from core import sektor_ayarlari as sa

    for dil in DILLER:
        mv = json.loads((ON_YUZ / "src/i18n/ek/modulVitrini" / f"{dil}.json").read_text(encoding="utf-8"))["modulVitrini"]
        for metin in sa.metinleri(mv["m"]["hukuk_burosu"]) + sa.metinleri(mv["p"]["hukuk_burosu"]) + sa.metinleri(mv["s"]["hukuk_burosu"]):
            if dil in ("tr", "en"):
                # Övgü / vaat / karşılaştırma yok (Avukatlık Kanunu m.55, TBB reklam yasağı).
                for desen in sa.REKLAM_IFADELERI:
                    assert not re.search(desen, metin, flags=re.IGNORECASE), (dil, desen, metin)
        assert "UYAP" in json.dumps(mv["m"]["hukuk_burosu"], ensure_ascii=False), dil
        assert len(mv["m"]["hukuk_burosu"]["ozet"]) <= 160
    tr = json.loads((ON_YUZ / "src/i18n/ek/hukuk/tr.json").read_text(encoding="utf-8"))["hukuk"]
    assert "kesin süreyi avukat doğrular" in tr["sure"]["not"] and "hukuki danışmanlık değildir" in tr["bilgilendirme"]
    assert "UYAP" in tr["uyap"] and "dini" in tr["ayar"]["tatil"]["tur"]["dini"].lower() or "bayram" in tr["ayar"]["tatil"]["aciklama"]


# ===========================================================================
# Pages Function, rotalar, i18n
# ===========================================================================
@pytest.mark.skipif(shutil.which("node") is None, reason="node yok")
def test_pages_fonksiyonu_node_testi():
    sonuc = subprocess.run(["node", "--test", "scripts/hukuk-fonksiyonu.test.mjs"], cwd=ON_YUZ, capture_output=True, text=True, timeout=120)
    assert sonuc.returncode == 0, sonuc.stdout[-3000:] + sonuc.stderr[-2000:]
    assert "# fail 0" in sonuc.stdout


def test_portal_rotasi_lazy_prerender_disi_noindex():
    app = (ON_YUZ / "src" / "App.tsx").read_text(encoding="utf-8")
    assert '<Route path="/hukuk/muvekkil/:jeton" element={<HukukPortal />} />' in app
    assert re.search(r"const HukukPortal = lazy\(\(\) => import\('\./pages/HukukPortal'\)\)", app)
    assert "'/hukuk/muvekkil/:jeton'" in (ON_YUZ / "scripts" / "check-routes.mjs").read_text(encoding="utf-8")
    site = (ON_YUZ / "prerender" / "site.js").read_text(encoding="utf-8")
    noindex = site[site.index("export const NOINDEX_ROUTES"):]
    assert "'/hukuk'" in noindex[: noindex.index("];")]
    assert "/hukuk" not in (ON_YUZ / "prerender" / "app.js").read_text(encoding="utf-8")
    sayfa = (ON_YUZ / "src" / "pages" / "HukukPortal.tsx").read_text(encoding="utf-8")
    assert "'noindex, nofollow'" in sayfa and "no-referrer" in sayfa
    fonk = (ON_YUZ / "functions" / "hukuk" / "[[yol]].js").read_text(encoding="utf-8")
    assert "noindex, nofollow" in fonk and "no-referrer" in fonk and "env.API_ORIGIN" not in fonk  # arka uca sorulmaz
    # Statik başlıklarda da (ikinci kat) dizine kapalı, Referer'sız, ara belleksiz.
    basliklar = (ON_YUZ / "public" / "_headers").read_text(encoding="utf-8")
    kural = basliklar[basliklar.index("\n/hukuk/*\n"):].split("\n\n")[0]
    assert "Referrer-Policy: no-referrer" in kural and "X-Robots-Tag: noindex, nofollow" in kural and "no-store" in kural


def _anahtarlar(d, on=""):
    for k_, v in d.items():
        if isinstance(v, dict):
            yield from _anahtarlar(v, f"{on}{k_}.")
        else:
            yield f"{on}{k_}", v


@pytest.mark.parametrize("paket", ["hukuk", "hukukPortal"])
def test_ek_paket_yedi_dilde_tutarli_ve_cevrilmis(paket):
    veriler = {d: json.loads((ON_YUZ / "src" / "i18n" / "ek" / paket / f"{d}.json").read_text(encoding="utf-8")) for d in DILLER}
    tr = dict(_anahtarlar(veriler["tr"]))
    assert tr
    for d in DILLER[1:]:
        diger = dict(_anahtarlar(veriler[d]))
        assert set(diger) == set(tr), d
        for k_, v in tr.items():
            assert isinstance(diger[k_], str) and diger[k_].strip(), (d, k_)
            assert sorted(set(re.findall(r"\{\{\s*(\w+)\s*\}\}", diger[k_]))) == sorted(set(re.findall(r"\{\{\s*(\w+)\s*\}\}", v))), (d, k_)
            assert "{{count}}" not in diger[k_]
        ayni = [k_ for k_, v in tr.items() if diger[k_] == v and len(v) > 4 and "{{" not in v]
        assert len(ayni) <= max(3, len(tr) // 50), (d, ayni[:8])


def test_kodda_kullanilan_anahtarlar_pakette_var():
    kaynak = ON_YUZ / "src"
    panel = [kaynak / "components" / "Hukuk.tsx", *sorted((kaynak / "components" / "hukuk").glob("*.tsx")), kaynak / "lib" / "hukuk.ts"]
    for paket, dosyalar in (("hukuk", panel), ("hukukPortal", [kaynak / "pages" / "HukukPortal.tsx"])):
        tr = {f"{paket}.{k_}" for k_, _ in _anahtarlar(json.loads((kaynak / "i18n" / "ek" / paket / "tr.json").read_text(encoding="utf-8"))[paket])}
        bulunan, sablon = set(), set()
        for f in dosyalar:
            m = f.read_text(encoding="utf-8")
            bulunan |= set(re.findall(r"""['"`](%s\.[A-Za-z0-9_.]+)['"`]""" % paket, m))
            sablon |= set(re.findall(r"`(%s\.[A-Za-z0-9_.]+)\.\$\{" % paket, m))
        assert sorted(k_ for k_ in bulunan if k_ not in tr) == [], paket
        assert sorted(s_ for s_ in sablon if not any(k_.startswith(s_ + ".") for k_ in tr)) == [], paket


def test_ortak_paketlerde_hukuk_satirlari_yedi_dilde():
    from services import zamanli

    assert "hukuk_bakimi" in zamanli.GOREV_ADLARI
    for dil in DILLER:
        ek = lambda p: json.loads((ON_YUZ / "src/i18n/ek" / p / f"{dil}.json").read_text(encoding="utf-8"))[p]  # noqa: E731
        assert ek("siteBakim")["zamanli"]["gorev"]["hukuk_bakimi"] and ek("siteBakim")["zamanli"]["ne"]["hukuk_bakimi"]
        assert ek("bildirim")["olay"]["hukuk_hatirlatma"] and ek("bildirim")["olay"]["hukuk_portal_mesaj"]
        assert ek("hesapEkibi")["izin"]["hukuk"] and ek("modul")["m"]["hukuk_burosu"]["ad"] and ek("modul")["ayar"]["dosya_siniri"]
        for tablo in ("hukuk_muvekkilleri", "hukuk_dosyalari", "hukuk_olaylari"):
            assert ek("denetim")["tablo"][tablo], (dil, tablo)
        ana = json.loads((ON_YUZ / "src/i18n" / f"{dil}.json").read_text(encoding="utf-8"))
        assert ana["ui"]["tabHukuk"].strip()
    assert json.loads((ON_YUZ / "src/i18n/ek/modul/tr.json").read_text(encoding="utf-8"))["modul"]["m"]["hukuk_burosu"]["ad"] == "Hukuk bürosu"
    assert json.loads((ON_YUZ / "src/i18n/ek/modul/en.json").read_text(encoding="utf-8"))["modul"]["m"]["hukuk_burosu"]["ad"] == "Law office"
