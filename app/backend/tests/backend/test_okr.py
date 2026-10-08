"""Faz 6O — Hedefler ve OKR: dönem, hedef, KR, check-in, otomatik kaynaklar, paylaşım, kapanış, hatırlatma.

Kapsam: ilerleme hesabı birim testleri (bölme sıfır / hedef = başlangıç, azalt yönü, negatif değerler, evet/hayır,
kilometre taşı, kırpma, ağırlıklı ortalama, beklenen ilerleme, renk), dönem tarihleri, hizalama döngüsü, değer
ayrıştırma (para kuruş), AI yanıtı ayrıştırma; yetki (anonim 401, müşteri 403 yönetici uçlarında, modül kapalı 403,
`hedefler_okur` yazamaz), müşteri izolasyonu, otomatik kaynaklar (her kaynak; başka hesabın verisi sayılmaz; modül
kapalıyken listede yok + sunucu reddeder + yenileme değeri değiştirmez), paylaşılmamış / özel hedef müşteriye sızmaz
(check-in notu paylaşılmaz), hizalama döngüsü reddi, dönem kapanışı ve taşıma (bağlantı geçmişi), olaylar (tehlikede ve
tamamlandı — geçişte bir kez), haftalık hatırlatma bir kez, zamanlı iş + haftalık özet, çöp kutusu, PDF/CSV, AI önerisi.
"""

import json
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from conftest import jeton_uret

Y = "/api/v1/okr-yonetim"
M = "/api/v1/okr"
P = "/api/v1/okr-paylasilan"
MODUL = "/api/v1/moduller"
UTC = timezone.utc


def _e(on: str = "okr") -> str:
    return f"{on}-{uuid.uuid4().hex[:8]}@okr.dev"


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


@pytest.fixture(autouse=True)
def _ortam():
    from routers import okr as r
    from services import hesap_ekibi

    r.hiz_sinirlarini_temizle()
    hesap_ekibi.onbellegi_temizle()
    yield
    r.hiz_sinirlarini_temizle()


async def _modul(istemci, yonetici_basligi, eposta, anahtar="hedefler", acik=True, **ayarlar):
    govde = {"acik": acik}
    if ayarlar:
        govde["ayarlar"] = ayarlar
    y = await istemci.put(f"{MODUL}/musteri/{eposta}/{anahtar}", json=govde, headers=yonetici_basligi)
    assert y.status_code == 200, y.text


async def _post(istemci, yol, govde, basliklar, beklenen=200):
    y = await istemci.post(yol, json=govde, headers=basliklar)
    assert y.status_code == beklenen, (yol, y.text)
    return y.json()


async def _put(istemci, yol, govde, basliklar, beklenen=200):
    y = await istemci.put(yol, json=govde, headers=basliklar)
    assert y.status_code == beklenen, (yol, y.text)
    return y.json()


def _bugun() -> date:
    from services import okr as s

    return s.bugun()


async def _donem(istemci, basliklar, yol=M, **govde):
    if not govde:
        b = _bugun()
        govde = {"tur": "ozel", "baslangic": (b - timedelta(days=30)).isoformat(), "bitis": (b + timedelta(days=60)).isoformat()}
    return await _post(istemci, f"{yol}/donemler", govde, basliklar)


async def _hedef(istemci, basliklar, donem_id, yol=M, **govde):
    govde.setdefault("baslik", f"Hedef {uuid.uuid4().hex[:5]}")
    return await _post(istemci, f"{yol}/hedefler", {"donem_id": donem_id, **govde}, basliklar)


async def _kr(istemci, basliklar, hedef_id, yol=M, beklenen=200, **govde):
    govde.setdefault("baslik", f"KR {uuid.uuid4().hex[:5]}")
    return await _post(istemci, f"{yol}/hedefler/{hedef_id}/krler", govde, basliklar, beklenen)


async def _musteri(istemci, yonetici_basligi, on="okr", **moduller):
    e = _e(on)
    await _modul(istemci, yonetici_basligi, e)
    for anahtar in moduller.get("ek", ()):
        await _modul(istemci, yonetici_basligi, e, anahtar)
    return e, _b(e)


async def _ekle(db, nesne):
    db.add(nesne)
    await db.commit()
    await db.refresh(nesne)
    return nesne


# ---------------------------------------------------------------------------
# İlerleme hesabı (birim)
# ---------------------------------------------------------------------------
def test_kr_ilerleme_kenar_durumlari():
    from services.okr import kr_ilerleme

    # Artır: (mevcut − başlangıç) / (hedef − başlangıç), 0–1 kırpılır.
    assert kr_ilerleme("sayi", 0, 10, 5) == 0.5
    assert kr_ilerleme("sayi", 0, 10, 15) == 1.0 and kr_ilerleme("sayi", 0, 10, -3) == 0.0
    assert kr_ilerleme("yuzde", 40, 90, 65) == 0.5
    # Azalt: hedef < başlangıç — doğru işaret (100 → 50; 75 = yarı yol, 120 = geride, 40 = aşıldı).
    assert kr_ilerleme("sayi", 100, 50, 75, "azalt") == 0.5
    assert kr_ilerleme("sayi", 100, 50, 120, "azalt") == 0.0 and kr_ilerleme("sayi", 100, 50, 40, "azalt") == 1.0
    # Hedef = başlangıç (bölme sıfır): hedefe ulaşıldıysa 1, değilse 0 — yöne göre.
    assert kr_ilerleme("sayi", 10, 10, 10) == 1.0 and kr_ilerleme("sayi", 10, 10, 9) == 0.0
    assert kr_ilerleme("sayi", 10, 10, 9, "azalt") == 1.0 and kr_ilerleme("sayi", 10, 10, 11, "azalt") == 0.0
    assert kr_ilerleme("sayi", 0, 0, 0) == 1.0 and kr_ilerleme("sayi", None, None, None) == 1.0
    # Negatif değerler: −10 → 0 hedefinde −5 = 0,5; zarardan kâra (−2000 → 3000) 500 = 0,5.
    assert kr_ilerleme("sayi", -10, 0, -5) == 0.5
    assert kr_ilerleme("para", -200000, 300000, 50000) == 0.5
    assert kr_ilerleme("sayi", -10, -50, -30, "azalt") == 0.5
    # Evet/hayır ve kilometre taşı.
    assert kr_ilerleme("evet_hayir", 0, 1, 1) == 1.0 and kr_ilerleme("evet_hayir", 0, 1, 0) == 0.0
    km = [{"id": "a", "metin": "x", "tamam": True}, {"id": "b", "metin": "y", "tamam": False}, {"id": "c", "metin": "z", "tamam": True},
          {"id": "d", "metin": "w"}]
    assert kr_ilerleme("kilometre", 0, 0, 0, kilometre=km) == 0.5
    assert kr_ilerleme("kilometre", 0, 0, 0, kilometre=[]) == 0.0 and kr_ilerleme("kilometre", 0, 0, 0) == 0.0


def test_hedef_ilerleme_beklenen_ve_renk():
    from services.okr import beklenen_ilerleme, hedef_ilerleme, ilerleme_durumu

    # Ağırlıklı ortalama: (1·3 + 0·1) / 4 = 0,75; ağırlık toplamı 0 / KR yok → None.
    assert hedef_ilerleme([(1.0, 3), (0.0, 1)]) == 0.75
    assert hedef_ilerleme([(0.5, 1), (0.5, 1)]) == 0.5
    assert hedef_ilerleme([]) is None and hedef_ilerleme([(1.0, 0)]) is None
    assert hedef_ilerleme([(1.7, 1), (-1.0, 1)]) == 0.5  # kırpılmış girdiler
    bas, bit = date(2026, 10, 1), date(2026, 12, 31)  # 92 gün
    assert beklenen_ilerleme(bas, bit, date(2026, 9, 1)) == 0.0
    assert beklenen_ilerleme(bas, bit, bas) == pytest.approx(1 / 92)
    assert beklenen_ilerleme(bas, bit, date(2026, 11, 15)) == pytest.approx(46 / 92)
    assert beklenen_ilerleme(bas, bit, bit) == 1.0 and beklenen_ilerleme(bas, bit, date(2027, 2, 1)) == 1.0
    assert beklenen_ilerleme(bas, bas, bas) == 1.0
    assert ilerleme_durumu(None, 0.5) is None and ilerleme_durumu(1.0, 0.2) == "tamam"
    assert ilerleme_durumu(0.45, 0.5) == "yolunda" and ilerleme_durumu(0.30, 0.5) == "riskli"
    assert ilerleme_durumu(0.20, 0.5) == "geride" and ilerleme_durumu(0.9, 0.1) == "yolunda"


