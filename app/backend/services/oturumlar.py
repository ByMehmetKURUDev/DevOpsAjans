"""Faz 2D — oturum güvenliği: oturum kaydı, iptal, kullanıcı bazlı kesim.

Neden?
------
Uygulama jetonu (JWT) durumsuz: verildikten sonra süresi dolana kadar
geçerliydi, "şu cihazdaki oturumu kapat" demenin yolu yoktu. Artık her yeni
jetonda rastgele bir `sid` var ve `oturumlar` tablosunda bir satırı
gösteriyor. Satır iptal edilince jeton reddediliyor.

Doğrulama iki yoldan geçiyor
----------------------------
* `dependencies/auth.get_current_user` (async bağımlılık)
* `dependencies/entity_guard._istekteki_kullanici` → `kayit_sahipligi._yonetici_mi`
  (birçok router jetonu kendisi, eşzamanlı çözüyor)

İkincisi eşzamanlı olduğu için veritabanına gidemez. Bu yüzden karar
`middlewares/oturum_bekcisi.py`'de, istek başında bir kez veriliyor
(`jeton_denetle`) ve isteğin `scope`'una yazılıyor; iki yol da oradan
okuyor (`istek_iptal_mi`). Ara katman çalışmamışsa (ör. `/api` dışı yol)
async yol kararı kendisi veriyor.

Her istekte veritabanına gitmemek için süreç içi önbellek (25 sn). İptal
eden uç önbelleği hemen boşaltıyor; yani iptal, aynı süreçte anında,
en kötü ihtimalle 25 sn içinde her yerde geçerli (Render ücretsiz planında
tek süreç var).

Geriye uyum
-----------
`sid` taşımayan eski jetonlar (bu sürümden önce verilenler, e2e aracı,
test jetonları) geçerli kalıyor. Onları düşürmenin yolu kullanıcı bazlı
kesim (`oturum_kesimleri`): "bu andan önce verilmiş her jeton geçersiz".
Kesim varken `iat` taşımayan jeton reddediliyor.

Veritabanı hatasında doğrulama AÇIK kalıyor (log + devam): veritabanı
yoksa uygulama zaten çalışmıyor; ama oturum tablosundaki geçici bir hata
herkesi dışarı atmasın.
"""

import logging
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from models.oturumlar import OturumKesimleri, Oturumlar
from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: Süreç içi önbellek ömrü (saniye).
ONBELLEK_SN = 25.0
#: `son_gorulme` en çok bu aralıkla yazılıyor.
SON_GORULME_ARALIGI = timedelta(minutes=5)
#: Biten/iptal edilen oturum satırları bu kadar gün sonra siliniyor.
SAKLAMA_GUN = 30
UA_SINIRI = 300
IPTAL_SEBEBI = "Oturum sonlandırıldı"

#: Bildirim olayı (services/bildirim_tercih.py OLAYLAR).
YENI_OTURUM_OLAYI = "yeni_oturum"


def simdi() -> datetime:
    return datetime.now(timezone.utc)


def _utc(an: Optional[datetime]) -> Optional[datetime]:
    """SQLite saat dilimini atıyor; zamanlar UTC yazıldığı için geri ekle."""
    if an is None:
        return None
    return an.replace(tzinfo=timezone.utc) if an.tzinfo is None else an.astimezone(timezone.utc)


def yeni_sid() -> str:
    """18 bayt rastgele → 24 karakter urlsafe."""
    return secrets.token_urlsafe(18)


# ---------------------------------------------------------------------------
# Cihaz adı (User-Agent → "Chrome · macOS")
# ---------------------------------------------------------------------------
_TARAYICILAR: Tuple[Tuple[str, str], ...] = (
    (r"Edg(?:e|A|iOS)?/", "Edge"),
    (r"OPR/|Opera", "Opera"),
    (r"SamsungBrowser/", "Samsung Internet"),
    (r"YaBrowser/", "Yandex"),
    (r"Firefox/|FxiOS/", "Firefox"),
    (r"Chrome/|CriOS/|Chromium/", "Chrome"),
    (r"Safari/", "Safari"),
    (r"curl/", "curl"),
    (r"python-requests|python-httpx|aiohttp", "Python"),
)
_SISTEMLER: Tuple[Tuple[str, str], ...] = (
    (r"iPhone|iPod", "iOS"),
    (r"iPad", "iPadOS"),
    (r"Android", "Android"),
    (r"CrOS", "ChromeOS"),
    (r"Windows", "Windows"),
    (r"Mac OS X|Macintosh", "macOS"),
    (r"Linux", "Linux"),
)


