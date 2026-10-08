"""Faz 6T — toplantılar: planlama, davet (ICS), girişsiz katılım yanıtı, hatırlatma, tutanak, takvim aboneliği.

Kapsam: yetki (anonim 401, müşteri 403 yönetici uçlarında), müşteri izolasyonu, PAYLAŞILMAMIŞ NOTUN hiçbir müşteri
ucundan sızmaması, dış katılımcı listesinin yalnız katılımcıya görünmesi, proje–müşteri uyuşmazlığı reddi, çakışma
uyarısı, ICS biçimi (CRLF, 75 sekizlik katlama — çok baytlı karakter bölünmeden, kaçış, UTC, SEQUENCE artışı, CANCEL),
imzalı yanıt (yanlış jeton, süresi dolmuş, iptal; ham jeton veritabanında yok), takvim akışı (yalnız kişinin
toplantıları, yeniden üretim / iptal sonrası 404, başlıklar), hatırlatmaların bir kez gitmesi, göreve dönüştürmenin tek
sefer olması, gelen kutusu kaynağı (`toplanti_talebi` → "Toplantı planla" → kapandı), otomasyon/webhook olayları,
erteleme / iptal davetleri, PDF (7 dil) + Markdown, çöp kutusu, haftalık özet ve kataloglar.
"""

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

Y = "/api/v1/toplantilar"
M = "/api/v1/toplantilarim"
YANIT = "/api/v1/toplanti-yanit"
AKIS = "/api/v1/toplanti-takvimi"
DILLER = ("tr", "en", "de", "ru", "zh", "hi", "ar")
I18N_EK = Path(__file__).resolve().parents[3] / "frontend" / "src" / "i18n" / "ek"


def _e(on: str = "m") -> str:
    return f"{on}-{uuid.uuid4().hex[:10]}@test.dev"


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


def _iso(an: datetime) -> str:
    return an.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@pytest.fixture(autouse=True)
def _sinirlar():
    from routers import toplantilar

    toplantilar.hiz_sinirlarini_temizle()
    yield


@pytest.fixture
def jetonlar(monkeypatch):
    """Davet e-postalarındaki ham yanıt jetonlarını yakalar (e-posta sağlayıcısı testte yok)."""
    from services import toplantilar as tp

    kayit = []
    asil = tp.jeton_uret

    def uret():
        ham, ozet = asil()
        kayit.append(ham)
        return ham, ozet

    monkeypatch.setattr(tp, "jeton_uret", uret)
    return kayit


@pytest.fixture
def ekler(monkeypatch):
    """`dispatch`'e giden e-posta eklerini (ICS) ve alıcıları yakalar; asıl dağıtım da çalışır."""
    from services import notify

    kayit = []
    asil = notify.dispatch

    async def sar(db, **kw):
        kayit.append({"olay": kw.get("event_type"), "alicilar": [a.get("email") for a in kw.get("recipients") or []],
                      "govde": kw.get("body"), "ekler": (kw.get("eposta_ek") or {}).get("ekler") or []})
        return await asil(db, **kw)

    monkeypatch.setattr(notify, "dispatch", sar)
    return kayit


async def _ekle(db, nesne):
    db.add(nesne)
    await db.commit()
    await db.refresh(nesne)
    return nesne


async def _personel(db, ad="Ece Ekip"):
    from models.staff import Staff

    s = await _ekle(db, Staff(ad=ad, email=_e("ekip"), rol="calisan", aktif=True))
    return s.email


async def _proje(db, musteri):
    from models.projects import Projects

    return await _ekle(db, Projects(title=f"Proje {uuid.uuid4().hex[:5]}", description="d", category="Website",
                                    client_email=musteri, client_name="Ada Kafe"))


async def _toplanti(istemci, yb, beklenen=200, **g):
    veri = {"baslik": "Haftalık durum", "baslangic": "2030-05-06T10:00", "sure_dk": 45, "yer_turu": "cevrimici",
            "baglanti": "https://meet.jit.si/mk-test", "gundem": ["Geçen hafta", "Bu hafta"], "katilimcilar": [], **g}
    y = await istemci.post(Y, json=veri, headers=yb)
    assert y.status_code == beklenen, y.text
    return y.json()


# ---------------------------------------------------------------------------
# Yetki
# ---------------------------------------------------------------------------
async def test_yetki_anonim_401_musteri_403(istemci, musteri_basligi):
    mb = musteri_basligi(_e())
    for metot, yol in (("GET", Y), ("POST", Y), ("GET", f"{Y}/meta"), ("GET", f"{Y}/1"), ("PUT", f"{Y}/1"),
                       ("DELETE", f"{Y}/1"), ("POST", f"{Y}/1/davet"), ("GET", f"{Y}/1/pdf"), ("GET", f"{Y}/talepler"),
                       ("POST", f"{Y}/aksiyonlar/1/gorev"), ("GET", f"{Y}/abonelikler"), ("POST", f"{Y}/cakisma")):
        kw = {} if metot in ("GET", "DELETE") else {"json": {}}
        assert (await istemci.request(metot, yol, **kw)).status_code == 401, (metot, yol)
        assert (await istemci.request(metot, yol, headers=mb, **kw)).status_code == 403, (metot, yol)
    for metot, yol in (("GET", M), ("GET", f"{M}/ozet"), ("GET", f"{M}/1"), ("POST", f"{M}/talepler"),
                       ("GET", f"{M}/takvim"), ("POST", f"{M}/1/yanit")):
        kw = {} if metot == "GET" else {"json": {}}
        assert (await istemci.request(metot, yol, **kw)).status_code == 401, (metot, yol)


# ---------------------------------------------------------------------------
# Oluşturma, doğrulama, çakışma
# ---------------------------------------------------------------------------
async def test_olustur_istanbul_saati_utc_saklanir_ve_proje_musteri_uyusmazligi(istemci, yonetici_basligi, db_oturumu):
    yb = yonetici_basligi
    a, b = _e("a"), _e("b")
    pa = await _proje(db_oturumu, a)
    t = await _toplanti(istemci, yb, hesap_email=a, proje_id=pa.id)
    # 10:00 İstanbul (UTC+3) → 07:00Z
    assert t["baslangic"] == "2030-05-06T07:00:00Z" and t["bitis"] == "2030-05-06T07:45:00Z"
    assert t["hesap_email"] == a and t["proje"]["id"] == pa.id and t["gundem"] == ["Geçen hafta", "Bu hafta"]
    # Proje başka müşterinin → 400
    y = await istemci.post(Y, json={"baslik": "X", "baslangic": "2030-05-06T10:00", "hesap_email": b, "proje_id": pa.id},
                           headers=yb)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "proje_musteri_uyusmuyor"
    # Müşteri seçilmeden proje → projenin müşterisi alınır
    t2 = await _toplanti(istemci, yb, proje_id=pa.id)
    assert t2["hesap_email"] == a
    # Düzenlemede de denetlenir
    y = await istemci.put(f"{Y}/{t['id']}", json={"hesap_email": b}, headers=yb)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "proje_musteri_uyusmuyor"
    # Doğrulamalar
    for govde, kod in (({"baslik": ""}, "baslik_gecersiz"), ({"baslangic": "dün"}, "baslangic_gecersiz"),
                       ({"sure_dk": 1}, "sure_gecersiz"), ({"yer_turu": "uzay"}, "yer_turu_gecersiz"),
                       ({"baglanti": "javascript:alert(1)"}, "baglanti_gecersiz"),
                       ({"yer_turu": "yuz_yuze", "adres": ""}, "adres_gerekli"),
                       ({"katilimcilar": [{"eposta": "bozuk"}]}, "katilimci_gecersiz"),
                       ({"katilimcilar": [{"eposta": _e(), "tur": "ekip"}]}, "ekip_gecersiz")):
        y = await istemci.post(Y, json={"baslik": "T", "baslangic": "2030-05-06T10:00", **govde}, headers=yb)
        assert y.status_code == 400 and y.json()["detail"]["kod"] == kod, (govde, y.text)
    # Ofsetli değer olduğu gibi (UTC'ye çevrilir)
    t3 = await _toplanti(istemci, yb, baslangic="2030-05-06T10:00:00Z")
    assert t3["baslangic"] == "2030-05-06T10:00:00Z"


