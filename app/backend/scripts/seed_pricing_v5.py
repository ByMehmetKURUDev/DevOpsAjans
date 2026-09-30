"""Fiyatlandırma v5 başlangıç verisi.

Onaylanmış spec'ten birebir kopyalandı (bkz. claude.ai Projesi:
`claude/fiyatlandirma-sistemi-v5-spec.md`) — isim, fiyat ve Türkçe metin
değiştirilmedi.

Çalıştırma:
    DATABASE_URL=... python -m scripts.seed_pricing_v5

Var olan `kod`/`ad` eşleşen satırları GÜNCELLER (upsert), tekrar
çalıştırmak yinelenen satır oluşturmaz — bu script hem ilk kurulumda
hem "veriyi düzelttim, tekrar yükle" durumunda güvenle kullanılabilir.
"""

import asyncio
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

logger = logging.getLogger(__name__)

PROFILES = [
    {"kod": "kurumsal", "ad": "Kurumsal", "carpan": 1.0, "etiket": "Fatura, KVKK, öncelikli destek", "sira": 1},
    {"kod": "startup", "ad": "Startup", "carpan": 0.85, "etiket": "Deck, hızlı lansman", "sira": 2},
    {"kod": "stk", "ad": "STK", "carpan": 0.6, "etiket": "STK/dernek indirimi", "sira": 3},
    {"kod": "bireysel", "ad": "Bireysel", "carpan": 0.7, "etiket": "Bireysel/freelancer indirimi", "sira": 4},
    {"kod": "egitim", "ad": "Eğitim", "carpan": 0.75, "etiket": "LMS, sertifika", "sira": 5},
]

SCALES = [
    {
        "kod": "ALFA", "sira": 1, "ad": "Alfa Serisi", "alt_baslik": "GİRİŞ",
        "calisan_araligi": "2-10 çalışan",
        "aciklama": "2-10 çalışan. İlk profesyonel site, hızlı canlıya çıkış.",
        "baz_aylik_fiyat_usd": 540,
        "ozellikler": [
            "Landing + Kurumsal 5 sayfa",
            "Figma → Next.js, %90+ PageSpeed",
            "KVKK + Sözleşme altyapısı hazır",
            "Temel SEO & Analytics kurulumu",
            "Mülkiyet %100 sende, panel dahil",
        ],
        "eklenti_limiti": "6 eklenti", "revizyon_saat": "2s", "populer": False,
        "karsilastirma": {
            "hosting": "Vercel Başlangıç", "sla": "En iyi çaba", "panel": "Hafif CMS",
            "devops": "Yok", "mulkiyet": "✓ %100 sende", "ads": "—", "seo": "Temel",
        },
    },
    {
        "kod": "BETA", "sira": 2, "ad": "Beta Serisi", "alt_baslik": "BÜYÜME",
        "calisan_araligi": "10-50 çalışan",
        "aciklama": "10-50 çalışan. E-ticaret + entegrasyonlar, ödeme/kargo/CRM.",
        "baz_aylik_fiyat_usd": 1140,
        "ozellikler": [
            "E-Ticaret (100 SKU) + Ödeme/Kargo",
            "CRM & E-posta otomasyon entegrasyonu",
            "Ads kurulumu + dönüşüm takibi",
            "Aylık 8 saat revizyon & bakım",
            "Yedekleme, SSL, uptime izleme",
        ],
        "eklenti_limiti": "7 eklenti", "revizyon_saat": "8s", "populer": True,
        "karsilastirma": {
            "hosting": "Vercel Standart", "sla": "%99.5", "panel": "E-ticaret CMS",
            "devops": "Temel", "mulkiyet": "✓ %100 sende", "ads": "Kurulum dahil", "seo": "Orta",
        },
    },
    {
        "kod": "OMEGA", "sira": 3, "ad": "Omega Serisi", "alt_baslik": "ÖLÇEK",
        "calisan_araligi": "50+ çalışan",
        "aciklama": "50+ çalışan. SaaS, multi-region, SLA, yüksek trafik.",
        "baz_aylik_fiyat_usd": 2280,
        "ozellikler": [
            "SaaS / Multi-tenant mimari",
            "Multi-region, edge cache, %99.9 SLA",
            "Sözleşme + KVKK + Veri işleme paketi",
            "DevOps & Güvenlik sertleştirme",
            "Aylık 16 saat senior geliştirme",
        ],
        "eklenti_limiti": "7 eklenti", "revizyon_saat": "16s", "populer": False,
        "karsilastirma": {
            "hosting": "Multi-region edge", "sla": "%99.9", "panel": "Custom admin",
            "devops": "İleri", "mulkiyet": "✓ %100 sende", "ads": "Yönetim dahil", "seo": "İleri",
        },
    },
    {
        "kod": "SIGMA", "sira": 4, "ad": "Sigma Serisi", "alt_baslik": "BAĞIMSIZ",
        "calisan_araligi": "Custom çalışan",
        "aciklama": "Σ mantığı — toplamı toplayan, kendi paketini kuranlar için.",
        "baz_aylik_fiyat_usd": 3360,
        "ozellikler": [
            "Custom scope, sınırsız entegrasyon",
            "Beyaz etiket + kendi domaininde panel",
            "Sınırsız revizyon havuzu (Kullandıkça Öde)",
            "DevOps, güvenlik, ölçek danışmanlığı",
            "Mülkiyet %100 sende + kod teslimi",
        ],
        "eklenti_limiti": "8 eklenti", "revizyon_saat": "Kullandıkça Öde", "populer": False,
        "karsilastirma": {
            "hosting": "Custom / kendi altyapın", "sla": "Sözleşmeli SLA", "panel": "Beyaz etiket",
            "devops": "Danışmanlık", "mulkiyet": "✓ %100 sende + kod", "ads": "Danışmanlık", "seo": "Danışmanlık",
        },
    },
]