def cihaz_adi(ua: Optional[str]) -> Optional[str]:
    """Ham User-Agent'tan kısa, okunur ad. Tanınmazsa None (arayüz "bilinmiyor" yazar)."""
    metin = (ua or "").strip()
    if not metin:
        return None
    tarayici = next((ad for desen, ad in _TARAYICILAR if re.search(desen, metin)), None)
    sistem = next((ad for desen, ad in _SISTEMLER if re.search(desen, metin)), None)
    parcalar = [p for p in (tarayici, sistem) if p]
    return " · ".join(parcalar)[:80] if parcalar else None


def istek_ip_ozeti(request: Any) -> Optional[str]:
    """Denetim kaydı ve site analiziyle aynı tuzlu özet, ilk 16 hane."""
    if request is None:
        return None
    try:
        from utils.istemci_ip import ip_ozeti, istemci_ip

        return ip_ozeti(istemci_ip(request))[:16]
    except Exception:  # noqa: BLE001
        return None


def _oturum_yapici():
    from core.database import db_manager

    return db_manager.async_session_maker


# ---------------------------------------------------------------------------
# Oturum açma (jeton verilirken)
# ---------------------------------------------------------------------------
async def oturum_ac(
    *,
    sid: str,
    kullanici_id: Optional[str],
    email: str,
    rol: Optional[str],
    bitis: Optional[datetime],
    request: Any = None,
) -> Optional[int]:
    """Oturum satırını yazar; yeni cihazsa kullanıcıya bildirir.

    Kendi veritabanı oturumunu açıyor: yazım başarısız olursa girişi
    (kullanıcı kaydı, jeton) etkilemesin. Hiçbir koşulda hata fırlatmaz;
    satırın kimliğini ya da None döndürür.
    """
    yapici = _oturum_yapici()
    if yapici is None:
        return None
    eposta = (email or "").strip().lower()
    if not eposta:
        return None
    ua = None
    if request is not None:
        try:
            ua = (request.headers.get("user-agent") or "")[:UA_SINIRI] or None
        except Exception:  # noqa: BLE001
            ua = None
    cihaz = cihaz_adi(ua)
    ip = istek_ip_ozeti(request)
    try:
        async with yapici() as db:
            onceki = (
                await db.execute(
                    select(Oturumlar.cihaz, Oturumlar.ip_ozet).where(Oturumlar.email == eposta).limit(500)
                )
            ).all()
            an = simdi()
            satir = Oturumlar(
                sid=sid,
                kullanici_id=kullanici_id,
                email=eposta,
                rol=rol,
                olusturma=an,
                son_gorulme=an,
                bitis=bitis,
                ip_ozet=ip,
                cihaz=cihaz,
                user_agent=ua,
            )
            db.add(satir)
            await db.commit()
            kimlik = satir.id

            # İlk giriş (hiç önceki oturum yok) → bildirim yok. Daha önce
            # görülmemiş (cihaz, ip) çifti → "yeni cihazdan giriş".
            if onceki and (cihaz, ip) not in {(c, i) for c, i in onceki}:
                await _yeni_cihaz_bildir(db, eposta=eposta, rol=rol, cihaz=cihaz, an=an, oturum_id=kimlik)
            return kimlik
    except Exception:  # noqa: BLE001 - oturum kaydı girişi ASLA bozmamalı
        logger.exception("Oturum kaydı yazılamadı")
        return None


