"""Faz 7K — PDF'lerde çok dilli yazı: yazı tipi yedek zinciri, Arapça (şekil + sağdan sola),
Devanagari (HarfBuzz) ve Çince. BÜTÜN ReportLab PDF üreticileri metni buradan geçirir.

Neden gerekli?
--------------
Sitenin yazı tipi Plus Jakarta Sans yalnız Latin harflerini taşıyor; Rusça, Arapça, Çince ve
Hintçe adlar PDF'te kutucuk ya da boş çıkıyordu. ReportLab bir paragraf içinde yazı tipi
yedeklemesi yapmıyor, Arapçayı birleştirmiyor ve sağdan sola dizmiyor.

Zincir (karakter başına, sırayla ilk kapsayan yazı tipi; hepsi SIL OFL 1.1, `data/fonts`):

1. MKSans — Plus Jakarta Sans (sitenin yazı tipi; Latin + Türkçe + simgeler: ₺ € — “ …)
2. MKLatinEk — Noto Sans, Latin genişletilmiş (ș ț ơ ư …)
3. MKKiril — Noto Sans, Kiril
4. MKYunan — Noto Sans, Yunan
5. MKArapca — Noto Sans Arabic (sunum biçimleri dâhil)
6. MKDevanagari — Noto Sans Devanagari (GSUB/GPOS ile; HarfBuzz şekillendiriyor)
7. STSong-Light — ReportLab'ın gömülü veri gerektirmeyen CID yazı tipi (Basitleştirilmiş Çince; Japonca kana ve
   tam genişlikli biçimler dâhil). Depoya CJK dosyası EKLENMEDİ (binlerce glif = MB'larca dosya); yazı tipi
   PDF'e gömülmez, okuyucu kendi Çince yazı tipini kullanır (tarayıcılar, macOS/iOS Önizleme, Android ve
   Windows'ta var; Adobe Reader bir kez "Asya dilleri yazı tipi paketi" isteyebilir). Kalın biçimi yok.

Boşluk, rakam ve noktalama (nötr karakterler) bulundukları parçanın yazı tipinde kalır;
böylece "Иван Петров" tek parça olur. Kalın (<b> ya da kalın stil) yedeğe de kalın geçer.

Paragraflar: `Paragraf` (ReportLab `Paragraph`'ın alt sınıfı) ayrıştırılmış parçaları yazı
tipine göre böler; Arapçayı `arabic-reshaper` ile birleşik (sunum) biçimlere çevirir ve satırlar
kırıldıktan SONRA her satırı Unicode çift yönlü algoritmasının sadeleştirilmiş biçimiyle
(W1–W7, N1–N2, I1–I2, L1, L2, L4; açık gömme/izole işaretleri yok sayılır) görsel sıraya dizer —
uzun Arapça paragraf da doğru satır sırasıyla akar. Arapça ağırlıklı paragraf sola yaslıysa
sağa yaslanır. Devanagari içeren paragrafta HarfBuzz (uharfbuzz) şekillendirmesi açılır;
ReportLab'ın tek yazı tipi varsayan şekillendiricisi, karışık yazı tipli sözcükleri bozmasın diye
yalnız Devanagari parçalarını şekillendirecek biçimde sarılır. Çince içeren paragraf CJK satır
kırma kuralını kullanır (boşluksuz metin taşmasın).

Kanvas metinleri (sayfa altı, sertifika): `metin_ciz` / `metin_genisligi` aynı zinciri kullanır.

Bilinen sınırlar: Çince PDF'e gömülmüyor (yukarıda, 7). Sayfa düzeni (tablo sütunları, etiket–değer
sırası) Arapçada da soldan sağa kalır — metin parçaları doğru şekillenip sağdan sola okunur. Devanagari'de
görüntü doğru (birleşik harfler, ि ön ekli ünlü); metin kopyalamada birleşik harfler kaynak harflere
eşlenir ama ön ekli ünlü (ि) görsel sırasıyla (ünsüzden önce) çıkar.
"""

from __future__ import annotations

import copy
import logging
import re
import threading
import unicodedata
from itertools import groupby
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple

from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.fonts import addMapping
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics, ttfonts
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import paragraph as _rl_paragraf
from reportlab.platypus import Paragraph

logger = logging.getLogger(__name__)

FONT_DIZINI = Path(__file__).resolve().parents[1] / "data" / "fonts"

YAZI = "MKSans"
KALIN = "MKSans-Bold"
CID_YEDEK = "STSong-Light"

