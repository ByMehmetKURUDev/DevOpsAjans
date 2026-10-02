"""Faz 5A — bilgi bankası: normalleştirme, kök kırpma, parçalama ve BM25 arama.

Gömme (embedding) servisi zorunlu değil: arama taşınabilir, sözcükseldir ve
hem SQLite (test) hem Postgres'te (canlı) aynı çalışır — veritabanına özel
tam metin araması (tsvector, FTS5) kullanılmıyor. Parçaların terimleri
yazılırken bir kez çıkarılıp `ai_asistan_parcalari.terimler` sütununa
konuyor; sorguda asistanın bütün parçaları bellekteki bir dizine yükleniyor
(`dizin_surumu` değişene kadar süreç içinde önbellekte). Bir asistanın en çok
birkaç bin parçası olur; dizin kurmak milisaniyeler, sorgu mikrosaniyeler.

Normalleştirme
--------------
* Türkçe küçük harf: `İ → i`, `I → ı` (Python'un `"İ".lower()` sonucu `i̇`, yani
  i + birleşik nokta — eşleşmeyi bozardı).
* Aksan katlama: `ı ş ç ğ ö ü â î û → i s c g o u a i u` ve Latin harflerdeki
  birleşik işaretler. Ziyaretçi "ucret" de yazsa "ücret" de aynı terim.
* Arapça: hareke ve tatvil silinir, elif biçimleri birleşir (`أ إ آ → ا`),
  `ة → ه`, `ى → ي`.
* Kesme işaretinden sonrası atılır: "İstanbul'da" → "istanbul".
* Çince/Japonca: boşluk yok → karakter ikilileri (bigram).

Kök kırpma: dile göre hafif sonek kırpma (Türkçe çekim ekleri, İngilizce
-s/-ing/-ed, Almanca, Rusça, Arapça önek/sonek). Dil, metnin kendisinden
tahmin ediliyor; sorguda belirti yoksa dizindeki baskın dil kullanılıyor.

Kapsama (devir eşiği): sorunun içerik terimlerinin (durak kelimeler hariç)
IDF ağırlıklı ne kadarı en iyi parçada geçiyor — 0 ile 1 arası. Asistanın
`devir_esigi` bunun altında kalan soruda "bilmiyorum" deyip insana devretmeyi
öneriyor (modele hiç gidilmeden).
"""

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Normalleştirme
# ---------------------------------------------------------------------------
_TR_BUYUK = str.maketrans({"İ": "i", "I": "ı"})
_KATLAMA = str.maketrans({
    "ı": "i", "ş": "s", "ç": "c", "ğ": "g", "ö": "o", "ü": "u", "â": "a", "î": "i", "û": "u",
    "ß": "ss", "æ": "ae", "œ": "oe", "ø": "o", "đ": "d", "ł": "l",
    # Arapça
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي", "ـ": "",
    # Kesme işaretinin türleri tek biçime
    "’": "'", "‘": "'", "`": "'", "´": "'",
})
_ARAPCA_HAREKE = re.compile(r"[ً-ٰٟۖ-ۭ]")
_KESME = re.compile(r"(?<=\w)'\w+")
_KELIME = re.compile(r"[^\W_]+", re.UNICODE)


def turkce_kucuk(metin: str) -> str:
    """Türkçe kurallarıyla küçük harf: İ → i, I → ı (aksanlar korunur)."""
    return str(metin or "").translate(_TR_BUYUK).lower()


def _latin_mi(harf: str) -> bool:
    return ord(harf) < 0x0250


def normallestir(metin: str) -> str:
    """Arama için: Türkçe küçük harf + aksan katlama + Arapça sadeleştirme."""
    m = turkce_kucuk(metin).translate(_KATLAMA)
    m = _ARAPCA_HAREKE.sub("", m)
    # Latin harflerin birleşik işaretleri (é → e, ä → a); Devanagari gibi
    # yazılarda işaretler harfin parçası, dokunulmuyor.
    ayrik = unicodedata.normalize("NFKD", m)
    cikti: List[str] = []
    onceki = ""
    for h in ayrik:
        if unicodedata.category(h) == "Mn" and onceki and _latin_mi(onceki):
            continue
        cikti.append(h)
        onceki = h
    return unicodedata.normalize("NFC", "".join(cikti))


