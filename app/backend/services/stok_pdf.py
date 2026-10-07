"""Faz 6P — satış fişi (80 mm termal) ve satıştan bilgi amaçlı fatura PDF'i (ReportLab; Faz 3T altyapısı).

Belgeler İŞLETMENİN (ajansın müşterisinin) belgesi: başlıkta işletmenin künyesi, ajansın markası yok.
Yazı tipi yalnız Latin harflerini taşıyor (Plus Jakarta Sans): tr / en / de; diğer dillerde İngilizce.

Yasal ibare (her belgede): fiş MALİ DEĞİLDİR (ÖKC fişi / e-Arşiv belge yerine geçmez); fatura bilgi
amaçlıdır (e-Fatura / e-Arşiv fatura yerine geçmez). Kart ödemesi yalnız kayıttır.
"""

import io
from typing import Any, Dict, List, Optional

from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from services import pdf_belge as pb

ETIKET: Dict[str, Dict[str, str]] = {
    "tr": {
        "fis": "SATIŞ FİŞİ", "no": "Fiş no", "tarih": "Tarih", "kasiyer": "Kasiyer", "musteri": "Müşteri",
        "ara_toplam": "Ara toplam", "indirim": "İndirim", "toplam": "TOPLAM", "kdv": "KDV %{oran}", "kdv_toplam": "Toplam KDV",
        "nakit": "Nakit", "kart": "Kart", "havale": "Havale", "alinan": "Alınan", "para_ustu": "Para üstü",
        "iade": "İade edilen", "iptal": "İPTAL EDİLDİ",
        "mali_degil": "BU BELGE MALİ FİŞ DEĞİLDİR. ÖKC fişi / e-Arşiv belge yerine geçmez.",
        "kart_notu": "Kart ödemesi yalnız kayıttır.",
        "fatura": "SATIŞ FATURASI", "fatura_no": "Fatura no", "fatura_tarihi": "Fatura tarihi", "ilgili_fis": "İlgili fiş",
        "alici": "Alıcı", "vergi": "Vergi dairesi / no", "aciklama": "Açıklama", "miktar": "Miktar", "birim_fiyat": "Birim fiyat (KDV dahil)",
        "oran": "KDV %", "tutar": "Tutar", "matrah": "Matrah", "genel_toplam": "Genel toplam (KDV dahil)", "odeme": "Ödeme",
        "fatura_notu": "Bu belge bilgi amaçlıdır; e-Fatura/e-Arşiv fatura yerine geçmez.",
    },
    "en": {
        "fis": "SALES RECEIPT", "no": "Receipt no", "tarih": "Date", "kasiyer": "Cashier", "musteri": "Customer",
        "ara_toplam": "Subtotal", "indirim": "Discount", "toplam": "TOTAL", "kdv": "VAT {oran}%", "kdv_toplam": "Total VAT",
        "nakit": "Cash", "kart": "Card", "havale": "Bank transfer", "alinan": "Received", "para_ustu": "Change",
        "iade": "Refunded", "iptal": "VOIDED",
        "mali_degil": "THIS IS NOT A FISCAL RECEIPT. It does not replace a fiscal cash register receipt or e-Archive document.",
        "kart_notu": "Card payment is recorded only.",
        "fatura": "SALES INVOICE", "fatura_no": "Invoice no", "fatura_tarihi": "Invoice date", "ilgili_fis": "Related receipt",
        "alici": "Bill to", "vergi": "Tax office / no", "aciklama": "Description", "miktar": "Qty", "birim_fiyat": "Unit price (VAT incl.)",
        "oran": "VAT %", "tutar": "Amount", "matrah": "Net", "genel_toplam": "Total (VAT incl.)", "odeme": "Payment",
        "fatura_notu": "This document is for information only; it does not replace an e-Invoice/e-Archive invoice.",
    },
    "de": {
        "fis": "KASSENBON", "no": "Bon-Nr.", "tarih": "Datum", "kasiyer": "Kassierer", "musteri": "Kunde",
        "ara_toplam": "Zwischensumme", "indirim": "Rabatt", "toplam": "SUMME", "kdv": "MwSt. {oran} %", "kdv_toplam": "MwSt. gesamt",
        "nakit": "Bar", "kart": "Karte", "havale": "Überweisung", "alinan": "Gegeben", "para_ustu": "Rückgeld",
        "iade": "Erstattet", "iptal": "STORNIERT",
        "mali_degil": "KEIN FISKALBELEG. Ersetzt weder einen Registrierkassenbeleg noch ein e-Archiv-Dokument.",
        "kart_notu": "Kartenzahlung wird nur erfasst.",
        "fatura": "RECHNUNG", "fatura_no": "Rechnungs-Nr.", "fatura_tarihi": "Rechnungsdatum", "ilgili_fis": "Zugehöriger Bon",
        "alici": "Rechnungsempfänger", "vergi": "Finanzamt / Steuer-Nr.", "aciklama": "Beschreibung", "miktar": "Menge",
        "birim_fiyat": "Einzelpreis (inkl. MwSt.)", "oran": "MwSt. %", "tutar": "Betrag", "matrah": "Netto",
        "genel_toplam": "Gesamt (inkl. MwSt.)", "odeme": "Zahlung",
        "fatura_notu": "Dieses Dokument dient nur zur Information und ersetzt keine E-Rechnung/e-Archiv-Rechnung.",
    },
}