#: (aile, normal dosya, kalın dosya) — sıra önemli (karakter başına ilk kapsayan).
ZINCIR: Tuple[Tuple[str, str, str], ...] = (
    ("MKSans", "PlusJakartaSans-Regular.ttf", "PlusJakartaSans-Bold.ttf"),
    ("MKLatinEk", "NotoSans-LatinEk-Regular.ttf", "NotoSans-LatinEk-Bold.ttf"),
    ("MKKiril", "NotoSans-Kiril-Regular.ttf", "NotoSans-Kiril-Bold.ttf"),
    ("MKYunan", "NotoSans-Yunan-Regular.ttf", "NotoSans-Yunan-Bold.ttf"),
    ("MKArapca", "NotoSansArabic-Regular.ttf", "NotoSansArabic-Bold.ttf"),
    ("MKDevanagari", "NotoSansDevanagari-Regular.ttf", "NotoSansDevanagari-Bold.ttf"),
)
# Zincirin son halkası (Çince/CJK) dosya değil: CID_YEDEK (aşağıda `_yedek`).

#: HarfBuzz ile şekillendirilen aileler (karmaşık yazı; Latin/Kiril/Arapça şekillendirilmez —
#: Arapça arabic-reshaper ile önceden birleştiriliyor).
SEKILLENEN_AILELER = frozenset({"MKDevanagari"})

_KILIT = threading.Lock()
_KAYITLI = False
#: yazı tipi adı → kapsadığı kod noktaları
_KAPSAM: Dict[str, FrozenSet[int]] = {}
#: yazı tipi adı → (aile, kalın mı)
_AILE: Dict[str, Tuple[str, bool]] = {}
_SEKILLENEN_ADLAR: FrozenSet[str] = frozenset()
#: yüz (PostScript) adı → şekillenen TTFont (ToUnicode'da özel alan gliflerinin adlarını okumak için)
_YUZ_FONT: Dict[str, Any] = {}

_ARAP = re.compile(r"[\u0600-\u06ff\u0750-\u077f\u0870-\u08ff\ufb50-\ufdff\ufe70-\ufeff]")
_DEVA = re.compile(r"[\u0900-\u097f\ua8e0-\ua8ff]")
_CJK = re.compile(r"[\u2e80-\u2fdf\u3000-\u303f\u3040-\u30ff\u3100-\u312f\u31a0-\u31ff\u3400-\u4dbf"
                  r"\u4e00-\u9fff\uf900-\ufaff\ufe30-\ufe4f\uff00-\uffef]")
_RTL_SINIF = frozenset({"R", "AL"})


def _cjk_mi(kod: int) -> bool:
    return (0x2E80 <= kod <= 0x2FDF or 0x3000 <= kod <= 0x312F or 0x31A0 <= kod <= 0x31FF
            or 0x3400 <= kod <= 0x4DBF or 0x4E00 <= kod <= 0x9FFF or 0xF900 <= kod <= 0xFAFF
            or 0xFE30 <= kod <= 0xFE4F or 0xFF00 <= kod <= 0xFFEF)


# ---------------------------------------------------------------------------
# Kayıt
# ---------------------------------------------------------------------------
def kaydet() -> None:
    """Zincirin bütün yazı tiplerini bir kez kaydeder (süreç başına; iş parçacığına güvenli)."""
    global _KAYITLI, _SEKILLENEN_ADLAR
    if _KAYITLI:
        return
    with _KILIT:
        if _KAYITLI:
            return
        sekillenen = set()
        for aile, normal, kalin in ZINCIR:
            for ad, dosya, kalin_mi in ((aile, normal, False), (f"{aile}-Bold", kalin, True)):
                # Hepsi "şekillendirilebilir" işaretli (ReportLab paragraf düzeyinde stilin yazı tipine
                # bakıyor); gerçekte yalnız SEKILLENEN_AILELER şekillendiriliyor (_bolumlu_sekillendir).
                font = TTFont(ad, str(FONT_DIZINI / dosya))
                pdfmetrics.registerFont(font)
                _KAPSAM[ad] = frozenset(font.face.charToGlyph)
                _AILE[ad] = (aile, kalin_mi)
                if aile in SEKILLENEN_AILELER:
                    sekillenen.add(ad)
                    yuz = font.face.name
                    _YUZ_FONT[yuz.decode("latin1") if isinstance(yuz, bytes) else str(yuz)] = font
            # <b> etiketi kalın dosyaya düşsün (italik dosya yok: düz kalıyor).
            addMapping(aile, 0, 0, aile)
            addMapping(aile, 1, 0, f"{aile}-Bold")
            addMapping(aile, 0, 1, aile)
            addMapping(aile, 1, 1, f"{aile}-Bold")
        try:
            pdfmetrics.registerFont(UnicodeCIDFont(CID_YEDEK))
            addMapping(CID_YEDEK, 0, 0, CID_YEDEK)
            addMapping(CID_YEDEK, 1, 0, CID_YEDEK)
            addMapping(CID_YEDEK, 0, 1, CID_YEDEK)
            addMapping(CID_YEDEK, 1, 1, CID_YEDEK)
        except Exception:  # noqa: BLE001 - CID verisi yoksa son halka yok sayılır
            logger.warning("STSong-Light kaydedilemedi; Çince metin kutucuk çıkabilir")
        _SEKILLENEN_ADLAR = frozenset(sekillenen)
        _rl_paragraf.shapeFragWord = _bolumlu_sekillendir
        _KAYITLI = True