def test_donem_dongu_deger_ve_ai_ayristirma():
    from services import okr as s

    assert s.ceyrek_araligi(2026, 1) == (date(2026, 1, 1), date(2026, 3, 31))
    assert s.ceyrek_araligi(2026, 4) == (date(2026, 10, 1), date(2026, 12, 31))
    v = s.donem_coz({"tur": "ceyrek", "yil": 2026, "ceyrek": 2})
    assert (v["baslangic"], v["bitis"]) == (date(2026, 4, 1), date(2026, 6, 30))
    assert s.donem_coz({"tur": "yil", "yil": 2027})["bitis"] == date(2027, 12, 31)
    for kotu, kod in (({"tur": "ozel", "baslangic": "2026-05-01", "bitis": "2026-04-01"}, "bitis_once"),
                      ({"tur": "ceyrek", "yil": 2026, "ceyrek": 5}, "aralik_disinda"),
                      ({"tur": "hafta"}, "secim_gecersiz")):
        with pytest.raises(s.OkrHatasi) as h:
            s.donem_coz(kotu)
        assert h.value.kod == kod
    # Döngü: 1 ← 2 ← 3; 1'in üstü 3 olamaz, kendisi olamaz; bağımsız 4 olabilir.
    ust = {1: None, 2: 1, 3: 2, 4: None}
    assert s.dongu_var_mi(ust, 1, 3) and s.dongu_var_mi(ust, 1, 1) and s.dongu_var_mi(ust, 2, 3)
    assert not s.dongu_var_mi(ust, 1, 4) and not s.dongu_var_mi(ust, 3, 1) and not s.dongu_var_mi(ust, None, 3)
    assert s.dongu_var_mi({1: 2, 2: 1}, 5, 1)  # bozuk zincir: güvenli tarafta
    # Para kuruş (yarım yukarı; eksi olabilir — kâr), sayı Türkçe ondalık, evet/hayır.
    assert s.deger_coz("1.250,50", "para", "x") == 125050 and s.deger_coz("-15,5", "para", "x") == -1550
    assert s.deger_coz("12,5", "sayi", "x") == 12.5 and s.deger_coz(7, "yuzde", "x") == 7.0
    assert s.deger_coz(True, "evet_hayir", "x") == 1.0 and s.deger_coz(0, "evet_hayir", "x") == 0.0
    for ham, tur in (("abc", "sayi"), ("", "sayi"), ("evet", "evet_hayir"), (float("nan"), "sayi"), (1e15, "sayi")):
        with pytest.raises(s.OkrHatasi):
            s.deger_coz(ham, tur, "x")
    with pytest.raises(s.OkrHatasi) as h:
        s.yon_denetle("artir", 10, 5)
    assert h.value.kod == "yon_tutarsiz"
    s.yon_denetle("azalt", 10, 5)
    # AI yanıtı: kod çiti, geçersiz öğe atılır, para ana birimden kuruşa, yön düzeltilir; hiçbiri geçerli değilse hata.
    oneriler = s.ai_yanitini_coz('```json\n{"oneriler":[{"baslik":"Ciro","tur":"para","baslangic":100,"hedef":250.5,'
                                 '"yon":"artir"},{"tur":"sayi"},"x",{"baslik":"Hata oranı","baslangic":10,"hedef":2,"yon":"artir"}]}\n```', 5)
    assert [o["baslik"] for o in oneriler] == ["Ciro", "Hata oranı"]
    assert oneriler[0]["baslangic"] == 10000 and oneriler[0]["hedef"] == 25050 and oneriler[1]["yon"] == "azalt"
    with pytest.raises(s.OkrHatasi):
        s.ai_yanitini_coz("düz metin", 3)


# ---------------------------------------------------------------------------
# Yetki
# ---------------------------------------------------------------------------
async def test_yetki_anonim_musteri_ve_modul(istemci, yonetici_basligi, db_oturumu):
    e = _e("yetki")
    b = _b(e)
    for yol in (f"{M}/meta", f"{Y}/meta", P, f"{M}/donemler", f"{Y}/musteri-hesaplari"):
        assert (await istemci.get(yol)).status_code == 401, yol
    # Yönetici uçları müşteriye 403.
    for yol in (f"{Y}/meta", f"{Y}/donemler", f"{Y}/musteri-hesaplari"):
        assert (await istemci.get(yol, headers=b)).status_code == 403, yol
    assert (await istemci.post(f"{Y}/donemler", json={"tur": "yil", "yil": 2026}, headers=b)).status_code == 403
    # Modül kapalı (varsayılan) → 403 modul_kapali; paylaşılan kart modülsüz açık.
    y = await istemci.get(f"{M}/meta", headers=b)
    assert y.status_code == 403 and _kod(y) == "modul_kapali"
    assert (await istemci.get(P, headers=b)).json() == {"items": []}
    await _modul(istemci, yonetici_basligi, e)
    y = await istemci.get(f"{M}/meta", headers=b)
    assert y.status_code == 200 and y.json()["ajans"] is False and y.json()["okur"] is False
    assert y.json()["ekip"][0]["email"] == e and y.json()["hedef_siniri"] == 30
    # Ekip: `hedefler_okur` okur ama yazamaz; izni olmayan 403 hesap_izni_yok.
    from models.hesap_uyeleri import HesapUyeleri
    from services import hesap_ekibi

    okur, yabanci = _e("okur"), _e("izinsiz")
    for uye, izinler in ((okur, ["hedefler_okur"]), (yabanci, ["projeler"])):
        db_oturumu.add(HesapUyeleri(hesap_email=e, uye_email=uye, rol="uye", izinler=json.dumps(izinler), durum="aktif"))
    await db_oturumu.commit()
    hesap_ekibi.onbellegi_temizle()
    d = await _donem(istemci, b)
    y = await istemci.get(f"{M}/meta", headers=_b(okur, e))
    assert y.status_code == 200 and y.json()["okur"] is True and y.json()["ai_hazir"] is False
    assert (await istemci.get(f"{M}/donemler/{d['id']}/ozet", headers=_b(okur, e))).status_code == 200
    y = await istemci.post(f"{M}/hedefler", json={"donem_id": d["id"], "baslik": "Okur yazamaz"}, headers=_b(okur, e))
    assert y.status_code == 403 and _kod(y) == "hesap_izni_yok"
    y = await istemci.get(f"{M}/meta", headers=_b(yabanci, e))
    assert y.status_code == 403 and _kod(y) == "hesap_izni_yok"
    # Okur paylaşılan kartı da görebilir (izin `hedefler_okur` yeter).
    assert (await istemci.get(P, headers=_b(okur, e))).status_code == 200


async def test_modul_kaydi_izinler_ve_eski_varsayilan():
    import json as _json

    from core import moduller as mf
    from core import sektor_paketleri
    from services import hesap_ekibi as he
    from services import otomasyon_kural, webhook, zamanli

    m = mf.modul("hedefler")
    assert m and m.musteri_sekmesi == "hedefler" and m.yonetici_sekmesi == "hedefler" and not m.varsayilan_acik
    assert sektor_paketleri.satilabilir_mi(m) and "hedef_siniri" in m.varsayilan_ayarlar()
    assert {"hedefler", "hedefler_okur"} <= set(he.IZINLER)
    assert "hedefler" not in he.ROL_VARSAYILAN["uye"] and "hedefler" in he.ROL_VARSAYILAN["yonetici"]
    # Canlıdaki (hedefler'siz) yönetici varsayılanı olduğu gibi kayıtlı üye yeni izinleri de alır; özelleştirilmiş almaz.
    eski = sorted(set(he.IZINLER) - {"hedefler", "hedefler_okur"})
    assert {"hedefler", "hedefler_okur"} <= set(he.izinleri_coz(_json.dumps(eski), "yonetici"))
    assert "hedefler" not in he.izinleri_coz(_json.dumps(["projeler", "muhasebe"]), "yonetici")
    for olay in ("okr.kr_riskte", "okr.hedef_tamamlandi"):
        assert olay in webhook.OLAY_SOZLUGU and olay in otomasyon_kural.OLAY_SOZLUGU
        assert otomasyon_kural.olay_nesneleri(olay, False) == ("okr", "hesap", "kisi", "olay")
    assert otomasyon_kural.kisi_sec("okr.kr_riskte", {"okr": otomasyon_kural.ORNEK["okr"]})["email"] == "satis@ornek.com"
    assert "okr_bakimi" in zamanli.GOREV_ADLARI and zamanli.GOREV_ADLARI[-1] == "aylik_site_analizi"


