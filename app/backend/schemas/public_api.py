"""Faz 4A — herkese açık API'nin (`/api/public/v1`) kararlı yanıt ve girdi şemaları.

İç tablo alanları olduğu gibi dökülmüyor: her kaynağın ne döndürdüğü burada
sabit. Kişisel veri bilinçli seçildi — örneğin destek mesajında yazanın
e-postası, menü siparişinde müşterinin adı/adresi, QR kaydında Wi-Fi parolası,
görevde atanan personel YOK. Zamanlar ISO 8601, UTC (`Z`).

Bu dosyadaki modeller OpenAPI belgesini (`/api/public/v1/openapi.json`) ve
MCP araçlarının çıktısını da tanımlıyor; alan eklemek geriye uyumlu, alan
silmek/yeniden adlandırmak değil (sürüm: v1).
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

ZAMAN = "ISO 8601, UTC (ör. 2026-10-01T12:00:00Z)"


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Hata(_Model):
    kod: str = Field(description="Kararlı, makinece okunur hata kodu (ör. `kapsam_yetersiz`).")
    mesaj: str = Field(description="İnsan için açıklama (değişebilir; koda göre karar verin).")


class HataYaniti(_Model):
    hata: Hata


class AnahtarBilgisi(_Model):
    ad: str
    onek: str = Field(description="Anahtarın görünür öneki (mk_live_XXXXXXXX…).")
    kapsamlar: List[str]
    son_kullanma: Optional[str] = Field(None, description=ZAMAN)


class HesapOzeti(_Model):
    sahip: Literal["ajans", "musteri"] = Field(description="Anahtar ajansın mı (bütün hesaplar) müşterinin mi.")
    hesap: Optional[str] = Field(None, description="Müşteri hesabı (e-posta); ajans anahtarında boş.")
    anahtar: AnahtarBilgisi
    sayilar: dict = Field(default_factory=dict, description="Kapsamdaki kaynakların kayıt sayıları.")


class Proje(_Model):
    id: int
    baslik: str
    kategori: Optional[str] = None
    aciklama: Optional[str] = None
    durum: Optional[str] = None
    asama: Optional[str] = Field(None, description="Proje aşaması (ör. kesif, tasarim, gelistirme, test, yayin).")
    ilerleme: Optional[int] = Field(None, description="Yüzde (0–100).")
    hesap: Optional[str] = Field(None, description="Müşteri hesabı (e-posta).")
    olusturma: Optional[str] = Field(None, description=ZAMAN)
    guncelleme: Optional[str] = Field(None, description=ZAMAN)


class Gorev(_Model):
    id: int
    proje_id: int
    baslik: str
    aciklama: Optional[str] = None
    durum: Literal["yapilacak", "suruyor", "incelemede", "tamam"]
    oncelik: Literal["dusuk", "normal", "yuksek", "acil"]
    bitis_tarihi: Optional[str] = Field(None, description="YYYY-MM-DD")
    kilometre_tasi: bool = False
    musteriye_gorunur: Optional[bool] = Field(None, description="Yalnız ajans anahtarında dolu.")
    tamamlandi_at: Optional[str] = Field(None, description=ZAMAN)
    olusturma: Optional[str] = Field(None, description=ZAMAN)
    guncelleme: Optional[str] = Field(None, description=ZAMAN)


class GorevOlustur(_Model):
    proje_id: int
    baslik: str = Field(min_length=1, max_length=200)
    aciklama: Optional[str] = Field(None, max_length=4000)
    oncelik: Literal["dusuk", "normal", "yuksek", "acil"] = "normal"
    bitis_tarihi: Optional[str] = Field(None, description="YYYY-MM-DD")
    durum: Optional[Literal["yapilacak", "suruyor", "incelemede", "tamam"]] = Field(
        None, description="Yalnız ajans anahtarı; müşteri anahtarında her zaman `yapilacak`."
    )
    musteriye_gorunur: Optional[bool] = Field(
        None, description="Yalnız ajans anahtarı (varsayılan hayır); müşteri anahtarıyla açılan görev hep görünür."
    )


class GorevGuncelle(_Model):
    baslik: Optional[str] = Field(None, min_length=1, max_length=200)
    aciklama: Optional[str] = Field(None, max_length=4000)
    oncelik: Optional[Literal["dusuk", "normal", "yuksek", "acil"]] = None
    bitis_tarihi: Optional[str] = Field(None, description="YYYY-MM-DD; boş metin tarihi kaldırır.")
    durum: Optional[Literal["yapilacak", "suruyor", "incelemede", "tamam"]] = None


class Fatura(_Model):
    id: int
    no: str
    hesap: Optional[str] = None
    aciklama: Optional[str] = None
    tutar: float
    para_birimi: str = "TRY"
    durum: Optional[str] = Field(None, description="unpaid | paid | overdue | kismi_odendi | cancelled | iade | draft (yalnız ajans)…")
    tur: Optional[str] = None
    duzenleme_tarihi: Optional[str] = None
    vade_tarihi: Optional[str] = None
    ara_toplam: Optional[float] = None
    kdv_toplam: Optional[float] = None
    olusturma: Optional[str] = Field(None, description=ZAMAN)
    guncelleme: Optional[str] = Field(None, description=ZAMAN)


class DestekMesaji(_Model):
    id: int
    yazan: Literal["musteri", "ajans", "otomatik"]
    mesaj: str
    olusturma: Optional[str] = Field(None, description=ZAMAN)


class DestekTalebi(_Model):
    id: int
    konu: str
    mesaj: str = Field(description="Talebin ilk mesajı.")
    durum: Optional[str] = Field(None, description="open | answered | closed …")
    oncelik: Optional[str] = None
    proje_id: Optional[int] = None
    hesap: Optional[str] = None
    kaynak: Optional[str] = None
    son_mesaj_at: Optional[str] = Field(None, description=ZAMAN)
    olusturma: Optional[str] = Field(None, description=ZAMAN)
    guncelleme: Optional[str] = Field(None, description=ZAMAN)
    mesajlar: Optional[List[DestekMesaji]] = Field(None, description="Yalnız tekil uçta.")


class DestekOlustur(_Model):
    konu: str = Field(min_length=1, max_length=200)
    mesaj: str = Field(min_length=1, max_length=10000)
    oncelik: Literal["dusuk", "normal", "yuksek", "acil"] = "normal"
    proje_id: Optional[int] = None
    hesap: Optional[str] = Field(None, description="Yalnız ajans anahtarı: talebin açılacağı müşteri hesabı (zorunlu).")


class DestekYanit(_Model):
    mesaj: str = Field(min_length=1, max_length=10000)


class Aday(_Model):
    id: int
    ad: str
    firma: Optional[str] = None
    email: Optional[str] = None
    telefon: Optional[str] = None
    kaynak: Optional[str] = None
    asama: Optional[str] = None
    deger_tahmini: Optional[float] = None
    para_birimi: Optional[str] = None
    olusturma: Optional[str] = Field(None, description=ZAMAN)
    guncelleme: Optional[str] = Field(None, description=ZAMAN)


class AdayOlustur(_Model):
    ad: str = Field(min_length=1, max_length=120)
    firma: Optional[str] = Field(None, max_length=160)
    email: Optional[str] = Field(None, max_length=254)
    telefon: Optional[str] = Field(None, max_length=40)
    deger_tahmini: Optional[float] = Field(None, ge=0, le=1e12)
    para_birimi: Literal["TRY", "USD", "EUR", "GBP"] = "TRY"
    notlar: Optional[str] = Field(None, max_length=10000)


class QrKodu(_Model):
    id: int
    ad: str
    tur: str
    kod: str
    kisa_adres: Optional[str] = None
    aktif: bool
    durum: str = Field(description="aktif | pasif | engelli | suresi_doldu | limit_doldu")
    tarama_sayisi: int
    son_tarama_at: Optional[str] = Field(None, description=ZAMAN)
    hesap: Optional[str] = None
    olusturma: Optional[str] = Field(None, description=ZAMAN)
    guncelleme: Optional[str] = Field(None, description=ZAMAN)


class Menu(_Model):
    id: int
    ad: str
    slug: str
    duzen: str = Field(description="menu | katalog")
    aktif: bool
    adres: Optional[str] = None
    hesap: Optional[str] = None
    olusturma: Optional[str] = Field(None, description=ZAMAN)
    guncelleme: Optional[str] = Field(None, description=ZAMAN)


class MenuSiparisi(_Model):
    id: int
    siparis_no: str
    magaza_id: int
    durum: str = Field(description="yeni | hazirlaniyor | teslim_edildi | iptal")
    teslimat: str = Field(description="gel_al | paket | masada")
    masa: Optional[str] = None
    kalem_sayisi: int
    ara_toplam_kurus: int
    indirim_kurus: int
    paket_ucreti_kurus: int
    toplam_kurus: int
    para_birimi: str
    olusturma: Optional[str] = Field(None, description=ZAMAN)
    guncelleme: Optional[str] = Field(None, description=ZAMAN)


def _sayfa(ad: str, oge: type):
    from pydantic import create_model

    return create_model(
        ad,
        __base__=_Model,
        veri=(List[oge], ...),
        sonraki_cursor=(Optional[str], Field(None, description="Sonraki sayfa için `cursor`; son sayfada boş.")),
        daha_var=(bool, ...),
    )


ProjeSayfasi = _sayfa("ProjeSayfasi", Proje)
GorevSayfasi = _sayfa("GorevSayfasi", Gorev)
FaturaSayfasi = _sayfa("FaturaSayfasi", Fatura)
DestekSayfasi = _sayfa("DestekSayfasi", DestekTalebi)
AdaySayfasi = _sayfa("AdaySayfasi", Aday)
QrSayfasi = _sayfa("QrSayfasi", QrKodu)
MenuSayfasi = _sayfa("MenuSayfasi", Menu)
SiparisSayfasi = _sayfa("SiparisSayfasi", MenuSiparisi)
