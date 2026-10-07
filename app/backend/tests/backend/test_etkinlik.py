"""Faz 6E — Etkinlik ve bilet: kayıt, QR bilet, kapıda okutma.

Kapsam: kapasite ve tür kontenjanı (eşzamanlı iki kayıtta aşım yok — kilit + veritabanı
benzersizliği), bekleme listesi davet akışı (24 saat, süre dolunca sıradaki), indirim kodu
(yüzde/tutar, kullanım sınırı, tür kısıtı, son tarih), satış tarih aralığı, gizli tür, QR imza
doğrulama (sahte/değiştirilmiş kod reddi), okutma idempotent ("zaten girdi"), farklı etkinlik ve
iptal edilen bilet reddi, görevli bağlantısının yalnız okutma yapabilmesi ve süresi/yenilenmesi,
ücretli bilette ödeme webhook'u → geçerli (Lemon taklidi), müşteri etkinliğinde ücretli bilet
oluşturulamaması, ICS/PDF/QR içeriği, bilgilendirme e-postası vs pazarlama (aktarım yalnız izinli),
Event JSON-LD (yalnız "arama motorlarında görünsün"), olay kataloğu (webhook + otomasyon), CRM yalnız
ajans etkinliği, müşteri izolasyonu + modül kapalıyken 403/410, ekip izni (`etkinlik_giris` yalnız
okutma), bal küpü, ödeme tutma süresi, teşekkür e-postası, liste sayfası, sınırlar, CSV, çöp kutusu.
"""

import asyncio
import hashlib
import hmac
import io
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from conftest import jeton_uret

Y = "/api/v1/etkinlik/yonetim"
M = "/api/v1/etkinliklerim"
A = "/api/v1/etkinlik"
MODUL = "/api/v1/moduller"
UTC = timezone.utc
#: Testlerin "şimdi"si: 5 Ekim 2026 Pazartesi 09:00 İstanbul.
SIMDI = datetime(2026, 10, 5, 6, 0, tzinfo=UTC)
BAS = "2026-11-05T10:00:00+03:00"
BIT = "2026-11-05T17:00:00+03:00"


def _e(on: str = "etkinlik") -> str:
    return f"{on}-{uuid.uuid4().hex[:8]}@etkinlik.dev"


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


def _z(ip: str | None = None) -> dict:
    return {"User-Agent": "Mozilla/5.0 Test", "X-MK-Istemci-IP": ip or f"198.51.100.{uuid.uuid4().int % 250 + 1}"}


@pytest.fixture(autouse=True)
def _ortam(monkeypatch):
    from routers import etkinlik as r
    from services import etkinlik as s
    from services import hesap_ekibi

    r.hiz_sinirlarini_temizle()
    hesap_ekibi.onbellegi_temizle()
    saat = {"an": SIMDI, "odeme": True}
    monkeypatch.setattr(s, "simdi", lambda: saat["an"])
    # Ödeme sağlayıcısı anahtarları testte yok: varsayılan "hazır" (ücretli akış), tek test kapatıyor.
    monkeypatch.setattr(s, "odeme_hazir_mi", lambda: saat["odeme"])
    yield saat
    r.hiz_sinirlarini_temizle()


@pytest.fixture
def epostalar(monkeypatch):
    from services import notify

    giden = []

    async def _sahte(alici, baslik, govde, ek=None):
        giden.append({"alici": alici, "konu": baslik, "govde": govde, "ek": ek or {}})
        return "sent", "test"

    monkeypatch.setattr(notify, "_eposta_gonder", _sahte)
    return giden


async def _modul(istemci, yonetici_basligi, eposta, acik=True, **ayarlar):
    govde = {"acik": acik}
    if ayarlar:
        govde["ayarlar"] = ayarlar
    y = await istemci.put(f"{MODUL}/musteri/{eposta}/etkinlik_bilet", json=govde, headers=yonetici_basligi)
    assert y.status_code == 200, y.text


async def _etkinlik(istemci, basliklar, yol=Y, yayinla=True, turler=None, **govde):
    govde.setdefault("baslik", f"Atölye {uuid.uuid4().hex[:5]}")
    govde.setdefault("baslangic", BAS)
    govde.setdefault("bitis", BIT)
    govde.setdefault("mekan_adi", "Kültür Merkezi")
    govde.setdefault("adres", "Moda Cd. 1, Kadıköy / İstanbul")
    y = await istemci.post(yol, json=govde, headers=basliklar)
    assert y.status_code == 200, y.text
    e = y.json()
    tl = (await istemci.get(f"{yol}/{e['id']}/bilet-turleri", headers=basliklar)).json()["items"]
    assert len(tl) == 1 and tl[0]["ad"] == "Standart" and tl[0]["fiyat"] == 0
    if turler is not None:
        await istemci.delete(f"{yol}/{e['id']}/bilet-turleri/{tl[0]['id']}", headers=basliklar)
        tl = []
        for t in turler:
            y = await istemci.post(f"{yol}/{e['id']}/bilet-turleri", json=t, headers=basliklar)
            assert y.status_code == 200, y.text
            tl.append(y.json())
    if yayinla:
        y = await istemci.put(f"{yol}/{e['id']}", json={"durum": "yayinda"}, headers=basliklar)
        assert y.status_code == 200, y.text
        e = y.json()
    return e, tl


async def _kayit(istemci, slug, kalemler, ip=None, **govde):
    govde.setdefault("ad", "Ayşe Yılmaz")
    govde.setdefault("eposta", f"ayse-{uuid.uuid4().hex[:6]}@ornek.com")
    govde["kalemler"] = kalemler
    return await istemci.post(f"{A}/{slug}/kayit", json=govde, headers=_z(ip))


async def _bilet_sayfasi(istemci, jeton):
    y = await istemci.get(f"{A}/bilet/{jeton}", headers=_z())
    assert y.status_code == 200, y.text
    return y.json()


# ---------------------------------------------------------------------------
# Saf kurallar
# ---------------------------------------------------------------------------
def test_qr_icerigi_kisisel_veri_tasimaz_ve_imza_dogrulanir():
    from services import etkinlik as s

    kod = s.kod_uret()
    icerik = s.qr_icerigi(kod)
    assert icerik.startswith("MKE1.") and kod in icerik and "@" not in icerik
    # QR alfanümerik kip: büyük harf, rakam, nokta
    assert all(c.isdigit() or ("A" <= c <= "Z") or c == "." for c in icerik)
    assert s.okutma_coz(icerik) == (kod, True)
    assert s.okutma_coz(icerik.lower()) == (kod, True)  # okuyucu küçük harf verse de
    # Değiştirilmiş imza / değiştirilmiş kod / sahte önek
    bozuk = icerik[:-1] + ("0" if icerik[-1] != "0" else "1")
    assert s.okutma_coz(bozuk) == (None, True)
    baska = s.kod_uret()
    assert s.okutma_coz(f"MKE1.{baska}.{icerik.rsplit('.', 1)[1]}") == (None, True)
    assert s.okutma_coz("MKE1.ABC") == (None, True)
    # Elle giriş: çıplak kod (boşluk/tire/küçük harf tolere), yanlış biçim reddedilir
    assert s.okutma_coz(f" {kod[:5].lower()}-{kod[5:]} ") == (kod, False)
    assert s.okutma_coz("12345") == (None, False)
    assert s.okutma_coz("") == (None, False)


def test_fiyat_ve_indirim_hesabi():
    from services import etkinlik as s

    k1 = s.Kalem(1, 2, 25000, "TRY")
    k2 = s.Kalem(2, 1, 10000, "TRY")
    assert s.fiyat_hesapla([k1, k2]) == {"ara_toplam": 60000, "indirim": 0, "toplam": 60000, "para_birimi": "TRY"}
    assert s.fiyat_hesapla([k1, k2], s.IndirimKurali(1, "yuzde", 10, None))["toplam"] == 54000
    assert s.fiyat_hesapla([k1, k2], s.IndirimKurali(1, "yuzde", 50, [2]))["indirim"] == 5000
    assert s.fiyat_hesapla([k1, k2], s.IndirimKurali(1, "tutar", 100000, None))["toplam"] == 0  # tutar toplamı aşamaz
    with pytest.raises(s.EtkinlikHatasi):
        s.fiyat_hesapla([k1, s.Kalem(3, 1, 500, "USD")])
    # Ücretsiz + ücretli karışık para birimi sorun değil (ücretsiz kalemin birimi önemsiz)
    assert s.fiyat_hesapla([s.Kalem(4, 1, 0, "USD"), k2])["para_birimi"] == "TRY"
    with pytest.raises(s.EtkinlikHatasi):
        s.kalemleri_duzelt([{"tur_id": 1, "adet": 15}, {"tur_id": 2, "adet": 6}])  # toplam > 20


def test_jetonlar_baska_kayitta_gecersiz():
    from services import etkinlik as s

    j = s.siparis_jetonu(5, "AAAA2222")
    assert s.siparis_jetonu_gecerli_mi(j, 5, "AAAA2222")
    assert not s.siparis_jetonu_gecerli_mi(j, 6, "AAAA2222") and not s.siparis_jetonu_gecerli_mi(j, 5, "BBBB2222")
    son = SIMDI + timedelta(hours=5)
    g = s.gorevli_jetonu(7, 2, son)
    assert s.gorevli_jetonu_coz(g) == (7, 2, son)
    parca = g.split("-")
    assert s.gorevli_jetonu_coz("-".join([parca[0], "3", parca[2], parca[3]])) is None  # sürüm değiştirilemez
    assert s.gorevli_jetonu_coz("-".join([parca[0], parca[1], str(int(parca[2]) + 3600), parca[3]])) is None  # süre uzatılamaz
    d = s.davet_jetonu(9, SIMDI)
    assert s.davet_jetonu_gecerli_mi(d, 9, SIMDI) and not s.davet_jetonu_gecerli_mi(d, 9, SIMDI + timedelta(seconds=1))


