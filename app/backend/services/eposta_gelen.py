"""Faz 2F — Gelen e-postadan destek talebi (sağlayıcıdan bağımsız çekirdek).

Giriş: `isle(db, ileti)`; `ileti` sözlüğü
    gonderen, gonderen_ad, alicilar, konu, metin, html, message_id,
    in_reply_to, references, basliklar, ekler:[{ad, tur, boyut,
    icerik_bytes | icerik (base64) | indirme_url}]
Uçlar (`routers/destek_eposta.py`) sağlayıcının biçimini buna çeviriyor:
genel HMAC imzalı JSON ve Resend'in `email.received` webhook'u.

Akış
----
1. **Bir kez işleme (idempotent)**: `gelen_epostalar.message_id` benzersiz.
   Satır ÖNCE "isleniyor" olarak yazılıp onaylanıyor; aynı ileti ikinci kez
   gelirse (sağlayıcı yeniden denedi, iki istek yarıştı) ikinci talep
   açılmıyor. "hata" durumundaki (ya da 10 dakikadır "isleniyor"da kalmış)
   ileti yeniden gelirse yeniden işleniyor — yeniden deneme bunun için.
2. **Döngü/spam koruması** (talep AÇMA, yalnız kayıt): `Auto-Submitted`
   (no dışında), `Precedence: bulk/junk/list/auto_reply`, `X-Autoreply`,
   `X-Autorespond`, liste iletileri (`List-Id`), "Out of office" konuları,
   kendi gönderen adresimiz ve gelen adresimiz, `mailer-daemon`, `postmaster`,
   `noreply` türevleri. Aynı göndericiden saatte en çok `SAATLIK_SINIR` ileti.
3. **Eşleştirme**: konuda `[#T-<id>]` belirteci ya da In-Reply-To/References
   içinde BİZİM kaydettiğimiz bir Message-ID (`talep_eposta_kimlikleri`) →
   o talep. Gönderen talebin sahibi DEĞİLSE mesaj o talebe EKLENMİYOR: ayrı,
   "doğrulanmadı" işaretli yeni talep açılıyor ve yöneticiye not düşülüyor.
   Neden: "From" başlığı kolayca taklit edilir; belirteç + sahip eşleşmesi
   olmadan başkasının yazışmasına (ve oradan müşteriye giden e-postalara)
   yabancı metin sokulamasın. Yeni talep ayrı durduğu için sahibin
   yazışmasına hiçbir şey sızmıyor; yönetici isterse elle taşır.
   Kapalı talebe yanıt gelirse talep yeniden açılıyor (panel akışıyla aynı).
4. **Yeni talep**: gönderen kayıtlı müşteriyse (kullanıcı hesabı ya da
   projesi var) ona bağlı; değilse `dogrulanmadi=True`, `kaynak="eposta"`,
   yöneticiye bildirim, OTOMATİK CEVAP YOK.
5. **Metin**: düz metin tercih; yalnız HTML varsa güvenli temizleyiciden
   (`services/guvenli_html.temizle`) geçirilip metne çevriliyor. Alıntılanmış
   eski yazışma kırpılıyor.
6. **Ekler**: izinli türler (resim, pdf, office, txt/csv, zip — içerik imzası
   da doğrulanıyor), tek dosya ≤ 10 MB, ileti başına ≤ 10; aşanlar atlanıp
   mesaja not düşülüyor. `services/dosyalar.dosya_kaydet` ile kalıcı depoya.
"""

import base64
import binascii
import hashlib
import hmac
import html as html_mod
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

SAATLIK_SINIR = 20
EK_SINIRI_BAYT = 10 * 1024 * 1024
EK_SAYISI_SINIRI = 10
IMZA_TOLERANSI_SN = 5 * 60
ISLENIYOR_ZAMAN_ASIMI = timedelta(minutes=10)
METIN_SINIRI = 8000
EK_KLASORU = "Destek e-postaları"

#: Ek indirme fonksiyonu: (adres, en_cok_bayt) → bayt. Testte değiştirilebilir.
Indirici = Callable[[str, int], Awaitable[bytes]]


class GeciciHata(Exception):
    """Yeniden denenince geçebilecek hata (ağ, sağlayıcı API). Uç 5xx döner."""


def simdi() -> datetime:
    return datetime.now(timezone.utc)


def _utc(an: Optional[datetime]) -> Optional[datetime]:
    if an is None:
        return None
    return an.replace(tzinfo=timezone.utc) if an.tzinfo is None else an.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# İmzalar
