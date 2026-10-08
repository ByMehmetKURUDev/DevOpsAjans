"""Faz 6T — toplantı tutanağı: PDF (7 dil, çok dilli yazı tipi zinciri) ve Markdown indirme.

PDF metni `services.pdf_yazi.Paragraf` (Kiril, Arapça, Devanagari, Çince adlar/metinler; Arapça sağdan sola) ile
yazılır. Tutanak = toplantı bilgisi + katılımcılar (yanıtlarıyla) + gündem + notlar + kararlar + aksiyonlar.
Müşteriye giden sürüm (`musteri=True`) yalnız PAYLAŞILMIŞ tutanakta üretilir (uç denetler); dış katılımcı
e-postaları müşteri sürümünde yazılmaz (adlar ve yanıt).
"""

from __future__ import annotations

import io
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from services.toplantilar import SAAT_DILIMI, bitis, json_liste, yerel

DILLER = ("tr", "en", "de", "ru", "zh", "hi", "ar")

ETIKET: Dict[str, Dict[str, str]] = {
    "tr": {"baslik": "Toplantı tutanağı", "tarih": "Tarih", "sure": "Süre", "yer": "Yer", "musteri": "Müşteri",
           "proje": "Proje", "durum": "Durum", "katilimcilar": "Katılımcılar", "gundem": "Gündem", "notlar": "Notlar",
           "kararlar": "Kararlar", "aksiyonlar": "Aksiyonlar", "sorumlu": "Sorumlu", "son_tarih": "Son tarih",
           "ekip": "Ekip", "musteri_tarafi": "Müşteri tarafı", "yok": "Kayıt yok.", "dk": "dk", "olusturma": "Oluşturma",
           "iptal_nedeni": "İptal nedeni", "yanit": "Yanıt",
           "not": "Bu tutanak bilgilendirme amaçlıdır; saatler Europe/Istanbul saat dilimindedir."},
    "en": {"baslik": "Meeting minutes", "tarih": "Date", "sure": "Duration", "yer": "Location", "musteri": "Client",
           "proje": "Project", "durum": "Status", "katilimcilar": "Attendees", "gundem": "Agenda", "notlar": "Notes",
           "kararlar": "Decisions", "aksiyonlar": "Action items", "sorumlu": "Owner", "son_tarih": "Due date",
           "ekip": "Team", "musteri_tarafi": "Client side", "yok": "No entries.", "dk": "min", "olusturma": "Created",
           "iptal_nedeni": "Cancellation reason", "yanit": "Response",
           "not": "These minutes are for information only; times are in the Europe/Istanbul time zone."},
    "de": {"baslik": "Besprechungsprotokoll", "tarih": "Datum", "sure": "Dauer", "yer": "Ort", "musteri": "Kunde",
           "proje": "Projekt", "durum": "Status", "katilimcilar": "Teilnehmende", "gundem": "Tagesordnung",
           "notlar": "Notizen", "kararlar": "Beschlüsse", "aksiyonlar": "Aufgaben", "sorumlu": "Verantwortlich",
           "son_tarih": "Fällig am", "ekip": "Team", "musteri_tarafi": "Kundenseite", "yok": "Keine Einträge.",
           "dk": "Min.", "olusturma": "Erstellt", "iptal_nedeni": "Absagegrund", "yanit": "Antwort",
           "not": "Dieses Protokoll dient nur zur Information; Zeiten in der Zeitzone Europe/Istanbul."},
    "ru": {"baslik": "Протокол встречи", "tarih": "Дата", "sure": "Длительность", "yer": "Место", "musteri": "Клиент",
           "proje": "Проект", "durum": "Статус", "katilimcilar": "Участники", "gundem": "Повестка", "notlar": "Заметки",
           "kararlar": "Решения", "aksiyonlar": "Задачи", "sorumlu": "Ответственный", "son_tarih": "Срок",
           "ekip": "Команда", "musteri_tarafi": "Сторона клиента", "yok": "Записей нет.", "dk": "мин",
           "olusturma": "Создано", "iptal_nedeni": "Причина отмены", "yanit": "Ответ",
           "not": "Протокол носит информационный характер; время указано в часовом поясе Europe/Istanbul."},
    "zh": {"baslik": "会议纪要", "tarih": "日期", "sure": "时长", "yer": "地点", "musteri": "客户", "proje": "项目",
           "durum": "状态", "katilimcilar": "参会人员", "gundem": "议程", "notlar": "笔记", "kararlar": "决定",
           "aksiyonlar": "行动项", "sorumlu": "负责人", "son_tarih": "截止日期", "ekip": "团队", "musteri_tarafi": "客户方",
           "yok": "暂无记录。", "dk": "分钟", "olusturma": "生成日期", "iptal_nedeni": "取消原因", "yanit": "回复",
           "not": "本纪要仅供参考；时间为 Europe/Istanbul 时区。"},
    "hi": {"baslik": "बैठक का कार्यवृत्त", "tarih": "दिनांक", "sure": "अवधि", "yer": "स्थान", "musteri": "ग्राहक",
           "proje": "परियोजना", "durum": "स्थिति", "katilimcilar": "प्रतिभागी", "gundem": "कार्यसूची", "notlar": "नोट्स",
           "kararlar": "निर्णय", "aksiyonlar": "कार्य बिंदु", "sorumlu": "ज़िम्मेदार", "son_tarih": "अंतिम तिथि",
           "ekip": "टीम", "musteri_tarafi": "ग्राहक पक्ष", "yok": "कोई प्रविष्टि नहीं।", "dk": "मिनट",
           "olusturma": "निर्मित", "iptal_nedeni": "रद्द करने का कारण", "yanit": "उत्तर",
           "not": "यह कार्यवृत्त केवल जानकारी के लिए है; समय Europe/Istanbul समय क्षेत्र में है।"},
    "ar": {"baslik": "محضر الاجتماع", "tarih": "التاريخ", "sure": "المدة", "yer": "المكان", "musteri": "العميل",
           "proje": "المشروع", "durum": "الحالة", "katilimcilar": "الحضور", "gundem": "جدول الأعمال", "notlar": "الملاحظات",
           "kararlar": "القرارات", "aksiyonlar": "بنود العمل", "sorumlu": "المسؤول", "son_tarih": "الموعد النهائي",
           "ekip": "الفريق", "musteri_tarafi": "جانب العميل", "yok": "لا توجد سجلات.", "dk": "د",
           "olusturma": "تاريخ الإنشاء", "iptal_nedeni": "سبب الإلغاء", "yanit": "الرد",
           "not": "هذا المحضر للعلم فقط؛ الأوقات بتوقيت Europe/Istanbul."},
}

