"""Faz 2F — Otomatik destek kuralları.

Talep açıldığında (panel, web, e-posta — hepsi `services/destek_talep.py`
üzerinden) etkin kurallar `sira`ya göre denenir. Eşleşen kuralın eylemleri
talebe uygulanır; "durdur" eylemi olan kural eşleşirse sonrakiler denenmez.

Koşullar (`kosullar` JSON listesi, `eslesme` = hepsi | herhangi)
------------------------------------------------------------------
    alan               işleçler
    konu, metin,       icerir, icermez, esittir   (büyük-küçük ve Türkçe harf
    konu_veya_metin                               duyarsız: İ/ı/I/i, ş/s, ğ/g …)
    gonderen           esittir (tam adres), alan_adi (@ sonrası), icerir
    kanal              esittir, esit_degil   (panel | eposta | web)
    oncelik            esittir, esit_degil   (acil | yuksek | normal | dusuk)
    hizmet             esittir, esit_degil   (talebin kategorisi)
    paket              esittir, esit_degil   (müşterinin paketi, `services/moduller`)

Boş koşul listesi "her talep" demektir (hepsi → doğru).

Eylemler (`eylemler` JSON listesi)
----------------------------------
    oncelik      değer: acil | yuksek | normal | dusuk
    ata          değer: ekip üyesinin e-postası (`staff`, aktif)
    hizmet       değer: talep kategorisi (routers/talep_mesajlari.HIZMETLER)
    etiket       değer: serbest etiket (küçük harf, 40 karakter)
    hazir_cevap  değer: hazır cevap id — müşteriye otomatik yanıt
    durdur       sonraki kurallar çalışmasın

Güvenlik: otomatik hazır cevap TALEP BAŞINA EN ÇOK BİR KEZ (koşullu UPDATE)
ve tanınmayan e-posta göndericisine HİÇ gönderilmez (sahte "From" ile bize
yazan birinin kurbanına bizim adımıza e-posta yağdırmasın).
"""

import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

ONCELIKLER = ("acil", "yuksek", "normal", "dusuk")
KANALLAR = ("panel", "eposta", "web")
METIN_ISLECLERI = ("icerir", "icermez", "esittir")
ESITLIK_ISLECLERI = ("esittir", "esit_degil")
KOSUL_ALANLARI: Dict[str, Sequence[str]] = {
    "konu": METIN_ISLECLERI,
    "metin": METIN_ISLECLERI,
    "konu_veya_metin": METIN_ISLECLERI,
    "gonderen": ("esittir", "alan_adi", "icerir"),
    "kanal": ESITLIK_ISLECLERI,
    "oncelik": ESITLIK_ISLECLERI,
    "hizmet": ESITLIK_ISLECLERI,
    "paket": ESITLIK_ISLECLERI,
}
EYLEM_TURLERI = ("oncelik", "ata", "hizmet", "etiket", "hazir_cevap", "durdur")
EN_COK_KOSUL = 20
EN_COK_EYLEM = 10
EN_COK_KURAL = 200
DEGER_SINIRI = 200


class KuralHatasi(Exception):
    def __init__(self, kod: str, **ek: Any):
        super().__init__(kod)
        self.kod = kod
        self.ek = ek


# ---------------------------------------------------------------------------
# Metin katlama — Türkçe harf ve büyük/küçük duyarsız
# ---------------------------------------------------------------------------
_TR_TABLO = str.maketrans({"İ": "i", "I": "i", "ı": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
                           "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c"})


def katla(metin: Any) -> str:
    """"İADE Talebi" → "iade talebi"; "ÖDEME" → "odeme"; "ıi" → "ii".

    Önce Türkçe harfler elle eşleniyor (Python'un `lower()`ı "İ"yi "i̇"
    yapıyor, "I"yı "ı" değil "i" yapıyor — ikisi de eşleşmeyi bozar), sonra
    kalan aksanlar (é, â …) NFKD ile atılıyor.
    """
    s = str(metin or "").translate(_TR_TABLO)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.casefold()).strip()


def tr_kucuk(metin: Any) -> str:
    """Türkçe küçük harf: "İşİ" → "işi" (Python'un lower()ı "İ"yi "i̇" yapar)."""
    return str(metin or "").replace("İ", "i").replace("I", "ı").lower()