# kategori, ad, baz_fiyat_usd, tek_seferlik, not_metni, yeni
SERVICES = [
    ("YAZILIM", "Web Tasarım & Kodlama", 900, False, None, False),
    ("TASARIM", "Landing Page (Tek Sayfa)", 450, False, None, False),
    ("YAZILIM", "Kurumsal Site (5 Sayfa)", 800, False, None, False),
    ("E-TICARET/GROWTH", "E-Ticaret Kurulumu", 1600, False, None, False),
    ("E-TICARET/GROWTH", "Ödeme Entegrasyonu", 300, False, None, False),
    ("E-TICARET/GROWTH", "Kargo Entegrasyonu", 250, False, None, False),
    ("E-TICARET/GROWTH", "Pazaryeri Entegrasyonu", 400, False, None, False),
    ("ALTYAPI", "CRM Entegrasyonu", 350, False, None, False),
    ("SEO/BÜYÜME", "E-posta Otomasyonu", 200, False, None, False),
    ("YAZILIM", "Figma → Next.js Dönüşüm", 600, False, None, False),
    ("YAZILIM", "Çok Dilli Altyapı", 300, False, None, False),
    ("MARKA/İÇERIK", "Blog / İçerik Modülü", 250, False, None, False),
    ("YAZILIM", "Üyelik Sistemi", 500, False, None, False),
    ("YAZILIM", "Randevu Sistemi", 400, False, None, False),
    ("YAZILIM", "Rezervasyon Modülü", 450, False, None, False),
    ("YAZILIM", "Etkinlik / Takvim", 350, False, None, False),
    ("YAZILIM", "Eğitim Portalı / LMS", 1200, False, None, False),
    ("YAZILIM", "Admin Panel (Custom)", 800, False, None, False),
    ("ALTYAPI", "API Geliştirme", 600, False, None, False),
    ("SEO/BÜYÜME", "SEO Temel Kurulum", 300, False, None, False),
    ("SEO/BÜYÜME", "SEO İleri (Teknik)", 700, False, None, False),
    ("SEO/BÜYÜME", "Google Ads Kurulum", 250, False, None, False),
    ("SEO/BÜYÜME", "Meta Ads Kurulum", 250, False, None, False),
    ("SEO/BÜYÜME", "Analytics + Search Console", 150, False, None, False),
    ("ALTYAPI", "Hız Optimizasyonu", 200, False, None, False),
    ("ALTYAPI", "KVKK & Sözleşme Sayfaları", 180, False, None, False),
    ("ALTYAPI", "SSL & Domain Yönetimi", 80, False, None, False),
    ("ALTYAPI", "Yedekleme & İzleme", 120, False, None, False),
    ("ALTYAPI", "Bakım / Aylık Destek", 200, False, "aylık", False),
    ("MARKA/İÇERIK", "İçerik Üretimi (10 sayfa)", 500, False, None, False),
    ("TASARIM", "Görsel & İkon Seti", 300, False, None, False),
    ("ALTYAPI", "Göç / Taşıma Hizmeti", 350, False, None, False),
    ("ALTYAPI", "Eğitim & Devretme", 200, False, None, False),
    ("MARKA/İÇERIK", "Logo & Brand Kit", 500, True, "tek seferlik", False),
    ("TASARIM", "Pitch Deck Tasarım", 600, False, None, False),
    ("ALTYAPI", "API Dokümantasyonu", 400, False, None, False),
    ("ALTYAPI", "Web Sitesi Hız Optimizasyonu", 300, False, None, False),
    ("ALTYAPI", "KVKK/GDPR Uyum Paketi", 350, False, None, False),
    ("ALTYAPI", "E-posta & Domain Migrasyon", 200, False, None, False),
    ("SEO/BÜYÜME", "A/B Test Kurulumu", 450, False, None, False),
    ("AI/OTOMASYON", "Chatbot Eğitim & Fine-tuning", 500, False, None, False),
    ("ALTYAPI", "Yedekleme & Felaket Kurtarma", 250, False, "aylık", False),
    ("SEO/BÜYÜME", "Analytics & Dashboard (Looker/Plausible)", 350, False, None, False),
    ("MARKA/İÇERIK", "Brand Strateji Workshop", 800, False, None, False),
    ("MARKA/İÇERIK", "Metin Yazarlığı & UX Copy", 250, False, None, False),
    ("SEO/BÜYÜME", "E-posta Pazarlama Otomasyonu", 300, False, "Mailchimp/Brevo + $99/ay", False),
    ("AI/OTOMASYON", "WhatsApp Business API Entegrasyonu", 400, False, "+$49/ay", False),
    ("ALTYAPI", "CRM Kurulumu (HubSpot/Pipedrive)", 500, False, None, False),
    ("YAZILIM", "Membership / Abonelik Sistemi", 700, False, None, False),
    ("YAZILIM", "Online Randevu Sistemi", 350, False, None, False),
    ("MARKA/İÇERIK", "Blog & İçerik Sistemi Kurulumu", 300, False, None, False),
    ("YAZILIM", "Çok Dilli Yapı (i18n) Kurulumu", 400, False, None, False),
    ("YAZILIM", "PWA Dönüşümü", 500, False, None, False),
    ("ALTYAPI", "Güvenlik Hardening & WAF", 350, False, None, False),
    ("SEO/BÜYÜME", "Dönüşüm Hunisi Audit", 400, False, None, False),
    ("MARKA/İÇERIK", "Video Prodüksiyon & Kurgu", 800, True, "tek seferlik landing + $299/ay kesit üretimi", True),
    ("MARKA/İÇERIK", "Podcast Sitesi + RSS + Transkript AI", 900, True, "tek seferlik", True),
    ("İLERI/WEB3", "NFT / Token Gated Erişim", 1200, False, "Web3 wallet connect", True),
    ("AI/OTOMASYON", "AI Ses Klonlama & Sesli Blog", 600, False, "kurulum + $99/ay", True),
    ("İLERI/WEB3", "3D / WebGL Showroom", 1500, False, "Three.js", True),
    ("E-TICARET/GROWTH", "Çok Satıcılı Marketplace", 8500, False, "satıcı paneli + komisyon $1.800/ay opsiyon", True),
    ("İLERI/WEB3", "IoT Dashboard (MQTT)", 2000, False, "cihaz verisi + $350/ay", True),
    ("YAZILIM", "Oyunlaştırma & Rozet Sistemi", 700, False, "puan, seviye, rozet", True),
    ("E-TICARET/GROWTH", "Affiliate / Referans Sistemi", 650, False, "referans + payout", True),
    ("E-TICARET/GROWTH", "B2B Portal (Bayi / Fiyat / Sipariş)", 6500, False, "bayi girişli $1.200/ay opsiyon", True),
    ("ALTYAPI", "Headless CMS Migrasyon", 800, False, "Contentful/Sanity/Strapi", True),
    ("YAZILIM", "Web + Mobil Uygulama Paket", 4500, False, "PWA + APK", True),
    ("AI/OTOMASYON", "AI Görsel Üretim Hattı", 400, False, "ürün foto çoğaltma + $79/ay", True),
    ("AI/OTOMASYON", "Sesli Asistan Entegrasyonu", 700, False, "Alexa/Google", True),
    ("E-TICARET/GROWTH", "Abonelik & Faturalandırma", 600, False, "Stripe Billing", True),
    ("E-TICARET/GROWTH", "Sadakat & Puan Sistemi", 550, False, None, True),
    ("YAZILIM", "Etkinlik & Biletleme Sistemi", 850, False, None, True),
    ("YAZILIM", "Emlak İlan & Filtreleme", 1200, False, None, True),
    ("YAZILIM", "İş İlanları / Kariyer Board", 900, False, None, True),
    ("YAZILIM", "Otel / Oda Rezervasyon", 1400, False, None, True),
    ("YAZILIM", "Restoran QR Menü & Online Sipariş", 1000, False, None, True),
    ("YAZILIM", "Bağış & Fon Toplama Platformu", 800, False, "STK için −%40, yani $480", True),
    ("YAZILIM", "LMS İleri (Quiz/Sertifika/Ödeme)", 1800, False, None, True),
    ("YAZILIM", "Topluluk Platformu", 1100, False, "Discord/Slack entegre forum", True),
    ("SEO/BÜYÜME", "CRO & Growth Deneyleri", 650, False, "aylık $650/ay, 3 deney", True),
]
assert len(SERVICES) == 80, f"beklenen 80 hizmet, bulunan {len(SERVICES)}"

