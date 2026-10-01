"""Faz 3C — gömülebilir aday formu: tanım doğrulama, köken (Origin) kuralı,
süre jetonu ve herkese açık gönderimin kuralları.

Gömme
-----
Yönetici panelde form tanımlıyor; siteye iki satır yapıştırılıyor::

    <script src="https://mehmetkuru.dev/crm-form.js" async></script>
    <div data-mk-form="<genel_anahtar>"></div>

Betik (`public/crm-form.js`, bağımlılıksız) `GET /api/v1/crm/form/<anahtar>`
ile tanımı (alanlar, seçili dilde etiketler, KVKK metni, süre jetonu) alıp
formu çiziyor; gönderim `POST` ile aynı adrese. Aynı formun doğrudan
bağlantısı: `/form/<anahtar>` (noindex, aynı betiği kullanıyor).

Kötüye kullanım önlemleri
-------------------------
* Köken: istekte `Origin` varsa yalnız formun izinli alan adları (alt alan
  adları dahil) + sitenin kendisi (`SITE_PUBLIC_URL`, mehmetkuru.dev) kabul.
  Reddedilen yanıttan CORS başlıkları siliniyor (`middlewares/crm_form_cors.py`);
  ön kontrol (OPTIONS) da aynı kurala bağlı. Origin'i olmayan istek (sunucudan
  sunucuya) kabul — onu durduran hız sınırı ve süre jetonu.
* Süre jetonu: tanım isteğinde HMAC imzalı `form_id.zaman_ms.imza`. Gönderim
  jetonsuzsa ya da imza tutmuyorsa 400 `jeton_gecersiz`; formu açtıktan sonra
  2 sn dolmadan gelirse 400 `cok_hizli` (bot); 24 saatten eskiyse
  `jeton_suresi_doldu`.
* Bal küpü: görünmeyen `web_adresi` alanı doluysa yanıt "başarılı" görünür
  ama HİÇBİR şey kaydedilmez (bot bunu anlamasın).
* IP başına hız sınırı (10 dakikada 5 gönderim), alan uzunluk sınırları,
  KVKK onayı zorunlu ve kaydı: metin sürümü + metnin özeti + zaman + IP özeti.
"""

import hashlib
import hmac
import json
import os
import re
import secrets
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from services.crm import eposta_duzelt, eposta_gecerli, etiketleri_duzelt, json_liste, json_sozluk

ALAN_ADLARI: Tuple[str, ...] = ("ad", "email", "telefon", "firma", "mesaj", "butce")
ALAN_SINIRLARI: Dict[str, int] = {"ad": 120, "email": 254, "telefon": 40, "firma": 160, "mesaj": 4000, "butce": 120}
VARSAYILAN_ALANLAR: Dict[str, Dict[str, bool]] = {
    "ad": {"acik": True, "zorunlu": True},
    "email": {"acik": True, "zorunlu": True},
    "telefon": {"acik": True, "zorunlu": False},
    "firma": {"acik": False, "zorunlu": False},
    "mesaj": {"acik": True, "zorunlu": False},
    "butce": {"acik": False, "zorunlu": False},
}
BAL_KUPU = "web_adresi"
EN_AZ_SURE_SN = 2.0
JETON_OMRU_SN = 24 * 3600
GOVDE_SINIRI = 20_000
IZINLI_ALAN_SAYISI = 20
DILLER = ("tr", "en", "de", "ru", "zh", "hi", "ar")

_ALAN_ADI = re.compile(r"^(?:\*\.)?(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$|^localhost$")

