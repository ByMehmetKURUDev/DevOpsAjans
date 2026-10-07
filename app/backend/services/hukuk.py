"""Faz 6H — hukuk bürosu: kurallar ve yardımcılar (veritabanına dokunmayan her şey).

Router `routers/hukuk.py`, veritabanı işleri `services/hukuk_kayit.py`. Burada:

* Doğrulayıcılar (randevu yardımcıları yeniden kullanılıyor; hata sınıfı onun alt sınıfı).
* Çıkar çatışması için ad/vergi no normalleştirme (Türkçe harf + büyük/küçük; şirket ekleri) ve eşleşme.
* SÜRE HESABI (yardımcıdır; kesin süreyi avukat doğrular):
  - HMK m.92: gün olarak belirlenen süre başladığı günün sonundan itibaren işler (tebliğ günü sayılmaz);
    hafta/ay olarak belirlenen süre son hafta/ayda başladığı güne karşılık gelen günde biter, o gün
    son ayda yoksa ayın son gününde biter.
  - HMK m.93: son gün resmî tatile (ya da hafta sonuna) rastlarsa izleyen ilk iş gününde biter.
  - HMK m.104 (isteğe bağlı): adli tatile (varsayılan 20 Temmuz – 31 Ağustos, HMK m.102) rastlayan süre,
    adli tatilin bittiği günden itibaren bir hafta uzatılmış sayılır.
  Adli tatil aralığı ve uzatma gün sayısı ayarlardan değiştirilebilir. Yarım gün tatil (arife) süreyi
  uzatmaz; yalnız uyarı verir.
* İmzalı müvekkil portalı jetonu (HMAC, `JWT_SECRET_KEY`'den amaca bağlı türetilmiş anahtar):
  `<müvekkil id>-<sürüm>-<imza>`; sürüm artınca (yenile) eski bağlantı ölür, iptal edilince hiçbiri çalışmaz.
* ICS (sorumlu avukat başına) ve masraf/zaman dökümü PDF'i (sitenin Türkçe destekli yazı tipi).

AI ÖZELLİĞİ YOK (hukuki görüş riski). UYAP entegrasyonu YOK (açık API yok; kazıma yapılmaz).
"""

import hashlib
import hmac
import io
import json
import os
import re
import secrets
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from services import randevu as r

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------
MODUL = "hukuk_burosu"
IZIN = "hukuk"
UTC = timezone.utc
SAAT_DILIMI = "Europe/Istanbul"

MUVEKKIL_TURLERI: Tuple[str, ...] = ("kisi", "sirket")
DOSYA_TURLERI: Tuple[str, ...] = ("dava", "icra", "arabuluculuk", "danismanlik", "sozlesme", "diger")
DOSYA_DURUMLARI: Tuple[str, ...] = ("acik", "beklemede", "kapandi")
OLAY_TURLERI: Tuple[str, ...] = ("durusma", "kesif", "bilirkisi", "kesin_sure", "gorev")
MASRAF_TURLERI: Tuple[str, ...] = ("harc", "tebligat", "bilirkisi", "yol", "diger")
SURE_BIRIMLERI: Tuple[str, ...] = ("gun", "hafta", "ay")
TATIL_TURLERI: Tuple[str, ...] = ("sabit", "dini", "diger")
PARA_BIRIMLERI: Tuple[str, ...] = ("TRY", "USD", "EUR", "GBP")
#: Portalda müvekkile gösterilebilecek alanlar ve varsayılanları (dosya başına işaretlenir).
PORTAL_ALANLARI: Dict[str, bool] = {"konu": True, "durum": True, "durusma": True, "belgeler": True, "masraf": False,
                                    "not": False}
VARSAYILAN_HATIRLATMA: Tuple[int, ...] = (7, 3, 1, 0)
HATIRLATMA_EN_COK_GUN = 30
VARSAYILAN_DOSYA_SINIRI = 200
SILINENLER_GUN = 30
EN_COK_KARSI_TARAF = 10
EN_COK_ETIKET = 10
DOSYA_EN_COK_MB = 20
#: Yaklaşan süre sayısı (yönetici meta görünümü + panel özeti) bu kadar gün ileriye bakar.
YAKLASAN_GUN = 14

#: 2429 sayılı Ulusal Bayram ve Genel Tatiller Hakkında Kanun — sabit ulusal günler (her yıl aynı ay-gün).
#: Dini bayramlar (Ramazan, Kurban) ay takvimine göre her yıl değişir: kullanıcı ekler (arayüz söylüyor).
SABIT_TATILLER: Tuple[Tuple[str, str, bool, str], ...] = (
    # (ay-gün, Türkçe ad, yarım gün mü, İngilizce ad)
    ("01-01", "Yılbaşı", False, "New Year's Day"),
    ("04-23", "Ulusal Egemenlik ve Çocuk Bayramı", False, "National Sovereignty and Children's Day"),
    ("05-01", "Emek ve Dayanışma Günü", False, "Labour and Solidarity Day"),
    ("05-19", "Atatürk'ü Anma, Gençlik ve Spor Bayramı", False, "Commemoration of Atatürk, Youth and Sports Day"),
    ("07-15", "Demokrasi ve Millî Birlik Günü", False, "Democracy and National Unity Day"),
    ("08-30", "Zafer Bayramı", False, "Victory Day"),
    ("10-28", "Cumhuriyet Bayramı arifesi (öğleden sonra)", True, "Republic Day eve (afternoon)"),
    ("10-29", "Cumhuriyet Bayramı", False, "Republic Day"),
)


