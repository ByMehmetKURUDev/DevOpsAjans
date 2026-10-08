"""Faz 11A — Yönetici "Genel bakış" özeti (`GET /api/v1/yonetim-ozeti`).

* Yetki: oturumsuz 401, müşteri 403, yönetici 200 (yanıt şekli).
* Hesaplar `services/yonetim_ozeti.yonetim_ozeti(db, eposta, an)` ile AYRI, boş bir SQLite
  veritabanında sınanıyor: testler aynı oturum veritabanını paylaştığı için sayılar başka testlerin
  kayıtlarıyla karışmasın. `an` sabit (2030-01-15 Salı 12:00 UTC = 15:00 TR) — fikstür kayıtlarının
  denetim kancasının yazdığı (gerçek saatli) satırlar pencerenin dışında kalıyor; 2030 için tatil
  listesi boş, mesai hafta içi 09:00–18:00 (services/sla.py varsayılanı).
"""

import json
import logging
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from tests.backend.conftest import jeton_uret

AN = datetime(2030, 1, 15, 12, 0, tzinfo=timezone.utc)  # Salı, TR 15:00
YONETICI = "yonetici@test.dev"


def u(yil, ay, gun, saat=0, dakika=0):
    return datetime(yil, ay, gun, saat, dakika, tzinfo=timezone.utc)


@pytest.fixture
async def ayri_db(uygulama, tmp_path):
    """Boş, yalnız bu teste ait veritabanı (bütün modellerin tabloları)."""
    import models.audit_log  # noqa: F401
    import models.crm  # noqa: F401
    import models.destek_sla  # noqa: F401
    import models.invoices  # noqa: F401
    import models.notifications  # noqa: F401
    import models.payments  # noqa: F401
    import models.pricing  # noqa: F401
    import models.proje_gorevleri  # noqa: F401
    import models.projects  # noqa: F401
    import models.saha_servisi  # noqa: F401
    import models.signed_actions  # noqa: F401
    import models.sozlesmeler  # noqa: F401
    import models.staff  # noqa: F401
    import models.support_tickets  # noqa: F401
    import models.teklifler  # noqa: F401
    import models.ticket_replies  # noqa: F401
    from core.database import Base
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    motor = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/ozet.db")
    async with motor.begin() as baglanti:
        await baglanti.run_sync(Base.metadata.create_all)
    yapici = async_sessionmaker(motor, class_=AsyncSession, expire_on_commit=False)
    async with yapici() as oturum:
        yield oturum
    await motor.dispose()


async def _ekle(db, *nesneler):
    for n in nesneler:
        db.add(n)
    await db.commit()
    return nesneler[0] if len(nesneler) == 1 else nesneler


async def _ozet(db):
    from services.yonetim_ozeti import yonetim_ozeti

    return await yonetim_ozeti(db, YONETICI, an=AN)


# ---------------------------------------------------------------------------
# Yetki ve yanıt şekli (oturum veritabanı)
# ---------------------------------------------------------------------------
async def test_oturumsuz_401(istemci):
    y = await istemci.get("/api/v1/yonetim-ozeti")
    assert y.status_code == 401


async def test_musteri_403(istemci, musteri_basligi):
    y = await istemci.get("/api/v1/yonetim-ozeti", headers=musteri_basligi("ozet-musteri@test.dev"))
    assert y.status_code == 403


async def test_yonetici_200_ve_sekil(istemci, yonetici_basligi):
    y = await istemci.get("/api/v1/yonetim-ozeti", headers=yonetici_basligi)
    assert y.status_code == 200
    assert y.headers.get("cache-control") == "no-store"
    g = y.json()
    assert set(g) == {"olusturma", "acil", "kpi", "hizmetHatti", "aktivite", "kategori", "saha", "sonIsler", "bildirimler"}
    assert set(g["kpi"]) == {"tahsilat", "acik_isler", "tamamlanan", "sla"}
    # Hesaplanabilen kalemler hata vermeden doluyor (oturum veritabanında başka testlerin kayıtları var).
    for kalem in ("hizmetHatti", "aktivite", "kategori"):
        assert g[kalem] is not None, kalem
    assert isinstance(g["sonIsler"], list) and isinstance(g["bildirimler"], list)
    assert len(g["aktivite"]["bugun"]) == 24 and len(g["aktivite"]["dun"]) == 24


