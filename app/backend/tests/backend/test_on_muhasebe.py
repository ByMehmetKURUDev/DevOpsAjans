"""Faz 6M — Ön muhasebe: hesaplar, gelir-gider, cari, bütçe, raporlar, CSV, otomatik yansıma.

Kapsam: saf kurallar (kuruş yuvarlama — yarım yukarı, KDV tam sayı aritmetiği, IBAN biçim + mod-97, kart son 4 hane,
vergi no, tekrar dönemleri ay sonu kırpma, yaşlandırma kova sınırları + FIFO), yetki (401/403, modül kapalı, müşteri
yalnız kendi hesabı, yönetici ajans tam / müşteri salt okunur, ekip izni `muhasebe`, eski varsayılan), hesap bakiyesi
(açılış + peşin + tahsilat; vadeli satış hesabı etkilemez), virman iki tarafı (ve farklı para biriminde giriş tutarı),
hareket doğrulamaları, KDV özeti toplamları (bilgilendirme amaçlı), cari ekstre (devreden bakiye, PDF + CSV),
yaşlandırma ucu, tekrarlayan gider (tekil üretim), bütçe aşımı (bir kez olay + otomasyon bağlamı), otomatik yansıma
(ajans: ödenen fatura / ödemesi kaydedilmemiş fatura; müşteri: POS gün sonu nakit/kart ayrı hesaba, hukuk masrafı,
saha işi) — tekillik ve kaynak silinince/iptalde TERS KAYIT, CSV içe aktarma (sütun eşleme, hatalı satır, tekrar
yüklemede atlama), CSV/PDF dışa aktarma (formül kaçışı), çöp kutusu, ekler, haftalık özet (yalnız ajans), zamanlı iş;
öneriler (hukuk / saha varsayılan onaylı, "ödendi" ama ödeme kaydı olmayan fatura hep öneri: onay → tek kayıt, yok say →
yeniden önerilmez, kaynak değişince yeniden açılır, toplu onay, saha carisi onayda açılır), müşterinin ajansa ödediği
faturalar (gider; Shopier → kart, havale → banka), IBAN yalnız son 4 hane (tam IBAN hiçbir uçta yok), POS / sanal POS
hesabı, `muhasebe_okur` (yalnız rapor), `muhasebe.alacak_gecikti` (eşik başına bir kez), bütçe aşımı bildirimi (bir kez),
nakit akışında 30 / 60 / 90 gün beklenen tahsilat / ödeme.

KDV özeti ve oranlar BİLGİLENDİRME amaçlıdır; beyanname yerine geçmez (3065 sayılı KDV Kanunu genel oranları 1/10/20 —
varsayılan liste; kullanıcı 0–100 arası oran girebilir).
"""

import json
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from conftest import jeton_uret

Y = "/api/v1/muhasebe-yonetim"
M = "/api/v1/muhasebe"
MODUL = "/api/v1/moduller"
UTC = timezone.utc
#: Testlerin "şimdi"si: 5 Ekim 2026 Pazartesi 09:00 İstanbul.
SIMDI = datetime(2026, 10, 5, 6, 0, tzinfo=UTC)
BUGUN = date(2026, 10, 5)


def _e(on: str = "mh") -> str:
    return f"{on}-{uuid.uuid4().hex[:8]}@muhasebe.dev"


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
def _ortam(monkeypatch):
    from routers import muhasebe as r
    from services import hesap_ekibi
    from services import muhasebe as s

    r.hiz_sinirlarini_temizle()
    hesap_ekibi.onbellegi_temizle()
    saat = {"an": SIMDI}
    monkeypatch.setattr(s, "simdi", lambda: saat["an"])
    yield saat
    r.hiz_sinirlarini_temizle()


async def _modul(istemci, yonetici_basligi, eposta, anahtar="on_muhasebe", acik=True, **ayarlar):
    govde = {"acik": acik}
    if ayarlar:
        govde["ayarlar"] = ayarlar
    y = await istemci.put(f"{MODUL}/musteri/{eposta}/{anahtar}", json=govde, headers=yonetici_basligi)
    assert y.status_code == 200, y.text


async def _post(istemci, yol, govde, basliklar, beklenen=200):
    y = await istemci.post(yol, json=govde, headers=basliklar)
    assert y.status_code == beklenen, (yol, y.text)
    return y.json()


async def _hesap(istemci, basliklar, yol=M, **govde):
    govde.setdefault("tur", "kasa")
    govde.setdefault("ad", f"Kasa {uuid.uuid4().hex[:5]}")
    return await _post(istemci, f"{yol}/hesaplar", govde, basliklar)


async def _cari(istemci, basliklar, yol=M, **govde):
    govde.setdefault("ad", f"Cari {uuid.uuid4().hex[:5]}")
    return await _post(istemci, f"{yol}/cariler", govde, basliklar)


async def _hareket(istemci, basliklar, yol=M, beklenen=200, **govde):
    govde.setdefault("tarih", BUGUN.isoformat())
    return await _post(istemci, f"{yol}/hareketler", govde, basliklar, beklenen)


async def _kategori(istemci, basliklar, tur, anahtar, yol=M):
    meta = (await istemci.get(f"{yol}/meta", headers=basliklar)).json()
    return next(k for k in meta["kategoriler"] if k["tur"] == tur and k["anahtar"] == anahtar)


async def _musteri(istemci, yonetici_basligi, on="mh"):
    m = _e(on)
    await _modul(istemci, yonetici_basligi, m)
    return m, _b(m)


# ---------------------------------------------------------------------------
# Saf kurallar
# ---------------------------------------------------------------------------
def test_kurus_yuvarlama_ve_kdv():
    from services import muhasebe as s

    assert s.kurus_coz("1.234,56", "t") == 123456 and s.kurus_coz("1,234.56", "t") == 123456
    # Yalnız virgül → Türkçe ondalık ("1,250" = 1,25 ₺); birden çok virgül binlik.
    assert s.kurus_coz("12,5", "t") == 1250 and s.kurus_coz("1,250", "t") == 125 and s.kurus_coz("1,234,567", "t") == 123456700
    assert s.kurus_coz(19.99, "t") == 1999 and s.kurus_coz("₺ 1.250 TL", "t") == 125000
    # Yarım yukarı: 0,005 → 0,01; 2,345 → 2,35; 2,344 → 2,34 (kayan nokta yok — Decimal).
    assert s.kurus_coz("0,005", "t") == 1 and s.kurus_coz("2,345", "t") == 235 and s.kurus_coz("2,344", "t") == 234
    # Tek nokta + 3 hane Türkçe binlik ("2.344" = 2.344 ₺); "2.5" / "0.005" ondalık.
    assert s.kurus_coz("2.344", "t") == 234400 and s.kurus_coz("2.5", "t") == 250 and s.kurus_coz("0.005", "t") == 1
    assert s.kurus_coz("-15.000,00", "t", eksi_olabilir=True) == -1500000 and s.kurus_coz("(250,00)", "t", eksi_olabilir=True) == -25000
    assert s.kurus_coz("1.000", "t", ondalik=",") == 100000 and s.kurus_coz("1,000", "t", ondalik=".") == 100000
    for kotu, kod in (("abc", "tutar_gecersiz"), ("-5", "tutar_eksi"), ("0", "tutar_sifir"), ("", "zorunlu")):
        with pytest.raises(s.MuhasebeHatasi) as h:
            s.kurus_coz(kotu, "t")
        assert h.value.kod == kod
    # KDV dahil 1.200,00 ₺ (%20) → 200,00 ₺; 1,00 ₺ (%20) → 0,17 ₺ (16,67 kuruş yukarı); %1 → 0.
    assert s.kdv_dahilden(120000, 20) == 20000 and s.kdv_dahilden(100, 20) == 17 and s.kdv_dahilden(5, 1) == 0
    assert s.kdv_haricten(1001, 10) == 100 and s.kdv_haricten(1005, 10) == 101 and s.kdv_dahilden(500, None) == 0
    assert s.yuvarla(5, 2) == 3 and s.yuvarla(-5, 2) == -3 and s.yuvarla(4, 3) == 1
    assert s.kdv_orani_duzelt("%20") == 20 and s.kdv_orani_duzelt(None) is None
    with pytest.raises(s.MuhasebeHatasi):
        s.kdv_orani_duzelt("101")


def test_iban_son4_vergi_no_ve_etiket():
    from services import muhasebe as s

    # ISO 13616 örnek IBAN'ı (mod-97 = 1); boşluk/küçük harf düzeltilir.
    assert s.iban_duzelt("tr33 0006 1005 1978 6457 8413 26") == "TR330006100519786457841326"
    assert s.iban_duzelt("DE89370400440532013000") == "DE89370400440532013000"
    for kotu in ("TR330006100519786457841327", "TR3300061005197864578413", "1234", "TRXX0006100519786457841326"):
        with pytest.raises(s.MuhasebeHatasi) as h:
            s.iban_duzelt(kotu)
        assert h.value.kod == "iban_gecersiz"
    # Gösterimde YALNIZ son 4 hane (ülke kodu harf; denetim haneleri de gizli).
    assert s.iban_maskele("TR330006100519786457841326") == "TR•• •••• 1326"
    assert s.son4_duzelt("4242") == "4242"
    for kotu in ("424", "42a2", "4242 4242"):
        with pytest.raises(s.MuhasebeHatasi):
            s.son4_duzelt(kotu)
    assert s.vergi_no_duzelt("123 456 7890") == "1234567890"
    with pytest.raises(s.MuhasebeHatasi):
        s.vergi_no_duzelt("12345")
    assert s.etiketler_duzelt("Kira, Ofis ,kira") == ["kira", "ofis"]


def test_tekrar_donemleri_ay_sonu():
    from services import muhasebe as s

    b = date(2026, 1, 31)
    assert [s.donem_tarihi(b, "aylik", n) for n in range(4)] == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)]
    assert s.donem_tarihi(date(2024, 2, 29), "yillik", 1) == date(2025, 2, 28)
    assert s.donem_tarihi(date(2026, 1, 15), "uc_aylik", 1) == date(2026, 4, 15)
    assert s.sonraki_donem(b, "aylik", date(2026, 2, 28)) == date(2026, 3, 31)
    assert s.sonraki_donem(date(2026, 10, 5), "haftalik", date(2026, 10, 5)) == date(2026, 10, 12)
    assert s.donemler(date(2026, 1, 5), "aylik", date(2026, 11, 1), date(2027, 1, 31)) == [
        date(2026, 11, 5), date(2026, 12, 5), date(2027, 1, 5)]
    assert s.donemler(date(2026, 1, 5), "aylik", date(2026, 11, 1), date(2027, 1, 31), bitis=date(2026, 12, 1)) == [date(2026, 11, 5)]


def test_yaslandirma_kova_sinirlari_ve_fifo():
    from services import muhasebe as s

    # Sınırlar dahil: 30. gün "0–30", 31. gün "31–60", 60 → "31–60", 61 → "61–90", 90 → "61–90", 91 → "90+".
    assert [s.kova(g) for g in (-1, 0, 30, 31, 60, 61, 90, 91, 400)] == [
        "vadesi_gelmemis", "0_30", "0_30", "31_60", "31_60", "61_90", "61_90", "90_ustu", "90_ustu"]
    t = date(2026, 10, 5)
    kalemler = [s.AcikKalem(t - timedelta(days=95), 10000, 1), s.AcikKalem(t - timedelta(days=45), 20000, 2),
                s.AcikKalem(t + timedelta(days=5), 5000, 3)]
    y = s.yaslandir(kalemler, 15000, t)  # en eski 100,00 tamamen, ikinci 50,00 kapanır
    assert y.kovalar == {"vadesi_gelmemis": 5000, "0_30": 0, "31_60": 15000, "61_90": 0, "90_ustu": 0}
    assert y.acik == 20000 and y.fazla == 0 and y.en_eski_gun == 45
    y = s.yaslandir(kalemler, 40000, t)
    assert y.acik == 0 and y.fazla == 5000
    # Cari etkisi: peşin satış etkisiz, vadeli satış borç, tahsilat alacak, cariye ödeme borç, vadeli alış alacak.
    assert s.cari_etkisi("gelir", 100, True) == (100, 100) and s.cari_etkisi("gelir", 100, False) == (100, 0)
    assert s.cari_etkisi("tahsilat", 100, True) == (0, 100) and s.cari_etkisi("odeme", 100, True) == (100, 0)
    assert s.cari_etkisi("gider", 100, False) == (0, 100)


# ---------------------------------------------------------------------------
# Yetki ve kapsam
# ---------------------------------------------------------------------------
async def test_yetki_401_403_ve_modul_kapali(istemci, yonetici_basligi):
    m = _e()
    for yol in (f"{M}/meta", f"{M}/hareketler", f"{Y}/meta", f"{Y}/musteri-hesaplari"):
        assert (await istemci.get(yol)).status_code == 401, yol
    assert (await istemci.get(f"{Y}/hareketler", headers=_b(m))).status_code == 403
    assert (await istemci.post(f"{Y}/hesaplar", json={"tur": "kasa", "ad": "X"}, headers=_b(m))).status_code == 403
    y = await istemci.get(f"{M}/meta", headers=_b(m))
    assert y.status_code == 403 and _kod(y) == "modul_kapali"
    await _modul(istemci, yonetici_basligi, m)
    y = await istemci.get(f"{M}/meta", headers=_b(m))
    assert y.status_code == 200, y.text
    meta = y.json()
    assert meta["ajans"] is False and meta["hesap_siniri"] == 10 and meta["aktarim_kaynaklari"] == ["odeme", "pos", "hukuk", "saha"]
    assert meta["okur"] is False and meta["oneri_sayisi"] == 0
    # Varsayılan Türkçe kategori seti ilk açılışta (bir kez) tohumlanır.
    anahtarlar = {k["anahtar"] for k in meta["kategoriler"]}
    assert {"satis", "hizmet", "kira", "personel", "pazarlama", "diger_gider"} <= anahtarlar
    assert len((await istemci.get(f"{M}/meta", headers=_b(m))).json()["kategoriler"]) == len(meta["kategoriler"])
    kira = next(k for k in meta["kategoriler"] if k["anahtar"] == "kira")
    assert kira["ad"] == "Kira" and kira["ad_degisti"] is False


