"""Faz 5C — bakiye ekstresi PDF'i (7 dil; `services.pdf_yazi.Paragraf` çok dilli yazı tipi yedeğiyle) ve CSV etiketleri."""

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

ETIKET: Dict[str, Dict[str, Any]] = {
    "tr": {
        "baslik": "BAKİYE EKSTRESİ", "hesap": "Hesap", "donem": "Dönem", "olusturma": "Oluşturma", "tarih": "Tarih",
        "islem": "İşlem", "aciklama": "Açıklama", "tutar": "Tutar", "bakiye": "Bakiye", "para_birimi": "Para birimi",
        "devreden": "Devreden bakiye", "kapanis": "Dönem sonu bakiyesi", "giris": "Toplam giriş", "cikis": "Toplam çıkış",
        "fatura": "Fatura", "bos": "Bu dönemde hareket yok.",
        "alt": "Bilgilendirme amaçlıdır; resmî kayıt ya da hukuki danışmanlık yerine geçmez.",
        "not": "Bakiye yalnız ajansın kendi hizmetlerinin bedeli için verilmiş avanstır; elektronik para ya da üçüncü "
               "kişilere ödeme aracı değildir, faiz işlemez, devredilemez. Kullanılmayan bakiye talep üzerine iade edilir. "
               "Bu belge bilgilendirme amaçlıdır; resmî kayıt ve hukuki danışmanlık yerine geçmez.",
        "tur": {"yukleme": "Yükleme", "harcama": "Fatura ödemesi", "iade": "İade (size ödeme)", "duzeltme": "Düzeltme",
                "ters_kayit": "Ters kayıt"},
        "yontem": {"havale": "Havale", "eft": "EFT", "nakit": "Nakit", "diger": "Diğer", "bakiye": "Bakiye"},
    },
    "en": {
        "baslik": "BALANCE STATEMENT", "hesap": "Account", "donem": "Period", "olusturma": "Created", "tarih": "Date",
        "islem": "Transaction", "aciklama": "Description", "tutar": "Amount", "bakiye": "Balance", "para_birimi": "Currency",
        "devreden": "Opening balance", "kapanis": "Closing balance", "giris": "Total in", "cikis": "Total out",
        "fatura": "Invoice", "bos": "No transactions in this period.",
        "alt": "For information only; not an official record or legal advice.",
        "not": "The balance is an advance paid only for the agency's own services; it is not electronic money or a means "
               "of payment to third parties, bears no interest and cannot be transferred. Unused balance is refunded on "
               "request. This document is for information only and is not an official record or legal advice.",
        "tur": {"yukleme": "Top-up", "harcama": "Invoice payment", "iade": "Refund (paid to you)", "duzeltme": "Adjustment",
                "ters_kayit": "Reversal"},
        "yontem": {"havale": "Bank transfer", "eft": "EFT", "nakit": "Cash", "diger": "Other", "bakiye": "Balance"},
    },
    "de": {
        "baslik": "GUTHABENAUSZUG", "hesap": "Konto", "donem": "Zeitraum", "olusturma": "Erstellt", "tarih": "Datum",
        "islem": "Vorgang", "aciklama": "Beschreibung", "tutar": "Betrag", "bakiye": "Guthaben", "para_birimi": "Währung",
        "devreden": "Anfangsguthaben", "kapanis": "Endguthaben", "giris": "Summe Eingänge", "cikis": "Summe Ausgänge",
        "fatura": "Rechnung", "bos": "Keine Vorgänge in diesem Zeitraum.",
        "alt": "Nur zur Information; kein amtlicher Nachweis und keine Rechtsberatung.",
        "not": "Das Guthaben ist eine Vorauszahlung ausschließlich für die eigenen Leistungen der Agentur; es ist kein "
               "E-Geld und kein Zahlungsmittel gegenüber Dritten, wird nicht verzinst und ist nicht übertragbar. Nicht "
               "genutztes Guthaben wird auf Anfrage erstattet. Dieses Dokument dient nur zur Information und ist weder "
               "amtlicher Nachweis noch Rechtsberatung.",
        "tur": {"yukleme": "Aufladung", "harcama": "Rechnungszahlung", "iade": "Erstattung (an Sie)", "duzeltme": "Korrektur",
                "ters_kayit": "Storno"},
        "yontem": {"havale": "Überweisung", "eft": "EFT", "nakit": "Bar", "diger": "Sonstiges", "bakiye": "Guthaben"},
    },
    "ru": {
        "baslik": "ВЫПИСКА ПО БАЛАНСУ", "hesap": "Аккаунт", "donem": "Период", "olusturma": "Создано", "tarih": "Дата",
        "islem": "Операция", "aciklama": "Описание", "tutar": "Сумма", "bakiye": "Баланс", "para_birimi": "Валюта",
        "devreden": "Входящий баланс", "kapanis": "Исходящий баланс", "giris": "Всего поступлений", "cikis": "Всего списаний",
        "fatura": "Счёт", "bos": "За этот период операций нет.",
        "alt": "Носит информационный характер; не является официальной записью или юридической консультацией.",
        "not": "Баланс — это аванс исключительно за собственные услуги агентства; он не является электронными деньгами "
               "или средством платежа третьим лицам, проценты не начисляются, передаче не подлежит. Неиспользованный "
               "баланс возвращается по запросу. Документ носит информационный характер и не является официальной "
               "записью или юридической консультацией.",
        "tur": {"yukleme": "Пополнение", "harcama": "Оплата счёта", "iade": "Возврат (вам)", "duzeltme": "Корректировка",
                "ters_kayit": "Сторно"},
        "yontem": {"havale": "Банковский перевод", "eft": "EFT", "nakit": "Наличные", "diger": "Другое", "bakiye": "Баланс"},
    },
    "zh": {
        "baslik": "余额对账单", "hesap": "账户", "donem": "期间", "olusturma": "生成日期", "tarih": "日期",
        "islem": "交易", "aciklama": "说明", "tutar": "金额", "bakiye": "余额", "para_birimi": "币种",
        "devreden": "期初余额", "kapanis": "期末余额", "giris": "转入合计", "cikis": "转出合计",
        "fatura": "发票", "bos": "本期间无交易。",
        "alt": "仅供参考；不构成正式记录或法律意见。",
        "not": "余额仅为支付本机构自身服务费用的预付款；它不是电子货币，也不能用于向第三方付款，不计利息，不可转让。"
               "未使用的余额可应要求退还。本文件仅供参考，不构成正式记录或法律意见。",
        "tur": {"yukleme": "充值", "harcama": "发票付款", "iade": "退款（付给您）", "duzeltme": "调整", "ters_kayit": "冲销"},
        "yontem": {"havale": "银行转账", "eft": "EFT", "nakit": "现金", "diger": "其他", "bakiye": "余额"},
    },
    "hi": {
        "baslik": "बैलेंस विवरण", "hesap": "खाता", "donem": "अवधि", "olusturma": "बनाया गया", "tarih": "तारीख",
        "islem": "लेन-देन", "aciklama": "विवरण", "tutar": "राशि", "bakiye": "बैलेंस", "para_birimi": "मुद्रा",
        "devreden": "प्रारंभिक बैलेंस", "kapanis": "अंतिम बैलेंस", "giris": "कुल जमा", "cikis": "कुल निकासी",
        "fatura": "चालान", "bos": "इस अवधि में कोई लेन-देन नहीं।",
        "alt": "केवल जानकारी के लिए; यह आधिकारिक रिकॉर्ड या कानूनी सलाह नहीं है।",
        "not": "बैलेंस केवल एजेंसी की अपनी सेवाओं के शुल्क के लिए दिया गया अग्रिम है; यह इलेक्ट्रॉनिक मुद्रा या तीसरे पक्ष को "
               "भुगतान का साधन नहीं है, इस पर ब्याज नहीं मिलता और यह हस्तांतरणीय नहीं है। अप्रयुक्त बैलेंस अनुरोध पर लौटाया "
               "जाता है। यह दस्तावेज़ केवल जानकारी के लिए है; यह आधिकारिक रिकॉर्ड या कानूनी सलाह नहीं है।",
        "tur": {"yukleme": "टॉप-अप", "harcama": "चालान भुगतान", "iade": "धनवापसी (आपको)", "duzeltme": "समायोजन",
                "ters_kayit": "उलट प्रविष्टि"},
        "yontem": {"havale": "बैंक ट्रांसफ़र", "eft": "EFT", "nakit": "नकद", "diger": "अन्य", "bakiye": "बैलेंस"},
    },
    "ar": {
        "baslik": "كشف الرصيد", "hesap": "الحساب", "donem": "الفترة", "olusturma": "تاريخ الإنشاء", "tarih": "التاريخ",
        "islem": "العملية", "aciklama": "الوصف", "tutar": "المبلغ", "bakiye": "الرصيد", "para_birimi": "العملة",
        "devreden": "الرصيد الافتتاحي", "kapanis": "الرصيد الختامي", "giris": "إجمالي الإيداعات", "cikis": "إجمالي الخصومات",
        "fatura": "فاتورة", "bos": "لا توجد عمليات في هذه الفترة.",
        "alt": "للعلم فقط؛ ليس سجلاً رسمياً ولا استشارة قانونية.",
        "not": "الرصيد دفعة مقدمة حصراً مقابل خدمات الوكالة نفسها؛ وهو ليس نقوداً إلكترونية ولا وسيلة دفع لأطراف ثالثة، "
               "ولا تترتب عليه فائدة، ولا يجوز تحويله. يُعاد الرصيد غير المستخدم عند الطلب. هذا المستند للعلم فقط وليس "
               "سجلاً رسمياً أو استشارة قانونية.",
        "tur": {"yukleme": "شحن", "harcama": "دفع فاتورة", "iade": "استرداد (مدفوع لك)", "duzeltme": "تسوية",
                "ters_kayit": "قيد عكسي"},
        "yontem": {"havale": "حوالة بنكية", "eft": "EFT", "nakit": "نقداً", "diger": "أخرى", "bakiye": "الرصيد"},
    },
}


