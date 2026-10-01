"""Faz 3T — fatura, teklif ve sözleşme PDF'leri (sunucuda, saf Python).

Neden ReportLab, neden sunucu?
------------------------------
* Render'ın ücretsiz planı: Chromium (Playwright/WeasyPrint'in tarayıcı ya da
  Cairo/Pango yığını) hem derlemeyi hem 512 MB belleği zorlar. ReportLab saf
  Python (tekerlek ~2 MB) ve yalnız Pillow'a dayanıyor.
* PDF'in sunucuda üretilmesi imzalı sözleşme için şart: indirilen belge her
  zaman aynı metni, aynı imza bloğunu ve doğrulama özetini taşımalı;
  tarayıcının "PDF olarak kaydet"i sayfa düzenine ve tarayıcıya göre değişir.
* Girişsiz bağlantıdan da (jetonla) indirilebiliyor; e-posta ekine
  konabilecek tek dosya.

Yazı tipi
---------
Sitenin kendi yazı tipi Plus Jakarta Sans (SIL OFL 1.1) — `public/fonts`'taki
değişken woff2 (U+0000-017F: Türkçe dâhil bütün Latin) fontTools ile 400 ve
700 kalınlığında iki statik TTF'ye çevrildi (`data/fonts/`, ~32 kB'lık iki
dosya, lisans `data/fonts/OFL.txt`). ReportLab woff2 okuyamıyor; standart
Helvetica ise ğ, ı, İ, ş harflerini taşımıyor (WinAnsi). TTF gömülü alt küme
olarak PDF'e giriyor ve ToUnicode tablosu yazılıyor: metin seçilip
kopyalanabiliyor, aranabiliyor (test metni çıkarıp Türkçe harfleri arıyor).

Marka künyesi vektör olarak çiziliyor (görsel dosyası yok): yuvarlatılmış
kare içinde `</>`, yanında "By Mehmet KURU Dev" — sitedeki `MarkaLogosu`
ile aynı biçim, kırpılmadan.
"""

import io
import logging
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from reportlab.graphics.shapes import Drawing, Line
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable,
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from xml.sax.saxutils import escape

logger = logging.getLogger(__name__)

FONT_DIZINI = Path(__file__).resolve().parents[1] / "data" / "fonts"
YAZI = "MKSans"
KALIN = "MKSans-Bold"

# Marka renkleri (sitedeki --primary yeşili ve mor-siyah zemin; kâğıtta okunur tonlar).
VURGU = colors.HexColor("#00A86B")
VURGU_ACIK = colors.HexColor("#E6F7F0")
KOYU = colors.HexColor("#1A0B2E")
GRI = colors.HexColor("#5B5368")
CIZGI = colors.HexColor("#D9D4E0")

E_FATURA_NOTU = {
    "tr": "Bu belge e-Fatura/e-Arşiv fatura yerine geçmez; bilgilendirme amaçlıdır.",
    "en": "This document does not replace an e-Invoice/e-Archive invoice; it is for information only.",
}
IMZA_NOTU = {
    "tr": (
        "Bu, 5070 sayılı Elektronik İmza Kanunu anlamında güvenli elektronik imza değildir; "
        "taraflar arasında basit elektronik onay kaydıdır."
    ),
    "en": (
        "This is not a secure electronic signature under Turkish Law No. 5070; "
        "it is a simple electronic consent record between the parties."
    ),
}

