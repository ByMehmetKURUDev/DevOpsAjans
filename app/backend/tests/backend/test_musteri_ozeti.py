"""Faz 11B — Müşteri paneli "Genel bakış" özeti (`GET /api/v1/musteri-ozeti`).

* Yetki: oturumsuz 401; üyesi olmadığı hesabın başlığıyla 403 `hesap_uyesi_degil`; yönetici kendi adına 200
  (kendi müşteri kaydı yok → boş kalemler — diğer müşteri uçlarının davranışı).
* Her test kendi benzersiz e-postalarıyla çalışır (oturum veritabanı paylaşılıyor; özet yalnız etkin hesabın
  kayıtlarını okuduğu için başka testlerin verisi karışmaz). Zamanlar gerçek "şimdi"ye göre kurulur.
* Gizlilik: başka müşterinin hiçbir kaydı, müşteriye görünmeyen (iç) görev, paylaşılmamış toplantı notu,
  paylaşılmamış ajans hedefi ve hesabın özel hedefi yanıtta YOK.
"""

import json
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from tests.backend.conftest import jeton_uret

BASLIK = "x-mk-hesap"
YONETICI_B = {"Authorization": f"Bearer {jeton_uret('yonetici@test.dev', 'admin')}"}


def _e(ad: str) -> str:
    return f"mo-{ad}-{uuid.uuid4().hex[:8]}@test.dev"


def _b(eposta: str, hesap: str | None = None, rol: str = "user") -> dict:
    h = {"Authorization": f"Bearer {jeton_uret(eposta, rol)}"}
    if hesap:
        h[BASLIK] = hesap
    return h


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


def _tr_bugun() -> date:
    return (_simdi() + timedelta(hours=3)).date()


async def _ekle(db, *nesneler):
    for n in nesneler:
        db.add(n)
    await db.commit()
    for n in nesneler:
        await db.refresh(n)
    return nesneler[0] if len(nesneler) == 1 else nesneler


async def _modul(istemci, eposta: str, *moduller: str, acik: bool = True):
    for m in moduller:
        y = await istemci.put(f"/api/v1/moduller/musteri/{eposta}/{m}", json={"acik": acik}, headers=YONETICI_B)
        assert y.status_code == 200, (m, y.text[:200])


async def _ozet(istemci, eposta: str, hesap: str | None = None, rol: str = "user") -> dict:
    y = await istemci.get("/api/v1/musteri-ozeti", headers=_b(eposta, hesap, rol))
    assert y.status_code == 200, y.text[:300]
    assert y.headers.get("cache-control") == "no-store"
    return y.json()


async def _uye_ekle(db, hesap: str, uye: str, rol: str, izinler=None):
    from models.hesap_uyeleri import HesapUyeleri
    from services import hesap_ekibi as s

    satir = HesapUyeleri(hesap_email=hesap, uye_email=uye, rol=rol, durum="aktif", olusturma=s.simdi(),
                         izinler=json.dumps(list(izinler if izinler is not None else s.ROL_VARSAYILAN[rol])))
    db.add(satir)
    await db.commit()
    s.onbellegi_temizle()
    return satir


KALEMLER = {"olusturma", "hesap", "karsilama", "projeIlerleme", "kalanIs", "ekip", "onayBekleyen", "toplanti", "hedef",
            "bakiye", "faturalar", "destek"}


@pytest.fixture(autouse=True)
async def _ornek_ekibi_pasiflestir(db_oturumu):
    """Örnek hesabın ekip kayıtları (Staff) oturum veritabanında kalıyor; test bitince pasifleştirilir. Yoksa
    şablondan proje oluşturma (hizmete göre İLK aktif ekip üyesi) sonraki testlerde bu kişileri seçiyor."""
    yield
    from sqlalchemy import update

    from models.staff import Staff

    await db_oturumu.execute(update(Staff).where(Staff.email.like("%@ajans.test")).values(aktif=False))
    await db_oturumu.commit()