# ---------------------------------------------------------------------------
# Akış: dönem, hedef, KR, check-in, ilerleme
# ---------------------------------------------------------------------------
async def test_donem_hedef_kr_checkin_ilerleme(istemci, yonetici_basligi):
    e, b = await _musteri(istemci, yonetici_basligi, "akis")
    d = await _donem(istemci, b)
    assert d["etkin"] is True  # ilk dönem kendiliğinden etkin
    d2 = await _post(istemci, f"{M}/donemler", {"tur": "ceyrek", "yil": 2027, "ceyrek": 1, "etkin": True}, b)
    assert d2["baslangic"] == "2027-01-01" and d2["bitis"] == "2027-03-31" and d2["etkin"] is True
    donemler = (await istemci.get(f"{M}/donemler", headers=b)).json()["items"]
    assert [x["id"] for x in donemler if x["etkin"]] == [d2["id"]]
    await _put(istemci, f"{M}/donemler/{d['id']}", {"etkin": True}, b)
    assert (await istemci.get(f"{M}/meta", headers=b)).json()["etkin_donem_id"] == d["id"]

    h = await _hedef(istemci, b, d["id"], baslik="Gelirleri büyüt", aciklama="Yıl sonu hedefi")
    assert h["sahip"] == e and h["durum"] == "etkin" and h["gorunurluk"] == "ekip" and h["ilerleme"] is None
    k1 = await _kr(istemci, b, h["id"], tur="sayi", baslangic=0, hedef=20, birim="müşteri", agirlik=3)
    assert k1["ilerleme"] == 0.0 and k1["mevcut"] == 0 and k1["birim"] == "müşteri"
    k2 = await _kr(istemci, b, h["id"], tur="para", baslangic="0", hedef="10.000", para_birimi="USD")
    assert k2["hedef"] == 1000000 and k2["para_birimi"] == "USD"
    k3 = await _kr(istemci, b, h["id"], tur="kilometre", kilometre_taslari=[{"metin": "Teklif şablonu"}, {"metin": "Fiyat listesi"}])
    assert k3["kilometre_toplam"] == 2 and k3["hedef"] == 2
    k4 = await _kr(istemci, b, h["id"], tur="sayi", baslangic=48, hedef=24, yon="azalt", birim="saat")
    y = await istemci.post(f"{M}/hedefler/{h['id']}/krler", json={"baslik": "X", "baslangic": 10, "hedef": 5}, headers=b)
    assert y.status_code == 400 and _kod(y) == "yon_tutarsiz"

    r = await _post(istemci, f"{M}/krler/{k1['id']}/checkin", {"deger": "10", "guven": "yolunda", "notlar": "İyi gidiyor"}, b)
    assert r["kr"]["ilerleme"] == 0.5 and r["kr"]["guven"] == "yolunda" and r["checkin"]["yazan"] == e
    await _post(istemci, f"{M}/krler/{k2['id']}/checkin", {"deger": "2.500"}, b)
    km = (await istemci.get(f"{M}/hedefler/{h['id']}", headers=b)).json()["krler"][2]["kilometre_taslari"]
    await _post(istemci, f"{M}/krler/{k3['id']}/checkin", {"kilometre": [{"id": km[0]["id"], "tamam": True}]}, b)
    await _post(istemci, f"{M}/krler/{k4['id']}/checkin", {"deger": 36}, b)
    ay = (await istemci.get(f"{M}/hedefler/{h['id']}", headers=b)).json()
    il = {x["id"]: x["ilerleme"] for x in ay["krler"]}
    assert il == {k1["id"]: 0.5, k2["id"]: 0.25, k3["id"]: 0.5, k4["id"]: 0.5}
    # Ağırlıklı: (0,5·3 + 0,25 + 0,5 + 0,5) / 6 = 0,4583
    assert ay["ilerleme"] == pytest.approx(2.75 / 6, abs=1e-4)
    assert len(ay["krler"][0]["checkinler"]) == 1 and ay["krler"][0]["checkinler"][0]["notlar"] == "İyi gidiyor"
    oz = (await istemci.get(f"{M}/donemler/{d['id']}/ozet", headers=b)).json()
    assert oz["hedefler"][0]["id"] == h["id"] and oz["ilerleme"] == pytest.approx(2.75 / 6, abs=1e-4)
    assert 0 < oz["donem"]["beklenen"] < 1 and oz["durum_rengi"] in ("yolunda", "riskli", "geride")
    # Doğrulamalar: gelecek tarihli check-in, değersiz check-in, KR sınırı, yabancı sahip.
    y = await istemci.post(f"{M}/krler/{k1['id']}/checkin", json={"deger": 1, "tarih": (_bugun() + timedelta(days=2)).isoformat()}, headers=b)
    assert y.status_code == 400 and _kod(y) == "tarih_ileride"
    y = await istemci.post(f"{M}/krler/{k1['id']}/checkin", json={"guven": "riskli"}, headers=b)
    assert y.status_code == 400 and _kod(y) == "zorunlu"
    y = await istemci.post(f"{M}/hedefler", json={"donem_id": d["id"], "baslik": "X", "sahip": "baskasi@yok.dev"}, headers=b)
    assert y.status_code == 400 and _kod(y) == "sahip_ekipte_yok"
    # Hedef sınırı (modül ayarı).
    await _modul(istemci, yonetici_basligi, e, hedef_siniri=1)
    y = await istemci.post(f"{M}/hedefler", json={"donem_id": d["id"], "baslik": "Sınır"}, headers=b)
    assert y.status_code == 409 and _kod(y) == "hedef_siniri"
    # Dolu dönem silinmez.
    y = await istemci.delete(f"{M}/donemler/{d['id']}", headers=b)
    assert y.status_code == 409 and _kod(y) == "donem_dolu"
    assert (await istemci.delete(f"{M}/donemler/{d2['id']}", headers=b)).status_code == 200


async def test_musteri_izolasyonu(istemci, yonetici_basligi):
    a, ba = await _musteri(istemci, yonetici_basligi, "izoa")
    b_, bb = await _musteri(istemci, yonetici_basligi, "izob")
    d = await _donem(istemci, ba)
    h = await _hedef(istemci, ba, d["id"], baslik="A'nın gizli planı")
    k = await _kr(istemci, ba, h["id"], baslangic=0, hedef=5)
    assert (await istemci.get(f"{M}/donemler", headers=bb)).json()["items"] == []
    for yol in (f"{M}/donemler/{d['id']}/ozet", f"{M}/hedefler/{h['id']}", f"{M}/krler/{k['id']}/checkinler",
                f"{M}/donemler/{d['id']}/rapor.pdf"):
        assert (await istemci.get(yol, headers=bb)).status_code == 404, yol
    assert (await istemci.post(f"{M}/krler/{k['id']}/checkin", json={"deger": 5}, headers=bb)).status_code == 404
    assert (await istemci.put(f"{M}/hedefler/{h['id']}", json={"baslik": "Ele geçirildi"}, headers=bb)).status_code == 404
    assert (await istemci.delete(f"{M}/hedefler/{h['id']}", headers=bb)).status_code == 404
    db_ = await _donem(istemci, bb)
    y = await istemci.post(f"{M}/hedefler", json={"donem_id": db_["id"], "baslik": "B", "ust_id": h["id"]}, headers=bb)
    assert y.status_code == 400 and _kod(y) == "hedef_bulunamadi"
    assert (await istemci.get(f"{M}/agac", headers=bb)).json()["items"] == []
    # Ajansın kendi OKR'ları müşteriden ayrı kapsam.
    assert all(x["id"] != d["id"] for x in (await istemci.get(f"{Y}/donemler", headers=yonetici_basligi)).json()["items"])


