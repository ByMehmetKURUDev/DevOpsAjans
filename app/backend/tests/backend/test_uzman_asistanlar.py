"""Faz 3U (B) — Uzman Asistanlar modülü.

Kapsam: tohumlama (idempotent; düzenleme ezilmez, silinen geri gelmez), modül
kapısı (varsayılan kapalı → 403), ekip izni `asistanlar` (izinsiz üye 403),
sohbet kişiye özel (başka hesabın / başka kişinin sohbeti 404), sistem istemi
müşteri yanıtlarında yok, istemci sistem istemi/model/max_tokens gönderemez,
bağlam kırpma, günlük sınır 429, kredi düşümü + yetersiz bakiye 402 + model
hatasında iade, kişi başı hız sınırı, yönetici CRUD + ayarlar + kullanım +
"Dene" (hiçbir şey kaydetmez), yumuşak silme.

Test veritabanı oturum boyunca ortak: her test kendi benzersiz e-postasıyla
çalışıyor; değiştirilen site ayarları test sonunda geri alınıyor.
"""

import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select

from conftest import jeton_uret

M = "/api/v1/asistanlarim"
Y = "/api/v1/uzman-asistanlar/yonetim"
MODUL = "/api/v1/moduller"
GERCEK_TOHUM = Path(__file__).resolve().parents[2] / "data" / "uzman_asistanlar_tohum.json"
ASISTAN = "seo-specialist"
KOTU = "KOTU-ISTEM-ezilmeye-calisiyor"
#: Tohum istemlerinden ve ortak ekten parçalar: müşteri yanıtında hiçbiri olmamalı.
ISTEM_PARCALARI = ("Your environment: you are a chat assistant", "Platform rules", "You are an SEO Specialist")


def _e(on: str = "asistan") -> str:
    return f"{on}-{uuid.uuid4().hex[:8]}@asistan.dev"


def _b(eposta: str, hesap: str | None = None) -> dict:
    h = {"Authorization": f"Bearer {jeton_uret(eposta)}"}
    if hesap:
        h["X-MK-Hesap"] = hesap
    return h


def _kod(y) -> str:
    d = y.json().get("detail")
    return d.get("kod", "") if isinstance(d, dict) else ""


@pytest.fixture(autouse=True)
def _temiz(monkeypatch):
    from routers import uzman_asistanlar as r
    from services import hesap_ekibi

    monkeypatch.delenv("ENVIRONMENT", raising=False)
    r.hiz_sinirlarini_temizle()
    hesap_ekibi.onbellegi_temizle()
    yield
    r.hiz_sinirlarini_temizle()


@pytest.fixture
async def tohumlu(db_oturumu):
    from services import uzman_asistanlar as s

    await s.tohumla(db_oturumu)
    return db_oturumu


@pytest.fixture
def ai(monkeypatch):
    """Sahte model: çağrıları yakalar; `ai.hata = True` iken hata verir."""
    from services import yapay_zeka

    class Sahte:
        cagrilar: list = []
        hata = False

    sahte = Sahte()
    sahte.cagrilar = []

    async def cagir(mesajlar, model, max_tokens, temperature):
        sahte.cagrilar.append({"mesajlar": mesajlar, "model": model, "max_tokens": max_tokens})
        if sahte.hata:
            raise RuntimeError("sağlayıcı düştü")
        return f"**Yanıt {len(sahte.cagrilar)}**\n\n- madde", {"prompt_tokens": 100, "completion_tokens": 20}

    monkeypatch.setattr(yapay_zeka, "_saglayici_cagir", cagir)
    return sahte


async def _modul_ac(istemci, yonetici_basligi, eposta, **ayarlar):
    govde = {"acik": True}
    if ayarlar:
        govde["ayarlar"] = ayarlar
    y = await istemci.put(f"{MODUL}/musteri/{eposta}/uzman_asistanlar", json=govde, headers=yonetici_basligi)
    assert y.status_code == 200, y.text


async def _musteri(istemci, yonetici_basligi, **ayarlar) -> str:
    e = _e()
    await _modul_ac(istemci, yonetici_basligi, e, **ayarlar)
    return e


async def _sohbet(istemci, eposta, hesap=None, asistan=ASISTAN) -> int:
    y = await istemci.post(f"{M}/sohbetler", json={"asistan_anahtar": asistan}, headers=_b(eposta, hesap))
    assert y.status_code == 200, y.text
    return y.json()["id"]


