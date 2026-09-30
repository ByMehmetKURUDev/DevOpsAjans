"""Faz 2C — Destek: SLA hesabı (mesai/hafta sonu/gece/tatil), eskalasyon bir kez,
hazır cevap değişkenleri, bilgi bankası (güvenli HTML, arama, öneri, modül bekçisi)."""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

TR = timezone(timedelta(hours=3))
DESTEK = "/api/v1/destek"
KB_Y = "/api/v1/bilgi-bankasi/yonetim"
KB = "/api/v1/bilgi-bankasi"
MODUL = "/api/v1/moduller"


def _eposta(on: str = "destek") -> str:
    return f"{on}-{uuid.uuid4().hex[:10]}@test.dev"


def _tr(y, a, g, s=0, d=0):
    return datetime(y, a, g, s, d, tzinfo=TR)


def _ayar(tatiller=()):
    from services.sla import MesaiAyari, _tatilleri_ayir

    tam, yarim = _tatilleri_ayir(tatiller)
    return MesaiAyari(tatiller=tam, yarim_gunler=yarim)


# ---------------------------------------------------------------------------
# Mesai hesabı — saf fonksiyon
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "baslangic, dakika, beklenen, tatiller",
    [
        # 1) Pazartesi mesai içi
        (_tr(2026, 10, 5, 10), 60, _tr(2026, 10, 5, 11), ()),
        # 2) Gün sonuna taşan → ertesi sabah
        (_tr(2026, 10, 5, 17, 30), 60, _tr(2026, 10, 6, 9, 30), ()),
        # 3) Cuma 17:00 + 4 saat → Pazartesi 12:00 (hafta sonu atlanır)
        (_tr(2026, 10, 9, 17), 240, _tr(2026, 10, 12, 12), ()),
        # 4) Cumartesi açılan talep → Pazartesi 09:00'dan sayılır
        (_tr(2026, 10, 10, 12), 60, _tr(2026, 10, 12, 10), ()),
        # 5) Gece 22:00 → ertesi sabah 09:00'dan
        (_tr(2026, 10, 6, 22), 30, _tr(2026, 10, 7, 9, 30), ()),
        # 6) Sabah 07:00 (mesai öncesi) → aynı gün 09:00'dan
        (_tr(2026, 10, 7, 7), 30, _tr(2026, 10, 7, 9, 30), ()),
        # 7) Tatil geçişi: Çarşamba 17:00 + 2 saat, Perşembe 29 Ekim tatil → Cuma 10:00
        (_tr(2026, 10, 28, 17), 120, _tr(2026, 10, 30, 10), ("2026-10-29",)),
        # 8) Tam gün: 09:00 + 540 dk → aynı gün 18:00 (ertesi güne kaymaz)
        (_tr(2026, 10, 5, 9), 540, _tr(2026, 10, 5, 18), ()),
        # 9) Üç iş günü: Pazartesi 09:00 + 1620 → Çarşamba 18:00
        (_tr(2026, 10, 5, 9), 1620, _tr(2026, 10, 7, 18), ()),
        # 10) Tatil + hafta sonu birlikte: Perşembe tatil, Cuma 17:30 + 60 → Pazartesi 09:30
        (_tr(2026, 10, 30, 17, 30), 60, _tr(2026, 11, 2, 9, 30), ("2026-10-29",)),
        # 11) Tatilde açılan talep: sonraki iş gününün başından sayılır
        (_tr(2026, 10, 29, 11), 90, _tr(2026, 10, 30, 10, 30), ("2026-10-29",)),
        # 12) UTC girdi: 06:00 UTC = 09:00 TR
        (datetime(2026, 10, 5, 6, 0, tzinfo=timezone.utc), 15, _tr(2026, 10, 5, 9, 15), ()),
    ],
)
def test_mesai_ekle(baslangic, dakika, beklenen, tatiller):
    from services.sla import mesai_ekle

    assert mesai_ekle(baslangic, dakika, _ayar(tatiller)) == beklenen.astimezone(timezone.utc)


def test_mesai_dakikasi_ve_ters_yon():
    from services.sla import mesai_dakikasi

    a = _ayar(("2026-10-29",))
    assert mesai_dakikasi(_tr(2026, 10, 9, 17), _tr(2026, 10, 12, 10), a) == 120  # hafta sonu sayılmaz
    assert mesai_dakikasi(_tr(2026, 10, 28, 20), _tr(2026, 10, 30, 8), a) == 0  # gece + tatil
    assert mesai_dakikasi(_tr(2026, 10, 12, 10), _tr(2026, 10, 9, 17), a) == -120
    assert mesai_dakikasi(_tr(2026, 10, 5, 8), _tr(2026, 10, 5, 19), a) == 540