ETIKET: Dict[str, Dict[str, str]] = {
    "tr": {
        "fatura": "FATURA", "iade_faturasi": "İADE FATURASI", "teklif": "TEKLİF", "sozlesme": "SÖZLEŞME",
        "no": "No", "tarih": "Tarih", "vade": "Son ödeme", "gecerlilik": "Geçerlilik",
        "musteri": "Sayın", "aciklama": "Açıklama", "adet": "Adet", "birim": "Birim fiyat",
        "indirim": "İnd. %", "kdv": "KDV %", "tutar": "Tutar", "ara_toplam": "Ara toplam",
        "indirim_toplam": "İndirim", "kdv_satir": "KDV (%{oran})", "genel_toplam": "Genel toplam",
        "odemeler": "Ödemeler", "odenen": "Ödenen", "kalan": "Kalan bakiye", "iade": "İade",
        "notlar": "Notlar", "sartlar": "Şartlar ve koşullar", "vergi": "Vergi dairesi / no",
        "iban": "IBAN", "sayfa": "Sayfa", "durum": "Durum", "imza": "İmza", "imzalayan": "İmzalayan",
        "imza_zamani": "İmza zamanı (UTC)", "ip": "IP özeti", "tarayici": "Tarayıcı",
        "metin_ozeti": "Metin özeti (SHA-256)", "dogrulama": "Doğrulama",
        "imzalanmadi": "Henüz imzalanmadı.", "surum": "Sürüm", "baslangic": "Başlangıç", "bitis": "Bitiş",
        "kabul": "Kabul eden", "kabul_zamani": "Kabul zamanı (UTC)", "yontem": "Yöntem",
        "bagli_fatura": "İlgili fatura", "donem": "Dönem", "cizim_yok": "(çizim imzası yok)",
    },
    "en": {
        "fatura": "INVOICE", "iade_faturasi": "CREDIT NOTE", "teklif": "QUOTE", "sozlesme": "CONTRACT",
        "no": "No", "tarih": "Date", "vade": "Due date", "gecerlilik": "Valid until",
        "musteri": "Bill to", "aciklama": "Description", "adet": "Qty", "birim": "Unit price",
        "indirim": "Disc. %", "kdv": "VAT %", "tutar": "Amount", "ara_toplam": "Subtotal",
        "indirim_toplam": "Discount", "kdv_satir": "VAT ({oran}%)", "genel_toplam": "Total",
        "odemeler": "Payments", "odenen": "Paid", "kalan": "Balance due", "iade": "Refund",
        "notlar": "Notes", "sartlar": "Terms and conditions", "vergi": "Tax office / no",
        "iban": "IBAN", "sayfa": "Page", "durum": "Status", "imza": "Signature", "imzalayan": "Signed by",
        "imza_zamani": "Signed at (UTC)", "ip": "IP digest", "tarayici": "Browser",
        "metin_ozeti": "Text digest (SHA-256)", "dogrulama": "Verification",
        "imzalanmadi": "Not signed yet.", "surum": "Version", "baslangic": "Start", "bitis": "End",
        "kabul": "Accepted by", "kabul_zamani": "Accepted at (UTC)", "yontem": "Method",
        "bagli_fatura": "Related invoice", "donem": "Period", "cizim_yok": "(no drawn signature)",
    },
}

_KAYITLI = False


def fontlari_kaydet() -> None:
    """TTF'leri bir kez kaydeder (süreç başına)."""
    global _KAYITLI
    if _KAYITLI:
        return
    from reportlab.lib.fonts import addMapping

    pdfmetrics.registerFont(TTFont(YAZI, str(FONT_DIZINI / "PlusJakartaSans-Regular.ttf")))
    pdfmetrics.registerFont(TTFont(KALIN, str(FONT_DIZINI / "PlusJakartaSans-Bold.ttf")))
    # <b> etiketi kalın dosyaya düşsün (italik dosya yok: düz kalıyor).
    addMapping(YAZI, 0, 0, YAZI)
    addMapping(YAZI, 1, 0, KALIN)
    addMapping(YAZI, 0, 1, YAZI)
    addMapping(YAZI, 1, 1, KALIN)
    _KAYITLI = True


def _dil(dil: Optional[str]) -> str:
    return "en" if (dil or "").lower().startswith("en") else "tr"


# ---------------------------------------------------------------------------
# Biçim
# ---------------------------------------------------------------------------
PARA_SIMGESI = {"TRY": "₺", "USD": "$", "EUR": "€", "GBP": "£"}


