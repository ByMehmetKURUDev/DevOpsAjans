"""Faz 4K — Dijital kartvizit + bio link ve Google yorum sayfası: kurallar ve ortak yardımcılar.

Router'lar: `routers/kartvizit.py` (kartlar, herkese açık `/kart/<slug>`, görseller)
ve `routers/google_yorum.py` (yorum sayfaları, `/yorum/<slug>`).

Faz 4Q ile paylaşılanlar (KOPYA YOK — `services/dinamik_qr` içe aktarılıyor):
vCard üretimi (`vcard_uret`, kartvizit için geriye uyumlu ek alanlarla), QR
görseli (`svg_ciz` / `png_ciz`, ortada logo), bot / cihaz ayıklama
(`bot_mu`, `cihaz_sinifi`), adres beyaz listesi (`guvenli_hedef_mi`,
`web_adresi_duzelt`), telefon/e-posta doğrulaması, Place ID → Google yorum
adresi, kod alfabesi ve ayrılmış adlar.

Adresler
--------
* `slug`: 3–50 karakter, küçük harf/rakam/tire, ayrılmış kelimeler engelli.
  Değişince eskisi 30 gün yeni adrese yönleniyor; o sürede başka bir kayıt
  alamıyor.
* `kod`: 7 karakter, değişmez, en az bir BÜYÜK harf (slug'lar küçük harf —
  iki ad alanı asla çakışmaz). QR kodu bunu taşıyor: slug değişse de basılı
  QR çalışır. Kod ile açılan görüntülenme analitikte "QR ile" sayılıyor.

Görseller
---------
JPEG/PNG/WebP, en çok 5 MB, en çok 40 megapiksel. Sunucuda Pillow ile
açılıp EXIF yönü uygulanıyor, küçültülüyor ve WebP'ye çevriliyor (EXIF,
konum ve gömülü her şey atılıyor). Paylaşım önizlemesi (og:image) ve
vCard fotoğrafı için gerektiğinde JPEG'e dönüştürülüyor.

Parola korumalı kart
--------------------
Parola pbkdf2-sha256 (dosya paylaşımıyla aynı yardımcı). Doğru parola
girilince 2 saatlik imzalı erişim jetonu veriliyor; jeton parola özetine
bağlı — parola değişince eski jetonlar geçersiz.
"""

import base64
import hashlib
import hmac
import io
import json
import logging
import os
import re
import secrets
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from services import dinamik_qr as qr

logger = logging.getLogger(__name__)

#: Hata türü 4Q ile aynı (`{"kod", "alan", ...}` gövdesi); 4Q yardımcılarının
#: fırlattığı hatalar da olduğu gibi geçiyor.
KartHatasi = qr.QrHatasi

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------
SAHIP_TURLERI: Tuple[str, ...] = ("kart", "yorum")
DUZENLER: Tuple[str, ...] = ("kartvizit", "bio_link")
DILLER: Tuple[str, ...] = qr.DILLER
SABLONLAR: Tuple[str, ...] = ("gece", "beyaz", "kurumsal", "canli", "doga")
#: Şablonun önerilen vurgu rengi (kullanıcı değiştirebilir).
SABLON_RENKLERI: Dict[str, str] = {
    "gece": "#a855f7", "beyaz": "#2563eb", "kurumsal": "#1e3a8a", "canli": "#ec4899", "doga": "#15803d",
}
#: Sitenin kendi yazı tipleri (public/fonts: Plus Jakarta Sans, JetBrains Mono) + sistem
#: yazı tipi. (Inter sitede yalnız Kiril altkümesiyle var; Latin'de sistem yazısına düşerdi.)
YAZI_TIPLERI: Tuple[str, ...] = ("jakarta", "mono", "sistem")
KOSELER: Tuple[str, ...] = ("keskin", "yumusak", "yuvarlak")
VARSAYILAN_TEMA: Dict[str, str] = {"sablon": "gece", "renk": "#a855f7", "yazi_tipi": "jakarta", "kose": "yumusak"}

