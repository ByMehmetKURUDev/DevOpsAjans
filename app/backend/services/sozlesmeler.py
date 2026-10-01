"""Faz 3T — sözleşme şablonları, sözleşmeler, basit elektronik imza, bitiş hatırlatması.

Hukuki çerçeve (sayfada ve PDF'te açıkça yazıyor): bu kayıt 5070 sayılı
Kanun anlamında güvenli elektronik imza DEĞİL; taraflar arasında basit
elektronik onay kaydı. Hukuki görüş değildir.

İmza kaydı
----------
* İmzalayanın yazdığı ad soyad (zorunlu), "okudum ve kabul ediyorum" onayı
  (zorunlu), isteğe bağlı el çizimi imza (PNG; Pillow ile yeniden kodlanır —
  meta veri ve bozuk içerik atılır — ve dosya deposuna yazılır).
* Zaman (UTC), IP özeti (tuzlu sha256, ham IP yok), tarayıcı bilgisi (kısaltılmış).
* Metnin SHA-256 özeti: gönderimde hesaplanıyor; imza isteği sayfada
  gösterilen metnin özetini geri yolluyor; ikisi ve kayıttaki metnin o anki
  özeti aynı değilse imza reddediliyor (`metin_degisti`).

Sürümler: imzalı sözleşmenin metni değişmez — değişiklik yeni sürüm açar
(aynı numara, `surum`+1, taslak). Gönderilmiş ama imzalanmamış sözleşmenin
metni değişirse bağlantı iptal edilir, sözleşme taslağa döner.

Kişisel veri ve silme: imzalı sözleşme (ad, IP özeti, tarayıcı, imza görseli)
silinemez — iptal edilebilir; bu kayıt sözleşmenin ispatı (KVKK m.5/2-c, e:
sözleşmenin kurulması/ifası, hakkın tesisi). İmzalanmamış sözleşme silinince
çöp kutusuna düşer (imza alanları zaten boş).
"""

import base64
import hashlib
import io
import json
import logging
import re
import secrets
import unicodedata
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from models.signed_actions import SignedActions
from models.sozlesmeler import HatirlatmaIzleri, SozlesmeSablonlari, Sozlesmeler
from services import belge_ortak as bo
from services.imzali_islem import IslemHatasi
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

TUR = "sozlesme_imza"
DURUMLAR = ("taslak", "gonderildi", "imzalandi", "iptal")
MUSTERI_DURUMLARI = ("gonderildi", "imzalandi", "iptal")
DILLER = ("tr", "en")
GOVDE_SINIRI = 60000
BASLIK_SINIRI = 200
PNG_SINIRI = 300 * 1024
PNG_EN_COK_PIKSEL = (2400, 1200)
TARAYICI_SINIRI = 300
BITIS_ESIKLERI = (30, 7)
SOZLESME_BAGLANTI_GUN = 30

YER_TUTUCU = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")

VARSAYILAN_SABLON_TR = """# Hizmet Sözleşmesi

**Taraflar:** {{ajans_unvani}} ("Ajans") ile {{musteri_adi}} ({{musteri_eposta}}) ("Müşteri").

**Tarih:** {{tarih}} · **Teklif:** {{teklif_no}}

## 1. Konu
Bu sözleşme, {{teklif_no}} numaralı teklifte tanımlanan hizmetlerin Ajans tarafından Müşteri'ye sunulmasına ilişkin koşulları düzenler.

## 2. Bedel ve ödeme
Hizmet bedeli {{toplam}} tutarındadır. Ödeme, düzenlenen faturalarda belirtilen vadelerde yapılır.

## 3. Süre
Sözleşme {{baslangic}} tarihinde başlar; bitiş tarihi {{bitis}}.

## 4. Gizlilik
Taraflar, iş sırasında öğrendikleri bilgileri gizli tutar.

## 5. Genel hükümler
Teklifte yer alan şartlar bu sözleşmenin ayrılmaz parçasıdır.
"""


class SozlesmeHatasi(Exception):
    def __init__(self, durum: int, kod: str, **ek: Any):
        super().__init__(kod)
        self.durum = durum
        self.kod = kod
        self.ek = ek

    def detay(self) -> Dict[str, Any]:
        return {"kod": self.kod, **self.ek}


def _metin(deger: Any, sinir: int) -> str:
    return str(deger or "").replace("\r\n", "\n").strip()[:sinir]