# ---------------------------------------------------------------------------
# Yetki, modül, izolasyon
# ---------------------------------------------------------------------------
async def test_yetki_ve_modul_kapisi(istemci, yonetici_basligi):
    e = _e()
    assert (await istemci.get(Y)).status_code == 401
    assert (await istemci.get(Y, headers=_b(e))).status_code == 403
    y = await istemci.get(M, headers=_b(e))
    assert y.status_code == 403 and _kod(y) == "modul_kapali"
    await _modul(istemci, yonetici_basligi, e)
    y = await istemci.get(M, headers=_b(e))
    assert y.status_code == 200 and y.json()["items"] == []
    m = (await istemci.get(f"{M}/meta", headers=_b(e))).json()
    assert m["ucretli_bilet"] is False and m["aylik_etkinlik_siniri"] == 5 and m["kapasite_siniri"] == 500


async def test_musteri_izolasyonu_ve_modul_kapaninca_410(istemci, yonetici_basligi):
    a, b = _e("a"), _e("b")
    await _modul(istemci, yonetici_basligi, a)
    await _modul(istemci, yonetici_basligi, b)
    ev, _ = await _etkinlik(istemci, _b(a), M)
    assert (await istemci.get(f"{M}/{ev['id']}", headers=_b(b))).status_code == 404
    assert (await istemci.put(f"{M}/{ev['id']}", json={"ozet": "x"}, headers=_b(b))).status_code == 404
    assert (await istemci.get(f"{M}/{ev['id']}/katilimcilar", headers=_b(b))).status_code == 404
    assert ev["id"] not in [x["id"] for x in (await istemci.get(M, headers=_b(b))).json()["items"]]
    # Yönetici müşterinin etkinliğini görür
    assert (await istemci.get(f"{Y}/{ev['id']}", headers=yonetici_basligi)).json()["hesap_email"] == a
    assert (await istemci.get(f"{A}/{ev['slug']}", headers=_z())).status_code == 200
    await _modul(istemci, yonetici_basligi, a, acik=False)
    y = await istemci.get(f"{A}/{ev['slug']}", headers=_z())
    assert y.status_code == 410 and _kod(y) == "etkinlik_pasif"
    y = await istemci.get(M, headers=_b(a))
    assert y.status_code == 403 and _kod(y) == "modul_kapali"


