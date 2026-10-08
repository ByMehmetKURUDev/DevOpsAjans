"""Faz 6O — Hedefler ve OKR: kurallar ve yardımcılar (veritabanına dokunmayan her şey).

Router `routers/okr.py`, veritabanı işleri `services/okr_kayit.py`, otomatik KR kaynakları `services/okr_kaynak.py`.
Burada:

* İlerleme hesabı TEK yerde (`kr_ilerleme`, `hedef_ilerleme`, `beklenen_ilerleme`, `ilerleme_durumu`); birim testli.
  KR = (mevcut − başlangıç) / (hedef − başlangıç), 0–1 aralığına kırpılır. "Azalt" yönünde hedef başlangıçtan küçüktür
  ve aynı formül doğru işareti verir ((75 − 100) / (50 − 100) = 0,5). Hedef = başlangıç ise bölme yok: hedefe
  ulaşıldıysa 1, değilse 0. Evet/hayır 0/1; kilometre taşı = tamamlanan / toplam (liste boşsa 0). Hedef (objective)
  ilerlemesi = KR'lerin ağırlıklı ortalaması (KR yoksa ya da ağırlık toplamı 0 ise `None` — "henüz ölçülmüyor").
* Beklenen ilerleme: dönemde geçen gün oranı (başlangıç günü 1/n; bitişten sonra 1). Renk: ilerleme beklenenin en çok
  10 puan gerisindeyse `yolunda`, 25 puana kadar `riskli`, daha gerisi `geride`; 1'e ulaşan `tamam`.
* Dönem tarihleri (çeyrek / yıl / özel), hizalama döngüsü denetimi, değer ayrıştırma (para KURUŞ — ön muhasebeyle
  aynı `kurus_coz`), kilometre taşı listesi, CSV, PDF (7 dil; `services.pdf_yazi.Paragraf`) ve "AI ile KR öner"
  mesajları + yanıt ayrıştırma.
"""

import json
import math
import re
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from services import muhasebe as m

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------
MODUL = "hedefler"
IZIN = "hedefler"
#: Yalnız okuma (dönem listesi, ağaç, ayrıntı, rapor); yazamaz.
IZIN_OKUR = "hedefler_okur"
AJANS_KAPSAMI = "@ajans"
SAAT_DILIMI = "Europe/Istanbul"
UTC = timezone.utc

DONEM_TURLERI: Tuple[str, ...] = ("ceyrek", "yil", "ozel")
DONEM_DURUMLARI: Tuple[str, ...] = ("acik", "kapandi")
HEDEF_DURUMLARI: Tuple[str, ...] = ("taslak", "etkin", "kapandi")
#: ekip = hesabın/ajansın ekibi görür; ozel = yalnız sahibi ve oluşturan ("yalnız ben").
GORUNURLUKLER: Tuple[str, ...] = ("ekip", "ozel")
KR_TURLERI: Tuple[str, ...] = ("sayi", "yuzde", "para", "evet_hayir", "kilometre")
YONLER: Tuple[str, ...] = ("artir", "azalt")
GUVENLER: Tuple[str, ...] = ("yolunda", "riskli", "tehlikede")
CHECKIN_TURLERI: Tuple[str, ...] = ("elle", "otomatik", "odak")
PARA_BIRIMLERI: Tuple[str, ...] = m.PARA_BIRIMLERI
ILERLEME_DURUMLARI: Tuple[str, ...] = ("tamam", "yolunda", "riskli", "geride")

EN_COK_KR = 10
EN_COK_KILOMETRE = 30
EN_COK_AGIRLIK = 10
EN_COK_DEGER = 1e12
VARSAYILAN_HEDEF_SINIRI = 30
#: Haftalık hatırlatma: bu kadar gündür check-in almamış etkin elle KR (KR başına bu aralıkta en çok bir bildirim).
HATIRLATMA_GUN = 7
#: Odak sayacı (Pomodoro) oturumu: çalışma / mola dakikası (arayüz), kaydedilen süre sınırı.
ODAK_DK = 25
MOLA_DK = 5
EN_COK_ODAK_DK = 240
#: Otomatik kaynaklar zamanlı işte bu kadar sıklıkla yenilenir (panel "şimdi yenile" her an).
YENILEME_ARALIGI = timedelta(hours=1)
AI_GUNLUK_BUTCE = 200
AI_KAPSAM = "okr"
EN_COK_ONERI = 5


class OkrHatasi(m.TemelHata):
    """Doğrulama/iş kuralı hatası: `{"kod", "alan"?, ...}` gövdesiyle döner."""


TemelHata = m.TemelHata


def simdi() -> datetime:
    """Testler bu fonksiyonu sabit bir ana çeviriyor (bütün zaman hesapları buradan)."""
    return datetime.now(UTC)


def tz():
    return m.tz()


def bugun() -> date:
    """İstanbul'un bugünü."""
    return simdi().astimezone(tz()).date()


