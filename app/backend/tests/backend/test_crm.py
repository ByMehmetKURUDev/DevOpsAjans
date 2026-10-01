"""Faz 3C — CRM ve aday hunisi + gömülebilir form.

Kapsam:
* Yetki: bütün yönetici uçları oturumsuz 401, müşteriye 403; form ucu herkese
  açık ama sınırlı (köken, hız, bal küpü, süre jetonu, KVKK, uzunluk).
* Otomatik aday: her kaynaktan (iletişim, bekleme, keşif, kaynaklar,
  marketplace, site analizi, fiyat teklifi) — aynı e-postada tekilleştirme;
  kanca hata verse de asıl talep kaydediliyor (SAVEPOINT).
* İçe aktarma idempotent; aşama taşıma aktivitesi; aşama silmede taşıma
  zorunluluğu; dönüştürme davet gönderiyor; puan kuralları; hatırlatma günde bir.
"""

import json
import time
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from conftest import jeton_uret

K = "/api/v1/crm"


def _e(on: str = "aday") -> str:
    return f"{on}-{uuid.uuid4().hex[:8]}@ornek-firma.com"


@pytest.fixture(autouse=True)
def _temiz():
    from routers import crm as r

    r.hiz_sinirlarini_temizle()
    yield
    r.hiz_sinirlarini_temizle()


async def _adaylar(db, email: str):
    from models.crm import CrmAdaylari

    return list(
        (await db.execute(select(CrmAdaylari).where(CrmAdaylari.email == email.lower())
                          .execution_options(populate_existing=True))).scalars().all()
    )


async def _aktiviteler(db, aday_id: int):
    from models.crm import CrmAktiviteler

    return list(
        (await db.execute(select(CrmAktiviteler).where(CrmAktiviteler.aday_id == aday_id).order_by(CrmAktiviteler.id)
                          .execution_options(populate_existing=True))).scalars().all()
    )


async def _bagli(db, aday_id: int):
    from models.crm import CrmBagliKayitlar

    return list((await db.execute(select(CrmBagliKayitlar).where(CrmBagliKayitlar.aday_id == aday_id))).scalars().all())


async def _talep(istemci, email: str, source: str = "iletisim-formu", message: str = "Merhaba, web sitesi istiyoruz.", **ek):
    govde = {"name": "Ayşe Yılmaz", "email": email, "message": message, "status": "new", **ek}
    if source is not None:
        govde["source"] = source
    y = await istemci.post("/api/v1/entities/inquiries", json=govde)
    assert y.status_code == 201, y.text
    return y.json()


async def _aday_olustur(istemci, yonetici_basligi, **alanlar):
    govde = {"ad": "Elle Aday", **alanlar}
    y = await istemci.post(f"{K}/adaylar", json=govde, headers=yonetici_basligi)
    assert y.status_code == 201, y.text
    return y.json()


# ---------------------------------------------------------------------------
# Yetki
# ---------------------------------------------------------------------------
YONETICI_UCLARI = [
    ("GET", "/meta"), ("GET", "/adaylar"), ("POST", "/adaylar"), ("GET", "/kanban"), ("GET", "/adaylar/1"),
    ("PATCH", "/adaylar/1"), ("DELETE", "/adaylar/1"), ("POST", "/adaylar/1/asama"), ("POST", "/adaylar/1/aktivite"),
    ("POST", "/adaylar/1/donustur"), ("GET", "/asamalar"), ("POST", "/asamalar"), ("PUT", "/asamalar/sira"),
    ("PATCH", "/asamalar/yeni"), ("DELETE", "/asamalar/yeni"), ("GET", "/ozet"), ("POST", "/ice-aktar"),
    ("GET", "/formlar"), ("POST", "/formlar"), ("PATCH", "/formlar/1"), ("DELETE", "/formlar/1"),
]


@pytest.mark.parametrize("metot,yol", YONETICI_UCLARI, ids=[f"{m} {y}" for m, y in YONETICI_UCLARI])
async def test_yonetici_uclari_anonime_401_musteriye_403(istemci, musteri_basligi, metot, yol):
    govde = {} if metot in ("POST", "PATCH", "PUT") else None
    y = await istemci.request(metot, K + yol, json=govde)
    assert y.status_code == 401, (yol, y.status_code)
    y = await istemci.request(metot, K + yol, json=govde, headers=musteri_basligi(_e("musteri")))
    assert y.status_code == 403, (yol, y.status_code)


async def test_form_ucu_herkese_acik_ama_bilinmeyen_anahtar_404(istemci):
    assert (await istemci.get("/api/v1/crm/form/yok-boyle-bir-anahtar")).status_code == 404
    y = await istemci.post("/api/v1/crm/form/yok-boyle-bir-anahtar", content=b"{}")
    assert y.status_code == 404 and y.json()["detail"]["kod"] == "form_yok"


async def test_varsayilan_asamalar_tohumlaniyor(istemci, yonetici_basligi):
    y = await istemci.get(f"{K}/asamalar", headers=yonetici_basligi)
    assert y.status_code == 200
    asamalar = y.json()["asamalar"]
    anahtarlar = [a["anahtar"] for a in asamalar]
    for beklenen in ("yeni", "iletisim_kuruldu", "kesif_gorusmesi", "teklif_gonderildi", "pazarlik", "kazanildi", "kaybedildi"):
        assert beklenen in anahtarlar
    turler = {a["anahtar"]: a["tur"] for a in asamalar}
    assert turler["kazanildi"] == "kazanildi" and turler["kaybedildi"] == "kaybedildi" and turler["yeni"] == "acik"
    yeni = next(a for a in asamalar if a["anahtar"] == "yeni")
    assert set(yeni["ceviriler"]) == {"en", "de", "ru", "zh", "hi", "ar"}


# ---------------------------------------------------------------------------
# Otomatik aday — her kaynaktan
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "source,beklenen",
    [
        ("iletisim-formu", "iletisim"),
        ("bekleme_listesi", "bekleme"),
        ("kesif", "kesif"),
        ("kesif-sihirbazi", "kesif"),
        ("kaynaklar: claude-skills", "kaynaklar"),
        ("marketplace: Kartvizit web sitesi", "iletisim"),
        (None, "iletisim"),
    ],
)
async def test_talepten_otomatik_aday(istemci, db_oturumu, source, beklenen):
    email = _e()
    talep = await _talep(istemci, email.upper(), source=source)
    adaylar = await _adaylar(db_oturumu, email)
    assert len(adaylar) == 1
    a = adaylar[0]
    assert a.kaynak == beklenen and a.kaynak_tablo == "inquiries" and a.kaynak_id == talep["id"]
    assert a.asama == "yeni" and a.email == email.lower() and a.ad == "Ayşe Yılmaz"
    assert a.bildirim_bekliyor is False  # iletişim talebi kendi bildirimini zaten gönderiyor
    assert [(b.tablo, b.kayit_id) for b in await _bagli(db_oturumu, a.id)] == [("inquiries", talep["id"])]
    akt = await _aktiviteler(db_oturumu, a.id)
    assert [(k.tur, k.olay) for k in akt] == [("sistem", "aday_olustu")]
    assert json.loads(akt[0].veri)["kaynak"] == beklenen
    assert a.puan > 0 and json.loads(a.puan_ayrinti)[0]["kural"] == "kaynak"