YER_ADI: Dict[str, Dict[str, str]] = {
    "tr": {"cevrimici": "Çevrim içi", "yuz_yuze": "Yüz yüze", "telefon": "Telefon"},
    "en": {"cevrimici": "Online", "yuz_yuze": "In person", "telefon": "Phone"},
    "de": {"cevrimici": "Online", "yuz_yuze": "Vor Ort", "telefon": "Telefon"},
    "ru": {"cevrimici": "Онлайн", "yuz_yuze": "Очно", "telefon": "По телефону"},
    "zh": {"cevrimici": "线上", "yuz_yuze": "面对面", "telefon": "电话"},
    "hi": {"cevrimici": "ऑनलाइन", "yuz_yuze": "आमने-सामने", "telefon": "फ़ोन"},
    "ar": {"cevrimici": "عبر الإنترنت", "yuz_yuze": "حضوريًا", "telefon": "هاتفيًا"},
}
DURUM_ADI: Dict[str, Dict[str, str]] = {
    "tr": {"planlandi": "Planlandı", "yapildi": "Yapıldı", "ertelendi": "Ertelendi", "iptal": "İptal"},
    "en": {"planlandi": "Scheduled", "yapildi": "Held", "ertelendi": "Rescheduled", "iptal": "Cancelled"},
    "de": {"planlandi": "Geplant", "yapildi": "Stattgefunden", "ertelendi": "Verschoben", "iptal": "Abgesagt"},
    "ru": {"planlandi": "Запланирована", "yapildi": "Проведена", "ertelendi": "Перенесена", "iptal": "Отменена"},
    "zh": {"planlandi": "已安排", "yapildi": "已举行", "ertelendi": "已改期", "iptal": "已取消"},
    "hi": {"planlandi": "निर्धारित", "yapildi": "संपन्न", "ertelendi": "स्थगित", "iptal": "रद्द"},
    "ar": {"planlandi": "مجدول", "yapildi": "عُقد", "ertelendi": "مؤجل", "iptal": "ملغى"},
}
YANIT_ADI: Dict[str, Dict[str, str]] = {
    "tr": {"bekliyor": "Yanıt bekleniyor", "katilacak": "Katılacak", "katilamayacak": "Katılamayacak", "belki": "Belki"},
    "en": {"bekliyor": "Awaiting response", "katilacak": "Attending", "katilamayacak": "Not attending", "belki": "Maybe"},
    "de": {"bekliyor": "Antwort ausstehend", "katilacak": "Nimmt teil", "katilamayacak": "Nimmt nicht teil", "belki": "Vielleicht"},
    "ru": {"bekliyor": "Ожидается ответ", "katilacak": "Примет участие", "katilamayacak": "Не сможет", "belki": "Возможно"},
    "zh": {"bekliyor": "等待回复", "katilacak": "参加", "katilamayacak": "不参加", "belki": "可能"},
    "hi": {"bekliyor": "उत्तर की प्रतीक्षा", "katilacak": "शामिल होंगे", "katilamayacak": "शामिल नहीं होंगे", "belki": "शायद"},
    "ar": {"bekliyor": "بانتظار الرد", "katilacak": "سيحضر", "katilamayacak": "لن يحضر", "belki": "ربما"},
}
AKSIYON_DURUM_ADI: Dict[str, Dict[str, str]] = {
    "tr": {"acik": "Açık", "tamamlandi": "Tamamlandı"},
    "en": {"acik": "Open", "tamamlandi": "Done"},
    "de": {"acik": "Offen", "tamamlandi": "Erledigt"},
    "ru": {"acik": "Открыта", "tamamlandi": "Выполнена"},
    "zh": {"acik": "进行中", "tamamlandi": "已完成"},
    "hi": {"acik": "खुला", "tamamlandi": "पूर्ण"},
    "ar": {"acik": "مفتوح", "tamamlandi": "مكتمل"},
}