#: Ziyaretçinin gördüğü metinler (betik ve /form sayfası sunucudan alıyor; 7 dil).
ETIKETLER: Dict[str, Dict[str, Any]] = {
    "tr": {
        "alan": {"ad": "Adınız", "email": "E-posta", "telefon": "Telefon", "firma": "Firma", "mesaj": "Mesajınız", "butce": "Bütçe"},
        "gonder": "Gönder", "gonderiliyor": "Gönderiliyor…", "aydinlatma": "Aydınlatma metni",
        "tesekkur": "Teşekkürler! Mesajınız bize ulaştı, en kısa sürede dönüş yapacağız.", "istege_bagli": "isteğe bağlı",
        "hata": {
            "kvkk_gerekli": "Devam etmek için onay kutusunu işaretleyin.", "alan_gerekli": "Lütfen zorunlu alanları doldurun.",
            "alan_uzun": "Bir alan çok uzun; lütfen kısaltın.", "eposta_gecersiz": "Geçerli bir e-posta adresi yazın.",
            "cok_hizli": "Çok hızlı gönderildi; lütfen birkaç saniye sonra tekrar deneyin.",
            "cok_fazla_istek": "Çok fazla deneme yapıldı; lütfen biraz sonra tekrar deneyin.",
            "jeton_suresi_doldu": "Formun süresi doldu; sayfayı yenileyip tekrar deneyin.",
            "form_yok": "Bu form artık kullanılmıyor.", "alan_adi_izinsiz": "Bu form bu sitede kullanılamıyor.",
            "genel": "Gönderilemedi; lütfen tekrar deneyin.",
        },
    },
    "en": {
        "alan": {"ad": "Your name", "email": "Email", "telefon": "Phone", "firma": "Company", "mesaj": "Your message", "butce": "Budget"},
        "gonder": "Send", "gonderiliyor": "Sending…", "aydinlatma": "Privacy notice",
        "tesekkur": "Thank you! Your message has reached us and we will get back to you shortly.", "istege_bagli": "optional",
        "hata": {
            "kvkk_gerekli": "Please tick the consent box to continue.", "alan_gerekli": "Please fill in the required fields.",
            "alan_uzun": "A field is too long; please shorten it.", "eposta_gecersiz": "Please enter a valid email address.",
            "cok_hizli": "Sent too quickly; please try again in a few seconds.",
            "cok_fazla_istek": "Too many attempts; please try again a little later.",
            "jeton_suresi_doldu": "The form has expired; please reload the page and try again.",
            "form_yok": "This form is no longer in use.", "alan_adi_izinsiz": "This form cannot be used on this site.",
            "genel": "Could not send; please try again.",
        },
    },
    "de": {
        "alan": {"ad": "Ihr Name", "email": "E-Mail", "telefon": "Telefon", "firma": "Firma", "mesaj": "Ihre Nachricht", "butce": "Budget"},
        "gonder": "Senden", "gonderiliyor": "Wird gesendet…", "aydinlatma": "Datenschutzhinweis",
        "tesekkur": "Vielen Dank! Ihre Nachricht ist bei uns eingegangen, wir melden uns in Kürze.", "istege_bagli": "optional",
        "hata": {
            "kvkk_gerekli": "Bitte setzen Sie das Häkchen zur Einwilligung.", "alan_gerekli": "Bitte füllen Sie die Pflichtfelder aus.",
            "alan_uzun": "Ein Feld ist zu lang; bitte kürzen Sie es.", "eposta_gecersiz": "Bitte geben Sie eine gültige E-Mail-Adresse ein.",
            "cok_hizli": "Zu schnell gesendet; bitte versuchen Sie es in einigen Sekunden erneut.",
            "cok_fazla_istek": "Zu viele Versuche; bitte versuchen Sie es etwas später erneut.",
            "jeton_suresi_doldu": "Das Formular ist abgelaufen; bitte laden Sie die Seite neu.",
            "form_yok": "Dieses Formular wird nicht mehr verwendet.", "alan_adi_izinsiz": "Dieses Formular kann auf dieser Website nicht verwendet werden.",
            "genel": "Senden fehlgeschlagen; bitte versuchen Sie es erneut.",
        },
    },
    "ru": {
        "alan": {"ad": "Ваше имя", "email": "Эл. почта", "telefon": "Телефон", "firma": "Компания", "mesaj": "Ваше сообщение", "butce": "Бюджет"},
        "gonder": "Отправить", "gonderiliyor": "Отправка…", "aydinlatma": "Уведомление о конфиденциальности",
        "tesekkur": "Спасибо! Ваше сообщение получено, мы скоро свяжемся с вами.", "istege_bagli": "необязательно",
        "hata": {
            "kvkk_gerekli": "Чтобы продолжить, отметьте согласие.", "alan_gerekli": "Заполните обязательные поля.",
            "alan_uzun": "Одно из полей слишком длинное; сократите его.", "eposta_gecersiz": "Укажите корректный адрес эл. почты.",
            "cok_hizli": "Отправлено слишком быстро; повторите через несколько секунд.",
            "cok_fazla_istek": "Слишком много попыток; повторите немного позже.",
            "jeton_suresi_doldu": "Срок действия формы истёк; обновите страницу и повторите.",
            "form_yok": "Эта форма больше не используется.", "alan_adi_izinsiz": "Эту форму нельзя использовать на этом сайте.",
            "genel": "Не удалось отправить; попробуйте ещё раз.",
        },
    },
    "zh": {
        "alan": {"ad": "您的姓名", "email": "电子邮箱", "telefon": "电话", "firma": "公司", "mesaj": "留言内容", "butce": "预算"},
        "gonder": "提交", "gonderiliyor": "正在提交…", "aydinlatma": "隐私说明",
        "tesekkur": "谢谢！我们已收到您的留言，会尽快与您联系。", "istege_bagli": "选填",
        "hata": {
            "kvkk_gerekli": "请勾选同意框后继续。", "alan_gerekli": "请填写必填项。",
            "alan_uzun": "有字段内容过长，请缩短。", "eposta_gecersiz": "请输入有效的电子邮箱地址。",
            "cok_hizli": "提交过快，请几秒后再试。", "cok_fazla_istek": "尝试次数过多，请稍后再试。",
            "jeton_suresi_doldu": "表单已过期，请刷新页面后重试。",
            "form_yok": "此表单已停用。", "alan_adi_izinsiz": "此表单不能在本网站使用。",
            "genel": "提交失败，请重试。",
        },
    },
    "hi": {
        "alan": {"ad": "आपका नाम", "email": "ईमेल", "telefon": "फ़ोन", "firma": "कंपनी", "mesaj": "आपका संदेश", "butce": "बजट"},
        "gonder": "भेजें", "gonderiliyor": "भेजा जा रहा है…", "aydinlatma": "गोपनीयता सूचना",
        "tesekkur": "धन्यवाद! आपका संदेश हमें मिल गया है, हम जल्द ही आपसे संपर्क करेंगे।", "istege_bagli": "वैकल्पिक",
        "hata": {
            "kvkk_gerekli": "आगे बढ़ने के लिए सहमति बॉक्स पर टिक करें।", "alan_gerekli": "कृपया आवश्यक फ़ील्ड भरें।",
            "alan_uzun": "एक फ़ील्ड बहुत लंबा है; कृपया छोटा करें।", "eposta_gecersiz": "कृपया मान्य ईमेल पता लिखें।",
            "cok_hizli": "बहुत जल्दी भेजा गया; कुछ सेकंड बाद फिर कोशिश करें।",
            "cok_fazla_istek": "बहुत अधिक प्रयास; थोड़ी देर बाद फिर कोशिश करें।",
            "jeton_suresi_doldu": "फ़ॉर्म की अवधि समाप्त हो गई; पेज रीफ़्रेश करके फिर कोशिश करें।",
            "form_yok": "यह फ़ॉर्म अब उपयोग में नहीं है।", "alan_adi_izinsiz": "यह फ़ॉर्म इस साइट पर उपयोग नहीं किया जा सकता।",
            "genel": "भेजा नहीं जा सका; कृपया फिर कोशिश करें।",
        },
    },
    "ar": {
        "alan": {"ad": "اسمك", "email": "البريد الإلكتروني", "telefon": "الهاتف", "firma": "الشركة", "mesaj": "رسالتك", "butce": "الميزانية"},
        "gonder": "إرسال", "gonderiliyor": "جارٍ الإرسال…", "aydinlatma": "إشعار الخصوصية",
        "tesekkur": "شكرًا لك! وصلتنا رسالتك وسنتواصل معك قريبًا.", "istege_bagli": "اختياري",
        "hata": {
            "kvkk_gerekli": "يرجى تحديد مربع الموافقة للمتابعة.", "alan_gerekli": "يرجى ملء الحقول المطلوبة.",
            "alan_uzun": "أحد الحقول طويل جدًا؛ يرجى اختصاره.", "eposta_gecersiz": "يرجى كتابة بريد إلكتروني صالح.",
            "cok_hizli": "تم الإرسال بسرعة كبيرة؛ يرجى المحاولة بعد بضع ثوانٍ.",
            "cok_fazla_istek": "محاولات كثيرة جدًا؛ يرجى المحاولة لاحقًا.",
            "jeton_suresi_doldu": "انتهت صلاحية النموذج؛ يرجى تحديث الصفحة والمحاولة مجددًا.",
            "form_yok": "هذا النموذج لم يعد مستخدمًا.", "alan_adi_izinsiz": "لا يمكن استخدام هذا النموذج على هذا الموقع.",
            "genel": "تعذّر الإرسال؛ يرجى المحاولة مجددًا.",
        },
    },
}


