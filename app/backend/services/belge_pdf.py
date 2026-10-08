"""Faz 5B — belge ve strateji şablonu PDF'i (ReportLab; Faz 3T altyapısı: yazı tipi, renk, künye).

* Belge: Markdown gövde sunucuda paragraf/tablo/liste parçalarına çevriliyor; ham HTML
  hiçbir zaman yorumlanmıyor (önce kaçış). Yapılacak maddesinin kutusu vektörle
  çiziliyor (☐ / ☑ Plus Jakarta Sans'ta yok; ZapfDingbats gömülmediği için her
  okuyucuda aynı görünmüyor).
* Strateji: şablonun ızgarası (`STRATEJI_SABLONLARI`) tablo + birleştirilmiş hücrelerle
  korunuyor; kanvaslar yatay A4.
* Faz 7K: metin `services/pdf_yazi.py`'nin yazı tipi zincirinden geçiyor (Kiril, Arapça — birleşik
  biçim + sağdan sola —, Devanagari, Çince); etiketler ve strateji şablonu adları 7 dilde.
"""

import io
import re
from typing import Any, Dict, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Flowable, SimpleDocTemplate, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

from services import pdf_belge as pb
from services.pdf_yazi import Paragraf as Paragraph  # çok dilli paragraf
from services.pdf_yazi import kod_blogu, metin_ciz
from services.belgeler import STRATEJI_SABLONLARI, kutu_adi, pdf_dili, sablon_adi

ETIKET: Dict[str, Dict[str, str]] = {
    "tr": {"belge": "BELGE", "surum": "Sürüm", "guncellendi": "Güncellendi", "etiketler": "Etiketler",
           "musteri": "Müşteri", "proje": "Proje", "isletme": "İşletme", "sayfa": "Sayfa", "ajans": "Ajans içi"},
    "en": {"belge": "DOCUMENT", "surum": "Version", "guncellendi": "Updated", "etiketler": "Tags",
           "musteri": "Client", "proje": "Project", "isletme": "Business", "sayfa": "Page", "ajans": "Internal"},
    "de": {"belge": "DOKUMENT", "surum": "Version", "guncellendi": "Aktualisiert", "etiketler": "Schlagwörter",
           "musteri": "Kunde", "proje": "Projekt", "isletme": "Unternehmen", "sayfa": "Seite", "ajans": "Intern"},
    "ru": {"belge": "ДОКУМЕНТ", "surum": "Версия", "guncellendi": "Обновлено", "etiketler": "Теги",
           "musteri": "Клиент", "proje": "Проект", "isletme": "Компания", "sayfa": "Стр.", "ajans": "Внутренний"},
    "zh": {"belge": "文档", "surum": "版本", "guncellendi": "更新于", "etiketler": "标签", "musteri": "客户",
           "proje": "项目", "isletme": "企业", "sayfa": "页", "ajans": "内部"},
    "hi": {"belge": "दस्तावेज़", "surum": "संस्करण", "guncellendi": "अद्यतन", "etiketler": "टैग", "musteri": "ग्राहक",
           "proje": "परियोजना", "isletme": "व्यवसाय", "sayfa": "पृष्ठ", "ajans": "आंतरिक"},
    "ar": {"belge": "مستند", "surum": "الإصدار", "guncellendi": "آخر تحديث", "etiketler": "الوسوم", "musteri": "العميل",
           "proje": "المشروع", "isletme": "النشاط التجاري", "sayfa": "صفحة", "ajans": "داخلي"},
}

#: Yazı tipinde olmayan sık işaretler → karşılığı olan glif.
_GLIF = str.maketrans({"→": "»", "←": "«", "☐": "", "☑": "", "✓": "", "✔": ""})


