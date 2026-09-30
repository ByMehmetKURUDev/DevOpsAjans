"""İmzalı işlem bağlantıları (Faz 1E) testleri.

Veritabanı oturum boyunca paylaşılıyor; her test kendi benzersiz müşteri
e-postası ve hedef kaydıyla çalışıyor. Bellek içi hız sınırı her testten
önce sıfırlanıyor (hepsi aynı test IP'sinden geliyor).
"""

import asyncio
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

YONETIM = "/api/v1/islem-yonetim"
ACIK = "/api/v1/islem"
MUSTERI = "/api/v1/islemlerim"


def _eposta(on: str = "islem") -> str:
    return f"{on}-{uuid.uuid4().hex[:10]}@test.dev"


@pytest.fixture(autouse=True)
def _sinir_sifirla():
    from routers.imzali_islemler import hiz_siniri

    hiz_siniri.temizle()
    yield
    hiz_siniri.temizle()


async def _teklif(db, eposta, tutar=450.0):
    from models.pricing import Pricing_inquiries

    kayit = Pricing_inquiries(
        scale_kod="kobi",
        profile_kod="standart",
        period="aylik",
        addon_ids='["Blog"]',
        hesaplanan_tutar=tutar,
        musteri_eposta=eposta,
        musteri_adi="Deneme",
        kaynak="website",
    )
    db.add(kayit)
    await db.commit()
    await db.refresh(kayit)
    return kayit


async def _proje(db, eposta, asama="review"):
    from models.projects import Projects

    kayit = Projects(
        title=f"Proje {uuid.uuid4().hex[:6]}",
        description="d",
        category="Website",
        client_email=eposta,
        client_name="Müşteri A.Ş.",
        stage=asama,
        status="active",
        progress=60,
    )
    db.add(kayit)
    await db.commit()
    await db.refresh(kayit)
    return kayit


async def _olustur(istemci, baslik, beklenen=200, **govde):
    yanit = await istemci.post(f"{YONETIM}/olustur", json=govde, headers=baslik)
    assert yanit.status_code == beklenen, yanit.text
    return yanit.json()


def _jeton(yanit) -> str:
    baglanti = yanit["baglanti"]
    assert baglanti.startswith("https://mehmetkuru.dev/islem/")
    return baglanti.rsplit("/", 1)[1]


async def _taze(db, model, kimlik):
    """Kaydı veritabanından yeniden okur (oturumdaki eski değerleri ezer)."""
    sorgu = select(model).where(model.id == kimlik).execution_options(populate_existing=True)
    return (await db.execute(sorgu)).scalar_one()


async def _kayit(db, islem_id):
    from models.signed_actions import SignedActions

    return await _taze(db, SignedActions, islem_id)


# ---------------------------------------------------------------------------
# Yetki
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "metot,yol",
    [
        ("POST", f"{YONETIM}/olustur"),
        ("GET", YONETIM),
        ("GET", f"{YONETIM}/hedefler?tur=teklif_kabul"),
        ("POST", f"{YONETIM}/1/iptal"),
        ("POST", f"{YONETIM}/1/yenile"),
    ],
)
async def test_yonetim_uclari_anonime_401_musteriye_403(istemci, musteri_basligi, metot, yol):
    govde = {"tur": "teklif_kabul", "hedef_id": 1} if metot == "POST" else None
    anonim = await istemci.request(metot, yol, json=govde)
    assert anonim.status_code == 401
    musteri = await istemci.request(metot, yol, json=govde, headers=musteri_basligi())
    assert musteri.status_code == 403


async def test_musteri_uclari_oturum_ister(istemci):
    assert (await istemci.get(MUSTERI)).status_code == 401
    assert (await istemci.post(f"{MUSTERI}/1", json={"sonuc": "kabul"})).status_code == 401


# ---------------------------------------------------------------------------
# Oluşturma, jeton özeti, maskeli e-posta
# ---------------------------------------------------------------------------