# ---------------------------------------------------------------------------
def hmac_imzasi(anahtar: str, zaman: str, ham_govde: bytes) -> str:
    return hmac.new(anahtar.encode(), f"{zaman}.".encode() + ham_govde, hashlib.sha256).hexdigest()


def hmac_dogrula(anahtar: str, zaman: Optional[str], imza: Optional[str], ham_govde: bytes, an: Optional[float] = None) -> bool:
    """Genel uç: X-MK-Imza = hex(HMAC-SHA256(anahtar, f"{zaman}.{ham_govde}")), ±5 dk."""
    if not anahtar or not zaman or not imza:
        return False
    try:
        z = int(str(zaman).strip())
    except ValueError:
        return False
    if abs((an if an is not None else time.time()) - z) > IMZA_TOLERANSI_SN:
        return False
    beklenen = hmac_imzasi(anahtar, str(zaman).strip(), ham_govde)
    return hmac.compare_digest(beklenen, str(imza).strip().lower())


def svix_imzasi(gizli: str, svix_id: str, zaman: str, ham_govde: bytes) -> str:
    anahtar = base64.b64decode(gizli.split("_", 1)[1] if gizli.startswith("whsec_") else gizli)
    icerik = f"{svix_id}.{zaman}.".encode() + ham_govde
    return base64.b64encode(hmac.new(anahtar, icerik, hashlib.sha256).digest()).decode()


def svix_dogrula(
    gizli: str,
    svix_id: Optional[str],
    zaman: Optional[str],
    imzalar: Optional[str],
    ham_govde: bytes,
    an: Optional[float] = None,
) -> bool:
    """Resend (Svix) webhook imzası — kütüphanesiz.

    İmzalanan içerik `{svix-id}.{svix-timestamp}.{ham gövde}`; anahtar
    `whsec_` sonrası base64 çözülmüş gizli; `svix-signature` boşlukla
    ayrılmış `v1,<base64>` listesi (anahtar döndürülürken birden çok olur).
    Zaman damgası ±5 dk (yeniden oynatma saldırısına karşı).
    """
    if not gizli or not svix_id or not zaman or not imzalar:
        return False
    try:
        z = int(str(zaman).strip())
    except ValueError:
        return False
    if abs((an if an is not None else time.time()) - z) > IMZA_TOLERANSI_SN:
        return False
    try:
        beklenen = svix_imzasi(gizli.strip(), svix_id.strip(), str(zaman).strip(), ham_govde)
    except (binascii.Error, ValueError, IndexError):
        return False
    for parca in str(imzalar).split():
        surum, _, deger = parca.partition(",")
        if surum == "v1" and deger and hmac.compare_digest(beklenen, deger):
            return True
    return False


# ---------------------------------------------------------------------------
# Başlıklar ve adresler
# ---------------------------------------------------------------------------
def adres_coz(ham: Any) -> Tuple[str, str]:
    """'Ayşe <AYSE@Ornek.com>' → ('Ayşe', 'ayse@ornek.com')."""
    ad, eposta = parseaddr(str(ham or ""))
    eposta = (eposta or "").strip().lower()
    if "@" not in eposta or len(eposta) > 254 or any(c.isspace() for c in eposta):
        return (ad or "").strip(), ""
    return (ad or "").strip()[:120], eposta


def basliklari_duzelt(ham: Any) -> Dict[str, str]:
    """Başlıklar sözlük ya da [{name, value}] listesi olabilir → küçük harf anahtarlı sözlük."""
    sonuc: Dict[str, str] = {}
    if isinstance(ham, dict):
        for k, v in ham.items():
            sonuc[str(k).strip().lower()] = " ".join(v) if isinstance(v, list) else str(v)
    elif isinstance(ham, list):
        for o in ham:
            if isinstance(o, dict):
                ad = o.get("name") or o.get("ad") or o.get("key")
                if ad:
                    sonuc[str(ad).strip().lower()] = str(o.get("value") or o.get("deger") or "")
    return sonuc


_KIMLIK = re.compile(r"<[^<>\s]{3,300}>")


def kimlikleri_ayikla(*degerler: Any) -> List[str]:
    kimlikler: List[str] = []
    for d in degerler:
        if isinstance(d, list):
            d = " ".join(str(x) for x in d)
        for m in _KIMLIK.findall(str(d or "")):
            if m not in kimlikler:
                kimlikler.append(m)
    return kimlikler[:50]