def iso(an: Optional[datetime]) -> Optional[str]:
    return m.iso(an)


def gun_iso(g: Optional[date]) -> Optional[str]:
    return g.isoformat() if g else None


def kapsam_anahtari(hesap: Optional[str]) -> str:
    return hesap or AJANS_KAPSAMI


def json_yukle(ham: Any, varsayilan: Any = None) -> Any:
    return m.json_yukle(ham, varsayilan)


def json_yaz(deger: Any) -> str:
    return m.json_yaz(deger)


def utc(an: Optional[datetime]) -> Optional[datetime]:
    if an is None:
        return None
    return an.replace(tzinfo=UTC) if an.tzinfo is None else an.astimezone(UTC)


def gun_baslangici(g: date) -> datetime:
    """İstanbul gününün başlangıcı (UTC)."""
    return datetime(g.year, g.month, g.day, tzinfo=tz()).astimezone(UTC)


def aralik_anlari(bas: date, bit: date) -> Tuple[datetime, datetime]:
    """[bas 00:00, bit+1 00:00) İstanbul → UTC (bitiş HARİÇ)."""
    return gun_baslangici(bas), gun_baslangici(bit + timedelta(days=1))


# ---------------------------------------------------------------------------
# Doğrulayıcılar (ön muhasebenin yardımcıları; hata türü OkrHatasi)
# ---------------------------------------------------------------------------
def _cevir(fonk, *a, **k):
    try:
        return fonk(*a, **k)
    except m.TemelHata as h:
        if isinstance(h, OkrHatasi):
            raise
        raise OkrHatasi(h.kod, h.alan, h.durum, **h.ek)


def metin(ham: Any, alan: str, sinir: int, zorunlu: bool = False, cok_satir: bool = False) -> str:
    return _cevir(m.metin, ham, alan, sinir, zorunlu=zorunlu, cok_satir=cok_satir)


def bos_ya_da(ham: Any, alan: str, sinir: int, cok_satir: bool = False) -> Optional[str]:
    return metin(ham, alan, sinir, cok_satir=cok_satir) or None


def secim(ham: Any, alan: str, secenekler: Sequence[str], varsayilan: Optional[str] = None) -> str:
    if ham in (None, "") and varsayilan is not None:
        return varsayilan
    if ham not in secenekler:
        raise OkrHatasi("secim_gecersiz", alan)
    return str(ham)


def bool_duzelt(ham: Any, alan: str) -> bool:
    if isinstance(ham, bool):
        return ham
    raise OkrHatasi("evet_hayir_gecersiz", alan)


def tam_sayi(ham: Any, alan: str, en_az: int, en_cok: int) -> int:
    return _cevir(m.tam_sayi, ham, alan, en_az, en_cok)


def kimlik(ham: Any, alan: str, bos_olabilir: bool = True) -> Optional[int]:
    return _cevir(m.kimlik, ham, alan, bos_olabilir)


def tarih_duzelt(ham: Any, alan: str) -> date:
    return _cevir(m.tarih_duzelt, ham, alan)


def para_birimi_duzelt(ham: Any, alan: str = "para_birimi", varsayilan: str = "TRY") -> str:
    return _cevir(m.para_birimi_duzelt, ham, alan, varsayilan)


def eposta_duzelt(ham: Any, alan: str = "sahip", zorunlu: bool = False) -> str:
    deger = str(ham or "").strip().lower()
    if not deger:
        if zorunlu:
            raise OkrHatasi("zorunlu", alan)
        return ""
    if len(deger) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", deger):
        raise OkrHatasi("eposta_gecersiz", alan)
    return deger


def deger_coz(ham: Any, tur: str, alan: str) -> float:
    """Ham değer → saklanan sayı. Para: KURUŞ (yarım yukarı; eksi olabilir — ör. kâr). Evet/hayır: 0/1.
    Sayı / yüzde: ondalıklı (Türkçe virgül de olur), |x| ≤ 10^12."""
    if tur == "evet_hayir":
        if isinstance(ham, bool):
            return 1.0 if ham else 0.0
        if ham in (0, 1, "0", "1"):
            return float(int(ham))
        raise OkrHatasi("evet_hayir_gecersiz", alan)
    if tur == "para":
        k = _cevir(m.kurus_coz, ham, alan, eksi_olabilir=True, sifir_olabilir=True)
        return float(k)
    if ham in (None, ""):
        raise OkrHatasi("zorunlu", alan)
    if isinstance(ham, bool):
        raise OkrHatasi("sayi_gecersiz", alan)
    try:
        d = float(m._ondalik(ham, None))  # noqa: SLF001 — ön muhasebenin ayırıcı kuralı (1.250,5 / 1,250.5 / 12,5)
    except Exception:  # noqa: BLE001
        raise OkrHatasi("sayi_gecersiz", alan)
    if not math.isfinite(d) or abs(d) > EN_COK_DEGER:
        raise OkrHatasi("sayi_gecersiz", alan)
    return round(d, 4)