def kanal_bul(kaynak: Optional[str]) -> str:
    k = (kaynak or "").strip().lower()
    if k in ("site", "web", "form"):
        return "web"
    if k in ("eposta", "email", "e-posta"):
        return "eposta"
    return k or "panel"


# ---------------------------------------------------------------------------
# Doğrulama
# ---------------------------------------------------------------------------
def _deger(ham: Any) -> str:
    return str(ham if ham is not None else "").strip()[:DEGER_SINIRI]


def kosullari_dogrula(ham: Any) -> List[Dict[str, str]]:
    if ham is None:
        return []
    if not isinstance(ham, list) or len(ham) > EN_COK_KOSUL:
        raise KuralHatasi("gecersiz_kosul")
    temiz: List[Dict[str, str]] = []
    for k in ham:
        if not isinstance(k, dict):
            raise KuralHatasi("gecersiz_kosul")
        alan = str(k.get("alan") or "").strip()
        islec = str(k.get("islec") or "").strip()
        deger = _deger(k.get("deger"))
        if alan not in KOSUL_ALANLARI or islec not in KOSUL_ALANLARI[alan]:
            raise KuralHatasi("gecersiz_kosul", alan=alan)
        if not deger:
            raise KuralHatasi("kosul_degeri_bos", alan=alan)
        if alan == "kanal" and deger not in KANALLAR:
            raise KuralHatasi("gecersiz_kosul", alan=alan)
        if alan == "oncelik" and deger not in ONCELIKLER:
            raise KuralHatasi("gecersiz_kosul", alan=alan)
        temiz.append({"alan": alan, "islec": islec, "deger": deger})
    return temiz


async def eylemleri_dogrula(db: AsyncSession, ham: Any) -> List[Dict[str, Any]]:
    from models.destek_sla import HazirCevaplar
    from routers.personel import atanabilir_mi
    from routers.talep_mesajlari import HIZMETLER

    if not isinstance(ham, list) or not ham or len(ham) > EN_COK_EYLEM:
        raise KuralHatasi("eylem_gerekli")
    temiz: List[Dict[str, Any]] = []
    for e in ham:
        if not isinstance(e, dict):
            raise KuralHatasi("gecersiz_eylem")
        tur = str(e.get("tur") or "").strip()
        if tur not in EYLEM_TURLERI:
            raise KuralHatasi("gecersiz_eylem", tur=tur)
        if tur == "durdur":
            temiz.append({"tur": "durdur"})
            continue
        deger = _deger(e.get("deger"))
        if tur == "oncelik" and deger not in ONCELIKLER:
            raise KuralHatasi("gecersiz_eylem", tur=tur)
        elif tur == "ata":
            deger = deger.lower()
            if not await atanabilir_mi(db, deger):
                raise KuralHatasi("ekipte_yok", tur=tur)
        elif tur == "hizmet" and deger not in HIZMETLER:
            raise KuralHatasi("gecersiz_eylem", tur=tur)
        elif tur == "etiket":
            deger = re.sub(r"[,\s]+", "-", tr_kucuk(deger)).strip("-")[:40]
            if not deger:
                raise KuralHatasi("gecersiz_eylem", tur=tur)
        elif tur == "hazir_cevap":
            try:
                hc_id = int(deger)
            except ValueError:
                raise KuralHatasi("hazir_cevap_yok", tur=tur)
            var = (await db.execute(select(HazirCevaplar.id).where(HazirCevaplar.id == hc_id))).first()
            if var is None:
                raise KuralHatasi("hazir_cevap_yok", tur=tur)
            deger = hc_id  # type: ignore[assignment]
        temiz.append({"tur": tur, "deger": deger})
    return temiz


def eslesme_dogrula(ham: Any) -> str:
    deger = str(ham or "hepsi").strip()
    if deger not in ("hepsi", "herhangi"):
        raise KuralHatasi("gecersiz_eslesme")
    return deger


# ---------------------------------------------------------------------------
# Eşleştirme — saf fonksiyonlar
# ---------------------------------------------------------------------------
@dataclass
class TalepBaglami:
    konu: str = ""
    metin: str = ""
    gonderen: str = ""
    kanal: str = "panel"
    oncelik: str = "normal"
    hizmet: str = "genel"
    paket: Optional[str] = None
    #: Katlanmış metinler (bir kez hesaplansın)
    _k: Dict[str, str] = field(default_factory=dict)

    def katli(self, alan: str) -> str:
        if alan not in self._k:
            self._k[alan] = katla(getattr(self, alan))
        return self._k[alan]