def _kapsar(font_adi: str, kod: int) -> bool:
    kume = _KAPSAM.get(font_adi)
    if kume is not None:
        return kod in kume
    if font_adi == CID_YEDEK:
        return _cjk_mi(kod)
    # Standart Type 1 yazı tipleri (Courier, Helvetica …) WinAnsi kodlamasıyla.
    try:
        chr(kod).encode("cp1252")
        return True
    except UnicodeEncodeError:
        return False


def _yedek(kod: int, kalin: bool) -> Optional[str]:
    for aile, _, _ in ZINCIR:
        ad = f"{aile}-Bold" if kalin else aile
        if kod in _KAPSAM.get(ad, ()):
            return ad
    if _cjk_mi(kod) and CID_YEDEK in pdfmetrics.getRegisteredFontNames():
        return CID_YEDEK
    return None


def _notr(ch: str) -> bool:
    """Boşluk, rakam, noktalama, birleşen işaret: önceki parçanın yazı tipinde kalabilir."""
    return unicodedata.category(ch)[0] in "ZPNSMC"


def parcala(metin: str, birincil: str = YAZI) -> List[Tuple[str, str]]:
    """Metni [(yazı tipi adı, parça)] dizisine böler (mantıksal sıra korunur)."""
    kaydet()
    kalin = _AILE.get(birincil, ("", birincil.endswith("-Bold")))[1]
    sonuc: List[Tuple[str, str]] = []
    simdiki: Optional[str] = None
    tampon: List[str] = []
    for ch in metin:
        kod = ord(ch)
        if simdiki is not None and _notr(ch) and _kapsar(simdiki, kod):
            font = simdiki
        elif _kapsar(birincil, kod):
            font = birincil
        else:
            font = _yedek(kod, kalin) or birincil
        if font != simdiki and tampon:
            sonuc.append((simdiki, "".join(tampon)))  # type: ignore[arg-type]
            tampon = []
        simdiki = font
        tampon.append(ch)
    if tampon:
        sonuc.append((simdiki, "".join(tampon)))  # type: ignore[arg-type]
    return sonuc


# ---------------------------------------------------------------------------
# Arapça: birleşik (sunum) biçimler
# ---------------------------------------------------------------------------
_BICIMLEYICI = None


def _bicimleyici():
    global _BICIMLEYICI
    if _BICIMLEYICI is None:
        import arabic_reshaper
        from arabic_reshaper.reshaper_config import ENABLE_NO_LIGATURES, config_for_true_type_font, default_config

        # Yalnız zorunlu lam-elif bağları (ﻻ ﻷ ﻹ ﻵ); "محمد" → ﷴ gibi sözcük/harf bağları adları
        # değiştirmesin ve metin kopyalanınca harfler aynı çıksın.
        ayar = config_for_true_type_font(str(FONT_DIZINI / ZINCIR[4][1]), ENABLE_NO_LIGATURES)
        ayar["support_ligatures"] = True
        for anahtar in default_config:
            if anahtar.startswith("ARABIC LIGATURE") or anahtar == "RIAL SIGN":
                ayar[anahtar] = anahtar.startswith("ARABIC LIGATURE LAM WITH ALEF")
        ayar["delete_harakat"] = False
        _BICIMLEYICI = arabic_reshaper.ArabicReshaper(configuration=ayar)
    return _BICIMLEYICI