def kilometre_duzelt(ham: Any, alan: str = "kilometre_taslari", onceki: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """[{"id"?, "metin", "tamam"?}] → doğrulanmış liste (id korunur ya da üretilir). En az 1, en çok 30."""
    if not isinstance(ham, list) or not ham:
        raise OkrHatasi("kilometre_gerekli", alan)
    if len(ham) > EN_COK_KILOMETRE:
        raise OkrHatasi("kilometre_cok", alan, en_cok=EN_COK_KILOMETRE)
    eski = {str(k.get("id")): k for k in (onceki or []) if isinstance(k, dict)}
    sonuc: List[Dict[str, Any]] = []
    gorulen = set()
    for i, k in enumerate(ham):
        if isinstance(k, str):
            k = {"metin": k}
        if not isinstance(k, dict):
            raise OkrHatasi("kilometre_gecersiz", f"{alan}.{i}")
        kid = str(k.get("id") or "")[:12]
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,12}", kid) or kid in gorulen:
            kid = "k" + secrets.token_hex(4)
        gorulen.add(kid)
        tamam = k.get("tamam", eski.get(kid, {}).get("tamam", False))
        sonuc.append({"id": kid, "metin": metin(k.get("metin"), f"{alan}.{i}.metin", 160, zorunlu=True),
                      "tamam": bool(tamam) if isinstance(tamam, bool) else False})
    return sonuc


def kilometre_sayilari(liste: Optional[Sequence[Dict[str, Any]]]) -> Tuple[int, int]:
    liste = [k for k in (liste or []) if isinstance(k, dict)]
    return sum(1 for k in liste if k.get("tamam")), len(liste)


# ---------------------------------------------------------------------------
# İlerleme hesabı (TEK yer)
# ---------------------------------------------------------------------------
def _kirp(x: float) -> float:
    if x != x:  # NaN
        return 0.0
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def kr_ilerleme(tur: str, baslangic: Optional[float], hedef: Optional[float], mevcut: Optional[float], yon: str = "artir",
                kilometre: Optional[Sequence[Dict[str, Any]]] = None) -> float:
    """Bir KR'nin 0–1 ilerlemesi.

    * sayi / yuzde / para: (mevcut − başlangıç) / (hedef − başlangıç), 0–1. Yön "azalt"ta hedef < başlangıç:
      aynı formül doğru işaretle (100 → 50 hedefinde 75 = 0,5; 120 = 0). Hedef = başlangıç (bölme sıfır): yönüne
      göre hedefe ulaşıldıysa 1, değilse 0. Negatif değerler olduğu gibi (−10 → 0 hedefinde −5 = 0,5).
    * evet_hayir: mevcut ≥ 1 → 1, değilse 0.
    * kilometre: tamamlanan / toplam (liste boşsa 0).
    """
    if tur == "kilometre":
        tamam, toplam = kilometre_sayilari(kilometre)
        return _kirp(tamam / toplam) if toplam else 0.0
    b = float(baslangic or 0.0)
    h = float(hedef or 0.0)
    c = float(mevcut or 0.0)
    if tur == "evet_hayir":
        return 1.0 if c >= 1 else 0.0
    if h == b:
        if yon == "azalt":
            return 1.0 if c <= h else 0.0
        return 1.0 if c >= h else 0.0
    return _kirp((c - b) / (h - b))


def hedef_ilerleme(krler: Iterable[Tuple[float, int]]) -> Optional[float]:
    """KR'lerin (ilerleme, ağırlık) ağırlıklı ortalaması; KR yoksa ya da ağırlık toplamı 0 ise None."""
    pay = 0.0
    payda = 0
    for ilerleme, agirlik in krler:
        a = max(0, int(agirlik or 0))
        pay += _kirp(float(ilerleme)) * a
        payda += a
    if payda <= 0:
        return None
    return _kirp(pay / payda)


def beklenen_ilerleme(bas: date, bit: date, gun: date) -> float:
    """Dönemde geçen gün oranı: başlangıçtan önce 0, başlangıç günü 1/n, bitiş günü ve sonrası 1."""
    if bit < bas:
        return 1.0
    toplam = (bit - bas).days + 1
    gecen = (gun - bas).days + 1
    return _kirp(gecen / toplam)


def ilerleme_durumu(ilerleme: Optional[float], beklenen: float) -> Optional[str]:
    """tamam | yolunda (en çok 10 puan geride) | riskli (en çok 25) | geride. İlerleme yoksa None."""
    if ilerleme is None:
        return None
    if ilerleme >= 1.0:
        return "tamam"
    fark = ilerleme - beklenen
    if fark >= -0.10:
        return "yolunda"
    if fark >= -0.25:
        return "riskli"
    return "geride"


