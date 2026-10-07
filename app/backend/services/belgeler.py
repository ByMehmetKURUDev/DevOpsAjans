"""Faz 5B — belgeler, wiki ve strateji araçları: kurallar ve ortak yardımcılar.

Uçlar `routers/belgeler.py`de, AI `services/belgeler_ai.py`de, PDF
`services/belge_pdf.py`de. Tablolar ve sahiplik kuralları `models/belgeler.py`
başında.

Editör kararı
-------------
Yeni paket yok. Gövde Markdown; HTML'e çevirme ve temizleme TEK yerde,
sunucuda (`services/guvenli_html.belge_html`): ham HTML hiç geçmiyor, çıktı
izinli etiket listesinden geçiyor. Ön yüz Markdown'ı kendisi HTML'e çevirmiyor
— önizleme ve okuma görünümü sunucunun ürettiği temiz HTML'i gösteriyor
(bilgi bankasındaki desen). Böylece "istemcide başka, sunucuda başka
temizleyici" ayrışması olamıyor.

Yapılacaklar
------------
Belge gövdesindeki `- [ ] metin` / `- [x] metin` satırları. `@eposta` ile
kişiye atanır (birden çok olabilir). Projeye görev olarak aktarılan maddenin
sonuna `→ #<görev id>` eklenir (aynı madde iki kez aktarılmasın). "Yapılacaklarım"
görünümü bu satırları belgelerden okuyor; ayrı tablo yok — belge tek kaynak.
Görevler modülü (Faz 2B) AYRI: madde oradan görev olunca bağlantıyla duruyor.
"""

import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from models.belgeler import BelgeSurumleri, Belgeler
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

MODUL = "belgeler"
IZIN = "belgeler"
DILLER = ("tr", "en", "de", "ru", "zh", "hi", "ar")

ALANLAR: Tuple[str, ...] = ("ajans", "musteri", "proje")
GORUNURLUKLER: Tuple[str, ...] = ("ekip", "paylasilan")
SINIR = {
    "baslik": 200,
    "icerik": 100_000,
    "etiket": 30,
    "etiket_sayisi": 10,
    "kutu": 3000,
    "isletme": 1000,
    "arama": 100,
}
#: Belge başına saklanan en çok sürüm (eskiler silinir).
SURUM_SINIRI = 20
LISTE_SINIRI = 300
#: "Yapılacaklarım" taramasında bakılan en çok belge (en yeni önce).
YAPILACAK_TARAMA_SINIRI = 500
YAPILACAK_SINIRI = 300
#: Müşteri modül ayarı yoksa.
VARSAYILAN_BELGE_SINIRI = 200


class BelgeHatasi(Exception):
    """Ön yüzün yedi dilde metne çevirdiği hata: `kod` + HTTP durumu + ek alanlar."""

    def __init__(self, kod: str, durum: int = 400, **ek: Any):
        super().__init__(kod)
        self.kod = kod
        self.durum = durum
        self.ek = ek

    def detay(self) -> Dict[str, Any]:
        return {"kod": self.kod, **self.ek}


# ---------------------------------------------------------------------------
# Strateji şablonları (TEK yer: ön yüz `/meta`dan okuyor, PDF buradan çiziyor)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Kutu:
    anahtar: str
    #: 1 tabanlı ızgara konumu ve genişliği (CSS grid ile aynı anlam).
    sutun: int
    satir: int
    en: int = 1
    boy: int = 1


@dataclass(frozen=True)
class StratejiSablonu:
    tur: str
    sutun: int
    satir: int
    kutular: Tuple[Kutu, ...]
    #: PDF yatay A4 (kanvaslar geniş).
    yatay: bool = False

    def sozluk(self) -> Dict[str, Any]:
        return {
            "tur": self.tur,
            "sutun": self.sutun,
            "satir": self.satir,
            "yatay": self.yatay,
            "kutular": [{"anahtar": k.anahtar, "sutun": k.sutun, "satir": k.satir, "en": k.en, "boy": k.boy} for k in self.kutular],
        }

    @property
    def anahtarlar(self) -> Tuple[str, ...]:
        return tuple(k.anahtar for k in self.kutular)


def _K(a: str, s: int, r: int, en: int = 1, boy: int = 1) -> Kutu:
    return Kutu(a, s, r, en, boy)