def _stiller() -> Dict[str, ParagraphStyle]:
    st = pb._stiller()  # noqa: SLF001 - Faz 3T ortak stilleri (yazı tipini de kaydeder)
    st["kutu_baslik"] = ParagraphStyle("kutu_baslik", fontName=pb.KALIN, fontSize=9, leading=12, textColor=pb.VURGU,
                                       spaceAfter=2)
    st["kutu"] = ParagraphStyle("kutu", fontName=pb.YAZI, fontSize=8.5, leading=11.5, textColor=pb.KOYU)
    st["alinti"] = ParagraphStyle("alinti", parent=st["govde"], leftIndent=10, textColor=pb.GRI)
    st["kod"] = ParagraphStyle("kod", fontName="Courier", fontSize=8, leading=10, textColor=pb.KOYU,
                               backColor=colors.HexColor("#F4F2F7"), borderPadding=4, leftIndent=4, spaceBefore=3,
                               spaceAfter=6)
    st["h3"] = ParagraphStyle("h3", fontName=pb.KALIN, fontSize=10, leading=14, textColor=pb.KOYU, spaceBefore=6,
                              spaceAfter=2)
    return st


class KutuIsareti(Flowable):
    """Yapılacak maddesinin onay kutusu (işaretliyse içinde tik)."""

    def __init__(self, tamam: bool):
        super().__init__()
        self.tamam = tamam
        self.width = 3.2 * mm
        self.height = 3.2 * mm

    def draw(self) -> None:
        c = self.canv
        c.setStrokeColor(pb.VURGU if self.tamam else pb.GRI)
        c.setLineWidth(0.8)
        c.roundRect(0, 0, self.width, self.height, 0.6 * mm, stroke=1, fill=0)
        if self.tamam:
            c.setStrokeColor(pb.VURGU)
            c.setLineWidth(1.1)
            p = c.beginPath()
            p.moveTo(0.7 * mm, 1.7 * mm)
            p.lineTo(1.4 * mm, 0.8 * mm)
            p.lineTo(2.6 * mm, 2.5 * mm)
            c.drawPath(p, stroke=1, fill=0)