def puan_duzelt(ham: Any, alan: str) -> float:
    """Kapanış puanı 0–1 (0,1 adım önerilir; iki ondalığa yuvarlanır)."""
    if ham in (None, "") or isinstance(ham, bool):
        raise OkrHatasi("puan_gecersiz", alan)
    try:
        d = float(str(ham).replace(",", "."))
    except (TypeError, ValueError):
        raise OkrHatasi("puan_gecersiz", alan)
    if not math.isfinite(d) or d < 0 or d > 1:
        raise OkrHatasi("puan_gecersiz", alan)
    return round(d, 2)


def yon_denetle(yon: str, baslangic: float, hedef: float) -> None:
    """Artır: hedef ≥ başlangıç; azalt: hedef ≤ başlangıç (eşitlik serbest — ilerleme kuralı yukarıda)."""
    if yon == "artir" and hedef < baslangic:
        raise OkrHatasi("yon_tutarsiz", "hedef_deger")
    if yon == "azalt" and hedef > baslangic:
        raise OkrHatasi("yon_tutarsiz", "hedef_deger")


# ---------------------------------------------------------------------------
# Dönem
# ---------------------------------------------------------------------------
def ceyrek_araligi(yil: int, ceyrek: int) -> Tuple[date, date]:
    bas = date(yil, 3 * (ceyrek - 1) + 1, 1)
    sonraki = date(yil + 1, 1, 1) if ceyrek == 4 else date(yil, 3 * ceyrek + 1, 1)
    return bas, sonraki - timedelta(days=1)


def yil_araligi(yil: int) -> Tuple[date, date]:
    return date(yil, 1, 1), date(yil, 12, 31)


def donem_coz(govde: Dict[str, Any]) -> Dict[str, Any]:
    """{tur, yil?, ceyrek?, baslangic?, bitis?, ad?} → doğrulanmış alanlar."""
    tur = secim(govde.get("tur"), "tur", DONEM_TURLERI, "ceyrek")
    ad = bos_ya_da(govde.get("ad"), "ad", 80)
    yil = ceyrek = None
    if tur in ("ceyrek", "yil"):
        yil = tam_sayi(govde.get("yil"), "yil", 2000, 2100)
        if tur == "ceyrek":
            ceyrek = tam_sayi(govde.get("ceyrek"), "ceyrek", 1, 4)
            bas, bit = ceyrek_araligi(yil, ceyrek)
        else:
            bas, bit = yil_araligi(yil)
    else:
        bas = tarih_duzelt(govde.get("baslangic"), "baslangic")
        bit = tarih_duzelt(govde.get("bitis"), "bitis")
        if bit < bas:
            raise OkrHatasi("bitis_once", "bitis")
        if (bit - bas).days > 3 * 366:
            raise OkrHatasi("donem_cok_uzun", "bitis")
    return {"tur": tur, "ad": ad, "yil": yil, "ceyrek": ceyrek, "baslangic": bas, "bitis": bit}


def donem_etiketi(tur: str, yil: Optional[int], ceyrek: Optional[int], bas: date, bit: date, ad: Optional[str], dil: str = "tr") -> str:
    """PDF / CSV / bildirimler için (arayüz kendi çevirisini kurar)."""
    if ad:
        return ad
    if tur == "ceyrek" and yil and ceyrek:
        return f"{yil} Q{ceyrek}" if dil != "tr" else f"{yil} Ç{ceyrek}"
    if tur == "yil" and yil:
        return str(yil)
    return f"{bas.strftime('%d.%m.%Y')} – {bit.strftime('%d.%m.%Y')}"


def dongu_var_mi(ust_haritasi: Dict[int, Optional[int]], hedef_id: Optional[int], yeni_ust: Optional[int]) -> bool:
    """`hedef_id`'nin üstü `yeni_ust` olursa döngü oluşur mu? (kendisi, ya da yeni üst onun alt ağacında)."""
    if yeni_ust is None:
        return False
    if hedef_id is not None and yeni_ust == hedef_id:
        return True
    gorulen = set()
    simdiki: Optional[int] = yeni_ust
    while simdiki is not None:
        if simdiki in gorulen:  # var olan bozuk zincir: güvenli tarafta kal
            return True
        if hedef_id is not None and simdiki == hedef_id:
            return True
        gorulen.add(simdiki)
        simdiki = ust_haritasi.get(simdiki)
    return False


# ---------------------------------------------------------------------------
# Biçim (CSV / PDF / bildirim)
# ---------------------------------------------------------------------------
def deger_metni(tur: str, deger: Optional[float], para_birimi: Optional[str] = None, birim: Optional[str] = None, dil: str = "tr") -> str:
    if deger is None:
        return "—"
    if tur == "para":
        from services import pdf_belge as pb

        return pb.para(float(deger) / 100, para_birimi or "TRY", "tr" if dil in ("tr", "de") else "en")
    if tur == "evet_hayir":
        return "✓" if deger >= 1 else "✗"
    sayi = f"{deger:,.2f}".rstrip("0").rstrip(".") if abs(deger - round(deger)) > 1e-9 else f"{int(round(deger)):,}"
    if dil in ("tr", "de"):
        sayi = sayi.replace(",", "§").replace(".", ",").replace("§", ".")
    if tur == "yuzde":
        return f"%{sayi}" if dil == "tr" else f"{sayi}%"
    return f"{sayi} {birim}".strip() if birim else sayi