_KANVAS_ALT = (_K("maliyetler", 1, 3, 5, 1), _K("gelirler", 6, 3, 5, 1))
STRATEJI_SABLONLARI: Dict[str, StratejiSablonu] = {
    s.tur: s
    for s in (
        StratejiSablonu("swot", 2, 2, (_K("guclu", 1, 1), _K("zayif", 2, 1), _K("firsatlar", 1, 2), _K("tehditler", 2, 2))),
        StratejiSablonu(
            "is_modeli", 10, 3,
            (_K("ortaklar", 1, 1, 2, 2), _K("faaliyetler", 3, 1, 2, 1), _K("kaynaklar", 3, 2, 2, 1),
             _K("deger", 5, 1, 2, 2), _K("iliskiler", 7, 1, 2, 1), _K("kanallar", 7, 2, 2, 1),
             _K("segmentler", 9, 1, 2, 2)) + _KANVAS_ALT,
            yatay=True,
        ),
        StratejiSablonu(
            "lean", 10, 3,
            (_K("problem", 1, 1, 2, 2), _K("cozum", 3, 1, 2, 1), _K("metrikler", 3, 2, 2, 1),
             _K("deger_onerisi", 5, 1, 2, 2), _K("haksiz_avantaj", 7, 1, 2, 1), _K("kanallar", 7, 2, 2, 1),
             _K("segmentler", 9, 1, 2, 2)) + _KANVAS_ALT,
            yatay=True,
        ),
        StratejiSablonu(
            "pestle", 3, 2,
            (_K("politik", 1, 1), _K("ekonomik", 2, 1), _K("sosyal", 3, 1),
             _K("teknolojik", 1, 2), _K("hukuki", 2, 2), _K("cevresel", 3, 2)),
        ),
        StratejiSablonu(
            "porter", 3, 3,
            (_K("yeni_girenler", 2, 1), _K("tedarikci_gucu", 1, 2), _K("rekabet", 2, 2),
             _K("alici_gucu", 3, 2), _K("ikameler", 2, 3)),
        ),
        StratejiSablonu(
            "mckinsey_7s", 3, 3,
            (_K("strateji", 1, 1), _K("yapi", 2, 1), _K("sistemler", 3, 1), _K("ortak_degerler", 1, 2, 3, 1),
             _K("stil", 1, 3), _K("personel", 2, 3), _K("yetenekler", 3, 3)),
        ),
        StratejiSablonu("mavi_okyanus", 2, 2, (_K("ortadan_kaldir", 1, 1), _K("yukselt", 2, 1), _K("azalt", 1, 2), _K("yarat", 2, 2))),
        StratejiSablonu(
            "ikigai", 3, 3,
            (_K("sevdigin", 1, 1), _K("tutku", 2, 1), _K("iyi_oldugun", 3, 1),
             _K("misyon", 1, 2), _K("ikigai", 2, 2), _K("meslek", 3, 2),
             _K("dunyanin_ihtiyaci", 1, 3), _K("ugras", 2, 3), _K("para_kazandiran", 3, 3)),
        ),
    )
}
STRATEJI_TURLERI: Tuple[str, ...] = tuple(STRATEJI_SABLONLARI)
TURLER: Tuple[str, ...] = ("belge",) + STRATEJI_TURLERI