class HukukHatasi(r.RandevuHatasi):
    """Doğrulama/iş kuralı hatası (`{"kod", "alan"?, ...}`)."""


TemelHata = r.RandevuHatasi


def simdi() -> datetime:
    """Testler bu fonksiyonu sabit bir ana çeviriyor."""
    return datetime.now(UTC)


def utc(an: Optional[datetime]) -> Optional[datetime]:
    if an is None:
        return None
    return an.replace(tzinfo=UTC) if an.tzinfo is None else an.astimezone(UTC)


def iso(an: Optional[datetime]) -> Optional[str]:
    a = utc(an)
    return a.isoformat().replace("+00:00", "Z") if a else None


def gun_iso(g: Optional[date]) -> Optional[str]:
    return g.isoformat() if g else None


def yerel_bugun(an: Optional[datetime] = None) -> date:
    return utc(an or simdi()).astimezone(r.saat_dilimi(SAAT_DILIMI)).date()


def yerel_saat(an: Optional[datetime] = None) -> str:
    return utc(an or simdi()).astimezone(r.saat_dilimi(SAAT_DILIMI)).strftime("%H:%M")


def json_yukle(ham: Any, varsayilan: Any = None) -> Any:
    return r.json_yukle(ham, varsayilan)


def json_yaz(deger: Any) -> str:
    return json.dumps(deger, ensure_ascii=False, separators=(",", ":"))


def site_adresi() -> str:
    return r.site_adresi()


def portal_adresi(jeton: str) -> str:
    return f"{site_adresi()}/hukuk/muvekkil/{jeton}"


# ---------------------------------------------------------------------------
# Doğrulayıcılar
# ---------------------------------------------------------------------------
metin = r.metin
eposta_duzelt = r.eposta_duzelt
telefon_duzelt = r.telefon_duzelt
tam_sayi = r.tam_sayi
bool_duzelt = r.bool_duzelt


def secim(ham: Any, secenekler: Sequence[str], alan: str) -> str:
    if ham not in secenekler:
        raise HukukHatasi("secim_gecersiz", alan)
    return str(ham)


def tarih_duzelt(ham: Any, alan: str, bos_olabilir: bool = True) -> Optional[date]:
    if ham in (None, ""):
        if bos_olabilir:
            return None
        raise HukukHatasi("zorunlu", alan)
    if isinstance(ham, date) and not isinstance(ham, datetime):
        return ham
    try:
        return date.fromisoformat(str(ham).strip()[:10])
    except ValueError:
        raise HukukHatasi("tarih_gecersiz", alan)


_SAAT = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def saat_duzelt(ham: Any, alan: str = "saat") -> Optional[str]:
    deger = str(ham or "").strip()
    if not deger:
        return None
    if not _SAAT.match(deger):
        raise HukukHatasi("saat_gecersiz", alan)
    return deger


_AY_GUN = re.compile(r"^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")


def ay_gun_duzelt(ham: Any, alan: str) -> str:
    deger = str(ham or "").strip()
    if not _AY_GUN.match(deger):
        raise HukukHatasi("tarih_gecersiz", alan)
    try:
        date(2024, int(deger[:2]), int(deger[3:]))  # artık yıl: 02-29 geçerli
    except ValueError:
        raise HukukHatasi("tarih_gecersiz", alan)
    return deger


def vergi_no_duzelt(ham: Any, alan: str = "vergi_no") -> Optional[str]:
    """VKN (10), TCKN (11) ya da yabancı kimlik/vergi no: boşluk, tire, nokta atılır; 5–20 harf/rakam."""
    deger = re.sub(r"[\s\-./]", "", str(ham or "")).upper()
    if not deger:
        return None
    if not re.fullmatch(r"[A-Z0-9]{5,20}", deger):
        raise HukukHatasi("vergi_no_gecersiz", alan)
    return deger


def etiketler_duzelt(ham: Any) -> List[str]:
    if ham in (None, ""):
        return []
    if not isinstance(ham, list):
        raise HukukHatasi("liste_gecersiz", "etiketler")
    sonuc: List[str] = []
    for x in ham:
        e = metin(x, "etiketler", 40)
        if e and e not in sonuc:
            sonuc.append(e)
    if len(sonuc) > EN_COK_ETIKET:
        raise HukukHatasi("cok_fazla", "etiketler", en_cok=EN_COK_ETIKET)
    return sonuc