def metin_ozeti(baslik: Optional[str], govde: Optional[str]) -> str:
    """İmzalanan metnin kanonik özeti: NFC, LF satır sonu, baştaki/sondaki boşluk yok."""
    kanonik = unicodedata.normalize("NFC", f"{(baslik or '').strip()}\n\n{(govde or '').replace(chr(13) + chr(10), chr(10)).strip()}")
    return hashlib.sha256(kanonik.encode("utf-8")).hexdigest()


def yer_tutuculari_doldur(govde: str, degerler: Dict[str, Any]) -> str:
    """`{{anahtar}}` → değer. Bilinmeyen yer tutucu olduğu gibi kalır (yönetici görsün)."""

    def degistir(m: "re.Match[str]") -> str:
        anahtar = m.group(1)
        if anahtar in degerler and degerler[anahtar] not in (None, ""):
            return str(degerler[anahtar])
        return m.group(0)

    return YER_TUTUCU.sub(degistir, govde or "")


# ---------------------------------------------------------------------------
# Şablonlar
# ---------------------------------------------------------------------------
async def sablon_yaz(db: AsyncSession, govde: Dict[str, Any], sablon: Optional[SozlesmeSablonlari] = None) -> SozlesmeSablonlari:
    yeni = sablon is None
    sablon = sablon or SozlesmeSablonlari(aktif=True)
    if "baslik" in govde or yeni:
        baslik = _metin(govde.get("baslik"), BASLIK_SINIRI)
        if not baslik:
            raise SozlesmeHatasi(400, "baslik_gerekli")
        sablon.baslik = baslik
    if "govde" in govde or yeni:
        metin = _metin(govde.get("govde"), GOVDE_SINIRI)
        if not metin:
            raise SozlesmeHatasi(400, "govde_gerekli")
        sablon.govde = metin
    if "baslik_en" in govde:
        sablon.baslik_en = _metin(govde.get("baslik_en"), BASLIK_SINIRI) or None
    if "govde_en" in govde:
        sablon.govde_en = _metin(govde.get("govde_en"), GOVDE_SINIRI) or None
    if "aktif" in govde:
        sablon.aktif = bool(govde.get("aktif"))
    if yeni:
        db.add(sablon)
    await db.commit()
    await db.refresh(sablon)
    return sablon


def sablon_sozlugu(s: SozlesmeSablonlari) -> Dict[str, Any]:
    return {
        "id": s.id, "baslik": s.baslik, "govde": s.govde, "baslik_en": s.baslik_en, "govde_en": s.govde_en,
        "aktif": bool(s.aktif), "created_at": bo.iso(s.created_at), "updated_at": bo.iso(s.updated_at),
    }


# ---------------------------------------------------------------------------
# Oluşturma
# ---------------------------------------------------------------------------
async def _degerler(db: AsyncSession, s: Sozlesmeler, teklif: Any = None) -> Dict[str, Any]:
    from services.faturalar import ajans_bilgileri
    from services.pdf_belge import para

    ajans = await ajans_bilgileri(db)
    d: Dict[str, Any] = {
        "musteri_adi": s.taraf_ad or s.taraf_eposta or s.hesap_email,
        "musteri_eposta": s.taraf_eposta or s.hesap_email,
        "tarih": bo.tr_bugun().strftime("%d.%m.%Y"),
        "baslangic": _tr_tarih(s.baslangic) or "—",
        "bitis": _tr_tarih(s.bitis) or "—",
        "ajans_unvani": ajans.get("unvan") or "By Mehmet KURU Dev",
        "sozlesme_no": s.no,
    }
    if teklif is not None:
        d["teklif_no"] = teklif.no
        d["toplam"] = para(teklif.genel_toplam, teklif.para_birimi, s.dil or "tr")
        d["teklif_baslik"] = teklif.baslik
    return d


def _tr_tarih(metin: Optional[str]) -> Optional[str]:
    if not metin:
        return None
    try:
        return date.fromisoformat(metin[:10]).strftime("%d.%m.%Y")
    except ValueError:
        return metin


async def _yeni_no(db: AsyncSession) -> str:
    return await bo.sirali_no(db, Sozlesmeler.no, "SZL")


