"""Faz 5B — belgeler, wiki ve strateji araçları.

Kapsam:
* CRUD + arama (Türkçe büyük/küçük harf, aksan) + etiket süzgeci; sürüm geçmişi, geri yükleme,
  eşzamanlı düzenleme çatışması (409), sürüm sınırı.
* Temizleyici: XSS denemeleri (betik, olay özniteliği, javascript:/data: adresi, varlıklı
  `java&#09;script:`, tablo ve yapılacak maddesi içinde) — ham HTML hiç geçmiyor.
* Görünürlük/yalıtım: ekip içi belge müşteriye sızmıyor; müşteri A, B'nin belgesini göremiyor;
  paylaşılan belge salt okunur; müşterinin paylaşılmamış belgesi ajansta yok.
* Modül kapalıyken müşteri oluşturma 403, paylaşılan okuma 200; belge sınırı.
* Strateji şablonları: ızgara tutarlılığı, doğrulama (bilinmeyen kutu, metin dışı, uzun); PDF/MD.
* Yapılacaklar: "Yapılacaklarım", işaretleme, eskimiş satır 409, görev bağı (Faz 2B ucu).
* AI: `ENVIRONMENT=test` sahte yanıt; anahtar yokken 503 `ai_kapali` (hak düşmeden); aylık sınır.
* Çöp kutusu (sürümlerle geri gelir; ajans belgesi müşterinin çöpünde yok), gelen kutusu,
  bildirim, PDF üretimi; ön yüz etiketleri sunucuyla aynı (tr/en/de).
"""

import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from conftest import jeton_uret

Y = "/api/v1/belgeler"
M = "/api/v1/belgelerim"
MODUL = "/api/v1/moduller"
ON_YUZ = Path(__file__).resolve().parents[3] / "frontend"
DILLER = ("tr", "en", "de", "ru", "zh", "hi", "ar")


def _e(on: str = "belge") -> str:
    return f"{on}-{uuid.uuid4().hex[:8]}@ornek-firma.com"


def _b(eposta: str) -> dict:
    return {"Authorization": f"Bearer {jeton_uret(eposta)}"}


async def _modul_ac(istemci, yb, eposta, acik=True, **ayarlar):
    govde = {"acik": acik}
    if ayarlar:
        govde["ayarlar"] = ayarlar
    y = await istemci.put(f"{MODUL}/musteri/{eposta}/belgeler", json=govde, headers=yb)
    assert y.status_code == 200, y.text


async def _belge(istemci, basliklar, yol=Y, **govde):
    govde.setdefault("baslik", "Ajans wiki: işe başlama")
    govde.setdefault("icerik", "# Giriş\n\nHoş geldiniz.")
    y = await istemci.post(yol, json=govde, headers=basliklar)
    assert y.status_code == 200, y.text
    return y.json()


async def _bildirimler(db, eposta, olay):
    from models.notifications import Notifications

    db.expire_all()
    return (await db.execute(select(Notifications).where(
        Notifications.event_type == olay, Notifications.recipient_email == eposta, Notifications.channel == "inapp"
    ))).scalars().all()


@pytest.fixture(autouse=True)
def _ai_kapali_varsayilan(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)


# ---------------------------------------------------------------------------
# Saf kurallar
# ---------------------------------------------------------------------------
def test_strateji_izgaralari_tutarli_ve_sekiz_sablon():
    from services.belgeler import STRATEJI_SABLONLARI

    assert set(STRATEJI_SABLONLARI) == {"swot", "is_modeli", "lean", "pestle", "porter", "mckinsey_7s", "mavi_okyanus", "ikigai"}
    assert len(STRATEJI_SABLONLARI["is_modeli"].kutular) == 9 and len(STRATEJI_SABLONLARI["lean"].kutular) == 9
    for s in STRATEJI_SABLONLARI.values():
        dolu = set()
        for k in s.kutular:
            assert 1 <= k.sutun and k.sutun + k.en - 1 <= s.sutun, (s.tur, k.anahtar)
            assert 1 <= k.satir and k.satir + k.boy - 1 <= s.satir, (s.tur, k.anahtar)
            hucreler = {(x, y) for x in range(k.sutun, k.sutun + k.en) for y in range(k.satir, k.satir + k.boy)}
            assert not (hucreler & dolu), (s.tur, k.anahtar)  # çakışma yok
            dolu |= hucreler
        assert len(set(s.anahtarlar)) == len(s.anahtarlar)


def test_on_yuz_sablon_adlari_sunucuyla_ayni_ve_yedi_dilde():
    from services.belgeler import SABLON_ADLARI, STRATEJI_SABLONLARI

    for dil in DILLER:
        ek = json.loads((ON_YUZ / "src/i18n/ek/belgeler" / f"{dil}.json").read_text(encoding="utf-8"))["belgeler"]
        for tur, s in STRATEJI_SABLONLARI.items():
            assert ek["sablon"][tur]["ad"].strip(), (dil, tur)
            for k in s.anahtarlar:
                assert ek["sablon"][tur]["kutu"][k].strip(), (dil, tur, k)
                if dil in SABLON_ADLARI:
                    assert ek["sablon"][tur]["kutu"][k] == SABLON_ADLARI[dil][tur][k], (dil, tur, k)
            if dil in SABLON_ADLARI:
                assert ek["sablon"][tur]["ad"] == SABLON_ADLARI[dil][tur]["ad"], (dil, tur)
        if dil != "tr":
            tr = json.loads((ON_YUZ / "src/i18n/ek/belgeler/tr.json").read_text(encoding="utf-8"))["belgeler"]
            assert ek["sablon"]["swot"]["kutu"]["guclu"] != tr["sablon"]["swot"]["kutu"]["guclu"], dil