def karsi_taraflar_duzelt(ham: Any) -> List[Dict[str, str]]:
    if ham in (None, ""):
        return []
    if not isinstance(ham, list):
        raise HukukHatasi("liste_gecersiz", "karsi_taraflar")
    if len(ham) > EN_COK_KARSI_TARAF:
        raise HukukHatasi("cok_fazla", "karsi_taraflar", en_cok=EN_COK_KARSI_TARAF)
    sonuc = []
    for i, x in enumerate(ham):
        if not isinstance(x, dict):
            raise HukukHatasi("liste_gecersiz", f"karsi_taraflar.{i}")
        ad = metin(x.get("ad"), f"karsi_taraflar.{i}.ad", 200)
        if not ad:
            continue
        sonuc.append({"ad": ad, "vergi_no": vergi_no_duzelt(x.get("vergi_no"), f"karsi_taraflar.{i}.vergi_no") or "",
                      "vekil": metin(x.get("vekil"), f"karsi_taraflar.{i}.vekil", 200)})
    return sonuc


def portal_alanlari(ham: Any) -> Dict[str, bool]:
    d = json_yukle(ham, None) if isinstance(ham, str) or ham is None else ham
    sonuc = dict(PORTAL_ALANLARI)
    if isinstance(d, dict):
        for k in PORTAL_ALANLARI:
            if isinstance(d.get(k), bool):
                sonuc[k] = d[k]
    return sonuc


def portal_alanlari_duzelt(ham: Any) -> Dict[str, bool]:
    if not isinstance(ham, dict):
        raise HukukHatasi("gecersiz", "portal_alanlari")
    for k, v in ham.items():
        if k not in PORTAL_ALANLARI or not isinstance(v, bool):
            raise HukukHatasi("gecersiz", f"portal_alanlari.{k}")
    return portal_alanlari(ham)


def hatirlatma_gunleri(ham: Any) -> List[int]:
    d = json_yukle(ham, None) if isinstance(ham, str) or ham is None else ham
    if not isinstance(d, list) or not d:
        return list(VARSAYILAN_HATIRLATMA)
    return sorted({int(x) for x in d if isinstance(x, int) and not isinstance(x, bool) and 0 <= x <= HATIRLATMA_EN_COK_GUN},
                  reverse=True) or list(VARSAYILAN_HATIRLATMA)


def hatirlatma_gunleri_duzelt(ham: Any) -> List[int]:
    if not isinstance(ham, list) or not 1 <= len(ham) <= 6:
        raise HukukHatasi("gecersiz", "hatirlatma_gunleri")
    for x in ham:
        if isinstance(x, bool) or not isinstance(x, int) or not 0 <= x <= HATIRLATMA_EN_COK_GUN:
            raise HukukHatasi("aralik_disi", "hatirlatma_gunleri", en_az=0, en_cok=HATIRLATMA_EN_COK_GUN)
    return sorted(set(ham), reverse=True)


def tutar_kurus(ham: Any, alan: str = "tutar") -> int:
    """"1250,50" / 1250.5 / "1.250,50" → 125050 kuruş. Negatif ve sıfır kabul edilmez."""
    if isinstance(ham, bool) or ham in (None, ""):
        raise HukukHatasi("zorunlu", alan)
    if isinstance(ham, (int, float)):
        deger = round(float(ham) * 100)
    else:
        s_ = str(ham).strip().replace(" ", "").replace("₺", "")
        if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d{1,2})?", s_):
            s_ = s_.replace(".", "").replace(",", ".")
        else:
            s_ = s_.replace(",", ".")
        try:
            deger = round(float(s_) * 100)
        except ValueError:
            raise HukukHatasi("sayi_gecersiz", alan)
    if deger <= 0 or deger > 100_000_000_00:
        raise HukukHatasi("aralik_disi", alan, en_az=0, en_cok=100_000_000)
    return int(deger)


# ---------------------------------------------------------------------------
# Çıkar çatışması — normalleştirme ve eşleşme
# ---------------------------------------------------------------------------
_TR_HARF = str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u", "â": "a", "î": "i", "û": "u"})
#: Sonda atılan şirket türü ekleri (normalize edilmiş belirteçler).
_SIRKET_EKLERI = frozenset({"as", "ltd", "sti", "limited", "sirketi", "anonim", "inc", "llc", "gmbh", "ltdsti", "kollektif",
                            "komandit", "koop", "kooperatifi"})


def turkce_kucuk(metin_: str) -> str:
    """Türkçe kurallı küçük harf: I → ı, İ → i (Python'un `lower()`ı İ'yi i̇ yapıyor)."""
    return (metin_ or "").replace("I", "ı").replace("İ", "i").lower()