# ---------------------------------------------------------------------------
# Örnek hesap (önizlemedeki gibi dolu)
# ---------------------------------------------------------------------------
async def ornek_hesap(db, istemci, hesap: str, kisi_adi: str = "Dr. Ayşe Demir", ek: str = "") -> dict:
    """Bir müşteri hesabını gerçek kayıtlarla doldurur; dönen sözlükte kimlikler ve iz metinleri."""
    from models.auth import User
    from models.belgeler import Belgeler
    from models.content_posts import Content_posts
    from models.cuzdan import CuzdanHesaplari
    from models.invoices import Invoices
    from models.mesajlar import KonusmaMesajlari, Konusmalar
    from models.okr import OkrAnahtarSonuclar, OkrDonemler, OkrHedefler
    from models.proje_gorevleri import ProjectTasks
    from models.projects import Projects
    from models.staff import Staff
    from models.support_tickets import Support_tickets
    from models.ticket_replies import Ticket_replies
    from models.toplantilar import ToplantiKatilimcilari, Toplantilar
    from services import imzali_islem

    simdi = _simdi()
    bugun = _tr_bugun()
    iz = uuid.uuid4().hex[:6]
    await _modul(istemci, hesap, "gorevler", "islem", "mesajlar")
    await _ekle(db, User(id=f"kimlik-{hesap}", email=hesap, name=kisi_adi, role="user"))

    p = await _ekle(db, Projects(title=f"Web sitesi yenileme{ek}", description="d", category="Web", client_email=hesap,
                                 client_name="Ada Dişçilik", status="in_progress", stage="build", progress=75,
                                 created_at=simdi - timedelta(days=20), updated_at=simdi - timedelta(hours=1)))
    p2 = await _ekle(db, Projects(title=f"Logo çalışması{ek}", description="d", category="Tasarım", client_email=hesap,
                                  status="in_progress", progress=40, created_at=simdi - timedelta(days=40),
                                  updated_at=simdi - timedelta(days=5)))
    await _ekle(db, Projects(title=f"Eski proje{ek}", description="d", category="Web", client_email=hesap, status="completed",
                             progress=100, updated_at=simdi))
    selin = f"selin-{iz}@ajans.test"
    burak = f"burak-{iz}@ajans.test"
    await _ekle(db, Staff(ad="Selin Kaya", email=selin, rol="calisan", hizmetler="website", aktif=True),
                Staff(ad="Burak Tan", email=burak, rol="calisan", hizmetler="seo", aktif=True))

    def gorev(baslik, durum="yapilacak", ust=None, gorunur=True, atanan=None, olusma=15, bitti=None, bitis=None, km=False, sira=0):
        return ProjectTasks(proje_id=p.id, baslik=baslik, durum=durum, ust_gorev_id=ust, musteriye_gorunur=gorunur, atanan=atanan,
                            created_at=simdi - timedelta(days=olusma), tamamlandi_at=(simdi - timedelta(days=bitti)) if bitti is not None else None,
                            bitis_tarihi=bitis, kilometre_tasi=km, sira=sira)

    web = await _ekle(db, gorev("Web sitesi", atanan=selin, olusma=19, bitis=bugun + timedelta(days=20), sira=0))
    seo = await _ekle(db, gorev("SEO", atanan=burak, olusma=19, sira=1))
    icerik = await _ekle(db, gorev("İçerik", olusma=19, sira=2))
    await _ekle(
        db,
        gorev("Logo teslimi", "tamam", ust=web.id, atanan=selin, olusma=18, bitti=5),
        gorev("Renk paleti", "tamam", ust=web.id, atanan=selin, olusma=18, bitti=8),
        gorev("Ana sayfa tasarımı", "incelemede", ust=web.id, atanan=selin, olusma=12, bitis=bugun + timedelta(days=4)),
        gorev("Hizmetler sayfası", ust=web.id, atanan=selin, olusma=3, bitis=bugun + timedelta(days=9)),
        gorev("Anahtar kelime analizi", "tamam", ust=seo.id, atanan=burak, olusma=16, bitti=2),
        gorev("Teknik SEO", "suruyor", ust=seo.id, atanan=burak, olusma=10, bitis=bugun + timedelta(days=12)),
        gorev("Hizmetler sayfası metni", ust=icerik.id, olusma=6, bitis=bugun + timedelta(days=6)),
        gorev(f"Sunucu şifresini yenile {iz}", gorunur=False, atanan=burak, olusma=4, bitis=bugun + timedelta(days=1)),
    )
    # Mesaj: müşteri yazdı, 18 dk sonra ajans yanıtladı.
    k = await _ekle(db, Konusmalar(hesap_email=hesap, konu="Genel", tekil_anahtar=f"genel:{hesap}", durum="acik"))
    await _ekle(db, KonusmaMesajlari(konusma_id=k.id, yazan_email=hesap, yazan_rol="client", metin="Merhaba",
                                     created_at=simdi - timedelta(days=2)),
                KonusmaMesajlari(konusma_id=k.id, yazan_email=selin, yazan_rol="admin", metin="Merhaba, bakıyoruz",
                                 created_at=simdi - timedelta(days=2) + timedelta(minutes=18)))
    # Onay bekleyenler: teslim onayı (imzalı işlem) + içerik onayı + paylaşılan belge.
    _, teslim = await imzali_islem.olustur(db, "teslimat_onay", ("projects", p.id), hesap, f"{p.title} · Geliştirme",
                                           {"proje_id": p.id, "proje": p.title, "asama": "build", "not": "Ana sayfa hazır"})
    gonderi = await _ekle(db, Content_posts(title=f"Hizmetler sayfası metni{ek}", body="bir iki üç dört beş", hesap_email=hesap,
                                            status="musteri_onayi", kanallar=json.dumps(["instagram"])))
    _, icerik_islem = await imzali_islem.olustur(db, "icerik_onay", ("content_posts", gonderi.id), hesap, gonderi.title)
    gonderi.onay_islem_id = icerik_islem.id
    await db.commit()
    belge = await _ekle(db, Belgeler(tur="belge", baslik=f"Proje kapsam belgesi{ek}", alan="ajans", musteri_email=hesap,
                                     gorunurluk="paylasilan", surum=2, okundu_surum=1, paylasildi_at=simdi - timedelta(days=1)))
    # Toplantı: yarın, çevrim içi; paylaşılmamış not.
    t = await _ekle(db, Toplantilar(uid=f"t-{iz}", baslik=f"İçerik planı görüşmesi{ek}", baslangic=simdi + timedelta(days=1),
                                    sure_dk=45, yer_turu="cevrimici", baglanti="https://meet.example/abc", hesap_email=hesap,
                                    durum="planlandi", notlar=f"GIZLI-NOT-{iz}", notlar_paylasildi=False))
    await _ekle(db, ToplantiKatilimcilari(toplanti_id=t.id, tur="ekip", eposta=selin, ad="Selin Kaya", yanit="katilacak"),
                ToplantiKatilimcilari(toplanti_id=t.id, tur="dis", eposta=hesap, ad=kisi_adi, yanit="katilacak"))
    # Ajansın paylaştığı hedef (bugünü kapsayan dönem) + paylaşılmamış hedef.
    d = await _ekle(db, OkrDonemler(kapsam="@ajans", tur="ozel", baslangic=bugun - timedelta(days=10),
                                    bitis=bugun + timedelta(days=80), etkin=True, durum="acik"))
    h = await _ekle(db, OkrHedefler(kapsam="@ajans", donem_id=d.id, baslik=f"Organik trafiği %30 artırmak{ek}", gorunurluk="ekip",
                                    durum="etkin", musteri_email=hesap, musteri_paylasim=True))
    await _ekle(db, OkrHedefler(kapsam="@ajans", donem_id=d.id, baslik=f"Paylaşılmayan iç hedef {iz}", gorunurluk="ekip",
                                durum="etkin", musteri_email=hesap, musteri_paylasim=False))
    await _ekle(
        db,
        OkrAnahtarSonuclar(kapsam="@ajans", hedef_id=h.id, baslik="Organik ziyaret", tur="sayi", baslangic_deger=0,
                           hedef_deger=100, mevcut_deger=62, sira=0),
        OkrAnahtarSonuclar(kapsam="@ajans", hedef_id=h.id, baslik="İlk 10'da 15 kelime", tur="sayi", baslangic_deger=0,
                           hedef_deger=15, mevcut_deger=7, sira=1),
        OkrAnahtarSonuclar(kapsam="@ajans", hedef_id=h.id, baslik="Aylık 40 randevu formu", tur="sayi", baslangic_deger=0,
                           hedef_deger=40, mevcut_deger=32, sira=2),
        OkrAnahtarSonuclar(kapsam="@ajans", hedef_id=h.id, baslik="Dördüncü KR", tur="sayi", baslangic_deger=0,
                           hedef_deger=10, mevcut_deger=1, sira=3),
    )
    # Bakiye 12.500 TRY; iki açık fatura (biri bakiyeyle ödenebilir), bir ödenmiş.
    await _ekle(db, CuzdanHesaplari(hesap_email=hesap, para_birimi="TRY", bakiye=1_250_000))
    f1 = await _ekle(db, Invoices(invoice_no=f"FTR-{iz}-1", client_email=hesap, amount=6000.0, currency="TRY", status="unpaid",
                                  due_date=(bugun + timedelta(days=5)).isoformat()))
    f2 = await _ekle(db, Invoices(invoice_no=f"FTR-{iz}-2", client_email=hesap, amount=20000.0, currency="TRY", status="unpaid",
                                  due_date=(bugun + timedelta(days=30)).isoformat()))
    await _ekle(db, Invoices(invoice_no=f"FTR-{iz}-3", client_email=hesap, amount=100.0, currency="TRY", status="paid"))
    # Destek: biri ajans yanıtladı (müşteriyi bekliyor), biri açık, biri kapalı.
    t1 = await _ekle(db, Support_tickets(client_email=hesap, subject=f"Form e-postası{ek}", message="m", status="answered"))
    await _ekle(db, Ticket_replies(ticket_id=t1.id, yazan="ajans", yazan_ad="Selin", mesaj="Kontrol eder misiniz?"))
    t2 = await _ekle(db, Support_tickets(client_email=hesap, subject=f"Yeni sayfa isteği{ek}", message="m", status="open"))
    await _ekle(db, Support_tickets(client_email=hesap, subject=f"Kapalı talep{ek}", message="m", status="closed"))
    return {"p": p, "p2": p2, "web": web, "seo": seo, "icerik": icerik, "teslim": teslim, "gonderi": gonderi, "belge": belge,
            "toplanti": t, "hedef": h, "f1": f1, "f2": f2, "t1": t1, "t2": t2, "iz": iz, "selin": selin}