async def test_baska_yoneticinin_bildirimi_gorunmez(istemci, db_oturumu):
    from models.notifications import Notifications

    db_oturumu.add(Notifications(recipient_email="baska-yonetici@test.dev", event_type="x", title="Başkasının", channel="inapp"))
    db_oturumu.add(Notifications(recipient_email="OzetYonetici@Test.dev", event_type="x", title="Benim bildirimim", channel="inapp"))
    db_oturumu.add(Notifications(recipient_email="ozetyonetici@test.dev", event_type="x", title="E-posta kaydı", channel="email"))
    await db_oturumu.commit()
    b = {"Authorization": f"Bearer {jeton_uret('ozetyonetici@test.dev', 'admin')}"}
    g = (await istemci.get("/api/v1/yonetim-ozeti", headers=b)).json()
    assert [x["baslik"] for x in g["bildirimler"]] == ["Benim bildirimim"]


# ---------------------------------------------------------------------------
# Boş veritabanı
# ---------------------------------------------------------------------------
async def test_bos_veritabaninda_null_ve_sifir(ayri_db, caplog):
    caplog.set_level(logging.ERROR, logger="services.yonetim_ozeti")
    g = await _ozet(ayri_db)
    assert not [r for r in caplog.records if "hesaplanamadı" in r.getMessage()]
    assert g["acil"] is None
    k = g["kpi"]
    assert k["tahsilat"]["tutar"] == 0 and k["tahsilat"]["degisim_yuzde"] is None and k["tahsilat"]["seri"] == [0] * 14
    assert k["acik_isler"]["toplam"] == 0 and k["acik_isler"]["degisim_yuzde"] is None and k["acik_isler"]["seri"] == [0] * 14
    assert k["tamamlanan"]["toplam"] == 0 and k["tamamlanan"]["degisim_yuzde"] is None
    assert k["sla"] is None
    h = g["hizmetHatti"]
    assert [h[d]["sayi"] for d in ("yeni_talep", "teklif", "sozlesme", "proje", "teslim", "fatura")] == [0] * 6
    assert h["proje"]["ort_ilerleme"] is None and h["teklif"]["toplamlar"] == [] and h["fatura"]["kalanlar"] == []
    assert h["donusum"] == {"talep_teklif": None, "teklif_kabul": None, "tahsilat_gun": None}
    assert g["aktivite"]["toplam_bugun"] == 0 and g["aktivite"]["dun"] == [0] * 24
    # Bugünün gelmemiş saatleri boş (TR 15:00 → 16..23 None).
    assert g["aktivite"]["bugun"][15] == 0 and g["aktivite"]["bugun"][16:] == [None] * 8
    assert g["kategori"] == {"dagilim": [], "toplam": 0, "bu_ay_yeni": 0, "ort_sure_gun": None, "en_hizli": None}
    assert g["saha"] is None
    assert g["sonIsler"] == [] and g["bildirimler"] == []