@pytest.mark.parametrize("yuk", [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "[tıkla](javascript:alert(1))",
    "[tıkla](JaVaScRiPt:alert(1))",
    "[tıkla](java&#09;script:alert(1))",
    "[tıkla](data:text/html;base64,PHNjcmlwdD4=)",
    "![g](javascript:alert(1))",
    '"><svg onload=alert(1)>',
    "<iframe src=https://kotu.example></iframe>",
    "| a | b |\n|---|---|\n| <script>alert(1)</script> | [x](javascript:alert(1)) |",
    "- [ ] <img src=x onerror=alert(1)> **kalın**",
    "# <a href=javascript:alert(1)>başlık</a>",
    "`<script>` ve ```\n<script>alert(1)</script>\n```",
])
def test_temizleyici_xss_denemeleri(yuk):
    import html as _html
    import re

    from services.guvenli_html import belge_html

    h = belge_html(yuk)
    etiketler = re.findall(r"<([a-zA-Z][^>]*)>", h)
    adlar = {e.split()[0].lower() for e in etiketler}
    # Yalnız izinli etiketler; betik/çerçeve/svg hiç yok (metin olarak kaçışlı görünebilir).
    assert adlar <= {"p", "br", "ul", "ol", "li", "strong", "em", "s", "code", "pre", "a", "table", "thead", "tbody",
                     "tr", "th", "td", "h2", "h3", "h4", "h5", "hr", "blockquote", "img"}, adlar
    for e in etiketler:
        assert not re.search(r"\son[a-z]+\s*=", e, re.I), e
        for adres in re.findall(r'(?:href|src)="([^"]*)"', e):
            sade = re.sub(r"[\x00-\x20]", "", _html.unescape(adres)).lower()
            assert not sade.startswith(("javascript:", "data:", "vbscript:")), e
        if e.lower().startswith("img"):
            assert re.search(r'src="https?://', e), e


def test_markdown_tablo_yapilacak_ve_satir_numarasi():
    from services.belgeler import yapilacaklar_cikar
    from services.guvenli_html import belge_html

    md = "Giriş\n\n- [ ] Logoyu yükle @ali@ornek.com\n- [x] Sözleşme\n\n| Ad | Not |\n|---|---|\n| **A** | b |\n\n```\n- [ ] kodda\n```"
    h = belge_html(md)
    assert '<li data-satir="2" data-tamam="0">☐ Logoyu yükle @ali@ornek.com</li>' in h
    assert 'data-satir="3" data-tamam="1"' in h and "<s>Sözleşme</s>" in h
    assert "<table><thead><tr><th>Ad</th><th>Not</th></tr></thead><tbody><tr><td><strong>A</strong></td><td>b</td></tr>" in h
    ogeler = yapilacaklar_cikar(md)
    assert [(o["satir"], o["tamam"], o["atananlar"]) for o in ogeler] == [(2, False, ["ali@ornek.com"]), (3, True, [])]


def test_bilgi_bankasi_temizleyicisi_degismedi():
    """Belge kipi eklenirken KB çıktısı aynı kaldı (data-* öznitelikleri KB'de geçmiyor)."""
    from services.guvenli_html import markdown_html, temizle

    assert markdown_html("**a** <kbd>Ctrl</kbd>") == "<p><strong>a</strong> <kbd>Ctrl</kbd></p>"
    assert temizle('<li data-satir="3">x</li>') == "<li>x</li>"


def test_arama_normallestirme():
    from services.belgeler import arama_normalle

    assert arama_normalle("ŞİRKET İçi Işık") == "sirket ici isik"
    assert arama_normalle("Straße") == "strasse"


# ---------------------------------------------------------------------------
# Yönetici CRUD, arama, sürüm
# ---------------------------------------------------------------------------
async def test_yetkisiz_ve_musteri_yonetici_uclarina_giremez(istemci):
    assert (await istemci.get(Y)).status_code == 401
    y = await istemci.get(Y, headers=_b(_e()))
    assert y.status_code == 403
    assert (await istemci.get(f"{M}/ozet")).status_code == 401


async def test_crud_arama_etiket_ve_sabit(istemci, yonetici_basligi):
    yb = yonetici_basligi
    a = await _belge(istemci, yb, baslik="Şirket içi süreçler", icerik="Kahve makinesi bakımı", etiketler=["Süreç", "süreç", "İK"])
    assert a["etiketler"] == ["Süreç", "İK"] and a["alan"] == "ajans" and a["gorunurluk"] == "ekip"
    assert a["surum"] == 1 and "<p>Kahve makinesi bakımı</p>" in a["html"]
    b = await _belge(istemci, yb, baslik="Başka not", icerik="Bambaşka", sabit=True)
    # Türkçe büyük/küçük harf + aksansız arama (SQLite lower() yalnız ASCII'yi küçültüyor).
    for q in ("sirket", "ŞİRKET", "kahve MAKİNESİ", "surec"):
        y = await istemci.get(Y, params={"q": q}, headers=yb)
        assert a["id"] in [x["id"] for x in y.json()["items"]], q
    y = await istemci.get(Y, params={"etiket": "ik"}, headers=yb)
    ids = [x["id"] for x in y.json()["items"]]
    assert a["id"] in ids and b["id"] not in ids
    assert any(e["ad"] == "Süreç" for e in y.json()["etiketler"])
    # Sabit belge listede önde.
    liste = (await istemci.get(Y, headers=yb)).json()["items"]
    assert liste[0]["sabit"] is True
    # Güncelle, sil.
    y = await istemci.put(f"{Y}/{a['id']}", json={"baslik": "Süreçler (güncel)", "etiketler": []}, headers=yb)
    assert y.status_code == 200 and y.json()["baslik"] == "Süreçler (güncel)" and y.json()["etiketler"] == []
    y = await istemci.put(f"{Y}/{a['id']}", json={"baslik": "   "}, headers=yb)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "metin_gerekli"
    y = await istemci.post(Y, json={"baslik": "x" * 201}, headers=yb)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "metin_uzun"
    y = await istemci.post(Y, json={"baslik": "x", "etiketler": [f"e{i}" for i in range(11)]}, headers=yb)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "cok_fazla"
    y = await istemci.delete(f"{Y}/{a['id']}", headers=yb)
    assert y.status_code == 200
    assert (await istemci.get(f"{Y}/{a['id']}", headers=yb)).status_code == 404


