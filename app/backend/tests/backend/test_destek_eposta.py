"""Faz 2F — E-postadan destek talebi ve otomatik destek kuralları."""

import base64
import hashlib
import hmac
import json
import time
import uuid

import pytest
from sqlalchemy import delete, select

DESTEK = "/api/v1/destek"
KURAL = "/api/v1/destek/kurallar"
PDF = b"%PDF-1.4\n%test\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _eposta(on: str = "eposta") -> str:
    return f"{on}-{uuid.uuid4().hex[:10]}@test.dev"


def _mid() -> str:
    return f"<{uuid.uuid4().hex}@istemci.test>"


@pytest.fixture
async def temiz(db_oturumu):
    """Kurallar paylaşılan veritabanında diğer testlerin taleplerine uygulanmasın."""
    yield
    from models.destek_eposta import DestekKurallari

    await db_oturumu.execute(delete(DestekKurallari))
    await db_oturumu.commit()


async def _kullanici(db, eposta: str):
    from models.auth import User

    db.add(User(id=f"k-{uuid.uuid4().hex}", email=eposta, name="Müşteri", role="user"))
    await db.commit()


async def _isle(db, **alanlar):
    from services.eposta_gelen import isle

    ileti = {"message_id": _mid(), "konu": "Merhaba", "metin": "Sitem açılmıyor"}
    ileti.update(alanlar)
    return await isle(db, ileti)


async def _talep(db, talep_id):
    from models.support_tickets import Support_tickets

    db.expire_all()
    return (await db.execute(select(Support_tickets).where(Support_tickets.id == talep_id))).scalar_one()


async def _mesajlar(db, talep_id):
    from models.ticket_replies import Ticket_replies

    db.expire_all()
    return (await db.execute(select(Ticket_replies).where(Ticket_replies.ticket_id == talep_id).order_by(Ticket_replies.id))).scalars().all()


async def _bildirimler(db, olay, ref_id, kanal="inapp"):
    from models.notifications import Notifications

    db.expire_all()
    return (
        await db.execute(
            select(Notifications).where(Notifications.event_type == olay, Notifications.ref_id == ref_id, Notifications.channel == kanal)
        )
    ).scalars().all()


# ---------------------------------------------------------------------------
# İmzalar
# ---------------------------------------------------------------------------
def test_hmac_imzasi_dogru_yanlis_eski():
    from services.eposta_gelen import hmac_dogrula, hmac_imzasi

    govde = b'{"konu":"x"}'
    an = 1_800_000_000
    imza = hmac_imzasi("gizli", str(an), govde)
    assert imza == hmac.new(b"gizli", f"{an}.".encode() + govde, hashlib.sha256).hexdigest()
    assert hmac_dogrula("gizli", str(an), imza, govde, an=an + 10)
    assert not hmac_dogrula("gizli", str(an), imza, govde + b" ", an=an)  # gövde değişti
    assert not hmac_dogrula("baska", str(an), imza, govde, an=an)  # yanlış anahtar
    assert not hmac_dogrula("gizli", str(an), imza, govde, an=an + 301)  # eski
    assert not hmac_dogrula("gizli", str(an), imza, govde, an=an - 301)  # gelecekten
    assert not hmac_dogrula("gizli", None, imza, govde, an=an)
    assert not hmac_dogrula("gizli", "abc", imza, govde, an=an)


def test_svix_imzasi_belge_ornegi_ve_yanlis():
    from services.eposta_gelen import svix_dogrula

    # Svix/Resend belgesindeki örnek vektör.
    gizli = "whsec_MfKQ9r8GKYqrTwjUPD8ILPZIo2LaLaSw"
    kimlik, zaman = "msg_p5jXN8AQM9LWM0D4loKWxJek", "1614265330"
    govde = b'{"test": 2432232314}'
    imza = "v1,g0hM9SsE+OTPJTGt/tmIKtSyZlE3uFJELVlNIOLJ1OE="
    assert svix_dogrula(gizli, kimlik, zaman, imza, govde, an=1614265330)
    # Döndürülen anahtarlar: listede biri doğruysa yeter.
    assert svix_dogrula(gizli, kimlik, zaman, "v1,yanlis= " + imza, govde, an=1614265330)
    assert not svix_dogrula(gizli, kimlik, zaman, imza, b'{"test": 2432232315}', an=1614265330)
    assert not svix_dogrula(gizli, "msg_baska", zaman, imza, govde, an=1614265330)
    assert not svix_dogrula("whsec_" + base64.b64encode(b"baska-anahtar").decode(), kimlik, zaman, imza, govde, an=1614265330)
    assert not svix_dogrula(gizli, kimlik, zaman, imza, govde, an=1614265330 + 400)  # eski
    assert not svix_dogrula(gizli, kimlik, zaman, "v2," + imza[3:], govde, an=1614265330)
    assert not svix_dogrula("whsec_!!!", kimlik, zaman, imza, govde, an=1614265330)


