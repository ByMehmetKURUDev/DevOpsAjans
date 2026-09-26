"""Müşteri sitesi kaydını ve geri bildirim düğmesini kendiliğinden kurar.

Neden var
---------
Geri bildirim düğmesini her müşteri için elle kurmak iki ayrı adım
istiyordu: panele site ekle, sonra gömme kodunu kopyala. Müşteri
sayısı arttıkça bu adım atlanıyor, düğme hiç takılmıyordu.

Buradaki kural tek: tahsilat gerçekleştiği anda o müşteri için site
kaydı ve düğme jetonu KENDİLİĞİNDEN açılıyor. Keşif promptu
üretildiğinde de aynı jeton prompt metnine giriyor -- işi yapan kişi
gömme satırını brief'in içinde hazır buluyor, panelde ayrıca bir yere
gitmesi gerekmiyor.

Tek atanan
----------
Bütün siteler ve düğmeden gelen talepler tek kişiye atanıyor:
`varsayilan_atanan()`. Ajans tek kişilik; her kayıtta "kim baksın"
sorusunu sormak boşa tıklamaydı. Değer ortam değişkeninden okunuyor ki
ekip büyüdüğünde kod değişmesin.

Aynı müşteriye ikinci site açmıyoruz
------------------------------------
Eşleştirme `client_email` (adres verildiyse adresle birlikte) üzerinden.
Her tahsilatta yeni satır açılsaydı bir müşterinin dört ödemesi dört
site kaydı ve dört ayrı jeton üretirdi; hangisinin gömülü olduğu
belirsizleşirdi.
"""

import logging
import os
import secrets
from typing import Optional

from models.client_sites import Client_sites
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: Düğmenin üzerinde ve panelde görünen ajans adı.
AJANS_ADI = "By Mehmet KURU Dev"


def varsayilan_atanan() -> str:
    """Her siteye ve düğme talebine atanacak tek kişi."""
    return (
        os.getenv("VARSAYILAN_ATANAN") or "mehmetkuru.dev@gmail.com"
    ).strip().lower()


def site_adresi() -> str:
    """Kendi sitemizin kökü.

    İstek başlığından türetmiyoruz: gömme kodu, isteği kimin yaptığına
    göre değişmemeli.
    """
    return (os.getenv("SITE_ADRESI") or "https://mehmetkuru.dev").rstrip("/")


def yeni_jeton() -> str:
    return secrets.token_urlsafe(24)


def gomme_kodu(jeton: Optional[str]) -> str:
    """Müşterinin sitesine yapıştırılacak tek satır."""
    return (
        f'<script src="{site_adresi()}/widget.js" '
        f'data-jeton="{jeton or ""}" defer></script>'
    )


def _temiz(deger: Optional[str]) -> str:
    return (deger or "").strip()