def ad_normalle(ad: Any) -> str:
    """"ŞAHİN İnşaat A.Ş." → "sahin insaat"; "Işık" ve "IŞIK" → "isik". Yalnız harf/rakam ve tek boşluk."""
    m = turkce_kucuk(str(ad or "")).translate(_TR_HARF)
    m = unicodedata.normalize("NFKD", m)
    m = "".join(c for c in m if not unicodedata.combining(c))
    m = re.sub(r"[^a-z0-9]+", " ", m).strip()
    parca = m.split()
    while parca:
        if parca[-1] in _SIRKET_EKLERI:
            parca.pop()
        elif len(parca) >= 2 and parca[-2:] == ["a", "s"]:
            parca = parca[:-2]
        else:
            break
    return " ".join(parca)[:220]


def benzerlik(a: str, b: str) -> Optional[str]:
    """İki normalize ad: "tam" | "kismi" | None. Kısmi: kısa adın (en az 2 belirteç, 5+ harf) bütün
    belirteçleri uzun adda geçiyor ("yilmaz insaat" ↔ "yilmaz insaat taahhut")."""
    if not a or not b:
        return None
    if a == b:
        return "tam"
    kisa, uzun = (a, b) if len(a) <= len(b) else (b, a)
    kb, ub = kisa.split(), set(uzun.split())
    if len(kisa) >= 5 and len(kb) >= 2 and set(kb) <= ub:
        return "kismi"
    return None


@dataclass
class Aday:
    """Çatışma araması için mevcut kayıt: müvekkil ya da bir dosyanın karşı tarafı."""

    rol: str  # muvekkil | karsi_taraf
    ad: str
    ad_normal: str
    vergi_no: Optional[str]
    muvekkil_id: Optional[int]
    dosya_id: Optional[int] = None


def eslesmeler(ad: Any, vergi_no: Optional[str], adaylar: Iterable[Aday]) -> List[Tuple[Aday, str]]:
    """(aday, eşleşme türü) — vergi_no | tam | kismi. Vergi no eşleşmesi önce."""
    n = ad_normalle(ad)
    v = vergi_no_duzelt(vergi_no) if vergi_no else None
    sonuc: List[Tuple[Aday, str]] = []
    for a in adaylar:
        if v and a.vergi_no and v == a.vergi_no:
            sonuc.append((a, "vergi_no"))
            continue
        tur = benzerlik(n, a.ad_normal)
        if tur:
            sonuc.append((a, tur))
    sira = {"vergi_no": 0, "tam": 1, "kismi": 2}
    return sorted(sonuc, key=lambda x: sira[x[1]])


# ---------------------------------------------------------------------------
# Süre hesabı (HMK m.92, m.93, m.104)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Tatil:
    ad: str
    tarih: date
    bitis: Optional[date] = None
    tekrar: bool = False
    yarim: bool = False

    def kapsar(self, gun: date) -> bool:
        if self.tekrar:
            bas = _yila_tasi(self.tarih, gun.year)
            bit = _yila_tasi(self.bitis, gun.year) if self.bitis else bas
            if bit < bas:  # yıl sonunu aşan aralık
                return gun >= bas or gun <= bit
            return bas <= gun <= bit
        return self.tarih <= gun <= (self.bitis or self.tarih)


def _yila_tasi(g: date, yil: int) -> date:
    try:
        return g.replace(year=yil)
    except ValueError:  # 29 Şubat → 28 Şubat
        return g.replace(year=yil, day=28)


def ay_ekle(g: date, ay: int) -> date:
    """HMK m.92/2: karşılık gelen gün son ayda yoksa ayın son günü (31 Ocak + 1 ay → 28/29 Şubat)."""
    toplam = g.year * 12 + (g.month - 1) + ay
    yil, ay_ = divmod(toplam, 12)
    ay_ += 1
    if ay_ == 12:
        son = 31
    else:
        son = (date(yil, ay_ + 1, 1) - timedelta(days=1)).day
    return date(yil, ay_, min(g.day, son))


def ham_son_gun(baslangic: date, miktar: int, birim: str) -> date:
    """HMK m.92: gün → başladığı günün sonundan itibaren (tebliğ günü sayılmaz); hafta/ay → karşılık gelen gün."""
    if birim == "gun":
        return baslangic + timedelta(days=miktar)
    if birim == "hafta":
        return baslangic + timedelta(weeks=miktar)
    if birim == "ay":
        return ay_ekle(baslangic, miktar)
    raise HukukHatasi("secim_gecersiz", "birim")


def tatil_bul(gun: date, tatiller: Sequence[Tatil], yarim_dahil: bool = False) -> Optional[Tatil]:
    for t in tatiller:
        if (yarim_dahil or not t.yarim) and t.kapsar(gun):
            return t
    return None


def is_gunu_mu(gun: date, tatiller: Sequence[Tatil]) -> bool:
    return gun.weekday() < 5 and tatil_bul(gun, tatiller) is None