# ---------------------------------------------------------------------------
# Metin
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "ham, beklenen",
    [
        ("Teşekkürler, çalıştı.\n\nOn Mon, 5 Oct 2026 at 10:00, Destek <d@x.com> wrote:\n> eski", "Teşekkürler, çalıştı."),
        ("Tamam.\n\nOn Mon, 5 Oct 2026 at 10:00, Destek Ekibi <d@x.com>\nwrote:\n> eski", "Tamam."),
        ("Olur.\n\n5 Eki 2026 Pzt, 10:00 tarihinde Destek <d@x.com> şunu yazdı:\n> eski satır", "Olur."),
        ("Yeni bilgi\n-----Original Message-----\nFrom: a\nSent: b\neski", "Yeni bilgi"),
        ("Ekte.\n\nFrom: Destek <d@x.com>\nSent: Monday\nTo: ben\nSubject: x\n\neski", "Ekte."),
        ("Cevap\n> alıntı 1\n> alıntı 2\nson söz", "Cevap\nson söz"),
        ("Merhaba\n-- \nAyşe Yılmaz\n0555", "Merhaba"),
        ("> hepsi alıntı", "> hepsi alıntı"),
    ],
)
def test_alinti_kirpma(ham, beklenen):
    from services.eposta_gelen import alintiyi_kirp

    assert alintiyi_kirp(ham) == beklenen


def test_html_metne_guvenli_ve_alintisiz():
    from services.eposta_gelen import govde_metni

    html = (
        "<div>Merhaba,<br>fatura <b>hatalı</b>.</div><script>alert(1)</script><style>p{}</style>"
        "<p>İkinci &amp; satır</p><div class=\"gmail_quote\">On x wrote:<blockquote>eski</blockquote></div>"
    )
    metin = govde_metni("", html)
    assert "alert" not in metin and "eski" not in metin and "<" not in metin
    assert "Merhaba," in metin and "fatura hatalı." in metin and "İkinci & satır" in metin
    # Düz metin varsa HTML kullanılmıyor.
    assert govde_metni("düz", "<p>html</p>") == "düz"


def test_otomatik_nedeni():
    from services.eposta_gelen import otomatik_nedeni

    kendi = ["bildirim@mehmetkuru.dev", "destek@mehmetkuru.dev"]
    assert otomatik_nedeni("a@b.com", "Selam", {"auto-submitted": "auto-replied"}, kendi) == "auto_submitted"
    assert otomatik_nedeni("a@b.com", "Selam", {"auto-submitted": "no"}, kendi) is None
    assert otomatik_nedeni("a@b.com", "Selam", {"precedence": "bulk"}, kendi) == "precedence"
    assert otomatik_nedeni("a@b.com", "Selam", {"x-autoreply": "yes"}, kendi) == "x_autoreply"
    assert otomatik_nedeni("MAILER-DAEMON@b.com".lower(), "x", {}, kendi) == "sistem_gondericisi"
    assert otomatik_nedeni("no-reply@b.com", "x", {}, kendi) == "sistem_gondericisi"
    assert otomatik_nedeni("destek@mehmetkuru.dev", "x", {}, kendi) == "kendi_adresimiz"
    assert otomatik_nedeni("a@b.com", "Out of Office: izindeyim", {}, kendi) == "otomatik_konu"
    assert otomatik_nedeni("a@b.com", "x", {"list-id": "<l.b.com>"}, kendi) == "liste_iletisi"


# ---------------------------------------------------------------------------
# İşleme: yeni talep, eşleşme, güvenlik
# ---------------------------------------------------------------------------
async def test_yeni_talep_kayitli_ve_taninmayan(db_oturumu):
    from models.destek_eposta import GelenEpostalar
    from models.destek_sla import TalepSla

    musteri = _eposta("kayitli")
    await _kullanici(db_oturumu, musteri)
    s = await _isle(db_oturumu, gonderen=f"Ayşe Yılmaz <{musteri.upper()}>", konu="Fatura sorusu", metin="Merhaba\n\nOn x wrote:\n> eski")
    assert s["durum"] == "islendi" and s["neden"] == "yeni_talep"
    t = await _talep(db_oturumu, s["talep_id"])
    assert t.client_email == musteri and t.client_name == "Ayşe Yılmaz" and t.kaynak == "eposta"
    assert not t.dogrulanmadi and t.message == "Merhaba" and t.status == "open"
    # Panel akışıyla aynı: SLA satırı ve yönetici bildirimi.
    assert (await db_oturumu.execute(select(TalepSla).where(TalepSla.ticket_id == t.id))).scalar_one()
    assert len(await _bildirimler(db_oturumu, "ticket", t.id)) >= 1

    yabanci = _eposta("yabanci")
    s2 = await _isle(db_oturumu, gonderen=yabanci, konu="Teklif", metin="Fiyat?")
    assert s2["neden"] == "yeni_talep_dogrulanmadi"
    t2 = await _talep(db_oturumu, s2["talep_id"])
    assert t2.dogrulanmadi is True and t2.client_email == yabanci
    admin = await _bildirimler(db_oturumu, "ticket", t2.id)
    assert admin and "doğrulanmadı" in admin[0].body
    # Kayıt: ham gövde yok, kısa özet var.
    kayit = (await db_oturumu.execute(select(GelenEpostalar).where(GelenEpostalar.talep_id == s2["talep_id"]))).scalar_one()
    assert kayit.durum == "islendi" and kayit.ozet == "Fiyat?" and kayit.gonderen == yabanci