async def test_jeton_yalniz_ozetle_saklaniyor_eposta_kaydinda_da_yok(istemci, yonetici_basligi, db_oturumu):
    from models.notifications import Notifications
    from models.signed_actions import SignedActions

    alici = _eposta()
    teklif = await _teklif(db_oturumu, alici)
    yanit = await _olustur(
        istemci, yonetici_basligi, tur="teklif_kabul", hedef_id=teklif.id, eposta_gonder=True, **{"not": "İlk dönem"}
    )
    jeton = _jeton(yanit)
    assert len(jeton) >= 32
    kayit = await _kayit(db_oturumu, yanit["islem"]["id"])
    assert kayit.jeton_ozeti == hashlib.sha256(jeton.encode()).hexdigest()
    assert kayit.alici_eposta == alici
    assert kayit.olusturan_eposta == "yonetici@test.dev"
    assert kayit.durum == "bekliyor" and kayit.tek_kullanimlik is True
    # Ham jeton hiçbir sütunda yok.
    for sutun in SignedActions.__table__.columns:
        assert jeton not in str(getattr(kayit, sutun.key) or "")
    # Varsayılan süre 14 gün.
    kalan = kayit.son_kullanma.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)
    assert timedelta(days=13, hours=23) < kalan <= timedelta(days=14)
    # E-posta dispatch ile gitti; bildirim satırlarında ham jeton kalmadı.
    bildirimler = (
        await db_oturumu.execute(
            select(Notifications).where(
                Notifications.ref_type == "signed_action", Notifications.ref_id == kayit.id
            )
        )
    ).scalars().all()
    assert bildirimler and all(b.recipient_email == alici for b in bildirimler)
    for b in bildirimler:
        assert jeton not in (b.body or "") and jeton not in (b.link or "") and jeton not in (b.title or "")
        assert b.link == "/client"
    # Yanıtta ayrıntı yönetici için
    assert yanit["islem"]["ayrinti"]["tutar"] == 450.0
    assert yanit["islem"]["ayrinti"]["not"] == "İlk dönem"


async def test_acik_ozet_maskeli_eposta_ve_ayrinti(istemci, yonetici_basligi, db_oturumu):
    alici = f"ahmet-{uuid.uuid4().hex[:6]}@alan.com"
    teklif = await _teklif(db_oturumu, alici, tutar=1234.5)
    jeton = _jeton(await _olustur(istemci, yonetici_basligi, tur="teklif_kabul", hedef_id=teklif.id))
    yanit = await istemci.get(f"{ACIK}/{jeton}")
    assert yanit.status_code == 200, yanit.text
    govde = yanit.json()
    assert govde["alici"] == "a***@alan.com"
    assert alici not in yanit.text
    assert govde["tur"] == "teklif_kabul" and govde["durum"] == "bekliyor"
    assert govde["sonuclar"] == ["kabul", "red"]
    assert govde["ayrinti"]["tutar"] == 1234.5
    assert govde["ayrinti"]["eklentiler"] == ["Blog"]
    assert "musteri_adi" not in govde["ayrinti"]


async def test_bilinmeyen_jeton_404(istemci):
    yanit = await istemci.get(f"{ACIK}/boyle-bir-jeton-yok-{uuid.uuid4().hex}")
    assert yanit.status_code == 404
    assert yanit.json()["detail"]["kod"] == "bulunamadi"
    yanit = await istemci.post(f"{ACIK}/yok-{uuid.uuid4().hex}", json={"sonuc": "kabul"})
    assert yanit.status_code == 404