def arapca_bicimle(metin: str) -> str:
    """Arapça harfleri bağlamına göre birleşik biçimlerine çevirir (mantıksal sıra korunur)."""
    if not metin or not _ARAP.search(metin):
        return metin
    try:
        return _bicimleyici().reshape(metin)
    except Exception:  # noqa: BLE001 - biçimlenemeyen metin olduğu gibi kalsın
        logger.exception("Arapça metin biçimlenemedi")
        return metin


# ---------------------------------------------------------------------------
# Çift yönlü sıralama (Unicode Bidi, sadeleştirilmiş)
# ---------------------------------------------------------------------------
_AYNA = {"(": ")", ")": "(", "[": "]", "]": "[", "{": "}", "}": "{", "<": ">", ">": "<", "«": "»", "»": "«",
         "‹": "›", "›": "‹"}
_NOTR_SINIFLAR = frozenset({"B", "S", "WS", "ON"})


def _sinif(ch: str) -> str:
    s = unicodedata.bidirectional(ch) or "L"
    if s in ("LRE", "RLE", "LRO", "RLO", "PDF", "LRI", "RLI", "FSI", "PDI", "BN"):
        return "ON"
    return s


def taban_rtl_mi(metin: str) -> bool:
    """P2/P3: ilk güçlü karakter sağdan solaysa paragraf sağdan soladır."""
    for ch in metin:
        s = unicodedata.bidirectional(ch)
        if s == "L":
            return False
        if s in _RTL_SINIF:
            return True
    return False


def _seviyeler(siniflar: Sequence[str], taban: int) -> List[int]:
    t = list(siniflar)
    n = len(t)
    sos = "R" if taban else "L"
    # W1
    onceki = sos
    for i in range(n):
        if t[i] == "NSM":
            t[i] = onceki
        onceki = t[i]
    # W2 + W3
    son = sos
    for i in range(n):
        if t[i] in ("L", "R", "AL"):
            son = t[i]
        elif t[i] == "EN" and son == "AL":
            t[i] = "AN"
    t = ["R" if x == "AL" else x for x in t]
    # W4
    for i in range(1, n - 1):
        if t[i] == "ES" and t[i - 1] == "EN" and t[i + 1] == "EN":
            t[i] = "EN"
        elif t[i] == "CS" and t[i - 1] == t[i + 1] and t[i - 1] in ("EN", "AN"):
            t[i] = t[i - 1]
    # W5
    i = 0
    while i < n:
        if t[i] == "ET":
            j = i
            while j < n and t[j] == "ET":
                j += 1
            if (i > 0 and t[i - 1] == "EN") or (j < n and t[j] == "EN"):
                for k in range(i, j):
                    t[k] = "EN"
            i = j
        else:
            i += 1
    # W6
    t = ["ON" if x in ("ES", "ET", "CS") else x for x in t]
    # W7
    son = sos
    for i in range(n):
        if t[i] in ("L", "R"):
            son = t[i]
        elif t[i] == "EN" and son == "L":
            t[i] = "L"
    # N1 + N2
    i = 0
    while i < n:
        if t[i] in _NOTR_SINIFLAR:
            j = i
            while j < n and t[j] in _NOTR_SINIFLAR:
                j += 1
            once = sos if i == 0 else ("R" if t[i - 1] in ("R", "EN", "AN") else "L")
            sonra = sos if j == n else ("R" if t[j] in ("R", "EN", "AN") else "L")
            yon = once if once == sonra else sos
            for k in range(i, j):
                t[k] = yon
            i = j
        else:
            i += 1
    # I1 + I2
    seviye: List[int] = []
    for x in t:
        if taban == 0:
            seviye.append(1 if x == "R" else 2 if x in ("AN", "EN") else 0)
        else:
            seviye.append(2 if x in ("L", "EN", "AN") else 1)
    # L1: satır sonundaki boşluklar taban seviyesine
    k = n - 1
    while k >= 0 and siniflar[k] in ("WS", "S", "B"):
        seviye[k] = taban
        k -= 1
    return seviye


def _sira(seviye: Sequence[int]) -> List[int]:
    """L2: en yüksek seviyeden en düşük tek seviyeye kadar ardışık dizileri ters çevir."""
    sira = list(range(len(seviye)))
    if not seviye:
        return sira
    en_yuksek = max(seviye)
    tekler = [s for s in seviye if s % 2]
    if not tekler:
        return sira
    en_dusuk_tek = min(tekler)
    for sev in range(en_yuksek, en_dusuk_tek - 1, -1):
        i = 0
        n = len(sira)
        while i < n:
            if seviye[sira[i]] >= sev:
                j = i
                while j < n and seviye[sira[j]] >= sev:
                    j += 1
                sira[i:j] = reversed(sira[i:j])
                i = j
            else:
                i += 1
    return sira