# ---------------------------------------------------------------------------
# Acil (SLA)
# ---------------------------------------------------------------------------
async def test_acil_en_yakin_hedef_asilan_once_siradaki_risk(ayri_db):
    from models.support_tickets import Support_tickets

    db = ayri_db
    # Aşılmış: Pazartesi 09:00 TR açılan yüksek öncelik (ilk yanıt 120 mesai dk → Pzt 11:00 TR).
    asilmis = Support_tickets(client_name="Örnek Kafe", client_email="kafe@ornek.dev", subject="Ödeme sayfası açılmıyor",
                              message="m", status="open", priority="yuksek", created_at=u(2030, 1, 14, 6))
    # Yaklaşan: 14:30 TR açılan acil (ilk yanıt 60 dk → 15:30 TR; kalan 30 dk ≤ eşik 30).
    yaklasan = Support_tickets(client_email="b@ornek.dev", subject="Site yavaş", message="m", status="open",
                               priority="acil", created_at=AN - timedelta(minutes=30))
    # Zamanında: 1 saat önce açılan normal (ilk yanıt 240 dk).
    normal = Support_tickets(client_email="c@ornek.dev", subject="Soru", message="m", status="open", priority="normal",
                             created_at=AN - timedelta(hours=1))
    # Kapalı talep sayılmaz.
    kapali = Support_tickets(client_email="d@ornek.dev", subject="Eski", message="m", status="closed", priority="acil",
                             created_at=u(2030, 1, 13, 6))
    await _ekle(db, asilmis, yaklasan, normal, kapali)
    g = await _ozet(db)
    a = g["acil"]
    assert a["talep_id"] == asilmis.id and a["kod"] == f"D-{asilmis.id}"
    assert a["durum"] == "asildi" and a["hedef_turu"] == "ilk_yanit" and a["kalan_sn"] < 0
    assert a["musteri"] == "Örnek Kafe" and a["baslik"] == "Ödeme sayfası açılmıyor" and a["oncelik"] == "yuksek"
    assert a["hedef"].startswith("2030-01-14T08:00")  # 11:00 TR
    assert a["siradaki"] == 1  # yalnız "yaklaşan" risk; normal zamanında


async def test_acil_yaklasan_kalan_sure_ve_ilk_yanittan_sonra_cozum_hedefi(ayri_db):
    from models.support_tickets import Support_tickets
    from models.ticket_replies import Ticket_replies

    db = ayri_db
    t = await _ekle(db, Support_tickets(client_email="b@ornek.dev", subject="Site yavaş", message="m", status="open",
                                        priority="acil", created_at=AN - timedelta(minutes=30)))
    g = await _ozet(db)
    assert g["acil"]["talep_id"] == t.id and g["acil"]["durum"] == "yaklasiyor"
    assert g["acil"]["kalan_sn"] == 30 * 60 and g["acil"]["siradaki"] == 0
    # Ajans yanıt verince bekleyen hedef çözüm (acil: 240 mesai dk → 18:00 TR'de 2,5 sa kalır + ertesi gün).
    await _ekle(db, Ticket_replies(ticket_id=t.id, yazan="ajans", mesaj="Bakıyoruz", created_at=AN - timedelta(minutes=10)))
    g = await _ozet(db)
    assert g["acil"]["hedef_turu"] == "cozum" and g["acil"]["durum"] == "zamaninda"


# ---------------------------------------------------------------------------
# KPI
# ---------------------------------------------------------------------------
async def test_tahsilat_bu_ay_degisim_ve_seri(ayri_db):
    from models.payments import Payments

    db = ayri_db
    await _ekle(
        db,
        Payments(durum="odendi", tutar=1000, para_birimi="TRY", odeme_tarihi="2030-01-02", created_at=u(2030, 1, 2)),
        # Tarihsiz elle ödeme yok → odendi_at (TR günü 14 Ocak).
        Payments(durum="odendi", tutar=500, para_birimi="TRY", odendi_at=u(2030, 1, 14, 10), created_at=u(2030, 1, 14, 10)),
        Payments(durum="iade", tutar=200, para_birimi="TRY", odeme_tarihi="2030-01-10", created_at=u(2030, 1, 10)),
        Payments(durum="odendi", tutar=999, para_birimi="USD", odeme_tarihi="2030-01-05", created_at=u(2030, 1, 5)),
        Payments(durum="bekliyor", tutar=777, para_birimi="TRY", created_at=u(2030, 1, 6)),
        # Geçen ay: aynı dönem (1–15 Aralık) 300, dönem dışı 400.
        Payments(durum="odendi", tutar=300, para_birimi="TL", odeme_tarihi="2029-12-05", created_at=u(2029, 12, 5)),
        Payments(durum="odendi", tutar=400, para_birimi="TRY", odeme_tarihi="2029-12-20", created_at=u(2029, 12, 20)),
    )
    t = (await _ozet(db))["kpi"]["tahsilat"]
    assert t["tutar"] == 1300 and t["onceki"] == 300 and t["degisim_yuzde"] == 333.3
    assert t["gunler"][0] == "2030-01-02" and t["gunler"][-1] == "2030-01-15"
    assert t["seri"][0] == 1000 and t["seri"][8] == -200 and t["seri"][12] == 500 and sum(t["seri"]) == 1300