# ---------------------------------------------------------------------------
# Yetki
# ---------------------------------------------------------------------------
async def test_anonim_401(istemci):
    y = await istemci.get("/api/v1/musteri-ozeti")
    assert y.status_code == 401


async def test_uye_olmayan_hesap_basligi_403(istemci):
    y = await istemci.get("/api/v1/musteri-ozeti", headers=_b(_e("yabanci"), _e("sahip")))
    assert y.status_code == 403
    assert y.json()["detail"]["kod"] == "hesap_uyesi_degil"


async def test_yonetici_kendi_adina_bos_kalemler(istemci):
    """Yönetici başlıksız gelir: kendi e-postasının (müşteri kaydı yok) boş özeti — 403 değil."""
    g = await _ozet(istemci, _e("yonetici"), rol="admin")
    assert set(g) == KALEMLER
    assert g["projeIlerleme"] is None and g["toplanti"] is None and g["hedef"] is None


# ---------------------------------------------------------------------------
# Boş hesap
# ---------------------------------------------------------------------------
async def test_bos_hesap_kalemler_bos_ve_hatasiz(istemci, caplog):
    hesap = _e("bos")
    with caplog.at_level("ERROR"):
        g = await _ozet(istemci, hesap)
    assert not [r for r in caplog.records if "musteri_ozeti" in r.getMessage()], "hiçbir kalem hata vermemeli"
    assert set(g) == KALEMLER
    assert g["hesap"] == {"kendi": True, "rol": "sahip"}
    assert g["karsilama"] == {"hitap": None, "hesap_adi": None, "proje": None, "siradaki": None, "onay_sayisi": 0}
    for k in ("projeIlerleme", "kalanIs", "ekip", "toplanti", "hedef", "bakiye"):
        assert g[k] is None, k
    assert g["onayBekleyen"] == {"toplam": 0, "ogeler": [], "revizyon": None}
    assert g["faturalar"] == {"acik_sayisi": 0, "ogeler": []}
    assert g["destek"] == {"acik_sayisi": 0, "ogeler": []}


