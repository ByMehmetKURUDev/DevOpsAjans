"""Denetim kaydı (audit log): kim, ne zaman, hangi kaydı, neyi değiştirdi.

Bağlama yolu — neden oturum olayı?
----------------------------------
Yazma işlemleri tek bir kapıdan geçmiyor: üretilmiş entity router'ları
kendi servis sınıflarını (`services/<tablo>.py`) kullanıyor, ama ödeme,
abonelik, müşteri sitesi, personel, fiyat-satın-al gibi uçlar modelleri
doğrudan değiştiriyor. Servis katmanına ekleseydik on bir ayrı servise ve
bir o kadar router'a dokunmak gerekirdi; yine de doğrudan yazan uçlar
dışarıda kalırdı. `entity_guard` ise yalnız isteği görüyor, eski/yeni
değerleri görmüyor.

Bütün bu yolların ortak noktası SQLAlchemy'nin iş birimi (unit of work):
her değişiklik bir `flush` ile veritabanına iniyor. Bu yüzden kayıt
`Session` sınıfına bağlı tek bir `after_flush` olayıyla tutuluyor:

* `session.new / dirty / deleted` içindeki her nesne için tablo, birincil
  anahtar ve alan bazında eski→yeni farkı (`inspect(obj).attrs[..].history`)
  çıkarılıyor. `after_flush` seçildi (`before_flush` değil): yeni
  kayıtların kimliği ancak INSERT'ten sonra belli oluyor, geçmiş bilgisi
  ise bu noktada hâlâ duruyor.
* Satırlar aynı bağlantıda, aynı işlem içinde bir SAVEPOINT'e yazılıyor.
  Asıl işlem geri alınırsa denetim satırı da geri gidiyor (olmamış bir
  değişikliğin kaydı kalmıyor); denetim yazımı patlarsa yalnız SAVEPOINT
  geri alınıyor, asıl işlem etkilenmiyor.
* Kimin yaptığı istek başına bir `ContextVar`'da duruyor; onu
  `middlewares/denetim_baglami.py` dolduruyor. Jeton yalnızca gerçekten
  yazılacak bir satır olduğunda çözülüyor (okuma isteklerine maliyeti yok).

Kapsam dışı: `delete(Model).where(...)` gibi toplu (Core) ifadeler iş
biriminden geçmediği için yakalanmıyor. Uygulamada bunlar yalnız süresi
dolmuş OIDC durumlarını ve bu tablonun kendi saklama temizliğini siliyor.

Veritabanına dokunmayan önemli işler (ortam ayarları gibi) `denetim_yaz`
ile elle kaydediliyor.
"""

import json
import logging
from contextvars import ContextVar
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

from models.audit_log import AuditLog
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