async def test_ozel_hedef_yalniz_sahibine(istemci, yonetici_basligi, db_oturumu):
    from models.hesap_uyeleri import HesapUyeleri
    from services import hesap_ekibi

    e, b = await _musteri(istemci, yonetici_basligi, "ozel")
    uye = _e("uye")
    db_oturumu.add(HesapUyeleri(hesap_email=e, uye_email=uye, rol="uye", izinler=json.dumps(["hedefler"]), durum="aktif"))
    await db_oturumu.commit()
    hesap_ekibi.onbellegi_temizle()
    d = await _donem(istemci, b)
    ozel = await _hedef(istemci, _b(uye, e), d["id"], baslik="Kişisel gelişim", gorunurluk="ozel")
    ekip = await _hedef(istemci, b, d["id"], baslik="Ekip hedefi", sahip=uye)
    assert ekip["sahip"] == uye and ozel["sahip"] == uye
    sahibin = {x["id"] for x in (await istemci.get(f"{M}/donemler/{d['id']}/ozet", headers=b)).json()["hedefler"]}
    assert sahibin == {ekip["id"]}
    assert (await istemci.get(f"{M}/hedefler/{ozel['id']}", headers=b)).status_code == 404
    uyenin = {x["id"] for x in (await istemci.get(f"{M}/donemler/{d['id']}/ozet", headers=_b(uye, e))).json()["hedefler"]}
    assert uyenin == {ekip["id"], ozel["id"]}


# ---------------------------------------------------------------------------
# Hizalama ağacı
# ---------------------------------------------------------------------------
async def test_hizalama_agaci_ve_dongu_reddi(istemci, yonetici_basligi):
    yb = yonetici_basligi
    yil = await _post(istemci, f"{Y}/donemler", {"tur": "ozel", "baslangic": "2030-01-01", "bitis": "2030-12-31"}, yb)
    cey = await _post(istemci, f"{Y}/donemler", {"tur": "ozel", "baslangic": "2030-01-01", "bitis": "2030-03-31"}, yb)
    kok = await _hedef(istemci, yb, yil["id"], Y, baslik="Pazar lideri ol")
    orta = await _hedef(istemci, yb, cey["id"], Y, baslik="Satışı büyüt", ust_id=kok["id"])
    yaprak = await _hedef(istemci, yb, cey["id"], Y, baslik="Yeni kanal aç", ust_id=orta["id"])
    for hid, ust in ((kok["id"], yaprak["id"]), (kok["id"], kok["id"]), (orta["id"], yaprak["id"])):
        y = await istemci.put(f"{Y}/hedefler/{hid}", json={"ust_id": ust}, headers=yb)
        assert y.status_code == 400 and _kod(y) == "hizalama_dongusu", (hid, ust, y.text)
    agac = (await istemci.get(f"{Y}/agac", params={"donem_id": cey["id"]}, headers=yb)).json()["items"]
    dugum = {x["id"]: x for x in agac if x["id"] in (kok["id"], orta["id"], yaprak["id"])}
    # Seçili dönemin hedefleri + başka dönemdeki üstü (kök) — kök "seçili dönem dışı" işaretli.
    assert set(dugum) == {kok["id"], orta["id"], yaprak["id"]}
    assert dugum[yaprak["id"]]["ust_id"] == orta["id"] and dugum[orta["id"]]["ust_id"] == kok["id"]
    assert dugum[kok["id"]]["secili_donemde"] is False and dugum[orta["id"]]["secili_donemde"] is True
    # Üstü silinen hedefin bağı kalkar.
    assert (await istemci.delete(f"{Y}/hedefler/{orta['id']}", headers=yb)).status_code == 200
    assert (await istemci.get(f"{Y}/hedefler/{yaprak['id']}", headers=yb)).json()["ust_id"] is None


# ---------------------------------------------------------------------------
# Otomatik kaynaklar — ajans
# ---------------------------------------------------------------------------
def _an(g: date, saat: int = 12) -> datetime:
    return datetime(g.year, g.month, g.day, saat, tzinfo=UTC)


async def test_ajans_kaynaklari_dogru_sayar(istemci, yonetici_basligi, db_oturumu):
    from models.crm import CrmAdaylari
    from models.muhasebe import MuhasebeHareketleri
    from models.payments import Payments
    from models.proje_gorevleri import ProjectTasks
    from models.projects import Projects
    from models.teklifler import Teklifler

    yb = yonetici_basligi
    bas, bit = date(2031, 2, 1), date(2031, 2, 28)
    ici, disi = date(2031, 2, 10), date(2031, 3, 5)
    # CRM: dönemde 2 aday (biri ayın son günü 23:30 İstanbul), dönem dışı 1.
    for an in (_an(ici), datetime(2031, 2, 28, 20, 30, tzinfo=UTC), _an(disi), datetime(2031, 1, 31, 20, 59, tzinfo=UTC)):
        db_oturumu.add(CrmAdaylari(ad="Aday", asama="yeni", kaynak="manuel", created_at=an))
    # Teklif: kabul TRY 1.500,50 + 499,50 (dönemde), USD 100 (dönemde), ret, dönem dışı kabul.
    for toplam, pb, durum, an in (("1500.50", "TRY", "kabul", _an(ici)), ("499.50", "TRY", "kabul", _an(ici)),
                                  ("100", "USD", "kabul", _an(ici)), ("9999", "TRY", "ret", _an(ici)), ("7777", "TRY", "kabul", _an(disi))):
        db_oturumu.add(Teklifler(no=f"T-{uuid.uuid4().hex[:10]}", baslik="Teklif", genel_toplam=toplam, para_birimi=pb, durum=durum,
                                 karar_at=an))
    # Tahsilat: 1.000 TRY ödendi (elle tarih), 250 TRY iade, 300 USD, dönem dışı 5.000, bekleyen 400.
    for tutar, pb, durum, tarih, an in ((1000.0, "TRY", "odendi", "2031-02-11", None), (250.0, "TRY", "iade", None, _an(ici)),
                                        (300.0, "USD", "odendi", "2031-02-12", None), (5000.0, "TRY", "odendi", "2031-03-02", None),
                                        (400.0, "TRY", "bekliyor", "2031-02-12", None)):
        db_oturumu.add(Payments(tutar=tutar, para_birimi=pb, durum=durum, odeme_tarihi=tarih, odendi_at=an, saglayici="havale"))
    # Ön muhasebe (@ajans): gelir 1.200 (KDV 200) → 1.000 KDV hariç; gider 300; müşteri defteri sayılmaz.
    for kapsam, hesap, tur, tutar, kdv in (("@ajans", None, "gelir", 120000, 20000), ("@ajans", None, "gider", 30000, 0),
                                           ("baska@okr.dev", "baska@okr.dev", "gelir", 999900, 0)):
        db_oturumu.add(MuhasebeHareketleri(kapsam=kapsam, hesap_email=hesap, tur=tur, tarih=ici, tutar=tutar, para_birimi="TRY",
                                           kdv_tutari=kdv, kaynak="manuel"))
    proje = Projects(title="OKR projesi", description="d", category="web", client_email="p@okr.dev")
    db_oturumu.add(proje)
    await db_oturumu.commit()
    await db_oturumu.refresh(proje)
    for durum in ("tamam", "tamam", "suruyor", "yapilacak"):
        db_oturumu.add(ProjectTasks(proje_id=proje.id, baslik="Görev", durum=durum))
    await db_oturumu.commit()

    meta = (await istemci.get(f"{Y}/meta", headers=yb)).json()
    anahtarlar = {k["anahtar"] for k in meta["kaynaklar"]}
    assert {"crm_aday", "teklif_kabul", "fatura_tahsilat", "muhasebe_gelir", "muhasebe_gider", "muhasebe_kar", "proje_gorev"} <= anahtarlar
    assert not anahtarlar & {"pos_satis", "randevu_sayisi", "egitim_kayit"}
    assert any(p["id"] == proje.id for p in meta["projeler"])
    d = await _post(istemci, f"{Y}/donemler", {"tur": "ozel", "baslangic": bas.isoformat(), "bitis": bit.isoformat()}, yb)
    h = await _hedef(istemci, yb, d["id"], Y, baslik="Ajans büyümesi")
    beklenen = {
        ("crm_aday", None): 2, ("teklif_kabul", "TRY"): 200000, ("teklif_kabul", "USD"): 10000, ("fatura_tahsilat", "TRY"): 75000,
        ("fatura_tahsilat", "USD"): 30000, ("muhasebe_gelir", "TRY"): 100000, ("muhasebe_gider", "TRY"): 30000,
        ("muhasebe_kar", "TRY"): 70000, ("muhasebe_gelir", "EUR"): 0,
    }
    for (kaynak, pb), deger in beklenen.items():
        ayar = {"para_birimi": pb} if pb else {}
        kr = await _kr(istemci, yb, h["id"], Y, kaynak=kaynak, kaynak_ayar=ayar, baslangic=0, hedef=1000000)
        assert kr["mevcut"] == deger and kr["kaynak"] == kaynak and kr["kaynak_hata"] is None, (kaynak, pb, kr)
        assert kr["tur"] in ("sayi", "para") and (pb is None or kr["para_birimi"] == pb)
        if len([1 for _ in range(1)]) and kaynak != "crm_aday":
            await istemci.delete(f"{Y}/krler/{kr['id']}", headers=yb)  # KR sınırı (10) aşılmasın
    kr = await _kr(istemci, yb, h["id"], Y, kaynak="proje_gorev", kaynak_ayar={"proje_id": proje.id}, baslangic=0, hedef=100)
    assert kr["tur"] == "yuzde" and kr["mevcut"] == 50.0 and kr["ilerleme"] == 0.5
    y = await istemci.post(f"{Y}/hedefler/{h['id']}/krler", json={"baslik": "X", "kaynak": "proje_gorev", "kaynak_ayar": {"proje_id": 999999},
                                                                 "baslangic": 0, "hedef": 100}, headers=yb)
    assert y.status_code == 400 and _kod(y) == "proje_bulunamadi"
    y = await istemci.post(f"{Y}/hedefler/{h['id']}/krler", json={"baslik": "X", "kaynak": "pos_satis", "hedef": 1}, headers=yb)
    assert y.status_code == 400 and _kod(y) == "kaynak_gecersiz"
    # Kaynaklı KR'de elle değer yok sayılır; "şimdi yenile" değişen değeri yakalar (otomatik check-in satırı).
    r = await _post(istemci, f"{Y}/krler/{kr['id']}/checkin", {"deger": 99, "guven": "riskli"}, yb)
    assert r["kr"]["mevcut"] == 50.0 and r["kr"]["guven"] == "riskli"
    son = (await db_oturumu.execute(select(ProjectTasks).where(ProjectTasks.proje_id == proje.id, ProjectTasks.durum == "suruyor"))).scalars().first()
    son.durum = "tamam"
    await db_oturumu.commit()
    r = await _post(istemci, f"{Y}/krler/{kr['id']}/yenile", {}, yb)
    assert r["degisti"] is True and r["kr"]["mevcut"] == 75.0
    gecmis = (await istemci.get(f"{Y}/krler/{kr['id']}/checkinler", headers=yb)).json()["items"]
    assert [c["tur"] for c in gecmis][:1] == ["otomatik"] and gecmis[0]["deger"] == 75.0 and gecmis[0]["onceki"] == 50.0
    r = await _post(istemci, f"{Y}/krler/{kr['id']}/yenile", {}, yb)
    assert r["degisti"] is False


