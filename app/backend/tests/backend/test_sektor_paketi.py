"""Faz 6R — sektör paketini tek tıkla açma + hazır sektör ayarları + vitrin fiyat anlık görüntüsü.

Kapsam:
* Set tanımları tutarlı (paket ↔ set, modül, sınır, alan değerleri, tr/en metin); sağlık/güzellik/spor
  setlerinde teşhis/tedavi/garanti gibi ifade yok, randevu formunda sağlık sorusu yok, KVKK notu var.
* Önizleme: açılacak / zaten açık modüller (bağımlılık sırası), plan etkisi, hazır ayarlar; hiçbir şey yazmaz.
* Uygulama: modüller + hazır ayarlar + günlük + denetim TEK işlem; bir modül ya da bir hazır ayar hata
  verirse HİÇBİRİ yazılmaz; müşteriye TEK özet bildirimi (isteğe bağlı).
* Var olan veri ezilmez (yalnız boş yerler); günlük; "hazır ayarları geri al" el değmiş kaydı korur.
* "Paketi kaldır" yalnız paketle açılan ve elle değiştirilmemiş modülleri eski haline döndürür; veri silmez.
* Otomasyon önerileri müşterinin meta yanıtında; gelen kutusunda vitrin paket talebi → "paketi uygula".
* Vitrin fiyat anlık görüntüsü (`prerender/modul-vitrini-fiyat.json`) tohum + `hesapla` ile tutarlı.
* Yetki: yalnız yönetici.
"""

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import func, select

from core import moduller as manifest
from core import sektor_ayarlari as sa
from core import sektor_paketleri as sp
from services import moduller as ms
from services import sektor_paketi as servis

from conftest import jeton_uret

U = "/api/v1/sektor-paketleri"
MODUL = "/api/v1/moduller"
ON_YUZ = Path(__file__).resolve().parents[3] / "frontend"
DILLER = ("tr", "en", "de", "ru", "zh", "hi", "ar")


def _e(on: str = "paket") -> str:
    return f"{on}-{uuid.uuid4().hex[:8]}@sektor.dev"


def _b(eposta: str) -> dict:
    return {"Authorization": f"Bearer {jeton_uret(eposta)}"}


async def _acik_mi(db, eposta: str, anahtar: str) -> bool:
    return (await ms.musteri_modulleri(db, eposta)).durumlar[anahtar].acik


async def _say(db, model, *kosullar) -> int:
    return int((await db.execute(select(func.count(model.id)).where(*kosullar))).scalar() or 0)


async def _uygula(istemci, yb, eposta, **govde):
    veri = {"paket": "klinik_guzellik", "set": "guzellik_kuafor", "dil": "tr", **govde}
    return await istemci.post(f"{U}/musteri/{eposta}/uygula", json=veri, headers=yb)


@pytest.fixture(autouse=True)
def _temiz():
    from routers import modul_vitrini as mvr

    mvr.hiz_sinirlarini_temizle()
    yield


# ---------------------------------------------------------------------------
# Set tanımları
# ---------------------------------------------------------------------------
def test_set_tanimlari_tutarli():
    assert sa.set_hatalari() == []
    for p in sp.SEKTOR_PAKETLERI:
        assert sa.paket_setleri(p.anahtar), p.anahtar
    # Klinik/güzellik paketi bölünmedi: dört alt seçenek (ilki varsayılan).
    assert sa.paket_setleri("klinik_guzellik") == ["klinik_saglik", "guzellik_kuafor", "spor_studyo", "danismanlik_kocluk"]
    assert sa.varsayilan_set("restoran_kafe") == "restoran_kafe"
    # Örnek değerler (kullanıcının istediği): kuaför saç kesimi 45 dk, boya 120 dk; klinik ilk muayene 30, kontrol 15;
    # spor PT 60 dk, grup dersi kapasiteli.
    tur = {t.anahtar: t for t in sa.hazir_set("guzellik_kuafor").randevu.turler}
    assert tur["sac-kesimi"].sure_dk == 45 and tur["sac-boyama"].sure_dk == 120 and tur["sac-kesimi"].tampon_sonra_dk > 0
    tur = {t.anahtar: t for t in sa.hazir_set("klinik_saglik").randevu.turler}
    assert tur["ilk-muayene"].sure_dk == 30 and tur["kontrol"].sure_dk == 15
    tur = {t.anahtar: t for t in sa.hazir_set("spor_studyo").randevu.turler}
    assert tur["pt-seansi"].sure_dk == 60 and tur["grup-dersi"].kapasite > 1
    # İçerik dili: tr → tr, diğer her dil → en.
    assert sa.icerik_dili("tr") == "tr" and all(sa.icerik_dili(d) == "en" for d in DILLER if d != "tr")
    # Bozuk tanım yakalanıyor.
    eski = sa.HAZIR_SETLER
    try:
        sa.HAZIR_SETLER = eski + (sa.HazirSet("bozuk", "yok_boyle", "Wrench", otomasyon=("yeni_aday_hosgeldin",)),)
        hatalar = sa.set_hatalari()
    finally:
        sa.HAZIR_SETLER = eski
    assert any("bilinmeyen paket" in h for h in hatalar)


