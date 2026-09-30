"""Bildirim merkezi: olay × kanal matrisi, kişisel tercih ve Web Push (Faz 1D).

Veritabanı oturum boyunca paylaşılıyor: her test kendi benzersiz e-postasıyla
çalışıyor, matris her testten sonra varsayılana dönüyor. Push servisine
hiç çıkılmıyor; `services.web_push._webpush_cagir` testte değiştiriliyor.
"""

import importlib.util
import os
import stat
import uuid
from datetime import time
from pathlib import Path

import pytest
from sqlalchemy import delete, select

MATRIS = "/api/v1/bildirim/matris"
TERCIH = "/api/v1/bildirim/tercihlerim"
ANAHTAR = "/api/v1/bildirim/push/anahtar"
ABONE = "/api/v1/bildirim/push/abone"
DENE = "/api/v1/bildirim/push/dene"


def _eposta(on: str = "bildirim") -> str:
    return f"{on}-{uuid.uuid4().hex[:10]}@test.dev"


def _uc_nokta() -> str:
    return f"https://fcm.googleapis.com/fcm/send/{uuid.uuid4().hex}"


ABONELIK_ANAHTARLARI = {
    "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM",
    "auth": "tBHItJI5svbpez7KI4CCXg",
}


def _vapid_script():
    yol = Path(__file__).resolve().parents[2] / "scripts" / "vapid_uret.py"
    spec = importlib.util.spec_from_file_location("vapid_uret", yol)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