# ---------------------------------------------------------------------------
# Otomatik kaynaklar — müşteri (yalnız kendi verisi, yalnız açık modüller)
# ---------------------------------------------------------------------------
async def test_musteri_kaynaklari_yalniz_kendi_verisi_ve_acik_modul(istemci, yonetici_basligi, db_oturumu):
    from models.egitim import EgitimOgrencileri
    from models.muhasebe import MuhasebeHareketleri
    from models.randevu import Randevular
    from models.stok_pos import PosSatislari

    a, ba = await _musteri(istemci, yonetici_basligi, "kaya")
    b_, bb = await _musteri(istemci, yonetici_basligi, "kayb")
    meta = (await istemci.get(f"{M}/meta", headers=ba)).json()
    assert meta["kaynaklar"] == []  # hiçbir veri modülü açık değil
    d = await _donem(istemci, ba, tur="ozel", baslangic="2031-02-01", bitis="2031-02-28")
    h = await _hedef(istemci, ba, d["id"])
    y = await istemci.post(f"{M}/hedefler/{h['id']}/krler", json={"baslik": "POS", "kaynak": "pos_satis", "hedef": "100"}, headers=ba)
    assert y.status_code == 403 and _kod(y) == "kaynak_kapali"
    y = await istemci.post(f"{M}/hedefler/{h['id']}/krler", json={"baslik": "CRM", "kaynak": "crm_aday", "hedef": 5}, headers=ba)
    assert y.status_code == 400 and _kod(y) == "kaynak_gecersiz"
    for e in (a, b_):
        for modul in ("on_muhasebe", "stok_pos", "randevu", "egitim"):
            await _modul(istemci, yonetici_basligi, e, modul)
    ici = date(2031, 2, 10)
    for hesap, tutar in ((a, 120000), (b_, 777700)):
        db_oturumu.add(MuhasebeHareketleri(kapsam=hesap, hesap_email=hesap, tur="gelir", tarih=ici, tutar=tutar, para_birimi="TRY",
                                           kdv_tutari=20000 if hesap == a else 0, kaynak="manuel"))
        db_oturumu.add(MuhasebeHareketleri(kapsam=hesap, hesap_email=hesap, tur="gider", tarih=ici, tutar=30000, para_birimi="TRY",
                                           kdv_tutari=0, kaynak="manuel"))
    for hesap, toplam, iade, durum, an in ((a, 50000, 10000, "kismi_iade", _an(ici)), (a, 25000, 0, "tamamlandi", _an(ici)),
                                           (a, 99999, 0, "iptal", _an(ici)), (a, 11111, 0, "tamamlandi", _an(date(2031, 3, 1))),
                                           (b_, 888800, 0, "tamamlandi", _an(ici))):
        db_oturumu.add(PosSatislari(hesap_email=hesap, no=f"S-{uuid.uuid4().hex[:10]}", konum_id=1, oturum_id=1, kasiyer=hesap,
                                    durum=durum, toplam=toplam, iade_toplam=iade, para_birimi="TRY", zaman=an))
    for hesap, durum, an in ((a, "onayli", _an(ici)), (a, "onayli", _an(date(2031, 2, 20))), (a, "iptal", _an(ici)),
                             (b_, "onayli", _an(ici)), (a, "onayli", _an(date(2031, 4, 1)))):
        db_oturumu.add(Randevular(uid=uuid.uuid4().hex, sayfa_id=1, tur_id=1, kisi_id=900000 + uuid.uuid4().int % 99999,
                                  hesap_email=hesap, baslangic=an, bitis=an + timedelta(minutes=30), dolu_bas=an,
                                  dolu_bit=an + timedelta(minutes=30), koltuk=0 if durum == "onayli" else None, durum=durum))
    for hesap, durum, an in ((a, "aktif", _an(ici)), (a, "ayrildi", _an(ici)), (a, "bekleme", _an(ici)), (b_, "aktif", _an(ici)),
                             (a, "aktif", _an(date(2031, 1, 5)))):
        db_oturumu.add(EgitimOgrencileri(kurs_id=1, hesap_email=hesap, kod=uuid.uuid4().hex[:10].upper(), durum=durum, kaynak="elle",
                                         created_at=an))
    await db_oturumu.commit()

    anahtarlar = {k["anahtar"] for k in (await istemci.get(f"{M}/meta", headers=ba)).json()["kaynaklar"]}
    assert anahtarlar == {"muhasebe_gelir", "muhasebe_gider", "muhasebe_kar", "pos_satis", "randevu_sayisi", "egitim_kayit"}
    beklenen = {"muhasebe_gelir": 100000, "muhasebe_gider": 30000, "muhasebe_kar": 70000, "pos_satis": 65000,
                "randevu_sayisi": 2, "egitim_kayit": 2}
    krler = {}
    for kaynak, deger in beklenen.items():
        para = kaynak.startswith("muhasebe") or kaynak == "pos_satis"
        kr = await _kr(istemci, ba, h["id"], kaynak=kaynak, kaynak_ayar={"para_birimi": "TRY"} if para else {}, baslangic=0,
                       hedef="1000000" if para else 10)
        assert kr["mevcut"] == deger, (kaynak, kr)
        krler[kaynak] = kr
    # B aynı kaynaklarla yalnız kendi verisini görür.
    db2 = await _donem(istemci, bb, tur="ozel", baslangic="2031-02-01", bitis="2031-02-28")
    hb = await _hedef(istemci, bb, db2["id"])
    kb = await _kr(istemci, bb, hb["id"], kaynak="pos_satis", kaynak_ayar={"para_birimi": "TRY"}, baslangic=0, hedef="10000")
    assert kb["mevcut"] == 888800
    # Ekip üyesi: kaynağın verisini görme izni yoksa kaynak listede yok ve bağlanamaz.
    from models.hesap_uyeleri import HesapUyeleri
    from services import hesap_ekibi

    uye = _e("kayuye")
    db_oturumu.add(HesapUyeleri(hesap_email=a, uye_email=uye, rol="uye", izinler=json.dumps(["hedefler", "randevu"]), durum="aktif"))
    await db_oturumu.commit()
    hesap_ekibi.onbellegi_temizle()
    uye_kaynak = {k["anahtar"] for k in (await istemci.get(f"{M}/meta", headers=_b(uye, a))).json()["kaynaklar"]}
    assert uye_kaynak == {"randevu_sayisi"}
    y = await istemci.post(f"{M}/hedefler/{h['id']}/krler", json={"baslik": "X", "kaynak": "muhasebe_kar", "hedef": "1"}, headers=_b(uye, a))
    assert y.status_code == 403 and _kod(y) == "kaynak_kapali"
    # Modül kapanınca: listede yok, yeni bağlama 403, yenileme değeri DEĞİŞTİRMEZ (modul_kapali).
    await _modul(istemci, yonetici_basligi, a, "stok_pos", acik=False)
    assert "pos_satis" not in {k["anahtar"] for k in (await istemci.get(f"{M}/meta", headers=ba)).json()["kaynaklar"]}
    y = await istemci.post(f"{M}/hedefler/{h['id']}/krler", json={"baslik": "POS2", "kaynak": "pos_satis", "hedef": "1"}, headers=ba)
    assert y.status_code == 403 and _kod(y) == "kaynak_kapali"
    r = await _post(istemci, f"{M}/krler/{krler['pos_satis']['id']}/yenile", {}, ba)
    assert r["hata"] == "modul_kapali" and r["kr"]["mevcut"] == 65000 and r["kr"]["kaynak_hata"] == "modul_kapali"