def para(deger: Any, para_birimi: Optional[str], dil: str = "tr") -> str:
    """1250.5, TRY → "1.250,50 ₺" (tr) / "₺1,250.50" (en)."""
    try:
        d = Decimal(str(deger if deger is not None else 0)).quantize(Decimal("0.01"))
    except Exception:  # noqa: BLE001
        d = Decimal("0.00")
    eksi = d < 0
    d = abs(d)
    tam, kesir = f"{d:.2f}".split(".")
    gruplar = []
    while tam:
        gruplar.insert(0, tam[-3:])
        tam = tam[:-3]
    birim = (para_birimi or "TRY").upper()
    simge = PARA_SIMGESI.get(birim, birim + " ")
    if _dil(dil) == "en":
        metin = f"{simge}{','.join(gruplar)}.{kesir}"
    else:
        metin = f"{'.'.join(gruplar)},{kesir} {simge.strip()}"
    return f"−{metin}" if eksi else metin


def sayi(deger: Any) -> str:
    try:
        d = Decimal(str(deger))
    except Exception:  # noqa: BLE001
        return str(deger)
    return f"{d.normalize():f}" if d == d.to_integral() else f"{d.normalize():f}".rstrip("0").rstrip(".")


def tarih(deger: Any) -> str:
    if not deger:
        return "—"
    if isinstance(deger, datetime):
        return deger.strftime("%d.%m.%Y %H:%M")
    metin = str(deger)
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", metin)
    if m:
        return f"{m.group(3)}.{m.group(2)}.{m.group(1)}"
    return metin


def _metin(deger: Any) -> str:
    """Paragraf içine güvenli metin (ReportLab mini-HTML'i kaçışlı, satır sonu korunur)."""
    return escape(str(deger or "")).replace("\n", "<br/>")


# ---------------------------------------------------------------------------
# Stiller ve parçalar
# ---------------------------------------------------------------------------
def _stiller() -> Dict[str, ParagraphStyle]:
    fontlari_kaydet()
    return {
        "govde": ParagraphStyle("govde", fontName=YAZI, fontSize=9.5, leading=13.5, textColor=KOYU),
        "kucuk": ParagraphStyle("kucuk", fontName=YAZI, fontSize=8, leading=11, textColor=GRI),
        "kalin": ParagraphStyle("kalin", fontName=KALIN, fontSize=9.5, leading=13.5, textColor=KOYU),
        "baslik": ParagraphStyle("baslik", fontName=KALIN, fontSize=20, leading=24, textColor=KOYU, alignment=TA_RIGHT),
        "sag": ParagraphStyle("sag", fontName=YAZI, fontSize=9.5, leading=13.5, textColor=KOYU, alignment=TA_RIGHT),
        "sag_kalin": ParagraphStyle("sag_kalin", fontName=KALIN, fontSize=9.5, leading=13.5, textColor=KOYU, alignment=TA_RIGHT),
        "bolum": ParagraphStyle("bolum", fontName=KALIN, fontSize=11, leading=15, textColor=VURGU, spaceBefore=8, spaceAfter=4),
        "h1": ParagraphStyle("h1", fontName=KALIN, fontSize=14, leading=18, textColor=KOYU, spaceBefore=6, spaceAfter=6),
        "h2": ParagraphStyle("h2", fontName=KALIN, fontSize=11.5, leading=15, textColor=KOYU, spaceBefore=8, spaceAfter=3),
        "madde": ParagraphStyle("madde", fontName=YAZI, fontSize=9.5, leading=13.5, textColor=KOYU, leftIndent=12, bulletIndent=2),
        "ozet": ParagraphStyle("ozet", fontName=YAZI, fontSize=7, leading=9, textColor=GRI, alignment=TA_LEFT),
    }