#: Kaydedilmeyen tablolar: denetim tablosunun kendisi, kendi günlüğü
#: olanlar (access_log), gürültülü/otomatik olanlar.
HARIC_TABLOLAR = frozenset({
    "audit_log", "notifications", "site_analyses", "access_log",
    "analytics_snapshots", "oidc_states",
    # Her gönderimde sayaç/zaman güncelleniyor, anahtar malzemesi taşıyor.
    "push_subscriptions",
    # Faz 2A: zamanlı görevin kendi yazdığı ölçüm/olay/kilit tabloları.
    # Birkaç dakikada bir yüzlerce satır; kimin neyi değiştirdiği sorusuyla
    # ilgisi yok (kesinti geçmişi zaten kendi tablosunda).
    "uptime_olculeri", "uptime_gunluk", "uptime_kesintileri",
    "bitis_bildirimleri", "zamanli_calisma",
    # Faz 2C: dosya içeriği (ikili, MB'larca) ve zamanlı görevin güncellediği
    # SLA saatleri. Dosyanın kendisi (`files`) ve paylaşım bağlantısı kaydediliyor.
    "dosya_icerikleri", "talep_sla",
    # Faz 2B: kişi başına okundu/kapattı ve oy satırları (gürültü; oy
    # verenin kimliği kimseye gösterilmiyor), ekran görüntüsünün ikili
    # içeriği (geri bildirim satırı zaten kaydediliyor) ve aylık revizyon
    # uyarısının tekrar kilidi.
    "duyuru_okumalari", "oneri_oylari", "feedback_attachments", "revizyon_uyarilari",
    # Faz 2D: oturum satırları (her girişte bir satır, son_gorulme güncellemesi;
    # iptaller `services/oturumlar.py`de elle, sid'siz kaydediliyor) ve çöp
    # kutusu (silinen kaydın tam kopyası; silme zaten kaydediliyor, geri alma
    # ve kalıcı silme elle kaydediliyor).
    "oturumlar", "oturum_kesimleri", "cop_kutusu",
    # Faz 3K: hangi tohum kaynağının bir kez eklendiği (teknik iz; kaynağın
    # kendisi `kaynaklar` tablosunda kaydediliyor).
    "kaynak_tohum_izi",
    # Faz 2G: kişi başına "nereye kadar okudu" (her yoklamada ilerleyebilir).
    # Mesajın kendisi (oluşturma/düzenleme/silme) kaydediliyor.
    "konusma_okunma",
    # Faz 2H: SEO/hız ölçüm geçmişi ve uyarı kilidi (zamanlı görev ve "Şimdi
    # tara" yazıyor; tarama sıklığı ayarı `site_izleme`de, o kaydediliyor).
    "site_seo_gecmisi", "site_seo_uyarilari",
    # Faz 3U: yapay zekâ sohbetleri (kişiye özel içerik — denetim kaydına
    # kopyalanmasın; her mesajda bir satır olurdu), günlük sayaç ve tohum izi.
    # Asistan tanımlarının yönetici düzenlemesi (`uzman_asistanlar`) kaydediliyor.
    "asistan_sohbetleri", "asistan_mesajlari", "ai_gunluk_kullanim", "uzman_asistan_tohum_izi",
    # Faz 3B: OAuth state satırları (her "Google ile bağlan" tıklamasında bir
    # satır; teknik iz, oidc_states gibi) ve eşitlemenin yazdığı sorgu/sayfa
    # listeleri. Bağlantının kendisi (`baglantilar`) kaydediliyor — jeton maskeli.
    "baglanti_durumlari", "analitik_listeleri",
    # Faz 3C: CRM zaman çizelgesi (kendisi bir kayıt), işlenmiş kayıt işaretleri ve
    # form gönderimlerinin KVKK onay kayıtları (kendi tablosunda saklanıyor). Aday,
    # aşama ve form tanımı değişiklikleri kaydediliyor.
    "crm_aktiviteler", "crm_bagli_kayitlar", "crm_form_gonderimleri",
    # Faz 3T: hatırlatma ve tekrarlayan fatura dönem kilitleri (zamanlı görevin
    # teknik izi; asıl fatura/sözleşme kayıtları kaydediliyor).
    "hatirlatma_izleri", "tekrarlayan_fatura_kayitlari",
    # Faz 4Q: QR taramaları (herkese açık, her taramada bir satır) ve logo
    # görseli (base64; logo ekleme/kaldırma `dinamik_qr.logo_var` ile kaydediliyor).
    "dinamik_qr_taramalari", "dinamik_qr_logolari",
    # Faz 4K: kart/yorum sayfası olayları (herkese açık, her görüntülemede bir satır),
    # eski slug yönlendirme kilitleri (teknik iz) ve ziyaretçi mesajları (herkese açık
    # formdan; kişisel veri — kendi tablosunda, denetime kopyalanmıyor). Kartın ve
    # sayfanın kendisi ile görselleri kaydediliyor.
    "kartvizit_olaylari", "kartvizit_eski_sluglar", "kartvizit_mesajlari",
})

#: Her güncellemede kendiliğinden değişen, bilgi taşımayan alanlar.
GURULTU_ALANLARI = frozenset({"created_at", "updated_at"})

