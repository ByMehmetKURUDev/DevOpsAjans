"""Keşif cevaplarından uzman promptları üretir.

Ne işe yarıyor
--------------
Keşif Asistanı beş soru soruyor (amaç, serbest anlatım, kapsam, zaman,
bütçe) ve ziyaretçiye bir paket öneriyor. Cevaplar orada kalıyordu: işe
başlarken aynı bilgiler baştan, elle brief'e çevriliyordu.

Bu uç o cevapları alıp her rol için ayrı bir çalışma promptu yazıyor
(mimar, yazılımcı, tasarımcı, SEO, PM, test) ve hepsini tek bir zincire
diziyor -- zincirde her adım bir öncekinin çıktısını girdi kabul ediyor.

Neden şablon, neden model değil
-------------------------------
Metinler burada SABİT şablon; dil modeline sorulmuyor. Üç sebep: her
seferinde aynı çıktıyı veriyor (modelin havasına bağlı değil), ücretsiz
ve anahtar gerekmiyor, ve modelin uyduracağı teknik detay riski yok.
Model zaten `aihub` üzerinden keşif özetini yazıyor; burada üretilen
prompt onun çıktısını da taşıyabiliyor (`ozet` alanı).

Uç yalnızca yöneticiye açık: müşteriye gösterilecek bir şey değil, iç
çalışma metni.
"""

import logging
from typing import Dict, List, Optional

from core.database import get_db
from dependencies.entity_guard import entity_guard
from dependencies.kayit_sahipligi import _yonetici_mi
from fastapi import APIRouter, HTTPException, Request, status
from fastapi import Depends as _Depends
from pydantic import BaseModel
from services.musteri_sitesi import eposta_ile_site, kurulum_blogu
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/kesif-brief",
    tags=["kesif_brief"],
    dependencies=[_Depends(entity_guard)],
)


# --------------------------------------------------------------------------
# Sihirbazdaki anahtarların insan diline karşılığı.
# KesifAsistani.tsx içindeki Amac / Kapsam / Zaman / Butce tipleriyle
# birebir aynı; orası değişirse burası da değişmeli.
# --------------------------------------------------------------------------

AMAC = {
    "website": "kurumsal web sitesi",
    "eticaret": "e-ticaret sitesi",
    "saas": "SaaS / abonelikli yazılım",
    "mobil": "mobil uygulama",
    "mevcut": "mevcut sitenin yenilenmesi",
}

KAPSAM = {
    "girisUyelik": "giriş ve üyelik",
    "odeme": "online ödeme",
    "cokDil": "çok dilli içerik",
    "yonetimPaneli": "yönetim paneli",
    "entegrasyon": "dış sistem entegrasyonu",
    "seoReklam": "SEO ve reklam",
}

ZAMAN = {
    "acil": "acil (2-4 hafta)",
    "ceyrek": "bir çeyrek (2-3 ay)",
    "yarim": "yarım yıl",
    "esnek": "esnek",
}

BUTCE = {
    "baslangic": "başlangıç",
    "orta": "orta",
    "genis": "geniş",
    "belirsiz": "henüz belirsiz",
}

#: Kapsam seçimine göre teknik karşılık. Prompt'a "ne yapılacak" diye
#: değil, "hangi kararı vermen gerekiyor" diye giriyor.
KAPSAM_TEKNIK = {
    "girisUyelik": "kimlik doğrulama (oturum süresi, parola sıfırlama, rol modeli)",
    "odeme": "ödeme akışı (sağlayıcı, 3D Secure, iade, webhook idempotency)",
    "cokDil": "çok dillilik (URL şeması, hreflang, içerik senkronu)",
    "yonetimPaneli": "yönetim paneli (yetki matrisi, denetim kaydı)",
    "entegrasyon": "dış entegrasyon (hız sınırı, yeniden deneme, hata kuyruğu)",
    "seoReklam": "SEO ve ölçümleme (sunucu tarafı render, şema, dönüşüm takibi)",
}