def _cjk_mi(h: str) -> bool:
    k = ord(h)
    return 0x4E00 <= k <= 0x9FFF or 0x3400 <= k <= 0x4DBF or 0x3040 <= k <= 0x30FF or 0xAC00 <= k <= 0xD7AF or 0xF900 <= k <= 0xFAFF


def kelimeler(metin: str) -> List[str]:
    """Normalleştirilmiş kelimeler (kesme sonrası atılmış; CJK karakter ikilileri)."""
    m = normallestir(_KESME.sub("", str(metin or "").replace("’", "'")))
    sonuc: List[str] = []
    for k in _KELIME.findall(m):
        if not any(_cjk_mi(h) for h in k):
            sonuc.append(k)
            continue
        # Karışık parça: CJK dizileri ikililere, geri kalanı kelime.
        parca = ""
        cjk = ""
        for h in k + " ":
            if h != " " and _cjk_mi(h):
                if parca:
                    sonuc.append(parca)
                    parca = ""
                cjk += h
                continue
            if cjk:
                sonuc.extend([cjk] if len(cjk) == 1 else [cjk[i:i + 2] for i in range(len(cjk) - 1)])
                cjk = ""
            if h != " ":
                parca += h
        if parca:
            sonuc.append(parca)
    return sonuc


# ---------------------------------------------------------------------------
# Durak kelimeler (katlanmış biçimde)
# ---------------------------------------------------------------------------
DURAK: Dict[str, frozenset] = {
    "tr": frozenset("""
        acaba ama ancak artik aslinda az bana bazen bazi belki ben beni benim bile bir biraz birkac birsey
        biz bize bizi bizim bu buna bunda bundan bunu bunun burada cok cunku da daha de defa diye dir
        en gibi hem hep hepsi her hic ile ise icin kadar kez ki kim kime kimi mi mu mi miyim misiniz
        musunuz mudur midir nasil ne neden nedir nerede nereye nicin niye o olan olarak oldu olur ona onda
        ondan onlar onu onun orada oyle sadece sanki sen sende senden seni senin siz size sizi sizin soyle
        su sunu var ve veya ya yani yok zaten mi lutfen merhaba selam acaba hangi hangisi kac
        olmak oluyor olabilir istiyorum ogrenmek alabilir miyim
    """.split()),
    "en": frozenset("""
        a about above after again all am an and any are as at be because been before being below between
        both but by can could did do does doing down during each few for from further had has have having
        he her here hers him his how i if in into is it its itself just me more most my no nor not now of
        off on once only or other our out over own please same she should so some such than that the their
        them then there these they this those through to too under until up very was we were what when
        where which while who whom why will with would you your yours hello hi hey thanks thank tell
    """.split()),
    "de": frozenset("""
        aber alle als also am an auch auf aus bei bin bis bitte da damit dann das dass dem den der des die
        doch du ein eine einem einen einer es fur gibt hab habe haben hallo hat ich ihr im in ist ja kann
        kein man mich mir mit nach nicht noch nur oder sein sie sind so uber um und uns von vor was wie wir
        wird wo zu zum zur
    """.split()),
    "ru": frozenset("""
        а без бы в вам вас вы где да для до его ее если есть еще же за и из или им их к как ли мне мы на
        не нет но о об он она они от по пожалуйста при с так то только у уже что это я здравствуйте привет
        какой какая какие сколько можно
    """.split()),
    "ar": frozenset("""
        في من على الى عن مع هذا هذه ذلك التي الذي هل ما ماذا كيف كم او و ثم لا نعم هو هي انا انت نحن هم
        كان يكون لكم لك لي مرحبا شكرا من فضلك
    """.split()),
    "hi": frozenset("""
        का की के है हैं में से को पर और या यह वह क्या कैसे कितना कितनी कब कहाँ मैं हम आप तुम नमस्ते
        भी तो ही था थी थे हो
    """.split()),
}
TUM_DURAK = frozenset().union(*DURAK.values())

