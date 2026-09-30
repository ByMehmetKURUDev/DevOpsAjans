"""Faz 2C — dosyalar: tür/boyut/ad, imzalı indirme, sahiplik, paylaşım, belge talebi, depo."""

import time
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

DOSYA = "/api/v1/dosyalar"
MUSTERI = "/api/v1/dosyalarim"
TALEP = "/api/v1/belge-talepleri"
MODUL = "/api/v1/moduller"

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
DOCX = b"PK\x03\x04" + b"\x00" * 40


def _eposta(on: str = "dosya") -> str:
    return f"{on}-{uuid.uuid4().hex[:10]}@test.dev"


@pytest.fixture(autouse=True)
def nesne_deposu_yok(monkeypatch):
    for ad in ("S3_ENDPOINT_URL", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY", "S3_BUCKET", "S3_REGION"):
        monkeypatch.delenv(ad, raising=False)


async def _modul_ac(istemci, yonetici_basligi, eposta, modul="dosyalar"):
    y = await istemci.put(f"{MODUL}/musteri/{eposta}/{modul}", json={"acik": True}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text


async def _yonetici_yukle(istemci, baslik, eposta, ad="rapor.pdf", veri=PDF, klasor="Genel", gorunurluk=None):
    data = {"client_email": eposta, "klasor": klasor}
    if gorunurluk:
        data["gorunurluk"] = gorunurluk
    return await istemci.post(f"{DOSYA}/yukle", data=data, files={"dosya": (ad, veri, "application/octet-stream")}, headers=baslik)


async def _bildirimler(db, eposta, olay):
    from models.notifications import Notifications

    db.expire_all()
    return (
        await db.execute(
            select(Notifications).where(
                Notifications.event_type == olay, Notifications.recipient_email == eposta, Notifications.channel == "inapp"
            )
        )
    ).scalars().all()


# ---------------------------------------------------------------------------
# Saf kurallar
# ---------------------------------------------------------------------------
def test_ad_temizleme():
    from services.dosyalar import AD_SINIRI, ad_temizle

    assert ad_temizle("../../etc/passwd") == "passwd"
    assert ad_temizle("C:\\Belgeler\\Rapor Son.PDF") == "Rapor Son.pdf"
    assert ad_temizle("fatura\u202egpj.exe") == "faturagpj.exe"  # sağdan-sola hilesi
    assert ad_temizle("a\x00b\x07c.txt") == "abc.txt"
    assert ad_temizle('<script>"x".pdf') == "scriptx.pdf"
    assert ad_temizle(".htaccess") == "htaccess"
    assert ad_temizle("   ") == "dosya"
    assert ad_temizle("çok   boşluklu    ad.docx") == "çok boşluklu ad.docx"
    uzun = ad_temizle("a" * 500 + ".pdf")
    assert len(uzun) == AD_SINIRI and uzun.endswith(".pdf")
    # NFD → NFC: aynı görünen iki ad tek sürüm zinciri olsun.
    assert ad_temizle("s\u0327e\u0308.txt") == "şë.txt"


def test_tur_dogrulama_icerikten():
    from services.dosyalar import DosyaHatasi, turu_dogrula

    assert turu_dogrula("a.pdf", PDF) == "application/pdf"
    assert turu_dogrula("a.png", PNG) == "image/png"
    assert turu_dogrula("a.docx", DOCX).startswith("application/vnd.openxml")
    assert turu_dogrula("a.txt", "merhaba dünya".encode()) .startswith("text/plain")
    for ad, veri, kod in [
        ("a.exe", b"MZ\x90\x00", "tur_izinsiz"),
        ("a.svg", b"<svg onload=alert(1)>", "tur_izinsiz"),
        ("a.html", b"<html>", "tur_izinsiz"),
        ("a.pdf", b"<html><script>alert(1)</script>", "icerik_uyusmuyor"),  # uzantı yalan
        ("a.png", PDF, "icerik_uyusmuyor"),
        ("a.txt", b"abc\x00def", "icerik_uyusmuyor"),
        ("a.txt", b"\xff\xfe\xfa", "icerik_uyusmuyor"),
        ("a.pdf", b"", "bos_dosya"),
    ]:
        with pytest.raises(DosyaHatasi) as h:
            turu_dogrula(ad, veri)
        assert h.value.kod == kod, (ad, h.value.kod)
    # Talebe özel tür listesi (jpg ile jpeg eşdeğer).
    with pytest.raises(DosyaHatasi) as h:
        turu_dogrula("a.png", PNG, ["pdf"])
    assert h.value.kod == "tur_talepte_yok"
    assert turu_dogrula("a.jpeg", b"\xff\xd8\xff\xe0" + b"\x00" * 8, ["jpg"]) == "image/jpeg"


def test_imza_sure_ve_kurcalama():
    from services.dosyalar import imza_gecerli_mi, imzali_yol, indirme_imzasi

    yol, son = imzali_yol(7)
    imza = yol.split("imza=")[1]
    assert imza_gecerli_mi(7, son, imza)
    assert son - time.time() <= 15 * 60 + 2  # 15 dakika
    assert not imza_gecerli_mi(8, son, imza)  # başka dosya
    assert not imza_gecerli_mi(7, son + 3600, imza)  # süre uzatma
    assert not imza_gecerli_mi(7, son, imza[:-1] + ("0" if imza[-1] != "0" else "1"))
    assert not imza_gecerli_mi(7, son, None) and not imza_gecerli_mi(7, "abc", imza)
    gecmis = int(time.time()) - 5
    assert not imza_gecerli_mi(7, gecmis, indirme_imzasi(7, gecmis))  # süresi dolmuş


def test_s3_sigv4_aws_test_vektorleri():
    from services.dosya_deposu import on_imzali_adres, sigv4_imza

    an = datetime(2013, 5, 24, tzinfo=timezone.utc)
    erisim, gizli = "AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    bos = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    imza, imzalanan = sigv4_imza(
        yontem="GET", url="https://examplebucket.s3.amazonaws.com/test.txt",
        basliklar={"host": "examplebucket.s3.amazonaws.com", "range": "bytes=0-9", "x-amz-content-sha256": bos, "x-amz-date": "20130524T000000Z"},
        govde_ozeti=bos, an=an, erisim=erisim, gizli=gizli, bolge="us-east-1",
    )
    assert imza == "f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"
    assert imzalanan == "host;range;x-amz-content-sha256;x-amz-date"
    adres = on_imzali_adres(
        url="https://examplebucket.s3.amazonaws.com/test.txt", an=an, erisim=erisim, gizli=gizli, bolge="us-east-1", sure_sn=86400
    )
    assert adres.endswith("X-Amz-Signature=aeeed9bbccd4d02ee5c0109b86d86835f995330da4c265957d157751f604d404")


def test_depo_secimi(monkeypatch):
    from services import dosya_deposu

    assert dosya_deposu.depo_turu() == "veritabani"
    assert dosya_deposu.depo_bilgisi() == {"tur": "veritabani", "kalici": True, "oneri": "r2"}
    for ad, deger in {
        "S3_ENDPOINT_URL": "https://hesap.r2.cloudflarestorage.com", "S3_ACCESS_KEY_ID": "a",
        "S3_SECRET_ACCESS_KEY": "b",
    }.items():
        monkeypatch.setenv(ad, deger)
    assert dosya_deposu.depo_turu() == "veritabani"  # kova adı yoksa yine veritabanı
    monkeypatch.setenv("S3_BUCKET", "mk-dosyalar")
    assert dosya_deposu.depo_turu() == "s3"


# ---------------------------------------------------------------------------
# Yükleme ve indirme
# ---------------------------------------------------------------------------
async def test_yukleme_tur_boyut_ad_ve_indirme(istemci, yonetici_basligi, musteri_basligi):
    eposta = _eposta()
    # Yetkisiz
    y = await istemci.post(f"{DOSYA}/yukle", data={"client_email": eposta}, files={"dosya": ("a.pdf", PDF)})
    assert y.status_code == 401
    y = await istemci.post(f"{DOSYA}/yukle", data={"client_email": eposta}, files={"dosya": ("a.pdf", PDF)}, headers=musteri_basligi(eposta))
    assert y.status_code == 403

    y = await _yonetici_yukle(istemci, yonetici_basligi, eposta, ad="../../gizli/<Teklif>.PDF")
    assert y.status_code == 200, y.text
    d = y.json()
    assert d["ad"] == "Teklif.pdf" and d["tur"] == "application/pdf" and d["boyut"] == len(PDF) and d["surum"] == 1
    # İstemcinin dediği tür değil, içerik: HTML'i .pdf diye yüklemek reddediliyor.
    y = await _yonetici_yukle(istemci, yonetici_basligi, eposta, ad="kotu.pdf", veri=b"<html><script>1</script></html>")
    assert y.status_code == 415 and y.json()["detail"]["kod"] == "icerik_uyusmuyor"
    y = await _yonetici_yukle(istemci, yonetici_basligi, eposta, ad="virus.exe", veri=b"MZ\x00\x00")
    assert y.status_code == 415 and y.json()["detail"]["kod"] == "tur_izinsiz"

    # Boyut sınırı ayarı (1 MB) → 1 MB + 1 bayt reddedilir; geri al.
    assert (await istemci.put(f"{DOSYA}/ayarlar", json={"boyut_siniri_mb": 0}, headers=yonetici_basligi)).status_code == 400
    assert (await istemci.put(f"{DOSYA}/ayarlar", json={"boyut_siniri_mb": 1}, headers=yonetici_basligi)).json() == {"boyut_siniri_mb": 1}
    buyuk = b"%PDF-" + b"0" * (1024 * 1024)
    y = await _yonetici_yukle(istemci, yonetici_basligi, eposta, ad="buyuk.pdf", veri=buyuk)
    assert y.status_code == 413 and y.json()["detail"] == {"kod": "boyut_asildi", "sinir_mb": 1}
    depo = (await istemci.get(f"{DOSYA}/depo", headers=yonetici_basligi)).json()
    assert depo["tur"] == "veritabani" and depo["kalici"] is True and depo["boyut_siniri_mb"] == 1
    await istemci.put(f"{DOSYA}/ayarlar", json={"boyut_siniri_mb": 20}, headers=yonetici_basligi)

    # Aynı ad ikinci kez → sürüm 2, eski sürüm listede değil ama sürümlerde var.
    y2 = (await _yonetici_yukle(istemci, yonetici_basligi, eposta, ad="Teklif.pdf", veri=PDF + b"v2")).json()
    assert y2["surum"] == 2
    liste = (await istemci.get(DOSYA, params={"client_email": eposta}, headers=yonetici_basligi)).json()
    assert [x["id"] for x in liste["dosyalar"]] == [y2["id"]]
    assert {k["ad"]: k["gorunurluk"] for k in liste["klasorler"]} == {"Genel": "musteri"}
    assert [s["surum"] for s in (await istemci.get(f"{DOSYA}/{y2['id']}/surumler", headers=yonetici_basligi)).json()] == [2, 1]

    # İmzalı indirme
    b = (await istemci.post(f"{DOSYA}/{y2['id']}/indirme-baglantisi", headers=yonetici_basligi)).json()
    assert b["adres"].startswith(f"/api/v1/dosya-indir/{y2['id']}?son=")
    indir = await istemci.get(b["adres"])
    assert indir.status_code == 200 and indir.content == PDF + b"v2"
    assert "attachment" in indir.headers["content-disposition"] and "Teklif.pdf" in indir.headers["content-disposition"]
    assert indir.headers["x-content-type-options"] == "nosniff" and "no-store" in indir.headers["cache-control"]
    # Kurcalama: başka dosya numarası, bozuk imza, imzasız
    assert (await istemci.get(b["adres"].replace(f"/{y2['id']}?", f"/{d['id']}?"))).status_code == 403
    assert (await istemci.get(b["adres"][:-3] + "abc")).status_code == 403
    assert (await istemci.get(f"/api/v1/dosya-indir/{y2['id']}")).status_code == 403

    # Silince önceki sürüm güncel olur.
    assert (await istemci.delete(f"{DOSYA}/{y2['id']}", headers=yonetici_basligi)).status_code == 200
    liste = (await istemci.get(DOSYA, params={"client_email": eposta}, headers=yonetici_basligi)).json()
    assert [x["surum"] for x in liste["dosyalar"]] == [1]


async def test_indirme_suresi_dolmus(istemci, yonetici_basligi, monkeypatch):
    from services import dosyalar as servis

    eposta = _eposta()
    d = (await _yonetici_yukle(istemci, yonetici_basligi, eposta)).json()
    yol, son = servis.imzali_yol(d["id"], an=time.time() - 16 * 60)  # 16 dk önce alınmış bağlantı
    assert son < time.time()
    assert (await istemci.get(yol)).status_code == 403


async def test_musteri_baskasinin_dosyasini_goremez_indiremez(istemci, yonetici_basligi, musteri_basligi):
    a, b = _eposta("a"), _eposta("b")
    for e in (a, b):
        await _modul_ac(istemci, yonetici_basligi, e)
    da = (await _yonetici_yukle(istemci, yonetici_basligi, a, ad="a.pdf")).json()
    db_ = (await _yonetici_yukle(istemci, yonetici_basligi, b, ad="b.pdf")).json()
    ic = (await _yonetici_yukle(istemci, yonetici_basligi, a, ad="ic-not.pdf", klasor="Ekip notları", gorunurluk="ekip")).json()

    liste = (await istemci.get(MUSTERI, headers=musteri_basligi(a))).json()
    assert [x["id"] for x in liste["dosyalar"]] == [da["id"]]
    assert liste["klasorler"] == ["Genel"]  # ekip klasörü görünmüyor
    # Başkasının dosyası ve kendi ekip klasöründeki dosya: 404 (varlığı sızmıyor)
    assert (await istemci.post(f"{MUSTERI}/{db_['id']}/indirme-baglantisi", headers=musteri_basligi(a))).status_code == 404
    assert (await istemci.post(f"{MUSTERI}/{ic['id']}/indirme-baglantisi", headers=musteri_basligi(a))).status_code == 404
    ok = await istemci.post(f"{MUSTERI}/{da['id']}/indirme-baglantisi", headers=musteri_basligi(a))
    assert ok.status_code == 200 and (await istemci.get(ok.json()["adres"])).content == PDF
    # Yönetici uçları müşteriye kapalı
    assert (await istemci.get(DOSYA, params={"client_email": b}, headers=musteri_basligi(a))).status_code == 403
    assert (await istemci.post(f"{DOSYA}/{db_['id']}/indirme-baglantisi", headers=musteri_basligi(a))).status_code == 403
    assert (await istemci.post(f"{DOSYA}/{db_['id']}/paylasim", json={"gun": 1}, headers=musteri_basligi(a))).status_code == 403

    # Müşteri yüklemesi kendi klasörüne; ekip klasörüne yazamaz.
    y = await istemci.post(f"{MUSTERI}/yukle", files={"dosya": ("benim.png", PNG)}, headers=musteri_basligi(a))
    assert y.status_code == 200 and y.json()["klasor"] == "Yüklemelerim" and y.json()["client_email"] == a
    y = await istemci.post(f"{MUSTERI}/yukle", data={"klasor": "Ekip notları"}, files={"dosya": ("x.png", PNG)}, headers=musteri_basligi(a))
    assert y.status_code == 404
    # Oturumsuz
    assert (await istemci.get(MUSTERI)).status_code == 401


async def test_modul_bekcisi_dosyalar(istemci, yonetici_basligi, musteri_basligi):
    eposta = _eposta("kapali")
    # Paketsiz müşteride dosyalar varsayılan kapalı.
    y = await istemci.get(MUSTERI, headers=musteri_basligi(eposta))
    assert y.status_code == 403 and y.json()["detail"] == {"kod": "modul_kapali", "modul": "dosyalar"}
    await _modul_ac(istemci, yonetici_basligi, eposta)
    assert (await istemci.get(MUSTERI, headers=musteri_basligi(eposta))).status_code == 200


async def test_s3_deposu_yazar_ve_indirmeyi_yonlendirir(istemci, yonetici_basligi, monkeypatch):
    from services import dosya_deposu

    for ad, deger in {
        "S3_ENDPOINT_URL": "https://hesap.r2.cloudflarestorage.com", "S3_ACCESS_KEY_ID": "anahtar",
        "S3_SECRET_ACCESS_KEY": "gizli", "S3_BUCKET": "mk-dosyalar",
    }.items():
        monkeypatch.setenv(ad, deger)
    cagrilar = []

    class Yanit:
        status_code = 200
        text = ""
        content = b""

    async def sahte(ayar, yontem, anahtar, veri=b"", tur=None):
        cagrilar.append((yontem, anahtar, len(veri), tur))
        return Yanit()

    monkeypatch.setattr(dosya_deposu, "_s3_istek", sahte)
    eposta = _eposta("s3")
    d = (await _yonetici_yukle(istemci, yonetici_basligi, eposta)).json()
    assert cagrilar[0][0] == "PUT" and cagrilar[0][1].startswith("dosyalar/") and cagrilar[0][2] == len(PDF)
    b = (await istemci.post(f"{DOSYA}/{d['id']}/indirme-baglantisi", headers=yonetici_basligi)).json()
    y = await istemci.get(b["adres"], follow_redirects=False)
    assert y.status_code == 302
    hedef = y.headers["location"]
    assert hedef.startswith("https://hesap.r2.cloudflarestorage.com/mk-dosyalar/dosyalar/")
    assert "X-Amz-Expires=900" in hedef and "X-Amz-Signature=" in hedef and "response-content-disposition" in hedef


# ---------------------------------------------------------------------------
# Paylaşım bağlantısı
# ---------------------------------------------------------------------------
async def test_paylasim_baglantisi_sure_parola_sayi(istemci, yonetici_basligi, db_oturumu):
    from models.dosyalar import PaylasimBaglantilari

    eposta = _eposta("paylas")
    d = (await _yonetici_yukle(istemci, yonetici_basligi, eposta, ad="Sunum.pdf")).json()
    for govde in ({"gun": 0}, {"gun": 31}, {"gun": 5, "sifre": "ab"}, {"gun": 5, "indirme_siniri": 0}):
        y = await istemci.post(f"{DOSYA}/{d['id']}/paylasim", json=govde, headers=yonetici_basligi)
        assert y.status_code == 400, govde
    p = (await istemci.post(f"{DOSYA}/{d['id']}/paylasim", json={"gun": 3, "sifre": "Gizli123", "indirme_siniri": 2}, headers=yonetici_basligi)).json()
    assert p["yol"].startswith("/paylas/") and p["adres"].endswith(p["yol"]) and p["sifreli"] is True
    jeton = p["yol"].split("/")[-1]

    # Parola ve jeton düz metin olarak saklanmıyor.
    db_oturumu.expire_all()
    satir = (await db_oturumu.execute(select(PaylasimBaglantilari).where(PaylasimBaglantilari.id == p["id"]))).scalar_one()
    assert satir.sifre_ozeti and "Gizli123" not in satir.sifre_ozeti and len(satir.sifre_ozeti) == 64 and satir.sifre_tuzu
    assert satir.jeton_ozeti != jeton and len(satir.jeton_ozeti) == 64

    bilgi = await istemci.get(f"/api/v1/paylas/{jeton}")
    assert bilgi.status_code == 200
    b = bilgi.json()
    assert b["ad"] == "Sunum.pdf" and b["sifreli"] is True and b["kalan_indirme"] == 2
    assert eposta not in bilgi.text and "dosyalar/" not in bilgi.text  # iç ayrıntı yok

    y = await istemci.post(f"/api/v1/paylas/{jeton}/indir", json={"sifre": "yanlis"})
    assert y.status_code == 403 and y.json()["detail"]["kod"] == "sifre_yanlis"
    y = await istemci.post(f"/api/v1/paylas/{jeton}/indir", json={})
    assert y.status_code == 403
    for _ in range(2):
        y = await istemci.post(f"/api/v1/paylas/{jeton}/indir", json={"sifre": "Gizli123"})
        assert y.status_code == 200, y.text
        assert (await istemci.get(y.json()["adres"])).content == PDF
    y = await istemci.post(f"/api/v1/paylas/{jeton}/indir", json={"sifre": "Gizli123"})
    assert y.status_code == 410 and y.json()["detail"]["kod"] == "sinir_doldu"
    assert (await istemci.get(f"/api/v1/paylas/{jeton}")).status_code == 410
    assert (await istemci.get("/api/v1/paylas/uydurma-jeton")).status_code == 404

    # Süre dolumu
    p2 = (await istemci.post(f"{DOSYA}/{d['id']}/paylasim", json={"gun": 1}, headers=yonetici_basligi)).json()
    j2 = p2["yol"].split("/")[-1]
    y = await istemci.post(f"/api/v1/paylas/{j2}/indir", json={})
    assert y.status_code == 200  # parolasız, sınırsız
    await db_oturumu.execute(
        update(PaylasimBaglantilari).where(PaylasimBaglantilari.id == p2["id"]).values(son_kullanma=datetime.now(timezone.utc) - timedelta(minutes=1))
    )
    await db_oturumu.commit()
    y = await istemci.post(f"/api/v1/paylas/{j2}/indir", json={})
    assert y.status_code == 410 and y.json()["detail"]["kod"] == "suresi_doldu"

    # İptal
    p3 = (await istemci.post(f"{DOSYA}/{d['id']}/paylasim", json={"gun": 30}, headers=yonetici_basligi)).json()
    assert (await istemci.post(f"{DOSYA}/paylasim/{p3['id']}/iptal", headers=yonetici_basligi)).json()["durum"] == "iptal"
    assert (await istemci.get(f"/api/v1/paylas/{p3['yol'].split('/')[-1]}")).json()["detail"]["kod"] == "iptal"

    # 10 yanlış parolada kilit (doğru parola da artık açmıyor)
    p4 = (await istemci.post(f"{DOSYA}/{d['id']}/paylasim", json={"gun": 2, "sifre": "dogru-sifre"}, headers=yonetici_basligi)).json()
    j4 = p4["yol"].split("/")[-1]
    for _ in range(10):
        await istemci.post(f"/api/v1/paylas/{j4}/indir", json={"sifre": "x"})
    y = await istemci.post(f"/api/v1/paylas/{j4}/indir", json={"sifre": "dogru-sifre"})
    assert y.status_code == 410 and y.json()["detail"]["kod"] == "kilitli"

    liste = (await istemci.get(f"{DOSYA}/{d['id']}/paylasimlar", headers=yonetici_basligi)).json()
    assert {x["durum"] for x in liste} == {"sinir_doldu", "suresi_doldu", "iptal", "kilitli"}


# ---------------------------------------------------------------------------
# Belge talebi
# ---------------------------------------------------------------------------
async def test_belge_talebi_akisi(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    eposta = _eposta("belge")
    await _modul_ac(istemci, yonetici_basligi, eposta)
    son = (date.today() + timedelta(days=10)).isoformat()
    y = await istemci.post(TALEP, json={"client_email": eposta, "baslik": "Vergi levhası", "son_tarih": son, "kabul_turleri": ["exe"]}, headers=yonetici_basligi)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "tur_izinsiz"
    assert (await istemci.post(TALEP, json={"client_email": eposta, "baslik": "x", "son_tarih": "31-12-2026"}, headers=yonetici_basligi)).status_code == 400
    assert (await istemci.post(TALEP, json={"client_email": eposta, "baslik": "x"}, headers=musteri_basligi(eposta))).status_code == 403
    t = (await istemci.post(
        TALEP,
        json={"client_email": eposta, "baslik": "Vergi levhası", "aciklama": "Güncel yıl", "son_tarih": son, "kabul_turleri": [".PDF", "jpg"]},
        headers=yonetici_basligi,
    )).json()
    assert t["kabul_turleri"] == ["pdf", "jpg"] and t["durum"] == "bekliyor"
    assert len(await _bildirimler(db_oturumu, eposta, "belge_talebi")) == 1

    # Başka müşteri bu talebi göremez ve yükleyemez.
    diger = _eposta("diger")
    await _modul_ac(istemci, yonetici_basligi, diger)
    assert (await istemci.get(f"{MUSTERI}/talepler", headers=musteri_basligi(diger))).json() == []
    y = await istemci.post(f"{MUSTERI}/talepler/{t['id']}/yukle", files={"dosya": ("v.pdf", PDF)}, headers=musteri_basligi(diger))
    assert y.status_code == 404

    talepler = (await istemci.get(f"{MUSTERI}/talepler", headers=musteri_basligi(eposta))).json()
    assert [x["id"] for x in talepler] == [t["id"]] and talepler[0]["kalan_gun"] is not None
    y = await istemci.post(f"{MUSTERI}/talepler/{t['id']}/yukle", files={"dosya": ("levha.png", PNG)}, headers=musteri_basligi(eposta))
    assert y.status_code == 415 and y.json()["detail"]["kod"] == "tur_talepte_yok"
    y = await istemci.post(f"{MUSTERI}/talepler/{t['id']}/yukle", files={"dosya": ("levha.pdf", PDF)}, headers=musteri_basligi(eposta))
    assert y.status_code == 200, y.text
    teslim = y.json()
    assert teslim["durum"] == "teslim_edildi" and teslim["dosya"]["ad"] == "levha.pdf" and teslim["dosya"]["klasor"] == "İstenen belgeler"
    assert len(await _bildirimler(db_oturumu, "yonetici@test.dev", "belge_teslim")) >= 1

    # Yönetici listesinde teslim edilen dosya; indirilebilir.
    liste = (await istemci.get(TALEP, params={"client_email": eposta}, headers=yonetici_basligi)).json()
    assert liste[0]["durum"] == "teslim_edildi" and liste[0]["dosya"]["id"] == teslim["dosya"]["id"]
    b = (await istemci.post(f"{DOSYA}/{teslim['dosya']['id']}/indirme-baglantisi", headers=yonetici_basligi)).json()
    assert (await istemci.get(b["adres"])).content == PDF
    # Müşteri de "İstenen belgeler" klasöründe görüyor.
    assert "İstenen belgeler" in (await istemci.get(MUSTERI, headers=musteri_basligi(eposta))).json()["klasorler"]


async def test_belge_hatirlatmalari_bir_kez(istemci, yonetici_basligi, db_oturumu):
    from services.dosyalar import belge_hatirlatmalari, bugun_tr

    eposta = _eposta("hatir")
    bugun = bugun_tr()
    yakin = (await istemci.post(TALEP, json={"client_email": eposta, "baslik": "Kimlik", "son_tarih": (bugun + timedelta(days=1)).isoformat()}, headers=yonetici_basligi)).json()
    gecmis = (await istemci.post(TALEP, json={"client_email": eposta, "baslik": "İmza sirküleri", "son_tarih": (bugun - timedelta(days=1)).isoformat()}, headers=yonetici_basligi)).json()
    uzak = (await istemci.post(TALEP, json={"client_email": eposta, "baslik": "Logo", "son_tarih": (bugun + timedelta(days=9)).isoformat()}, headers=yonetici_basligi)).json()
    await belge_hatirlatmalari(db_oturumu)
    await belge_hatirlatmalari(db_oturumu)  # ikinci tur yeni bildirim üretmez
    hatir = [n.ref_id for n in await _bildirimler(db_oturumu, eposta, "belge_hatirlatma")]
    assert hatir == [yakin["id"]]
    gecikti = [n.ref_id for n in await _bildirimler(db_oturumu, eposta, "belge_gecikti")]
    assert gecikti == [gecmis["id"]]
    yonetici = [n.ref_id for n in await _bildirimler(db_oturumu, "yonetici@test.dev", "belge_gecikti")]
    assert yonetici.count(gecmis["id"]) == 1
    assert uzak["id"] not in hatir + gecikti