def _metin_islec(islec: str, kaynak: str, deger: str) -> bool:
    d = katla(deger)
    if islec == "icerir":
        return d in kaynak
    if islec == "icermez":
        return d not in kaynak
    if islec == "esittir":
        return kaynak == d
    return False


def kosul_uyuyor(kosul: Dict[str, Any], b: TalepBaglami) -> bool:
    alan, islec, deger = kosul.get("alan"), kosul.get("islec"), str(kosul.get("deger") or "")
    if alan in ("konu", "metin"):
        return _metin_islec(islec, b.katli(alan), deger)  # type: ignore[arg-type]
    if alan == "konu_veya_metin":
        if islec == "icermez":
            return _metin_islec("icermez", b.katli("konu"), deger) and _metin_islec("icermez", b.katli("metin"), deger)
        return _metin_islec(islec, b.katli("konu"), deger) or _metin_islec(islec, b.katli("metin"), deger)  # type: ignore[arg-type]
    if alan == "gonderen":
        adres = (b.gonderen or "").strip().lower()
        d = deger.strip().lower()
        if islec == "esittir":
            return bool(adres) and adres == d
        if islec == "alan_adi":
            alan_adi = adres.rsplit("@", 1)[-1] if "@" in adres else ""
            d = d.lstrip("@")
            # "ornek.com" alt alan adlarını da kapsasın: destek.ornek.com
            return bool(alan_adi) and (alan_adi == d or alan_adi.endswith("." + d))
        if islec == "icerir":
            return bool(d) and d in adres
        return False
    if alan in ("kanal", "oncelik", "hizmet", "paket"):
        mevcut = str(getattr(b, alan) or "").strip().lower()
        esit = mevcut == deger.strip().lower()
        return esit if islec == "esittir" else not esit
    return False


def kural_uyuyor(kosullar: List[Dict[str, Any]], eslesme: str, b: TalepBaglami) -> bool:
    if not kosullar:
        return True
    sonuclar = (kosul_uyuyor(k, b) for k in kosullar)
    return any(sonuclar) if eslesme == "herhangi" else all(sonuclar)


def _json(metin: Any) -> List[Dict[str, Any]]:
    try:
        deger = json.loads(metin or "[]")
        return deger if isinstance(deger, list) else []
    except (TypeError, ValueError):
        return []


def kural_sozlugu(k: Any) -> Dict[str, Any]:
    return {
        "id": k.id,
        "ad": k.ad,
        "aktif": bool(k.aktif),
        "sira": int(k.sira or 0),
        "eslesme": k.eslesme or "hepsi",
        "kosullar": _json(k.kosullar),
        "eylemler": _json(k.eylemler),
    }


def eslesenleri_bul(kurallar: Sequence[Dict[str, Any]], b: TalepBaglami) -> List[Dict[str, Any]]:
    """Sırayla eşleşen etkin kurallar; "durdur" içeren eşleşmede kesilir."""
    sonuc: List[Dict[str, Any]] = []
    for k in sorted(kurallar, key=lambda x: (int(x.get("sira") or 0), int(x.get("id") or 0))):
        if not k.get("aktif"):
            continue
        if not kural_uyuyor(k.get("kosullar") or [], k.get("eslesme") or "hepsi", b):
            continue
        sonuc.append(k)
        if any(e.get("tur") == "durdur" for e in k.get("eylemler") or []):
            break
    return sonuc


def paket_gerekli_mi(kurallar: Sequence[Dict[str, Any]]) -> bool:
    return any(c.get("alan") == "paket" for k in kurallar if k.get("aktif") for c in k.get("kosullar") or [])


async def kurallari_oku(db: AsyncSession) -> List[Dict[str, Any]]:
    from models.destek_eposta import DestekKurallari

    satirlar = (
        await db.execute(select(DestekKurallari).order_by(DestekKurallari.sira.asc(), DestekKurallari.id.asc()))
    ).scalars().all()
    return [kural_sozlugu(k) for k in satirlar]