def yuzde_metni(oran: Optional[float]) -> str:
    return "—" if oran is None else f"{round(oran * 100)}%"


def csv_metni(basliklar: Sequence[str], satirlar: Iterable[Sequence[Any]]) -> str:
    return m.csv_metni(basliklar, satirlar)


PDF_ETIKET: Dict[str, Dict[str, str]] = {
    "tr": {"baslik": "OKR RAPORU", "donem": "Dönem", "olusturma": "Oluşturma", "durum": "Durum", "acik": "Açık",
           "kapandi": "Kapandı", "genel": "Genel ilerleme", "beklenen": "Beklenen", "hedef": "Hedef", "sahip": "Sahibi",
           "kr": "Anahtar sonuç", "baslangic": "Başlangıç", "hedef_deger": "Hedef değer", "mevcut": "Mevcut",
           "ilerleme": "İlerleme", "guven": "Güven", "puan": "Puan", "kaynak": "otomatik", "bos": "Bu dönemde hedef yok.",
           "kr_yok": "Anahtar sonuç yok.", "kapanis_notu": "Kapanış notu", "yolunda": "Yolunda", "riskli": "Riskli",
           "tehlikede": "Tehlikede", "taslak": "Taslak", "etkin": "Etkin",
           "not": "Bu rapor bilgi amaçlıdır; ilerleme girilen ve hesaplanan değerlerden üretilmiştir."},
    "en": {"baslik": "OKR REPORT", "donem": "Period", "olusturma": "Created", "durum": "Status", "acik": "Open",
           "kapandi": "Closed", "genel": "Overall progress", "beklenen": "Expected", "hedef": "Objective", "sahip": "Owner",
           "kr": "Key result", "baslangic": "Start", "hedef_deger": "Target", "mevcut": "Current", "ilerleme": "Progress",
           "guven": "Confidence", "puan": "Score", "kaynak": "automatic", "bos": "No objectives in this period.",
           "kr_yok": "No key results.", "kapanis_notu": "Closing note", "yolunda": "On track", "riskli": "At risk",
           "tehlikede": "Off track", "taslak": "Draft", "etkin": "Active",
           "not": "This report is for information only; progress is derived from entered and calculated values."},
    "de": {"baslik": "OKR-BERICHT", "donem": "Zeitraum", "olusturma": "Erstellt", "durum": "Status", "acik": "Offen",
           "kapandi": "Abgeschlossen", "genel": "Gesamtfortschritt", "beklenen": "Erwartet", "hedef": "Ziel",
           "sahip": "Verantwortlich", "kr": "Schlüsselergebnis", "baslangic": "Start", "hedef_deger": "Zielwert",
           "mevcut": "Aktuell", "ilerleme": "Fortschritt", "guven": "Zuversicht", "puan": "Bewertung", "kaynak": "automatisch",
           "bos": "Keine Ziele in diesem Zeitraum.", "kr_yok": "Keine Schlüsselergebnisse.", "kapanis_notu": "Abschlussnotiz",
           "yolunda": "Im Plan", "riskli": "Gefährdet", "tehlikede": "Kritisch", "taslak": "Entwurf", "etkin": "Aktiv",
           "not": "Dieser Bericht dient nur zur Information; der Fortschritt beruht auf eingegebenen und berechneten Werten."},
    "ru": {"baslik": "ОТЧЁТ ПО OKR", "donem": "Период", "olusturma": "Создан", "durum": "Статус", "acik": "Открыт",
           "kapandi": "Закрыт", "genel": "Общий прогресс", "beklenen": "Ожидаемый", "hedef": "Цель", "sahip": "Ответственный",
           "kr": "Ключевой результат", "baslangic": "Начало", "hedef_deger": "Цель (значение)", "mevcut": "Текущее",
           "ilerleme": "Прогресс", "guven": "Уверенность", "puan": "Оценка", "kaynak": "автоматически",
           "bos": "В этом периоде нет целей.", "kr_yok": "Нет ключевых результатов.", "kapanis_notu": "Итоговая заметка",
           "yolunda": "По плану", "riskli": "Под угрозой", "tehlikede": "Отстаёт", "taslak": "Черновик", "etkin": "Активна",
           "not": "Отчёт носит информационный характер; прогресс рассчитан по введённым и вычисленным значениям."},
    "zh": {"baslik": "OKR 报告", "donem": "周期", "olusturma": "生成日期", "durum": "状态", "acik": "进行中", "kapandi": "已关闭",
           "genel": "总体进度", "beklenen": "预期", "hedef": "目标", "sahip": "负责人", "kr": "关键结果", "baslangic": "起始值",
           "hedef_deger": "目标值", "mevcut": "当前值", "ilerleme": "进度", "guven": "信心", "puan": "评分", "kaynak": "自动",
           "bos": "本周期没有目标。", "kr_yok": "没有关键结果。", "kapanis_notu": "结项说明", "yolunda": "正常", "riskli": "有风险",
           "tehlikede": "落后", "taslak": "草稿", "etkin": "进行中", "not": "本报告仅供参考；进度根据录入值和计算值生成。"},
    "hi": {"baslik": "OKR रिपोर्ट", "donem": "अवधि", "olusturma": "बनाया गया", "durum": "स्थिति", "acik": "खुली",
           "kapandi": "बंद", "genel": "कुल प्रगति", "beklenen": "अपेक्षित", "hedef": "लक्ष्य", "sahip": "ज़िम्मेदार",
           "kr": "मुख्य परिणाम", "baslangic": "शुरुआत", "hedef_deger": "लक्ष्य मान", "mevcut": "वर्तमान", "ilerleme": "प्रगति",
           "guven": "भरोसा", "puan": "अंक", "kaynak": "स्वचालित", "bos": "इस अवधि में कोई लक्ष्य नहीं।",
           "kr_yok": "कोई मुख्य परिणाम नहीं।", "kapanis_notu": "समापन नोट", "yolunda": "सही दिशा में", "riskli": "जोखिम में",
           "tehlikede": "पीछे", "taslak": "मसौदा", "etkin": "सक्रिय",
           "not": "यह रिपोर्ट केवल जानकारी के लिए है; प्रगति दर्ज और गणना किए गए मानों से बनी है।"},
    "ar": {"baslik": "تقرير الأهداف والنتائج الرئيسية", "donem": "الفترة", "olusturma": "تاريخ الإنشاء", "durum": "الحالة",
           "acik": "مفتوحة", "kapandi": "مغلقة", "genel": "التقدم الإجمالي", "beklenen": "المتوقع", "hedef": "الهدف",
           "sahip": "المسؤول", "kr": "النتيجة الرئيسية", "baslangic": "البداية", "hedef_deger": "القيمة المستهدفة",
           "mevcut": "الحالية", "ilerleme": "التقدم", "guven": "الثقة", "puan": "التقييم", "kaynak": "تلقائي",
           "bos": "لا توجد أهداف في هذه الفترة.", "kr_yok": "لا توجد نتائج رئيسية.", "kapanis_notu": "ملاحظة الإغلاق",
           "yolunda": "على المسار", "riskli": "معرّض للخطر", "tehlikede": "متأخر", "taslak": "مسودة", "etkin": "نشط",
           "not": "هذا التقرير للعلم فقط؛ التقدم محسوب من القيم المُدخلة والمحسوبة."},
}