#: PDF'in ve yapay zekâ isteminin kullandığı adlar (tr/en/de). Ön yüzün 7 dilli adları
#: `src/i18n/ek/belgeler/<dil>.json` › `sablon`; tr/en/de bunlarla AYNI (test bağlıyor).
SABLON_ADLARI: Dict[str, Dict[str, Dict[str, str]]] = {
    "tr": {
        "swot": {"ad": "SWOT analizi", "guclu": "Güçlü yönler", "zayif": "Zayıf yönler", "firsatlar": "Fırsatlar",
                 "tehditler": "Tehditler"},
        "is_modeli": {"ad": "İş Modeli Kanvası", "ortaklar": "Kilit ortaklar", "faaliyetler": "Kilit faaliyetler",
                      "kaynaklar": "Kilit kaynaklar", "deger": "Değer önerisi", "iliskiler": "Müşteri ilişkileri",
                      "kanallar": "Kanallar", "segmentler": "Müşteri segmentleri", "maliyetler": "Maliyet yapısı",
                      "gelirler": "Gelir akışları"},
        "lean": {"ad": "Lean Canvas", "problem": "Problem", "cozum": "Çözüm", "metrikler": "Temel metrikler",
                 "deger_onerisi": "Benzersiz değer önerisi", "haksiz_avantaj": "Haksız avantaj", "kanallar": "Kanallar",
                 "segmentler": "Müşteri segmentleri", "maliyetler": "Maliyet yapısı", "gelirler": "Gelir akışları"},
        "pestle": {"ad": "PESTLE analizi", "politik": "Politik", "ekonomik": "Ekonomik", "sosyal": "Sosyal",
                   "teknolojik": "Teknolojik", "hukuki": "Hukuki", "cevresel": "Çevresel"},
        "porter": {"ad": "Porter'ın 5 gücü", "yeni_girenler": "Yeni girenlerin tehdidi",
                   "tedarikci_gucu": "Tedarikçilerin pazarlık gücü", "rekabet": "Sektör içi rekabet",
                   "alici_gucu": "Alıcıların pazarlık gücü", "ikameler": "İkame ürün tehdidi"},
        "mckinsey_7s": {"ad": "McKinsey 7S", "strateji": "Strateji", "yapi": "Yapı", "sistemler": "Sistemler",
                        "ortak_degerler": "Ortak değerler", "stil": "Yönetim tarzı", "personel": "Personel",
                        "yetenekler": "Yetenekler"},
        "mavi_okyanus": {"ad": "Mavi Okyanus — Dört Eylem", "ortadan_kaldir": "Ortadan kaldır", "yukselt": "Yükselt",
                         "azalt": "Azalt", "yarat": "Yarat"},
        "ikigai": {"ad": "Ikigai", "sevdigin": "Sevdiğin", "tutku": "Tutku", "iyi_oldugun": "İyi olduğun",
                   "misyon": "Misyon", "ikigai": "Ikigai", "meslek": "Meslek", "dunyanin_ihtiyaci": "Dünyanın ihtiyacı",
                   "ugras": "Uğraş", "para_kazandiran": "Para kazandıran"},
    },
    "en": {
        "swot": {"ad": "SWOT analysis", "guclu": "Strengths", "zayif": "Weaknesses", "firsatlar": "Opportunities",
                 "tehditler": "Threats"},
        "is_modeli": {"ad": "Business Model Canvas", "ortaklar": "Key partners", "faaliyetler": "Key activities",
                      "kaynaklar": "Key resources", "deger": "Value propositions", "iliskiler": "Customer relationships",
                      "kanallar": "Channels", "segmentler": "Customer segments", "maliyetler": "Cost structure",
                      "gelirler": "Revenue streams"},
        "lean": {"ad": "Lean Canvas", "problem": "Problem", "cozum": "Solution", "metrikler": "Key metrics",
                 "deger_onerisi": "Unique value proposition", "haksiz_avantaj": "Unfair advantage", "kanallar": "Channels",
                 "segmentler": "Customer segments", "maliyetler": "Cost structure", "gelirler": "Revenue streams"},
        "pestle": {"ad": "PESTLE analysis", "politik": "Political", "ekonomik": "Economic", "sosyal": "Social",
                   "teknolojik": "Technological", "hukuki": "Legal", "cevresel": "Environmental"},
        "porter": {"ad": "Porter's Five Forces", "yeni_girenler": "Threat of new entrants",
                   "tedarikci_gucu": "Bargaining power of suppliers", "rekabet": "Industry rivalry",
                   "alici_gucu": "Bargaining power of buyers", "ikameler": "Threat of substitutes"},
        "mckinsey_7s": {"ad": "McKinsey 7S", "strateji": "Strategy", "yapi": "Structure", "sistemler": "Systems",
                        "ortak_degerler": "Shared values", "stil": "Style", "personel": "Staff", "yetenekler": "Skills"},
        "mavi_okyanus": {"ad": "Blue Ocean — Four Actions", "ortadan_kaldir": "Eliminate", "yukselt": "Raise",
                         "azalt": "Reduce", "yarat": "Create"},
        "ikigai": {"ad": "Ikigai", "sevdigin": "What you love", "tutku": "Passion", "iyi_oldugun": "What you are good at",
                   "misyon": "Mission", "ikigai": "Ikigai", "meslek": "Profession", "dunyanin_ihtiyaci": "What the world needs",
                   "ugras": "Vocation", "para_kazandiran": "What you can be paid for"},
    },
    "de": {
        "swot": {"ad": "SWOT-Analyse", "guclu": "Stärken", "zayif": "Schwächen", "firsatlar": "Chancen",
                 "tehditler": "Risiken"},
        "is_modeli": {"ad": "Business Model Canvas", "ortaklar": "Schlüsselpartner", "faaliyetler": "Schlüsselaktivitäten",
                      "kaynaklar": "Schlüsselressourcen", "deger": "Wertangebote", "iliskiler": "Kundenbeziehungen",
                      "kanallar": "Kanäle", "segmentler": "Kundensegmente", "maliyetler": "Kostenstruktur",
                      "gelirler": "Einnahmequellen"},
        "lean": {"ad": "Lean Canvas", "problem": "Problem", "cozum": "Lösung", "metrikler": "Schlüsselkennzahlen",
                 "deger_onerisi": "Alleinstellungsmerkmal", "haksiz_avantaj": "Unfairer Vorteil", "kanallar": "Kanäle",
                 "segmentler": "Kundensegmente", "maliyetler": "Kostenstruktur", "gelirler": "Einnahmequellen"},
        "pestle": {"ad": "PESTLE-Analyse", "politik": "Politisch", "ekonomik": "Wirtschaftlich", "sosyal": "Sozial",
                   "teknolojik": "Technologisch", "hukuki": "Rechtlich", "cevresel": "Ökologisch"},
        "porter": {"ad": "Porters Five Forces", "yeni_girenler": "Bedrohung durch neue Anbieter",
                   "tedarikci_gucu": "Verhandlungsmacht der Lieferanten", "rekabet": "Wettbewerb in der Branche",
                   "alici_gucu": "Verhandlungsmacht der Abnehmer", "ikameler": "Bedrohung durch Ersatzprodukte"},
        "mckinsey_7s": {"ad": "McKinsey 7S", "strateji": "Strategie", "yapi": "Struktur", "sistemler": "Systeme",
                        "ortak_degerler": "Gemeinsame Werte", "stil": "Führungsstil", "personel": "Personal",
                        "yetenekler": "Fähigkeiten"},
        "mavi_okyanus": {"ad": "Blue Ocean — Vier Aktionen", "ortadan_kaldir": "Eliminieren", "yukselt": "Steigern",
                         "azalt": "Reduzieren", "yarat": "Kreieren"},
        "ikigai": {"ad": "Ikigai", "sevdigin": "Was du liebst", "tutku": "Leidenschaft", "iyi_oldugun": "Was du gut kannst",
                   "misyon": "Mission", "ikigai": "Ikigai", "meslek": "Beruf", "dunyanin_ihtiyaci": "Was die Welt braucht",
                   "ugras": "Berufung", "para_kazandiran": "Wofür du bezahlt wirst"},
    },
}