def pdf_dili(dil: Optional[str]) -> str:
    d = (dil or "tr")[:2].lower()
    return d if d in ETIKET else "en"


def etiketler(dil: Optional[str]) -> Dict[str, Any]:
    return ETIKET[pdf_dili(dil)]


def _tarih(g: Optional[date]) -> str:
    return g.strftime("%d.%m.%Y") if g else "—"


def _para(kurus: int, pb: str, dil: str) -> str:
    from services import pdf_belge as pb_

    return pb_.para(Decimal(int(kurus or 0)) / 100, pb, "tr" if dil in ("tr", "de") else "en")


def ekstre_pdf(v: Dict[str, Any], dil: str = "tr", firma: Optional[str] = None) -> bytes:
    """`v`: `services.cuzdan.ekstre_verisi` çıktısı (tutarlar kuruş, tarihler date)."""
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, Spacer, Table, TableStyle

    from services import pdf_belge as pb
    from services.cuzdan import aciklama_metni
    from services.pdf_yazi import Paragraf as Paragraph  # çok dilli paragraf (7 dil yazı tipi yedeği)

    dil = pdf_dili(dil)
    e = ETIKET[dil]
    st = pb._stiller()  # noqa: SLF001
    m = pb._metin  # noqa: SLF001
    pbr = v.get("para_birimi") or "TRY"
    sol = [Paragraph(f"<b>{m(firma)}</b>" if firma else "&nbsp;", st["govde"])]
    bilgiler = [(e["hesap"], v.get("ad") or v.get("hesap_email") or ""), (e["para_birimi"], pbr),
                (e["donem"], f"{_tarih(v.get('bas'))} – {_tarih(v.get('bit'))}"), (e["olusturma"], _tarih(v.get("olusturma")))]
    parcalar: List[Any] = [pb._baslik_blogu(sol, e["baslik"], bilgiler, st), pb._ayrac(), Spacer(1, 4 * mm)]  # noqa: SLF001
    basliklar = [e["tarih"], e["islem"], e["aciklama"], e["tutar"], e["bakiye"]]
    veri: List[List[Any]] = [[Paragraph(f"<b>{m(b)}</b>", st["govde"] if i < 3 else st["sag"]) for i, b in enumerate(basliklar)]]
    veri.append([Paragraph(_tarih(v.get("bas")), st["govde"]), Paragraph(f"<i>{m(e['devreden'])}</i>", st["govde"]),
                 Paragraph("", st["govde"]), Paragraph("", st["sag"]),
                 Paragraph(m(_para(v.get("devreden") or 0, pbr, dil)), st["sag"])])
    for s in v.get("satirlar") or []:
        tutar = int(s.get("tutar") or 0)
        isaret = "+" if tutar > 0 else "−"
        veri.append([Paragraph(_tarih(s.get("tarih")), st["govde"]), Paragraph(m(e["tur"].get(s.get("tur"), s.get("tur") or "")), st["govde"]),
                     Paragraph(m(aciklama_metni(s, e)), st["govde"]),
                     Paragraph(m(f"{isaret}{_para(abs(tutar), pbr, dil)}"), st["sag"]),
                     Paragraph(m(_para(s.get("bakiye") or 0, pbr, dil)), st["sag"])])
    if not v.get("satirlar"):
        veri.append([Paragraph("", st["govde"]), Paragraph("", st["govde"]), Paragraph(m(e["bos"]), st["kucuk"]),
                     Paragraph("", st["sag"]), Paragraph("", st["sag"])])
    t = Table(veri, colWidths=[24 * mm, 32 * mm, 70 * mm, 27 * mm, 27 * mm], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), pb.VURGU_ACIK), ("LINEBELOW", (0, 0), (-1, 0), 0.8, pb.VURGU),
                           ("LINEBELOW", (0, 1), (-1, -1), 0.3, pb.CIZGI), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    parcalar += [t, Spacer(1, 3 * mm)]
    toplamlar = [(e["giris"], _para(v.get("giris") or 0, pbr, dil), False), (e["cikis"], _para(v.get("cikis") or 0, pbr, dil), False),
                 (e["kapanis"], _para(v.get("kapanis") or 0, pbr, dil), True)]
    parcalar.append(KeepTogether(pb._toplam_tablosu(toplamlar, st)))  # noqa: SLF001
    # Hukuki not gövdede (sarılır); sayfa altında kısa bilgilendirme satırı.
    parcalar += [Spacer(1, 5 * mm), Paragraph(m(e["not"]), st["kucuk"])]
    return pb._uret(parcalar, e["alt"], "tr" if dil == "tr" else "en", f"{e['baslik']} {v.get('hesap_email') or ''}")  # noqa: SLF001