async def _gonder(istemci, eposta, sid, icerik="Merhaba", hesap=None, **ek):
    return await istemci.post(f"{M}/sohbetler/{sid}/mesaj", json={"icerik": icerik, **ek}, headers=_b(eposta, hesap))


async def _ayarlar(istemci, yonetici_basligi, **govde):
    y = await istemci.put(f"{Y}/ayarlar", json=govde, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    return y.json()


# ---------------------------------------------------------------------------
# Tohumlama
# ---------------------------------------------------------------------------
def _tohum_dosyasi(tmp_path: Path, asistanlar: list) -> Path:
    veri = json.loads(GERCEK_TOHUM.read_text(encoding="utf-8"))
    veri["asistanlar"] = asistanlar
    yol = tmp_path / "tohum.json"
    yol.write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")
    return yol


def _tohum_kaydi(anahtar: str, **ek) -> dict:
    kayit = json.loads(GERCEK_TOHUM.read_text(encoding="utf-8"))["asistanlar"][0]
    kayit = {**kayit, "anahtar": anahtar, **ek}
    return kayit


def test_tohum_dosyasi_17_asistan_7_dil_ve_mit_bildirimi():
    veri = json.loads(GERCEK_TOHUM.read_text(encoding="utf-8"))
    assert len(veri["asistanlar"]) == 17
    assert veri["kaynak"]["lisans"] == "MIT" and "Permission is hereby granted" in veri["kaynak"]["lisans_metni"]
    for a in veri["asistanlar"]:
        assert a["kategori"] in veri["kategoriler"]
        for dil in ("tr", "en", "de", "ru", "zh", "hi", "ar"):
            assert a["ad"][dil] and a["aciklama"][dil] and len(a["ornek_sorular"][dil]) == 3


async def test_tohumlama_idempotent_duzenleme_ezilmez_silinen_gelmez(db_oturumu, tmp_path):
    from models.uzman_asistanlar import UzmanAsistanlar
    from services import uzman_asistanlar as s

    a1, a2 = f"tohum-{uuid.uuid4().hex[:6]}", f"tohum-{uuid.uuid4().hex[:6]}"
    yol = _tohum_dosyasi(tmp_path, [_tohum_kaydi(a1), _tohum_kaydi(a2), _tohum_kaydi("Gecersiz Anahtar!")])
    ilk = await s.tohumla(db_oturumu, yol)
    assert ilk["eklenen"] == [a1, a2] and ilk["atlanan"] == ["gecersiz anahtar!"]
    assert (await s.tohumla(db_oturumu, yol))["eklenen"] == []

    satir = (await db_oturumu.execute(select(UzmanAsistanlar).where(UzmanAsistanlar.anahtar == a1))).scalars().one()
    assert satir.ad == "SEO Uzmanı" and json.loads(satir.ceviriler)["en"]["ad"] == "SEO Specialist"
    assert satir.atif == "agency-agents (marketing/marketing-seo-specialist.md), MIT"
    satir.ad = "Panelde değişti"
    await db_oturumu.commit()
    await db_oturumu.execute(delete(UzmanAsistanlar).where(UzmanAsistanlar.anahtar == a2))
    await db_oturumu.commit()
    assert (await s.tohumla(db_oturumu, yol))["eklenen"] == []
    db_oturumu.expire_all()
    satir = (await db_oturumu.execute(select(UzmanAsistanlar).where(UzmanAsistanlar.anahtar == a1))).scalars().one()
    assert satir.ad == "Panelde değişti"
    assert (await db_oturumu.execute(select(func.count()).where(UzmanAsistanlar.anahtar == a2))).scalar() == 0


async def test_gercek_tohum_17_asistani_ekler(tohumlu):
    from models.uzman_asistanlar import UzmanAsistanlar

    anahtarlar = set((await tohumlu.execute(select(UzmanAsistanlar.anahtar))).scalars().all())
    veri = json.loads(GERCEK_TOHUM.read_text(encoding="utf-8"))
    assert {a["anahtar"] for a in veri["asistanlar"]} <= anahtarlar


# ---------------------------------------------------------------------------
# Kapılar: oturum, modül, izin
# ---------------------------------------------------------------------------
async def test_oturumsuz_401_modul_kapali_403(istemci, tohumlu):
    assert (await istemci.get(M)).status_code == 401
    e = _e("kapali")
    for metot, yol, govde in (
        ("GET", M, None),
        ("GET", f"{M}/sohbetler", None),
        ("POST", f"{M}/sohbetler", {"asistan_anahtar": ASISTAN}),
        ("POST", f"{M}/sohbetler/1/mesaj", {"icerik": "x"}),
        ("DELETE", f"{M}/sohbetler/1", None),
    ):
        y = await istemci.request(metot, yol, json=govde, headers=_b(e))
        assert y.status_code == 403 and y.json()["detail"] == {"kod": "modul_kapali", "modul": "uzman_asistanlar"}, (yol, y.text)


async def test_modul_varsayilan_kapali_paketlerde_yok():
    from core.moduller import MODUL_SOZLUGU

    m = MODUL_SOZLUGU["uzman_asistanlar"]
    assert m.varsayilan_acik is False and m.paketler == () and m.musteri_sekmesi == "asistanlar"
    assert m.yonetici_sekmesi == "uzmanAsistanlar" and not m.cekirdek


async def test_izin_uye_gecer_izinsiz_uye_ve_fatura_403(istemci, yonetici_basligi, tohumlu, ai):
    from models.hesap_uyeleri import HesapUyeleri
    from services import hesap_ekibi as he

    sahip = await _musteri(istemci, yonetici_basligi)
    uye, kisitli, fatura = _e("uye"), _e("kisitli"), _e("fatura")
    for kisi, rol, izinler in ((uye, "uye", None), (kisitli, "uye", []), (fatura, "fatura", None)):
        tohumlu.add(HesapUyeleri(hesap_email=sahip, uye_email=kisi, rol=rol, durum="aktif", olusturma=he.simdi(),
                                 izinler=json.dumps(list(he.ROL_VARSAYILAN[rol] if izinler is None else izinler))))
    await tohumlu.commit()
    he.onbellegi_temizle()
    assert "asistanlar" in he.ROL_VARSAYILAN["uye"] and "asistanlar" in he.ROL_VARSAYILAN["yonetici"]
    assert "asistanlar" not in he.ROL_VARSAYILAN["fatura"]

    assert (await istemci.get(M, headers=_b(uye, sahip))).status_code == 200
    for kisi in (kisitli, fatura):
        y = await istemci.get(M, headers=_b(kisi, sahip))
        assert y.status_code == 403 and y.json()["detail"] == {"kod": "hesap_izni_yok", "izin": "asistanlar"}
    # Üye sahibin hesabında sohbet açar; sohbet üyenin (kişiye özel) — sahip göremez.
    sid = await _sohbet(istemci, uye, sahip)
    assert (await _gonder(istemci, uye, sid, hesap=sahip)).status_code == 200
    assert (await istemci.get(f"{M}/sohbetler/{sid}", headers=_b(sahip))).status_code == 404
    assert sid not in [s["id"] for s in (await istemci.get(f"{M}/sohbetler", headers=_b(sahip))).json()["sohbetler"]]
    # Ama günlük hak hesap düzeyinde: sahibin sayacına da yansır.
    assert (await istemci.get(M, headers=_b(sahip))).json()["kullanim"]["bugun"] == 1


async def test_eski_varsayilan_izinli_uye_asistanlar_iznini_alir(db_oturumu):
    from services.hesap_ekibi import izinleri_coz

    eski_uye = ["projeler", "gorevler", "destek", "dosyalar", "siteler", "raporlar", "mesajlar"]
    assert "asistanlar" in izinleri_coz(json.dumps(eski_uye), "uye")
    eski_yonetici = ["projeler", "gorevler", "destek", "dosyalar", "faturalar", "siteler", "raporlar", "krediler",
                     "abonelikler", "mesajlar"]
    assert "asistanlar" in izinleri_coz(json.dumps(eski_yonetici), "yonetici")
    assert "asistanlar" not in izinleri_coz(json.dumps(["projeler", "mesajlar"]), "uye")


# ---------------------------------------------------------------------------
# Liste: dil, sistem istemi yok
# ---------------------------------------------------------------------------
async def test_liste_dilde_ve_sistem_istemi_yok(istemci, yonetici_basligi, tohumlu):
    e = await _musteri(istemci, yonetici_basligi)
    y = await istemci.get(M, params={"dil": "en"}, headers=_b(e))
    assert y.status_code == 200, y.text
    g = y.json()
    seo = next(a for a in g["asistanlar"] if a["anahtar"] == ASISTAN)
    assert seo == {
        "anahtar": ASISTAN,
        "kategori": "seo",
        "ad": "SEO Specialist",
        "aciklama": seo["aciklama"],
        "ornek_sorular": seo["ornek_sorular"],
    }
    assert len(seo["ornek_sorular"]) == 3 and seo["ornek_sorular"][0].startswith("Why")
    assert g["kategoriler"][0] == {"anahtar": "seo", "ad": "SEO & AI Search"}
    assert g["kullanim"] == {"bugun": 0, "sinir": 50, "kalan": 50}
    assert g["kredi"] == {"mesaj_basi": 0.0, "bakiye": None}
    assert g["kaynak"] == {"ad": "agency-agents", "depo": "https://github.com/msitarzewski/agency-agents", "lisans": "MIT"}
    assert "sistem_istemi" not in y.text
    for parca in ISTEM_PARCALARI:
        assert parca not in y.text
    # Arapça
    g = (await istemci.get(M, params={"dil": "ar"}, headers=_b(e))).json()
    assert next(a for a in g["asistanlar"] if a["anahtar"] == ASISTAN)["ad"] == "خبير تحسين محركات البحث (SEO)"
    # Kategori sırası: tohum dosyasının sırası.
    kategoriler = [a["kategori"] for a in g["asistanlar"]]
    assert kategoriler == sorted(kategoriler, key=[k["anahtar"] for k in g["kategoriler"]].index)


# ---------------------------------------------------------------------------
# Sohbet akışı
# ---------------------------------------------------------------------------
async def test_sohbet_akisi_baslik_ve_yanitlarda_istem_yok(istemci, yonetici_basligi, tohumlu, ai):
    e = await _musteri(istemci, yonetici_basligi)
    sid = await _sohbet(istemci, e)
    y = await _gonder(istemci, e, sid, "Sitem Google'da neden görünmüyor?\nİkinci satır")
    assert y.status_code == 200, y.text
    g = y.json()
    assert g["kullanici_mesaji"]["rol"] == "user" and g["asistan_mesaji"]["rol"] == "assistant"
    assert g["asistan_mesaji"]["icerik"] == "**Yanıt 1**\n\n- madde"
    assert g["sohbet"]["baslik"] == "Sitem Google'da neden görünmüyor? İkinci satır"
    assert g["kullanim"] == {"bugun": 1, "sinir": 50, "kalan": 49}
    d = (await istemci.get(f"{M}/sohbetler/{sid}", headers=_b(e))).json()
    assert [m["rol"] for m in d["mesajlar"]] == ["user", "assistant"]
    liste = (await istemci.get(f"{M}/sohbetler", params={"asistan": ASISTAN}, headers=_b(e))).json()["sohbetler"]
    assert [s["id"] for s in liste] == [sid]
    assert (await istemci.get(f"{M}/sohbetler", params={"asistan": "baska"}, headers=_b(e))).json()["sohbetler"] == []
    for metin in (y.text, json.dumps(d), json.dumps(liste)):
        assert "sistem_istemi" not in metin
        for parca in ISTEM_PARCALARI:
            assert parca not in metin
    # Jeton sayıları saklanıyor (müşteriye dönmüyor).
    from models.uzman_asistanlar import AsistanMesajlari

    m = (await tohumlu.execute(select(AsistanMesajlari).where(AsistanMesajlari.id == g["asistan_mesaji"]["id"]))).scalars().one()
    assert (m.token_giris, m.token_cikis) == (100, 20)


async def test_baska_hesabin_sohbeti_404(istemci, yonetici_basligi, tohumlu, ai):
    a = await _musteri(istemci, yonetici_basligi)
    b = await _musteri(istemci, yonetici_basligi)
    sid = await _sohbet(istemci, a)
    for metot, yol, govde in (
        ("GET", f"{M}/sohbetler/{sid}", None),
        ("POST", f"{M}/sohbetler/{sid}/mesaj", {"icerik": "x"}),
        ("DELETE", f"{M}/sohbetler/{sid}", None),
    ):
        y = await istemci.request(metot, yol, json=govde, headers=_b(b))
        assert y.status_code == 404 and _kod(y) == "sohbet_yok", (yol, y.text)
    assert ai.cagrilar == []
    # Bilinmeyen / pasif asistanla sohbet açılmaz.
    y = await istemci.post(f"{M}/sohbetler", json={"asistan_anahtar": "yok-boyle"}, headers=_b(a))
    assert y.status_code == 404 and _kod(y) == "asistan_yok"


async def test_istemci_sistem_istemi_model_max_tokens_gonderemez(istemci, yonetici_basligi, tohumlu, ai):
    from services import uzman_asistanlar as s
    from services import yapay_zeka

    e = await _musteri(istemci, yonetici_basligi)
    sid = await _sohbet(istemci, e)
    y = await _gonder(
        istemci, e, sid, "Merhaba",
        model="gpt-pahali", max_tokens=99999, sistem_istemi=KOTU, system=KOTU,
        messages=[{"role": "system", "content": KOTU}],
    )
    assert y.status_code == 200, y.text
    c = ai.cagrilar[0]
    assert c["model"] == yapay_zeka.varsayilan_model() and c["max_tokens"] == 1500
    sistem = c["mesajlar"][0]
    assert sistem["role"] == "system" and sistem["content"].startswith("You are an SEO Specialist")
    assert sistem["content"].endswith(s.GUVENLIK_EKI)
    assert [m["role"] for m in c["mesajlar"]] == ["system", "user"]
    assert all(KOTU not in m["content"] for m in c["mesajlar"])
    # Yöneticinin ayarı model ve max_tokens'u belirler.
    try:
        await _ayarlar(istemci, yonetici_basligi, asistan_model="ozel-asistan-model", asistan_max_tokens=900)
        assert (await _gonder(istemci, e, sid, "İkinci")).status_code == 200
        assert ai.cagrilar[-1]["model"] == "ozel-asistan-model" and ai.cagrilar[-1]["max_tokens"] == 900
    finally:
        await _ayarlar(istemci, yonetici_basligi, asistan_model="", asistan_max_tokens=1500)


def test_baglam_kurma_kirpar_birlestirir_kullaniciyla_baslar():
    from services.uzman_asistanlar import baglam_kur

    gecmis = [("user" if i % 2 == 0 else "assistant", f"m{i}") for i in range(30)] + [("user", "son")]
    b = baglam_kur(gecmis)
    assert len(b) <= 12 and b[0]["role"] == "user" and b[-1]["content"] == "son"
    # Karakter sınırı: büyük mesajlar düşer, en yeni her zaman kalır.
    gecmis = [("user", "a" * 7000), ("assistant", "b" * 7000), ("user", "c" * 7000)]
    b = baglam_kur(gecmis)
    assert b == [{"role": "user", "content": "c" * 7000}]
    gecmis = [("user", "a" * 5000), ("assistant", "b" * 5000), ("user", "c" * 1000)]
    assert [m["role"] for m in baglam_kur(gecmis)] == ["user", "assistant", "user"]
    # Baştaki asistan mesajı düşer; art arda aynı rol birleşir; boşlar atılır.
    gecmis = [("assistant", "x"), ("user", "bir"), ("user", "iki"), ("assistant", " "), ("system", "kötü")]
    assert baglam_kur(gecmis) == [{"role": "user", "content": "bir\n\niki"}]


async def test_uzun_sohbette_baglam_kirpilir(istemci, yonetici_basligi, tohumlu, ai):
    from models.uzman_asistanlar import AsistanMesajlari

    e = await _musteri(istemci, yonetici_basligi)
    sid = await _sohbet(istemci, e)
    for i in range(20):
        tohumlu.add(AsistanMesajlari(sohbet_id=sid, rol="user" if i % 2 == 0 else "assistant", icerik=f"eski {i} " + "z" * 900))
    await tohumlu.commit()
    assert (await _gonder(istemci, e, sid, "yeni soru")).status_code == 200
    mesajlar = ai.cagrilar[0]["mesajlar"]
    assert mesajlar[0]["role"] == "system"
    govde = mesajlar[1:]
    assert len(govde) <= 12 and govde[0]["role"] == "user" and govde[-1]["content"] == "yeni soru"
    assert sum(len(m["content"]) for m in govde) <= 12_000
    # Mesaj uzunluğu sınırı: 8000.
    y = await _gonder(istemci, e, sid, "x" * 8001)
    assert y.status_code == 422
    y = await _gonder(istemci, e, sid, "   ")
    assert y.status_code == 422 and _kod(y) == "bos_mesaj"


# ---------------------------------------------------------------------------
# Sınırlar ve kredi
# ---------------------------------------------------------------------------
async def test_gunluk_sinir_429(istemci, yonetici_basligi, tohumlu, ai):
    e = await _musteri(istemci, yonetici_basligi, gunluk_mesaj=2)
    sid = await _sohbet(istemci, e)
    assert (await istemci.get(M, headers=_b(e))).json()["kullanim"] == {"bugun": 0, "sinir": 2, "kalan": 2}
    for _ in range(2):
        assert (await _gonder(istemci, e, sid)).status_code == 200
    y = await _gonder(istemci, e, sid)
    assert y.status_code == 429 and _kod(y) == "gunluk_sinir" and y.json()["detail"]["kalan"] == 0
    assert len(ai.cagrilar) == 2
    assert (await istemci.get(M, headers=_b(e))).json()["kullanim"]["kalan"] == 0
    # Silinen sohbet hakkı geri vermez.
    assert (await istemci.delete(f"{M}/sohbetler/{sid}", headers=_b(e))).status_code == 200
    sid2 = await _sohbet(istemci, e)
    assert (await _gonder(istemci, e, sid2)).status_code == 429


async def test_genel_gunluk_sinir_site_ayarindan(istemci, yonetici_basligi, tohumlu, ai):
    e = await _musteri(istemci, yonetici_basligi)
    try:
        await _ayarlar(istemci, yonetici_basligi, asistan_gunluk_sinir=1)
        sid = await _sohbet(istemci, e)
        assert (await _gonder(istemci, e, sid)).status_code == 200
        assert (await _gonder(istemci, e, sid)).status_code == 429
    finally:
        await _ayarlar(istemci, yonetici_basligi, asistan_gunluk_sinir=50)


async def test_kisi_basi_dakikada_10_mesaj(istemci, yonetici_basligi, tohumlu, ai):
    e = await _musteri(istemci, yonetici_basligi)
    sid = await _sohbet(istemci, e)
    for i in range(10):
        assert (await _gonder(istemci, e, sid, f"soru {i}")).status_code == 200
    y = await _gonder(istemci, e, sid, "on birinci")
    assert y.status_code == 429 and _kod(y) == "cok_hizli"
    assert len(ai.cagrilar) == 10


async def test_kredi_dusumu_yetersiz_402_hata_iadesi_ve_yeniden(istemci, yonetici_basligi, tohumlu, ai):
    from models.uzman_asistanlar import AsistanMesajlari
    from services import kredi

    e = await _musteri(istemci, yonetici_basligi)
    sid = await _sohbet(istemci, e)
    try:
        g = await _ayarlar(istemci, yonetici_basligi, asistan_mesaj_kredi=0.3)
        assert g["asistan_mesaj_kredi"] == 0.5  # 0.25'in katına yukarı
        await _ayarlar(istemci, yonetici_basligi, asistan_mesaj_kredi=0.25)
        assert (await istemci.get(M, headers=_b(e))).json()["kredi"] == {"mesaj_basi": 0.25, "bakiye": 0.0}

        y = await _gonder(istemci, e, sid, "kredisiz")
        assert y.status_code == 402 and _kod(y) == "kredi_yetersiz", y.text
        assert ai.cagrilar == []
        sayi = (await tohumlu.execute(select(func.count()).where(AsistanMesajlari.sohbet_id == sid))).scalar()
        assert sayi == 0  # gönderilemeyen mesaj kaydedilmez

        await kredi.yukle(tohumlu, eposta=e, saat=0.5, tur="hediye", aciklama="test")
        assert (await _gonder(istemci, e, sid, "birinci")).status_code == 200
        assert await kredi.bakiye(tohumlu, e) == 0.25

        # Model hatası: kullanıcı mesajı kalır, kredi iade edilir, hata kodu döner.
        ai.hata = True
        y = await _gonder(istemci, e, sid, "ikinci")
        assert y.status_code == 502 and _kod(y) == "ai_hatasi", y.text
        bekleyen_id = y.json()["detail"]["mesaj_id"]
        assert await kredi.bakiye(tohumlu, e) == 0.25
        hareketler = await kredi.hareketler(tohumlu, e)
        assert [h.tur for h in hareketler][:2] == ["iade", "harcama"]
        tohumlu.expire_all()
        d = (await istemci.get(f"{M}/sohbetler/{sid}", headers=_b(e))).json()["mesajlar"]
        assert [m["rol"] for m in d] == ["user", "assistant", "user"] and d[-1]["id"] == bekleyen_id

        # Yeniden dene: yeni kullanıcı mesajı yazılmaz, yanıt bekleyen mesaja gelir.
        ai.hata = False
        y = await _gonder(istemci, e, sid, "", yeniden=True)
        assert y.status_code == 200, y.text
        assert y.json()["kullanici_mesaji"]["id"] == bekleyen_id
        d = (await istemci.get(f"{M}/sohbetler/{sid}", headers=_b(e))).json()["mesajlar"]
        assert [m["rol"] for m in d] == ["user", "assistant", "user", "assistant"]
        assert await kredi.bakiye(tohumlu, e) == 0.0
        assert (await _gonder(istemci, e, sid, "üçüncü")).status_code == 402
    finally:
        await _ayarlar(istemci, yonetici_basligi, asistan_mesaj_kredi=0)


async def test_yapilandirilmamis_ai_503_kullanici_mesaji_kalir(istemci, yonetici_basligi, tohumlu):
    # conftest varsayılanı: sağlayıcı yok → 503 ai_kapali.
    e = await _musteri(istemci, yonetici_basligi)
    sid = await _sohbet(istemci, e)
    y = await _gonder(istemci, e, sid, "kimse yok mu")
    assert y.status_code == 503 and _kod(y) == "ai_kapali"
    d = (await istemci.get(f"{M}/sohbetler/{sid}", headers=_b(e))).json()["mesajlar"]
    assert [m["icerik"] for m in d] == ["kimse yok mu"]
    assert (await istemci.get(M, headers=_b(e))).json()["kullanim"]["bugun"] == 0


async def test_yumusak_silme(istemci, yonetici_basligi, tohumlu, ai):
    from models.uzman_asistanlar import AsistanSohbetleri

    e = await _musteri(istemci, yonetici_basligi)
    sid = await _sohbet(istemci, e)
    assert (await istemci.delete(f"{M}/sohbetler/{sid}", headers=_b(e))).json() == {"ok": True}
    assert (await istemci.get(f"{M}/sohbetler/{sid}", headers=_b(e))).status_code == 404
    assert (await istemci.get(f"{M}/sohbetler", headers=_b(e))).json()["sohbetler"] == []
    tohumlu.expire_all()
    satir = (await tohumlu.execute(select(AsistanSohbetleri).where(AsistanSohbetleri.id == sid))).scalars().one()
    assert satir.silindi is True


# ---------------------------------------------------------------------------
# Yönetici
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "metot,yol",
    [("GET", Y), ("PUT", f"{Y}/ayarlar"), ("GET", f"{Y}/kullanim"), ("PUT", f"{Y}/{ASISTAN}"), ("POST", f"{Y}/{ASISTAN}/dene")],
)
async def test_yonetim_uclari_anonim_401_musteri_403(istemci, metot, yol):
    assert (await istemci.request(metot, yol, json={})).status_code == 401
    assert (await istemci.request(metot, yol, json={}, headers=_b(_e()))).status_code == 403