async def test_olustur_dogrulamalari(istemci, yonetici_basligi, db_oturumu):
    teklif = await _teklif(db_oturumu, _eposta())
    y = await _olustur(istemci, yonetici_basligi, 400, tur="bilinmeyen", hedef_id=teklif.id)
    assert y["detail"]["kod"] == "tur_gecersiz"
    y = await _olustur(istemci, yonetici_basligi, 404, tur="teklif_kabul", hedef_id=99999999)
    assert y["detail"]["kod"] == "hedef_yok"
    for gun in (0, 91, -3):
        y = await _olustur(istemci, yonetici_basligi, 400, tur="teklif_kabul", hedef_id=teklif.id, gun=gun)
        assert y["detail"]["kod"] == "gun_gecersiz"
    y = await _olustur(
        istemci, yonetici_basligi, 400, tur="teklif_kabul", hedef_id=teklif.id, alici_eposta="gecersiz"
    )
    assert y["detail"]["kod"] == "alici_gecersiz"
    # Alıcısı olmayan proje, alıcı verilmeden bağlanamaz.
    proje = await _proje(db_oturumu, None)
    y = await _olustur(istemci, yonetici_basligi, 400, tur="teslimat_onay", hedef_id=proje.id)
    assert y["detail"]["kod"] == "alici_gecersiz"
    # Sınırlar kabul: 1 ve 90 gün; alıcı elle verilebilir.
    y = await _olustur(istemci, yonetici_basligi, tur="teklif_kabul", hedef_id=teklif.id, gun=90)
    assert y["islem"]["alici_eposta"] == teklif.musteri_eposta
    y = await _olustur(
        istemci, yonetici_basligi, tur="teslimat_onay", hedef_id=proje.id, gun=1, alici_eposta="Elle@Test.dev"
    )
    assert y["islem"]["alici_eposta"] == "elle@test.dev"


# ---------------------------------------------------------------------------
# Teklif: kabul / red
# ---------------------------------------------------------------------------


async def test_teklif_kabul_etkisi_bildirim_denetim_ve_tek_kullanim(istemci, yonetici_basligi, db_oturumu):
    from models.audit_log import AuditLog
    from models.notifications import Notifications
    from models.pricing import Pricing_inquiries

    alici = _eposta("kabul")
    teklif = await _teklif(db_oturumu, alici)
    yanit = await _olustur(istemci, yonetici_basligi, tur="teklif_kabul", hedef_id=teklif.id)
    jeton = _jeton(yanit)

    karar = await istemci.post(f"{ACIK}/{jeton}", json={"sonuc": "kabul"})
    assert karar.status_code == 200, karar.text
    assert karar.json()["durum"] == "kullanildi" and karar.json()["sonuc"] == "kabul"

    t = await _taze(db_oturumu, Pricing_inquiries, teklif.id)
    assert t.durum == "kabul" and t.durum_at is not None and t.durum_notu is None

    kayit = await _kayit(db_oturumu, yanit["islem"]["id"])
    assert kayit.durum == "kullanildi" and kayit.sonuc == "kabul"
    assert kayit.kullanildi_at is not None and kayit.kullanan_ip_ozeti and len(kayit.kullanan_ip_ozeti) == 64

    # Yöneticiye bildirim
    bildirim = (
        await db_oturumu.execute(
            select(Notifications).where(
                Notifications.event_type == "imzali_islem_sonuc",
                Notifications.ref_type == "pricing_inquiry",
                Notifications.ref_id == teklif.id,
            )
        )
    ).scalars().all()
    assert bildirim and bildirim[0].recipient_email == "yonetici@test.dev"
    assert "kabul" in bildirim[0].title

    # Denetim: teklif güncellemesi alıcı adına (anonim değil) + onay satırı
    satirlar = (
        await db_oturumu.execute(
            select(AuditLog).where(AuditLog.tablo == "pricing_inquiries", AuditLog.kayit_id == str(teklif.id))
        )
    ).scalars().all()
    guncelleme = [s for s in satirlar if s.islem == "guncelle"]
    assert guncelleme and guncelleme[-1].aktor_eposta == alici and guncelleme[-1].aktor_rol == "client"
    onay = (
        await db_oturumu.execute(
            select(AuditLog).where(AuditLog.tablo == "signed_actions", AuditLog.islem == "onay", AuditLog.kayit_id == str(kayit.id))
        )
    ).scalars().all()
    assert onay and onay[0].aktor_eposta == alici

    # İkinci kullanım 409; özet "kullanildi" gösterir.
    ikinci = await istemci.post(f"{ACIK}/{jeton}", json={"sonuc": "red"})
    assert ikinci.status_code == 409 and ikinci.json()["detail"]["kod"] == "kullanildi"
    ozet = (await istemci.get(f"{ACIK}/{jeton}")).json()
    assert ozet["durum"] == "kullanildi" and ozet["sonuc"] == "kabul"
    t = await _taze(db_oturumu, Pricing_inquiries, teklif.id)
    assert t.durum == "kabul"


