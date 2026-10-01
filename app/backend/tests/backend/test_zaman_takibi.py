"""Faz 3Z — zaman takibi + proje şablonları.

Kapsam: yetki (401/403, personel yalnız kendi kaydı), tek açık sayaç (servis +
kısmi benzersiz indeks), unutulan sayaç (12 saat), onay kilidi, ret notu,
Faz 2B aynası (görev saati + revizyon sayacı), faturaya aktarım (gruplama,
taslak fatura, çift faturalama — servis + veritabanı), fatura iptal/silmede
kilidin açılması, taslağın müşteriden gizlenmesi, CSV, çizelge, iş yükü,
müşterinin harcanan süre özeti (ayar + sahiplik + modül), proje şablonları
(tohum, tarih ofsetleri, projeden şablon, teklif kabulünde şablon görevleri).
"""

import csv
import io
import json
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

Z = "/api/v1/zaman"
ZY = "/api/v1/zaman/yonetim"
ZM = "/api/v1/zamanim"
S = "/api/v1/proje-sablonlari"


def _eposta(on: str = "zaman") -> str:
    return f"{on}-{uuid.uuid4().hex[:10]}@test.dev"


async def _proje(db, eposta=None, **ek):
    from models.projects import Projects

    alanlar = dict(title=f"Proje {uuid.uuid4().hex[:6]}", description="d", category="Website",
                   client_email=eposta or _eposta("musteri"), client_name="Müşteri", stage="build",
                   status="in_progress", progress=40)
    alanlar.update(ek)
    kayit = Projects(**alanlar)
    db.add(kayit)
    await db.commit()
    await db.refresh(kayit)
    return kayit