# ---------------------------------------------------------------------------
# Dil tahmini
# ---------------------------------------------------------------------------
_TR_HARF = set("ğışİı")
_TR_YARI = set("çöüÇÖÜşŞĞ")
_DE_HARF = set("äßÄ")


def dil_tahmin(metin: str) -> Optional[str]:
    """Metnin baskın dili: tr | en | de | ru | ar | hi | zh — belirti yoksa None."""
    m = str(metin or "")
    if not m.strip():
        return None
    yazi = Counter()
    for h in m:
        k = ord(h)
        if 0x0400 <= k <= 0x04FF:
            yazi["ru"] += 1
        elif 0x0600 <= k <= 0x06FF:
            yazi["ar"] += 1
        elif 0x0900 <= k <= 0x097F:
            yazi["hi"] += 1
        elif _cjk_mi(h):
            yazi["zh"] += 1
        elif h.isalpha():
            yazi["latin"] += 1
    if not yazi:
        return None
    baskin, sayi = yazi.most_common(1)[0]
    if baskin != "latin":
        return baskin
    puan = Counter()
    for h in m:
        if h in _TR_HARF:
            puan["tr"] += 3
        elif h in _TR_YARI:
            puan["tr"] += 1
            if h in "öüÖÜ":
                puan["de"] += 1
        elif h in _DE_HARF:
            puan["de"] += 3
    for k in (normallestir(x) for x in re.findall(r"[^\W\d_]+", m)):
        for dil in ("tr", "en", "de"):
            if k in DURAK[dil]:
                puan[dil] += 2
    if not puan:
        return None
    (ilk, p1), *geri = puan.most_common(2)
    if geri and geri[0][1] == p1:
        return None
    return ilk


# ---------------------------------------------------------------------------
# Kök kırpma (hafif, dile göre)
# ---------------------------------------------------------------------------
_TR_EKLER = sorted(
    {
        "lerimiz", "larimiz", "leriniz", "lariniz", "lerinin", "larinin", "lerinde", "larinda", "lerinden",
        "larindan", "lerini", "larini", "lerine", "larina", "leri", "lari", "ler", "lar",
        "iyoruz", "uyoruz", "yoruz", "iyor", "uyor", "yor",
        "imiz", "umuz", "iniz", "unuz", "miz", "muz", "niz", "nuz",
        "inin", "unun", "nin", "nun", "inde", "unda", "inda", "unde", "nde", "nda",
        "den", "dan", "ten", "tan", "de", "da", "te", "ta",
        "ine", "una", "ina", "une", "ye", "ya", "yi", "yu", "yle", "yla", "le", "la",
        "dir", "dur", "tir", "tur", "lik", "luk", "si", "su", "in", "un", "im", "um", "ma", "me",
        "mak", "mek", "i", "u", "e", "a",
    },
    key=len,
    reverse=True,
)
_EN_EKLER = ("ingly", "edly", "ing", "ed", "ly")
_DE_EKLER = ("ern", "en", "er", "es", "e", "s", "n")
_RU_EKLER = sorted(
    "ами ями ого его ому ему ыми ими ах ях ой ей ый ий ая яя ое ее ом ем ам ям ов ев ые ие ую юю ы и а я о е у ю ь".split(),
    key=len,
    reverse=True,
)
_AR_ONEKLER = ("وال", "بال", "كال", "فال", "لل", "ال")
_AR_SONEKLER = ("ات", "ون", "ين", "ها", "يه", "ه", "ي")


def _tr_kok(k: str) -> str:
    for _ in range(4):
        degisti = False
        for ek in _TR_EKLER:
            if k.endswith(ek) and len(k) - len(ek) >= (4 if len(ek) == 1 else 3):
                k = k[: -len(ek)]
                degisti = True
                break
        if not degisti:
            break
    return k