CSV_BASLIKLARI: Dict[str, List[str]] = {
    "tr": ["Hedef", "Hedef sahibi", "Hedef durumu", "Hedef ilerlemesi (%)", "Anahtar sonuç", "Tür", "Yön", "Başlangıç",
           "Hedef değer", "Mevcut", "Para birimi", "Ağırlık", "İlerleme (%)", "Güven", "Kaynak", "Kapanış puanı", "KR sahibi"],
    "en": ["Objective", "Objective owner", "Objective status", "Objective progress (%)", "Key result", "Type", "Direction",
           "Start", "Target", "Current", "Currency", "Weight", "Progress (%)", "Confidence", "Source", "Closing score", "KR owner"],
}


def pdf_dili(dil: Optional[str]) -> str:
    d = (dil or "tr")[:2].lower()
    return d if d in PDF_ETIKET else "en"


def rapor_pdf(v: Dict[str, Any], dil: str = "tr") -> bytes:
    """`v`: {"firma", "donem": {ad, bas, bit, durum, kapanis_notu}, "ilerleme", "beklenen", "hedefler": [{baslik, sahip,
    durum, ilerleme, krler: [{baslik, tur, baslangic, hedef, mevcut, para_birimi, birim, ilerleme, guven, puan, kaynak}]}]}."""
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, Spacer, Table, TableStyle

    from services import pdf_belge as pb
    from services.pdf_yazi import Paragraf as Paragraph  # çok dilli paragraf (Faz 7K yazı tipi yedeği)

    dil = pdf_dili(dil)
    e = PDF_ETIKET[dil]
    st = pb._stiller()  # noqa: SLF001
    t_ = pb._metin  # noqa: SLF001
    d = v.get("donem") or {}
    sol = [Paragraph(f"<b>{t_(v.get('firma') or '')}</b>" if v.get("firma") else "&nbsp;", st["govde"])]
    bilgiler = [(e["donem"], d.get("ad") or ""),
                ("", f"{_pdf_tarih(d.get('bas'))} – {_pdf_tarih(d.get('bit'))}"),
                (e["durum"], e.get(d.get("durum") or "acik", "")),
                (e["olusturma"], _pdf_tarih(v.get("olusturma")))]
    bilgiler = [(a, b) for a, b in bilgiler if b]
    parcalar: List[Any] = [pb._baslik_blogu(sol, e["baslik"], bilgiler, st), pb._ayrac(), Spacer(1, 3 * mm)]  # noqa: SLF001
    parcalar.append(Paragraph(f"<b>{t_(e['genel'])}:</b> {yuzde_metni(v.get('ilerleme'))} · "
                              f"{t_(e['beklenen'])}: {yuzde_metni(v.get('beklenen'))}", st["govde"]))
    if d.get("kapanis_notu"):
        parcalar += [Spacer(1, 2 * mm), Paragraph(f"<b>{t_(e['kapanis_notu'])}:</b> {t_(d['kapanis_notu'])}", st["govde"])]
    parcalar.append(Spacer(1, 4 * mm))
    hedefler = v.get("hedefler") or []
    if not hedefler:
        parcalar.append(Paragraph(t_(e["bos"]), st["kucuk"]))
    kapali = d.get("durum") == "kapandi"
    for h in hedefler:
        ust = [Paragraph(f"<b>{t_(e['hedef'])}: {t_(h.get('baslik'))}</b> — {yuzde_metni(h.get('ilerleme'))}", st["govde"])]
        alt = [x for x in (f"{e['sahip']}: {h['sahip']}" if h.get("sahip") else "", e.get(h.get("durum") or "", "")) if x]
        if alt:
            ust.append(Paragraph(t_(" · ".join(alt)), st["kucuk"]))
        basliklar = [e["kr"], e["baslangic"], e["hedef_deger"], e["mevcut"], e["ilerleme"], e["puan"] if kapali else e["guven"]]
        veri: List[List[Any]] = [[Paragraph(f"<b>{t_(b)}</b>", st["govde"] if i == 0 else st["sag"]) for i, b in enumerate(basliklar)]]
        for k in h.get("krler") or []:
            ad = k.get("baslik") or ""
            if k.get("kaynak"):
                ad = f"{ad} ({e['kaynak']})"
            son = (yuzde_metni(k.get("puan")) if k.get("puan") is not None else "—") if kapali else e.get(k.get("guven") or "", "—")
            tur, pbr, br = k.get("tur"), k.get("para_birimi"), k.get("birim")
            if tur == "kilometre":
                bas_m, hed_m, mev_m = "0", str(k.get("toplam") or 0), str(k.get("tamam") or 0)
            else:
                bas_m = deger_metni(tur, k.get("baslangic"), pbr, br, dil)
                hed_m = deger_metni(tur, k.get("hedef"), pbr, br, dil)
                mev_m = deger_metni(tur, k.get("mevcut"), pbr, br, dil)
            veri.append([Paragraph(t_(ad), st["govde"]), Paragraph(t_(bas_m), st["sag"]), Paragraph(t_(hed_m), st["sag"]),
                         Paragraph(t_(mev_m), st["sag"]), Paragraph(yuzde_metni(k.get("ilerleme")), st["sag"]),
                         Paragraph(t_(son), st["sag"])])
        if not h.get("krler"):
            veri.append([Paragraph(t_(e["kr_yok"]), st["kucuk"])] + [Paragraph("", st["sag"]) for _ in range(5)])
        tablo = Table(veri, colWidths=[66 * mm, 24 * mm, 24 * mm, 24 * mm, 20 * mm, 22 * mm], repeatRows=1)
        tablo.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), pb.VURGU_ACIK), ("LINEBELOW", (0, 0), (-1, 0), 0.8, pb.VURGU),
                                   ("LINEBELOW", (0, 1), (-1, -1), 0.3, pb.CIZGI), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        parcalar += [KeepTogether(ust + [Spacer(1, 1.5 * mm), tablo]), Spacer(1, 5 * mm)]
    return pb._uret(parcalar, e["not"], "tr" if dil == "tr" else "en", f"{e['baslik']} {d.get('ad') or ''}")  # noqa: SLF001