# scale_kod, ad, baz_fiyat_usd, sira
ADDONS = [
    ("ALFA", "Çok Dilli (TR/EN)", 80, 1),
    ("ALFA", "Blog Modülü", 60, 2),
    ("ALFA", "Randevu/Rezervasyon", 90, 3),
    ("ALFA", "Gelişmiş SEO Paketi", 120, 4),
    ("ALFA", "Hız + %95 Skor Garantisi", 70, 5),
    ("ALFA", "Ek Revizyon Saati (5s)", 40, 6),
    ("BETA", "Pazaryeri Entegrasyonu", 180, 1),
    ("BETA", "Üyelik & Sadakat Sistemi", 150, 2),
    ("BETA", "Gelişmiş Filtre & Arama", 120, 3),
    ("BETA", "WhatsApp Sipariş Botu", 90, 4),
    ("BETA", "Meta + Google Ads Yönetimi", 220, 5),
    ("BETA", "A/B Test Altyapısı", 110, 6),
    ("BETA", "Ek 20 SKU Yükleme", 70, 7),
    ("OMEGA", "SaaS Abonelik & Faturalama", 320, 1),
    ("OMEGA", "Rol Bazlı Yetki (RBAC)", 180, 2),
    ("OMEGA", "Audit Log & SSO", 220, 3),
    ("OMEGA", "Özel API & Webhook", 260, 4),
    ("OMEGA", "Yük Testi + SLO Raporu", 200, 5),
    ("OMEGA", "7/24 PagerDuty Entegrasyonu", 280, 6),
    ("OMEGA", "KVKK Veri Haritası", 150, 7),
    ("SIGMA", "Özel Modül Geliştirme (10 saat)", 400, 1),
    ("SIGMA", "AI Asistan Entegrasyonu", 350, 2),
    ("SIGMA", "Mobil App (Expo) Köprüsü", 480, 3),
    ("SIGMA", "Kurumsal Eğitim (1 gün)", 600, 4),
    ("SIGMA", "Kaynak Kod Audit", 300, 5),
    ("SIGMA", "Özel SLA & Hukuki Çerçeve", 250, 6),
    ("SIGMA", "Sınırsız Eklenti Hakkı", 200, 7),
    ("SIGMA", "CTO Office Saatliği (saat)", 180, 8),
]
assert len(ADDONS) == 28, f"beklenen 28 eklenti, bulunan {len(ADDONS)}"