def gorsel_sira(metin: str, taban_rtl: Optional[bool] = None) -> str:
    """Tek satırlık mantıksal metin → çizim (soldan sağa) sırası; ters seviyede ayna karakterler."""
    if not metin or not any(unicodedata.bidirectional(c) in _RTL_SINIF for c in metin):
        return metin
    taban = 1 if (taban_rtl_mi(metin) if taban_rtl is None else taban_rtl) else 0
    siniflar = [_sinif(c) for c in metin]
    seviye = _seviyeler(siniflar, taban)
    return "".join(_AYNA.get(metin[i], metin[i]) if seviye[i] % 2 else metin[i] for i in _sira(seviye))


# ---------------------------------------------------------------------------
# Paragraf
# ---------------------------------------------------------------------------
def _parcalari_bol(parcalar: Sequence[Any]) -> List[Any]:
    """ReportLab'ın ayrıştırdığı parçaları (frag) yazı tipi kapsamına göre böler; Arapçayı biçimler."""
    yeni: List[Any] = []
    for f in parcalar:
        metin = getattr(f, "text", None)
        if not metin or getattr(f, "cbDefn", None) is not None or getattr(f, "lineBreak", False) \
                or isinstance(metin, ttfonts.ShapedStr):
            yeni.append(f)
            continue
        metin = arapca_bicimle(metin)
        bolumler = parcala(metin, f.fontName)
        if len(bolumler) == 1 and bolumler[0][0] == f.fontName:
            if metin != f.text:
                f = f.clone(text=metin)
            yeni.append(f)
            continue
        for font, parca in bolumler:
            yeni.append(f.clone(text=parca, fontName=font))
    return yeni


class Paragraf(Paragraph):
    """Çok dilli `Paragraph`: yazı tipi yedeği, Arapça (şekil + sağdan sola), Devanagari, Çince."""

    def __init__(self, text, style=None, *args, **kwargs):
        kaydet()
        super().__init__(text, style, *args, **kwargs)
        self.frags = _parcalari_bol(self.frags)
        duz = "".join(str(getattr(f, "text", "") or "") for f in self.frags)
        self._rtl = bool(_ARAP.search(duz)) or any(unicodedata.bidirectional(c) in _RTL_SINIF for c in duz)
        self._taban_rtl = taban_rtl_mi(duz) if self._rtl else False
        degisiklik: Dict[str, Any] = {}
        if self._taban_rtl and self.style.alignment == TA_LEFT:
            degisiklik["alignment"] = TA_RIGHT
        if _DEVA.search(duz) and not getattr(self.style, "shaping", 0):
            degisiklik["shaping"] = 1
        if _CJK.search(duz) and getattr(self.style, "wordWrap", None) != "CJK":
            degisiklik["wordWrap"] = "CJK"
        if degisiklik:
            self.style = ParagraphStyle(f"{self.style.name}~", parent=self.style, **degisiklik)

    def drawPara(self, debug=0):
        if not getattr(self, "_rtl", False):
            return super().drawPara(debug)
        asil = self.blPara
        self.blPara = _gorsel_satirlar(asil, 1 if self._taban_rtl else 0)
        try:
            return super().drawPara(debug)
        finally:
            self.blPara = asil


def _gorsel_satirlar(bl: Any, taban: int) -> Any:
    """Kırılmış satırları (mantıksal) görsel sıraya dizilmiş bir kopyaya çevirir."""
    yeni = copy.copy(bl)
    satirlar = []
    if bl.kind == 0:
        for bosluk, sozcukler in bl.lines:
            metin = " ".join(sozcukler)
            satirlar.append((bosluk, [gorsel_sira(metin, bool(taban))]))
    else:
        for satir in bl.lines:
            s2 = copy.copy(satir)
            s2.words = _parcalari_sirala(list(satir.words), taban)
            satirlar.append(s2)
    yeni.lines = satirlar
    return yeni