#: Tabloya özel gürültü: zamanlı görevin her çalışmada yazdığı durum alanları.
#: Yalnız bunlar değiştiyse satır yazılmıyor; ayar değişikliği (adres,
#: aralık, bitiş tarihi, sağlayıcı…) yine kaydediliyor.
TABLO_GURULTU_ALANLARI: Dict[str, frozenset] = {
    "uptime_kontrolleri": frozenset({"son_kontrol_at", "son_durum", "ardisik_hata", "ilk_hata_at"}),
    "site_izleme": frozenset({"alan_kontrol_at", "ssl_kontrol_at", "ssl_bitis", "ssl_hata", "alan_rdap_hata"}),
    # Faz 2B: Kanban'da sürükle-bırak yalnız sırayı değiştiriyorsa satır yok;
    # harcanan saat önbellek (asıl kayıt task_time_entries).
    "project_tasks": frozenset({"sira", "harcanan_saat"}),
    # Faz 2G: her mesajda güncellenen önbellek ve bildirim toplama alanları
    # (durum/konu değişikliği yine kaydediliyor).
    "konusmalar": frozenset({
        "son_mesaj_at", "son_mesaj_id", "son_mesaj_ozet", "son_mesaj_rol",
        "son_client_mesaj_id", "son_admin_mesaj_id", "degisiklik",
        "bildirilen_admin_mesaj_id", "bildirilen_client_mesaj_id", "bildirim_admin_at", "bildirim_client_at",
    }),
    # Faz 3B: eşitlemenin her turda yazdığı zaman/hata alanları (bağlanma,
    # seçim değişikliği, durum değişikliği ve kaldırma yine kaydediliyor).
    "baglantilar": frozenset({"son_esitleme", "son_deneme", "son_hata"}),
    # Faz 3C: puan önbelleği, hatırlatma/bildirim kilitleri ve form sayaçları.
    "crm_adaylar": frozenset({"puan", "puan_ayrinti", "hatirlatma_tarihi", "bildirim_bekliyor", "asama_degisme_at"}),
    "crm_formlar": frozenset({"gonderim_sayisi", "son_gonderim_at"}),
    # Faz 4Q: tarama sayacı (asıl kayıt `dinamik_qr_taramalari`).
    "dinamik_qr": frozenset({"tarama_sayisi", "son_tarama_at"}),
}

#: Adında bunlardan biri geçen alanın değeri "***" olarak saklanıyor.
HASSAS_PARCALAR = ("password", "sifre", "token", "jeton", "secret", "api_key", "anahtar", "kart")

#: Adı tam olarak bunlardan biri olan alan da maskeli (parça olarak aranırsa
#: "consider", "inside" gibi zararsız adları yakalardı). `sid`: oturum
#: kimliği — elinde olan, jetonu olmadan da o oturumun iptal durumunu
#: bilebilir; kayıtta açık görünmemeli.
HASSAS_TAM_ADLAR = frozenset({"sid"})

#: Uzun değerler (ham yanıtlar, gövdeler) bu uzunlukta kesiliyor.
DEGER_SINIRI = 200
OZET_SINIRI = 200

ISLEMLER = ("olustur", "guncelle", "sil", "giris", "onay", "odeme", "diger")
ROLLER = ("admin", "client", "sistem", "anonim")

#: Kaydın "adı" gibi okunabilecek alanlar; özetin başına ilk dolu olan yazılıyor.
ETIKET_ALANLARI = (
    "invoice_no", "title", "baslik", "name", "ad", "subject", "konu", "key",
    "alan_adi", "domain", "slug", "kod", "modul_anahtari", "email", "client_email",
)


# ---------------------------------------------------------------------------
# İstek bağlamı (kim yapıyor?)
# ---------------------------------------------------------------------------