#: Sosyal bağlantı platformları → kullanıcı adı yazılırsa tamamlanan taban adres.
PLATFORMLAR: Dict[str, Optional[str]] = {
    "linkedin": "https://www.linkedin.com/in/",
    "instagram": "https://www.instagram.com/",
    "x": "https://x.com/",
    "facebook": "https://www.facebook.com/",
    "youtube": "https://www.youtube.com/@",
    "tiktok": "https://www.tiktok.com/@",
    "github": "https://github.com/",
    "behance": "https://www.behance.net/",
    "dribbble": "https://dribbble.com/",
    "pinterest": "https://www.pinterest.com/",
    "telegram": "https://t.me/",
    "threads": "https://www.threads.net/@",
    "medium": "https://medium.com/@",
    "twitch": "https://www.twitch.tv/",
    "snapchat": "https://www.snapchat.com/add/",
    "spotify": None,
    "discord": None,
    "web": None,
}
#: Bio link bağlantısının isteğe bağlı simgesi (ön yüzde lucide eşlemesi).
SIMGELER: Tuple[str, ...] = (
    "link", "globe", "shop", "calendar", "video", "music", "file", "mail", "phone", "map", "star", "gift",
    "book", "briefcase", "heart", "camera", "message", "download", "ticket", "megaphone",
)
GUNLER: Tuple[str, ...] = ("pzt", "sal", "car", "per", "cum", "cmt", "paz")
TELEFON_TIPLERI: Tuple[str, ...] = ("cep", "is", "ev", "faks")
_VCARD_TEL = {"cep": "CELL", "is": "WORK", "ev": "HOME", "faks": "FAX"}

EN_COK = {"telefon": 5, "web": 5, "sosyal": 12, "baglanti": 30, "hizmet": 20, "galeri": 8}
SINIR = {
    "ad_soyad": 100, "unvan": 100, "sirket": 120, "tanitim": 600, "etiket": 30, "adres": 300, "baslik": 80,
    "hizmet_aciklama": 300, "saat_notu": 120, "isletme_adi": 120, "tesekkur": 500,
}

SLUG_DESENI = re.compile(r"^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$")
KOD_DESENI = re.compile(r"^[A-Za-z0-9]{7}$")
#: Kart/yorum yollarında alt uç adlarıyla da çakışmasın.
AYRILMIS_SLUGLAR = frozenset(qr.AYRILMIS_ADLAR | {
    "kart", "kartlar", "kartvizit", "yorum", "yorumlar", "gorsel", "ozet", "yeni", "duzenle", "meta",
    "mesajlar", "geri-bildirim", "geri-bildirimler", "slug-uygun", "bio", "vcard", "qr", "parola", "olay",
    "mesaj", "rehber", "google",
})
ESKI_SLUG_GUN = 30

GORSEL_TURLERI_KART: Tuple[str, ...] = ("foto", "logo", "kapak", "galeri")
GORSEL_EN_COK_BAYT = 5 * 1024 * 1024
GORSEL_EN_COK_PIKSEL = 40_000_000
#: Tür → en büyük kenar (gen, yük). Fotoğraf kare kırpılıyor (yuvarlak gösteriliyor).
GORSEL_KENAR: Dict[str, Tuple[int, int]] = {
    "foto": (640, 640), "logo": (512, 512), "kapak": (1600, 900), "galeri": (1600, 1600),
}
GORSEL_KALITE = 82
VCARD_FOTO_KENAR = 256
VCARD_FOTO_EN_COK = 40 * 1024

ERISIM_SURE_SN = 2 * 3600
FORM_EN_AZ_SN = 2
FORM_OMRU_SN = 24 * 3600

OG_LOCALE = {"tr": "tr_TR", "en": "en_US", "de": "de_DE", "ru": "ru_RU", "zh": "zh_CN", "hi": "hi_IN", "ar": "ar_AR"}
#: Parola korumalı kartın paylaşım önizlemesi: kişisel bilgi YOK.
KILITLI_METIN: Dict[str, Tuple[str, str]] = {
    "tr": ("Korumalı dijital kartvizit", "Bu kartvizit parola ile korunuyor."),
    "en": ("Protected digital business card", "This business card is password protected."),
    "de": ("Geschützte digitale Visitenkarte", "Diese Visitenkarte ist passwortgeschützt."),
    "ru": ("Защищённая цифровая визитка", "Эта визитка защищена паролем."),
    "zh": ("受保护的电子名片", "此名片受密码保护。"),
    "hi": ("सुरक्षित डिजिटल बिज़नेस कार्ड", "यह बिज़नेस कार्ड पासवर्ड से सुरक्षित है।"),
    "ar": ("بطاقة أعمال رقمية محمية", "بطاقة الأعمال هذه محمية بكلمة مرور."),
}
#: Tanıtım metni yoksa önizleme açıklaması.
KART_YEDEK_ACIKLAMA: Dict[str, str] = {
    "tr": "Dijital kartvizit", "en": "Digital business card", "de": "Digitale Visitenkarte",
    "ru": "Цифровая визитка", "zh": "电子名片", "hi": "डिजिटल बिज़नेस कार्ड", "ar": "بطاقة أعمال رقمية",
}


# ---------------------------------------------------------------------------
# Genel yardımcılar
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


def json_yukle(ham: Any) -> Dict[str, Any]:
    return qr.json_yukle(ham)


def site_adresi() -> str:
    return qr.site_adresi()


def kart_adresi(slug: str) -> str:
    return f"{site_adresi()}/kart/{slug}"