async def test_ayni_message_id_bir_kez(db_oturumu):
    from models.support_tickets import Support_tickets

    mid = _mid()
    gonderen = _eposta("tekrar")
    s1 = await _isle(db_oturumu, gonderen=gonderen, message_id=mid)
    s2 = await _isle(db_oturumu, gonderen=gonderen, message_id=mid, konu="farklı konu")
    assert s1["durum"] == "islendi" and s2.get("tekrar") is True and s2["talep_id"] == s1["talep_id"]
    sayi = (await db_oturumu.execute(select(Support_tickets.id).where(Support_tickets.client_email == gonderen))).all()
    assert len(sayi) == 1


async def test_hata_durumundaki_ileti_yeniden_islenir(db_oturumu, monkeypatch):
    from services import eposta_gelen

    async def bozuk(*a, **k):
        raise eposta_gelen.GeciciHata("depo_hatasi")

    mid = _mid()
    gonderen = _eposta("yeniden")
    monkeypatch.setattr(eposta_gelen, "ekleri_hazirla", bozuk)
    with pytest.raises(eposta_gelen.GeciciHata):
        await _isle(db_oturumu, gonderen=gonderen, message_id=mid)
    from models.destek_eposta import GelenEpostalar

    db_oturumu.expire_all()
    k = (await db_oturumu.execute(select(GelenEpostalar).where(GelenEpostalar.message_id == mid))).scalar_one()
    assert k.durum == "hata" and k.talep_id is None
    monkeypatch.undo()
    s = await _isle(db_oturumu, gonderen=gonderen, message_id=mid)
    assert s["durum"] == "islendi" and s["talep_id"]


async def test_belirtecle_mevcut_talebe_ekleme_ve_yeniden_acma(db_oturumu):
    musteri = _eposta("sahip")
    await _kullanici(db_oturumu, musteri)
    s = await _isle(db_oturumu, gonderen=musteri, konu="Site yavaş")
    tid = s["talep_id"]
    t = await _talep(db_oturumu, tid)
    t.status = "closed"
    await db_oturumu.commit()

    s2 = await _isle(db_oturumu, gonderen=musteri, konu=f"Re: [#T-{tid}] Site yavaş", metin="Hâlâ yavaş.\n\n> eski")
    assert s2["neden"] == "mesaj_eklendi" and s2["talep_id"] == tid
    mesajlar = await _mesajlar(db_oturumu, tid)
    assert mesajlar[-1].yazan == "musteri" and mesajlar[-1].mesaj == "Hâlâ yavaş."
    assert (await _talep(db_oturumu, tid)).status == "open"  # kapalı talep yeniden açıldı


async def test_baskasinin_talebine_belirtecle_yazilamaz(db_oturumu):
    sahip = _eposta("sahip")
    await _kullanici(db_oturumu, sahip)
    tid = (await _isle(db_oturumu, gonderen=sahip, konu="Gizli iş"))["talep_id"]
    saldirgan = _eposta("saldirgan")
    await _kullanici(db_oturumu, saldirgan)  # kayıtlı olsa bile
    s = await _isle(db_oturumu, gonderen=saldirgan, konu=f"Re: [#T-{tid}] Gizli iş", metin="araya girdim")
    assert s["neden"] == "yeni_talep_yetkisiz_belirtec" and s["talep_id"] != tid
    assert all(m.mesaj != "araya girdim" for m in await _mesajlar(db_oturumu, tid))
    yeni = await _talep(db_oturumu, s["talep_id"])
    assert yeni.dogrulanmadi is True and yeni.client_email == saldirgan
    bildirim = await _bildirimler(db_oturumu, "ticket", yeni.id)
    assert bildirim and f"#{tid}" in bildirim[0].body


async def test_in_reply_to_bizim_message_id_ile_eslesir(istemci, yonetici_basligi, db_oturumu):
    from models.destek_eposta import TalepEpostaKimlikleri

    musteri = _eposta("zincir")
    await _kullanici(db_oturumu, musteri)
    tid = (await _isle(db_oturumu, gonderen=musteri, konu="Soru"))["talep_id"]
    # Ajans panelden yanıtlar → müşteriye yanıtlanabilir e-posta, Message-ID kaydı.
    y = await istemci.post(f"/api/v1/talep/{tid}/mesaj", json={"mesaj": "Bakıyoruz"}, headers=yonetici_basligi)
    assert y.status_code == 200
    giden = (
        await db_oturumu.execute(
            select(TalepEpostaKimlikleri).where(TalepEpostaKimlikleri.ticket_id == tid, TalepEpostaKimlikleri.yon == "giden")
        )
    ).scalars().all()
    giden_kimlik = giden[0].message_id
    assert len(giden) == 1 and giden_kimlik.startswith(f"<talep-{tid}-")
    bildirim = await _bildirimler(db_oturumu, "ticket_reply", tid)
    assert bildirim and bildirim[0].recipient_email == musteri and f"[#T-{tid}]" in bildirim[0].title

    # Konuda belirteç yok; yalnız In-Reply-To.
    s = await _isle(db_oturumu, gonderen=musteri, konu="Re: Soru", metin="Teşekkürler", in_reply_to=giden_kimlik)
    assert s["neden"] == "mesaj_eklendi" and s["talep_id"] == tid
    # Biçimi taklit eden ama kayıtlı olmayan kimlik eşleşmez.
    s = await _isle(db_oturumu, gonderen=musteri, konu="Re: Soru", in_reply_to=f"<talep-{tid}-uydurma@mehmetkuru.dev>")
    assert s["neden"] == "yeni_talep" and s["talep_id"] != tid