# ---------------------------------------------------------------------------
# Örnek veri: her kalemin içeriği
# ---------------------------------------------------------------------------
async def test_ornek_veriyle_kalemler(istemci, db_oturumu):
    hesap = _e("ada")
    o = await ornek_hesap(db_oturumu, istemci, hesap)
    g = await _ozet(istemci, hesap)
    bugun = _tr_bugun()

    k = g["karsilama"]
    assert k["hitap"] == "Dr. Ayşe"
    assert k["hesap_adi"] == "Ada Dişçilik"
    assert k["proje"] == {"id": o["p"].id, "baslik": o["p"].title, "yuzde": 75, "kategori": "Web"}
    # Sıradaki teslim: açık, görünür, son tarihi en yakın (iç görev yarın ama müşteriye görünmüyor).
    assert k["siradaki"]["baslik"] == "Ana sayfa tasarımı" and k["siradaki"]["tarih"] == (bugun + timedelta(days=4)).isoformat()
    assert k["onay_sayisi"] == 3

    pi = g["projeIlerleme"]
    assert pi["tur"] == "grup" and pi["kalem_sayisi"] == 3 and pi["proje"]["id"] == o["p"].id
    assert [(h["ad"], h["tamam"], h["toplam"], h["yuzde"]) for h in pi["halkalar"]] == [
        ("Web sitesi", 2, 4, 50), ("SEO", 1, 2, 50), ("İçerik", 0, 1, 0)]
    assert pi["son_teslim"]["baslik"] == "Anahtar kelime analizi"
    assert pi["siradaki"]["baslik"] == "Ana sayfa tasarımı"

    ki = g["kalanIs"]
    assert len(ki["gunler"]) == 14 and ki["gunler"][-1] == bugun.isoformat()
    # Bugün açık görünür görev: 3 grup + 5 alt görev − 3 tamamlanmış = 7 (iç görev sayılmaz).
    assert ki["kalan"] == 7 and ki["gercek"][-1] == 7 and ki["toplam"] == 10
    # 9 gün önce: 3 grup + logo, palet, anahtar kelime, ana sayfa, teknik seo açık (hepsi sonradan bitti / sürüyor).
    assert ki["gercek"][-10] == 3 + 5
    assert ki["plan"] is not None and len(ki["plan"]) == 14 and ki["plan_bitis"] == (bugun + timedelta(days=20)).isoformat()
    # Plan: proje açılışı (20 gün önce) → son görev tarihi (20 gün sonra), kapsam 10. 7 açık iş planda
    # bitişten 40 × 7/10 = 28 gün önce (8 gün sonra) olmalıydı → bugün 20 − 28 = 8 gün geride.
    assert ki["plan_baslangic"] == (bugun - timedelta(days=20)).isoformat()
    assert ki["plan_farki_gun"] == -8
    assert ki["plan"][-1] == pytest.approx(10 * 20 / 40)

    e = g["ekip"]
    adlar = [x["ad"] for x in e["kisiler"]]
    assert adlar == ["Selin K.", "Burak T."], adlar
    assert e["kisiler"][0]["bas_harf"] == "SK" and e["kisiler"][0]["hizmet"] == "website"
    assert e["ort_yanit_dk"] == 18
    assert "@" not in json.dumps(e)

    ob = g["onayBekleyen"]
    assert ob["toplam"] == 3
    turler = {x["tur"]: x for x in ob["ogeler"]}
    assert set(turler) == {"teslimat", "icerik", "belge"}
    assert turler["teslimat"]["id"] == o["teslim"].id and turler["teslimat"]["eylemler"] == ["onay", "revizyon"]
    assert turler["teslimat"]["not"] == "Ana sayfa hazır"
    assert turler["icerik"]["id"] == o["gonderi"].id and turler["icerik"]["kelime"] == 5
    assert turler["belge"]["id"] == o["belge"].id and turler["belge"]["eylemler"] == ["okundu"]

    t = g["toplanti"]
    assert t["id"] == o["toplanti"].id and t["yer_turu"] == "cevrimici" and t["yanitim"] == "katilacak"
    assert t["katilimci_miyim"] is True and t["katilimci_sayisi"] == 2
    assert sorted(x["bas_harf"] for x in t["katilimcilar"]) == ["AD", "SK"]
    # Yarınki toplantının katıl bağlantısı henüz verilmez (15 dk kala açılır).
    assert t["katil_baglantisi"] is None and t["katil_yakinda"] is True

    h = g["hedef"]
    assert h["kaynak"] == "ajans" and h["id"] == o["hedef"].id
    assert [x["baslik"] for x in h["krler"]] == ["Organik ziyaret", "İlk 10'da 15 kelime", "Aylık 40 randevu formu"]
    assert h["kr_sayisi"] == 4 and h["krler"][0]["ilerleme"] == pytest.approx(0.62)
    assert h["durum"] in ("tamam", "yolunda", "riskli", "geride")

    b = g["bakiye"]
    assert b == {"bakiyeler": [{"para_birimi": "TRY", "bakiye": 12500.0}], "otomatik_odeme": False, "bekleyen_yukleme": 0}

    f = g["faturalar"]
    assert f["acik_sayisi"] == 2
    assert [(x["kod"], x["kalan"], x["bakiyeden"]) for x in f["ogeler"]] == [
        (o["f1"].invoice_no, 6000.0, True), (o["f2"].invoice_no, 20000.0, False)]

    d = g["destek"]
    assert d["acik_sayisi"] == 2
    assert d["ogeler"][0]["id"] == o["t1"].id and d["ogeler"][0]["yanit_bekliyor"] is True
    assert d["ogeler"][0]["kod"] == f"D-{o['t1'].id}"
    assert d["ogeler"][1]["id"] == o["t2"].id and d["ogeler"][1]["yanit_bekliyor"] is False

    # Gizlilik: iç görev ve paylaşılmamış not/hedef yok.
    metin = json.dumps(g, ensure_ascii=False)
    assert f"Sunucu şifresini yenile {o['iz']}" not in metin
    assert f"GIZLI-NOT-{o['iz']}" not in metin
    assert f"Paylaşılmayan iç hedef {o['iz']}" not in metin
    assert o["selin"] not in metin