@pytest.fixture(autouse=True)
async def _temiz_ortam(db_oturumu, monkeypatch):
    """Her testte VAPID yok, matris varsayılan; test bitince de öyle kalsın."""
    from models.site_settings import Site_settings

    monkeypatch.delenv("VAPID_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)
    yield
    await db_oturumu.execute(delete(Site_settings).where(Site_settings.setting_key == "bildirim_matrisi"))
    await db_oturumu.commit()


@pytest.fixture
def vapid(monkeypatch):
    """Geçici, gerçek bir VAPID çifti (anahtarlar yalnız bu test sürecinde)."""
    acik, gizli = _vapid_script().anahtar_cifti_uret()
    monkeypatch.setenv("VAPID_PUBLIC_KEY", acik)
    monkeypatch.setenv("VAPID_PRIVATE_KEY", gizli)
    return {"acik": acik, "gizli": gizli}


@pytest.fixture
def sahte_push(monkeypatch):
    """endpoint → HTTP kodu. Çağrılan endpoint'ler `cagrilar` listesinde."""
    from services import web_push

    durum = {"kodlar": {}, "varsayilan": 201, "cagrilar": [], "veriler": []}

    def _cagir(abonelik, veri, gizli, konu):
        durum["cagrilar"].append(abonelik["endpoint"])
        durum["veriler"].append(veri)
        assert gizli and konu.startswith("mailto:")
        return durum["kodlar"].get(abonelik["endpoint"], durum["varsayilan"])

    monkeypatch.setattr(web_push, "_webpush_cagir", _cagir)
    return durum


async def _dagit(db, olay, eposta, rol="client", **ek):
    from services.notify import dispatch

    return await dispatch(
        db,
        event_type=olay,
        title=ek.get("baslik", "Başlık"),
        body="Gövde",
        recipients=[{"email": eposta, "role": rol}],
        link="/client",
    )


async def _satirlar(db, eposta, olay):
    from models.notifications import Notifications

    sonuc = await db.execute(
        select(Notifications).where(Notifications.recipient_email == eposta, Notifications.event_type == olay)
    )
    return {s.channel: s for s in sonuc.scalars().all()}


async def _matris_kapat(istemci, yonetici_basligi, rol, olay, kanal):
    yanit = await istemci.get(MATRIS, headers=yonetici_basligi)
    assert yanit.status_code == 200, yanit.text
    matris = yanit.json()["matris"]
    matris[rol][olay][kanal] = False
    yanit = await istemci.put(MATRIS, json={"matris": matris}, headers=yonetici_basligi)
    assert yanit.status_code == 200, yanit.text
    return yanit.json()


async def _abone_ol(istemci, baslik, endpoint, beklenen=200):
    yanit = await istemci.post(
        ABONE, json={"endpoint": endpoint, "keys": ABONELIK_ANAHTARLARI}, headers=baslik
    )
    assert yanit.status_code == beklenen, yanit.text
    return yanit


# ---------------------------------------------------------------------------
# Yetki
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("metot", ["GET", "PUT"])
async def test_matris_anonime_401_musteriye_403(istemci, musteri_basligi, metot):
    govde = {"matris": {}} if metot == "PUT" else None
    assert (await istemci.request(metot, MATRIS, json=govde)).status_code == 401
    assert (await istemci.request(metot, MATRIS, json=govde, headers=musteri_basligi())).status_code == 403


@pytest.mark.parametrize(
    "metot,yol",
    [("GET", TERCIH), ("PUT", TERCIH), ("POST", ABONE), ("DELETE", ABONE), ("POST", DENE)],
)
async def test_kisisel_uclar_anonime_401(istemci, metot, yol):
    govde = {"endpoint": _uc_nokta(), "keys": ABONELIK_ANAHTARLARI} if metot != "GET" else None
    assert (await istemci.request(metot, yol, json=govde)).status_code == 401


async def test_musteri_tercihleri_yalniz_musteri_olaylari(istemci, musteri_basligi):
    yanit = await istemci.get(TERCIH, headers=musteri_basligi(_eposta()))
    assert yanit.status_code == 200, yanit.text
    govde = yanit.json()
    assert govde["rol"] == "client"
    olaylar = {o["olay"] for o in govde["olaylar"]}
    assert {"project_stage", "kredi_yuklendi", "invoice", "ticket_reply"} <= olaylar
    assert "inquiry" not in olaylar and "site_analizi_aday" not in olaylar
    assert govde["kanallar"] == ["inapp", "email", "push", "sms", "whatsapp"]
    # Test ortamında hiçbir dış kanal yapılandırılmamış.
    assert govde["kanal_durumu"]["inapp"] == "hazir"
    assert govde["kanal_durumu"]["email"] == "yapilandirilmadi"
    assert govde["kanal_durumu"]["push"] == "yapilandirilmadi"
    assert govde["push"] == {"yapilandirildi": False, "anahtar": None, "abonelik_sayisi": 0}


async def test_yonetici_tercihleri_yonetici_olaylari(istemci, yonetici_basligi):
    yanit = await istemci.get(TERCIH, headers=yonetici_basligi)
    assert yanit.status_code == 200
    olaylar = {o["olay"] for o in yanit.json()["olaylar"]}
    assert yanit.json()["rol"] == "admin"
    assert {"inquiry", "ticket", "site_analizi_aday", "kredi_azaldi"} <= olaylar
    assert "project_note" not in olaylar


# ---------------------------------------------------------------------------
# Matris
# ---------------------------------------------------------------------------


async def test_matris_varsayilani_ve_katalog(istemci, yonetici_basligi):
    govde = (await istemci.get(MATRIS, headers=yonetici_basligi)).json()
    olaylar = {o["olay"]: o for o in govde["olaylar"]}
    for gerekli in (
        "inquiry", "ticket", "ticket_reply", "project_stage", "project_delivery", "invoice",
        "invoice_paid", "kredi_yuklendi", "kredi_azaldi", "site_analizi_rapor", "bekleme_listesi",
    ):
        assert gerekli in olaylar
    assert olaylar["inquiry"]["roller"] == ["admin"]
    assert olaylar["ticket_reply"]["tetikleniyor"] is False
    assert all(govde["matris"][r][o][k] for r in ("admin", "client") for o in olaylar for k in govde["kanallar"])
    assert govde["push"]["yapilandirildi"] is False


async def test_matris_gecersiz_girdi_temizleniyor_inapp_kapatilamiyor(istemci, yonetici_basligi):
    yanit = await istemci.put(
        MATRIS,
        json={
            "matris": {
                "client": {
                    "invoice": {"inapp": False, "email": False, "faks": False, "sms": "hayir"},
                    "uydurma_olay": {"email": False},
                },
                "misafir": {"invoice": {"email": False}},
            }
        },
        headers=yonetici_basligi,
    )
    assert yanit.status_code == 200, yanit.text
    matris = yanit.json()["matris"]
    assert set(matris) == {"admin", "client"}
    assert matris["client"]["invoice"] == {"inapp": True, "email": False, "push": True, "sms": True, "whatsapp": True}
    assert "uydurma_olay" not in matris["client"]
    # Kalıcı: yeniden okununca aynı.
    assert (await istemci.get(MATRIS, headers=yonetici_basligi)).json()["matris"] == matris


async def test_matris_kapali_kanal_satir_yazmiyor(istemci, yonetici_basligi, db_oturumu):
    await _matris_kapat(istemci, yonetici_basligi, "client", "kredi_yuklendi", "email")
    eposta = _eposta()

    await _dagit(db_oturumu, "kredi_yuklendi", eposta)
    satirlar = await _satirlar(db_oturumu, eposta, "kredi_yuklendi")
    assert "inapp" in satirlar and "email" not in satirlar
    # Push hâlâ açık: anahtar olmadığı için "skipped" yazılıyor.
    assert satirlar["push"].delivery_status == "skipped"

    # Aynı kişiye matrisin kapatmadığı olay: e-posta satırı var.
    await _dagit(db_oturumu, "kredi_azaldi", eposta)
    assert "email" in await _satirlar(db_oturumu, eposta, "kredi_azaldi")


async def test_matris_rol_ayri(istemci, yonetici_basligi, db_oturumu):
    """Müşteri tablosunda kapatılan kanal yöneticiye gitmeye devam ediyor."""
    await _matris_kapat(istemci, yonetici_basligi, "client", "project_stage", "email")
    musteri, yonetici = _eposta("m"), _eposta("y")
    from services.notify import dispatch

    await dispatch(
        db_oturumu,
        event_type="project_stage",
        title="Aşama",
        recipients=[{"email": musteri, "role": "client"}, {"email": yonetici, "role": "admin"}],
    )
    assert "email" not in await _satirlar(db_oturumu, musteri, "project_stage")
    assert "email" in await _satirlar(db_oturumu, yonetici, "project_stage")


# ---------------------------------------------------------------------------
# Kişisel tercih
# ---------------------------------------------------------------------------


async def test_kisisel_tercih_kapatinca_satir_yazmiyor(istemci, musteri_basligi, db_oturumu):
    kapatan, diger = _eposta("kapatan"), _eposta("diger")
    yanit = await istemci.put(
        TERCIH, json={"tercih": {"project_note": {"email": False, "push": False}}}, headers=musteri_basligi(kapatan)
    )
    assert yanit.status_code == 200, yanit.text
    hucre = next(o for o in yanit.json()["olaylar"] if o["olay"] == "project_note")
    assert hucre["acik"]["email"] is False and hucre["izin"]["email"] is True

    await _dagit(db_oturumu, "project_note", kapatan)
    await _dagit(db_oturumu, "project_note", diger)
    kapatanin = await _satirlar(db_oturumu, kapatan, "project_note")
    assert set(kapatanin) == {"inapp"}
    assert {"inapp", "email", "push"} <= set(await _satirlar(db_oturumu, diger, "project_note"))


async def test_kisisel_tercih_kaydedilir_ve_geri_acilir(istemci, musteri_basligi):
    baslik = musteri_basligi(_eposta())
    await istemci.put(TERCIH, json={"tercih": {"invoice": {"sms": False}}}, headers=baslik)
    hucre = next(o for o in (await istemci.get(TERCIH, headers=baslik)).json()["olaylar"] if o["olay"] == "invoice")
    assert hucre["acik"]["sms"] is False
    await istemci.put(TERCIH, json={"tercih": {"invoice": {"sms": True}}}, headers=baslik)
    hucre = next(o for o in (await istemci.get(TERCIH, headers=baslik)).json()["olaylar"] if o["olay"] == "invoice")
    assert hucre["acik"]["sms"] is True


async def test_inapp_kapatilamiyor(istemci, musteri_basligi, db_oturumu):
    eposta = _eposta()
    yanit = await istemci.put(TERCIH, json={"tercih": {"kredi_azaldi": {"inapp": False}}}, headers=musteri_basligi(eposta))
    hucre = next(o for o in yanit.json()["olaylar"] if o["olay"] == "kredi_azaldi")
    assert hucre["acik"]["inapp"] is True
    await _dagit(db_oturumu, "kredi_azaldi", eposta)
    assert (await _satirlar(db_oturumu, eposta, "kredi_azaldi"))["inapp"].delivery_status == "sent"


async def test_kisi_matrisin_kapattigini_acamaz(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    await _matris_kapat(istemci, yonetici_basligi, "client", "invoice", "email")
    eposta = _eposta()
    yanit = await istemci.put(TERCIH, json={"tercih": {"invoice": {"email": True}}}, headers=musteri_basligi(eposta))
    hucre = next(o for o in yanit.json()["olaylar"] if o["olay"] == "invoice")
    assert hucre["izin"]["email"] is False and hucre["acik"]["email"] is False
    await _dagit(db_oturumu, "invoice", eposta)
    assert "email" not in await _satirlar(db_oturumu, eposta, "invoice")


async def test_katalog_disi_olay_eski_davranis(db_oturumu):
    """Davet gibi katalog dışı olay: e-posta ana anahtara bağlı, push yok."""
    eposta = _eposta()
    await _dagit(db_oturumu, "client_invite", eposta)
    satirlar = await _satirlar(db_oturumu, eposta, "client_invite")
    assert set(satirlar) == {"inapp", "email"}


async def test_sessiz_saatler(istemci, musteri_basligi, db_oturumu, monkeypatch, vapid, sahte_push):
    from services import bildirim_tercih as bt

    assert bt.sessiz_saatte_mi({"bas": "22:00", "bit": "08:00"}, time(23, 30))
    assert bt.sessiz_saatte_mi({"bas": "22:00", "bit": "08:00"}, time(7, 59))
    assert not bt.sessiz_saatte_mi({"bas": "22:00", "bit": "08:00"}, time(12, 0))
    assert bt.sessiz_saatte_mi({"bas": "09:00", "bit": "17:00"}, time(12, 0))
    assert not bt.sessiz_saatte_mi(None, time(12, 0))
    assert bt.sessiz_duzelt({"bas": "25:00", "bit": "08:00"}) is None

    eposta = _eposta()
    baslik = musteri_basligi(eposta)
    yanit = await istemci.put(TERCIH, json={"sessiz_saatler": {"bas": "09:00", "bit": "17:00"}}, headers=baslik)
    assert yanit.json()["sessiz_saatler"] == {"bas": "09:00", "bit": "17:00"}
    await _abone_ol(istemci, baslik, _uc_nokta())
    monkeypatch.setattr(bt, "_yerel_saat", lambda: time(12, 0))

    await _dagit(db_oturumu, "project_stage", eposta)
    satirlar = await _satirlar(db_oturumu, eposta, "project_stage")
    assert satirlar["push"].delivery_status == "skipped"
    assert satirlar["push"].delivery_detail == "sessiz saatler"
    assert "email" in satirlar  # e-posta sessiz saatten etkilenmiyor
    assert sahte_push["cagrilar"] == []


# ---------------------------------------------------------------------------
# Web Push
# ---------------------------------------------------------------------------


async def test_push_anahtari(istemci, vapid):
    assert (await istemci.get(ANAHTAR)).json() == {"acik": True, "anahtar": vapid["acik"]}


async def test_push_anahtari_yokken_kapali(istemci):
    assert (await istemci.get(ANAHTAR)).json() == {"acik": False}


async def test_push_anahtar_yokken_skipped_ve_abonelik_409(istemci, musteri_basligi, db_oturumu):
    eposta = _eposta()
    await _abone_ol(istemci, musteri_basligi(eposta), _uc_nokta(), beklenen=409)
    await _dagit(db_oturumu, "kredi_azaldi", eposta)
    push = (await _satirlar(db_oturumu, eposta, "kredi_azaldi"))["push"]
    assert push.delivery_status == "skipped"
    assert "VAPID" in push.delivery_detail


async def test_push_abonelik_ekle_sil_yetkisi(istemci, musteri_basligi, db_oturumu, vapid):
    from models.bildirim import PushSubscriptions

    sahip, baska = _eposta("sahip"), _eposta("baska")
    uc = _uc_nokta()
    yanit = await _abone_ol(istemci, musteri_basligi(sahip), uc)
    assert yanit.json()["abonelik_sayisi"] == 1
    # Aynı endpoint ikinci kez: çoğalmıyor.
    assert (await _abone_ol(istemci, musteri_basligi(sahip), uc)).json()["abonelik_sayisi"] == 1

    kayit = (await db_oturumu.execute(select(PushSubscriptions).where(PushSubscriptions.endpoint == uc))).scalar_one()
    assert kayit.eposta == sahip and kayit.hata_sayisi == 0

    # Başkası silemez (404, varlığı da sızmıyor).
    yanit = await istemci.request("DELETE", ABONE, json={"endpoint": uc}, headers=musteri_basligi(baska))
    assert yanit.status_code == 404

    yanit = await istemci.request("DELETE", ABONE, json={"endpoint": uc}, headers=musteri_basligi(sahip))
    assert yanit.status_code == 200 and yanit.json()["abonelik_sayisi"] == 0

    # Sorgu parametresiyle de (DELETE gövdesi gönderemeyen istemci).
    await _abone_ol(istemci, musteri_basligi(sahip), uc)
    yanit = await istemci.delete(ABONE, params={"endpoint": uc}, headers=musteri_basligi(baska))
    assert yanit.status_code == 404
    yanit = await istemci.delete(ABONE, params={"endpoint": uc}, headers=musteri_basligi(sahip))
    assert yanit.status_code == 200 and yanit.json()["abonelik_sayisi"] == 0
    assert (await istemci.delete(ABONE, headers=musteri_basligi(sahip))).status_code == 400

    # Tercihlerde yapılandırma ve abonelik sayısı görünüyor.
    govde = (await istemci.get(TERCIH, headers=musteri_basligi(sahip))).json()
    assert govde["kanal_durumu"]["push"] == "hazir"
    assert govde["push"]["yapilandirildi"] is True and govde["push"]["anahtar"] == vapid["acik"]


async def test_push_abonelik_gecersiz_adres(istemci, musteri_basligi, vapid):
    baslik = musteri_basligi(_eposta())
    await _abone_ol(istemci, baslik, "http://ornek.com/push/abc", beklenen=400)
    yanit = await istemci.post(ABONE, json={"endpoint": _uc_nokta(), "keys": {"p256dh": "x", "auth": "y"}}, headers=baslik)
    assert yanit.status_code == 422


async def test_yonetici_yonetici_basligiyla_baskasinin_aboneligini_silemez(
    istemci, musteri_basligi, yonetici_basligi, vapid
):
    uc = _uc_nokta()
    await _abone_ol(istemci, musteri_basligi(_eposta()), uc)
    yanit = await istemci.request("DELETE", ABONE, json={"endpoint": uc}, headers=yonetici_basligi)
    assert yanit.status_code == 404


async def test_webpush_410_abonelik_siliniyor(istemci, musteri_basligi, db_oturumu, vapid, sahte_push):
    from models.bildirim import PushSubscriptions

    eposta = _eposta()
    baslik = musteri_basligi(eposta)
    olu, canli = _uc_nokta(), _uc_nokta()
    await _abone_ol(istemci, baslik, olu)
    await _abone_ol(istemci, baslik, canli)
    sahte_push["kodlar"][olu] = 410

    await _dagit(db_oturumu, "project_stage", eposta, baslik="Aşama değişti")
    push = (await _satirlar(db_oturumu, eposta, "project_stage"))["push"]
    assert push.delivery_status == "sent"
    assert "1/2" in push.delivery_detail and "silindi" in push.delivery_detail
    assert set(sahte_push["cagrilar"]) == {olu, canli}
    assert '"title": "Aşama değişti"' in sahte_push["veriler"][0] and '"url": "/client"' in sahte_push["veriler"][0]

    db_oturumu.expire_all()
    kalanlar = (await db_oturumu.execute(select(PushSubscriptions).where(PushSubscriptions.eposta == eposta))).scalars().all()
    assert [k.endpoint for k in kalanlar] == [canli]
    assert kalanlar[0].son_basari_at is not None


async def test_webpush_404_ve_hata_sayaci(istemci, musteri_basligi, db_oturumu, vapid, sahte_push):
    from models.bildirim import PushSubscriptions

    eposta = _eposta()
    baslik = musteri_basligi(eposta)
    bozuk, kayip = _uc_nokta(), _uc_nokta()
    await _abone_ol(istemci, baslik, bozuk)
    await _abone_ol(istemci, baslik, kayip)
    sahte_push["kodlar"].update({bozuk: 500, kayip: 404})

    await _dagit(db_oturumu, "kredi_yuklendi", eposta)
    push = (await _satirlar(db_oturumu, eposta, "kredi_yuklendi"))["push"]
    assert push.delivery_status == "failed"
    db_oturumu.expire_all()
    kalanlar = (await db_oturumu.execute(select(PushSubscriptions).where(PushSubscriptions.eposta == eposta))).scalars().all()
    assert [(k.endpoint, k.hata_sayisi) for k in kalanlar] == [(bozuk, 1)]


async def test_push_alici_basina_en_cok_bes(istemci, musteri_basligi, db_oturumu, vapid, sahte_push):
    eposta = _eposta()
    baslik = musteri_basligi(eposta)
    for _ in range(7):
        await _abone_ol(istemci, baslik, _uc_nokta())
    await _dagit(db_oturumu, "kredi_yuklendi", eposta)
    assert len(sahte_push["cagrilar"]) == 5


async def test_push_dene(istemci, musteri_basligi, vapid, sahte_push):
    eposta = _eposta()
    baslik = musteri_basligi(eposta)
    yanit = await istemci.post(DENE, headers=baslik)
    assert yanit.json()["durum"] == "skipped"  # henüz tarayıcı yok
    await _abone_ol(istemci, baslik, _uc_nokta())
    yanit = await istemci.post(DENE, headers=baslik)
    assert yanit.status_code == 200 and yanit.json()["durum"] == "sent"
    assert len(sahte_push["cagrilar"]) == 1


async def test_yonetici_matrisinde_push_durumu(istemci, yonetici_basligi, musteri_basligi, vapid):
    await _abone_ol(istemci, musteri_basligi(_eposta()), _uc_nokta())
    govde = (await istemci.get(MATRIS, headers=yonetici_basligi)).json()
    assert govde["push"]["yapilandirildi"] is True
    assert govde["push"]["abonelik_sayisi"] >= 1 and govde["push"]["kisi_sayisi"] >= 1
    assert govde["kanal_durumu"]["push"] == "hazir"


async def test_gercek_pywebpush_imzasi(monkeypatch, vapid):
    """Ağ yok, ama pywebpush gerçek anahtarla şifreleyip imzalayabiliyor mu?"""
    import requests

    from services import web_push

    yakalanan = {}

    class _Yanit:
        status_code = 201
        reason = "Created"
        text = ""
        headers: dict = {}

    def _post(self, url, data=None, headers=None, timeout=None, **_):
        yakalanan.update(url=url, headers=headers, timeout=timeout, boyut=len(data or b""))
        return _Yanit()

    monkeypatch.setattr(requests.Session, "post", _post, raising=True)
    monkeypatch.setattr(requests, "post", lambda url, **kw: _post(None, url, **kw))
    uc = _uc_nokta()
    kod = web_push._webpush_cagir(
        {"endpoint": uc, "keys": ABONELIK_ANAHTARLARI}, '{"title":"t"}', vapid["gizli"], "mailto:by@mehmetkuru.dev"
    )
    assert kod == 201
    assert yakalanan["url"] == uc
    assert yakalanan["headers"]["authorization"].startswith("vapid t=")
    assert yakalanan["timeout"] == web_push.ZAMAN_ASIMI


# ---------------------------------------------------------------------------
# Anahtar üretme betiği
# ---------------------------------------------------------------------------


def test_vapid_uret_dosyaya_yazar_ekrana_yazmaz(tmp_path, capsys):
    from py_vapid import Vapid

    betik = _vapid_script()
    hedef = tmp_path / "vapid.env"
    assert betik.main(["vapid_uret.py", str(hedef)]) == 0

    icerik = dict(
        satir.split("=", 1) for satir in hedef.read_text().splitlines() if satir and not satir.startswith("#")
    )
    assert set(icerik) == {"VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY", "VAPID_SUBJECT"}
    assert icerik["VAPID_SUBJECT"] == "mailto:by@mehmetkuru.dev"
    assert stat.S_IMODE(os.stat(hedef).st_mode) == 0o600

    cikti = capsys.readouterr()
    assert icerik["VAPID_PRIVATE_KEY"] not in cikti.out + cikti.err
    assert icerik["VAPID_PUBLIC_KEY"] not in cikti.out + cikti.err

    # Gizli anahtar pywebpush'un kullandığı biçimde okunabiliyor ve açıkla eşleşiyor.
    v = Vapid.from_string(icerik["VAPID_PRIVATE_KEY"])
    from cryptography.hazmat.primitives import serialization

    ham = v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    assert betik._b64(ham) == icerik["VAPID_PUBLIC_KEY"]

    # Var olan dosyanın üzerine yazmıyor.
    assert betik.main(["vapid_uret.py", str(hedef)]) == 1
    assert betik.main(["vapid_uret.py"]) == 2