def pdf_dil(dil: Optional[str]) -> str:
    d = (dil or "tr")[:2].lower()
    return d if d in ETIKET else "en"


def _tarih_metni(an: datetime) -> str:
    return f"{yerel(an):%d.%m.%Y %H:%M}"


def _sorumlu(a: Any, ekip: Dict[str, str], e: Dict[str, str]) -> str:
    if a.sorumlu_tur == "musteri":
        return e["musteri_tarafi"] + (f" ({a.sorumlu_eposta})" if a.sorumlu_eposta else "")
    if a.sorumlu_eposta:
        return ekip.get(a.sorumlu_eposta) or a.sorumlu_eposta
    return e["ekip"]


def _katilimci_metni(k: Any, d: str, musteri: bool) -> str:
    """Müşteri sürümünde e-posta yazılmaz (ad ya da maskeli adres)."""
    from services.toplantilar import eposta_maskele

    if musteri:
        ad = k.ad or eposta_maskele(k.eposta)
    else:
        ad = f"{k.ad} <{k.eposta}>" if k.ad else k.eposta
    return f"{ad} — {YANIT_ADI[d].get(k.yanit, k.yanit)}"


def tutanak_md(t: Any, ks: Sequence[Any], ak: Sequence[Any], *, dil: str = "tr", ekip: Optional[Dict[str, str]] = None,
               hesap_adi: Optional[str] = None, proje_adi: Optional[str] = None, musteri: bool = False) -> str:
    """Markdown tutanak (indirilebilir; notlar zaten markdown — olduğu gibi gömülür)."""
    d = pdf_dil(dil)
    e = ETIKET[d]
    ekip = ekip or {}
    satirlar: List[str] = [f"# {e['baslik']}: {t.baslik}", ""]
    satirlar.append(f"- **{e['tarih']}:** {_tarih_metni(t.baslangic)} – {yerel(bitis(t)):%H:%M} ({SAAT_DILIMI})")
    satirlar.append(f"- **{e['sure']}:** {int(t.sure_dk or 0)} {e['dk']}")
    yer = YER_ADI[d].get(t.yer_turu, t.yer_turu)
    ayrinti = t.baglanti if t.yer_turu == "cevrimici" else (t.adres if t.yer_turu == "yuz_yuze" else t.telefon)
    satirlar.append(f"- **{e['yer']}:** {yer}" + (f" — {ayrinti}" if ayrinti else ""))
    satirlar.append(f"- **{e['durum']}:** {DURUM_ADI[d].get(t.durum, t.durum)}")
    if hesap_adi or t.hesap_email:
        satirlar.append(f"- **{e['musteri']}:** {hesap_adi or t.hesap_email}")
    if proje_adi:
        satirlar.append(f"- **{e['proje']}:** {proje_adi}")
    if t.durum == "iptal" and t.iptal_nedeni:
        satirlar.append(f"- **{e['iptal_nedeni']}:** {t.iptal_nedeni}")
    satirlar += ["", f"## {e['katilimcilar']}", ""]
    satirlar += [f"- {_katilimci_metni(k, d, musteri)}" for k in ks] or [f"_{e['yok']}_"]
    gundem = json_liste(t.gundem)
    satirlar += ["", f"## {e['gundem']}", ""]
    satirlar += [f"{i}. {m}" for i, m in enumerate(gundem, 1)] or [f"_{e['yok']}_"]
    satirlar += ["", f"## {e['notlar']}", "", (t.notlar or "").strip() or f"_{e['yok']}_"]
    kararlar = json_liste(t.kararlar)
    satirlar += ["", f"## {e['kararlar']}", ""]
    satirlar += [f"- {k}" for k in kararlar] or [f"_{e['yok']}_"]
    satirlar += ["", f"## {e['aksiyonlar']}", ""]
    if ak:
        for a in ak:
            kutu = "x" if a.durum == "tamamlandi" else " "
            ek = f" — {e['sorumlu']}: {_sorumlu(a, ekip, e)}"
            if a.son_tarih:
                ek += f" — {e['son_tarih']}: {a.son_tarih:%d.%m.%Y}"
            satirlar.append(f"- [{kutu}] {a.metin}{ek}")
    else:
        satirlar.append(f"_{e['yok']}_")
    satirlar += ["", "---", f"_{e['not']}_", ""]
    return "\n".join(satirlar)