async def olustur(db: AsyncSession, govde: Dict[str, Any], olusturan: Optional[str], *, commit: bool = True) -> Sozlesmeler:
    """Şablondan (`sablon_id`) ya da doğrudan metinden; `teklif_id` verilirse yer tutucular tekliften."""
    from models.teklifler import Teklifler

    teklif = None
    if govde.get("teklif_id"):
        teklif = (await db.execute(select(Teklifler).where(Teklifler.id == int(govde["teklif_id"])))).scalar_one_or_none()
        if teklif is None:
            raise SozlesmeHatasi(404, "teklif_yok")
    dil = (govde.get("dil") or "tr").strip().lower()
    if dil not in DILLER:
        raise SozlesmeHatasi(400, "dil_gecersiz")
    sablon = None
    if govde.get("sablon_id"):
        sablon = (
            await db.execute(select(SozlesmeSablonlari).where(SozlesmeSablonlari.id == int(govde["sablon_id"])))
        ).scalar_one_or_none()
        if sablon is None:
            raise SozlesmeHatasi(404, "sablon_yok")
    s = Sozlesmeler(durum="taslak", surum=1, dil=dil, olusturan_eposta=bo.eposta_duzelt(olusturan) or None)
    s.hesap_email = bo.eposta_duzelt(govde.get("hesap_email") or (teklif.hesap_email if teklif else None)) or None
    s.taraf_eposta = bo.eposta_duzelt(govde.get("taraf_eposta") or (teklif.aday_eposta if teklif else None)
                                     or s.hesap_email) or None
    s.taraf_ad = _metin(govde.get("taraf_ad") or (teklif.aday_ad if teklif else None), 200) or None
    for alan in ("hesap_email", "taraf_eposta"):
        deger = getattr(s, alan)
        if deger and not bo.eposta_gecerli(deger):
            raise SozlesmeHatasi(400, "eposta_gecersiz")
    if not s.taraf_eposta:
        raise SozlesmeHatasi(400, "alici_gerekli")
    try:
        s.baslangic = bo.tarih_dogrula(govde.get("baslangic")) or bo.tr_bugun().isoformat()
        s.bitis = bo.tarih_dogrula(govde.get("bitis"))
    except ValueError:
        raise SozlesmeHatasi(400, "tarih_gecersiz")
    if s.bitis and s.bitis < s.baslangic:
        raise SozlesmeHatasi(400, "bitis_once")
    s.teklif_id = teklif.id if teklif else None
    s.sablon_id = sablon.id if sablon else None
    if sablon is not None:
        baslik = (sablon.baslik_en if dil == "en" and sablon.baslik_en else sablon.baslik)
        metin = (sablon.govde_en if dil == "en" and sablon.govde_en else sablon.govde)
    else:
        baslik = govde.get("baslik") or (f"Hizmet Sözleşmesi — {teklif.baslik}" if teklif else "")
        metin = govde.get("govde") or (VARSAYILAN_SABLON_TR if teklif else "")
    baslik = _metin(govde.get("baslik") or baslik, BASLIK_SINIRI)
    if not baslik:
        raise SozlesmeHatasi(400, "baslik_gerekli")
    for deneme in range(5):
        s.no = await _yeni_no(db)
        degerler = await _degerler(db, s, teklif)
        s.baslik = yer_tutuculari_doldur(baslik, degerler)[:BASLIK_SINIRI]
        s.govde = _metin(yer_tutuculari_doldur(metin, degerler), GOVDE_SINIRI)
        if not s.govde:
            raise SozlesmeHatasi(400, "govde_gerekli")
        try:
            async with db.begin_nested():
                db.add(s)
                await db.flush()
            break
        except IntegrityError:
            if deneme == 4:
                raise
    s.kok_id = s.id
    await db.flush()
    if commit:
        await db.commit()
        await db.refresh(s)
    return s


async def tekliften_olustur(db: AsyncSession, teklif: Any) -> Sozlesmeler:
    """Teklif kabulünde sözleşme TASLAĞI (aynı işlem; commit ETMEZ)."""
    sablon_id = teklif.sozlesme_sablon_id
    if not sablon_id:
        sablon_id = (
            await db.execute(
                select(SozlesmeSablonlari.id).where(SozlesmeSablonlari.aktif.is_(True)).order_by(SozlesmeSablonlari.id)
            )
        ).scalars().first()
    try:
        return await olustur(
            db,
            {"teklif_id": teklif.id, "sablon_id": sablon_id, "hesap_email": teklif.hesap_email,
             "taraf_eposta": teklif.hesap_email, "taraf_ad": teklif.karar_ad or teklif.aday_ad},
            teklif.olusturan_eposta,
            commit=False,
        )
    except SozlesmeHatasi as h:
        raise IslemHatasi(h.durum, h.kod)


async def getir(db: AsyncSession, sozlesme_id: int) -> Sozlesmeler:
    s = (await db.execute(select(Sozlesmeler).where(Sozlesmeler.id == sozlesme_id))).scalar_one_or_none()
    if s is None:
        raise SozlesmeHatasi(404, "sozlesme_yok")
    return s


