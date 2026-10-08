"""Faz 7K — çok dilli PDF: bütün ReportLab üreticileri 7 dilde etiket + Kiril/Arapça/Çince/Hintçe adlar.

Her üretici her dilde PDF üretir → pypdf ile metin çıkarılır →
* başlık etiketi o dilin kendi metni (İngilizceye ya da Türkçeye düşmüyor),
* dört yazıdaki adlar (Rusça, Arapça, Çince, Hintçe) metinde,
* doğru yazı tipleri — Kiril → Noto Sans Kiril, Arapça → Noto Sans Arabic, Hintçe → Noto Sans Devanagari
  (gömülü alt küme, FontFile2); Çince → ReportLab'ın CID yazı tipi STSong-Light (bilerek gömülmüyor:
  depoya CJK dosyası eklenmedi).
* Çince metin pypdf'te Unicode olarak geri okunuyor (UniGB-UCS2-H kodlaması).

Karşılaştırma notları:
* Arapça PDF'te birleşik (sunum) biçimlerle yazılır (ﺃﺣﻤﺪ); karşılaştırma NFKC ile temel harflere
  çevrilip boşluksuz yapılır, pypdf'in sıralamasına bağlı kalmamak için tersiyle de bakılır.
* Hintçede HarfBuzz şekillendirmesi gliflerin görsel sırasını yazıyor: ön ekli ünlü (ि) ünsüzden
  ÖNCE, reph (र्) sonraki ünsüzden SONRA çıkıyor; karşılaştırma bunu mantıksal sıraya çeviriyor
  (bilinen sınır: kopyala-yapıştırda aynı sıra görülür). pypdf 3.x konumlandırılmış Devanagari
  glif dizilerinde zaman zaman glif atlıyor ya da araya boşluk koyuyor; pypdf'te bulunamayan
  Devanagari metni MuPDF'in (PyMuPDF, bağımlılıklarda var) çıkarımıyla da aranıyor.
"""

import io
import re
import unicodedata
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from services import belge_pdf, egitim, etkinlik, hukuk, ik, pdf_belge, pdf_yazi, saha_pdf, stok_pdf

DILLER = ("tr", "en", "de", "ru", "zh", "hi", "ar")
RU = "Иван Петров"
AR = "أحمد علي"
ZH = "张伟"
HI = "राम कृष्ण"
ADLAR = (RU, AR, ZH, HI)
HEPSI = " · ".join(ADLAR)


def _metin(veri: bytes) -> str:
    from pypdf import PdfReader

    return "\n".join((s.extract_text() or "") for s in PdfReader(io.BytesIO(veri)).pages)


