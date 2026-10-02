"""Faz 5M — E-posta pazarlama: kurallar (izin, ret, jetonlar, segment, CSV, metinler).

Hukuki çerçeve (koda "tavsiye" olarak değil, ZORUNLU kural olarak gömülü)
-----------------------------------------------------------------------
Türkiye'de ticari elektronik ileti: 6563 sayılı Kanun + Ticari İletişim ve Ticari
Elektronik İletiler Hakkında Yönetmelik + İYS. Sistem şunları zorunlu kılıyor:

1. Her kişinin izin durumu + kaynağı + zamanı + metin sürümü + kanıtı (`ep_kisiler`).
2. Alıcı türü: `bireysel` (tüketici — önceden onay şart) / `kurumsal` (tacir/esnaf —
   önceden onay gerekmeyebilir, ret hakkı her iletide sunulur).
3. Bireysel alıcıya YALNIZ izinli ise gönderilir (`gonderim_karari`).
4. Her iletide tek tıkla ret bağlantısı + `List-Unsubscribe` ve
   `List-Unsubscribe-Post: List-Unsubscribe=One-Click` başlıkları (RFC 8058;
   Gmail/Yahoo toplu gönderici kuralları).
5. Gönderen kimliği (unvan, adres) her iletinin altında: ajansta Site Ayarları ›
   Yasal bilgiler (`yasal_*`), müşteride kendi ayarı (yoksa gönderim 409).
6. Ret anında etkili ve kalıcı: kişi `reddetti` + bastırma listesi; bekleyen
   gönderimler de gönderim anında yeniden denetleniyor.

Satın alınmış/kazınmış liste caydırıcısı: CSV içe aktarmada her satır için izin
kaynağı ve izin tarihi ZORUNLU sütun; yoksa kişi `izinsiz` içe alınır ve bireysel
ise hiç gönderilmez.

Çift onaylı abonelik (double opt-in): form → onay e-postası (72 saat geçerli,
tek kullanımlık jeton; veritabanında yalnız özeti) → onaylanınca izin kaydı.
"""

import base64
import csv
import hashlib
import hmac
import io
import json
import math
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

MODUL = "eposta_pazarlama"
IZIN = "pazarlama"
AJANS_KAPSAMI = "@ajans"
GENEL_KAPSAM = "*"
DILLER = ("tr", "en", "de", "ru", "zh", "hi", "ar")
ALICI_TURLERI = ("bireysel", "kurumsal")
IZIN_DURUMLARI = ("izinli", "izinsiz", "bekliyor", "reddetti")
KAYNAKLAR = ("form", "csv", "manuel", "crm")
BASTIRMA_NEDENLERI = ("ret", "sert_geri_donme", "sikayet", "elle")
IYS_DURUMLARI = ("bilinmiyor", "var", "yok")
TETIKLER = ("liste_katildi", "abonelik_onaylandi")

#: Abonelik formundaki izin metninin sürümü (metin değişirse artırılır).
BULTEN_IZIN_SURUMU = "1"
ONAY_SURESI = timedelta(hours=72)
#: Aynı adrese (aynı liste) 24 saatte en çok bu kadar onay e-postası.
ONAY_EPOSTA_SINIRI = 2
VARSAYILAN_GUNLUK_KISI_SINIRI = 1
VARSAYILAN_AYLIK_SINIR = 10000
VARSAYILAN_KISI_SINIRI = 2000
#: Otomatik askıya alma eşikleri (son 30 gün, en az ESIK_HACIM ileti).
SIKAYET_ESIGI = 0.003
GERI_DONME_ESIGI = 0.05
ESIK_HACIM = 50

_EPOSTA = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$")
_ETIKET = re.compile(r"^[\w .\-]{1,40}$", re.UNICODE)
_OZEL_ANAHTAR = re.compile(r"^[a-z][a-z0-9_]{0,29}$")


class PazarlamaHatasi(Exception):
    def __init__(self, kod: str, alan: Optional[str] = None, durum: int = 400, **ek: Any):
        super().__init__(kod)
        self.kod = kod
        self.alan = alan
        self.durum = durum
        self.ek = ek

    def detay(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"kod": self.kod}
        if self.alan:
            d["alan"] = self.alan
        d.update(self.ek)
        return d


# ---------------------------------------------------------------------------
# Zaman ve küçük yardımcılar
# ---------------------------------------------------------------------------
def simdi() -> datetime:
    """Testler bunu sabitliyor (monkeypatch)."""
    return datetime.now(timezone.utc)


def utc(an: Optional[datetime]) -> Optional[datetime]:
    if an is None:
        return None
    return an.replace(tzinfo=timezone.utc) if an.tzinfo is None else an.astimezone(timezone.utc)


def iso(an: Optional[datetime]) -> Optional[str]:
    a = utc(an)
    return a.isoformat().replace("+00:00", "Z") if a else None


def kapsam_anahtari(hesap: Optional[str]) -> str:
    return hesap or AJANS_KAPSAMI


def eposta_duzelt(ham: Any) -> str:
    return str(ham or "").strip().lower()


def eposta_gecerli(eposta: str) -> bool:
    return bool(eposta) and len(eposta) <= 254 and bool(_EPOSTA.match(eposta))


def dil_sec(ham: Any) -> str:
    d = str(ham or "").strip().lower()[:2]
    return d if d in DILLER else "tr"


def json_yukle(ham: Any, varsayilan: Any) -> Any:
    if ham in (None, ""):
        return varsayilan
    if isinstance(ham, (list, dict)):
        return ham
    try:
        deger = json.loads(ham)
    except (TypeError, ValueError):
        return varsayilan
    return deger if isinstance(deger, type(varsayilan)) else varsayilan


def json_yaz(deger: Any) -> str:
    return json.dumps(deger, ensure_ascii=False, separators=(",", ":"))