async def test_kaynak_degeri_baska_hesabi_saymaz_dogrudan(db_oturumu):
    """Servis düzeyi: müşteri kaynağı hesapsız (ajans) çağrılamaz; ajans kaynağı müşteriyle çağrılamaz."""
    from services import okr as s
    from services import okr_kaynak as ok

    db = db_oturumu
    if True:
        with pytest.raises(s.OkrHatasi):
            await ok.kaynak_degeri(db, "pos_satis", None, date(2031, 2, 1), date(2031, 2, 28), {"para_birimi": "TRY"})
        with pytest.raises(s.OkrHatasi):
            await ok.kaynak_degeri(db, "crm_aday", "x@okr.dev", date(2031, 2, 1), date(2031, 2, 28), {})
        with pytest.raises(s.OkrHatasi):
            await ok.kaynak_degeri(db, "yok", None, date(2031, 2, 1), date(2031, 2, 28), {})


# ---------------------------------------------------------------------------
# Müşteriyle paylaşım
# ---------------------------------------------------------------------------
async def test_paylasilan_hedef_gorunur_paylasilmayan_sizmaz(istemci, yonetici_basligi):
    yb = yonetici_basligi
    m, bm = _e("paylas"), None
    bm = _b(m)
    d = await _post(istemci, f"{Y}/donemler", {"tur": "ozel", "baslangic": (_bugun() - timedelta(days=10)).isoformat(),
                                               "bitis": (_bugun() + timedelta(days=80)).isoformat()}, yb)
    paylasilan = await _hedef(istemci, yb, d["id"], Y, baslik="Müşterinin organik trafiğini artır", musteri_email=m,
                              musteri_paylasim=True)
    ic = await _hedef(istemci, yb, d["id"], Y, baslik="İç hedef: kârlılık", musteri_email=m)
    ozel = await _hedef(istemci, yb, d["id"], Y, baslik="Özel not", musteri_email=m, gorunurluk="ozel")
    taslak = await _hedef(istemci, yb, d["id"], Y, baslik="Taslak paylaşım", musteri_email=m, musteri_paylasim=True, durum="taslak")
    y = await istemci.put(f"{Y}/hedefler/{ozel['id']}", json={"musteri_paylasim": True}, headers=yb)
    assert y.status_code == 400 and _kod(y) == "paylasim_kosulu"
    y = await istemci.post(f"{Y}/hedefler", json={"donem_id": d["id"], "baslik": "X", "musteri_paylasim": True}, headers=yb)
    assert y.status_code == 400 and _kod(y) == "paylasim_kosulu"
    kr = await _kr(istemci, yb, paylasilan["id"], Y, baslangic=1000, hedef=3000, birim="ziyaret")
    await _post(istemci, f"{Y}/krler/{kr['id']}/checkin", {"deger": 2000, "guven": "riskli", "notlar": "İÇ NOT: bütçe kısıldı"}, yb)
    await _kr(istemci, yb, ic["id"], Y, baslangic=0, hedef=10)
    liste = (await istemci.get(P, headers=bm)).json()["items"]
    assert [x["id"] for x in liste] == [paylasilan["id"]]
    x = liste[0]
    assert x["ilerleme"] == 0.5 and x["krler"][0]["ilerleme"] == 0.5 and x["krler"][0]["birim"] == "ziyaret"
    ham = json.dumps(liste, ensure_ascii=False)
    for sizmamali in ("İÇ NOT", "riskli", "guven", "sahip", "checkin", "notlar", "İç hedef", "Özel not", "Taslak paylaşım", "yonetici@"):
        assert sizmamali not in ham, sizmamali
    # Müşterinin kendi OKR uçları ajansın hedeflerini göstermez (modül açılsa da ayrı kapsam).
    await _modul(istemci, yonetici_basligi, m)
    assert (await istemci.get(f"{M}/donemler", headers=bm)).json()["items"] == []
    for hid in (paylasilan["id"], ic["id"], ozel["id"], taslak["id"]):
        assert (await istemci.get(f"{M}/hedefler/{hid}", headers=bm)).status_code == 404
    assert (await istemci.get(f"{M}/krler/{kr['id']}/checkinler", headers=bm)).status_code == 404
    # Başka müşteri bu hedefi görmez; paylaşım kapanınca kart kaybolur.
    assert (await istemci.get(P, headers=_b(_e("baska")))).json()["items"] == []
    await _put(istemci, f"{Y}/hedefler/{paylasilan['id']}", {"musteri_paylasim": False}, yb)
    assert (await istemci.get(P, headers=bm)).json()["items"] == []
    hesaplar = (await istemci.get(f"{Y}/musteri-hesaplari", headers=yb)).json()["items"]
    assert isinstance(hesaplar, list)