async def _personel(istemci, yonetici_basligi, eposta=None, **ek):
    eposta = eposta or _eposta("personel")
    y = await istemci.post("/api/v1/ekip", json={"ad": ek.get("ad", "Ekip Üyesi"), "email": eposta,
                                                  "rol": ek.get("rol", "calisan"), "hizmetler": ek.get("hizmetler")},
                           headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    return eposta


async def _gorev(istemci, basliklar, proje_id, **govde):
    govde.setdefault("baslik", f"Görev {uuid.uuid4().hex[:4]}")
    y = await istemci.post(f"/api/v1/gorevler/proje/{proje_id}", json=govde, headers=basliklar)
    assert y.status_code == 200, y.text
    return y.json()


async def _kayit(istemci, basliklar, proje_id, beklenen=200, **govde):
    veri = {"proje_id": proje_id, "tarih": date.today().isoformat(), "saat": "10:00", "sure_dk": 90,
            "aciklama": "Geliştirme", **govde}
    y = await istemci.post(f"{Z}/kayitlar", json=veri, headers=basliklar)
    assert y.status_code == beklenen, y.text
    return y.json()


async def _onayla(istemci, yonetici_basligi, idler, islem="onayla", not_=None):
    y = await istemci.post(f"{ZY}/onay", json={"idler": idler, "islem": islem, "not": not_}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    return y.json()


async def _modul_ac(istemci, yonetici_basligi, eposta, anahtar="zaman_takibi", acik=True):
    y = await istemci.put(f"/api/v1/moduller/musteri/{eposta}/{anahtar}", json={"acik": acik}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text


# ---------------------------------------------------------------------------
# Yetki
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "metot,yol",
    [
        ("GET", f"{Z}/secenekler"),
        ("GET", f"{Z}/sayac"),
        ("POST", f"{Z}/sayac/baslat"),
        ("POST", f"{Z}/sayac/durdur"),
        ("GET", f"{Z}/kayitlar"),
        ("POST", f"{Z}/kayitlar"),
        ("PATCH", f"{Z}/kayitlar/1"),
        ("DELETE", f"{Z}/kayitlar/1"),
        ("GET", f"{Z}/cizelge"),
    ],
)
async def test_personel_uclari_anonime_401_personel_olmayana_403(istemci, musteri_basligi, metot, yol):
    govde = {} if metot in ("POST", "PATCH") else None
    assert (await istemci.request(metot, yol, json=govde)).status_code == 401
    y = await istemci.request(metot, yol, json=govde, headers=musteri_basligi(_eposta("yabanci")))
    assert y.status_code == 403 and y.json()["detail"]["kod"] == "personel_degil"


@pytest.mark.parametrize(
    "metot,yol",
    [
        ("POST", f"{ZY}/onay"),
        ("POST", f"{ZY}/kayitlar/1/onay-geri-al"),
        ("GET", f"{ZY}/is-yuku"),
        ("GET", f"{ZY}/faturalanabilir?proje_id=1"),
        ("POST", f"{ZY}/faturaya-aktar"),
        ("GET", f"{ZY}/disa-aktar.csv"),
        ("GET", f"{ZY}/proje/1/ayar"),
        ("PUT", f"{ZY}/proje/1/ayar"),
        ("GET", f"{ZY}/ayarlar"),
        ("PUT", f"{ZY}/ayarlar"),
        ("GET", S),
        ("POST", S),
        ("POST", f"{S}/1/proje-olustur"),
        ("POST", f"{S}/projeden/1"),
        ("DELETE", f"{S}/1"),
    ],
)
async def test_yonetici_uclari_anonime_401_personele_403(istemci, yonetici_basligi, musteri_basligi, metot, yol):
    personel = await _personel(istemci, yonetici_basligi)
    govde = {} if metot in ("POST", "PUT", "PATCH") else None
    assert (await istemci.request(metot, yol, json=govde)).status_code == 401
    assert (await istemci.request(metot, yol, json=govde, headers=musteri_basligi(personel))).status_code == 403


async def test_ben_ucu_kimligi_soyler(istemci, yonetici_basligi, musteri_basligi):
    assert (await istemci.get(f"{Z}/ben")).status_code == 401
    musteri = (await istemci.get(f"{Z}/ben", headers=musteri_basligi(_eposta()))).json()
    assert musteri["personel"] is False and musteri["yonetici"] is False
    personel = await _personel(istemci, yonetici_basligi, ad="Ayşe Çalışkan")
    p = (await istemci.get(f"{Z}/ben", headers=musteri_basligi(personel))).json()
    assert p["personel"] is True and p["yonetici"] is False and p["ad"] == "Ayşe Çalışkan"
    y = (await istemci.get(f"{Z}/ben", headers=yonetici_basligi)).json()
    assert y["personel"] is True and y["yonetici"] is True


async def test_pasif_personel_403(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    from models.staff import Staff

    personel = await _personel(istemci, yonetici_basligi)
    await db_oturumu.execute(update(Staff).where(Staff.email == personel).values(aktif=False))
    await db_oturumu.commit()
    assert (await istemci.get(f"{Z}/kayitlar", headers=musteri_basligi(personel))).status_code == 403


async def test_personel_yalniz_kendi_kaydini_gorur_ve_yonetir(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    a = await _personel(istemci, yonetici_basligi)
    b = await _personel(istemci, yonetici_basligi)
    proje = await _proje(db_oturumu)
    ka = await _kayit(istemci, musteri_basligi(a), proje.id)
    kb = await _kayit(istemci, musteri_basligi(b), proje.id, aciklama="B'nin işi")
    assert ka["kisi_eposta"] == a and ka["durum"] == "taslak" and ka["sure_dk"] == 90

    liste = (await istemci.get(f"{Z}/kayitlar", headers=musteri_basligi(a))).json()["kayitlar"]
    assert {k["id"] for k in liste} >= {ka["id"]} and kb["id"] not in {k["id"] for k in liste}
    # ?kisi= ile başkasını isteyemez (yok sayılır).
    liste = (await istemci.get(f"{Z}/kayitlar?kisi={b}", headers=musteri_basligi(a))).json()["kayitlar"]
    assert all(k["kisi_eposta"] == a for k in liste)
    # Başkasının kaydı: yok (404).
    assert (await istemci.patch(f"{Z}/kayitlar/{kb['id']}", json={"aciklama": "x"}, headers=musteri_basligi(a))).status_code == 404
    assert (await istemci.delete(f"{Z}/kayitlar/{kb['id']}", headers=musteri_basligi(a))).status_code == 404
    # Başkası adına kayıt açamaz.
    y = await istemci.post(f"{Z}/kayitlar", json={"proje_id": proje.id, "tarih": date.today().isoformat(), "sure_dk": 30,
                                                   "kisi_eposta": b}, headers=musteri_basligi(a))
    assert y.status_code == 403 and y.json()["detail"]["kod"] == "baskasi_adina"
    # Onaylayamaz.
    assert (await istemci.post(f"{ZY}/onay", json={"idler": [ka["id"]], "islem": "onayla"},
                               headers=musteri_basligi(a))).status_code == 403
    # Yönetici ikisini de görür; başkası adına kayıt girebilir.
    hepsi = (await istemci.get(f"{Z}/kayitlar?proje_id={proje.id}", headers=yonetici_basligi)).json()["kayitlar"]
    assert {ka["id"], kb["id"]} <= {k["id"] for k in hepsi}
    kc = await _kayit(istemci, yonetici_basligi, proje.id, kisi_eposta=a, sure_dk=15)
    assert kc["kisi_eposta"] == a
    # Kendi kaydını düzenler/siler (taslak).
    y = await istemci.patch(f"{Z}/kayitlar/{ka['id']}", json={"sure_dk": 120, "aciklama": "Düzeltildi"}, headers=musteri_basligi(a))
    assert y.status_code == 200 and y.json()["sure_dk"] == 120
    assert (await istemci.delete(f"{Z}/kayitlar/{ka['id']}", headers=musteri_basligi(a))).status_code == 200


async def test_kayit_dogrulamalari(istemci, yonetici_basligi, db_oturumu):
    proje = await _proje(db_oturumu)
    baska = await _proje(db_oturumu)
    g = await _gorev(istemci, yonetici_basligi, baska.id)
    for govde, kod in [
        ({"sure_dk": 0}, "sure_gecersiz"),
        ({"sure_dk": 24 * 60 + 1}, "sure_gecersiz"),
        ({"gorev_id": g["id"]}, "gorev_gecersiz"),
        ({"tur": "bilinmez"}, "tur_gecersiz"),
        ({"tarih": "2026-13-40"}, "tarih_gecersiz"),
        ({"tarih": (date.today() + timedelta(days=5)).isoformat()}, "gelecek_tarih"),
    ]:
        y = await istemci.post(f"{Z}/kayitlar", json={"proje_id": proje.id, "tarih": date.today().isoformat(), "sure_dk": 30, **govde},
                               headers=yonetici_basligi)
        assert y.status_code == 400 and y.json()["detail"]["kod"] == kod, (govde, y.text)
    y = await istemci.post(f"{Z}/kayitlar", json={"proje_id": 99999999, "sure_dk": 30, "tarih": date.today().isoformat()},
                           headers=yonetici_basligi)
    assert y.status_code == 404
    # bitis ile süre hesaplanır; Türkiye saatiyle gün.
    y = await istemci.post(f"{Z}/kayitlar", json={"proje_id": proje.id, "baslangic": "2026-03-02T23:30:00+03:00",
                                                   "bitis": "2026-03-03T01:00:00+03:00"}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["sure_dk"] == 90 and y.json()["gun"] == "2026-03-02"


# ---------------------------------------------------------------------------
# Sayaç
# ---------------------------------------------------------------------------
async def test_tek_acik_sayac_yenisi_oncekini_durdurur(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    from models.zaman_takibi import ZamanKayitlari

    personel = await _personel(istemci, yonetici_basligi)
    b = musteri_basligi(personel)
    p1 = await _proje(db_oturumu)
    p2 = await _proje(db_oturumu)
    assert (await istemci.get(f"{Z}/sayac", headers=b)).json()["sayac"] is None
    y = await istemci.post(f"{Z}/sayac/baslat", json={"proje_id": p1.id, "aciklama": "İlk iş"}, headers=b)
    assert y.status_code == 200, y.text
    ilk = y.json()["sayac"]
    assert ilk["calisiyor"] is True and ilk["bitis"] is None and y.json()["durdurulan"] is None
    # Sayfa kapansa da: durum sunucuda.
    assert (await istemci.get(f"{Z}/sayac", headers=b)).json()["sayac"]["id"] == ilk["id"]
    y = await istemci.post(f"{Z}/sayac/baslat", json={"proje_id": p2.id}, headers=b)
    assert y.status_code == 200
    ikinci = y.json()["sayac"]
    assert y.json()["durdurulan"]["id"] == ilk["id"] and y.json()["durdurulan"]["calisiyor"] is False
    assert y.json()["durdurulan"]["sure_dk"] >= 1
    acik = (await db_oturumu.execute(
        select(ZamanKayitlari).where(ZamanKayitlari.kisi_eposta == personel, ZamanKayitlari.bitis.is_(None))
    )).scalars().all()
    assert [k.id for k in acik] == [ikinci["id"]]
    # Çalışan sayacın süresi elle değişmez.
    y = await istemci.patch(f"{Z}/kayitlar/{ikinci['id']}", json={"sure_dk": 30}, headers=b)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "sayac_calisiyor"
    y = await istemci.post(f"{Z}/sayac/durdur", json={"aciklama": "Bitti"}, headers=b)
    assert y.status_code == 200 and y.json()["kayit"]["calisiyor"] is False and y.json()["kayit"]["aciklama"] == "Bitti"
    assert (await istemci.post(f"{Z}/sayac/durdur", json={}, headers=b)).status_code == 404


async def test_acik_sayac_veritabaninda_tekil(istemci, yonetici_basligi, db_oturumu):
    """Kısmi benzersiz indeks: servis atlansa bile aynı kişiye iki açık sayaç yazılamaz."""
    from models.zaman_takibi import ZamanKayitlari
    from sqlalchemy.exc import IntegrityError

    pid = (await _proje(db_oturumu)).id
    kisi = _eposta("dbsayac")
    an = datetime.now(timezone.utc)
    db_oturumu.add(ZamanKayitlari(proje_id=pid, kisi_eposta=kisi, baslangic=an, durum="taslak", tur="normal", faturalanabilir=True))
    await db_oturumu.commit()
    db_oturumu.add(ZamanKayitlari(proje_id=pid, kisi_eposta=kisi, baslangic=an, durum="taslak", tur="normal", faturalanabilir=True))
    with pytest.raises(IntegrityError):
        await db_oturumu.commit()
    await db_oturumu.rollback()
    # Durmuş kayıtlar sınırsız.
    for _ in range(2):
        db_oturumu.add(ZamanKayitlari(proje_id=pid, kisi_eposta=kisi, baslangic=an, bitis=an + timedelta(minutes=5),
                                      sure_dk=5, durum="taslak", tur="normal", faturalanabilir=True))
    await db_oturumu.commit()


async def test_unutulan_sayac_uyari_ve_duzeltme(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    from models.zaman_takibi import ZamanKayitlari

    personel = await _personel(istemci, yonetici_basligi)
    b = musteri_basligi(personel)
    proje = await _proje(db_oturumu)
    k = (await istemci.post(f"{Z}/sayac/baslat", json={"proje_id": proje.id}, headers=b)).json()["sayac"]
    await db_oturumu.execute(update(ZamanKayitlari).where(ZamanKayitlari.id == k["id"])
                             .values(baslangic=datetime.now(timezone.utc) - timedelta(hours=13)))
    await db_oturumu.commit()
    durum = (await istemci.get(f"{Z}/sayac", headers=b)).json()["sayac"]
    assert durum["uzun"] is True and durum["gecen_dk"] >= 13 * 60
    y = await istemci.post(f"{Z}/sayac/durdur", json={}, headers=b)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "uzun_sayac" and y.json()["detail"]["gecen_dk"] >= 780
    # Yeni sayaç da unutulmuşu sessizce kapatmaz.
    y = await istemci.post(f"{Z}/sayac/baslat", json={"proje_id": proje.id}, headers=b)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "uzun_sayac"
    # Geçen süreden uzun ya da 24 saatten uzun süre verilemez.
    y = await istemci.post(f"{Z}/sayac/durdur", json={"sure_dk": 14 * 60}, headers=b)
    assert y.status_code == 400
    y = await istemci.post(f"{Z}/sayac/durdur", json={"sure_dk": 150}, headers=b)
    assert y.status_code == 200
    kayit = y.json()["kayit"]
    assert kayit["sure_dk"] == 150 and kayit["calisiyor"] is False
    bas = datetime.fromisoformat(kayit["baslangic"])
    bit = datetime.fromisoformat(kayit["bitis"])
    assert (bit - bas) == timedelta(minutes=150)


# ---------------------------------------------------------------------------
# Onay kilidi + Faz 2B aynası
# ---------------------------------------------------------------------------
async def test_onay_kilidi_ret_ve_geri_alma(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    personel = await _personel(istemci, yonetici_basligi)
    b = musteri_basligi(personel)
    proje = await _proje(db_oturumu)
    k1 = await _kayit(istemci, b, proje.id)
    k2 = await _kayit(istemci, b, proje.id, sure_dk=30)
    calisan = (await istemci.post(f"{Z}/sayac/baslat", json={"proje_id": proje.id}, headers=b)).json()["sayac"]
    sonuc = await _onayla(istemci, yonetici_basligi, [k1["id"], calisan["id"], 99999999])
    assert sonuc["islenen"] == [k1["id"]] and set(sonuc["atlanan"]) == {calisan["id"], 99999999}
    # Kilitli: personel de yönetici de düzenleyemez/silemez.
    for basliklar in (b, yonetici_basligi):
        y = await istemci.patch(f"{Z}/kayitlar/{k1['id']}", json={"aciklama": "değiş"}, headers=basliklar)
        assert y.status_code == 409 and y.json()["detail"]["kod"] == "kayit_kilitli"
        assert (await istemci.delete(f"{Z}/kayitlar/{k1['id']}", headers=basliklar)).status_code == 409
    # Ret notu zorunlu.
    y = await istemci.post(f"{ZY}/onay", json={"idler": [k2["id"]], "islem": "reddet"}, headers=yonetici_basligi)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "ret_notu_gerekli"
    await _onayla(istemci, yonetici_basligi, [k2["id"]], "reddet", "Süre fazla görünüyor")
    liste = (await istemci.get(f"{Z}/kayitlar?durum=reddedildi", headers=b)).json()["kayitlar"]
    red = next(k for k in liste if k["id"] == k2["id"])
    assert red["ret_notu"] == "Süre fazla görünüyor" and red["kilitli"] is False
    # Düzeltilen ret yeniden onaya düşer.
    y = await istemci.patch(f"{Z}/kayitlar/{k2['id']}", json={"sure_dk": 20}, headers=b)
    assert y.json()["durum"] == "taslak" and y.json()["ret_notu"] is None
    # Onayı geri al → taslak, yeniden düzenlenebilir.
    y = await istemci.post(f"{ZY}/kayitlar/{k1['id']}/onay-geri-al", headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["durum"] == "taslak"
    assert (await istemci.patch(f"{Z}/kayitlar/{k1['id']}", json={"aciklama": "ok"}, headers=b)).status_code == 200


async def test_onay_gorev_saatine_ve_revizyon_sayacina_yansir(istemci, yonetici_basligi, db_oturumu):
    from models.proje_gorevleri import TaskTimeEntries

    musteri = _eposta("revmusteri")
    proje = await _proje(db_oturumu, musteri)
    gorev = await _gorev(istemci, yonetici_basligi, proje.id, etiketler=["revizyon"])
    normal = await _gorev(istemci, yonetici_basligi, proje.id)
    # Revizyon etiketli görevde tür kendiliğinden revizyon.
    k1 = await _kayit(istemci, yonetici_basligi, proje.id, gorev_id=gorev["id"], sure_dk=90)
    assert k1["tur"] == "revizyon"
    k2 = await _kayit(istemci, yonetici_basligi, proje.id, gorev_id=normal["id"], sure_dk=60)
    k3 = await _kayit(istemci, yonetici_basligi, proje.id, sure_dk=30, tur="revizyon")  # görevsiz revizyon
    once = (await istemci.get(f"/api/v1/gorevler/proje/{proje.id}", headers=yonetici_basligi)).json()["revizyon"]
    await _onayla(istemci, yonetici_basligi, [k1["id"], k2["id"], k3["id"]])
    yanit = (await istemci.get(f"/api/v1/gorevler/proje/{proje.id}", headers=yonetici_basligi)).json()
    gorevler = {g["id"]: g for g in yanit["gorevler"]}
    assert gorevler[gorev["id"]]["harcanan_saat"] == 1.5 and gorevler[normal["id"]]["harcanan_saat"] == 1.0
    # 1.5 (görevli revizyon) + 0.5 (görevsiz revizyon); normal görev sayılmaz.
    assert round(yanit["revizyon"]["kullanilan"] - once["kullanilan"], 2) == 2.0
    girisler = (await db_oturumu.execute(select(TaskTimeEntries).where(TaskTimeEntries.proje_id == proje.id))).scalars().all()
    assert sorted((g.saat, g.revizyon) for g in girisler) == [(1.0, False), (1.5, True)]
    # Ayna giriş görev ekranından silinemez; onayı geri almak siler.
    ayna = next(g for g in girisler if g.revizyon)
    y = await istemci.delete(f"/api/v1/gorevler/saat/{ayna.id}", headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "zaman_kaydindan"
    await istemci.post(f"{ZY}/kayitlar/{k1['id']}/onay-geri-al", headers=yonetici_basligi)
    yanit = (await istemci.get(f"/api/v1/gorevler/proje/{proje.id}", headers=yonetici_basligi)).json()
    assert {g["id"]: g for g in yanit["gorevler"]}[gorev["id"]]["harcanan_saat"] == 0.0
    assert round(yanit["revizyon"]["kullanilan"] - once["kullanilan"], 2) == 0.5


# ---------------------------------------------------------------------------
# Faturaya aktarım
# ---------------------------------------------------------------------------
async def _faturali_proje(istemci, yonetici_basligi, db, ucret=1000.0, para="TRY"):
    musteri = _eposta("faturamusteri")
    proje = await _proje(db, musteri)
    y = await istemci.put(f"{ZY}/proje/{proje.id}/ayar", json={"saatlik_ucret": ucret, "ucret_para_birimi": para},
                          headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["etkin_ucret"] == ucret and y.json()["ucret_kaynagi"] == "proje"
    return musteri, proje


async def test_faturaya_aktar_gruplu_ve_cift_faturalama_engeli(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    from models.invoices import Invoices
    from models.zaman_takibi import ZamanFaturaBaglari, ZamanKayitlari

    a = await _personel(istemci, yonetici_basligi, ad="Ali")
    b = await _personel(istemci, yonetici_basligi, ad="Banu")
    musteri, proje = await _faturali_proje(istemci, yonetici_basligi, db_oturumu)
    g = await _gorev(istemci, yonetici_basligi, proje.id, baslik="Ana sayfa")
    ka = await _kayit(istemci, musteri_basligi(a), proje.id, sure_dk=90, gorev_id=g["id"])
    kb = await _kayit(istemci, musteri_basligi(b), proje.id, sure_dk=30)
    kc = await _kayit(istemci, musteri_basligi(b), proje.id, sure_dk=60, faturalanabilir=False)
    kd = await _kayit(istemci, musteri_basligi(b), proje.id, sure_dk=45)  # taslak kalacak
    assert ka["saatlik_ucret"] == 1000.0 and ka["para_birimi"] == "TRY" and ka["tutar"] == 1500.0
    await _onayla(istemci, yonetici_basligi, [ka["id"], kb["id"], kc["id"]])

    ozet = (await istemci.get(f"{ZY}/faturalanabilir?proje_id={proje.id}", headers=yonetici_basligi)).json()
    assert {k["id"] for k in ozet["kayitlar"]} == {ka["id"], kb["id"]} and ozet["toplam_dk"] == 120
    # Uygun olmayan seçim (faturalanamaz / taslak) reddedilir.
    for idler in ([kc["id"]], [kd["id"]]):
        y = await istemci.post(f"{ZY}/faturaya-aktar", json={"proje_id": proje.id, "idler": idler}, headers=yonetici_basligi)
        assert y.status_code == 409 and y.json()["detail"]["kod"] == "uygun_degil", y.text

    y = await istemci.post(f"{ZY}/faturaya-aktar", json={"proje_id": proje.id, "idler": [ka["id"], kb["id"]],
                                                         "gruplama": "kisi", "kdv_orani": 20}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    sonuc = y.json()
    assert sonuc["yeni_fatura"] is True and sonuc["durum"] == "draft" and sonuc["kalem_sayisi"] == 2
    fatura = (await db_oturumu.execute(select(Invoices).where(Invoices.id == sonuc["fatura_id"]))).scalar_one()
    kalemler = json.loads(fatura.kalemler)
    assert fatura.client_email == musteri and fatura.currency == "TRY" and fatura.status == "draft"
    # Ali 1.5 sa × 1000 = 1500; Banu 0.5 sa × 1000 = 500 → 2000 + %20 = 2400
    assert sorted((k["adet"], k["birim_fiyat"]) for k in kalemler) == [(0.5, 1000.0), (1.5, 1000.0)]
    assert any("Ali" in k["aciklama"] for k in kalemler) and fatura.amount == 2400.0
    for kid in (ka["id"], kb["id"]):
        k = (await db_oturumu.execute(select(ZamanKayitlari).where(ZamanKayitlari.id == kid))).scalar_one()
        await db_oturumu.refresh(k)
        assert k.durum == "faturalandi" and k.fatura_id == fatura.id

    # 1) Servis: aynı kayıt ikinci kez → 409, fatura değişmez.
    y = await istemci.post(f"{ZY}/faturaya-aktar", json={"proje_id": proje.id, "idler": [ka["id"]]}, headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "zaten_faturalandi"
    await db_oturumu.refresh(fatura)
    assert fatura.amount == 2400.0
    # 2) Veritabanı: bağ tablosunda aynı kayıt ikinci kez yazılamaz.
    from sqlalchemy.exc import IntegrityError

    pid, fid = proje.id, fatura.id
    db_oturumu.add(ZamanFaturaBaglari(zaman_kaydi_id=ka["id"], fatura_id=fid))
    with pytest.raises(IntegrityError):
        await db_oturumu.commit()
    await db_oturumu.rollback()
    # 3) Koşullu UPDATE: kayıt servis denetiminden sonra başka işlemde faturalanmış gibi.
    kayit_e = await _kayit(istemci, yonetici_basligi, pid, sure_dk=15)
    await _onayla(istemci, yonetici_basligi, [kayit_e["id"]])
    from services import zaman_takibi as zs

    asil = zs._uygun_mu
    zs._uygun_mu = lambda k: True  # servis denetimi "atlatıldı"
    try:
        await db_oturumu.execute(update(ZamanKayitlari).where(ZamanKayitlari.id == kayit_e["id"]).values(fatura_id=fid))
        await db_oturumu.commit()
        y = await istemci.post(f"{ZY}/faturaya-aktar", json={"proje_id": pid, "idler": [kayit_e["id"]]}, headers=yonetici_basligi)
        assert y.status_code == 409 and y.json()["detail"]["kod"] == "zaten_faturalandi"
    finally:
        zs._uygun_mu = asil
    await db_oturumu.execute(update(ZamanKayitlari).where(ZamanKayitlari.id == kayit_e["id"]).values(fatura_id=None))
    await db_oturumu.commit()

    # Yeni onaylı kayıt aynı TASLAK faturaya eklenir (tek satır).
    y = await istemci.post(f"{ZY}/faturaya-aktar", json={"proje_id": pid, "gruplama": "tek"}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    assert y.json()["fatura_id"] == fid and y.json()["yeni_fatura"] is False and y.json()["kayitlar"] == [kayit_e["id"]]
    fatura = (await db_oturumu.execute(select(Invoices).where(Invoices.id == fid))).scalar_one()
    await db_oturumu.refresh(fatura)
    assert len(json.loads(fatura.kalemler)) == 3 and fatura.amount == 2700.0
    # Hepsi faturalandı → aktarılacak kayıt yok.
    y = await istemci.post(f"{ZY}/faturaya-aktar", json={"proje_id": pid}, headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "kayit_yok"


async def test_faturaya_aktar_ucret_ve_para_birimi(istemci, yonetici_basligi, db_oturumu):
    musteri = _eposta("ucretsiz")
    proje = await _proje(db_oturumu, musteri)
    # Ne proje ne site ücreti: kayıt ücretsiz → aktarımda 409 ucret_yok, varsayılan ücretle geçer.
    await istemci.put(f"{ZY}/ayarlar", json={"saatlik_ucret": None, "para_birimi": "TRY"}, headers=yonetici_basligi)
    k = await _kayit(istemci, yonetici_basligi, proje.id, sure_dk=120)
    assert k["saatlik_ucret"] is None
    await _onayla(istemci, yonetici_basligi, [k["id"]])
    y = await istemci.post(f"{ZY}/faturaya-aktar", json={"proje_id": proje.id}, headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "ucret_yok"
    y = await istemci.post(f"{ZY}/faturaya-aktar", json={"proje_id": proje.id, "varsayilan_ucret": 750, "kdv_orani": 0,
                                                         "gruplama": "gorev"}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["tutar"] == 1500.0
    # Site ayarı: yeni kayıt ücreti oradan sabitlenir; sonra değişse de eski kayıt değişmez.
    y = await istemci.put(f"{ZY}/ayarlar", json={"saatlik_ucret": 500, "para_birimi": "USD"}, headers=yonetici_basligi)
    assert y.json() == {"saatlik_ucret": 500.0, "para_birimi": "USD"}
    k2 = await _kayit(istemci, yonetici_basligi, proje.id, sure_dk=60)
    assert k2["saatlik_ucret"] == 500.0 and k2["para_birimi"] == "USD"
    await istemci.put(f"{ZY}/proje/{proje.id}/ayar", json={"saatlik_ucret": 40, "ucret_para_birimi": "EUR"}, headers=yonetici_basligi)
    k3 = await _kayit(istemci, yonetici_basligi, proje.id, sure_dk=60)
    assert k3["saatlik_ucret"] == 40.0 and k3["para_birimi"] == "EUR"
    liste = (await istemci.get(f"{Z}/kayitlar?proje_id={proje.id}", headers=yonetici_basligi)).json()["kayitlar"]
    assert next(x for x in liste if x["id"] == k2["id"])["saatlik_ucret"] == 500.0
    await _onayla(istemci, yonetici_basligi, [k2["id"], k3["id"]])
    y = await istemci.post(f"{ZY}/faturaya-aktar", json={"proje_id": proje.id}, headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "para_birimi_karisik"
    # Para birimi başına ayrı taslak.
    y = await istemci.post(f"{ZY}/faturaya-aktar", json={"proje_id": proje.id, "idler": [k3["id"]]}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["para_birimi"] == "EUR" and y.json()["yeni_fatura"] is True
    await istemci.put(f"{ZY}/ayarlar", json={"saatlik_ucret": None, "para_birimi": "TRY"}, headers=yonetici_basligi)


async def test_fatura_iptal_ve_silmede_kilit_acilir(istemci, yonetici_basligi, db_oturumu):
    from models.zaman_takibi import ZamanFaturaBaglari, ZamanKayitlari

    _, proje = await _faturali_proje(istemci, yonetici_basligi, db_oturumu, ucret=100)
    k1 = await _kayit(istemci, yonetici_basligi, proje.id, sure_dk=60)
    k2 = await _kayit(istemci, yonetici_basligi, proje.id, sure_dk=30)
    await _onayla(istemci, yonetici_basligi, [k1["id"], k2["id"]])
    f1 = (await istemci.post(f"{ZY}/faturaya-aktar", json={"proje_id": proje.id, "idler": [k1["id"]]}, headers=yonetici_basligi)).json()

    async def durum(kid):
        k = (await db_oturumu.execute(select(ZamanKayitlari).where(ZamanKayitlari.id == kid))).scalar_one()
        await db_oturumu.refresh(k)
        return k.durum, k.fatura_id

    assert await durum(k1["id"]) == ("faturalandi", f1["fatura_id"])
    # Faturalanmış kaydın onayı geri alınamaz.
    y = await istemci.post(f"{ZY}/kayitlar/{k1['id']}/onay-geri-al", headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "kayit_faturalandi"
    # İptal (entity ucu) → kilit açılır, bağ silinir, kayıt yeniden faturalanabilir.
    y = await istemci.put(f"/api/v1/entities/invoices/{f1['fatura_id']}", json={"status": "cancelled"}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    assert await durum(k1["id"]) == ("onaylandi", None)
    assert (await db_oturumu.execute(select(ZamanFaturaBaglari).where(ZamanFaturaBaglari.zaman_kaydi_id == k1["id"]))).first() is None
    # İptal edilen fatura taslak değil: yeni aktarım yeni taslak açar.
    f2 = (await istemci.post(f"{ZY}/faturaya-aktar", json={"proje_id": proje.id}, headers=yonetici_basligi)).json()
    assert f2["fatura_id"] != f1["fatura_id"] and set(f2["kayitlar"]) == {k1["id"], k2["id"]}
    # Silme → kilit açılır (çöp kutusu yolu dahil).
    y = await istemci.delete(f"/api/v1/entities/invoices/{f2['fatura_id']}", headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    assert await durum(k1["id"]) == ("onaylandi", None) and await durum(k2["id"]) == ("onaylandi", None)
    assert (await db_oturumu.execute(select(ZamanFaturaBaglari).where(ZamanFaturaBaglari.fatura_id == f2["fatura_id"]))).first() is None


async def test_taslak_fatura_musteriden_gizli(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    musteri, proje = await _faturali_proje(istemci, yonetici_basligi, db_oturumu, ucret=200)
    k = await _kayit(istemci, yonetici_basligi, proje.id, sure_dk=60)
    await _onayla(istemci, yonetici_basligi, [k["id"]])
    f = (await istemci.post(f"{ZY}/faturaya-aktar", json={"proje_id": proje.id}, headers=yonetici_basligi)).json()
    mb = musteri_basligi(musteri)
    assert all(x["id"] != f["fatura_id"] for x in (await istemci.get("/api/v1/faturalarim", headers=mb)).json()["faturalar"])
    assert (await istemci.get(f"/api/v1/faturalarim/{f['fatura_id']}", headers=mb)).status_code == 404
    ogeler = (await istemci.get("/api/v1/entities/invoices?limit=200", headers=mb)).json()["items"]
    assert all(x["id"] != f["fatura_id"] for x in ogeler)
    assert (await istemci.get(f"/api/v1/entities/invoices/{f['fatura_id']}", headers=mb)).status_code == 404
    # Yönetici görür; taslağa ödeme bağlantısı açılmaz.
    assert (await istemci.get(f"/api/v1/entities/invoices/{f['fatura_id']}", headers=yonetici_basligi)).status_code == 200
    y = await istemci.post(f"/api/v1/fatura-yonetim/{f['fatura_id']}/odeme-baglantisi", headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "fatura_taslak"
    # Kesilince (unpaid) müşteri görür.
    await istemci.put(f"/api/v1/entities/invoices/{f['fatura_id']}", json={"status": "unpaid"}, headers=yonetici_basligi)
    assert any(x["id"] == f["fatura_id"] for x in (await istemci.get("/api/v1/faturalarim", headers=mb)).json()["faturalar"])


# ---------------------------------------------------------------------------
# Çizelge, iş yükü, CSV
# ---------------------------------------------------------------------------
async def test_cizelge_ve_is_yuku(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    personel = await _personel(istemci, yonetici_basligi, ad="Çizelge Kişisi")
    b = musteri_basligi(personel)
    proje = await _proje(db_oturumu)
    pazartesi = date.today() - timedelta(days=date.today().weekday())
    await _kayit(istemci, b, proje.id, tarih=pazartesi.isoformat(), sure_dk=60)
    await _kayit(istemci, b, proje.id, tarih=pazartesi.isoformat(), sure_dk=30)
    red = await _kayit(istemci, b, proje.id, tarih=pazartesi.isoformat(), sure_dk=500)
    await _onayla(istemci, yonetici_basligi, [red["id"]], "reddet", "yanlış")
    await _kayit(istemci, b, proje.id, tarih=(pazartesi - timedelta(days=3)).isoformat(), sure_dk=45)
    g = await _gorev(istemci, yonetici_basligi, proje.id, atanan=personel, bitis_tarihi=(date.today() - timedelta(days=2)).isoformat())
    await _gorev(istemci, yonetici_basligi, proje.id, atanan=personel)

    c = (await istemci.get(f"{Z}/cizelge", headers=b)).json()
    assert c["hafta_baslangic"] == pazartesi.isoformat() and len(c["gunler"]) == 7
    satir = next(s for s in c["kisiler"] if s["eposta"] == personel)
    assert satir["gunler"][0] == 90 and satir["toplam_dk"] == 90 and satir["taslak_dk"] == 90
    assert all(s["eposta"] == personel for s in c["kisiler"])  # personel yalnız kendini görür
    gecen = (await istemci.get(f"{Z}/cizelge?hafta={(pazartesi - timedelta(days=3)).isoformat()}", headers=b)).json()
    assert next(s for s in gecen["kisiler"] if s["eposta"] == personel)["toplam_dk"] == 45

    yuk = (await istemci.get(f"{ZY}/is-yuku", headers=yonetici_basligi)).json()
    s = next(k for k in yuk["kisiler"] if k["eposta"] == personel)
    assert s["ad"] == "Çizelge Kişisi" and s["bu_hafta_dk"] == 90 and s["gecen_hafta_dk"] == 45
    assert s["acik_gorev"] == 2 and s["geciken_gorev"] == 1
    assert yuk["en_cok_dk"] >= 90
    await istemci.patch(f"/api/v1/gorevler/{g['id']}", json={"durum": "tamam"}, headers=yonetici_basligi)
    s = next(k for k in (await istemci.get(f"{ZY}/is-yuku", headers=yonetici_basligi)).json()["kisiler"] if k["eposta"] == personel)
    assert s["acik_gorev"] == 1 and s["geciken_gorev"] == 0


async def test_csv_disa_aktarim(istemci, yonetici_basligi, db_oturumu):
    _, proje = await _faturali_proje(istemci, yonetici_basligi, db_oturumu, ucret=300)
    diger = await _proje(db_oturumu)
    await _kayit(istemci, yonetici_basligi, proje.id, tarih="2026-02-10", sure_dk=90, aciklama="=HYPERLINK(\"x\")")
    await _kayit(istemci, yonetici_basligi, proje.id, tarih="2026-02-20", sure_dk=30, aciklama="Şükrü'nün işi")
    await _kayit(istemci, yonetici_basligi, diger.id, tarih="2026-02-10", sure_dk=15)
    y = await istemci.get(f"{ZY}/disa-aktar.csv?baslangic=2026-02-01&bitis=2026-02-15&proje_id={proje.id}", headers=yonetici_basligi)
    assert y.status_code == 200 and y.headers["content-type"].startswith("text/csv")
    assert "attachment" in y.headers["content-disposition"]
    metin = y.content.decode("utf-8")
    assert metin.startswith("﻿")
    satirlar = list(csv.reader(io.StringIO(metin.lstrip("﻿"))))
    assert satirlar[0][:6] == ["id", "tarih", "baslangic", "bitis", "sure_dk", "saat"]
    assert len(satirlar) == 2
    veri = dict(zip(satirlar[0], satirlar[1]))
    assert veri["tarih"] == "2026-02-10" and veri["sure_dk"] == "90" and veri["saat"] == "1.50"
    assert veri["tutar"] == "450.00" and veri["proje"] == proje.title
    assert veri["aciklama"].startswith("'=")  # formül olarak çalışmaz
    hepsi = list(csv.reader(io.StringIO((await istemci.get(f"{ZY}/disa-aktar.csv?proje_id={proje.id}", headers=yonetici_basligi)).content.decode().lstrip("﻿"))))
    assert len(hepsi) == 3 and any("Şükrü" in h for s in hepsi for h in s)
    y = await istemci.get(f"{ZY}/disa-aktar.csv?baslangic=2026-03-01&bitis=2026-02-01", headers=yonetici_basligi)
    assert y.status_code == 400


# ---------------------------------------------------------------------------
# Müşteri görünümü
# ---------------------------------------------------------------------------
async def test_musteri_yalniz_kendi_projesinin_suresini_ayar_aciksa_gorur(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    musteri = _eposta("suremusteri")
    baska = _eposta("baskamusteri")
    proje = await _proje(db_oturumu, musteri)
    baska_proje = await _proje(db_oturumu, baska)
    for e in (musteri, baska):
        await _modul_ac(istemci, yonetici_basligi, e)
    k1 = await _kayit(istemci, yonetici_basligi, proje.id, sure_dk=90)
    await _kayit(istemci, yonetici_basligi, proje.id, sure_dk=60, faturalanabilir=False)
    await _kayit(istemci, yonetici_basligi, proje.id, sure_dk=600)  # taslak: müşteri görmez
    liste = (await istemci.get(f"{Z}/kayitlar?proje_id={proje.id}&durum=taslak", headers=yonetici_basligi)).json()["kayitlar"]
    await _onayla(istemci, yonetici_basligi, [x["id"] for x in liste if x["sure_dk"] in (90, 60)])
    mb = musteri_basligi(musteri)
    assert (await istemci.get(f"{ZM}/proje/{proje.id}")).status_code == 401
    # Ayar kapalı: hiç görmez.
    y = await istemci.get(f"{ZM}/proje/{proje.id}", headers=mb)
    assert y.status_code == 404 and y.json()["detail"]["kod"] == "gizli"
    await istemci.put(f"{ZY}/proje/{proje.id}/ayar", json={"sure_musteriye_gorunur": True}, headers=yonetici_basligi)
    y = await istemci.get(f"{ZM}/proje/{proje.id}", headers=mb)
    assert y.status_code == 200, y.text
    ozet = y.json()
    assert ozet["toplam_dk"] == 150 and ozet["toplam_saat"] == 2.5 and "faturalanabilir_dk" not in ozet
    assert "kisi_eposta" not in json.dumps(ozet) and "ucret" not in json.dumps(ozet)
    await istemci.put(f"{ZY}/proje/{proje.id}/ayar", json={"faturalanabilir_musteriye_gorunur": True}, headers=yonetici_basligi)
    ozet = (await istemci.get(f"{ZM}/proje/{proje.id}", headers=mb)).json()
    assert ozet["faturalanabilir_dk"] == 90 and ozet["faturalanabilir_saat"] == 1.5
    # Başkasının projesi: yok (açık olsa bile).
    await istemci.put(f"{ZY}/proje/{baska_proje.id}/ayar", json={"sure_musteriye_gorunur": True}, headers=yonetici_basligi)
    assert (await istemci.get(f"{ZM}/proje/{baska_proje.id}", headers=mb)).status_code == 404
    assert (await istemci.get(f"{ZM}/proje/{proje.id}", headers=musteri_basligi(baska))).status_code == 404
    # Modül kapalı → 403 modul_kapali.
    await _modul_ac(istemci, yonetici_basligi, musteri, acik=False)
    y = await istemci.get(f"{ZM}/proje/{proje.id}", headers=mb)
    assert y.status_code == 403 and y.json()["detail"]["kod"] == "modul_kapali"
    assert k1["id"]


async def test_modul_kaydi():
    from core import moduller as mf

    z = mf.modul("zaman_takibi")
    s = mf.modul("proje_sablonlari")
    assert z and z.yonetici_sekmesi == "zaman" and not z.varsayilan_acik and z.paketler == ("BETA", "OMEGA", "SIGMA")
    assert s and s.yonetici_sekmesi == "projeSablonlari" and s.varsayilan_acik and z.musteriye_gorunur and s.musteriye_gorunur


# ---------------------------------------------------------------------------
# Proje şablonları
# ---------------------------------------------------------------------------
async def test_hazir_sablonlar_tohumlanir(istemci, yonetici_basligi):
    y = await istemci.get(S, headers=yonetici_basligi)
    assert y.status_code == 200
    adlar = {s["ad"]: s for s in y.json()["sablonlar"]}
    for ad in ("Kurumsal web sitesi", "SEO bakım (aylık)", "E-ticaret kurulumu"):
        assert ad in adlar and adlar[ad]["hazir"] and adlar[ad]["gorev_sayisi"] >= 5 and adlar[ad]["tahmini_saat"]
    # İkinci listeleme yeniden yazmaz.
    tekrar = (await istemci.get(S, headers=yonetici_basligi)).json()["sablonlar"]
    assert sum(1 for s in tekrar if s["ad"] == "Kurumsal web sitesi") == 1


async def test_sablondan_proje_tarih_ofsetleri_ve_atama(istemci, yonetici_basligi, db_oturumu):
    from models.proje_gorevleri import ProjectTasks, TaskChecklist

    seo = await _personel(istemci, yonetici_basligi, ad="SEO Uzmanı", hizmetler="seo,google_ads")
    sabit = await _personel(istemci, yonetici_basligi, ad="Tasarımcı")
    y = await istemci.post(S, json={
        "ad": "Deneme şablonu", "aciklama": "Ofset testi", "kategori": "Website",
        "gorevler": [
            {"baslik": "Keşif", "asama": "Keşif", "baslangic_gun": 0, "sure_gun": 2, "kontrol_listesi": ["Brief", "Rakipler"],
             "musteriye_gorunur": True, "tahmini_saat": 3},
            {"baslik": "Tasarım", "baslangic_gun": 3, "sure_gun": 2, "atanan_eposta": sabit, "tahmini_saat": 5},
            {"baslik": "SEO", "baslangic_gun": 10, "sure_gun": 1, "atanan_rol": "seo", "kilometre_tasi": True},
            {"baslik": "Kimsesiz", "baslangic_gun": 1, "atanan_eposta": "yok@test.dev", "atanan_rol": "bilinmeyen"},
        ],
    }, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    sablon = y.json()
    assert sablon["tahmini_saat"] == 8.0 and sablon["toplam_gun"] == 11 and sablon["gorevler"][3]["sure_gun"] == 1
    musteri = _eposta("sablonmusteri")
    y = await istemci.post(f"{S}/{sablon['id']}/proje-olustur", json={"baslangic_tarihi": "2026-10-05", "baslik": "Yeni site",
                                                                       "client_email": musteri.upper()}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    sonuc = y.json()
    assert sonuc["gorev_sayisi"] == 4 and sonuc["proje"]["client_email"] == musteri
    gorevler = {g.baslik: g for g in (await db_oturumu.execute(
        select(ProjectTasks).where(ProjectTasks.proje_id == sonuc["proje"]["id"]))).scalars().all()}
    assert (gorevler["Keşif"].baslangic_tarihi, gorevler["Keşif"].bitis_tarihi) == (date(2026, 10, 5), date(2026, 10, 6))
    assert (gorevler["Tasarım"].baslangic_tarihi, gorevler["Tasarım"].bitis_tarihi) == (date(2026, 10, 8), date(2026, 10, 9))
    assert (gorevler["SEO"].baslangic_tarihi, gorevler["SEO"].bitis_tarihi) == (date(2026, 10, 15), date(2026, 10, 15))
    assert gorevler["Tasarım"].atanan == sabit and gorevler["SEO"].atanan == seo and gorevler["Kimsesiz"].atanan is None
    assert all(g.durum == "yapilacak" for g in gorevler.values())
    assert sorted(g.sira for g in gorevler.values()) == [0, 1, 2, 3]
    assert gorevler["Keşif"].musteriye_gorunur and json.loads(gorevler["Keşif"].etiketler) == ["keşif"]
    assert gorevler["SEO"].kilometre_tasi and gorevler["Tasarım"].tahmini_saat == 5
    maddeler = (await db_oturumu.execute(select(TaskChecklist).where(TaskChecklist.gorev_id == gorevler["Keşif"].id))).scalars().all()
    assert sorted(m.metin for m in maddeler) == ["Brief", "Rakipler"]
    # Kanban'da görünür (Faz 2B ucu).
    kanban = (await istemci.get(f"/api/v1/gorevler/proje/{sonuc['proje']['id']}", headers=yonetici_basligi)).json()
    assert len(kanban["gorevler"]) == 4 and kanban["gorevler"][0]["baslangic_tarihi"] == "2026-10-05"

    # Projeden şablon kaydet → göreli günler korunur.
    y = await istemci.post(f"{S}/projeden/{sonuc['proje']['id']}", json={"ad": "Kopya şablon"}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    kopya = {g["baslik"]: g for g in y.json()["gorevler"]}
    assert (kopya["Keşif"]["baslangic_gun"], kopya["Keşif"]["sure_gun"]) == (0, 2)
    assert (kopya["Tasarım"]["baslangic_gun"], kopya["Tasarım"]["sure_gun"]) == (3, 2)
    assert kopya["SEO"]["baslangic_gun"] == 10 and kopya["Keşif"]["kontrol_listesi"] == ["Brief", "Rakipler"]
    assert kopya["Keşif"]["asama"] == "keşif"
    # Mevcut projeye uygula: görevler sona eklenir.
    hedef = await _proje(db_oturumu)
    await _gorev(istemci, yonetici_basligi, hedef.id, baslik="Önceden var")
    y = await istemci.post(f"{S}/{sablon['id']}/uygula", json={"proje_id": hedef.id, "baslangic_tarihi": "2026-01-01"}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["gorev_sayisi"] == 4
    siralar = sorted(g.sira for g in (await db_oturumu.execute(select(ProjectTasks).where(ProjectTasks.proje_id == hedef.id))).scalars().all())
    assert siralar == [0, 1, 2, 3, 4]
    # Doğrulama.
    for govde, kod in [({"ad": ""}, "ad_gerekli"), ({"ad": "x", "gorevler": [{"baslik": ""}]}, "gorev_basligi_gerekli"),
                       ({"ad": "x", "gorevler": [{"baslik": "a", "sure_gun": 0}]}, "sure_gecersiz"),
                       ({"ad": "x", "gorevler": "nope"}, "gorevler_gecersiz")]:
        y = await istemci.post(S, json=govde, headers=yonetici_basligi)
        assert y.status_code == 400 and y.json()["detail"]["kod"] == kod, (govde, y.text)
    # Güncelle + sil (çöp kutusuna).
    y = await istemci.put(f"{S}/{sablon['id']}", json={"ad": "Yeni ad"}, headers=yonetici_basligi)
    assert y.json()["ad"] == "Yeni ad" and y.json()["gorev_sayisi"] == 4
    assert (await istemci.delete(f"{S}/{sablon['id']}", headers=yonetici_basligi)).status_code == 200
    assert (await istemci.get(f"{S}/{sablon['id']}", headers=yonetici_basligi)).status_code == 404
    from services.cop_kutusu import cop_kutusunda_mi

    assert await cop_kutusunda_mi(db_oturumu, "proje_sablonlari", sablon["id"])


async def test_teklif_kabulunde_sablon_gorevleri_olusur(istemci, yonetici_basligi, db_oturumu):
    from models.proje_gorevleri import ProjectTasks
    from routers import teklifler
    from services.zaman_takibi import bugun

    teklifler.hiz_siniri.temizle()
    sablon = (await istemci.post(S, json={"ad": "Teklif şablonu", "gorevler": [
        {"baslik": "Başlangıç toplantısı", "baslangic_gun": 0, "musteriye_gorunur": True},
        {"baslik": "Teslim", "baslangic_gun": 7, "sure_gun": 1, "kilometre_tasi": True},
    ]}, headers=yonetici_basligi)).json()
    musteri = _eposta("teklifsablon")
    y = await istemci.post("/api/v1/teklif-yonetim", json={
        "baslik": "Şablonlu teklif", "kalemler": [{"aciklama": "Site", "adet": 1, "birim_fiyat": 100, "kdv_orani": 20}],
        "para_birimi": "TRY", "aday_ad": "Ayşe", "aday_eposta": musteri, "otomatik_proje": True, "proje_sablon_id": sablon["id"],
    }, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    t = y.json()
    assert (await istemci.get(f"/api/v1/teklif-yonetim/{t['id']}", headers=yonetici_basligi)).json()["proje_sablon_id"] == sablon["id"]
    # Bilinmeyen şablon reddedilir.
    y = await istemci.put(f"/api/v1/teklif-yonetim/{t['id']}", json={"proje_sablon_id": 99999999}, headers=yonetici_basligi)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "proje_sablonu_yok"
    g = (await istemci.post(f"/api/v1/teklif-yonetim/{t['id']}/gonder", json={}, headers=yonetici_basligi)).json()
    jeton = g["baglanti"].rsplit("/", 1)[1]
    y = await istemci.post(f"/api/v1/teklif/{jeton}/karar", json={"sonuc": "kabul", "ad_soyad": "Ayşe Yılmaz"})
    assert y.status_code == 200, y.text
    yon = (await istemci.get(f"/api/v1/teklif-yonetim/{t['id']}", headers=yonetici_basligi)).json()
    assert yon["proje_id"]
    gorevler = {g.baslik: g for g in (await db_oturumu.execute(
        select(ProjectTasks).where(ProjectTasks.proje_id == yon["proje_id"]))).scalars().all()}
    assert set(gorevler) == {"Başlangıç toplantısı", "Teslim"}
    assert gorevler["Başlangıç toplantısı"].bitis_tarihi == bugun()
    assert gorevler["Teslim"].bitis_tarihi == bugun() + timedelta(days=7)


async def test_teklif_revizyonu_sablonu_tasir(istemci, yonetici_basligi):
    from routers import teklifler

    teklifler.hiz_siniri.temizle()
    sablon = (await istemci.post(S, json={"ad": "Revize şablon", "gorevler": [{"baslik": "a"}]}, headers=yonetici_basligi)).json()
    t = (await istemci.post("/api/v1/teklif-yonetim", json={
        "baslik": "Revize", "kalemler": [{"aciklama": "x", "adet": 1, "birim_fiyat": 10}], "aday_eposta": _eposta("rev"),
        "otomatik_proje": True, "proje_sablon_id": sablon["id"]}, headers=yonetici_basligi)).json()
    await istemci.post(f"/api/v1/teklif-yonetim/{t['id']}/gonder", json={}, headers=yonetici_basligi)
    y = await istemci.post(f"/api/v1/teklif-yonetim/{t['id']}/revize", headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    yeni = y.json()
    yeni_id = yeni.get("id") or yeni.get("teklif", {}).get("id")
    assert (await istemci.get(f"/api/v1/teklif-yonetim/{yeni_id}", headers=yonetici_basligi)).json()["proje_sablon_id"] == sablon["id"]


async def test_zaman_kaydi_silinince_cop_kutusuna_duser(istemci, yonetici_basligi, db_oturumu):
    from services.cop_kutusu import cop_kutusunda_mi

    proje = await _proje(db_oturumu)
    k = await _kayit(istemci, yonetici_basligi, proje.id)
    assert (await istemci.delete(f"{Z}/kayitlar/{k['id']}", headers=yonetici_basligi)).status_code == 200
    assert await cop_kutusunda_mi(db_oturumu, "zaman_kayitlari", k["id"])


async def test_tam_iade_ile_iptal_edilen_faturada_kilit_acilir(istemci, yonetici_basligi, db_oturumu):
    """Faz 3T iade akışı: net borç sıfırlanınca fatura `cancelled` olur → kayıtlar yeniden faturalanabilir."""
    from models.zaman_takibi import ZamanKayitlari

    _, proje = await _faturali_proje(istemci, yonetici_basligi, db_oturumu, ucret=250)
    pid = proje.id
    k = await _kayit(istemci, yonetici_basligi, pid, sure_dk=120)
    await _onayla(istemci, yonetici_basligi, [k["id"]])
    f = (await istemci.post(f"{ZY}/faturaya-aktar", json={"proje_id": pid, "kdv_orani": 0}, headers=yonetici_basligi)).json()
    # Taslak kesilir (unpaid), sonra tam iade.
    await istemci.put(f"/api/v1/entities/invoices/{f['fatura_id']}", json={"status": "unpaid"}, headers=yonetici_basligi)
    y = await istemci.post(f"/api/v1/fatura-yonetim/{f['fatura_id']}/iade", json={"neden": "İş iptal"}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    assert y.json()["fatura"]["status"] == "cancelled"
    kayit = (await db_oturumu.execute(select(ZamanKayitlari).where(ZamanKayitlari.id == k["id"]))).scalar_one()
    await db_oturumu.refresh(kayit)
    assert (kayit.durum, kayit.fatura_id) == ("onaylandi", None)
    # Belirli bir taslağa ekleme: taslak olmayan fatura reddedilir.
    y = await istemci.post(f"{ZY}/faturaya-aktar", json={"proje_id": pid, "fatura_id": f["fatura_id"]}, headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "fatura_taslak_degil"