def ilk_is_gunu(gun: date, tatiller: Sequence[Tatil]) -> Tuple[date, List[Dict[str, Any]]]:
    """HMK m.93: tatil/hafta sonu ise izleyen ilk iş günü; atlanan günler ve nedenleri."""
    atlanan: List[Dict[str, Any]] = []
    while not is_gunu_mu(gun, tatiller):
        t = tatil_bul(gun, tatiller)
        atlanan.append({"tarih": gun.isoformat(), "neden": "tatil" if t else "hafta_sonu", "ad": t.ad if t else None})
        gun += timedelta(days=1)
        if len(atlanan) > 60:  # bozuk tatil listesine karşı sigorta
            raise HukukHatasi("tatil_listesi_gecersiz", "tatiller")
    return gun, atlanan


def adli_tatil_araligi(yil: int, bas: str = "07-20", bit: str = "08-31") -> Tuple[date, date]:
    return date(yil, int(bas[:2]), int(bas[3:])), date(yil, int(bit[:2]), int(bit[3:]))


def adli_tatilde_mi(gun: date, bas: str = "07-20", bit: str = "08-31") -> bool:
    b, s_ = adli_tatil_araligi(gun.year, bas, bit)
    return b <= gun <= s_


def son_gun_hesapla(baslangic: date, miktar: int, birim: str, *, adli_tatil: bool, tatiller: Sequence[Tatil] = (),
                    adli_bas: str = "07-20", adli_bit: str = "08-31", uzatma_gun: int = 7) -> Dict[str, Any]:
    """Sürenin son günü + uygulanan kurallar (adımlar) + uyarılar.

    Sıra: m.92 (ham son gün) → m.93 (tatil/hafta sonu kaydırması) → [m.104 adli tatil uzatması → m.93].
    Kaydırma sonucu adli tatile düşen süre de uzatılır (ör. 18 Temmuz Cumartesi → 20 Temmuz Pazartesi →
    adli tatil → 7 Eylül).
    """
    if birim not in SURE_BIRIMLERI:
        raise HukukHatasi("secim_gecersiz", "birim")
    if isinstance(miktar, bool) or not isinstance(miktar, int) or not 1 <= miktar <= 3650:
        raise HukukHatasi("aralik_disi", "miktar", en_az=1, en_cok=3650)
    adimlar: List[Dict[str, Any]] = []
    uyarilar: List[str] = []
    ham = ham_son_gun(baslangic, miktar, birim)
    adimlar.append({"kural": "hmk92", "tarih": ham.isoformat(), "birim": birim, "miktar": miktar})
    gun, atlanan = ilk_is_gunu(ham, tatiller)
    if atlanan:
        adimlar.append({"kural": "hmk93", "tarih": gun.isoformat(), "atlanan": atlanan})
    if adli_tatilde_mi(gun, adli_bas, adli_bit):
        if adli_tatil:
            _, bitis = adli_tatil_araligi(gun.year, adli_bas, adli_bit)
            uzatilmis = bitis + timedelta(days=uzatma_gun)
            adimlar.append({"kural": "hmk104", "tarih": uzatilmis.isoformat(), "adli_tatil_bitis": bitis.isoformat(),
                            "uzatma_gun": uzatma_gun})
            gun, atlanan = ilk_is_gunu(uzatilmis, tatiller)
            if atlanan:
                adimlar.append({"kural": "hmk93", "tarih": gun.isoformat(), "atlanan": atlanan})
        else:
            uyarilar.append("adli_tatil_icinde")
    if tatil_bul(gun, tatiller, yarim_dahil=True) is not None:
        uyarilar.append("yarim_gun")
    return {"baslangic": baslangic.isoformat(), "miktar": miktar, "birim": birim, "adli_tatil": adli_tatil,
            "ham_son_gun": ham.isoformat(), "son_gun": gun.isoformat(), "adimlar": adimlar, "uyarilar": uyarilar}


def sabit_tatiller(dil: str = "tr") -> List[Dict[str, Any]]:
    return [{"ay_gun": ag, "ad": tr if dil == "tr" else en, "yarim": yarim} for ag, tr, yarim, en in SABIT_TATILLER]


# ---------------------------------------------------------------------------
# Müvekkil portalı jetonu
# ---------------------------------------------------------------------------
_YEDEK: Optional[bytes] = None


def _anahtar() -> bytes:
    global _YEDEK
    gizli = os.environ.get("JWT_SECRET_KEY") or ""
    if not gizli:
        if _YEDEK is None:
            _YEDEK = secrets.token_bytes(32)
        return _YEDEK
    return hashlib.sha256(("hukuk-portal:" + gizli).encode()).digest()


def _imza(mesaj: str) -> str:
    return hmac.new(_anahtar(), mesaj.encode(), hashlib.sha256).hexdigest()[:32]


_JETON = re.compile(r"^(\d{1,12})-(\d{1,6})-([0-9a-f]{32})$")


def muvekkil_jetonu(muvekkil_id: int, surum: int) -> str:
    return f"{int(muvekkil_id)}-{int(surum)}-{_imza(f'muvekkil|{int(muvekkil_id)}|{int(surum)}')}"