async def test_musteri_yalniz_kendi_hesabi(istemci, yonetici_basligi):
    a, ba = await _musteri(istemci, yonetici_basligi, "a")
    b, bb = await _musteri(istemci, yonetici_basligi, "b")
    h = await _hesap(istemci, ba, ad="A kasası", acilis_bakiyesi="100")
    c = await _cari(istemci, ba, ad="A carisi")
    x = await _hareket(istemci, ba, tur="gelir", tutar="50", hesap_id=h["id"])
    for yontem, yol in (("PUT", f"{M}/hesaplar/{h['id']}"), ("DELETE", f"{M}/hesaplar/{h['id']}"), ("GET", f"{M}/cariler/{c['id']}"),
                        ("PUT", f"{M}/cariler/{c['id']}"), ("GET", f"{M}/hareketler/{x['id']}"), ("PUT", f"{M}/hareketler/{x['id']}"),
                        ("DELETE", f"{M}/hareketler/{x['id']}"), ("GET", f"{M}/cariler/{c['id']}/ekstre")):
        y = await istemci.request(yontem, yol, json={"ad": "Ele geçir", "tutar": "1"} if yontem == "PUT" else None, headers=bb)
        assert y.status_code == 404, (yontem, yol, y.text)
    # Başkasının hesabına/carisine kayıt yazılamaz.
    y = await istemci.post(f"{M}/hareketler", json={"tur": "gelir", "tutar": "5", "hesap_id": h["id"]}, headers=bb)
    assert y.status_code == 400 and _kod(y) == "hesap_bulunamadi"
    assert (await istemci.get(f"{M}/hareketler", headers=bb)).json()["items"] == []
    assert (await istemci.get(f"{M}/hesaplar", params={"hesap": a}, headers=bb)).json()["items"] == []


async def test_yonetici_ajans_tam_musteri_salt_okunur(istemci, yonetici_basligi):
    m, bm = await _musteri(istemci, yonetici_basligi, "destek")
    hm = await _hesap(istemci, bm, ad="Müşteri kasası")
    ha = await _hesap(istemci, yonetici_basligi, Y, ad=f"Ajans kasası {uuid.uuid4().hex[:4]}")
    ajans = (await istemci.get(f"{Y}/hesaplar", headers=yonetici_basligi)).json()["items"]
    assert ha["id"] in [x["id"] for x in ajans] and hm["id"] not in [x["id"] for x in ajans]
    y = await istemci.get(f"{Y}/hesaplar", params={"hesap": m}, headers=yonetici_basligi)
    assert [x["id"] for x in y.json()["items"]] == [hm["id"]]
    meta = (await istemci.get(f"{Y}/meta", params={"hesap": m}, headers=yonetici_basligi)).json()
    assert meta["salt_okunur"] is True and meta["hesap"] == m and meta["aktarim_kaynaklari"] == ["odeme", "pos", "hukuk", "saha"]
    assert (await istemci.get(f"{Y}/meta", headers=yonetici_basligi)).json()["aktarim_kaynaklari"] == ["odeme"]
    for yontem, yol, govde in (("POST", f"{Y}/hesaplar?hesap={m}", {"tur": "kasa", "ad": "X"}),
                               ("PUT", f"{Y}/hesaplar/{hm['id']}?hesap={m}", {"ad": "Y"}),
                               ("POST", f"{Y}/hareketler?hesap={m}", {"tur": "gelir", "tutar": "1", "hesap_id": hm["id"]}),
                               ("PUT", f"{Y}/ayarlar?hesap={m}", {"firma_adi": "X"}), ("POST", f"{Y}/esitle?hesap={m}", {}),
                               ("PUT", f"{Y}/butceler?hesap={m}", {"kategori_id": 1, "tutar": "5"})):
        y = await istemci.request(yontem, yol, json=govde, headers=yonetici_basligi)
        assert y.status_code == 403 and _kod(y) == "salt_okunur", (yol, y.text)
    assert (await istemci.get(f"{Y}/hesaplar/{hm['id']}", headers=yonetici_basligi)).status_code in (404, 405)
    assert (await istemci.put(f"{Y}/hesaplar/{hm['id']}", json={"ad": "Z"}, headers=yonetici_basligi)).status_code == 404
    liste = (await istemci.get(f"{Y}/musteri-hesaplari", headers=yonetici_basligi)).json()["items"]
    assert any(x["hesap_email"] == m and x["hesap_sayisi"] == 1 for x in liste)


async def test_ekip_izni_muhasebe(istemci, yonetici_basligi):
    from core.database import db_manager
    from models.hesap_uyeleri import HesapUyeleri
    from services import hesap_ekibi as he

    sahip, uye, muhasebeci = _e("sahip"), _e("uye"), _e("muhasebeci")
    await _modul(istemci, yonetici_basligi, sahip)
    async with db_manager.async_session_maker() as db:
        for kisi, izinler in ((uye, he.ROL_VARSAYILAN["uye"]), (muhasebeci, ("projeler", "muhasebe"))):
            db.add(HesapUyeleri(hesap_email=sahip, uye_email=kisi, rol="uye", izinler=json.dumps(list(izinler)), durum="aktif",
                                olusturma=he.simdi()))
        await db.commit()
    he.onbellegi_temizle()
    assert "muhasebe" not in he.ROL_VARSAYILAN["uye"] and "muhasebe" not in he.ROL_VARSAYILAN["fatura"]
    assert "muhasebe" in he.ROL_VARSAYILAN["yonetici"]
    y = await istemci.get(f"{M}/hareketler", headers=_b(uye, sahip))
    assert y.status_code == 403 and _kod(y) == "hesap_izni_yok"
    h = await _hesap(istemci, _b(muhasebeci, sahip), ad="Ekip kasası")
    assert [x["ad"] for x in (await istemci.get(f"{M}/hesaplar", headers=_b(sahip))).json()["items"]] == ["Ekip kasası"]
    assert h["id"]


def test_modul_kaydi_ve_eski_yonetici_varsayilani():
    import json as _json

    from core import moduller, sektor_paketleri
    from services import hesap_ekibi as he

    m = moduller.modul("on_muhasebe")
    assert m is not None and m.varsayilan_acik is False and m.kategori == "finans" and not m.paketler
    assert m.musteri_sekmesi == "onMuhasebe" and m.yonetici_sekmesi == "onMuhasebe" and m.varsayilan_ayarlar() == {"hesap_siniri": 10}
    assert all("on_muhasebe" not in p.moduller for p in sektor_paketleri.SEKTOR_PAKETLERI)
    # Canlıdaki (muhasebe / muhasebe_okur'suz; ik ve hukuk VAR) yönetici varsayılanı olduğu gibi kayıtlı üye yeni
    # izinleri de alır; üye ve fatura rolünün varsayılanında ikisi de yok.
    eski = sorted(set(he.IZINLER) - {"muhasebe", "muhasebe_okur"})
    coz = he.izinleri_coz(_json.dumps(eski), "yonetici")
    assert "muhasebe" in coz and "muhasebe_okur" in coz
    for rol in ("uye", "fatura"):
        assert not {"muhasebe", "muhasebe_okur"} & set(he.ROL_VARSAYILAN[rol])
    # Özelleştirilmiş liste değişmez.
    assert "muhasebe" not in he.izinleri_coz(_json.dumps(["projeler", "faturalar"]), "yonetici")


# ---------------------------------------------------------------------------
# Hesaplar, bakiye, virman
# ---------------------------------------------------------------------------
async def test_hesap_turleri_iban_kart_ve_sinir(istemci, yonetici_basligi):
    m = _e("sinir")
    await _modul(istemci, yonetici_basligi, m, hesap_siniri=2)
    b = _b(m)
    banka = await _hesap(istemci, b, tur="banka", ad="İş Bankası", iban="TR33 0006 1005 1978 6457 8413 26", banka_adi="Örnek Bank")
    # Tam IBAN saklanır ama HİÇBİR uçta dönmez: yalnız son 4 hane maskeli.
    assert "iban" not in banka and banka["iban_var"] is True and banka["iban_maske"] == "TR•• •••• 1326" and banka["son4"] == ""
    for yol in (f"{M}/hesaplar", f"{M}/meta"):
        assert "TR330006100519786457841326" not in (await istemci.get(yol, headers=b)).text
    kart = await _hesap(istemci, b, tur="kredi_karti", ad="Şirket kartı", son4="4242", acilis_bakiyesi="-1.250,50")
    assert kart["son4"] == "4242" and kart["iban_var"] is False and kart["bakiye"] == -125050
    # Kart / hesap numarası alınmaz.
    y = await istemci.post(f"{M}/hesaplar", json={"tur": "kredi_karti", "ad": "X", "son4": "1111", "kart_no": "4242424242424242"}, headers=b)
    assert y.status_code == 400 and _kod(y) == "numara_saklanmaz"
    y = await istemci.post(f"{M}/hesaplar", json={"tur": "banka", "ad": "X", "iban": "TR330006100519786457841327"}, headers=b)
    assert y.status_code == 400 and _kod(y) == "iban_gecersiz"
    y = await istemci.post(f"{M}/hesaplar", json={"tur": "kasa", "ad": "Üçüncü"}, headers=b)
    assert y.status_code == 409 and _kod(y) == "hesap_siniri"
    # Arşive alınan hesap sınıra sayılmaz.
    await istemci.put(f"{M}/hesaplar/{kart['id']}", json={"arsiv": True}, headers=b)
    ucuncu = await _hesap(istemci, b, ad="Üçüncü")
    await istemci.put(f"{M}/hesaplar/{ucuncu['id']}", json={"arsiv": True}, headers=b)
    y = await istemci.put(f"{M}/hesaplar/{banka['id']}", json={"tur": "kasa"}, headers=b)
    assert y.status_code == 400 and _kod(y) == "tur_degistirilemez"
    # IBAN değiştirmeden başka alan güncellenince IBAN korunur; yenisi yazılabilir.
    y = (await istemci.put(f"{M}/hesaplar/{banka['id']}", json={"notlar": "Maaş hesabı"}, headers=b)).json()
    assert y["iban_var"] is True and y["iban_maske"] == "TR•• •••• 1326"
    y = (await istemci.put(f"{M}/hesaplar/{banka['id']}", json={"iban": "DE89 3704 0044 0532 0130 00"}, headers=b)).json()
    assert y["iban_maske"] == "DE•• •••• 3000"
    # POS / sanal POS hesabı: yalnız sağlayıcı adı (IBAN, kart no yok).
    await istemci.put(f"{M}/hesaplar/{kart['id']}", json={"arsiv": True}, headers=b)
    pos = await _hesap(istemci, b, tur="pos", ad="Sanal POS", banka_adi="iyzico", iban="TR330006100519786457841326", son4="1111")
    assert pos["tur"] == "pos" and pos["banka_adi"] == "iyzico" and pos["iban_var"] is False and pos["son4"] == ""


async def test_bakiye_hesabi(istemci, yonetici_basligi):
    m, b = await _musteri(istemci, yonetici_basligi, "bakiye")
    kasa = await _hesap(istemci, b, ad="Kasa", acilis_bakiyesi="1.000,00")
    cari = await _cari(istemci, b, ad="Müşteri A")
    await _hareket(istemci, b, tur="gelir", tutar="500", hesap_id=kasa["id"])                       # peşin satış +500
    await _hareket(istemci, b, tur="gider", tutar="200,25", hesap_id=kasa["id"])                    # gider −200,25
    await _hareket(istemci, b, tur="gelir", tutar="700", cari_id=cari["id"])                        # vadeli: hesap etkilenmez
    await _hareket(istemci, b, tur="tahsilat", tutar="300", hesap_id=kasa["id"], cari_id=cari["id"])  # +300
    hesaplar = (await istemci.get(f"{M}/hesaplar", headers=b)).json()
    k = next(x for x in hesaplar["items"] if x["id"] == kasa["id"])
    assert k["bakiye"] == 100000 + 50000 - 20025 + 30000 and hesaplar["toplamlar"] == [{"para_birimi": "TRY", "bakiye": k["bakiye"]}]
    c = (await istemci.get(f"{M}/cariler/{cari['id']}", headers=b)).json()
    assert c["bakiye"] == 70000 - 30000  # cari bize 400,00 borçlu
    ozet = (await istemci.get(f"{M}/ozet", headers=b)).json()
    assert ozet["bakiyeler"] == [{"para_birimi": "TRY", "bakiye": k["bakiye"]}]
    assert ozet["bu_ay"][0]["gelir"] == 120000 and ozet["bu_ay"][0]["gider"] == 20025