async def test_otomatik_yanitlar_yoksayilir(db_oturumu):
    from models.destek_eposta import GelenEpostalar

    for alanlar, neden in (
        ({"basliklar": {"Auto-Submitted": "auto-replied"}}, "auto_submitted"),
        ({"basliklar": [{"name": "Precedence", "value": "bulk"}]}, "precedence"),
        ({"gonderen": "MAILER-DAEMON@x.test"}, "sistem_gondericisi"),
        ({"gonderen": "bildirim@mehmetkuru.dev"}, "kendi_adresimiz"),
        ({"gonderen": ""}, "gecersiz_gonderen"),
    ):
        ileti = {"gonderen": _eposta("oto")}
        ileti.update(alanlar)
        s = await _isle(db_oturumu, **ileti)
        assert s["durum"] == "yoksayildi" and s["neden"] == neden and s["talep_id"] is None
    kayit = (await db_oturumu.execute(select(GelenEpostalar).where(GelenEpostalar.neden == "auto_submitted"))).scalars().first()
    assert kayit is not None and kayit.talep_id is None


async def test_saatlik_sinir(db_oturumu, monkeypatch):
    from services import eposta_gelen

    monkeypatch.setattr(eposta_gelen, "SAATLIK_SINIR", 2)
    g = _eposta("sel")
    assert (await _isle(db_oturumu, gonderen=g))["durum"] == "islendi"
    assert (await _isle(db_oturumu, gonderen=g))["durum"] == "islendi"
    s = await _isle(db_oturumu, gonderen=g)
    assert s["durum"] == "yoksayildi" and s["neden"] == "hiz_siniri"


async def test_ek_boyut_tur_ve_sayi_siniri(istemci, db_oturumu, musteri_basligi):
    from models.destek_eposta import TalepEkleri
    from models.dosyalar import Dosyalar

    musteri = _eposta("ek")
    await _kullanici(db_oturumu, musteri)
    b64 = lambda v: base64.b64encode(v).decode()  # noqa: E731
    ekler = [
        {"ad": "fatura.pdf", "icerik": b64(PDF)},
        {"ad": "ekran.png", "icerik": b64(PNG)},
        {"ad": "virus.exe", "icerik": b64(b"MZ")},
        {"ad": "sahte.pdf", "icerik": b64(b"<html>")},
        {"ad": "buyuk.pdf", "boyut": 11 * 1024 * 1024, "icerik": b64(PDF)},
        {"ad": "buyuk2.pdf", "icerik": b64(PDF + b"0" * (10 * 1024 * 1024))},
    ] + [{"ad": f"n{i}.txt", "icerik": b64(b"not")} for i in range(6)]
    s = await _isle(db_oturumu, gonderen=musteri, konu="Belgeler", metin="Ekte", ekler=ekler)
    tid = s["talep_id"]
    kayitlar = (await db_oturumu.execute(select(TalepEkleri).where(TalepEkleri.ticket_id == tid))).scalars().all()
    adlar = sorted(k.ad for k in kayitlar)
    ilk_dosya = kayitlar[0].dosya_id
    # 12 ekten ilk 10'u denenir; 4'ü tür/içerik/boyut yüzünden atlanır.
    assert adlar == sorted(["fatura.pdf", "ekran.png", "n0.txt", "n1.txt", "n2.txt", "n3.txt"])
    t = await _talep(db_oturumu, tid)
    for parca in ("virus.exe", "sahte.pdf", "buyuk.pdf", "buyuk2.pdf", "n4.txt", "n5.txt", "Atlanan ekler"):
        assert parca in t.message
    d = (await db_oturumu.execute(select(Dosyalar).where(Dosyalar.id == ilk_dosya))).scalar_one()
    assert d.client_email == musteri and d.klasor == "Destek e-postaları"

    # Yazışmada ek görünür; indirme bağlantısını sahip alır, başkası alamaz.
    y = await istemci.get(f"/api/v1/talep/{tid}/mesajlar", headers=musteri_basligi(musteri))
    assert y.status_code == 200
    acilis = y.json()["mesajlar"][0]
    assert len(acilis["ekler"]) == 6 and y.json()["kaynak"] == "eposta"
    ek_id = acilis["ekler"][0]["id"]
    y = await istemci.post(f"/api/v1/talep/{tid}/ekler/{ek_id}/indirme-baglantisi", headers=musteri_basligi(musteri))
    assert y.status_code == 200 and y.json()["url"].startswith("/api/v1/dosya-indir/")
    indir = await istemci.get(y.json()["url"])
    assert indir.status_code == 200
    y = await istemci.post(f"/api/v1/talep/{tid}/ekler/{ek_id}/indirme-baglantisi", headers=musteri_basligi(_eposta("baska")))
    assert y.status_code == 403
    y = await istemci.post(f"/api/v1/talep/{tid}/ekler/999999/indirme-baglantisi", headers=musteri_basligi(musteri))
    assert y.status_code == 404