def _pdf_tarih(g: Any) -> str:
    if isinstance(g, str):
        try:
            g = date.fromisoformat(g[:10])
        except ValueError:
            return g
    return g.strftime("%d.%m.%Y") if isinstance(g, date) else "—"


# ---------------------------------------------------------------------------
# "AI ile KR öner" (SMART yardımcısı) — öneriler KAYDEDİLMEZ; kullanıcı seçip ekler
# ---------------------------------------------------------------------------
def ai_mesajlari(*, dil: str, hedef: str, aciklama: str, mevcut: Sequence[str], sayi: int) -> List[Dict[str, str]]:
    from services.yapay_zeka import DIL_ADLARI

    sistem = (
        "You help a team write SMART key results (OKR) for an objective. Each key result must be Specific, Measurable, "
        "Achievable, Relevant and Time-bound within the current period, with a numeric start and target value. "
        f"Write titles in {DIL_ADLARI.get(dil, 'Turkish')}. Do not repeat existing key results. Answer with ONLY a JSON "
        'object, no prose, no code fences: {"oneriler":[{"baslik":"…","tur":"sayi|yuzde|para|evet_hayir",'
        '"baslangic":<number>,"hedef":<number>,"yon":"artir|azalt","birim":"short unit or empty","gerekce":"one short sentence"}]}'
    )
    kullanici = (f"Objective: {hedef[:200]}\nDescription: {aciklama[:600]}\nExisting key results: "
                 f"{'; '.join(x[:120] for x in mevcut[:10]) or '-'}\nNumber of suggestions: {int(sayi)}")
    return [{"role": "system", "content": sistem}, {"role": "user", "content": kullanici}]