async def test_virman_iki_tarafi_ve_para_birimi(istemci, yonetici_basligi):
    m, b = await _musteri(istemci, yonetici_basligi, "virman")
    kasa = await _hesap(istemci, b, ad="Kasa", acilis_bakiyesi="1000")
    banka = await _hesap(istemci, b, tur="banka", ad="Banka", acilis_bakiyesi="50")
    usd = await _hesap(istemci, b, tur="banka", ad="Döviz", para_birimi="USD")
    v = await _post(istemci, f"{M}/virman", {"kaynak_hesap_id": kasa["id"], "hedef_hesap_id": banka["id"], "tutar": "400"}, b)
    assert v["tur"] == "virman" and v["hesap_id"] == kasa["id"] and v["hedef_hesap_id"] == banka["id"] and v["hedef_tutar"] is None
    bak = {x["id"]: x["bakiye"] for x in (await istemci.get(f"{M}/hesaplar", headers=b)).json()["items"]}
    assert bak[kasa["id"]] == 60000 and bak[banka["id"]] == 45000  # iki taraf
    y = await istemci.post(f"{M}/virman", json={"kaynak_hesap_id": kasa["id"], "hedef_hesap_id": kasa["id"], "tutar": "1"}, headers=b)
    assert y.status_code == 400 and _kod(y) == "ayni_hesap"
    # Farklı para birimi: dönüşüm yapılmaz, giriş tutarı zorunlu.
    y = await istemci.post(f"{M}/virman", json={"kaynak_hesap_id": banka["id"], "hedef_hesap_id": usd["id"], "tutar": "330"}, headers=b)
    assert y.status_code == 400 and _kod(y) == "hedef_tutar_gerekli"
    await _post(istemci, f"{M}/virman", {"kaynak_hesap_id": banka["id"], "hedef_hesap_id": usd["id"], "tutar": "330", "hedef_tutar": "10"}, b)
    bak = {x["id"]: x["bakiye"] for x in (await istemci.get(f"{M}/hesaplar", headers=b)).json()["items"]}
    assert bak[banka["id"]] == 12000 and bak[usd["id"]] == 1000
    # Virman gelir/gider raporuna girmez.
    assert (await istemci.get(f"{M}/raporlar/aylik", params={"yil": 2026}, headers=b)).json()["para_birimleri"] == []


async def test_hareket_dogrulamalari_ve_kdv(istemci, yonetici_basligi):
    m, b = await _musteri(istemci, yonetici_basligi, "dogrula")
    kasa = await _hesap(istemci, b, ad="Kasa")
    cari = await _cari(istemci, b, ad="Tedarikçi", tur="tedarikci")
    usd_cari = await _cari(istemci, b, ad="Yabancı", para_birimi="USD")
    kira = await _kategori(istemci, b, "gider", "kira")
    satis = await _kategori(istemci, b, "gelir", "satis")
    for govde, kod in (({"tur": "tahsilat", "tutar": "5", "hesap_id": kasa["id"]}, "cari_gerekli"),
                       ({"tur": "gelir", "tutar": "5"}, "hesap_ya_da_cari_gerekli"),
                       ({"tur": "gider", "tutar": "5", "hesap_id": kasa["id"], "kategori_id": satis["id"]}, "kategori_turu_uyusmuyor"),
                       ({"tur": "gider", "tutar": "5", "hesap_id": kasa["id"], "cari_id": usd_cari["id"]}, "para_birimi_uyusmuyor"),
                       ({"tur": "gider", "tutar": "5", "cari_id": cari["id"], "vade_tarihi": "2026-09-01"}, "vade_once"),
                       ({"tur": "gider", "tutar": "-5", "hesap_id": kasa["id"]}, "tutar_eksi"),
                       ({"tur": "yok", "tutar": "5", "hesap_id": kasa["id"]}, "secim_gecersiz")):
        y = await istemci.post(f"{M}/hareketler", json={"tarih": BUGUN.isoformat(), **govde}, headers=b)
        assert y.status_code == 400 and _kod(y) == kod, (govde, y.text)
    # KDV dahil: 1.200,00 (%20) → KDV 200,00. KDV hariç 1.000,00 + %20 → tutar 1.200,00.
    x = await _hareket(istemci, b, tur="gider", tutar="1.200,00", kdv_orani=20, hesap_id=kasa["id"], kategori_id=kira["id"])
    assert x["tutar"] == 120000 and x["kdv_tutari"] == 20000 and x["kategori"]["anahtar"] == "kira"
    x = await _hareket(istemci, b, tur="gider", tutar="1000", kdv_orani=20, kdv_dahil=False, hesap_id=kasa["id"])
    assert x["tutar"] == 120000 and x["kdv_tutari"] == 20000
    # Vadeli alış: vade varsayılan = tarih; düzenleme kısmi alanla çalışır.
    x = await _hareket(istemci, b, tur="gider", tutar="99,99", kdv_orani=10, cari_id=cari["id"], etiketler=["Ofis"])
    assert x["vade_tarihi"] == BUGUN.isoformat() and x["etiketler"] == ["ofis"] and x["kdv_tutari"] == 909
    y = await istemci.put(f"{M}/hareketler/{x['id']}", json={"aciklama": "Kırtasiye"}, headers=b)
    assert y.status_code == 200 and y.json()["aciklama"] == "Kırtasiye" and y.json()["tutar"] == 9999 and y.json()["kdv_tutari"] == 909


async def test_kdv_ozeti_toplamlari(istemci, yonetici_basligi):
    m, b = await _musteri(istemci, yonetici_basligi, "kdv")
    kasa = await _hesap(istemci, b, ad="Kasa")
    await _hareket(istemci, b, tur="gelir", tutar="1200", kdv_orani=20, hesap_id=kasa["id"], tarih="2026-09-10")
    await _hareket(istemci, b, tur="gelir", tutar="110", kdv_orani=10, hesap_id=kasa["id"], tarih="2026-09-20")
    await _hareket(istemci, b, tur="gider", tutar="600", kdv_orani=20, hesap_id=kasa["id"], tarih="2026-09-15")
    await _hareket(istemci, b, tur="gider", tutar="240", kdv_orani=20, hesap_id=kasa["id"], tarih="2026-10-02")
    r = (await istemci.get(f"{M}/raporlar/kdv", params={"yil": 2026}, headers=b)).json()
    assert r["bilgilendirme"] is True
    p = r["para_birimleri"][0]
    eylul = p["aylar"][8]
    assert (eylul["hesaplanan"], eylul["indirilecek"], eylul["fark"]) == (20000 + 1000, 10000, 11000)
    assert eylul["matrah_satis"] == 100000 + 10000 and eylul["matrah_alis"] == 50000
    ekim = p["aylar"][9]
    assert (ekim["hesaplanan"], ekim["indirilecek"], ekim["fark"]) == (0, 4000, -4000)
    assert (p["hesaplanan"], p["indirilecek"], p["fark"]) == (21000, 14000, 7000)
    y = await istemci.get(f"{M}/raporlar.csv", params={"tur": "kdv", "yil": 2026}, headers=b)
    assert y.status_code == 200 and "hesaplanan_kdv" in y.text and "2026-09;TRY;1100,00;210,00;500,00;100,00;110,00" in y.text


# ---------------------------------------------------------------------------
# Cari: ekstre, yaşlandırma
# ---------------------------------------------------------------------------
async def test_cari_ekstre_devreden_pdf_csv(istemci, yonetici_basligi):
    m, b = await _musteri(istemci, yonetici_basligi, "ekstre")
    kasa = await _hesap(istemci, b, ad="Kasa")
    c = await _cari(istemci, b, ad="Kafe Ada", vergi_no="1234567890", acilis_bakiyesi="1000", acilis_tarihi="2026-01-01")
    await _hareket(istemci, b, tur="gelir", tutar="500", cari_id=c["id"], tarih="2026-03-10", aciklama="Vadeli satış")
    await _hareket(istemci, b, tur="tahsilat", tutar="700", cari_id=c["id"], hesap_id=kasa["id"], tarih="2026-05-05")
    await _hareket(istemci, b, tur="gelir", tutar="200", cari_id=c["id"], hesap_id=kasa["id"], tarih="2026-06-01")  # peşin
    e = (await istemci.get(f"{M}/cariler/{c['id']}/ekstre", params={"bas": "2026-04-01", "bit": "2026-10-31"}, headers=b)).json()
    assert e["devreden"] == 150000  # açılış 1.000 + Mart vadeli satış 500
    assert [(x["tur"], x["borc"], x["alacak"], x["bakiye"]) for x in e["satirlar"]] == [
        ("tahsilat", 0, 70000, 80000), ("gelir", 20000, 20000, 80000)]
    assert (e["toplam_borc"], e["toplam_alacak"], e["kapanis"]) == (20000, 90000, 80000)
    # Açılış tarihi aralıktaysa satır olarak.
    e = (await istemci.get(f"{M}/cariler/{c['id']}/ekstre", params={"bas": "2026-01-01", "bit": "2026-12-31"}, headers=b)).json()
    assert e["devreden"] == 0 and e["satirlar"][0]["tur"] == "acilis" and e["kapanis"] == 80000
    y = await istemci.get(f"{M}/cariler/{c['id']}/ekstre.pdf", params={"bas": "2026-04-01", "bit": "2026-10-31", "dil": "tr"}, headers=b)
    assert y.status_code == 200 and y.headers["content-type"].startswith("application/pdf") and y.content[:4] == b"%PDF"
    from services.pdf_belge import pdf_metni

    metin = pdf_metni(y.content)
    assert "CARİ HESAP" in metin and "Kafe Ada" in metin and "Devreden bakiye" in metin and "1.500,00" in metin
    y = await istemci.get(f"{M}/cariler/{c['id']}/ekstre.csv", params={"bas": "2026-04-01", "bit": "2026-10-31"}, headers=b)
    assert y.status_code == 200 and y.text.startswith("﻿") and "devreden" in y.text and "kapanis;;;900,00" not in y.text
    assert "2026-10-31;kapanis;;;200,00;900,00;800,00" in y.text
    y = await istemci.get(f"{M}/cariler/{c['id']}/ekstre", params={"bas": "2026-05-01", "bit": "2026-04-01"}, headers=b)
    assert y.status_code == 400


async def test_yaslandirma_ucu(istemci, yonetici_basligi):
    m, b = await _musteri(istemci, yonetici_basligi, "yas")
    kasa = await _hesap(istemci, b, ad="Kasa")
    c = await _cari(istemci, b, ad="Geciken Müşteri")
    for gun, tutar in ((95, "100"), (45, "200"), (10, "50")):
        t = (BUGUN - timedelta(days=gun)).isoformat()
        await _hareket(istemci, b, tur="gelir", tutar=tutar, cari_id=c["id"], tarih=t, vade_tarihi=t)
    await _hareket(istemci, b, tur="gelir", tutar="80", cari_id=c["id"], vade_tarihi=(BUGUN + timedelta(days=20)).isoformat())
    await _hareket(istemci, b, tur="tahsilat", tutar="150", cari_id=c["id"], hesap_id=kasa["id"])
    r = (await istemci.get(f"{M}/yaslandirma", headers=b)).json()
    satir = next(x for x in r["satirlar"] if x["cari_id"] == c["id"])
    assert satir["kovalar"] == {"vadesi_gelmemis": 8000, "0_30": 5000, "31_60": 15000, "61_90": 0, "90_ustu": 0}
    assert satir["acik"] == 28000 and satir["en_eski_gun"] == 45
    assert r["toplamlar"][0]["acik"] == 28000
    # Tedarikçi borcu yönü.
    t = await _cari(istemci, b, ad="Tedarikçi", tur="tedarikci")
    await _hareket(istemci, b, tur="gider", tutar="300", cari_id=t["id"], tarih="2026-06-01", vade_tarihi="2026-07-01")
    r = (await istemci.get(f"{M}/yaslandirma", params={"yon": "borc"}, headers=b)).json()
    assert next(x for x in r["satirlar"] if x["cari_id"] == t["id"])["kovalar"]["90_ustu"] == 30000  # 1 Tem → 5 Eki = 96 gün
    cari = (await istemci.get(f"{M}/cariler/{c['id']}", headers=b)).json()
    assert cari["yaslandirma_alacak"]["acik"] == 28000 and cari["bakiye"] == 28000
    ozet = (await istemci.get(f"{M}/ozet", headers=b)).json()
    assert ozet["gecikmis_alacak"] == [{"para_birimi": "TRY", "tutar": 20000}] and ozet["gecikmis_cari"] == 1