def jeton_parcala(jeton: Any) -> Optional[Tuple[int, int]]:
    m = _JETON.match(str(jeton or ""))
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def jeton_gecerli_mi(jeton: Any, muvekkil_id: int, surum: int) -> bool:
    return hmac.compare_digest(str(jeton or ""), muvekkil_jetonu(muvekkil_id, surum))


# ---------------------------------------------------------------------------
# Etiketler (sunucunun yazdığı metinler: ICS, PDF, bildirim) — tr/en
# ---------------------------------------------------------------------------
OLAY_ADI = {
    "tr": {"durusma": "Duruşma", "kesif": "Keşif", "bilirkisi": "Bilirkişi", "kesin_sure": "Kesin süre (son gün)",
           "gorev": "Görev"},
    "en": {"durusma": "Hearing", "kesif": "Site inspection", "bilirkisi": "Expert examination",
           "kesin_sure": "Deadline (last day)", "gorev": "Task"},
}
MASRAF_ADI = {
    "tr": {"harc": "Harç", "tebligat": "Tebligat", "bilirkisi": "Bilirkişi", "yol": "Yol", "diger": "Diğer"},
    "en": {"harc": "Court fee", "tebligat": "Service of process", "bilirkisi": "Expert", "yol": "Travel", "diger": "Other"},
}
DOSYA_TURU_ADI = {
    "tr": {"dava": "Dava", "icra": "İcra", "arabuluculuk": "Arabuluculuk", "danismanlik": "Danışmanlık",
           "sozlesme": "Sözleşme", "diger": "Diğer"},
    "en": {"dava": "Lawsuit", "icra": "Enforcement", "arabuluculuk": "Mediation", "danismanlik": "Advisory",
           "sozlesme": "Contract", "diger": "Other"},
}


def _dil(dil: Optional[str]) -> str:
    return "tr" if (dil or "tr")[:2] == "tr" else "en"


def olay_basligi(o: Any, dil: str = "tr") -> str:
    ad = OLAY_ADI[_dil(dil)].get(o.tur, o.tur)
    return f"{ad}: {o.baslik}" if getattr(o, "baslik", None) else ad


# ---------------------------------------------------------------------------
# ICS (RFC 5545)
# ---------------------------------------------------------------------------
def ics_uret(olaylar: Sequence[Any], dosyalar: Dict[int, Any], *, takvim_adi: str, dil: str = "tr",
             an: Optional[datetime] = None) -> str:
    """Saatli olay 60 dk'lık VEVENT (yerel saat → UTC), saatsiz olay (kesin süre, görev) tüm gün."""
    from services import dinamik_qr as qr

    an = an or simdi()
    tz = r.saat_dilimi(SAAT_DILIMI)
    alan = (site_adresi().split("://", 1)[-1].split("/", 1)[0] or "mehmetkuru.dev").split(":", 1)[0]
    satirlar = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//mehmetkuru.dev//Hukuk//TR", "CALSCALE:GREGORIAN",
                "METHOD:PUBLISH", f"X-WR-CALNAME:{qr._kacis(takvim_adi)}"]
    for o in olaylar:
        d = dosyalar.get(o.dosya_id) if o.dosya_id else None
        parcalar = [olay_basligi(o, dil)]
        if d is not None:
            parcalar.append(" ".join(x for x in (d.dosya_no or "", d.esas_no or "") if x) or (d.konu or ""))
        ozet = " — ".join(p for p in parcalar if p)
        aciklama = "\n".join(x for x in ((d.mahkeme if d is not None else None), o.notlar) if x)
        satirlar += ["BEGIN:VEVENT", f"UID:hukuk-{o.id}@{alan}", "DTSTAMP:" + utc(an).strftime("%Y%m%dT%H%M%SZ")]
        if o.saat:
            bas = datetime(o.tarih.year, o.tarih.month, o.tarih.day, int(o.saat[:2]), int(o.saat[3:]), tzinfo=tz)
            satirlar += ["DTSTART:" + utc(bas).strftime("%Y%m%dT%H%M%SZ"),
                         "DTEND:" + utc(bas + timedelta(hours=1)).strftime("%Y%m%dT%H%M%SZ")]
        else:
            satirlar += ["DTSTART;VALUE=DATE:" + o.tarih.strftime("%Y%m%d"),
                         "DTEND;VALUE=DATE:" + (o.tarih + timedelta(days=1)).strftime("%Y%m%d")]
        satirlar.append(f"SUMMARY:{qr._kacis(ozet)}")
        if aciklama:
            satirlar.append(f"DESCRIPTION:{qr._kacis(aciklama)}")
        if o.yer:
            satirlar.append(f"LOCATION:{qr._kacis(o.yer)}")
        satirlar += ["STATUS:CONFIRMED", "END:VEVENT"]
    satirlar.append("END:VCALENDAR")
    return "\r\n".join(qr._katla(s_) for s_ in satirlar) + "\r\n"