async def test_acik_isler_tamamlanan_ve_sla_uyumu(ayri_db):
    from models.destek_sla import TalepSla
    from models.proje_gorevleri import ProjectTasks
    from models.saha_servisi import SahaIsEmirleri
    from models.support_tickets import Support_tickets

    db = ayri_db
    await _ekle(
        db,
        ProjectTasks(proje_id=1, baslik="açık 1", durum="yapilacak", created_at=u(2029, 12, 1)),
        ProjectTasks(proje_id=1, baslik="açık 2", durum="suruyor", created_at=u(2030, 1, 10)),
        ProjectTasks(proje_id=1, baslik="bitti bu ay", durum="tamam", created_at=u(2029, 12, 1), tamamlandi_at=u(2030, 1, 12, 9)),
        ProjectTasks(proje_id=1, baslik="bitti geçen ay", durum="tamam", created_at=u(2029, 11, 1), tamamlandi_at=u(2029, 12, 3, 9)),
        Support_tickets(client_email="a@x.dev", subject="açık", message="m", status="open", created_at=u(2030, 1, 14, 7)),
        Support_tickets(client_email="a@x.dev", subject="kapalı", message="m", status="closed",
                        created_at=u(2030, 1, 3, 7), updated_at=u(2030, 1, 5, 7)),
        SahaIsEmirleri(hesap_email="firma@x.dev", no="İE-1", uid=uuid.uuid4().hex, baslik="Klima", musteri_id=1,
                       durum="yolda", created_at=u(2030, 1, 15, 6)),
        SahaIsEmirleri(hesap_email="firma@x.dev", no="İE-2", uid=uuid.uuid4().hex, baslik="Bakım", musteri_id=1,
                       durum="tamamlandi", created_at=u(2030, 1, 8), bitir_at=u(2030, 1, 9, 9)),
        SahaIsEmirleri(hesap_email="firma@x.dev", no="İE-3", uid=uuid.uuid4().hex, baslik="İptal", musteri_id=1,
                       durum="iptal", created_at=u(2030, 1, 8), iptal_at=u(2030, 1, 9, 9)),
        # SLA: son 30 günde 3 ilk yanıt — 2 zamanında, 1 geç; ortalama 60 mesai dk.
        TalepSla(ticket_id=901, oncelik="normal", baslangic=u(2030, 1, 7, 7), ilk_yanit_hedef=u(2030, 1, 7, 11),
                 ilk_yanit_at=u(2030, 1, 7, 7, 30)),
        TalepSla(ticket_id=902, oncelik="normal", baslangic=u(2030, 1, 8, 7), ilk_yanit_hedef=u(2030, 1, 8, 11),
                 ilk_yanit_at=u(2030, 1, 8, 8)),
        TalepSla(ticket_id=903, oncelik="acil", baslangic=u(2030, 1, 9, 7), ilk_yanit_hedef=u(2030, 1, 9, 7, 30),
                 ilk_yanit_at=u(2030, 1, 9, 8, 30)),
        # Önceki 30 gün: 1 karar, zamanında → %100 (fark −33,3 puan).
        TalepSla(ticket_id=904, oncelik="normal", baslangic=u(2029, 12, 10, 7), ilk_yanit_hedef=u(2029, 12, 10, 11),
                 ilk_yanit_at=u(2029, 12, 10, 8)),
    )
    k = (await _ozet(db))["kpi"]
    a = k["acik_isler"]
    assert (a["gorev"], a["destek"], a["is_emri"], a["toplam"]) == (2, 1, 1, 4)
    # 30 gün önce (16 Aralık): açık 1 + "bitti bu ay" (o gün açıktı) = 2 görev.
    assert a["onceki"] == 2 and a["degisim_yuzde"] == 100.0
    assert a["seri"][-1] == 4 and len(a["seri"]) == 14
    tm = k["tamamlanan"]
    assert (tm["gorev"], tm["destek"], tm["is_emri"], tm["toplam"]) == (1, 1, 1, 3)
    assert tm["onceki"] == 1 and tm["degisim_yuzde"] == 200.0
    s = k["sla"]
    assert s["karar_sayisi"] == 3 and s["uyum_yuzde"] == 66.7 and s["ilk_yanit_ort_dk"] == 60.0
    assert s["onceki_uyum_yuzde"] == 100.0 and s["degisim_puan"] == -33.3