AI_PM_TIERS = [
    {"kod": "starter_ai", "ad": "Starter — AI", "fiyat_aylik_usd": 900, "rozet": "EN HIZLI", "sira": 1,
     "ozellikler": ["1 AI otomasyon (n8n/Make)", "1 entegrasyon (CRM/WhatsApp/E-posta)", "Hata log+monitoring", "Dokümantasyon"]},
    {"kod": "yonetim_pm", "ad": "Yönetim — PM", "fiyat_aylik_usd": 1400, "rozet": "EN DÜZENLİ", "sira": 2,
     "ozellikler": ["Linear/Notion kurulum", "Haftalık sprint+rapor", "2 revizyon döngüsü", "Ekip onboarding"]},
    {"kod": "kombin_ai_pm", "ad": "Kombin — AI + PM", "fiyat_aylik_usd": 2200, "rozet": "POPÜLER ✓", "sira": 3,
     "ozellikler": ["3 otomasyon+yönetim paneli", "CRM+Ads+E-posta entegre", "A/B test+analytics", "12 ay destek"]},
    {"kod": "kurumsal_olcek", "ad": "Kurumsal — Ölçek", "fiyat_aylik_usd": 4800, "rozet": "ÖLÇEK", "sira": 4,
     "ozellikler": ["Sınırsız otomasyon", "Özel API+SSO+Audit", "SLA+7/24 izleme", "CTO desteği"]},
]