# ---------------------------------------------------------------------------
# Tekrar, bütçe
# ---------------------------------------------------------------------------
async def test_tekrarlayan_gider_tekil_uretim(istemci, yonetici_basligi, _ortam):
    m, b = await _musteri(istemci, yonetici_basligi, "tekrar")
    kasa = await _hesap(istemci, b, ad="Kasa")
    kira = await _kategori(istemci, b, "gider", "kira")
    t = await _post(istemci, f"{M}/tekrarlar", {"tur": "gider", "aciklama": "Dükkan kirası", "tutar": "15.000", "kdv_orani": 20,
                                                "periyot": "aylik", "baslangic": "2026-08-05", "hesap_id": kasa["id"],
                                                "kategori_id": kira["id"], "gecmisi_de": True}, b)
    # 5 Ağu, 5 Eyl, 5 Eki (bugün) üretildi; sonraki 5 Kas.
    assert t["sonraki"] == "2026-11-05" and t["son_uretilen"] == "2026-10-05"
    liste = (await istemci.get(f"{M}/hareketler", params={"kaynak": "tekrar"}, headers=b)).json()["items"]
    assert sorted(x["tarih"] for x in liste) == ["2026-08-05", "2026-09-05", "2026-10-05"]
    assert all(x["tutar"] == 1500000 and x["kdv_tutari"] == 250000 and x["tekrar_id"] == t["id"] for x in liste)
    # Yeniden eşitleme / aynı gün tekrar çağrı çift üretmez.
    for _ in range(2):
        assert (await _post(istemci, f"{M}/esitle", {}, b))["tekrar"] == 0
    # Geçmiş istenmezse ilk dönem bugünden sonra.
    t2 = await _post(istemci, f"{M}/tekrarlar", {"tur": "gider", "aciklama": "İnternet", "tutar": "500", "periyot": "aylik",
                                                 "baslangic": "2026-01-20", "hesap_id": kasa["id"]}, b)
    assert t2["sonraki"] == "2026-10-20" and t2["son_uretilen"] is None
    # Nakit akışı tahmini (3 ay): Kasım/Aralık/Ocak'ta kira + internet çıkışı.
    n = (await istemci.get(f"{M}/raporlar/nakit-akisi", headers=b)).json()["para_birimleri"][0]
    assert [x["ay"] for x in n["tahmin"]] == ["2026-11", "2026-12", "2027-01"]
    assert all(x["cikis"] == 1500000 + 50000 and x["tahmin"] for x in n["tahmin"])
    assert n["bu_ay_kalan"]["cikis"] == 50000  # 20 Ekim interneti
    assert n["gecmis"][-1]["ay"] == "2026-10" and n["gecmis"][-1]["cikis"] == 1500000
    assert n["tahmin"][0]["bakiye"] == n["gecmis"][-1]["bakiye"] - 50000 - 1550000
    # Bir ay sonra: yalnız yeni dönemler (kira 5 Kas, internet 20 Eki).
    _ortam["an"] = SIMDI + timedelta(days=31)
    r = await _post(istemci, f"{M}/esitle", {}, b)
    assert r["tekrar"] == 2
    tarihler = sorted(x["tarih"] for x in (await istemci.get(f"{M}/hareketler", params={"kaynak": "tekrar"}, headers=b)).json()["items"])
    assert tarihler == ["2026-08-05", "2026-09-05", "2026-10-05", "2026-10-20", "2026-11-05"]


async def test_butce_asim_uyarisi_bir_kez_olay(istemci, yonetici_basligi, db_oturumu, monkeypatch):
    from models.api_erisimi import WebhookTeslimatlari, WebhookUcNoktalari
    from models.muhasebe import MuhasebeButceAsimlari
    from services import otomasyon_kural, webhook
    from services.api_erisimi import gizli_sakla

    assert "muhasebe.butce_asildi" in webhook.OLAY_SOZLUGU and "muhasebe.butce_asildi" in otomasyon_kural.OLAY_SOZLUGU
    assert otomasyon_kural.olay_nesneleri("muhasebe.butce_asildi", False) == ("butce", "hesap", "kisi", "olay")
    monkeypatch.setattr(webhook, "ANLIK_TESLIMAT", False)
    uc = WebhookUcNoktalari(sahip_tur="ajans", hesap_email=None, url="https://kanca.ornek.com/muhasebe",
                            olaylar=json.dumps(["muhasebe.butce_asildi"]), aktif=True, gizli_anahtar=gizli_sakla("whsec_test"),
                            ardisik_hata=0, tum_musteriler=False)
    db_oturumu.add(uc)
    await db_oturumu.commit()
    webhook.onbellegi_temizle()
    try:
        yb = yonetici_basligi
        kasa = await _hesap(istemci, yb, Y, ad=f"Bütçe kasası {uuid.uuid4().hex[:4]}")
        kat = await _post(istemci, f"{Y}/kategoriler", {"tur": "gider", "ad": f"Reklam {uuid.uuid4().hex[:5]}"}, yb)
        assert (await istemci.put(f"{Y}/butceler", json={"kategori_id": kat["id"], "ay": "*", "tutar": "1.000"}, headers=yb)).status_code == 200
        await _hareket(istemci, yb, Y, tur="gider", tutar="850", hesap_id=kasa["id"], kategori_id=kat["id"])
        d = (await istemci.get(f"{Y}/butceler", params={"ay": "2026-10"}, headers=yb)).json()
        x = next(k for k in d["kalemler"] if k["kategori_id"] == kat["id"])
        assert x["durum"] == "yaklasti" and x["oran"] == 85.0 and x["kalan"] == 15000 and x["butce_kaynak"] == "her_ay"
        h = await _hareket(istemci, yb, Y, tur="gider", tutar="200", hesap_id=kasa["id"], kategori_id=kat["id"])
        assert h["butce_asimi"] == 1
        await _hareket(istemci, yb, Y, tur="gider", tutar="50", hesap_id=kasa["id"], kategori_id=kat["id"])
        x = next(k for k in (await istemci.get(f"{Y}/butceler", headers=yb)).json()["kalemler"] if k["kategori_id"] == kat["id"])
        assert x["durum"] == "asildi" and x["gerceklesen"] == 110000 and x["uyari_at"]
        izler = (await db_oturumu.execute(select(MuhasebeButceAsimlari).where(MuhasebeButceAsimlari.kategori_id == kat["id"]))).scalars().all()
        assert len(izler) == 1 and izler[0].ay == "2026-10" and izler[0].gerceklesen == 105000
        teslimat = [x for x in (await db_oturumu.execute(select(WebhookTeslimatlari).where(WebhookTeslimatlari.uc_id == uc.id))).scalars().all()
                    if json.loads(x.govde)["veri"]["kategori_id"] == kat["id"]]
        assert len(teslimat) == 1 and teslimat[0].tur == "muhasebe.butce_asildi"
        veri = json.loads(teslimat[0].govde)["veri"]
        assert veri["butce"] == 1000 and veri["gerceklesen"] == 1050 and veri["asim"] == 50 and veri["yuzde"] == 105
        # Ayın kendi bütçesi "her ay"ı ezer.
        assert (await istemci.put(f"{Y}/butceler", json={"kategori_id": kat["id"], "ay": "2026-10", "tutar": "5000"}, headers=yb)).status_code == 200
        x = next(k for k in (await istemci.get(f"{Y}/butceler", headers=yb)).json()["kalemler"] if k["kategori_id"] == kat["id"])
        assert x["butce"] == 500000 and x["butce_kaynak"] == "ay" and x["durum"] == "normal"
        from core.database import db_manager
        from services import otomasyon

        async with db_manager.async_session_maker() as db:
            b = await otomasyon.baglam_kur(db, "muhasebe.butce_asildi", veri, None, True)
        assert b["butce"]["kategori"] == kat["ad"] and b["butce"]["asim"] == 50 and b["butce"]["para_birimi"] == "TRY"
        # Gelir kategorisine bütçe yazılmaz.
        satis = await _kategori(istemci, yb, "gelir", "satis", Y)
        y = await istemci.put(f"{Y}/butceler", json={"kategori_id": satis["id"], "tutar": "1"}, headers=yb)
        assert y.status_code == 400 and _kod(y) == "kategori_turu_uyusmuyor"
    finally:
        uc.aktif = False
        await db_oturumu.commit()
        webhook.onbellegi_temizle()


# ---------------------------------------------------------------------------
# Otomatik yansıma
# ---------------------------------------------------------------------------
async def test_ayarlar_aktarim_dogrulama(istemci, yonetici_basligi):
    m, b = await _musteri(istemci, yonetici_basligi, "ayar")
    kasa = await _hesap(istemci, b, ad="Kasa")
    for govde, kod in (({"aktarim": {"fatura": {"acik": True}}}, "aktarim_kaynagi_gecersiz"),
                       ({"aktarim": {"odeme": {"acik": True}}}, "hedef_hesap_gerekli"),
                       ({"aktarim": {"hukuk": {"onay": "evet"}}}, "evet_hayir_gecersiz"),
                       ({"aktarim": {"pos": {"acik": True, "nakit_hesap_id": kasa["id"]}}}, "hedef_hesap_gerekli"),
                       ({"aktarim": {"hukuk": {"acik": True, "hesap_id": 999999}}}, "hesap_bulunamadi"),
                       ({"aktarim": {"hukuk": {"acik": True, "hesap_id": kasa["id"], "baslangic": "2020-01-01"}}}, "baslangic_cok_eski"),
                       ({"uyari_yuzde": 0}, "aralik_disinda")):
        y = await istemci.put(f"{M}/ayarlar", json=govde, headers=b)
        assert y.status_code == 400 and _kod(y) == kod, (govde, y.text)
    a = (await istemci.put(f"{M}/ayarlar", json={"aktarim": {"saha": {"acik": True}}, "firma_adi": "Ada Ltd"}, headers=b)).json()
    # Varsayılan onay: saha / hukuk öneri (onaylı), ödeme / POS otomatik.
    assert a["aktarim"]["saha"] == {"acik": True, "baslangic": BUGUN.isoformat(), "hesap_id": None, "onay": True} and a["firma_adi"] == "Ada Ltd"
    assert a["aktarim"]["pos"]["acik"] is False and a["aktarim"]["pos"]["onay"] is False and a["aktarim"]["odeme"]["onay"] is False
    assert a["aktarim"]["hukuk"]["onay"] is True and "cevrimici_hesap_id" in a["aktarim"]["odeme"]
    y = await istemci.put(f"{Y}/ayarlar", json={"aktarim": {"pos": {"acik": True}}}, headers=yonetici_basligi)
    assert y.status_code == 400 and _kod(y) == "aktarim_kaynagi_gecersiz"
    # Aktarımda kullanılan hesap silinmez.
    await istemci.put(f"{M}/ayarlar", json={"aktarim": {"hukuk": {"acik": True, "hesap_id": kasa["id"]}}}, headers=b)
    y = await istemci.delete(f"{M}/hesaplar/{kasa['id']}", headers=b)
    assert y.status_code == 409 and _kod(y) == "hesap_kullaniliyor"


async def test_ajans_odenen_fatura_yansimasi_tekil_ve_ters(istemci, yonetici_basligi, db_oturumu):
    """Ajans: ödeme kaydı olan tahsilat OTOMATİK (havale → banka, elden → kasa, Lemon Squeezy → sanal POS); ödeme
    kaydı olmadan "ödendi" işaretlenen fatura ÖNERİ (onaylanınca deftere). Kaynak iptal / ödeme gelince ters kayıt."""
    from models.invoices import Invoices
    from models.payments import Payments

    yb = yonetici_basligi
    banka = await _hesap(istemci, yb, Y, tur="banka", ad=f"Ajans bankası {uuid.uuid4().hex[:4]}")
    kasa = await _hesap(istemci, yb, Y, ad=f"Ajans kasası {uuid.uuid4().hex[:4]}")
    sanal = await _hesap(istemci, yb, Y, tur="pos", ad=f"Lemon Squeezy {uuid.uuid4().hex[:4]}", banka_adi="Lemon Squeezy")
    musteri = _e("fatura")
    f1 = Invoices(invoice_no=f"F-{uuid.uuid4().hex[:6]}", client_email=musteri, client_name="Ada Kafe", amount=1200.0, kdv_toplam=200.0,
                  currency="TRY", status="paid", kalemler=json.dumps([{"kdv_orani": 20}]))
    f2 = Invoices(invoice_no=f"F-{uuid.uuid4().hex[:6]}", client_email=musteri, client_name="Ada Kafe", amount=600.0, currency="TRY",
                  status="paid")
    f3 = Invoices(invoice_no=f"F-{uuid.uuid4().hex[:6]}", client_email=musteri, client_name="Ada Kafe", amount=300.0, currency="TRY",
                  status="paid")
    db_oturumu.add_all([f1, f2, f3])
    await db_oturumu.commit()
    # Fatura müşteri hesabına bağlı cari (fatura e-postası bağlantı adayıdır).
    cari = await _cari(istemci, yb, Y, ad="Ada Kafe", bagli_tur="musteri_hesabi", bagli_id=musteri)
    p1 = Payments(invoice_id=f1.id, invoice_no=f1.invoice_no, client_email=musteri, saglayici="havale", tutar=1200.0, para_birimi="TRY",
                  durum="odendi", odeme_tarihi=BUGUN.isoformat())
    p2 = Payments(invoice_id=f1.id, invoice_no=f1.invoice_no, client_email=musteri, saglayici="elden", tutar=0.5, para_birimi="USD",
                  durum="odendi", odeme_tarihi=BUGUN.isoformat())
    p3 = Payments(invoice_id=f3.id, invoice_no=f3.invoice_no, client_email=musteri, saglayici="lemonsqueezy", tutar=300.0, para_birimi="TRY",
                  durum="odendi", odendi_at=SIMDI - timedelta(hours=1))
    db_oturumu.add_all([p1, p2, p3])
    await db_oturumu.commit()
    await istemci.put(f"{Y}/ayarlar", json={"aktarim": {"odeme": {"acik": True, "banka_hesap_id": banka["id"], "nakit_hesap_id": kasa["id"],
                                                                     "cevrimici_hesap_id": sanal["id"]}}}, headers=yb)
    try:
        r = await _post(istemci, f"{Y}/esitle", {}, yb)
        assert r["atlanan"].get("para_birimi", 0) >= 1  # USD ödeme TRY kasasına yazılmaz

        async def benim():
            items = (await istemci.get(f"{Y}/hareketler", params={"cari_id": cari["id"], "adet": 200}, headers=yb)).json()["items"]
            return [x for x in items if x["belge_no"] in (f1.invoice_no, f2.invoice_no, f3.invoice_no)]

        async def onerilerim(durum="bekliyor"):
            items = (await istemci.get(f"{Y}/oneriler", params={"durum": durum}, headers=yb)).json()["items"]
            return [x for x in items if x["belge_no"] in (f1.invoice_no, f2.invoice_no, f3.invoice_no)]

        x = await benim()
        odeme = sorted((h for h in x if h["kaynak"] == "odeme"), key=lambda h: h["tutar"])
        assert [h["kaynak"] for h in x if h["kaynak"] != "odeme"] == []  # fatura deftere DEĞİL, öneriye
        assert [(h["tutar"], h["hesap_id"]) for h in odeme] == [(30000, sanal["id"]), (120000, banka["id"])]
        assert odeme[1]["kdv_tutari"] == 20000 and odeme[1]["kdv_orani"] == 20
        assert odeme[1]["tur"] == "gelir" and odeme[1]["otomatik"] and not odeme[1]["duzenlenebilir"]
        oneri = await onerilerim()
        assert [(o["kaynak"], o["tutar"], o["tur"], o["hesap_id"], o["cari"]) for o in oneri] == [("fatura", 60000, "gelir", banka["id"], "Ada Kafe")]
        assert (await istemci.get(f"{Y}/meta", headers=yb)).json()["oneri_sayisi"] >= 1
        # Tekillik: tekrar eşitleme yeni kayıt / öneri üretmez.
        r = await _post(istemci, f"{Y}/esitle", {}, yb)
        assert len(await benim()) == 2 and len(await onerilerim()) == 1
        # Öneri onaylanır → deftere (aynı kaynak kimliği); ikinci onay 404, eşitleme yeniden önermez.
        h = await _post(istemci, f"{Y}/oneriler/{oneri[0]['id']}/onayla", {}, yb)
        assert h["kaynak"] == "fatura" and h["tutar"] == 60000 and h["hesap_id"] == banka["id"] and h["otomatik"]
        assert (await istemci.post(f"{Y}/oneriler/{oneri[0]['id']}/onayla", json={}, headers=yb)).status_code == 404
        await _post(istemci, f"{Y}/esitle", {}, yb)
        assert await onerilerim() == [] and len([h for h in await benim() if h["kaynak"] == "fatura"]) == 1
        # Otomatik kayıt elle silinmez / düzenlenmez.
        y = await istemci.delete(f"{Y}/hareketler/{odeme[1]['id']}", headers=yb)
        assert y.status_code == 409 and _kod(y) == "otomatik_kayit"
        # İkinci faturaya ödeme gelir → (onaylanmış) fatura yansıması ters, ödeme yansıması (çift sayım yok).
        db_oturumu.add(Payments(invoice_id=f2.id, invoice_no=f2.invoice_no, client_email=musteri, saglayici="elden", tutar=600.0,
                                para_birimi="TRY", durum="odendi", odeme_tarihi=BUGUN.isoformat()))
        # İlk ödeme iptal → ters kayıt.
        p1.durum = "iptal"
        await db_oturumu.commit()
        r = await _post(istemci, f"{Y}/esitle", {}, yb)
        assert r["ters"] >= 2
        x = await benim()
        ters = [h for h in x if h["ters"]]
        assert {(h["kaynak"], h["tutar"]) for h in ters} == {("odeme", -120000), ("fatura", -60000)}
        assert all(h["kdv_tutari"] <= 0 for h in ters)
        net = sum(h["tutar"] for h in x)
        assert net == 90000  # f2'nin elden ödemesi + f3'ün Lemon Squeezy ödemesi
        elden = [h for h in x if h["kaynak"] == "odeme" and not h["ters"] and not h["ters_edildi"] and h["belge_no"] == f2.invoice_no]
        assert len(elden) == 1 and elden[0]["hesap_id"] == kasa["id"]
        await _post(istemci, f"{Y}/esitle", {}, yb)
        assert len(await benim()) == len(x)
        e = (await istemci.get(f"{Y}/cariler/{cari['id']}/ekstre", params={"bas": "2026-10-01", "bit": "2026-10-31"}, headers=yb)).json()
        assert e["kapanis"] == 0  # peşin tahsilatlar cariyi etkilemez (borç = alacak)
    finally:
        await istemci.put(f"{Y}/ayarlar", json={"aktarim": {"odeme": {"acik": False}}}, headers=yb)