# ---------------------------------------------------------------------------
# Hizmet hattı
# ---------------------------------------------------------------------------
async def test_hizmet_hatti_sayilari_ve_donusum(ayri_db):
    from models.crm import CrmFormGonderimleri
    from models.inquiries import Inquiries
    from models.invoices import Invoices
    from models.payments import Payments
    from models.pricing import Pricing_inquiries
    from models.projects import Projects
    from models.signed_actions import SignedActions
    from models.sozlesmeler import Sozlesmeler
    from models.teklifler import Teklifler

    db = ayri_db
    pr = lambda **k: Projects(title="P", description="d", category="Website", **k)  # noqa: E731
    sa = lambda **k: SignedActions(jeton_ozeti=uuid.uuid4().hex, hedef_tablo="projects", hedef_id=1,  # noqa: E731
                                   alici_eposta="m@x.dev", baslik="Teslim", **k)
    _, b, c = await _ekle(
        db,
        Invoices(invoice_no="F-1", amount=1000, currency="TRY", status="unpaid", issue_date="2030-01-01"),
        Invoices(invoice_no="F-2", amount=500, currency="TRY", status="kismi_odendi", issue_date="2030-01-01"),
        Invoices(invoice_no="F-3", amount=800, currency="TRY", status="paid", issue_date="2030-01-01"),
    )
    await _ekle(
        db,
        # Son 24 saat: 2 iletişim + 1 teklif isteği + 1 CRM formu; 30 saat önceki sayılmaz.
        Inquiries(name="A", email="a@talep.dev", message="m", created_at=AN - timedelta(hours=1)),
        Inquiries(name="B", email="b@talep.dev", message="m", created_at=AN - timedelta(hours=23)),
        Inquiries(name="C", email="c@talep.dev", message="m", created_at=AN - timedelta(hours=30)),
        Pricing_inquiries(hesaplanan_tutar=100, musteri_eposta="d@talep.dev", created_at=AN - timedelta(hours=2)),
        CrmFormGonderimleri(form_id=1, kvkk_surum=1, kvkk_metin_ozeti="x", kvkk_onay_at=AN, created_at=AN - timedelta(hours=3)),
        # Teklifler: 2 bekleyen (3000 TRY), 1 taslak, kararlar: 1 kabul + 1 ret.
        Teklifler(no="TKL-1", baslik="Site", genel_toplam=1000, durum="gonderildi", aday_eposta="a@talep.dev",
                  gonderildi_at=AN - timedelta(minutes=30), created_at=AN - timedelta(minutes=40)),
        Teklifler(no="TKL-2", baslik="SEO", genel_toplam=2000, durum="goruntulendi", hesap_email="x@x.dev",
                  gonderildi_at=u(2030, 1, 10), created_at=u(2030, 1, 10)),
        Teklifler(no="TKL-3", baslik="Taslak", genel_toplam=5000, durum="taslak", created_at=u(2030, 1, 11)),
        Teklifler(no="TKL-4", baslik="K", genel_toplam=10, durum="kabul", karar_at=u(2030, 1, 5), created_at=u(2030, 1, 1)),
        Teklifler(no="TKL-5", baslik="R", genel_toplam=10, durum="ret", karar_at=u(2030, 1, 6), created_at=u(2030, 1, 1)),
        Sozlesmeler(no="S-1", baslik="S", govde="g", durum="gonderildi"),
        Sozlesmeler(no="S-2", baslik="S", govde="g", durum="imzalandi"),
        pr(client_email="m1@x.dev", status="in_progress", progress=40),
        pr(client_email="m2@x.dev", status="planning", progress=60),
        pr(client_email="m3@x.dev", status="completed", progress=100),
        pr(client_email="", status="in_progress", progress=10),  # vaka çalışması — müşteri projesi değil
        sa(tur="teslimat_onay", durum="bekliyor", son_kullanma=AN + timedelta(days=3)),
        sa(tur="teslimat_onay", durum="bekliyor", son_kullanma=AN - timedelta(days=1)),  # süresi dolmuş
        sa(tur="teslimat_onay", durum="kullanildi", son_kullanma=AN + timedelta(days=3)),
        sa(tur="teklif_kabul", durum="bekliyor", son_kullanma=AN + timedelta(days=3)),
        Payments(invoice_id=b.id, durum="odendi", tutar=200, para_birimi="TRY", odeme_tarihi="2030-01-03"),
        Payments(invoice_id=c.id, durum="odendi", tutar=800, para_birimi="TRY", odeme_tarihi="2030-01-11"),
    )
    h = (await _ozet(db))["hizmetHatti"]
    assert h["yeni_talep"] == {"sayi": 4, "bolum": "gelenKutusu"}
    assert h["teklif"]["sayi"] == 2 and h["teklif"]["toplamlar"] == [{"para_birimi": "TRY", "tutar": 3000.0}]
    assert h["sozlesme"]["sayi"] == 1 and h["sozlesme"]["bolum"] == "sozlesmeler"
    assert h["proje"]["sayi"] == 2 and h["proje"]["ort_ilerleme"] == 50.0
    assert h["teslim"]["sayi"] == 1
    assert h["fatura"]["sayi"] == 2 and h["fatura"]["kalanlar"] == [{"para_birimi": "TRY", "tutar": 1300.0}]
    d = h["donusum"]
    # 4 talep gönderen kişi (a, b, c, d — formun adayı yok); yalnız a'ya sonrasında teklif gitti → %25.
    assert d["talep_teklif"] == 25.0
    assert d["teklif_kabul"] == 50.0
    # Tamamen ödenen F-3: 1 Ocak → 11 Ocak = 10 gün.
    assert d["tahsilat_gun"] == 10.0