def message_id_duzelt(ham: Any) -> str:
    deger = str(ham or "").strip()
    if not deger:
        return ""
    if not deger.startswith("<"):
        deger = f"<{deger.strip('<>')}>"
    return deger[:300]


_BELIRTEC = re.compile(r"\[#T-(\d{1,9})\]", re.I)


def belirtec_bul(konu: Any) -> Optional[int]:
    m = _BELIRTEC.search(str(konu or ""))
    return int(m.group(1)) if m else None


_OTOMATIK_YEREL = re.compile(
    r"^(mailer-daemon|postmaster|no-?reply|do-?not-?reply|donotreply|noreply[-.+].*|no-reply[-.+].*|bounces?(\+.*)?|auto-?reply)$",
    re.I,
)
_OTOMATIK_KONU = re.compile(
    r"^\s*(auto(matic)?[ -]?(reply|response)|out of (the )?office|otomatik (yan[ıi]t|cevap)|abwesenheit|autoreply|undeliverable|delivery status notification)",
    re.I,
)


def otomatik_nedeni(gonderen: str, konu: str, basliklar: Dict[str, str], kendi_adreslerimiz: List[str]) -> Optional[str]:
    """Talep açılmaması gereken ileti ise nedeni; değilse None."""
    yerel = gonderen.split("@", 1)[0] if "@" in gonderen else gonderen
    if gonderen and gonderen in [a.lower() for a in kendi_adreslerimiz if a]:
        return "kendi_adresimiz"
    if _OTOMATIK_YEREL.match(yerel or ""):
        return "sistem_gondericisi"
    oto = basliklar.get("auto-submitted", "").strip().lower()
    if oto and oto != "no":
        return "auto_submitted"
    oncelik = basliklar.get("precedence", "").strip().lower()
    if oncelik in ("bulk", "junk", "list", "auto_reply", "auto-reply"):
        return "precedence"
    if "x-autoreply" in basliklar or "x-autorespond" in basliklar or "x-autoresponder" in basliklar:
        return "x_autoreply"
    bastir = basliklar.get("x-auto-response-suppress", "").lower()
    if "oof" in bastir or bastir.strip() == "all":
        return "x_autoreply"
    if "list-id" in basliklar or "list-unsubscribe" in basliklar:
        return "liste_iletisi"
    if _OTOMATIK_KONU.match(konu or ""):
        return "otomatik_konu"
    return None


# ---------------------------------------------------------------------------
# Metin: HTML → metin, alıntı kırpma
# ---------------------------------------------------------------------------
_HTML_ALINTI = re.compile(
    r"<(div|blockquote)[^>]*(gmail_quote|yahoo_quoted|moz-cite-prefix|divRplyFwdMsg|appendonsend|type=\"?cite)[^>]*>"
    r"|<div[^>]*id=\"?(divRplyFwdMsg|appendonsend)",
    re.I,
)
_BLOK_SONU = re.compile(r"<\s*(br|/p|/div|/li|/tr|/h[1-6]|/blockquote|hr)\b[^>]*>", re.I)


def html_metne(ham_html: str) -> str:
    """HTML'i metne çevirir. Önce güvenli temizleyiciden geçer (script/style atılır)."""
    from services.guvenli_html import temizle

    ham = str(ham_html or "")
    m = _HTML_ALINTI.search(ham)
    if m:
        ham = ham[: m.start()]
    # Satır sonları etiketlerle birlikte kaybolmasın: temizleyici div'i atıyor.
    ham = _BLOK_SONU.sub("\n", ham)
    temiz = temizle(ham)
    metin = re.sub(r"<[^>]*>", "", temiz)
    metin = html_mod.unescape(metin).replace("\xa0", " ")
    satirlar = [re.sub(r"[ \t]+", " ", s).strip() for s in metin.replace("\r\n", "\n").split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(satirlar)).strip()


_ALINTI_BASI = [
    re.compile(r"^-{2,}\s*(original message|orijinal (ileti|mesaj)|urspr[üu]ngliche nachricht|forwarded message)\s*-{2,}\s*$", re.I),
    re.compile(r"^_{10,}\s*$"),
    re.compile(r"^.{0,300}\btarihinde\b.{0,300}\byazd[ıi]\s*:\s*$", re.I),
    re.compile(r"^.{0,300}\b(şunu|sunu) yazd[ıi]\s*:\s*$", re.I),
    re.compile(r"^am .{0,300} schrieb .{0,300}:\s*$", re.I),
    re.compile(r"^le .{0,300} a [ée]crit\s*:\s*$", re.I),
]
_ON_WROTE = re.compile(r"^on\s.{0,300}\bwrote:\s*$", re.I)