class MarkaKunyesi(Flowable):
    """Sitedeki künyenin vektör karşılığı: kutu içinde </> + iki satır yazı."""

    def __init__(self, unvan: str, alt_satir: str):
        super().__init__()
        self.unvan = unvan
        self.alt_satir = alt_satir
        self.width = 95 * mm
        self.height = 13 * mm

    def draw(self) -> None:
        c = self.canv
        k = 11 * mm
        c.setFillColor(KOYU)
        c.setStrokeColor(VURGU)
        c.setLineWidth(1)
        c.roundRect(0, 0.5 * mm, k, k, 2.6 * mm, stroke=1, fill=1)
        # </> işareti (24'lük görünüm kutusu → k)
        o = k / 24.0
        c.setStrokeColor(VURGU)
        c.setLineWidth(1.6)
        c.setLineCap(1)
        c.setLineJoin(1)
        y0 = 0.5 * mm

        def yol(noktalar):
            p = c.beginPath()
            x, y = noktalar[0]
            p.moveTo(x * o, y0 + (24 - y) * o)
            for x, y in noktalar[1:]:
                p.lineTo(x * o, y0 + (24 - y) * o)
            c.drawPath(p, stroke=1, fill=0)

        yol([(18, 16), (22, 12), (18, 8)])
        yol([(6, 8), (2, 12), (6, 16)])
        yol([(14.5, 4), (9.5, 20)])
        # canlılık noktası
        c.setFillColor(VURGU)
        c.circle(k - 0.2 * mm, k + 0.3 * mm, 1.1 * mm, stroke=0, fill=1)
        # yazı
        c.setFillColor(KOYU)
        c.setFont(KALIN, 12.5)
        c.drawString(k + 3 * mm, 6.4 * mm, self.unvan)
        c.setFillColor(GRI)
        c.setFont(YAZI, 7)
        c.drawString(k + 3 * mm, 2.4 * mm, self.alt_satir.upper())


def _ust_bilgi(ajans: Dict[str, Any], st: Dict[str, ParagraphStyle], dil: str) -> List[Any]:
    e = ETIKET[dil]
    unvan = (ajans.get("unvan") or "").strip()
    parcalar: List[Any] = [MarkaKunyesi("By Mehmet KURU Dev", "Full-stack & AI Systems"), Spacer(1, 2 * mm)]
    satirlar = []
    if unvan and unvan.lower() != "by mehmet kuru dev":
        satirlar.append(f"<b>{_metin(unvan)}</b>")
    if ajans.get("adres"):
        satirlar.append(_metin(ajans["adres"]))
    vergi = " / ".join(x for x in (ajans.get("vergi_dairesi"), ajans.get("vergi_no")) if x)
    if vergi:
        satirlar.append(f"{e['vergi']}: {_metin(vergi)}")
    iletisim = " · ".join(x for x in (ajans.get("eposta"), ajans.get("telefon")) if x)
    if iletisim:
        satirlar.append(_metin(iletisim))
    if ajans.get("iban"):
        satirlar.append(f"{e['iban']}: {_metin(ajans['iban'])}")
    if satirlar:
        parcalar.append(Paragraph("<br/>".join(satirlar), st["kucuk"]))
    return parcalar