async def test_onay_karari_sonrasi_ogeler_duser(istemci, db_oturumu):
    """Mevcut uçlarla verilen karar sonrası öğe listeden düşer (ön yüzün çağırdığı uçlar)."""
    hesap = _e("karar")
    o = await ornek_hesap(db_oturumu, istemci, hesap)
    y = await istemci.post(f"/api/v1/islemlerim/{o['teslim'].id}", json={"sonuc": "onay"}, headers=_b(hesap))
    assert y.status_code == 200, y.text[:200]
    y = await istemci.post(f"/api/v1/belgelerim/{o['belge'].id}/okundu", headers=_b(hesap))
    assert y.status_code == 200, y.text[:200]
    g = await _ozet(istemci, hesap)
    assert [x["tur"] for x in g["onayBekleyen"]["ogeler"]] == ["icerik"]
    assert g["karsilama"]["onay_sayisi"] == 1
    # Bakiyeden öde (mevcut uç) → fatura listeden düşer, bakiye azalır.
    y = await istemci.post(f"/api/v1/cuzdanim/faturalar/{o['f1'].id}/ode", json={"istek_anahtari": uuid.uuid4().hex}, headers=_b(hesap))
    assert y.status_code == 200, y.text[:200]
    g = await _ozet(istemci, hesap)
    assert [x["id"] for x in g["faturalar"]["ogeler"]] == [o["f2"].id]
    assert g["bakiye"]["bakiyeler"][0]["bakiye"] == 6500.0