# ---------------------------------------------------------------------------
# Düzenleme ve sürüm
# ---------------------------------------------------------------------------
async def _baglantiyi_iptal_et(db: AsyncSession, s: Sozlesmeler) -> None:
    if s.islem_id:
        await db.execute(
            update(SignedActions)
            .where(SignedActions.id == s.islem_id, SignedActions.durum == "bekliyor")
            .values(durum="iptal")
            .execution_options(synchronize_session=False)
        )


async def guncelle(db: AsyncSession, s: Sozlesmeler, govde: Dict[str, Any]) -> Tuple[Sozlesmeler, bool]:
    """Günceller → (kayıt, yeni_surum_mu).

    İmzalı sözleşmede metin/başlık/taraf değişikliği → YENİ SÜRÜM (eski olduğu
    gibi kalır). Yalnız `bitis` (hatırlatma için meta veri, imzalı metnin
    parçası değil) imzalı sürümde de güncellenebilir.
    """
    if s.durum == "iptal":
        raise SozlesmeHatasi(409, "durum_iptal")
    yeni_baslik = _metin(govde["baslik"], BASLIK_SINIRI) if "baslik" in govde else s.baslik
    yeni_govde = _metin(govde["govde"], GOVDE_SINIRI) if "govde" in govde else s.govde
    if not yeni_baslik:
        raise SozlesmeHatasi(400, "baslik_gerekli")
    if not yeni_govde:
        raise SozlesmeHatasi(400, "govde_gerekli")
    metin_degisti = (yeni_baslik != s.baslik) or (yeni_govde != s.govde)
    taraf = {k: govde[k] for k in ("taraf_ad", "taraf_eposta", "hesap_email") if k in govde}
    try:
        baslangic = bo.tarih_dogrula(govde["baslangic"]) if "baslangic" in govde else s.baslangic
        bitis = bo.tarih_dogrula(govde["bitis"]) if "bitis" in govde else s.bitis
    except ValueError:
        raise SozlesmeHatasi(400, "tarih_gecersiz")
    if bitis and baslangic and bitis < baslangic:
        raise SozlesmeHatasi(400, "bitis_once")

    if s.durum == "imzalandi":
        if metin_degisti or taraf or baslangic != s.baslangic:
            yeni = await yeni_surum(db, s, baslik=yeni_baslik, govde=yeni_govde, taraf=taraf,
                                    baslangic=baslangic, bitis=bitis)
            return yeni, True
        s.bitis = bitis
        await db.commit()
        await db.refresh(s)
        return s, False

    for k, v in taraf.items():
        temiz = bo.eposta_duzelt(v) if k != "taraf_ad" else _metin(v, 200)
        if k != "taraf_ad" and temiz and not bo.eposta_gecerli(temiz):
            raise SozlesmeHatasi(400, "eposta_gecersiz")
        setattr(s, k, temiz or None)
    if s.durum == "gonderildi" and (metin_degisti or taraf):
        # Müşteri gördüğünden farklı bir metni imzalamasın.
        await _baglantiyi_iptal_et(db, s)
        s.durum = "taslak"
        s.metin_ozeti = None
        s.islem_id = None
    s.baslik, s.govde, s.baslangic, s.bitis = yeni_baslik, yeni_govde, baslangic, bitis
    await db.commit()
    await db.refresh(s)
    return s, False


async def yeni_surum(
    db: AsyncSession, s: Sozlesmeler, *, baslik: str, govde: str, taraf: Optional[Dict[str, Any]] = None,
    baslangic: Optional[str] = None, bitis: Optional[str] = None,
) -> Sozlesmeler:
    kok_id = s.kok_id or s.id
    son = (
        await db.execute(select(Sozlesmeler.surum).where(Sozlesmeler.kok_id == kok_id).order_by(Sozlesmeler.surum.desc()))
    ).scalars().first() or s.surum or 1
    taraf = taraf or {}
    yeni = Sozlesmeler(
        no=s.no, surum=son + 1, kok_id=kok_id, onceki_id=s.id,
        hesap_email=bo.eposta_duzelt(taraf.get("hesap_email", s.hesap_email)) or None,
        taraf_ad=_metin(taraf.get("taraf_ad", s.taraf_ad), 200) or None,
        taraf_eposta=bo.eposta_duzelt(taraf.get("taraf_eposta", s.taraf_eposta)) or None,
        baslik=baslik, govde=govde, dil=s.dil, sablon_id=s.sablon_id, teklif_id=s.teklif_id,
        baslangic=baslangic or s.baslangic, bitis=bitis if bitis is not None else s.bitis,
        durum="taslak", olusturan_eposta=s.olusturan_eposta,
    )
    db.add(yeni)
    await db.commit()
    await db.refresh(yeni)
    return yeni