async def test_teklif_red_gerekceyle(istemci, yonetici_basligi, db_oturumu):
    from models.pricing import Pricing_inquiries

    teklif = await _teklif(db_oturumu, _eposta("red"))
    jeton = _jeton(await _olustur(istemci, yonetici_basligi, tur="teklif_kabul", hedef_id=teklif.id))
    karar = await istemci.post(f"{ACIK}/{jeton}", json={"sonuc": "red", "not": "  Bütçe şimdilik yetmiyor  "})
    assert karar.status_code == 200, karar.text
    t = await _taze(db_oturumu, Pricing_inquiries, teklif.id)
    assert t.durum == "red" and t.durum_notu == "Bütçe şimdilik yetmiyor"


async def test_yanlis_sonuc_ve_not_denetimi_400_ve_baglanti_bozulmaz(istemci, yonetici_basligi, db_oturumu):
    teklif = await _teklif(db_oturumu, _eposta())
    jeton = _jeton(await _olustur(istemci, yonetici_basligi, tur="teklif_kabul", hedef_id=teklif.id))
    for sonuc in ("onay", "revizyon", "goruntulendi", "", "KABULX"):
        y = await istemci.post(f"{ACIK}/{jeton}", json={"sonuc": sonuc})
        assert y.status_code == 400 and y.json()["detail"]["kod"] == "gecersiz_sonuc", sonuc
    y = await istemci.post(f"{ACIK}/{jeton}", json={"sonuc": "red", "not": "x" * 2001})
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "not_uzun"
    # Hatalı denemeler bağlantıyı tüketmez.
    assert (await istemci.post(f"{ACIK}/{jeton}", json={"sonuc": "KABUL"})).status_code == 200

    proje = await _proje(db_oturumu, _eposta())
    jeton2 = _jeton(await _olustur(istemci, yonetici_basligi, tur="teslimat_onay", hedef_id=proje.id))
    y = await istemci.post(f"{ACIK}/{jeton2}", json={"sonuc": "revizyon", "not": "   "})
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "not_gerekli"
    y = await istemci.post(f"{ACIK}/{jeton2}", json={"sonuc": "kabul"})
    assert y.status_code == 400


async def test_yaris_iki_eszamanli_istekten_biri_409(istemci, yonetici_basligi, db_oturumu):
    from models.pricing import Pricing_inquiries

    teklif = await _teklif(db_oturumu, _eposta("yaris"))
    jeton = _jeton(await _olustur(istemci, yonetici_basligi, tur="teklif_kabul", hedef_id=teklif.id))
    y1, y2 = await asyncio.gather(
        istemci.post(f"{ACIK}/{jeton}", json={"sonuc": "kabul"}),
        istemci.post(f"{ACIK}/{jeton}", json={"sonuc": "red", "not": "vazgeçtim"}),
    )
    assert sorted([y1.status_code, y2.status_code]) == [200, 409], (y1.text, y2.text)
    kazanan = (y1 if y1.status_code == 200 else y2).json()["sonuc"]
    t = await _taze(db_oturumu, Pricing_inquiries, teklif.id)
    assert t.durum == kazanan