async def test_surum_gecmisi_geri_yukleme_ve_catisma(istemci, yonetici_basligi):
    yb = yonetici_basligi
    a = await _belge(istemci, yb, icerik="v1")
    await istemci.put(f"{Y}/{a['id']}", json={"icerik": "v2", "surum": 1}, headers=yb)
    y = await istemci.put(f"{Y}/{a['id']}", json={"icerik": "v3", "surum": 2}, headers=yb)
    assert y.json()["surum"] == 3
    # Başkası arada kaydetti: eski sürümle kaydetmek 409.
    y = await istemci.put(f"{Y}/{a['id']}", json={"icerik": "çakışan", "surum": 2}, headers=yb)
    assert y.status_code == 409 and y.json()["detail"] == {"kod": "surum_catismasi", "guncel": 3}
    # Değişiklik yoksa sürüm artmıyor.
    y = await istemci.put(f"{Y}/{a['id']}", json={"icerik": "v3"}, headers=yb)
    assert y.json()["surum"] == 3
    s = (await istemci.get(f"{Y}/{a['id']}/surumler", headers=yb)).json()
    assert [x["surum"] for x in s["items"]] == [3, 2, 1] and s["guncel"] == 3
    ilk = s["items"][-1]
    d = (await istemci.get(f"{Y}/{a['id']}/surumler/{ilk['id']}", headers=yb)).json()
    assert d["icerik"] == "v1" and "<p>v1</p>" in d["html"]
    y = await istemci.post(f"{Y}/{a['id']}/surumler/{ilk['id']}/geri-yukle", headers=yb)
    assert y.status_code == 200 and y.json()["icerik"] == "v1" and y.json()["surum"] == 4
    s = (await istemci.get(f"{Y}/{a['id']}/surumler", headers=yb)).json()["items"]
    assert s[0]["surum"] == 4 and s[0]["aciklama"] == "geri_yukleme:1"
    # Başka belgenin sürümü bu belgeye geri yüklenemez.
    b = await _belge(istemci, yb, icerik="başka")
    y = await istemci.post(f"{Y}/{b['id']}/surumler/{ilk['id']}/geri-yukle", headers=yb)
    assert y.status_code == 404


async def test_surum_siniri_eskiler_silinir(istemci, yonetici_basligi):
    from services.belgeler import SURUM_SINIRI

    a = await _belge(istemci, yonetici_basligi, icerik="0")
    for i in range(1, SURUM_SINIRI + 5):
        await istemci.put(f"{Y}/{a['id']}", json={"icerik": str(i)}, headers=yonetici_basligi)
    s = (await istemci.get(f"{Y}/{a['id']}/surumler", headers=yonetici_basligi)).json()["items"]
    assert len(s) == SURUM_SINIRI and s[0]["surum"] == SURUM_SINIRI + 5


async def test_onizleme_temiz_html(istemci, yonetici_basligi):
    y = await istemci.post(f"{Y}/onizle", json={"icerik": "**a** <script>alert(1)</script>\n\n- [ ] b"}, headers=yonetici_basligi)
    assert y.status_code == 200
    assert "<strong>a</strong> &lt;script&gt;" in y.json()["html"] and y.json()["yapilacaklar"][0]["metin"] == "b"


# ---------------------------------------------------------------------------
# Görünürlük, paylaşım, yalıtım
# ---------------------------------------------------------------------------
async def test_ekip_ici_belge_musteriye_sizmaz_paylasilan_salt_okunur(istemci, yonetici_basligi, db_oturumu):
    yb = yonetici_basligi
    a, b = _e("a"), _e("b")
    gizli = await _belge(istemci, yb, baslik="İç not: A fiyat stratejisi", alan="musteri", musteri_email=a)
    assert gizli["gorunurluk"] == "ekip"
    # Ajans içi wiki paylaşılamaz.
    y = await istemci.post(Y, json={"baslik": "wiki", "alan": "ajans", "gorunurluk": "paylasilan"}, headers=yb)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "paylasim_icin_musteri"
    # A göremez (liste, ayrıntı, PDF, MD): 404 — varlığı da sızmıyor.
    assert (await istemci.get(M, headers=_b(a))).json()["items"] == []
    for yol in ("", "/pdf", "/md"):
        assert (await istemci.get(f"{M}/{gizli['id']}{yol}", headers=_b(a))).status_code == 404
    assert (await istemci.get(f"{M}/ozet", headers=_b(a))).json()["paylasilan"] == 0
    # Paylaş → A görür (modül kapalıyken de), bildirim gider; B göremez.
    y = await istemci.put(f"{Y}/{gizli['id']}", json={"gorunurluk": "paylasilan"}, headers=yb)
    assert y.status_code == 200 and y.json()["paylasildi_at"]
    assert len(await _bildirimler(db_oturumu, a, "belge_paylasildi")) == 1
    liste = (await istemci.get(M, headers=_b(a))).json()
    assert [x["id"] for x in liste["items"]] == [gizli["id"]] and liste["kendi_belge"] is False
    d = (await istemci.get(f"{M}/{gizli['id']}", headers=_b(a))).json()
    assert d["baslik"].startswith("İç not") and d["son_duzenleyen"] is None
    assert (await istemci.get(f"{M}/ozet", headers=_b(a))).json()["paylasilan_belge"] == 1
    assert (await istemci.get(f"{M}/{gizli['id']}", headers=_b(b))).status_code == 404
    assert (await istemci.get(M, headers=_b(b))).json()["items"] == []
    # Salt okunur: düzenleme/silme yok (modül kapalı → önce modül bekçisi).
    y = await istemci.put(f"{M}/{gizli['id']}", json={"baslik": "x"}, headers=_b(a))
    assert y.status_code == 403
    await _modul_ac(istemci, yb, a)
    y = await istemci.put(f"{M}/{gizli['id']}", json={"baslik": "x"}, headers=_b(a))
    assert y.status_code == 403 and y.json()["detail"]["kod"] == "salt_okunur"
    y = await istemci.delete(f"{M}/{gizli['id']}", headers=_b(a))
    assert y.status_code == 403
    y = await istemci.post(f"{M}/{gizli['id']}/yapilacak", json={"satir": 0, "tamam": True}, headers=_b(a))
    assert y.status_code == 403
    # Paylaşım geri çekilince yine görünmez.
    await istemci.put(f"{Y}/{gizli['id']}", json={"gorunurluk": "ekip"}, headers=yb)
    assert (await istemci.get(f"{M}/{gizli['id']}", headers=_b(a))).status_code == 404