async def iptal_et(db: AsyncSession, s: Sozlesmeler) -> Sozlesmeler:
    if s.durum == "iptal":
        raise SozlesmeHatasi(409, "durum_iptal")
    await _baglantiyi_iptal_et(db, s)
    s.durum = "iptal"
    s.iptal_at = bo.simdi()
    await db.commit()
    await db.refresh(s)
    return s


async def sil(db: AsyncSession, s: Sozlesmeler) -> None:
    if s.durum == "imzalandi" or s.imza_at:
        raise SozlesmeHatasi(409, "imzali_silinemez")
    await _baglantiyi_iptal_et(db, s)
    await db.delete(s)
    await db.commit()


# ---------------------------------------------------------------------------
# Gönderim
# ---------------------------------------------------------------------------
def baglanti(jeton: str) -> str:
    return f"{bo.site_adresi()}/sozlesme/{jeton}"


async def gonder(
    db: AsyncSession, s: Sozlesmeler, *, olusturan: Optional[str], gun: Optional[int] = None, eposta_gonder: bool = False
) -> Tuple[str, bool]:
    from services import imzali_islem

    if s.durum not in ("taslak", "gonderildi"):
        raise SozlesmeHatasi(409, f"durum_{s.durum}")
    hedef = bo.eposta_duzelt(s.taraf_eposta or s.hesap_email)
    if not bo.eposta_gecerli(hedef):
        raise SozlesmeHatasi(400, "alici_gerekli")
    await _baglantiyi_iptal_et(db, s)
    await db.commit()
    try:
        jeton, kayit = await imzali_islem.olustur(
            db, TUR, ("sozlesmeler", s.id), hedef, f"{s.no} · {s.baslik}",
            {"sozlesme_id": s.id, "no": s.no, "surum": s.surum}, gun or SOZLESME_BAGLANTI_GUN, olusturan=olusturan,
        )
    except IslemHatasi as h:
        raise SozlesmeHatasi(h.durum, h.kod)
    s.islem_id = kayit.id
    s.metin_ozeti = metin_ozeti(s.baslik, s.govde)
    s.durum = "gonderildi"
    s.gonderildi_at = bo.simdi()
    await db.commit()
    await db.refresh(s)
    adres = baglanti(jeton)
    gitti = False
    if eposta_gonder:
        gitti = await bo.baglantili_bildirim(
            db,
            event_type="sozlesme_imza_bekliyor",
            alici=hedef,
            baslik=f"Sözleşmeniz imzanızı bekliyor: {s.no} / Your contract is awaiting signature",
            govde=(
                f"Merhaba,\n\n{s.baslik} ({s.no}) imzanızı bekliyor. Metni okuyup giriş yapmadan imzalayabilirsiniz:\n"
                f"{adres}\n\nPlease review and sign {s.baslik} ({s.no}), no login needed:\n{adres}\n\n— By Mehmet KURU Dev"
            ),
            baglanti=adres,
            ref_type="sozlesme",
            ref_id=s.id,
            panel_linki="/client?sekme=invoices",
            degerler={"sozlesme_no": s.no},
        )
    return adres, gitti


# ---------------------------------------------------------------------------
# İmza
# ---------------------------------------------------------------------------
async def jetondan(db: AsyncSession, jeton: str) -> Tuple[Sozlesmeler, SignedActions]:
    from services import imzali_islem

    kayit = await imzali_islem.coz(db, jeton)
    if kayit is None or kayit.tur != TUR:
        raise SozlesmeHatasi(404, "bulunamadi")
    s = (await db.execute(select(Sozlesmeler).where(Sozlesmeler.id == kayit.hedef_id))).scalar_one_or_none()
    if s is None:
        raise SozlesmeHatasi(404, "bulunamadi")
    return s, kayit