class FormHatasi(Exception):
    def __init__(self, kod: str, durum: int = 400, **ek: Any):
        super().__init__(kod)
        self.kod = kod
        self.durum = durum
        self.ek = ek


def dil_sec(ham: Optional[str]) -> str:
    d = (ham or "").strip().lower()[:2]
    return d if d in DILLER else "tr"


# ---------------------------------------------------------------------------
# Tanım doğrulama (panel)
# ---------------------------------------------------------------------------
def alanlari_duzelt(ham: Any) -> Dict[str, Dict[str, bool]]:
    sonuc = {k: dict(v) for k, v in VARSAYILAN_ALANLAR.items()}
    if ham in (None, ""):
        return sonuc
    if isinstance(ham, str):
        ham = json_sozluk(ham)
    if not isinstance(ham, dict):
        raise FormHatasi("alanlar_gecersiz")
    for ad in ALAN_ADLARI:
        girdi = ham.get(ad)
        if not isinstance(girdi, dict):
            continue
        acik = bool(girdi.get("acik", sonuc[ad]["acik"]))
        zorunlu = bool(girdi.get("zorunlu", sonuc[ad]["zorunlu"])) and acik
        sonuc[ad] = {"acik": acik, "zorunlu": zorunlu}
    # E-posta tekilleştirme anahtarı: her zaman açık ve zorunlu.
    sonuc["email"] = {"acik": True, "zorunlu": True}
    return sonuc