# ---------------------------------------------------------------------------
# Masraf / zaman dökümü PDF'i — Türkçe harfleri taşıyan sitenin yazı tipi (Plus Jakarta Sans, Latin)
# ---------------------------------------------------------------------------
PDF_ETIKET = {
    "tr": {"baslik": "Masraf ve zaman dökümü", "baslik_masraf": "Masraf dökümü", "muvekkil": "Müvekkil",
           "dosya": "Dosya", "mahkeme": "Mahkeme / daire", "tarih": "Tarih", "tur": "Tür", "aciklama": "Açıklama",
           "tutar": "Tutar", "avans": "Avanstan", "evet": "Evet", "masraflar": "Masraflar", "zaman": "Zaman kayıtları",
           "sure": "Süre", "faturalanabilir": "Faturalanabilir", "toplam": "Toplam", "avans_toplam": "Avanstan karşılanan",
           "diger_toplam": "Büroca karşılanan", "saat": "sa", "dk": "dk", "olusturma": "Oluşturma",
           "yok": "Kayıt yok.",
           "not": "Bu döküm bilgilendirme amaçlıdır; tahsilat ya da ödeme belgesi değildir."},
    "en": {"baslik": "Expense and time statement", "baslik_masraf": "Expense statement", "muvekkil": "Client",
           "dosya": "Matter", "mahkeme": "Court / office", "tarih": "Date", "tur": "Type", "aciklama": "Description",
           "tutar": "Amount", "avans": "From advance", "evet": "Yes", "masraflar": "Expenses", "zaman": "Time entries",
           "sure": "Duration", "faturalanabilir": "Billable", "toplam": "Total", "avans_toplam": "Covered by advance",
           "diger_toplam": "Covered by the firm", "saat": "h", "dk": "min", "olusturma": "Created",
           "yok": "No entries.",
           "not": "This statement is for information only; it is not a receipt or payment document."},
}


def sure_yaz(dk: int, dil: str = "tr") -> str:
    e = PDF_ETIKET[_dil(dil)]
    sa, kalan = divmod(int(dk or 0), 60)
    if sa and kalan:
        return f"{sa} {e['saat']} {kalan} {e['dk']}"
    if sa:
        return f"{sa} {e['saat']}"
    return f"{kalan} {e['dk']}"