async def baglam_kur(db: AsyncSession, kurallar: Sequence[Dict[str, Any]], **alanlar: Any) -> TalepBaglami:
    b = TalepBaglami(
        konu=str(alanlar.get("konu") or ""),
        metin=str(alanlar.get("metin") or ""),
        gonderen=str(alanlar.get("gonderen") or "").strip().lower(),
        kanal=kanal_bul(alanlar.get("kanal")),
        oncelik=str(alanlar.get("oncelik") or "normal").strip().lower() or "normal",
        hizmet=str(alanlar.get("hizmet") or "genel").strip() or "genel",
        paket=alanlar.get("paket"),
    )
    if b.paket is None and b.gonderen and paket_gerekli_mi(kurallar):
        try:
            from services.moduller import musteri_paketi

            b.paket = await musteri_paketi(db, b.gonderen)
        except Exception:  # noqa: BLE001 - paket okunamazsa koşul eşleşmez
            logger.warning("Kural için müşteri paketi okunamadı", exc_info=True)
    return b


# ---------------------------------------------------------------------------
# Talebe uygulama
# ---------------------------------------------------------------------------
@dataclass
class UygulamaSonucu:
    uygulanan: List[Dict[str, Any]] = field(default_factory=list)
    #: Gönderilecek otomatik hazır cevap (ilk eşleşen kuralınki); yoksa None.
    hazir_cevap_id: Optional[int] = None
    degisenler: Dict[str, Any] = field(default_factory=dict)


async def talebe_uygula(db: AsyncSession, talep: Any, *, kanal: str) -> UygulamaSonucu:
    """Kuralları talebe uygular ve commit eder. Hata fırlatmaz (talep düşmesin)."""
    from routers.personel import atanabilir_mi
    from services import denetim

    sonuc = UygulamaSonucu()
    try:
        kurallar = await kurallari_oku(db)
        if not any(k["aktif"] for k in kurallar):
            return sonuc
        b = await baglam_kur(
            db, kurallar, konu=talep.subject, metin=talep.message, gonderen=talep.client_email,
            kanal=kanal, oncelik=talep.priority, hizmet=talep.hizmet,
        )
        eslesenler = eslesenleri_bul(kurallar, b)
        if not eslesenler:
            return sonuc
        once = {"priority": talep.priority, "atanan": talep.atanan, "hizmet": talep.hizmet, "etiketler": talep.etiketler}
        etiketler = [e for e in (talep.etiketler or "").split(",") if e]
        for k in eslesenler:
            yapilan: List[str] = []
            for e in k["eylemler"]:
                tur, deger = e.get("tur"), e.get("deger")
                if tur == "oncelik" and deger in ONCELIKLER:
                    talep.priority = deger
                    yapilan.append(f"oncelik={deger}")
                elif tur == "ata" and deger:
                    # Kural kaydedildiğinden beri kişi ekipten çıkmış olabilir.
                    if await atanabilir_mi(db, str(deger)):
                        talep.atanan = str(deger).lower()
                        yapilan.append(f"ata={talep.atanan}")
                elif tur == "hizmet" and deger:
                    talep.hizmet = str(deger)
                    yapilan.append(f"hizmet={deger}")
                elif tur == "etiket" and deger:
                    if deger not in etiketler:
                        etiketler.append(str(deger))
                    yapilan.append(f"etiket={deger}")
                elif tur == "hazir_cevap" and deger:
                    if sonuc.hazir_cevap_id is None:
                        sonuc.hazir_cevap_id = int(deger)
                    yapilan.append(f"hazir_cevap={deger}")
                elif tur == "durdur":
                    yapilan.append("durdur")
            sonuc.uygulanan.append({"id": k["id"], "ad": k["ad"], "eylemler": yapilan})
        talep.etiketler = ",".join(etiketler)[:500] or None
        sonra = {"priority": talep.priority, "atanan": talep.atanan, "hizmet": talep.hizmet, "etiketler": talep.etiketler}
        sonuc.degisenler = {a: sonra[a] for a in sonra if sonra[a] != once[a]}
        await db.commit()
        # Talep geçmişi: hangi kural ne yaptı — denetim kaydına "sistem" olarak.
        ozet = "Otomatik kural: " + "; ".join(f"{u['ad']} ({', '.join(u['eylemler'])})" for u in sonuc.uygulanan)
        await denetim.denetim_yaz(
            db, aktor={"eposta": None, "rol": "sistem"}, islem="guncelle", tablo="support_tickets",
            kayit_id=talep.id, ozet=ozet, once=once, sonra=sonra, commit=True,
        )
    except Exception:  # noqa: BLE001 - kural hatası talebi düşürmesin
        logger.exception("Destek kuralları uygulanamadı: talep %s", getattr(talep, "id", None))
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
    return sonuc