def alintiyi_kirp(metin: str) -> str:
    """Yanıtın altındaki eski yazışmayı atar.

    "On … wrote:" (iki satıra bölünmüş olabilir), Türkçe "… tarihinde …
    yazdı:", "-----Original Message-----", Outlook "From:/Sent:" bloğu,
    "> " ile başlayan satırlar. Hepsi kırpılıp geriye bir şey kalmazsa
    özgün metin döner (tamamı alıntı olan bir ileti boş talep açmasın).
    """
    satirlar = str(metin or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    kes = len(satirlar)
    for i, satir in enumerate(satirlar):
        yalin = satir.strip()
        if any(d.match(yalin) for d in _ALINTI_BASI):
            kes = i
            break
        if _ON_WROTE.match(yalin):
            kes = i
            break
        # "On Mon, 1 Jan 2026 at 10:00, Ayşe <a@b.com>\nwrote:" — Gmail uzun satırı böler.
        if re.match(r"^on\s", yalin, re.I) and i + 1 < len(satirlar) and re.search(r"\bwrote:\s*$", satirlar[i + 1].strip(), re.I):
            kes = i
            break
        if re.match(r"^(from|kimden|von)\s*:\s*\S", yalin, re.I):
            sonraki = " ".join(s.strip() for s in satirlar[i + 1 : i + 4])
            if re.search(r"\b(sent|g[öo]nderildi|gesendet|date|tarih|to|kime)\s*:", sonraki, re.I):
                kes = i
                break
    govde = [s for s in satirlar[:kes] if not s.lstrip().startswith(">")]
    sonuc = "\n".join(govde).strip()
    # İmza ayracı: tek başına "-- " satırı ve sonrası
    imza = re.search(r"(?m)^-- ?$", sonuc)
    if imza:
        sonuc = sonuc[: imza.start()].strip()
    if not sonuc:
        return str(metin or "").strip()
    return re.sub(r"\n{3,}", "\n\n", sonuc)


def govde_metni(metin: Any, html: Any) -> str:
    duz = str(metin or "").strip()
    if not duz and html:
        duz = html_metne(str(html))
    return alintiyi_kirp(duz)[:METIN_SINIRI]


# ---------------------------------------------------------------------------
# Ekler
# ---------------------------------------------------------------------------
async def varsayilan_indirici(adres: str, sinir: int) -> bytes:
    import httpx

    if not str(adres).lower().startswith("https://"):
        raise GeciciHata("gecersiz_ek_adresi")
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as istemci:
            async with istemci.stream("GET", adres) as yanit:
                if yanit.status_code >= 300:
                    raise GeciciHata(f"ek_indirilemedi_{yanit.status_code}")
                parcalar: List[bytes] = []
                toplam = 0
                async for parca in yanit.aiter_bytes():
                    toplam += len(parca)
                    if toplam > sinir:
                        raise _BoyutAsildi()
                    parcalar.append(parca)
                return b"".join(parcalar)
    except (_BoyutAsildi, GeciciHata):
        raise
    except Exception as hata:  # noqa: BLE001
        raise GeciciHata(f"ek_indirilemedi: {type(hata).__name__}")


class _BoyutAsildi(Exception):
    pass


def _boyut_metni(bayt: int) -> str:
    return f"{bayt / (1024 * 1024):.1f} MB"


async def ekleri_hazirla(
    db: AsyncSession,
    ekler: Any,
    *,
    sahip: str,
    gonderen: str,
    indirici: Optional[Indirici] = None,
) -> Tuple[List[Any], List[str]]:
    """Ekleri doğrular ve depoya yazar (flush; commit ETMEZ).

    (kaydedilen dosya satırları, atlananların okunur notları) döndürür.
    """
    from services.dosyalar import IZINLI_TURLER, DosyaHatasi, ad_temizle, dosya_kaydet, klasor_hazirla, uzanti_al

    kaydedilen: List[Any] = []
    atlanan: List[str] = []
    if not isinstance(ekler, list) or not ekler:
        return kaydedilen, atlanan
    indirici = indirici or varsayilan_indirici
    klasor_hazir = False
    for sira, ek in enumerate(ekler):
        if not isinstance(ek, dict):
            continue
        ad = ad_temizle(ek.get("ad") or ek.get("filename") or "ek")
        if sira >= EK_SAYISI_SINIRI:
            atlanan.append(f"{ad} (ileti başına en çok {EK_SAYISI_SINIRI} ek)")
            continue
        if uzanti_al(ad) not in IZINLI_TURLER:
            atlanan.append(f"{ad} (izin verilmeyen dosya türü)")
            continue
        try:
            beyan = int(ek.get("boyut") or ek.get("size") or 0)
        except (TypeError, ValueError):
            beyan = 0
        if beyan > EK_SINIRI_BAYT:
            atlanan.append(f"{ad} ({_boyut_metni(beyan)} — 10 MB sınırını aşıyor)")
            continue
        veri: Optional[bytes] = None
        if isinstance(ek.get("icerik_bytes"), (bytes, bytearray)):
            veri = bytes(ek["icerik_bytes"])
        elif ek.get("icerik") or ek.get("icerik_base64"):
            ham = str(ek.get("icerik") or ek.get("icerik_base64"))
            if len(ham) > EK_SINIRI_BAYT * 4 // 3 + 16:
                atlanan.append(f"{ad} (10 MB sınırını aşıyor)")
                continue
            try:
                veri = base64.b64decode(ham, validate=False)
            except (binascii.Error, ValueError):
                atlanan.append(f"{ad} (içerik okunamadı)")
                continue
        elif ek.get("indirme_url"):
            try:
                veri = await indirici(str(ek["indirme_url"]), EK_SINIRI_BAYT)
            except _BoyutAsildi:
                atlanan.append(f"{ad} (10 MB sınırını aşıyor)")
                continue
        if veri is None:
            atlanan.append(f"{ad} (içerik yok)")
            continue
        if len(veri) > EK_SINIRI_BAYT:
            atlanan.append(f"{ad} ({_boyut_metni(len(veri))} — 10 MB sınırını aşıyor)")
            continue
        try:
            if not klasor_hazir:
                # Klasör "yalnız ekip": ekler talep ekranından (talep yetkisiyle)
                # açılıyor; müşterinin Dosyalarım listesine karışmıyor.
                await klasor_hazirla(db, sahip, EK_KLASORU, "ekip")
                klasor_hazir = True
            async with db.begin_nested():
                d = await dosya_kaydet(
                    db, eposta=sahip, klasor=EK_KLASORU, ad_ham=ad, veri=veri,
                    yukleyen=gonderen, yukleyen_rol="client",
                )
            kaydedilen.append(d)
        except DosyaHatasi as h:
            neden = {
                "tur_izinsiz": "izin verilmeyen dosya türü",
                "icerik_uyusmuyor": "içerik uzantısıyla uyuşmuyor",
                "bos_dosya": "boş dosya",
            }.get(h.kod, "kaydedilemedi")
            if h.kod == "depo_hatasi":
                raise GeciciHata("depo_hatasi")
            atlanan.append(f"{ad} ({neden})")
    return kaydedilen, atlanan


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
async def kayitli_musteri_mi(db: AsyncSession, eposta: str) -> bool:
    """Kullanıcı hesabı ya da projesi olan adres."""
    from models.auth import User
    from models.projects import Projects

    if not eposta:
        return False
    try:
        if (await db.execute(select(User.id).where(func.lower(User.email) == eposta).limit(1))).first():
            return True
    except Exception:  # noqa: BLE001 - tablo yoksa
        logger.debug("users okunamadı", exc_info=True)
    try:
        if (await db.execute(select(Projects.id).where(func.lower(Projects.client_email) == eposta).limit(1))).first():
            return True
    except Exception:  # noqa: BLE001
        logger.debug("projects okunamadı", exc_info=True)
    return False


async def kendi_adreslerimiz(db: AsyncSession) -> List[str]:
    from services.destek_talep import gelen_adres

    adresler = []
    _, gonderen = adres_coz(os.environ.get("NOTIFY_FROM_EMAIL") or "bildirim@mehmetkuru.dev")
    if gonderen:
        adresler.append(gonderen)
    gelen = await gelen_adres(db)
    if gelen:
        adresler.append(gelen.lower())
    return adresler


def _turetilmis_kimlik(gonderen: str, konu: str, metin: str) -> str:
    ozet = hashlib.sha256(f"{gonderen}\n{konu}\n{metin[:4000]}".encode("utf-8", "replace")).hexdigest()[:40]
    return f"<turetilmis-{ozet}@gelen>"


def _ozet(metin: str) -> str:
    tek = re.sub(r"\s+", " ", metin or "").strip()
    return tek[:200]


async def _talep_eslestir(db: AsyncSession, konu: str, kimlikler: List[str]) -> Optional[Any]:
    from models.destek_eposta import TalepEpostaKimlikleri
    from models.support_tickets import Support_tickets

    talep_id = belirtec_bul(konu)
    if talep_id is None and kimlikler:
        talep_id = (
            await db.execute(
                select(TalepEpostaKimlikleri.ticket_id)
                .where(TalepEpostaKimlikleri.message_id.in_(kimlikler), TalepEpostaKimlikleri.yon == "giden")
                .order_by(TalepEpostaKimlikleri.id.desc())
                .limit(1)
            )
        ).scalars().first()
    if talep_id is None:
        return None
    return (await db.execute(select(Support_tickets).where(Support_tickets.id == talep_id))).scalars().first()


# ---------------------------------------------------------------------------
# Giriş noktası
# ---------------------------------------------------------------------------
async def _kaydi_al(db: AsyncSession, message_id: str, gonderen: str, konu: str, kaynak: str) -> Tuple[Optional[Any], Optional[Dict[str, Any]]]:
    """(kayıt, tekrar_yaniti). İleti daha önce işlendiyse tekrar yanıtı döner."""
    from models.destek_eposta import GelenEpostalar

    mevcut = (await db.execute(select(GelenEpostalar).where(GelenEpostalar.message_id == message_id))).scalars().first()
    if mevcut is not None:
        eski_durum = mevcut.durum
        bayat = eski_durum == "isleniyor" and (_utc(mevcut.updated_at) or simdi()) < simdi() - ISLENIYOR_ZAMAN_ASIMI
        if eski_durum != "hata" and not bayat:
            return None, {"durum": eski_durum, "neden": mevcut.neden, "talep_id": mevcut.talep_id, "tekrar": True}
        # Yeniden dene: koşullu UPDATE — iki eş zamanlı yeniden deneme ikisi birden almasın.
        sonuc = await db.execute(
            update(GelenEpostalar)
            .where(GelenEpostalar.id == mevcut.id, GelenEpostalar.durum == eski_durum)
            .values(durum="isleniyor", neden=None, updated_at=simdi())
            .execution_options(synchronize_session=False)
        )
        await db.commit()
        if int(sonuc.rowcount or 0) != 1:
            return None, {"durum": "isleniyor", "tekrar": True}
        await db.refresh(mevcut)
        return mevcut, None
    kayit = GelenEpostalar(message_id=message_id, gonderen=gonderen or None, konu=(konu or "")[:250] or None, durum="isleniyor", kaynak=kaynak)
    db.add(kayit)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return None, {"durum": "isleniyor", "tekrar": True}
    return kayit, None


async def _bitir(db: AsyncSession, kayit: Any, durum: str, neden: str, talep_id: Optional[int] = None, ozet: str = "", ek: int = 0) -> Dict[str, Any]:
    kayit.durum = durum
    kayit.neden = neden[:200]
    kayit.talep_id = talep_id
    kayit.ozet = _ozet(ozet) or None
    kayit.ek_sayisi = ek
    kayit.updated_at = simdi()
    await db.commit()
    return {"durum": durum, "neden": neden, "talep_id": talep_id}


async def isle(
    db: AsyncSession,
    ileti: Dict[str, Any],
    *,
    kaynak: str = "genel",
    indirici: Optional[Indirici] = None,
) -> Dict[str, Any]:
    """Gelen bir iletiyi işler. {durum, neden, talep_id, tekrar?} döner.

    GeciciHata (ve beklenmeyen hata) yukarı fırlatılır; kayıt "hata" olarak
    kalır, ileti yeniden gelince yeniden işlenir.
    """
    from models.destek_eposta import GelenEpostalar, TalepEkleri, TalepEpostaKimlikleri
    from models.support_tickets import Support_tickets
    from services import destek_talep

    gonderen_ad, gonderen = adres_coz(ileti.get("gonderen"))
    if not gonderen_ad and ileti.get("gonderen_ad"):
        gonderen_ad = str(ileti["gonderen_ad"]).strip()[:120]
    konu = re.sub(r"\s+", " ", str(ileti.get("konu") or "")).strip()[:250]
    basliklar = basliklari_duzelt(ileti.get("basliklar"))
    metin = govde_metni(ileti.get("metin"), ileti.get("html"))
    message_id = message_id_duzelt(ileti.get("message_id") or basliklar.get("message-id")) or _turetilmis_kimlik(gonderen, konu, metin)

    kayit, tekrar = await _kaydi_al(db, message_id, gonderen, konu, kaynak)
    if tekrar is not None:
        return tekrar
    kayit_id = kayit.id

    try:
        if not gonderen:
            return await _bitir(db, kayit, "yoksayildi", "gecersiz_gonderen", ozet=metin)
        neden = otomatik_nedeni(gonderen, konu, basliklar, await kendi_adreslerimiz(db))
        if neden:
            return await _bitir(db, kayit, "yoksayildi", neden, ozet=metin)
        sinir_an = simdi() - timedelta(hours=1)
        son_saat = (
            await db.execute(
                select(func.count(GelenEpostalar.id)).where(
                    GelenEpostalar.gonderen == gonderen,
                    GelenEpostalar.durum == "islendi",
                    GelenEpostalar.created_at >= sinir_an,
                )
            )
        ).scalar_one()
        if int(son_saat or 0) >= SAATLIK_SINIR:
            return await _bitir(db, kayit, "yoksayildi", "hiz_siniri", ozet=metin)

        kimlikler = kimlikleri_ayikla(
            ileti.get("in_reply_to") or basliklar.get("in-reply-to"),
            ileti.get("references") or basliklar.get("references"),
        )
        talep = await _talep_eslestir(db, konu, kimlikler)
        uyari: Optional[str] = None
        if talep is not None and (talep.client_email or "").strip().lower() != gonderen:
            uyari = (
                f"Gönderen {gonderen}, #{talep.id} numaralı talebe yazmaya çalıştı ama talebin sahibi değil; "
                "mesaj o talebe EKLENMEDİ, ayrı talep açıldı."
            )
            talep = None
            yetkisiz = True
        else:
            yetkisiz = False

        ekler = ileti.get("ekler") or []

        # --- Mevcut talebe mesaj -------------------------------------------------
        if talep is not None:
            dosyalar, atlanan = await ekleri_hazirla(db, ekler, sahip=gonderen, gonderen=gonderen, indirici=indirici)
            govde = _govdeye_not_ekle(metin, atlanan, bool(dosyalar))
            yanit = await destek_talep.mesaj_ekle(
                db, talep, yazan="musteri", yazan_ad=gonderen_ad or talep.client_name,
                yazan_email=gonderen, metin=govde, eposta_kimligi=message_id, commit=False,
            )
            for d in dosyalar:
                db.add(TalepEkleri(ticket_id=talep.id, reply_id=yanit.id, dosya_id=d.id, ad=d.ad, boyut=d.boyut, tur=d.tur))
            sonuc = await _bitir(db, kayit, "islendi", "mesaj_eklendi", talep.id, metin, len(dosyalar))
            await destek_talep.mesaj_eklendi_sonrasi(db, talep, yanit)
            return sonuc

        # --- Yeni talep ------------------------------------------------------------
        kayitli = await kayitli_musteri_mi(db, gonderen)
        dogrulanmadi = yetkisiz or not kayitli
        dosyalar, atlanan = await ekleri_hazirla(db, ekler, sahip=gonderen, gonderen=gonderen, indirici=indirici)
        govde = _govdeye_not_ekle(metin, atlanan, bool(dosyalar))
        an = datetime.now()
        talep = Support_tickets(
            client_name=gonderen_ad or None,
            client_email=gonderen,
            subject=konu or "(konusuz e-posta)",
            message=govde or "(boş ileti)",
            status="open",
            priority="normal",
            hizmet="genel",
            kaynak="eposta",
            dogrulanmadi=dogrulanmadi,
            son_mesaj_at=an,
            created_at=an,
        )
        db.add(talep)
        await db.flush()
        db.add(TalepEpostaKimlikleri(message_id=message_id, ticket_id=talep.id, reply_id=None, yon="gelen"))
        for d in dosyalar:
            db.add(TalepEkleri(ticket_id=talep.id, reply_id=None, dosya_id=d.id, ad=d.ad, boyut=d.boyut, tur=d.tur))
        neden = "yeni_talep_yetkisiz_belirtec" if yetkisiz else ("yeni_talep" if kayitli else "yeni_talep_dogrulanmadi")
        sonuc = await _bitir(db, kayit, "islendi", neden, talep.id, metin, len(dosyalar))

        notlar = ["Bu talep e-postayla geldi."]
        if not kayitli:
            notlar.append("Gönderen kayıtlı bir müşteri değil (doğrulanmadı); otomatik yanıt gönderilmedi.")
        if uyari:
            notlar.append(uyari)
        await destek_talep.talep_acildi(db, talep, kanal="eposta", ek_not=" ".join(notlar))
        return sonuc
    except Exception as hata:
        try:
            await db.rollback()
            kayit_tazesi = (await db.execute(select(GelenEpostalar).where(GelenEpostalar.id == kayit_id))).scalars().first()
            if kayit_tazesi is not None:
                await _bitir(db, kayit_tazesi, "hata", f"{type(hata).__name__}: {hata}"[:200])
        except Exception:  # noqa: BLE001
            logger.exception("Gelen e-posta hata kaydı yazılamadı")
        if not isinstance(hata, GeciciHata):
            logger.exception("Gelen e-posta işlenemedi: %s", message_id)
        raise


def _govdeye_not_ekle(metin: str, atlanan: List[str], ek_var: bool) -> str:
    govde = metin
    if not govde:
        govde = "(yalnız ek gönderildi)" if ek_var else ""
    if atlanan:
        govde = (govde + "\n\n" if govde else "") + "[Atlanan ekler: " + "; ".join(atlanan) + "]"
    return govde[:METIN_SINIRI + 1000]


# ---------------------------------------------------------------------------
# Resend (receiving) — webhook yalnız üst veri taşıyor; gövde ve ekler API'den
# ---------------------------------------------------------------------------
RESEND_API = "https://api.resend.com"


async def _resend_get(yol: str) -> Dict[str, Any]:
    import httpx

    anahtar = (os.environ.get("RESEND_API_KEY") or "").strip()
    if not anahtar:
        raise GeciciHata("resend_api_anahtari_yok")
    try:
        async with httpx.AsyncClient(timeout=10.0) as istemci:
            yanit = await istemci.get(f"{RESEND_API}{yol}", headers={"Authorization": f"Bearer {anahtar}"})
    except Exception as hata:  # noqa: BLE001
        raise GeciciHata(f"resend_erisilemedi: {type(hata).__name__}")
    if yanit.status_code >= 300:
        raise GeciciHata(f"resend_{yanit.status_code}")
    try:
        return yanit.json()
    except ValueError:
        raise GeciciHata("resend_gecersiz_yanit")


async def resend_iletisi(veri: Dict[str, Any]) -> Dict[str, Any]:
    """`email.received` olayının `data`sından tam `ileti` sözlüğünü kurar.

    GET /emails/receiving/{email_id}           → html, text, headers, message_id …
    GET /emails/receiving/{email_id}/attachments → download_url, size, filename
    (Belge: resend.com/docs/dashboard/receiving — webhook gövdesi içerik ve
    ek taşımıyor; "serverless ortamlarda büyük ekler" için bilerek böyle.)
    """
    eposta_id = str(veri.get("email_id") or veri.get("id") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9-]{8,80}", eposta_id):
        raise ValueError("gecersiz_email_id")
    tam = await _resend_get(f"/emails/receiving/{eposta_id}")
    ekler: List[Dict[str, Any]] = []
    if veri.get("attachments") or tam.get("attachments"):
        liste = await _resend_get(f"/emails/receiving/{eposta_id}/attachments")
        for e in (liste.get("data") or [])[: EK_SAYISI_SINIRI + 5]:
            ekler.append(
                {
                    "ad": e.get("filename") or "ek",
                    "tur": e.get("content_type"),
                    "boyut": e.get("size") or 0,
                    "indirme_url": e.get("download_url"),
                }
            )
    basliklar = basliklari_duzelt(tam.get("headers"))
    return {
        "gonderen": tam.get("from") or veri.get("from"),
        "alicilar": tam.get("to") or veri.get("to") or [],
        "konu": tam.get("subject") or veri.get("subject") or "",
        "metin": tam.get("text") or "",
        "html": tam.get("html") or "",
        "message_id": tam.get("message_id") or veri.get("message_id") or f"<resend-{eposta_id}@gelen>",
        "in_reply_to": basliklar.get("in-reply-to"),
        "references": basliklar.get("references"),
        "basliklar": basliklar,
        "ekler": ekler,
    }
