"""Faz 2B — "Hata bildir": yükleme doğrulaması (tür/boyut, imza), sahiplik, göreve
dönüştürme, durum bildirimleri, ek okuma yetkisi, modül bekçisi.
"""

import uuid

import pytest
from sqlalchemy import select

GM = "/api/v1/geri-bildirimlerim"
GY = "/api/v1/geri-bildirim"
EK = "/api/v1/geri-bildirim-ek"
G = "/api/v1/gorevler"
MODUL = "/api/v1/moduller"

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 64


def _eposta(on: str = "fb") -> str:
    return f"{on}-{uuid.uuid4().hex[:10]}@test.dev"


async def _proje(db, eposta):
    from models.projects import Projects

    kayit = Projects(title=f"Proje {uuid.uuid4().hex[:6]}", description="d", category="Website", client_email=eposta, stage="build")
    db.add(kayit)
    await db.commit()
    await db.refresh(kayit)
    return kayit


async def _gonder(istemci, basliklar, beklenen=200, dosya=None, **alanlar):
    alanlar.setdefault("baslik", "Sepet düğmesi çalışmıyor")
    veri = {k: str(v) for k, v in alanlar.items() if v is not None}
    dosyalar = {"ekran": dosya} if dosya else None
    y = await istemci.post(GM, data=veri, files=dosyalar, headers=basliklar)
    assert y.status_code == beklenen, y.text
    return y.json()


async def _bildirimler(db, olay, eposta=None, ref_id=None):
    from models.notifications import Notifications

    sorgu = select(Notifications).where(Notifications.event_type == olay, Notifications.channel == "inapp")
    if eposta:
        sorgu = sorgu.where(Notifications.recipient_email == eposta)
    if ref_id is not None:
        sorgu = sorgu.where(Notifications.ref_id == ref_id)
    return list((await db.execute(sorgu)).scalars().all())


def test_gorsel_imzasi():
    from services.geri_bildirim import gorsel_turu

    assert gorsel_turu(PNG) == "image/png"
    assert gorsel_turu(JPEG) == "image/jpeg"
    assert gorsel_turu(WEBP) == "image/webp"
    assert gorsel_turu(b"GIF89a" + b"\x00" * 20) == "image/gif"
    assert gorsel_turu(b"<svg xmlns='http://www.w3.org/2000/svg'></svg>") is None
    assert gorsel_turu(b"%PDF-1.7" + b"\x00" * 20) is None
    assert gorsel_turu(b"\x89PNG") is None


@pytest.mark.parametrize("metot,yol", [("GET", GY), ("PATCH", f"{GY}/1"), ("POST", f"{GY}/1/goreve-donustur")])
async def test_yonetici_uclari_yetki(istemci, musteri_basligi, metot, yol):
    govde = {} if metot != "GET" else None
    assert (await istemci.request(metot, yol, json=govde)).status_code == 401
    assert (await istemci.request(metot, yol, json=govde, headers=musteri_basligi())).status_code == 403


async def test_oturumsuz_401(istemci):
    assert (await istemci.get(GM)).status_code == 401
    assert (await istemci.post(GM, data={"baslik": "x"})).status_code == 401
    assert (await istemci.get(f"{EK}/1")).status_code == 401


async def test_gonderim_ekran_goruntusu_ve_otomatik_bilgiler(istemci, musteri_basligi, yonetici_basligi, db_oturumu):
    m = _eposta()
    proje = await _proje(db_oturumu, m)
    fb = await _gonder(
        istemci, {**musteri_basligi(m), "User-Agent": "Deneme/1.0"}, dosya=("ekran.png", PNG, "image/png"),
        aciklama="Ödeme adımında düğme tepki vermiyor", sayfa_adresi="https://musteri.test/sepet", proje_id=proje.id,
    )
    assert fb["durum"] == "yeni" and fb["proje_id"] == proje.id and len(fb["ekler"]) == 1
    assert fb["ekler"][0]["icerik_turu"] == "image/png" and fb["ekler"][0]["boyut"] == len(PNG)
    assert "musteri_eposta" not in fb and "tarayici" not in fb and "gorev_id" not in fb
    # Tarayıcı bilgisi formda yoksa istek başlığından
    liste = (await istemci.get(GY, headers=yonetici_basligi)).json()
    kayit = next(k for k in liste if k["id"] == fb["id"])
    assert kayit["tarayici"] == "Deneme/1.0" and kayit["musteri_eposta"] == m
    # Yöneticiye "yeni geri bildirim"
    assert await _bildirimler(db_oturumu, "geri_bildirim_yeni", "yonetici@test.dev", fb["id"])

    # Ek: sahibi ve yönetici okur, başkası 404; içerik aynı, nosniff
    y = await istemci.get(f"{EK}/{fb['ekler'][0]['id']}", headers=musteri_basligi(m))
    assert y.status_code == 200 and y.content == PNG and y.headers["content-type"] == "image/png"
    assert y.headers["x-content-type-options"] == "nosniff"
    assert (await istemci.get(f"{EK}/{fb['ekler'][0]['id']}", headers=yonetici_basligi)).status_code == 200
    assert (await istemci.get(f"{EK}/{fb['ekler'][0]['id']}", headers=musteri_basligi(_eposta()))).status_code == 404

    # Tek projesi olan müşteride proje verilmese de bağlanır; javascript: adresi atılır
    fb2 = await _gonder(istemci, musteri_basligi(m), sayfa_adresi="javascript:alert(1)", tarayici="Firefox 130 · 390x844")
    assert fb2["proje_id"] == proje.id and fb2["sayfa_adresi"] is None
    # Kendi listesi
    kendi = (await istemci.get(GM, headers=musteri_basligi(m))).json()
    assert {k["id"] for k in kendi} == {fb["id"], fb2["id"]}
    assert (await istemci.get(GM, headers=musteri_basligi(_eposta()))).json() == []