async def test_proje_belgesi_projenin_musterisine_bagli(istemci, yonetici_basligi, db_oturumu):
    from models.projects import Projects

    a = _e("proje")
    p = Projects(title="Web sitesi", description="d", category="Web", client_email=a, client_name="A", published=False,
                 status="in_progress")
    db_oturumu.add(p)
    await db_oturumu.commit()
    await db_oturumu.refresh(p)
    d = await _belge(istemci, yonetici_basligi, alan="proje", proje_id=p.id, gorunurluk="paylasilan")
    assert d["musteri_email"] == a and d["proje_adi"] == "Web sitesi"
    assert (await istemci.get(f"{M}/{d['id']}", headers=_b(a))).status_code == 200
    y = await istemci.post(Y, json={"baslik": "x", "alan": "proje", "proje_id": 999999}, headers=yonetici_basligi)
    assert y.status_code == 404 and y.json()["detail"]["kod"] == "proje_yok"
    y = await istemci.post(Y, json={"baslik": "x", "alan": "musteri", "musteri_email": _e(), "proje_id": p.id},
                           headers=yonetici_basligi)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "proje_musteri_uyusmuyor"


async def test_modul_kapaliyken_olusturma_403_paylasilan_okuma_200(istemci, yonetici_basligi):
    a = _e("kapali")
    d = await _belge(istemci, yonetici_basligi, alan="musteri", musteri_email=a, gorunurluk="paylasilan")
    y = await istemci.post(M, json={"baslik": "Benim notum"}, headers=_b(a))
    assert y.status_code == 403 and y.json()["detail"] == {"kod": "modul_kapali", "modul": "belgeler"}
    for yol in ("/onizle", "/ai"):
        assert (await istemci.post(f"{M}{yol}", json={"icerik": "x", "islem": "yaz"}, headers=_b(a))).status_code == 403
    assert (await istemci.get(f"{M}/{d['id']}", headers=_b(a))).status_code == 200
    assert (await istemci.get(f"{M}/{d['id']}/pdf", headers=_b(a))).status_code == 200
    assert (await istemci.post(f"{M}/{d['id']}/okundu", headers=_b(a))).status_code == 200
    m = (await istemci.get(f"{M}/meta", headers=_b(a))).json()
    assert m["modul_acik"] is False and m["kendi_belge"] is False and len(m["strateji_sablonlari"]) == 8


async def test_musteri_kendi_belgesi_ajansla_paylasma_ve_yalitim(istemci, yonetici_basligi, db_oturumu):
    yb = yonetici_basligi
    a, b = _e("kendi"), _e("baska")
    await _modul_ac(istemci, yb, a)
    await _modul_ac(istemci, yb, b)
    d = await _belge(istemci, _b(a), yol=M, baslik="Pazarlama planım", icerik="- [ ] Instagram @" + a)
    assert d["musteri_belgesi"] is True and d["sahip_hesap"] == a and d["gorunurluk"] == "ekip" and d["alan"] == "musteri"
    # Ajans listesinde ve ayrıntıda YOK (paylaşılmamış müşteri belgesi).
    assert d["id"] not in [x["id"] for x in (await istemci.get(Y, headers=yb)).json()["items"]]
    assert (await istemci.get(f"{Y}/{d['id']}", headers=yb)).status_code == 404
    # B göremez, düzenleyemez.
    assert (await istemci.get(f"{M}/{d['id']}", headers=_b(b))).status_code == 404
    assert (await istemci.put(f"{M}/{d['id']}", json={"baslik": "ele geçir"}, headers=_b(b))).status_code == 404
    assert (await istemci.delete(f"{M}/{d['id']}", headers=_b(b))).status_code == 404
    # A düzenler, sürüm geçmişi.
    y = await istemci.put(f"{M}/{d['id']}", json={"icerik": "- [x] Instagram"}, headers=_b(a))
    assert y.status_code == 200 and y.json()["surum"] == 2
    assert len((await istemci.get(f"{M}/{d['id']}/surumler", headers=_b(a))).json()["items"]) == 2
    # Ajansla paylaş → yöneticilere bildirim + gelen kutusunda "yeni"; ajans salt okunur görür.
    y = await istemci.put(f"{M}/{d['id']}", json={"gorunurluk": "paylasilan"}, headers=_b(a))
    assert y.status_code == 200
    assert len(await _bildirimler(db_oturumu, "yonetici@test.dev", "belge_paylasildi")) >= 1
    assert (await istemci.get(f"{Y}/{d['id']}", headers=yb)).status_code == 200
    y = await istemci.put(f"{Y}/{d['id']}", json={"baslik": "x"}, headers=yb)
    assert y.status_code == 403 and y.json()["detail"]["kod"] == "musteri_belgesi"
    assert (await istemci.delete(f"{Y}/{d['id']}", headers=yb)).status_code == 403
    k = (await istemci.get("/api/v1/gelen-kutusu", params={"kaynak": "belge_paylasim", "durum": "hepsi"}, headers=yb)).json()
    oge = next(o for o in k["ogeler"] if o["kimlik"] == d["id"])
    assert oge["durum"] == "yeni" and oge["hesap_email"] == a and "alt=belgeler" in oge["ac_baglantisi"]
    # Modül kapanınca kendi belgesine erişim kapanır (veri silinmez).
    await _modul_ac(istemci, yb, a, acik=False)
    y = await istemci.get(f"{M}/{d['id']}", headers=_b(a))
    assert y.status_code == 403 and y.json()["detail"]["kod"] == "modul_kapali"
    assert (await istemci.get(M, headers=_b(a))).json()["items"] == []