def alan_adi_duzelt(ham: str) -> str:
    s = (ham or "").strip().lower()
    if "://" in s:
        s = urlparse(s).hostname or ""
    s = s.split("/")[0].split(":")[0].strip(".")
    # Alt alan adları zaten izinli: "*.ornek.com" ve "www.ornek.com" → "ornek.com".
    for onek in ("*.", "www."):
        if s.startswith(onek):
            s = s[len(onek):]
    if not s or not _ALAN_ADI.match(s):
        raise FormHatasi("alan_adi_gecersiz", deger=(ham or "")[:100])
    return s


def izinli_alanlari_duzelt(ham: Any) -> List[str]:
    if ham in (None, ""):
        return []
    if isinstance(ham, str):
        ham = [p for p in re.split(r"[\s,;]+", ham) if p]
    if not isinstance(ham, (list, tuple)):
        raise FormHatasi("alan_adi_gecersiz")
    sonuc: List[str] = []
    for h in ham:
        a = alan_adi_duzelt(str(h))
        if a not in sonuc:
            sonuc.append(a)
    if len(sonuc) > IZINLI_ALAN_SAYISI:
        raise FormHatasi("alan_adi_sayisi")
    return sonuc


def https_adresi(ham: Any, kod: str) -> Optional[str]:
    s = (str(ham or "")).strip()
    if not s:
        return None
    p = urlparse(s)
    if len(s) > 500 or p.scheme != "https" or not p.hostname or any(c.isspace() for c in s):
        raise FormHatasi(kod)
    return s