def pdf_dili(dil: Optional[str]) -> str:
    d = (dil or "tr")[:2].lower()
    return d if d in ETIKET else "en"


def _m(deger: Any) -> str:
    return pb._metin(deger)  # noqa: SLF001 - Faz 3T ortak yardımcısı


def _para(kurus: int, para_birimi: str, dil: str) -> str:
    return pb.para((kurus or 0) / 100, para_birimi, "tr" if dil in ("tr", "de") else "en")


def _miktar(binde: int, birim: str) -> str:
    deger = pb.sayi((binde or 0) / 1000)
    return deger if birim == "adet" else f"{deger} {birim}"


# ---------------------------------------------------------------------------
# Fiş (80 mm)
# ---------------------------------------------------------------------------
def fis_pdf(v: Dict[str, Any], dil: str = "tr") -> bytes:
    """`v`: routers/stok_pos._satis_ayrintisi çıktısı + `firma` künyesi."""
    dil = pdf_dili(dil)
    e = ETIKET[dil]
    pb.fontlari_kaydet()
    pb_ = v.get("para_birimi") or "TRY"
    kucuk = ParagraphStyle("fk", fontName=pb.YAZI, fontSize=7.5, leading=9.5)
    govde = ParagraphStyle("fg", fontName=pb.YAZI, fontSize=8.5, leading=11)
    orta = ParagraphStyle("fo", parent=govde, alignment=TA_CENTER)
    baslik = ParagraphStyle("fb", fontName=pb.KALIN, fontSize=11, leading=14, alignment=TA_CENTER)
    kalin = ParagraphStyle("fkl", fontName=pb.KALIN, fontSize=10, leading=13)
    genislik = 72 * mm

    def satir(sol: str, sag: str, stil=govde) -> Table:
        t = Table([[Paragraph(sol, stil), Paragraph(sag, ParagraphStyle("s", parent=stil, alignment=2))]],
                  colWidths=[genislik * 0.62, genislik * 0.38])
        t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                               ("TOPPADDING", (0, 0), (-1, -1), 0.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 0.5),
                               ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        return t

    def cizgi() -> Paragraph:
        return Paragraph("- " * 34, kucuk)

    f = v.get("firma") or {}
    parcalar: List[Any] = []
    if f.get("ad"):
        parcalar.append(Paragraph(f"<b>{_m(f['ad'])}</b>", baslik))
    for alan in ("adres", "telefon"):
        if f.get(alan):
            parcalar.append(Paragraph(_m(f[alan]), orta))
    vergi = " / ".join(x for x in (f.get("vergi_dairesi"), f.get("vergi_no")) if x)
    if vergi:
        parcalar.append(Paragraph(_m(vergi), orta))
    parcalar += [Spacer(1, 1.5 * mm), Paragraph(f"<b>{_m(e['fis'])}</b>", orta), cizgi()]
    parcalar.append(satir(f"{_m(e['no'])}: <b>{_m(v.get('no'))}</b>", _m(v.get("tarih_metni") or "")))
    if v.get("kasiyer"):
        parcalar.append(Paragraph(f"{_m(e['kasiyer'])}: {_m(v['kasiyer'])}", kucuk))
    if v.get("musteri_ad"):
        parcalar.append(Paragraph(f"{_m(e['musteri'])}: {_m(v['musteri_ad'])}", kucuk))
    parcalar.append(cizgi())
    for k in v.get("kalemler") or []:
        parcalar.append(Paragraph(_m(k.get("ad")), govde))
        detay = f"{_m(_miktar(k['adet_binde'], k.get('birim') or 'adet'))} × {_m(_para(k['birim_fiyat'], pb_, dil))}  %{k.get('kdv_orani')}"
        parcalar.append(satir(detay, _m(_para(k["brut"], pb_, dil)), kucuk))
        if k.get("satir_indirim"):
            parcalar.append(satir(f"  {_m(e['indirim'])}", "−" + _m(_para(k["satir_indirim"], pb_, dil)), kucuk))
    parcalar.append(cizgi())
    if v.get("toplam_indirim"):
        ara = int(v.get("ara_toplam") or 0) - int(v.get("satir_indirim") or 0)
        parcalar.append(satir(_m(e["ara_toplam"]), _m(_para(ara, pb_, dil))))
        parcalar.append(satir(_m(e["indirim"]), "−" + _m(_para(v["toplam_indirim"], pb_, dil))))
    parcalar.append(satir(f"<b>{_m(e['toplam'])}</b>", f"<b>{_m(_para(v.get('toplam') or 0, pb_, dil))}</b>", kalin))
    for d in v.get("kdv_dokumu") or []:
        if d.get("kdv"):
            parcalar.append(satir(_m(e["kdv"].format(oran=d["oran"])), _m(_para(d["kdv"], pb_, dil)), kucuk))
    parcalar.append(satir(_m(e["kdv_toplam"]), _m(_para(v.get("kdv_toplam") or 0, pb_, dil)), kucuk))
    parcalar.append(cizgi())
    for tur in ("nakit", "kart", "havale"):
        if v.get(tur):
            parcalar.append(satir(_m(e[tur]), _m(_para(v[tur], pb_, dil))))
    if v.get("nakit") and v.get("para_ustu"):
        parcalar.append(satir(_m(e["alinan"]), _m(_para(v.get("nakit_alinan") or 0, pb_, dil))))
        parcalar.append(satir(_m(e["para_ustu"]), _m(_para(v.get("para_ustu") or 0, pb_, dil))))
    if v.get("iade_toplam"):
        parcalar.append(satir(_m(e["iade"]), "−" + _m(_para(v["iade_toplam"], pb_, dil))))
    if v.get("durum") == "iptal":
        parcalar.append(Paragraph(f"<b>{_m(e['iptal'])}</b>", baslik))
    parcalar.append(cizgi())
    if f.get("fis_notu"):
        parcalar.append(Paragraph(_m(f["fis_notu"]), orta))
    if v.get("kart"):
        parcalar.append(Paragraph(_m(e["kart_notu"]), ParagraphStyle("kn", parent=kucuk, alignment=TA_CENTER)))
    parcalar.append(Paragraph(f"<b>{_m(e['mali_degil'])}</b>", ParagraphStyle("md", parent=kucuk, alignment=TA_CENTER)))

    satir_sayisi = 22 + 2.4 * len(v.get("kalemler") or []) + len(v.get("kdv_dokumu") or [])
    yukseklik = max(110 * mm, satir_sayisi * 4.6 * mm)
    tampon = io.BytesIO()
    doc = SimpleDocTemplate(tampon, pagesize=(80 * mm, yukseklik), leftMargin=4 * mm, rightMargin=4 * mm,
                            topMargin=4 * mm, bottomMargin=4 * mm, title=f"{e['fis']} {v.get('no') or ''}",
                            author=str(f.get("ad") or ""), creator="mehmetkuru.dev")
    doc.build(parcalar)
    return tampon.getvalue()