async def test_belge_siniri_modul_ayari(istemci, yonetici_basligi):
    a = _e("sinir")
    await _modul_ac(istemci, yonetici_basligi, a, belge_siniri=1)
    await _belge(istemci, _b(a), yol=M)
    y = await istemci.post(M, json={"baslik": "ikinci"}, headers=_b(a))
    assert y.status_code == 409 and y.json()["detail"] == {"kod": "belge_siniri", "sinir": 1}


async def test_okundu_onayi_surum_basina_ve_gelen_kutusu(istemci, yonetici_basligi, db_oturumu):
    yb = yonetici_basligi
    a = _e("okur")
    d = await _belge(istemci, yb, alan="musteri", musteri_email=a, gorunurluk="paylasilan")
    once = len(await _bildirimler(db_oturumu, "yonetici@test.dev", "belge_onaylandi"))
    y = await istemci.post(f"{M}/{d['id']}/okundu", headers=_b(a))
    assert y.status_code == 200 and y.json()["okundu_surum"] == 1 and y.json()["okuyan"] == a
    await istemci.post(f"{M}/{d['id']}/okundu", headers=_b(a))  # ikinci kez: yeni bildirim yok
    assert len(await _bildirimler(db_oturumu, "yonetici@test.dev", "belge_onaylandi")) == once + 1
    k = (await istemci.get("/api/v1/gelen-kutusu", params={"kaynak": "belge_paylasim", "durum": "hepsi"}, headers=yb)).json()
    oge = next(o for o in k["ogeler"] if o["kimlik"] == d["id"])
    assert oge["durum"] == "okundu" and oge["ek"]["tur"] == "onayladi"
    # Yeni sürümde yeniden onaylanabilir.
    await istemci.put(f"{Y}/{d['id']}", json={"icerik": "güncel"}, headers=yb)
    y = await istemci.post(f"{M}/{d['id']}/okundu", headers=_b(a))
    assert y.json()["okundu_surum"] == 2
    # Müşterinin kendi belgesine "okundu" verilmez.
    await _modul_ac(istemci, yb, a)
    k2 = await _belge(istemci, _b(a), yol=M)
    assert (await istemci.post(f"{M}/{k2['id']}/okundu", headers=_b(a))).status_code == 400


# ---------------------------------------------------------------------------
# Strateji şablonları
# ---------------------------------------------------------------------------
async def test_strateji_dogrulama_pdf_ve_md(istemci, yonetici_basligi):
    yb = yonetici_basligi
    y = await istemci.post(Y, json={"baslik": "SWOT", "tur": "swot", "icerik": {"kutular": {"yok_boyle": "x"}}}, headers=yb)
    assert y.status_code == 400 and y.json()["detail"] == {"kod": "bilinmeyen_kutu", "alan": "kutular", "kutu": "yok_boyle"}
    y = await istemci.post(Y, json={"baslik": "SWOT", "tur": "swot", "icerik": {"kutular": {"guclu": 5}}}, headers=yb)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "gecersiz"
    y = await istemci.post(Y, json={"baslik": "SWOT", "tur": "swot", "icerik": {"kutular": {"guclu": "x" * 3001}}}, headers=yb)
    assert y.status_code == 400 and y.json()["detail"]["kod"] == "metin_uzun"
    y = await istemci.post(Y, json={"baslik": "SWOT", "tur": "swot", "icerik": {"baska": 1}}, headers=yb)
    assert y.status_code == 400
    y = await istemci.post(Y, json={"baslik": "SWOT", "tur": "yok"}, headers=yb)
    assert y.status_code == 400 and y.json()["detail"]["alan"] == "tur"
    s = await _belge(istemci, yb, baslik="Kafe SWOT", tur="swot", icerik={
        "isletme": "Kadıköy'de kahve dükkânı", "kutular": {"guclu": "- Taze kavrum\n- Merkezî konum", "tehditler": "- Zincirler"}})
    assert s["strateji"] is True and s["strateji_icerik"]["kutular"]["guclu"].startswith("- Taze")
    assert "icerik" not in s and "html" not in s
    bmc = await _belge(istemci, yb, baslik="Kafe iş modeli", tur="is_modeli", icerik={"kutular": {"deger": "- Üçüncü dalga kahve"}})
    # Strateji süzgeci.
    liste = (await istemci.get(Y, params={"tur": "strateji"}, headers=yb)).json()["items"]
    assert {s["id"], bmc["id"]} <= {x["id"] for x in liste} and all(x["strateji"] for x in liste)
    # PDF: ızgara + kutu adları (tr), Almanca etiketler.
    from services.belge_pdf import pdf_metni

    y = await istemci.get(f"{Y}/{s['id']}/pdf", headers=yb)
    assert y.status_code == 200 and y.headers["content-type"] == "application/pdf" and y.content[:4] == b"%PDF"
    metin = pdf_metni(y.content)
    assert "Güçlü yönler" in metin and "Taze kavrum" in metin and "SWOT ANALİZİ" in metin
    y = await istemci.get(f"{Y}/{bmc['id']}/pdf", params={"dil": "de"}, headers=yb)
    assert "Wertangebote" in pdf_metni(y.content)
    y = await istemci.get(f"{Y}/{s['id']}/md", headers=yb)
    assert y.status_code == 200 and y.headers["content-type"].startswith("text/markdown")
    assert "## Güçlü yönler" in y.text and "- Taze kavrum" in y.text and "## Fırsatlar" in y.text
    # Sürüm geri yükleme stratejide de çalışıyor.
    await istemci.put(f"{Y}/{s['id']}", json={"icerik": {"kutular": {"guclu": "değişti"}}}, headers=yb)
    ilk = (await istemci.get(f"{Y}/{s['id']}/surumler", headers=yb)).json()["items"][-1]
    d = (await istemci.get(f"{Y}/{s['id']}/surumler/{ilk['id']}", headers=yb)).json()
    assert d["strateji_icerik"]["kutular"]["tehditler"] == "- Zincirler"
    y = await istemci.post(f"{Y}/{s['id']}/surumler/{ilk['id']}/geri-yukle", headers=yb)
    assert y.json()["strateji_icerik"]["kutular"]["guclu"].startswith("- Taze")