async def test_ekip_uyesi_cakismasi_uyarir(istemci, yonetici_basligi, db_oturumu):
    yb = yonetici_basligi
    ekip = await _personel(db_oturumu)
    t1 = await _toplanti(istemci, yb, baslangic="2031-01-10T10:00", sure_dk=60,
                         katilimcilar=[{"eposta": ekip, "tur": "ekip"}])
    assert t1["cakismalar"] == [] and t1["katilimcilar"][0]["ad"] == "Ece Ekip"
    t2 = await _toplanti(istemci, yb, baslangic="2031-01-10T10:30", sure_dk=30,
                         katilimcilar=[{"eposta": ekip, "tur": "ekip"}, {"eposta": _e("dis")}])
    assert [c["toplanti_id"] for c in t2["cakismalar"]] == [t1["id"]] and t2["cakismalar"][0]["eposta"] == ekip
    # Bitişik (11:00) çakışma değil; canlı denetim ucu
    y = await istemci.post(f"{Y}/cakisma", json={"baslangic": "2031-01-10T11:00", "sure_dk": 30, "ekip": [ekip]}, headers=yb)
    assert y.status_code == 200 and all(c["toplanti_id"] != t1["id"] for c in y.json()["cakismalar"])
    y = await istemci.post(f"{Y}/cakisma", json={"baslangic": "2031-01-10T10:15", "sure_dk": 20, "ekip": [ekip],
                                                 "haric_id": t1["id"]}, headers=yb)
    assert [c["toplanti_id"] for c in y.json()["cakismalar"]] == [t2["id"]]
    # İptal edilen toplantı çakışma sayılmaz
    await istemci.post(f"{Y}/{t1['id']}/iptal", json={"neden": "Gerek kalmadı"}, headers=yb)
    y = await istemci.post(f"{Y}/cakisma", json={"baslangic": "2031-01-10T10:00", "sure_dk": 20, "ekip": [ekip]}, headers=yb)
    assert all(c["toplanti_id"] != t1["id"] for c in y.json()["cakismalar"])


# ---------------------------------------------------------------------------
# ICS
# ---------------------------------------------------------------------------
def _satirlar(ics: str):
    assert ics.endswith("\r\n") and "\n" not in ics.replace("\r\n", "")
    fiziksel = ics.split("\r\n")[:-1]
    for s in fiziksel:
        assert len(s.encode("utf-8")) <= 75, s
        s.encode("utf-8").decode("utf-8")  # çok baytlı karakter bölünmemiş
    mantiksal = []
    for s in fiziksel:
        if s.startswith(" "):
            mantiksal[-1] += s[1:]
        else:
            mantiksal.append(s)
    return mantiksal


def _alan(satirlar, ad):
    return [s.split(":", 1)[1] for s in satirlar if s.split(":", 1)[0].split(";", 1)[0] == ad]


async def test_ics_bicimi_katlama_kacis_utc_sequence_ve_cancel(istemci, yonetici_basligi, db_oturumu, ekler, jetonlar):
    from services import toplantilar as tp

    yb = yonetici_basligi
    baslik = "Çeyrek planı; bütçe, içerik\\SEO ve ğüşıöç ünlü harfli uzun başlık — " + "Ş" * 40
    t = await _toplanti(istemci, yb, baslik=baslik, gundem=["Satır 1\nSatır 2"],
                        katilimcilar=[{"eposta": _e("k1"), "ad": "Zeynep, Kaya"}])
    y = await istemci.get(f"{Y}/{t['id']}/ics", headers=yb)
    assert y.status_code == 200 and y.headers["content-type"].startswith("text/calendar")
    s = _satirlar(y.text)
    assert s[0] == "BEGIN:VCALENDAR" and "METHOD:PUBLISH" in s and s[-1] == "END:VCALENDAR"
    ozet = _alan(s, "SUMMARY")[0]
    assert ozet.startswith("Çeyrek planı\\; bütçe\\, içerik\\\\SEO") and ozet.endswith("Ş" * 40)
    assert "\\n" in _alan(s, "DESCRIPTION")[0]
    assert _alan(s, "DTSTART")[0] == "20300506T070000Z" and _alan(s, "DTEND")[0] == "20300506T074500Z"
    assert re.fullmatch(r"\d{8}T\d{6}Z", _alan(s, "DTSTAMP")[0])
    uid = _alan(s, "UID")[0]
    assert uid.startswith("toplanti-") and uid.endswith("@mehmetkuru.dev") and _alan(s, "SEQUENCE") == ["0"]
    # Davet: METHOD:REQUEST, ORGANIZER + ATTENDEE (PARTSTAT=NEEDS-ACTION)
    y = await istemci.post(f"{Y}/{t['id']}/davet", json={}, headers=yb)
    assert y.status_code == 200 and y.json()["davet"]["gonderilen"] == 1
    davet = [e for e in ekler if e["olay"] == "toplanti_davet"][-1]
    ek = davet["ekler"][0]
    assert ek["tur"].startswith("text/calendar; method=REQUEST")
    s = _satirlar(ek["icerik"])
    assert "METHOD:REQUEST" in s and _alan(s, "UID") == [uid] and _alan(s, "SEQUENCE") == ["0"]
    assert any(x.startswith("ORGANIZER;") for x in s)
    att = [x for x in s if x.startswith("ATTENDEE;")]
    assert len(att) == 1 and "PARTSTAT=NEEDS-ACTION" in att[0] and 'CN="Zeynep, Kaya"' in att[0]
    # Saat değişince SEQUENCE +1, güncelleme bekliyor
    y = await istemci.put(f"{Y}/{t['id']}", json={"baslangic": "2030-05-06T11:00"}, headers=yb)
    assert y.json()["sira_no"] == 1 and y.json()["guncelleme_bekliyor"] is True
    y = await istemci.post(f"{Y}/{t['id']}/davet", json={}, headers=yb)
    assert y.json()["davet"]["guncelleme"] is True and y.json()["guncelleme_bekliyor"] is False
    s = _satirlar([e for e in ekler if e["olay"] == "toplanti_davet"][-1]["ekler"][0]["icerik"])
    assert _alan(s, "SEQUENCE") == ["1"] and _alan(s, "DTSTART") == ["20300506T080000Z"] and _alan(s, "UID") == [uid]
    # Yalnız başlık değişince SEQUENCE değişmez
    y = await istemci.put(f"{Y}/{t['id']}", json={"baslik": "Yeni başlık"}, headers=yb)
    assert y.json()["sira_no"] == 1
    # İptal: METHOD:CANCEL, STATUS:CANCELLED, SEQUENCE +1 (neden zorunlu)
    y = await istemci.post(f"{Y}/{t['id']}/iptal", json={}, headers=yb)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "neden_gerekli"
    y = await istemci.post(f"{Y}/{t['id']}/iptal", json={"neden": "Müşteri; ertelemek istedi"}, headers=yb)
    assert y.status_code == 200 and y.json()["durum"] == "iptal" and y.json()["iptal_bildirimi"]["gonderilen"] == 1
    iptal = [e for e in ekler if e["olay"] == "toplanti_iptal"][-1]
    assert iptal["ekler"][0]["tur"].startswith("text/calendar; method=CANCEL")
    s = _satirlar(iptal["ekler"][0]["icerik"])
    assert "METHOD:CANCEL" in s and "STATUS:CANCELLED" in s and _alan(s, "SEQUENCE") == ["2"] and _alan(s, "UID") == [uid]
    # Ortak yardımcı: katlama 75 sekizlik sınırında çok baytlı harfi bölmüyor
    katli = tp._katla("SUMMARY:" + "ğ" * 60)  # noqa: SLF001
    assert all(len(p.encode()) <= 75 for p in katli.split("\r\n")) and katli.replace("\r\n ", "") == "SUMMARY:" + "ğ" * 60
    # İptal edilmiş toplantıya davet gitmez
    y = await istemci.post(f"{Y}/{t['id']}/davet", json={}, headers=yb)
    assert y.status_code == 409