async def _pos_oturumu(db, hesap, nakit, kart, oran=20, iade_nakit=0):
    from models.stok_pos import PosIadeler, PosKasaOturumlari, PosSatisKalemleri, PosSatislari

    an = SIMDI - timedelta(hours=1)
    o = PosKasaOturumlari(hesap_email=hesap, konum_id=1, durum="kapali", acik_anahtar=None, acan=hesap, acilis_at=an - timedelta(hours=8),
                          acilis_nakit=0, kapatan=hesap, kapanis_at=an)
    db.add(o)
    await db.flush()
    for i, (tutar, nk, kr) in enumerate(((nakit, nakit, 0), (kart, 0, kart))):
        if not tutar:
            continue
        x = PosSatislari(hesap_email=hesap, no=f"S-{uuid.uuid4().hex[:8]}", konum_id=1, oturum_id=o.id, kasiyer=hesap, durum="tamamlandi",
                         ara_toplam=tutar, toplam=tutar, kdv_toplam=0, odeme_turu="nakit" if nk else "kart", nakit=nk, kart=kr,
                         para_birimi="TRY", zaman=an)
        db.add(x)
        await db.flush()
        db.add(PosSatisKalemleri(satis_id=x.id, hesap_email=hesap, urun_id=1, ad="Kahve", adet=1000, birim_fiyat=tutar, tutar=tutar,
                                 kdv_orani=oran, kdv=0))
    if iade_nakit:
        db.add(PosIadeler(hesap_email=hesap, satis_id=0, oturum_id=o.id, tur="iade", tutar=iade_nakit, odeme_turu="nakit", kalemler="[]"))
    await db.commit()
    return o


async def test_pos_gun_sonu_nakit_kart_ayri_hesaba(istemci, yonetici_basligi, db_oturumu):
    m, b = await _musteri(istemci, yonetici_basligi, "pos")
    kasa = await _hesap(istemci, b, ad="Kasa")
    banka = await _hesap(istemci, b, tur="banka", ad="POS bankası")
    o = await _pos_oturumu(db_oturumu, m, nakit=12000, kart=6000)
    await istemci.put(f"{M}/ayarlar", json={"aktarim": {"pos": {"acik": True, "nakit_hesap_id": kasa["id"], "kart_hesap_id": banka["id"]}}},
                      headers=b)
    # Modül kapalıysa yansıma yok (kayıt silinmez/ters çevrilmez — yalnız yeni üretilmez).
    r = await _post(istemci, f"{M}/esitle", {}, b)
    assert r["olusturulan"] == 0 and r["atlanan"].get("modul_kapali") == 1
    await _modul(istemci, yonetici_basligi, m, "stok_pos")
    r = await _post(istemci, f"{M}/esitle", {}, b)
    assert r["olusturulan"] == 2
    x = (await istemci.get(f"{M}/hareketler", params={"kaynak": "pos"}, headers=b)).json()["items"]
    by = {h["hesap_id"]: h for h in x}
    # KDV dökümü (oturum özeti) ödeme türüne oranla bölünür: toplam KDV 18.000 × 20/120 = 3.000.
    assert by[kasa["id"]]["tutar"] == 12000 and by[kasa["id"]]["kdv_tutari"] == 2000 and by[kasa["id"]]["kategori"]["anahtar"] == "satis"
    assert by[banka["id"]]["tutar"] == 6000 and by[banka["id"]]["kdv_tutari"] == 1000 and by[banka["id"]]["belge_no"] == f"Z-{o.id}"
    assert (await _post(istemci, f"{M}/esitle", {}, b))["olusturulan"] == 0
    bak = {h["id"]: h["bakiye"] for h in (await istemci.get(f"{M}/hesaplar", headers=b)).json()["items"]}
    assert bak[kasa["id"]] == 12000 and bak[banka["id"]] == 6000
    # İade fazlası olan oturum (nakit net eksi) → gider.
    await _pos_oturumu(db_oturumu, m, nakit=1000, kart=0, iade_nakit=3000)
    await _post(istemci, f"{M}/esitle", {}, b)
    gider = [h for h in (await istemci.get(f"{M}/hareketler", params={"kaynak": "pos", "tur": "gider"}, headers=b)).json()["items"]]
    assert len(gider) == 1 and gider[0]["tutar"] == 2000 and gider[0]["hesap_id"] == kasa["id"]


async def test_hukuk_ve_saha_yansimasi_ters_kayit(istemci, yonetici_basligi, db_oturumu):
    from models.hukuk import HukukMasraflari
    from models.saha_servisi import SahaAyarlari, SahaIsEmirleri, SahaMalzemeKullanimi, SahaMusterileri

    m, b = await _musteri(istemci, yonetici_basligi, "hukuksaha")
    for anahtar in ("hukuk_burosu", "saha_servisi"):
        await _modul(istemci, yonetici_basligi, m, anahtar)
    kasa = await _hesap(istemci, b, ad="Kasa")
    m1 = HukukMasraflari(hesap_email=m, dosya_id=1, tur="harc", tutar_kurus=45000, para_birimi="TRY", tarih=BUGUN, aciklama="Gizli dosya")
    m2 = HukukMasraflari(hesap_email=m, dosya_id=1, tur="tebligat", tutar_kurus=9000, para_birimi="TRY", tarih=BUGUN, avanstan=True)
    m3 = HukukMasraflari(hesap_email=m, dosya_id=1, tur="yol", tutar_kurus=1000, para_birimi="TRY", tarih=BUGUN - timedelta(days=30))
    sm = SahaMusterileri(hesap_email=m, tur="kurumsal", ad="Ahmet Yıldız", firma="Yıldız Otel")
    db_oturumu.add_all([m1, m2, m3, sm, SahaAyarlari(hesap_email=m, kdv_orani=20, para_birimi="TRY")])
    await db_oturumu.commit()
    ie = SahaIsEmirleri(hesap_email=m, no="IE-1", uid=uuid.uuid4().hex, baslik="Klima bakımı", musteri_id=sm.id, durum="tamamlandi",
                        iscilik_ucreti=50000, bitir_at=SIMDI - timedelta(hours=2))
    db_oturumu.add(ie)
    await db_oturumu.commit()
    db_oturumu.add(SahaMalzemeKullanimi(is_emri_id=ie.id, hesap_email=m, ad="Filtre", miktar=2.0, birim_fiyat=12500))
    await db_oturumu.commit()
    # Bu test OTOMATİK yolu sınar (onay kapalı); varsayılan onaylı yol `test_oneri_*`.
    await istemci.put(f"{M}/ayarlar", json={"aktarim": {"hukuk": {"acik": True, "hesap_id": kasa["id"], "onay": False},
                                                         "saha": {"acik": True, "onay": False}}}, headers=b)
    r = await _post(istemci, f"{M}/esitle", {}, b)
    assert r["olusturulan"] == 2 and r["oneri"] == 0, r
    hukuk = (await istemci.get(f"{M}/hareketler", params={"kaynak": "hukuk"}, headers=b)).json()["items"]
    # Avanstan karşılanan ve başlangıçtan eski masraf alınmaz; açıklama genel (dosya bilgisi taşınmaz).
    assert len(hukuk) == 1 and hukuk[0]["tutar"] == 45000 and hukuk[0]["aciklama"] == "Hukuk masrafı (harç)"
    assert hukuk[0]["kategori"]["anahtar"] == "dava_masraf" and "Gizli" not in json.dumps(hukuk)
    saha = (await istemci.get(f"{M}/hareketler", params={"kaynak": "saha"}, headers=b)).json()["items"]
    # (500,00 işçilik + 2 × 125,00 malzeme) = 750,00 + %20 KDV 150,00 = 900,00; hesap yok → saha müşterisinin carisine vadeli.
    assert len(saha) == 1 and saha[0]["tutar"] == 90000 and saha[0]["kdv_tutari"] == 15000 and saha[0]["hesap_id"] is None
    assert saha[0]["cari"] == "Yıldız Otel" and saha[0]["vade_tarihi"] == BUGUN.isoformat()
    cariler = (await istemci.get(f"{M}/cariler", headers=b)).json()["items"]
    assert [(c["ad"], c["bagli_tur"], c["bakiye"]) for c in cariler] == [("Yıldız Otel", "saha_musteri", 90000)]
    # Kaynak silinir / iş yeniden açılır → ters kayıt (eksi tutar); cari bakiyesi sıfırlanır.
    await db_oturumu.delete(m1)
    ie.durum = "iste"
    await db_oturumu.commit()
    r = await _post(istemci, f"{M}/esitle", {}, b)
    assert r["ters"] == 2 and r["olusturulan"] == 0
    hukuk = (await istemci.get(f"{M}/hareketler", params={"kaynak": "hukuk"}, headers=b)).json()["items"]
    assert sorted(x["tutar"] for x in hukuk) == [-45000, 45000] and any(x["ters_edildi"] for x in hukuk)
    assert (await istemci.get(f"{M}/cariler", headers=b)).json()["items"][0]["bakiye"] == 0
    bak = {h["id"]: h["bakiye"] for h in (await istemci.get(f"{M}/hesaplar", headers=b)).json()["items"]}
    assert bak[kasa["id"]] == 0
    # İş yeniden tamamlanır, tutar değişti → yeni sürüm (çift sayım yok).
    ie.durum = "tamamlandi"
    ie.iscilik_ucreti = 60000
    await db_oturumu.commit()
    r = await _post(istemci, f"{M}/esitle", {}, b)
    assert r["olusturulan"] == 1
    saha = (await istemci.get(f"{M}/hareketler", params={"kaynak": "saha"}, headers=b)).json()["items"]
    assert sum(x["tutar"] for x in saha) == 102000 and len(saha) == 3


