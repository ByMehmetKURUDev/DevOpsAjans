---
title: "Data Classification ve PII Management Nedir? Customer 360 Verilerini Sınıflandırma Rehberi"
description: "Data Classification ve PII Management ile Customer 360 ve pazarlama verilerini sınıflandırma, maskeleme, erişim kontrolü, retention ve aktivasyon guardrail'lerini uçtan uca kurma rehberi."
keywords: "Data Classification, PII Management, kişisel veri sınıflandırma, PII detection, customer data classification, data discovery, data masking, data catalog, Customer 360, marketing data governance"
category: "Veri ve Analitik"
tags:
  - "Veri ve Analitik"
  - "Data Governance"
  - "Customer 360"
date: "2026-09-08"
lang: "tr"
og_title: "Data Classification ve PII Management Rehberi"
og_description: "Customer 360 ve pazarlama verilerini sınıflandırma, PII tespiti, maskeleme, erişim kontrolü ve aktivasyon guardrail'leri için pratik bir mimari rehberi."
og_type: "article"
twitter_card: "summary"
twitter_title: "Data Classification ve PII Management Rehberi"
twitter_description: "Customer 360 ve pazarlama verilerini sınıflandırma, PII tespiti, maskeleme, erişim kontrolü ve aktivasyon guardrail'leri için pratik bir mimari rehberi."
---

# Data Classification ve PII Management Nedir? Customer 360 ve Marketing Verilerini Sınıflandırma Rehberi

## 1. Data Classification Nedir?

Data Classification, verilerin içerik, hassasiyet, kullanım amacı ve erişim riskine göre belirli sınıflara ayrılmasıdır. Amaç yalnızca etiket koymak değil; erişim, saklama, maskeleme, paylaşım, aktivasyon ve imha politikalarını verinin niteliğine göre yönetmektir.

## 2. PII Management Nedir?

PII Management, kişiyi doğrudan veya dolaylı olarak tanımlayabilecek bilgilerin keşfedilmesi, sınıflandırılması, korunması, izlenmesi ve gerektiğinde silinmesi süreçlerinin bütünüdür.

PII kavramı uluslararası teknik literatürde kullanılır. KVKK'daki kişisel veri ve özel nitelikli kişisel veri kavramlarıyla birebir eş anlamlı kabul edilmemelidir. Hukuki sınıflandırma ile teknik veri sınıflandırması birlikte düşünülmelidir.

## 3. Neden Data Classification Gereklidir?

Customer 360 mimarisinde CRM, GA4, GTM, e-ticaret, çağrı merkezi, reklam platformları ve Data Warehouse gibi kaynaklardan çok farklı veri türleri gelir. Hepsine aynı erişim ve saklama kuralını uygulamak güvenlik ve yönetişim açısından sağlıklı değildir.

Örneğin:
- anonim kampanya metriği ile müşteri e-posta adresi aynı erişim seviyesinde olmamalıdır,
- müşteri kimliği ile reklam performans toplamları aynı retention politikasına tabi tutulmamalıdır,
- aktivasyona gönderilecek audience verisi ile ham CRM tablosu aynı risk profiline sahip değildir.

## 4. Örnek Veri Sınıflandırma Modeli

Kuruma göre değişmek üzere başlangıç modeli:

- PUBLIC: herkesle paylaşılabilen veri
- INTERNAL: kurum içi kullanım
- CONFIDENTIAL: sınırlı ekiplerin erişebildiği veri
- PERSONAL: kişisel veri içeren veri
- RESTRICTED: yüksek riskli veya özel koruma gerektiren veri

Bu sınıflar hukuki standart olarak değil, kurum içi politika modeli olarak ele alınmalıdır.

## 5. PII Türleri

### Doğrudan tanımlayıcılar
- e-posta
- telefon
- müşteri numarası
- açık ad-soyad
- hesap numarası

### Dolaylı tanımlayıcılar
Tek başına kişiyi göstermeyebilir ancak başka veri kümeleriyle birleştiğinde kişiyi belirlenebilir hale getirebilir.

Örneğin:
- nadir lokasyon + tarih + cihaz bilgisi,
- müşteri ID + işlem zamanı,
- benzersiz davranış kombinasyonu.

Bu nedenle yalnızca kolon adı üzerinden PII tespiti yapmak yeterli değildir.

## 6. Data Discovery Nasıl Yapılır?

Tipik akış:

Data Sources → Data Discovery → Classification / PII Detection → Data Catalog → Lineage + Policies → Access / Retention / Activation

Kaynaklar:
- CRM
- GA4
- GTM / Data Layer
- e-ticaret
- API
- Data Warehouse
- dosya sistemleri
- destek sistemleri

Tespit yöntemleri:
- kolon adı sözlükleri,
- regex,
- format analizi,
- veri profilleme,
- örnek değer analizi,
- ML tabanlı sınıflandırma,
- insan doğrulaması.

## 7. Otomatik PII Detection

Örneğin e-posta için regex tabanlı bir ilk filtre kullanılabilir. Ancak regex sonucu tek başına kesin hukuki sınıflandırma değildir.