async def test_bayat_kayitla_kullanim_kosullu_update_ile_reddedilir(istemci, yonetici_basligi, db_oturumu):
    """Ön denetimi geçmiş (bellekte hâlâ "bekliyor") ikinci istek: UPDATE 0 satır → 409.

    Zamanlamaya bağlı olmayan yarış testi: eşzamanlı ikinci isteğin tam
    olarak düştüğü durumu elle kuruyor.
    """
    from core.database import db_manager
    from models.pricing import Pricing_inquiries
    from models.signed_actions import SignedActions
    from services import imzali_islem as servis

    teklif = await _teklif(db_oturumu, _eposta("bayat"))
    yanit = await _olustur(istemci, yonetici_basligi, tur="teklif_kabul", hedef_id=teklif.id)
    async with db_manager.async_session_maker() as ikinci:
        bayat = (
            await ikinci.execute(select(SignedActions).where(SignedActions.id == yanit["islem"]["id"]))
        ).scalar_one()
        await ikinci.commit()  # okuma kilidini bırak; nesne bellekte "bekliyor"
        assert bayat.durum == "bekliyor"

        assert (await istemci.post(f"{ACIK}/{_jeton(yanit)}", json={"sonuc": "kabul"})).status_code == 200

        with pytest.raises(servis.IslemHatasi) as hata:
            await servis._kullan_kayit(ikinci, bayat, "red", "geç kaldım", ip_ozeti=None)
        assert hata.value.durum == 409 and hata.value.kod == "kullanildi"
    t = await _taze(db_oturumu, Pricing_inquiries, teklif.id)
    assert t.durum == "kabul" and t.durum_notu is None


async def test_etki_patlarsa_kullanim_geri_alinir(istemci, yonetici_basligi, db_oturumu, monkeypatch):
    from services import imzali_islem as servis

    teklif = await _teklif(db_oturumu, _eposta("geri"))
    yanit = await _olustur(istemci, yonetici_basligi, tur="teklif_kabul", hedef_id=teklif.id)

    async def _patla(*a, **k):
        raise RuntimeError("hedef yazılamadı")

    monkeypatch.setattr(servis, "_etkiyi_uygula", _patla)
    with pytest.raises(RuntimeError):
        await istemci.post(f"{ACIK}/{_jeton(yanit)}", json={"sonuc": "kabul"})
    kayit = await _kayit(db_oturumu, yanit["islem"]["id"])
    assert kayit.durum == "bekliyor" and kayit.sonuc is None
    monkeypatch.undo()
    assert (await istemci.post(f"{ACIK}/{_jeton(yanit)}", json={"sonuc": "kabul"})).status_code == 200


async def test_suresi_dolan_baglanti_410(istemci, yonetici_basligi, db_oturumu):
    from models.signed_actions import SignedActions

    teklif = await _teklif(db_oturumu, _eposta("sure"))
    yanit = await _olustur(istemci, yonetici_basligi, tur="teklif_kabul", hedef_id=teklif.id, gun=1)
    jeton = _jeton(yanit)
    await db_oturumu.execute(
        update(SignedActions)
        .where(SignedActions.id == yanit["islem"]["id"])
        .values(son_kullanma=datetime.now(timezone.utc) - timedelta(minutes=1))
    )
    await db_oturumu.commit()
    y = await istemci.post(f"{ACIK}/{jeton}", json={"sonuc": "kabul"})
    assert y.status_code == 410 and y.json()["detail"]["kod"] == "suresi_doldu"
    ozet = (await istemci.get(f"{ACIK}/{jeton}")).json()
    assert ozet["durum"] == "suresi_doldu"
    kayit = await _kayit(db_oturumu, yanit["islem"]["id"])
    assert kayit.durum == "suresi_doldu"


# ---------------------------------------------------------------------------
# Teslimat: onay / revizyon
# ---------------------------------------------------------------------------