# ---------------------------------------------------------------------------
# Gizlilik ve izinler
# ---------------------------------------------------------------------------
async def test_baska_musterinin_verisi_gelmez(istemci, db_oturumu):
    a = _e("a")
    b = _e("b")
    oa = await ornek_hesap(db_oturumu, istemci, a, ek=" (A)")
    ob = await ornek_hesap(db_oturumu, istemci, b, ek=" (B)")
    ga = json.dumps(await _ozet(istemci, a), ensure_ascii=False)
    gb = json.dumps(await _ozet(istemci, b), ensure_ascii=False)
    assert "(B)" not in ga and ob["iz"] not in ga
    assert "(A)" not in gb and oa["iz"] not in gb
    # Başka hesabın başlığıyla (üye değil) erişim yok.
    y = await istemci.get("/api/v1/musteri-ozeti", headers=_b(a, b))
    assert y.status_code == 403


async def test_ekip_uyesi_izinsiz_kalem_null(istemci, db_oturumu):
    sahip = _e("sahip")
    uye = _e("uye")
    fatura = _e("fatura")
    kisitli = _e("kisitli")
    await ornek_hesap(db_oturumu, istemci, sahip)
    await _uye_ekle(db_oturumu, sahip, uye, "uye")
    await _uye_ekle(db_oturumu, sahip, fatura, "fatura")
    await _uye_ekle(db_oturumu, sahip, kisitli, "uye", izinler=[])

    g = await _ozet(istemci, uye, sahip)
    assert g["hesap"] == {"kendi": False, "rol": "uye"}
    # Üyenin `faturalar` izni yok: bakiye ve faturalar null; proje/görev/destek var.
    assert g["bakiye"] is None and g["faturalar"] is None
    assert g["projeIlerleme"] is not None and g["kalanIs"] is not None and g["destek"]["acik_sayisi"] == 2
    assert g["karsilama"]["proje"] is not None

    g = await _ozet(istemci, fatura, sahip)
    # Fatura rolü: yalnız faturalar/bakiye; proje, görev, toplantı, destek null.
    assert g["faturalar"]["acik_sayisi"] == 2 and g["bakiye"] is not None
    for k in ("projeIlerleme", "kalanIs", "ekip", "toplanti", "destek"):
        assert g[k] is None, k
    assert g["karsilama"]["proje"] is None

    g = await _ozet(istemci, kisitli, sahip)
    for k in ("projeIlerleme", "kalanIs", "ekip", "onayBekleyen", "toplanti", "hedef", "bakiye", "faturalar", "destek"):
        assert g[k] is None, k