def yorum_adresi(slug: str) -> str:
    return f"{site_adresi()}/yorum/{slug}"


def aydinlatma_adresi(dil: str) -> str:
    """Formun altındaki aydınlatma satırının bağlantısı (kartın dilindeki /gizlilik)."""
    return "/gizlilik" if dil == "tr" else f"/{dil}/gizlilik"


_KONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def metin(ham: Any, alan: str, sinir: int, cok_satir: bool = False, zorunlu: bool = False) -> str:
    """Kontrol karakterleri atılmış, boşlukları sadeleşmiş metin; uzunsa / boşsa hata."""
    if ham is None or isinstance(ham, (dict, list, bool)):
        deger = ""
    else:
        deger = str(ham)
    deger = _KONTROL.sub("", deger.replace("\r\n", "\n").replace("\r", "\n"))
    if cok_satir:
        deger = "\n".join(" ".join(s.split()) for s in deger.split("\n"))
        deger = re.sub(r"\n{3,}", "\n\n", deger)
    else:
        deger = " ".join(deger.split())
    deger = deger.strip()
    if len(deger) > sinir:
        raise KartHatasi("cok_uzun", alan, sinir=sinir)
    if zorunlu and not deger:
        raise KartHatasi("zorunlu", alan)
    return deger


def _bool(ham: Any, varsayilan: bool = False) -> bool:
    if isinstance(ham, bool):
        return ham
    if ham is None:
        return varsayilan
    if isinstance(ham, (int, float)):
        return bool(ham)
    if isinstance(ham, str):
        return ham.strip().lower() in ("1", "true", "evet", "yes", "on")
    return varsayilan


def dil_duzelt(ham: Any) -> str:
    deger = str(ham or "tr").strip().lower()
    if deger not in DILLER:
        raise KartHatasi("dil_gecersiz", "dil")
    return deger


# ---------------------------------------------------------------------------
# Slug ve kod
# ---------------------------------------------------------------------------
_HARF = str.maketrans({
    "ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g", "ü": "u", "Ü": "u", "ö": "o", "Ö": "o",
    "ç": "c", "Ç": "c", "ß": "ss", "æ": "ae", "ø": "o", "å": "a", "ł": "l",
})


def slug_oner(kaynak: Any) -> str:
    """Addan okunaklı slug önerisi (Türkçe harfler sadeleşir); 3 karakterden kısa → ''."""
    m = str(kaynak or "").translate(_HARF)
    m = unicodedata.normalize("NFKD", m).encode("ascii", "ignore").decode("ascii").lower()
    m = re.sub(r"[^a-z0-9]+", "-", m).strip("-")
    m = re.sub(r"-{2,}", "-", m)[:50].strip("-")
    return m if len(m) >= 3 else ""


def slug_duzelt(ham: Any, alan: str = "slug") -> str:
    if not isinstance(ham, str) or not ham.strip():
        raise KartHatasi("zorunlu", alan)
    deger = ham.strip().lower()
    if not SLUG_DESENI.match(deger) or "--" in deger:
        raise KartHatasi("slug_gecersiz", alan)
    if deger in AYRILMIS_SLUGLAR:
        raise KartHatasi("slug_ayrilmis", alan)
    return deger


def kod_uret() -> str:
    """Değişmez QR kodu: 4Q alfabesi, en az bir büyük harf (slug ile çakışmasın)."""
    while True:
        kod = qr.kod_uret()
        if any(c.isupper() for c in kod):
            return kod


def kod_mu(deger: str) -> bool:
    return bool(KOD_DESENI.match(deger or "")) and any(c.isupper() for c in deger)


# ---------------------------------------------------------------------------
# Kart içeriği
# ---------------------------------------------------------------------------
_GEVSEK_TELEFON = re.compile(r"^\+?[0-9][0-9 ()\-.]{3,30}$")
_RENK = re.compile(r"^#[0-9a-fA-F]{6}$")
_SAAT = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
_BAG_ID = re.compile(r"^[a-z0-9]{6}$")


def tel_adresi(numara: str) -> str:
    """Görünen numara → `tel:` adresi (yalnız rakam ve baştaki +)."""
    temiz = re.sub(r"[^\d+]", "", numara or "")
    temiz = ("+" + temiz.replace("+", "")) if temiz.startswith("+") else temiz.replace("+", "")
    if temiz.startswith("00"):
        temiz = "+" + temiz[2:]
    return "tel:" + temiz


def harita_adresi(adres: str) -> str:
    from urllib.parse import quote

    return "https://www.google.com/maps/search/?api=1&query=" + quote(adres, safe=",")


def whatsapp_adresi(numara: str) -> str:
    return "https://wa.me/" + numara.lstrip("+")