async def test_yukleme_dogrulamasi_tur_boyut_ve_baskasinin_projesi(istemci, musteri_basligi, db_oturumu):
    from models.geri_bildirim import FeedbackItems
    from services import geri_bildirim as gb

    m, baska = _eposta("m"), _eposta("baska")
    await _proje(db_oturumu, m)
    onun = await _proje(db_oturumu, baska)

    # Tür, tarayıcının söylediğine göre değil imzaya göre
    y = await istemci.post(GM, data={"baslik": "svg"}, files={"ekran": ("a.png", b"<svg onload='x'/>" + b" " * 40, "image/png")}, headers=musteri_basligi(m))
    assert y.status_code == 415 and y.json()["detail"]["kod"] == "tur_desteklenmiyor"
    y = await istemci.post(GM, data={"baslik": "pdf"}, files={"ekran": ("a.pdf", b"%PDF-1.4" + b"\x00" * 64, "application/pdf")}, headers=musteri_basligi(m))
    assert y.status_code == 415
    # Doğru görsel, yanlış bildirilen tür: kabul, sunucunun türüyle
    fb = await _gonder(istemci, musteri_basligi(m), dosya=("x.gif", JPEG, "image/gif"))
    assert fb["ekler"][0]["icerik_turu"] == "image/jpeg"
    # Boyut: 5 MB + 1 bayt reddedilir, tam 5 MB kabul
    buyuk = PNG + b"\x00" * (gb.EN_BUYUK_BOYUT - len(PNG) + 1)
    y = await istemci.post(GM, data={"baslik": "büyük"}, files={"ekran": ("b.png", buyuk, "image/png")}, headers=musteri_basligi(m))
    assert y.status_code == 413 and y.json()["detail"]["kod"] == "dosya_buyuk"
    tam = buyuk[:-1]
    await _gonder(istemci, musteri_basligi(m), dosya=("t.png", tam, "image/png"), baslik="tam 5 MB")
    y = await istemci.post(GM, data={"baslik": "boş"}, files={"ekran": ("b.png", b"", "image/png")}, headers=musteri_basligi(m))
    assert y.status_code == 400
    # Geçersiz dosyalı istekte kayıt oluşmamalı
    adet = (await db_oturumu.execute(select(FeedbackItems).where(FeedbackItems.musteri_eposta == m))).scalars().all()
    assert {k.baslik for k in adet} == {"Sepet düğmesi çalışmıyor", "tam 5 MB"}

    # Başkasının projesine yükleyemez (404, varlık sızmaz)
    y = await istemci.post(GM, data={"baslik": "x", "proje_id": str(onun.id)}, files={"ekran": ("a.png", PNG, "image/png")}, headers=musteri_basligi(m))
    assert y.status_code == 404
    y = await istemci.post(f"{GM}/{fb['id']}/ek", files={"ekran": ("a.png", PNG, "image/png")}, headers=musteri_basligi(baska))
    assert y.status_code == 404
    # Ek sınırı (3)
    for _ in range(2):
        assert (await istemci.post(f"{GM}/{fb['id']}/ek", files={"ekran": ("a.png", PNG, "image/png")}, headers=musteri_basligi(m))).status_code == 200
    assert (await istemci.post(f"{GM}/{fb['id']}/ek", files={"ekran": ("a.png", PNG, "image/png")}, headers=musteri_basligi(m))).status_code == 409
    # Geçersiz tür/başlık
    await _gonder(istemci, musteri_basligi(m), 400, tur="sikayet")
    await _gonder(istemci, musteri_basligi(m), 400, baslik="   ")