def _parcalari_sirala(parcalar: List[Any], taban: int) -> List[Any]:
    """Bir satırın parçalarını (frag) karakter düzeyinde görsel sıraya dizer, yeniden gruplar."""
    birimler: List[Tuple[int, str, str]] = []  # (parça no, metin, sınıf)
    for i, f in enumerate(parcalar):
        metin = getattr(f, "text", "")
        if not metin or isinstance(metin, ttfonts.ShapedStr) or getattr(f, "cbDefn", None) is not None:
            birimler.append((i, metin or "", "L" if metin else "ON"))
            continue
        for ch in metin:
            birimler.append((i, ch, _sinif(ch)))
    if not any(s in _RTL_SINIF for _, _, s in birimler):
        return parcalar
    seviye = _seviyeler([s for _, _, s in birimler], taban)
    sira = _sira(seviye)
    sonuc: List[Any] = []
    for i, grup in groupby(sira, key=lambda k: birimler[k][0]):
        grup = list(grup)
        f = parcalar[i]
        metin = getattr(f, "text", "")
        if not metin or isinstance(metin, ttfonts.ShapedStr) or getattr(f, "cbDefn", None) is not None:
            sonuc.append(f)
            continue
        parca = "".join(_AYNA.get(birimler[k][1], birimler[k][1]) if seviye[k] % 2 else birimler[k][1] for k in grup)
        sonuc.append(f.clone(text=parca))
    return sonuc


# ---------------------------------------------------------------------------
# HarfBuzz: yalnız Devanagari parçalarını şekillendir
# ---------------------------------------------------------------------------
_ASIL_SEKILLENDIR = ttfonts.shapeFragWord
#: yüz adı (PostScript) → {özel alan kodu: kaynak metin} — metin kopyalama (ToUnicode) için
_OZEL_KARSILIK: Dict[str, Dict[int, str]] = {}


def _bolumlu_sekillendir(w, *args, **kwargs):
    """ReportLab'ın `shapeFragWord`'ü sözcüğün TAMAMINI ilk parçanın yazı tipiyle şekillendiriyor;
    "नमस्ते," gibi karışık yazı tipli sözcükte virgül bozuk çıkıyor. Burada sözcük yazı tipine göre
    bölünür, yalnız şekillenen ailelerin parçaları şekillendirilir."""
    if isinstance(w, ttfonts.ShapedFragWord) or len(w) < 2:
        return w
    parcalar = w[1:]
    if not any(getattr(f, "fontName", None) in _SEKILLENEN_ADLAR for f, _ in parcalar):
        return w
    yeni = ttfonts.makeShapedFragWord(w)([])
    toplam = 0.0
    degisti = False
    for anahtar, grup in groupby(parcalar, key=lambda fs: (getattr(fs[0], "fontName", None)
                                                           if getattr(fs[0], "cbDefn", None) is None else id(fs[0]))):
        grup = list(grup)
        if anahtar in _SEKILLENEN_ADLAR:
            genislik = sum(pdfmetrics.stringWidth(s, f.fontName, f.fontSize) for f, s in grup)
            alt = [genislik] + grup
            sonuc = _ASIL_SEKILLENDIR(alt, *args, **kwargs)
            if sonuc is not alt:
                degisti = True
                _ozel_karsiliklari_kaydet(grup, sonuc)
            toplam += sonuc[0]
            yeni.extend(sonuc[1:])
        else:
            for f, s in grup:
                toplam += getattr(f, "width", 0) if getattr(f, "cbDefn", None) is not None else \
                    pdfmetrics.stringWidth(s, f.fontName, f.fontSize)
                yeni.append((f, s))
    if not degisti:
        return w
    yeni.insert(0, toplam)
    return yeni