def test_saglik_setlerinde_yasak_ifade_ve_saglik_sorusu_yok():
    ozel = [s for s in sa.HAZIR_SETLER if s.kvkk_ozel]
    assert {s.anahtar for s in ozel} == {"klinik_saglik", "guzellik_kuafor", "spor_studyo"}
    saglik_sorusu = re.compile(r"sağlık|saglik|alerji|ilaç|hastalık|şikayet|şikâyet|health|allerg|medic|illness|symptom", re.I)
    for s in ozel:
        assert sa.yasak_ifadeler(s) == [], s.anahtar
        # KVKK: karşılamada "formda sağlık bilgisi paylaşmayın" notu (tr + en).
        assert "sağlık" in s.randevu.karsilama["tr"].lower() and "health" in s.randevu.karsilama["en"].lower()
        for t in s.randevu.turler:
            for q in t.sorular:
                for dil in sa.ICERIK_DILLERI:
                    assert not saglik_sorusu.search(q.etiket[dil]), (s.anahtar, t.anahtar, q.etiket[dil])
                    assert not any(saglik_sorusu.search(x[dil]) for x in q.secenekler)
    # Klinik setinin tür açıklamalarında KVKK notu var.
    for t in sa.hazir_set("klinik_saglik").randevu.turler:
        assert "açık rıza" in t.aciklama["tr"] and "consent" in t.aciklama["en"]
    # Tarayıcı gerçekten yakalıyor (kendini sınama).
    bozuk = sa.HazirSet("x", "klinik_guzellik", "Activity", kvkk_ozel=True,
                        yorum_tesekkur={"tr": "Tedavi garantisi veriyoruz", "en": "We guarantee to treat and cure"})
    assert len(sa.yasak_ifadeler(bozuk)) >= 4
    assert sa.yasak_ifadeler(sa.HazirSet("y", "klinik_guzellik", "Activity", yorum_tesekkur={"tr": "Sağlığınız", "en": "Your health"})) == []


def test_set_metinleri_vitrinde_yedi_dilde():
    for dil in DILLER:
        ek = json.loads((ON_YUZ / "src/i18n/ek/modulVitrini" / f"{dil}.json").read_text(encoding="utf-8"))["modulVitrini"]
        assert set(ek["s"]) == {s.anahtar for s in sa.HAZIR_SETLER}, dil
        for s in sa.HAZIR_SETLER:
            assert ek["s"][s.anahtar]["ad"].strip() and ek["s"][s.anahtar]["ozet"].strip(), (dil, s.anahtar)
        assert ek["detay"]["hazirKurulum"].strip() and ek["detay"]["hazirKurulumAciklama"].strip()
        if dil != "tr":
            tr = json.loads((ON_YUZ / "src/i18n/ek/modulVitrini/tr.json").read_text(encoding="utf-8"))["modulVitrini"]
            assert ek["s"]["guzellik_kuafor"]["ozet"] != tr["s"]["guzellik_kuafor"]["ozet"], dil
    # Yönetim ekranının metinleri (ek paket `sektorPaketi`) 7 dilde aynı anahtarlarla.
    def anahtarlar(d, on=""):
        for k, v in d.items():
            if isinstance(v, dict):
                yield from anahtarlar(v, f"{on}{k}.")
            else:
                yield f"{on}{k}"
    tr_anahtarlar = set(anahtarlar(json.loads((ON_YUZ / "src/i18n/ek/sektorPaketi/tr.json").read_text(encoding="utf-8"))))
    for dil in DILLER:
        d = json.loads((ON_YUZ / "src/i18n/ek/sektorPaketi" / f"{dil}.json").read_text(encoding="utf-8"))
        assert set(anahtarlar(d)) == tr_anahtarlar, dil


def test_hedef_moduller_bagimlilik_sirasiyla():
    from types import SimpleNamespace

    p = sp.SektorPaketi("t", {"tr": "t", "en": "t"}, "Wrench", ("uptime", "randevu"))
    kapali = ms.durumlari_hesapla(None, {"sitem": SimpleNamespace(acik=False, ayarlar_json=None)})
    hedef = servis.hedef_moduller(p, kapali)
    assert hedef == ["sitem", "uptime", "randevu"] or hedef == [m.anahtar for m in manifest.sirali()
                                                                  if m.anahtar in {"sitem", "uptime", "randevu"}]
    assert hedef.index("sitem") < hedef.index("uptime")
    # Bağımlılık zaten açıksa listeye girmez; paketin kendi modülü açık olsa da girer ("zaten açık" gösterilir).
    acik = ms.durumlari_hesapla(None, {"randevu": SimpleNamespace(acik=True, ayarlar_json=None)})
    assert servis.hedef_moduller(p, acik) == [m.anahtar for m in manifest.sirali() if m.anahtar in {"uptime", "randevu"}]


# ---------------------------------------------------------------------------
# Yetki
# ---------------------------------------------------------------------------
async def test_yalniz_yonetici(istemci):
    e = _e()
    for yontem, yol, govde in (
        ("GET", U, None), ("GET", f"{U}/musteri/{e}", None),
        ("POST", f"{U}/musteri/{e}/onizleme", {"paket": "restoran_kafe"}),
        ("POST", f"{U}/musteri/{e}/uygula", {"paket": "restoran_kafe"}),
        ("POST", f"{U}/musteri/{e}/hazir", {"set": "restoran_kafe"}),
        ("POST", f"{U}/uygulamalar/1/kaldir", {}), ("POST", f"{U}/uygulamalar/1/hazir-geri-al", None),
    ):
        y = await istemci.request(yontem, yol, json=govde)
        assert y.status_code == 401, (yol, y.status_code)
        y = await istemci.request(yontem, yol, json=govde, headers=_b(e))
        assert y.status_code == 403, (yol, y.status_code)


async def test_katalog_ve_dogrulama(istemci, yonetici_basligi):
    y = await istemci.get(U, headers=yonetici_basligi)
    assert y.status_code == 200
    g = y.json()
    assert [p["anahtar"] for p in g["paketler"]] == [p.anahtar for p in sp.SEKTOR_PAKETLERI]
    assert next(p for p in g["paketler"] if p["anahtar"] == "klinik_guzellik")["setler"][1] == "guzellik_kuafor"
    e = _e()
    for govde, kod in (
        ({"paket": "yok"}, "paket_yok"),
        ({"paket": "restoran_kafe", "set": "guzellik_kuafor"}, "set_gecersiz"),
        ({"paket": "restoran_kafe", "isletme_adi": "x" * 101}, "cok_uzun"),
        ({"paket": "restoran_kafe", "hazir_ayarlar": "evet"}, "gecersiz"),
    ):
        y = await istemci.post(f"{U}/musteri/{e}/uygula", json=govde, headers=yonetici_basligi)
        assert y.status_code in (400, 404) and y.json()["detail"]["kod"] == kod, (govde, y.text)
    y = await istemci.post(f"{U}/musteri/gecersiz/onizleme", json={"paket": "restoran_kafe"}, headers=yonetici_basligi)
    assert y.status_code == 400