def tanimi_dogrula(veri: Dict[str, Any], mevcut: Optional[Any], asama_anahtarlari: List[str]) -> Dict[str, Any]:
    """Panel gövdesi → sütun değerleri (yalnız verilen alanlar; oluşturmada zorunlular)."""
    sonuc: Dict[str, Any] = {}
    yeni = mevcut is None

    if "ad" in veri or yeni:
        ad = " ".join(str(veri.get("ad") or "").split())
        if not ad:
            raise FormHatasi("ad_gerekli")
        if len(ad) > 120:
            raise FormHatasi("ad_uzun")
        sonuc["ad"] = ad
    if "baslik" in veri:
        b = " ".join(str(veri.get("baslik") or "").split())
        if len(b) > 160:
            raise FormHatasi("baslik_uzun")
        sonuc["baslik"] = b or None
    if "alanlar" in veri or yeni:
        sonuc["alanlar"] = json.dumps(alanlari_duzelt(veri.get("alanlar")))
    if "varsayilan_asama" in veri:
        a = (veri.get("varsayilan_asama") or "").strip() or None
        if a and a not in asama_anahtarlari:
            raise FormHatasi("asama_yok")
        sonuc["varsayilan_asama"] = a
    if "varsayilan_etiketler" in veri:
        try:
            sonuc["varsayilan_etiketler"] = json.dumps(etiketleri_duzelt(veri.get("varsayilan_etiketler")), ensure_ascii=False)
        except ValueError as h:
            raise FormHatasi(str(h))
    if "tesekkur_metni" in veri:
        t = str(veri.get("tesekkur_metni") or "").strip()
        if len(t) > 1000:
            raise FormHatasi("tesekkur_uzun")
        sonuc["tesekkur_metni"] = t or None
    if "yonlendirme_adresi" in veri:
        sonuc["yonlendirme_adresi"] = https_adresi(veri.get("yonlendirme_adresi"), "yonlendirme_https")
    if "izinli_alanlar" in veri:
        sonuc["izinli_alanlar"] = json.dumps(izinli_alanlari_duzelt(veri.get("izinli_alanlar")))
    if "kvkk_metni" in veri or yeni:
        k = str(veri.get("kvkk_metni") or "").strip()
        if len(k) < 10:
            raise FormHatasi("kvkk_metni_gerekli")
        if len(k) > 2000:
            raise FormHatasi("kvkk_metni_uzun")
        sonuc["kvkk_metni"] = k
    if "aydinlatma_baglantisi" in veri:
        sonuc["aydinlatma_baglantisi"] = https_adresi(veri.get("aydinlatma_baglantisi"), "aydinlatma_https")
    if "aktif" in veri:
        sonuc["aktif"] = bool(veri.get("aktif"))

    # KVKK metni ya da bağlantısı değiştiyse onay sürümü artar.
    if not yeni:
        degisti = (
            ("kvkk_metni" in sonuc and sonuc["kvkk_metni"] != mevcut.kvkk_metni)
            or ("aydinlatma_baglantisi" in sonuc and (sonuc["aydinlatma_baglantisi"] or None) != (mevcut.aydinlatma_baglantisi or None))
        )
        if degisti:
            sonuc["kvkk_surum"] = int(mevcut.kvkk_surum or 1) + 1
    return sonuc


def yeni_genel_anahtar() -> str:
    return secrets.token_urlsafe(12).replace("-", "x").replace("_", "y")