def etiketleri_duzelt(ham: Any) -> List[str]:
    if ham in (None, ""):
        return []
    if isinstance(ham, str):
        ham = [p for p in re.split(r"[,;]", ham)]
    if not isinstance(ham, (list, tuple)):
        raise PazarlamaHatasi("etiket_gecersiz", "etiketler")
    sonuc: List[str] = []
    for e in ham:
        s = " ".join(str(e or "").split()).lower()
        if not s:
            continue
        if not _ETIKET.match(s):
            raise PazarlamaHatasi("etiket_gecersiz", "etiketler")
        if s not in sonuc:
            sonuc.append(s)
    if len(sonuc) > 20:
        raise PazarlamaHatasi("etiket_sayisi", "etiketler")
    return sonuc


def ozel_alanlari_duzelt(ham: Any) -> Dict[str, str]:
    if ham in (None, ""):
        return {}
    if not isinstance(ham, dict):
        raise PazarlamaHatasi("ozel_alan_gecersiz", "ozel_alanlar")
    sonuc: Dict[str, str] = {}
    for k, v in ham.items():
        anahtar = str(k or "").strip().lower()
        if not _OZEL_ANAHTAR.match(anahtar):
            raise PazarlamaHatasi("ozel_alan_gecersiz", "ozel_alanlar")
        deger = " ".join(str(v if v is not None else "").split())[:200]
        if deger:
            sonuc[anahtar] = deger
    if len(sonuc) > 20:
        raise PazarlamaHatasi("ozel_alan_gecersiz", "ozel_alanlar")
    return sonuc


def metin(ham: Any, alan: str, sinir: int, zorunlu: bool = False, cok_satir: bool = False) -> str:
    if ham is not None and not isinstance(ham, (str, int, float)):
        raise PazarlamaHatasi("metin_gecersiz", alan)
    s = str(ham if ham is not None else "")
    s = s.strip() if cok_satir else " ".join(s.split())
    if len(s) > sinir:
        raise PazarlamaHatasi("metin_uzun", alan, en_cok=sinir)
    if zorunlu and not s:
        raise PazarlamaHatasi("metin_gerekli", alan)
    return s


def site_adresi() -> str:
    return (os.environ.get("SITE_PUBLIC_URL") or "https://mehmetkuru.dev").rstrip("/")


def maskeli_eposta(eposta: str) -> str:
    yerel, _, alan = (eposta or "").partition("@")
    if not alan:
        return "***"
    return f"{yerel[:1]}***@{alan}"


# ---------------------------------------------------------------------------
# İmzalı jetonlar (ret/tercih, izleme) ve onay jetonu
# ---------------------------------------------------------------------------
_YEDEK: Optional[bytes] = None


def _anahtar(amac: str) -> bytes:
    gizli = os.environ.get("JWT_SECRET_KEY") or ""
    if not gizli:
        global _YEDEK
        if _YEDEK is None:
            _YEDEK = secrets.token_bytes(32)
        gizli = _YEDEK.hex()
    return hashlib.sha256(f"eposta-pazarlama:{amac}:{gizli}".encode()).digest()