def _baslik_blogu(
    sol: List[Any], baslik: str, bilgiler: Sequence[tuple], st: Dict[str, ParagraphStyle]
) -> Table:
    sag: List[Any] = [Paragraph(_metin(baslik), st["baslik"]), Spacer(1, 2 * mm)]
    for ad, deger in bilgiler:
        if deger in (None, ""):
            continue
        sag.append(Paragraph(f"<font color='#5B5368'>{_metin(ad)}:</font> <b>{_metin(deger)}</b>", st["sag"]))
    t = Table([[sol, sag]], colWidths=[105 * mm, 75 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    return t


def _ayrac() -> Drawing:
    d = Drawing(180 * mm, 3 * mm)
    d.add(Line(0, 1.5 * mm, 180 * mm, 1.5 * mm, strokeColor=VURGU, strokeWidth=1.2))
    return d


def _musteri_blogu(musteri: Dict[str, Any], st: Dict[str, ParagraphStyle], dil: str) -> List[Any]:
    e = ETIKET[dil]
    satirlar = [x for x in (musteri.get("ad"), musteri.get("eposta")) if x]
    if not satirlar:
        return []
    return [
        Paragraph(f"<font color='#5B5368'>{e['musteri']}</font>", st["kucuk"]),
        Paragraph("<br/>".join(_metin(x) for x in satirlar), st["kalin"]),
        Spacer(1, 4 * mm),
    ]


def _kalem_tablosu(kalemler: List[Dict[str, Any]], para_birimi: str, st, dil: str) -> Table:
    e = ETIKET[dil]
    basliklar = ["#", e["aciklama"], e["adet"], e["birim"], e["indirim"], e["kdv"], e["tutar"]]
    veri: List[List[Any]] = [[Paragraph(f"<b>{_metin(b)}</b>", st["govde"] if i < 2 else st["sag"]) for i, b in enumerate(basliklar)]]
    for i, k in enumerate(kalemler, 1):
        veri.append([
            Paragraph(str(i), st["govde"]),
            Paragraph(_metin(k.get("aciklama")), st["govde"]),
            Paragraph(sayi(k.get("adet")), st["sag"]),
            Paragraph(para(k.get("birim_fiyat"), para_birimi, dil), st["sag"]),
            Paragraph(sayi(k.get("indirim") or 0), st["sag"]),
            Paragraph(sayi(k.get("kdv_orani") or 0), st["sag"]),
            Paragraph(para(k.get("matrah"), para_birimi, dil), st["sag"]),
        ])
    t = Table(veri, colWidths=[8 * mm, 66 * mm, 14 * mm, 26 * mm, 16 * mm, 16 * mm, 34 * mm], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), VURGU_ACIK),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, VURGU),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, CIZGI),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _toplam_tablosu(satirlar: List[tuple], st) -> Table:
    veri = []
    for i, (ad, deger, kalin) in enumerate(satirlar):
        stil_ad = st["sag_kalin"] if kalin else st["sag"]
        veri.append([Paragraph(_metin(ad), stil_ad), Paragraph(_metin(deger), stil_ad)])
    t = Table(veri, colWidths=[118 * mm, 62 * mm])
    son = len(veri) - 1
    stil = [("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0)]
    for i, (_, _, kalin) in enumerate(satirlar):
        if kalin:
            stil.append(("LINEABOVE", (1, i), (1, i), 0.8, VURGU))
    if son >= 0:
        stil.append(("BOTTOMPADDING", (0, son), (-1, son), 3))
    t.setStyle(TableStyle(stil))
    return t


def _belge_toplamlari(ozet: Dict[str, Any], para_birimi: str, dil: str) -> List[tuple]:
    e = ETIKET[dil]
    satirlar: List[tuple] = []
    if ozet.get("indirim_toplam"):
        satirlar.append((e["indirim_toplam"], para(-abs(Decimal(str(ozet["indirim_toplam"]))), para_birimi, dil), False))
    satirlar.append((e["ara_toplam"], para(ozet.get("ara_toplam"), para_birimi, dil), False))
    for d in ozet.get("kdv_dokumu") or []:
        if not d.get("oran") and not d.get("kdv"):
            continue
        satirlar.append((e["kdv_satir"].format(oran=sayi(d.get("oran"))), para(d.get("kdv"), para_birimi, dil), False))
    satirlar.append((e["genel_toplam"], para(ozet.get("genel_toplam"), para_birimi, dil), True))
    return satirlar


def _sayfa_alti(not_metni: str, dil: str):
    e = ETIKET[dil]

    def ciz(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(CIZGI)
        canvas.setLineWidth(0.4)
        canvas.line(15 * mm, 14 * mm, 195 * mm, 14 * mm)
        canvas.setFont(YAZI, 7)
        canvas.setFillColor(GRI)
        canvas.drawString(15 * mm, 10 * mm, not_metni[:180])
        canvas.drawRightString(195 * mm, 10 * mm, f"{e['sayfa']} {doc.page}")
        canvas.restoreState()

    return ciz


def _uret(parcalar: List[Any], not_metni: str, dil: str, baslik: str) -> bytes:
    tampon = io.BytesIO()
    doc = SimpleDocTemplate(
        tampon,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=14 * mm,
        bottomMargin=20 * mm,
        title=baslik,
        author="By Mehmet KURU Dev",
        creator="mehmetkuru.dev",
    )
    alt = _sayfa_alti(not_metni, dil)
    doc.build(parcalar, onFirstPage=alt, onLaterPages=alt)
    return tampon.getvalue()


def _paragraf_blogu(baslik: str, metin: Optional[str], st) -> List[Any]:
    if not (metin or "").strip():
        return []
    return [Paragraph(_metin(baslik), st["bolum"]), Paragraph(_metin(metin.strip()), st["govde"])]


# ---------------------------------------------------------------------------
# Belgeler
# ---------------------------------------------------------------------------
def fatura_pdf(fatura: Dict[str, Any], ajans: Dict[str, Any], dil: str = "tr") -> bytes:
    """`fatura`: services/faturalar.fatura_ozeti çıktısı."""
    dil = _dil(dil)
    e = ETIKET[dil]
    st = _stiller()
    pb = fatura.get("currency") or "TRY"
    iade = fatura.get("tur") == "iade"
    baslik = e["iade_faturasi"] if iade else e["fatura"]
    bilgiler = [
        (e["no"], fatura.get("invoice_no")),
        (e["tarih"], tarih(fatura.get("issue_date"))),
        (e["vade"], tarih(fatura.get("due_date")) if fatura.get("due_date") else None),
        (e["donem"], fatura.get("donem")),
        (e["bagli_fatura"], fatura.get("bagli_fatura_no")),
    ]
    parcalar: List[Any] = [_baslik_blogu(_ust_bilgi(ajans, st, dil), baslik, bilgiler, st), _ayrac(), Spacer(1, 3 * mm)]
    parcalar += _musteri_blogu({"ad": fatura.get("client_name"), "eposta": fatura.get("client_email")}, st, dil)

    kalemler = fatura.get("kalemler") or []
    if not kalemler:
        # Eski tek tutarlı fatura: açıklama tek satır, KDV bilgisi yok.
        kalemler = [{
            "aciklama": fatura.get("description") or "—", "adet": 1, "birim_fiyat": fatura.get("amount"),
            "indirim": 0, "kdv_orani": 0, "matrah": fatura.get("amount"),
        }]
    elif fatura.get("description"):
        parcalar.append(Paragraph(_metin(fatura["description"]), st["govde"]))
        parcalar.append(Spacer(1, 2 * mm))
    parcalar.append(_kalem_tablosu(kalemler, pb, st, dil))
    parcalar.append(Spacer(1, 3 * mm))

    ozet = fatura.get("ozet") or {}
    if not fatura.get("kalemler"):
        ozet = {"ara_toplam": fatura.get("amount"), "genel_toplam": fatura.get("amount"), "kdv_dokumu": []}
    toplamlar = _belge_toplamlari(ozet, pb, dil)
    bakiye = fatura.get("bakiye") or {}
    if bakiye and not iade:
        if bakiye.get("iade_toplam"):
            toplamlar.append((e["iade"], para(-abs(Decimal(str(bakiye["iade_toplam"]))), pb, dil), False))
        toplamlar.append((e["odenen"], para(bakiye.get("odenen"), pb, dil), False))
        toplamlar.append((e["kalan"], para(bakiye.get("kalan"), pb, dil), True))
    parcalar.append(KeepTogether(_toplam_tablosu(toplamlar, st)))

    odemeler = [o for o in (fatura.get("odemeler") or []) if o.get("durum") in ("odendi", "iade")]
    if odemeler:
        parcalar.append(Paragraph(e["odemeler"], st["bolum"]))
        veri = []
        for o in odemeler:
            isaret = -1 if o.get("durum") == "iade" else 1
            veri.append([
                Paragraph(tarih(o.get("odeme_tarihi") or o.get("odendi_at")), st["govde"]),
                Paragraph(_metin(o.get("yontem_etiketi") or o.get("saglayici") or "—"), st["govde"]),
                Paragraph(para(isaret * float(o.get("tutar") or 0), pb, dil), st["sag"]),
            ])
        t = Table(veri, colWidths=[40 * mm, 90 * mm, 50 * mm])
        t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, CIZGI)]))
        parcalar.append(t)

    parcalar += _paragraf_blogu(e["notlar"], fatura.get("notlar"), st)
    return _uret(parcalar, E_FATURA_NOTU[dil], dil, f"{baslik} {fatura.get('invoice_no') or ''}")