# ---------------------------------------------------------------------------
# Kapanış ve taşıma
# ---------------------------------------------------------------------------
async def test_donem_kapanisi_ve_tasima(istemci, yonetici_basligi):
    e, b = await _musteri(istemci, yonetici_basligi, "kapanis")
    d = await _donem(istemci, b, tur="ozel", baslangic="2030-01-01", bitis="2030-03-31")
    sonraki = await _donem(istemci, b, tur="ozel", baslangic="2030-04-01", bitis="2030-06-30")
    h = await _hedef(istemci, b, d["id"], baslik="Müşteri memnuniyeti")
    biten = await _kr(istemci, b, h["id"], baslangic=0, hedef=10, mevcut=10)
    acik = await _kr(istemci, b, h["id"], baslangic=0, hedef=10, mevcut=4)
    await _post(istemci, f"{M}/krler/{acik['id']}/checkin", {"deger": 4, "notlar": "eski dönem notu"}, b)
    tam = await _hedef(istemci, b, d["id"], baslik="Bitti")
    await _kr(istemci, b, tam["id"], tur="evet_hayir", mevcut=True)
    k = (await istemci.get(f"{M}/donemler/{d['id']}/kapanis", headers=b)).json()
    krs = {x["id"]: x for hh in k["hedefler"] for x in hh["krler"]}
    assert krs[acik["id"]]["onerilen_puan"] == 0.4 and krs[acik["id"]]["acik"] is True and krs[biten["id"]]["acik"] is False
    assert [x["id"] for x in k["hedef_donemler"]] == [sonraki["id"]]
    y = await istemci.post(f"{M}/donemler/{d['id']}/kapat", json={"puanlar": {str(acik["id"]): 1.5}}, headers=b)
    assert y.status_code == 400 and _kod(y) == "puan_gecersiz"
    r = await _post(istemci, f"{M}/donemler/{d['id']}/kapat", {"puanlar": {str(acik["id"]): 0.3}, "kapanis_notu": "İyi çeyrek",
                                                               "tasi": True, "hedef_donem_id": sonraki["id"]}, b)
    assert r["tasinan_hedef"] == 1 and r["tasinan_kr"] == 1
    oz = (await istemci.get(f"{M}/donemler/{d['id']}/ozet", headers=b)).json()
    assert oz["donem"]["durum"] == "kapandi" and oz["donem"]["kapanis_notu"] == "İyi çeyrek"
    assert all(x["durum"] == "kapandi" for x in oz["hedefler"])
    puan = {x["id"]: x["kapanis_puani"] for hh in oz["hedefler"] for x in hh["krler"]}
    assert puan[acik["id"]] == 0.3 and puan[biten["id"]] == 1.0
    # Kapalı dönemde yazma yok.
    y = await istemci.post(f"{M}/krler/{acik['id']}/checkin", json={"deger": 5}, headers=b)
    assert y.status_code == 409 and _kod(y) == "donem_kapali"
    y = await istemci.post(f"{M}/donemler/{d['id']}/kapat", json={}, headers=b)
    assert y.status_code == 409
    # Sonraki dönemde KOPYA: aynı başlık, açık KR değerleriyle, eski KR'ye bağ (check-in geçmişi eski KR'de).
    yeni = (await istemci.get(f"{M}/donemler/{sonraki['id']}/ozet", headers=b)).json()["hedefler"]
    assert len(yeni) == 1 and yeni[0]["baslik"] == "Müşteri memnuniyeti" and yeni[0]["tasindi_kaynak_id"] == h["id"]
    assert len(yeni[0]["krler"]) == 1 and yeni[0]["krler"][0]["mevcut"] == 4 and yeni[0]["krler"][0]["tasindi_kaynak_id"] == acik["id"]
    ay = (await istemci.get(f"{M}/hedefler/{yeni[0]['id']}", headers=b)).json()
    gecmis = ay["krler"][0]["tasima_gecmisi"]
    assert gecmis and gecmis[0]["kr_id"] == acik["id"] and gecmis[0]["kapanis_puani"] == 0.3 and gecmis[0]["checkin_sayisi"] == 1
    # Kapalı dönem raporu: PDF + CSV (puan sütunu).
    y = await istemci.get(f"{M}/donemler/{d['id']}/rapor.pdf", params={"dil": "ar"}, headers=b)
    assert y.status_code == 200 and y.content[:4] == b"%PDF"
    y = await istemci.get(f"{M}/donemler/{d['id']}/rapor.csv", headers=b)
    assert y.status_code == 200 and "Kapanış puanı" in y.text and "Müşteri memnuniyeti" in y.text and "0.3" in y.text


# ---------------------------------------------------------------------------
# Olaylar: tehlikede ve tamamlandı (geçişte bir kez)
# ---------------------------------------------------------------------------
async def test_olaylar_bir_kez(istemci, yonetici_basligi, db_oturumu, monkeypatch):
    from models.api_erisimi import WebhookTeslimatlari, WebhookUcNoktalari
    from services import webhook
    from services.api_erisimi import gizli_sakla

    monkeypatch.setattr(webhook, "ANLIK_TESLIMAT", False)
    uc = WebhookUcNoktalari(sahip_tur="ajans", hesap_email=None, url="https://kanca.ornek.com/okr",
                            olaylar=json.dumps(["okr.kr_riskte", "okr.hedef_tamamlandi"]), aktif=True,
                            gizli_anahtar=gizli_sakla("whsec_test"), ardisik_hata=0, tum_musteriler=False)
    db_oturumu.add(uc)
    await db_oturumu.commit()
    webhook.onbellegi_temizle()
    try:
        yb = yonetici_basligi
        d = await _post(istemci, f"{Y}/donemler", {"tur": "ozel", "baslangic": (_bugun() - timedelta(days=5)).isoformat(),
                                                   "bitis": (_bugun() + timedelta(days=5)).isoformat()}, yb)
        h = await _hedef(istemci, yb, d["id"], Y, baslik=f"Olay hedefi {uuid.uuid4().hex[:4]}")
        kr = await _kr(istemci, yb, h["id"], Y, baslangic=0, hedef=4)
        for deger, guven in ((1, "tehlikede"), (1, "tehlikede"), (2, "riskli"), (2, "tehlikede"), (4, "yolunda"), (3, None), (4, None)):
            await _post(istemci, f"{Y}/krler/{kr['id']}/checkin", {"deger": deger, **({"guven": guven} if guven else {})}, yb)
        teslimat = [x for x in (await db_oturumu.execute(select(WebhookTeslimatlari).where(WebhookTeslimatlari.uc_id == uc.id))).scalars().all()
                    if json.loads(x.govde)["veri"].get("hedef_id") == h["id"]]
        turler = [x.tur for x in sorted(teslimat, key=lambda x: x.id)]
        # Tehlikede: 1. check-in (geçiş) + 4. check-in (riskli'den yeniden geçiş). Tamamlandı: 5. (4/4) ve 7. (düşüp yeniden).
        assert turler.count("okr.kr_riskte") == 2 and turler.count("okr.hedef_tamamlandi") == 2, turler
        veri = json.loads(teslimat[0].govde)["veri"]
        assert veri["kr_id"] == kr["id"] and veri["guven"] == "tehlikede" and veri["ilerleme"] == 25.0
        from core.database import db_manager
        from services import otomasyon

        async with db_manager.async_session_maker() as db:
            bag = await otomasyon.baglam_kur(db, "okr.kr_riskte", veri, None, True)
            assert bag["okr"]["kr"] == kr["baslik"] and bag["okr"]["hedef_ilerleme"] == 100.0 and bag["okr"]["sahip"] == "yonetici@test.dev"
            assert await otomasyon.baglam_kur(db, "okr.kr_riskte", veri, "musteri@okr.dev", False) is None
    finally:
        uc.aktif = False
        await db_oturumu.commit()
        webhook.onbellegi_temizle()