def form_sozlugu(f: Any) -> Dict[str, Any]:
    from services.crm import iso

    return {
        "id": f.id, "ad": f.ad, "baslik": f.baslik, "genel_anahtar": f.genel_anahtar,
        "alanlar": alanlari_duzelt(f.alanlar), "varsayilan_asama": f.varsayilan_asama,
        "varsayilan_etiketler": json_liste(f.varsayilan_etiketler), "tesekkur_metni": f.tesekkur_metni,
        "yonlendirme_adresi": f.yonlendirme_adresi, "izinli_alanlar": json_liste(f.izinli_alanlar),
        "kvkk_metni": f.kvkk_metni, "aydinlatma_baglantisi": f.aydinlatma_baglantisi, "kvkk_surum": f.kvkk_surum,
        "aktif": bool(f.aktif), "gonderim_sayisi": f.gonderim_sayisi or 0, "son_gonderim_at": iso(f.son_gonderim_at),
        "created_at": iso(f.created_at), "updated_at": iso(f.updated_at),
    }


# ---------------------------------------------------------------------------
# Köken (Origin) kuralı
# ---------------------------------------------------------------------------
def site_alan_adlari() -> List[str]:
    """Her formda izinli: sitenin kendisi (SITE_PUBLIC_URL) ve mehmetkuru.dev."""
    adlar = ["mehmetkuru.dev"]
    adres = (os.environ.get("SITE_PUBLIC_URL") or "").strip()
    if adres:
        h = (urlparse(adres).hostname or "").lower()
        if h.startswith("www."):
            h = h[4:]
        if h and h not in adlar:
            adlar.append(h)
    return adlar


def koken_izinli_mi(koken: Optional[str], izinli_alanlar: Any) -> bool:
    """`Origin` yoksa True (tarayıcı dışı); "null" ya da listede olmayan → False."""
    if koken is None or koken == "":
        return True
    k = koken.strip().lower()
    if k == "null":
        return False
    p = urlparse(k)
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    host = p.hostname.strip(".")
    adlar = site_alan_adlari() + [str(a).lower() for a in json_liste(izinli_alanlar)]
    for a in adlar:
        a = a[2:] if a.startswith("*.") else a
        if host == a or host.endswith("." + a):
            return True
    return False


# ---------------------------------------------------------------------------
# Süre jetonu
# ---------------------------------------------------------------------------
_YEDEK: Optional[bytes] = None


def _imza_anahtari() -> bytes:
    gizli = os.environ.get("JWT_SECRET_KEY") or ""
    if not gizli:
        global _YEDEK
        if _YEDEK is None:
            _YEDEK = secrets.token_bytes(32)
        return _YEDEK
    return hashlib.sha256(("crm-form:" + gizli).encode()).digest()


def _imza(form_id: int, zaman_ms: int) -> str:
    return hmac.new(_imza_anahtari(), f"{int(form_id)}.{int(zaman_ms)}".encode(), hashlib.sha256).hexdigest()[:32]


def jeton_uret(form_id: int, an: Optional[float] = None) -> str:
    zaman_ms = int((an if an is not None else time.time()) * 1000)
    return f"{int(form_id)}.{zaman_ms}.{_imza(form_id, zaman_ms)}"


def jeton_dogrula(jeton: Any, form_id: int, an: Optional[float] = None) -> None:
    """Geçersizse FormHatasi (jeton_gecersiz | cok_hizli | jeton_suresi_doldu)."""
    parcalar = str(jeton or "").split(".")
    if len(parcalar) != 3 or not parcalar[0].isdigit() or not parcalar[1].isdigit():
        raise FormHatasi("jeton_gecersiz")
    fid, zaman_ms, imza = int(parcalar[0]), int(parcalar[1]), parcalar[2]
    if fid != int(form_id) or not hmac.compare_digest(imza, _imza(fid, zaman_ms)):
        raise FormHatasi("jeton_gecersiz")
    gecen = (an if an is not None else time.time()) - zaman_ms / 1000.0
    if gecen < EN_AZ_SURE_SN:
        raise FormHatasi("cok_hizli")
    if gecen > JETON_OMRU_SN:
        raise FormHatasi("jeton_suresi_doldu")