def _yapilacak_satiri(icerik: str, tamam: bool, st: Dict[str, ParagraphStyle], genislik: float) -> Table:
    t = Table([[KutuIsareti(tamam), Paragraph(f"<strike>{icerik}</strike>" if tamam else icerik, st["govde"])]],
              colWidths=[6 * mm, genislik - 6 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("TOPPADDING", (0, 0), (0, 0), 2.5), ("TOPPADDING", (1, 0), (1, 0), 0),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    return t


def _metin(s: Any) -> str:
    return escape(str(s or "").translate(_GLIF))


_KOD = re.compile(r"`([^`\n]+)`")
_BAGLANTI = re.compile(r"!?\[([^\]\n]+)\]\(((?:[^()\s]|\([^()\s]*\))+)(?:\s+\"[^\"]*\")?\)")


def _satir_ici(metin: str) -> str:
    """Kaçışlı paragraf metni: **kalın**, *eğik* (düz), `kod`, [bağlantı](http…)."""
    saklanan: List[str] = []

    def sakla(p: str) -> str:
        saklanan.append(p)
        return f"\x00{len(saklanan) - 1}\x00"

    metin = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", metin or "")
    metin = _KOD.sub(lambda m: sakla(f'<font face="Courier">{_metin(m.group(1))}</font>'), metin)

    def baglanti(m: "re.Match[str]") -> str:
        from services.guvenli_html import url_guvenli_mi

        yazi, adres = m.group(1), m.group(2)
        if m.group(0).startswith("!"):
            return sakla(f"[{_metin(yazi)}]")
        if re.match(r"^(https?:|mailto:)", adres, re.I) and url_guvenli_mi(adres):
            return sakla(f'<link href="{escape(adres, {chr(34): "&quot;"})}" color="#00A86B">{_metin(yazi)}</link>')
        return sakla(_metin(yazi))

    metin = _BAGLANTI.sub(baglanti, metin)
    metin = _metin(metin)
    metin = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: f"<b>{m.group(1) or m.group(2)}</b>", metin)
    metin = re.sub(r"~~(.+?)~~", r"<strike>\1</strike>", metin)
    return re.sub(r"\x00(\d+)\x00", lambda m: saklanan[int(m.group(1))], metin)


def _hucreler(satir: str) -> List[str]:
    s = satir.strip().strip("|")
    return [h.strip() for h in s.split("|")]


_TABLO_AYRAC = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?$")


def markdown_parcalari(md: str, st: Dict[str, ParagraphStyle], genislik: float) -> List[Any]:
    satirlar = (md or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    parcalar: List[Any] = []
    paragraf: List[str] = []
    i, n = 0, len(satirlar)

    def bosalt() -> None:
        if paragraf:
            parcalar.append(Paragraph("<br/>".join(_satir_ici(s) for s in paragraf), st["govde"]))
            parcalar.append(Spacer(1, 2 * mm))
            paragraf.clear()

    while i < n:
        yalin = satirlar[i].strip()
        if yalin.startswith("```"):
            bosalt()
            kod: List[str] = []
            i += 1
            while i < n and not satirlar[i].strip().startswith("```"):
                kod.append(satirlar[i])
                i += 1
            parcalar.append(kod_blogu("\n".join(kod).translate(_GLIF), st["kod"]))
            i += 1
            continue
        if not yalin:
            bosalt()
            i += 1
            continue
        b = re.match(r"^(#{1,6})\s+(.*?)\s*#*$", yalin)
        if b:
            bosalt()
            seviye = len(b.group(1))
            parcalar.append(Paragraph(_satir_ici(b.group(2)), st["h1" if seviye == 1 else "h2" if seviye == 2 else "h3"]))
            i += 1
            continue
        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", yalin):
            bosalt()
            parcalar.append(pb._ayrac())  # noqa: SLF001
            i += 1
            continue
        if yalin.startswith("|") and i + 1 < n and _TABLO_AYRAC.match(satirlar[i + 1].strip()):
            bosalt()
            basliklar = _hucreler(yalin)
            veri = [[Paragraph(f"<b>{_satir_ici(h)}</b>", st["kutu"]) for h in basliklar]]
            i += 2
            while i < n and satirlar[i].strip().startswith("|"):
                h = (_hucreler(satirlar[i]) + [""] * len(basliklar))[: len(basliklar)]
                veri.append([Paragraph(_satir_ici(x), st["kutu"]) for x in h])
                i += 1
            t = Table(veri, colWidths=[genislik / max(1, len(basliklar))] * len(basliklar), repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), pb.VURGU_ACIK),
                ("GRID", (0, 0), (-1, -1), 0.4, pb.CIZGI),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            parcalar += [t, Spacer(1, 3 * mm)]
            continue
        g = re.match(r"^[-*+]\s+\[( |x|X)\]\s+(.*)$", yalin)
        if g:
            bosalt()
            tamam = g.group(1) in ("x", "X")
            icerik = _satir_ici(g.group(2))
            parcalar.append(_yapilacak_satiri(icerik, tamam, st, genislik))
            i += 1
            continue
        m = re.match(r"^[-*+•]\s+(.*)$", yalin)
        if m:
            bosalt()
            parcalar.append(Paragraph(_satir_ici(m.group(1)), st["madde"], bulletText="•"))
            i += 1
            continue
        s = re.match(r"^(\d{1,3})[.)]\s+(.*)$", yalin)
        if s:
            bosalt()
            parcalar.append(Paragraph(_satir_ici(s.group(2)), st["madde"], bulletText=f"{s.group(1)}."))
            i += 1
            continue
        if yalin.startswith(">"):
            bosalt()
            parcalar.append(Paragraph(_satir_ici(yalin[1:].strip()), st["alinti"]))
            i += 1
            continue
        paragraf.append(yalin)
        i += 1
    bosalt()
    return parcalar


def _kutu_metni(metin: str) -> str:
    satirlar = []
    for s in (metin or "").split("\n"):
        s = s.strip()
        if not s:
            continue
        m = re.match(r"^[-*+•]\s+(.*)$", s)
        satirlar.append(f"• {_satir_ici(m.group(1))}" if m else _satir_ici(s))
    return "<br/>".join(satirlar) or "&nbsp;"


def strateji_tablosu(tur: str, veri: Dict[str, Any], dil: str, st: Dict[str, ParagraphStyle], genislik: float,
                     punto: float = 8.5) -> Table:
    """Şablonun ızgarası: kutu = (birleştirilmiş) hücre, çerçeve marka yeşili."""
    sablon = STRATEJI_SABLONLARI[tur]
    kutular = veri.get("kutular") or {}
    metin_stili = ParagraphStyle(f"kutu{punto}", parent=st["kutu"], fontSize=punto, leading=punto * 1.35)
    hucreler: List[List[Any]] = [["" for _ in range(sablon.sutun)] for _ in range(sablon.satir)]
    stil: List[Any] = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]
    for k in sablon.kutular:
        x, y = k.sutun - 1, k.satir - 1
        hucreler[y][x] = [
            Paragraph(_metin(kutu_adi(tur, k.anahtar, dil)), st["kutu_baslik"]),
            Paragraph(_kutu_metni(kutular.get(k.anahtar, "")), metin_stili),
        ]
        x2, y2 = x + k.en - 1, y + k.boy - 1
        if k.en > 1 or k.boy > 1:
            stil.append(("SPAN", (x, y), (x2, y2)))
        stil.append(("BOX", (x, y), (x2, y2), 0.8, pb.VURGU))
        if k.anahtar in VURGULU_KUTULAR:
            stil.append(("BACKGROUND", (x, y), (x2, y2), pb.VURGU_ACIK))
    # Boş kutular da kanvas gibi görünsün: satır başına en az yükseklik.
    en_az = (20 if sablon.satir >= 3 else 30) * mm
    t = Table(hucreler, colWidths=[genislik / sablon.sutun] * sablon.sutun)
    t.setStyle(TableStyle(stil))
    _, yukseklik = t.wrap(genislik, 10_000)
    satir_boylari = list(getattr(t, "_rowHeights", []) or [])
    if satir_boylari and any(h < en_az for h in satir_boylari):
        t = Table(hucreler, colWidths=[genislik / sablon.sutun] * sablon.sutun,
                  rowHeights=[max(h, en_az) for h in satir_boylari])
        t.setStyle(TableStyle(stil))
    return t