def teklif_pdf(teklif: Dict[str, Any], ajans: Dict[str, Any], dil: str = "tr") -> bytes:
    dil = _dil(dil)
    e = ETIKET[dil]
    st = _stiller()
    pb = teklif.get("para_birimi") or "TRY"
    bilgiler = [
        (e["no"], teklif.get("no")),
        (e["tarih"], tarih(teklif.get("tarih"))),
        (e["gecerlilik"], tarih(teklif.get("gecerlilik")) if teklif.get("gecerlilik") else None),
        (e["surum"], str(teklif.get("surum")) if (teklif.get("surum") or 1) > 1 else None),
    ]
    parcalar: List[Any] = [_baslik_blogu(_ust_bilgi(ajans, st, dil), e["teklif"], bilgiler, st), _ayrac(), Spacer(1, 3 * mm)]
    parcalar += _musteri_blogu({"ad": teklif.get("musteri_ad"), "eposta": teklif.get("musteri_eposta")}, st, dil)
    parcalar.append(Paragraph(_metin(teklif.get("baslik")), st["h1"]))
    parcalar.append(_kalem_tablosu(teklif.get("kalemler") or [], pb, st, dil))
    parcalar.append(Spacer(1, 3 * mm))
    parcalar.append(KeepTogether(_toplam_tablosu(_belge_toplamlari(teklif.get("ozet") or {}, pb, dil), st)))
    parcalar += _paragraf_blogu(e["notlar"], teklif.get("notlar"), st)
    parcalar += _paragraf_blogu(e["sartlar"], teklif.get("sartlar"), st)
    if teklif.get("karar_ad") and teklif.get("durum") == "kabul":
        parcalar.append(Spacer(1, 4 * mm))
        parcalar.append(Paragraph(
            f"{e['kabul']}: <b>{_metin(teklif['karar_ad'])}</b> · {e['kabul_zamani']}: {_metin(teklif.get('karar_at') or '—')}",
            st["kucuk"],
        ))
    return _uret(parcalar, E_FATURA_NOTU[dil], dil, f"{e['teklif']} {teklif.get('no') or ''}")