class DenetimBaglami:
    """Bir isteğin denetim bilgisi. Jeton ilk ihtiyaçta çözülüyor."""

    __slots__ = ("_istek", "_cozuldu", "aktor_eposta", "aktor_rol", "ip_ozeti", "istek_yolu")

    def __init__(self, istek: Any = None, *, aktor_eposta: Optional[str] = None, aktor_rol: Optional[str] = None):
        self._istek = istek
        self._cozuldu = istek is None
        self.aktor_eposta = aktor_eposta
        self.aktor_rol = aktor_rol or ("sistem" if istek is None else None)
        self.ip_ozeti: Optional[str] = None
        self.istek_yolu: Optional[str] = None

    def coz(self) -> "DenetimBaglami":
        if self._cozuldu:
            return self
        self._cozuldu = True
        istek = self._istek
        try:
            from dependencies.kayit_sahipligi import _yonetici_mi
            from utils.istemci_ip import ip_ozeti, istemci_ip

            yol = istek.url.path
            self.istek_yolu = f"{istek.method} {yol}"[:OZET_SINIRI]
            self.ip_ozeti = ip_ozeti(istemci_ip(istek))
            if self.aktor_rol is None:
                kullanici, yonetici = _yonetici_mi(istek)
                if kullanici is not None:
                    self.aktor_eposta = (kullanici.email or "").strip().lower() or None
                    self.aktor_rol = "admin" if yonetici else "client"
                elif "/webhook" in yol:
                    # Ödeme sağlayıcısının bildirimi: bir kişi değil, sistem.
                    self.aktor_rol = "sistem"
                else:
                    self.aktor_rol = "anonim"
        except Exception:  # noqa: BLE001 - denetim asıl işi bozmamalı
            logger.exception("Denetim bağlamı çözülemedi")
            self.aktor_rol = self.aktor_rol or "anonim"
        return self


_BAGLAM: ContextVar[Optional[DenetimBaglami]] = ContextVar("denetim_baglami", default=None)


def baglam_kur(istek: Any):
    """İstek başında çağrılır; `baglam_birak` için jeton döndürür."""
    return _BAGLAM.set(DenetimBaglami(istek))


def baglam_birak(jeton) -> None:
    try:
        _BAGLAM.reset(jeton)
    except (ValueError, RuntimeError):  # farklı bağlamda sıfırlama — yok say
        pass


def aktor_ata(eposta: Optional[str], rol: str = "client") -> None:
    """Bu isteğin geri kalanındaki yazımların aktörünü elle belirler.

    Oturumsuz ama kimliği başka yoldan bilinen işlemler için: imzalı işlem
    bağlantısını (`/islem/<jeton>`) açan kişi oturum açmamış olsa da
    bağlantının gönderildiği adres belli. Bu çağrıdan sonra düşen denetim
    satırları "anonim" yerine o e-postayla yazılıyor. IP ve istek yolu
    istekten çözülmeye devam ediyor.
    """
    baglam = _BAGLAM.get()
    if baglam is None:
        # İstek dışı (test, betik): bağlamı bu görev için kur.
        baglam = DenetimBaglami()
        _BAGLAM.set(baglam)
    baglam.coz()
    baglam.aktor_eposta = (eposta or "").strip().lower() or None
    baglam.aktor_rol = rol if rol in ROLLER else "client"


def _gecerli_baglam() -> DenetimBaglami:
    baglam = _BAGLAM.get()
    return baglam.coz() if baglam is not None else DenetimBaglami()


# ---------------------------------------------------------------------------
# Değer biçimleme, maske, fark
# ---------------------------------------------------------------------------


#: Adında hassas bir parça geçse de gizli bilgi taşımayan alanlar
#: (`modul_anahtari` bir modül adı, "anahtar" parolası değil).
HASSAS_OLMAYAN_ALANLAR = frozenset({"modul_anahtari", "anahtar_kelime"})


def hassas_mi(alan: str) -> bool:
    ad = (alan or "").lower()
    if ad in HASSAS_OLMAYAN_ALANLAR:
        return False
    if ad in HASSAS_TAM_ADLAR:
        return True
    return any(parca in ad for parca in HASSAS_PARCALAR)