# ---------------------------------------------------------------------------
# Uçlar
# ---------------------------------------------------------------------------
async def test_genel_uc_hmac(istemci, db_oturumu, monkeypatch):
    govde = json.dumps({"gonderen": _eposta("uc"), "konu": "Uçtan", "metin": "Merhaba", "message_id": _mid()}).encode()
    monkeypatch.delenv("EPOSTA_GELEN_ANAHTARI", raising=False)
    y = await istemci.post(f"{DESTEK}/eposta-gelen", content=govde)
    assert y.status_code == 503 and y.json()["detail"]["kod"] == "kapali"

    monkeypatch.setenv("EPOSTA_GELEN_ANAHTARI", "cok-gizli")
    zaman = str(int(time.time()))
    imza = hmac.new(b"cok-gizli", f"{zaman}.".encode() + govde, hashlib.sha256).hexdigest()
    y = await istemci.post(f"{DESTEK}/eposta-gelen", content=govde, headers={"X-MK-Zaman": zaman, "X-MK-Imza": "0" * 64})
    assert y.status_code == 401
    eski = str(int(time.time()) - 600)
    eski_imza = hmac.new(b"cok-gizli", f"{eski}.".encode() + govde, hashlib.sha256).hexdigest()
    y = await istemci.post(f"{DESTEK}/eposta-gelen", content=govde, headers={"X-MK-Zaman": eski, "X-MK-Imza": eski_imza})
    assert y.status_code == 401
    y = await istemci.post(f"{DESTEK}/eposta-gelen", content=govde, headers={"X-MK-Zaman": zaman, "X-MK-Imza": imza})
    assert y.status_code == 200 and y.json()["durum"] == "islendi" and y.json()["talep_id"]
    # Aynı gövde yeniden → ikinci talep yok.
    y2 = await istemci.post(f"{DESTEK}/eposta-gelen", content=govde, headers={"X-MK-Zaman": zaman, "X-MK-Imza": imza})
    assert y2.status_code == 200 and y2.json()["tekrar"] is True and y2.json()["talep_id"] == y.json()["talep_id"]


async def test_resend_ucu_svix(istemci, db_oturumu, monkeypatch):
    from services import eposta_gelen

    gizli_ham = b"resend-test-anahtari-32-bayt-000"
    gizli = "whsec_" + base64.b64encode(gizli_ham).decode()
    monkeypatch.setenv("RESEND_GELEN_IMZA_ANAHTARI", gizli)
    gonderen = _eposta("resend")
    cagri = []

    async def sahte(veri):
        cagri.append(veri["email_id"])
        return {"gonderen": f"Ali <{gonderen}>", "konu": veri["subject"], "metin": "Resend'den", "html": "",
                "message_id": veri["message_id"], "basliklar": {}, "ekler": []}

    monkeypatch.setattr(eposta_gelen, "resend_iletisi", sahte)
    olay = {"type": "email.received", "created_at": "2026-09-30T10:00:00Z",
            "data": {"email_id": "56761188-7520-42d8-8898-ff6fc54ce618", "from": gonderen, "to": ["destek@x.dev"],
                     "subject": "Resend konusu", "message_id": _mid(), "attachments": []}}
    govde = json.dumps(olay).encode()

    def basliklar(g=govde, zaman=None, anahtar=gizli_ham):
        z = zaman or str(int(time.time()))
        imza = base64.b64encode(hmac.new(anahtar, f"msg_1.{z}.".encode() + g, hashlib.sha256).digest()).decode()
        return {"svix-id": "msg_1", "svix-timestamp": z, "svix-signature": f"v1,{imza}", "content-type": "application/json"}

    y = await istemci.post(f"{DESTEK}/eposta-gelen/resend", content=govde, headers=basliklar(anahtar=b"yanlis"))
    assert y.status_code == 401
    y = await istemci.post(f"{DESTEK}/eposta-gelen/resend", content=govde, headers=basliklar(zaman=str(int(time.time()) - 900)))
    assert y.status_code == 401
    y = await istemci.post(f"{DESTEK}/eposta-gelen/resend", content=govde, headers=basliklar())
    assert y.status_code == 200 and y.json()["durum"] == "islendi", y.text
    t = await _talep(db_oturumu, y.json()["talep_id"])
    assert t.client_email == gonderen and t.subject == "Resend konusu" and t.kaynak == "eposta"
    # Yeniden gönderim: Resend API'ye yeniden gidilmez, ikinci talep yok.
    y = await istemci.post(f"{DESTEK}/eposta-gelen/resend", content=govde, headers=basliklar())
    assert y.status_code == 200 and y.json()["tekrar"] is True and len(cagri) == 1
    # Başka olay türü sessizce kabul.
    diger = json.dumps({"type": "email.sent", "data": {}}).encode()
    y = await istemci.post(f"{DESTEK}/eposta-gelen/resend", content=diger, headers=basliklar(g=diger))
    assert y.status_code == 200 and y.json()["neden"] == "olay_turu"

    # Resend API geçici hatası → 503 (Svix yeniden dener).
    async def cokuk(veri):
        raise eposta_gelen.GeciciHata("resend_502")

    monkeypatch.setattr(eposta_gelen, "resend_iletisi", cokuk)
    olay["data"]["message_id"] = _mid()
    govde2 = json.dumps(olay).encode()
    y = await istemci.post(f"{DESTEK}/eposta-gelen/resend", content=govde2, headers=basliklar(g=govde2))
    assert y.status_code == 503 and y.json()["yeniden_dene"] is True

    monkeypatch.delenv("RESEND_GELEN_IMZA_ANAHTARI")
    y = await istemci.post(f"{DESTEK}/eposta-gelen/resend", content=govde, headers=basliklar())
    assert y.status_code == 503