async def siteyi_hazirla(
    db: AsyncSession,
    *,
    client_email: Optional[str],
    ad: Optional[str] = None,
    adres: Optional[str] = None,
    kaynak: str = "odeme",
) -> Optional[Client_sites]:
    """Müşteri için site kaydını bulur, yoksa açar; jetonu garanti eder.

    `commit` ÇAĞIRAN TARAFTA: tahsilat ile site kaydı aynı işlemde
    yazılsın. Biri yazılıp diğeri yazılmadan kalırsa ödeme alınmış ama
    düğme kurulmamış olur ve bunu kimse görmez.

    Hiç e-posta yoksa `None` dönüyor: adressiz bir site kaydının
    sahibi belirsiz olurdu, düğmeden gelen talep kimseye düşmezdi.
    """
    eposta = _temiz(client_email).lower()
    if "@" not in eposta:
        return None

    sorgu = select(Client_sites).where(Client_sites.client_email == eposta)
    temiz_adres = _temiz(adres).rstrip("/")
    if temiz_adres:
        sorgu = sorgu.where(Client_sites.adres == temiz_adres)

    sonuc = await db.execute(sorgu.order_by(Client_sites.id.asc()))
    site = sonuc.scalars().first()

    if site is None and temiz_adres:
        # Adresle eşleşen yok: aynı müşterinin adressiz kaydı varsa onu
        # kullan ve adresini doldur. Yoksa aynı müşteri için ikinci bir
        # satır açılırdı.
        sonuc = await db.execute(
            select(Client_sites)
            .where(Client_sites.client_email == eposta)
            .where(Client_sites.adres.is_(None))
            .order_by(Client_sites.id.asc())
        )
        site = sonuc.scalars().first()

    if site is None:
        site = Client_sites(
            client_email=eposta,
            ad=_temiz(ad) or eposta.split("@")[0],
            adres=temiz_adres or None,
            platform="diger",
            durum="aktif",
            # Bakım izni yine KAPALI açılıyor: erişim iznini müşteri
            # verir, tahsilat vermez.
            bakim_izni=False,
            widget_jetonu=yeni_jeton(),
            widget_acik=True,
            atanan=varsayilan_atanan(),
            kaynak=kaynak,
        )
        db.add(site)
        await db.flush()
        logger.info("Musteri sitesi otomatik acildi: %s (kaynak=%s)", eposta, kaynak)
        return site

    # Var olan kaydın eksiklerini tamamlıyoruz; dolu alanlara
    # dokunmuyoruz -- panelde elle düzeltilmiş bir değeri otomatik bir
    # işlem geri almamalı.
    if not _temiz(site.widget_jetonu):
        site.widget_jetonu = yeni_jeton()
    if site.widget_acik is None:
        site.widget_acik = True
    if not _temiz(site.atanan):
        site.atanan = varsayilan_atanan()
    if temiz_adres and not _temiz(site.adres):
        site.adres = temiz_adres
    if not _temiz(site.ad) and _temiz(ad):
        site.ad = _temiz(ad)
    await db.flush()
    return site


async def eposta_ile_site(
    db: AsyncSession, client_email: Optional[str]
) -> Optional[Client_sites]:
    """Müşterinin site kaydı varsa döndürür; YOKSA AÇMIYOR.

    Keşif promptu bunu kullanıyor: kod ancak tahsilat sonrası açılan
    kayıttan çıkıyor. Prompt üretmek tek başına site kaydı açmamalı,
    yoksa teklif aşamasındaki her görüşme müşteri listesine düşerdi.
    """
    eposta = _temiz(client_email).lower()
    if "@" not in eposta:
        return None
    sonuc = await db.execute(
        select(Client_sites)
        .where(Client_sites.client_email == eposta)
        .order_by(Client_sites.id.asc())
    )
    return sonuc.scalars().first()


def kurulum_blogu(site: Optional[Client_sites]) -> str:
    """Keşif promptunun içine giren "düğmeyi tak" bölümü.

    Site kaydı yoksa da bir metin dönüyor: promptu okuyan kişi adımın
    var olduğunu bilsin, jetonun neden boş olduğunu anlasın.
    """
    if site is None or not _temiz(site.widget_jetonu):
        return (
            "GERİ BİLDİRİM DÜĞMESİ\n"
            f"- {AJANS_ADI} geri bildirim düğmesi bu projeye takılacak.\n"
            "- Gömme satırı, müşterinin tahsilatı kaydedildiğinde "
            "kendiliğinden üretiliyor; şu an bu müşteri için tahsilat "
            "görünmüyor, o yüzden jeton boş.\n"
            "- Sayfa iskeletini kurarken </body> öncesinde bu satır için "
            "yer bırak."
        )

    return (
        "GERİ BİLDİRİM DÜĞMESİ (zorunlu teslim şartı)\n"
        f"- Aşağıdaki satır, teslim edilecek sitenin HER sayfasında "
        "</body> etiketinden hemen önce yer alacak:\n"
        f"  {gomme_kodu(site.widget_jetonu)}\n"
        "- Satır hazır; değiştirme, jetonu düzenleme, başka bir adrese "
        "taşıma.\n"
        "- Ek CSS ya da kütüphane gerekmiyor; düğme shadow DOM içinde "
        "çalışıyor, sitenin stilleriyle çakışmıyor.\n"
        f"- Düğme sayfanın sağ kenarında {AJANS_ADI} logosuyla çıkıyor; "
        "gelen istek müşterinin panel hesabına düşüyor.\n"
        "- Yayın öncesi kontrol listesine şunu ekle: düğme görünüyor mu, "
        "test mesajı panele düştü mü?"
    )