def _en_kok(k: str) -> str:
    if len(k) <= 3:
        return k
    if k.endswith("ies") and len(k) > 4:
        k = k[:-3] + "y"
    elif k.endswith("sses"):
        k = k[:-2]
    elif k.endswith("s") and not k.endswith(("ss", "us", "is")):
        k = k[:-1]
    for ek in _EN_EKLER:
        if k.endswith(ek) and len(k) - len(ek) >= 3:
            k = k[: -len(ek)]
            if len(k) > 3 and k[-1] == k[-2] and k[-1] not in "lsz":
                k = k[:-1]
            break
    if k.endswith("e") and len(k) > 4:
        k = k[:-1]
    return k


def _de_kok(k: str) -> str:
    for ek in _DE_EKLER:
        if k.endswith(ek) and len(k) - len(ek) >= 4:
            return k[: -len(ek)]
    return k


def _ru_kok(k: str) -> str:
    for ek in _RU_EKLER:
        if k.endswith(ek) and len(k) - len(ek) >= 3:
            return k[: -len(ek)]
    return k


def _ar_kok(k: str) -> str:
    for on in _AR_ONEKLER:
        if k.startswith(on) and len(k) - len(on) >= 3:
            k = k[len(on):]
            break
    for son in _AR_SONEKLER:
        if k.endswith(son) and len(k) - len(son) >= 3:
            k = k[: -len(son)]
            break
    return k


_KOKLER = {"tr": _tr_kok, "en": _en_kok, "de": _de_kok, "ru": _ru_kok, "ar": _ar_kok}


def kok(kelime: str, dil: Optional[str]) -> str:
    if kelime.isdigit():
        return kelime
    f = _KOKLER.get(dil or "")
    return f(kelime) if f else kelime


def terimler(metin: str, dil: Optional[str] = None, durak_at: bool = True) -> List[str]:
    """Metin → arama terimleri (normalleştirilmiş, durak kelimesiz, kökü kırpılmış).

    `dil` verilmezse metinden tahmin ediliyor.
    """
    dil = dil or dil_tahmin(metin)
    sonuc = []
    for k in kelimeler(metin):
        if durak_at and k in TUM_DURAK:
            continue
        if len(k) == 1 and not k.isdigit() and not _cjk_mi(k):
            continue
        sonuc.append(kok(k, dil))
    return sonuc


# ---------------------------------------------------------------------------
# Parçalama (başlık duyarlı, örtüşmeli)
# ---------------------------------------------------------------------------
HEDEF_UZUNLUK = 800
ORTUSME = 150
_BASLIK_SATIRI = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
_CUMLE = re.compile(r"(?<=[.!?…。！？؟])\s+")


@dataclass
class Parca:
    baslik: Optional[str]
    metin: str
    adres: Optional[str] = None