def test_hedef_durumu():
    from services.sla import hedef_durumu

    a = _ayar()
    hedef = _tr(2026, 10, 5, 13)
    assert hedef_durumu(None, None, _tr(2026, 10, 5, 10), 240, a)["durum"] == "yok"
    assert hedef_durumu(hedef, None, _tr(2026, 10, 5, 10), 240, a)["durum"] == "zamaninda"
    d = hedef_durumu(hedef, None, _tr(2026, 10, 5, 12, 30), 240, a)
    assert d["durum"] == "yaklasiyor" and d["kalan_dk"] == 30
    d = hedef_durumu(hedef, None, _tr(2026, 10, 5, 14), 240, a)
    assert d["durum"] == "asildi" and d["kalan_dk"] == -60
    assert hedef_durumu(hedef, _tr(2026, 10, 5, 12), _tr(2026, 10, 6, 10), 240, a)["durum"] == "karsilandi"
    assert hedef_durumu(hedef, _tr(2026, 10, 5, 15), _tr(2026, 10, 6, 10), 240, a)["durum"] == "gecikti"


def test_oncelik_ve_ayar_dogrulama():
    from services.sla import SlaHatasi, ayarlari_coz, oncelik_duzelt

    assert [oncelik_duzelt(x) for x in ("urgent", "High", "düşük", None, "normal", "medium")] == [
        "acil", "yuksek", "dusuk", "normal", "normal", "normal",
    ]
    varsayilan = ayarlari_coz(None)
    assert date(2026, 10, 29) in varsayilan.mesai.tatiller and varsayilan.mesai.bas_dk == 540
    for bozuk in (
        {"mesai": {"bas": "18:00", "bit": "09:00"}},
        {"mesai": {"gunler": [7]}},
        {"tatiller": ["2026-13-01"]},
        {"hedefler": {"acil": {"ilk_yanit_dk": 600, "cozum_dk": 60}}},
        {"hedefler": {"bilinmeyen": {"ilk_yanit_dk": 1}}},
    ):
        with pytest.raises(SlaHatasi):
            ayarlari_coz(bozuk, sessiz=False)
        assert ayarlari_coz(bozuk).mesai.bas_dk == 540  # sessiz → varsayılan


# ---------------------------------------------------------------------------
# SLA uçları ve zamanlı kontrol
# ---------------------------------------------------------------------------
async def _talep(istemci, musteri_basligi, eposta, konu="Sitem açılmıyor", oncelik="normal"):
    y = await istemci.post(
        "/api/v1/entities/support_tickets",
        json={"client_email": eposta, "client_name": "Ayşe Yılmaz", "subject": konu, "message": "Yardım", "status": "open", "priority": oncelik},
        headers=musteri_basligi(eposta),
    )
    assert y.status_code == 201, y.text
    return y.json()


async def _bildirim_sayisi(db, olay, ref_id):
    from models.notifications import Notifications

    db.expire_all()
    satirlar = (
        await db.execute(
            select(Notifications.id).where(Notifications.event_type == olay, Notifications.ref_id == ref_id, Notifications.channel == "inapp")
        )
    ).all()
    return len(satirlar)