async def test_modul_kapaliyken_kendi_hedefi_null_paylasilan_gorunur(istemci, db_oturumu):
    from models.okr import OkrAnahtarSonuclar, OkrDonemler, OkrHedefler

    hesap = _e("okr")
    bugun = _tr_bugun()
    d = await _ekle(db_oturumu, OkrDonemler(kapsam=hesap, tur="ozel", baslangic=bugun - timedelta(days=5),
                                            bitis=bugun + timedelta(days=60), etkin=True, durum="acik"))
    kendi = await _ekle(db_oturumu, OkrHedefler(kapsam=hesap, donem_id=d.id, baslik="Kendi ekip hedefimiz", gorunurluk="ekip",
                                                durum="etkin"))
    await _ekle(db_oturumu, OkrHedefler(kapsam=hesap, donem_id=d.id, baslik="Özel hedefim", gorunurluk="ozel",
                                        sahip=hesap, durum="etkin", sira=-1))
    await _ekle(db_oturumu, OkrAnahtarSonuclar(kapsam=hesap, hedef_id=kendi.id, baslik="KR", tur="sayi",
                                               baslangic_deger=0, hedef_deger=10, mevcut_deger=5))
    # Modül kapalı (varsayılan): kendi hedefi gelmez.
    g = await _ozet(istemci, hesap)
    assert g["hedef"] is None
    # Modül açık: yalnız ekip görünürlüklü kendi hedefi (özel hedef asla).
    await _modul(istemci, hesap, "hedefler")
    g = await _ozet(istemci, hesap)
    assert g["hedef"]["kaynak"] == "kendi" and g["hedef"]["baslik"] == "Kendi ekip hedefimiz"
    assert "Özel hedefim" not in json.dumps(g, ensure_ascii=False)
    # Modül yeniden kapalı; ajansın paylaştığı hedef 6O kuralıyla yine görünür (modül gerekmez).
    await _modul(istemci, hesap, "hedefler", acik=False)
    da = await _ekle(db_oturumu, OkrDonemler(kapsam="@ajans", tur="ozel", baslangic=bugun - timedelta(days=5),
                                             bitis=bugun + timedelta(days=60), etkin=True, durum="acik"))
    await _ekle(db_oturumu, OkrHedefler(kapsam="@ajans", donem_id=da.id, baslik="Ajansla ortak hedef", gorunurluk="ekip",
                                        durum="etkin", musteri_email=hesap, musteri_paylasim=True))
    g = await _ozet(istemci, hesap)
    assert g["hedef"]["kaynak"] == "ajans" and g["hedef"]["baslik"] == "Ajansla ortak hedef"