# ---------------------------------------------------------------------------
# CSV içe / dışa aktarma, PDF
# ---------------------------------------------------------------------------
async def test_csv_ice_aktarma_esleme_hatali_satir_ve_tekrar(istemci, yonetici_basligi):
    m, b = await _musteri(istemci, yonetici_basligi, "csv")
    banka = await _hesap(istemci, b, tur="banka", ad="Banka")
    kira = await _kategori(istemci, b, "gider", "kira")
    csv = ("Tarih;Açıklama;Tutar;Bakiye\n"
           "01.10.2026;KİRA EKİM;-15.000,00;1.000,00\n"
           "02.10.2026;EFT GELEN ADA KAFE;2.500,50;3.500,50\n"
           "31.02.2026;HATALI TARİH;100,00;0\n"
           "03.10.2026;TUTARSIZ;;0\n"
           "04.10.2026;KOMİSYON;-12,34;3.488,16\n")
    o = await _post(istemci, f"{M}/ice-aktar/onizle", {"csv": csv}, b)
    assert o["basliklar"] == ["Tarih", "Açıklama", "Tutar", "Bakiye"] and o["satir_sayisi"] == 5
    assert o["esleme"]["tarih"] == 0 and o["esleme"]["aciklama"] == 1 and o["esleme"]["tutar"] == 2
    govde = {"csv": csv, "hesap_id": banka["id"], "esleme": o["esleme"], "tarih_bicimi": "gg.aa.yyyy", "ondalik": ",",
             "gider_kategori_id": kira["id"]}
    d = await _post(istemci, f"{M}/ice-aktar", {**govde, "dene": True}, b)
    assert d["dene"] is True and d["eklenen"] == 3 and d["hata_sayisi"] == 2
    assert (await istemci.get(f"{M}/hareketler", headers=b)).json()["items"] == []
    r = await _post(istemci, f"{M}/ice-aktar", govde, b)
    assert (r["eklenen"], r["tekrar"], r["hata_sayisi"]) == (3, 0, 2)
    assert [(h["satir"], h["kod"]) for h in r["hatalar"]] == [(4, "tarih_gecersiz"), (5, "zorunlu")]
    items = (await istemci.get(f"{M}/hareketler", headers=b)).json()["items"]
    assert sorted((x["tur"], x["tutar"]) for x in items) == [("gelir", 250050), ("gider", 1234), ("gider", 1500000)]
    assert all(x["kaynak"] == "csv" and x["hesap_id"] == banka["id"] for x in items)
    assert next(x for x in items if x["tutar"] == 1500000)["kategori_id"] == kira["id"]
    # Aynı ekstre ikinci kez: atlanır.
    r = await _post(istemci, f"{M}/ice-aktar", govde, b)
    assert (r["eklenen"], r["tekrar"]) == (0, 3)
    # Son eşleme hatırlanır; ayrı giriş/çıkış sütunlu biçim.
    csv2 = "Date,Description,Debit,Credit\n10/05/2026,Card fee,4.50,\n10/06/2026,Transfer in,,100.00\n"
    o2 = await _post(istemci, f"{M}/ice-aktar/onizle", {"csv": csv2}, b)
    assert o2["esleme"]["cikis"] == 2 and o2["esleme"]["giris"] == 3 and o2["esleme"]["tutar"] is None
    r = await _post(istemci, f"{M}/ice-aktar", {"csv": csv2, "hesap_id": banka["id"], "esleme": o2["esleme"], "tarih_bicimi": "aa/gg/yyyy",
                                                "ondalik": "."}, b)
    assert r["eklenen"] == 2 and r["hata_sayisi"] == 0
    items = (await istemci.get(f"{M}/hareketler", params={"bas": "2026-10-05"}, headers=b)).json()["items"]
    assert sorted((x["tarih"], x["tur"], x["tutar"]) for x in items) == [("2026-10-05", "gider", 450), ("2026-10-06", "gelir", 10000)]
    y = await istemci.post(f"{M}/ice-aktar", json={**govde, "esleme": {"aciklama": 1}}, headers=b)
    assert y.status_code == 400 and _kod(y) == "esleme_tarih_gerekli"


async def test_csv_pdf_disa_aktarma_ve_formul_kacisi(istemci, yonetici_basligi):
    m, b = await _musteri(istemci, yonetici_basligi, "disa")
    kasa = await _hesap(istemci, b, ad="Kasa")
    await _hareket(istemci, b, tur="gelir", tutar="1.234,56", kdv_orani=20, hesap_id=kasa["id"], aciklama="=HYPERLINK(x)",
                   etiketler=["proje"])
    await _hareket(istemci, b, tur="gider", tutar="100", hesap_id=kasa["id"], aciklama="Kahve", tarih="2026-09-01")
    y = await istemci.get(f"{M}/hareketler.csv", params={"bas": "2026-10-01"}, headers=b)
    assert y.status_code == 200 and y.text.startswith("﻿") and y.headers["content-type"].startswith("text/csv")
    satirlar = y.text.lstrip("﻿").strip().splitlines()
    assert satirlar[0].startswith("tarih;tur;tutar;para_birimi") and len(satirlar) == 2
    assert "1234,56;TRY;20;205,76" in satirlar[1] and ";'=HYPERLINK" in satirlar[1] and "proje" in satirlar[1]
    y = await istemci.get(f"{M}/hareketler.pdf", params={"dil": "en"}, headers=b)
    assert y.status_code == 200 and y.content[:4] == b"%PDF"
    from services.pdf_belge import pdf_metni

    metin = pdf_metni(y.content)
    assert "TRANSACTION LIST" in metin and "Kahve" in metin
    # Etiket ve arama süzgeci.
    assert len((await istemci.get(f"{M}/hareketler", params={"etiket": "proje"}, headers=b)).json()["items"]) == 1
    assert len((await istemci.get(f"{M}/hareketler", params={"ara": "kahve"}, headers=b)).json()["items"]) == 1
    r = (await istemci.get(f"{M}/hareketler", headers=b)).json()
    assert r["toplamlar"] == [{"para_birimi": "TRY", "gelir": 123456, "gider": 10000, "tahsilat": 0, "odeme": 0, "virman": 0, "net": 113456}]


async def test_raporlar_aylik_ve_kategori(istemci, yonetici_basligi):
    m, b = await _musteri(istemci, yonetici_basligi, "rapor")
    kasa = await _hesap(istemci, b, ad="Kasa")
    usd = await _hesap(istemci, b, tur="banka", ad="USD", para_birimi="USD")
    kira = await _kategori(istemci, b, "gider", "kira")
    pazarlama = await _kategori(istemci, b, "gider", "pazarlama")
    await _hareket(istemci, b, tur="gider", tutar="300", hesap_id=kasa["id"], kategori_id=kira["id"], tarih="2026-10-01")
    await _hareket(istemci, b, tur="gider", tutar="100", hesap_id=kasa["id"], kategori_id=pazarlama["id"], tarih="2026-10-02")
    await _hareket(istemci, b, tur="gelir", tutar="1000", hesap_id=kasa["id"], tarih="2026-03-15")
    await _hareket(istemci, b, tur="gelir", tutar="50", hesap_id=usd["id"], tarih="2026-10-03")
    r = (await istemci.get(f"{M}/raporlar/aylik", params={"yil": 2026}, headers=b)).json()
    pb = {p["para_birimi"]: p for p in r["para_birimleri"]}
    assert set(pb) == {"TRY", "USD"}  # para birimleri ayrı; dönüşüm yok
    assert pb["TRY"]["aylar"][2]["gelir"] == 100000 and pb["TRY"]["aylar"][9]["gider"] == 40000 and pb["TRY"]["net"] == 60000
    assert pb["USD"]["gelir"] == 5000
    k = (await istemci.get(f"{M}/raporlar/kategori", params={"bas": "2026-10-01", "bit": "2026-10-31"}, headers=b)).json()
    kalemler = k["para_birimleri"][0]["kalemler"]
    assert [(x["anahtar"], x["tutar"], x["oran"]) for x in kalemler] == [("kira", 30000, 75.0), ("pazarlama", 10000, 25.0)]
    y = await istemci.get(f"{M}/raporlar.csv", params={"tur": "aylik", "yil": 2026}, headers=b)
    assert "2026-03;TRY;1000,00;0,00;1000,00" in y.text
    assert (await istemci.get(f"{M}/raporlar.csv", params={"tur": "yok"}, headers=b)).status_code == 400


# ---------------------------------------------------------------------------
# Silme, çöp kutusu, ekler, kategoriler, bağlantı adayları
# ---------------------------------------------------------------------------
async def test_silme_cop_kutusu_ve_kullanimdakiler(istemci, yonetici_basligi, db_oturumu):
    from models.cop_kutusu import CopKutusu

    m, b = await _musteri(istemci, yonetici_basligi, "cop")
    kasa = await _hesap(istemci, b, ad="Kasa")
    bos = await _hesap(istemci, b, ad="Boş hesap")
    c = await _cari(istemci, b, ad="Silinecek")
    kat = await _post(istemci, f"{M}/kategoriler", {"tur": "gider", "ad": "Özel gider"}, b)
    y = await istemci.post(f"{M}/kategoriler", json={"tur": "gider", "ad": "Özel gider"}, headers=b)
    assert y.status_code == 409 and _kod(y) == "kategori_var"
    x = await _hareket(istemci, b, tur="gider", tutar="10", hesap_id=kasa["id"], kategori_id=kat["id"])
    for yol, kod in ((f"{M}/hesaplar/{kasa['id']}", "hesap_kullaniliyor"), (f"{M}/kategoriler/{kat['id']}", "kategori_kullaniliyor")):
        y = await istemci.delete(yol, headers=b)
        assert y.status_code == 409 and _kod(y) == kod
    ek = await istemci.post(f"{M}/hareketler/{x['id']}/ekler", files={"dosya": ("fis.txt", b"fis icerigi", "text/plain")}, headers=b)
    assert ek.status_code == 200, ek.text
    y = await istemci.get(f"{M}/ekler/{ek.json()['id']}", headers=b)
    assert y.status_code == 200 and y.content == b"fis icerigi"
    assert (await istemci.get(f"{M}/hareketler/{x['id']}", headers=b)).json()["ekler"][0]["ad"] == "fis.txt"
    assert (await istemci.delete(f"{M}/hareketler/{x['id']}", headers=b)).status_code == 200
    satirlar = (await db_oturumu.execute(select(CopKutusu).where(CopKutusu.sahip_email == m))).scalars().all()
    assert {"muhasebe_hareketleri", "muhasebe_ekleri"} <= {s_.tablo for s_ in satirlar}
    for yol in (f"{M}/hesaplar/{bos['id']}", f"{M}/cariler/{c['id']}", f"{M}/kategoriler/{kat['id']}"):
        assert (await istemci.delete(yol, headers=b)).status_code == 200, yol
    # Varsayılan kategori silinip geri yüklenir.
    kira = await _kategori(istemci, b, "gider", "kira")
    assert (await istemci.delete(f"{M}/kategoriler/{kira['id']}", headers=b)).status_code == 200
    assert (await _post(istemci, f"{M}/kategoriler/varsayilanlar", {}, b))["eklenen"] == 1
    # Ad değiştirilen varsayılan kategori "ad_degisti" olur (ön yüz çevirmez).
    pz = await _kategori(istemci, b, "gider", "pazarlama")
    y = await istemci.put(f"{M}/kategoriler/{pz['id']}", json={"ad": "Instagram reklamı"}, headers=b)
    assert y.json()["ad_degisti"] is True


async def test_baglanti_adaylari_izinle(istemci, yonetici_basligi, db_oturumu):
    from core.database import db_manager
    from models.hesap_uyeleri import HesapUyeleri
    from models.saha_servisi import SahaMusterileri
    from services import hesap_ekibi as he

    sahip, muhasebeci = _e("sahip"), _e("mh")
    await _modul(istemci, yonetici_basligi, sahip)
    db_oturumu.add(SahaMusterileri(hesap_email=sahip, ad="Saha Kişisi", firma="Saha Firma"))
    async with db_manager.async_session_maker() as db:
        db.add(HesapUyeleri(hesap_email=sahip, uye_email=muhasebeci, rol="uye", izinler=json.dumps(["muhasebe"]), durum="aktif",
                            olusturma=he.simdi()))
        await db.commit()
    await db_oturumu.commit()
    he.onbellegi_temizle()
    sahibin = (await istemci.get(f"{M}/cariler/baglanti-adaylari", params={"ara": "Saha"}, headers=_b(sahip))).json()["items"]
    assert [(x["tur"], x["ad"]) for x in sahibin] == [("saha_musteri", "Saha Firma")]
    # Yalnız `muhasebe` izni olan üye başka modülün kişi kayıtlarını görmez.
    assert (await istemci.get(f"{M}/cariler/baglanti-adaylari", params={"ara": "Saha"}, headers=_b(muhasebeci, sahip))).json()["items"] == []
    c = await _cari(istemci, _b(sahip), ad="Saha Firma", bagli_tur="saha_musteri", bagli_id=sahibin[0]["id"])
    y = await istemci.post(f"{M}/cariler", json={"ad": "İkinci", "bagli_tur": "saha_musteri", "bagli_id": sahibin[0]["id"]}, headers=_b(sahip))
    assert y.status_code == 409 and _kod(y) == "baglanti_kullaniliyor"
    y = await istemci.post(f"{M}/cariler", json={"ad": "Yanlış", "bagli_tur": "saha_musteri", "bagli_id": "999999"}, headers=_b(sahip))
    assert y.status_code == 400 and _kod(y) == "baglanti_gecersiz"
    assert (await istemci.get(f"{M}/cariler/{c['id']}", headers=_b(sahip))).json()["bagli"]["ad"] == "Saha Firma"
    # Stok tedarikçisi (stok izniyle) tedarikçi cariye bağlanır.
    from models.stok_pos import StokTedarikcileri

    db_oturumu.add(StokTedarikcileri(hesap_email=sahip, ad="Tedarik Kahve A.Ş.", yetkili="Can Yıldız"))
    await db_oturumu.commit()
    ted = (await istemci.get(f"{M}/cariler/baglanti-adaylari", params={"ara": "Tedarik"}, headers=_b(sahip))).json()["items"]
    assert [(x["tur"], x["ad"], x["ayrinti"]) for x in ted] == [("stok_tedarikci", "Tedarik Kahve A.Ş.", "Can Yıldız")]
    tc = await _cari(istemci, _b(sahip), ad="Tedarik Kahve", tur="tedarikci", bagli_tur="stok_tedarikci", bagli_id=ted[0]["id"])
    assert tc["bagli_tur"] == "stok_tedarikci"
    assert (await istemci.get(f"{M}/cariler/baglanti-adaylari", params={"ara": "Tedarik"}, headers=_b(muhasebeci, sahip))).json()["items"] == []