async def test_belge_pdf_markdown_ve_guvenli(istemci, yonetici_basligi):
    from services.belge_pdf import pdf_metni

    d = await _belge(istemci, yonetici_basligi, baslik="Kurulum kılavuzu",
                     icerik="## Adımlar\n\n1. Sunucu\n- [ ] DNS → #5\n\n| A | B |\n|---|---|\n| ğ | ş |\n\n<script>x</script>")
    y = await istemci.get(f"{Y}/{d['id']}/pdf", headers=yonetici_basligi)
    assert y.status_code == 200 and "attachment" in y.headers["content-disposition"]
    metin = pdf_metni(y.content)
    assert "Kurulum kılavuzu" in metin and "Adımlar" in metin and "ğ" in metin and "<script>x</script>" in metin
    md = (await istemci.get(f"{Y}/{d['id']}/md", headers=yonetici_basligi)).text
    assert md.startswith("# Kurulum kılavuzu") and "- [ ] DNS → #5" in md


# ---------------------------------------------------------------------------
# Yapılacaklar
# ---------------------------------------------------------------------------
async def test_yapilacaklarim_isaretleme_ve_gorev_bagi(istemci, yonetici_basligi, db_oturumu):
    from models.projects import Projects

    yb = yonetici_basligi
    p = Projects(title="Kafe sitesi", description="d", category="Web", client_email=_e(), client_name="K", published=False,
                 status="in_progress")
    db_oturumu.add(p)
    await db_oturumu.commit()
    await db_oturumu.refresh(p)
    d = await _belge(istemci, yb, alan="proje", proje_id=p.id, icerik=(
        "Toplantı notu\n\n- [ ] Logo dosyasını iste @yonetici@test.dev\n- [ ] Menü fiyatları\n- [x] Alan adı\n\n```\n- [ ] kod\n```"))
    assert d["acik_yapilacak"] == 2 and len(d["yapilacaklar"]) == 3
    bana = (await istemci.get(f"{Y}/yapilacaklar", headers=yb)).json()["items"]
    benim = [o for o in bana if o["belge_id"] == d["id"]]
    assert [o["metin"] for o in benim] == ["Logo dosyasını iste @yonetici@test.dev"] and benim[0]["bana"] is True
    hepsi = [o for o in (await istemci.get(f"{Y}/yapilacaklar", params={"kapsam": "hepsi"}, headers=yb)).json()["items"]
             if o["belge_id"] == d["id"]]
    assert [o["satir"] for o in hepsi] == [2, 3]
    # İşaretle (eski metinle 409).
    y = await istemci.post(f"{Y}/{d['id']}/yapilacak", json={"satir": 3, "metin": "Menü fiyatları", "tamam": True}, headers=yb)
    assert y.status_code == 200 and "- [x] Menü fiyatları" in y.json()["icerik"] and y.json()["acik_yapilacak"] == 1
    y = await istemci.post(f"{Y}/{d['id']}/yapilacak", json={"satir": 3, "metin": "Başka madde", "tamam": False}, headers=yb)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "madde_degisti"
    y = await istemci.post(f"{Y}/{d['id']}/yapilacak", json={"satir": 0, "tamam": True}, headers=yb)
    assert y.status_code == 409
    # Art arda işaretler tek sürümde birleşir.
    await istemci.post(f"{Y}/{d['id']}/yapilacak", json={"satir": 3, "metin": "Menü fiyatları", "tamam": False}, headers=yb)
    s = (await istemci.get(f"{Y}/{d['id']}/surumler", headers=yb)).json()["items"]
    assert [x["aciklama"] for x in s] == ["yapilacak", "olusturma"]
    # Maddeden görev: Faz 2B ucu, sonra bağ.
    g = await istemci.post(f"/api/v1/gorevler/proje/{p.id}", json={"baslik": "Logo dosyasını iste"}, headers=yb)
    assert g.status_code == 200, g.text
    gid = g.json()["id"]
    metin = "Logo dosyasını iste @yonetici@test.dev"
    y = await istemci.post(f"{Y}/{d['id']}/yapilacak/gorev", json={"satir": 2, "metin": metin, "gorev_id": gid}, headers=yb)
    assert y.status_code == 200 and f"{metin} → #{gid}" in y.json()["icerik"]
    assert next(o for o in y.json()["yapilacaklar"] if o["satir"] == 2)["gorev_id"] == gid
    y = await istemci.post(f"{Y}/{d['id']}/yapilacak/gorev",
                           json={"satir": 2, "metin": f"{metin} → #{gid}", "gorev_id": gid}, headers=yb)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "gorev_bagli"
    y = await istemci.post(f"{Y}/{d['id']}/yapilacak/gorev", json={"satir": 3, "gorev_id": 999999}, headers=yb)
    assert y.status_code == 404