def _imza(amac: str, kimlik: int) -> str:
    ham = hmac.new(_anahtar(amac), f"{amac}|{int(kimlik)}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(ham).decode().rstrip("=")[:22]


def imzali_jeton(amac: str, kimlik: int) -> str:
    """`<kimlik>-<imza>`; süresiz (ret bağlantısı her zaman çalışmalı)."""
    return f"{int(kimlik)}-{_imza(amac, kimlik)}"


def jeton_coz(amac: str, jeton: Any) -> Optional[int]:
    s = str(jeton or "").strip()
    kimlik, _, imza = s.partition("-")
    if not kimlik.isdigit() or len(kimlik) > 12 or len(imza) != 22:
        return None
    if not hmac.compare_digest(imza, _imza(amac, int(kimlik))):
        return None
    return int(kimlik)


#: Abonelik formu süre jetonu: formu açtıktan en az 2 sn sonra, en geç 24 saat içinde gönderim.
FORM_EN_AZ_SN = 2.0
FORM_JETON_OMRU_SN = 24 * 3600


def form_jetonu(form_id: int, an: Optional[float] = None) -> str:
    import time as _time

    ms = int((an if an is not None else _time.time()) * 1000)
    imza = hmac.new(_anahtar("form"), f"{int(form_id)}.{ms}".encode(), hashlib.sha256).hexdigest()[:32]
    return f"{int(form_id)}.{ms}.{imza}"


def form_jetonu_dogrula(jeton: Any, form_id: int, an: Optional[float] = None) -> None:
    """Geçersizse PazarlamaHatasi: jeton_gecersiz | cok_hizli | jeton_suresi_doldu."""
    import time as _time

    parcalar = str(jeton or "").split(".")
    if len(parcalar) != 3 or not parcalar[0].isdigit() or not parcalar[1].isdigit():
        raise PazarlamaHatasi("jeton_gecersiz")
    fid, ms, imza = int(parcalar[0]), int(parcalar[1]), parcalar[2]
    beklenen = hmac.new(_anahtar("form"), f"{fid}.{ms}".encode(), hashlib.sha256).hexdigest()[:32]
    if fid != int(form_id) or not hmac.compare_digest(imza, beklenen):
        raise PazarlamaHatasi("jeton_gecersiz")
    gecen = (an if an is not None else _time.time()) - ms / 1000.0
    if gecen < FORM_EN_AZ_SN:
        raise PazarlamaHatasi("cok_hizli")
    if gecen > FORM_JETON_OMRU_SN:
        raise PazarlamaHatasi("jeton_suresi_doldu")


def ret_jetonu(kisi_id: int) -> str:
    return imzali_jeton("ret", kisi_id)


def izleme_jetonu(gonderim_id: int) -> str:
    return imzali_jeton("izle", gonderim_id)


def onay_jetonu_uret() -> Tuple[str, str]:
    """(ham jeton — yalnız e-postada, özet — veritabanında)."""
    ham = secrets.token_urlsafe(24)
    return ham, onay_ozeti(ham)


def onay_ozeti(ham: str) -> str:
    return hashlib.sha256(("ep-onay:" + str(ham or "")).encode()).hexdigest()


def tercih_adresi(kisi_id: int, ret: bool = False) -> str:
    return f"{site_adresi()}/bulten/tercih/{ret_jetonu(kisi_id)}" + ("?islem=ret" if ret else "")


def tek_tik_adresi(kisi_id: int) -> str:
    """RFC 8058: `List-Unsubscribe` adresi (POST → anında ret; GET → tercih sayfasına)."""
    return f"{site_adresi()}/api/v1/bulten/ret/{ret_jetonu(kisi_id)}"


def onay_adresi(ham_jeton: str) -> str:
    return f"{site_adresi()}/bulten/onay/{ham_jeton}"


def form_adresi(anahtar: str) -> str:
    return f"{site_adresi()}/bulten/{anahtar}"


def gorsel_adresi(anahtar: str) -> str:
    return f"{site_adresi()}/api/v1/bulten/gorsel/{anahtar}"


def piksel_adresi(gonderim_id: int) -> str:
    return f"{site_adresi()}/api/v1/bulten/a/{izleme_jetonu(gonderim_id)}.gif"


def tiklama_adresi(gonderim_id: int, indeks: int) -> str:
    return f"{site_adresi()}/api/v1/bulten/t/{izleme_jetonu(gonderim_id)}/{int(indeks)}"


def ret_basliklari(kisi_id: int) -> Dict[str, str]:
    """Her pazarlama iletisinde: tek tıkla ret (Gmail/Yahoo toplu gönderici kuralları)."""
    return {
        "List-Unsubscribe": f"<{tek_tik_adresi(kisi_id)}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }


# ---------------------------------------------------------------------------
# Gönderim kararı (izin kuralları)
# ---------------------------------------------------------------------------
def gonderim_karari(
    kisi: Any,
    *,
    bastirilmis: bool,
    son_24_saat: int = 0,
    gunluk_sinir: int = VARSAYILAN_GUNLUK_KISI_SINIRI,
) -> Optional[str]:
    """Gönderilebilirse None; değilse atlama nedeni.

    Sıra: geçersiz adres → bastırma → ret → izin (bireysel yalnız izinli; kurumsal
    izinsiz de olur ama reddettiyse asla) → sıklık sınırı.
    """
    eposta = eposta_duzelt(getattr(kisi, "eposta", ""))
    if not eposta_gecerli(eposta):
        return "gecersiz_adres"
    if bastirilmis:
        return "bastirildi"
    if getattr(kisi, "ret_zamani", None) is not None or getattr(kisi, "izin_durumu", None) == "reddetti":
        return "ret"
    tur = getattr(kisi, "alici_turu", None) or "bireysel"
    izin = getattr(kisi, "izin_durumu", None) or "izinsiz"
    if tur != "kurumsal" and izin != "izinli":
        return "izin_yok"
    if gunluk_sinir and son_24_saat >= gunluk_sinir:
        return "siklik_siniri"
    return None


def neden_anahtari(kisi: Any) -> str:
    """Alt bilgideki "neden aldınız" satırı: izinli → izin; kurumsal izinsiz → ticari iletişim."""
    return "neden_izinli" if getattr(kisi, "izin_durumu", None) == "izinli" else "neden_kurumsal"


# ---------------------------------------------------------------------------
# A/B konu testi
# ---------------------------------------------------------------------------
def ab_orneklem(toplam: int, oran: int) -> Tuple[int, int]:
    """(A sayısı, B sayısı): toplamın %oran'ı ikiye bölünür (her biri en az 1)."""
    if toplam < 2:
        return toplam, 0
    ornek = max(2, math.ceil(toplam * max(5, min(50, int(oran))) / 100))
    ornek = min(ornek, toplam)
    a = math.ceil(ornek / 2)
    return a, ornek - a


def ab_kazanan(a: Dict[str, int], b: Dict[str, int], olcut: str = "acilma") -> str:
    """Oran = benzersiz açılma (ya da tıklama) / gönderilen. Eşitlikte A (ilk konu)."""
    alan = "tiklayan" if olcut == "tiklama" else "acilan"

    def oran(s: Dict[str, int]) -> float:
        g = int(s.get("gonderilen") or 0)
        return (int(s.get(alan) or 0) / g) if g else 0.0

    return "b" if oran(b) > oran(a) else "a"


def ab_duzelt(ham: Any) -> Dict[str, Any]:
    d = ham if isinstance(ham, dict) else json_yukle(ham, {})
    acik = d.get("acik") is True
    sonuc: Dict[str, Any] = {"acik": acik}
    if not acik:
        return sonuc
    konu_b = " ".join(str(d.get("konu_b") or "").replace("\r", " ").replace("\n", " ").split())
    if not konu_b:
        raise PazarlamaHatasi("metin_gerekli", "konu_b")
    if len(konu_b) > 200:
        raise PazarlamaHatasi("metin_uzun", "konu_b", en_cok=200)
    oran = d.get("oran", 20)
    bekleme = d.get("bekleme_saat", 4)
    for ad, deger, en_az, en_cok in (("oran", oran, 10, 50), ("bekleme_saat", bekleme, 1, 72)):
        if isinstance(deger, bool) or not isinstance(deger, (int, float)) or not (en_az <= int(deger) <= en_cok):
            raise PazarlamaHatasi("sayi_gecersiz", ad, en_az=en_az, en_cok=en_cok)
    olcut = d.get("olcut") if d.get("olcut") in ("acilma", "tiklama") else "acilma"
    sonuc.update({"konu_b": konu_b, "oran": int(oran), "bekleme_saat": int(bekleme), "olcut": olcut})
    return sonuc


# ---------------------------------------------------------------------------
# Segment değerlendirme (saf)
# ---------------------------------------------------------------------------
SEGMENT_ALANLARI = (
    "kaynak", "etiket", "alici_turu", "izin_durumu", "son_etkilesim", "kayit", "ozel", "liste", "crm_asama", "crm_etiket",
)
SEGMENT_OPLARI = {
    "kaynak": ("esit", "esit_degil"),
    "alici_turu": ("esit",),
    "izin_durumu": ("esit", "esit_degil"),
    "etiket": ("icerir", "icermez"),
    "crm_etiket": ("icerir", "icermez"),
    "crm_asama": ("esit", "esit_degil"),
    "son_etkilesim": ("son_gun", "gun_once", "hic"),
    "kayit": ("son_gun", "gun_once"),
    "ozel": ("esit", "esit_degil", "icerir", "dolu", "bos"),
    "liste": ("uye", "uye_degil"),
}
#: Yalnız ajans (CRM ajansın kendi satış hunisi).
YALNIZ_AJANS_ALANLARI = ("crm_asama", "crm_etiket")


def segment_duzelt(ham: Any, ajans: bool) -> Dict[str, Any]:
    d = ham if isinstance(ham, dict) else json_yukle(ham, {})
    birlesim = "veya" if d.get("birlesim") == "veya" else "ve"
    kurallar = d.get("kurallar")
    if not isinstance(kurallar, list) or not kurallar:
        raise PazarlamaHatasi("kural_gerekli", "kurallar")
    if len(kurallar) > 20:
        raise PazarlamaHatasi("kural_sayisi", "kurallar")
    temiz: List[Dict[str, Any]] = []
    for i, k in enumerate(kurallar):
        if not isinstance(k, dict):
            raise PazarlamaHatasi("kural_gecersiz", "kurallar", indeks=i)
        alan = k.get("alan")
        if alan not in SEGMENT_ALANLARI or (alan in YALNIZ_AJANS_ALANLARI and not ajans):
            raise PazarlamaHatasi("kural_gecersiz", "alan", indeks=i)
        op = k.get("op")
        if op not in SEGMENT_OPLARI[alan]:
            raise PazarlamaHatasi("kural_gecersiz", "op", indeks=i)
        kural: Dict[str, Any] = {"alan": alan, "op": op}
        if alan in ("son_etkilesim", "kayit"):
            if op != "hic":
                g = k.get("deger")
                if isinstance(g, bool) or not isinstance(g, (int, float)) or not (1 <= int(g) <= 3650):
                    raise PazarlamaHatasi("kural_gecersiz", "deger", indeks=i)
                kural["deger"] = int(g)
        elif alan == "liste":
            lid = k.get("deger")
            if isinstance(lid, bool) or not isinstance(lid, int):
                raise PazarlamaHatasi("kural_gecersiz", "deger", indeks=i)
            kural["deger"] = lid
        elif alan == "ozel":
            anahtar = str(k.get("anahtar") or "").strip().lower()
            if not _OZEL_ANAHTAR.match(anahtar):
                raise PazarlamaHatasi("kural_gecersiz", "anahtar", indeks=i)
            kural["anahtar"] = anahtar
            if op not in ("dolu", "bos"):
                kural["deger"] = " ".join(str(k.get("deger") or "").split())[:200]
        else:
            deger = " ".join(str(k.get("deger") or "").split()).lower()[:80]
            if not deger:
                raise PazarlamaHatasi("kural_gecersiz", "deger", indeks=i)
            kural["deger"] = deger
        temiz.append(kural)
    return {"birlesim": birlesim, "kurallar": temiz}


def _katla(s: Any) -> str:
    """Karşılaştırma için küçük harf (Türkçe İ/I dahil; ı ile i eşit sayılır: "İzmir" = "izmir")."""
    return str(s or "").replace("İ", "i").replace("I", "ı").lower().replace("ı", "i").replace("\u0307", "")


def _kural_tutar(k: Dict[str, Any], kisi: Any, baglam: Dict[str, Any]) -> bool:
    alan, op = k["alan"], k["op"]
    an: datetime = baglam.get("simdi") or simdi()
    if alan in ("kaynak", "alici_turu", "izin_durumu"):
        deger = str(getattr(kisi, alan, "") or "").lower()
        return (deger == k["deger"]) if op == "esit" else (deger != k["deger"])
    if alan == "etiket":
        etiketler = json_yukle(getattr(kisi, "etiketler", None), [])
        var = _katla(k["deger"]) in [_katla(e) for e in etiketler]
        return var if op == "icerir" else not var
    if alan in ("crm_asama", "crm_etiket"):
        crm = (baglam.get("crm") or {}).get(getattr(kisi, "crm_aday_id", None))
        if alan == "crm_asama":
            asama = (crm or {}).get("asama")
            return (asama == k["deger"]) if op == "esit" else (asama != k["deger"])
        var = k["deger"] in ((crm or {}).get("etiketler") or [])
        return var if op == "icerir" else not var
    if alan == "son_etkilesim":
        son = utc(getattr(kisi, "son_etkilesim_at", None))
        if op == "hic":
            return son is None
        if son is None:
            return op == "gun_once"
        sinir = an - timedelta(days=k["deger"])
        return son >= sinir if op == "son_gun" else son < sinir
    if alan == "kayit":
        olusma = utc(getattr(kisi, "created_at", None)) or an
        sinir = an - timedelta(days=k["deger"])
        return olusma >= sinir if op == "son_gun" else olusma < sinir
    if alan == "ozel":
        alanlar = json_yukle(getattr(kisi, "ozel_alanlar", None), {})
        deger = str(alanlar.get(k["anahtar"]) or "")
        if op == "dolu":
            return bool(deger)
        if op == "bos":
            return not deger
        if op == "icerir":
            return _katla(k["deger"]) in _katla(deger)
        esit = _katla(deger) == _katla(k["deger"])
        return esit if op == "esit" else not esit
    if alan == "liste":
        uye = k["deger"] in (baglam.get("uyelikler") or {}).get(getattr(kisi, "id", None), set())
        return uye if op == "uye" else not uye
    return False


def segment_degerlendir(kurallar: Dict[str, Any], kisiler: Iterable[Any], baglam: Optional[Dict[str, Any]] = None) -> List[Any]:
    """Kurallara uyan kişiler. `baglam`: {"simdi", "uyelikler": {kisi_id: {liste_id}}, "crm": {aday_id: {...}}}."""
    baglam = baglam or {}
    liste = kurallar.get("kurallar") or []
    herhangi = kurallar.get("birlesim") == "veya"
    sonuc = []
    for kisi in kisiler:
        tutanlar = (_kural_tutar(k, kisi, baglam) for k in liste)
        if (any(tutanlar) if herhangi else all(tutanlar)):
            sonuc.append(kisi)
    return sonuc


# ---------------------------------------------------------------------------
# CSV içe aktarma (saf)
# ---------------------------------------------------------------------------
CSV_EN_COK_SATIR = 20000
CSV_EN_COK_BAYT = 5 * 1024 * 1024
_CSV_BASLIKLARI = {
    "eposta": "eposta", "e-posta": "eposta", "email": "eposta", "e_posta": "eposta", "mail": "eposta", "e-mail": "eposta",
    "ad": "ad", "ad_soyad": "ad", "adsoyad": "ad", "name": "ad", "isim": "ad", "full_name": "ad",
    "firma": "firma", "sirket": "firma", "şirket": "firma", "company": "firma",
    "alici_turu": "alici_turu", "tur": "alici_turu", "tür": "alici_turu", "type": "alici_turu",
    "izin_kaynagi": "izin_kaynagi", "izin kaynağı": "izin_kaynagi", "izin_kaynağı": "izin_kaynagi", "consent_source": "izin_kaynagi",
    "izin_tarihi": "izin_tarihi", "izin tarihi": "izin_tarihi", "consent_date": "izin_tarihi",
    "etiketler": "etiketler", "etiket": "etiketler", "tags": "etiketler",
    "dil": "dil", "language": "dil",
}
_TUR_ESLEME = {"bireysel": "bireysel", "b2c": "bireysel", "tuketici": "bireysel", "tüketici": "bireysel", "individual": "bireysel",
               "kurumsal": "kurumsal", "b2b": "kurumsal", "tacir": "kurumsal", "esnaf": "kurumsal", "business": "kurumsal"}


def _tarih_coz(ham: str) -> Optional[datetime]:
    s = (ham or "").strip()
    if not s:
        return None
    for bicim in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d.%m.%Y", "%d.%m.%Y %H:%M", "%d/%m/%Y"):
        try:
            an = datetime.strptime(s.replace("Z", ""), bicim)
            return an.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        an = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return utc(an)
    except ValueError:
        return None


def csv_coz(bayt: bytes, varsayilan_tur: str = "bireysel") -> Dict[str, Any]:
    """CSV → {satirlar: [...], hatalar: [...], ozet}. Satır: eposta, ad, firma, alici_turu, izinli, izin_kaynagi, izin_zamani…

    İzin sütunları: `izin_kaynagi` + `izin_tarihi` İKİSİ de dolu ve tarih geçmişteyse
    satır `izinli`; biri eksikse `izinsiz` (bireysel ise gönderilmez — uyarı listesinde).
    """
    if len(bayt) > CSV_EN_COK_BAYT:
        raise PazarlamaHatasi("dosya_buyuk", "dosya", durum=413)
    metin_ = None
    for kod in ("utf-8-sig", "cp1254", "latin-1"):
        try:
            metin_ = bayt.decode(kod)
            break
        except UnicodeDecodeError:
            continue
    if metin_ is None:
        raise PazarlamaHatasi("dosya_gecersiz", "dosya")
    ilk = metin_.split("\n", 1)[0]
    ayrac = ";" if ilk.count(";") > ilk.count(",") else ("\t" if ilk.count("\t") > ilk.count(",") else ",")
    okuyucu = csv.reader(io.StringIO(metin_), delimiter=ayrac)
    try:
        basliklar = next(okuyucu)
    except StopIteration:
        raise PazarlamaHatasi("dosya_bos", "dosya")
    esleme = [_CSV_BASLIKLARI.get(b.strip().lower()) for b in basliklar]
    if "eposta" not in esleme:
        raise PazarlamaHatasi("eposta_sutunu_yok", "dosya")
    an = simdi()
    satirlar: List[Dict[str, Any]] = []
    hatalar: List[Dict[str, Any]] = []
    gorulen: set = set()
    izinsiz_bireysel = 0
    for no, satir in enumerate(okuyucu, start=2):
        if not any((h or "").strip() for h in satir):
            continue
        if len(satirlar) + len(hatalar) >= CSV_EN_COK_SATIR:
            raise PazarlamaHatasi("satir_sayisi", "dosya", en_cok=CSV_EN_COK_SATIR)
        d: Dict[str, str] = {}
        for i, h in enumerate(satir):
            if i < len(esleme) and esleme[i] and esleme[i] not in d:
                d[esleme[i]] = (h or "").strip()
        eposta = eposta_duzelt(d.get("eposta"))
        if not eposta_gecerli(eposta):
            hatalar.append({"satir": no, "kod": "eposta_gecersiz", "deger": (d.get("eposta") or "")[:80]})
            continue
        if eposta in gorulen:
            hatalar.append({"satir": no, "kod": "tekrar", "deger": eposta})
            continue
        gorulen.add(eposta)
        tur = _TUR_ESLEME.get((d.get("alici_turu") or "").strip().lower(), varsayilan_tur)
        izin_kaynagi = " ".join((d.get("izin_kaynagi") or "").split())[:120]
        izin_zamani = _tarih_coz(d.get("izin_tarihi") or "")
        izinli = bool(izin_kaynagi) and izin_zamani is not None and izin_zamani <= an
        try:
            etiketler = etiketleri_duzelt(d.get("etiketler") or "")
        except PazarlamaHatasi:
            etiketler = []
        if not izinli and tur == "bireysel":
            izinsiz_bireysel += 1
        satirlar.append({
            "satir": no, "eposta": eposta, "ad": " ".join((d.get("ad") or "").split())[:120] or None,
            "firma": " ".join((d.get("firma") or "").split())[:160] or None, "alici_turu": tur,
            "izinli": izinli, "izin_kaynagi": izin_kaynagi or None, "izin_zamani": iso(izin_zamani) if izinli else None,
            "etiketler": etiketler, "dil": dil_sec(d.get("dil")) if d.get("dil") else None,
        })
    return {
        "satirlar": satirlar,
        "hatalar": hatalar[:200],
        "ozet": {
            "gecerli": len(satirlar), "hatali": len(hatalar), "izinli": sum(1 for s in satirlar if s["izinli"]),
            "izinsiz": sum(1 for s in satirlar if not s["izinli"]), "izinsiz_bireysel": izinsiz_bireysel,
            "kurumsal": sum(1 for s in satirlar if s["alici_turu"] == "kurumsal"),
        },
    }


# ---------------------------------------------------------------------------
# Ziyaretçiye/alıcıya giden sunucu metinleri (7 dil)
# ---------------------------------------------------------------------------
#: Abonelik formu (gömme betiği ve /bulten/<anahtar> sunucudan alıyor).
FORM_METINLERI: Dict[str, Dict[str, Any]] = {
    "tr": {
        "eposta": "E-posta", "ad": "Adınız", "gonder": "Abone ol", "gonderiliyor": "Gönderiliyor…", "istege_bagli": "isteğe bağlı",
        "kurumsal": "Bu bir işletme (kurumsal) adresi", "aydinlatma": "Aydınlatma metni",
        "izin": "{gonderen} tarafından gönderilecek kampanya, duyuru ve bülten e-postalarını almak istiyorum. İznimi her iletideki bağlantıyla dilediğim an geri alabilirim.",
        "tesekkur": "Neredeyse tamam! Aboneliğinizi başlatmak için e-posta kutunuza gönderdiğimiz bağlantıya tıklayın.",
        "hata": {"alan_gerekli": "Lütfen zorunlu alanları doldurun.", "eposta_gecersiz": "Geçerli bir e-posta adresi yazın.",
                 "izin_gerekli": "Abone olmak için onay kutusunu işaretleyin.", "cok_hizli": "Çok hızlı gönderildi; birkaç saniye sonra tekrar deneyin.",
                 "cok_fazla_istek": "Çok fazla deneme yapıldı; biraz sonra tekrar deneyin.", "jeton_suresi_doldu": "Formun süresi doldu; sayfayı yenileyin.",
                 "form_yok": "Bu form artık kullanılmıyor.", "alan_adi_izinsiz": "Bu form bu sitede kullanılamıyor.", "genel": "Gönderilemedi; lütfen tekrar deneyin."},
    },
    "en": {
        "eposta": "Email", "ad": "Your name", "gonder": "Subscribe", "gonderiliyor": "Sending…", "istege_bagli": "optional",
        "kurumsal": "This is a business address", "aydinlatma": "Privacy notice",
        "izin": "I would like to receive campaign, announcement and newsletter emails from {gonderen}. I can withdraw my consent at any time using the link in every message.",
        "tesekkur": "Almost done! Click the link we have sent to your inbox to start your subscription.",
        "hata": {"alan_gerekli": "Please fill in the required fields.", "eposta_gecersiz": "Please enter a valid email address.",
                 "izin_gerekli": "Please tick the consent box to subscribe.", "cok_hizli": "Sent too quickly; please try again in a few seconds.",
                 "cok_fazla_istek": "Too many attempts; please try again a little later.", "jeton_suresi_doldu": "The form has expired; please reload the page.",
                 "form_yok": "This form is no longer in use.", "alan_adi_izinsiz": "This form cannot be used on this site.", "genel": "Could not send; please try again."},
    },
    "de": {
        "eposta": "E-Mail", "ad": "Ihr Name", "gonder": "Abonnieren", "gonderiliyor": "Wird gesendet…", "istege_bagli": "optional",
        "kurumsal": "Dies ist eine geschäftliche Adresse", "aydinlatma": "Datenschutzhinweis",
        "izin": "Ich möchte E-Mails mit Aktionen, Ankündigungen und Newslettern von {gonderen} erhalten. Meine Einwilligung kann ich jederzeit über den Link in jeder Nachricht widerrufen.",
        "tesekkur": "Fast geschafft! Klicken Sie auf den Link, den wir an Ihr Postfach gesendet haben, um Ihr Abonnement zu starten.",
        "hata": {"alan_gerekli": "Bitte füllen Sie die Pflichtfelder aus.", "eposta_gecersiz": "Bitte geben Sie eine gültige E-Mail-Adresse ein.",
                 "izin_gerekli": "Bitte setzen Sie das Häkchen, um zu abonnieren.", "cok_hizli": "Zu schnell gesendet; bitte in einigen Sekunden erneut versuchen.",
                 "cok_fazla_istek": "Zu viele Versuche; bitte etwas später erneut versuchen.", "jeton_suresi_doldu": "Das Formular ist abgelaufen; bitte Seite neu laden.",
                 "form_yok": "Dieses Formular wird nicht mehr verwendet.", "alan_adi_izinsiz": "Dieses Formular kann auf dieser Website nicht verwendet werden.",
                 "genel": "Senden fehlgeschlagen; bitte erneut versuchen."},
    },
    "ru": {
        "eposta": "Эл. почта", "ad": "Ваше имя", "gonder": "Подписаться", "gonderiliyor": "Отправка…", "istege_bagli": "необязательно",
        "kurumsal": "Это рабочий (корпоративный) адрес", "aydinlatma": "Уведомление о конфиденциальности",
        "izin": "Я хочу получать от {gonderen} письма с акциями, объявлениями и рассылкой. Я могу отозвать согласие в любой момент по ссылке в каждом письме.",
        "tesekkur": "Почти готово! Чтобы начать подписку, перейдите по ссылке из письма, которое мы отправили вам.",
        "hata": {"alan_gerekli": "Заполните обязательные поля.", "eposta_gecersiz": "Укажите корректный адрес эл. почты.",
                 "izin_gerekli": "Чтобы подписаться, отметьте согласие.", "cok_hizli": "Отправлено слишком быстро; повторите через несколько секунд.",
                 "cok_fazla_istek": "Слишком много попыток; повторите немного позже.", "jeton_suresi_doldu": "Срок действия формы истёк; обновите страницу.",
                 "form_yok": "Эта форма больше не используется.", "alan_adi_izinsiz": "Эту форму нельзя использовать на этом сайте.",
                 "genel": "Не удалось отправить; попробуйте ещё раз."},
    },
    "zh": {
        "eposta": "电子邮箱", "ad": "您的姓名", "gonder": "订阅", "gonderiliyor": "正在提交…", "istege_bagli": "选填",
        "kurumsal": "这是企业（工作）邮箱", "aydinlatma": "隐私说明",
        "izin": "我希望接收 {gonderen} 发送的优惠活动、公告和简报邮件。我可以随时通过每封邮件中的链接撤回同意。",
        "tesekkur": "就差一步！请点击我们发送到您邮箱的链接以开始订阅。",
        "hata": {"alan_gerekli": "请填写必填项。", "eposta_gecersiz": "请输入有效的电子邮箱地址。", "izin_gerekli": "请勾选同意框以订阅。",
                 "cok_hizli": "提交过快，请几秒后再试。", "cok_fazla_istek": "尝试次数过多，请稍后再试。", "jeton_suresi_doldu": "表单已过期，请刷新页面。",
                 "form_yok": "此表单已停用。", "alan_adi_izinsiz": "此表单不能在本网站使用。", "genel": "提交失败，请重试。"},
    },
    "hi": {
        "eposta": "ईमेल", "ad": "आपका नाम", "gonder": "सदस्यता लें", "gonderiliyor": "भेजा जा रहा है…", "istege_bagli": "वैकल्पिक",
        "kurumsal": "यह एक व्यावसायिक पता है", "aydinlatma": "गोपनीयता सूचना",
        "izin": "मैं {gonderen} से अभियान, घोषणा और न्यूज़लेटर ईमेल पाना चाहता/चाहती हूँ। मैं हर संदेश में दिए लिंक से कभी भी अपनी सहमति वापस ले सकता/सकती हूँ।",
        "tesekkur": "लगभग पूरा! सदस्यता शुरू करने के लिए आपके इनबॉक्स में भेजे गए लिंक पर क्लिक करें।",
        "hata": {"alan_gerekli": "कृपया आवश्यक फ़ील्ड भरें।", "eposta_gecersiz": "कृपया मान्य ईमेल पता लिखें।", "izin_gerekli": "सदस्यता के लिए सहमति बॉक्स पर टिक करें।",
                 "cok_hizli": "बहुत जल्दी भेजा गया; कुछ सेकंड बाद फिर कोशिश करें।", "cok_fazla_istek": "बहुत अधिक प्रयास; थोड़ी देर बाद फिर कोशिश करें।",
                 "jeton_suresi_doldu": "फ़ॉर्म की अवधि समाप्त हो गई; पेज रीफ़्रेश करें।", "form_yok": "यह फ़ॉर्म अब उपयोग में नहीं है।",
                 "alan_adi_izinsiz": "यह फ़ॉर्म इस साइट पर उपयोग नहीं किया जा सकता।", "genel": "भेजा नहीं जा सका; कृपया फिर कोशिश करें।"},
    },
    "ar": {
        "eposta": "البريد الإلكتروني", "ad": "اسمك", "gonder": "اشترك", "gonderiliyor": "جارٍ الإرسال…", "istege_bagli": "اختياري",
        "kurumsal": "هذا عنوان بريد تجاري (لشركة)", "aydinlatma": "إشعار الخصوصية",
        "izin": "أرغب في تلقي رسائل العروض والإعلانات والنشرات الإخبارية من {gonderen}. يمكنني سحب موافقتي في أي وقت عبر الرابط الموجود في كل رسالة.",
        "tesekkur": "اقتربت! انقر على الرابط الذي أرسلناه إلى بريدك لبدء اشتراكك.",
        "hata": {"alan_gerekli": "يرجى ملء الحقول المطلوبة.", "eposta_gecersiz": "يرجى كتابة بريد إلكتروني صالح.", "izin_gerekli": "يرجى تحديد مربع الموافقة للاشتراك.",
                 "cok_hizli": "تم الإرسال بسرعة كبيرة؛ يرجى المحاولة بعد بضع ثوانٍ.", "cok_fazla_istek": "محاولات كثيرة جدًا؛ يرجى المحاولة لاحقًا.",
                 "jeton_suresi_doldu": "انتهت صلاحية النموذج؛ يرجى تحديث الصفحة.", "form_yok": "هذا النموذج لم يعد مستخدمًا.",
                 "alan_adi_izinsiz": "لا يمكن استخدام هذا النموذج على هذا الموقع.", "genel": "تعذّر الإرسال؛ يرجى المحاولة مجددًا."},
    },
}

#: İleti alt bilgisi ve onay e-postası (alıcının/kampanyanın dilinde).
ILETI_METINLERI: Dict[str, Dict[str, str]] = {
    "tr": {
        "neden_izinli": "Bu e-postayı, {gonderen} iletilerini almayı kabul ettiğiniz için aldınız.",
        "neden_kurumsal": "Bu e-posta, işletmenize yönelik ticari iletişim kapsamında {gonderen} tarafından gönderildi.",
        "ret": "Abonelikten çık", "tercih": "E-posta tercihleri", "gonderen": "Gönderen",
        "onay_konu": "Aboneliğinizi onaylayın — {liste}",
        "onay_baslik": "Aboneliğinizi onaylayın",
        "onay_govde": "Merhaba{ad},\n\nBu adres {gonderen} e-posta listesine ({liste}) abone olmak için kullanıldı. Aboneliğinizi başlatmak için aşağıdaki düğmeye tıklayın.\n\nBu isteği siz yapmadıysanız bu e-postayı yok sayın; onaylamadığınız sürece size hiçbir bülten gönderilmez. Bağlantı 72 saat geçerlidir.",
        "onay_dugme": "Aboneliğimi onayla", "test_onek": "[TEST]",
    },
    "en": {
        "neden_izinli": "You received this email because you agreed to receive messages from {gonderen}.",
        "neden_kurumsal": "This email was sent by {gonderen} as part of business communication addressed to your company.",
        "ret": "Unsubscribe", "tercih": "Email preferences", "gonderen": "Sender",
        "onay_konu": "Please confirm your subscription — {liste}",
        "onay_baslik": "Confirm your subscription",
        "onay_govde": "Hello{ad},\n\nThis address was used to subscribe to the {gonderen} mailing list ({liste}). Click the button below to start your subscription.\n\nIf you did not make this request, simply ignore this email; you will not receive any newsletter unless you confirm. The link is valid for 72 hours.",
        "onay_dugme": "Confirm my subscription", "test_onek": "[TEST]",
    },
    "de": {
        "neden_izinli": "Sie erhalten diese E-Mail, weil Sie dem Empfang von Nachrichten von {gonderen} zugestimmt haben.",
        "neden_kurumsal": "Diese E-Mail wurde von {gonderen} im Rahmen geschäftlicher Kommunikation an Ihr Unternehmen gesendet.",
        "ret": "Abmelden", "tercih": "E-Mail-Einstellungen", "gonderen": "Absender",
        "onay_konu": "Bitte bestätigen Sie Ihr Abonnement — {liste}",
        "onay_baslik": "Abonnement bestätigen",
        "onay_govde": "Hallo{ad},\n\nDiese Adresse wurde für ein Abonnement der Mailingliste von {gonderen} ({liste}) verwendet. Klicken Sie auf die Schaltfläche unten, um Ihr Abonnement zu starten.\n\nWenn Sie das nicht waren, ignorieren Sie diese E-Mail einfach; ohne Bestätigung erhalten Sie keinen Newsletter. Der Link ist 72 Stunden gültig.",
        "onay_dugme": "Abonnement bestätigen", "test_onek": "[TEST]",
    },
    "ru": {
        "neden_izinli": "Вы получили это письмо, потому что согласились получать сообщения от {gonderen}.",
        "neden_kurumsal": "Это письмо отправлено {gonderen} в рамках деловой переписки с вашей компанией.",
        "ret": "Отписаться", "tercih": "Настройки рассылки", "gonderen": "Отправитель",
        "onay_konu": "Подтвердите подписку — {liste}",
        "onay_baslik": "Подтвердите подписку",
        "onay_govde": "Здравствуйте{ad}!\n\nЭтот адрес был указан для подписки на рассылку {gonderen} ({liste}). Нажмите кнопку ниже, чтобы начать подписку.\n\nЕсли это были не вы, просто проигнорируйте письмо: без подтверждения рассылка не придёт. Ссылка действует 72 часа.",
        "onay_dugme": "Подтвердить подписку", "test_onek": "[ТЕСТ]",
    },
    "zh": {
        "neden_izinli": "您收到此邮件，是因为您同意接收 {gonderen} 的信息。",
        "neden_kurumsal": "此邮件由 {gonderen} 作为面向贵公司的商务沟通发送。",
        "ret": "退订", "tercih": "邮件偏好设置", "gonderen": "发件人",
        "onay_konu": "请确认您的订阅 — {liste}",
        "onay_baslik": "确认订阅",
        "onay_govde": "您好{ad}：\n\n有人使用此地址订阅了 {gonderen} 的邮件列表（{liste}）。请点击下方按钮开始订阅。\n\n如果不是您本人操作，请忽略此邮件；未经确认，您不会收到任何简报。链接 72 小时内有效。",
        "onay_dugme": "确认订阅", "test_onek": "[测试]",
    },
    "hi": {
        "neden_izinli": "आपको यह ईमेल इसलिए मिला क्योंकि आपने {gonderen} से संदेश पाने की सहमति दी थी।",
        "neden_kurumsal": "यह ईमेल {gonderen} ने आपकी कंपनी को व्यावसायिक संचार के तहत भेजा है।",
        "ret": "सदस्यता छोड़ें", "tercih": "ईमेल प्राथमिकताएँ", "gonderen": "प्रेषक",
        "onay_konu": "कृपया अपनी सदस्यता की पुष्टि करें — {liste}",
        "onay_baslik": "सदस्यता की पुष्टि करें",
        "onay_govde": "नमस्ते{ad},\n\nइस पते का उपयोग {gonderen} की मेलिंग सूची ({liste}) की सदस्यता के लिए किया गया। सदस्यता शुरू करने के लिए नीचे दिए बटन पर क्लिक करें।\n\nअगर यह अनुरोध आपने नहीं किया, तो इस ईमेल को अनदेखा करें; पुष्टि के बिना आपको कोई न्यूज़लेटर नहीं भेजा जाएगा। लिंक 72 घंटे तक मान्य है।",
        "onay_dugme": "मेरी सदस्यता की पुष्टि करें", "test_onek": "[परीक्षण]",
    },
    "ar": {
        "neden_izinli": "تلقيت هذه الرسالة لأنك وافقت على تلقي الرسائل من {gonderen}.",
        "neden_kurumsal": "أُرسلت هذه الرسالة من {gonderen} في إطار التواصل التجاري الموجّه إلى شركتك.",
        "ret": "إلغاء الاشتراك", "tercih": "تفضيلات البريد", "gonderen": "المرسل",
        "onay_konu": "يرجى تأكيد اشتراكك — {liste}",
        "onay_baslik": "تأكيد الاشتراك",
        "onay_govde": "مرحبًا{ad}،\n\nاستُخدم هذا العنوان للاشتراك في القائمة البريدية لـ {gonderen} ({liste}). انقر على الزر أدناه لبدء اشتراكك.\n\nإذا لم تقم بهذا الطلب فتجاهل هذه الرسالة؛ لن تصلك أي نشرة ما لم تؤكد. الرابط صالح لمدة 72 ساعة.",
        "onay_dugme": "تأكيد اشتراكي", "test_onek": "[اختبار]",
    },
}


def form_izin_metni(dil: str, gonderen: str) -> str:
    return FORM_METINLERI[dil_sec(dil)]["izin"].replace("{gonderen}", gonderen)


def form_izin_surumu(dil: str) -> str:
    return f"bulten-{BULTEN_IZIN_SURUMU}/{dil_sec(dil)}"


def metin_ozeti(metin_: str) -> str:
    return hashlib.sha256((metin_ or "").encode("utf-8")).hexdigest()[:32]


def ileti_metni(dil: str, anahtar: str, **degerler: str) -> str:
    s = ILETI_METINLERI[dil_sec(dil)][anahtar]
    for k, v in degerler.items():
        s = s.replace("{" + k + "}", v)
    return s


__all__ = [
    "MODUL", "IZIN", "PazarlamaHatasi", "simdi", "utc", "iso", "kapsam_anahtari", "eposta_duzelt", "eposta_gecerli",
    "gonderim_karari", "ab_orneklem", "ab_kazanan", "ab_duzelt", "segment_duzelt", "segment_degerlendir", "csv_coz",
    "ret_jetonu", "izleme_jetonu", "jeton_coz", "ret_basliklari", "onay_jetonu_uret", "onay_ozeti",
]