def imza_gorseli_coz(veri: Optional[str]) -> Optional[bytes]:
    """`data:image/png;base64,...` → yeniden kodlanmış PNG (ya da None). Bozuksa hata."""
    if not veri:
        return None
    metin = veri.strip()
    if metin.startswith("data:"):
        if not metin.startswith("data:image/png;base64,"):
            raise SozlesmeHatasi(400, "imza_gorseli_gecersiz")
        metin = metin.split(",", 1)[1]
    if len(metin) > PNG_SINIRI * 4 // 3 + 16:
        raise SozlesmeHatasi(413, "imza_gorseli_buyuk")
    try:
        ham = base64.b64decode(metin, validate=True)
    except (ValueError, base64.binascii.Error):
        raise SozlesmeHatasi(400, "imza_gorseli_gecersiz")
    if not ham.startswith(b"\x89PNG\r\n\x1a\n") or len(ham) > PNG_SINIRI:
        raise SozlesmeHatasi(400, "imza_gorseli_gecersiz")
    try:
        from PIL import Image

        with Image.open(io.BytesIO(ham)) as g:
            if g.format != "PNG":
                raise SozlesmeHatasi(400, "imza_gorseli_gecersiz")
            if g.width > PNG_EN_COK_PIKSEL[0] or g.height > PNG_EN_COK_PIKSEL[1] or g.width < 10 or g.height < 10:
                raise SozlesmeHatasi(400, "imza_gorseli_gecersiz")
            g.load()
            temiz = g.convert("RGBA")
            # Boş tuval (tamamen saydam) imza sayılmaz.
            if temiz.getchannel("A").getbbox() is None:
                return None
            cikti = io.BytesIO()
            temiz.save(cikti, format="PNG", optimize=True)
            return cikti.getvalue()
    except SozlesmeHatasi:
        raise
    except Exception:  # noqa: BLE001
        raise SozlesmeHatasi(400, "imza_gorseli_gecersiz")


def imza_on_denetim(
    s: Sozlesmeler, *, ad: Optional[str], onay: bool, gosterilen_ozet: Optional[str], imza_png: Optional[str]
) -> Dict[str, Any]:
    if s.durum == "imzalandi":
        raise SozlesmeHatasi(409, "kullanildi")
    if s.durum == "iptal":
        raise SozlesmeHatasi(410, "iptal")
    if s.durum != "gonderildi":
        raise SozlesmeHatasi(409, f"durum_{s.durum}")
    if not onay:
        raise SozlesmeHatasi(400, "onay_gerekli")
    try:
        temiz_ad = bo.ad_duzelt(ad)
    except ValueError:
        raise SozlesmeHatasi(400, "ad_gerekli")
    guncel = metin_ozeti(s.baslik, s.govde)
    if not s.metin_ozeti or guncel != s.metin_ozeti or (gosterilen_ozet or "").strip().lower() != guncel:
        raise SozlesmeHatasi(409, "metin_degisti")
    return {"ad": temiz_ad, "png": imza_gorseli_coz(imza_png), "metin_ozeti": guncel}


async def imzala(
    db: AsyncSession,
    *,
    jeton: Optional[str] = None,
    sozlesme: Optional[Sozlesmeler] = None,
    eposta: Optional[str] = None,
    ad: Optional[str],
    onay: bool,
    gosterilen_ozet: Optional[str],
    imza_png: Optional[str],
    ip_ozeti: Optional[str],
    tarayici: Optional[str],
    kanal: str,
) -> Sozlesmeler:
    from services import imzali_islem

    if jeton is not None:
        s, kayit = await jetondan(db, jeton)
    else:
        s = sozlesme
        if s is None or not s.islem_id:
            raise SozlesmeHatasi(409, "baglanti_yok")
        kayit = (await db.execute(select(SignedActions).where(SignedActions.id == s.islem_id))).scalar_one_or_none()
        if kayit is None:
            raise SozlesmeHatasi(409, "baglanti_yok")
    if kayit.id != s.islem_id:
        raise SozlesmeHatasi(410, "iptal")
    ek = imza_on_denetim(s, ad=ad, onay=onay, gosterilen_ozet=gosterilen_ozet, imza_png=imza_png)
    ek["tarayici"] = (tarayici or "")[:TARAYICI_SINIRI] or None
    ek["kanal"] = kanal
    try:
        if jeton is not None:
            sonuc = await imzali_islem.kullan(db, jeton, "onay", None, ip_ozeti=ip_ozeti, ek=ek)
        else:
            sonuc = await imzali_islem.kullan_id(db, kayit.id, eposta or "", "onay", None, ip_ozeti=ip_ozeti, ek=ek)
    except IslemHatasi as h:
        raise SozlesmeHatasi(h.durum, h.kod)
    await imzali_islem.bildirimleri_gonder(db, sonuc.bildirimler)
    await db.refresh(s)
    return s