async def test_talep_acilinca_sla_satiri_ve_yetki(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    from models.destek_sla import TalepSla
    from services.sla import mesai_ekle

    eposta = _eposta()
    t = await _talep(istemci, musteri_basligi, eposta, oncelik="acil")
    satir = (await db_oturumu.execute(select(TalepSla).where(TalepSla.ticket_id == t["id"]))).scalar_one()
    assert satir.oncelik == "acil"
    bas = satir.baslangic.replace(tzinfo=timezone.utc) if satir.baslangic.tzinfo is None else satir.baslangic
    hedef = satir.ilk_yanit_hedef.replace(tzinfo=timezone.utc) if satir.ilk_yanit_hedef.tzinfo is None else satir.ilk_yanit_hedef
    assert hedef == mesai_ekle(bas, 60, _ayar(__import__("services.sla", fromlist=["x"]).VARSAYILAN_TATILLER))

    y = await istemci.get(f"{DESTEK}/sla", params={"ids": str(t["id"])}, headers=yonetici_basligi)
    assert y.status_code == 200
    d = y.json()[str(t["id"])]
    assert d["oncelik"] == "acil" and d["ilk_yanit"]["durum"] in ("zamaninda", "yaklasiyor", "asildi") and d["ozet"]
    assert (await istemci.get(f"{DESTEK}/sla", headers=musteri_basligi(eposta))).status_code == 403
    assert (await istemci.get(f"{DESTEK}/sla")).status_code == 401

    # Müşteri yalnız kendi taleplerini görür.
    baska = _eposta("baska")
    t2 = await _talep(istemci, musteri_basligi, baska)
    bilgi = (await istemci.get(f"{DESTEK}/sla-bilgisi", headers=musteri_basligi(eposta))).json()
    assert set(bilgi["talepler"]) == {str(t["id"])} and str(t2["id"]) not in bilgi["talepler"]
    assert bilgi["mesai"]["bas"] == "09:00" and bilgi["hedefler"]["normal"]["ilk_yanit_dk"] == 240
    assert "eskalasyon" not in str(bilgi)

    # Ajans yanıtı ilk yanıtı karşılar.
    y = await istemci.post(f"/api/v1/talep/{t['id']}/mesaj", json={"mesaj": "Bakıyoruz"}, headers=yonetici_basligi)
    assert y.status_code == 200
    d = (await istemci.get(f"{DESTEK}/sla", params={"ids": str(t["id"])}, headers=yonetici_basligi)).json()[str(t["id"])]
    assert d["ilk_yanit"]["durum"] in ("karsilandi", "gecikti")
    # Kapatılınca çözüm tamam; yeniden açılınca geri döner.
    await istemci.put(f"/api/v1/entities/support_tickets/{t['id']}", json={"status": "closed"}, headers=yonetici_basligi)
    d = (await istemci.get(f"{DESTEK}/sla", params={"ids": str(t["id"])}, headers=yonetici_basligi)).json()[str(t["id"])]
    assert d["cozum"]["durum"] in ("karsilandi", "gecikti")
    await istemci.put(f"/api/v1/entities/support_tickets/{t['id']}", json={"status": "open"}, headers=yonetici_basligi)
    d = (await istemci.get(f"{DESTEK}/sla", params={"ids": str(t["id"])}, headers=yonetici_basligi)).json()[str(t["id"])]
    assert d["cozum"]["durum"] not in ("karsilandi", "gecikti")


async def test_eskalasyon_ve_uyari_bir_kez(istemci, musteri_basligi, db_oturumu):
    from models.destek_sla import TalepSla
    from services.sla import sla_kontrolu

    eposta = _eposta("esk")
    asilan = await _talep(istemci, musteri_basligi, eposta, "Ödeme sayfası hata veriyor")
    yaklasan = await _talep(istemci, musteri_basligi, eposta, "Logo değişikliği")
    simdi = datetime.now(timezone.utc)
    await db_oturumu.execute(
        update(TalepSla).where(TalepSla.ticket_id == asilan["id"]).values(
            ilk_yanit_hedef=simdi - timedelta(hours=1), cozum_hedef=simdi + timedelta(days=30)
        )
    )
    # "Yaklaşıyor": hedefe birkaç mesai dakikası — her an için tutarlı olsun diye
    # hedefi şimdiye çok yakın ve SLA mesaisini 7/24 yapan ayarla.
    await db_oturumu.execute(
        update(TalepSla).where(TalepSla.ticket_id == yaklasan["id"]).values(
            ilk_yanit_hedef=simdi + timedelta(minutes=10), cozum_hedef=simdi + timedelta(days=30)
        )
    )
    await db_oturumu.commit()
    from services import sla as sla_servis

    ayar = await sla_servis.ayarlari_oku(db_oturumu)
    tam_gun = sla_servis.SlaAyarlari(
        mesai=sla_servis.MesaiAyari(bas_dk=0, bit_dk=24 * 60, gunler=frozenset(range(7))), hedefler=ayar.hedefler
    )

    async def sabit_ayar(db):
        return tam_gun

    import unittest.mock as m

    with m.patch.object(sla_servis, "ayarlari_oku", sabit_ayar):
        # Öncelik değişmesin diye hedefleri yeniden hesaplatacak bir şey yok; iki tur.
        await sla_kontrolu(db_oturumu)
        await sla_kontrolu(db_oturumu)
    assert await _bildirim_sayisi(db_oturumu, "sla_asildi", asilan["id"]) == 1
    assert await _bildirim_sayisi(db_oturumu, "sla_yaklasiyor", asilan["id"]) == 0  # aşılan için ayrıca uyarı yok
    assert await _bildirim_sayisi(db_oturumu, "sla_yaklasiyor", yaklasan["id"]) == 1
    assert await _bildirim_sayisi(db_oturumu, "sla_asildi", yaklasan["id"]) == 0
    db_oturumu.expire_all()
    s = (await db_oturumu.execute(select(TalepSla).where(TalepSla.ticket_id == asilan["id"]))).scalar_one()
    assert s.eskalasyon_ilk_at is not None and s.eskalasyon_cozum_at is None


async def test_eski_talepte_geriye_donuk_eskalasyon_yagmuru_yok(db_oturumu):
    from models.support_tickets import Support_tickets
    from services.sla import senkronla, sla_kontrolu

    t = Support_tickets(
        client_email=_eposta("eski"), subject="Eski talep", message="x", status="open", priority="normal",
        created_at=datetime.now() - timedelta(days=60),
    )
    db_oturumu.add(t)
    await db_oturumu.commit()
    tid = t.id
    await sla_kontrolu(db_oturumu)
    assert await _bildirim_sayisi(db_oturumu, "sla_asildi", tid) == 0
    t = (await db_oturumu.execute(select(Support_tickets).where(Support_tickets.id == tid))).scalar_one()
    satirlar = await senkronla(db_oturumu, [t])
    assert satirlar[tid].eskalasyon_ilk_at is not None  # "gönderildi" sayıldı


async def test_sla_ayarlari_uclari(istemci, yonetici_basligi, musteri_basligi):
    assert (await istemci.get(f"{DESTEK}/sla-ayarlari", headers=musteri_basligi(_eposta()))).status_code == 403
    mevcut = (await istemci.get(f"{DESTEK}/sla-ayarlari", headers=yonetici_basligi)).json()
    assert mevcut["mesai"] == {"bas": "09:00", "bit": "18:00", "gunler": [0, 1, 2, 3, 4]}
    y = await istemci.put(f"{DESTEK}/sla-ayarlari", json={"mesai": {"bas": "10:00", "bit": "09:00"}}, headers=yonetici_basligi)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "gecersiz_saat"
    yeni = {**mevcut, "tatiller": mevcut["tatiller"] + ["2026-12-31"], "hedefler": {**mevcut["hedefler"], "acil": {"ilk_yanit_dk": 30, "cozum_dk": 120}}}
    y = await istemci.put(f"{DESTEK}/sla-ayarlari", json=yeni, headers=yonetici_basligi)
    assert y.status_code == 200 and "2026-12-31" in y.json()["tatiller"] and y.json()["hedefler"]["acil"]["ilk_yanit_dk"] == 30
    await istemci.put(f"{DESTEK}/sla-ayarlari", json=mevcut, headers=yonetici_basligi)


# ---------------------------------------------------------------------------
# Hazır cevaplar
# ---------------------------------------------------------------------------
def test_degisken_doldurma():
    from routers.destek import degiskenleri_doldur

    metin = "Merhaba {musteri_adi}, {talep_no} ({konu}) {bilinmeyen} {musteri_adi}"
    assert degiskenleri_doldur(metin, {"musteri_adi": "Ayşe", "talep_no": "#12", "konu": "Logo"}) == (
        "Merhaba Ayşe, #12 (Logo) {bilinmeyen} Ayşe"
    )
    assert degiskenleri_doldur("{musteri_adi}", {"musteri_adi": None}) == "{musteri_adi}"


async def test_hazir_cevap_uclari(istemci, yonetici_basligi, musteri_basligi):
    eposta = _eposta("hc")
    t = await _talep(istemci, musteri_basligi, eposta, "Fatura kopyası")
    assert (await istemci.get(f"{DESTEK}/hazir-cevaplar", headers=musteri_basligi(eposta))).status_code == 403
    assert (await istemci.post(f"{DESTEK}/hazir-cevaplar", json={"baslik": "", "metin": "x"}, headers=yonetici_basligi)).status_code == 400
    hc = (await istemci.post(
        f"{DESTEK}/hazir-cevaplar",
        json={"baslik": "Karşılama", "metin": "Merhaba {musteri_adi}, {talep_no} numaralı \"{konu}\" talebinizi aldık."},
        headers=yonetici_basligi,
    )).json()
    y = await istemci.post(f"{DESTEK}/hazir-cevaplar/{hc['id']}/uygula", json={"ticket_id": t["id"]}, headers=yonetici_basligi)
    assert y.json()["metin"] == f"Merhaba Ayşe Yılmaz, #{t['id']} numaralı \"Fatura kopyası\" talebinizi aldık."
    assert (await istemci.post(f"{DESTEK}/hazir-cevaplar/{hc['id']}/uygula", json={"ticket_id": 999999}, headers=yonetici_basligi)).status_code == 404
    y = await istemci.put(f"{DESTEK}/hazir-cevaplar/{hc['id']}", json={"baslik": "Karşılama 2", "metin": "Selam {musteri_adi}"}, headers=yonetici_basligi)
    assert y.json()["baslik"] == "Karşılama 2"
    assert any(h["id"] == hc["id"] for h in (await istemci.get(f"{DESTEK}/hazir-cevaplar", headers=yonetici_basligi)).json())
    assert (await istemci.delete(f"{DESTEK}/hazir-cevaplar/{hc['id']}", headers=yonetici_basligi)).status_code == 200


# ---------------------------------------------------------------------------
# Bilgi bankası
# ---------------------------------------------------------------------------
def test_kb_html_temizleme():
    from services.guvenli_html import markdown_html, temizle, url_guvenli_mi

    html = markdown_html(
        "# Başlık\n\nMetin <script>alert(1)</script> <img src=x onerror=alert(1)> "
        "<a href=\"javascript:alert(1)\">a</a> [b](JaVaScRiPt:alert(1)) [c](java\tscript:x) "
        "<a href=\"&#106;avascript:alert(1)\">d</a> <iframe src=\"https://x\"></iframe> "
        "<div onclick=\"x()\" style=\"x\">e</div> [iyi](https://ornek.com)\n\n```\n<script>kod</script>\n```"
    )
    alt = html.lower()
    assert "<script" not in alt and "onerror" not in alt and "onclick" not in alt
    assert "javascript:" not in alt and "<iframe" not in alt and "style=" not in alt
    assert '<a href="https://ornek.com" rel="noopener noreferrer nofollow" target="_blank">iyi</a>' in html
    assert "&lt;script&gt;kod&lt;/script&gt;" in html  # kod bloğunda metin olarak
    assert "<h2>Başlık</h2>" in html
    assert temizle('<p onmouseover="x">a<svg><script>1</script></svg></p>') == "<p>a</p>"
    assert temizle("<img src=\"data:image/png;base64,AAA\">") == ""
    for kotu in ("javascript:alert(1)", " JAVASCRIPT:x", "java\nscript:x", "vbscript:x", "data:text/html,x", "&#x6A;avascript:x"):
        assert not url_guvenli_mi(kotu), kotu
    for iyi in ("https://a.b", "/yardim", "#baslik", "mailto:a@b.c"):
        assert url_guvenli_mi(iyi), iyi


async def test_kb_yonetim_arama_oneri_ve_bekci(istemci, yonetici_basligi, musteri_basligi):
    eposta = _eposta("kb")
    assert (await istemci.post(KB_Y, json={"baslik": "x"}, headers=musteri_basligi(eposta))).status_code == 403
    assert (await istemci.post(KB_Y, json={"baslik": "x", "durum": "bilinmiyor"}, headers=yonetici_basligi)).status_code == 400
    anahtar = uuid.uuid4().hex[:6]
    yayinda = (await istemci.post(
        KB_Y,
        json={
            "kategori": "Hosting",
            "baslik": f"E-posta şifresi nasıl sıfırlanır {anahtar}",
            "icerik": "Panelden **şifre** sıfırlayın.\n\n<script>alert(1)</script>",
            "ceviriler": {"en": {"baslik": f"How to reset your email password {anahtar}", "icerik": "Use the **panel**."}},
            "durum": "yayinda",
        },
        headers=yonetici_basligi,
    )).json()
    taslak = (await istemci.post(KB_Y, json={"baslik": f"Gizli taslak şifre {anahtar}", "icerik": "x", "durum": "taslak"}, headers=yonetici_basligi)).json()
    assert (await istemci.post(KB_Y, json={"baslik": "x", "ceviriler": {"xx": {"baslik": "a"}}}, headers=yonetici_basligi)).status_code == 400
    onizleme = (await istemci.post(f"{KB_Y}/onizle", json={"icerik": "**a** <script>1</script>"}, headers=yonetici_basligi)).json()
    assert onizleme["html"] == "<p><strong>a</strong> </p>"

    # Arama: Türkçe karakter/büyük harf duyarsız; taslak görünmez.
    sonuc = (await istemci.get(KB, params={"q": f"SİFRE {anahtar}"}, headers=musteri_basligi(eposta))).json()["makaleler"]
    assert [m["id"] for m in sonuc] == [yayinda["id"]]
    assert "<" not in sonuc[0]["ozet"] or "script" not in sonuc[0]["ozet"]
    # Dil: İngilizce çeviri; Almanca yoksa Türkçeye düşer.
    en = (await istemci.get(f"{KB}/{yayinda['id']}", params={"dil": "en"}, headers=musteri_basligi(eposta))).json()
    assert en["baslik"].startswith("How to reset") and en["dil"] == "en" and "<strong>panel</strong>" in en["html"]
    de = (await istemci.get(f"{KB}/{yayinda['id']}", params={"dil": "de"}, headers=musteri_basligi(eposta))).json()
    assert de["dil"] == "tr" and "<script" not in de["html"] and "<strong>şifre</strong>" in de["html"]
    assert (await istemci.get(f"{KB}/{taslak['id']}", headers=musteri_basligi(eposta))).status_code == 404
    # İngilizce arama İngilizce çeviride bulur.
    assert [m["id"] for m in (await istemci.get(KB, params={"q": f"reset {anahtar}", "dil": "en"}, headers=musteri_basligi(eposta))).json()["makaleler"]] == [yayinda["id"]]
    # Öneri: talep başlığından.
    oneri = (await istemci.get(f"{KB}/oneri", params={"baslik": f"e-posta şifremi unuttum {anahtar}"}, headers=musteri_basligi(eposta))).json()
    assert [m["id"] for m in oneri["makaleler"]][:1] == [yayinda["id"]]
    assert (await istemci.get(f"{KB}/oneri", params={"baslik": "ve"}, headers=musteri_basligi(eposta))).json() == {"makaleler": []}
    # Oturumsuz 401; modül kapalıysa 403.
    assert (await istemci.get(KB)).status_code == 401
    kapali = _eposta("kbkapali")
    await istemci.put(f"{MODUL}/musteri/{kapali}/bilgi_bankasi", json={"acik": False}, headers=yonetici_basligi)
    y = await istemci.get(KB, headers=musteri_basligi(kapali))
    assert y.status_code == 403 and y.json()["detail"]["modul"] == "bilgi_bankasi"

    y = await istemci.put(f"{KB_Y}/{taslak['id']}", json={"baslik": "Yayında artık", "icerik": "x", "durum": "yayinda"}, headers=yonetici_basligi)
    assert y.json()["durum"] == "yayinda"
    assert (await istemci.delete(f"{KB_Y}/{taslak['id']}", headers=yonetici_basligi)).status_code == 200


def test_arife_yarim_gun_mesai_13te_biter():
    from datetime import datetime, date
    from services.sla import ayarlari_coz, _pencere, TR

    ayar = ayarlari_coz({"tatiller": ["2026-03-20", "2026-03-19 yarım"]}).mesai
    bas, bit = _pencere(date(2026, 3, 19), ayar)
    assert bas == datetime(2026, 3, 19, 9, 0, tzinfo=TR) and bit == datetime(2026, 3, 19, 13, 0, tzinfo=TR)
    assert _pencere(date(2026, 3, 20), ayar) is None
    # varsayılan listede arifeler var ve sözlükte "yarım" olarak dönüyor
    from services.sla import SlaAyarlari
    varsayilan = ayarlari_coz({})
    assert date(2026, 5, 26) in varsayilan.mesai.yarim_gunler
    assert "2026-05-26 yarım" in varsayilan.sozluk()["tatiller"]
    import pytest
    from services.sla import SlaHatasi
    with pytest.raises(SlaHatasi):
        ayarlari_coz({"tatiller": ["2026-03-19 bilmem"]}, sessiz=False)