def dokum_pdf(*, buro_adi: str, muvekkil_adi: str, dosya: Dict[str, Any], masraflar: Sequence[Dict[str, Any]],
              zamanlar: Optional[Sequence[Dict[str, Any]]], dil: str = "tr", an: Optional[datetime] = None) -> bytes:
    """A4 dikey döküm. `zamanlar=None` → yalnız masraf (müvekkil portalı). Tutarlar para birimine göre ayrı toplanır."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from services import pdf_belge as pb

    d = _dil(dil)
    e = PDF_ETIKET[d]
    st = pb._stiller()  # noqa: SLF001 — sitenin Türkçe destekli yazı tipi ve stilleri
    an = an or simdi()
    m = pb._metin  # noqa: SLF001
    parcalar: List[Any] = [
        Paragraph(f"<b>{m(buro_adi or '—')}</b>", st["h1"]),
        Paragraph(m(e["baslik"] if zamanlar is not None else e["baslik_masraf"]), st["bolum"]),
        Spacer(1, 2 * mm),
    ]
    bilgi = [(e["muvekkil"], muvekkil_adi), (e["dosya"], dosya.get("baslik")), (e["mahkeme"], dosya.get("mahkeme")),
             (e["olusturma"], pb.tarih(yerel_bugun(an).isoformat()))]
    for ad, deger in bilgi:
        if deger:
            parcalar.append(Paragraph(f"<font color='#5B5368'>{m(ad)}:</font> {m(deger)}", st["govde"]))
    parcalar.append(Spacer(1, 4 * mm))

    def tablo(veri: List[List[Any]], genislik: List[float]) -> Table:
        t = Table(veri, colWidths=genislik, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), pb.VURGU_ACIK), ("LINEBELOW", (0, 0), (-1, 0), 0.8, pb.VURGU),
            ("LINEBELOW", (0, 1), (-1, -1), 0.3, pb.CIZGI), ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        return t

    parcalar.append(Paragraph(m(e["masraflar"]), st["bolum"]))
    if masraflar:
        veri: List[List[Any]] = [[Paragraph(f"<b>{m(x)}</b>", st["govde"] if i < 3 else st["sag"])
                                  for i, x in enumerate((e["tarih"], e["tur"], e["aciklama"], e["avans"], e["tutar"]))]]
        toplam: Dict[str, int] = {}
        avans: Dict[str, int] = {}
        for x in masraflar:
            pbirim = x.get("para_birimi") or "TRY"
            toplam[pbirim] = toplam.get(pbirim, 0) + int(x["tutar_kurus"])
            if x.get("avanstan"):
                avans[pbirim] = avans.get(pbirim, 0) + int(x["tutar_kurus"])
            veri.append([
                Paragraph(pb.tarih(x.get("tarih")), st["govde"]),
                Paragraph(m(MASRAF_ADI[d].get(x.get("tur"), x.get("tur"))), st["govde"]),
                Paragraph(m(x.get("aciklama") or ""), st["govde"]),
                Paragraph(m(e["evet"] if x.get("avanstan") else "—"), st["sag"]),
                Paragraph(m(pb.para(int(x["tutar_kurus"]) / 100, pbirim, d)), st["sag"]),
            ])
        parcalar.append(tablo(veri, [24 * mm, 28 * mm, 70 * mm, 22 * mm, 36 * mm]))
        for pbirim in sorted(toplam):
            satir = f"<b>{m(e['toplam'])}:</b> {m(pb.para(toplam[pbirim] / 100, pbirim, d))}"
            if avans.get(pbirim):
                satir += (f" · {m(e['avans_toplam'])}: {m(pb.para(avans[pbirim] / 100, pbirim, d))}"
                          f" · {m(e['diger_toplam'])}: {m(pb.para((toplam[pbirim] - avans[pbirim]) / 100, pbirim, d))}")
            parcalar += [Spacer(1, 2 * mm), Paragraph(satir, st["sag"])]
    else:
        parcalar.append(Paragraph(m(e["yok"]), st["kucuk"]))
    if zamanlar is not None:
        parcalar += [Spacer(1, 4 * mm), Paragraph(m(e["zaman"]), st["bolum"])]
        if zamanlar:
            veri = [[Paragraph(f"<b>{m(x)}</b>", st["govde"] if i < 2 else st["sag"])
                     for i, x in enumerate((e["tarih"], e["aciklama"], e["faturalanabilir"], e["sure"]))]]
            top_dk = fat_dk = 0
            for x in zamanlar:
                top_dk += int(x["sure_dk"])
                fat_dk += int(x["sure_dk"]) if x.get("faturalanabilir") else 0
                veri.append([Paragraph(pb.tarih(x.get("tarih")), st["govde"]), Paragraph(m(x.get("aciklama") or ""), st["govde"]),
                             Paragraph(m(e["evet"] if x.get("faturalanabilir") else "—"), st["sag"]),
                             Paragraph(m(sure_yaz(x["sure_dk"], d)), st["sag"])])
            parcalar.append(tablo(veri, [24 * mm, 100 * mm, 26 * mm, 30 * mm]))
            parcalar += [Spacer(1, 2 * mm), Paragraph(
                f"<b>{m(e['toplam'])}:</b> {m(sure_yaz(top_dk, d))} · {m(e['faturalanabilir'])}: {m(sure_yaz(fat_dk, d))}",
                st["sag"])]
        else:
            parcalar.append(Paragraph(m(e["yok"]), st["kucuk"]))
    tampon = io.BytesIO()
    doc = SimpleDocTemplate(tampon, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm,
                            bottomMargin=20 * mm, title=e["baslik"], author=(buro_adi or "")[:80] or "—",
                            creator="mehmetkuru.dev")

    def alt(canvas, doc_):
        canvas.saveState()
        canvas.setStrokeColor(pb.CIZGI)
        canvas.setLineWidth(0.4)
        canvas.line(15 * mm, 14 * mm, 195 * mm, 14 * mm)
        canvas.setFont(pb.YAZI, 7)
        canvas.setFillColor(colors.HexColor("#5B5368"))
        canvas.drawString(15 * mm, 10 * mm, e["not"][:180])
        canvas.drawRightString(195 * mm, 10 * mm, str(doc_.page))
        canvas.restoreState()

    doc.build(parcalar, onFirstPage=alt, onLaterPages=alt)
    return tampon.getvalue()


def dosya_basligi(d: Any, dil: str = "tr") -> str:
    """Dosyanın kısa adı: iç no / esas no + konu (yoksa tür)."""
    no = " · ".join(x for x in (d.dosya_no or "", d.esas_no or "") if x)
    konu = d.konu or DOSYA_TURU_ADI[_dil(dil)].get(d.tur, d.tur)
    return f"{no} — {konu}" if no else konu


def pdf_dosya_adi(onek: str, d: Any) -> str:
    temiz = re.sub(r"[^A-Za-z0-9._-]+", "-", (d.dosya_no or d.esas_no or str(d.id)).strip()).strip("-") or str(d.id)
    return f"{onek}-{temiz}.pdf"


__all__ = [
    "MODUL", "IZIN", "HukukHatasi", "TemelHata", "ad_normalle", "benzerlik", "eslesmeler", "Aday", "Tatil", "ay_ekle",
    "ham_son_gun", "ilk_is_gunu", "son_gun_hesapla", "adli_tatilde_mi", "muvekkil_jetonu", "jeton_parcala",
    "jeton_gecerli_mi", "ics_uret", "dokum_pdf",
]
