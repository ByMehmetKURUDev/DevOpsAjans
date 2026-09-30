"""Kredi defteri (Kullandıkça Öde) testleri.

Veritabanı oturum boyunca paylaşılıyor; her test kendi benzersiz müşteri
e-postasıyla çalışıyor. Zaman `services.kredi._simdi` üzerinden kaydırılıyor.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, update


def _eposta(on: str = "kredi") -> str:
    return f"{on}-{uuid.uuid4().hex[:10]}@test.dev"


YONETIM = "/api/v1/kredi/yonetim"


async def _yukle(istemci, baslik, eposta, saat, tur="hediye", aciklama="deneme", beklenen=200):
    yanit = await istemci.post(
        f"{YONETIM}/yukle",
        json={"eposta": eposta, "saat": saat, "tur": tur, "aciklama": aciklama},
        headers=baslik,
    )
    assert yanit.status_code == beklenen, yanit.text
    return yanit.json()


async def _harca(istemci, baslik, eposta, saat, beklenen=200, **ek):
    govde = {"eposta": eposta, "saat": saat, "aciklama": "iş"}
    govde.update(ek)
    yanit = await istemci.post(f"{YONETIM}/harca", json=govde, headers=baslik)
    assert yanit.status_code == beklenen, yanit.text
    return yanit.json()


async def _kredilerim(istemci, musteri_basligi, eposta):
    yanit = await istemci.get("/api/v1/kredilerim", headers=musteri_basligi(eposta))
    assert yanit.status_code == 200, yanit.text
    return yanit.json()


@pytest.fixture
def saat_makinesi(monkeypatch):
    """`an(gun)` → zamanı başlangıçtan `gun` gün sonraya kaydırır."""
    from services import kredi

    baslangic = datetime.now(timezone.utc).replace(microsecond=0)
    durum = {"an": baslangic}
    monkeypatch.setattr(kredi, "_simdi", lambda: durum["an"])

    def an(gun: float = 0):
        durum["an"] = baslangic + timedelta(days=gun)
        return durum["an"]

    return an


# ---------------------------------------------------------------------------
# Yetki
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "metot,yol",
    [
        ("GET", f"{YONETIM}/musteriler"),
        ("GET", f"{YONETIM}/musteri/a@b.dev"),
        ("POST", f"{YONETIM}/harca"),
        ("POST", f"{YONETIM}/yukle"),
        ("POST", f"{YONETIM}/sure-dolumlari"),
    ],
)
async def test_yonetim_uclari_anonime_401_musteriye_403(istemci, musteri_basligi, metot, yol):
    govde = {"eposta": "a@b.dev", "saat": 1, "tur": "hediye", "aciklama": "x"}
    anonim = await istemci.request(metot, yol, json=govde if metot == "POST" else None)
    assert anonim.status_code == 401
    musteri = await istemci.request(metot, yol, json=govde if metot == "POST" else None, headers=musteri_basligi())
    assert musteri.status_code == 403


async def test_kredilerim_oturum_istiyor(istemci):
    assert (await istemci.get("/api/v1/kredilerim")).status_code == 401


async def test_musteri_yalniz_kendi_kredisini_gorur(istemci, yonetici_basligi, musteri_basligi):
    a, b = _eposta("a"), _eposta("b")
    await _yukle(istemci, yonetici_basligi, b, 7, aciklama="B'nin kredisi")
    await _yukle(istemci, yonetici_basligi, a, 1.5)

    veri = await _kredilerim(istemci, musteri_basligi, a)
    assert veri["bakiye"] == 1.5
    assert [h["miktar"] for h in veri["hareketler"]] == [1.5]
    assert all("B'nin" not in (h["aciklama"] or "") for h in veri["hareketler"])
    # Sorgu parametresiyle başkasının kredisi istenemez: e-posta jetondan.
    yanit = await istemci.get(f"/api/v1/kredilerim?eposta={b}", headers=musteri_basligi(a))
    assert yanit.json()["bakiye"] == 1.5
    # Müşteri satırında iç alanlar yok.
    assert "olusturan_eposta" not in veri["hareketler"][0]


# ---------------------------------------------------------------------------
# Doğrulama
# ---------------------------------------------------------------------------


async def test_girdi_dogrulama(istemci, yonetici_basligi):
    e = _eposta()
    await _yukle(istemci, yonetici_basligi, e, 0.3, beklenen=400)  # 0.25'in katı değil
    await _yukle(istemci, yonetici_basligi, e, 0, beklenen=400)
    await _yukle(istemci, yonetici_basligi, e, -1, tur="hediye", beklenen=400)
    await _yukle(istemci, yonetici_basligi, e, 1, tur="harcama", beklenen=400)
    await _yukle(istemci, yonetici_basligi, e, 1, tur="sure_dolumu", beklenen=400)
    await _yukle(istemci, yonetici_basligi, e, 1, aciklama="  ", beklenen=400)
    await _yukle(istemci, yonetici_basligi, "adres-degil", 1, beklenen=400)
    await _harca(istemci, yonetici_basligi, e, 0.1, beklenen=400)

    # Düzeltme eksi olabilir; e-posta küçük harfe iniyor.
    await _yukle(istemci, yonetici_basligi, e.upper(), 2.75)
    sonuc = await _yukle(istemci, yonetici_basligi, e, -0.75, tur="duzeltme")
    assert sonuc["bakiye"] == 2.0
    assert sonuc["hareket"]["son_kullanma"] is None


# ---------------------------------------------------------------------------
# Harcama, yetersiz bakiye, eksi izni
# ---------------------------------------------------------------------------


async def test_yetersiz_bakiye_409_ve_eksi_izni(istemci, yonetici_basligi, musteri_basligi):
    e = _eposta()
    await _yukle(istemci, yonetici_basligi, e, 3)
    yanit = await istemci.post(
        f"{YONETIM}/harca", json={"eposta": e, "saat": 3.25, "aciklama": "fazla"}, headers=yonetici_basligi
    )
    assert yanit.status_code == 409
    assert yanit.json()["detail"] == "yetersiz_bakiye"

    sonuc = await _harca(istemci, yonetici_basligi, e, 3.25, izin_eksi=True)
    assert sonuc["bakiye"] == -0.25
    assert sonuc["hareket"]["miktar"] == -3.25 and sonuc["hareket"]["tur"] == "harcama"

    # Borç bir sonraki yüklemeden önce düşülüyor.
    sonuc = await _yukle(istemci, yonetici_basligi, e, 1, tur="satin_alma")
    assert sonuc["bakiye"] == 0.75
    assert (await _kredilerim(istemci, musteri_basligi, e))["bakiye"] == 0.75


async def test_proje_bagli_harcama_ve_ayrinti(istemci, yonetici_basligi):
    e = _eposta()
    await _yukle(istemci, yonetici_basligi, e, 5)
    await _harca(istemci, yonetici_basligi, e, 1.25, proje_id=42)
    yanit = await istemci.get(f"{YONETIM}/musteri/{e}", headers=yonetici_basligi)
    assert yanit.status_code == 200
    veri = yanit.json()
    assert veri["bakiye"] == 3.75
    assert veri["hareketler"][0]["proje_id"] == 42
    assert veri["hareketler"][0]["olusturan_eposta"] == "yonetici@test.dev"
    assert len(veri["yaklasan_son_kullanma"]) == 1 and veri["yaklasan_son_kullanma"][0]["miktar"] == 3.75

    liste = (await istemci.get(f"{YONETIM}/musteriler", headers=yonetici_basligi)).json()
    satir = next(m for m in liste if m["eposta"] == e)
    assert satir["bakiye"] == 3.75 and satir["hareket_sayisi"] == 2
    assert satir["son_hareket_turu"] == "harcama"
    assert satir["en_yakin_miktar"] == 3.75


# ---------------------------------------------------------------------------
# FIFO + süre dolumu
# ---------------------------------------------------------------------------


async def test_fifo_ve_sure_dolumu(istemci, yonetici_basligi, musteri_basligi, saat_makinesi, db_oturumu):
    from models.credit_ledger import CreditLedger

    e = _eposta("fifo")
    saat_makinesi(0)
    a = await _yukle(istemci, yonetici_basligi, e, 10)  # A: 0. gün → 365. gün
    saat_makinesi(100)
    await _yukle(istemci, yonetici_basligi, e, 5)  # B: 100. gün → 465. gün
    saat_makinesi(200)
    sonuc = await _harca(istemci, yonetici_basligi, e, 4)  # en eski (A) önce: A=6, B=5
    assert sonuc["bakiye"] == 11

    veri = await _kredilerim(istemci, musteri_basligi, e)
    yaklasan = veri["yaklasan_son_kullanma"]
    assert [k["miktar"] for k in yaklasan] == [6, 5]

    # A'nın süresi doldu: kalan 6 saat düşülüyor, B'nin 5 saati duruyor.
    saat_makinesi(366)
    veri = await _kredilerim(istemci, musteri_basligi, e)
    assert veri["bakiye"] == 5
    dolumlar = [h for h in veri["hareketler"] if h["tur"] == "sure_dolumu"]
    assert len(dolumlar) == 1 and dolumlar[0]["miktar"] == -6
    assert [k["miktar"] for k in veri["yaklasan_son_kullanma"]] == [5]

    # İkinci okuma ve toplu işlem ikinci satır yazmıyor.
    await _kredilerim(istemci, musteri_basligi, e)
    toplu = await istemci.post(f"{YONETIM}/sure-dolumlari", headers=yonetici_basligi)
    assert toplu.status_code == 200
    db_oturumu.expire_all()
    satirlar = (
        await db_oturumu.execute(
            select(CreditLedger).where(CreditLedger.musteri_eposta == e, CreditLedger.tur == "sure_dolumu")
        )
    ).scalars().all()
    assert len(satirlar) == 1
    assert satirlar[0].kaynak_ref == f"sure_dolumu:{a['hareket']['id']}"
    # Defterin toplamı bakiyeye eşit (10 + 5 − 4 − 6).
    toplam = (
        await db_oturumu.execute(select(func.sum(CreditLedger.miktar)).where(CreditLedger.musteri_eposta == e))
    ).scalar()
    assert toplam == 5

    # Süresi dolmuş yükleme harcamaya kullanılamıyor.
    await _harca(istemci, yonetici_basligi, e, 5.25, beklenen=409)
    assert (await _harca(istemci, yonetici_basligi, e, 5))["bakiye"] == 0


async def test_toplu_sure_dolumu_isleme(istemci, yonetici_basligi, saat_makinesi):
    e = _eposta("toplu")
    saat_makinesi(0)
    await _yukle(istemci, yonetici_basligi, e, 2)
    saat_makinesi(400)
    # Okuma yapılmadan da bakiye doğru: süresi geçmiş yükleme sayılmıyor.
    liste = (await istemci.get(f"{YONETIM}/musteriler", headers=yonetici_basligi)).json()
    satir = next(m for m in liste if m["eposta"] == e)
    assert satir["bakiye"] == 0 and satir["dolum_bekleyen"] == 2

    yanit = await istemci.post(f"{YONETIM}/sure-dolumlari", headers=yonetici_basligi)
    assert yanit.status_code == 200 and yanit.json()["yazilan"] >= 1
    tekrar = await istemci.post(f"{YONETIM}/sure-dolumlari", headers=yonetici_basligi)
    liste = (await istemci.get(f"{YONETIM}/musteriler", headers=yonetici_basligi)).json()
    satir = next(m for m in liste if m["eposta"] == e)
    assert satir["dolum_bekleyen"] == 0 and satir["son_hareket_turu"] == "sure_dolumu"
    assert tekrar.json()["yazilan"] == 0


def test_durum_hesapla_birim():
    """Yeniden oynatma: süre dolumu yalnız hedef yüklemeyi etkiler."""
    from models.credit_ledger import CreditLedger
    from services.kredi import durum_hesapla

    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    gun = lambda n: t0 + timedelta(days=n)  # noqa: E731
    satirlar = [
        CreditLedger(id=1, created_at=gun(0), miktar=4, tur="hediye", son_kullanma=gun(365)),
        CreditLedger(id=2, created_at=gun(10), miktar=4, tur="hediye", son_kullanma=gun(375)),
        CreditLedger(id=3, created_at=gun(20), miktar=-5, tur="harcama"),  # 1: 0, 2: 3
    ]
    d = durum_hesapla(satirlar, gun(370))
    assert d.bakiye == 3 and d.dolmus == []
    d = durum_hesapla(satirlar, gun(380))
    assert d.bakiye == 0 and [y.satir.id for y in d.dolmus] == [2]
    satirlar.append(
        CreditLedger(id=5, created_at=gun(375), miktar=-3, tur="sure_dolumu", kaynak_ref="sure_dolumu:2")
    )
    d = durum_hesapla(satirlar, gun(380))
    assert d.bakiye == 0 and d.dolmus == [] and d.borc == 0


# ---------------------------------------------------------------------------
# Eşik bildirimi
# ---------------------------------------------------------------------------


async def _esik_bildirimleri(db_oturumu, eposta):
    from models.notifications import Notifications

    db_oturumu.expire_all()
    return (
        await db_oturumu.execute(
            select(Notifications).where(
                Notifications.event_type == "kredi_azaldi",
                Notifications.recipient_email == eposta,
                Notifications.channel == "inapp",
            )
        )
    ).scalars().all()


async def test_esik_bildirimi_gunde_bir(istemci, yonetici_basligi, db_oturumu):
    from models.notifications import Notifications

    e = _eposta("esik")
    await _yukle(istemci, yonetici_basligi, e, 5)
    await _harca(istemci, yonetici_basligi, e, 1)  # 4 > 2: bildirim yok
    assert await _esik_bildirimleri(db_oturumu, e) == []

    await _harca(istemci, yonetici_basligi, e, 2)  # 2 ≤ 2: bildirim
    ilk = await _esik_bildirimleri(db_oturumu, e)
    assert len(ilk) == 1 and ilk[0].recipient_role == "client"
    assert "2" in ilk[0].body and ilk[0].link == "/client?sekme=krediler"
    yonetici = (
        await db_oturumu.execute(
            select(Notifications).where(
                Notifications.event_type == "kredi_azaldi",
                Notifications.recipient_email == "yonetici@test.dev",
                Notifications.body.contains(e),
            )
        )
    ).scalars().all()
    assert yonetici, "yöneticiye de bildirim gitmeli"

    await _harca(istemci, yonetici_basligi, e, 0.5)  # aynı gün: yeni bildirim yok
    assert len(await _esik_bildirimleri(db_oturumu, e)) == 1

    # Bir gün geçmiş gibi: önceki bildirim 25 saat öncesine çekiliyor.
    await db_oturumu.execute(
        update(Notifications)
        .where(Notifications.event_type == "kredi_azaldi", Notifications.recipient_email == e)
        .values(created_at=datetime.now() - timedelta(hours=25))
    )
    await db_oturumu.commit()
    await _harca(istemci, yonetici_basligi, e, 0.25)
    assert len(await _esik_bildirimleri(db_oturumu, e)) == 2


async def test_esik_ayari_site_settings(istemci, yonetici_basligi, db_oturumu):
    from models.site_settings import Site_settings

    ayar = Site_settings(setting_key="kredi_esik_saat", setting_value="10", group_name="kredi")
    db_oturumu.add(ayar)
    await db_oturumu.commit()
    try:
        e = _eposta("esik10")
        await _yukle(istemci, yonetici_basligi, e, 20)
        await _harca(istemci, yonetici_basligi, e, 10)  # 10 ≤ 10
        assert len(await _esik_bildirimleri(db_oturumu, e)) == 1
    finally:
        await db_oturumu.delete(ayar)
        await db_oturumu.commit()


# ---------------------------------------------------------------------------
# Ödeme kancası
# ---------------------------------------------------------------------------


async def _kredi_satin_al(istemci, eposta, paket=25):
    yanit = await istemci.post(
        "/api/v1/fiyat-satin-al", json={"kredi_paketi": paket, "musteri_eposta": eposta, "musteri_adi": "Test"}
    )
    assert yanit.status_code == 200, yanit.text
    return yanit.json()


async def _odeme(db_oturumu, invoice_id):
    from models.payments import Payments

    db_oturumu.expire_all()
    return (
        await db_oturumu.execute(select(Payments).where(Payments.invoice_id == invoice_id, Payments.durum == "bekliyor"))
    ).scalars().first()


async def _defter(db_oturumu, eposta):
    from models.credit_ledger import CreditLedger

    db_oturumu.expire_all()
    return (
        await db_oturumu.execute(
            select(CreditLedger).where(CreditLedger.musteri_eposta == eposta).order_by(CreditLedger.id)
        )
    ).scalars().all()


async def _yuklendi_bildirimleri(db_oturumu, eposta):
    from models.notifications import Notifications

    return (
        await db_oturumu.execute(
            select(Notifications).where(
                Notifications.event_type == "kredi_yuklendi",
                Notifications.recipient_email == eposta,
                Notifications.channel == "inapp",
            )
        )
    ).scalars().all()


async def test_lemon_odemesi_kredi_yukler_bir_kez(istemci, db_oturumu, musteri_basligi):
    from routers.odemeler import _lemon_odemesini_isle

    e = _eposta("lemon")
    satin = await _kredi_satin_al(istemci, e.upper(), 25)
    odeme = await _odeme(db_oturumu, satin["invoice_id"])
    siparis = {"id": "L-1", "attributes": {"status": "paid"}}

    kimlik, yeni = await _lemon_odemesini_isle(db_oturumu, odeme.jeton, siparis)
    assert kimlik and yeni
    kimlik2, yeni2 = await _lemon_odemesini_isle(db_oturumu, odeme.jeton, siparis)
    assert kimlik2 == kimlik and not yeni2

    satirlar = await _defter(db_oturumu, e)
    assert [(s.tur, s.miktar) for s in satirlar] == [("satin_alma", 25), ("bonus", 2)]
    assert all(s.fatura_id == satin["invoice_id"] and s.son_kullanma is not None for s in satirlar)
    assert satirlar[0].kaynak_ref == f"fatura:{satin['invoice_id']}:kredi"
    assert (await _kredilerim(istemci, musteri_basligi, e))["bakiye"] == 27
    bildirimler = await _yuklendi_bildirimleri(db_oturumu, e)
    assert len(bildirimler) == 1 and "27" in bildirimler[0].body


async def test_shopier_odemesi_kredi_yukler_bir_kez(istemci, db_oturumu, monkeypatch):
    from core import shopier
    from routers.odemeler import _odemeyi_isle

    async def _kapat(_urun_id):
        return True

    monkeypatch.setattr(shopier, "odeme_urununu_kapat", _kapat)

    e = _eposta("shopier")
    satin = await _kredi_satin_al(istemci, e, 10)
    odeme = await _odeme(db_oturumu, satin["invoice_id"])
    urun = f"urun-{uuid.uuid4().hex[:8]}"
    odeme.shopier_urun_id = urun
    await db_oturumu.commit()

    siparis = {"id": "S-1", "paymentStatus": "paid", "lineItems": [{"productId": urun}]}
    assert (await _odemeyi_isle(db_oturumu, siparis))[1] is True
    assert (await _odemeyi_isle(db_oturumu, siparis))[1] is False

    satirlar = await _defter(db_oturumu, e)
    # 10'luk pakette bonus yok: tek satır.
    assert [(s.tur, s.miktar) for s in satirlar] == [("satin_alma", 10)]
    assert len(await _yuklendi_bildirimleri(db_oturumu, e)) == 1


async def test_elle_tahsilat_kredi_yukler_bir_kez(istemci, yonetici_basligi, db_oturumu):
    e = _eposta("elle")
    satin = await _kredi_satin_al(istemci, e, 100)

    # Kısmi tahsilat faturayı kapatmıyor: kredi henüz yok.
    yanit = await istemci.post(
        "/api/v1/odeme/elle", json={"invoice_id": satin["invoice_id"], "tutar": 100, "kanal": "havale"},
        headers=yonetici_basligi,
    )
    assert yanit.status_code == 200, yanit.text
    assert await _defter(db_oturumu, e) == []

    for _ in range(2):  # iki kez tam tahsilat girilse de kredi bir kez
        yanit = await istemci.post(
            "/api/v1/odeme/elle", json={"invoice_id": satin["invoice_id"], "kanal": "eft"}, headers=yonetici_basligi
        )
        assert yanit.status_code == 200, yanit.text

    satirlar = await _defter(db_oturumu, e)
    assert [(s.tur, s.miktar) for s in satirlar] == [("satin_alma", 100), ("bonus", 15)]
    assert len(await _yuklendi_bildirimleri(db_oturumu, e)) == 1


async def test_kredi_olmayan_fatura_deftere_yazmaz(istemci, yonetici_basligi, db_oturumu):
    from models.credit_ledger import CreditLedger

    once = (await db_oturumu.execute(select(func.count(CreditLedger.id)))).scalar()
    fatura = await istemci.post(
        "/api/v1/entities/invoices",
        json={"invoice_no": f"INV-{uuid.uuid4().hex[:6]}", "amount": 50.0, "client_email": _eposta(), "status": "unpaid"},
        headers=yonetici_basligi,
    )
    assert fatura.status_code in (200, 201), fatura.text
    yanit = await istemci.post(
        "/api/v1/odeme/elle", json={"invoice_id": fatura.json()["id"], "kanal": "havale"}, headers=yonetici_basligi
    )
    assert yanit.status_code == 200
    db_oturumu.expire_all()
    assert (await db_oturumu.execute(select(func.count(CreditLedger.id)))).scalar() == once


# ---------------------------------------------------------------------------
# Denetim kaydı (1B) — otomatik
# ---------------------------------------------------------------------------


async def test_denetim_kaydina_dusuyor(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    from models.audit_log import AuditLog

    e = _eposta("denetim")
    sonuc = await _yukle(istemci, yonetici_basligi, e, 3, aciklama="hoş geldin hediyesi")
    await _harca(istemci, yonetici_basligi, e, 1)

    db_oturumu.expire_all()
    satirlar = (
        await db_oturumu.execute(
            select(AuditLog).where(AuditLog.tablo == "credit_ledger", AuditLog.ilgili_eposta == e).order_by(AuditLog.id)
        )
    ).scalars().all()
    assert [s.islem for s in satirlar] == ["olustur", "olustur"]
    assert satirlar[0].kayit_id == str(sonuc["hareket"]["id"])
    assert all(s.aktor_eposta == "yonetici@test.dev" and s.aktor_rol == "admin" for s in satirlar)
    assert "hoş geldin" in satirlar[0].degisiklik_json

    # Müşterinin "Hesap hareketleri"nde de görünüyor.
    benim = await istemci.get("/api/v1/denetim/benim", headers=musteri_basligi(e))
    assert benim.status_code == 200
    assert sum(1 for s in benim.json() if s["tablo"] == "credit_ledger") == 2