# ---------------------------------------------------------------------------
# Önizleme
# ---------------------------------------------------------------------------
async def test_onizleme_acilacak_acik_ve_hazir_ayarlar_yazmaz(istemci, yonetici_basligi, db_oturumu):
    from models.randevu import RandevuSayfalari
    from models.workspace_modules import WorkspaceModules

    e = _e()
    assert (await istemci.put(f"{MODUL}/musteri/{e}/randevu", json={"acik": True}, headers=yonetici_basligi)).status_code == 200
    y = await istemci.post(f"{U}/musteri/{e}/onizleme", json={"paket": "klinik_guzellik", "set": "guzellik_kuafor", "dil": "tr"},
                           headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    g = y.json()
    beklenen = [m.anahtar for m in manifest.sirali() if m.anahtar in sp.paket("klinik_guzellik").moduller]
    assert [m["anahtar"] for m in g["moduller"]] == beklenen
    durum = {m["anahtar"]: m for m in g["moduller"]}
    assert durum["randevu"]["durum"] == "acik" and durum["ai_asistan"]["durum"] == "acilacak"
    assert g["ozet"]["acilacak"] == 3 and g["ozet"]["zaten_acik"] == 1
    # Plan etkisi (Modüller ekranının mantığı): pakete bağlı olmayan modül ayrı satılan; AI asistan kredi kullanıyor.
    assert durum["dijital_kartvizit"]["etki"] == "ayri_satilan" and durum["ai_asistan"]["kredi"] is True
    assert "ai_asistan" in g["ozet"]["kredi"]
    hazir = {b["modul"]: b for b in g["hazir"]}
    turler = [o for o in hazir["randevu"]["ogeler"] if o["tur"] == "randevu_turu"]
    assert [t["ad"] for t in turler] == ["Saç kesimi", "Saç boyama", "Fön", "Manikür"]
    assert turler[0]["sure_dk"] == 45 and turler[1]["sure_dk"] == 120 and not turler[0]["aktif"]  # adres yok → pasif
    assert "kvkk_ozel" in g["uyarilar"] and "adres_gerekli" in g["uyarilar"]
    # İşletme adı yok → kartvizit atlanır; yorum sayfası Place ID istediği için önerilir.
    assert hazir["dijital_kartvizit"]["atlanan"][0]["neden"] == "ad_gerekli"
    assert hazir["google_yorum_sayfasi"]["atlanan"][0]["neden"] == "place_id_gerekli"
    assert "Google" in hazir["google_yorum_sayfasi"]["atlanan"][0]["oneri"]
    # Adresle: türler aktif, uyarı yok; İngilizce içerik (de → en).
    y = await istemci.post(f"{U}/musteri/{e}/onizleme", json={"paket": "klinik_guzellik", "set": "guzellik_kuafor", "dil": "de",
                                                            "isletme_adi": "Studio Ayse", "adres": "Moda Cad. 1"},
                           headers=yonetici_basligi)
    g = y.json()
    assert g["icerik_dili"] == "en" and "adres_gerekli" not in g["uyarilar"]
    turler = [o for o in {b["modul"]: b for b in g["hazir"]}["randevu"]["ogeler"] if o["tur"] == "randevu_turu"]
    assert turler[0]["ad"] == "Haircut" and all(t["aktif"] for t in turler)
    # Önizleme hiçbir şey yazmadı.
    assert await _say(db_oturumu, RandevuSayfalari, RandevuSayfalari.hesap_email == e) == 0
    assert await _say(db_oturumu, WorkspaceModules, WorkspaceModules.musteri_eposta == e) == 1
    # Yalnız hazır ayar önizlemesi (paket yok): kapalı modüllere yazılmaz.
    y = await istemci.post(f"{U}/musteri/{e}/onizleme", json={"set": "klinik_saglik"}, headers=yonetici_basligi)
    g = y.json()
    assert g["paket"] is None and g["moduller"] == []
    assert {b["modul"]: b for b in g["hazir"]}["ai_asistan"]["atlanan"][0]["neden"] == "modul_kapali"


# ---------------------------------------------------------------------------
# Uygulama
# ---------------------------------------------------------------------------
async def test_uygula_tek_islem_hazir_ayarlar_denetim_bildirim(istemci, yonetici_basligi, db_oturumu):
    from models.ai_asistan import AiAsistanKaynaklari, AiAsistanlar
    from models.audit_log import AuditLog
    from models.kartvizit import Kartvizitler
    from models.notifications import Notifications
    from models.randevu import RandevuKisileri, RandevuSayfalari, RandevuTurleri
    from models.sektor_paketi import SektorPaketiUygulamalari

    e = _e("kuafor")
    y = await _uygula(istemci, yonetici_basligi, e, isletme_adi="Ayşe Kuaför", adres="Moda Cad. 1, Kadıköy", bildirim=True)
    assert y.status_code == 200, y.text
    u = y.json()["uygulama"]
    assert u["durum"] == "uygulandi" and u["hazir_durum"] == "uygulandi" and u["set"] == "guzellik_kuafor"
    assert [m["anahtar"] for m in u["acilan_moduller"]] == [m.anahtar for m in manifest.sirali()
                                                            if m.anahtar in sp.paket("klinik_guzellik").moduller]
    mm = await ms.musteri_modulleri(db_oturumu, e)
    for k in sp.paket("klinik_guzellik").moduller:
        assert mm.durumlar[k].acik and mm.durumlar[k].kaynak == "elle", k
    # Randevu: sayfa + kişi (Pzt–Cmt 10–20) + 4 tür (adres verildiği için aktif, tampon ve sorular dahil).
    sayfa = (await db_oturumu.execute(select(RandevuSayfalari).where(RandevuSayfalari.hesap_email == e))).scalar_one()
    assert sayfa.baslik == "Ayşe Kuaför" and "sağlık" in (sayfa.karsilama or "")
    kisi = (await db_oturumu.execute(select(RandevuKisileri).where(RandevuKisileri.sayfa_id == sayfa.id))).scalar_one()
    assert set(json.loads(kisi.haftalik)) == {"0", "1", "2", "3", "4", "5"} and json.loads(kisi.haftalik)["0"] == [["10:00", "20:00"]]
    turler = (await db_oturumu.execute(select(RandevuTurleri).where(RandevuTurleri.sayfa_id == sayfa.id)
                                       .order_by(RandevuTurleri.sira))).scalars().all()
    assert [(t.slug, t.sure_dk, t.aktif) for t in turler] == [
        ("sac-kesimi", 45, True), ("sac-boyama", 120, True), ("fon", 30, True), ("manikur", 45, True)]
    assert turler[0].konum_turu == "yuz_yuze" and turler[0].konum_degeri == "Moda Cad. 1, Kadıköy"
    assert turler[0].tampon_sonra_dk == 10 and json.loads(turler[0].sorular)[0]["tur"] == "secim"
    assert json.loads(turler[0].kisiler) == [kisi.id]
    # AI asistan taslak (pasif) + SSS kaynağı dizine işlenmiş.
    a = (await db_oturumu.execute(select(AiAsistanlar).where(AiAsistanlar.hesap_email == e)
                                  .execution_options(populate_existing=True))).scalar_one()
    assert a.aktif is False and json.loads(a.yasakli_konular)
    k = (await db_oturumu.execute(select(AiAsistanKaynaklari).where(AiAsistanKaynaklari.asistan_id == a.id)
                                  .execution_options(populate_existing=True))).scalar_one()
    assert k.tur == "sss" and k.durum == "hazir" and k.parca_sayisi >= 5
    # Kartvizit taslak: hizmetler randevu türlerinden, çalışma saatleri, randevu bağlantısı.
    kart = (await db_oturumu.execute(select(Kartvizitler).where(Kartvizitler.hesap_email == e))).scalar_one()
    icerik = json.loads(kart.icerik)
    assert kart.aktif is False and kart.ad_soyad == "Ayşe Kuaför" and json.loads(kart.tema)["sablon"] == "canli"
    assert [h["baslik"] for h in icerik["hizmetler"]] == ["Saç kesimi", "Saç boyama", "Fön", "Manikür"]
    assert icerik["calisma_saatleri"]["goster"] and icerik["baglantilar"][0]["url"].endswith(f"/randevu/{sayfa.slug}")
    # Günlük: oluşturulan her kayıt; atlanan (yorum sayfası Place ID istiyor).
    log = (await db_oturumu.execute(select(SektorPaketiUygulamalari).where(SektorPaketiUygulamalari.musteri_eposta == e))).scalar_one()
    kayitlar = json.loads(log.hazir_kayitlar)
    assert {x["tablo"] for x in kayitlar} >= {"randevu_sayfalari", "randevu_kisileri", "randevu_turleri", "ai_asistanlar",
                                              "ai_asistan_kaynaklari", "kartvizitler"}
    assert all(x["iz"] for x in kayitlar)
    assert any(a_["neden"] == "place_id_gerekli" for a_ in json.loads(log.atlananlar))
    # Denetim kaydı: elle özet + tablo yazımları.
    denetim = (await db_oturumu.execute(select(AuditLog).where(AuditLog.tablo == "sektor_paketi_uygulamalari",
                                                               AuditLog.kayit_id == str(log.id)))).scalars().all()
    elle = [d for d in denetim if "Sektör paketi uygulandı" in (d.ozet or "")]
    assert len(elle) == 1 and elle[0].aktor_eposta == "yonetici@test.dev" and "4 modül açıldı" in elle[0].ozet
    assert await _say(db_oturumu, AuditLog, AuditLog.tablo == "randevu_turleri", AuditLog.islem == "olustur") >= 4
    # Müşteriye TEK özet bildirimi (modül başına ayrı değil).
    bildirimler = (await db_oturumu.execute(select(Notifications).where(Notifications.recipient_email == e,
                                                                        Notifications.channel == "inapp"))).scalars().all()
    assert len(bildirimler) == 1 and bildirimler[0].event_type == "modul_acildi" and "Klinik" in bildirimler[0].title
    # Müşteri panelinde randevu sekmesi ve hazır türler görünüyor.
    y = await istemci.get("/api/v1/randevularim", headers=_b(e))
    assert y.status_code == 200 and y.json()["items"][0]["tur_sayisi"] == 4
    y = await istemci.get(f"/api/v1/randevularim/{sayfa.id}/turler", headers=_b(e))
    assert [t["ad"] for t in y.json()["items"]] == ["Saç kesimi", "Saç boyama", "Fön", "Manikür"]
    # Geçmiş ucu.
    g = (await istemci.get(f"{U}/musteri/{e}", headers=yonetici_basligi)).json()
    assert g["gecmis"][0]["id"] == log.id and g["varsayilan"]["dil"] == "tr" and "iz" not in g["gecmis"][0]["hazir_kayitlar"][0]


async def test_bir_modul_hata_verirse_hicbiri(istemci, yonetici_basligi, db_oturumu, monkeypatch):
    from models.randevu import RandevuSayfalari
    from models.sektor_paketi import SektorPaketiUygulamalari
    from models.workspace_modules import WorkspaceModules

    gercek = servis._modul_acma_denetimi

    def bozuk(anahtar):
        if anahtar == "ai_asistan":
            raise ms.ModulHatasi(409, "deneme_hatasi", [anahtar])
        gercek(anahtar)

    monkeypatch.setattr(servis, "_modul_acma_denetimi", bozuk)
    e = _e("atomik")
    y = await _uygula(istemci, yonetici_basligi, e, isletme_adi="X Salon")
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "deneme_hatasi"
    assert await _say(db_oturumu, WorkspaceModules, WorkspaceModules.musteri_eposta == e) == 0
    assert await _say(db_oturumu, SektorPaketiUygulamalari, SektorPaketiUygulamalari.musteri_eposta == e) == 0
    monkeypatch.setattr(servis, "_modul_acma_denetimi", gercek)

    # Hazır ayarlardan biri patlarsa: açılan modüller ve önceki hazır kayıtlar (randevu) da geri alınır.
    from services import sektor_ayarlari as hazir

    async def patla(b):
        raise RuntimeError("kartvizit yazılamadı")

    monkeypatch.setitem(hazir.UYGULAYICILAR, "dijital_kartvizit", patla)
    y = await _uygula(istemci, yonetici_basligi, e, isletme_adi="X Salon")
    assert y.status_code == 409 and y.json()["detail"] == {"kod": "hazir_ayar_hatasi", "modul": "dijital_kartvizit",
                                                           "neden": "RuntimeError"}
    assert await _say(db_oturumu, WorkspaceModules, WorkspaceModules.musteri_eposta == e) == 0
    assert await _say(db_oturumu, RandevuSayfalari, RandevuSayfalari.hesap_email == e) == 0
    assert await _say(db_oturumu, SektorPaketiUygulamalari, SektorPaketiUygulamalari.musteri_eposta == e) == 0
    for k in sp.paket("klinik_guzellik").moduller:
        assert not await _acik_mi(db_oturumu, e, k)


async def test_var_olan_veri_ezilmez_yalniz_bos_yerler(istemci, yonetici_basligi, db_oturumu):
    from models.kartvizit import YorumSayfalari
    from models.randevu import RandevuSayfalari, RandevuTurleri

    e = _e("mevcut")
    for k in ("randevu", "google_yorum_sayfasi"):
        await istemci.put(f"{MODUL}/musteri/{e}/{k}", json={"acik": True}, headers=yonetici_basligi)
    y = await istemci.post("/api/v1/randevularim", json={"baslik": "Kendi sayfam"}, headers=_b(e))
    assert y.status_code in (200, 201), y.text
    sid = y.json()["id"]
    y = await istemci.post(f"/api/v1/randevularim/{sid}/turler", json={"ad": "Benim türüm", "sure_dk": 50}, headers=_b(e))
    assert y.status_code in (200, 201), y.text
    db_oturumu.add_all([
        YorumSayfalari(hesap_email=e, kod="AbCdEf1", slug=f"y1-{uuid.uuid4().hex[:6]}", isletme_adi="Dolu", place_id="ChIJ1",
                       tesekkur="Benim metnim"),
        YorumSayfalari(hesap_email=e, kod="AbCdEf2", slug=f"y2-{uuid.uuid4().hex[:6]}", isletme_adi="Bos", place_id="ChIJ2"),
    ])
    await db_oturumu.commit()
    y = await _uygula(istemci, yonetici_basligi, e, set="klinik_saglik")
    assert y.status_code == 200, y.text
    plan = {b["modul"]: b for b in y.json()["plan"]}
    nedenler = [a["neden"] for a in plan["randevu"]["atlanan"]]
    assert "sayfa_var" in nedenler and "turler_var" in nedenler
    sayfa = (await db_oturumu.execute(select(RandevuSayfalari).where(RandevuSayfalari.id == sid)
                                      .execution_options(populate_existing=True))).scalar_one()
    assert sayfa.baslik == "Kendi sayfam" and not sayfa.karsilama
    turler = (await db_oturumu.execute(select(RandevuTurleri.ad).where(RandevuTurleri.sayfa_id == sid))).scalars().all()
    assert turler == ["Benim türüm"]
    sayfalar = {s.isletme_adi: s for s in (await db_oturumu.execute(
        select(YorumSayfalari).where(YorumSayfalari.hesap_email == e).execution_options(populate_existing=True))).scalars().all()}
    assert sayfalar["Dolu"].tesekkur == "Benim metnim"
    assert sayfalar["Bos"].tesekkur.startswith("Bizi tercih ettiğiniz için")
    # Aynı seti yeniden uygulamak hiçbir şey eklemez (her şey dolu).
    y = await istemci.post(f"{U}/musteri/{e}/hazir", json={"set": "klinik_saglik"}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["uygulama"] is None


async def test_hazir_ayarlari_geri_al_el_degmisi_korur(istemci, yonetici_basligi, db_oturumu):
    from models.ai_asistan import AiAsistanlar
    from models.kartvizit import Kartvizitler
    from models.randevu import RandevuKisileri, RandevuSayfalari, RandevuTurleri

    e = _e("geri")
    y = await _uygula(istemci, yonetici_basligi, e, set="spor_studyo", isletme_adi="Fit Stüdyo", adres="Bağdat Cad. 5")
    uid = y.json()["uygulama"]["id"]
    sayfa = (await db_oturumu.execute(select(RandevuSayfalari).where(RandevuSayfalari.hesap_email == e))).scalar_one()
    # Müşteri bir türün adını değiştiriyor (el değdi).
    y = await istemci.get(f"/api/v1/randevularim/{sayfa.id}/turler", headers=_b(e))
    pt = next(t for t in y.json()["items"] if t["slug"] == "pt-seansi")
    y = await istemci.put(f"/api/v1/randevularim/{sayfa.id}/turler/{pt['id']}", json={"ad": "PT (birebir)"}, headers=_b(e))
    assert y.status_code == 200, y.text
    y = await istemci.post(f"{U}/uygulamalar/{uid}/hazir-geri-al", headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    sonuc = y.json()["hazir"]
    korunan = {(x["tablo"], x["neden"]) for x in sonuc["korunan"]}
    assert ("randevu_turleri", "degistirildi") in korunan
    assert ("randevu_sayfalari", "bagli_kayit_var") in korunan and ("randevu_kisileri", "bagli_kayit_var") in korunan
    kalan = (await db_oturumu.execute(select(RandevuTurleri.ad).where(RandevuTurleri.sayfa_id == sayfa.id))).scalars().all()
    assert kalan == ["PT (birebir)"]
    assert await _say(db_oturumu, RandevuKisileri, RandevuKisileri.sayfa_id == sayfa.id) == 1
    assert await _say(db_oturumu, AiAsistanlar, AiAsistanlar.hesap_email == e) == 0
    assert await _say(db_oturumu, Kartvizitler, Kartvizitler.hesap_email == e) == 0
    assert y.json()["uygulama"]["hazir_durum"] == "geri_alindi" and y.json()["uygulama"]["durum"] == "uygulandi"
    # Modüller açık kaldı (yalnız hazır ayarlar geri alındı); ikinci kez geri alma yok.
    assert await _acik_mi(db_oturumu, e, "randevu")
    y = await istemci.post(f"{U}/uygulamalar/{uid}/hazir-geri-al", headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "hazir_ayar_yok"


async def test_paketi_kaldir_yalniz_paketle_acilan_ve_el_degmemis(istemci, yonetici_basligi, db_oturumu):
    from models.notifications import Notifications
    from models.randevu import RandevuSayfalari
    from models.workspace_modules import WorkspaceModules

    e = _e("kaldir")
    # Randevu paketten önce elle açıktı: paket ona dokunmaz, kaldırınca da açık kalır.
    await istemci.put(f"{MODUL}/musteri/{e}/randevu", json={"acik": True}, headers=yonetici_basligi)
    y = await _uygula(istemci, yonetici_basligi, e, set="danismanlik_kocluk", isletme_adi="Koç Ali")
    g = y.json()["uygulama"]
    assert g["zaten_acik"] == ["randevu"] and "randevu" not in [m["anahtar"] for m in g["acilan_moduller"]]
    # Yönetici AI asistanı sonradan kapatıp yeniden açıyor (açılış anı değişti → el değdi).
    await istemci.put(f"{MODUL}/musteri/{e}/ai_asistan", json={"acik": False}, headers=yonetici_basligi)
    satir = (await db_oturumu.execute(select(WorkspaceModules).where(WorkspaceModules.musteri_eposta == e,
                                                                     WorkspaceModules.modul_anahtari == "ai_asistan"))).scalar_one()
    satir.acik = True
    satir.acilis_at = datetime.now(timezone.utc) + timedelta(minutes=1)
    await db_oturumu.commit()
    y = await istemci.post(f"{U}/uygulamalar/{g['id']}/kaldir", json={"hazir_ayarlar": False, "bildirim": True},
                           headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    s = y.json()
    assert set(s["kapatilan"]) == {"dijital_kartvizit", "google_yorum_sayfasi"}
    assert {x["anahtar"]: x["neden"] for x in s["korunan"]} == {"ai_asistan": "elle_degisti"}
    for k, acik in (("randevu", True), ("ai_asistan", True), ("dijital_kartvizit", False), ("google_yorum_sayfasi", False)):
        assert await _acik_mi(db_oturumu, e, k) is acik, k
    # Veri silinmedi (hazır ayarlar geri alınmadı): randevu sayfası duruyor.
    assert await _say(db_oturumu, RandevuSayfalari, RandevuSayfalari.hesap_email == e) == 1
    assert s["uygulama"]["durum"] == "kaldirildi" and s["uygulama"]["hazir_durum"] == "uygulandi"
    kapanis = (await db_oturumu.execute(select(Notifications).where(Notifications.recipient_email == e,
                                                                     Notifications.event_type == "modul_kapandi",
                                                                     Notifications.ref_type == "sektor_paketi",
                                                                     Notifications.channel == "inapp"))).scalars().all()
    assert len(kapanis) == 1 and "Dijital kartvizit" in kapanis[0].body and "Verileriniz silinmedi" in kapanis[0].body
    y = await istemci.post(f"{U}/uygulamalar/{g['id']}/kaldir", json={}, headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "zaten_kaldirildi"
    # Hazır ayarlar ayrıca geri alınabilir (paket kaldırıldıktan sonra da).
    y = await istemci.post(f"{U}/uygulamalar/{g['id']}/hazir-geri-al", headers=yonetici_basligi)
    assert y.status_code == 200 and await _say(db_oturumu, RandevuSayfalari, RandevuSayfalari.hesap_email == e) == 0


async def test_kaldir_baska_acik_modulun_bagimliligini_korur(istemci, yonetici_basligi, db_oturumu):
    """Paketin açtığı bir modüle sonradan açılan başka bir modül bağlıysa o bağımlılık kapanmaz."""
    from models.workspace_modules import WorkspaceModules

    e = _e("bagimli")
    p = sp.SektorPaketi("t6r_test", {"tr": "Test", "en": "Test"}, "Wrench", ("randevu", "dinamik_qr"))
    sp.PAKET_SOZLUGU["t6r_test"] = p
    sa.SET_SOZLUGU["t6r_test"] = sa.HazirSet("t6r_test", "t6r_test", "Wrench")
    try:
        # sitem varsayılan açık ama müşteride elle kapalı → uptime paketi sitem'i de açar.
        await istemci.put(f"{MODUL}/musteri/{e}/sitem", json={"acik": False}, headers=yonetici_basligi)
        sp.PAKET_SOZLUGU["t6r_test"] = sp.SektorPaketi("t6r_test", {"tr": "Test", "en": "Test"}, "Wrench", ("uptime",))
        y = await istemci.post(f"{U}/musteri/{e}/uygula", json={"paket": "t6r_test", "set": "t6r_test"}, headers=yonetici_basligi)
        assert y.status_code == 200, y.text
        g = y.json()["uygulama"]
        assert [m["anahtar"] for m in g["acilan_moduller"]] == ["sitem", "uptime"]
        # Sonradan "yenileme" (sitem'e bağlı) elle açılıyor; paket kaldırılınca sitem açık kalmalı.
        assert (await istemci.put(f"{MODUL}/musteri/{e}/yenileme", json={"acik": True}, headers=yonetici_basligi)).status_code == 200
        y = await istemci.post(f"{U}/uygulamalar/{g['id']}/kaldir", json={}, headers=yonetici_basligi)
        s = y.json()
        assert s["kapatilan"] == ["uptime"] and s["korunan"][0]["anahtar"] == "sitem"
        assert s["korunan"][0]["neden"] == "bagimli_acik" and "yenileme" in s["korunan"][0]["moduller"]
        assert await _acik_mi(db_oturumu, e, "sitem") and await _acik_mi(db_oturumu, e, "yenileme")
        assert not await _acik_mi(db_oturumu, e, "uptime")
        satir = (await db_oturumu.execute(select(WorkspaceModules).where(WorkspaceModules.musteri_eposta == e,
                                                                         WorkspaceModules.modul_anahtari == "uptime"))).scalar_one()
        assert satir.acik is None  # önceki hali: satır yoktu → varsayılana döndü
    finally:
        sp.PAKET_SOZLUGU.pop("t6r_test", None)
        sa.SET_SOZLUGU.pop("t6r_test", None)


async def test_yalniz_hazir_ayarlar_acik_modullere(istemci, yonetici_basligi, db_oturumu):
    from models.eposta_pazarlama import EpDiziAdimlari, EpDiziler, EpListeler
    from models.saha_servisi import SahaAyarlari, SahaSablonlari

    e = _e("hazir")
    for k in ("saha_servisi", "eposta_pazarlama"):
        await istemci.put(f"{MODUL}/musteri/{e}/{k}", json={"acik": True}, headers=yonetici_basligi)
    y = await istemci.post(f"{U}/musteri/{e}/hazir", json={"set": "teknik_servis", "dil": "en", "isletme_adi": "Cool Service"},
                           headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    u = y.json()["uygulama"]
    assert u["tur"] == "hazir" and u["acilan_moduller"] == [] and u["icerik_dili"] == "en"
    plan = {b["modul"]: b for b in y.json()["plan"]}
    assert plan["randevu"]["atlanan"][0]["neden"] == "modul_kapali"
    ayar = (await db_oturumu.execute(select(SahaAyarlari).where(SahaAyarlari.hesap_email == e))).scalar_one()
    assert ayar.randevu_kancasi is True and ayar.firma_adi == "Cool Service" and ayar.varsayilan_dil == "en"
    sablonlar = (await db_oturumu.execute(select(SahaSablonlari).where(SahaSablonlari.hesap_email == e))).scalars().all()
    assert {s.is_turu for s in sablonlar} == {"kesif", "ariza", "kurulum"} and sablonlar[0].ad == "Site survey"
    # E-posta dizisi: yalnız taslak (pasif), liste ve 3 adım.
    y = await istemci.post(f"{U}/musteri/{e}/hazir", json={"set": "egitim_etkinlik"}, headers=yonetici_basligi)
    dizi = (await db_oturumu.execute(select(EpDiziler).where(EpDiziler.hesap_email == e))).scalar_one()
    assert dizi.aktif is False and dizi.tetik == "abonelik_onaylandi"
    assert await _say(db_oturumu, EpDiziAdimlari, EpDiziAdimlari.dizi_id == dizi.id) == 3
    assert await _say(db_oturumu, EpListeler, EpListeler.hesap_email == e) == 1
    uid = y.json()["uygulama"]["id"]
    y = await istemci.post(f"{U}/uygulamalar/{uid}/hazir-geri-al", headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["uygulama"]["durum"] == "kaldirildi"
    assert await _say(db_oturumu, EpDiziler, EpDiziler.hesap_email == e) == 0
    assert await _say(db_oturumu, EpListeler, EpListeler.hesap_email == e) == 0
    y = await istemci.post(f"{U}/uygulamalar/{uid}/kaldir", json={}, headers=yonetici_basligi)
    assert y.status_code == 400


async def test_restoran_menusu_ve_yorum_metni(istemci, yonetici_basligi, db_oturumu):
    from models.qr_menu import MenuKategorileri, MenuMagazalari

    e = _e("restoran")
    y = await istemci.post(f"{U}/musteri/{e}/uygula", json={"paket": "restoran_kafe", "isletme_adi": "Kafe Deniz"},
                           headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    m = (await db_oturumu.execute(select(MenuMagazalari).where(MenuMagazalari.hesap_email == e))).scalar_one()
    assert m.aktif is False and m.ad == "Kafe Deniz" and m.duzen == "menu"
    kategoriler = (await db_oturumu.execute(select(MenuKategorileri.ad).where(MenuKategorileri.magaza_id == m.id)
                                            .order_by(MenuKategorileri.sira))).scalars().all()
    assert kategoriler[:3] == ["Kahvaltı", "Başlangıçlar", "Ana yemekler"] and len(kategoriler) == 6
    # Ürün/fiyat uydurulmadı.
    from models.qr_menu import MenuUrunleri

    assert await _say(db_oturumu, MenuUrunleri, MenuUrunleri.magaza_id == m.id) == 0


# ---------------------------------------------------------------------------
# Otomasyon önerileri ve gelen kutusu kısayolu
# ---------------------------------------------------------------------------
async def test_otomasyon_onerileri_musteri_metasinda(istemci, yonetici_basligi):
    e = _e("ajans")
    y = await istemci.post(f"{U}/musteri/{e}/uygula", json={"paket": "ajans_serbest", "isletme_adi": "Mavi Ajans"},
                           headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    uid = y.json()["uygulama"]["id"]
    meta = (await istemci.get("/api/v1/otomasyonlarim/meta", headers=_b(e))).json()
    assert meta["onerilen_sablonlar"] == ["kart_mesaj_otomatik_yanit", "teklif_kabul_gorev", "destek_acil_bildirim"]
    assert "kart_mesaj_otomatik_yanit" in {s["anahtar"] for s in meta["sablonlar"]}
    # Öneri kurulmaz: kural yok.
    assert (await istemci.get("/api/v1/otomasyonlarim/kurallar", headers=_b(e))).json()["items"] == []
    # Yeni müşteri şablonları tek tıkla kurulabiliyor.
    y = await istemci.post("/api/v1/otomasyonlarim/kurallar/sablondan", json={"sablon": "kart_mesaj_otomatik_yanit"}, headers=_b(e))
    assert y.status_code == 200 and y.json()["eylemler"][0]["alici"] == "kisi"
    await istemci.post(f"{U}/uygulamalar/{uid}/kaldir", json={}, headers=yonetici_basligi)
    await istemci.put(f"{MODUL}/musteri/{e}/otomasyon", json={"acik": True}, headers=yonetici_basligi)
    meta = (await istemci.get("/api/v1/otomasyonlarim/meta", headers=_b(e))).json()
    assert meta["onerilen_sablonlar"] == []


async def test_gelen_kutusu_paket_talebi_kisayolu(istemci, yonetici_basligi):
    musteri = _e("vitrin")
    yabanci = _e("yabanci")
    await istemci.put(f"{MODUL}/musteri/{musteri}/randevu", json={"acik": True}, headers=yonetici_basligi)
    for eposta, ip in ((musteri, "203.0.113.61"), (yabanci, "203.0.113.62")):
        y = await istemci.post("/api/v1/modul-vitrini/talep", headers={"x-mk-istemci-ip": ip}, json={
            "tur": "paket", "anahtar": "klinik_guzellik", "ad": "Ayşe", "eposta": eposta, "dil": "tr"})
        assert y.status_code == 200, y.text
    liste = (await istemci.get("/api/v1/gelen-kutusu", params={"kaynak": "iletisim", "q": "sektor.dev", "adet": 50},
                               headers=yonetici_basligi)).json()
    ogeler = {o["kisi_eposta"]: o for o in liste["ogeler"] if o["kisi_eposta"] in (musteri, yabanci)}
    assert ogeler[musteri]["ek"]["paket"] == "klinik_guzellik"
    assert "paket_uygula" in [x["anahtar"] for x in ogeler[musteri]["eylemler"]]
    assert "paket_uygula" not in [x["anahtar"] for x in ogeler[yabanci]["eylemler"]]
    y = await istemci.get(f"/api/v1/gelen-kutusu/iletisim/{ogeler[musteri]['kimlik']}", headers=yonetici_basligi)
    assert "paket_uygula" in [x["anahtar"] for x in y.json()["oge"]["eylemler"]]


# ---------------------------------------------------------------------------
# Randevu: hazır ayarla pasif oluşan yüz yüze tür adressiz açılamaz
# ---------------------------------------------------------------------------
async def test_adressiz_yuz_yuze_tur_acilamaz(istemci, yonetici_basligi, db_oturumu):
    from models.randevu import RandevuSayfalari, RandevuTurleri

    e = _e("adres")
    y = await _uygula(istemci, yonetici_basligi, e, set="klinik_saglik")
    assert "adres_gerekli" in y.json()["uyarilar"]
    sayfa = (await db_oturumu.execute(select(RandevuSayfalari).where(RandevuSayfalari.hesap_email == e))).scalar_one()
    turler = {t.slug: t for t in (await db_oturumu.execute(select(RandevuTurleri).where(RandevuTurleri.sayfa_id == sayfa.id))).scalars()}
    assert turler["ilk-muayene"].aktif is False and turler["online-on-gorusme"].aktif is True
    yol = f"/api/v1/randevularim/{sayfa.id}/turler/{turler['ilk-muayene'].id}"
    y = await istemci.put(yol, json={"aktif": True}, headers=_b(e))
    assert y.status_code == 400 and y.json()["detail"] == {"kod": "zorunlu", "alan": "konum_degeri"}
    y = await istemci.put(yol, json={"aktif": True, "konum_turu": "yuz_yuze", "konum_degeri": "Klinik adresi 1"}, headers=_b(e))
    assert y.status_code == 200 and y.json()["aktif"] is True


# ---------------------------------------------------------------------------
# Vitrin fiyat anlık görüntüsü
# ---------------------------------------------------------------------------
def test_fiyat_anlik_goruntusu_depoda_guncel_ve_hesapla_ile_tutarli():
    """Tohum değiştiyse: `python -m scripts.modul_vitrini_tohum` ile dosyayı yeniden üretin."""
    from core.fiyat_hesaplama import hesapla
    from scripts.modul_vitrini_tohum import FIYAT_HEDEF, fiyat_metni
    from scripts.seed_pricing_v5 import PROFILES, SCALES

    assert FIYAT_HEDEF.read_text(encoding="utf-8") == fiyat_metni(), "prerender/modul-vitrini-fiyat.json güncel değil"
    anlik = json.loads(FIYAT_HEDEF.read_text(encoding="utf-8"))
    assert anlik["surum"] == 1 and set(anlik["fiyatlar"]) == {s["kod"] for s in SCALES}
    baz = {s["kod"]: float(s["baz_aylik_fiyat_usd"]) for s in SCALES}
    carpan = {p["kod"]: float(p["carpan"]) for p in PROFILES}
    for kod, f in anlik["fiyatlar"].items():
        beklenen = min(hesapla(scale_kod=kod, profile_kod=p, period="aylik", addon_kodlari=[], scale_baz_fiyatlari=baz,
                               profile_carpanlari=carpan, addon_fiyatlari={}).paket_fiyat for p in carpan)
        assert f["baslangic_aylik"] == beklenen and f["para_birimi"] == "USD", kod
        assert set(f["ad"]) == set(DILLER) and f["ad"]["tr"] == next(s["ad"] for s in SCALES if s["kod"] == kod)


async def test_fiyat_anlik_goruntusu_canli_uc_ile_ayni(istemci, db_oturumu):
    from scripts.modul_vitrini_tohum import FIYAT_HEDEF
    from scripts.seed_pricing_v5 import seed

    await seed(db_oturumu)
    canli = (await istemci.get("/api/v1/modul-vitrini")).json()["fiyatlar"]
    anlik = json.loads(FIYAT_HEDEF.read_text(encoding="utf-8"))["fiyatlar"]
    for kod in ("ALFA", "BETA", "OMEGA", "SIGMA"):
        assert canli[kod]["baslangic_aylik"] == anlik[kod]["baslangic_aylik"], kod
        assert canli[kod]["ad"]["tr"] == anlik[kod]["ad"]["tr"]


def test_prerender_yukleyici_anlik_goruntuye_duser():
    """`prerender/moduller-yukle.js`: zaman aşımı 20 sn, 2 yeniden deneme, anlık görüntü yedeği, ayar."""
    metin = (ON_YUZ / "prerender/moduller-yukle.js").read_text(encoding="utf-8")
    assert "modul-vitrini-fiyat.json" in metin and "ZAMAN_ASIMI_MS = 20000" in metin and "YENIDEN_DENEME = 2" in metin
    assert "'anlik'" in metin and "MODUL_VITRINI_KAYNAGI" in metin