async def test_musteri_yapilacaklari_paylasilan_salt_okunur(istemci, yonetici_basligi):
    a = _e("yap")
    await _modul_ac(istemci, yonetici_basligi, a)
    await _belge(istemci, yonetici_basligi, alan="musteri", musteri_email=a, gorunurluk="paylasilan",
                 icerik=f"- [ ] Fotoğrafları gönder @{a}")
    kendi = await _belge(istemci, _b(a), yol=M, icerik=f"- [ ] Kendi işim @{a}")
    ogeler = (await istemci.get(f"{M}/yapilacaklar", headers=_b(a))).json()["items"]
    assert {(o["metin"].split(" @")[0], o["salt_okunur"]) for o in ogeler} == {("Fotoğrafları gönder", True), ("Kendi işim", False)}
    y = await istemci.post(f"{M}/{kendi['id']}/yapilacak", json={"satir": 0, "metin": f"Kendi işim @{a}", "tamam": True},
                           headers=_b(a))
    assert y.status_code == 200 and y.json()["acik_yapilacak"] == 0


# ---------------------------------------------------------------------------
# Yapay zekâ
# ---------------------------------------------------------------------------
async def test_ai_anahtar_yokken_503_ve_hak_dusmez(istemci, yonetici_basligi):
    y = await istemci.post(f"{Y}/ai", json={"islem": "ozetle", "metin": "Uzun bir metin"}, headers=yonetici_basligi)
    assert y.status_code == 503 and y.json()["detail"]["kod"] == "ai_kapali"
    m = (await istemci.get(f"{Y}/meta", headers=yonetici_basligi)).json()
    assert m["ai_hazir"] is False and m["kullanim"]["bugun"] == 0