def bolumler(metin: str) -> List[Tuple[List[str], str]]:
    """Markdown benzeri başlıklara göre bölümler: (başlık yolu, gövde)."""
    yol: List[Tuple[int, str]] = []
    sonuc: List[Tuple[List[str], str]] = []
    govde: List[str] = []

    def bitir() -> None:
        icerik = "\n".join(govde).strip()
        if icerik:
            sonuc.append(([b for _, b in yol], icerik))
        govde.clear()

    for satir in str(metin or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        m = _BASLIK_SATIRI.match(satir)
        if m:
            bitir()
            seviye = len(m.group(1))
            while yol and yol[-1][0] >= seviye:
                yol.pop()
            yol.append((seviye, " ".join(m.group(2).split())[:160]))
            continue
        govde.append(satir)
    bitir()
    if not sonuc and yol:
        # Yalnız başlıklardan oluşan metin: başlıklar kendisi içerik.
        sonuc.append(([], " — ".join(b for _, b in yol)))
    return sonuc


def _cumleler(paragraf: str, hedef: int) -> List[str]:
    parcalar = [c.strip() for c in _CUMLE.split(paragraf) if c.strip()]
    sonuc: List[str] = []
    for c in parcalar:
        while len(c) > hedef:
            kes = c.rfind(" ", 0, hedef)
            kes = kes if kes > hedef // 2 else hedef
            sonuc.append(c[:kes].strip())
            c = c[kes:].strip()
        if c:
            sonuc.append(c)
    return sonuc


def _kuyruk(metin: str, ortusme: int) -> str:
    """Önceki parçanın son cümle(ler)i — örtüşme için en çok `ortusme` karakter."""
    if ortusme <= 0 or not metin:
        return ""
    cumleler = [c for c in _CUMLE.split(metin) if c.strip()]
    kuyruk = ""
    for c in reversed(cumleler):
        aday = (c.strip() + " " + kuyruk).strip()
        if len(aday) > ortusme:
            break
        kuyruk = aday
    if not kuyruk:
        son = metin[-ortusme:]
        bosluk = son.find(" ")
        kuyruk = son[bosluk + 1:] if 0 <= bosluk < len(son) - 1 else son
    return kuyruk.strip()


def parcala(
    metin: str,
    kok_baslik: Optional[str] = None,
    hedef: int = HEDEF_UZUNLUK,
    ortusme: int = ORTUSME,
    adres: Optional[str] = None,
) -> List[Parca]:
    """Metni başlıklara göre bölüp her bölümü ~`hedef` karakterlik örtüşmeli parçalara ayırır.

    Parçanın başlığı başlık yolu ("Kök › H1 › H2"); paragraflar bölünmez (hedefi aşan
    paragraf cümlelerine, cümle de kelime sınırından bölünür). Aynı bölümde yeni parça
    bir öncekinin son cümlesiyle başlar (örtüşme).
    """
    sonuc: List[Parca] = []
    for yol, govde in bolumler(metin):
        baslik_parcalari = ([kok_baslik] if kok_baslik else []) + yol
        baslik = " › ".join(b for b in baslik_parcalari if b) or None
        paragraflar = [" ".join(p.split()) for p in re.split(r"\n\s*\n", govde) if p.strip()]
        birimler: List[str] = []
        for p in paragraflar:
            birimler.extend([p] if len(p) <= hedef else _cumleler(p, hedef))
        simdiki = ""
        for b in birimler:
            if simdiki and len(simdiki) + 2 + len(b) > hedef:
                sonuc.append(Parca(baslik, simdiki, adres))
                kuyruk = _kuyruk(simdiki, ortusme)
                simdiki = (kuyruk + "\n\n" + b) if kuyruk and len(kuyruk) + 2 + len(b) <= hedef + ortusme else b
            else:
                simdiki = (simdiki + "\n\n" + b) if simdiki else b
        if simdiki:
            sonuc.append(Parca(baslik, simdiki, adres))
    return sonuc


# ---------------------------------------------------------------------------
# BM25 dizini
# ---------------------------------------------------------------------------
K1 = 1.2
B = 0.75


@dataclass
class DizinBelgesi:
    id: int
    kaynak_id: int
    baslik: Optional[str]
    metin: str
    adres: Optional[str]
    dil: Optional[str]
    terimler: List[str]
    vektor: Optional[List[float]] = None


@dataclass
class Sonuc:
    belge: DizinBelgesi
    skor: float
    kapsama: float
    benzerlik: Optional[float] = None


@dataclass
class Dizin:
    belgeler: List[DizinBelgesi]
    surum: int = 0
    tf: List[Counter] = field(default_factory=list)
    df: Counter = field(default_factory=Counter)
    ortalama: float = 0.0
    baskin_dil: Optional[str] = None

    @classmethod
    def kur(cls, belgeler: Sequence[DizinBelgesi], surum: int = 0) -> "Dizin":
        d = cls(belgeler=list(belgeler), surum=surum)
        d.tf = [Counter(b.terimler) for b in d.belgeler]
        for tf in d.tf:
            d.df.update(tf.keys())
        toplam = sum(len(b.terimler) for b in d.belgeler)
        d.ortalama = (toplam / len(d.belgeler)) if d.belgeler else 0.0
        diller = Counter(b.dil for b in d.belgeler if b.dil)
        d.baskin_dil = diller.most_common(1)[0][0] if diller else None
        return d

    @property
    def n(self) -> int:
        return len(self.belgeler)

    def idf(self, terim: str) -> float:
        df = self.df.get(terim, 0)
        return math.log(1.0 + (self.n - df + 0.5) / (df + 0.5))

    def sorgu_terimleri(self, soru: str) -> List[str]:
        dil = dil_tahmin(soru) or self.baskin_dil
        return list(dict.fromkeys(terimler(soru, dil)))

    def _skor(self, i: int, sorgu: Iterable[str]) -> float:
        tf = self.tf[i]
        dl = len(self.belgeler[i].terimler) or 1
        payda_kat = K1 * (1 - B + B * dl / (self.ortalama or 1.0))
        skor = 0.0
        for t in sorgu:
            f = tf.get(t, 0)
            if f:
                skor += self.idf(t) * f * (K1 + 1) / (f + payda_kat)
        return skor

    def kapsama(self, i: int, sorgu: Sequence[str]) -> float:
        if not sorgu:
            return 0.0
        agirliklar = {t: self.idf(t) for t in sorgu}
        toplam = sum(agirliklar.values()) or 1.0
        tf = self.tf[i]
        return sum(w for t, w in agirliklar.items() if tf.get(t)) / toplam

    def ara(
        self,
        soru: str,
        k: int = 5,
        sorgu_vektoru: Optional[List[float]] = None,
    ) -> Tuple[List[str], List[Sonuc]]:
        """(sorgu terimleri, en iyi `k` sonuç). Vektör verilirse BM25 + kosinüs sırası RRF ile birleşir."""
        sorgu = self.sorgu_terimleri(soru)
        if not self.belgeler:
            return sorgu, []
        skorlar = [(i, self._skor(i, sorgu)) for i in range(self.n)] if sorgu else []
        bm25 = sorted((x for x in skorlar if x[1] > 0), key=lambda x: (-x[1], x[0]))
        benzerlikler: Dict[int, float] = {}
        if sorgu_vektoru:
            for i, b in enumerate(self.belgeler):
                if b.vektor:
                    benzerlikler[i] = kosinus(sorgu_vektoru, b.vektor)
        if benzerlikler:
            vsira = sorted(benzerlikler.items(), key=lambda x: (-x[1], x[0]))[: max(k * 4, 20)]
            rrf: Dict[int, float] = {}
            for sira, (i, _) in enumerate(bm25[: max(k * 4, 20)]):
                rrf[i] = rrf.get(i, 0.0) + 1.0 / (60 + sira)
            for sira, (i, _) in enumerate(vsira):
                rrf[i] = rrf.get(i, 0.0) + 1.0 / (60 + sira)
            sirali = [i for i, _ in sorted(rrf.items(), key=lambda x: (-x[1], x[0]))]
        else:
            sirali = [i for i, _ in bm25]
        skor_sozlugu = dict(skorlar)
        sonuc = [
            Sonuc(self.belgeler[i], skor_sozlugu.get(i, 0.0), self.kapsama(i, sorgu), benzerlikler.get(i))
            for i in sirali[:k]
        ]
        return sorgu, sonuc


def kosinus(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    ust = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return ust / (na * nb) if na and nb else 0.0


def parca_terimleri(baslik: Optional[str], metin: str) -> Tuple[List[str], Optional[str]]:
    """Parçanın terimleri (başlık terimleri ağırlık için iki kez) ve tahmini dili."""
    dil = dil_tahmin(f"{baslik or ''}\n{metin}")
    govde = terimler(metin, dil)
    bas = terimler(baslik or "", dil) if baslik else []
    return bas + bas + govde, dil
