"""Faz 6S — servis formu / fiş PDF'i (ReportLab; Faz 3T altyapısı: yazı tipi, stiller, sayfa altı).

Belge servis FİRMASININ belgesi: başlıkta firmanın künyesi (ajansın markası değil).
Etiketler 7 dilde; metin `services/pdf_yazi.py`'nin yazı tipi zincirinden geçiyor (Faz 7K: Kiril,
Arapça, Devanagari, Çince). E-fatura / e-arşiv yerine geçmez (sayfa altında yazıyor) — gerçek
e-fatura ileride.
"""

import io
import logging
from typing import Any, Dict, List, Optional

from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, KeepTogether, Spacer, Table, TableStyle
from services import pdf_belge as pb
from services.pdf_yazi import Paragraf as Paragraph  # çok dilli paragraf

logger = logging.getLogger(__name__)

ETIKET: Dict[str, Dict[str, str]] = {
    "tr": {
        "baslik": "SERVİS FORMU", "no": "No", "tarih": "Tarih", "durum": "Durum", "musteri": "Müşteri",
        "adres": "Adres", "telefon": "Telefon", "is": "İş bilgisi", "tur": "Tür", "oncelik": "Öncelik",
        "teknisyen": "Teknisyen", "plan": "Planlanan", "basla": "Başlangıç", "bitir": "Bitiş", "sure": "Süre",
        "dk": "dk", "cihazlar": "Cihazlar", "cihaz": "Cihaz", "marka": "Marka / model", "seri": "Seri no",
        "aciklama": "Açıklama", "kontrol": "Kontrol listesi", "madde": "Madde", "sonuc": "Sonuç",
        "evet": "Evet", "hayir": "Hayır", "foto_var": "fotoğraf eklendi", "foto_yok": "fotoğraf yok", "bos": "—",
        "malzeme": "Kullanılan malzeme ve işçilik", "kalem": "Kalem", "miktar": "Miktar", "birim_fiyat": "Birim fiyat",
        "tutar": "Tutar", "iscilik": "İşçilik", "ara_toplam": "Ara toplam", "kdv": "KDV (%{oran})",
        "genel_toplam": "Genel toplam", "not": "Teknisyen notu", "imza": "Müşteri onayı", "imzalayan": "İmzalayan",
        "imza_zamani": "İmza zamanı", "imzasiz": "İmza alınmadı.", "fotograflar": "Fotoğraf",
        "alt": "Bu servis formu bilgilendirme amaçlıdır; e-Fatura/e-Arşiv fatura yerine geçmez.",
        "kurulum": "Kurulum", "ariza": "Arıza", "bakim": "Bakım", "temizlik": "Temizlik", "kesif": "Keşif",
        "dusuk": "Düşük", "normal": "Normal", "yuksek": "Yüksek", "acil": "Acil",
        "yeni": "Yeni", "planlandi": "Planlandı", "yolda": "Yolda", "iste": "İşte", "tamamlandi": "Tamamlandı",
        "iptal": "İptal", "ertelendi": "Ertelendi",
    },
    "en": {
        "baslik": "SERVICE REPORT", "no": "No", "tarih": "Date", "durum": "Status", "musteri": "Customer",
        "adres": "Address", "telefon": "Phone", "is": "Job details", "tur": "Type", "oncelik": "Priority",
        "teknisyen": "Technician", "plan": "Scheduled", "basla": "Started", "bitir": "Finished", "sure": "Duration",
        "dk": "min", "cihazlar": "Equipment", "cihaz": "Equipment", "marka": "Make / model", "seri": "Serial no",
        "aciklama": "Description", "kontrol": "Checklist", "madde": "Item", "sonuc": "Result",
        "evet": "Yes", "hayir": "No", "foto_var": "photo attached", "foto_yok": "no photo", "bos": "—",
        "malzeme": "Materials and labour", "kalem": "Item", "miktar": "Qty", "birim_fiyat": "Unit price",
        "tutar": "Amount", "iscilik": "Labour", "ara_toplam": "Subtotal", "kdv": "VAT ({oran}%)",
        "genel_toplam": "Total", "not": "Technician note", "imza": "Customer approval", "imzalayan": "Signed by",
        "imza_zamani": "Signed at", "imzasiz": "No signature taken.", "fotograflar": "Photos",
        "alt": "This service report is for information only; it does not replace an e-Invoice/e-Archive invoice.",
        "kurulum": "Installation", "ariza": "Repair", "bakim": "Maintenance", "temizlik": "Cleaning", "kesif": "Site survey",
        "dusuk": "Low", "normal": "Normal", "yuksek": "High", "acil": "Urgent",
        "yeni": "New", "planlandi": "Scheduled", "yolda": "On the way", "iste": "In progress", "tamamlandi": "Completed",
        "iptal": "Cancelled", "ertelendi": "Postponed",
    },
    "de": {
        "baslik": "SERVICEBERICHT", "no": "Nr.", "tarih": "Datum", "durum": "Status", "musteri": "Kunde",
        "adres": "Adresse", "telefon": "Telefon", "is": "Auftrag", "tur": "Art", "oncelik": "Priorität",
        "teknisyen": "Techniker", "plan": "Geplant", "basla": "Beginn", "bitir": "Ende", "sure": "Dauer",
        "dk": "Min.", "cihazlar": "Geräte", "cihaz": "Gerät", "marka": "Marke / Modell", "seri": "Seriennr.",
        "aciklama": "Beschreibung", "kontrol": "Checkliste", "madde": "Punkt", "sonuc": "Ergebnis",
        "evet": "Ja", "hayir": "Nein", "foto_var": "Foto vorhanden", "foto_yok": "kein Foto", "bos": "—",
        "malzeme": "Material und Arbeitszeit", "kalem": "Position", "miktar": "Menge", "birim_fiyat": "Einzelpreis",
        "tutar": "Betrag", "iscilik": "Arbeitszeit", "ara_toplam": "Zwischensumme", "kdv": "MwSt. ({oran} %)",
        "genel_toplam": "Gesamt", "not": "Notiz des Technikers", "imza": "Bestätigung des Kunden", "imzalayan": "Unterzeichnet von",
        "imza_zamani": "Unterzeichnet am", "imzasiz": "Keine Unterschrift.", "fotograflar": "Fotos",
        "alt": "Dieser Servicebericht dient nur zur Information und ersetzt keine E-Rechnung.",
        "kurulum": "Installation", "ariza": "Störung", "bakim": "Wartung", "temizlik": "Reinigung", "kesif": "Besichtigung",
        "dusuk": "Niedrig", "normal": "Normal", "yuksek": "Hoch", "acil": "Dringend",
        "yeni": "Neu", "planlandi": "Geplant", "yolda": "Unterwegs", "iste": "In Arbeit", "tamamlandi": "Abgeschlossen",
        "iptal": "Storniert", "ertelendi": "Verschoben",
    },
    "ru": {
        "baslik": "СЕРВИСНЫЙ ОТЧЁТ", "no": "№", "tarih": "Дата", "durum": "Статус", "musteri": "Клиент",
        "adres": "Адрес", "telefon": "Телефон", "is": "Сведения о работе", "tur": "Тип", "oncelik": "Приоритет",
        "teknisyen": "Техник", "plan": "Запланировано", "basla": "Начало", "bitir": "Окончание", "sure": "Длительность",
        "dk": "мин", "cihazlar": "Оборудование", "cihaz": "Оборудование", "marka": "Марка / модель",
        "seri": "Серийный №", "aciklama": "Описание", "kontrol": "Контрольный список", "madde": "Пункт",
        "sonuc": "Результат", "evet": "Да", "hayir": "Нет", "foto_var": "фото приложено", "foto_yok": "нет фото",
        "bos": "—", "malzeme": "Материалы и работа", "kalem": "Позиция", "miktar": "Кол-во",
        "birim_fiyat": "Цена за ед.", "tutar": "Сумма", "iscilik": "Работа", "ara_toplam": "Промежуточный итог",
        "kdv": "НДС ({oran}%)", "genel_toplam": "Итого", "not": "Примечание техника", "imza": "Подтверждение клиента",
        "imzalayan": "Подписал(а)", "imza_zamani": "Время подписи", "imzasiz": "Подпись не получена.",
        "fotograflar": "Фото",
        "alt": ("Этот сервисный отчёт носит информационный характер и не заменяет электронный счёт-фактуру "
                "(e-Fatura/e-Arşiv)."),
        "kurulum": "Установка", "ariza": "Ремонт", "bakim": "Обслуживание", "temizlik": "Чистка",
        "kesif": "Осмотр объекта", "dusuk": "Низкий", "normal": "Обычный", "yuksek": "Высокий", "acil": "Срочный",
        "yeni": "Новый", "planlandi": "Запланирован", "yolda": "В пути", "iste": "В работе", "tamamlandi": "Завершён",
        "iptal": "Отменён", "ertelendi": "Отложен",
    },
    "zh": {
        "baslik": "服务报告", "no": "编号", "tarih": "日期", "durum": "状态", "musteri": "客户", "adres": "地址",
        "telefon": "电话", "is": "工单信息", "tur": "类型", "oncelik": "优先级", "teknisyen": "技术员", "plan": "计划时间",
        "basla": "开始", "bitir": "结束", "sure": "时长", "dk": "分钟", "cihazlar": "设备", "cihaz": "设备",
        "marka": "品牌 / 型号", "seri": "序列号", "aciklama": "描述", "kontrol": "检查清单", "madde": "项目",
        "sonuc": "结果", "evet": "是", "hayir": "否", "foto_var": "已附照片", "foto_yok": "无照片", "bos": "—",
        "malzeme": "材料与人工", "kalem": "项目", "miktar": "数量", "birim_fiyat": "单价", "tutar": "金额",
        "iscilik": "人工", "ara_toplam": "小计", "kdv": "增值税（{oran}%）", "genel_toplam": "总计",
        "not": "技术员备注", "imza": "客户确认", "imzalayan": "签署人", "imza_zamani": "签署时间",
        "imzasiz": "未取得签名。", "fotograflar": "照片", "alt": "本服务报告仅供参考，不能替代电子发票（e-Fatura/e-Arşiv）。",
        "kurulum": "安装", "ariza": "维修", "bakim": "保养", "temizlik": "清洁", "kesif": "现场勘查",
        "dusuk": "低", "normal": "普通", "yuksek": "高", "acil": "紧急",
        "yeni": "新建", "planlandi": "已安排", "yolda": "在途中", "iste": "进行中", "tamamlandi": "已完成",
        "iptal": "已取消", "ertelendi": "已推迟",
    },
    "hi": {
        "baslik": "सेवा रिपोर्ट", "no": "क्रमांक", "tarih": "दिनांक", "durum": "स्थिति", "musteri": "ग्राहक",
        "adres": "पता", "telefon": "फ़ोन", "is": "कार्य विवरण", "tur": "प्रकार", "oncelik": "प्राथमिकता",
        "teknisyen": "तकनीशियन", "plan": "निर्धारित", "basla": "आरंभ", "bitir": "समाप्त", "sure": "अवधि",
        "dk": "मिनट", "cihazlar": "उपकरण", "cihaz": "उपकरण", "marka": "ब्रांड / मॉडल", "seri": "सीरियल नंबर",
        "aciklama": "विवरण", "kontrol": "जाँच सूची", "madde": "मद", "sonuc": "परिणाम", "evet": "हाँ", "hayir": "नहीं",
        "foto_var": "फ़ोटो संलग्न", "foto_yok": "फ़ोटो नहीं", "bos": "—", "malzeme": "प्रयुक्त सामग्री और श्रम",
        "kalem": "मद", "miktar": "मात्रा", "birim_fiyat": "इकाई मूल्य", "tutar": "राशि", "iscilik": "श्रम",
        "ara_toplam": "उप-योग", "kdv": "वैट ({oran}%)", "genel_toplam": "कुल योग", "not": "तकनीशियन की टिप्पणी",
        "imza": "ग्राहक की स्वीकृति", "imzalayan": "हस्ताक्षरकर्ता", "imza_zamani": "हस्ताक्षर का समय",
        "imzasiz": "हस्ताक्षर नहीं लिया गया।", "fotograflar": "फ़ोटो",
        "alt": "यह सेवा रिपोर्ट केवल जानकारी के लिए है; यह ई-इनवॉइस/ई-आर्काइव चालान का स्थान नहीं लेती।",
        "kurulum": "स्थापना", "ariza": "मरम्मत", "bakim": "रखरखाव", "temizlik": "सफ़ाई", "kesif": "स्थल निरीक्षण",
        "dusuk": "निम्न", "normal": "सामान्य", "yuksek": "उच्च", "acil": "अत्यावश्यक",
        "yeni": "नया", "planlandi": "निर्धारित", "yolda": "रास्ते में", "iste": "प्रगति में", "tamamlandi": "पूर्ण",
        "iptal": "रद्द", "ertelendi": "स्थगित",
    },
    "ar": {
        "baslik": "تقرير الخدمة", "no": "رقم", "tarih": "التاريخ", "durum": "الحالة", "musteri": "العميل",
        "adres": "العنوان", "telefon": "الهاتف", "is": "تفاصيل العمل", "tur": "النوع", "oncelik": "الأولوية",
        "teknisyen": "الفني", "plan": "الموعد المقرر", "basla": "البدء", "bitir": "الانتهاء", "sure": "المدة",
        "dk": "دقيقة", "cihazlar": "الأجهزة", "cihaz": "الجهاز", "marka": "العلامة / الطراز", "seri": "الرقم التسلسلي",
        "aciklama": "الوصف", "kontrol": "قائمة التحقق", "madde": "البند", "sonuc": "النتيجة", "evet": "نعم",
        "hayir": "لا", "foto_var": "صورة مرفقة", "foto_yok": "لا توجد صورة", "bos": "—", "malzeme": "المواد والعمالة",
        "kalem": "البند", "miktar": "الكمية", "birim_fiyat": "سعر الوحدة", "tutar": "المبلغ", "iscilik": "العمالة",
        "ara_toplam": "المجموع الفرعي", "kdv": "ضريبة القيمة المضافة ({oran}%)", "genel_toplam": "الإجمالي",
        "not": "ملاحظة الفني", "imza": "موافقة العميل", "imzalayan": "الموقِّع", "imza_zamani": "وقت التوقيع",
        "imzasiz": "لم يُؤخذ توقيع.", "fotograflar": "الصور",
        "alt": "تقرير الخدمة هذا للعلم فقط؛ ولا يحل محل الفاتورة الإلكترونية (e-Fatura/e-Arşiv).",
        "kurulum": "تركيب", "ariza": "إصلاح", "bakim": "صيانة", "temizlik": "تنظيف", "kesif": "معاينة الموقع",
        "dusuk": "منخفضة", "normal": "عادية", "yuksek": "عالية", "acil": "عاجلة",
        "yeni": "جديد", "planlandi": "مجدول", "yolda": "في الطريق", "iste": "قيد التنفيذ", "tamamlandi": "مكتمل",
        "iptal": "ملغى", "ertelendi": "مؤجل",
    },
}