async def test_teslimat_onayi_olay_asama_ilerletme_bildirim(istemci, yonetici_basligi, db_oturumu):
    from models.notifications import Notifications
    from models.project_events import Project_events
    from models.projects import Projects

    alici = _eposta("teslim")
    proje = await _proje(db_oturumu, alici, "review")
    yanit = await _olustur(
        istemci, yonetici_basligi, tur="teslimat_onay", hedef_id=proje.id, baglanti="https://onizleme.test/v2",
        **{"not": "Ana sayfa ve iletişim hazır"},
    )
    ayr = yanit["islem"]["ayrinti"]
    assert ayr["asama"] == "review" and ayr["baglanti"] == "https://onizleme.test/v2" and ayr["ilerlet"] is True
    jeton = _jeton(yanit)
    acik = (await istemci.get(f"{ACIK}/{jeton}")).json()
    assert acik["sonuclar"] == ["onay", "revizyon"] and acik["not_zorunlu"] == ["revizyon"]

    karar = await istemci.post(f"{ACIK}/{jeton}", json={"sonuc": "onay"})
    assert karar.status_code == 200, karar.text

    p = await _taze(db_oturumu, Projects, proje.id)
    assert p.stage == "launch" and p.progress == 83
    olaylar = (
        await db_oturumu.execute(select(Project_events).where(Project_events.project_id == proje.id))
    ).scalars().all()
    turler = {o.event_type for o in olaylar}
    assert {"client_approval", "stage_change"} <= turler
    onay = next(o for o in olaylar if o.event_type == "client_approval")
    assert onay.actor_email == alici and onay.visible_to_client == "1" and "İnceleme" in onay.title
    bildirim = (
        await db_oturumu.execute(
            select(Notifications).where(
                Notifications.event_type == "imzali_islem_sonuc",
                Notifications.ref_type == "project",
                Notifications.ref_id == proje.id,
            )
        )
    ).scalars().all()
    assert bildirim and bildirim[0].recipient_email == "yonetici@test.dev"


async def test_teslimat_onayi_proje_elle_ilerletildiyse_asamaya_dokunmaz(istemci, yonetici_basligi, db_oturumu):
    from models.projects import Projects

    proje = await _proje(db_oturumu, _eposta(), "design")
    jeton = _jeton(await _olustur(istemci, yonetici_basligi, tur="teslimat_onay", hedef_id=proje.id))
    await db_oturumu.execute(update(Projects).where(Projects.id == proje.id).values(stage="build"))
    await db_oturumu.commit()
    assert (await istemci.post(f"{ACIK}/{jeton}", json={"sonuc": "onay"})).status_code == 200
    p = await _taze(db_oturumu, Projects, proje.id)
    assert p.stage == "build"


async def test_teslimat_revizyon_olay_destek_talebi_bildirim(istemci, yonetici_basligi, db_oturumu):
    from models.notifications import Notifications
    from models.project_events import Project_events
    from models.projects import Projects
    from models.support_tickets import Support_tickets

    alici = _eposta("revizyon")
    proje = await _proje(db_oturumu, alici, "review")
    jeton = _jeton(await _olustur(istemci, yonetici_basligi, tur="teslimat_onay", hedef_id=proje.id))
    metin = "Logo biraz daha büyük olsun, iletişim formuna telefon alanı eklensin."
    karar = await istemci.post(f"{ACIK}/{jeton}", json={"sonuc": "revizyon", "not": metin})
    assert karar.status_code == 200, karar.text

    p = await _taze(db_oturumu, Projects, proje.id)
    assert p.stage == "review"  # revizyon aşamayı ilerletmez
    olay = (
        await db_oturumu.execute(
            select(Project_events).where(
                Project_events.project_id == proje.id, Project_events.event_type == "revision_request"
            )
        )
    ).scalar_one()
    assert olay.body == metin and olay.actor_email == alici
    talep = (
        await db_oturumu.execute(select(Support_tickets).where(Support_tickets.project_id == proje.id))
    ).scalar_one()
    assert talep.client_email == alici and talep.message == metin and talep.kaynak == "islem" and talep.status == "open"
    bildirim = (
        await db_oturumu.execute(
            select(Notifications).where(
                Notifications.event_type == "imzali_islem_sonuc",
                Notifications.ref_type == "project",
                Notifications.ref_id == proje.id,
            )
        )
    ).scalars().all()
    assert bildirim and "Revizyon" in bildirim[0].title and f"#{talep.id}" in bildirim[0].body


# ---------------------------------------------------------------------------
# Müşteri paneli
# ---------------------------------------------------------------------------