# ---------------------------------------------------------------------------
# Girişsiz katılım yanıtı
# ---------------------------------------------------------------------------
async def test_imzali_yanit_jeton_suresi_iptal_ve_ham_jeton_saklanmaz(istemci, yonetici_basligi, db_oturumu, jetonlar):
    from models.notifications import Notifications
    from models.toplantilar import ToplantiKatilimcilari, Toplantilar

    yb = yonetici_basligi
    dis = _e("dis")
    t = await _toplanti(istemci, yb, baslangic=_iso(_simdi() + timedelta(days=3)), katilimcilar=[{"eposta": dis, "ad": "Ali"}])
    assert (await istemci.post(f"{Y}/{t['id']}/davet", json={}, headers=yb)).status_code == 200
    ham = jetonlar[-1]
    # Ham jeton veritabanında yok: yalnız özet; bildirim kayıtlarında da yok.
    k = (await db_oturumu.execute(select(ToplantiKatilimcilari).where(ToplantiKatilimcilari.eposta == dis))).scalars().first()
    assert k.yanit_jeton_ozeti and k.yanit_jeton_ozeti != ham and len(k.yanit_jeton_ozeti) == 64
    satirlar = (await db_oturumu.execute(select(Notifications).where(Notifications.recipient_email == dis))).scalars().all()
    assert satirlar and all(ham not in (s.body or "") + (s.link or "") + (s.title or "") for s in satirlar)
    assert any("…" in (s.body or "") and "toplanti-yanit" not in (s.body or "") for s in satirlar)
    # GET özet (başlıklar: noindex, no-store, no-referrer; diğer katılımcı yok; e-posta maskeli)
    y = await istemci.get(f"{YANIT}/{ham}")
    assert y.status_code == 200 and "noindex" in y.headers["x-robots-tag"] and y.headers["cache-control"] == "no-store"
    assert y.headers["referrer-policy"] == "no-referrer"
    assert y.json()["baslik"] == "Haftalık durum" and y.json()["eposta"].startswith("d***@") and "katilimcilar" not in y.json()
    # Yanlış jeton → 404; geçersiz yanıt → 400
    assert (await istemci.get(f"{YANIT}/yanlis-jeton")).status_code == 404
    assert (await istemci.post(YANIT, json={"jeton": "yanlis", "yanit": "katilacak"})).status_code == 404
    assert (await istemci.post(YANIT, json={"jeton": ham, "yanit": "bekliyor"})).status_code == 400
    # Yanıt + not → yönetici katılımcı satırında görür
    y = await istemci.post(YANIT, json={"jeton": ham, "yanit": "belki", "not": "Trafik olabilir"})
    assert y.status_code == 200 and y.json()["yanit"] == "belki"
    d = (await istemci.get(f"{Y}/{t['id']}", headers=yb)).json()
    kat = d["katilimcilar"][0]
    assert kat["yanit"] == "belki" and kat["yanit_notu"] == "Trafik olabilir" and kat["yanit_kaynagi"] == "baglanti"
    assert d["yanitlar"]["belki"] == 1
    # Yeniden davet → eski bağlantı geçersiz (jeton yenilenir)
    await istemci.post(f"{Y}/{t['id']}/davet", json={}, headers=yb)
    assert (await istemci.get(f"{YANIT}/{ham}")).status_code == 404
    ham2 = jetonlar[-1]
    assert (await istemci.get(f"{YANIT}/{ham2}")).status_code == 200
    # Toplantı bitti → 410 suresi_doldu
    tt = (await db_oturumu.execute(select(Toplantilar).where(Toplantilar.id == t["id"]))).scalars().first()
    tt.baslangic = _simdi() - timedelta(hours=3)
    await db_oturumu.commit()
    y = await istemci.post(YANIT, json={"jeton": ham2, "yanit": "katilacak"})
    assert y.status_code == 410 and y.json()["detail"]["kod"] == "suresi_doldu"
    # İptal → 410 iptal
    tt.baslangic = _simdi() + timedelta(days=2)
    await db_oturumu.commit()
    await istemci.post(f"{Y}/{t['id']}/iptal", json={"neden": "Hastalık"}, headers=yb)
    y = await istemci.get(f"{YANIT}/{ham2}")
    assert y.status_code == 410 and y.json()["detail"]["kod"] == "iptal"


# ---------------------------------------------------------------------------
# Müşteri: izolasyon, gizlilik, paylaşım
# ---------------------------------------------------------------------------
GIZLI = "GIZLI-EKIP-NOTU-7Q"