def pdf_dili(dil: Optional[str]) -> str:
    d = (dil or "tr")[:2].lower()
    return d if d in ETIKET else "en"


def _m(deger: Any) -> str:
    return pb._metin(deger)  # noqa: SLF001 - Faz 3T ortak yardımcısı


def _firma_blogu(firma: Dict[str, Any], st) -> List[Any]:
    satirlar = [f"<b>{_m(firma.get('ad') or '')}</b>"] if firma.get("ad") else []
    if firma.get("adres"):
        satirlar.append(_m(firma["adres"]))
    iletisim = " · ".join(x for x in (firma.get("telefon"), firma.get("eposta")) if x)
    if iletisim:
        satirlar.append(_m(iletisim))
    if firma.get("vergi_no"):
        satirlar.append(_m(firma["vergi_no"]))
    return [Paragraph("<br/>".join(satirlar) or "&nbsp;", st["govde"])]


def _tablo(veri: List[List[Any]], genislikler: List[float], baslikli: bool = True) -> Table:
    t = Table(veri, colWidths=genislikler, repeatRows=1 if baslikli else 0)
    stil = [
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, pb.CIZGI),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if baslikli:
        stil += [("BACKGROUND", (0, 0), (-1, 0), pb.VURGU_ACIK), ("LINEBELOW", (0, 0), (-1, 0), 0.8, pb.VURGU)]
    t.setStyle(TableStyle(stil))
    return t