# ---------------------------------------------------------------------------
# Haftalık hatırlatma (bir kez), zamanlı iş, haftalık özet
# ---------------------------------------------------------------------------
async def test_hatirlatma_bir_kez_ve_ozet(istemci, yonetici_basligi, db_oturumu):
    from models.notifications import Notifications
    from models.okr import OkrAnahtarSonuclar
    from services import haftalik_ozet as ho
    from services import okr_kayit

    e, b = await _musteri(istemci, yonetici_basligi, "hatir")
    d = await _donem(istemci, b)
    h = await _hedef(istemci, b, d["id"], baslik="Hatırlatma hedefi")
    elle = await _kr(istemci, b, h["id"], baslik="Haftalık satış görüşmesi", baslangic=0, hedef=10)
    yeni = await _kr(istemci, b, h["id"], baslik="Yeni check-in almış", baslangic=0, hedef=10)
    await _kr(istemci, b, h["id"], baslik="Bitmiş", baslangic=0, hedef=10, mevcut=10)
    taslak = await _hedef(istemci, b, d["id"], baslik="Taslak", durum="taslak")
    await _kr(istemci, b, taslak["id"], baslangic=0, hedef=10)
    an = datetime.now(UTC) + timedelta(days=8)
    satir = (await db_oturumu.execute(select(OkrAnahtarSonuclar).where(OkrAnahtarSonuclar.id == yeni["id"]))).scalars().one()
    satir.son_checkin_at = an - timedelta(days=1)
    await db_oturumu.commit()

    async def _sayi():
        return len([n for n in (await db_oturumu.execute(select(Notifications).where(Notifications.event_type == "okr_hatirlatma",
                                                                                     Notifications.recipient_email == e))).scalars().all()
                    if n.channel == "inapp"])

    once = await _sayi()
    assert await okr_kayit.hatirlatmalari_gonder(db_oturumu, an) >= 1
    assert await _sayi() == once + 1
    n = (await db_oturumu.execute(select(Notifications).where(Notifications.event_type == "okr_hatirlatma", Notifications.recipient_email == e)
                                  .order_by(Notifications.id.desc()))).scalars().first()
    assert "Haftalık satış görüşmesi" in (n.body or "") and "Yeni check-in almış" not in (n.body or "") and "Bitmiş" not in (n.body or "")
    # Aynı hafta ikinci tur: yeni bildirim yok. 7 gün sonra (hâlâ güncellenmemişse) yeniden.
    await okr_kayit.hatirlatmalari_gonder(db_oturumu, an + timedelta(hours=3))
    assert await _sayi() == once + 1
    await okr_kayit.hatirlatmalari_gonder(db_oturumu, an + timedelta(days=7, hours=1))
    assert await _sayi() == once + 2
    # Ajansın kendi bayat KR'si haftalık özette (müşterininki yok).
    yb = yonetici_basligi
    da = await _post(istemci, f"{Y}/donemler", {"tur": "ozel", "baslangic": (_bugun() - timedelta(days=30)).isoformat(),
                                                "bitis": (_bugun() + timedelta(days=60)).isoformat()}, yb)
    ha = await _hedef(istemci, yb, da["id"], Y, baslik="Ajans hedefi")
    await _kr(istemci, yb, ha["id"], Y, baslik="Ajansın bayat KR'si", baslangic=0, hedef=3)
    bolum = await ho._okr(db_oturumu, an)  # noqa: SLF001
    adlar = [x["ad"] for x in bolum["ornekler"]]
    assert bolum["anahtar"] == "okr" and bolum["sekme"] == "hedefler" and bolum["sayi"] >= 1
    assert "Haftalık satış görüşmesi" not in adlar
    tum = await okr_kayit.haftalik_ozet_satirlari(db_oturumu, an)
    assert any(x["kr"] == "Ajansın bayat KR'si" and x["gun"] >= 7 for x in tum)
    assert ho._satir_metni(ho._satir("X", tur="kr_guncellenmedi", gun=9)).endswith("9 gündür check-in yok")  # noqa: SLF001


async def test_zamanli_is_otomatik_kaynaklari_yeniler(istemci, yonetici_basligi, db_oturumu):
    from models.crm import CrmAdaylari
    from models.okr import OkrAnahtarSonuclar
    from services import zamanli

    yb = yonetici_basligi
    bugun = _bugun()
    d = await _post(istemci, f"{Y}/donemler", {"tur": "ozel", "baslangic": bugun.isoformat(), "bitis": (bugun + timedelta(days=3)).isoformat()}, yb)
    h = await _hedef(istemci, yb, d["id"], Y, baslik="Aday hedefi")
    kr = await _kr(istemci, yb, h["id"], Y, kaynak="crm_aday", baslangic=0, hedef=500)
    once = kr["mevcut"]
    db_oturumu.add(CrmAdaylari(ad="Zamanlı aday", asama="yeni", kaynak="manuel"))
    satir = (await db_oturumu.execute(select(OkrAnahtarSonuclar).where(OkrAnahtarSonuclar.id == kr["id"]))).scalars().one()
    satir.kaynak_son_yenileme = datetime.now(UTC) - timedelta(hours=2)
    await db_oturumu.commit()
    r = await zamanli.GOREVLER[zamanli.GOREV_ADLARI.index("okr_bakimi")].calistir(db_oturumu, True)
    assert r["yenilenen"] >= 1
    sonra = (await istemci.get(f"{Y}/hedefler/{h['id']}", headers=yb)).json()["krler"][0]
    assert sonra["mevcut"] >= once + 1 and sonra["kaynak_son_yenileme"]


# ---------------------------------------------------------------------------
# Çöp kutusu, odak, AI, rapor
# ---------------------------------------------------------------------------
async def test_cop_kutusu_odak_ai_ve_rapor(istemci, yonetici_basligi, db_oturumu, monkeypatch):
    from models.cop_kutusu import CopKutusu
    from models.okr import OkrCheckinler

    e, b = await _musteri(istemci, yonetici_basligi, "cop")
    d = await _donem(istemci, b)
    h = await _hedef(istemci, b, d["id"], baslik="Silinecek hedef")
    kr = await _kr(istemci, b, h["id"], baslangic=0, hedef=3)
    await _post(istemci, f"{M}/krler/{kr['id']}/checkin", {"deger": 1}, b)
    # Odak oturumu: not olarak (değer değişmez).
    r = await _post(istemci, f"{M}/krler/{kr['id']}/odak", {"sure_dk": 25, "notlar": "Rakip analizi"}, b)
    assert r["checkin"]["tur"] == "odak" and r["checkin"]["sure_dk"] == 25
    ay = (await istemci.get(f"{M}/hedefler/{h['id']}", headers=b)).json()
    assert ay["krler"][0]["mevcut"] == 1 and [c["tur"] for c in ay["krler"][0]["checkinler"]] == ["odak", "elle"]
    # AI önerisi: yapılandırılmamışsa düğme gizli (ai_hazir false) ve uç 503; sahte modelle öneri — kaydedilmez.
    from services import yapay_zeka

    monkeypatch.setattr(yapay_zeka, "sahte_ai_acik_mi", lambda: False)
    monkeypatch.delenv("APP_AI_BASE_URL", raising=False)
    monkeypatch.delenv("APP_AI_KEY", raising=False)
    assert (await istemci.get(f"{M}/meta", headers=b)).json()["ai_hazir"] is False
    y = await istemci.post(f"{M}/ai/kr-oner", json={"hedef_id": h["id"]}, headers=b)
    assert y.status_code == 503 and _kod(y) == "ai_kapali"
    monkeypatch.setattr(yapay_zeka, "sahte_ai_acik_mi", lambda: True)
    meta = (await istemci.get(f"{M}/meta", headers=b)).json()
    oneri = await _post(istemci, f"{M}/ai/kr-oner", {"hedef_id": h["id"], "sayi": 2}, b)
    assert meta["ai_hazir"] is True and len(oneri["oneriler"]) == 2 and all(o["baslik"] for o in oneri["oneriler"])
    assert len((await istemci.get(f"{M}/hedefler/{h['id']}", headers=b)).json()["krler"]) == 1
    # PDF (7 dil) ve CSV.
    for dil in ("tr", "en", "zh", "hi"):
        y = await istemci.get(f"{M}/donemler/{d['id']}/rapor.pdf", params={"dil": dil}, headers=b)
        assert y.status_code == 200 and y.headers["content-type"] == "application/pdf" and y.content[:4] == b"%PDF"
    y = await istemci.get(f"{M}/donemler/{d['id']}/rapor.csv", params={"dil": "en"}, headers=b)
    assert y.status_code == 200 and y.text.startswith("﻿Objective;") and "Silinecek hedef" in y.text
    # Hedef silinince KR'leri ve check-in'leri de çöpe; hepsi birlikte geri gelir.
    assert (await istemci.delete(f"{M}/hedefler/{h['id']}", headers=b)).status_code == 200
    assert (await istemci.get(f"{M}/hedefler/{h['id']}", headers=b)).status_code == 404
    cop = (await db_oturumu.execute(select(CopKutusu).where(CopKutusu.tablo.in_(("okr_hedefler", "okr_anahtar_sonuclar", "okr_checkinler")),
                                                            CopKutusu.sahip_email == e))).scalars().all()
    assert {c.tablo for c in cop} == {"okr_hedefler", "okr_anahtar_sonuclar", "okr_checkinler"}
    hedef_satiri = next(c for c in cop if c.tablo == "okr_hedefler")
    y = await istemci.post(f"/api/v1/cop-kutum/{hedef_satiri.id}/geri-al", headers=b)
    assert y.status_code == 200, y.text
    ay = (await istemci.get(f"{M}/hedefler/{h['id']}", headers=b)).json()
    assert ay["krler"][0]["mevcut"] == 1 and len(ay["krler"][0]["checkinler"]) == 2
    assert (await db_oturumu.execute(select(OkrCheckinler).where(OkrCheckinler.kr_id == kr["id"]))).scalars().all()