def _ozel_karsiliklari_kaydet(grup: Sequence[Tuple[Any, str]], sonuc: Sequence[Any]) -> None:
    """HarfBuzz'ın birleşik glifleri özel alana (U+E000…) eşleniyor; PDF'te metin kopyalanınca
    kaynak harfler çıksın diye kümeyi (cluster) kaynak metne bağlar."""
    kaynak = "".join(s for _, s in grup)
    for f, s in sonuc[1:]:
        veri = getattr(s, "__shapeData__", None)
        if not veri:
            continue
        kumeler = sorted({d.cluster for d in veri if d.cluster >= 0})
        sonraki = {k: (kumeler[i + 1] if i + 1 < len(kumeler) else len(kaynak)) for i, k in enumerate(kumeler)}
        try:
            yuz = pdfmetrics.getFont(f.fontName).face.name
        except Exception:  # noqa: BLE001
            continue
        if isinstance(yuz, bytes):
            yuz = yuz.decode("latin1")
        tablo = _OZEL_KARSILIK.setdefault(yuz, {})
        # Küme başına: kaynak metinden, kümedeki ÖZEL OLMAYAN gliflerin harfleri düşülür; kalan
        # harfler kümenin (ilk) özel glifine yazılır — "हि" kümesinde ि'nin bağlam biçimi özel
        # alanda, ह sıradan: özel glif "ि" olur (yoksa metin "हिह" çıkıyordu).
        kume_glifleri: Dict[int, List[str]] = {}
        for ch, d in zip(s, veri):
            if d.cluster >= 0:
                kume_glifleri.setdefault(d.cluster, []).append(ch)
        for kume, glifler in kume_glifleri.items():
            ozeller = [g for g in glifler if 0xE000 <= ord(g) <= 0xF8FF]
            if not ozeller:
                continue
            kalan = list(kaynak[kume:sonraki[kume]])
            for g in glifler:
                if g not in ozeller and g in kalan:
                    kalan.remove(g)
            # Ön ekli ünlü (ि) kümenin ilk glifi ve özelse yalnız ona; kalan harfler sıradaki özel glife.
            if glifler[0] in ozeller and "\u093f" in kalan and len(ozeller) > 1:
                if ord(glifler[0]) not in tablo:
                    tablo[ord(glifler[0])] = "\u093f"
                kalan.remove("\u093f")
                ozeller = ozeller[1:]
            if kalan and ord(ozeller[0]) not in tablo:
                tablo[ord(ozeller[0])] = "".join(kalan)


_ASIL_TOUNICODE = ttfonts.makeToUnicodeCMap


_UNI_ADI = re.compile(r"^uni((?:[0-9A-Fa-f]{4})+)(?:[._]|$)")


def _glif_adi_metni(yuz: str) -> Dict[int, str]:
    """Özel alan kodu → glif adından kaynak metin. Noto Devanagari'de birleşik gliflerin adı kaynak
    dizisini taşıyor ("uni0915094D0937" = क्ष, "uni0930094D" = र् reph, "uni093F.08" = ि biçimi);
    bağlamdan bağımsız ve kesin olduğu için küme tahmininin önüne geçer."""
    font = _YUZ_FONT.get(yuz)
    adlar = getattr(font, "_TTFont__hbUnis", None) or {}
    sonuc: Dict[int, str] = {}
    for ad, kod in adlar.items():
        m = _UNI_ADI.match(ad if isinstance(ad, str) else ad.decode("latin1"))
        ad = ad if isinstance(ad, str) else ad.decode("latin1")
        if m:
            h = m.group(1)
            sonuc[kod] = "".join(chr(int(h[i:i + 4], 16)) for i in range(0, len(h), 4))
        elif ad.lower().startswith("null"):
            # Boş yer tutucu (NullMark): bağa katılan işaretin eski yeri; hangi işaret olduğu bağlama
            # göre değişiyor — görünmez sıfır genişlikli boşluk.
            sonuc[kod] = "\u200b"
    return sonuc


def _tounicode(fontname, subset):
    """Özel alana eşlenmiş glifler için ToUnicode'da kaynak metni yaz (yoksa ReportLab'ınki)."""
    ad = fontname.decode("latin1") if isinstance(fontname, bytes) else str(fontname)
    yuz = ad.split("+", 1)[-1]
    tablo = dict(_OZEL_KARSILIK.get(yuz) or {})
    tablo.update(_glif_adi_metni(yuz))
    if not tablo or not any(k in tablo for k in subset):
        return _ASIL_TOUNICODE(fontname, subset)
    satirlar = []
    for kod, uni in enumerate(subset):
        hedef = tablo.get(uni)
        if hedef:
            onaltilik = "".join(f"{b:02X}" for b in hedef.encode("utf-16-be"))
        else:
            onaltilik = "".join(f"{b:02X}" for b in chr(uni).encode("utf-16-be"))
        satirlar.append(f"<{kod:02X}> <{onaltilik}>")
    return "\n".join((
        "/CIDInit /ProcSet findresource begin",
        "12 dict begin",
        "begincmap",
        "/CIDSystemInfo",
        "<< /Registry (%s)" % ad,
        "/Ordering (%s)" % ad,
        "/Supplement 0",
        ">> def",
        "/CMapName /%s def" % ad,
        "/CMapType 2 def",
        "1 begincodespacerange",
        "<00> <%02X>" % (len(subset) - 1),
        "endcodespacerange",
        "%d beginbfchar" % len(subset),
    ) + tuple(satirlar) + (
        "endbfchar",
        "endcmap",
        "CMapName currentdict /CMap defineresource pop",
        "end",
        "end",
    ))