def _jsonla(deger: Any) -> Any:
    """Değeri JSON'a yazılabilir, kısa bir biçime çevirir."""
    if deger is None or isinstance(deger, bool):
        return deger
    if isinstance(deger, int):
        return deger
    if isinstance(deger, float):
        return deger if deger == deger and deger not in (float("inf"), float("-inf")) else str(deger)
    if isinstance(deger, Decimal):
        return float(deger)
    if isinstance(deger, (datetime, date)):
        return deger.isoformat()
    if isinstance(deger, (bytes, bytearray)):
        return f"<{len(deger)} bayt>"
    if isinstance(deger, (dict, list, tuple)):
        try:
            metin = json.dumps(deger, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            metin = str(deger)
    else:
        metin = str(deger)
    if len(metin) > DEGER_SINIRI:
        return metin[: DEGER_SINIRI - 1] + "…"
    return metin


def _maskele(fark: Dict[str, List[Any]], ek_hassas: Iterable[str] = ()) -> Dict[str, List[Any]]:
    ekler = {a.lower() for a in ek_hassas}
    sonuc: Dict[str, List[Any]] = {}
    for alan, (eski, yeni) in fark.items():
        if hassas_mi(alan) or alan.lower() in ekler:
            sonuc[alan] = [None if eski is None else "***", None if yeni is None else "***"]
        else:
            sonuc[alan] = [_jsonla(eski), _jsonla(yeni)]
    return sonuc


def fark_hesapla(
    once: Optional[Dict[str, Any]],
    sonra: Optional[Dict[str, Any]],
    ek_hassas: Iterable[str] = (),
) -> Dict[str, List[Any]]:
    """Yalnız değişen alanlar: {"alan": [eski, yeni]} — hassaslar maskeli."""
    once = once or {}
    sonra = sonra or {}
    ham: Dict[str, List[Any]] = {}
    for alan in list(once.keys()) + [k for k in sonra.keys() if k not in once]:
        eski, yeni = once.get(alan), sonra.get(alan)
        if eski != yeni:
            ham[alan] = [eski, yeni]
    return _maskele(ham, ek_hassas)


def _kisalt(metin: str, sinir: int = OZET_SINIRI) -> str:
    metin = " ".join((metin or "").split())
    return metin if len(metin) <= sinir else metin[: sinir - 1] + "…"


# ---------------------------------------------------------------------------
# Oturum olayı
# ---------------------------------------------------------------------------


def _islem_belirle(tablo: str, tur: str, fark: Dict[str, List[Any]]) -> str:
    """Genel olustur/guncelle/sil'i, anlamı belli birkaç durumda inceltir."""

    def yeni(alan: str) -> Any:
        return fark.get(alan, [None, None])[1]

    if tablo == "payments" and "durum" in fark and yeni("durum") == "odendi":
        return "odeme"
    if tablo == "invoices" and "status" in fark and yeni("status") == "paid":
        return "odeme"
    if tablo == "client_sites" and tur == "guncelle" and "bakim_izni" in fark:
        return "onay"
    if tablo == "users" and tur == "guncelle" and "last_login" in fark and set(fark) <= {"last_login", "email", "name"}:
        return "giris"
    return tur


def _etiket(sozluk: Dict[str, Any]) -> str:
    for alan in ETIKET_ALANLARI:
        deger = sozluk.get(alan)
        if deger not in (None, "") and not hassas_mi(alan):
            return _kisalt(str(deger), 80)
    return ""


def _ozet_uret(tur: str, etiket: str, fark: Dict[str, List[Any]]) -> str:
    if tur in ("olustur", "sil") or not fark:
        return _kisalt(etiket)
    alanlar = ", ".join(fark.keys())
    return _kisalt(f"{etiket} · {alanlar}" if etiket else alanlar)


def _nesne_satiri(obj: Any, tur: str, baglam: DenetimBaglami) -> Optional[Dict[str, Any]]:
    durum = inspect(obj)
    mapper = durum.mapper
    tablo = getattr(mapper.local_table, "name", None) or ""
    if not tablo or tablo in HARIC_TABLOLAR:
        return None

    pk_anahtarlari = [mapper.get_property_by_column(k).key for k in mapper.primary_key]
    sozluk = durum.dict  # yüklenmiş değerler; burada tembel yükleme tetiklenmiyor

    fark: Dict[str, List[Any]] = {}
    tablo_gurultu = TABLO_GURULTU_ALANLARI.get(tablo, frozenset())
    for ozellik in mapper.column_attrs:
        alan = ozellik.key
        if alan in GURULTU_ALANLARI or alan in pk_anahtarlari or alan in tablo_gurultu:
            continue
        if tur == "olustur":
            deger = sozluk.get(alan)
            if deger is not None:
                fark[alan] = [None, deger]
        elif tur == "sil":
            deger = sozluk.get(alan)
            if deger is not None:
                fark[alan] = [deger, None]
        else:
            gecmis = durum.attrs[alan].history
            if not gecmis.added and not gecmis.deleted:
                continue
            eski = gecmis.deleted[0] if gecmis.deleted else None
            yeni = gecmis.added[0] if gecmis.added else None
            if eski == yeni:
                continue
            fark[alan] = [eski, yeni]

    if tur == "guncelle" and not fark:
        return None

    islem = _islem_belirle(tablo, tur, fark)
    kimlik = ",".join(str(sozluk.get(k)) for k in pk_anahtarlari if sozluk.get(k) is not None) or None

    aktor_eposta, aktor_rol = baglam.aktor_eposta, baglam.aktor_rol or "sistem"
    if islem == "giris":
        # Giriş anında istekte henüz jeton yok: aktör, giriş yapan kullanıcı.
        aktor_eposta = (str(sozluk.get("email") or "").strip().lower()) or aktor_eposta
        aktor_rol = "admin" if sozluk.get("role") == "admin" else "client"

    ilgili = sozluk.get("client_email") if "client_email" in sozluk else None
    if tablo == "users":
        ilgili = sozluk.get("email")
    elif ilgili is None and "musteri_eposta" in sozluk:
        # Kredi defteri gibi sahibini `musteri_eposta` ile tutan tablolar.
        ilgili = sozluk.get("musteri_eposta")
    elif ilgili is None and "hesap_email" in sozluk:
        # Faz 2E — hesap ekibi: değişiklik hesabın sahibini ilgilendiriyor.
        ilgili = sozluk.get("hesap_email")
    ilgili = (str(ilgili).strip().lower() or None) if ilgili else None

    maskeli = _maskele(fark)
    return {
        "aktor_eposta": aktor_eposta,
        "aktor_rol": aktor_rol,
        "islem": islem,
        "tablo": tablo,
        "kayit_id": kimlik[:64] if kimlik else None,
        "ozet": _ozet_uret(tur, _etiket(sozluk), fark),
        "degisiklik_json": json.dumps(maskeli, ensure_ascii=False) if maskeli else None,
        "ip_ozeti": baglam.ip_ozeti,
        "istek_yolu": baglam.istek_yolu,
        "ilgili_eposta": ilgili,
    }


def _degisiklik_satirlari(session: Session) -> List[Dict[str, Any]]:
    satirlar: List[Dict[str, Any]] = []
    baglam: Optional[DenetimBaglami] = None
    for tur, kume in (("olustur", session.new), ("guncelle", session.dirty), ("sil", session.deleted)):
        for obj in list(kume):
            if isinstance(obj, AuditLog):
                continue
            if baglam is None:
                baglam = _gecerli_baglam()
            satir = _nesne_satiri(obj, tur, baglam)
            if satir is not None:
                satirlar.append(satir)
    return satirlar


def _ekleme_sorgusu():
    """Ayrı fonksiyon: testler yazımı bilerek patlatabilsin."""
    return AuditLog.__table__.insert()


def _satirlari_yaz(session: Session, satirlar: List[Dict[str, Any]]) -> bool:
    """Satırları oturumun işleminde, bir SAVEPOINT içinde yazar.

    Hata olursa yalnız SAVEPOINT geri alınıyor; asıl işlem sürüyor.
    """
    if not satirlar:
        return True
    try:
        baglanti = session.connection()
        with baglanti.begin_nested():
            baglanti.execute(_ekleme_sorgusu(), satirlar)
        return True
    except Exception:  # noqa: BLE001 - denetim asıl işi ASLA bozmamalı
        logger.exception("Denetim kaydı yazılamadı (%d satır)", len(satirlar))
        return False


@event.listens_for(Session, "after_flush")
def _flush_sonrasi(session: Session, _flush_baglami) -> None:
    if session.info.get("denetim_kapali"):
        return
    try:
        satirlar = _degisiklik_satirlari(session)
    except Exception:  # noqa: BLE001
        logger.exception("Denetim farkı çıkarılamadı")
        return
    _satirlari_yaz(session, satirlar)


# ---------------------------------------------------------------------------
# Elle kayıt
# ---------------------------------------------------------------------------


def _aktor_coz(aktor: Any, request: Any) -> Tuple[Optional[str], str]:
    if aktor is not None:
        if isinstance(aktor, str):
            eposta = aktor.strip().lower() or None
            rol = None
        elif isinstance(aktor, dict):
            eposta = (aktor.get("email") or aktor.get("eposta") or "").strip().lower() or None
            rol = aktor.get("rol") or aktor.get("role")
        else:
            eposta = (getattr(aktor, "email", "") or "").strip().lower() or None
            rol = getattr(aktor, "role", None)
        if rol == "admin":
            return eposta, "admin"
        if rol in ROLLER:
            return eposta, rol
        return eposta, "client" if eposta else "sistem"

    if request is not None:
        from dependencies.kayit_sahipligi import _yonetici_mi

        kullanici, yonetici = _yonetici_mi(request)
        if kullanici is not None:
            return (kullanici.email or "").strip().lower() or None, "admin" if yonetici else "client"
        return None, "anonim"

    baglam = _gecerli_baglam()
    return baglam.aktor_eposta, baglam.aktor_rol or "sistem"


async def denetim_yaz(
    db,
    *,
    request: Any = None,
    aktor: Any = None,
    islem: str,
    tablo: str,
    kayit_id: Any = None,
    ozet: str = "",
    once: Optional[Dict[str, Any]] = None,
    sonra: Optional[Dict[str, Any]] = None,
    commit: bool = False,
    maskele: Iterable[str] = (),
) -> bool:
    """Tek bir denetim satırını elle yazar (oturum olayının görmediği işler).

    Farkı kendisi hesaplıyor (yalnız değişen alanlar), hassas alanları ve
    `maskele` ile verilenleri "***" yapıyor. Satır `db`'nin işleminde bir
    SAVEPOINT'e yazılıyor: asıl işlem geri alınırsa o da gidiyor.
    `commit=True` ise işlem hemen onaylanıyor.

    Hiçbir koşulda hata fırlatmaz; yazamazsa loglar ve False döner.
    """
    try:
        aktor_eposta, aktor_rol = _aktor_coz(aktor, request)
        baglam = _gecerli_baglam()
        ip, yol = baglam.ip_ozeti, baglam.istek_yolu
        if request is not None:
            from utils.istemci_ip import ip_ozeti, istemci_ip

            ip = ip_ozeti(istemci_ip(request))
            yol = f"{request.method} {request.url.path}"[:OZET_SINIRI]

        fark = fark_hesapla(once, sonra, maskele)
        satir = {
            "aktor_eposta": aktor_eposta,
            "aktor_rol": aktor_rol,
            "islem": islem if islem in ISLEMLER else "diger",
            "tablo": (tablo or "")[:64],
            "kayit_id": str(kayit_id)[:64] if kayit_id is not None else None,
            "ozet": _kisalt(ozet or ""),
            "degisiklik_json": json.dumps(fark, ensure_ascii=False) if fark else None,
            "ip_ozeti": ip,
            "istek_yolu": yol,
            "ilgili_eposta": None,
        }
        yazildi = await db.run_sync(lambda oturum: _satirlari_yaz(oturum, [satir]))
        if commit:
            await db.commit()
        return bool(yazildi)
    except Exception:  # noqa: BLE001 - denetim asıl işi ASLA bozmamalı
        logger.exception("denetim_yaz başarısız: %s/%s", tablo, islem)
        return False