def _liste(ham: Any, alan: str, en_cok: int) -> List[Any]:
    if ham in (None, ""):
        return []
    if not isinstance(ham, list):
        raise KartHatasi("liste_gecersiz", alan)
    if len(ham) > en_cok:
        raise KartHatasi("cok_oge", alan, en_cok=en_cok)
    return ham


def _sosyal_adresi(platform: str, ham: str, alan: str) -> str:
    deger = (ham or "").strip()
    if not deger:
        raise KartHatasi("zorunlu", alan)
    taban = PLATFORMLAR.get(platform)
    # "@kullanici" ya da düz kullanıcı adı → platform adresi.
    if taban and re.match(r"^@?[A-Za-z0-9_.\-]{1,60}$", deger) and "." not in deger.lstrip("@").rstrip("."):
        deger = taban + deger.lstrip("@")
    return qr.web_adresi_duzelt(deger, alan)


def baglanti_adresi(ham: Any, alan: str) -> str:
    """Bio link hedefi: http(s), tel:, mailto: (4Q beyaz listesi)."""
    deger = str(ham or "").strip()
    if not deger:
        raise KartHatasi("zorunlu", alan)
    if re.match(r"^(tel|mailto|sms):", deger, re.I):
        if not qr.guvenli_hedef_mi(deger):
            raise KartHatasi("url_gecersiz", alan)
        return deger
    return qr.web_adresi_duzelt(deger, alan)


def _saatler(ham: Any) -> Dict[str, Any]:
    if not isinstance(ham, dict):
        return {"goster": False, "gunler": [], "not": ""}
    goster = _bool(ham.get("goster"))
    gunler_ham = ham.get("gunler") if isinstance(ham.get("gunler"), list) else []
    gelen = {g.get("gun"): g for g in gunler_ham if isinstance(g, dict)}
    gunler: List[Dict[str, Any]] = []
    for gun in GUNLER:
        g = gelen.get(gun) or {}
        acik = _bool(g.get("acik"), False)
        acilis = str(g.get("acilis") or "").strip()
        kapanis = str(g.get("kapanis") or "").strip()
        if acik:
            if not _SAAT.match(acilis) or not _SAAT.match(kapanis):
                raise KartHatasi("saat_gecersiz", f"calisma_saatleri.{gun}")
        gunler.append({"gun": gun, "acik": acik, "acilis": acilis if acik else "", "kapanis": kapanis if acik else ""})
    return {
        "goster": goster,
        "gunler": gunler,
        "not": metin(ham.get("not"), "calisma_saatleri.not", SINIR["saat_notu"]),
    }