async def test_musteri_paneli_yalniz_kendi_bekleyenleri_ve_panelden_karar(
    istemci, yonetici_basligi, musteri_basligi, db_oturumu
):
    from models.pricing import Pricing_inquiries

    ben, baskasi = _eposta("ben"), _eposta("baskasi")
    t1 = await _teklif(db_oturumu, ben)
    t2 = await _teklif(db_oturumu, baskasi)
    y1 = await _olustur(istemci, yonetici_basligi, tur="teklif_kabul", hedef_id=t1.id)
    y2 = await _olustur(istemci, yonetici_basligi, tur="teklif_kabul", hedef_id=t2.id)

    liste = await istemci.get(MUSTERI, headers=musteri_basligi(ben))
    assert liste.status_code == 200
    kimlikler = [s["id"] for s in liste.json()]
    assert kimlikler == [y1["islem"]["id"]]
    satir = liste.json()[0]
    assert "baglanti" not in satir and "jeton" not in str(satir).lower()
    assert satir["sonuclar"] == ["kabul", "red"]

    # Başkasınınkine karar veremez (404 — varlığı da sızmaz)
    y = await istemci.post(f"{MUSTERI}/{y2['islem']['id']}", json={"sonuc": "kabul"}, headers=musteri_basligi(ben))
    assert y.status_code == 404

    # Kendi işlemine panelden karar
    y = await istemci.post(f"{MUSTERI}/{y1['islem']['id']}", json={"sonuc": "kabul"}, headers=musteri_basligi(ben))
    assert y.status_code == 200, y.text
    t = await _taze(db_oturumu, Pricing_inquiries, t1.id)
    assert t.durum == "kabul"
    # Artık listede yok; bağlantı da kullanılmış
    assert (await istemci.get(MUSTERI, headers=musteri_basligi(ben))).json() == []
    ikinci = await istemci.post(f"{ACIK}/{_jeton(y1)}", json={"sonuc": "red"})
    assert ikinci.status_code == 409
    y = await istemci.post(f"{MUSTERI}/{y1['islem']['id']}", json={"sonuc": "red"}, headers=musteri_basligi(ben))
    assert y.status_code == 409


# ---------------------------------------------------------------------------
# Yönetim: liste, iptal, yenile, hedefler
# ---------------------------------------------------------------------------


async def test_iptal_ve_yenile(istemci, yonetici_basligi, db_oturumu):
    teklif = await _teklif(db_oturumu, _eposta("iptal"))
    yanit = await _olustur(istemci, yonetici_basligi, tur="teklif_kabul", hedef_id=teklif.id, gun=7)
    islem_id, eski_jeton = yanit["islem"]["id"], _jeton(yanit)

    iptal = await istemci.post(f"{YONETIM}/{islem_id}/iptal", headers=yonetici_basligi)
    assert iptal.status_code == 200 and iptal.json()["durum"] == "iptal"
    y = await istemci.post(f"{ACIK}/{eski_jeton}", json={"sonuc": "kabul"})
    assert y.status_code == 410 and y.json()["detail"]["kod"] == "iptal"
    assert (await istemci.get(f"{ACIK}/{eski_jeton}")).json()["durum"] == "iptal"
    tekrar = await istemci.post(f"{YONETIM}/{islem_id}/iptal", headers=yonetici_basligi)
    assert tekrar.status_code == 409

    yeni = await istemci.post(f"{YONETIM}/{islem_id}/yenile", json={}, headers=yonetici_basligi)
    assert yeni.status_code == 200, yeni.text
    yj = yeni.json()
    assert yj["eski_id"] == islem_id and yj["islem"]["id"] != islem_id
    assert yj["islem"]["baslik"] == yanit["islem"]["baslik"] and yj["islem"]["durum"] == "bekliyor"
    kalan = datetime.fromisoformat(yj["islem"]["son_kullanma"]) - datetime.now(timezone.utc)
    assert timedelta(days=6) < kalan <= timedelta(days=7)
    yeni_jeton = _jeton(yj)
    assert yeni_jeton != eski_jeton
    assert (await istemci.post(f"{ACIK}/{yeni_jeton}", json={"sonuc": "kabul"})).status_code == 200
    # Kullanılmış bağlantı yenilenmez
    y = await istemci.post(f"{YONETIM}/{yj['islem']['id']}/yenile", headers=yonetici_basligi)
    assert y.status_code == 409