class BriefIstegi(BaseModel):
    amac: Optional[str] = ""
    serbest: Optional[str] = ""
    kapsam: List[str] = []
    zaman: Optional[str] = ""
    butce: Optional[str] = ""
    musteri: Optional[str] = ""
    proje: Optional[str] = ""
    #: Keşif asistanının modelden aldığı özet; varsa prompt'a giriyor.
    ozet: Optional[str] = ""
    #: Müşterinin e-postası. Verilirse ve o müşteri için tahsilat
    #: sonrası açılmış bir site kaydı varsa, geri bildirim düğmesinin
    #: gömme satırı prompt'un içine giriyor.
    musteri_eposta: Optional[str] = ""


class RolPromptu(BaseModel):
    id: str
    ad: str
    prompt: str


class BriefYaniti(BaseModel):
    baslik: str
    kunye: str
    roller: List[RolPromptu]
    zincir: str
    #: Geri bildirim düğmesinin kurulum bölümü. Panelde ayrı bir sekme
    #: olarak da gösteriliyor ki tek satır kopyalanabilsin.
    kurulum: str = ""


def _oku(sozluk: Dict[str, str], anahtar: Optional[str], varsayilan: str) -> str:
    return sozluk.get((anahtar or "").strip(), varsayilan)


def _kunye(p: BriefIstegi) -> str:
    kapsamlar = [KAPSAM.get(k, k) for k in p.kapsam] or ["(belirtilmedi)"]
    satirlar = [
        f"Müşteri: {p.musteri or '(belirtilmedi)'}",
        f"Proje: {p.proje or _oku(AMAC, p.amac, '(belirtilmedi)')}",
        f"Tip: {_oku(AMAC, p.amac, '(belirtilmedi)')}",
        f"Kapsam: {', '.join(kapsamlar)}",
        f"Zaman: {_oku(ZAMAN, p.zaman, '(belirtilmedi)')}",
        f"Bütçe: {_oku(BUTCE, p.butce, '(belirtilmedi)')}",
    ]
    if (p.serbest or "").strip():
        satirlar.append(f"Müşterinin kendi anlatımı: {p.serbest.strip()}")
    if (p.ozet or "").strip():
        satirlar.append(f"Keşif özeti: {p.ozet.strip()}")
    return "\n".join(satirlar)


def _teknik_liste(p: BriefIstegi) -> str:
    secili = [KAPSAM_TEKNIK[k] for k in p.kapsam if k in KAPSAM_TEKNIK]
    if not secili:
        return "- (kapsam belirtilmedi; önce kapsamı netleştirecek soruları yaz)"
    return "\n".join(f"- {s}" for s in secili)


#: Her rolün ortak zemini. Tekrarı tek yerde tutuyoruz ki altı promptun
#: kuralları birbirinden ayrışmasın.
ORTAK_KURAL = (
    "KURALLAR\n"
    "- Uydurma. Bilmediğin bir şeyi \"varsayım:\" diye açıkça işaretle.\n"
    "- Fiyat, süre ve sonuç taahhüdü verme; tahmin veriyorsan tahmin olduğunu yaz.\n"
    "- Kararların gerekçesini bir cümleyle yaz; alternatifini neden elediğini söyle.\n"
    "- Çıktı Türkçe olsun, kod ve teknik terimler İngilizce kalabilir."
)