Daha güvenli model:

Detection → Confidence Score → Human Review → Classification → Policy

Confidence düşükse insan incelemesi devreye alınabilir.

## 8. Masking, Tokenization, Pseudonymization ve Anonymization

### Masking
Verinin görünürlüğünü azaltır.

Örnek:
`mehmet@example.com` → `m*****@example.com`

### Tokenization
Asıl değer yerine token kullanır.

`customer_id=4821` → `token_8F21`

### Pseudonymization
Kimliği başka bir değerle ilişkilendirir; yeniden ilişkilendirme için ayrı bilgi bulunabilir.

### Anonymization
Doğru uygulandığında kişinin artık makul yollarla belirlenemeyeceği bir veri yapısı hedeflenir.

Bu kavramlar birbirinin yerine kullanılmamalıdır.

## 9. Customer 360 İçinde Classification

Örnek:

CRM:
- customer_id → PERSONAL / CONFIDENTIAL
- email → PERSONAL
- phone → PERSONAL
- revenue → CONFIDENTIAL

GA4:
- aggregate revenue → INTERNAL
- raw user-level event → policy'ye bağlı daha yüksek sınıf

Data Warehouse:
- customer dimension → PERSONAL / CONFIDENTIAL
- KPI aggregate → INTERNAL

Activation:
- audience membership → PERSONAL / RESTRICTED olarak politika ile yönetilebilir.

## 10. Access Control ile Birlikte Çalışma

Classification tek başına koruma sağlamaz.

Önerilen model:

Classification → Access Policy → Masking → Audit Log → Review

Örneğin marketing analyst aggregate revenue görebilirken müşteri e-posta kolonuna erişemeyebilir.

## 11. Retention ile Birlikte Çalışma

Data Classification, retention politikasını da beslemelidir.

Örneğin:
- raw event → kısa süre,
- customer profile → amaç ve ilişkiye göre,
- campaign aggregate → daha uzun analiz süresi,
- temporary activation file → çok kısa süre.

Burada tek bir "müşteri verisi 24 ay tutulur" kuralı yerine veri türü + amaç + hukuki/politika koşullarına göre sınıf bazlı retention daha sağlıklıdır.

## 12. Activation Guardrails

Customer 360 verisi Google Ads, CRM veya başka aktivasyon sistemlerine gönderilecekse sınıflandırma bir kontrol kapısı olmalıdır.

Örnek:

Restricted data
→ policy check
→ eligible audience?
→ consent / legal basis check where required
→ destination check
→ activation
→ audit

Identity, consent ve legal basis birbirinden ayrı kavramlardır.

## 13. Classification Drift

Verinin yapısı zamanla değişebilir.

Örneğin başlangıçta:

`campaign_id | revenue`

olan bir tabloya daha sonra:

`email | phone | customer_id`

kolonları eklenebilir.

Schema değişikliği veri sınıfını da değiştirebilir. Bu nedenle classification yalnızca ilk keşif aşamasında yapılmamalıdır.

## 14. Data Classification Metadata Örneği

```json
{
  "dataset": "crm.customer",
  "classification": "PERSONAL",
  "contains_pii": true,
  "owner": "CRM Data Owner",
  "retention_class": "ACTIVE_RELATIONSHIP",
  "masking_required": true,
  "activation_allowed": false
}
```

Bu metadata Data Catalog, Data Lineage ve Access Control sistemleriyle ilişkilendirilebilir.

## 15. 30 Günlük MVP

### 1. Hafta
- veri kaynaklarını listele,
- kritik datasetleri seç,
- sınıflandırma sözlüğünü oluştur.

### 2. Hafta
- PII detection kur,
- örnekleme ve confidence modeli oluştur,
- insan doğrulaması ekle.

### 3. Hafta
- access policy,
- masking,
- retention,
- activation guardrails.

### 4. Hafta
- dashboard,
- drift detection,
- audit,
- exception workflow.

## 16. Sık Hatalar

- PII'yi sadece kolon adına göre tespit etmek
- teknik PII kavramını doğrudan hukuki kategori sanmak
- classification yapıp access control uygulamamak
- retention ile classification arasında bağlantı kurmamak
- activation öncesi veri politikası kontrolü yapmamak
- schema değişikliklerini izlememek
- tokenization ile anonymization'ı aynı kabul etmek

## Sonuç

Data Classification, Customer 360 ve Marketing Data Governance mimarisinin temel kontrol katmanlarından biridir. Sağlıklı bir mimaride veri yalnızca depolanmaz; keşfedilir, sınıflandırılır, sahiplenilir, erişimi kontrol edilir, lineage ile izlenir, retention ile yönetilir ve aktivasyon öncesinde politika kontrollerinden geçirilir.

Önerilen mimari:

Data Sources
→ Data Discovery
→ Classification / PII Detection
→ Data Catalog
→ Data Lineage
→ Access Control
→ Retention
→ Activation Guardrails
→ Monitoring / Audit