def _sade(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    return "".join(c for c in s if not c.isspace() and unicodedata.category(c) != "Cf")


_DEVA_UNSUZ = r"[\u0915-\u0939\u0958-\u095f]"


def _hintce_mantiksal(s: str) -> str:
    s = re.sub(r" ([\u0900-\u0903\u093a-\u094f\u0962\u0963])", r"\1", s)  # pypdf'in işaret öncesi boşluğu
    s = re.sub(rf"\u093f([\u0901\u0902]?)({_DEVA_UNSUZ}(?:\u094d{_DEVA_UNSUZ})*)", r"\2" + "\u093f" + r"\1", s)  # ön ekli ünlü
    s = re.sub(rf"({_DEVA_UNSUZ}[\u093e-\u094c]?)\u0930\u094d", "\u0930\u094d" + r"\1", s)  # reph
    return s


def _var(metin: str, aranan: str, veri: bytes = b"") -> bool:
    sade, a = _sade(metin), _sade(aranan)
    if a in sade or a[::-1] in sade:
        return True
    if a in _sade(_hintce_mantiksal(metin)):
        return True
    if veri and re.search("[\u0900-\u097f]", aranan):
        import pymupdf

        with pymupdf.open(stream=veri, filetype="pdf") as belge:
            ikinci = "\n".join(s.get_text() for s in belge)
        return a in _sade(_hintce_mantiksal(ikinci))
    return False


def _fontlar(veri: bytes) -> dict:
    """{taban ad: gömülü mü} — alt küme öneki atılmış."""
    from pypdf import PdfReader

    sonuc = {}
    for sayfa in PdfReader(io.BytesIO(veri)).pages:
        fontlar = sayfa["/Resources"].get_object().get("/Font")
        if not fontlar:
            continue
        for ref in fontlar.get_object().values():
            f = ref.get_object()
            ad = str(f.get("/BaseFont", "")).lstrip("/").split("+", 1)[-1]
            tanim = f.get("/FontDescriptor")
            gomulu = bool(tanim and any(k in tanim.get_object() for k in ("/FontFile", "/FontFile2", "/FontFile3")))
            sonuc[ad] = sonuc.get(ad, False) or gomulu
    return sonuc


YAZI_TIPI = {RU: "NotoSans-Kiril", AR: "NotoSansArabic", ZH: "STSong-Light", HI: "NotoSansDevanagari"}
#: Gömülmeyen (CID) yazı tipleri: okuyucunun kendi yazı tipiyle çiziliyor.
GOMULMEYEN = {"STSong-Light"}


def _yazi_tipleri_dogru(veri: bytes, adlar=ADLAR) -> None:
    f = _fontlar(veri)
    assert any(a.startswith("PlusJakartaSans") for a in f)  # Latin: sitenin yazı tipi
    for ad in adlar:
        onek = YAZI_TIPI[ad]
        bulunan = [a for a in f if a.startswith(onek)]
        assert bulunan, (onek, sorted(f))
        if onek in GOMULMEYEN:
            assert not any(f[a] for a in bulunan), (onek, "CID yazı tipi gömülmemeli")
        else:
            assert all(f[a] for a in bulunan), (onek, "gömülü değil")


def _denetle(veri: bytes, baslik: str, adlar=ADLAR) -> str:
    assert veri[:5] == b"%PDF-"
    metin = _metin(veri)
    assert _var(metin, baslik, veri), (baslik, metin[:400])
    for ad in adlar:
        assert _var(metin, ad, veri), (ad, metin[:600])
    _yazi_tipleri_dogru(veri, adlar)
    return metin


AJANS = {"unvan": "By Mehmet KURU Dev", "adres": "İstanbul", "eposta": "a@b.dev", "iban": "TR00 0000"}


def _kalemler():
    return [{"aciklama": f"Hizmet — {RU}", "adet": 2, "birim_fiyat": 100, "indirim": 0, "kdv_orani": 20, "matrah": 200},
            {"aciklama": f"{ZH} 网站设计", "adet": 1, "birim_fiyat": 50, "indirim": 0, "kdv_orani": 20, "matrah": 50}]


@pytest.mark.parametrize("dil", DILLER)
def test_fatura_teklif_sozlesme(dil):
    ozet = {"ara_toplam": 250, "genel_toplam": 300, "kdv_dokumu": [{"oran": 20, "kdv": 50}]}
    f = {"currency": "TRY", "invoice_no": "INV-1", "issue_date": "2026-10-01", "client_name": AR, "client_email": "m@x.dev",
         "kalemler": _kalemler(), "ozet": ozet, "notlar": f"{HI} · {ZH}", "bakiye": {"odenen": 100, "kalan": 200}}
    _denetle(pdf_belge.fatura_pdf(f, AJANS, dil), pdf_belge.ETIKET[dil]["fatura"])

    t = {"para_birimi": "EUR", "no": "T-7", "tarih": "2026-10-01", "musteri_ad": RU, "baslik": f"{AR} — {HI}",
         "kalemler": _kalemler(), "ozet": ozet, "sartlar": ZH}
    _denetle(pdf_belge.teklif_pdf(t, AJANS, dil), pdf_belge.ETIKET[dil]["teklif"])

    s = {"no": "S-3", "surum": 1, "taraf_ad": ZH, "baslik": HEPSI, "govde": f"# {RU}\n\n- {AR}\n- {HI}\n\n**{ZH}**"}
    _denetle(pdf_belge.sozlesme_pdf(s, AJANS, None, dil), pdf_belge.ETIKET[dil]["imzalanmadi"])


@pytest.mark.parametrize("dil", DILLER)
def test_belge_ve_strateji(dil):
    v = {"baslik": RU, "tur": "belge", "icerik": f"## {AR}\n\n| a | b |\n|---|---|\n| {ZH} | {HI} |\n\n```\nкод {ZH}\n```",
         "surum": 2, "guncellendi": "2026-10-01", "etiketler": [HI], "musteri": ZH}
    _denetle(belge_pdf.belge_pdf(v, dil), belge_pdf.ETIKET[dil]["belge"])
    s = {"baslik": "SWOT", "tur": "swot", "strateji": {"isletme": AR, "kutular": {"guclu": RU, "zayif": ZH, "firsatlar": HI}}}
    from services.belgeler import kutu_adi

    _denetle(belge_pdf.belge_pdf(s, dil), kutu_adi("swot", "guclu", dil))


@pytest.mark.parametrize("dil", DILLER)
def test_servis_formu(dil):
    v = {"para_birimi": "TRY", "is": {"no": "IS-1", "tarih": "01.10.2026", "durum": "tamamlandi", "tur": "ariza",
                                       "oncelik": "acil", "baslik": RU, "aciklama": AR},
         "firma": {"ad": ZH}, "musteri": {"ad": HI}, "teknisyenler": [RU],
         "kontrol": [{"tur": "evet_hayir", "deger": True, "metin": ZH}],
         "malzemeler": [{"ad": AR, "miktar": 1, "birim": "adet", "birim_fiyat": 1000}], "kdv_orani": 20}
    veri = saha_pdf.servis_formu_pdf(v, dil)
    metin = _denetle(veri, saha_pdf.ETIKET[dil]["baslik"])
    assert _var(metin, saha_pdf.ETIKET[dil]["tamamlandi"], veri)


@pytest.mark.parametrize("dil", DILLER)
def test_fis_ve_satis_faturasi(dil):
    kalem = {"ad": RU, "adet_binde": 1000, "birim": "adet", "birim_fiyat": 1000, "kdv_orani": 20, "brut": 1000,
             "tutar": 1000, "indirim": 0}
    v = {"para_birimi": "TRY", "firma": {"ad": AR, "adres": ZH}, "no": "F-1", "tarih_metni": "01.10.2026",
         "kasiyer": HI, "kalemler": [kalem], "toplam": 1000, "kdv_dokumu": [{"oran": 20, "kdv": 167, "matrah": 833}],
         "kdv_toplam": 167, "nakit": 1000, "fatura_no": "SF-1", "fatura_tarihi": "01.10.2026", "alici": {"ad": ZH}}
    _denetle(stok_pdf.fis_pdf(v, dil), stok_pdf.ETIKET[dil]["fis"])
    _denetle(stok_pdf.fatura_pdf(v, dil), stok_pdf.ETIKET[dil]["fatura"], adlar=(RU, AR, ZH))


@pytest.mark.parametrize("dil", DILLER)
def test_hukuk_dokumu(dil):
    veri = hukuk.dokum_pdf(buro_adi=AR, muvekkil_adi=RU, dosya={"baslik": ZH, "mahkeme": HI},
                           masraflar=[{"tarih": "2026-10-01", "tur": "harc", "aciklama": RU, "tutar_kurus": 1000,
                                       "para_birimi": "TRY", "avanstan": True}],
                           zamanlar=[{"tarih": "2026-10-01", "aciklama": ZH, "sure_dk": 90, "faturalanabilir": True}],
                           dil=dil)
    metin = _denetle(veri, hukuk.PDF_ETIKET[dil]["baslik"])
    assert _var(metin, hukuk.MASRAF_ADI[dil]["harc"], veri)


@pytest.mark.parametrize("dil", DILLER)
def test_vardiya_plani(dil):
    satirlar = [{"ad": a, "gunler": [[f"09:00–17:00 {ZH}"]] + [[] for _ in range(6)], "toplam_saat": 8} for a in ADLAR]
    veri = ik.plan_pdf(firma=AR, hafta_bas=date(2026, 10, 5), satirlar=satirlar, dil=dil)
    metin = _denetle(veri, ik.PDF_ETIKET[dil]["baslik"])
    assert _var(metin, ik.PDF_ETIKET[dil]["gunler"][0], veri)


@pytest.mark.parametrize("dil", DILLER)
def test_etkinlik_bileti(dil):
    e = SimpleNamespace(baslik=f"{RU} · {AR}", baslangic=datetime(2026, 11, 1, 10, tzinfo=timezone.utc),
                        bitis=datetime(2026, 11, 1, 12, tzinfo=timezone.utc), saat_dilimi="Europe/Istanbul",
                        mekan_adi=ZH, adres=HI, bicim="yuz_yuze", online_baglanti=None)
    siparis = SimpleNamespace(kod="ABC123", ad=HI)
    bilet = SimpleNamespace(kod="B1", katilimci_ad=ZH, durum="gecerli")
    _denetle(etkinlik.bilet_pdf(e, siparis, [(bilet, AR)], dil), etkinlik.PDF_ETIKET[dil]["kod"])


@pytest.mark.parametrize("dil", DILLER)
def test_sertifika(dil):
    for sablon in ("klasik", "modern"):
        veri = egitim.sertifika_pdf(ad=f"{RU} {AR}", kurs_adi=f"{ZH} {HI}", kurum=AR, kod="ABCD1234EFGH",
                                    verilme=datetime(2026, 10, 1, tzinfo=timezone.utc), sablon=sablon, dil=dil,
                                    saat=12, egitmenler=[ZH], imza_adi=HI, imza_unvan=RU)
        _denetle(veri, egitim.PDF_ETIKET[dil]["baslik"])


def test_yedek_zinciri_ve_cift_yon():
    """Birim: parçalama, nötr karakterlerin parçada kalması, kalının yedeğe geçmesi, bidi sırası."""
    assert pdf_yazi.parcala("Ali Иван Петров", pdf_yazi.YAZI) == [("MKSans", "Ali "), ("MKKiril", "Иван Петров")]
    assert pdf_yazi.parcala("Иван", pdf_yazi.KALIN) == [("MKKiril-Bold", "Иван")]
    # Çince (noktalama dâhil) → STSong-Light (CID, gömülmez); kalın istense de aynı (kalın biçimi yok)
    assert pdf_yazi.parcala("张伟，你好", pdf_yazi.YAZI) == [("STSong-Light", "张伟，你好")]
    assert pdf_yazi.parcala("龘", pdf_yazi.KALIN) == [("STSong-Light", "龘")]
    assert pdf_yazi.parcala("Ali 张伟 12", pdf_yazi.YAZI) == [("MKSans", "Ali "), ("STSong-Light", "张伟"), ("MKSans", " 12")]
    # python-bidi ile aynı görsel sıra (ayna karakterler hariç: python-bidi 0.6 aynalamıyor)
    from bidi import get_display

    for s in ("مرحبا بالعالم", "فاتورة INV-2026-001", "Müşteri: أحمد علي", "المجموع: 1,250.50 ₺", "رقم ١٢٣ و 456"):
        assert pdf_yazi.gorsel_sira(s) == get_display(s)
    assert pdf_yazi.gorsel_sira("(مرحبا) abc") == "abc (ابحرم)"
    # Arapça birleşik biçim: yalnız zorunlu lam-elif bağı; "محمد" bağ (ﷴ) olmasın
    assert "\ufdf4" not in pdf_yazi.arapca_bicimle("محمد") and "\ufefb" in pdf_yazi.arapca_bicimle("لا")


def test_uzun_arapca_paragraf_satir_sirasi():
    """Uzun Arapça metin satırlara MANTIKSAL sırayla bölünmeli: ilk sözcük ilk satırda (sağda)."""
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate

    ilk, son = "البداية", "النهاية"
    govde = " ".join([ilk] + ["كلمة"] * 120 + [son])
    tampon = io.BytesIO()
    st = ParagraphStyle("t", fontName=pdf_yazi.YAZI, fontSize=11, leading=15)
    SimpleDocTemplate(tampon).build([pdf_yazi.Paragraf(govde, st)])
    satirlar = [s for s in _metin(tampon.getvalue()).split("\n") if s.strip()]
    assert len(satirlar) > 3
    assert _var(satirlar[0], ilk) and not _var(satirlar[0], son)
    assert _var(satirlar[-1], son)


def test_hintce_sekillendirme_ve_karisik_sozcuk():
    """Devanagari HarfBuzz ile şekillenir (birleşik glif → özel alan, ToUnicode kaynak harfler);
    "नमस्ते," gibi sonu Latin noktalamalı sözcük bozulmaz."""
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate

    tampon = io.BytesIO()
    st = ParagraphStyle("t", fontName=pdf_yazi.YAZI, fontSize=11, leading=15)
    SimpleDocTemplate(tampon).build([pdf_yazi.Paragraf("नमस्ते, क्षत्रिय विद्यालय (हिंदी)!", st)])
    # NullMark (bağa katılmış işaretin boş yer tutucusu) sıfır genişlikli boşluk olarak çıkar.
    metin = _hintce_mantiksal(_metin(tampon.getvalue())).replace("\u200b", "")
    for parca in ("नमस्ते,", "क्षत्रिय", "विद्यालय", "(हिंदी)!"):
        assert parca in metin, metin
    assert not re.search("[\ue000-\uf8ff]", metin)  # özel alan karakteri sızmıyor


def test_gomulu_yazi_tipleri_toplam_boyutu():
    """Faz 7K'nın eklediği yazı tipleri (Noto) toplam 6 MB'ı geçmez, CJK dosyası yok; lisans dosyası var."""
    dizin = pdf_yazi.FONT_DIZINI
    eklenen = [p for p in dizin.glob("*.ttf") if p.name.startswith("Noto")]
    assert eklenen and sum(p.stat().st_size for p in eklenen) <= 6 * 1024 * 1024
    assert not [p for p in eklenen if "CJK" in p.name or "SC" in p.name.split("-")[0]]
    lisans = (dizin / "OFL-Noto.txt").read_text(encoding="utf-8")
    assert "SIL Open Font License" in lisans
    for aile, normal, kalin in pdf_yazi.ZINCIR[1:]:
        assert (dizin / normal).exists() and (dizin / kalin).exists()