# ---------------------------------------------------------------------------
# Herkese açık tanım ve gönderim
# ---------------------------------------------------------------------------
def kvkk_ozeti(f: Any) -> str:
    return hashlib.sha256(f"{f.kvkk_metni or ''}\n{f.aydinlatma_baglantisi or ''}".encode("utf-8")).hexdigest()


#: Faz 3Y: formda aydınlatma bağlantısı boşsa sitenin Gizlilik ve KVKK
#: Aydınlatma Metni gösterilir (Türkçe kökte, diğer diller /<dil>/ önekiyle).
#: Gömülen form başka sitelerde de çalıştığı için mutlak adres.
VARSAYILAN_AYDINLATMA = "https://mehmetkuru.dev/gizlilik"


def aydinlatma_adresi(f: Any, dil: str) -> str:
    """Formun aydınlatma bağlantısı; boşsa seçili dildeki /gizlilik sayfası."""
    kayitli = (getattr(f, "aydinlatma_baglantisi", None) or "").strip()
    if kayitli:
        return kayitli
    d = dil_sec(dil)
    return VARSAYILAN_AYDINLATMA if d == "tr" else VARSAYILAN_AYDINLATMA.replace("/gizlilik", f"/{d}/gizlilik")


def acik_tanim(f: Any, dil: str) -> Dict[str, Any]:
    d = dil_sec(dil)
    e = ETIKETLER[d]
    alanlar = alanlari_duzelt(f.alanlar)
    return {
        "anahtar": f.genel_anahtar,
        "baslik": f.baslik or None,
        "dil": d,
        "yon": "rtl" if d == "ar" else "ltr",
        "alanlar": [
            {"ad": ad, "zorunlu": alanlar[ad]["zorunlu"], "etiket": e["alan"][ad], "en_cok": ALAN_SINIRLARI[ad]}
            for ad in ALAN_ADLARI if alanlar[ad]["acik"]
        ],
        "kvkk": {"metin": f.kvkk_metni, "baglanti": aydinlatma_adresi(f, d), "surum": f.kvkk_surum},
        "metinler": {
            "gonder": e["gonder"], "gonderiliyor": e["gonderiliyor"], "aydinlatma": e["aydinlatma"],
            "istege_bagli": e["istege_bagli"], "hata": e["hata"],
        },
        "tesekkur": f.tesekkur_metni or e["tesekkur"],
        "yonlendirme": f.yonlendirme_adresi or None,
        "jeton": jeton_uret(f.id),
        "bal_kupu": BAL_KUPU,
    }


def gonderimi_dogrula(f: Any, govde: Dict[str, Any]) -> Dict[str, str]:
    """Açık alanların temiz değerleri; hata → FormHatasi (alan bilgisiyle)."""
    if govde.get("kvkk_onay") is not True:
        raise FormHatasi("kvkk_gerekli")
    alanlar = alanlari_duzelt(f.alanlar)
    degerler: Dict[str, str] = {}
    for ad in ALAN_ADLARI:
        if not alanlar[ad]["acik"]:
            continue
        ham = govde.get(ad)
        if ham is not None and not isinstance(ham, (str, int, float)):
            raise FormHatasi("alan_gecersiz", alan=ad)
        deger = str(ham if ham is not None else "").strip()
        if ad != "mesaj":
            deger = " ".join(deger.split())
        if len(deger) > ALAN_SINIRLARI[ad]:
            raise FormHatasi("alan_uzun", alan=ad, en_cok=ALAN_SINIRLARI[ad])
        if alanlar[ad]["zorunlu"] and not deger:
            raise FormHatasi("alan_gerekli", alan=ad)
        degerler[ad] = deger
    degerler["email"] = eposta_duzelt(degerler.get("email"))
    if not eposta_gecerli(degerler["email"]):
        raise FormHatasi("eposta_gecersiz", alan="email")
    return degerler
