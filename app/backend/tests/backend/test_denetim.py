"""Denetim kaydı (audit log) testleri.

Test veritabanı oturum boyunca paylaşılıyor; her test kendi benzersiz
e-postası / fatura numarasıyla çalışıp yalnız kendi satırlarına bakıyor.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text


def _benzersiz(on: str = "t") -> str:
    return f"{on}-{uuid.uuid4().hex[:10]}"


@pytest.fixture
async def ilk_id(db_oturumu):
    """Testin başındaki en büyük denetim kimliği.

    SQLite silinen satırın kimliğini yeniden kullanabiliyor; önceki bir
    testte silinen fatura ile bu testin faturası aynı kimliği alabilir.
    Bu yüzden her test yalnız kendi başladıktan sonraki satırlara bakıyor.
    """
    from models.audit_log import AuditLog
    from sqlalchemy import func

    return (await db_oturumu.execute(select(func.max(AuditLog.id)))).scalar() or 0


async def _satirlar(db_oturumu, ilk_id, **kosul):
    from models.audit_log import AuditLog

    sorgu = select(AuditLog).where(AuditLog.id > ilk_id).order_by(AuditLog.id.asc())
    for alan, deger in kosul.items():
        sorgu = sorgu.where(getattr(AuditLog, alan) == deger)
    db_oturumu.expire_all()
    return list((await db_oturumu.execute(sorgu)).scalars().all())


async def _fatura_ac(istemci, baslik, **ek):
    govde = {"invoice_no": _benzersiz("INV"), "amount": 100.0, "client_email": "musteri@test.dev", "status": "draft"}
    govde.update(ek)
    yanit = await istemci.post("/api/v1/entities/invoices", json=govde, headers=baslik)
    assert yanit.status_code in (200, 201), yanit.text
    return yanit.json()


# ---------------------------------------------------------------------------
# Yetki
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("yol", ["/api/v1/denetim", "/api/v1/denetim/ozet", "/api/v1/denetim/tablolar"])
async def test_yonetici_uclari_anonime_401_musteriye_403(istemci, musteri_basligi, yol):
    assert (await istemci.get(yol)).status_code == 401
    assert (await istemci.get(yol, headers=musteri_basligi())).status_code == 403


async def test_benim_ucu_oturum_istiyor(istemci):
    assert (await istemci.get("/api/v1/denetim/benim")).status_code == 401


async def test_liste_siniri_200(istemci, yonetici_basligi):
    assert (await istemci.get("/api/v1/denetim?limit=201", headers=yonetici_basligi)).status_code == 422
    assert (await istemci.get("/api/v1/denetim?limit=200", headers=yonetici_basligi)).status_code == 200


# ---------------------------------------------------------------------------
# Oturum olayı: oluştur → güncelle → sil
# ---------------------------------------------------------------------------


async def test_entity_olustur_guncelle_sil_uc_satir_ve_dogru_fark(ilk_id, istemci, yonetici_basligi, db_oturumu):
    fatura = await _fatura_ac(istemci, yonetici_basligi, description="ilk")
    kimlik = str(fatura["id"])

    yanit = await istemci.put(
        f"/api/v1/entities/invoices/{kimlik}",
        json={"amount": 250.5, "description": "ikinci"},
        headers=yonetici_basligi,
    )
    assert yanit.status_code == 200, yanit.text
    yanit = await istemci.delete(f"/api/v1/entities/invoices/{kimlik}", headers=yonetici_basligi)
    assert yanit.status_code in (200, 204), yanit.text

    satirlar = await _satirlar(db_oturumu, ilk_id, tablo="invoices", kayit_id=kimlik)
    assert [s.islem for s in satirlar] == ["olustur", "guncelle", "sil"]
    for s in satirlar:
        assert s.aktor_eposta == "yonetici@test.dev"
        assert s.aktor_rol == "admin"
        assert s.ip_ozeti and len(s.ip_ozeti) == 64
        assert s.istek_yolu.endswith(f"/api/v1/entities/invoices" + ("" if s.islem == "olustur" else f"/{kimlik}"))
        assert s.ilgili_eposta == "musteri@test.dev"

    olustur, guncelle, sil = (json.loads(s.degisiklik_json) for s in satirlar)
    assert olustur["invoice_no"] == [None, fatura["invoice_no"]]
    assert olustur["amount"] == [None, 100.0]
    assert "id" not in olustur and "created_at" not in olustur

    # Yalnız değişen alanlar; eşit kalanlar (invoice_no, status…) yok.
    assert guncelle == {"amount": [100.0, 250.5], "description": ["ilk", "ikinci"]}
    etiket, alanlar = satirlar[1].ozet.split(" · ")
    assert etiket == fatura["invoice_no"] and set(alanlar.split(", ")) == {"amount", "description"}

    assert sil["amount"] == [250.5, None]
    assert sil["invoice_no"] == [fatura["invoice_no"], None]


async def test_degismeyen_guncelleme_satir_yazmaz(ilk_id, istemci, yonetici_basligi, db_oturumu):
    fatura = await _fatura_ac(istemci, yonetici_basligi, description="ayni")
    yanit = await istemci.put(
        f"/api/v1/entities/invoices/{fatura['id']}", json={"description": "ayni"}, headers=yonetici_basligi
    )
    assert yanit.status_code == 200
    satirlar = await _satirlar(db_oturumu, ilk_id, tablo="invoices", kayit_id=str(fatura["id"]))
    assert [s.islem for s in satirlar] == ["olustur"]


async def test_fatura_odendi_isareti_odeme_islemi(ilk_id, istemci, yonetici_basligi, db_oturumu):
    fatura = await _fatura_ac(istemci, yonetici_basligi)
    await istemci.put(f"/api/v1/entities/invoices/{fatura['id']}", json={"status": "paid"}, headers=yonetici_basligi)
    satirlar = await _satirlar(db_oturumu, ilk_id, tablo="invoices", kayit_id=str(fatura["id"]))
    assert [s.islem for s in satirlar] == ["olustur", "odeme"]


async def test_anonim_iletisim_formu_anonim_aktor(ilk_id, istemci, db_oturumu):
    eposta = f"{_benzersiz('ziyaretci')}@test.dev"
    yanit = await istemci.post(
        "/api/v1/entities/inquiries",
        json={"name": "Ziyaretçi", "email": eposta, "message": "Merhaba"},
    )
    assert yanit.status_code in (200, 201), yanit.text
    satirlar = await _satirlar(db_oturumu, ilk_id, tablo="inquiries", kayit_id=str(yanit.json()["id"]))
    assert len(satirlar) == 1
    assert satirlar[0].aktor_rol == "anonim"
    assert satirlar[0].aktor_eposta is None


async def test_gurultulu_tablolar_yazilmaz(ilk_id, db_oturumu):
    from models.notifications import Notifications

    db_oturumu.add(Notifications(recipient_email="x@test.dev", recipient_role="client", event_type="deneme", title="t"))
    await db_oturumu.commit()
    assert await _satirlar(db_oturumu, ilk_id, tablo="notifications") == []


# ---------------------------------------------------------------------------
# Hassas alanlar
# ---------------------------------------------------------------------------


async def test_hassas_alan_maskesi_orm(ilk_id, istemci, yonetici_basligi, db_oturumu):
    eposta = f"{_benzersiz('site')}@test.dev"
    yanit = await istemci.post(
        "/api/v1/musteri-sitesi",
        json={"client_email": eposta, "ad": "Deneme sitesi", "adres": "https://ornek.com"},
        headers=yonetici_basligi,
    )
    assert yanit.status_code in (200, 201), yanit.text
    site_id = yanit.json()["id"]
    satirlar = await _satirlar(db_oturumu, ilk_id, tablo="client_sites", kayit_id=str(site_id))
    assert satirlar and satirlar[0].islem == "olustur"
    fark = json.loads(satirlar[0].degisiklik_json)
    assert fark["widget_jetonu"] == [None, "***"]
    assert fark["ad"] == [None, "Deneme sitesi"]
    # Maskeli değer satırın hiçbir yerinde açık durmuyor.
    ham = satirlar[0].degisiklik_json + (satirlar[0].ozet or "")
    from models.client_sites import Client_sites

    site = (await db_oturumu.execute(select(Client_sites).where(Client_sites.id == site_id))).scalar_one()
    assert site.widget_jetonu and site.widget_jetonu not in ham


async def test_musteri_izni_onay_islemi(ilk_id, istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    eposta = f"{_benzersiz('izin')}@test.dev"
    yanit = await istemci.post(
        "/api/v1/musteri-sitesi", json={"client_email": eposta, "ad": "İzin sitesi"}, headers=yonetici_basligi
    )
    site_id = yanit.json()["id"]
    yanit = await istemci.post(
        f"/api/v1/sitelerim/{site_id}/izin", json={"izin": True}, headers=musteri_basligi(eposta)
    )
    assert yanit.status_code == 200, yanit.text
    satirlar = await _satirlar(db_oturumu, ilk_id, tablo="client_sites", kayit_id=str(site_id))
    assert satirlar[-1].islem == "onay"
    assert satirlar[-1].aktor_eposta == eposta
    assert satirlar[-1].aktor_rol == "client"
    assert json.loads(satirlar[-1].degisiklik_json)["bakim_izni"] == [False, True]


def test_fark_hesapla_maske_ve_kesme():
    from services.denetim import fark_hesapla

    fark = fark_hesapla(
        {"password": "eski", "api_key": "a", "not": "x" * 500, "ayni": 1, "kart_no": None},
        {"password": "yeni", "api_key": "a", "not": "kisa", "ayni": 1, "kart_no": "4111", "SIFRE": "s"},
    )
    assert fark["password"] == ["***", "***"]
    assert "api_key" not in fark  # değişmedi
    assert "ayni" not in fark
    assert fark["kart_no"] == [None, "***"]
    assert fark["SIFRE"] == [None, "***"]
    assert len(fark["not"][0]) == 200 and fark["not"][0].endswith("…")
    assert fark["not"][1] == "kisa"


async def test_ayarlar_elle_denetim_deger_maskeli(ilk_id, istemci, yonetici_basligi, db_oturumu, tmp_path, monkeypatch):
    import routers.settings as ayarlar

    monkeypatch.setattr(ayarlar, "get_env_file_path", lambda tur: tmp_path / f"{tur}.env")
    anahtar = f"DENEME_{uuid.uuid4().hex[:6].upper()}"
    yanit = await istemci.put(
        f"/api/v1/admin/settings/backend/{anahtar}", json={"value": "cok-gizli-deger"}, headers=yonetici_basligi
    )
    assert yanit.status_code == 200, yanit.text
    yanit = await istemci.put(
        f"/api/v1/admin/settings/backend/{anahtar}", json={"value": "ikinci-gizli"}, headers=yonetici_basligi
    )
    yanit = await istemci.delete(f"/api/v1/admin/settings/backend/{anahtar}", headers=yonetici_basligi)
    assert yanit.status_code == 200, yanit.text

    satirlar = await _satirlar(db_oturumu, ilk_id, tablo="ayarlar", kayit_id=f"backend:{anahtar}")
    assert [s.islem for s in satirlar] == ["olustur", "guncelle", "sil"]
    assert json.loads(satirlar[0].degisiklik_json) == {"deger": [None, "***"]}
    assert json.loads(satirlar[1].degisiklik_json) == {"deger": ["***", "***"]}
    assert json.loads(satirlar[2].degisiklik_json) == {"deger": ["***", None]}
    assert all(s.aktor_eposta == "yonetici@test.dev" and s.aktor_rol == "admin" for s in satirlar)
    for s in satirlar:
        assert "gizli" not in (s.degisiklik_json + (s.ozet or ""))


# ---------------------------------------------------------------------------
# Denetim hatası asıl işlemi bozmuyor
# ---------------------------------------------------------------------------


async def test_denetim_yazimi_patlarsa_asil_islem_surer(ilk_id, istemci, yonetici_basligi, db_oturumu, monkeypatch):
    import services.denetim as denetim

    # Veritabanı düzeyinde hata: var olmayan tabloya INSERT (SAVEPOINT geri alınmalı).
    monkeypatch.setattr(denetim, "_ekleme_sorgusu", lambda: text("INSERT INTO olmayan_denetim_tablosu (x) VALUES (:x)"))
    fatura = await _fatura_ac(istemci, yonetici_basligi, description="patlamali")
    yanit = await istemci.put(
        f"/api/v1/entities/invoices/{fatura['id']}", json={"amount": 5.0}, headers=yonetici_basligi
    )
    assert yanit.status_code == 200, yanit.text
    assert yanit.json()["amount"] == 5.0

    monkeypatch.undo()
    oku = await istemci.get(f"/api/v1/entities/invoices/{fatura['id']}", headers=yonetici_basligi)
    assert oku.status_code == 200 and oku.json()["amount"] == 5.0
    assert await _satirlar(db_oturumu, ilk_id, tablo="invoices", kayit_id=str(fatura["id"])) == []


async def test_fark_cikarimi_patlarsa_asil_islem_surer(ilk_id, istemci, yonetici_basligi, db_oturumu, monkeypatch):
    import services.denetim as denetim

    def patla(*_a, **_k):
        raise RuntimeError("bilerek")

    monkeypatch.setattr(denetim, "_nesne_satiri", patla)
    fatura = await _fatura_ac(istemci, yonetici_basligi)
    monkeypatch.undo()
    oku = await istemci.get(f"/api/v1/entities/invoices/{fatura['id']}", headers=yonetici_basligi)
    assert oku.status_code == 200
    assert await _satirlar(db_oturumu, ilk_id, tablo="invoices", kayit_id=str(fatura["id"])) == []


async def test_asil_islem_geri_alinirsa_denetim_satiri_da_gider(ilk_id, db_oturumu):
    from models.invoices import Invoices

    no = _benzersiz("GERI")
    db_oturumu.add(Invoices(invoice_no=no, amount=1.0))
    await db_oturumu.flush()
    # flush sonrası denetim satırı aynı işlemde yazıldı…
    assert len(await _satirlar(db_oturumu, ilk_id, tablo="invoices", ozet=no)) == 1
    await db_oturumu.rollback()
    # …işlem geri alınınca o da gitti.
    assert await _satirlar(db_oturumu, ilk_id, tablo="invoices", ozet=no) == []


async def test_denetim_yaz_hata_firlatmaz(db_oturumu, monkeypatch):
    import services.denetim as denetim

    monkeypatch.setattr(denetim, "_ekleme_sorgusu", lambda: text("INSERT INTO yok_boyle_tablo (x) VALUES (:x)"))
    sonuc = await denetim.denetim_yaz(db_oturumu, aktor="a@test.dev", islem="diger", tablo="deneme", commit=True)
    assert sonuc is False


# ---------------------------------------------------------------------------
# Filtreler, özet, saklama
# ---------------------------------------------------------------------------


async def _elle_satir(db_oturumu, **alanlar):
    from models.audit_log import AuditLog

    varsayilan = {"aktor_rol": "admin", "islem": "diger", "tablo": "deneme_tablosu"}
    varsayilan.update(alanlar)
    satir = AuditLog(**varsayilan)
    db_oturumu.add(satir)
    await db_oturumu.commit()
    return satir


async def test_filtreler(istemci, yonetici_basligi, db_oturumu):
    etiket = _benzersiz("filtre")
    tablo = f"tbl_{etiket}"
    simdi = datetime.now(timezone.utc)
    await _elle_satir(db_oturumu, tablo=tablo, aktor_eposta=f"ayse.{etiket}@ornek.com", islem="olustur", kayit_id="1")
    await _elle_satir(db_oturumu, tablo=tablo, aktor_eposta=f"ali.{etiket}@ornek.com", islem="guncelle", kayit_id="2")
    await _elle_satir(
        db_oturumu, tablo=tablo, aktor_eposta=f"ali.{etiket}@ornek.com", islem="sil", kayit_id="2",
        created_at=simdi - timedelta(days=10),
    )

    async def al(**p):
        yanit = await istemci.get("/api/v1/denetim", params={"tablo": tablo, **p}, headers=yonetici_basligi)
        assert yanit.status_code == 200, yanit.text
        return yanit.json()

    hepsi = await al()
    assert hepsi["total"] == 3
    # En yeniden eskiye
    assert [s["islem"] for s in hepsi["items"]] == ["guncelle", "olustur", "sil"]

    assert (await al(aktor=f"ALI.{etiket}"))["total"] == 2  # içerir, büyük/küçük harf duyarsız
    assert (await al(islem="olustur"))["total"] == 1
    assert (await al(kayit_id="2"))["total"] == 2
    bugun = simdi.date().isoformat()
    assert (await al(baslangic=bugun))["total"] == 2
    on_gun_once = (simdi - timedelta(days=10)).date().isoformat()
    assert (await al(bitis=on_gun_once))["total"] == 1
    assert (await al(baslangic=on_gun_once, bitis=on_gun_once))["total"] == 1

    sayfa = await al(limit=1, skip=1)
    assert sayfa["total"] == 3 and len(sayfa["items"]) == 1 and sayfa["items"][0]["islem"] == "olustur"

    secenekler = (await istemci.get("/api/v1/denetim/tablolar", headers=yonetici_basligi)).json()
    assert tablo in secenekler["tablolar"]
    assert "odeme" in secenekler["islemler"] and "anonim" in secenekler["roller"]


async def test_ozet_son_7_gun(istemci, yonetici_basligi, db_oturumu):
    etiket = _benzersiz("ozet")
    tablo = f"tbl_{etiket}"
    await _elle_satir(db_oturumu, tablo=tablo, aktor_eposta=f"{etiket}@ornek.com")
    await _elle_satir(db_oturumu, tablo=tablo, aktor_eposta=f"{etiket}@ornek.com")
    await _elle_satir(
        db_oturumu, tablo=tablo, aktor_eposta=f"{etiket}@ornek.com",
        created_at=datetime.now(timezone.utc) - timedelta(days=8),
    )
    yanit = await istemci.get("/api/v1/denetim/ozet", headers=yonetici_basligi)
    assert yanit.status_code == 200
    veri = yanit.json()
    assert veri["gun"] == 7 and veri["toplam"] >= 2
    # İlk 10'a girmeyebilir; ama girdiyse sayısı 2 olmalı (8 günlük satır sayılmaz).
    for s in veri["tablolar"]:
        if s["ad"] == tablo:
            assert s["sayi"] == 2


async def test_saklama_temizligi_gunde_bir(ilk_id, istemci, yonetici_basligi, db_oturumu):
    import routers.denetim as denetim_router
    from models.audit_log import AuditLog

    tablo = f"tbl_{_benzersiz('saklama')}"
    eski = datetime.now(timezone.utc) - timedelta(days=400)
    yeni_sayilir = datetime.now(timezone.utc) - timedelta(days=300)
    await _elle_satir(db_oturumu, tablo=tablo, created_at=eski, kayit_id="eski")
    await _elle_satir(db_oturumu, tablo=tablo, created_at=yeni_sayilir, kayit_id="kalir")

    denetim_router._son_temizlik_gunu = None
    assert (await istemci.get("/api/v1/denetim", headers=yonetici_basligi)).status_code == 200
    kalanlar = await _satirlar(db_oturumu, ilk_id, tablo=tablo)
    assert [s.kayit_id for s in kalanlar] == ["kalir"]

    # Aynı gün ikinci liste isteği yeniden silmiyor.
    await _elle_satir(db_oturumu, tablo=tablo, created_at=eski, kayit_id="eski2")
    await istemci.get("/api/v1/denetim", headers=yonetici_basligi)
    assert sorted(s.kayit_id for s in await _satirlar(db_oturumu, ilk_id, tablo=tablo)) == ["eski2", "kalir"]

    # Ertesi gün (simülasyon) yine siliyor.
    denetim_router._son_temizlik_gunu = None
    await istemci.get("/api/v1/denetim", headers=yonetici_basligi)
    assert [s.kayit_id for s in await _satirlar(db_oturumu, ilk_id, tablo=tablo)] == ["kalir"]
    assert AuditLog  # modül yüklü


# ---------------------------------------------------------------------------
# Müşteri: /benim
# ---------------------------------------------------------------------------


async def test_benim_yalniz_kendi_hareketleri_ve_fark_yok(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    ben = f"{_benzersiz('ben')}@test.dev"
    baskasi = f"{_benzersiz('baska')}@test.dev"

    # Yönetici benim faturamı açıyor ve güncelliyor → benim listemde (kendisi=False).
    fatura = await _fatura_ac(istemci, yonetici_basligi, client_email=ben)
    await istemci.put(f"/api/v1/entities/invoices/{fatura['id']}", json={"amount": 7.0}, headers=yonetici_basligi)
    # Başkasının faturası → görünmemeli.
    diger = await _fatura_ac(istemci, yonetici_basligi, client_email=baskasi)
    # Kendim bir destek talebi açıyorum → kendisi=True.
    yanit = await istemci.post(
        "/api/v1/entities/support_tickets",
        json={"subject": "Yardım", "message": "Bir sorun var", "client_email": ben},
        headers=musteri_basligi(ben),
    )
    assert yanit.status_code in (200, 201), yanit.text

    yanit = await istemci.get("/api/v1/denetim/benim", headers=musteri_basligi(ben))
    assert yanit.status_code == 200
    satirlar = yanit.json()
    assert len(satirlar) == 3
    for s in satirlar:
        assert "degisiklik" not in s and "degisiklik_json" not in s
        assert "ip_ozeti" not in s and "aktor_eposta" not in s and "istek_yolu" not in s
    faturalar = [s for s in satirlar if s["tablo"] == "invoices"]
    assert {s["kayit_id"] for s in faturalar} == {str(fatura["id"])}
    assert all(s["kendisi"] is False and s["aktor_rol"] == "admin" for s in faturalar)
    talep = [s for s in satirlar if s["tablo"] == "support_tickets"]
    assert len(talep) == 1 and talep[0]["kendisi"] is True and talep[0]["islem"] == "olustur"
    assert str(diger["id"]) not in {s["kayit_id"] for s in satirlar if s["tablo"] == "invoices"}

    # Sorgu parametresiyle başkasının e-postası verilemez (yok sayılır).
    yanit = await istemci.get(f"/api/v1/denetim/benim?eposta={baskasi}", headers=musteri_basligi(ben))
    assert len(yanit.json()) == 3


async def test_giris_islemi_kullanicinin_kendisi(ilk_id, db_oturumu, istemci, musteri_basligi):
    from services.auth import AuthService

    eposta = f"{_benzersiz('giris')}@test.dev"
    kimlik = _benzersiz("sub")
    servis = AuthService(db_oturumu)
    await servis.get_or_create_user(kimlik, eposta, "Deneme")  # ilk kez: olustur
    await servis.get_or_create_user(kimlik, eposta, "Deneme")  # tekrar: giris
    satirlar = await _satirlar(db_oturumu, ilk_id, tablo="users", kayit_id=kimlik)
    assert [s.islem for s in satirlar] == ["olustur", "giris"]
    assert satirlar[1].aktor_eposta == eposta and satirlar[1].aktor_rol == "client"
    assert set(json.loads(satirlar[1].degisiklik_json)) == {"last_login"}

    hareketler = (await istemci.get("/api/v1/denetim/benim", headers=musteri_basligi(eposta))).json()
    assert [h["islem"] for h in hareketler][:1] == ["giris"]


async def test_liste_farki_json_olarak_doner(istemci, yonetici_basligi):
    fatura = await _fatura_ac(istemci, yonetici_basligi, description="a")
    await istemci.put(f"/api/v1/entities/invoices/{fatura['id']}", json={"description": "b"}, headers=yonetici_basligi)
    yanit = await istemci.get(
        "/api/v1/denetim", params={"tablo": "invoices", "kayit_id": str(fatura["id"])}, headers=yonetici_basligi
    )
    veri = yanit.json()
    # (SQLite silinmiş bir faturanın kimliğini yeniden verebilir; en yeni ikisi bizim.)
    assert veri["total"] >= 2
    assert [s["islem"] for s in veri["items"][:2]] == ["guncelle", "olustur"]
    assert veri["items"][0]["degisiklik"] == {"description": ["a", "b"]}
    assert veri["items"][0]["aktor_eposta"] == "yonetici@test.dev"
    assert len(veri["items"][0]["ip_ozeti"]) == 12


def test_webhook_istegi_sistem_aktoru():
    from services.denetim import DenetimBaglami
    from starlette.requests import Request

    def istek(yol, basliklar=()):
        return Request({"type": "http", "method": "POST", "path": yol, "headers": list(basliklar),
                        "query_string": b"", "client": ("9.9.9.9", 1), "server": ("test", 80), "scheme": "http"})

    b = DenetimBaglami(istek("/api/v1/odeme/shopier/webhook")).coz()
    assert b.aktor_rol == "sistem" and b.aktor_eposta is None
    assert b.istek_yolu == "POST /api/v1/odeme/shopier/webhook" and len(b.ip_ozeti) == 64
    assert DenetimBaglami(istek("/api/v1/entities/inquiries")).coz().aktor_rol == "anonim"


def test_islem_inceltme_kurallari():
    from services.denetim import _islem_belirle

    assert _islem_belirle("payments", "guncelle", {"durum": ["bekliyor", "odendi"]}) == "odeme"
    assert _islem_belirle("payments", "guncelle", {"durum": ["odendi", "iade"]}) == "guncelle"
    assert _islem_belirle("invoices", "guncelle", {"status": ["sent", "paid"]}) == "odeme"
    assert _islem_belirle("client_sites", "guncelle", {"bakim_izni": [True, False]}) == "onay"
    assert _islem_belirle("users", "guncelle", {"last_login": [None, "x"], "name": ["a", "b"]}) == "giris"
    assert _islem_belirle("users", "guncelle", {"role": ["user", "admin"], "last_login": [1, 2]}) == "guncelle"


async def test_denetim_kapali_oturum_yazmaz(ilk_id, db_oturumu):
    """Açılış tohumu gibi toplu işler oturumu işaretleyip kaydı kapatabiliyor."""
    from core.database import db_manager
    from models.invoices import Invoices

    no = _benzersiz("TOHUM")
    async with db_manager.async_session_maker() as oturum:
        oturum.info["denetim_kapali"] = True
        oturum.add(Invoices(invoice_no=no, amount=1.0))
        await oturum.commit()
    assert await _satirlar(db_oturumu, ilk_id, tablo="invoices", ozet=no) == []