# ---------------------------------------------------------------------------
# Aktivite, kategori
# ---------------------------------------------------------------------------
async def test_aktivite_saat_kovalari_tr_saatiyle(ayri_db):
    from models.audit_log import AuditLog

    db = ayri_db
    satir = lambda z: AuditLog(created_at=z, islem="olustur", tablo="invoices")  # noqa: E731
    await _ekle(
        db,
        *[satir(u(2030, 1, 15, 11, 10 + i)) for i in range(3)],  # bugün 14:1x TR
        satir(u(2030, 1, 15, 5)),  # bugün 08:00 TR
        satir(u(2030, 1, 15, 13)),  # gelecek (16:00 TR) — sayılmaz
        satir(u(2030, 1, 14, 20, 30)),  # dün 23:30 TR
        satir(u(2030, 1, 13, 21, 0)),  # dün 00:00 TR
        satir(u(2030, 1, 13, 20, 59)),  # evvelsi gün 23:59 TR — sayılmaz
    )
    a = (await _ozet(db))["aktivite"]
    assert a["bugun"][14] == 3 and a["bugun"][8] == 1 and a["toplam_bugun"] == 4
    assert a["bugun"][15] == 0 and a["bugun"][16] is None
    assert a["dun"][23] == 1 and a["dun"][0] == 1 and a["toplam_dun"] == 2
    assert a["kaynak"] == "audit_log"