async def test_yenile_bekleyeni_iptal_eder(istemci, yonetici_basligi, db_oturumu):
    teklif = await _teklif(db_oturumu, _eposta())
    yanit = await _olustur(istemci, yonetici_basligi, tur="teklif_kabul", hedef_id=teklif.id)
    yeni = await istemci.post(f"{YONETIM}/{yanit['islem']['id']}/yenile", json={"gun": 3}, headers=yonetici_basligi)
    assert yeni.status_code == 200
    assert (await _kayit(db_oturumu, yanit["islem"]["id"])).durum == "iptal"
    assert (await istemci.post(f"{ACIK}/{_jeton(yanit)}", json={"sonuc": "kabul"})).status_code == 410
    assert (await istemci.post(f"{YONETIM}/99999999/yenile", headers=yonetici_basligi)).status_code == 404


async def test_yonetim_listesi_filtreler_ve_suresi_dolan(istemci, yonetici_basligi, db_oturumu):
    from models.signed_actions import SignedActions

    alici = _eposta("liste")
    teklif = await _teklif(db_oturumu, alici)
    proje = await _proje(db_oturumu, alici)
    a = await _olustur(istemci, yonetici_basligi, tur="teklif_kabul", hedef_id=teklif.id)
    b = await _olustur(istemci, yonetici_basligi, tur="teslimat_onay", hedef_id=proje.id)
    await db_oturumu.execute(
        update(SignedActions)
        .where(SignedActions.id == b["islem"]["id"])
        .values(son_kullanma=datetime.now(timezone.utc) - timedelta(seconds=5))
    )
    await db_oturumu.commit()

    y = await istemci.get(YONETIM, params={"tur": "teklif_kabul"}, headers=yonetici_basligi)
    assert y.status_code == 200
    assert a["islem"]["id"] in [s["id"] for s in y.json()]
    assert all(s["tur"] == "teklif_kabul" for s in y.json())
    y = await istemci.get(YONETIM, params={"durum": "suresi_doldu"}, headers=yonetici_basligi)
    assert b["islem"]["id"] in [s["id"] for s in y.json()]
    # Listede bağlantı/jeton yok
    assert "jeton" not in y.text and "/islem/" not in y.text


async def test_hedefler_listesi(istemci, yonetici_basligi, db_oturumu):
    alici = _eposta("hedef")
    teklif = await _teklif(db_oturumu, alici)
    proje = await _proje(db_oturumu, alici)
    y = await istemci.get(f"{YONETIM}/hedefler", params={"tur": "teklif_kabul"}, headers=yonetici_basligi)
    assert y.status_code == 200
    satir = next(s for s in y.json() if s["id"] == teklif.id)
    assert satir["alici"] == alici and "450" in satir["etiket"]
    y = await istemci.get(f"{YONETIM}/hedefler", params={"tur": "teslimat_onay"}, headers=yonetici_basligi)
    assert any(s["id"] == proje.id and s["ek"] == "review" for s in y.json())
    y = await istemci.get(f"{YONETIM}/hedefler", params={"tur": "x"}, headers=yonetici_basligi)
    assert y.status_code == 400


# ---------------------------------------------------------------------------
# Hız sınırı
# ---------------------------------------------------------------------------


async def test_ip_basina_dakikada_20_istek(istemci):
    kodlar = [(await istemci.get(f"{ACIK}/yok-{i}")).status_code for i in range(21)]
    assert kodlar[:20] == [404] * 20
    assert kodlar[20] == 429
    y = await istemci.post(f"{ACIK}/yok", json={"sonuc": "kabul"})
    assert y.status_code == 429 and y.json()["detail"]["kod"] == "sinir"


async def test_servis_maske_ve_gun():
    from services import imzali_islem as s

    assert s.eposta_maskele("Ahmet@Alan.com") == "a***@alan.com"
    assert s.eposta_maskele("x") == "***"
    assert s.gun_duzelt(None) == 14
    with pytest.raises(s.IslemHatasi):
        s.gun_duzelt(91)