async def _upsert(db: AsyncSession, model_cls, match_fields: dict, data: dict):
    conditions = [getattr(model_cls, k) == v for k, v in match_fields.items()]
    existing = (await db.execute(select(model_cls).where(*conditions))).scalars().first()
    if existing:
        for k, v in data.items():
            setattr(existing, k, v)
        return existing, False
    obj = model_cls(**data)
    db.add(obj)
    return obj, True


async def seed(db: AsyncSession) -> dict:
    from models.pricing import Ai_pm_tiers, Pricing_addons, Pricing_profiles, Pricing_scales, Pricing_services

    counts = {"pricing_scales": 0, "pricing_profiles": 0, "pricing_services": 0, "pricing_addons": 0, "ai_pm_tiers": 0}

    for row in PROFILES:
        _, created = await _upsert(db, Pricing_profiles, {"kod": row["kod"]}, row)
        counts["pricing_profiles"] += 1 if created else 0

    for row in SCALES:
        data = dict(row)
        data["ozellikler"] = json.dumps(data["ozellikler"], ensure_ascii=False)
        data["karsilastirma"] = json.dumps(data["karsilastirma"], ensure_ascii=False)
        _, created = await _upsert(db, Pricing_scales, {"kod": row["kod"]}, data)
        counts["pricing_scales"] += 1 if created else 0

    for kategori, ad, baz_fiyat_usd, tek_seferlik, not_metni, yeni in SERVICES:
        data = {
            "kategori": kategori, "ad": ad, "baz_fiyat_usd": baz_fiyat_usd,
            "tek_seferlik": tek_seferlik, "not_metni": not_metni, "yeni": yeni,
        }
        _, created = await _upsert(db, Pricing_services, {"ad": ad}, data)
        counts["pricing_services"] += 1 if created else 0

    for scale_kod, ad, baz_fiyat_usd, sira in ADDONS:
        data = {"scale_kod": scale_kod, "ad": ad, "baz_fiyat_usd": baz_fiyat_usd, "birim": "ay", "sira": sira}
        _, created = await _upsert(db, Pricing_addons, {"scale_kod": scale_kod, "ad": ad}, data)
        counts["pricing_addons"] += 1 if created else 0

    for row in AI_PM_TIERS:
        data = dict(row)
        data["ozellikler"] = json.dumps(data["ozellikler"], ensure_ascii=False)
        _, created = await _upsert(db, Ai_pm_tiers, {"kod": row["kod"]}, data)
        counts["ai_pm_tiers"] += 1 if created else 0

    await db.commit()
    return counts


async def main():
    from core.database import Base

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL ortam değişkeni gerekli")

    engine = create_async_engine(database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        counts = await seed(db)

    print("Fiyatlandırma v5 verisi yüklendi (yeni eklenen satır sayısı):")
    for table, n in counts.items():
        print(f"  {table}: +{n}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