async def test_ai_test_ortami_sahte_yanit_ve_taslak(istemci, yonetici_basligi, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    yb = yonetici_basligi
    assert (await istemci.get(f"{Y}/meta", headers=yb)).json()["ai_hazir"] is True
    for islem, govde in (("ozetle", {"metin": "Toplantıda üç karar alındı."}), ("duzelt", {"metin": "yanlis yazi"}),
                         ("yaz", {"talimat": "Kısa bir hoş geldin metni"})):
        y = await istemci.post(f"{Y}/ai", json={"islem": islem, **govde}, headers=yb)
        assert y.status_code == 200 and y.json()["sahte"] is True and y.json()["metin"], (islem, y.text)
    y = await istemci.post(f"{Y}/ai", json={"islem": "taslak", "tur": "is_modeli", "isletme": "Kadıköy'de üçüncü dalga kahveci"},
                           headers=yb)
    assert y.status_code == 200
    from services.belgeler import STRATEJI_SABLONLARI

    assert set(y.json()["kutular"]) == set(STRATEJI_SABLONLARI["is_modeli"].anahtarlar)
    # Doğrulama: zorunlu alanlar, bilinmeyen işlem.
    assert (await istemci.post(f"{Y}/ai", json={"islem": "yaz"}, headers=yb)).status_code == 400
    assert (await istemci.post(f"{Y}/ai", json={"islem": "taslak", "tur": "belge", "isletme": "x"}, headers=yb)).status_code == 400
    assert (await istemci.post(f"{Y}/ai", json={"islem": "sil"}, headers=yb)).status_code == 400
    assert (await istemci.get(f"{Y}/meta", headers=yb)).json()["kullanim"]["bugun"] == 4


async def test_ai_gercek_yanit_json_uyarisi_ve_iade(istemci, yonetici_basligi, monkeypatch):
    from services import belgeler_ai as bai
    from services import yapay_zeka

    monkeypatch.setattr(bai, "ai_hazir", lambda: True)
    yanitlar = [json.dumps({"kutular": {"guclu": ["Taze kavrum", "Pazarın %40'ı bizde"], "zayif": "- Küçük salon"}}), None]

    async def _sahte(mesajlar, model, max_tokens, temperature):
        y = yanitlar.pop(0)
        if y is None:
            raise yapay_zeka.YapayZekaHatasi("ai_hatasi", 502)
        assert "<veri alan=\"isletme\">" in mesajlar[1]["content"]
        return y, {"prompt_tokens": 10, "completion_tokens": 5}

    monkeypatch.setattr(yapay_zeka, "_saglayici_cagir", _sahte)
    yb = yonetici_basligi
    once = (await istemci.get(f"{Y}/meta", headers=yb)).json()["kullanim"]["bugun"]
    y = await istemci.post(f"{Y}/ai", json={"islem": "taslak", "tur": "swot", "isletme": "Küçük kahve dükkânı"}, headers=yb)
    g = y.json()
    assert g["kutular"]["guclu"] == "- Taze kavrum\n- Pazarın %40'ı bizde" and g["kutular"]["zayif"] == "- Küçük salon"
    # Girdide olmayan sayı → uyarı (uydurma rakam insan gözüne).
    assert g["uyarilar"]["guclu"][0]["tur"] == "kaynaksiz_sayi"
    y = await istemci.post(f"{Y}/ai", json={"islem": "taslak", "tur": "swot", "isletme": "x"}, headers=yb)
    assert y.status_code == 502
    assert (await istemci.get(f"{Y}/meta", headers=yb)).json()["kullanim"]["bugun"] == once + 1  # hata iade edildi


async def test_ai_musteri_aylik_sinir(istemci, yonetici_basligi, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    a = _e("ai")
    await _modul_ac(istemci, yonetici_basligi, a, aylik_uretim=1, kredi_ile_asim=False)
    y = await istemci.post(f"{M}/ai", json={"islem": "ozetle", "metin": "metin"}, headers=_b(a))
    assert y.status_code == 200 and y.json()["kullanim"]["ay"] == 1
    y = await istemci.post(f"{M}/ai", json={"islem": "ozetle", "metin": "metin"}, headers=_b(a))
    assert y.status_code == 409 and y.json()["detail"] == {"kod": "aylik_sinir", "sinir": 1}


# ---------------------------------------------------------------------------
# Çöp kutusu
# ---------------------------------------------------------------------------
async def test_cop_kutusu_surumlerle_geri_gelir_ve_ajans_belgesi_musteriye_dusmez(istemci, yonetici_basligi):
    yb = yonetici_basligi
    a = _e("cop")
    d = await _belge(istemci, yb, alan="musteri", musteri_email=a, icerik="v1")
    await istemci.put(f"{Y}/{d['id']}", json={"icerik": "v2"}, headers=yb)
    assert (await istemci.delete(f"{Y}/{d['id']}", headers=yb)).status_code == 200
    cop = (await istemci.get("/api/v1/cop-kutusu", params={"tablo": "belgeler"}, headers=yb)).json()["items"]
    satir = next(c for c in cop if c["kayit_id"] == str(d["id"]))
    assert satir["bagli_sayisi"] == 2 and satir["sahip_email"] is None
    # Ajansın müşteri hakkındaki ekip içi belgesi müşterinin "Silinenler"inde yok.
    assert all(c["kayit_id"] != str(d["id"]) for c in (await istemci.get("/api/v1/cop-kutum", headers=_b(a))).json()["items"])
    y = await istemci.post(f"/api/v1/cop-kutusu/{satir['id']}/geri-al", headers=yb)
    assert y.status_code == 200, y.text
    g = (await istemci.get(f"{Y}/{d['id']}", headers=yb)).json()
    assert g["icerik"] == "v2" and len((await istemci.get(f"{Y}/{d['id']}/surumler", headers=yb)).json()["items"]) == 2
    # Müşterinin kendi belgesi kendi çöp kutusuna düşer, kendisi geri alır.
    await _modul_ac(istemci, yb, a)
    k = await _belge(istemci, _b(a), yol=M, baslik="Silinecek not")
    assert (await istemci.delete(f"{M}/{k['id']}", headers=_b(a))).status_code == 200
    mc = (await istemci.get("/api/v1/cop-kutum", headers=_b(a))).json()["items"]
    s2 = next(c for c in mc if c["kayit_id"] == str(k["id"]))
    assert (await istemci.post(f"/api/v1/cop-kutum/{s2['id']}/geri-al", headers=_b(a))).status_code == 200
    assert (await istemci.get(f"{M}/{k['id']}", headers=_b(a))).status_code == 200


async def test_denetim_kaydina_belge_yazilir_surumler_yazilmaz(istemci, yonetici_basligi, db_oturumu):
    from sqlalchemy import func

    from models.audit_log import AuditLog

    son = (await db_oturumu.execute(select(func.coalesce(func.max(AuditLog.id), 0)))).scalar()
    d = await _belge(istemci, yonetici_basligi, icerik="denetim")
    await istemci.put(f"{Y}/{d['id']}", json={"icerik": "denetim 2"}, headers=yonetici_basligi)
    db_oturumu.expire_all()
    satirlar = (await db_oturumu.execute(select(AuditLog).where(AuditLog.id > son))).scalars().all()
    tablolar = {s.tablo for s in satirlar}
    assert "belgeler" in tablolar and "belge_surumleri" not in tablolar and "belge_ai_kullanimi" not in tablolar
    guncelleme = next(s for s in satirlar if s.tablo == "belgeler" and s.islem == "guncelle")
    assert "arama_metni" not in (guncelleme.degisiklik_json or "") and "icerik" in (guncelleme.degisiklik_json or "")


def test_eski_varsayilan_uyeler_belgeler_iznini_alir_ozellestirilmis_almaz():
    from services import hesap_ekibi as he

    eski_uye = ["projeler", "gorevler", "destek", "dosyalar", "siteler", "raporlar", "mesajlar", "asistanlar", "qr",
                "kartvizit", "menu", "randevu", "asistan", "icerik", "etkinlik_giris"]
    assert "belgeler" in he.izinleri_coz(json.dumps(eski_uye), "uye")
    # Canlıdaki yönetici varsayılanı: bugünkü IZINLER'den 5B ile birlikte yayına çıkan 6P/6K izinleri (ve sonraki
    # 6I `ik`, 6H `hukuk`) de düşülür.
    yeni = {"belgeler", "stok", "kasa", "egitim", "egitim_egitmen", "ik", "hukuk", "muhasebe", "muhasebe_okur"}  # Faz 6M: muhasebe, muhasebe_okur da yoktu
    assert "belgeler" in he.izinleri_coz(json.dumps(sorted(set(he.IZINLER) - yeni)), "yonetici")
    assert "belgeler" not in he.izinleri_coz(json.dumps(["projeler", "dosyalar"]), "uye")
    assert "belgeler" in he.ROL_VARSAYILAN["uye"] and "belgeler" not in he.ROL_VARSAYILAN["fatura"]
