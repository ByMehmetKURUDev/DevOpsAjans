---
title: "Frontend Mimarisi Nasıl Kurulur?"
description: "Ölçeklenebilir frontend mimarisi: klasör yapısı, katman ayrımı, durum yönetimi stratejisi, tasarım sistemi, veri katmanı, test yaklaşımı ve teknik borç yönetimi."
keywords: "frontend mimarisi, klasör yapısı, katmanlı mimari, durum yönetimi, tasarım sistemi, bileşen mimarisi, feature-based yapı, teknik borç"
category: "Web Geliştirme"
tags:
  - "Web Geliştirme"
  - "Mimari"
  - "Frontend"
date: "2026-08-05"
lang: "tr"
og_title: "Frontend Mimarisi Nasıl Kurulur?"
og_description: "Katman ayrımı, durum yönetimi ve tasarım sistemiyle ölçeklenebilir frontend."
og_type: "article"
twitter_card: "summary"
twitter_title: "Frontend Mimarisi Nasıl Kurulur?"
twitter_description: "Sürdürülebilir frontend mimarisinin temel kararları."
---
Frontend mimarisi, kod büyüdükçe hız kaybetmeyen bir yapı kurmakla ilgilidir. Küçük bir projede her yaklaşım işe yarar; sorunlar ekip ve kod tabanı büyüdüğünde çıkar: bir değişikliğin nereyi etkileyeceği kestirilemez hâle gelir, aynı iş birden fazla yerde farklı biçimde yapılır ve yeni bir geliştiricinin uyum süresi uzar.

## 1. Klasör Yapısı: Özellik Odaklı Organizasyon

Teknik türe göre organizasyon (`components/`, `hooks/`, `utils/` altında her şey) küçük projelerde çalışır ancak büyüdükçe ilişkili dosyalar birbirinden uzaklaşır. Özellik odaklı yapı daha iyi ölçeklenir:

```
src/
├── app/              # uygulama kabuğu, router, sağlayıcılar
├── features/
│   ├── auth/         # bu özelliğe ait bileşen, hook, servis, tip
│   ├── projects/
│   └── billing/
├── shared/
│   ├── ui/           # tasarım sistemi bileşenleri
│   ├── lib/          # yardımcı fonksiyonlar
│   └── api/          # istemci yapılandırması
└── pages/            # rota giriş noktaları
```

Kural: bir özellik klasörü kendi içinde bütündür; başka bir özelliğin iç dosyalarına doğrudan erişmez. Paylaşılması gereken şey `shared/` altına yükseltilir.

## 2. Katman Ayrımı

Üç katman net biçimde ayrılmalıdır:

**Sunum katmanı.** Yalnızca görüntüleme ve kullanıcı etkileşimi. İş kuralı ve API çağrısı içermez.

**Uygulama katmanı.** İş kuralları, durum yönetimi, akış kontrolü. Bileşenlerden bağımsız test edilebilir.

**Veri katmanı.** API iletişimi, önbellek, veri dönüşümü, hata normalizasyonu.

Bu ayrım sağlandığında bir API sözleşmesi değiştiğinde yalnızca veri katmanı, bir tasarım değiştiğinde yalnızca sunum katmanı etkilenir.

## 3. Durum Yönetimi Stratejisi

Tek bir global depo her şeyin çözümü değildir. Durum türüne göre karar verilir:

| Durum türü | Uygun yaklaşım |
|---|---|
| Yerel UI durumu (açık/kapalı, form girdisi) | Bileşen içi durum |
| Sunucu verisi | Veri getirme/önbellek kütüphanesi |
| URL'de yaşaması gereken durum (filtre, sekme) | Rota parametreleri |
| Gerçekten global durum (tema, oturum) | Hafif global depo veya context |
| Türetilmiş veri | Hesaplama, ayrı durumda tutmayın |

En yaygın hata, sunucu verisini global depoya kopyalamaktır. Bu, senkronizasyon sorunları ve gereksiz karmaşıklık üretir.

## 4. Tasarım Sistemi

Tutarlılık ve hız için paylaşılan bir bileşen katmanı gerekir:

- tasarım token'ları (renk, boşluk, tipografi, gölge, yarıçap) tek kaynaktan tanımlanır,
- temel bileşenler (buton, girdi, kart, modal, tablo) tüm durumlarıyla (varsayılan, hover, odak, devre dışı, hata, yükleniyor) üretilir,
- erişilebilirlik bileşen düzeyinde çözülür; her kullanımda tekrar düşünülmez,
- bileşenler iş kuralı içermez, yalnızca sunum sorumluluğu taşır.

## 5. Veri Katmanı Tasarımı

- API istemcisi tek bir yerde yapılandırılır (temel URL, kimlik doğrulama başlıkları, hata yakalama),
- sunucu yanıtları uygulama içi tiplere dönüştürülür; API şeması doğrudan bileşenlere sızmaz,
- hata durumları normalize edilir; her bileşen kendi hata biçimini yorumlamaz,
- yükleme, boş ve hata durumları standart bir kalıpla ele alınır,
- yeniden deneme ve zaman aşımı politikaları merkezi olarak tanımlanır.

## 6. Tip Güvenliği

TypeScript kullanımı mimarinin bir parçasıdır. Etkili uygulama: API sözleşmelerinden tip üretimi, `any` kullanımının sınırlandırılması, ayrık birleşim tipleriyle durum modelleme (yükleniyor / başarılı / hata) ve paylaşılan tiplerin tek bir yerde tanımlanması.

## 7. Test Stratejisi

Kapsam hedefi değil, risk odaklı test yaklaşımı benimsenir:

- **Birim testleri:** İş kuralları ve yardımcı fonksiyonlar.
- **Bileşen testleri:** Kritik etkileşimler ve erişilebilirlik davranışı.
- **Entegrasyon testleri:** Özellik düzeyinde akışlar.
- **Uçtan uca testler:** Yalnızca en kritik kullanıcı yolları (giriş, ödeme, form gönderimi).

Kırılgan ve yavaş test paketi zamanla görmezden gelinir; az sayıda güvenilir test daha değerlidir.

## 8. Performans Kararları Mimaride Verilir

Rota bazlı kod bölme, ağır bağımlılıkların ertelenmesi, görsel stratejisi ve sunucu tarafı render kararı mimari düzeyde alınmalıdır. Sonradan eklenen optimizasyonlar, yapı buna uygun kurulmadıysa sınırlı fayda üretir.

## 9. Teknik Borç Yönetimi

Borç kaçınılmazdır; yönetilmemesi sorundur. Uygulanabilir pratikler: bilinçli kısayolların gerekçesiyle kaydedilmesi, her dönemde borç azaltmaya sabit kapasite ayrılması, tekrarlayan kod kalıplarının paylaşılan katmana yükseltilmesi ve mimari kararların kısa kayıtlarla belgelenmesi.

## Sık Sorulan Sorular

**Küçük projede bu yapı fazla mı?** Katman ayrımı ve token tabanlı tasarım sistemi küçük projede de maliyetsizdir. Karmaşık durum yönetimi ve çok katmanlı soyutlama ise erken eklenmemelidir.

**Monorepo gerekli mi?** Birden fazla uygulama paylaşılan bileşen kullanıyorsa avantajlıdır. Tek uygulamada ek karmaşıklık getirir.

**Mimari kararlar nasıl belgelenir?** Kısa karar kayıtları (bağlam, seçenekler, seçim, gerekçe) yeterlidir. Uzun dokümanlar güncellenmediği için değerini kaybeder.