async def test_musteri_izolasyonu_ve_paylasilmamis_not_hicbir_uctan_sizmaz(istemci, yonetici_basligi, musteri_basligi,
                                                                            db_oturumu, ekler):
    yb = yonetici_basligi
    a, b, dis = _e("a"), _e("b"), _e("dis")
    ekip = await _personel(db_oturumu, "Mert Ekip")
    pa = await _proje(db_oturumu, a)
    t = await _toplanti(istemci, yb, hesap_email=a, proje_id=pa.id,
                        katilimcilar=[{"eposta": ekip, "tur": "ekip"}, {"eposta": dis, "ad": "Dış Kişi"}])
    tb = await _toplanti(istemci, yb, hesap_email=b, baslik="B toplantısı")
    y = await istemci.put(f"{Y}/{t['id']}/tutanak", json={"notlar": f"## İç\n{GIZLI} fiyatı düşürmeyelim",
                                                          "kararlar": [f"Karar {GIZLI}"]}, headers=yb)
    assert y.status_code == 200 and GIZLI in y.json()["notlar_html"]
    for govde in ({"metin": "Logo dosyalarını gönder", "sorumlu_tur": "musteri"},
                  {"metin": f"İç iş {GIZLI}", "sorumlu_tur": "ekip", "sorumlu_eposta": ekip}):
        assert (await istemci.post(f"{Y}/{t['id']}/aksiyonlar", json=govde, headers=yb)).status_code == 200
    ma, mb = musteri_basligi(a), musteri_basligi(b)
    # İzolasyon
    liste_a = (await istemci.get(M, headers=ma)).json()["items"]
    assert [x["id"] for x in liste_a] == [t["id"]]
    liste_b = (await istemci.get(M, headers=mb)).json()["items"]
    assert [x["id"] for x in liste_b] == [tb["id"]]
    assert (await istemci.get(f"{M}/{t['id']}", headers=mb)).status_code == 404
    assert (await istemci.get(f"{M}/{t['id']}/ics", headers=mb)).status_code == 404
    # Paylaşılmamış not / karar / ekip aksiyonu HİÇBİR müşteri ucunda yok
    yanitlar = [await istemci.get(M, headers=ma), await istemci.get(f"{M}/{t['id']}", headers=ma),
                await istemci.get(f"{M}/{t['id']}/ics", headers=ma), await istemci.get(f"{M}/ozet", headers=ma),
                await istemci.get(f"{M}/{t['id']}/pdf", headers=ma), await istemci.get(f"{M}/{t['id']}/md", headers=ma)]
    for r in yanitlar:
        assert GIZLI not in r.text, r.request.url
    assert yanitlar[4].status_code == 404 and yanitlar[5].status_code == 404
    d = yanitlar[1].json()
    assert d["notlar_html"] is None and d["kararlar"] == [] and [x["metin"] for x in d["aksiyonlar"]] == ["Logo dosyalarını gönder"]
    # Dış katılımcılar yalnız katılımcıya: A katılımcı değil → yalnız ekip (adı; e-postası yok) + sayı
    assert d["katilimci_miyim"] is False and d["dis_sayisi"] == 1
    assert [k["tur"] for k in d["katilimcilar"]] == ["ekip"] and "eposta" not in d["katilimcilar"][0]
    assert dis not in yanitlar[1].text and ekip not in yanitlar[1].text
    # A katılımcı olunca dış listeyi görür
    await istemci.put(f"{Y}/{t['id']}", json={"katilimcilar": [{"eposta": ekip, "tur": "ekip"}, {"eposta": dis}, {"eposta": a}]},
                      headers=yb)
    d = (await istemci.get(f"{M}/{t['id']}", headers=ma)).json()
    assert d["katilimci_miyim"] is True and {k.get("eposta") for k in d["katilimcilar"] if k["tur"] == "dis"} == {dis, a}
    # Müşteri panelinden yanıt (katılımcı değilse 403)
    y = await istemci.post(f"{M}/{t['id']}/yanit", json={"yanit": "katilacak"}, headers=ma)
    assert y.status_code == 200 and y.json()["yanit"] == "katilacak"
    y = await istemci.post(f"{M}/{tb['id']}/yanit", json={"yanit": "katilacak"}, headers=mb)
    assert y.status_code == 403 and y.json()["detail"]["kod"] == "katilimci_degil"
    # Paylaş → müşteri görür + bildirim (hesaba)
    y = await istemci.post(f"{Y}/{t['id']}/paylas", json={"paylas": True}, headers=yb)
    assert y.status_code == 200 and y.json()["notlar_paylasildi"] is True
    assert any(e["olay"] == "toplanti_notlari" and e["alicilar"] == [a] for e in ekler)
    d = (await istemci.get(f"{M}/{t['id']}", headers=ma)).json()
    assert GIZLI in d["notlar_html"] and d["kararlar"] == [f"Karar {GIZLI}"] and len(d["aksiyonlar"]) == 2
    y = await istemci.get(f"{M}/{t['id']}/md", headers=ma)
    assert y.status_code == 200 and GIZLI in y.text
    y = await istemci.get(f"{M}/{t['id']}/pdf?dil=en", headers=ma)
    assert y.status_code == 200 and y.content.startswith(b"%PDF")
    # Paylaşım geri alınınca yine sızmaz; müşterisiz toplantıda paylaşım yok
    await istemci.post(f"{Y}/{t['id']}/paylas", json={"paylas": False}, headers=yb)
    assert GIZLI not in (await istemci.get(f"{M}/{t['id']}", headers=ma)).text
    y = await istemci.post(f"{Y}/{(await _toplanti(istemci, yb))['id']}/paylas", json={"paylas": True}, headers=yb)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "musteri_yok"