def pdf_dili(dil: Optional[str]) -> str:
    d = (dil or "tr")[:2].lower()
    return d if d in SABLON_ADLARI else "en"


def sablon_adi(tur: str, dil: str = "tr") -> str:
    return SABLON_ADLARI[pdf_dili(dil)].get(tur, {}).get("ad", tur)


def kutu_adi(tur: str, kutu: str, dil: str = "tr") -> str:
    return SABLON_ADLARI[pdf_dili(dil)].get(tur, {}).get(kutu, kutu)


def strateji_mi(tur: Optional[str]) -> bool:
    return tur in STRATEJI_SABLONLARI


# ---------------------------------------------------------------------------
# Küçük yardımcılar
# ---------------------------------------------------------------------------
def simdi() -> datetime:
    return datetime.now(timezone.utc)


def utc(an: Optional[datetime]) -> Optional[datetime]:
    if an is None:
        return None
    return an.replace(tzinfo=timezone.utc) if an.tzinfo is None else an.astimezone(timezone.utc)


def iso(an: Optional[datetime]) -> Optional[str]:
    u = utc(an)
    return u.isoformat() if u else None


def eposta_duzelt(e: Any) -> str:
    return str(e or "").strip().lower()


_DENETIM = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def arama_normalle(s: Any) -> str:
    """Büyük/küçük harf ve aksan farkını siler: "Şirket İçi" → "sirket ici" (Türkçe ı → i)."""
    metin = unicodedata.normalize("NFKD", str(s or "").casefold())
    metin = "".join(c for c in metin if not unicodedata.combining(c)).replace("ı", "i")
    return re.sub(r"\s+", " ", metin).strip()


def _metin(deger: Any, alan: str, sinir: int, *, zorunlu: bool = False, tek_satir: bool = False) -> str:
    if deger is None:
        deger = ""
    if not isinstance(deger, str):
        raise BelgeHatasi("gecersiz", alan=alan)
    s = _DENETIM.sub("", deger.replace("\r\n", "\n").replace("\r", "\n"))
    if tek_satir:
        s = re.sub(r"\s+", " ", s)
    s = s.strip() if tek_satir else s
    if zorunlu and not s.strip():
        raise BelgeHatasi("metin_gerekli", alan=alan)
    if len(s) > sinir:
        raise BelgeHatasi("metin_uzun", alan=alan, sinir=sinir)
    return s


def etiketleri_duzelt(ham: Any) -> List[str]:
    if ham in (None, ""):
        return []
    if isinstance(ham, str):
        ham = [x for x in ham.split(",")]
    if not isinstance(ham, list):
        raise BelgeHatasi("gecersiz", alan="etiketler")
    sonuc: List[str] = []
    gorulen = set()
    for x in ham:
        if not isinstance(x, str):
            raise BelgeHatasi("gecersiz", alan="etiketler")
        e = re.sub(r"\s+", " ", _DENETIM.sub("", x)).strip().lstrip("#").strip()
        if not e:
            continue
        if len(e) > SINIR["etiket"]:
            raise BelgeHatasi("metin_uzun", alan="etiketler", sinir=SINIR["etiket"])
        anahtar = arama_normalle(e)
        if anahtar in gorulen:
            continue
        gorulen.add(anahtar)
        sonuc.append(e)
    if len(sonuc) > SINIR["etiket_sayisi"]:
        raise BelgeHatasi("cok_fazla", alan="etiketler", sinir=SINIR["etiket_sayisi"])
    return sonuc