# ---------------------------------------------------------------------------
# Fatura (A4, bilgi amaçlı)
# ---------------------------------------------------------------------------
def fatura_pdf(v: Dict[str, Any], dil: str = "tr") -> bytes:
    dil = pdf_dili(dil)
    e = ETIKET[dil]
    st = pb._stiller()  # noqa: SLF001
    pb_ = v.get("para_birimi") or "TRY"
    f = v.get("firma") or {}
    sol = []
    satirlar = [f"<b>{_m(f.get('ad'))}</b>"] if f.get("ad") else []
    for alan in ("adres", "telefon", "eposta"):
        if f.get(alan):
            satirlar.append(_m(f[alan]))
    vergi = " / ".join(x for x in (f.get("vergi_dairesi"), f.get("vergi_no")) if x)
    if vergi:
        satirlar.append(f"{_m(e['vergi'])}: {_m(vergi)}")
    sol.append(Paragraph("<br/>".join(satirlar) or "&nbsp;", st["govde"]))
    bilgiler = [(e["fatura_no"], v.get("fatura_no")), (e["fatura_tarihi"], v.get("fatura_tarihi")), (e["ilgili_fis"], v.get("no"))]
    parcalar: List[Any] = [pb._baslik_blogu(sol, e["fatura"], bilgiler, st), pb._ayrac(), Spacer(1, 3 * mm)]  # noqa: SLF001
    a = v.get("alici") or {}
    alici = [f"<b>{_m(a.get('ad'))}</b>"] if a.get("ad") else []
    for alan in ("adres", "eposta", "telefon"):
        if a.get(alan):
            alici.append(_m(a[alan]))
    avergi = " / ".join(x for x in (a.get("vergi_dairesi"), a.get("vergi_no")) if x)
    if avergi:
        alici.append(f"{_m(e['vergi'])}: {_m(avergi)}")
    parcalar += [Paragraph(f"<font color='#5B5368'>{_m(e['alici'])}</font>", st["kucuk"]),
                 Paragraph("<br/>".join(alici) or "—", st["govde"]), Spacer(1, 4 * mm)]
    basliklar = ["#", e["aciklama"], e["miktar"], e["birim_fiyat"], e["indirim"], e["oran"], e["tutar"]]
    veri: List[List[Any]] = [[Paragraph(f"<b>{_m(b)}</b>", st["govde"] if i < 2 else st["sag"]) for i, b in enumerate(basliklar)]]
    for i, k in enumerate(v.get("kalemler") or [], 1):
        veri.append([Paragraph(str(i), st["govde"]), Paragraph(_m(k.get("ad")), st["govde"]),
                     Paragraph(_m(_miktar(k["adet_binde"], k.get("birim") or "adet")), st["sag"]),
                     Paragraph(_m(_para(k["birim_fiyat"], pb_, dil)), st["sag"]),
                     Paragraph(_m(_para(k["indirim"], pb_, dil)) if k.get("indirim") else "—", st["sag"]),
                     Paragraph(str(k.get("kdv_orani") or 0), st["sag"]),
                     Paragraph(_m(_para(k["tutar"], pb_, dil)), st["sag"])])
    t = Table(veri, colWidths=[8 * mm, 60 * mm, 18 * mm, 30 * mm, 24 * mm, 12 * mm, 28 * mm], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), pb.VURGU_ACIK), ("LINEBELOW", (0, 0), (-1, 0), 0.8, pb.VURGU),
                           ("LINEBELOW", (0, 1), (-1, -1), 0.3, pb.CIZGI), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    parcalar += [t, Spacer(1, 3 * mm)]
    toplamlar = []
    for d in v.get("kdv_dokumu") or []:
        toplamlar.append((f"{e['matrah']} %{d['oran']}", _para(d["matrah"], pb_, dil), False))
        if d.get("kdv"):
            toplamlar.append((e["kdv"].format(oran=d["oran"]), _para(d["kdv"], pb_, dil), False))
    toplamlar.append((e["genel_toplam"], _para(v.get("toplam") or 0, pb_, dil), True))
    parcalar.append(KeepTogether(pb._toplam_tablosu(toplamlar, st)))  # noqa: SLF001
    odeme = " · ".join(f"{e[t]}: {_para(v[t], pb_, dil)}" for t in ("nakit", "kart", "havale") if v.get(t))
    if odeme:
        parcalar += [Spacer(1, 3 * mm), Paragraph(f"{_m(e['odeme'])}: {_m(odeme)}", st["kucuk"])]
    return pb._uret(parcalar, e["fatura_notu"], "tr" if dil == "tr" else "en", f"{e['fatura']} {v.get('fatura_no') or ''}")  # noqa: SLF001