def icerik_dogrula(ham: Any) -> Dict[str, Any]:
    """Kart içeriği (JSON) → temiz sözlük. Geçersizse KartHatasi (alan yolu ile)."""
    g = ham if isinstance(ham, dict) else {}
    a: Dict[str, Any] = {
        "ad_soyad": metin(g.get("ad_soyad"), "ad_soyad", SINIR["ad_soyad"], zorunlu=True),
        "unvan": metin(g.get("unvan"), "unvan", SINIR["unvan"]),
        "sirket": metin(g.get("sirket"), "sirket", SINIR["sirket"]),
        "tanitim": metin(g.get("tanitim"), "tanitim", SINIR["tanitim"], cok_satir=True),
        "adres": metin(g.get("adres"), "adres", SINIR["adres"], cok_satir=True),
    }

    telefonlar = []
    for i, t in enumerate(_liste(g.get("telefonlar"), "telefonlar", EN_COK["telefon"])):
        t = t if isinstance(t, dict) else {}
        numara = metin(t.get("numara"), f"telefonlar.{i}.numara", 32)
        if not numara:
            continue
        if not _GEVSEK_TELEFON.match(numara) or not qr.guvenli_hedef_mi(tel_adresi(numara)):
            raise KartHatasi("telefon_gecersiz", f"telefonlar.{i}.numara")
        tip = t.get("tip") if t.get("tip") in TELEFON_TIPLERI else "cep"
        telefonlar.append({"etiket": metin(t.get("etiket"), f"telefonlar.{i}.etiket", SINIR["etiket"]), "numara": numara, "tip": tip})
    a["telefonlar"] = telefonlar

    eposta = metin(g.get("eposta"), "eposta", 254).lower()
    if eposta and not qr.eposta_dogru_mu(eposta):
        raise KartHatasi("eposta_gecersiz", "eposta")
    a["eposta"] = eposta

    webler = []
    for i, w in enumerate(_liste(g.get("webler"), "webler", EN_COK["web"])):
        w = w if isinstance(w, dict) else {}
        url = str(w.get("url") or "").strip()
        if not url:
            continue
        webler.append({
            "etiket": metin(w.get("etiket"), f"webler.{i}.etiket", SINIR["etiket"]),
            "url": qr.web_adresi_duzelt(url, f"webler.{i}.url"),
        })
    a["webler"] = webler

    harita = str(g.get("harita_url") or "").strip()
    a["harita_url"] = qr.web_adresi_duzelt(harita, "harita_url", zorunlu=False) if harita else ""
    a["whatsapp"] = qr.telefon_duzelt(str(g.get("whatsapp") or ""), "whatsapp", zorunlu=False)

    sosyal = []
    for i, s_ in enumerate(_liste(g.get("sosyal"), "sosyal", EN_COK["sosyal"])):
        s_ = s_ if isinstance(s_, dict) else {}
        platform = str(s_.get("platform") or "").strip().lower()
        if platform not in PLATFORMLAR:
            raise KartHatasi("platform_gecersiz", f"sosyal.{i}.platform")
        if not str(s_.get("url") or "").strip():
            continue
        sosyal.append({"platform": platform, "url": _sosyal_adresi(platform, str(s_.get("url")), f"sosyal.{i}.url")})
    a["sosyal"] = sosyal

    baglantilar = []
    gorulen: set = set()
    for i, b in enumerate(_liste(g.get("baglantilar"), "baglantilar", EN_COK["baglanti"])):
        b = b if isinstance(b, dict) else {}
        baslik = metin(b.get("baslik"), f"baglantilar.{i}.baslik", SINIR["baslik"])
        url_ham = str(b.get("url") or "").strip()
        if not baslik and not url_ham:
            continue
        if not baslik:
            raise KartHatasi("zorunlu", f"baglantilar.{i}.baslik")
        kimlik = str(b.get("id") or "")
        if not _BAG_ID.match(kimlik) or kimlik in gorulen:
            kimlik = secrets.token_hex(3)
        gorulen.add(kimlik)
        simge = b.get("simge") if b.get("simge") in SIMGELER else ""
        baglantilar.append({
            "id": kimlik, "baslik": baslik, "url": baglanti_adresi(url_ham, f"baglantilar.{i}.url"), "simge": simge,
        })
    a["baglantilar"] = baglantilar

    hizmetler = []
    for i, h in enumerate(_liste(g.get("hizmetler"), "hizmetler", EN_COK["hizmet"])):
        h = h if isinstance(h, dict) else {}
        baslik = metin(h.get("baslik"), f"hizmetler.{i}.baslik", SINIR["baslik"])
        aciklama = metin(h.get("aciklama"), f"hizmetler.{i}.aciklama", SINIR["hizmet_aciklama"], cok_satir=True)
        if not baslik and not aciklama:
            continue
        if not baslik:
            raise KartHatasi("zorunlu", f"hizmetler.{i}.baslik")
        hizmetler.append({"baslik": baslik, "aciklama": aciklama})
    a["hizmetler"] = hizmetler
    a["calisma_saatleri"] = _saatler(g.get("calisma_saatleri"))
    return a


def tema_dogrula(ham: Any) -> Dict[str, str]:
    g = ham if isinstance(ham, dict) else {}
    sablon = g.get("sablon") or VARSAYILAN_TEMA["sablon"]
    if sablon not in SABLONLAR:
        raise KartHatasi("sablon_gecersiz", "tema.sablon")
    renk = str(g.get("renk") or SABLON_RENKLERI[sablon]).strip()
    if not _RENK.match(renk):
        raise KartHatasi("renk_gecersiz", "tema.renk")
    yazi = g.get("yazi_tipi") or VARSAYILAN_TEMA["yazi_tipi"]
    if yazi not in YAZI_TIPLERI:
        raise KartHatasi("yazi_tipi_gecersiz", "tema.yazi_tipi")
    kose = g.get("kose") or VARSAYILAN_TEMA["kose"]
    if kose not in KOSELER:
        raise KartHatasi("kose_gecersiz", "tema.kose")
    return {"sablon": sablon, "renk": renk.lower(), "yazi_tipi": yazi, "kose": kose}


def renk_duzelt(ham: Any, alan: str = "renk") -> Optional[str]:
    if ham in (None, ""):
        return None
    deger = str(ham).strip()
    if not _RENK.match(deger):
        raise KartHatasi("renk_gecersiz", alan)
    return deger.lower()


def sifre_dogrula(ham: Any) -> Optional[str]:
    """Parola (boş → korumasız). 4–128 karakter."""
    if ham is None:
        return None
    deger = str(ham)
    if not deger.strip():
        return None
    if not 4 <= len(deger) <= 128 or _KONTROL.search(deger):
        raise KartHatasi("sifre_gecersiz", "sifre")
    return deger


# ---------------------------------------------------------------------------
# Yorum sayfası
# ---------------------------------------------------------------------------
def place_id_dogrula(ham: Any) -> str:
    deger = str(ham or "").strip()
    if not deger:
        raise KartHatasi("zorunlu", "place_id")
    if not qr.place_id_gecerli_mi(deger):
        raise KartHatasi("place_id_gecersiz", "place_id")
    return deger