async def test_yonetici_liste_duzenleme_pasif_ve_dogrulama(istemci, yonetici_basligi, tohumlu, ai):
    g = (await istemci.get(Y, headers=yonetici_basligi)).json()
    seo = next(a for a in g["asistanlar"] if a["anahtar"] == ASISTAN)
    assert seo["sistem_istemi"].startswith("You are an SEO Specialist") and seo["aktif"] is True
    assert set(seo["ceviriler"]) == {"en", "de", "ru", "zh", "hi", "ar"}
    assert g["kaynak"]["lisans"] == "MIT" and "Permission is hereby granted" in g["kaynak"]["lisans_metni"]
    assert g["ayarlar"]["asistan_max_tokens"] == 1500 and g["ayarlar"]["asistan_gunluk_sinir"] == 50

    anahtar = "brand-strategist"
    once = next(a for a in g["asistanlar"] if a["anahtar"] == anahtar)
    e = await _musteri(istemci, yonetici_basligi)
    sid = await _sohbet(istemci, e, asistan=anahtar)
    try:
        y = await istemci.put(
            f"{Y}/{anahtar}",
            json={
                "ad": "Marka Stratejisti (yeni)",
                "ceviriler": {**once["ceviriler"], "en": {**once["ceviriler"]["en"], "ad": "Brand Strategist (new)"}},
                "sistem_istemi": "Yeni istem.",
                "sira": 5,
                "aktif": False,
            },
            headers=yonetici_basligi,
        )
        assert y.status_code == 200, y.text
        assert y.json()["ad"] == "Marka Stratejisti (yeni)" and y.json()["aktif"] is False
        liste = (await istemci.get(M, headers=_b(e))).json()["asistanlar"]
        assert anahtar not in [a["anahtar"] for a in liste]
        y = await istemci.post(f"{M}/sohbetler", json={"asistan_anahtar": anahtar}, headers=_b(e))
        assert y.status_code == 404
        y = await _gonder(istemci, e, sid)
        assert y.status_code == 409 and _kod(y) == "asistan_pasif"

        y = await istemci.put(f"{Y}/{anahtar}", json={"aktif": True}, headers=yonetici_basligi)
        assert y.status_code == 200 and y.json()["sistem_istemi"] == "Yeni istem."
        liste = (await istemci.get(M, params={"dil": "en"}, headers=_b(e))).json()["asistanlar"]
        assert next(a for a in liste if a["anahtar"] == anahtar)["ad"] == "Brand Strategist (new)"
        assert (await _gonder(istemci, e, sid)).status_code == 200
        assert ai.cagrilar[-1]["mesajlar"][0]["content"].startswith("Yeni istem.")

        for govde, alan in (
            ({"ad": "  "}, "ad"),
            ({"kategori": "yok"}, "kategori"),
            ({"sira": -1}, "sira"),
            ({"aktif": "evet"}, "aktif"),
            ({"sistem_istemi": ""}, "sistem_istemi"),
            ({"ornek_sorular": ["s"] * 7}, "ornek_sorular"),
        ):
            y = await istemci.put(f"{Y}/{anahtar}", json=govde, headers=yonetici_basligi)
            assert y.status_code == 400 and y.json()["detail"]["alan"] == alan, (govde, y.text)
        assert (await istemci.put(f"{Y}/yok-boyle", json={"aktif": True}, headers=yonetici_basligi)).status_code == 404
    finally:
        await istemci.put(
            f"{Y}/{anahtar}",
            json={k: once[k] for k in ("ad", "ceviriler", "sistem_istemi", "sira", "aktif")},
            headers=yonetici_basligi,
        )