async def _yeni_cihaz_bildir(
    db: AsyncSession, *, eposta: str, rol: Optional[str], cihaz: Optional[str], an: datetime, oturum_id: int
) -> None:
    try:
        from services.notify import dispatch, render

        yonetici = rol == "admin"
        cihaz_metni = cihaz or "Bilinmeyen cihaz"
        zaman = an.astimezone(timezone(timedelta(hours=3))).strftime("%d.%m.%Y %H:%M")
        baslik, govde = await render(
            db,
            YENI_OTURUM_OLAYI,
            "Hesabınıza yeni bir cihazdan giriş yapıldı",
            (
                f"Cihaz: {cihaz_metni}\nZaman: {zaman} (TSİ)\n\n"
                "Bu giriş size ait değilse panelde Güvenlik bölümünden oturumu hemen kapatın."
            ),
            {"cihaz": cihaz_metni, "zaman": zaman, "eposta": eposta},
        )
        await dispatch(
            db,
            event_type=YENI_OTURUM_OLAYI,
            title=baslik,
            body=govde,
            recipients=[{"email": eposta, "role": "admin" if yonetici else "client"}],
            link="/admin?sekme=guvenlik" if yonetici else "/client?sekme=profile",
            ref_type="oturum",
            ref_id=oturum_id,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Yeni cihaz bildirimi gönderilemedi")


# ---------------------------------------------------------------------------
# Doğrulama (önbellekli)
# ---------------------------------------------------------------------------
#: sid → (bitiş_monotonic, bilgi|None). bilgi: {"id", "iptal", "son_gorulme"}
_oturum_onbellegi: Dict[str, Tuple[float, Optional[Dict[str, Any]]]] = {}
#: email → (bitiş_monotonic, kesim_zaman_damgası|None)
_kesim_onbellegi: Dict[str, Tuple[float, Optional[float]]] = {}


def onbellegi_temizle() -> None:
    """İptal/kesim sonrası: bu süreçte bir sonraki istek veritabanına baksın."""
    _oturum_onbellegi.clear()
    _kesim_onbellegi.clear()


def _onbellekten(sozluk: Dict[str, Tuple[float, Any]], anahtar: str) -> Tuple[bool, Any]:
    kayit = sozluk.get(anahtar)
    if kayit is None or kayit[0] < time.monotonic():
        return False, None
    return True, kayit[1]


def _onbellege(sozluk: Dict[str, Tuple[float, Any]], anahtar: str, deger: Any) -> None:
    if len(sozluk) > 10000:
        sozluk.clear()
    sozluk[anahtar] = (time.monotonic() + ONBELLEK_SN, deger)


async def jeton_denetle(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Çözülmüş (imzası, süresi geçerli) jetonun iptal durumu.

    Dönen sözlük: {"iptal": bool, "sid": str|None, "oturum_id": int|None}.
    Hata fırlatmaz; veritabanına ulaşılamazsa iptal=False (açık kalır).
    """
    sid = payload.get("sid") if isinstance(payload.get("sid"), str) else None
    sonuc: Dict[str, Any] = {"iptal": False, "sid": sid, "oturum_id": None}
    eposta = str(payload.get("email") or "").strip().lower()
    iat = payload.get("iat")

    kesim_var, kesim = _onbellekten(_kesim_onbellegi, eposta) if eposta else (True, None)
    oturum_var, bilgi = _onbellekten(_oturum_onbellegi, sid) if sid else (True, None)
    son_gorulme_yaz = False

    if not (kesim_var and oturum_var):
        yapici = _oturum_yapici()
        if yapici is None:
            return sonuc
        try:
            async with yapici() as db:
                if not kesim_var:
                    satir = (
                        await db.execute(
                            select(OturumKesimleri.gecersiz_once).where(OturumKesimleri.email == eposta)
                        )
                    ).first()
                    kesim = _utc(satir[0]).timestamp() if satir and satir[0] else None
                    _onbellege(_kesim_onbellegi, eposta, kesim)
                if not oturum_var:
                    satir = (
                        await db.execute(
                            select(Oturumlar.id, Oturumlar.iptal_zamani, Oturumlar.son_gorulme).where(
                                Oturumlar.sid == sid
                            )
                        )
                    ).first()
                    bilgi = (
                        {"id": satir[0], "iptal": satir[1] is not None, "son_gorulme": _utc(satir[2])}
                        if satir
                        else None
                    )
                    _onbellege(_oturum_onbellegi, sid, bilgi)
        except Exception:  # noqa: BLE001
            logger.exception("Oturum denetimi yapılamadı (açık bırakıldı)")
            return sonuc

    if kesim is not None:
        try:
            iat_sayi = float(iat) if iat is not None else None
        except (TypeError, ValueError):
            iat_sayi = None
        if iat_sayi is None or iat_sayi < kesim:
            sonuc["iptal"] = True
            return sonuc

    if bilgi is not None:
        sonuc["oturum_id"] = bilgi["id"]
        if bilgi["iptal"]:
            sonuc["iptal"] = True
            return sonuc
        son = bilgi.get("son_gorulme")
        if son is None or simdi() - son >= SON_GORULME_ARALIGI:
            bilgi["son_gorulme"] = simdi()
            son_gorulme_yaz = True

    if son_gorulme_yaz:
        await _son_gorulme_guncelle(bilgi["id"])
    return sonuc


async def _son_gorulme_guncelle(oturum_id: int) -> None:
    yapici = _oturum_yapici()
    if yapici is None:
        return
    try:
        async with yapici() as db:
            await db.execute(
                update(Oturumlar)
                .where(Oturumlar.id == oturum_id, Oturumlar.iptal_zamani.is_(None))
                .values(son_gorulme=simdi())
                .execution_options(synchronize_session=False)
            )
            await db.commit()
    except Exception:  # noqa: BLE001
        logger.debug("son_gorulme güncellenemedi", exc_info=True)


# İstek kapsamı ----------------------------------------------------------------
KAPSAM_ANAHTARI = "mk_oturum"


def istek_durumu(request: Any) -> Optional[Dict[str, Any]]:
    """Ara katmanın bu istek için verdiği karar (yoksa None)."""
    try:
        return request.scope.get(KAPSAM_ANAHTARI)
    except Exception:  # noqa: BLE001
        return None


def istek_iptal_mi(request: Any) -> bool:
    durum = istek_durumu(request)
    return bool(durum and durum.get("iptal"))


def istek_sid(request: Any) -> Optional[str]:
    """İsteği yapan jetonun sid'i (ara katmandan; yoksa jetonu çözerek)."""
    durum = istek_durumu(request)
    if durum is not None:
        return durum.get("sid")
    try:
        from core.auth import decode_access_token

        baslik = request.headers.get("authorization") or ""
        if not baslik.lower().startswith("bearer "):
            return None
        sid = decode_access_token(baslik.split(" ", 1)[1].strip()).get("sid")
        return sid if isinstance(sid, str) else None
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# İptal / kesim
# ---------------------------------------------------------------------------
def etkin_kosulu(an: Optional[datetime] = None):
    an = an or simdi()
    return (Oturumlar.iptal_zamani.is_(None)) & (or_(Oturumlar.bitis.is_(None), Oturumlar.bitis > an))


def etkin_mi(satir: Oturumlar, an: Optional[datetime] = None) -> bool:
    an = an or simdi()
    bitis = _utc(satir.bitis)
    return satir.iptal_zamani is None and (bitis is None or bitis > an)


async def iptal_et(
    db: AsyncSession,
    satirlar: Iterable[Oturumlar],
    *,
    iptal_eden: Optional[str],
    request: Any = None,
) -> int:
    """Satırları iptal eder, commit eder, önbelleği boşaltır, denetime yazar."""
    from services.denetim import denetim_yaz

    an = simdi()
    iptaller: List[Oturumlar] = []
    for s in satirlar:
        if s.iptal_zamani is not None:
            continue
        s.iptal_zamani = an
        s.iptal_eden = (iptal_eden or "sistem")[:200]
        iptaller.append(s)
    if not iptaller:
        return 0
    await db.flush()
    for s in iptaller:
        # sid denetim kaydına yazılmıyor: yalnız satır kimliği, cihaz ve e-posta.
        await denetim_yaz(
            db,
            request=request,
            islem="diger",
            tablo="oturumlar",
            kayit_id=s.id,
            ozet=f"Oturum sonlandırıldı · {s.cihaz or 'bilinmeyen cihaz'} · {s.email}",
            once={"iptal_zamani": None},
            sonra={"iptal_zamani": an.isoformat()},
        )
    await db.commit()
    onbellegi_temizle()
    return len(iptaller)


async def kesim_koy(db: AsyncSession, email: str, *, iptal_eden: Optional[str], request: Any = None) -> datetime:
    """Bu e-postaya şu ana kadar verilmiş BÜTÜN jetonları geçersiz kılar (sid'siz eskiler dahil)."""
    from services.denetim import denetim_yaz

    eposta = (email or "").strip().lower()
    an = simdi()
    satir = (await db.execute(select(OturumKesimleri).where(OturumKesimleri.email == eposta))).scalar_one_or_none()
    if satir is None:
        db.add(OturumKesimleri(email=eposta, gecersiz_once=an, guncelleyen=iptal_eden))
    else:
        satir.gecersiz_once = an
        satir.guncelleyen = iptal_eden
    await db.flush()
    await denetim_yaz(
        db,
        request=request,
        islem="diger",
        tablo="oturumlar",
        kayit_id=None,
        ozet=f"Kullanıcı her yerden çıkarıldı · {eposta}",
        once=None,
        sonra={"gecersiz_once": an.isoformat(), "email": eposta},
    )
    await db.commit()
    onbellegi_temizle()
    return an


# ---------------------------------------------------------------------------
# Temizlik (zamanlı görev)
# ---------------------------------------------------------------------------
async def temizle(db: AsyncSession) -> Dict[str, Any]:
    """30 günden eski biten/iptal oturum satırları ve artık etkisiz kesimler."""
    from core.config import settings

    esik = simdi() - timedelta(days=SAKLAMA_GUN)
    s1 = await db.execute(
        delete(Oturumlar)
        .where(or_(Oturumlar.bitis < esik, Oturumlar.iptal_zamani < esik))
        .execution_options(synchronize_session=False)
    )
    # Kesimden önce verilen jetonların hepsinin süresi dolduysa kesim satırı artık bir şey yapmıyor.
    try:
        omur = int(getattr(settings, "jwt_expire_minutes", 60) or 60)
    except (TypeError, ValueError):
        omur = 60
    kesim_esigi = simdi() - timedelta(minutes=omur) - timedelta(days=1)
    s2 = await db.execute(
        delete(OturumKesimleri)
        .where(OturumKesimleri.gecersiz_once < kesim_esigi)
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    onbellegi_temizle()
    return {"silinen_oturum": int(s1.rowcount or 0), "silinen_kesim": int(s2.rowcount or 0)}