async def test_kategori_dagilim_bu_ay_yeni_ort_sure_en_hizli(ayri_db):
    from models.audit_log import AuditLog
    from models.projects import Projects

    db = ayri_db
    pr = lambda kat, durum, z, e="m@x.dev": Projects(  # noqa: E731
        title="P", description="d", category=kat, client_email=e, status=durum, created_at=z
    )
    p1, p2, p3, p4, p5, p6, _ = await _ekle(
        db,
        pr("Website", "in_progress", u(2030, 1, 5)),
        pr("SEO", "planning", u(2030, 1, 10)),
        pr("Website", "completed", u(2029, 12, 1)),
        pr("SEO", "in_progress", u(2029, 12, 10)),
        pr("SEO", "completed", u(2029, 12, 3)),
        pr("Website", "in_progress", u(2030, 1, 12)),
        pr("Website", "in_progress", u(2030, 1, 13), e=""),  # vaka çalışması
    )
    await _ekle(
        db,
        AuditLog(created_at=u(2029, 12, 11), islem="guncelle", tablo="projects", kayit_id=str(p3.id),
                 degisiklik_json=json.dumps({"status": ["in_progress", "completed"]})),
        AuditLog(created_at=u(2029, 12, 23), islem="guncelle", tablo="projects", kayit_id=str(p5.id),
                 degisiklik_json=json.dumps({"status": ["in_progress", "completed"], "progress": [80, 100]})),
        AuditLog(created_at=u(2029, 12, 24), islem="guncelle", tablo="projects", kayit_id=str(p4.id),
                 degisiklik_json=json.dumps({"progress": [10, 20]})),
    )
    k = (await _ozet(db))["kategori"]
    # Küme: etkin ya da bu ay açılan müşteri projeleri → p1, p2, p4, p6.
    assert k["toplam"] == 4 and k["dagilim"] == [{"ad": "SEO", "sayi": 2}, {"ad": "Website", "sayi": 2}]
    assert k["bu_ay_yeni"] == 3
    assert k["ort_sure_gun"] == 15.0  # (10 + 20) / 2
    # Website: bu ay 2, geçen ayın aynı döneminde 1 → %100; SEO: 1 ↔ 2 (düşüş).
    assert k["en_hizli"] == {"ad": "Website", "artis_yuzde": 100.0}


# ---------------------------------------------------------------------------
# Saha, son işler
# ---------------------------------------------------------------------------
async def test_saha_bugunku_etkin_isler_ve_teknisyenler(ayri_db):
    from models.saha_servisi import SahaAyarlari, SahaIsAtamalari, SahaIsEmirleri, SahaMusterileri, SahaTeknisyenleri

    db = ayri_db
    firma = "klima@firma.dev"
    m = await _ekle(db, SahaMusterileri(hesap_email=firma, ad="Atlas Klima"))
    ali, zey = await _ekle(db, SahaTeknisyenleri(hesap_email=firma, eposta="ali@firma.dev", ad="Ali Y."),
                           SahaTeknisyenleri(hesap_email=firma, eposta="zey@firma.dev", ad="Zeynep S."))
    ie = lambda no, durum, plan=None, **k: SahaIsEmirleri(  # noqa: E731
        hesap_email=firma, no=no, uid=uuid.uuid4().hex, baslik=f"İş {no}", musteri_id=m.id, durum=durum, plan_bas=plan, **k
    )
    yolda, iste, plan_bugun, plan_yarin, bitti = await _ekle(
        db,
        ie("İE-218", "yolda", u(2030, 1, 15, 8)),
        ie("İE-215", "iste", u(2030, 1, 15, 6),
           kontrol_listesi=json.dumps([{"id": 1, "metin": "a"}, {"id": 2, "metin": "b"}]), kontrol_yanitlari=json.dumps({"1": True})),
        ie("İE-220", "planlandi", u(2030, 1, 15, 13)),
        ie("İE-221", "planlandi", u(2030, 1, 16, 8)),
        ie("İE-200", "tamamlandi", u(2030, 1, 15, 5)),
    )
    await _ekle(
        db,
        SahaAyarlari(hesap_email=firma, firma_adi="Serin Klima Servis"),
        SahaIsAtamalari(is_emri_id=yolda.id, teknisyen_id=ali.id, hesap_email=firma),
        SahaIsAtamalari(is_emri_id=iste.id, teknisyen_id=zey.id, hesap_email=firma),
        SahaIsAtamalari(is_emri_id=plan_bugun.id, teknisyen_id=ali.id, hesap_email=firma),
    )
    s = (await _ozet(db))["saha"]
    assert [x["no"] for x in s["isler"]] == ["İE-215", "İE-218", "İE-220"]  # işte > yolda > planlı; yarın ve biten yok
    assert s["isler"][0]["ilerleme"] == 74 and s["isler"][1]["ilerleme"] == 40 and s["isler"][2]["ilerleme"] == 15
    assert s["isler"][0]["musteri"] == "Atlas Klima" and s["isler"][0]["firma"] == "Serin Klima Servis"
    assert [(t["ad"], t["durum"], t["is_no"]) for t in s["teknisyenler"]] == [("Zeynep S.", "iste", "İE-215"), ("Ali Y.", "yolda", "İE-218")]
    assert s["aktif"] == 2 and s["is_sayisi"] == 3 and s["bolum"] == "sahaServisi"