async def test_dene_kaydetmez_istem_taslagi_kullanir(istemci, yonetici_basligi, tohumlu, ai):
    from models.uzman_asistanlar import AsistanMesajlari, AsistanSohbetleri

    async def sayilar():
        s = (await tohumlu.execute(select(func.count(AsistanSohbetleri.id)))).scalar()
        m = (await tohumlu.execute(select(func.count(AsistanMesajlari.id)))).scalar()
        return s, m

    once = await sayilar()
    y = await istemci.post(f"{Y}/{ASISTAN}/dene", json={"icerik": "Deneme sorusu"}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    assert y.json()["icerik"].startswith("**Yanıt 1**") and y.json()["token_giris"] == 100
    assert ai.cagrilar[0]["mesajlar"][0]["content"].startswith("You are an SEO Specialist")
    y = await istemci.post(
        f"{Y}/{ASISTAN}/dene", json={"icerik": "x", "sistem_istemi": "Taslak istem"}, headers=yonetici_basligi
    )
    assert y.status_code == 200
    assert ai.cagrilar[1]["mesajlar"][0]["content"].startswith("Taslak istem")
    assert await sayilar() == once
    # Taslak istem kaydedilmedi.
    g = (await istemci.get(Y, headers=yonetici_basligi)).json()
    assert next(a for a in g["asistanlar"] if a["anahtar"] == ASISTAN)["sistem_istemi"].startswith("You are an SEO")
    assert (await istemci.post(f"{Y}/yok-boyle/dene", json={"icerik": "x"}, headers=yonetici_basligi)).status_code == 404


async def test_ayarlar_dogrulama_ve_kullanim_ozeti(istemci, yonetici_basligi, tohumlu, ai):
    y = await istemci.put(f"{Y}/ayarlar", json={"asistan_model": "kötü model!"}, headers=yonetici_basligi)
    assert y.status_code == 400 and y.json()["detail"]["alan"] == "asistan_model"
    y = await istemci.put(f"{Y}/ayarlar", json={"asistan_max_tokens": 99999}, headers=yonetici_basligi)
    assert y.status_code == 422
    y = await istemci.put(f"{Y}/ayarlar", json={"asistan_gunluk_sinir": -1}, headers=yonetici_basligi)
    assert y.status_code == 422

    e = await _musteri(istemci, yonetici_basligi)
    sid = await _sohbet(istemci, e)
    for _ in range(3):
        assert (await _gonder(istemci, e, sid)).status_code == 200
    g = (await istemci.get(f"{Y}/kullanim", params={"gun": 30}, headers=yonetici_basligi)).json()
    satir = next(h for h in g["hesaplar"] if h["hesap_email"] == e)
    assert satir["kullanici_mesaji"] == 3 and satir["asistan_mesaji"] == 3
    assert satir["token_giris"] == 300 and satir["token_cikis"] == 60 and satir["son_mesaj_at"]
    assert any(a["anahtar"] == ASISTAN and a["asistan_mesaji"] >= 3 for a in g["asistanlar"])
    assert any(s["kapsam"] == "asistan" and s["istek"] >= 3 for s in g["gunluk"])
    assert (await istemci.get(f"{Y}/kullanim", params={"gun": 0}, headers=yonetici_basligi)).status_code == 422