ttfonts.makeToUnicodeCMap = _tounicode


# ---------------------------------------------------------------------------
# Kanvas
# ---------------------------------------------------------------------------
def _satir_parcalari(metin: str, font: str, boyut: float) -> List[Tuple[str, Any, float]]:
    kaydet()
    metin = arapca_bicimle(str(metin or ""))
    parcalar = parcala(metin, font)
    if any(unicodedata.bidirectional(c) in _RTL_SINIF for c in metin):
        sahte = [_Parca(f, s) for f, s in parcalar]
        sirali = _parcalari_sirala(sahte, 1 if taban_rtl_mi(metin) else 0)
        parcalar = [(p.fontName, p.text) for p in sirali]
    sonuc: List[Tuple[str, Any, float]] = []
    for f, s in parcalar:
        if f in _SEKILLENEN_ADLAR and pdfmetrics.getFont(f).shapable:
            sekilli = ttfonts.shapeStr(s, f, boyut)
            veri = getattr(sekilli, "__shapeData__", None)
            if veri:
                genislik = sum(d.x_advance for d in veri) * boyut / 1000
                sonuc.append((f, sekilli, genislik))
                continue
        sonuc.append((f, s, pdfmetrics.stringWidth(s, f, boyut)))
    return sonuc


class _Parca:
    """Kanvas satırı için parça (frag) benzeri küçük nesne."""

    def __init__(self, fontName: str, text: str):
        self.fontName = fontName
        self.text = text

    def clone(self, **kw):
        p = _Parca(self.fontName, self.text)
        for k, v in kw.items():
            setattr(p, k, v)
        return p


def metin_genisligi(metin: Any, font: str, boyut: float) -> float:
    return sum(g for _, _, g in _satir_parcalari(str(metin or ""), font, boyut))


def metin_ciz(c: Any, x: float, y: float, metin: Any, font: str = YAZI, boyut: float = 10, hiza: str = "sol") -> float:
    """Kanvasa tek satır çok dilli metin çizer; `hiza`: sol | sag | orta. Genişliği döndürür."""
    parcalar = _satir_parcalari(str(metin or ""), font, boyut)
    toplam = sum(g for _, _, g in parcalar)
    x0 = x - toplam if hiza == "sag" else x - toplam / 2 if hiza == "orta" else x
    for f, s, g in parcalar:
        c.setFont(f, boyut)
        c.drawString(x0, y, s)
        x0 += g
    return toplam


def kod_blogu(metin: str, stil: ParagraphStyle):
    """Kod bloğu: yalnız WinAnsi karakterleri varsa `Preformatted` (eş aralıklı), değilse
    boşlukları koruyan çok dilli paragraf."""
    from reportlab.platypus import Preformatted
    from xml.sax.saxutils import escape

    try:
        metin.encode("cp1252")
        return Preformatted(metin, stil)
    except UnicodeEncodeError:
        satirlar = [escape(s).replace(" ", "&nbsp;") for s in metin.split("\n")]
        return Paragraf("<br/>".join(satirlar) or "&nbsp;", stil)


def gomulu_yazi_tipleri(veri: bytes) -> List[str]:
    """Testler için: PDF'teki yazı tiplerinin taban adları (alt küme öneki atılmış)."""
    import io

    from pypdf import PdfReader

    adlar = set()
    for sayfa in PdfReader(io.BytesIO(veri)).pages:
        kaynaklar = (sayfa.get("/Resources") or {}).get_object() if sayfa.get("/Resources") else {}
        fontlar = kaynaklar.get("/Font") or {}
        fontlar = fontlar.get_object() if hasattr(fontlar, "get_object") else fontlar
        for ref in fontlar.values():
            font = ref.get_object()
            ad = str(font.get("/BaseFont", ""))
            adlar.add(ad.lstrip("/").split("+", 1)[-1])
    return sorted(adlar)


__all__ = [
    "YAZI", "KALIN", "CID_YEDEK", "ZINCIR", "kaydet", "parcala", "arapca_bicimle", "gorsel_sira", "taban_rtl_mi",
    "Paragraf", "metin_ciz", "metin_genisligi", "kod_blogu", "gomulu_yazi_tipleri",
]