_MD_BASLIK = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_MD_MADDE = re.compile(r"^\s*[-*+•]\s+(.*)$")
_MD_SIRALI = re.compile(r"^\s*(\d{1,3})[.)]\s+(.*)$")


def _satir_ici(metin: str) -> str:
    """Kaçışlı metinde **kalın** ve *eğik* (eğik → düz; italik yazı tipi yok)."""
    m = escape(metin)
    m = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", m)
    m = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"\1", m)
    return m


def markdown_parcalari(metin: str, st) -> List[Any]:
    """Sözleşme gövdesi için küçük, güvenli Markdown → paragraf dönüşümü.

    Ham HTML hiçbir zaman yorumlanmıyor (önce kaçış). Desteklenen: başlık,
    madde/numaralı liste, paragraf, **kalın**.
    """
    parcalar: List[Any] = []
    paragraf: List[str] = []

    def bosalt():
        if paragraf:
            parcalar.append(Paragraph("<br/>".join(_satir_ici(s) for s in paragraf), st["govde"]))
            parcalar.append(Spacer(1, 2 * mm))
            paragraf.clear()

    for satir in (metin or "").replace("\r\n", "\n").split("\n"):
        if not satir.strip():
            bosalt()
            continue
        b = _MD_BASLIK.match(satir)
        if b:
            bosalt()
            parcalar.append(Paragraph(_satir_ici(b.group(2)), st["h1"] if len(b.group(1)) == 1 else st["h2"]))
            continue
        m = _MD_MADDE.match(satir)
        if m:
            bosalt()
            parcalar.append(Paragraph(_satir_ici(m.group(1)), st["madde"], bulletText="•"))
            continue
        s = _MD_SIRALI.match(satir)
        if s:
            bosalt()
            parcalar.append(Paragraph(_satir_ici(s.group(2)), st["madde"], bulletText=f"{s.group(1)}."))
            continue
        paragraf.append(satir.strip())
    bosalt()
    return parcalar