async def imza_etkisi(db: AsyncSession, kayit: SignedActions, ek: Dict[str, Any]) -> List[Dict[str, Any]]:
    """`imzali_islem._etkiyi_uygula` içinden: imza kaydını yazar (commit ETMEZ)."""
    from services import dosya_deposu

    s = (await db.execute(select(Sozlesmeler).where(Sozlesmeler.id == kayit.hedef_id))).scalar_one_or_none()
    if s is None:
        raise IslemHatasi(404, "hedef_yok")
    if s.durum != "gonderildi":
        raise IslemHatasi(409, "kullanildi")
    if metin_ozeti(s.baslik, s.govde) != ek.get("metin_ozeti") or s.metin_ozeti != ek.get("metin_ozeti"):
        raise IslemHatasi(409, "metin_degisti")
    if not ek.get("ad"):
        raise IslemHatasi(400, "ad_gerekli")
    png = ek.get("png")
    if png:
        anahtar = f"sozlesmeler/imza/{bo.simdi():%Y/%m}/{secrets.token_hex(16)}.png"
        try:
            s.imza_gorsel_depo = await dosya_deposu.yaz(db, anahtar, png, "image/png")
        except dosya_deposu.DepoHatasi:
            raise IslemHatasi(502, "depo_hatasi")
        s.imza_gorsel_anahtari = anahtar
    s.imza_ad = ek["ad"]
    s.imza_at = bo.simdi()
    s.imza_ip_ozeti = ek.get("ip_ozeti")
    s.imza_tarayici = ek.get("tarayici")
    s.imza_metin_ozeti = ek["metin_ozeti"]
    s.imza_kanali = ek.get("kanal")
    s.durum = "imzalandi"
    await db.flush()
    bildirim = {
        "event_type": "sozlesme_imzalandi",
        "title": f"Sözleşme imzalandı: {s.no} (v{s.surum}) — {s.imza_ad}"[:250],
        "body": f"{s.baslik}\nİmzalayan: {s.imza_ad} ({kayit.alici_eposta})\nMetin özeti: {s.imza_metin_ozeti}",
        "yoneticiye": True,
        "link": "/admin?sekme=sozlesmeler",
        "ref_type": "sozlesme",
        "ref_id": s.id,
    }
    musteri = {
        "event_type": "sozlesme_imzalandi",
        "title": f"Sözleşme imzalandı: {s.no} / Contract signed",
        "body": f"{s.baslik} — {s.imza_ad}. İmzalı kopyayı panelden indirebilirsiniz. / You can download the signed copy from your panel.",
        "alicilar": [{"email": kayit.alici_eposta, "role": "client"}],
        "link": "/client?sekme=invoices",
        "ref_type": "sozlesme",
        "ref_id": s.id,
    }
    return [bildirim, musteri]


async def imza_gorseli(db: AsyncSession, s: Sozlesmeler) -> Optional[bytes]:
    if not s.imza_gorsel_anahtari:
        return None
    from services import dosya_deposu

    try:
        return await dosya_deposu.oku(db, s.imza_gorsel_depo or "veritabani", s.imza_gorsel_anahtari)
    except dosya_deposu.DepoHatasi:
        logger.warning("İmza görseli okunamadı: sözleşme=%s", s.id)
        return None