def servis_formu_pdf(v: Dict[str, Any], dil: str = "tr") -> bytes:
    dil = pdf_dili(dil)
    e = ETIKET[dil]
    st = pb._stiller()  # noqa: SLF001
    para_birimi = v.get("para_birimi") or "TRY"
    para_dili = dil  # tutar biçimi dile göre (pdf_belge.para)
    ie = v["is"]
    bilgiler = [
        (e["no"], ie.get("no")),
        (e["tarih"], ie.get("tarih")),
        (e["durum"], e.get(ie.get("durum") or "", ie.get("durum"))),
    ]
    parcalar: List[Any] = [pb._baslik_blogu(_firma_blogu(v.get("firma") or {}, st), e["baslik"], bilgiler, st),  # noqa: SLF001
                           pb._ayrac(), Spacer(1, 3 * mm)]  # noqa: SLF001

    # Müşteri + iş bilgisi (iki sütun)
    m = v.get("musteri") or {}
    sol = [Paragraph(f"<font color='#5B5368'>{_m(e['musteri'])}</font>", st["kucuk"]),
           Paragraph("<br/>".join(_m(x) for x in (m.get("ad"), m.get("firma")) if x) or e["bos"], st["kalin"])]
    if v.get("adres"):
        sol += [Spacer(1, 1.5 * mm), Paragraph(f"<font color='#5B5368'>{_m(e['adres'])}</font>", st["kucuk"]),
                Paragraph(_m(v["adres"]), st["govde"])]
    if m.get("telefon"):
        sol.append(Paragraph(f"{_m(e['telefon'])}: {_m(m['telefon'])}", st["govde"]))
    sag_satirlar = [
        (e["tur"], e.get(ie.get("tur") or "", ie.get("tur"))),
        (e["oncelik"], e.get(ie.get("oncelik") or "", ie.get("oncelik"))),
        (e["teknisyen"], ", ".join(v.get("teknisyenler") or []) or e["bos"]),
        (e["plan"], ie.get("plan")),
        (e["basla"], ie.get("basla")),
        (e["bitir"], ie.get("bitir")),
        (e["sure"], f"{ie['sure_dk']} {e['dk']}" if ie.get("sure_dk") is not None else None),
    ]
    sag = [Paragraph(f"<font color='#5B5368'>{_m(a)}:</font> <b>{_m(d)}</b>", st["govde"]) for a, d in sag_satirlar if d]
    ust = Table([[sol, sag]], colWidths=[95 * mm, 85 * mm])
    ust.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    parcalar += [ust, Spacer(1, 3 * mm), Paragraph(_m(ie.get("baslik")), st["h2"])]
    if ie.get("aciklama"):
        parcalar.append(Paragraph(_m(ie["aciklama"]), st["govde"]))

    cihazlar = v.get("cihazlar") or []
    if cihazlar:
        veri = [[Paragraph(f"<b>{_m(x)}</b>", st["govde"]) for x in (e["cihaz"], e["marka"], e["seri"])]]
        for c in cihazlar:
            veri.append([Paragraph(_m(c.get("tur")), st["govde"]),
                         Paragraph(_m(" ".join(x for x in (c.get("marka"), c.get("model")) if x) or e["bos"]), st["govde"]),
                         Paragraph(_m(c.get("seri_no") or e["bos"]), st["govde"])])
        parcalar += [Paragraph(_m(e["cihazlar"]), st["bolum"]), _tablo(veri, [50 * mm, 80 * mm, 50 * mm])]

    kontrol = v.get("kontrol") or []
    if kontrol:
        veri = [[Paragraph(f"<b>{_m(e['madde'])}</b>", st["govde"]), Paragraph(f"<b>{_m(e['sonuc'])}</b>", st["govde"])]]
        for k in kontrol:
            tur, deger = k.get("tur"), k.get("deger")
            if tur == "evet_hayir":
                metin = e["evet"] if deger is True else e["hayir"] if deger is False else e["bos"]
            elif tur == "foto":
                metin = e["foto_var"] if deger else e["foto_yok"]
            elif deger is None or deger == "":
                metin = e["bos"]
            else:
                metin = f"{pb.sayi(deger) if isinstance(deger, (int, float)) else deger}{(' ' + k['birim']) if k.get('birim') else ''}"
            veri.append([Paragraph(_m(k.get("metin")) + (" *" if k.get("zorunlu") else ""), st["govde"]),
                         Paragraph(_m(metin), st["govde"])])
        parcalar += [Paragraph(_m(e["kontrol"]), st["bolum"]), _tablo(veri, [120 * mm, 60 * mm])]

    malzemeler = v.get("malzemeler") or []
    iscilik = int(v.get("iscilik_ucreti") or 0)
    if malzemeler or iscilik:
        veri = [[Paragraph(f"<b>{_m(x)}</b>", st["govde"] if i == 0 else st["sag"])
                 for i, x in enumerate((e["kalem"], e["miktar"], e["birim_fiyat"], e["tutar"]))]]
        ara = 0
        for k in malzemeler:
            tutar = int(round(float(k.get("miktar") or 0) * int(k.get("birim_fiyat") or 0)))
            ara += tutar
            veri.append([Paragraph(_m(k.get("ad")), st["govde"]),
                         Paragraph(f"{pb.sayi(k.get('miktar'))} {_m(k.get('birim') or '')}", st["sag"]),
                         Paragraph(pb.para((k.get("birim_fiyat") or 0) / 100, para_birimi, para_dili), st["sag"]),
                         Paragraph(pb.para(tutar / 100, para_birimi, para_dili), st["sag"])])
        if iscilik:
            ara += iscilik
            veri.append([Paragraph(_m(e["iscilik"]) + (f" ({v['iscilik_dk']} {e['dk']})" if v.get("iscilik_dk") else ""), st["govde"]),
                         Paragraph("", st["sag"]), Paragraph("", st["sag"]),
                         Paragraph(pb.para(iscilik / 100, para_birimi, para_dili), st["sag"])])
        oran = int(v.get("kdv_orani") or 0)
        kdv = int(round(ara * oran / 100))
        toplamlar = [(e["ara_toplam"], pb.para(ara / 100, para_birimi, para_dili), False)]
        if oran:
            toplamlar.append((e["kdv"].format(oran=oran), pb.para(kdv / 100, para_birimi, para_dili), False))
        toplamlar.append((e["genel_toplam"], pb.para((ara + kdv) / 100, para_birimi, para_dili), True))
        parcalar += [Paragraph(_m(e["malzeme"]), st["bolum"]), _tablo(veri, [90 * mm, 25 * mm, 32 * mm, 33 * mm]),
                     Spacer(1, 1.5 * mm), pb._toplam_tablosu(toplamlar, st)]  # noqa: SLF001

    if v.get("teknisyen_notu"):
        parcalar += [Paragraph(_m(e["not"]), st["bolum"]), Paragraph(_m(v["teknisyen_notu"]), st["govde"])]
    if v.get("foto_sayisi"):
        parcalar.append(Paragraph(f"{_m(e['fotograflar'])}: {int(v['foto_sayisi'])}", st["kucuk"]))

    blok: List[Any] = [Spacer(1, 3 * mm), Paragraph(_m(e["imza"]), st["bolum"])]
    png = v.get("imza_png")
    if png:
        try:
            okuyucu = ImageReader(io.BytesIO(png))
            gen, yuk = okuyucu.getSize()
            boy = min(25 * mm, 60 * mm * yuk / max(gen, 1))
            en = boy * gen / max(yuk, 1)
            blok.append(Image(io.BytesIO(png), width=en, height=boy, hAlign="LEFT"))
        except Exception:  # noqa: BLE001 - bozuk görsel PDF'i düşürmesin
            logger.warning("Servis formu: imza görseli eklenemedi")
        blok.append(Paragraph(f"{_m(e['imzalayan'])}: <b>{_m(v.get('imza_ad') or e['bos'])}</b> · "
                              f"{_m(e['imza_zamani'])}: {_m(v.get('imza_at') or e['bos'])}", st["kucuk"]))
    else:
        blok.append(Paragraph(_m(e["imzasiz"]), st["kucuk"]))
    parcalar.append(KeepTogether(blok))
    return pb._uret(parcalar, e["alt"], para_dili, f"{e['baslik']} {ie.get('no') or ''}")  # noqa: SLF001