# ---------------------------------------------------------------------------
# Haftalık özet ve zamanlı iş
# ---------------------------------------------------------------------------
async def test_haftalik_ozet_yalniz_ajans_ve_zamanli_is(istemci, yonetici_basligi, db_oturumu):
    from services import haftalik_ozet as ho
    from services import zamanli

    assert "muhasebe_bakimi" in zamanli.GOREV_ADLARI
    yb = yonetici_basligi
    ad = f"Geciken Ajans Müşterisi {uuid.uuid4().hex[:5]}"
    c = await _cari(istemci, yb, Y, ad=ad)
    await _hareket(istemci, yb, Y, tur="gelir", tutar="750", cari_id=c["id"], tarih="2026-08-01", vade_tarihi="2026-08-15")
    m, b = await _musteri(istemci, yonetici_basligi, "ozet")
    mc = await _cari(istemci, b, ad=f"Müşteri {ad}")
    await _hareket(istemci, b, tur="gelir", tutar="750", cari_id=mc["id"], tarih="2026-08-01", vade_tarihi="2026-08-15")
    o = await ho.ozet_hazirla(db_oturumu, SIMDI)
    bolum = [x for x in o["bolumler"] if x["anahtar"] == "muhasebe"][0]
    assert bolum["sekme"] == "onMuhasebe" and bolum["ek"]["alacak"] >= 1
    tumu = bolum["ornekler"]
    assert any(s_["ad"] == ad and s_["tur"] == "cari_gecikme" and s_["gun"] == 51 and s_["tutar"] == 750 for s_ in tumu) or \
        bolum["sayi"] > len(tumu)
    assert not any(s_["ad"] == f"Müşteri {ad}" for s_ in tumu)
    assert "Ön muhasebe" in o["eposta"]["metin"]
    # Zamanlı iş: ayarı olan kapsamlar eşitlenir (hata vermez).
    r = await zamanli.GOREVLER[zamanli.GOREV_ADLARI.index("muhasebe_bakimi")].calistir(db_oturumu, True)
    assert r["hata"] == 0 and r["kapsam"] >= 1


# ---------------------------------------------------------------------------
# Öneriler (onaylı yansıma), müşterinin ajans faturaları, okur izni, gecikme olayı, bütçe bildirimi
# ---------------------------------------------------------------------------
async def test_oneri_hukuk_saha_onay_yoksay_geri_al(istemci, yonetici_basligi, db_oturumu):
    """Hukuk masrafı ve saha işi varsayılan ONAYLI: öneri olarak gelir; onay → deftere (aynı kaynak kimliği, iki kez
    sayılmaz), yok say → yeniden önerilmez (kaynak değişince yeniden açılır), kaynak gidince onaylanmış kayıt ters."""
    from models.hukuk import HukukMasraflari
    from models.saha_servisi import SahaAyarlari, SahaIsEmirleri, SahaMusterileri

    m, b = await _musteri(istemci, yonetici_basligi, "oneri")
    for anahtar in ("hukuk_burosu", "saha_servisi"):
        await _modul(istemci, yonetici_basligi, m, anahtar)
    kasa = await _hesap(istemci, b, ad="Kasa")
    banka = await _hesap(istemci, b, tur="banka", ad="Banka")
    m1 = HukukMasraflari(hesap_email=m, dosya_id=1, tur="harc", tutar_kurus=45000, para_birimi="TRY", tarih=BUGUN)
    m2 = HukukMasraflari(hesap_email=m, dosya_id=1, tur="yol", tutar_kurus=2000, para_birimi="TRY", tarih=BUGUN)
    sm = SahaMusterileri(hesap_email=m, tur="kurumsal", ad="Ayşe Kaya", firma="Kaya Market")
    db_oturumu.add_all([m1, m2, sm, SahaAyarlari(hesap_email=m, kdv_orani=20, para_birimi="TRY")])
    await db_oturumu.commit()
    ie = SahaIsEmirleri(hesap_email=m, no="IE-7", uid=uuid.uuid4().hex, baslik="Kombi bakımı", musteri_id=sm.id, durum="tamamlandi",
                        iscilik_ucreti=100000, bitir_at=SIMDI - timedelta(hours=3))
    db_oturumu.add(ie)
    await db_oturumu.commit()
    await istemci.put(f"{M}/ayarlar", json={"aktarim": {"hukuk": {"acik": True, "hesap_id": kasa["id"]}, "saha": {"acik": True}}}, headers=b)
    r = await _post(istemci, f"{M}/esitle", {}, b)
    assert (r["olusturulan"], r["oneri"], r["bekleyen_oneri"]) == (0, 3, 3), r
    assert (await istemci.get(f"{M}/hareketler", headers=b)).json()["items"] == []
    # Onaydan önce saha müşterisinin carisi AÇILMAZ (yok sayılan öneri boş kart bırakmasın).
    assert (await istemci.get(f"{M}/cariler", headers=b)).json()["items"] == []
    d = (await istemci.get(f"{M}/oneriler", headers=b)).json()
    assert d["sayilar"] == {"bekliyor": 3, "yoksayildi": 0}
    by = {(o["kaynak"], o["tutar"]): o for o in d["items"]}
    harc, yol, saha = by[("hukuk", 45000)], by[("hukuk", 2000)], by[("saha", 120000)]
    assert harc["tur"] == "gider" and harc["hesap_id"] == kasa["id"] and harc["kategori"]["anahtar"] == "dava_masraf"
    assert saha["cari"] == "Kaya Market" and saha["hesap_id"] is None and saha["kdv_tutari"] == 20000 and saha["vade_tarihi"] == BUGUN.isoformat()
    assert (await _post(istemci, f"{M}/esitle", {}, b))["oneri"] == 0  # aynı öneri yinelenmez
    # Onay: başka hesap + kategori seçilebilir; para birimi uymayan hesap reddedilir.
    usd = await _hesap(istemci, b, ad="USD kasa", para_birimi="USD")
    y = await istemci.post(f"{M}/oneriler/{harc['id']}/onayla", json={"hesap_id": usd["id"]}, headers=b)
    assert y.status_code == 400 and _kod(y) == "para_birimi_uyusmuyor"
    kira = await _kategori(istemci, b, "gider", "kira")
    h = await _post(istemci, f"{M}/oneriler/{harc['id']}/onayla", {"hesap_id": banka["id"], "kategori_id": kira["id"]}, b)
    assert (h["kaynak"], h["tutar"], h["hesap_id"], h["kategori_id"], h["otomatik"]) == ("hukuk", 45000, banka["id"], kira["id"], True)
    # Yok say: deftere yazılmaz, yeniden önerilmez; kaynak değişince (tutar) yeniden açılır.
    assert (await _post(istemci, f"{M}/oneriler/{yol['id']}/yoksay", {}, b))["bekleyen"] == 1
    await _post(istemci, f"{M}/esitle", {}, b)
    d = (await istemci.get(f"{M}/oneriler", params={"durum": "yoksayildi"}, headers=b)).json()
    assert [o["id"] for o in d["items"]] == [yol["id"]] and d["sayilar"]["bekliyor"] == 1
    m2.tutar_kurus = 2500
    await db_oturumu.commit()
    assert (await _post(istemci, f"{M}/esitle", {}, b))["oneri"] == 1
    d = (await istemci.get(f"{M}/oneriler", headers=b)).json()
    assert sorted(o["tutar"] for o in d["items"]) == [2500, 120000] and d["sayilar"]["yoksayildi"] == 0
    await _post(istemci, f"{M}/oneriler/{yol['id']}/yoksay", {}, b)
    assert (await _post(istemci, f"{M}/oneriler/{yol['id']}/geri-al", {}, b))["bekleyen"] == 2
    # Toplu onay: saha önerisi cariyi ONAYDA açar (vadeli alacak); bilinmeyen kimlik raporlanır.
    t = await _post(istemci, f"{M}/oneriler/toplu", {"islem": "onayla", "idler": [saha["id"], yol["id"], 999999]}, b)
    assert t["tamam"] == 2 and t["hatalar"] == [{"id": 999999, "kod": "bulunamadi"}] and t["bekleyen"] == 0
    cariler = (await istemci.get(f"{M}/cariler", headers=b)).json()["items"]
    assert [(c["ad"], c["bagli_tur"], c["bakiye"]) for c in cariler] == [("Kaya Market", "saha_musteri", 120000)]
    hs = (await istemci.get(f"{M}/hareketler", headers=b)).json()["items"]
    assert sorted((x["kaynak"], x["tutar"]) for x in hs) == [("hukuk", 2500), ("hukuk", 45000), ("saha", 120000)]
    # İki kez sayılmaz: eşitleme onaylanmışları yeniden önermez / yazmaz.
    r = await _post(istemci, f"{M}/esitle", {}, b)
    assert (r["olusturulan"], r["oneri"], r["ters"]) == (0, 0, 0)
    # Onaylanmış kaydın kaynağı silinince / değişince TERS kayıt (otomatik); yeni sürüm yine öneri.
    await db_oturumu.delete(m1)
    ie.iscilik_ucreti = 110000
    await db_oturumu.commit()
    r = await _post(istemci, f"{M}/esitle", {}, b)
    assert (r["ters"], r["oneri"], r["olusturulan"]) == (2, 1, 0), r
    assert sum(x["tutar"] for x in (await istemci.get(f"{M}/hareketler", params={"kaynak": "hukuk"}, headers=b)).json()["items"]) == 2500
    # Aktarım kapatılınca bekleyen öneriler kalkar (defterdekilere dokunulmaz).
    await istemci.put(f"{M}/ayarlar", json={"aktarim": {"saha": {"acik": False}}}, headers=b)
    await _post(istemci, f"{M}/esitle", {}, b)
    assert (await istemci.get(f"{M}/oneriler", headers=b)).json()["sayilar"] == {"bekliyor": 0, "yoksayildi": 0}
    assert (await istemci.post(f"{M}/oneriler/{saha['id']}/onayla", json={}, headers=b)).status_code == 404
    # Başka hesap öneriye erişemez.
    _, bb = await _musteri(istemci, yonetici_basligi, "baskasi")
    y = await istemci.post(f"{M}/oneriler/{yol['id']}/yoksay", json={}, headers=bb)
    assert y.status_code == 404


async def test_musteri_ajansa_odedigi_faturalar_gider(istemci, yonetici_basligi, db_oturumu):
    """Müşteri tarafı `odeme`: ajansa ödediği faturalar GİDER (Shopier → kart hesabı, havale → banka), iade GELİR;
    ödeme kaydı olmadan "ödendi" fatura öneri; başka müşterinin ödemeleri gelmez."""
    from models.invoices import Invoices
    from models.payments import Payments

    m, b = await _musteri(istemci, yonetici_basligi, "ajansfat")
    baska = _e("baska")
    banka = await _hesap(istemci, b, tur="banka", ad="Banka")
    kart = await _hesap(istemci, b, tur="kredi_karti", ad="Şirket kartı", son4="4242")
    f1 = Invoices(invoice_no=f"A-{uuid.uuid4().hex[:6]}", client_email=m, client_name="Müşteri", amount=1200.0, kdv_toplam=200.0,
                  currency="TRY", status="paid", kalemler=json.dumps([{"kdv_orani": 20}]))
    f2 = Invoices(invoice_no=f"A-{uuid.uuid4().hex[:6]}", client_email=m, client_name="Müşteri", amount=500.0, currency="TRY", status="paid")
    fb = Invoices(invoice_no=f"A-{uuid.uuid4().hex[:6]}", client_email=baska, client_name="Başka", amount=999.0, currency="TRY", status="paid")
    db_oturumu.add_all([f1, f2, fb])
    await db_oturumu.commit()
    db_oturumu.add_all([
        Payments(invoice_id=f1.id, invoice_no=f1.invoice_no, client_email=m, saglayici="shopier", tutar=1200.0, para_birimi="TRY",
                 durum="odendi", odendi_at=SIMDI - timedelta(hours=2)),
        Payments(invoice_id=f1.id, invoice_no=f1.invoice_no, client_email=m.upper(), saglayici="havale", tutar=100.0, para_birimi="TRY",
                 durum="iade", odeme_tarihi=BUGUN.isoformat()),
        Payments(invoice_id=fb.id, invoice_no=fb.invoice_no, client_email=baska, saglayici="havale", tutar=999.0, para_birimi="TRY",
                 durum="odendi", odeme_tarihi=BUGUN.isoformat()),
    ])
    await db_oturumu.commit()
    y = await istemci.put(f"{M}/ayarlar", json={"aktarim": {"odeme": {"acik": True, "banka_hesap_id": banka["id"],
                                                                       "cevrimici_hesap_id": kart["id"]}}}, headers=b)
    assert y.status_code == 200, y.text
    r = await _post(istemci, f"{M}/esitle", {}, b)
    assert (r["olusturulan"], r["oneri"]) == (2, 1), r
    x = {h["tutar"]: h for h in (await istemci.get(f"{M}/hareketler", params={"kaynak": "odeme"}, headers=b)).json()["items"]}
    assert set(x) == {120000, 10000}
    assert (x[120000]["tur"], x[120000]["hesap_id"], x[120000]["kdv_tutari"], x[120000]["kategori"]["anahtar"]) == ("gider", kart["id"], 20000, "yazilim")
    assert (x[10000]["tur"], x[10000]["hesap_id"], x[10000]["kategori"]["anahtar"]) == ("gelir", banka["id"], "diger_gelir")
    o = (await istemci.get(f"{M}/oneriler", headers=b)).json()["items"]
    assert [(i["kaynak"], i["tur"], i["tutar"], i["belge_no"]) for i in o] == [("fatura", "gider", 50000, f2.invoice_no)]
    bak = {h["id"]: h["bakiye"] for h in (await istemci.get(f"{M}/hesaplar", headers=b)).json()["items"]}
    assert bak[kart["id"]] == -120000 and bak[banka["id"]] == 10000
    # KDV özeti: ajans faturasının KDV'si indirilecek KDV'ye girer.
    kdv = (await istemci.get(f"{M}/raporlar/kdv", params={"yil": 2026}, headers=b)).json()["para_birimleri"][0]
    assert kdv["indirilecek"] == 20000