async def test_son_isler_karisik_ve_en_yeni_once(ayri_db):
    from models.projects import Projects
    from models.saha_servisi import SahaIsEmirleri
    from models.staff import Staff
    from models.support_tickets import Support_tickets
    from models.teklifler import Teklifler

    db = ayri_db
    await _ekle(
        db,
        Staff(ad="Selin K.", email="selin@ajans.dev"),
        Projects(title="Web sitesi yenileme", description="d", category="Website", client_name="Ada Dişçilik",
                 client_email="ada@x.dev", status="in_progress", created_at=u(2030, 1, 15, 7)),
        Projects(title="Vaka", description="d", category="Website", client_email="", created_at=u(2030, 1, 15, 11)),
        Support_tickets(client_name="Örnek Kafe", client_email="kafe@x.dev", subject="Ödeme sayfası hatası", message="m",
                        status="open", priority="acil", atanan="selin@ajans.dev", created_at=u(2030, 1, 15, 9)),
        SahaIsEmirleri(hesap_email="f@x.dev", no="İE-218", uid=uuid.uuid4().hex, baslik="Saha bakım ziyareti",
                       musteri_id=99, durum="yolda", created_at=u(2030, 1, 15, 8)),
        Teklifler(no="TKL-9", baslik="Kurumsal kimlik", genel_toplam=12250, durum="gonderildi", aday_ad="Kuzey Mimarlık",
                  olusturan_eposta="selin@ajans.dev", created_at=u(2030, 1, 15, 10)),
    )
    s = (await _ozet(db))["sonIsler"]
    assert [x["kod"] for x in s] == ["TKL-9", f"D-{s[1]['id']}", "İE-218", f"PRJ-{s[3]['id']}"]
    assert [x["tur"] for x in s] == ["teklif", "destek", "is_emri", "proje"]
    tk, d = s[0], s[1]
    assert tk["musteri"] == "Kuzey Mimarlık" and tk["tutar"] == 12250 and tk["para_birimi"] == "TRY" and tk["sorumlu"] == "Selin K."
    assert d["musteri"] == "Örnek Kafe" and d["oncelik"] == "acil" and d["sorumlu"] == "Selin K." and d["bolum"] == "tickets"
    assert s[3]["hizmet"] == "Web sitesi yenileme" and s[3]["bolum"] == "projects"


async def test_bir_kalem_patlarsa_yalniz_o_null(ayri_db, monkeypatch):
    from services import yonetim_ozeti as servis

    async def patla(db, an):
        raise RuntimeError("deneme")

    monkeypatch.setattr(servis, "kategori_hesapla", patla)
    g = await _ozet(ayri_db)
    assert g["kategori"] is None and g["aktivite"] is not None and g["hizmetHatti"] is not None


def test_onceki_ay_ayni_gun_kisa_ay():
    from services.yonetim_ozeti import onceki_ay_ayni_gun

    assert onceki_ay_ayni_gun(date(2030, 3, 31)) == (date(2030, 2, 1), date(2030, 2, 28))
    assert onceki_ay_ayni_gun(date(2030, 1, 15)) == (date(2029, 12, 1), date(2029, 12, 15))