def strateji_listesi(tur: str, veri: Dict[str, Any], dil: str, st: Dict[str, ParagraphStyle]) -> List[Any]:
    """Izgara sayfaya sığmayacak kadar doluysa: kutu kutu akan liste (sayfalara bölünebilir)."""
    parcalar: List[Any] = []
    for k in STRATEJI_SABLONLARI[tur].kutular:
        parcalar.append(Paragraph(_metin(kutu_adi(tur, k.anahtar, dil)), st["h2"]))
        parcalar.append(Paragraph(_kutu_metni((veri.get("kutular") or {}).get(k.anahtar, "")), st["govde"]))
    return parcalar


VURGULU_KUTULAR = frozenset({"ikigai", "ortak_degerler", "rekabet", "deger", "deger_onerisi"})


def _buyuk(s: str, dil: str) -> str:
    """Türkçede i → İ, ı → I (Python'un upper()'ı "analizi"yi "ANALIZI" yapar)."""
    if dil == "tr":
        s = s.replace("i", "İ").replace("ı", "I")
    return s.upper()


def _sayfa_alti(not_metni: str, dil: str, sayfa_boyu):
    e = ETIKET[dil]

    def ciz(canvas, doc):
        canvas.saveState()
        genislik = sayfa_boyu[0]
        canvas.setStrokeColor(pb.CIZGI)
        canvas.setLineWidth(0.4)
        canvas.line(15 * mm, 12 * mm, genislik - 15 * mm, 12 * mm)
        canvas.setFillColor(pb.GRI)
        metin_ciz(canvas, 15 * mm, 8 * mm, not_metni.translate(_GLIF)[:150], pb.YAZI, 7)
        metin_ciz(canvas, genislik - 15 * mm, 8 * mm, f"{e['sayfa']} {doc.page}", pb.YAZI, 7, "sag")
        canvas.restoreState()

    return ciz