async def test_muhasebe_okur_yalniz_rapor(istemci, yonetici_basligi):
    """`muhasebe_okur` (örn. mali müşavir): özet / bütçe / yaşlandırma / raporlar okunur; hareket, cari, hesap ayrıntısı,
    öneriler ve her yazma 403 `hesap_izni_yok`."""
    from core.database import db_manager
    from models.hesap_uyeleri import HesapUyeleri
    from services import hesap_ekibi as he

    sahip, okur = _e("sahip"), _e("musavir")
    await _modul(istemci, yonetici_basligi, sahip)
    async with db_manager.async_session_maker() as db:
        db.add(HesapUyeleri(hesap_email=sahip, uye_email=okur, rol="uye", izinler=json.dumps(["muhasebe_okur"]), durum="aktif",
                            olusturma=he.simdi()))
        await db.commit()
    he.onbellegi_temizle()
    bs, bo = _b(sahip), _b(okur, sahip)
    kasa = await _hesap(istemci, bs, ad="Kasa")
    c = await _cari(istemci, bs, ad="Gizli Cari")
    await _hareket(istemci, bs, tur="gelir", tutar="100", hesap_id=kasa["id"], aciklama="Ayrıntı")
    meta = (await istemci.get(f"{M}/meta", headers=bo)).json()
    assert meta["okur"] is True and meta["salt_okunur"] is True
    o = (await istemci.get(f"{M}/ozet", headers=bo)).json()
    assert o["son_hareketler"] == [] and o["bakiyeler"] == [{"para_birimi": "TRY", "bakiye": 10000}] and "Ayrıntı" not in json.dumps(o)
    for yol in ("/raporlar/aylik", "/raporlar/kategori", "/raporlar/kar-zarar", "/raporlar/nakit-akisi", "/raporlar/kdv", "/raporlar.csv?tur=aylik", "/butceler",
                "/yaslandirma"):
        assert (await istemci.get(f"{M}{yol}", headers=bo)).status_code == 200, yol
    for yontem, yol in (("GET", "/hareketler"), ("GET", f"/cariler/{c['id']}"), ("GET", "/cariler"), ("GET", "/hesaplar"),
                        ("GET", "/oneriler"), ("GET", "/hareketler.csv"), ("GET", f"/cariler/{c['id']}/ekstre.pdf"),
                        ("POST", "/hesaplar"), ("PUT", "/ayarlar"), ("POST", "/esitle"), ("PUT", "/butceler")):
        y = await istemci.request(yontem, f"{M}{yol}", json=None if yontem == "GET" else {}, headers=bo)
        assert y.status_code == 403 and _kod(y) == "hesap_izni_yok", (yol, y.status_code, y.text)
    assert (await istemci.get(f"{M}/meta", headers=bs)).json()["okur"] is False


async def test_alacak_gecikti_esik_basina_bir_kez(istemci, yonetici_basligi, db_oturumu, _ortam):
    """Vadesi geçen açık alacak kalemi (FIFO) 1 / 30 / 60 / 90. günde BİR kez `muhasebe.alacak_gecikti`; eşiğin
    üstünden 7 günden fazla geçmişse susar (modül ilk açılınca eski alacaklar için olay yağmuru yok)."""
    from core.database import db_manager
    from models.muhasebe import MuhasebeGecikmeIzleri
    from services import muhasebe_kayit as k
    from services import otomasyon, otomasyon_kural, webhook

    assert "muhasebe.alacak_gecikti" in webhook.OLAY_SOZLUGU and "muhasebe.alacak_gecikti" in otomasyon_kural.OLAY_SOZLUGU
    assert otomasyon_kural.olay_nesneleri("muhasebe.alacak_gecikti", False) == ("alacak", "hesap", "kisi", "olay")
    m, b = await _musteri(istemci, yonetici_basligi, "gecikme")
    c = await _cari(istemci, b, ad="Geciken Ltd", eposta="odeme@geciken.com")
    # Vade 31 gün önce → 30. gün eşiği; ikincisinin vadesi gelmemiş; 200 gün geçmiş olan sessiz.
    h1 = await _hareket(istemci, b, tur="gelir", tutar="1.000", cari_id=c["id"], tarih="2026-08-20", vade_tarihi="2026-09-04", belge_no="F-1")
    h2 = await _hareket(istemci, b, tur="gelir", tutar="500", cari_id=c["id"], tarih="2026-10-01", vade_tarihi="2026-11-01")
    c2 = await _cari(istemci, b, ad="Eski Borçlu")
    await _hareket(istemci, b, tur="gelir", tutar="50", cari_id=c2["id"], tarih="2026-03-01", vade_tarihi="2026-03-19")

    async def izler():
        return [(i.cari_id, i.hareket_id, i.esik, i.gun, i.tutar) for i in (await db_oturumu.execute(
            select(MuhasebeGecikmeIzleri).where(MuhasebeGecikmeIzleri.kapsam == m).order_by(MuhasebeGecikmeIzleri.id))).scalars().all()]

    r = await _post(istemci, f"{M}/esitle", {}, b)
    assert r["gecikme"] == 1
    assert await izler() == [(c["id"], h1["id"], 30, 31, 100000)]
    assert (await _post(istemci, f"{M}/esitle", {}, b))["gecikme"] == 0
    # Kısmi tahsilat (FIFO en eskiyi kapatır) → 30 gün sonra 60. gün eşiği kalan tutarla; ikinci kalem 1. gün eşiği.
    kasa = await _hesap(istemci, b, ad="Kasa")
    await _hareket(istemci, b, tur="tahsilat", tutar="400", hesap_id=kasa["id"], cari_id=c["id"])
    _ortam["an"] = SIMDI + timedelta(days=30)
    r = await _post(istemci, f"{M}/esitle", {}, b)
    assert r["gecikme"] == 2
    son = (await izler())[1:]
    assert sorted((x[1], x[2], x[4]) for x in son) == sorted([(h1["id"], 60, 60000), (h2["id"], 1, 50000)])
    iz = (await db_oturumu.execute(select(MuhasebeGecikmeIzleri).where(MuhasebeGecikmeIzleri.kapsam == m, MuhasebeGecikmeIzleri.esik == 60))).scalars().one()
    async with db_manager.async_session_maker() as db:
        bg = await otomasyon.baglam_kur(db, "muhasebe.alacak_gecikti", k.gecikme_verisi(iz, "Geciken Ltd"), m, False)
        assert bg["alacak"]["eposta"] == "odeme@geciken.com" and bg["alacak"]["no"] == "F-1" and bg["alacak"]["gecikme_gun"] == 60
        assert bg["alacak"]["tutar"] == 600.0 and bg["kisi"] == {"ad": "Geciken Ltd", "email": "odeme@geciken.com"}
        # Başka hesabın olayı müşteri bağlamında kurulmaz.
        assert await otomasyon.baglam_kur(db, "muhasebe.alacak_gecikti", k.gecikme_verisi(iz, "x"), _e("yabanci"), False) is None
    assert (await _post(istemci, f"{M}/esitle", {}, b))["gecikme"] == 0


async def test_butce_asimi_bildirimi_bir_kez(istemci, yonetici_basligi, db_oturumu):
    """Bütçe aşımı bildirimi (müşteride hesaba) (kategori, ay) başına BİR kez; aşım sürse de tekrar etmez."""
    from models.notifications import Notifications

    m, b = await _musteri(istemci, yonetici_basligi, "butcebildirim")
    kasa = await _hesap(istemci, b, ad="Kasa")
    kat = await _kategori(istemci, b, "gider", "pazarlama")
    assert (await istemci.put(f"{M}/butceler", json={"kategori_id": kat["id"], "ay": "*", "tutar": "100"}, headers=b)).status_code == 200
    for tutar in ("80", "30", "50"):
        await _hareket(istemci, b, tur="gider", tutar=tutar, hesap_id=kasa["id"], kategori_id=kat["id"])
    await _post(istemci, f"{M}/esitle", {}, b)
    satirlar = (await db_oturumu.execute(select(Notifications).where(Notifications.event_type == "muhasebe_butce",
                                                                    Notifications.recipient_email == m,
                                                                    Notifications.channel == "inapp"))).scalars().all()
    assert len(satirlar) == 1 and "/client?sekme=onMuhasebe" in (satirlar[0].link or "")
    assert "Reklam ve pazarlama" in satirlar[0].body


async def test_kar_zarar_kdv_haric(istemci, yonetici_basligi):
    """Kâr-zarar: KDV hariç (1.200 %20 dahil satış → 1.000 gelir; 600 %20 dahil gider → 500; 100 KDV'siz gider);
    sonuç 400, marj %40; CSV'de satırlar ve sonuç."""
    m, b = await _musteri(istemci, yonetici_basligi, "karzarar")
    kasa = await _hesap(istemci, b, ad="Kasa")
    satis, kira = await _kategori(istemci, b, "gelir", "satis"), await _kategori(istemci, b, "gider", "kira")
    await _hareket(istemci, b, tur="gelir", tutar="1.200", kdv_orani=20, hesap_id=kasa["id"], kategori_id=satis["id"])
    await _hareket(istemci, b, tur="gider", tutar="600", kdv_orani=20, hesap_id=kasa["id"], kategori_id=kira["id"])
    await _hareket(istemci, b, tur="gider", tutar="100", hesap_id=kasa["id"])
    d = (await istemci.get(f"{M}/raporlar/kar-zarar", headers=b)).json()
    p = d["para_birimleri"][0]
    assert (p["toplam_gelir"], p["toplam_gider"], p["sonuc"], p["marj"]) == (100000, 60000, 40000, 40.0) and d["bilgilendirme"] is True
    assert [(x["anahtar"], x["tutar"], x["kdv"]) for x in p["giderler"]] == [("kira", 50000, 10000), (None, 10000, 0)]
    y = await istemci.get(f"{M}/raporlar.csv", params={"tur": "kar_zarar"}, headers=b)
    assert y.status_code == 200 and "sonuc" in y.text and "400,00" in y.text


async def test_nakit_akisi_30_60_90_gun_beklenen(istemci, yonetici_basligi):
    """Önümüzdeki 30 / 60 / 90 gün: açık vadeli alacak (tahsilat) / borç (ödeme) kalemleri vadesine göre + tekrarlayan
    kayıtlar; vadesi geçmiş açık kalemler ayrı (`gecikmis`), ufka katılmaz."""
    m, b = await _musteri(istemci, yonetici_basligi, "nakit")
    kasa = await _hesap(istemci, b, ad="Kasa", acilis_bakiyesi="1.000")
    c = await _cari(istemci, b, ad="Alıcı")
    t = await _cari(istemci, b, ad="Tedarikçi", tur="tedarikci")
    await _hareket(istemci, b, tur="gelir", tutar="800", cari_id=c["id"], vade_tarihi=(BUGUN + timedelta(days=20)).isoformat())
    await _hareket(istemci, b, tur="gelir", tutar="50", cari_id=c["id"], tarih="2026-09-01", vade_tarihi="2026-09-10")  # gecikmiş
    await _hareket(istemci, b, tur="gider", tutar="400", cari_id=t["id"], vade_tarihi=(BUGUN + timedelta(days=45)).isoformat())
    await _post(istemci, f"{M}/tekrarlar", {"tur": "gider", "aciklama": "Kira", "tutar": "100", "hesap_id": kasa["id"], "periyot": "aylik",
                                           "baslangic": "2026-11-01"}, b)
    d = (await istemci.get(f"{M}/raporlar/nakit-akisi", headers=b)).json()["para_birimleri"][0]
    u = {x["gun"]: x for x in d["beklenen"]}
    assert (u[30]["tahsilat"], u[30]["odeme"], u[30]["tekrar_cikis"]) == (80000, 0, 10000)
    assert (u[60]["tahsilat"], u[60]["odeme"], u[60]["tekrar_cikis"]) == (80000, 40000, 20000)
    assert u[90]["net"] == 80000 - 40000 - 30000 and u[90]["bakiye"] == 100000 + u[90]["net"]
    assert d["gecikmis"] == {"tahsilat": 5000, "odeme": 0}