# ---------------------------------------------------------------------------
# Bitiş hatırlatması (zamanlı görev)
# ---------------------------------------------------------------------------
async def bitis_hatirlatmalari(db: AsyncSession, bugun: Optional[date] = None) -> Dict[str, Any]:
    """İmzalı sözleşmenin bitişine 30 ve 7 gün kala, eşik başına BİR kez (yönetici + müşteri)."""
    from services.notify import admin_recipients, dispatch, render

    bugun = bugun or bo.tr_bugun()
    ust = (bugun + timedelta(days=max(BITIS_ESIKLERI))).isoformat()
    adaylar = (
        await db.execute(
            select(Sozlesmeler).where(
                Sozlesmeler.durum == "imzalandi", Sozlesmeler.bitis.isnot(None),
                Sozlesmeler.bitis >= bugun.isoformat(), Sozlesmeler.bitis <= ust,
            )
        )
    ).scalars().all()
    gonderilmis: Dict[int, set] = {}
    if adaylar:
        for iz in (
            await db.execute(
                select(HatirlatmaIzleri).where(
                    HatirlatmaIzleri.tur == "sozlesme_bitis", HatirlatmaIzleri.ref_id.in_([s.id for s in adaylar])
                )
            )
        ).scalars().all():
            gonderilmis.setdefault(iz.ref_id, set()).add(iz.esik)
    gidecek = []
    for s in adaylar:
        try:
            kalan = (date.fromisoformat(s.bitis[:10]) - bugun).days
        except ValueError:
            continue
        # Kalan gün ≤ eşik: birden çok eşik birden geldiyse (görev çalışmadı) tek bildirim.
        ulasilan = [e for e in BITIS_ESIKLERI if kalan <= e]
        yeni = [e for e in ulasilan if e not in gonderilmis.get(s.id, set())]
        if not yeni:
            continue
        esik = min(yeni)
        try:
            async with db.begin_nested():
                for e in yeni:
                    db.add(HatirlatmaIzleri(tur="sozlesme_bitis", ref_id=s.id, esik=e))
                await db.flush()
        except IntegrityError:
            continue
        gidecek.append((s, esik, kalan))
    await db.commit()
    if not gidecek:
        return {"aday": len(adaylar), "bildirim": 0}
    yoneticiler = await admin_recipients(db)
    gonderilen = 0
    for s, esik, kalan in gidecek:
        tarih = _tr_tarih(s.bitis)
        try:
            baslik, govde = await render(
                db, "sozlesme_bitis",
                f"Sözleşme bitişi yaklaşıyor: {s.no} ({kalan} gün) / Contract ends in {kalan} days",
                (f"{s.baslik} ({s.no}) {tarih} tarihinde bitiyor ({kalan} gün kaldı). Yenileme için bizimle iletişime geçebilirsiniz.\n\n"
                 f"{s.baslik} ({s.no}) ends on {tarih} ({kalan} days left)."),
                {"sozlesme_no": s.no, "kalan": kalan, "tarih": tarih, "esik": esik},
            )
            alicilar = list(yoneticiler)
            musteri = bo.eposta_duzelt(s.hesap_email or s.taraf_eposta)
            for a in alicilar:
                await dispatch(db, event_type="sozlesme_bitis", title=baslik, body=govde, recipients=[a],
                               link="/admin?sekme=sozlesmeler", ref_type="sozlesme", ref_id=s.id)
            if musteri:
                await dispatch(db, event_type="sozlesme_bitis", title=baslik, body=govde,
                               recipients=[{"email": musteri, "role": "client"}],
                               link="/client?sekme=invoices", ref_type="sozlesme", ref_id=s.id)
            gonderilen += 1
        except Exception:  # noqa: BLE001
            logger.exception("Sözleşme bitiş hatırlatması gönderilemedi: %s", s.id)
    return {"aday": len(adaylar), "bildirim": gonderilen}


# ---------------------------------------------------------------------------
# Görünüm ve PDF
# ---------------------------------------------------------------------------
def sozluk(s: Sozlesmeler, *, yonetici: bool = False) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "id": s.id, "no": s.no, "surum": s.surum or 1, "baslik": s.baslik, "govde": s.govde, "dil": s.dil,
        "durum": s.durum, "baslangic": s.baslangic, "bitis": s.bitis, "taraf_ad": s.taraf_ad,
        "metin_ozeti": s.metin_ozeti or metin_ozeti(s.baslik, s.govde),
        "imza_ad": s.imza_ad, "imza_at": bo.iso(s.imza_at), "imza_metin_ozeti": s.imza_metin_ozeti,
        "imza_gorseli_var": bool(s.imza_gorsel_anahtari), "teklif_id": s.teklif_id,
        "gonderildi_at": bo.iso(s.gonderildi_at), "created_at": bo.iso(s.created_at),
    }
    if yonetici:
        d.update({
            "hesap_email": s.hesap_email, "taraf_eposta": s.taraf_eposta, "sablon_id": s.sablon_id,
            "kok_id": s.kok_id, "onceki_id": s.onceki_id, "islem_id": s.islem_id,
            "imza_ip_ozeti": (s.imza_ip_ozeti or "")[:16] or None, "imza_tarayici": s.imza_tarayici,
            "imza_kanali": s.imza_kanali, "iptal_at": bo.iso(s.iptal_at), "olusturan_eposta": s.olusturan_eposta,
        })
    return d


async def pdf(db: AsyncSession, s: Sozlesmeler, dil: Optional[str] = None) -> bytes:
    from services.faturalar import ajans_bilgileri
    from services.pdf_belge import sozlesme_pdf

    veri = sozluk(s, yonetici=True)
    veri["imza_ip_ozeti"] = s.imza_ip_ozeti
    veri["taraf_eposta"] = s.taraf_eposta or s.hesap_email
    return sozlesme_pdf(veri, await ajans_bilgileri(db), await imza_gorseli(db, s), dil or s.dil or "tr")