def json_yukle(ham: Any, varsayilan: Any) -> Any:
    if not ham:
        return varsayilan
    try:
        d = json.loads(ham)
    except (TypeError, ValueError):
        return varsayilan
    return d if isinstance(d, type(varsayilan)) else varsayilan


# ---------------------------------------------------------------------------
# Strateji gövdesi
# ---------------------------------------------------------------------------
def strateji_dogrula(tur: str, ham: Any) -> Dict[str, Any]:
    """`{"isletme": str, "kutular": {kutu: str}}` — bilinmeyen kutu ya da metin dışı değer 400."""
    sablon = STRATEJI_SABLONLARI[tur]
    if ham in (None, ""):
        ham = {}
    if isinstance(ham, str):
        try:
            ham = json.loads(ham)
        except ValueError:
            raise BelgeHatasi("gecersiz", alan="icerik")
    if not isinstance(ham, dict):
        raise BelgeHatasi("gecersiz", alan="icerik")
    bilinmeyen = set(ham) - {"isletme", "kutular"}
    if bilinmeyen:
        raise BelgeHatasi("gecersiz", alan="icerik")
    kutular_ham = ham.get("kutular") or {}
    if not isinstance(kutular_ham, dict):
        raise BelgeHatasi("gecersiz", alan="kutular")
    yabanci = sorted(set(kutular_ham) - set(sablon.anahtarlar))
    if yabanci:
        raise BelgeHatasi("bilinmeyen_kutu", alan="kutular", kutu=yabanci[0])
    kutular: Dict[str, str] = {}
    for k in sablon.anahtarlar:
        deger = _metin(kutular_ham.get(k), k, SINIR["kutu"])
        if deger.strip():
            kutular[k] = deger
    return {"isletme": _metin(ham.get("isletme"), "isletme", SINIR["isletme"]), "kutular": kutular}


def strateji_coz(b: Belgeler) -> Dict[str, Any]:
    d = json_yukle(b.icerik, {})
    kutular = d.get("kutular") if isinstance(d.get("kutular"), dict) else {}
    return {
        "isletme": d.get("isletme") if isinstance(d.get("isletme"), str) else "",
        "kutular": {k: v for k, v in kutular.items() if isinstance(v, str)},
    }