_BASLIK = re.compile(r"^#{1,6}\s+")
_MADDE = re.compile(r"^\s*([-*+]|\d+[.)])\s+")
_VURGU = re.compile(r"(\*\*|__)(.+?)\1")


def _not_paragraflari(notlar: str, st: Dict[str, Any], m) -> List[Any]:
    """Markdown notları sade PDF paragraflarına çevirir (başlık → kalın, madde → •). HTML yok: metin kaçışlı."""
    from services.pdf_yazi import Paragraf as Paragraph  # çok dilli paragraf

    sonuc: List[Any] = []
    for satir in (notlar or "").splitlines():
        s = satir.strip()
        if not s:
            continue
        if _BASLIK.match(s):
            sonuc.append(Paragraph(f"<b>{m(_BASLIK.sub('', s))}</b>", st["govde"]))
        elif _MADDE.match(s):
            govde = _VURGU.sub(lambda x: x.group(2), _MADDE.sub("", s))
            sonuc.append(Paragraph(m(govde), st["madde"], bulletText="•"))
        else:
            sonuc.append(Paragraph(m(_VURGU.sub(lambda x: x.group(2), s)), st["govde"]))
    return sonuc


def tutanak_pdf(t: Any, ks: Sequence[Any], ak: Sequence[Any], *, dil: str = "tr", ekip: Optional[Dict[str, str]] = None,
                hesap_adi: Optional[str] = None, proje_adi: Optional[str] = None, musteri: bool = False,
                an: Optional[datetime] = None) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Spacer, Table, TableStyle

    from services import pdf_belge as pb
    from services.pdf_yazi import Paragraf as Paragraph  # çok dilli paragraf
    from services.pdf_yazi import metin_ciz
    from services.toplantilar import simdi

    d = pdf_dil(dil)
    e = ETIKET[d]
    ekip = ekip or {}
    st = pb._stiller()  # noqa: SLF001 — sitenin Türkçe destekli yazı tipi ve stilleri
    m = pb._metin  # noqa: SLF001
    an = an or simdi()
    parcalar: List[Any] = [
        Paragraph(f"<b>{m(e['baslik'])}</b>", st["bolum"]),
        Paragraph(f"<b>{m(t.baslik)}</b>", st["h1"]),
    ]
    yer = YER_ADI[d].get(t.yer_turu, t.yer_turu)
    ayrinti = t.baglanti if t.yer_turu == "cevrimici" else (t.adres if t.yer_turu == "yuz_yuze" else t.telefon)
    bilgi = [
        (e["tarih"], f"{_tarih_metni(t.baslangic)} – {yerel(bitis(t)):%H:%M} ({SAAT_DILIMI})"),
        (e["sure"], f"{int(t.sure_dk or 0)} {e['dk']}"),
        (e["yer"], f"{yer}" + (f" — {ayrinti}" if ayrinti else "")),
        (e["durum"], DURUM_ADI[d].get(t.durum, t.durum)),
        (e["musteri"], hesap_adi or t.hesap_email),
        (e["proje"], proje_adi),
        (e["iptal_nedeni"], t.iptal_nedeni if t.durum == "iptal" else None),
        (e["olusturma"], _tarih_metni(an)),
    ]
    for ad, deger in bilgi:
        if deger:
            parcalar.append(Paragraph(f"<font color='#5B5368'>{m(ad)}:</font> {m(deger)}", st["govde"]))

    def bolum(ad: str) -> None:
        parcalar.append(Spacer(1, 2 * mm))
        parcalar.append(Paragraph(m(ad), st["bolum"]))

    bolum(e["katilimcilar"])
    if ks:
        for k in ks:
            parcalar.append(Paragraph(m(_katilimci_metni(k, d, musteri)), st["madde"], bulletText="•"))
    else:
        parcalar.append(Paragraph(m(e["yok"]), st["kucuk"]))

    bolum(e["gundem"])
    gundem = json_liste(t.gundem)
    if gundem:
        for i, madde in enumerate(gundem, 1):
            parcalar.append(Paragraph(m(madde), st["madde"], bulletText=f"{i}."))
    else:
        parcalar.append(Paragraph(m(e["yok"]), st["kucuk"]))

    bolum(e["notlar"])
    notlar = _not_paragraflari(t.notlar or "", st, m)
    parcalar += notlar or [Paragraph(m(e["yok"]), st["kucuk"])]

    bolum(e["kararlar"])
    kararlar = json_liste(t.kararlar)
    if kararlar:
        for k in kararlar:
            parcalar.append(Paragraph(m(k), st["madde"], bulletText="•"))
    else:
        parcalar.append(Paragraph(m(e["yok"]), st["kucuk"]))

    bolum(e["aksiyonlar"])
    if ak:
        veri: List[List[Any]] = [[Paragraph(f"<b>{m(x)}</b>", st["govde"]) for x in
                                  (e["aksiyonlar"], e["sorumlu"], e["son_tarih"], e["durum"])]]
        for a in ak:
            veri.append([
                Paragraph(m(a.metin), st["govde"]),
                Paragraph(m(_sorumlu(a, ekip, e)), st["govde"]),
                Paragraph(m(f"{a.son_tarih:%d.%m.%Y}" if a.son_tarih else "—"), st["govde"]),
                Paragraph(m(AKSIYON_DURUM_ADI[d].get(a.durum, a.durum)), st["govde"]),
            ])
        tablo = Table(veri, colWidths=[78 * mm, 48 * mm, 26 * mm, 28 * mm], repeatRows=1)
        tablo.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), pb.VURGU_ACIK), ("LINEBELOW", (0, 0), (-1, 0), 0.8, pb.VURGU),
            ("LINEBELOW", (0, 1), (-1, -1), 0.3, pb.CIZGI), ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        parcalar.append(tablo)
    else:
        parcalar.append(Paragraph(m(e["yok"]), st["kucuk"]))

    tampon = io.BytesIO()
    doc = SimpleDocTemplate(tampon, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm,
                            bottomMargin=20 * mm, title=f"{e['baslik']} — {t.baslik}"[:120], author="By Mehmet KURU Dev",
                            creator="mehmetkuru.dev")

    def alt(canvas, doc_):
        canvas.saveState()
        canvas.setStrokeColor(pb.CIZGI)
        canvas.setLineWidth(0.4)
        canvas.line(15 * mm, 14 * mm, 195 * mm, 14 * mm)
        canvas.setFillColor(colors.HexColor("#5B5368"))
        metin_ciz(canvas, 15 * mm, 10 * mm, e["not"][:180], pb.YAZI, 7)
        metin_ciz(canvas, 195 * mm, 10 * mm, str(doc_.page), pb.YAZI, 7, "sag")
        canvas.restoreState()

    doc.build(parcalar, onFirstPage=alt, onLaterPages=alt)
    return tampon.getvalue()


def dosya_adi(t: Any, uzanti: str) -> str:
    return f"toplanti-tutanagi-{t.id}-{yerel(t.baslangic):%Y%m%d}.{uzanti}"