async def test_paylasilmamis_hedef_ozel_ajans_hedefi_ve_toplanti_notu_gelmez(istemci, db_oturumu):
    from models.okr import OkrDonemler, OkrHedefler
    from models.toplantilar import Toplantilar

    hesap = _e("gizli")
    bugun = _tr_bugun()
    d = await _ekle(db_oturumu, OkrDonemler(kapsam="@ajans", tur="ozel", baslangic=bugun - timedelta(days=5),
                                            bitis=bugun + timedelta(days=60), etkin=True, durum="acik"))
    # Paylaşılmamış ve "özel" görünürlüklü (paylaşım işaretli olsa da) ajans hedefi gelmez.
    await _ekle(db_oturumu, OkrHedefler(kapsam="@ajans", donem_id=d.id, baslik="Paylaşılmamış", gorunurluk="ekip", durum="etkin",
                                        musteri_email=hesap, musteri_paylasim=False),
                OkrHedefler(kapsam="@ajans", donem_id=d.id, baslik="Özel ajans hedefi", gorunurluk="ozel", durum="etkin",
                            musteri_email=hesap, musteri_paylasim=True))
    await _ekle(db_oturumu, Toplantilar(uid=f"g-{uuid.uuid4().hex[:8]}", baslik="Gizli notlu toplantı",
                                        baslangic=_simdi() + timedelta(days=2), sure_dk=30, yer_turu="yuz_yuze",
                                        hesap_email=hesap, durum="planlandi", notlar="PAYLASILMAMIS-NOT",
                                        kararlar=json.dumps(["GIZLI-KARAR"]), notlar_paylasildi=False))
    g = await _ozet(istemci, hesap)
    assert g["hedef"] is None
    assert g["toplanti"]["baslik"] == "Gizli notlu toplantı" and g["toplanti"]["katil_baglantisi"] is None
    metin = json.dumps(g, ensure_ascii=False)
    for gizli in ("Paylaşılmamış", "Özel ajans hedefi", "PAYLASILMAMIS-NOT", "GIZLI-KARAR"):
        assert gizli not in metin


async def test_katil_baglantisi_yalniz_yakin_cevrim_ici_toplantida(istemci, db_oturumu):
    from models.toplantilar import Toplantilar

    hesap = _e("katil")
    await _ekle(db_oturumu, Toplantilar(uid=f"k-{uuid.uuid4().hex[:8]}", baslik="Başlamak üzere", baslangic=_simdi() + timedelta(minutes=5),
                                        sure_dk=30, yer_turu="cevrimici", baglanti="https://meet.example/yakin", hesap_email=hesap,
                                        durum="planlandi"))
    g = await _ozet(istemci, hesap)
    assert g["toplanti"]["katil_baglantisi"] == "https://meet.example/yakin"


async def test_modul_kapaliyken_gorev_kalemleri_null(istemci, db_oturumu):
    """Görevler modülü kapalı: kalan iş ve sıradaki teslim yok; halkalar etkin projelere düşer."""
    from models.proje_gorevleri import ProjectTasks
    from models.projects import Projects

    hesap = _e("modulsuz")
    p = await _ekle(db_oturumu, Projects(title="Tek proje", description="d", category="Web", client_email=hesap,
                                         status="in_progress", progress=30))
    await _ekle(db_oturumu, ProjectTasks(proje_id=p.id, baslik="Görünür görev", musteriye_gorunur=True,
                                         bitis_tarihi=_tr_bugun() + timedelta(days=3)))
    await _modul(istemci, hesap, "gorevler", acik=False)  # varsayılanı açık
    g = await _ozet(istemci, hesap)
    assert g["kalanIs"] is None and g["karsilama"]["siradaki"] is None
    assert g["projeIlerleme"]["tur"] == "proje" and g["projeIlerleme"]["halkalar"][0]["yuzde"] == 30
    await _modul(istemci, hesap, "gorevler")
    g = await _ozet(istemci, hesap)
    assert g["kalanIs"]["kalan"] == 1 and g["karsilama"]["siradaki"]["baslik"] == "Görünür görev"


async def test_hitap_ve_kisa_ad():
    from services.musteri_ozeti import bas_harf, hitap, kisa_ad

    assert hitap("Dr. Ayşe Demir") == "Dr. Ayşe"
    assert hitap("Mehmet") == "Mehmet"
    assert hitap("  ") is None
    assert kisa_ad("Selin Kaya") == "Selin K." and kisa_ad("Ali") == "Ali"
    assert bas_harf("Selin Kaya") == "SK" and bas_harf(None, "ayse@x.com") == "AY"