def sozlesme_pdf(
    sozlesme: Dict[str, Any], ajans: Dict[str, Any], imza_png: Optional[bytes] = None, dil: str = "tr"
) -> bytes:
    """İmzalıysa metin + imza bloğu + doğrulama özeti; değilse yalnız metin."""
    dil = _dil(dil)
    e = ETIKET[dil]
    st = _stiller()
    bilgiler = [
        (e["no"], sozlesme.get("no")),
        (e["surum"], str(sozlesme.get("surum") or 1)),
        (e["baslangic"], tarih(sozlesme.get("baslangic")) if sozlesme.get("baslangic") else None),
        (e["bitis"], tarih(sozlesme.get("bitis")) if sozlesme.get("bitis") else None),
    ]
    parcalar: List[Any] = [_baslik_blogu(_ust_bilgi(ajans, st, dil), e["sozlesme"], bilgiler, st), _ayrac(), Spacer(1, 3 * mm)]
    parcalar += _musteri_blogu({"ad": sozlesme.get("taraf_ad"), "eposta": sozlesme.get("taraf_eposta")}, st, dil)
    parcalar.append(Paragraph(_metin(sozlesme.get("baslik")), st["h1"]))
    parcalar += markdown_parcalari(sozlesme.get("govde") or "", st)

    blok: List[Any] = [Spacer(1, 4 * mm), Paragraph(e["imza"], st["bolum"])]
    if sozlesme.get("imza_at"):
        if imza_png:
            try:
                okuyucu = ImageReader(io.BytesIO(imza_png))
                gen, yuk = okuyucu.getSize()
                en = 60 * mm
                boy = min(25 * mm, en * yuk / max(gen, 1))
                en = boy * gen / max(yuk, 1)
                blok.append(Image(io.BytesIO(imza_png), width=en, height=boy, hAlign="LEFT"))
            except Exception:  # noqa: BLE001 - bozuk görsel PDF'i düşürmesin
                logger.warning("İmza görseli PDF'e eklenemedi")
        else:
            blok.append(Paragraph(e["cizim_yok"], st["kucuk"]))
        satirlar = [
            (e["imzalayan"], sozlesme.get("imza_ad")),
            (e["imza_zamani"], sozlesme.get("imza_at")),
            (e["ip"], (sozlesme.get("imza_ip_ozeti") or "")[:16] + "…" if sozlesme.get("imza_ip_ozeti") else "—"),
            (e["tarayici"], (sozlesme.get("imza_tarayici") or "—")[:120]),
            (e["metin_ozeti"], sozlesme.get("imza_metin_ozeti")),
        ]
        veri = [[Paragraph(_metin(a), st["kucuk"]), Paragraph(_metin(d), st["ozet"] if a == e["metin_ozeti"] else st["kucuk"])]
                for a, d in satirlar]
        t = Table(veri, colWidths=[42 * mm, 138 * mm])
        t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, CIZGI), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        blok.append(t)
    else:
        blok.append(Paragraph(e["imzalanmadi"], st["kucuk"]))
    blok.append(Spacer(1, 3 * mm))
    blok.append(Paragraph(_metin(IMZA_NOTU[dil]), st["kucuk"]))
    parcalar.append(KeepTogether(blok))
    return _uret(parcalar, IMZA_NOTU[dil], dil, f"{e['sozlesme']} {sozlesme.get('no') or ''}")


def pdf_metni(veri: bytes) -> str:
    """Testler için: PDF'ten metin (pypdf). Kurulu değilse ImportError."""
    from pypdf import PdfReader

    okuyucu = PdfReader(io.BytesIO(veri))
    return "\n".join((s.extract_text() or "") for s in okuyucu.pages)


def dosya_adi(onek: str, no: Optional[str]) -> str:
    temiz = re.sub(r"[^A-Za-z0-9._-]+", "-", (no or "").strip()).strip("-") or "belge"
    return f"{onek}-{temiz}.pdf"