def bos_strateji() -> str:
    return json.dumps({"isletme": "", "kutular": {}}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Yapılacaklar (belge gövdesindeki onay kutuları)
# ---------------------------------------------------------------------------
_YAPILACAK_SATIRI = re.compile(r"^(\s*[-*+]\s+\[)( |x|X)(\]\s+)(.*)$")
_ATANAN = re.compile(r"@([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})")
_GOREV_BAGI = re.compile(r"\s*→\s*#(\d+)\s*$")


def yapilacaklar_cikar(md: Optional[str]) -> List[Dict[str, Any]]:
    """[{satir, metin, tamam, atananlar, gorev_id}] — kod bloğundakiler sayılmaz."""
    sonuc: List[Dict[str, Any]] = []
    kodda = False
    for i, satir in enumerate((md or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")):
        if satir.strip().startswith("```"):
            kodda = not kodda
            continue
        if kodda:
            continue
        m = _YAPILACAK_SATIRI.match(satir)
        if not m or satir.lstrip().startswith(">"):
            continue
        metin = m.group(4).strip()
        gorev = _GOREV_BAGI.search(metin)
        sonuc.append({
            "satir": i,
            "metin": metin,
            "tamam": m.group(2) in ("x", "X"),
            "atananlar": sorted({eposta_duzelt(a) for a in _ATANAN.findall(metin)}),
            "gorev_id": int(gorev.group(1)) if gorev else None,
        })
    return sonuc


def _yapilacak_satiri(md: str, satir: int, metin: Optional[str]) -> Tuple[List[str], re.Match]:
    satirlar = (md or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if isinstance(satir, bool) or not isinstance(satir, int) or not 0 <= satir < len(satirlar):
        raise BelgeHatasi("madde_degisti", 409)
    m = _YAPILACAK_SATIRI.match(satirlar[satir])
    # Belge bu arada değiştiyse (satır kaydı ya da madde başka) yanlış maddeyi işaretlemeyelim.
    if not m or (metin is not None and m.group(4).strip() != str(metin).strip()):
        raise BelgeHatasi("madde_degisti", 409)
    return satirlar, m


def yapilacak_isaretle(md: str, satir: int, metin: Optional[str], tamam: bool) -> str:
    satirlar, m = _yapilacak_satiri(md, satir, metin)
    satirlar[satir] = f"{m.group(1)}{'x' if tamam else ' '}{m.group(3)}{m.group(4)}"
    return "\n".join(satirlar)


def gorev_bagla(md: str, satir: int, metin: Optional[str], gorev_id: int) -> str:
    satirlar, m = _yapilacak_satiri(md, satir, metin)
    if _GOREV_BAGI.search(m.group(4)):
        raise BelgeHatasi("gorev_bagli", 409)
    satirlar[satir] = f"{m.group(1)}{m.group(2)}{m.group(3)}{m.group(4).rstrip()} → #{int(gorev_id)}"
    return "\n".join(satirlar)


# ---------------------------------------------------------------------------
# Sözlükler
# ---------------------------------------------------------------------------
def acik_yapilacak_sayisi(b: Belgeler) -> int:
    if b.tur != "belge" or "[ ]" not in (b.icerik or ""):
        return 0
    return sum(1 for y in yapilacaklar_cikar(b.icerik) if not y["tamam"])


def ozet_metni(b: Belgeler) -> str:
    from services.guvenli_html import belge_duz_metin

    if b.tur == "belge":
        return belge_duz_metin(b.icerik or "", 180)
    d = strateji_coz(b)
    parca = d["isletme"] or " · ".join(v.replace("\n", " ") for v in d["kutular"].values())
    parca = re.sub(r"\s+", " ", parca).strip()
    return parca if len(parca) <= 180 else parca[:179].rstrip() + "…"


def musteri_belgesi_mi(b: Belgeler) -> bool:
    return bool(eposta_duzelt(b.sahip_hesap))


def belge_sozlugu(b: Belgeler, *, ayrintili: bool = False, proje_adi: Optional[str] = None) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "id": b.id,
        "tur": b.tur,
        "strateji": strateji_mi(b.tur),
        "baslik": b.baslik,
        "etiketler": json_yukle(b.etiketler, []),
        "alan": b.alan,
        "musteri_email": b.musteri_email or None,
        "proje_id": b.proje_id,
        "proje_adi": proje_adi,
        "gorunurluk": b.gorunurluk,
        "musteri_belgesi": musteri_belgesi_mi(b),
        "sahip_hesap": b.sahip_hesap or None,
        "sabit": bool(b.sabit),
        "surum": int(b.surum or 1),
        "olusturan": b.olusturan,
        "son_duzenleyen": b.son_duzenleyen,
        "son_duzenleyen_rol": b.son_duzenleyen_rol,
        "paylasildi_at": iso(b.paylasildi_at),
        "okundu_at": iso(b.okundu_at),
        "okuyan": b.okuyan,
        "okundu_surum": b.okundu_surum,
        "created_at": iso(b.created_at),
        "updated_at": iso(b.updated_at) or iso(b.created_at),
        "ozet": ozet_metni(b),
        "acik_yapilacak": acik_yapilacak_sayisi(b),
    }
    if ayrintili:
        if b.tur == "belge":
            from services.guvenli_html import belge_html

            d["icerik"] = b.icerik or ""
            d["html"] = belge_html(b.icerik or "")
            d["yapilacaklar"] = yapilacaklar_cikar(b.icerik)
        else:
            d["strateji_icerik"] = strateji_coz(b)
    return d


def surum_sozlugu(s: BelgeSurumleri, *, icerikli: bool = False) -> Dict[str, Any]:
    d = {"id": s.id, "belge_id": s.belge_id, "surum": s.surum, "baslik": s.baslik, "duzenleyen": s.duzenleyen,
         "rol": s.rol, "aciklama": s.aciklama, "created_at": iso(s.created_at), "boyut": len(s.icerik or "")}
    if icerikli:
        d["icerik"] = s.icerik or ""
    return d


# ---------------------------------------------------------------------------
# Kayıt işlemleri
# ---------------------------------------------------------------------------
def arama_metnini_kur(b: Belgeler) -> None:
    if b.tur == "belge":
        govde = b.icerik or ""
    else:
        d = strateji_coz(b)
        govde = d["isletme"] + "\n" + "\n".join(d["kutular"].values())
    etiketler = " ".join(json_yukle(b.etiketler, []))
    b.arama_metni = arama_normalle(f"{b.baslik}\n{etiketler}\n{govde}")


#: Aynı kişinin art arda yaptığı yapılacak işaretleri bu süre içinde TEK sürümde birleşir
#: (20 kutu işaretlemek 20 sürüm yazıp gerçek geçmişi silmesin).
BIRLESTIRME_SN = 600


async def surum_yaz(db: AsyncSession, b: Belgeler, kisi: str, rol: str, aciklama: str, *, birlestir: bool = False) -> None:
    """Belgenin ŞU ANKİ hâlini sürüm olarak yazar; son SURUM_SINIRI dışındakiler silinir."""
    if birlestir:
        son = (await db.execute(
            select(BelgeSurumleri).where(BelgeSurumleri.belge_id == b.id)
            .order_by(BelgeSurumleri.surum.desc(), BelgeSurumleri.id.desc()).limit(1)
        )).scalars().first()
        if (son is not None and son.aciklama == aciklama and eposta_duzelt(son.duzenleyen) == eposta_duzelt(kisi)
                and son.created_at is not None and (simdi() - utc(son.created_at)).total_seconds() < BIRLESTIRME_SN):
            son.surum, son.baslik, son.icerik, son.created_at = int(b.surum or 1), b.baslik, b.icerik, simdi()
            await db.flush()
            return
    db.add(BelgeSurumleri(belge_id=b.id, surum=int(b.surum or 1), baslik=b.baslik, icerik=b.icerik,
                          duzenleyen=kisi or None, rol=rol, aciklama=aciklama[:120], created_at=simdi()))
    await db.flush()
    eski = (await db.execute(
        select(BelgeSurumleri.id).where(BelgeSurumleri.belge_id == b.id)
        .order_by(BelgeSurumleri.surum.desc(), BelgeSurumleri.id.desc()).offset(SURUM_SINIRI)
    )).scalars().all()
    if eski:
        # Toplu silme bilerek Core: eski sürümler çöp kutusuna düşmesin (belge silinince
        # kalan sürümler ORM ile siliniyor ve belgeyle birlikte geri geliyor).
        await db.execute(delete(BelgeSurumleri).where(BelgeSurumleri.id.in_(list(eski))))


async def surumleri_sil(db: AsyncSession, belge_id: int) -> None:
    for s in (await db.execute(select(BelgeSurumleri).where(BelgeSurumleri.belge_id == belge_id))).scalars().all():
        await db.delete(s)


def icerik_degistir(b: Belgeler, *, baslik: Optional[str] = None, icerik: Optional[str] = None,
                    kisi: str, rol: str) -> bool:
    """Başlık/gövde değiştiyse alanları yazar, sürümü artırır. Değişti mi?"""
    degisti = False
    if baslik is not None and baslik != b.baslik:
        b.baslik = baslik
        degisti = True
    if icerik is not None and icerik != (b.icerik or ""):
        b.icerik = icerik
        degisti = True
    if degisti:
        b.surum = int(b.surum or 1) + 1
        b.son_duzenleyen = kisi or None
        b.son_duzenleyen_rol = rol
        b.updated_at = simdi()
        arama_metnini_kur(b)
    return degisti


def arama_kosulu(q: Optional[str]):
    aranan = arama_normalle((q or "")[: SINIR["arama"]])
    if not aranan:
        return None
    desen = "%" + aranan.replace("\\", "").replace("%", "").replace("_", "") + "%"
    return func.coalesce(Belgeler.arama_metni, "").like(desen)


def tur_kosulu(tur: Optional[str]):
    if not tur:
        return None
    if tur == "strateji":
        return Belgeler.tur.in_(STRATEJI_TURLERI)
    if tur not in TURLER:
        raise BelgeHatasi("gecersiz", alan="tur")
    return Belgeler.tur == tur


def etiket_suz(satirlar: Iterable[Belgeler], etiket: Optional[str]) -> List[Belgeler]:
    hedef = arama_normalle(etiket)
    if not hedef:
        return list(satirlar)
    return [b for b in satirlar if hedef in {arama_normalle(e) for e in json_yukle(b.etiketler, [])}]


def siralama():
    return (Belgeler.sabit.desc(), func.coalesce(Belgeler.updated_at, Belgeler.created_at).desc(), Belgeler.id.desc())


async def proje_adlari(db: AsyncSession, idler: Iterable[Optional[int]]) -> Dict[int, str]:
    liste = sorted({int(i) for i in idler if i})
    if not liste:
        return {}
    from models.projects import Projects

    return {int(i): t for i, t in (await db.execute(select(Projects.id, Projects.title).where(Projects.id.in_(liste)))).all()}


def etiket_ozeti(satirlar: Sequence[Belgeler]) -> List[Dict[str, Any]]:
    sayac: Dict[str, Dict[str, Any]] = {}
    for b in satirlar:
        for e in json_yukle(b.etiketler, []):
            k = arama_normalle(e)
            if k not in sayac:
                sayac[k] = {"ad": e, "sayi": 0}
            sayac[k]["sayi"] += 1
    return sorted(sayac.values(), key=lambda x: (-x["sayi"], arama_normalle(x["ad"])))[:50]


def tum_yapilacaklar(satirlar: Sequence[Belgeler], *, kisi: Optional[str], yalniz_bana: bool,
                     tamamlananlar: bool = False) -> List[Dict[str, Any]]:
    ben = eposta_duzelt(kisi)
    sonuc: List[Dict[str, Any]] = []
    for b in satirlar:
        if b.tur != "belge":
            continue
        for y in yapilacaklar_cikar(b.icerik):
            if y["tamam"] and not tamamlananlar:
                continue
            if yalniz_bana and ben not in y["atananlar"]:
                continue
            sonuc.append({**y, "belge_id": b.id, "belge_baslik": b.baslik, "proje_id": b.proje_id,
                          "musteri_email": b.musteri_email or None, "bana": ben in y["atananlar"],
                          "updated_at": iso(b.updated_at) or iso(b.created_at)})
            if len(sonuc) >= YAPILACAK_SINIRI:
                return sonuc
    return sonuc


# ---------------------------------------------------------------------------
# Dışa aktarma — Markdown
# ---------------------------------------------------------------------------
def markdown_disa_aktar(b: Belgeler, dil: str = "tr") -> str:
    if b.tur == "belge":
        govde = b.icerik or ""
        return govde if govde.lstrip().startswith("# ") else f"# {b.baslik}\n\n{govde}".rstrip() + "\n"
    d = strateji_coz(b)
    parcalar = [f"# {b.baslik}", "", f"_{sablon_adi(b.tur, dil)}_", ""]
    if d["isletme"].strip():
        parcalar += [d["isletme"].strip(), ""]
    for k in STRATEJI_SABLONLARI[b.tur].anahtarlar:
        parcalar.append(f"## {kutu_adi(b.tur, k, dil)}")
        parcalar.append("")
        metin = (d["kutular"].get(k) or "").strip()
        if metin:
            for satir in metin.split("\n"):
                s = satir.strip()
                if s:
                    parcalar.append(s if re.match(r"^([-*+]|\d+[.)])\s", s) else f"- {s}")
        else:
            parcalar.append("—")
        parcalar.append("")
    return "\n".join(parcalar).rstrip() + "\n"


def dosya_adi(b: Belgeler, uzanti: str) -> str:
    temel = arama_normalle(b.baslik)
    temel = re.sub(r"[^a-z0-9]+", "-", temel).strip("-")[:60] or "belge"
    return f"{temel}-{b.id}.{uzanti}"


# ---------------------------------------------------------------------------
# Bildirim
# ---------------------------------------------------------------------------
async def bildir(db: AsyncSession, **kw: Any) -> None:
    try:
        from services.notify import dispatch

        await dispatch(db, **kw)
    except Exception:  # noqa: BLE001 - bildirim asıl işi bozmasın
        logger.exception("Belge bildirimi gönderilemedi")


async def musteriye_paylasildi_bildir(db: AsyncSession, b: Belgeler) -> None:
    if not b.musteri_email:
        return
    await bildir(
        db,
        event_type="belge_paylasildi",
        title=f"Sizinle bir belge paylaşıldı: {b.baslik}",
        body=f"{b.baslik} — panelinizdeki Dosyalar › Belgeler bölümünden okuyabilirsiniz.",
        recipients=[{"email": b.musteri_email, "role": "client"}],
        link=f"/client?sekme=dosyalar&alt={'strateji' if strateji_mi(b.tur) else 'belgeler'}&belge={b.id}",
        ref_type="belge",
        ref_id=b.id,
    )


async def ajansa_paylasildi_bildir(db: AsyncSession, b: Belgeler, kisi: str) -> None:
    from services.notify import admin_recipients

    await bildir(
        db,
        event_type="belge_paylasildi",
        title=f"Müşteri bir belge paylaştı: {b.baslik}",
        body=f"{kisi} ({b.sahip_hesap}) belgesini ajansla paylaştı: {b.baslik}",
        recipients=await admin_recipients(db),
        link=f"/admin?sekme=dosyalar&alt={'strateji' if strateji_mi(b.tur) else 'belgeler'}&belge={b.id}",
        ref_type="belge",
        ref_id=b.id,
    )


async def okundu_bildir(db: AsyncSession, b: Belgeler, kisi: str) -> None:
    from services.notify import admin_recipients

    await bildir(
        db,
        event_type="belge_onaylandi",
        title=f"Müşteri belgeyi okudu ve onayladı: {b.baslik}",
        body=f"{kisi} ({b.musteri_email}) paylaşılan belgeyi okudu/onayladı (sürüm {b.okundu_surum}).",
        recipients=await admin_recipients(db),
        link=f"/admin?sekme=dosyalar&alt={'strateji' if strateji_mi(b.tur) else 'belgeler'}&belge={b.id}",
        ref_type="belge",
        ref_id=b.id,
    )


def sorgu_ajans_gorur():
    """Ajansın görebildiği belgeler: kendi belgeleri + müşterinin AJANSLA PAYLAŞTIĞI belgeleri."""
    return or_(
        func.coalesce(Belgeler.sahip_hesap, "") == "",
        Belgeler.gorunurluk == "paylasilan",
    )