def _roller(p: BriefIstegi, kurulum: str = "") -> List[RolPromptu]:
    kunye = _kunye(p)
    teknik = _teknik_liste(p)
    # Kurulum bölümü yalnızca gerçekten iş yapacak rollere giriyor:
    # yazılımcı satırı ekliyor, test onu kontrol listesine alıyor.
    # SEO ya da tasarımcı promptuna koymak gürültü olurdu.
    ek = f"\n\n{kurulum.strip()}" if kurulum.strip() else ""

    def kur(id_: str, ad: str, govde: str, kurulumlu: bool = False) -> RolPromptu:
        kuyruk = ek if kurulumlu else ""
        return RolPromptu(
            id=id_,
            ad=ad,
            prompt=f"{govde.strip()}\n\nPROJE\n{kunye}{kuyruk}\n\n{ORTAK_KURAL}",
        )

    return [
        kur(
            "mimar",
            "Mimar",
            "ROL: Kıdemli yazılım mimarı.\n\n"
            "GÖREV: Bu proje için teknik mimariyi kur.\n"
            "1. Veri modeli: tablolar, ilişkiler, hangi alanın neden orada olduğu.\n"
            "2. Servis sınırları: neyin tek serviste kalacağı, neyin ayrılacağı.\n"
            "3. Karar verilmesi gereken başlıklar:\n"
            f"{teknik}\n"
            "4. Ölçeklenme ve yedekleme: ilk yıl için yeterli olan en basit kurulum.\n"
            "5. Riskler: en çok hangi üç şey işi geciktirir?\n\n"
            "ÇIKTI: Karar tablosu (karar / seçilen / elenen / gerekçe) + veri modeli şeması.",
        ),
        kur(
            "pm",
            "Proje yöneticisi",
            "ROL: Küçük ekip yöneten proje yöneticisi.\n\n"
            "GÖREV: İşi teslim edilebilir parçalara böl.\n"
            "1. Kapsam: bu sürümde NE VAR, daha önemlisi NE YOK.\n"
            "2. Aşamalar: keşif, tasarım, geliştirme, test, yayın, bakım — "
            "her aşamada biten somut çıktı ne?\n"
            "3. Müşteriden ne zaman ne gerekiyor (içerik, görsel, hesap erişimi)?\n"
            "4. En olası üç gecikme sebebi ve her biri için önlem.\n\n"
            "ÇIKTI: Aşama tablosu (aşama / çıktı / müşteriden gereken / risk).",
        ),
        kur(
            "tasarimci",
            "Tasarımcı",
            "ROL: Ürün tasarımcısı.\n\n"
            "GÖREV: Arayüzün iskeletini çıkar.\n"
            "1. Ana akış: kullanıcı hedefine kaç adımda ulaşıyor? Adımları yaz.\n"
            "2. Ekran listesi ve her ekranda görünen en önemli üç şey.\n"
            "3. Tasarım sistemi: tipografi ölçeği, boşluk düzeni, renk rolleri "
            "(marka rengi değil, ROL: arka plan / vurgu / uyarı / hata).\n"
            "4. Mobil: hangi ekran mobilde bozulmaya en yatkın, nasıl çözülecek?\n"
            "5. Erişilebilirlik: klavye ile gezinme, kontrast, ekran okuyucu etiketleri.\n\n"
            "ÇIKTI: Ekran listesi + akış adımları + tasarım kararları.",
        ),
        kur(
            "yazilimci",
            "Yazılımcı",
            "ROL: Kıdemli full-stack geliştirici.\n\n"
            "GÖREV: Mimarinin kararlarını çalışır koda çevir.\n"
            "1. Dosya ve klasör düzeni: ne nerede duracak?\n"
            "2. Uçtan uca BİR özelliği tam yaz (veri modeli → uç → arayüz → test).\n"
            "3. Hata durumları: ağ koptuğunda, yetki yoksa, veri eksikse ne oluyor?\n"
            "4. Yapılmayacaklar: bu projede gereksiz olan soyutlamaları say.\n\n"
            "ÇIKTI: Çalışır kod + kısa kurulum notu. Kod yorumları neden'i anlatsın.",
            kurulumlu=True,
        ),
        kur(
            "test",
            "Test ve kalite",
            "ROL: Kalite mühendisi.\n\n"
            "GÖREV: Bu iş için doğrulama planı yaz.\n"
            "1. Kabul ölçütleri: her ana akış için \"bitti\" ne demek?\n"
            "2. Kırılma senaryoları: hangi girdi sistemi bozar?\n"
            "3. Performans hedefi: hangi sayfa ne kadar sürede açmalı, nasıl ölçülecek?\n"
            "4. Yayın öncesi kontrol listesi (en fazla 12 madde).\n\n"
            "ÇIKTI: Kontrol listesi + test senaryoları.",
            kurulumlu=True,
        ),
        kur(
            "seo",
            "SEO ve büyüme",
            "ROL: Teknik SEO ve büyüme uzmanı.\n\n"
            "GÖREV: Proje yayına çıktığında bulunur olmasını sağla.\n"
            "1. Sayfa yapısı: hangi sayfa hangi arama niyetini karşılıyor?\n"
            "2. Teknik: render yöntemi, site haritası, şema işaretlemesi, "
            "Core Web Vitals hedefleri.\n"
            "3. İçerik: ilk 90 günde yazılacak başlıklar ve her birinin amacı.\n"
            "4. Ölçüm: hangi olay takip edilecek, başarı hangi sayıyla anlaşılacak?\n\n"
            "ÇIKTI: Sayfa-niyet tablosu + teknik kontrol listesi + içerik planı.\n"
            "Trafik veya sıralama sözü VERME.",
        ),
    ]