async def test_musteri_aksiyonu_tamamlar_ekip_aksiyonunu_isaretleyemez(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    yb = yonetici_basligi
    a, baska = _e("a"), _e("baska")
    t = await _toplanti(istemci, yb, hesap_email=a)
    ma = (await istemci.post(f"{Y}/{t['id']}/aksiyonlar", json={"metin": "İçerik metni", "sorumlu_tur": "musteri"},
                             headers=yb)).json()
    me = (await istemci.post(f"{Y}/{t['id']}/aksiyonlar", json={"metin": "İç iş", "sorumlu_tur": "ekip"}, headers=yb)).json()
    y = await istemci.post(f"{M}/aksiyonlar/{ma['id']}/tamamla", json={"tamam": True}, headers=musteri_basligi(a))
    assert y.status_code == 200 and y.json()["durum"] == "tamamlandi"
    d = (await istemci.get(f"{Y}/{t['id']}", headers=yb)).json()
    assert next(x for x in d["aksiyonlar"] if x["id"] == ma["id"])["tamamlayan_eposta"] == a
    assert (await istemci.post(f"{M}/aksiyonlar/{me['id']}/tamamla", json={}, headers=musteri_basligi(a))).status_code == 404
    assert (await istemci.post(f"{M}/aksiyonlar/{ma['id']}/tamamla", json={}, headers=musteri_basligi(baska))).status_code == 404
    # Müşterisiz toplantıda müşteri tarafı aksiyon yok
    t2 = await _toplanti(istemci, yb)
    y = await istemci.post(f"{Y}/{t2['id']}/aksiyonlar", json={"metin": "X", "sorumlu_tur": "musteri"}, headers=yb)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "musteri_yok"


# ---------------------------------------------------------------------------
# Göreve dönüştürme
# ---------------------------------------------------------------------------
async def test_goreve_donustur_tek_sefer(istemci, yonetici_basligi, db_oturumu):
    from models.proje_gorevleri import ProjectTasks

    yb = yonetici_basligi
    a = _e("a")
    ekip = await _personel(db_oturumu)
    p = await _proje(db_oturumu, a)
    t = await _toplanti(istemci, yb, hesap_email=a, proje_id=p.id)
    ak = (await istemci.post(f"{Y}/{t['id']}/aksiyonlar", json={"metin": "Ana sayfa taslağı", "sorumlu_tur": "ekip",
                                                               "sorumlu_eposta": ekip, "son_tarih": "2030-06-01"},
                             headers=yb)).json()
    y = await istemci.post(f"{Y}/aksiyonlar/{ak['id']}/gorev", headers=yb)
    assert y.status_code == 200, y.text
    g = (await db_oturumu.execute(select(ProjectTasks).where(ProjectTasks.id == y.json()["gorev_id"]))).scalars().first()
    assert g.proje_id == p.id and g.baslik == "Ana sayfa taslağı" and g.atanan == ekip and str(g.bitis_tarihi) == "2030-06-01"
    assert json.loads(g.etiketler) == ["toplanti"] and g.musteriye_gorunur is False
    y = await istemci.post(f"{Y}/aksiyonlar/{ak['id']}/gorev", headers=yb)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "zaten_gorev"
    adet = (await db_oturumu.execute(select(ProjectTasks).where(ProjectTasks.proje_id == p.id))).scalars().all()
    assert len(adet) == 1
    d = (await istemci.get(f"{Y}/{t['id']}", headers=yb)).json()
    assert d["aksiyonlar"][0]["gorev_id"] == g.id
    # Projesiz toplantıda dönüştürme yok
    t2 = await _toplanti(istemci, yb)
    ak2 = (await istemci.post(f"{Y}/{t2['id']}/aksiyonlar", json={"metin": "X"}, headers=yb)).json()
    y = await istemci.post(f"{Y}/aksiyonlar/{ak2['id']}/gorev", headers=yb)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "proje_yok"


# ---------------------------------------------------------------------------
# Takvim aboneliği
# ---------------------------------------------------------------------------
async def test_takvim_akisi_yalniz_kisinin_toplantilari_ve_iptal_sonrasi_404(istemci, yonetici_basligi, musteri_basligi,
                                                                             db_oturumu):
    from models.toplantilar import ToplantiTakvimAbonelikleri

    yb = yonetici_basligi
    a, b = _e("a"), _e("b")
    ta = await _toplanti(istemci, yb, hesap_email=a, baslik="A ile", katilimcilar=[{"eposta": a}])
    tb = await _toplanti(istemci, yb, hesap_email=b, baslik="B ile", katilimcilar=[{"eposta": b}])
    ti = await _toplanti(istemci, yb, hesap_email=a, baslik="A iptal", katilimcilar=[{"eposta": a}])
    await istemci.post(f"{Y}/{ti['id']}/iptal", json={"neden": "x"}, headers=yb)
    ma = musteri_basligi(a)
    assert (await istemci.get(f"{M}/takvim", headers=ma)).json() == {"var": False}
    y = await istemci.post(f"{M}/takvim", headers=ma)
    assert y.status_code == 200 and y.json()["var"] is True and y.headers["cache-control"] == "no-store"
    adres = y.json()["adres"]
    assert adres.startswith("https://mehmetkuru.dev/api/v1/toplanti-takvimi/") and adres.endswith(".ics")
    ham = adres.rsplit("/", 1)[1][:-4]
    satir = (await db_oturumu.execute(select(ToplantiTakvimAbonelikleri).where(ToplantiTakvimAbonelikleri.kisi_email == a))).scalars().first()
    assert satir.jeton_ozeti != ham and len(satir.jeton_ozeti) == 64
    y = await istemci.get(f"{AKIS}/{ham}.ics")
    assert y.status_code == 200 and y.headers["content-type"].startswith("text/calendar")
    assert y.headers["cache-control"].startswith("private") and "noindex" in y.headers["x-robots-tag"]
    s = _satirlar(y.text)
    ozetler = _alan(s, "SUMMARY")
    assert "A ile" in ozetler and "B ile" not in ozetler and "A iptal" in ozetler
    assert "STATUS:CANCELLED" in s and "METHOD:PUBLISH" in s and not any(x.startswith("ATTENDEE") for x in s)
    assert tb["id"] and ta["id"]
    # Yeniden üret → eski adres 404, yeni çalışır; iptal → 404
    y2 = await istemci.post(f"{M}/takvim", headers=ma)
    ham2 = y2.json()["adres"].rsplit("/", 1)[1][:-4]
    assert (await istemci.get(f"{AKIS}/{ham}.ics")).status_code == 404
    assert (await istemci.get(f"{AKIS}/{ham2}.ics")).status_code == 200
    assert (await istemci.delete(f"{M}/takvim", headers=ma)).json() == {"iptal": True}
    assert (await istemci.get(f"{AKIS}/{ham2}.ics")).status_code == 404
    # Ekip üyesi aboneliği (yönetici üretir); ekip dışı adres reddedilir
    ekip = await _personel(db_oturumu)
    await _toplanti(istemci, yb, baslik="Ekip toplantısı", katilimcilar=[{"eposta": ekip, "tur": "ekip"}])
    y = await istemci.post(f"{Y}/abonelikler", json={"eposta": ekip}, headers=yb)
    assert y.status_code == 200
    ozetler = _alan(_satirlar((await istemci.get(f"{AKIS}/{y.json()['adres'].rsplit('/', 1)[1][:-4]}.ics")).text), "SUMMARY")
    assert ozetler == ["Ekip toplantısı"]
    assert (await istemci.post(f"{Y}/abonelikler", json={"eposta": _e("yabanci")}, headers=yb)).status_code == 400
    liste = (await istemci.get(f"{Y}/abonelikler", headers=yb)).json()["items"]
    assert next(x for x in liste if x["email"] == ekip)["var"] is True
    assert (await istemci.post(f"{Y}/abonelikler/iptal", json={"eposta": ekip}, headers=yb)).json() == {"iptal": True}


# ---------------------------------------------------------------------------
# Hatırlatmalar
# ---------------------------------------------------------------------------
async def test_hatirlatmalar_bir_kez(istemci, yonetici_basligi, db_oturumu, ekler):
    from models.toplantilar import Toplantilar
    from services import toplantilar as tp
    from services import zamanli

    yb = yonetici_basligi
    k1, k2, red = _e("k1"), _e("k2"), _e("red")
    t = await _toplanti(istemci, yb, baslangic=_iso(_simdi() + timedelta(hours=20)),
                        katilimcilar=[{"eposta": k1}, {"eposta": k2}, {"eposta": red}])
    # Davet gitmeden hatırlatma yok
    once = len([e for e in ekler if e["olay"] == "toplanti_hatirlatma"])
    await tp.hatirlatmalari_gonder(db_oturumu)
    assert len([e for e in ekler if e["olay"] == "toplanti_hatirlatma"]) == once
    await istemci.post(f"{Y}/{t['id']}/davet", json={}, headers=yb)
    d = (await istemci.get(f"{Y}/{t['id']}", headers=yb)).json()
    # "Katılamayacak" diyene hatırlatma gitmez
    from models.toplantilar import ToplantiKatilimcilari

    kr = (await db_oturumu.execute(select(ToplantiKatilimcilari).where(ToplantiKatilimcilari.eposta == red))).scalars().first()
    kr.yanit = "katilamayacak"
    await db_oturumu.commit()

    def sayi(eposta):
        return len([e for e in ekler if e["olay"] == "toplanti_hatirlatma" and e["alicilar"] == [eposta]])

    await tp.hatirlatmalari_gonder(db_oturumu)
    await tp.hatirlatmalari_gonder(db_oturumu)
    assert sayi(k1) == 1 and sayi(k2) == 1 and sayi(red) == 0
    # Zamanlı iş kaydında; 1 saat kala yalnız 1 saatlik hatırlatma, o da bir kez
    assert "toplanti_hatirlatmalari" in zamanli.GOREV_ADLARI and zamanli.GOREV_ADLARI[-1] == "aylik_site_analizi"
    gorev = next(g for g in zamanli.GOREVLER if g.ad == "toplanti_hatirlatmalari")
    tt = (await db_oturumu.execute(select(Toplantilar).where(Toplantilar.id == t["id"]))).scalars().first()
    tt.baslangic = _simdi() + timedelta(minutes=50)
    await db_oturumu.commit()
    s1 = await gorev.calistir(db_oturumu, True)
    s2 = await gorev.calistir(db_oturumu, True)
    assert s1["hatirlatma_1"] == 2 and s2["hatirlatma_1"] == 0 and s1["hatirlatma_24"] == 0
    assert sayi(k1) == 2 and sayi(k2) == 2
    assert d["katilimcilar"][0]["hatirlatma_24_at"] is None


# ---------------------------------------------------------------------------
# Erteleme, yapıldı
# ---------------------------------------------------------------------------
async def test_erteleme_sequence_yanitlari_sifirlar_ve_guncelleme_daveti(istemci, yonetici_basligi, ekler, jetonlar):
    yb = yonetici_basligi
    k = _e("k")
    t = await _toplanti(istemci, yb, baslangic=_iso(_simdi() + timedelta(days=5)), katilimcilar=[{"eposta": k}])
    await istemci.post(f"{Y}/{t['id']}/davet", json={}, headers=yb)
    await istemci.post(YANIT, json={"jeton": jetonlar[-1], "yanit": "katilacak"})
    yeni = _simdi() + timedelta(days=7)
    y = await istemci.post(f"{Y}/{t['id']}/ertele", json={"baslangic": _iso(yeni)}, headers=yb)
    assert y.status_code == 200, y.text
    d = y.json()
    assert d["durum"] == "ertelendi" and d["sira_no"] == 1 and d["davet"]["guncelleme"] is True
    assert d["katilimcilar"][0]["yanit"] == "bekliyor" and d["kategori"] == "yaklasan"
    s = _satirlar([e for e in ekler if e["olay"] == "toplanti_davet"][-1]["ekler"][0]["icerik"])
    assert _alan(s, "SEQUENCE") == ["1"] and _alan(s, "DTSTART") == [yeni.strftime("%Y%m%dT%H%M%SZ")]
    y = await istemci.post(f"{Y}/{t['id']}/ertele", json={"baslangic": _iso(yeni)}, headers=yb)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "tarih_ayni"
    # Henüz başlamamış toplantı "yapıldı" olamaz
    y = await istemci.post(f"{Y}/{t['id']}/yapildi", headers=yb)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "henuz_baslamadi"


# ---------------------------------------------------------------------------
# Gelen kutusu: toplantı talebi
# ---------------------------------------------------------------------------
async def test_musteri_toplanti_talebi_gelen_kutusunda_ve_planlaninca_kapanir(istemci, yonetici_basligi, musteri_basligi, ekler):
    yb = yonetici_basligi
    a = _e("talep")
    ma = musteri_basligi(a)
    bas = _simdi() + timedelta(days=2)
    araliklar = [{"bas": _iso(bas), "bit": _iso(bas + timedelta(hours=2))}]
    for govde, kod in (({"konu": "", "araliklar": araliklar}, "konu_gecersiz"), ({"konu": "X", "araliklar": []}, "aralik_gerekli"),
                       ({"konu": "X", "araliklar": araliklar * 4}, "aralik_cok"),
                       ({"konu": "X", "araliklar": [{"bas": _iso(bas), "bit": _iso(bas - timedelta(hours=1))}]}, "aralik_gecersiz"),
                       ({"konu": "X", "araliklar": [{"bas": _iso(_simdi() - timedelta(days=1, hours=2)),
                                                     "bit": _iso(_simdi() - timedelta(days=1))}]}, "aralik_gecmis")):
        y = await istemci.post(f"{M}/talepler", json=govde, headers=ma)
        assert y.status_code == 400 and y.json()["detail"]["kod"] == kod, (govde, y.text)
    y = await istemci.post(f"{M}/talepler", json={"konu": "Kampanya planı", "araliklar": araliklar, "not": "Öğleden sonra"},
                           headers=ma)
    assert y.status_code == 200, y.text
    talep = y.json()
    assert any(e["olay"] == "toplanti_talebi" for e in ekler)
    assert (await istemci.get(f"{M}/ozet", headers=ma)).json()["talep"] == 1
    # Gelen kutusu
    g = (await istemci.get("/api/v1/gelen-kutusu", params={"kaynak": "toplanti_talebi", "durum": "hepsi", "adet": 100},
                           headers=yb)).json()
    assert "toplanti_talebi" in g["meta"]["kaynaklar"]
    o = next(x for x in g["ogeler"] if x["kimlik"] == talep["id"])
    assert o["durum"] == "yeni" and o["kisi_eposta"] == a and o["hesap_email"] == a and o["baslik"] == "Kampanya planı"
    assert {e["anahtar"] for e in o["eylemler"]} == {"toplanti_planla", "kapat"}
    assert o["ac_baglantisi"] == f"/admin?sekme=toplantilar&talep={talep['id']}"
    ay = (await istemci.get(f"/api/v1/gelen-kutusu/toplanti_talebi/{talep['id']}", headers=yb)).json()
    assert ay["ayrinti"]["araliklar"] == araliklar and ay["ayrinti"]["not"] == "Öğleden sonra"
    sayac = (await istemci.get("/api/v1/gelen-kutusu/sayac", headers=yb)).json()
    assert sayac["kaynaklar"]["toplanti_talebi"] >= 1
    # "Toplantı planla": talep ön doldurma ucu + talep_id ile oluşturma → kapandı
    on = (await istemci.get(f"{Y}/talepler/{talep['id']}", headers=yb)).json()
    assert on["konu"] == "Kampanya planı" and on["hesap_email"] == a
    t = await _toplanti(istemci, yb, baslik=on["konu"], baslangic=araliklar[0]["bas"], hesap_email=a,
                        talep_id=talep["id"], katilimcilar=[{"eposta": a}])
    assert t["talep_id"] == talep["id"]
    o = (await istemci.get(f"/api/v1/gelen-kutusu/toplanti_talebi/{talep['id']}", headers=yb)).json()["oge"]
    assert o["durum"] == "kapandi" and o["eylemler"] == []
    talepler = (await istemci.get(f"{M}/talepler", headers=ma)).json()["items"]
    assert talepler[0]["durum"] == "planlandi" and talepler[0]["toplanti_id"] == t["id"]
    # Elle kapatma eylemi
    y = await istemci.post(f"{M}/talepler", json={"konu": "İkinci", "araliklar": araliklar}, headers=ma)
    t2 = y.json()
    y = await istemci.post(f"{Y}/talepler/{t2['id']}/kapat", headers=yb)
    assert y.status_code == 200 and y.json()["durum"] == "kapandi"


# ---------------------------------------------------------------------------
# Olaylar, kataloglar, PDF, çöp kutusu, haftalık özet
# ---------------------------------------------------------------------------
async def test_otomasyon_ve_webhook_olaylari(istemci, yonetici_basligi, db_oturumu):
    from models.toplantilar import Toplantilar
    from services import otomasyon, otomasyon_kural, webhook

    for tur in ("toplanti.planlandi", "toplanti.yapildi", "toplanti.iptal"):
        assert tur in webhook.OLAY_SOZLUGU and not webhook.OLAY_SOZLUGU[tur].musteri
        assert tur in otomasyon_kural.OLAY_SOZLUGU and otomasyon_kural.OLAY_SOZLUGU[tur].proje_var
        b = otomasyon_kural.ornek_baglam(tur, True)
        assert b["toplanti"]["durum"] == {"toplanti.planlandi": "planlandi", "toplanti.yapildi": "yapildi",
                                          "toplanti.iptal": "iptal"}[tur]
    gelen = []
    webhook.abone_ekle(webhook.OlayAbonesi(
        ad="test_toplanti", ilgileniyor_mu=lambda tur: tur is None or str(tur).startswith("toplanti."),
        yaz=lambda baglanti, olaylar, baglam: gelen.extend(o for o in olaylar if o[0].startswith("toplanti.")),
        tablolar=frozenset({"toplantilar"}),
    ))
    try:
        yb = yonetici_basligi
        a = _e("a")
        p = await _proje(db_oturumu, a)
        t = await _toplanti(istemci, yb, hesap_email=a, proje_id=p.id, baslangic=_iso(_simdi() - timedelta(hours=2)))
        assert [o[0] for o in gelen] == ["toplanti.planlandi"] and gelen[0][1] == a
        assert gelen[0][2]["toplanti_id"] == t["id"] and "baslik" not in gelen[0][2] and gelen[0][3] is False
        await istemci.put(f"{Y}/{t['id']}/tutanak", json={"notlar": "x"}, headers=yb)
        assert len(gelen) == 1  # tutanak olay değil
        assert (await istemci.post(f"{Y}/{t['id']}/yapildi", headers=yb)).status_code == 200
        t2 = await _toplanti(istemci, yb, hesap_email=a)
        await istemci.post(f"{Y}/{t2['id']}/iptal", json={"neden": "x"}, headers=yb)
        assert [o[0] for o in gelen] == ["toplanti.planlandi", "toplanti.yapildi", "toplanti.planlandi", "toplanti.iptal"]
    finally:
        webhook._EK_ABONELER[:] = [x for x in webhook._EK_ABONELER if x.ad != "test_toplanti"]  # noqa: SLF001
    b = await otomasyon.baglam_kur(db_oturumu, "toplanti.yapildi", {"toplanti_id": t["id"]}, a, True)
    assert b["toplanti"]["durum"] == "yapildi" and b["proje"]["id"] == p.id and b["kisi"]["email"] == a
    assert "notlar" not in b["toplanti"] and "x" not in json.dumps(b["toplanti"].get("iptal_nedeni") or "")
    tt = (await db_oturumu.execute(select(Toplantilar).where(Toplantilar.id == t["id"]))).scalars().first()
    assert tt.yapildi_at is not None


@pytest.mark.parametrize("dil", DILLER)
async def test_tutanak_pdf_yedi_dil_ve_markdown(istemci, yonetici_basligi, dil):
    from services import toplanti_pdf as tpdf

    yb = yonetici_basligi
    t = await _toplanti(istemci, yb, baslik="Иван · أحمد · 张伟 · राम", katilimcilar=[{"eposta": _e(), "ad": "张伟"}])
    await istemci.put(f"{Y}/{t['id']}/tutanak", json={"notlar": "# Başlık\n- madde **kalın**\nDüz satır",
                                                      "kararlar": ["Bütçe onaylandı"]}, headers=yb)
    await istemci.post(f"{Y}/{t['id']}/aksiyonlar", json={"metin": "Teklif hazırla"}, headers=yb)
    y = await istemci.get(f"{Y}/{t['id']}/pdf", params={"dil": dil}, headers=yb)
    assert y.status_code == 200 and y.content.startswith(b"%PDF") and y.headers["content-type"] == "application/pdf"
    from pypdf import PdfReader
    import io

    metin = "".join((s.extract_text() or "") for s in PdfReader(io.BytesIO(y.content)).pages)
    if dil not in ("ar", "hi", "zh"):
        assert tpdf.ETIKET[dil]["kararlar"] in metin
    y = await istemci.get(f"{Y}/{t['id']}/md", params={"dil": dil}, headers=yb)
    assert y.status_code == 200 and y.text.startswith(f"# {tpdf.ETIKET[dil]['baslik']}") and "Bütçe onaylandı" in y.text
    assert "- [ ] Teklif hazırla" in y.text and "attachment" in y.headers["content-disposition"]


async def test_silme_cop_kutusuna_birlikte(istemci, yonetici_basligi, db_oturumu):
    from models.cop_kutusu import CopKutusu

    yb = yonetici_basligi
    t = await _toplanti(istemci, yb, baslik=f"Silinecek {uuid.uuid4().hex[:6]}", katilimcilar=[{"eposta": _e()}])
    await istemci.post(f"{Y}/{t['id']}/aksiyonlar", json={"metin": "A"}, headers=yb)
    assert (await istemci.delete(f"{Y}/{t['id']}", headers=yb)).status_code == 200
    assert (await istemci.get(f"{Y}/{t['id']}", headers=yb)).status_code == 404
    satirlar = (await db_oturumu.execute(select(CopKutusu).where(CopKutusu.kayit_id == str(t["id"]),
                                                                 CopKutusu.tablo == "toplantilar"))).scalars().all()
    assert len(satirlar) == 1 and satirlar[0].sahip_email is None
    grup = (await db_oturumu.execute(select(CopKutusu.tablo).where(CopKutusu.grup == satirlar[0].grup))).scalars().all()
    assert {"toplantilar", "toplanti_katilimcilari", "toplanti_aksiyonlari"} <= set(grup)


async def test_liste_gorunumleri_ve_suzgecler(istemci, yonetici_basligi, db_oturumu):
    yb = yonetici_basligi
    a = _e("a")
    p = await _proje(db_oturumu, a)
    gelecek = await _toplanti(istemci, yb, hesap_email=a, proje_id=p.id, baslangic=_iso(_simdi() + timedelta(days=1)))
    gecmis = await _toplanti(istemci, yb, hesap_email=a, baslangic=_iso(_simdi() - timedelta(days=1)))
    iptal = await _toplanti(istemci, yb, hesap_email=a, baslangic=_iso(_simdi() + timedelta(days=2)))
    await istemci.post(f"{Y}/{iptal['id']}/iptal", json={"neden": "x"}, headers=yb)

    async def idler(**p_):
        y = await istemci.get(Y, params={"hesap": a, **p_}, headers=yb)
        assert y.status_code == 200, y.text
        return [x["id"] for x in y.json()["items"]]

    assert await idler(gorunum="yaklasan") == [gelecek["id"]]
    assert await idler(gorunum="gecmis") == [gecmis["id"]]
    assert await idler(gorunum="iptal") == [iptal["id"]]
    assert set(await idler(gorunum="hepsi")) == {gelecek["id"], gecmis["id"], iptal["id"]}
    assert await idler(gorunum="hepsi", proje_id=p.id) == [gelecek["id"]]
    assert await idler(gorunum="hepsi", durum="iptal") == [iptal["id"]]
    gun = (_simdi() + timedelta(days=1)).astimezone(timezone(timedelta(hours=3))).date().isoformat()
    assert gelecek["id"] in await idler(gorunum="hepsi", bas=gun, bit=gun)
    y = await istemci.get(Y, params={"gorunum": "uydurma"}, headers=yb)
    assert y.status_code == 400
    liste = (await istemci.get(Y, params={"hesap": a, "gorunum": "yaklasan"}, headers=yb)).json()["items"]
    assert re.fullmatch(r"\d{4}-W\d{2}", liste[0]["hafta"])
    meta = (await istemci.get(f"{Y}/meta", headers=yb)).json()
    assert meta["saat_dilimi"] == "Europe/Istanbul" and any(x["id"] == p.id and x["hesap_email"] == a for x in meta["projeler"])
    j = (await istemci.get(f"{Y}/jitsi", headers=yb)).json()["baglanti"]
    assert re.fullmatch(r"https://meet\.jit\.si/mk-[0-9a-f]{32}", j)


async def test_haftalik_ozet_notu_yazilmamis_gecmis_toplanti(istemci, yonetici_basligi, db_oturumu):
    from services import haftalik_ozet as ho

    yb = yonetici_basligi
    baslik = f"Notsuz {uuid.uuid4().hex[:6]}"
    t = await _toplanti(istemci, yb, baslik=baslik, baslangic=_iso(_simdi() - timedelta(days=2)))
    o = await ho.ozet_hazirla(db_oturumu)
    bolum = next(b for b in o["bolumler"] if b["anahtar"] == "toplantilar")
    assert bolum["sekme"] == "toplantilar" and bolum["sayi"] >= 1
    assert "Notu yazılmamış geçmiş toplantılar" in o["eposta"]["metin"]
    await istemci.put(f"{Y}/{t['id']}/tutanak", json={"notlar": "Yazıldı"}, headers=yb)
    from services import toplantilar as tp

    assert all(x.baslik != baslik for x in await tp.notsuz_gecmis(db_oturumu))


def test_kataloglar_ve_etiketler():
    from services import bildirim_tercih as bt
    from services import hesap_ekibi as he
    from services.gelen_kutusu import KAYNAK_TANIMI, KAYNAKLAR

    for olay in ("toplanti_davet", "toplanti_iptal", "toplanti_hatirlatma", "toplanti_notlari", "toplanti_talebi"):
        assert bt.OLAYLAR[olay]["tetikleniyor"] is True
        for dil in DILLER:
            ek = json.loads((I18N_EK / "bildirim" / f"{dil}.json").read_text(encoding="utf-8"))
            assert ek["bildirim"]["olay"][olay], (dil, olay)
    # Davet kişiye özel (imzalı bağlantı): ekibe genişlemez; paylaşım `projeler` iznine.
    assert "toplanti_davet" not in he.OLAY_IZNI and he.OLAY_IZNI["toplanti_notlari"] == "projeler"
    assert "toplanti_talebi" in KAYNAKLAR and KAYNAK_TANIMI["toplanti_talebi"]
    # Toplantılar ayrı satılan modül değil
    from core import moduller as mf

    assert all("toplanti" not in m.anahtar for m in mf.MODULLER)


def test_ek_paketler_yedi_dilde_esit_anahtarlar():
    def duz(d, on=""):
        for k, v in d.items():
            if isinstance(v, dict):
                yield from duz(v, f"{on}{k}.")
            else:
                yield f"{on}{k}", v

    for ad in ("toplantilar", "toplantiYanit"):
        paketler = {dil: dict(duz(json.loads((I18N_EK / ad / f"{dil}.json").read_text(encoding="utf-8"))))
                    for dil in DILLER}
        anahtarlar = set(paketler["tr"])
        for dil, p in paketler.items():
            assert set(p) == anahtarlar, (ad, dil, sorted(set(p) ^ anahtarlar)[:5])
            assert all(isinstance(v, str) and v.strip() for v in p.values()), (ad, dil)
        for dil in ("en", "de", "ru", "zh", "hi", "ar"):
            ayni = [k for k in anahtarlar if paketler[dil][k] == paketler["tr"][k] and len(paketler["tr"][k]) > 12
                    and "{{" not in paketler["tr"][k]]
            assert not ayni, (ad, dil, ayni[:5])
    # Sunucunun döndürdüğü hata kodlarının metni var
    kaynak = (Path(__file__).resolve().parents[2] / "services" / "toplantilar.py").read_text(encoding="utf-8")
    kaynak += (Path(__file__).resolve().parents[2] / "routers" / "toplantilar.py").read_text(encoding="utf-8")
    kodlar = set(re.findall(r'ToplantiHatasi\(\d+, "([a-z_]+)"', kaynak)) | set(re.findall(r'"kod": "([a-z_]+)"', kaynak))
    tr = json.loads((I18N_EK / "toplantilar" / "tr.json").read_text(encoding="utf-8"))["toplantilar"]["hata"]
    assert kodlar <= set(tr), sorted(kodlar - set(tr))


def test_on_yuz_kayitlari_rota_noindex_basliklar_ve_menuler():
    """Girişsiz yanıt sayfası: rota (site düzeni dışında), prerender yok + noindex, Referer yok; yönetici sekmesi
    Projeler grubunun sonunda, müşteri sekmesi Projeler grubunda; Jitsi yalnız bağlantı (CSP'ye ekleme yok)."""
    on = Path(__file__).resolve().parents[3] / "frontend"
    app = (on / "src" / "App.tsx").read_text(encoding="utf-8")
    assert '<Route path="/toplanti-yanit/:jeton" element={<ToplantiYanitSayfasi />} />' in app
    assert "'/toplanti-yanit/:jeton'" in (on / "scripts" / "check-routes.mjs").read_text(encoding="utf-8")
    site = (on / "prerender" / "site.js").read_text(encoding="utf-8")
    noindex = site[site.index("export const NOINDEX_ROUTES"):]
    assert "'/toplanti-yanit'" in noindex[: noindex.index("];")]
    basliklar = (on / "public" / "_headers").read_text(encoding="utf-8")
    blok = basliklar[basliklar.index("/toplanti-yanit/*"):].split("\n\n", 1)[0]
    assert "Referrer-Policy: no-referrer" in blok and "X-Robots-Tag: noindex" in blok
    menu = (on / "src" / "lib" / "yonetimMenusu.ts").read_text(encoding="utf-8")
    assert "sekmeler: ['projects', 'zaman', 'projeSablonlari', 'dosyalar', 'toplantilar']" in menu
    musteri = (on / "src" / "lib" / "musteriMenusu.ts").read_text(encoding="utf-8")
    assert "sekmeler: ['projects', 'dosyalar', 'raporlar', 'toplantilar']" in musteri
    assert "meet.jit.si" not in (on / "functions" / "_ortak" / "csp.js").read_text(encoding="utf-8")
    sayfa = (on / "src" / "pages" / "ToplantiYanitSayfasi.tsx").read_text(encoding="utf-8")
    assert "<iframe" not in sayfa and "noindex" in sayfa
    for dil in DILLER:
        ana = json.loads((on / "src" / "i18n" / f"{dil}.json").read_text(encoding="utf-8"))
        assert ana["ui"]["tabToplantilar"], dil