async def test_yonetici_uclari_yetki_ve_gizlilik(istemci, yonetici_basligi, musteri_basligi, monkeypatch):
    monkeypatch.setenv("EPOSTA_GELEN_ANAHTARI", "degeri-gorunmemeli")
    for yol in ("/gelen-epostalar", "/eposta-ayarlari"):
        assert (await istemci.get(DESTEK + yol)).status_code == 401
        assert (await istemci.get(DESTEK + yol, headers=musteri_basligi())).status_code == 403
    y = await istemci.get(f"{DESTEK}/gelen-epostalar", params={"durum": "islendi"}, headers=yonetici_basligi)
    assert y.status_code == 200 and all(k["durum"] == "islendi" for k in y.json())
    assert (await istemci.get(f"{DESTEK}/gelen-epostalar", params={"durum": "x"}, headers=yonetici_basligi)).status_code == 400

    y = await istemci.get(f"{DESTEK}/eposta-ayarlari", headers=yonetici_basligi)
    assert y.status_code == 200 and "degeri-gorunmemeli" not in y.text
    assert y.json()["genel_anahtar_tanimli"] is True and y.json()["webhook"]["resend"].endswith("/api/v1/destek/eposta-gelen/resend")
    assert (await istemci.put(f"{DESTEK}/eposta-ayarlari", json={"gelen_adres": "x"}, headers=yonetici_basligi)).status_code == 400
    assert (await istemci.put(f"{DESTEK}/eposta-ayarlari", json={"gelen_adres": "d@x.dev"}, headers=musteri_basligi())).status_code == 403

    # Müşteri ipucu: adres tanımlı değilken kapalı, tanımlıyken açık.
    assert (await istemci.get(f"{DESTEK}/eposta-bilgisi")).status_code == 401
    y = await istemci.put(f"{DESTEK}/eposta-ayarlari", json={"gelen_adres": "Destek@Destek.MehmetKuru.dev"}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["gelen_adres"] == "destek@destek.mehmetkuru.dev"
    y = await istemci.get(f"{DESTEK}/eposta-bilgisi", headers=musteri_basligi())
    assert y.json() == {"acik": True, "gelen_adres": "destek@destek.mehmetkuru.dev"}
    await istemci.put(f"{DESTEK}/eposta-ayarlari", json={"gelen_adres": ""}, headers=yonetici_basligi)
    assert (await istemci.get(f"{DESTEK}/eposta-bilgisi", headers=musteri_basligi())).json()["acik"] is False


async def test_musteri_baskasi_adina_talep_acamaz(istemci, musteri_basligi, db_oturumu):
    ben, kurban = _eposta("ben"), _eposta("kurban")
    y = await istemci.post(
        "/api/v1/entities/support_tickets",
        json={"client_email": kurban, "subject": "x", "message": "y", "kaynak": "eposta", "atanan": "a@b.c"},
        headers=musteri_basligi(ben),
    )
    assert y.status_code == 201
    assert y.json()["client_email"] == ben and y.json()["kaynak"] == "panel" and y.json()["atanan"] is None


# ---------------------------------------------------------------------------
# Kurallar
# ---------------------------------------------------------------------------
def test_katla_turkce():
    from services.destek_kurallari import katla

    assert katla("İADE Talebi") == "iade talebi"
    assert katla("IŞIK") == katla("ışık") == "isik"
    assert katla("ÖDEME  Çağrı") == "odeme cagri"


def test_kosul_eslesmesi_saf():
    from services.destek_kurallari import TalepBaglami, kural_uyuyor

    b = TalepBaglami(konu="İADE talebim var", metin="ödeme iki kez çekildi", gonderen="ali@musteri.com.tr", kanal="eposta")
    assert kural_uyuyor([{"alan": "konu", "islec": "icerir", "deger": "iade"}], "hepsi", b)
    assert kural_uyuyor([{"alan": "metin", "islec": "icerir", "deger": "ODEME"}], "hepsi", b)
    assert kural_uyuyor([{"alan": "konu_veya_metin", "islec": "icerir", "deger": "ÇEKİLDİ"}], "hepsi", b)
    assert not kural_uyuyor([{"alan": "konu", "islec": "icermez", "deger": "ıade"}], "hepsi", b)
    assert kural_uyuyor([{"alan": "gonderen", "islec": "alan_adi", "deger": "com.tr"}], "hepsi", b)
    assert not kural_uyuyor([{"alan": "gonderen", "islec": "alan_adi", "deger": "musteri.com"}], "hepsi", b)
    iki = [{"alan": "kanal", "islec": "esittir", "deger": "panel"}, {"alan": "konu", "islec": "icerir", "deger": "iade"}]
    assert not kural_uyuyor(iki, "hepsi", b) and kural_uyuyor(iki, "herhangi", b)
    assert kural_uyuyor([], "hepsi", b)


async def _hazir_cevap(istemci, yonetici_basligi):
    y = await istemci.post(f"{DESTEK}/hazir-cevaplar", json={"baslik": "Alındı", "metin": "Merhaba {musteri_adi}, {talep_no} alındı."}, headers=yonetici_basligi)
    assert y.status_code == 200
    return y.json()["id"]


async def test_kural_uclari_yetki_ve_dogrulama(istemci, yonetici_basligi, musteri_basligi, temiz):
    assert (await istemci.get(KURAL)).status_code == 401
    assert (await istemci.get(KURAL, headers=musteri_basligi())).status_code == 403
    assert (await istemci.post(f"{KURAL}/dene", json={}, headers=musteri_basligi())).status_code == 403
    assert (await istemci.post(f"{KURAL}/sirala", json={"idler": []}, headers=musteri_basligi())).status_code == 403
    assert (await istemci.delete(f"{KURAL}/1", headers=musteri_basligi())).status_code == 403
    kotu = [
        {"ad": "", "eylemler": [{"tur": "durdur"}]},
        {"ad": "x", "eylemler": []},
        {"ad": "x", "kosullar": [{"alan": "yok", "islec": "icerir", "deger": "a"}], "eylemler": [{"tur": "durdur"}]},
        {"ad": "x", "kosullar": [{"alan": "konu", "islec": "icerir", "deger": ""}], "eylemler": [{"tur": "durdur"}]},
        {"ad": "x", "eylemler": [{"tur": "oncelik", "deger": "cok"}]},
        {"ad": "x", "eylemler": [{"tur": "ata", "deger": "ekipte-degil@x.dev"}]},
        {"ad": "x", "eylemler": [{"tur": "hazir_cevap", "deger": 999999}]},
        {"ad": "x", "eslesme": "bazen", "eylemler": [{"tur": "durdur"}]},
    ]
    for g in kotu:
        y = await istemci.post(KURAL, json=g, headers=yonetici_basligi)
        assert y.status_code == 400, g


async def test_kurallar_sira_durdur_atama_oncelik_otomatik_cevap(istemci, yonetici_basligi, musteri_basligi, db_oturumu, temiz):
    from models.destek_eposta import DestekKurallari
    from models.staff import Staff

    ekipci = _eposta("ekip")
    db_oturumu.add(Staff(ad="Ekip", email=ekipci, rol="calisan", aktif=True))
    await db_oturumu.commit()
    hc = await _hazir_cevap(istemci, yonetici_basligi)

    k1 = (await istemci.post(KURAL, json={
        "ad": "İade acil", "kosullar": [{"alan": "konu_veya_metin", "islec": "icerir", "deger": "İADE"}],
        "eylemler": [{"tur": "oncelik", "deger": "acil"}, {"tur": "ata", "deger": ekipci.upper()},
                     {"tur": "etiket", "deger": "Muhasebe İşi"}, {"tur": "hazir_cevap", "deger": hc}],
    }, headers=yonetici_basligi)).json()
    k2 = (await istemci.post(KURAL, json={
        "ad": "Durdur", "kosullar": [{"alan": "kanal", "islec": "esittir", "deger": "eposta"}],
        "eylemler": [{"tur": "hizmet", "deger": "seo"}, {"tur": "durdur"}],
    }, headers=yonetici_basligi)).json()
    k3 = (await istemci.post(KURAL, json={
        "ad": "Hiç çalışmamalı", "kosullar": [], "eylemler": [{"tur": "oncelik", "deger": "dusuk"}],
    }, headers=yonetici_basligi)).json()
    assert [k["id"] for k in (await istemci.get(KURAL, headers=yonetici_basligi)).json()] == [k1["id"], k2["id"], k3["id"]]
    assert k1["eylemler"][1]["deger"] == ekipci and k1["eylemler"][2]["deger"] == "muhasebe-işi"

    # Kayıtlı müşteri, e-postadan "ıade" (Türkçe harf duyarsız).
    musteri = _eposta("kural")
    await _kullanici(db_oturumu, musteri)
    s = await _isle(db_oturumu, gonderen=musteri, konu="ıade isteği", metin="para")
    tid = s["talep_id"]
    t = await _talep(db_oturumu, tid)
    assert t.priority == "acil" and t.atanan == ekipci and t.hizmet == "seo" and t.etiketler == "muhasebe-işi"
    assert t.status == "open"  # otomatik yanıt durumu değiştirmez
    mesajlar = await _mesajlar(db_oturumu, tid)
    assert len(mesajlar) == 1 and mesajlar[0].yazan == "otomatik" and f"#{tid}" in mesajlar[0].mesaj
    assert await _bildirimler(db_oturumu, "ticket_reply", tid)
    # SLA önceliği kuraldan geldi.
    from models.destek_sla import TalepSla

    assert (await db_oturumu.execute(select(TalepSla).where(TalepSla.ticket_id == tid))).scalar_one().oncelik == "acil"
    # Bir kez: yeniden tetiklense de ikinci otomatik cevap yok.
    from services.destek_talep import otomatik_cevap_gonder

    assert await otomatik_cevap_gonder(db_oturumu, await _talep(db_oturumu, tid), hc) is False
    assert len(await _mesajlar(db_oturumu, tid)) == 1

    # Tanınmayan göndericiye otomatik cevap YOK (kurallar yine uygulanır).
    s = await _isle(db_oturumu, gonderen=_eposta("tanimsiz"), konu="İade", metin="x")
    t2 = await _talep(db_oturumu, s["talep_id"])
    assert t2.dogrulanmadi and t2.priority == "acil"
    assert await _mesajlar(db_oturumu, s["talep_id"]) == [] and not await _bildirimler(db_oturumu, "ticket_reply", s["talep_id"])

    # Sıralama: durdur'lu kural başa alınınca iade kuralı çalışmaz.
    y = await istemci.post(f"{KURAL}/sirala", json={"idler": [k2["id"], k1["id"], k3["id"]]}, headers=yonetici_basligi)
    assert y.status_code == 200 and [k["id"] for k in y.json()] == [k2["id"], k1["id"], k3["id"]]
    assert (await istemci.post(f"{KURAL}/sirala", json={"idler": [k2["id"]]}, headers=yonetici_basligi)).status_code == 409
    s = await _isle(db_oturumu, gonderen=musteri, konu="İade 2", metin="x")
    t3 = await _talep(db_oturumu, s["talep_id"])
    assert t3.priority == "normal" and t3.hizmet == "seo"

    # Panel kanalı: durdur çalışmaz (kanal eposta değil) → iade + sonuncu kural.
    y = await istemci.post("/api/v1/entities/support_tickets", json={"subject": "iade", "message": "m", "kaynak": "panel"},
                           headers=musteri_basligi(musteri))
    t4 = await _talep(db_oturumu, y.json()["id"])
    assert t4.priority == "dusuk" and t4.atanan == ekipci  # k1 acil yaptı, k3 düşük yaptı (sırayla)

    # Pasif kural çalışmaz; güncelleme ve silme.
    y = await istemci.put(f"{KURAL}/{k3['id']}", json={**{k: k3[k] for k in ("ad", "eslesme", "kosullar", "eylemler")}, "aktif": False}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["aktif"] is False
    assert (await istemci.delete(f"{KURAL}/{k3['id']}", headers=yonetici_basligi)).status_code == 200
    assert (await istemci.delete(f"{KURAL}/{k3['id']}", headers=yonetici_basligi)).status_code == 404
    kalan = (await db_oturumu.execute(select(DestekKurallari.id))).scalars().all()
    assert set(kalan) == {k1["id"], k2["id"]}


async def test_dene_ucu_yazmaz(istemci, yonetici_basligi, db_oturumu, temiz):
    from models.destek_eposta import GelenEpostalar
    from models.support_tickets import Support_tickets

    await istemci.post(KURAL, json={"ad": "Fatura", "kosullar": [{"alan": "konu", "islec": "icerir", "deger": "FATURA"}],
                                    "eylemler": [{"tur": "oncelik", "deger": "yuksek"}, {"tur": "durdur"}]}, headers=yonetici_basligi)
    await istemci.post(KURAL, json={"ad": "Alan adı", "kosullar": [{"alan": "gonderen", "islec": "alan_adi", "deger": "vip.com"}],
                                    "eylemler": [{"tur": "oncelik", "deger": "acil"}]}, headers=yonetici_basligi)
    once_t = (await db_oturumu.execute(select(Support_tickets.id))).all()
    once_g = (await db_oturumu.execute(select(GelenEpostalar.id))).all()
    y = await istemci.post(f"{KURAL}/dene", json={"konu": "Faturam gelmedi", "gonderen": "a@vip.com"}, headers=yonetici_basligi)
    assert y.status_code == 200
    assert [k["ad"] for k in y.json()["eslesen"]] == ["Fatura"] and y.json()["durduruldu"] is True
    y = await istemci.post(f"{KURAL}/dene", json={"konu": "Merhaba", "gonderen": "a@vip.com"}, headers=yonetici_basligi)
    assert [k["ad"] for k in y.json()["eslesen"]] == ["Alan adı"] and y.json()["durduruldu"] is False
    assert (await db_oturumu.execute(select(Support_tickets.id))).all() == once_t
    assert (await db_oturumu.execute(select(GelenEpostalar.id))).all() == once_g