def google_adresi(place_id: str) -> str:
    """"Google'da yorum yaz" adresi — 4Q'daki Google yorum QR türüyle aynı üretici."""
    adres = qr.google_yorum_adresi(place_id)
    if not qr.guvenli_hedef_mi(adres):
        raise KartHatasi("place_id_gecersiz", "place_id")
    return adres


# ---------------------------------------------------------------------------
# Görsel işleme
# ---------------------------------------------------------------------------
def gorsel_hazirla(bayt: bytes, tur: str) -> Tuple[bytes, int, int]:
    """Yüklenen JPEG/PNG/WebP → küçültülmüş WebP (bayt, genişlik, yükseklik)."""
    if tur not in GORSEL_KENAR:
        raise KartHatasi("gorsel_turu_gecersiz", "tur")
    if not bayt:
        raise KartHatasi("dosya_bos", "dosya")
    if len(bayt) > GORSEL_EN_COK_BAYT:
        raise KartHatasi("gorsel_buyuk", "dosya", en_cok_mb=GORSEL_EN_COK_BAYT // (1024 * 1024), durum=413)
    from PIL import Image, ImageOps

    try:
        with Image.open(io.BytesIO(bayt)) as ham:
            if ham.format not in ("JPEG", "PNG", "WEBP"):
                raise KartHatasi("gorsel_bicimi", "dosya")
            if getattr(ham, "is_animated", False) and getattr(ham, "n_frames", 1) > 1:
                raise KartHatasi("gorsel_bicimi", "dosya")
            gen, yuk = ham.size
            if gen < 16 or yuk < 16 or gen * yuk > GORSEL_EN_COK_PIKSEL:
                raise KartHatasi("gorsel_boyutu", "dosya")
            ham.load()
            gorsel = ImageOps.exif_transpose(ham)
            saydam = gorsel.mode in ("RGBA", "LA", "PA") or (gorsel.mode == "P" and "transparency" in gorsel.info)
            gorsel = gorsel.convert("RGBA" if saydam else "RGB")
    except KartHatasi:
        raise
    except Exception as exc:  # noqa: BLE001 - bozuk / tanınmayan dosya
        raise KartHatasi("gorsel_bicimi", "dosya") from exc
    hedef = GORSEL_KENAR[tur]
    if tur == "foto":
        kenar = min(hedef[0], gorsel.width, gorsel.height)
        gorsel = ImageOps.fit(gorsel, (kenar, kenar), Image.LANCZOS)
    else:
        gorsel.thumbnail(hedef, Image.LANCZOS)
    cikti = io.BytesIO()
    gorsel.save(cikti, format="WEBP", quality=GORSEL_KALITE, method=4)
    return cikti.getvalue(), gorsel.width, gorsel.height


def _rgb_duz(gorsel):
    from PIL import Image

    if gorsel.mode in ("RGBA", "LA", "P"):
        gorsel = gorsel.convert("RGBA")
        zemin = Image.new("RGB", gorsel.size, (255, 255, 255))
        zemin.paste(gorsel, mask=gorsel.split()[-1])
        return zemin
    return gorsel.convert("RGB")


def jpeg_uret(webp: bytes, kenar: int, kalite: int = 85, en_cok: Optional[int] = None) -> bytes:
    """WebP → JPEG (paylaşım önizlemesi / vCard). `en_cok` aşılırsa kalite düşürülür."""
    from PIL import Image

    with Image.open(io.BytesIO(webp)) as ham:
        gorsel = _rgb_duz(ham)
    gorsel.thumbnail((kenar, kenar), Image.LANCZOS)
    k = kalite
    while True:
        cikti = io.BytesIO()
        gorsel.save(cikti, format="JPEG", quality=k, optimize=True, progressive=False)
        veri = cikti.getvalue()
        if en_cok is None or len(veri) <= en_cok or k <= 35:
            return veri
        k -= 10


def png_b64(webp: bytes, kenar: int = 512) -> str:
    """WebP → PNG base64 (QR'ın ortasındaki logo için; 4Q `svg_ciz`/`png_ciz` PNG bekliyor)."""
    from PIL import Image

    with Image.open(io.BytesIO(webp)) as ham:
        gorsel = ham.convert("RGBA")
    gorsel.thumbnail((kenar, kenar), Image.LANCZOS)
    cikti = io.BytesIO()
    gorsel.save(cikti, format="PNG", optimize=True)
    return base64.b64encode(cikti.getvalue()).decode("ascii")


def gorsel_adresi(anahtar: str, uzanti: str = "webp") -> str:
    return f"/api/v1/kart/gorsel/{anahtar}.{uzanti}"


# ---------------------------------------------------------------------------
# İmzalı jetonlar (parola erişimi, form)
# ---------------------------------------------------------------------------
_YEDEK_ANAHTAR: Optional[bytes] = None


def _imza_anahtari() -> bytes:
    gizli = os.environ.get("JWT_SECRET_KEY") or ""
    if not gizli:
        global _YEDEK_ANAHTAR
        if _YEDEK_ANAHTAR is None:
            _YEDEK_ANAHTAR = secrets.token_bytes(32)
        return _YEDEK_ANAHTAR
    return hashlib.sha256(("kartvizit:" + gizli).encode()).digest()


def _imza(metin_: str) -> str:
    return hmac.new(_imza_anahtari(), metin_.encode(), hashlib.sha256).hexdigest()[:32]


def _erisim_imzasi(kart_id: int, son: int, sifre_ozet: Optional[str]) -> str:
    # Parola özetinin başı imzaya giriyor: parola değişince eski jetonlar geçersiz.
    return _imza("erisim.%d.%d.%s" % (int(kart_id), int(son), (sifre_ozet or "")[:16]))


def erisim_jetonu_uret(kart_id: int, sifre_ozet: Optional[str], an: Optional[float] = None) -> str:
    son = int(an if an is not None else time.time()) + ERISIM_SURE_SN
    return f"{son}.{_erisim_imzasi(kart_id, son, sifre_ozet)}"


def erisim_jetonu_gecerli_mi(jeton: Any, kart_id: int, sifre_ozet: Optional[str], an: Optional[float] = None) -> bool:
    parca = str(jeton or "").split(".")
    if len(parca) != 2 or not parca[0].isdigit():
        return False
    son = int(parca[0])
    if son < int(an if an is not None else time.time()):
        return False
    return hmac.compare_digest(parca[1], _erisim_imzasi(kart_id, son, sifre_ozet))


def _form_imzasi(sahip_tur: str, sahip_id: int, ms: int) -> str:
    return _imza("form.%s.%d.%d" % (sahip_tur, int(sahip_id), int(ms)))


def form_jetonu_uret(sahip_tur: str, sahip_id: int, an: Optional[float] = None) -> str:
    ms = int((an if an is not None else time.time()) * 1000)
    return f"{ms}.{_form_imzasi(sahip_tur, sahip_id, ms)}"


def form_jetonu_dogrula(jeton: Any, sahip_tur: str, sahip_id: int, an: Optional[float] = None) -> None:
    parca = str(jeton or "").split(".")
    if len(parca) != 2 or not parca[0].isdigit():
        raise KartHatasi("form_jetonu", None)
    ms = int(parca[0])
    if not hmac.compare_digest(parca[1], _form_imzasi(sahip_tur, sahip_id, ms)):
        raise KartHatasi("form_jetonu", None)
    gecen = (an if an is not None else time.time()) - ms / 1000.0
    if gecen < FORM_EN_AZ_SN:
        raise KartHatasi("cok_hizli", None, durum=429)
    if gecen > FORM_OMRU_SN:
        raise KartHatasi("form_suresi", None)


def mesaj_dogrula(govde: Dict[str, Any], sahip_tur: str) -> Dict[str, str]:
    """Kart: ad + (e-posta ya da telefon) zorunlu, mesaj isteğe bağlı.
    Yorum (özel geri bildirim): mesaj zorunlu, ad/iletişim isteğe bağlı."""
    kart = sahip_tur == "kart"
    ad = metin(govde.get("ad"), "ad", 120, zorunlu=kart)
    eposta = metin(govde.get("eposta"), "eposta", 254).lower()
    if eposta and not qr.eposta_dogru_mu(eposta):
        raise KartHatasi("eposta_gecersiz", "eposta")
    telefon = metin(govde.get("telefon"), "telefon", 40)
    if telefon and not _GEVSEK_TELEFON.match(telefon):
        raise KartHatasi("telefon_gecersiz", "telefon")
    if kart and not (eposta or telefon):
        raise KartHatasi("iletisim_gerekli", "eposta")
    mesaj_ = metin(govde.get("mesaj"), "mesaj", 2000, cok_satir=True, zorunlu=not kart)
    return {"ad": ad, "eposta": eposta, "telefon": telefon, "mesaj": mesaj_}


# ---------------------------------------------------------------------------
# vCard ve paylaşım önizlemesi
# ---------------------------------------------------------------------------
def vcard_alanlari(kart: Any, icerik: Dict[str, Any], foto_jpeg: Optional[bytes] = None) -> Dict[str, Any]:
    """Kart → 4Q `vcard_uret` girdisi (ek telefon/web/sosyal/fotoğraf alanlarıyla)."""
    ad_soyad = icerik.get("ad_soyad") or kart.ad_soyad or ""
    parcalar = ad_soyad.split()
    ad, soyad = (" ".join(parcalar[:-1]), parcalar[-1]) if len(parcalar) > 1 else (ad_soyad, "")
    a: Dict[str, Any] = {
        "ad": ad,
        "soyad": soyad,
        "kurum": icerik.get("sirket") or "",
        "unvan": icerik.get("unvan") or "",
        "eposta": icerik.get("eposta") or "",
        "web": kart_adresi(kart.slug),
        "adres_sokak": " ".join((icerik.get("adres") or "").split()),
        "not": icerik.get("tanitim") or "",
        "telefonlar": [
            {"tip": _VCARD_TEL.get(t.get("tip"), "VOICE"), "numara": t.get("numara")}
            for t in icerik.get("telefonlar") or []
        ],
        "ek_webler": [w["url"] for w in icerik.get("webler") or [] if w.get("url")],
        "sosyal": [{"platform": s_["platform"], "url": s_["url"]} for s_ in icerik.get("sosyal") or []],
    }
    if icerik.get("whatsapp"):
        a["telefonlar"].append({"tip": "CELL", "numara": icerik["whatsapp"]})
    if foto_jpeg:
        a["foto_jpeg_b64"] = base64.b64encode(foto_jpeg).decode("ascii")
    return a


def vcard_dosya_adi(slug: str) -> str:
    return f"{slug}.vcf"


def ozet_basligi(icerik: Dict[str, Any], kart: Any) -> str:
    ad = icerik.get("ad_soyad") or kart.ad_soyad
    ek = " · ".join(x for x in (icerik.get("unvan"), icerik.get("sirket")) if x)
    return f"{ad} — {ek}" if ek else ad


def ozet_aciklamasi(icerik: Dict[str, Any], dil: str) -> str:
    tanitim = " ".join((icerik.get("tanitim") or "").split())
    if tanitim:
        return tanitim if len(tanitim) <= 200 else tanitim[:199].rstrip() + "…"
    ek = " · ".join(x for x in (icerik.get("unvan"), icerik.get("sirket")) if x)
    return ek or KART_YEDEK_ACIKLAMA.get(dil, KART_YEDEK_ACIKLAMA["tr"])


# ---------------------------------------------------------------------------
# Analitik yardımcıları (4Q'nun bot / cihaz kuralı)
# ---------------------------------------------------------------------------
ONIZLEME_BASLIKLARI = ("purpose", "sec-purpose", "x-purpose", "x-moz")


def istek_bot_mu(request: Any) -> bool:
    if request.method == "HEAD":
        return True
    basliklar = {ad: request.headers.get(ad, "") for ad in ONIZLEME_BASLIKLARI}
    return qr.bot_mu(request.headers.get("user-agent") or "", basliklar)


def olay_satiri(request: Any, sahip_tur: str, sahip_id: int, olay: str, hedef: Optional[str] = None,
                kanal: Optional[str] = None) -> Dict[str, Any]:
    """Yazılacak olay (ham IP/UA yok): gün + tuzla IP özeti, cihaz sınıfı, bot işareti."""
    from utils.istemci_ip import ip_ozeti, istemci_ip

    an = simdi()
    gun = an.date().isoformat()
    ip = istemci_ip(request)
    return {
        "sahip_tur": sahip_tur,
        "sahip_id": int(sahip_id),
        "olay": olay,
        "hedef": (hedef or None) and str(hedef)[:40],
        "kanal": kanal,
        "zaman": an,
        "gun": gun,
        # Gün tuzun parçası: aynı günün tekil sayımı için yeter, günler arası izleme yok.
        "ip_ozeti": ip_ozeti(f"kart|{gun}|{ip}"),
        "cihaz": qr.cihaz_sinifi(request.headers.get("user-agent")),
        "bot": istek_bot_mu(request),
    }


def hiz_anahtari(request: Any, *ek: Any) -> str:
    from utils.istemci_ip import ip_ozeti, istemci_ip

    return "|".join([ip_ozeti("kart-hiz|" + istemci_ip(request)), *(str(x) for x in ek)])


def hedef_gecerli_mi(hedef: Any) -> bool:
    """Tıklama olayının hedef anahtarı: `l:<id>`, `tel:<n>`, `web:<n>`, `s:<platform>`, `wa`, `eposta`, `harita`."""
    if not isinstance(hedef, str):
        return False
    return bool(re.match(r"^(l:[a-z0-9]{6}|tel:[0-9]{1,2}|web:[0-9]{1,2}|s:[a-z]{1,20}|wa|eposta|harita|galeri|qr)$", hedef))


def json_dok(d: Any) -> str:
    return json.dumps(d, ensure_ascii=False)


def eski_slug_bitisi() -> datetime:
    return simdi() + timedelta(days=ESKI_SLUG_GUN)