async def test_oss_tanimliysa_depoya_yukler(istemci, musteri_basligi, db_oturumu, monkeypatch):
    from models.geri_bildirim import FeedbackAttachments
    from services import geri_bildirim as gb

    depo = {}

    async def yukle(anahtar, bayt, tur):
        depo[anahtar] = (bayt, tur)

    async def oku(anahtar):
        return depo[anahtar][0]

    monkeypatch.setenv("OSS_SERVICE_URL", "https://oss.test")
    monkeypatch.setenv("OSS_API_KEY", "anahtar")
    monkeypatch.setattr(gb, "_oss_yukle", yukle)
    monkeypatch.setattr(gb, "_oss_oku", oku)
    m = _eposta("oss")
    fb = await _gonder(istemci, musteri_basligi(m), dosya=("a.png", PNG, "image/png"))
    ek = (await db_oturumu.execute(select(FeedbackAttachments).where(FeedbackAttachments.id == fb["ekler"][0]["id"]))).scalar_one()
    assert ek.depo == "oss" and ek.icerik is None and ek.nesne_anahtari in depo
    y = await istemci.get(f"{EK}/{ek.id}", headers=musteri_basligi(m))
    assert y.status_code == 200 and y.content == PNG

    # Depo hata verirse veritabanına düşer
    async def bozuk(*_a):
        raise RuntimeError("erişilemedi")

    monkeypatch.setattr(gb, "_oss_yukle", bozuk)
    fb2 = await _gonder(istemci, musteri_basligi(m), dosya=("a.png", PNG, "image/png"))
    ek2 = (await db_oturumu.execute(select(FeedbackAttachments).where(FeedbackAttachments.id == fb2["ekler"][0]["id"]))).scalar_one()
    assert ek2.depo == "db" and bytes(ek2.icerik) == PNG


async def test_goreve_donustur_ve_durum_bildirimleri(istemci, musteri_basligi, yonetici_basligi, db_oturumu):
    m = _eposta("donustur")
    proje = await _proje(db_oturumu, m)
    fb = await _gonder(istemci, musteri_basligi(m), aciklama="Menü mobilde açılmıyor", sayfa_adresi="/iletisim", proje_id=proje.id,
                       dosya=("a.png", PNG, "image/png"))

    # Kanban sütunu: projenin açık bildirimleri
    tam = (await istemci.get(f"{G}/proje/{proje.id}", headers=yonetici_basligi)).json()
    assert [k["id"] for k in tam["geri_bildirimler"]] == [fb["id"]]

    y = await istemci.patch(f"{GY}/{fb['id']}", json={"durum": "inceleniyor", "oncelik": "yuksek"}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["durum"] == "inceleniyor"
    assert len(await _bildirimler(db_oturumu, "geri_bildirim_durumu", m, fb["id"])) == 1
    assert (await istemci.patch(f"{GY}/{fb['id']}", json={"durum": "gorev"}, headers=yonetici_basligi)).status_code == 409
    assert (await istemci.patch(f"{GY}/{fb['id']}", json={"durum": "bilinmez"}, headers=yonetici_basligi)).status_code == 400

    y = await istemci.post(f"{GY}/{fb['id']}/goreve-donustur", json={}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    gorev = y.json()["gorev"]
    assert y.json()["geri_bildirim"]["durum"] == "gorev" and y.json()["geri_bildirim"]["gorev_id"] == gorev["id"]
    assert gorev["proje_id"] == proje.id and gorev["etiketler"] == ["hata"] and gorev["musteriye_gorunur"] is True
    assert gorev["oncelik"] == "yuksek" and "/iletisim" in gorev["aciklama"] and gorev["geri_bildirim_id"] == fb["id"]
    assert (await istemci.post(f"{GY}/{fb['id']}/goreve-donustur", json={}, headers=yonetici_basligi)).status_code == 409
    # Artık açık sütunda değil; müşteri görev tahtasında görür
    tam = (await istemci.get(f"{G}/proje/{proje.id}", headers=yonetici_basligi)).json()
    assert tam["geri_bildirimler"] == []
    gorunum = (await istemci.get(f"/api/v1/gorevlerim/proje/{proje.id}", headers=musteri_basligi(m))).json()
    assert [g["id"] for g in gorunum["gorevler"]] == [gorev["id"]]
    assert len(await _bildirimler(db_oturumu, "geri_bildirim_durumu", m, fb["id"])) == 2

    # Görev tamamlanınca bildirim "çözüldü" ve müşteriye haber
    await istemci.patch(f"{G}/{gorev['id']}", json={"durum": "tamam"}, headers=yonetici_basligi)
    kendi = (await istemci.get(GM, headers=musteri_basligi(m))).json()
    assert next(k for k in kendi if k["id"] == fb["id"])["durum"] == "cozuldu"
    assert len(await _bildirimler(db_oturumu, "geri_bildirim_durumu", m, fb["id"])) == 3


async def test_projesiz_bildirim_goreve_donusemez(istemci, musteri_basligi, yonetici_basligi):
    m = _eposta("projesiz")
    fb = await _gonder(istemci, musteri_basligi(m))
    assert fb["proje_id"] is None
    y = await istemci.post(f"{GY}/{fb['id']}/goreve-donustur", json={}, headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "proje_yok"


async def test_modul_kapaliyken_musteri_403(istemci, musteri_basligi, yonetici_basligi):
    m = _eposta("kapali")
    y = await istemci.put(f"{MODUL}/musteri/{m}/geri_bildirim", json={"acik": False}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    y = await istemci.post(GM, data={"baslik": "x"}, headers=musteri_basligi(m))
    assert y.status_code == 403 and y.json()["detail"]["modul"] == "geri_bildirim"
    assert (await istemci.get(GM, headers=musteri_basligi(m))).status_code == 403
    assert (await istemci.get(GY, headers=yonetici_basligi)).status_code == 200