def ai_yanitini_coz(metin_: str, sayi: int) -> List[Dict[str, Any]]:
    """Model yanıtı → doğrulanmış öneriler (geçersizleri atılır). Hiçbiri geçerli değilse `ai_bicim`."""
    ham = re.sub(r"^```(?:json)?\s*|\s*```$", "", (metin_ or "").strip())
    bas, son = ham.find("{"), ham.rfind("}")
    try:
        veri = json.loads(ham[bas:son + 1]) if bas >= 0 and son > bas else json.loads(ham)
    except (ValueError, TypeError):
        raise OkrHatasi("ai_bicim", durum=502)
    liste = veri.get("oneriler") if isinstance(veri, dict) else veri
    if not isinstance(liste, list):
        raise OkrHatasi("ai_bicim", durum=502)
    sonuc: List[Dict[str, Any]] = []
    for o in liste:
        if len(sonuc) >= max(1, min(EN_COK_ONERI, int(sayi))):
            break
        if not isinstance(o, dict):
            continue
        try:
            tur = o.get("tur") if o.get("tur") in ("sayi", "yuzde", "para", "evet_hayir") else "sayi"
            yon = o.get("yon") if o.get("yon") in YONLER else "artir"
            baslik = metin(o.get("baslik"), "baslik", 200, zorunlu=True)
            if tur == "evet_hayir":
                b_, h_ = 0.0, 1.0
                yon = "artir"
            else:
                b_ = float(o.get("baslangic") or 0)
                h_ = float(o.get("hedef") if o.get("hedef") is not None else 0)
                if not (math.isfinite(b_) and math.isfinite(h_)) or abs(b_) > EN_COK_DEGER or abs(h_) > EN_COK_DEGER:
                    continue
                if tur == "para":  # model ana birimle yazar → kuruş
                    b_, h_ = round(b_ * 100), round(h_ * 100)
                if (yon == "artir" and h_ < b_) or (yon == "azalt" and h_ > b_):
                    yon = "azalt" if h_ < b_ else "artir"
            sonuc.append({"baslik": baslik, "tur": tur, "baslangic": b_, "hedef": h_, "yon": yon,
                          "birim": (metin(o.get("birim"), "birim", 20) or None) if tur == "sayi" else None,
                          "gerekce": metin(o.get("gerekce"), "gerekce", 240) or None})
        except (TemelHata, TypeError, ValueError):
            continue
    if not sonuc:
        raise OkrHatasi("ai_bicim", durum=502)
    return sonuc


def sahte_oneriler(hedef: str, sayi: int) -> List[Dict[str, Any]]:
    """Test ortamı (ENVIRONMENT=test, sahte model JSON vermiyor): belirlenimci öneriler."""
    taban = [
        {"baslik": f"{hedef[:120]}: yeni müşteri sayısı", "tur": "sayi", "baslangic": 0, "hedef": 10, "yon": "artir",
         "birim": "müşteri", "gerekce": "Ölçülebilir ve dönem içinde ulaşılabilir."},
        {"baslik": f"{hedef[:120]}: müşteri memnuniyeti", "tur": "yuzde", "baslangic": 70, "hedef": 90, "yon": "artir"},
        {"baslik": f"{hedef[:120]}: ortalama yanıt süresi (saat)", "tur": "sayi", "baslangic": 24, "hedef": 4, "yon": "azalt",
         "birim": "saat"},
    ]
    return ai_yanitini_coz(json.dumps({"oneriler": taban}, ensure_ascii=False), sayi)


__all__ = [
    "MODUL", "IZIN", "IZIN_OKUR", "OkrHatasi", "TemelHata", "simdi", "bugun", "kr_ilerleme", "hedef_ilerleme",
    "beklenen_ilerleme", "ilerleme_durumu", "donem_coz", "dongu_var_mi", "deger_coz", "kilometre_duzelt", "rapor_pdf",
    "ai_mesajlari", "ai_yanitini_coz", "sahte_oneriler",
]