async def test_taslak_herkese_kapali_ve_yayin_kosullari(istemci, yonetici_basligi):
    ev, turler = await _etkinlik(istemci, yonetici_basligi, yayinla=False)
    assert ev["durum"] == "taslak"
    assert (await istemci.get(f"{A}/{ev['slug']}", headers=_z())).status_code == 404
    await istemci.delete(f"{Y}/{ev['id']}/bilet-turleri/{turler[0]['id']}", headers=yonetici_basligi)
    y = await istemci.put(f"{Y}/{ev['id']}", json={"durum": "yayinda"}, headers=yonetici_basligi)
    assert y.status_code == 409 and _kod(y) == "bilet_turu_yok"
    await istemci.post(f"{Y}/{ev['id']}/bilet-turleri", json={"ad": "Genel"}, headers=yonetici_basligi)
    y = await istemci.put(f"{Y}/{ev['id']}", json={"durum": "yayinda", "bicim": "online"}, headers=yonetici_basligi)
    assert y.status_code == 400 and _kod(y) == "online_baglanti_gerekli"
    y = await istemci.put(f"{Y}/{ev['id']}", json={"durum": "yayinda", "bicim": "online",
                                                   "online_baglanti": "https://meet.ornek.com/abc"}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["durum"] == "yayinda"
    # Zaman kuralları
    y = await istemci.put(f"{Y}/{ev['id']}", json={"bitis": "2026-11-05T09:00:00+03:00"}, headers=yonetici_basligi)
    assert y.status_code == 400 and _kod(y) == "bitis_once"
    y = await istemci.put(f"{Y}/{ev['id']}", json={"baslangic": "2026-11-05T10:00:00"}, headers=yonetici_basligi)
    assert y.status_code == 400 and _kod(y) == "zaman_gecersiz"


async def test_musteri_etkinliginde_ucretli_bilet_olusturulamaz(istemci, yonetici_basligi):
    e = _e()
    await _modul(istemci, yonetici_basligi, e)
    ev, turler = await _etkinlik(istemci, _b(e), M)
    y = await istemci.post(f"{M}/{ev['id']}/bilet-turleri", json={"ad": "VIP", "fiyat": 50000}, headers=_b(e))
    assert y.status_code == 409 and _kod(y) == "ucretli_bilet_yalniz_ajans"
    y = await istemci.put(f"{M}/{ev['id']}/bilet-turleri/{turler[0]['id']}", json={"fiyat": 100}, headers=_b(e))
    assert y.status_code == 409 and _kod(y) == "ucretli_bilet_yalniz_ajans"
    # Yönetici de müşterinin etkinliği için para toplayamaz
    y = await istemci.post(f"{Y}/{ev['id']}/bilet-turleri", json={"ad": "VIP", "fiyat": 50000}, headers=yonetici_basligi)
    assert y.status_code == 409 and _kod(y) == "ucretli_bilet_yalniz_ajans"
    # "Kapıda ödeme / havale" metni herkese açık sayfada
    await istemci.put(f"{M}/{ev['id']}", json={"odeme_notu": "Kapıda 200 TL"}, headers=_b(e))
    assert (await istemci.get(f"{A}/{ev['slug']}", headers=_z())).json()["odeme_notu"] == "Kapıda 200 TL"


async def test_odeme_saglayicisi_yokken_ucretli_tur_acilmaz(istemci, yonetici_basligi, _ortam):
    _ortam["odeme"] = False
    assert (await istemci.get(f"{Y}/meta", headers=yonetici_basligi)).json()["odeme_hazir"] is False
    ev, turler = await _etkinlik(istemci, yonetici_basligi)
    y = await istemci.post(f"{Y}/{ev['id']}/bilet-turleri", json={"ad": "VIP", "fiyat": 50000}, headers=yonetici_basligi)
    assert y.status_code == 409 and _kod(y) == "odeme_saglayicisi_yok"
    y = await istemci.put(f"{Y}/{ev['id']}/bilet-turleri/{turler[0]['id']}", json={"fiyat": 100}, headers=yonetici_basligi)
    assert y.status_code == 409 and _kod(y) == "odeme_saglayicisi_yok"
    # Ücretsiz tür sorunsuz; anahtarlar tanımlanınca açılır
    assert (await istemci.post(f"{Y}/{ev['id']}/bilet-turleri", json={"ad": "Öğrenci", "fiyat": 0},
                               headers=yonetici_basligi)).status_code == 200
    _ortam["odeme"] = True
    assert (await istemci.get(f"{Y}/meta", headers=yonetici_basligi)).json()["odeme_hazir"] is True
    y = await istemci.post(f"{Y}/{ev['id']}/bilet-turleri", json={"ad": "VIP", "fiyat": 50000}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text


async def test_aylik_sinir_ve_kapasite_siniri(istemci, yonetici_basligi):
    e = _e()
    await _modul(istemci, yonetici_basligi, e, aylik_etkinlik_siniri=2, kapasite_siniri=50)
    ev, _ = await _etkinlik(istemci, _b(e), M, yayinla=False)
    assert ev["kapasite"] == 50  # sınırsız istenemez: üst sınıra iner
    y = await istemci.put(f"{M}/{ev['id']}", json={"kapasite": 51}, headers=_b(e))
    assert y.status_code == 409 and _kod(y) == "kapasite_siniri"
    await _etkinlik(istemci, _b(e), M, yayinla=False)
    y = await istemci.post(M, json={"baslik": "Üçüncü", "baslangic": BAS, "bitis": BIT}, headers=_b(e))
    assert y.status_code == 409 and _kod(y) == "aylik_etkinlik_siniri"
    # Ajans etkinliği sınırsız olabilir
    ev, _ = await _etkinlik(istemci, yonetici_basligi, yayinla=False)
    assert ev["kapasite"] is None


# ---------------------------------------------------------------------------
# Kayıt, kapasite, kontenjan
# ---------------------------------------------------------------------------
async def test_ucretsiz_kayit_bilet_eposta_ve_online_baglanti_yalniz_sahibine(istemci, yonetici_basligi, epostalar, db_oturumu):
    from models.notifications import Notifications

    ev, turler = await _etkinlik(istemci, yonetici_basligi, bicim="karma", online_baglanti="https://meet.ornek.com/gizli-oda",
                                 sorular=[{"etiket": "Sektörünüz", "tur": "metin", "zorunlu": True}])
    acik = (await istemci.get(f"{A}/{ev['slug']}", headers=_z())).json()
    assert "gizli-oda" not in json.dumps(acik) and acik["turler"][0]["fiyat"] == 0 and acik["kayit_acik"] is True
    y = await _kayit(istemci, ev["slug"], [{"tur_id": turler[0]["id"], "adet": 2}])
    assert y.status_code == 400 and _kod(y) == "zorunlu"  # zorunlu soru
    soru_id = acik["sorular"][0]["id"]
    y = await _kayit(istemci, ev["slug"], [{"tur_id": turler[0]["id"], "adet": 2}], eposta="Ziyaretci@Ornek.com",
                     yanitlar={soru_id: "Eğitim"}, dil="en")
    assert y.status_code == 200, y.text
    g = y.json()
    assert g["siparis"]["durum"] == "onayli" and g["siparis"]["bilet_sayisi"] == 2 and "odeme_adresi" not in g
    sayfa = await _bilet_sayfasi(istemci, g["jeton"])
    assert sayfa["etkinlik"]["online_baglanti"] == "https://meet.ornek.com/gizli-oda"
    assert [b["durum"] for b in sayfa["biletler"]] == ["gecerli", "gecerli"]
    assert all(b["qr"].startswith("MKE1.") for b in sayfa["biletler"]) and sayfa["takvim"]["google"].startswith("https://")
    # Onay e-postası (İngilizce): bilet kodları, online bağlantı, PDF + ICS eki
    onay = [x for x in epostalar if x["alici"] == "ziyaretci@ornek.com"]
    assert len(onay) == 1 and onay[0]["konu"].startswith("Your ticket is ready")
    for b in sayfa["biletler"]:
        assert b["kod"] in onay[0]["govde"]
    assert "gizli-oda" in onay[0]["govde"]
    ekler = {e_["dosya_adi"]: e_ for e_ in onay[0]["ek"]["ekler"]}
    assert "etkinlik.ics" in ekler and any(a.endswith(".pdf") for a in ekler)
    # Bilet bağlantısı (yetki belgesi) ve online bağlantı kalıcı bildirim kaydında yok; panel içi kopya yok
    kayitlar = (await db_oturumu.execute(select(Notifications).where(Notifications.recipient_email == "ziyaretci@ornek.com"))).scalars().all()
    assert kayitlar and all(n.channel != "inapp" for n in kayitlar)
    assert all(g["jeton"] not in (n.body or "") and "gizli-oda" not in (n.body or "") for n in kayitlar), [(n.channel, n.body) for n in kayitlar]
    # Sahibine bildirim (ajans etkinliği → yöneticiler)
    sahip = (await db_oturumu.execute(select(Notifications).where(Notifications.event_type == "etkinlik_kayit"))).scalars().all()
    assert any("Ayşe Yılmaz" in n.title for n in sahip)


async def test_kapasite_eszamanli_iki_kayitta_asim_yok(istemci, yonetici_basligi, db_oturumu):
    from models.etkinlik import EtkinlikBiletleri

    ev, turler = await _etkinlik(istemci, yonetici_basligi, kapasite=1)
    t = turler[0]["id"]
    y1, y2 = await asyncio.gather(_kayit(istemci, ev["slug"], [{"tur_id": t, "adet": 1}], ad="Bir"),
                                  _kayit(istemci, ev["slug"], [{"tur_id": t, "adet": 1}], ad="İki"))
    assert sorted([y1.status_code, y2.status_code]) == [200, 409], (y1.text, y2.text)
    assert {_kod(y1), _kod(y2)} >= {"dolu"}
    n = (await db_oturumu.execute(select(func.count(EtkinlikBiletleri.id)).where(
        EtkinlikBiletleri.etkinlik_id == ev["id"], EtkinlikBiletleri.durum == "gecerli"))).scalar()
    assert n == 1
    acik = (await istemci.get(f"{A}/{ev['slug']}", headers=_z())).json()
    assert acik["dolu"] is True and acik["kalan"] == 0 and acik["turler"][0]["dolu"] is True


async def test_tur_kontenjani_eszamanli_ve_diger_tur_acik(istemci, yonetici_basligi):
    ev, turler = await _etkinlik(istemci, yonetici_basligi, turler=[{"ad": "Erken kayıt", "kontenjan": 2},
                                                                     {"ad": "Standart"}])
    erken, standart = turler[0]["id"], turler[1]["id"]
    sonuc = await asyncio.gather(*[_kayit(istemci, ev["slug"], [{"tur_id": erken, "adet": 1}]) for _ in range(4)])
    assert sorted(y.status_code for y in sonuc) == [200, 200, 409, 409]
    assert {_kod(y) for y in sonuc if y.status_code == 409} == {"tur_dolu"}
    assert (await _kayit(istemci, ev["slug"], [{"tur_id": standart, "adet": 3}])).status_code == 200
    # Kişi başı sınır
    y = await _kayit(istemci, ev["slug"], [{"tur_id": standart, "adet": 6}])
    assert y.status_code == 400 and _kod(y) == "kisi_basi_siniri"
    # Kontenjan satılandan aşağı çekilemez
    y = await istemci.put(f"{Y}/{ev['id']}/bilet-turleri/{erken}", json={"kontenjan": 1}, headers=yonetici_basligi)
    assert y.status_code == 409 and _kod(y) == "kontenjan_az"


async def test_veritabani_koltuk_benzersizligi(db_oturumu):
    from sqlalchemy.exc import IntegrityError

    from models.etkinlik import EtkinlikBiletleri

    ortak = dict(etkinlik_id=-77, siparis_id=-1, tur_id=-5, koltuk=0, durum="gecerli")
    db_oturumu.add(EtkinlikBiletleri(kod=uuid.uuid4().hex[:10].upper(), **ortak))
    await db_oturumu.commit()
    db_oturumu.add(EtkinlikBiletleri(kod=uuid.uuid4().hex[:10].upper(), **{**ortak, "tur_id": -6}))
    with pytest.raises(IntegrityError):
        await db_oturumu.commit()
    await db_oturumu.rollback()
    # İptal (koltuğu boş) biletler çakışmaz
    for _ in range(2):
        db_oturumu.add(EtkinlikBiletleri(kod=uuid.uuid4().hex[:10].upper(), **{**ortak, "koltuk": None, "durum": "iptal"}))
    await db_oturumu.commit()


async def test_kapasite_sonradan_konunca_koltuk_verilir(istemci, yonetici_basligi):
    ev, turler = await _etkinlik(istemci, yonetici_basligi)  # sınırsız
    for _ in range(3):
        assert (await _kayit(istemci, ev["slug"], [{"tur_id": turler[0]["id"], "adet": 1}])).status_code == 200
    y = await istemci.put(f"{Y}/{ev['id']}", json={"kapasite": 2}, headers=yonetici_basligi)
    assert y.status_code == 409 and _kod(y) == "kapasite_az"
    y = await istemci.put(f"{Y}/{ev['id']}", json={"kapasite": 4}, headers=yonetici_basligi)
    assert y.status_code == 200
    assert (await _kayit(istemci, ev["slug"], [{"tur_id": turler[0]["id"], "adet": 1}])).status_code == 200
    y = await _kayit(istemci, ev["slug"], [{"tur_id": turler[0]["id"], "adet": 1}])
    assert y.status_code == 409 and _kod(y) == "dolu"


async def test_satis_tarih_araligi_gizli_tur_ve_kayit_penceresi(istemci, yonetici_basligi, _ortam):
    ev, turler = await _etkinlik(istemci, yonetici_basligi, turler=[
        {"ad": "Erken", "satis_bit": "2026-10-01T00:00:00Z"},
        {"ad": "Geç", "satis_bas": "2026-10-20T00:00:00Z"},
        {"ad": "Davetli", "gizli": True, "gizli_kod": "vip-2026"},
        {"ad": "Normal"},
    ])
    erken, gec, gizli, normal = (t["id"] for t in turler)
    acik = (await istemci.get(f"{A}/{ev['slug']}", headers=_z())).json()
    durumlar = {t["ad"]: t["satis"] for t in acik["turler"]}
    assert durumlar == {"Erken": "bitti", "Geç": "baslamadi", "Normal": "acik"} and acik["gizli_tur_var"] is True
    y = await _kayit(istemci, ev["slug"], [{"tur_id": erken, "adet": 1}])
    assert y.status_code == 409 and _kod(y) == "satis_bitti"
    y = await _kayit(istemci, ev["slug"], [{"tur_id": gec, "adet": 1}])
    assert y.status_code == 409 and _kod(y) == "satis_baslamadi"
    y = await _kayit(istemci, ev["slug"], [{"tur_id": gizli, "adet": 1}])
    assert y.status_code == 404 and _kod(y) == "tur_yok"
    gorunen = (await istemci.get(f"{A}/{ev['slug']}?kod=VIP-2026", headers=_z())).json()
    assert "Davetli" in [t["ad"] for t in gorunen["turler"]]
    assert (await _kayit(istemci, ev["slug"], [{"tur_id": gizli, "adet": 1}], gizli_kod="vip-2026")).status_code == 200
    _ortam["an"] = datetime(2026, 10, 21, tzinfo=UTC)
    assert (await _kayit(istemci, ev["slug"], [{"tur_id": gec, "adet": 1}])).status_code == 200
    # Kayıt başlangıçta kapanır
    _ortam["an"] = datetime(2026, 11, 5, 8, 0, tzinfo=UTC)
    y = await _kayit(istemci, ev["slug"], [{"tur_id": normal, "adet": 1}])
    assert y.status_code == 409 and _kod(y) == "kayit_bitti"


async def test_indirim_kodu_yuzde_tutar_sinir_ve_tur(istemci, yonetici_basligi, monkeypatch):
    import os

    ev, turler = await _etkinlik(istemci, yonetici_basligi, turler=[
        {"ad": "Atölye", "fiyat": 100000, "para_birimi": "TRY"}, {"ad": "Öğrenci", "fiyat": 40000}])
    atolye, ogrenci = turler[0]["id"], turler[1]["id"]
    for g in ({"kod": "erken10", "tur": "yuzde", "deger": 10, "kullanim_siniri": 1},
              {"kod": "OGR", "tur": "tutar", "deger": 15000, "bilet_turleri": [ogrenci]},
              {"kod": "ESKI", "tur": "yuzde", "deger": 50, "son_tarih": "2026-10-01T00:00:00Z"}):
        y = await istemci.post(f"{Y}/{ev['id']}/indirimler", json=g, headers=yonetici_basligi)
        assert y.status_code == 200, y.text
    y = await istemci.post(f"{Y}/{ev['id']}/indirimler", json={"kod": "ERKEN10", "tur": "yuzde", "deger": 5}, headers=yonetici_basligi)
    assert y.status_code == 409 and _kod(y) == "kod_var"
    y = await istemci.post(f"{Y}/{ev['id']}/indirimler", json={"kod": "COK", "tur": "yuzde", "deger": 150}, headers=yonetici_basligi)
    assert y.status_code == 400
    f = (await istemci.post(f"{A}/{ev['slug']}/fiyat", json={"kalemler": [{"tur_id": atolye, "adet": 2}],
                                                             "indirim_kodu": "erken10"}, headers=_z())).json()
    assert f == {"ara_toplam": 200000, "indirim": 20000, "toplam": 180000, "para_birimi": "TRY"}
    y = await istemci.post(f"{A}/{ev['slug']}/fiyat", json={"kalemler": [{"tur_id": atolye, "adet": 1}], "indirim_kodu": "OGR"},
                           headers=_z())
    assert y.status_code == 400 and _kod(y) == "indirim_bu_ture_gecmez"
    y = await istemci.post(f"{A}/{ev['slug']}/fiyat", json={"kalemler": [{"tur_id": atolye, "adet": 1}], "indirim_kodu": "ESKI"},
                           headers=_z())
    assert y.status_code == 400 and _kod(y) == "indirim_suresi_doldu"
    r1 = await _kayit(istemci, ev["slug"], [{"tur_id": atolye, "adet": 2}], indirim_kodu="ERKEN10")
    assert r1.status_code == 200 and r1.json()["siparis"]["toplam"] == 180000
    r2 = await _kayit(istemci, ev["slug"], [{"tur_id": atolye, "adet": 1}], indirim_kodu="ERKEN10")
    assert r2.status_code == 409 and _kod(r2) == "indirim_tukendi"
    r3 = await _kayit(istemci, ev["slug"], [{"tur_id": ogrenci, "adet": 1}, {"tur_id": atolye, "adet": 1}], indirim_kodu="ogr")
    assert r3.status_code == 200 and r3.json()["siparis"]["toplam"] == 140000 - 15000
    kodlar = {i["kod"]: i for i in (await istemci.get(f"{Y}/{ev['id']}/indirimler", headers=yonetici_basligi)).json()["items"]}
    assert kodlar["ERKEN10"]["kullanilan"] == 1 and kodlar["OGR"]["kullanilan"] == 1
    # %100 indirim → ödeme yok, anında onay
    await istemci.post(f"{Y}/{ev['id']}/indirimler", json={"kod": "HEDIYE", "tur": "yuzde", "deger": 100}, headers=yonetici_basligi)
    y = await _kayit(istemci, ev["slug"], [{"tur_id": atolye, "adet": 1}], indirim_kodu="HEDIYE")
    assert y.status_code == 200 and y.json()["siparis"]["durum"] == "onayli" and y.json()["siparis"]["toplam"] == 0


async def test_bal_kupu_ve_hiz_siniri(istemci, yonetici_basligi, db_oturumu):
    from models.etkinlik import EtkinlikSiparisleri

    ev, turler = await _etkinlik(istemci, yonetici_basligi)
    y = await _kayit(istemci, ev["slug"], [{"tur_id": turler[0]["id"], "adet": 1}], web_adresi="http://spam")
    assert y.status_code == 200 and y.json()["siparis"] is None
    assert (await db_oturumu.execute(select(func.count(EtkinlikSiparisleri.id)).where(
        EtkinlikSiparisleri.etkinlik_id == ev["id"]))).scalar() == 0
    kodlar = [(await _kayit(istemci, ev["slug"], [{"tur_id": turler[0]["id"], "adet": 1}], ip="203.0.113.9")).status_code
              for _ in range(8)]
    assert kodlar.count(200) == 6 and kodlar[-1] == 429


# ---------------------------------------------------------------------------
# Bekleme listesi
# ---------------------------------------------------------------------------
async def test_bekleme_listesi_davet_akisi(istemci, yonetici_basligi, epostalar, _ortam):
    from services import etkinlik_kayit as k
    from core.database import db_manager

    ev, turler = await _etkinlik(istemci, yonetici_basligi, kapasite=1)
    t = turler[0]["id"]
    ilk = await _kayit(istemci, ev["slug"], [{"tur_id": t, "adet": 1}], eposta="ilk@ornek.com")
    assert ilk.status_code == 200
    # Yer varken bekleme listesine girilmez; doluyken girilir
    y = await istemci.post(f"{A}/{ev['slug']}/bekleme", json={"ad": "Bir", "eposta": "bir@ornek.com", "adet": 2}, headers=_z())
    assert y.status_code == 200 and y.json()["sira"] == 1
    y = await istemci.post(f"{A}/{ev['slug']}/bekleme", json={"ad": "İki", "eposta": "iki@ornek.com"}, headers=_z())
    assert y.status_code == 200 and y.json()["sira"] == 2
    y = await istemci.post(f"{A}/{ev['slug']}/bekleme", json={"ad": "İki", "eposta": "iki@ornek.com"}, headers=_z())
    assert y.status_code == 409 and _kod(y) == "zaten_listede"
    assert any(x["alici"] == "iki@ornek.com" and "bekleme" in x["konu"].lower() for x in epostalar)
    # İlk katılımcı iptal eder → 1 yer açılır: "Bir" 2 kişi istediği için atlanır, "İki" davet edilir
    y = await istemci.post(f"{A}/bilet/{ilk.json()['jeton']}/iptal", json={}, headers=_z())
    assert y.status_code == 200, y.text
    davet = [x for x in epostalar if x["alici"] == "iki@ornek.com" and "Yer açıldı" in x["konu"]]
    assert len(davet) == 1
    baglanti = next(s_ for s_ in davet[0]["govde"].split() if "davet=" in s_)
    jeton = baglanti.split("davet=", 1)[1]
    # Davetli yerini tutar: başkası kayıt olamaz
    y = await _kayit(istemci, ev["slug"], [{"tur_id": t, "adet": 1}])
    assert y.status_code == 409 and _kod(y) == "dolu"
    acik = (await istemci.get(f"{A}/{ev['slug']}?davet={jeton}", headers=_z())).json()
    assert acik["davet"]["gecerli"] is True and acik["davet"]["eposta"] == "iki@ornek.com"
    assert acik["turler"][0]["dolu"] is False  # davetli için yer var
    y = await _kayit(istemci, ev["slug"], [{"tur_id": t, "adet": 1}], davet=jeton, eposta="iki@ornek.com")
    assert y.status_code == 200, y.text
    y = await _kayit(istemci, ev["slug"], [{"tur_id": t, "adet": 1}], davet=jeton)
    assert y.status_code == 409 and _kod(y) == "davet_kullanildi"
    # İkinci yer açılır (kapasite 3): "Bir" (2 kişi) davet edilir; süresi dolunca durumu düşer
    await istemci.put(f"{Y}/{ev['id']}", json={"kapasite": 3}, headers=yonetici_basligi)
    liste = (await istemci.get(f"{Y}/{ev['id']}/bekleme", headers=yonetici_basligi)).json()["items"]
    durum = {w["eposta"]: w["durum"] for w in liste}
    assert durum == {"bir@ornek.com": "davet", "iki@ornek.com": "kullanildi"}
    _ortam["an"] = SIMDI + timedelta(hours=25)
    async with db_manager.async_session_maker() as db:
        sonuc = await k.zamanli_bakim(db)
    assert sonuc["birakilan_etkinlik"] >= 1
    liste = (await istemci.get(f"{Y}/{ev['id']}/bekleme", headers=yonetici_basligi)).json()["items"]
    assert {w["eposta"]: w["durum"] for w in liste}["bir@ornek.com"] == "suresi_doldu"
    y = await _kayit(istemci, ev["slug"], [{"tur_id": t, "adet": 2}], davet=jeton)
    assert y.status_code == 409


# ---------------------------------------------------------------------------
# Okutma
# ---------------------------------------------------------------------------
async def test_okutma_idempotent_farkli_etkinlik_iptal_ve_sahte(istemci, yonetici_basligi, db_oturumu):
    from models.etkinlik import EtkinlikOkutmalar

    ev, turler = await _etkinlik(istemci, yonetici_basligi)
    ev2, turler2 = await _etkinlik(istemci, yonetici_basligi)
    k1 = (await _kayit(istemci, ev["slug"], [{"tur_id": turler[0]["id"], "adet": 2}], ad="Ali Veli")).json()
    sayfa = await _bilet_sayfasi(istemci, k1["jeton"])
    b1, b2 = sayfa["biletler"]
    diger = (await _bilet_sayfasi(istemci, (await _kayit(istemci, ev2["slug"], [{"tur_id": turler2[0]["id"], "adet": 1}])).json()["jeton"]))
    okut = lambda kod: istemci.post(f"{Y}/{ev['id']}/okut", json={"kod": kod}, headers=yonetici_basligi)  # noqa: E731
    y = (await okut(b1["qr"])).json()
    assert y["sonuc"] == "gecerli" and y["bilet"]["ad"] == "Ali Veli" and y["bilet"]["tur"] == "Standart"
    assert y["sayac"]["giren"] == 1 and y["sayac"]["toplam"] == 2
    y = (await okut(b1["qr"])).json()
    assert y["sonuc"] == "zaten_girdi" and y["bilet"]["giris_at"]
    y = (await okut(b1["kod"].lower())).json()  # elle giriş, küçük harf
    assert y["sonuc"] == "zaten_girdi"
    # Değiştirilmiş imza / uydurma kod
    sahte = b2["qr"][:-2] + ("00" if not b2["qr"].endswith("00") else "11")
    assert (await okut(sahte)).json()["sonuc"] == "gecersiz"
    assert (await okut("ZZZZZZZZZZ")).json()["sonuc"] == "gecersiz"
    # Başka etkinliğin bileti: kişisel bilgi yok
    y = (await okut(diger["biletler"][0]["qr"])).json()
    assert y["sonuc"] == "farkli_etkinlik" and y["bilet"] is None
    # İptal edilen bilet
    satir = (await istemci.get(f"{Y}/{ev['id']}/katilimcilar?ara={b2['kod']}", headers=yonetici_basligi)).json()["items"][0]
    assert (await istemci.post(f"{Y}/{ev['id']}/biletler/{satir['id']}/iptal", json={}, headers=yonetici_basligi)).status_code == 200
    assert (await okut(b2["qr"])).json()["sonuc"] == "iptal"
    # Çevrimdışı kuyruktan gelen tekrar: idempotent
    y = await istemci.post(f"{Y}/{ev['id']}/okut", json={"kod": b1["qr"], "cevrimdisi": True, "zaman": "2026-11-05T07:00:00Z"},
                           headers=yonetici_basligi)
    assert y.json()["sonuc"] == "zaten_girdi"
    gunluk = (await db_oturumu.execute(select(EtkinlikOkutmalar).where(EtkinlikOkutmalar.etkinlik_id == ev["id"]))).scalars().all()
    assert [g.sonuc for g in gunluk].count("gecerli") == 1 and any(g.cevrimdisi for g in gunluk)
    ist = (await istemci.get(f"{Y}/{ev['id']}/istatistik", headers=yonetici_basligi)).json()
    assert ist["giren"] == 1 and ist["toplam"] == 1 and len(ist["son_okutmalar"]) >= 6
    # Etkinlik iptal edilince okutma "etkinlik_iptal"
    await istemci.put(f"{Y}/{ev2['id']}", json={"durum": "iptal", "bildir": False}, headers=yonetici_basligi)
    y = (await istemci.post(f"{Y}/{ev2['id']}/okut", json={"kod": diger["biletler"][0]["qr"]}, headers=yonetici_basligi)).json()
    assert y["sonuc"] == "etkinlik_iptal"


async def test_gorevli_baglantisi_yalniz_okutma_sure_ve_yenileme(istemci, yonetici_basligi, _ortam):
    ev, turler = await _etkinlik(istemci, yonetici_basligi)
    k1 = (await _kayit(istemci, ev["slug"], [{"tur_id": turler[0]["id"], "adet": 1}])).json()
    qr = (await _bilet_sayfasi(istemci, k1["jeton"]))["biletler"][0]["qr"]
    g = (await istemci.post(f"{Y}/{ev['id']}/gorevli", json={"saat": 6}, headers=yonetici_basligi)).json()
    jeton = g["adres"].rsplit("/", 1)[1]
    assert g["adres"].startswith("https://mehmetkuru.dev/etkinlik/giris/")
    ozet = (await istemci.get(f"{A}/giris/{jeton}")).json()
    assert ozet["etkinlik"]["baslik"] == ev["baslik"] and ozet["sayac"]["toplam"] == 1
    assert "katilimcilar" not in json.dumps(ozet) and "@" not in json.dumps(ozet["etkinlik"])
    y = (await istemci.post(f"{A}/giris/{jeton}/okut", json={"kod": qr})).json()
    assert y["sonuc"] == "gecerli"
    assert (await istemci.post(f"{A}/giris/{jeton}/okut", json={"kod": qr})).json()["sonuc"] == "zaten_girdi"
    assert (await istemci.get(f"{A}/giris/{jeton}/sayac")).json()["giren"] == 1
    # Jeton panel uçlarını açmaz (oturum yok → 401)
    assert (await istemci.get(f"{Y}/{ev['id']}/katilimcilar", headers={"Authorization": f"Bearer {jeton}"})).status_code == 401
    assert (await istemci.get(f"{A}/giris/{jeton}/katilimcilar")).status_code in (404, 405)
    # Süre dolunca 410
    _ortam["an"] = SIMDI + timedelta(hours=7)
    assert (await istemci.get(f"{A}/giris/{jeton}")).status_code == 410
    _ortam["an"] = SIMDI
    # Yenileme bütün eski bağlantıları geçersiz kılar
    y = (await istemci.post(f"{Y}/{ev['id']}/gorevli", json={"yenile": True}, headers=yonetici_basligi)).json()
    assert y["surum"] == 2
    assert (await istemci.get(f"{A}/giris/{jeton}")).status_code == 404
    yeni = y["adres"].rsplit("/", 1)[1]
    assert (await istemci.get(f"{A}/giris/{yeni}")).status_code == 200
    assert (await istemci.get(f"{A}/giris/1-1-1999999999-{'0' * 32}")).status_code == 404


# ---------------------------------------------------------------------------
# Ücretli bilet: ödeme bağlantısı + sağlayıcı webhook'u (Lemon Squeezy taklidi)
# ---------------------------------------------------------------------------
async def test_ucretli_bilet_odeme_webhooku_gecerli_yapar(istemci, yonetici_basligi, epostalar, db_oturumu, monkeypatch):
    from core import lemonsqueezy
    from models.client_sites import Client_sites
    from models.payments import Payments

    ev, turler = await _etkinlik(istemci, yonetici_basligi, turler=[{"ad": "Atölye", "fiyat": 75000, "para_birimi": "TRY"}])
    y = await _kayit(istemci, ev["slug"], [{"tur_id": turler[0]["id"], "adet": 2}], eposta="odeyen@ornek.com")
    assert y.status_code == 200, y.text
    g = y.json()
    assert g["siparis"]["durum"] == "odeme_bekliyor" and g["siparis"]["toplam"] == 150000 and g["odeme_adresi"].startswith("/ode/")
    odeme_jetonu = g["odeme_adresi"].rsplit("/", 1)[1]
    # Mevcut /ode sayfasının ucu ödemeyi gösterir
    o = (await istemci.get(f"/api/v1/odeme/{odeme_jetonu}")).json()
    assert o["tutar"] == 1500.0 and o["para_birimi"] == "TRY" and o["durum"] == "bekliyor" and o["invoice_no"].startswith("ETK-")
    sayfa = await _bilet_sayfasi(istemci, g["jeton"])
    assert [b["durum"] for b in sayfa["biletler"]] == ["odeme_bekliyor"] * 2 and all(b["qr"] is None for b in sayfa["biletler"])
    assert sayfa["siparis"]["odeme_adresi"] == g["odeme_adresi"]
    # Ödenmemiş bilet kapıda geçmez
    kod = sayfa["biletler"][0]["kod"]
    assert (await istemci.post(f"{Y}/{ev['id']}/okut", json={"kod": kod}, headers=yonetici_basligi)).json()["sonuc"] == "odeme_bekliyor"
    assert any(x["alici"] == "odeyen@ornek.com" and odeme_jetonu in x["govde"] for x in epostalar)
    # Sağlayıcı: imzalı bildirim + siparişin kendisi (taklit)
    monkeypatch.setenv("LEMON_WEBHOOK_SECRET", "whsec_lemon_test")

    async def _siparis(sid):
        return {"id": sid, "attributes": {"status": "paid", "total": 150000, "currency": "TRY"}}

    monkeypatch.setattr(lemonsqueezy, "siparis_getir", _siparis)
    govde = json.dumps({"meta": {"event_name": "order_created", "custom_data": {"jeton": odeme_jetonu}},
                        "data": {"id": "9911", "type": "orders"}}).encode()
    imza = hmac.new(b"whsec_lemon_test", govde, hashlib.sha256).hexdigest()
    y = await istemci.post("/api/v1/odeme/lemon/webhook", content=govde,
                           headers={"X-Signature": imza, "X-Event-Name": "order_created", "Content-Type": "application/json"})
    assert y.status_code == 200 and y.json()["islendi"] is True, y.text
    sayfa = await _bilet_sayfasi(istemci, g["jeton"])
    assert sayfa["siparis"]["durum"] == "onayli" and [b["durum"] for b in sayfa["biletler"]] == ["gecerli"] * 2
    p = (await db_oturumu.execute(select(Payments).where(Payments.jeton == odeme_jetonu))).scalars().first()
    assert p.durum == "odendi" and p.invoice_id is None
    # Bilet ödemesi müşteri sitesi kaydı açmaz; bilet e-postası gider
    assert (await db_oturumu.execute(select(Client_sites).where(Client_sites.client_email == "odeyen@ornek.com"))).first() is None
    assert any(x["alici"] == "odeyen@ornek.com" and "Biletiniz hazır" in x["konu"] for x in epostalar)
    # Aynı bildirim ikinci kez: değişiklik yok
    y = await istemci.post("/api/v1/odeme/lemon/webhook", content=govde,
                           headers={"X-Signature": imza, "X-Event-Name": "order_created", "Content-Type": "application/json"})
    assert y.status_code == 200
    satis = (await istemci.get(f"{Y}/{ev['id']}/satis", headers=yonetici_basligi)).json()
    assert satis["gelir"] == 150000 and satis["turler"][0]["gecerli"] == 2
    # İmzasız bildirim reddedilir
    y = await istemci.post("/api/v1/odeme/lemon/webhook", content=govde, headers={"X-Signature": "00", "X-Event-Name": "order_created"})
    assert y.status_code == 401


async def test_odeme_tutma_suresi_dolunca_yer_birakilir(istemci, yonetici_basligi, _ortam):
    ev, turler = await _etkinlik(istemci, yonetici_basligi, kapasite=1,
                                 turler=[{"ad": "Atölye", "fiyat": 50000, "para_birimi": "TRY"}])
    t = turler[0]["id"]
    y = await _kayit(istemci, ev["slug"], [{"tur_id": t, "adet": 1}])
    assert y.status_code == 200 and y.json()["siparis"]["durum"] == "odeme_bekliyor"
    y = await _kayit(istemci, ev["slug"], [{"tur_id": t, "adet": 1}])
    assert y.status_code == 409 and _kod(y) == "dolu"  # tutma süresince yer dolu
    _ortam["an"] = SIMDI + timedelta(minutes=61)
    y = await _kayit(istemci, ev["slug"], [{"tur_id": t, "adet": 1}])
    assert y.status_code == 200, y.text


async def test_havale_ile_odendi_isaretleme(istemci, yonetici_basligi, epostalar):
    ev, turler = await _etkinlik(istemci, yonetici_basligi, turler=[{"ad": "Atölye", "fiyat": 50000, "para_birimi": "EUR"}])
    g = (await _kayit(istemci, ev["slug"], [{"tur_id": turler[0]["id"], "adet": 1}], eposta="havale@ornek.com")).json()
    satir = (await istemci.get(f"{Y}/{ev['id']}/katilimcilar", headers=yonetici_basligi)).json()["items"][0]
    y = await istemci.post(f"{Y}/{ev['id']}/siparisler/{satir['siparis']['id']}/odendi", headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    assert (await _bilet_sayfasi(istemci, g["jeton"]))["biletler"][0]["durum"] == "gecerli"
    y = await istemci.post(f"{Y}/{ev['id']}/siparisler/{satir['siparis']['id']}/odendi", headers=yonetici_basligi)
    assert y.status_code == 409


# ---------------------------------------------------------------------------
# Bilet sayfası: ICS, PDF, QR, iptal sınırı
# ---------------------------------------------------------------------------
async def test_ics_pdf_qr_icerigi_ve_iptal_siniri(istemci, yonetici_basligi, _ortam, epostalar):
    from services.pdf_belge import pdf_metni

    ev, turler = await _etkinlik(istemci, yonetici_basligi, baslik="Seminer ICS", iptal_sinir_saat=48, oturumlar=[
        {"ad": "Gün 1", "baslangic": "2026-11-05T10:00:00+03:00", "bitis": "2026-11-05T12:00:00+03:00"},
        {"ad": "Gün 2", "baslangic": "2026-11-05T14:00:00+03:00", "bitis": "2026-11-05T17:00:00+03:00"}])
    g = (await _kayit(istemci, ev["slug"], [{"tur_id": turler[0]["id"], "adet": 1}], ad="Zeynep Kaya")).json()
    sayfa = await _bilet_sayfasi(istemci, g["jeton"])
    ics = (await istemci.get(sayfa["ics_adresi"])).text
    assert ics.startswith("BEGIN:VCALENDAR") and ics.count("BEGIN:VEVENT") == 2
    assert "DTSTART:20261105T070000Z" in ics and "DTEND:20261105T140000Z" in ics and "SUMMARY:Seminer ICS — Gün 2" in ics
    assert f"UID:etkinlik-{ev['id']}-{g['siparis']['kod']}-1@mehmetkuru.dev" in ics and "STATUS:CONFIRMED" in ics
    y = await istemci.get(sayfa["pdf_adresi"])
    assert y.status_code == 200 and y.headers["content-type"] == "application/pdf"
    metin = pdf_metni(y.content)
    assert sayfa["biletler"][0]["kod"] in metin and "Seminer ICS" in metin and "Zeynep Kaya" in metin
    y = await istemci.get(sayfa["biletler"][0]["qr_adresi"])
    assert y.status_code == 200 and y.headers["content-type"].startswith("image/svg+xml") and b"<svg" in y.content
    assert (await istemci.get(f"{A}/bilet/{g['jeton']}/qr/AAAAAAAAAA.svg")).status_code == 404
    # Başka jetonla aynı sipariş açılmaz
    sahte = g["jeton"].split("-")[0] + "-" + "0" * 32
    assert (await istemci.get(f"{A}/bilet/{sahte}")).status_code == 404
    # İptal sınırı: başlangıçtan 48 saat önce kapanır
    _ortam["an"] = datetime(2026, 11, 3, 8, 0, tzinfo=UTC)
    y = await istemci.post(f"{A}/bilet/{g['jeton']}/iptal", json={}, headers=_z())
    assert y.status_code == 409 and _kod(y) == "iptal_suresi_gecti"
    _ortam["an"] = SIMDI
    y = await istemci.post(f"{A}/bilet/{g['jeton']}/iptal", json={}, headers=_z())
    assert y.status_code == 200 and y.json()["biletler"][0]["durum"] == "iptal" and y.json()["pdf_adresi"] is None
    iptal = [x for x in epostalar if "iptal" in x["konu"].lower() and x["ek"].get("ekler")]
    assert iptal and "STATUS:CANCELLED" in iptal[-1]["ek"]["ekler"][0]["icerik"]


# ---------------------------------------------------------------------------
# JSON-LD, olaylar, CRM, pazarlama
# ---------------------------------------------------------------------------
async def test_event_jsonld_yalniz_arama_motoru_seciliyken(istemci, yonetici_basligi):
    ev, turler = await _etkinlik(istemci, yonetici_basligi, bicim="karma", online_baglanti="https://meet.ornek.com/gizli",
                                 organizator_ad="By Mehmet KURU Dev", organizator_url="https://mehmetkuru.dev",
                                 ozet="Yapay zekâ ile otomasyon atölyesi")
    o = (await istemci.get(f"{A}/{ev['slug']}/ozet")).json()
    assert o["jsonld"] is None and o["indekslenebilir"] is False
    y = await istemci.get(f"{A}/{ev['slug']}", headers=_z())
    assert y.headers.get("x-robots-tag") == "noindex"
    await istemci.put(f"{Y}/{ev['id']}", json={"arama_motoru": True}, headers=yonetici_basligi)
    await istemci.post(f"{Y}/{ev['id']}/bilet-turleri", json={"ad": "VIP", "fiyat": 120000, "para_birimi": "TRY"},
                       headers=yonetici_basligi)
    o = (await istemci.get(f"{A}/{ev['slug']}/ozet")).json()
    j = o["jsonld"]
    assert j["@context"] == "https://schema.org" and j["@type"] == "Event" and j["name"] == ev["baslik"]
    assert j["startDate"] == "2026-11-05T10:00:00+03:00" and j["endDate"] == "2026-11-05T17:00:00+03:00"
    assert j["eventAttendanceMode"] == "https://schema.org/MixedEventAttendanceMode"
    assert j["eventStatus"] == "https://schema.org/EventScheduled"
    assert {x["@type"] for x in j["location"]} == {"Place", "VirtualLocation"}
    assert j["organizer"] == {"@type": "Organization", "name": "By Mehmet KURU Dev", "url": "https://mehmetkuru.dev"}
    assert sorted((x["name"], x["price"]) for x in j["offers"]) == [("Standart", "0.00"), ("VIP", "1200.00")]
    assert "gizli" not in json.dumps(j)  # online bağlantı asla
    assert "x-robots-tag" not in {k.lower() for k in (await istemci.get(f"{A}/{ev['slug']}", headers=_z())).headers}


async def test_olay_katalogu_webhook_ve_otomasyon(istemci, yonetici_basligi, db_oturumu, monkeypatch):
    from models.api_erisimi import WebhookTeslimatlari, WebhookUcNoktalari
    from services import otomasyon_kural, webhook
    from services.api_erisimi import gizli_sakla

    tumu = {"etkinlik.kayit", "etkinlik.bilet_satildi", "etkinlik.giris", "etkinlik.iptal"}
    assert tumu <= set(webhook.OLAY_SOZLUGU) and tumu <= set(otomasyon_kural.OLAY_SOZLUGU)
    assert otomasyon_kural.olay_nesneleri("etkinlik.kayit", False) == ("etkinlik", "hesap", "kisi", "olay")
    # Ücretli bilet satışı yalnız ajansın kataloğunda (müşteri etkinliğinde ücretli bilet yok)
    assert "etkinlik.bilet_satildi" not in {o["anahtar"] for o in webhook.olay_katalogu(False)}
    assert "etkinlik.bilet_satildi" not in {o["anahtar"] for o in otomasyon_kural.olay_katalogu(False)}
    assert "etkinlik.bilet_satildi" in {o["anahtar"] for o in webhook.olay_katalogu(True)}
    # Olaylar merkezi flush kancasından (ikinci kanca sistemi yok)
    assert {"etkinlik_biletleri", "etkinlik_okutmalar"} <= webhook.IZLENEN_TABLOLAR
    monkeypatch.setattr(webhook, "ANLIK_TESLIMAT", False)
    uc = WebhookUcNoktalari(sahip_tur="ajans", hesap_email=None, url="https://kanca.ornek.com/etkinlik",
                            olaylar=json.dumps(sorted(tumu)), aktif=True,
                            gizli_anahtar=gizli_sakla("whsec_test"), ardisik_hata=0, tum_musteriler=False)
    db_oturumu.add(uc)
    await db_oturumu.commit()
    webhook.onbellegi_temizle()
    try:
        ev, turler = await _etkinlik(istemci, yonetici_basligi)
        g = (await _kayit(istemci, ev["slug"], [{"tur_id": turler[0]["id"], "adet": 2}], ad="Gizli Kişi",
                          eposta="gizli.kisi@ornek.com")).json()
        sayfa = await _bilet_sayfasi(istemci, g["jeton"])
        await istemci.post(f"{Y}/{ev['id']}/okut", json={"kod": sayfa["biletler"][0]["qr"]}, headers=yonetici_basligi)
        await istemci.post(f"{A}/bilet/{g['jeton']}/iptal", json={"kodlar": [sayfa["biletler"][1]["kod"]]}, headers=_z())
        teslimat = (await db_oturumu.execute(select(WebhookTeslimatlari).where(WebhookTeslimatlari.uc_id == uc.id)
                                             .order_by(WebhookTeslimatlari.id))).scalars().all()
        assert [x.tur for x in teslimat] == ["etkinlik.kayit", "etkinlik.giris", "etkinlik.iptal"]
        for x in teslimat:
            assert "gizli" not in x.govde.lower() and json.loads(x.govde)["veri"]["etkinlik_id"] == ev["id"]
        assert json.loads(teslimat[0].govde)["veri"]["bilet_sayisi"] == 2
        assert json.loads(teslimat[1].govde)["veri"]["bilet_kod"] == sayfa["biletler"][0]["kod"]
        assert json.loads(teslimat[2].govde)["veri"]["bilet_sayisi"] == 1
        # Ücretli: kayıt anında olay yok (ödeme bekliyor); havale "ödendi" → kayıt + bilet satıldı
        ev2, turler2 = await _etkinlik(istemci, yonetici_basligi, turler=[{"ad": "Atölye", "fiyat": 40000, "para_birimi": "TRY"}])
        await _kayit(istemci, ev2["slug"], [{"tur_id": turler2[0]["id"], "adet": 1}], eposta="odeyen.gizli@ornek.com")
        once = len(teslimat)
        satir = (await istemci.get(f"{Y}/{ev2['id']}/katilimcilar?durum=tum", headers=yonetici_basligi)).json()["items"][0]
        y = await istemci.post(f"{Y}/{ev2['id']}/siparisler/{satir['siparis']['id']}/odendi", headers=yonetici_basligi)
        assert y.status_code == 200, y.text
        teslimat = (await db_oturumu.execute(select(WebhookTeslimatlari).where(WebhookTeslimatlari.uc_id == uc.id)
                                             .order_by(WebhookTeslimatlari.id))).scalars().all()
        yeni = teslimat[once:]
        assert [x.tur for x in yeni] == ["etkinlik.kayit", "etkinlik.bilet_satildi"]
        assert json.loads(yeni[1].govde)["veri"]["toplam_kurus"] == 40000 and "gizli" not in yeni[1].govde
    finally:
        uc.aktif = False
        await db_oturumu.commit()
        webhook.onbellegi_temizle()


async def test_crm_yalniz_ajans_etkinligi_ve_pazarlama_izni(istemci, yonetici_basligi, db_oturumu):
    from models.crm import CrmAdaylari

    ev, turler = await _etkinlik(istemci, yonetici_basligi)
    y = await _kayit(istemci, ev["slug"], [{"tur_id": turler[0]["id"], "adet": 1}], eposta="crm-ajans@ornek.com",
                     ad="CRM Aday", pazarlama_izni=True)
    assert y.status_code == 200
    aday = (await db_oturumu.execute(select(CrmAdaylari).where(CrmAdaylari.email == "crm-ajans@ornek.com"))).scalars().first()
    assert aday is not None and aday.pazarlama_izni_at is not None
    satir = (await istemci.get(f"{Y}/{ev['id']}/katilimcilar", headers=yonetici_basligi)).json()["items"][0]
    assert satir["siparis"]["crm_aday_id"] == aday.id and satir["siparis"]["pazarlama_izni"] is True
    e = _e()
    await _modul(istemci, yonetici_basligi, e)
    ev2, turler2 = await _etkinlik(istemci, _b(e), M)
    await _kayit(istemci, ev2["slug"], [{"tur_id": turler2[0]["id"], "adet": 1}], eposta="crm-musteri@ornek.com")
    assert (await db_oturumu.execute(select(CrmAdaylari).where(CrmAdaylari.email == "crm-musteri@ornek.com"))).first() is None


async def test_bilgilendirme_eposta_vs_pazarlama_aktarimi(istemci, yonetici_basligi, epostalar, db_oturumu):
    from models.eposta_pazarlama import EpKisiler, EpListeler, EpListeUyelikleri

    e = _e()
    await _modul(istemci, yonetici_basligi, e)
    ev, turler = await _etkinlik(istemci, _b(e), M)
    t = turler[0]["id"]
    await _kayit(istemci, ev["slug"], [{"tur_id": t, "adet": 1}], eposta="izinli@ornek.com", pazarlama_izni=True)
    await _kayit(istemci, ev["slug"], [{"tur_id": t, "adet": 1}], eposta="izinsiz@ornek.com")
    await _kayit(istemci, ev["slug"], [{"tur_id": t, "adet": 1}], eposta="metin@ornek.com", pazarlama_izni="true")  # yalnız JSON true
    # Onay e-postası herkese (işlemsel, izin gerektirmez)
    assert {x["alici"] for x in epostalar if "Biletiniz hazır" in x["konu"]} >= {"izinli@ornek.com", "izinsiz@ornek.com"}
    # Duyuru: bütün bilet sahiplerine, bilgilendirme notuyla
    epostalar.clear()
    y = await istemci.post(f"{M}/{ev['id']}/duyuru", json={"konu": "Salon değişti", "metin": "B salonundayız."}, headers=_b(e))
    assert y.status_code == 200 and y.json()["alici"] == 3
    duyuru = [x for x in epostalar if "Salon değişti" in x["konu"]]
    assert len(duyuru) == 3 and all("etkinlik bilgilendirmesi" in x["govde"] for x in duyuru)
    # Pazarlama aktarımı: modül kapalıyken 403; açıkken yalnız izinli kişi listeye
    y = await istemci.get(f"{M}/{ev['id']}/pazarlama", headers=_b(e))
    assert y.json()["acik"] is False and y.json()["izinli"] == 1
    y = await istemci.post(f"{M}/{ev['id']}/pazarlama", json={"liste_id": 1}, headers=_b(e))
    assert y.status_code == 403 and _kod(y) == "modul_kapali"
    y = await istemci.put(f"{MODUL}/musteri/{e}/eposta_pazarlama", json={"acik": True}, headers=yonetici_basligi)
    assert y.status_code == 200
    liste = EpListeler(hesap_email=e, ad="Etkinlik katılımcıları")
    db_oturumu.add(liste)
    await db_oturumu.commit()
    await db_oturumu.refresh(liste)
    y = await istemci.post(f"{M}/{ev['id']}/pazarlama", json={"liste_id": liste.id}, headers=_b(e))
    assert y.status_code == 200, y.text
    assert y.json()["sayilar"]["aktarilan"] == 1 and y.json()["sayilar"]["listeye"] == 1
    kisiler = (await db_oturumu.execute(select(EpKisiler).where(EpKisiler.hesap_email == e))).scalars().all()
    assert [(k_.eposta, k_.izin_durumu) for k_ in kisiler] == [("izinli@ornek.com", "izinli")]
    assert kisiler[0].izin_kaynagi == f"etkinlik:{ev['id']}" and kisiler[0].izin_zamani is not None
    uyeler = (await db_oturumu.execute(select(EpListeUyelikleri).where(EpListeUyelikleri.liste_id == liste.id))).scalars().all()
    assert len(uyeler) == 1
    # Başka hesabın listesine aktarılamaz
    yabanci = EpListeler(hesap_email=_e("yabanci"), ad="Yabancı")
    db_oturumu.add(yabanci)
    await db_oturumu.commit()
    await db_oturumu.refresh(yabanci)
    y = await istemci.post(f"{M}/{ev['id']}/pazarlama", json={"liste_id": yabanci.id}, headers=_b(e))
    assert y.status_code == 404 and _kod(y) == "liste_yok"


# ---------------------------------------------------------------------------
# Ekip izni, panel işlemleri, liste sayfası, teşekkür, çöp kutusu
# ---------------------------------------------------------------------------
async def test_ekip_etkinlik_giris_izni_yalniz_okutma(istemci, yonetici_basligi, db_oturumu):
    from models.hesap_uyeleri import HesapUyeleri
    from services import hesap_ekibi as he

    sahip, gorevli = _e("sahip"), _e("kapi")
    await _modul(istemci, yonetici_basligi, sahip)
    db_oturumu.add(HesapUyeleri(hesap_email=sahip, uye_email=gorevli, rol="uye", izinler=json.dumps(["etkinlik_giris"]),
                                durum="aktif", olusturma=he.simdi()))
    await db_oturumu.commit()
    he.onbellegi_temizle()
    ev, turler = await _etkinlik(istemci, _b(sahip), M)
    g = (await _kayit(istemci, ev["slug"], [{"tur_id": turler[0]["id"], "adet": 1}])).json()
    qr = (await _bilet_sayfasi(istemci, g["jeton"]))["biletler"][0]["qr"]
    b = _b(gorevli, sahip)
    liste = (await istemci.get(f"{M}/giris-listesi", headers=b)).json()["items"]
    assert [x["id"] for x in liste] == [ev["id"]] and "eposta" not in json.dumps(liste)
    assert (await istemci.post(f"{M}/{ev['id']}/okut", json={"kod": qr}, headers=b)).json()["sonuc"] == "gecerli"
    assert (await istemci.get(f"{M}/{ev['id']}/sayac", headers=b)).json()["giren"] == 1
    for yol in (f"{M}/{ev['id']}/katilimcilar", f"{M}/{ev['id']}", M, f"{M}/{ev['id']}/katilimcilar.csv", f"{M}/{ev['id']}/gorevli"):
        y = await istemci.get(yol, headers=b)
        assert y.status_code == 403 and _kod(y) == "hesap_izni_yok", yol
    # Eski (5A dönemi) üye varsayılanı yeni okutma iznini kendiliğinden alır; yönetim izni almaz
    eski = ["projeler", "gorevler", "destek", "dosyalar", "siteler", "raporlar", "mesajlar", "asistanlar", "qr", "kartvizit",
            "menu", "randevu", "asistan"]
    coz = he.izinleri_coz(json.dumps(eski), "uye")
    assert "etkinlik_giris" in coz and "etkinlik" not in coz
    # 5M dönemi yönetici varsayılanı (o günkü bütün izinler; 5I/6S/6E izinleri henüz yoktu).
    yeni_izinler = {"etkinlik", "etkinlik_giris", "icerik", "saha_yonetim", "saha_teknisyen",
                    "stok", "kasa", "egitim", "egitim_egitmen"}  # Faz 6P/6K izinleri de o gün yoktu
    assert "etkinlik" in he.izinleri_coz(json.dumps(sorted(set(he.IZINLER) - yeni_izinler)), "yonetici")


async def test_panel_elle_ekle_csv_iade_ve_giris_geri_al(istemci, yonetici_basligi, epostalar):
    ev, turler = await _etkinlik(istemci, yonetici_basligi, kapasite=2,
                                 sorular=[{"etiket": "Not", "tur": "metin"}],
                                 turler=[{"ad": "Atölye", "fiyat": 30000, "para_birimi": "TRY"}])
    t = turler[0]["id"]
    y = await istemci.post(f"{Y}/{ev['id']}/katilimcilar", json={"ad": "=HYPERLINK(\"x\")", "eposta": "kapi@ornek.com",
                                                                  "tur_id": t, "adet": 1}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    satir = (await istemci.get(f"{Y}/{ev['id']}/katilimcilar", headers=yonetici_basligi)).json()["items"][0]
    assert satir["durum"] == "gecerli" and satir["siparis"]["kaynak"] == "panel"  # elle eklenen ödeme beklemez
    assert any(x["alici"] == "kapi@ornek.com" for x in epostalar)
    y = await istemci.post(f"{Y}/{ev['id']}/katilimcilar", json={"ad": "Fazla", "eposta": "f@ornek.com", "tur_id": t, "adet": 2},
                           headers=yonetici_basligi)
    assert y.status_code == 409 and _kod(y) == "dolu"  # panel de kapasiteyi aşamaz
    csv_ = (await istemci.get(f"{Y}/{ev['id']}/katilimcilar.csv", headers=yonetici_basligi)).text
    assert csv_.startswith("﻿bilet_kodu,") and "'=HYPERLINK" in csv_ and satir["kod"] in csv_
    # Giriş + geri al
    assert (await istemci.post(f"{Y}/{ev['id']}/biletler/{satir['id']}/giris", headers=yonetici_basligi)).json()["sonuc"] == "gecerli"
    assert (await istemci.delete(f"{Y}/{ev['id']}/biletler/{satir['id']}/giris", headers=yonetici_basligi)).status_code == 200
    assert (await istemci.get(f"{Y}/{ev['id']}/katilimcilar?giris=evet", headers=yonetici_basligi)).json()["toplam"] == 0
    # İptal + iade işaretle
    y = await istemci.post(f"{Y}/{ev['id']}/siparisler/{satir['siparis']['id']}/iptal", json={"iade": True}, headers=yonetici_basligi)
    assert y.status_code == 200
    satir = (await istemci.get(f"{Y}/{ev['id']}/katilimcilar?durum=iptal", headers=yonetici_basligi)).json()["items"][0]
    assert satir["iade"] == "bekliyor"
    y = await istemci.post(f"{Y}/{ev['id']}/biletler/{satir['id']}/iade", json={"durum": "yapildi"}, headers=yonetici_basligi)
    assert y.json()["iade"] == "yapildi"


async def test_etkinlik_iptali_katilimcilara_eposta_ve_tesekkur_zamanli(istemci, yonetici_basligi, epostalar, _ortam):
    from core.database import db_manager
    from services import etkinlik_kayit as k

    ev, turler = await _etkinlik(istemci, yonetici_basligi)
    g = (await _kayit(istemci, ev["slug"], [{"tur_id": turler[0]["id"], "adet": 1}], eposta="iptal-olan@ornek.com")).json()
    epostalar.clear()
    await istemci.put(f"{Y}/{ev['id']}", json={"durum": "iptal"}, headers=yonetici_basligi)
    assert [x["konu"] for x in epostalar if x["alici"] == "iptal-olan@ornek.com"] == [f"Etkinlik iptal edildi: {ev['baslik']}"]
    y = await istemci.put(f"{Y}/{ev['id']}", json={"durum": "yayinda"}, headers=yonetici_basligi)
    assert y.status_code == 409 and _kod(y) == "iptal_geri_alinamaz"
    # Teşekkür + anket: yalnız giriş yapanlara, bir kez
    ev2, turler2 = await _etkinlik(istemci, yonetici_basligi, tesekkur_aktif=True, anket_url="https://anket.ornek.com/a",
                                   tesekkur_metni="Sunumlar ekte.")
    gelen = (await _kayit(istemci, ev2["slug"], [{"tur_id": turler2[0]["id"], "adet": 1}], eposta="gelen@ornek.com")).json()
    await _kayit(istemci, ev2["slug"], [{"tur_id": turler2[0]["id"], "adet": 1}], eposta="gelmeyen@ornek.com")
    qr = (await _bilet_sayfasi(istemci, gelen["jeton"]))["biletler"][0]["qr"]
    await istemci.post(f"{Y}/{ev2['id']}/okut", json={"kod": qr}, headers=yonetici_basligi)
    epostalar.clear()
    async with db_manager.async_session_maker() as db:
        await k.zamanli_bakim(db)
    assert not [x for x in epostalar if "teşekkür" in x["konu"].lower()]  # etkinlik bitmedi
    _ortam["an"] = datetime(2026, 11, 5, 17, 0, tzinfo=UTC)  # bitişten 3 saat sonra
    async with db_manager.async_session_maker() as db:
        sonuc = await k.zamanli_bakim(db)
        await k.zamanli_bakim(db)
    tesekkur = [x for x in epostalar if x["konu"].startswith("Katıldığınız için teşekkürler")]
    assert [x["alici"] for x in tesekkur] == ["gelen@ornek.com"] and "https://anket.ornek.com/a" in tesekkur[0]["govde"]
    assert sonuc["tamamlanan"] >= 1
    assert (await istemci.get(f"{Y}/{ev2['id']}", headers=yonetici_basligi)).json()["durum"] == "tamamlandi"


async def test_hesap_listesi_sayfasi(istemci, yonetici_basligi):
    e = _e()
    await _modul(istemci, yonetici_basligi, e)
    ev, _ = await _etkinlik(istemci, _b(e), M, baslik="Listede görünen")
    gizli, _ = await _etkinlik(istemci, _b(e), M, baslik="Listede yok", listede_goster=False)
    slug = f"kafe-{uuid.uuid4().hex[:6]}"
    y = await istemci.get(f"/api/v1/etkinlikler/{slug}")
    assert y.status_code == 404
    y = await istemci.put(f"{M}/liste-ayari", json={"baslik": "Kafe etkinlikleri", "slug": slug, "acik": False}, headers=_b(e))
    assert y.status_code == 200 and y.json()["adres_url"].endswith(f"/etkinlikler/{slug}")
    assert (await istemci.get(f"/api/v1/etkinlikler/{slug}")).status_code == 404  # kapalı
    await istemci.put(f"{M}/liste-ayari", json={"acik": True}, headers=_b(e))
    v = (await istemci.get(f"/api/v1/etkinlikler/{slug}")).json()
    assert [x["slug"] for x in v["etkinlikler"]] == [ev["slug"]] and v["etkinlikler"][0]["ucretsiz"] is True
    assert (await istemci.put(f"{M}/liste-ayari", json={"slug": "giris"}, headers=_b(e))).status_code == 400


async def test_kapak_gorseli_silme_ve_cop_kutusu(istemci, yonetici_basligi, db_oturumu):
    from PIL import Image

    from models.cop_kutusu import CopKutusu
    from models.etkinlik import EtkinlikSiparisleri

    e = _e()
    await _modul(istemci, yonetici_basligi, e)
    ev, turler = await _etkinlik(istemci, _b(e), M)
    tampon = io.BytesIO()
    Image.new("RGB", (800, 400), (124, 58, 237)).save(tampon, format="PNG")
    y = await istemci.post(f"{M}/{ev['id']}/kapak", files={"dosya": ("kapak.png", tampon.getvalue(), "image/png")}, headers=_b(e))
    assert y.status_code == 200 and y.json()["kapak"].startswith("/api/v1/etkinlik/gorsel/")
    assert (await istemci.get(y.json()["kapak"])).headers["content-type"] == "image/webp"
    await istemci.post(f"{M}/{ev['id']}/indirimler", json={"kod": "SIL", "tur": "yuzde", "deger": 5}, headers=_b(e))
    g = (await _kayit(istemci, ev["slug"], [{"tur_id": turler[0]["id"], "adet": 1}], eposta="silinecek@ornek.com")).json()
    y = await istemci.delete(f"{M}/{ev['id']}", headers=_b(e))
    assert y.status_code == 409 and _kod(y) == "katilimci_var"
    await istemci.put(f"{M}/{ev['id']}", json={"durum": "iptal", "bildir": False}, headers=_b(e))
    assert (await istemci.delete(f"{M}/{ev['id']}", headers=_b(e))).status_code == 200
    kayitlar = (await db_oturumu.execute(select(CopKutusu).where(CopKutusu.sahip_email == e))).scalars().all()
    assert {k_.tablo for k_ in kayitlar} == {"etkinlikler", "etkinlik_bilet_turleri", "etkinlik_indirim_kodlari"}
    assert len({k_.grup for k_ in kayitlar}) == 1
    sp = (await db_oturumu.execute(select(EtkinlikSiparisleri).where(EtkinlikSiparisleri.etkinlik_id == ev["id"]))).scalars().first()
    assert sp.anonim and sp.eposta is None  # kişisel alanlar hemen silindi
    assert (await istemci.get(f"{A}/{ev['slug']}")).status_code == 404
    assert (await istemci.get(f"{A}/bilet/{g['jeton']}")).status_code == 404


async def test_saklama_suresi_dolunca_anonimlestirme(istemci, yonetici_basligi, _ortam):
    from core.database import db_manager
    from services import etkinlik_kayit as k

    ev, turler = await _etkinlik(istemci, yonetici_basligi, saklama_gun=30)
    g = (await _kayit(istemci, ev["slug"], [{"tur_id": turler[0]["id"], "adet": 1}], eposta="saklama@ornek.com")).json()
    _ortam["an"] = datetime(2026, 12, 10, tzinfo=UTC)
    async with db_manager.async_session_maker() as db:
        sonuc = await k.zamanli_bakim(db)
    assert sonuc["anonimlestirilen"] >= 1
    satir = (await istemci.get(f"{Y}/{ev['id']}/katilimcilar", headers=yonetici_basligi)).json()["items"][0]
    assert satir["siparis"]["eposta"] is None and satir["siparis"]["anonim"] is True
    assert (await istemci.get(f"{A}/bilet/{g['jeton']}")).status_code == 410


def test_modul_izin_bildirim_ve_kayit():
    from core import moduller as mf
    from services import bildirim_tercih as bt
    from services import denetim
    from services import hesap_ekibi as he
    from services.zamanli import GOREV_ADLARI

    m = mf.MODUL_SOZLUGU["etkinlik_bilet"]
    assert m.kategori == "is_araclari" and not m.varsayilan_acik and m.musteri_sekmesi == "etkinlik"
    assert m.varsayilan_ayarlar() == {"aylik_etkinlik_siniri": 5, "kapasite_siniri": 500}
    assert {"etkinlik", "etkinlik_giris"} <= set(he.IZINLER)
    assert "etkinlik_giris" in he.ROL_VARSAYILAN["uye"] and "etkinlik" not in he.ROL_VARSAYILAN["uye"]
    assert he.OLAY_IZNI["etkinlik_kayit"] == "etkinlik" and "etkinlik_katilimci" not in he.OLAY_IZNI
    assert "etkinlik_kayit" in bt.OLAYLAR and "etkinlik_katilimci" not in bt.OLAYLAR
    for tablo in ("etkinlik_siparisleri", "etkinlik_biletleri", "etkinlik_bekleme", "etkinlik_okutmalar"):
        assert tablo in denetim.HARIC_TABLOLAR
    assert "etkinlik_bakimi" in GOREV_ADLARI and GOREV_ADLARI[-1] == "aylik_site_analizi"