async def test_kesif_ozetindeki_butce_okunuyor(istemci, db_oturumu):
    email = _e("kesif")
    mesaj = "Keşif özeti\n\nAmaç: E-ticaret\nBütçe aralığı: Orta\n\nÖnerilen paket: Beta"
    await _talep(istemci, email, source="kesif", message=mesaj)
    a = (await _adaylar(db_oturumu, email))[0]
    assert a.butce == "Orta"
    ayrinti = {k["kural"]: k for k in json.loads(a.puan_ayrinti)}
    assert ayrinti["butce"]["puan"] == 15 and ayrinti["kaynak"]["puan"] == 25


async def test_site_analizi_adayi_orm_yolundan(db_oturumu):
    """Site analizi router'ı `Inquiries`'i doğrudan ORM ile ekliyor: kanca onu da yakalıyor."""
    from models.inquiries import Inquiries

    email = _e("analiz")
    t = Inquiries(name="Analiz", email=email, subject="Site analizi: ornek.com", message="Tam rapor", status="new",
                  source="site_analizi")
    db_oturumu.add(t)
    await db_oturumu.commit()
    a = (await _adaylar(db_oturumu, email))[0]
    assert a.kaynak == "site_analizi" and a.kaynak_id == t.id


async def test_fiyat_tekliften_aday_deger_ve_bildirim_bekliyor(istemci, db_oturumu):
    email = _e("teklif")
    y = await istemci.post("/api/v1/fiyat-teklif", json={"kredi_paketi": 10, "musteri_eposta": email, "musteri_adi": "Can"})
    assert y.status_code == 200, y.text
    a = (await _adaylar(db_oturumu, email))[0]
    assert a.kaynak == "fiyat_teklifi" and a.kaynak_tablo == "pricing_inquiries" and a.kaynak_id == y.json()["inquiry_id"]
    assert a.deger_tahmini and a.deger_tahmini > 0 and a.para_birimi == "USD"
    assert a.bildirim_bekliyor is True

    # Zamanlı görev bildirimi gönderir ve işareti kaldırır.
    from models.notifications import Notifications
    from services.crm import bekleyen_bildirimleri_gonder

    sonuc = await bekleyen_bildirimleri_gonder(db_oturumu)
    assert sonuc["gonderilen"] >= 1
    a = (await _adaylar(db_oturumu, email))[0]
    assert a.bildirim_bekliyor is False
    satir = (
        await db_oturumu.execute(
            select(Notifications).where(Notifications.event_type == "crm_yeni_aday", Notifications.ref_id == a.id,
                                        Notifications.channel == "inapp")
        )
    ).scalars().first()
    assert satir is not None and satir.recipient_role == "admin" and satir.link == f"/admin?sekme=crm&aday={a.id}"


async def test_ayni_epostada_tekillestirme_ve_kapanmis_adaydan_sonra_yeni(istemci, yonetici_basligi, db_oturumu):
    email = _e("tekil")
    t1 = await _talep(istemci, email, source="iletisim-formu")
    a = (await _adaylar(db_oturumu, email))[0]
    ilk_puan = a.puan
    t2 = await _talep(istemci, email.upper(), source="bekleme_listesi", message="İkinci mesaj")
    adaylar = await _adaylar(db_oturumu, email)
    assert len(adaylar) == 1
    a = adaylar[0]
    assert sorted(b.kayit_id for b in await _bagli(db_oturumu, a.id)) == sorted([t1["id"], t2["id"]])
    akt = await _aktiviteler(db_oturumu, a.id)
    assert [k.olay for k in akt] == ["aday_olustu", "talep_eklendi"]
    assert akt[1].metin == "İkinci mesaj" and json.loads(akt[1].veri)["kaynak"] == "bekleme"
    assert a.puan == ilk_puan + 5  # ikinci talep = bir etkileşim

    # Kazanıldı → kapalı; aynı kişi yeniden yazınca yeni fırsat açılır.
    y = await istemci.post(f"{K}/adaylar/{a.id}/asama", json={"asama": "kazanildi"}, headers=yonetici_basligi)
    assert y.status_code == 200
    await _talep(istemci, email, source="iletisim-formu", message="Yeni proje")
    adaylar = await _adaylar(db_oturumu, email)
    assert len(adaylar) == 2 and {x.asama for x in adaylar} == {"kazanildi", "yeni"}


async def test_kanca_hatasi_asil_talebi_bozmaz(istemci, db_oturumu, monkeypatch):
    from models.inquiries import Inquiries
    from services import crm

    def patla(*_a, **_k):
        raise RuntimeError("CRM yazılamadı")

    monkeypatch.setattr(crm, "kayittan_aday_sync", patla)
    email = _e("hata")
    talep = await _talep(istemci, email)
    assert (await db_oturumu.execute(select(Inquiries).where(Inquiries.id == talep["id"]))).scalar_one() is not None
    assert await _adaylar(db_oturumu, email) == []


async def test_kancada_veritabani_hatasi_yalniz_savepointi_geri_alir(istemci, db_oturumu, monkeypatch):
    """Aday yazımı SQL hatası verirse talep yine kaydediliyor; yarım CRM satırı kalmıyor."""
    from models.crm import CrmBagliKayitlar
    from models.inquiries import Inquiries
    from services import crm
    from sqlalchemy import text

    class Bozuk:
        def values(self, **_k):
            return text("INSERT INTO crm_olmayan_tablo (x) VALUES (1)")

    monkeypatch.setattr(crm, "_aday_ekleme_sorgusu", lambda: Bozuk())
    email = _e("sql")
    talep = await _talep(istemci, email)
    assert (await db_oturumu.execute(select(Inquiries).where(Inquiries.id == talep["id"]))).scalar_one() is not None
    assert await _adaylar(db_oturumu, email) == []
    bag = (await db_oturumu.execute(
        select(CrmBagliKayitlar).where(CrmBagliKayitlar.tablo == "inquiries", CrmBagliKayitlar.kayit_id == talep["id"])
    )).scalars().all()
    assert bag == []