def _zincir(p: BriefIstegi, roller: List[RolPromptu], kurulum: str = "") -> str:
    """Rolleri sıralı tek bir prompta dizer.

    Zincirin anlamı: her adım bir önceki adımın çıktısını girdi kabul
    ediyor. Altı promptu ayrı ayrı çalıştırmak yerine bunu tek seferde
    verdiğinde model kendi kararlarını sonraki adımda tutarlı tutuyor.
    """
    adimlar = "\n".join(
        f"{i}. {r.ad}: {r.prompt.splitlines()[2].replace('GÖREV: ', '')}"
        for i, r in enumerate(roller, start=1)
    )
    return (
        "Aşağıdaki projeyi altı adımda uçtan uca planla ve üret.\n"
        "Her adımda bir önceki adımın çıktısını GİRDİ kabul et; çelişki "
        "çıkarsa önceki kararı düzelt ve neyi neden değiştirdiğini yaz.\n"
        "Her adımın sonunda \"Bir sonraki adıma taşınan kararlar\" başlığıyla "
        "en fazla beş madde bırak.\n\n"
        f"ADIMLAR\n{adimlar}\n\n"
        f"PROJE\n{_kunye(p)}\n\n"
        + (f"{kurulum.strip()}\n\n" if kurulum.strip() else "")
        + f"{ORTAK_KURAL}"
    )


@router.post("", response_model=BriefYaniti)
async def brief_uret(
    payload: BriefIstegi,
    request: Request,
    db: AsyncSession = _Depends(get_db),
):
    _, yonetici = _yonetici_mi(request)
    if not yonetici:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu işlem için yönetici olmanız gerekiyor",
        )

    # Geri bildirim düğmesinin gömme satırı prompt'un içine giriyor.
    # Site kaydı burada AÇILMIYOR, yalnızca aranıyor: kayıt tahsilat
    # anında açılıyor. Prompt üretmek tek başına müşteri kaydı
    # yaratmamalı, yoksa teklif aşamasındaki her görüşme müşteri
    # listesine düşerdi.
    site = None
    try:
        site = await eposta_ile_site(db, payload.musteri_eposta)
    except Exception:  # noqa: BLE001 - brief bu yüzden üretilmemiş olmasın
        logger.exception("Musteri sitesi okunamadi: %s", payload.musteri_eposta)

    kurulum = kurulum_blogu(site)
    roller = _roller(payload, kurulum)
    baslik = payload.proje or _oku(AMAC, payload.amac, "Proje")
    return BriefYaniti(
        baslik=baslik,
        kunye=_kunye(payload),
        roller=roller,
        zincir=_zincir(payload, roller, kurulum),
        kurulum=kurulum,
    )