def belge_pdf(v: Dict[str, Any], dil: str = "tr") -> bytes:
    """`v`: {baslik, tur, icerik (belge) | strateji {isletme, kutular}, surum, guncellendi, etiketler,
    musteri, proje}."""
    dil = pdf_dili(dil)
    e = ETIKET[dil]
    st = _stiller()
    tur = v.get("tur") or "belge"
    strateji = tur in STRATEJI_SABLONLARI
    sayfa = landscape(A4) if strateji and STRATEJI_SABLONLARI[tur].yatay else A4
    genislik = sayfa[0] - 30 * mm
    tip = _buyuk(sablon_adi(tur, dil), dil) if strateji else e["belge"]
    bilgiler = [
        (e["surum"], str(v.get("surum") or 1)),
        (e["guncellendi"], pb.tarih(v.get("guncellendi"))),
        (e["musteri"], v.get("musteri")),
        (e["proje"], v.get("proje")),
    ]
    sag: List[Any] = [Paragraph(_metin(tip), ParagraphStyle("tip", parent=st["baslik"], fontSize=14, leading=18))]
    for ad, deger in bilgiler:
        if deger:
            sag.append(Paragraph(f"<font color='#5B5368'>{_metin(ad)}:</font> <b>{_metin(deger)}</b>", st["sag"]))
    ust = Table([[[pb.MarkaKunyesi("By Mehmet KURU Dev", "Full-stack & AI Systems")], sag]],
                colWidths=[genislik * 0.55, genislik * 0.45])
    ust.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    cizgi = Table([[""]], colWidths=[genislik], rowHeights=[2 * mm])
    cizgi.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 1.2, pb.VURGU)]))
    parcalar: List[Any] = [ust, cizgi, Spacer(1, 3 * mm), Paragraph(_metin(v.get("baslik")), st["h1"])]
    etiketler = [x for x in (v.get("etiketler") or []) if x]
    if etiketler:
        parcalar.append(Paragraph(f"{_metin(e['etiketler'])}: " + _metin(", ".join(etiketler)), st["kucuk"]))
        parcalar.append(Spacer(1, 2 * mm))
    if strateji:
        veri = v.get("strateji") or {}
        if (veri.get("isletme") or "").strip():
            parcalar.append(Paragraph(f"<b>{_metin(e['isletme'])}:</b> {_satir_ici(veri['isletme'])}", st["govde"]))
            parcalar.append(Spacer(1, 3 * mm))
        # Izgara tek sayfaya sığmalı (birleştirilmiş hücreler sayfa arasında bölünemiyor): önce
        # punto küçülterek dene, yine sığmazsa kutu kutu akan listeye düş.
        kalan = sayfa[1] - 30 * mm - 12 - sum(p.wrap(genislik, sayfa[1])[1] for p in parcalar)
        secilen: List[Any] = []
        for punto in (8.5, 7.5, 6.5):
            t = strateji_tablosu(tur, veri, dil, st, genislik, punto)
            if t.wrap(genislik, sayfa[1])[1] <= kalan:
                secilen = [t]
                break
        parcalar += secilen or strateji_listesi(tur, veri, dil, st)
    else:
        parcalar += markdown_parcalari(v.get("icerik") or "", st, genislik)
    tampon = io.BytesIO()
    doc = SimpleDocTemplate(tampon, pagesize=sayfa, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=12 * mm,
                            bottomMargin=18 * mm, title=str(v.get("baslik") or ""), author="By Mehmet KURU Dev",
                            creator="mehmetkuru.dev")
    alt = _sayfa_alti(f"mehmetkuru.dev — {v.get('baslik') or ''}", dil, sayfa)
    doc.build(parcalar, onFirstPage=alt, onLaterPages=alt)
    return tampon.getvalue()


def pdf_metni(veri: bytes) -> str:
    return pb.pdf_metni(veri)