# ---------------------------------------------------------------------------
# Geçmiş talepleri içe aktar
# ---------------------------------------------------------------------------
async def test_gecmisi_ice_aktar_idempotent(istemci, yonetici_basligi, db_oturumu):
    from datetime import datetime, timezone

    from models.inquiries import Inquiries
    from models.pricing import Pricing_inquiries

    # CRM'den önceki kayıtlar gibi: kanca kapalı eklenir.
    db_oturumu.sync_session.info["crm_kanca_kapali"] = True
    e1, e2 = _e("eski"), _e("eskiteklif")
    eski = datetime(2025, 1, 5, 10, 0, tzinfo=timezone.utc)
    db_oturumu.add_all([
        Inquiries(name="Eski 1", email=e1, message="İlk", status="new", source="iletisim-formu", created_at=eski),
        Inquiries(name="Eski 1", email=e1, message="İkinci", status="new", source="kesif",
                  created_at=eski + timedelta(days=3)),
        Pricing_inquiries(scale_kod="BETA", profile_kod="kobi", period="aylik", hesaplanan_tutar=250, musteri_eposta=e2,
                          musteri_adi="Eski Teklif", created_at=eski + timedelta(days=1)),
    ])
    await db_oturumu.commit()
    db_oturumu.sync_session.info.pop("crm_kanca_kapali", None)
    assert await _adaylar(db_oturumu, e1) == [] and await _adaylar(db_oturumu, e2) == []

    y = await istemci.post(f"{K}/ice-aktar", headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    ilk = y.json()
    assert ilk["olusturulan"] >= 2 and ilk["eklenen"] >= 1
    a1 = await _adaylar(db_oturumu, e1)
    assert len(a1) == 1 and a1[0].kaynak == "iletisim"  # en eski talep adayı açtı
    assert a1[0].created_at.replace(tzinfo=None) == eski.replace(tzinfo=None)
    akt = await _aktiviteler(db_oturumu, a1[0].id)
    assert [k.olay for k in akt] == ["aday_olustu", "talep_eklendi"]
    assert all(json.loads(k.veri).get("ice_aktarma") for k in akt)
    a2 = await _adaylar(db_oturumu, e2)
    assert len(a2) == 1 and a2[0].kaynak == "fiyat_teklifi" and a2[0].deger_tahmini == 250
    assert a2[0].bildirim_bekliyor is False  # içe aktarma bildirim göndermez

    y = await istemci.post(f"{K}/ice-aktar", headers=yonetici_basligi)
    assert y.json()["olusturulan"] == 0 and y.json()["eklenen"] == 0
    assert len(await _adaylar(db_oturumu, e1)) == 1 and len(await _aktiviteler(db_oturumu, a1[0].id)) == 2


# ---------------------------------------------------------------------------
# Elle aday, liste, kanban, güncelleme
# ---------------------------------------------------------------------------
async def test_elle_aday_ve_ayni_eposta_409(istemci, yonetici_basligi):
    email = _e("elle")
    a = await _aday_olustur(istemci, yonetici_basligi, email=email.upper(), firma="Ornek A.Ş.", deger_tahmini=5000,
                            para_birimi="TRY", etiketler=["Web", "web", " SEO "])
    assert a["email"] == email and a["kaynak"] == "manuel" and a["asama"] == "yeni" and a["olasilik"] == 10
    assert a["etiketler"] == ["web", "seo"]
    y = await istemci.post(f"{K}/adaylar", json={"ad": "Tekrar", "email": email}, headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"] == {"kod": "ayni_eposta_acik_aday", "aday_id": a["id"]}
    y = await istemci.post(f"{K}/adaylar", json={"ad": "", "email": _e()}, headers=yonetici_basligi)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "alan_gerekli"
    y = await istemci.post(f"{K}/adaylar", json={"ad": "X", "email": "gecersiz"}, headers=yonetici_basligi)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "eposta_gecersiz"
    y = await istemci.post(f"{K}/adaylar", json={"ad": "X" * 121}, headers=yonetici_basligi)
    assert y.status_code == 400 and y.json()["detail"] == {"kod": "alan_uzun", "alan": "ad", "en_cok": 120}


async def test_liste_suzgec_siralama_sayfa(istemci, yonetici_basligi):
    etiket = f"liste-{uuid.uuid4().hex[:6]}"
    sorumlu = _e("sorumlu")
    a1 = await _aday_olustur(istemci, yonetici_basligi, ad="Zeynep Liste", email=_e(), etiketler=[etiket], kaynak="eposta")
    a2 = await _aday_olustur(istemci, yonetici_basligi, ad="Ali Liste", email=_e(), etiketler=[etiket], sorumlu=sorumlu,
                             deger_tahmini=100)
    a3 = await _aday_olustur(istemci, yonetici_basligi, ad="Berk Liste", etiketler=[etiket])
    y = await istemci.get(f"{K}/adaylar", params={"etiket": etiket, "siralama": "ad"}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["toplam"] == 3
    assert [x["id"] for x in y.json()["items"]] == [a2["id"], a3["id"], a1["id"]]
    y = await istemci.get(f"{K}/adaylar", params={"etiket": etiket, "sorumlu": sorumlu}, headers=yonetici_basligi)
    assert [x["id"] for x in y.json()["items"]] == [a2["id"]]
    y = await istemci.get(f"{K}/adaylar", params={"etiket": etiket, "sorumlu": "-"}, headers=yonetici_basligi)
    assert {x["id"] for x in y.json()["items"]} == {a1["id"], a3["id"]}
    y = await istemci.get(f"{K}/adaylar", params={"etiket": etiket, "kaynak": "eposta"}, headers=yonetici_basligi)
    assert [x["id"] for x in y.json()["items"]] == [a1["id"]]
    y = await istemci.get(f"{K}/adaylar", params={"etiket": etiket, "ara": "zeyn"}, headers=yonetici_basligi)
    assert [x["id"] for x in y.json()["items"]] == [a1["id"]]
    y = await istemci.get(f"{K}/adaylar", params={"etiket": etiket, "siralama": "ad", "boyut": 2, "sayfa": 2},
                          headers=yonetici_basligi)
    assert y.json()["toplam"] == 3 and [x["id"] for x in y.json()["items"]] == [a1["id"]]
    y = await istemci.get(f"{K}/adaylar", params={"siralama": "sifre"}, headers=yonetici_basligi)
    assert y.status_code == 400


async def test_kanban_asama_basina_sayi_ve_toplam(istemci, yonetici_basligi):
    etiket = f"kanban-{uuid.uuid4().hex[:6]}"
    await _aday_olustur(istemci, yonetici_basligi, ad="K1", etiketler=[etiket], deger_tahmini=1000, para_birimi="TRY")
    await _aday_olustur(istemci, yonetici_basligi, ad="K2", etiketler=[etiket], deger_tahmini=500, para_birimi="TRY")
    await _aday_olustur(istemci, yonetici_basligi, ad="K3", etiketler=[etiket], deger_tahmini=20, para_birimi="USD",
                        asama="pazarlik")
    y = await istemci.get(f"{K}/kanban", params={"etiket": etiket}, headers=yonetici_basligi)
    assert y.status_code == 200
    sutunlar = {s["anahtar"]: s for s in y.json()["asamalar"]}
    assert sutunlar["yeni"]["sayi"] == 2 and sutunlar["yeni"]["toplam_deger"] == {"TRY": 1500.0}
    assert sutunlar["pazarlik"]["sayi"] == 1 and sutunlar["pazarlik"]["toplam_deger"] == {"USD": 20.0}
    assert [s["anahtar"] for s in y.json()["asamalar"]][0] == "yeni"


async def test_guncelleme_ve_puan_yeniden(istemci, yonetici_basligi):
    a = await _aday_olustur(istemci, yonetici_basligi, ad="Puan", email=_e("puan").replace("ornek-firma.com", "gmail.com"))
    onceki = a["puan"]
    y = await istemci.patch(f"{K}/adaylar/{a['id']}", json={"email": "kisi@kurumsal-firma.com.tr", "deger_tahmini": 3000,
                                                            "sonraki_adim": "Teklifi ara", "sonraki_adim_tarihi": "2030-01-02"},
                            headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    d = y.json()
    assert d["puan"] == onceki + 15 + 15  # alan adı kurumsal (+15) ve bütçe (+15)
    assert d["sonraki_adim_tarihi"] == "2030-01-02" and d["gecikti"] is False
    y = await istemci.patch(f"{K}/adaylar/{a['id']}", json={"sonraki_adim_tarihi": "bozuk"}, headers=yonetici_basligi)
    assert y.status_code == 400
    y = await istemci.patch(f"{K}/adaylar/{a['id']}", json={"olasilik": 120}, headers=yonetici_basligi)
    assert y.status_code == 400
    y = await istemci.patch(f"{K}/adaylar/{a['id']}", json={"etiketler": ["x" * 41]}, headers=yonetici_basligi)
    assert y.status_code == 400


async def test_aktivite_ekleme_puani_artirir(istemci, yonetici_basligi):
    a = await _aday_olustur(istemci, yonetici_basligi, ad="Aktivite")
    y = await istemci.post(f"{K}/adaylar/{a['id']}/aktivite", json={"tur": "arama", "metin": "Telefonla konuşuldu"},
                           headers=yonetici_basligi)
    assert y.status_code == 201, y.text
    assert y.json()["aktivite"]["tur"] == "arama" and y.json()["aktivite"]["yapan"] == "yonetici@test.dev"
    assert y.json()["aday"]["puan"] == a["puan"] + 5
    y = await istemci.post(f"{K}/adaylar/{a['id']}/aktivite", json={"tur": "asama", "metin": "x"}, headers=yonetici_basligi)
    assert y.status_code == 400
    y = await istemci.post(f"{K}/adaylar/{a['id']}/aktivite", json={"tur": "not", "metin": "  "}, headers=yonetici_basligi)
    assert y.status_code == 400
    y = await istemci.get(f"{K}/adaylar/{a['id']}", headers=yonetici_basligi)
    turler = [k["tur"] for k in y.json()["aktiviteler"]]
    assert turler == ["arama", "sistem"]  # yeniden eskiye


# ---------------------------------------------------------------------------
# Aşama taşıma ve aşama yönetimi
# ---------------------------------------------------------------------------
async def test_asama_tasima_aktivite_kaydi(istemci, yonetici_basligi, db_oturumu):
    a = await _aday_olustur(istemci, yonetici_basligi, ad="Taşı")
    y = await istemci.post(f"{K}/adaylar/{a['id']}/asama", json={"asama": "teklif_gonderildi"}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["degisti"] is True
    d = y.json()["aday"]
    assert d["asama"] == "teklif_gonderildi" and d["olasilik"] == 60 and d["asama_degisme_at"] >= a["asama_degisme_at"]
    akt = await _aktiviteler(db_oturumu, a["id"])
    son = akt[-1]
    assert son.tur == "asama" and son.olay == "asama_degisti" and json.loads(son.veri) == {"eski": "yeni", "yeni": "teklif_gonderildi"}
    assert son.yapan == "yonetici@test.dev"
    # Aynı aşama: değişiklik yok, yeni aktivite yok.
    y = await istemci.post(f"{K}/adaylar/{a['id']}/asama", json={"asama": "teklif_gonderildi"}, headers=yonetici_basligi)
    assert y.json()["degisti"] is False and len(await _aktiviteler(db_oturumu, a["id"])) == len(akt)
    # Kaybedildi: neden kaydediliyor.
    y = await istemci.post(f"{K}/adaylar/{a['id']}/asama", json={"asama": "kaybedildi", "kaybedilme_nedeni": "Bütçe yetmedi"},
                           headers=yonetici_basligi)
    assert y.json()["aday"]["kaybedilme_nedeni"] == "Bütçe yetmedi" and y.json()["aday"]["olasilik"] == 0
    y = await istemci.post(f"{K}/adaylar/{a['id']}/asama", json={"asama": "boyle-yok"}, headers=yonetici_basligi)
    assert y.status_code == 404


async def test_asama_yonetimi_ekle_adlandir_sirala_sil_tasima_zorunlu(istemci, yonetici_basligi, db_oturumu):
    y = await istemci.post(f"{K}/asamalar", json={"ad": "Sözleşme Hazırlığı", "renk": "teal", "olasilik": 90},
                           headers=yonetici_basligi)
    assert y.status_code == 201, y.text
    yeni = y.json()
    assert yeni["anahtar"].startswith("sozlesme_hazirligi") and yeni["tur"] == "acik"
    y = await istemci.patch(f"{K}/asamalar/{yeni['anahtar']}",
                            json={"ad": "Sözleşme", "ceviriler": {"en": {"ad": "Contract"}, "xx": {"ad": "?"}}},
                            headers=yonetici_basligi)
    assert y.json()["ad"] == "Sözleşme" and y.json()["ceviriler"] == {"en": {"ad": "Contract"}}
    y = await istemci.patch(f"{K}/asamalar/{yeni['anahtar']}", json={"renk": "mor"}, headers=yonetici_basligi)
    assert y.status_code == 400

    liste = (await istemci.get(f"{K}/asamalar", headers=yonetici_basligi)).json()["asamalar"]
    sira = [a["anahtar"] for a in liste]
    sira.remove(yeni["anahtar"])
    sira.insert(0, yeni["anahtar"])
    y = await istemci.put(f"{K}/asamalar/sira", json={"anahtarlar": sira}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["asamalar"][0]["anahtar"] == yeni["anahtar"]
    y = await istemci.put(f"{K}/asamalar/sira", json={"anahtarlar": sira[:-1]}, headers=yonetici_basligi)
    assert y.status_code == 400
    # Sırayı geri al (diğer testler "yeni"nin ilk açık aşama olduğunu varsayıyor).
    sira.remove(yeni["anahtar"])
    sira.append(yeni["anahtar"])
    assert (await istemci.put(f"{K}/asamalar/sira", json={"anahtarlar": sira}, headers=yonetici_basligi)).status_code == 200

    a = await _aday_olustur(istemci, yonetici_basligi, ad="Silinecek aşamada", asama=yeni["anahtar"])
    y = await istemci.delete(f"{K}/asamalar/{yeni['anahtar']}", headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"] == {"kod": "tasima_gerekli", "sayi": 1}
    y = await istemci.delete(f"{K}/asamalar/{yeni['anahtar']}", params={"hedef": yeni["anahtar"]}, headers=yonetici_basligi)
    assert y.status_code == 400
    y = await istemci.delete(f"{K}/asamalar/{yeni['anahtar']}", params={"hedef": "pazarlik"}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json() == {"silindi": True, "tasinan": 1}
    d = (await istemci.get(f"{K}/adaylar/{a['id']}", headers=yonetici_basligi)).json()
    assert d["aday"]["asama"] == "pazarlik"
    son = d["aktiviteler"][0]
    assert son["olay"] == "asama_degisti" and son["veri"] == {"eski": yeni["anahtar"], "yeni": "pazarlik", "sebep": "asama_silindi"}
    assert yeni["anahtar"] not in [x["anahtar"] for x in (await istemci.get(f"{K}/asamalar", headers=yonetici_basligi)).json()["asamalar"]]


async def test_son_kazanildi_ya_da_kaybedildi_asamasi_silinemez(istemci, yonetici_basligi):
    y = await istemci.delete(f"{K}/asamalar/kazanildi", headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "son_tur_asamasi"
    y = await istemci.patch(f"{K}/asamalar/kaybedildi", json={"tur": "acik"}, headers=yonetici_basligi)
    assert y.status_code == 409


# ---------------------------------------------------------------------------
# Müşteriye dönüştür
# ---------------------------------------------------------------------------
async def test_musteriye_donustur_davet_olusturur(istemci, yonetici_basligi, db_oturumu):
    from models.notifications import Notifications

    email = _e("donustur")
    a = await _aday_olustur(istemci, yonetici_basligi, ad="Dönüşen", email=email, firma="Dönüşen Ltd.")
    y = await istemci.post(f"{K}/adaylar/{a['id']}/donustur", json={}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    d = y.json()
    assert d["aday"]["asama"] == "kazanildi" and d["aday"]["musteri_email"] == email
    assert d["davet"]["ok"] is True and d["davet"]["link"] == "/client" and email in d["davet"]["message"]
    davet = (await db_oturumu.execute(
        select(Notifications).where(Notifications.event_type == "client_invite", Notifications.recipient_email == email)
    )).scalars().all()
    assert davet, "davet bildirimi yazılmadı"
    akt = await _aktiviteler(db_oturumu, a["id"])
    assert [k.olay for k in akt][-2:] == ["asama_degisti", "donusturuldu"]
    assert json.loads(akt[-1].veri)["musteri_email"] == email

    b = await _aday_olustur(istemci, yonetici_basligi, ad="E-postasız")
    y = await istemci.post(f"{K}/adaylar/{b['id']}/donustur", json={}, headers=yonetici_basligi)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "eposta_yok"


# ---------------------------------------------------------------------------
# Silme → çöp kutusu → geri al
# ---------------------------------------------------------------------------
async def test_aday_silme_cop_kutusuna_ve_geri_alma(istemci, yonetici_basligi, db_oturumu):
    from models.cop_kutusu import CopKutusu

    email = _e("sil")
    await _talep(istemci, email)
    a = (await _adaylar(db_oturumu, email))[0]
    await istemci.post(f"{K}/adaylar/{a.id}/aktivite", json={"tur": "not", "metin": "Not"}, headers=yonetici_basligi)
    y = await istemci.delete(f"{K}/adaylar/{a.id}", headers=yonetici_basligi)
    assert y.status_code == 200
    assert await _adaylar(db_oturumu, email) == []
    cop = (await db_oturumu.execute(
        select(CopKutusu).where(CopKutusu.tablo == "crm_adaylar", CopKutusu.kayit_id == str(a.id))
    )).scalars().first()
    assert cop is not None
    # İçe aktarma silinen adayı geri getirmez (bağlı kayıt işareti duruyor).
    await istemci.post(f"{K}/ice-aktar", headers=yonetici_basligi)
    assert await _adaylar(db_oturumu, email) == []
    y = await istemci.post(f"/api/v1/cop-kutusu/{cop.id}/geri-al", headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    geri = await _adaylar(db_oturumu, email)
    assert len(geri) == 1 and geri[0].id == a.id
    assert [k.olay or k.tur for k in await _aktiviteler(db_oturumu, a.id)] == ["aday_olustu", "not"]
    d = (await istemci.get(f"{K}/adaylar/{a.id}", headers=yonetici_basligi)).json()
    assert d["bagli_kayitlar"][0]["tablo"] == "inquiries" and d["bagli_kayitlar"][0]["baslik"]


# ---------------------------------------------------------------------------
# Puan kuralları (saf fonksiyon)
# ---------------------------------------------------------------------------
def test_puan_kurallari():
    from services.crm import alan_adi_turu, kaynak_esle, puan_hesapla

    puan, ayrinti = puan_hesapla(kaynak="fiyat_teklifi", email="ceo@firma.com.tr", deger_tahmini=1000,
                                 ilk_mesaj="x" * 300, etkilesim=9)
    assert puan == 100 and [a["kural"] for a in ayrinti] == ["kaynak", "butce", "kapsam", "alan_adi", "etkilesim"]
    assert {a["kural"]: a["puan"] for a in ayrinti} == {"kaynak": 30, "butce": 15, "kapsam": 10, "alan_adi": 20, "etkilesim": 25}

    puan, ayrinti = puan_hesapla(kaynak="bekleme", email="kisi@gmail.com")
    assert puan == 5 + 5
    assert {a["kural"]: a["deger"] for a in ayrinti}["alan_adi"] == "ucretsiz"

    assert puan_hesapla(kaynak="iletisim", email=None, ilk_mesaj="y" * 100)[0] == 20 + 5
    assert puan_hesapla(kaynak="iletisim", email=None, ilk_mesaj="y" * 99)[0] == 20
    assert puan_hesapla(kaynak="manuel", email=None, butce="Orta")[0] == 10 + 15
    assert puan_hesapla(kaynak="bilinmeyen", email=None)[0] == 10
    assert puan_hesapla(kaynak="form", email="a@b.co", etkilesim=2)[0] == 20 + 20 + 10
    assert alan_adi_turu("x@HOTMAIL.com.tr") == "ucretsiz" and alan_adi_turu("x@ajans.io") == "kurumsal"
    assert alan_adi_turu("bozuk") == "yok"
    assert kaynak_esle("pricing_inquiries", "website") == "fiyat_teklifi"
    assert kaynak_esle("crm_form_gonderimleri", None) == "form"
    assert kaynak_esle("inquiries", "site_analizi") == "site_analizi"


# ---------------------------------------------------------------------------
# Özet
# ---------------------------------------------------------------------------
async def test_ozet_huni_kaynak_sure_bu_ay(istemci, yonetici_basligi):
    once = (await istemci.get(f"{K}/ozet", headers=yonetici_basligi)).json()
    a = await _aday_olustur(istemci, yonetici_basligi, ad="Özet 1", kaynak="eposta", deger_tahmini=700, para_birimi="EUR")
    b = await _aday_olustur(istemci, yonetici_basligi, ad="Özet 2", kaynak="eposta")
    for asama in ("iletisim_kuruldu", "teklif_gonderildi", "kazanildi"):
        await istemci.post(f"{K}/adaylar/{a['id']}/asama", json={"asama": asama}, headers=yonetici_basligi)
    await istemci.post(f"{K}/adaylar/{b['id']}/asama", json={"asama": "iletisim_kuruldu"}, headers=yonetici_basligi)
    await istemci.post(f"{K}/adaylar/{b['id']}/asama", json={"asama": "kaybedildi"}, headers=yonetici_basligi)
    y = await istemci.get(f"{K}/ozet", headers=yonetici_basligi)
    assert y.status_code == 200
    d = y.json()
    huni = {h["anahtar"]: h for h in d["huni"]}
    assert "kaybedildi" not in huni
    on = {h["anahtar"]: h for h in once["huni"]}
    assert huni["yeni"]["ulasan"] - on["yeni"]["ulasan"] == 2
    assert huni["iletisim_kuruldu"]["ulasan"] - on["iletisim_kuruldu"]["ulasan"] == 2
    assert huni["teklif_gonderildi"]["ulasan"] - on["teklif_gonderildi"]["ulasan"] == 1
    assert huni["kazanildi"]["ulasan"] - on["kazanildi"]["ulasan"] == 1
    assert 0 <= (huni["yeni"]["donusum"] or 0) <= 1
    kaynak = {k["kaynak"]: k for k in d["kaynaklar"]}["eposta"]
    onceki_k = {k["kaynak"]: k for k in once["kaynaklar"]}.get("eposta", {"sayi": 0, "kazanilan": 0, "kaybedilen": 0})
    assert kaynak["sayi"] - onceki_k["sayi"] == 2 and kaynak["kazanilan"] - onceki_k["kazanilan"] == 1
    assert kaynak["kaybedilen"] - onceki_k["kaybedilen"] == 1 and 0 < kaynak["kazanma_orani"] <= 1
    assert d["bu_ay"]["deger"].get("EUR", 0) - once["bu_ay"]["deger"].get("EUR", 0) == 700
    assert {s["anahtar"] for s in d["asama_sureleri"]} >= {"yeni", "iletisim_kuruldu"}


# ---------------------------------------------------------------------------
# Hatırlatma (günde bir)
# ---------------------------------------------------------------------------
async def test_hatirlatma_gunde_bir_ozet(istemci, yonetici_basligi, db_oturumu, monkeypatch):
    from models.notifications import Notifications
    from services import crm, zamanli

    gorev = next(g for g in zamanli.GOREVLER if g.ad == "crm_hatirlatma")
    assert gorev.siklik >= timedelta(hours=20)
    assert "crm_bildirimleri" in zamanli.GOREV_ADLARI and zamanli.GOREV_ADLARI[-1] == "aylik_site_analizi"

    gun = date(2031, 3, 10)
    monkeypatch.setattr(crm, "_bugun", lambda: gun)
    sorumlu = _e("sorumlu")
    a = await _aday_olustur(istemci, yonetici_basligi, ad="Hatırlat", sorumlu=sorumlu, sonraki_adim="Ara",
                            sonraki_adim_tarihi=gun.isoformat())
    b = await _aday_olustur(istemci, yonetici_basligi, ad="Gecikmiş", sonraki_adim="Teklif",
                            sonraki_adim_tarihi=(gun - timedelta(days=2)).isoformat())
    c = await _aday_olustur(istemci, yonetici_basligi, ad="Gelecek", sonraki_adim_tarihi=(gun + timedelta(days=1)).isoformat())
    kapali = await _aday_olustur(istemci, yonetici_basligi, ad="Kapalı", sonraki_adim_tarihi=gun.isoformat())
    await istemci.post(f"{K}/adaylar/{kapali['id']}/asama", json={"asama": "kaybedildi"}, headers=yonetici_basligi)

    async def sayi(eposta):
        return (await db_oturumu.execute(select(func.count()).select_from(Notifications).where(
            Notifications.event_type == "crm_hatirlatma", Notifications.recipient_email == eposta,
            Notifications.channel == "inapp"))).scalar()

    s0_sorumlu, s0_yonetici = await sayi(sorumlu), await sayi("yonetici@test.dev")
    sonuc = await crm.hatirlatmalari_gonder(db_oturumu)
    assert sonuc["aday"] >= 2
    assert await sayi(sorumlu) == s0_sorumlu + 1  # sorumlunun adayı ona
    assert await sayi("yonetici@test.dev") == s0_yonetici + 1  # sorumlusuz olan yöneticiye (tek özet)
    satir = (await db_oturumu.execute(select(Notifications).where(
        Notifications.event_type == "crm_hatirlatma", Notifications.recipient_email == "yonetici@test.dev"
    ).order_by(Notifications.id.desc()))).scalars().first()
    assert "Gecikmiş" in satir.body and "Gelecek" not in satir.body and "Kapalı" not in satir.body

    # Aynı gün ikinci tur: yeni bildirim yok.
    sonuc = await crm.hatirlatmalari_gonder(db_oturumu)
    assert sonuc["aday"] == 0
    assert await sayi(sorumlu) == s0_sorumlu + 1 and await sayi("yonetici@test.dev") == s0_yonetici + 1

    # Ertesi gün: hâlâ yapılmamış adımlar (ve yarına planlanan) yeniden hatırlatılır.
    monkeypatch.setattr(crm, "_bugun", lambda: gun + timedelta(days=1))
    await crm.hatirlatmalari_gonder(db_oturumu)
    assert await sayi(sorumlu) == s0_sorumlu + 2
    _ = (a, b, c)


# ---------------------------------------------------------------------------
# Gömülebilir form
# ---------------------------------------------------------------------------
KVKK = "Kişisel verilerimin aydınlatma metninde belirtilen amaçlarla işlenmesini kabul ediyorum."


async def _form(istemci, yonetici_basligi, **alanlar):
    govde = {
        "ad": "Site formu", "baslik": "Bize yazın", "kvkk_metni": KVKK,
        "aydinlatma_baglantisi": "https://mehmetkuru.dev/kvkk", "izinli_alanlar": ["musteri-sitesi.com"], **alanlar,
    }
    y = await istemci.post(f"{K}/formlar", json=govde, headers=yonetici_basligi)
    assert y.status_code == 201, y.text
    return y.json()


def _jeton(form_id: int, once_sn: float = 5.0) -> str:
    from services.crm_form import jeton_uret

    return jeton_uret(form_id, an=time.time() - once_sn)


async def _gonder(istemci, f, govde=None, *, origin=None, jeton=None, **basliklar):
    veri = {"ad": "Form Kişisi", "email": _e("form"), "mesaj": "Bir web sitesi istiyoruz.", "kvkk_onay": True,
            "jeton": jeton if jeton is not None else _jeton(f["id"]), "dil": "tr", **(govde or {})}
    h = {"content-type": "text/plain;charset=UTF-8", **basliklar}
    if origin:
        h["origin"] = origin
    return await istemci.post(f"/api/v1/crm/form/{f['genel_anahtar']}", content=json.dumps(veri).encode(), headers=h), veri


async def test_form_tanimi_dogrulama(istemci, yonetici_basligi):
    f = await _form(istemci, yonetici_basligi, izinli_alanlar=["https://www.Ornek-Site.com/iletisim", "*.ajans.dev"],
                    varsayilan_etiketler=["Web Formu"], varsayilan_asama="iletisim_kuruldu",
                    alanlar={"email": {"acik": False}, "firma": {"acik": True, "zorunlu": True}, "telefon": {"acik": False, "zorunlu": True}})
    assert f["izinli_alanlar"] == ["ornek-site.com", "ajans.dev"]
    assert f["alanlar"]["email"] == {"acik": True, "zorunlu": True}  # e-posta kapatılamaz
    assert f["alanlar"]["firma"] == {"acik": True, "zorunlu": True}
    assert f["alanlar"]["telefon"] == {"acik": False, "zorunlu": False}
    assert len(f["genel_anahtar"]) >= 12 and f["kvkk_surum"] == 1 and f["varsayilan_etiketler"] == ["web formu"]

    for govde, kod in (
        ({"yonlendirme_adresi": "http://musteri-sitesi.com/tesekkur"}, "yonlendirme_https"),
        ({"yonlendirme_adresi": "javascript:alert(1)"}, "yonlendirme_https"),
        ({"izinli_alanlar": ["bozuk alan adı"]}, "alan_adi_gecersiz"),
        ({"kvkk_metni": "kısa"}, "kvkk_metni_gerekli"),
        ({"aydinlatma_baglantisi": "ftp://x.com/k"}, "aydinlatma_https"),
        ({"varsayilan_asama": "olmayan"}, "asama_yok"),
    ):
        y = await istemci.patch(f"{K}/formlar/{f['id']}", json=govde, headers=yonetici_basligi)
        assert y.status_code == 400 and y.json()["detail"]["kod"] == kod, (govde, y.text)
    y = await istemci.patch(f"{K}/formlar/{f['id']}", json={"yonlendirme_adresi": "https://musteri-sitesi.com/tesekkur"},
                            headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["yonlendirme_adresi"] == "https://musteri-sitesi.com/tesekkur"
    assert y.json()["kvkk_surum"] == 1
    y = await istemci.patch(f"{K}/formlar/{f['id']}", json={"kvkk_metni": KVKK + " (güncel)"}, headers=yonetici_basligi)
    assert y.json()["kvkk_surum"] == 2

    liste = (await istemci.get(f"{K}/formlar", headers=yonetici_basligi)).json()
    assert any(x["id"] == f["id"] for x in liste["formlar"]) and "mehmetkuru.dev" in liste["her_zaman_izinli"]


async def test_form_acik_tanim_dilde(istemci, yonetici_basligi):
    f = await _form(istemci, yonetici_basligi, alanlar={"butce": {"acik": True}})
    y = await istemci.get(f"/api/v1/crm/form/{f['genel_anahtar']}", params={"dil": "ar"})
    assert y.status_code == 200 and y.headers.get("cache-control") == "no-store"
    d = y.json()
    assert d["dil"] == "ar" and d["yon"] == "rtl" and d["baslik"] == "Bize yazın"
    assert [a["ad"] for a in d["alanlar"]] == ["ad", "email", "telefon", "mesaj", "butce"]
    assert d["alanlar"][0]["etiket"] == "اسمك" and d["metinler"]["gonder"] == "إرسال"
    assert d["kvkk"] == {"metin": KVKK, "baglanti": "https://mehmetkuru.dev/kvkk", "surum": 1}
    assert d["jeton"].startswith(f"{f['id']}.") and d["bal_kupu"] == "web_adresi"
    assert "izinli_alanlar" not in d and "genel_anahtar" not in d  # iç ayar sızmıyor
    en = (await istemci.get(f"/api/v1/crm/form/{f['genel_anahtar']}", params={"dil": "xx"})).json()
    assert en["dil"] == "tr"


async def test_form_gonderimi_aday_kvkk_kaydi_ve_bildirim(istemci, yonetici_basligi, db_oturumu):
    from models.crm import CrmFormGonderimleri
    from models.notifications import Notifications

    f = await _form(istemci, yonetici_basligi, varsayilan_asama="iletisim_kuruldu", varsayilan_etiketler=["site formu"],
                    alanlar={"firma": {"acik": True}}, tesekkur_metni="Sağ olun!",
                    yonlendirme_adresi="https://musteri-sitesi.com/tesekkur")
    email = _e("formgonderim")
    y, _ = await _gonder(istemci, f, {"email": email, "firma": "Müşteri A.Ş.", "telefon": "0555"},
                         origin="https://www.musteri-sitesi.com")
    assert y.status_code == 200, y.text
    assert y.json() == {"ok": True, "tesekkur": "Sağ olun!", "yonlendirme": "https://musteri-sitesi.com/tesekkur"}
    assert y.headers.get("access-control-allow-origin") == "https://www.musteri-sitesi.com"
    a = (await _adaylar(db_oturumu, email))[0]
    assert a.kaynak == "form" and a.asama == "iletisim_kuruldu" and a.firma == "Müşteri A.Ş." and a.kaynak_detay == "Site formu"
    assert json.loads(a.etiketler) == ["site formu"]
    g = (await db_oturumu.execute(select(CrmFormGonderimleri).where(CrmFormGonderimleri.aday_id == a.id))).scalars().all()
    assert len(g) == 1
    g = g[0]
    assert g.kvkk_surum == 1 and len(g.kvkk_metin_ozeti) == 64 and g.kvkk_onay_at is not None
    assert g.ip_ozeti and g.ip_ozeti != "127.0.0.1" and len(g.ip_ozeti) == 64  # ham IP saklanmıyor
    assert g.koken == "https://www.musteri-sitesi.com"
    bildirim = (await db_oturumu.execute(select(Notifications).where(
        Notifications.event_type == "crm_yeni_aday", Notifications.ref_id == a.id, Notifications.channel == "inapp"
    ))).scalars().all()
    assert len(bildirim) == 1 and "Yeni aday" in bildirim[0].title

    # Aynı kişi ikinci kez: aynı aday, yeni aktivite, KVKK sürümü güncel.
    await istemci.patch(f"{K}/formlar/{f['id']}", json={"kvkk_metni": KVKK + " v2"}, headers=yonetici_basligi)
    y, _ = await _gonder(istemci, f, {"email": email, "mesaj": "Ek bilgi"})
    assert y.status_code == 200
    assert len(await _adaylar(db_oturumu, email)) == 1
    assert [k.olay for k in await _aktiviteler(db_oturumu, a.id)] == ["aday_olustu", "talep_eklendi"]
    surumler = sorted(x.kvkk_surum for x in (await db_oturumu.execute(
        select(CrmFormGonderimleri).where(CrmFormGonderimleri.form_id == f["id"])
    )).scalars().all())
    assert surumler == [1, 2]
    d = (await istemci.get(f"{K}/adaylar/{a.id}", headers=yonetici_basligi)).json()
    assert {b["tablo"] for b in d["bagli_kayitlar"]} == {"crm_form_gonderimleri"}
    assert d["bagli_kayitlar"][0]["baslik"] == "Site formu" and d["bagli_kayitlar"][0]["kvkk_surum"] == 1
    formlar_ = (await istemci.get(f"{K}/formlar", headers=yonetici_basligi)).json()["formlar"]
    assert next(x for x in formlar_ if x["id"] == f["id"])["gonderim_sayisi"] == 2


async def test_form_kvkk_onayi_zorunlu(istemci, yonetici_basligi, db_oturumu):
    f = await _form(istemci, yonetici_basligi)
    email = _e("kvkk")
    for i, onay in enumerate((None, False, "true", 1)):
        y, _ = await _gonder(istemci, f, {"email": email, "kvkk_onay": onay}, **{"x-mk-istemci-ip": f"192.0.2.{100 + i}"})
        assert y.status_code == 400 and y.json()["detail"]["kod"] == "kvkk_gerekli", onay
    assert await _adaylar(db_oturumu, email) == []


async def test_form_bal_kupu_sessizce_yok_sayar(istemci, yonetici_basligi, db_oturumu):
    from models.crm import CrmFormGonderimleri

    f = await _form(istemci, yonetici_basligi)
    email = _e("bot")
    y, _ = await _gonder(istemci, f, {"email": email, "web_adresi": "http://spam.example"})
    assert y.status_code == 200 and y.json()["ok"] is True
    assert await _adaylar(db_oturumu, email) == []
    sayi = (await db_oturumu.execute(select(func.count()).select_from(CrmFormGonderimleri)
                                     .where(CrmFormGonderimleri.form_id == f["id"]))).scalar()
    assert sayi == 0


async def test_form_sure_kontrolu_ve_jeton(istemci, yonetici_basligi, db_oturumu):
    f = await _form(istemci, yonetici_basligi)
    tanim = (await istemci.get(f"/api/v1/crm/form/{f['genel_anahtar']}")).json()
    # Tanımı alır almaz göndermek (2 sn'den hızlı) → red.
    y, _ = await _gonder(istemci, f, jeton=tanim["jeton"])
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "cok_hizli"
    y, _ = await _gonder(istemci, f, jeton="")
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "jeton_gecersiz"
    sahte = _jeton(f["id"]).rsplit(".", 1)[0] + ".0123456789abcdef0123456789abcdef"
    y, _ = await _gonder(istemci, f, jeton=sahte)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "jeton_gecersiz"
    baska_form = _jeton(f["id"] + 100000)
    y, _ = await _gonder(istemci, f, jeton=baska_form)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "jeton_gecersiz"
    y, _ = await _gonder(istemci, f, jeton=_jeton(f["id"], once_sn=25 * 3600))
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "jeton_suresi_doldu"


async def test_form_hiz_siniri(istemci, yonetici_basligi):
    f = await _form(istemci, yonetici_basligi)
    kodlar = []
    for _ in range(6):
        y, _ = await _gonder(istemci, f)
        kodlar.append(y.status_code)
    assert kodlar[:5] == [200] * 5 and kodlar[5] == 429
    y, _ = await _gonder(istemci, f)
    assert y.json()["detail"]["kod"] == "cok_fazla_istek"
    # Başka IP etkilenmiyor (vekil başlığı).
    y, _ = await _gonder(istemci, f, **{"x-mk-istemci-ip": "198.51.100.7"})
    assert y.status_code == 200


async def test_form_alan_uzunluklari_ve_zorunluluk(istemci, yonetici_basligi):
    f = await _form(istemci, yonetici_basligi, alanlar={"firma": {"acik": True}, "butce": {"acik": True}})
    for govde, kod, alan in (
        ({"ad": "A" * 121}, "alan_uzun", "ad"),
        ({"mesaj": "m" * 4001}, "alan_uzun", "mesaj"),
        ({"firma": "F" * 161}, "alan_uzun", "firma"),
        ({"butce": "9" * 121}, "alan_uzun", "butce"),
        ({"telefon": "5" * 41}, "alan_uzun", "telefon"),
        ({"ad": "   "}, "alan_gerekli", "ad"),
        ({"email": "gecersiz-adres"}, "eposta_gecersiz", "email"),
        ({"email": "a" * 250 + "@b.com"}, "alan_uzun", "email"),
        ({"ad": {"x": 1}}, "alan_gecersiz", "ad"),
    ):
        y, _ = await _gonder(istemci, f, govde, **{"x-mk-istemci-ip": f"198.51.100.{len(kod) + len(alan)}"})
        assert y.status_code == 400, (govde, y.text)
        assert y.json()["detail"]["kod"] == kod and y.json()["detail"]["alan"] == alan, y.text
    # Kapalı alan (ör. kapalı form alanı) yok sayılır, sınırı da yok.
    f2 = await _form(istemci, yonetici_basligi, alanlar={"telefon": {"acik": False}})
    y, _ = await _gonder(istemci, f2, {"telefon": "5" * 500}, **{"x-mk-istemci-ip": "198.51.100.200"})
    assert y.status_code == 200
    # Gövde sınırı.
    y = await istemci.post(f"/api/v1/crm/form/{f['genel_anahtar']}", content=b"x" * 20001,
                           headers={"x-mk-istemci-ip": "198.51.100.201"})
    assert y.status_code == 413
    y = await istemci.post(f"/api/v1/crm/form/{f['genel_anahtar']}", content=b"[1,2]",
                           headers={"x-mk-istemci-ip": "198.51.100.202"})
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "govde_gecersiz"


async def test_form_koken_ve_cors(istemci, yonetici_basligi, db_oturumu):
    f = await _form(istemci, yonetici_basligi, izinli_alanlar=["musteri-sitesi.com"])
    yol = f"/api/v1/crm/form/{f['genel_anahtar']}"

    # İzinli: alan adı, alt alan adı, site kendisi (SITE_PUBLIC_URL / mehmetkuru.dev), kökensiz istek.
    for i, koken in enumerate(("https://musteri-sitesi.com", "https://blog.musteri-sitesi.com", "https://mehmetkuru.dev", None)):
        y, _ = await _gonder(istemci, f, origin=koken, **{"x-mk-istemci-ip": f"192.0.2.{i + 1}"})
        assert y.status_code == 200, (koken, y.text)
        if koken:
            assert y.headers.get("access-control-allow-origin") == koken
        y = await istemci.get(yol, headers={"origin": koken} if koken else {})
        assert y.status_code == 200

    # İzinsiz: kayıt yok, CORS başlığı yok (tarayıcı yanıtı göremez).
    for i, koken in enumerate(("https://kotu-site.com", "https://musteri-sitesi.com.kotu.net", "null", "https://evilmusteri-sitesi.com")):
        email = _e("koken")
        y, _ = await _gonder(istemci, f, {"email": email}, origin=koken, **{"x-mk-istemci-ip": f"192.0.2.{50 + i}"})
        assert y.status_code == 403 and y.json()["detail"]["kod"] == "alan_adi_izinsiz", koken
        assert "access-control-allow-origin" not in y.headers and "x-mk-cors" not in y.headers
        assert await _adaylar(db_oturumu, email) == []
        y = await istemci.get(yol, headers={"origin": koken})
        assert y.status_code == 403 and "access-control-allow-origin" not in y.headers

    # Ön kontrol (OPTIONS): yalnız izinli kökene.
    on = {"access-control-request-method": "POST", "access-control-request-headers": "content-type"}
    y = await istemci.options(yol, headers={"origin": "https://musteri-sitesi.com", **on})
    assert y.status_code == 204 and y.headers["access-control-allow-origin"] == "https://musteri-sitesi.com"
    assert "POST" in y.headers["access-control-allow-methods"]
    y = await istemci.options(yol, headers={"origin": "https://kotu-site.com", **on})
    assert y.status_code == 403 and "access-control-allow-origin" not in y.headers
    y = await istemci.options("/api/v1/crm/form/yok", headers={"origin": "https://musteri-sitesi.com", **on})
    assert y.status_code == 403

    # Diğer uçların genel CORS davranışı değişmedi.
    y = await istemci.options("/api/v1/kaynaklar", headers={"origin": "https://kotu-site.com", **on})
    assert y.headers.get("access-control-allow-origin") == "https://kotu-site.com"


async def test_pasif_ya_da_silinen_form_kapali(istemci, yonetici_basligi, db_oturumu):
    from models.cop_kutusu import CopKutusu

    f = await _form(istemci, yonetici_basligi)
    await istemci.patch(f"{K}/formlar/{f['id']}", json={"aktif": False}, headers=yonetici_basligi)
    assert (await istemci.get(f"/api/v1/crm/form/{f['genel_anahtar']}")).status_code == 404
    y, _ = await _gonder(istemci, f)
    assert y.status_code == 404
    y = await istemci.delete(f"{K}/formlar/{f['id']}", headers=yonetici_basligi)
    assert y.status_code == 200
    assert (await db_oturumu.execute(select(CopKutusu).where(CopKutusu.tablo == "crm_formlar",
                                                             CopKutusu.kayit_id == str(f["id"])))).scalars().first()


async def test_meta_ve_bildirim_olaylari(istemci, yonetici_basligi):
    from services.bildirim_tercih import OLAYLAR

    assert OLAYLAR["crm_yeni_aday"] == {"roller": ("admin",), "tetikleniyor": True}
    assert OLAYLAR["crm_hatirlatma"] == {"roller": ("admin",), "tetikleniyor": True}
    y = await istemci.get(f"{K}/meta", headers=yonetici_basligi)
    assert y.status_code == 200
    d = y.json()
    assert "yonetici@test.dev" in [s["email"] for s in d["sorumlular"]]
    assert d["aktivite_turleri"] == ["not", "arama", "eposta", "toplanti"] and "form" in d["kaynaklar"]
    assert d["puan_kurallari"]["en_cok"] == {"kaynak": 30, "butce": 15, "kapsam": 10, "alan_adi": 20, "etkilesim": 25}


def test_modul_kaydi_yonetici_yalniz():
    from core.moduller import MODUL_SOZLUGU

    m = MODUL_SOZLUGU["crm"]
    assert m.gerekli_rol == "admin" and m.musteri_sekmesi is None and m.yonetici_sekmesi == "crm" and m.varsayilan_acik


async def test_baska_rolden_jeton_musteri_admin_degil(istemci):
    """Rolü 'user' olan jeton CRM'e giremez; e-postası yönetici adresi olsa bile."""
    h = {"Authorization": f"Bearer {jeton_uret('yonetici@test.dev', 'user')}"}
    assert (await istemci.get(f"{K}/adaylar", headers=h)).status_code == 403
