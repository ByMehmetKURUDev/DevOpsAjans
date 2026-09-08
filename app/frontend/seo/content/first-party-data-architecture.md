---
title: "Birinci Taraf Veri (First-Party Data) Mimarisi"
description: "Birinci taraf veri mimarisi nasıl kurulur? Veri toplama stratejisi, rıza yönetimi, sunucu tarafı ölçüm, veri modeli, aktivasyon ve üçüncü taraf çerez sonrası dönem."
keywords: "birinci taraf veri, first-party data, veri mimarisi, rıza yönetimi, sunucu tarafı ölçüm, çerezsiz ölçüm, veri stratejisi"
category: "Veri ve Analitik"
tags:
  - "Veri ve Analitik"
  - "Veri Mimarisi"
  - "Gizlilik"
date: "2026-09-12"
lang: "tr"
og_title: "Birinci Taraf Veri Mimarisi"
og_description: "Çerez sonrası dönemde dayanıklı veri altyapısı kurmak."
og_type: "article"
twitter_card: "summary"
twitter_title: "Birinci Taraf Veri Mimarisi"
twitter_description: "Veri toplama, rıza ve aktivasyon katmanları."
---

# Birinci Taraf Veri (First-Party Data) Mimarisi

Üçüncü taraf tanımlayıcıların kısıtlandığı bir ortamda, pazarlama etkinliğinin temeli kendi topladığınız veriye kaydı. Birinci taraf veri, kullanıcıyla doğrudan ilişkiniz üzerinden, açık bir izinle ve tanımlı bir amaç için topladığınız veridir. Bu mimariyi kurmak teknik olduğu kadar ürün ve etik bir tasarım işidir.

## 1. Birinci Taraf Verinin Kapsamı

- site ve uygulama davranış verisi (görüntüleme, arama, sepet, akış adımları),
- işlem verisi (siparişler, iadeler, abonelikler),
- profil ve tercih verisi (üyelik bilgileri, ilgi alanları, bildirim tercihleri),
- iletişim verisi (destek talepleri, çağrı kayıtları, sohbet geçmişi),
- pazarlama etkileşimi (e-posta açma/tıklama, kampanya yanıtları),
- anket ve doğrudan beyan verisi (kullanıcının kendi bildirdiği bilgi).

Son kategori özellikle değerlidir: kullanıcının açıkça beyan ettiği tercih, davranışsal çıkarımdan hem daha doğru hem de gizlilik açısından daha savunulabilirdir.

## 2. Mimari Katmanlar

**Toplama katmanı.** Web, uygulama, sunucu ve iş sistemlerinden olay toplama. Merkezi bir olay şeması ve veri katmanı sözleşmesi üzerine kurulur.

**Rıza katmanı.** Toplama öncesinde rıza durumunu belirler ve tüm aşağı akışta uygular. Mimarinin en kritik parçasıdır; sonradan eklenmesi en zor olanıdır.

**Depolama ve model katmanı.** Ham olayların saklandığı ve iş anlamı kazandığı katman. Veri ambarı burada durur.

**Kimlik katmanı.** Dağınık kimliklerin tek profile bağlandığı katman.

**Semantik katman.** Metrik ve boyut tanımlarının merkezileştiği katman.

**Aktivasyon katmanı.** Segmentlerin pazarlama ve ürün kanallarına gönderildiği katman.

**Yönetişim katmanı.** Erişim kontrolü, sınıflandırma, saklama süresi, denetim ve silme süreçleri. Diğer tüm katmanları kesen bir sorumluluktur.

## 3. Rıza Yönetimi: Mimarinin Merkezi

Rıza, kullanıcı arayüzünde bir banner değil, veri akışının davranışını belirleyen bir durumdur:

- rıza kategorileri açık ve anlaşılır tanımlanır (zorunlu, analitik, pazarlama),
- reddetme, kabul etmek kadar kolay olmalıdır,
- rıza durumu profile bağlı olarak saklanır ve tarihçesi tutulur,
- rıza reddedildiğinde ölçüm ve aktivasyon davranışı test edilmiş olmalıdır,
- geri çekme talebi tüm aşağı sistemlere yayılmalıdır,
- rıza verilmemişse aktivasyon yapılmaz — teknik olarak mümkün olsa bile.

Rıza yönetimi teknik borç olarak bırakıldığında, sonradan düzeltmek genellikle veri silme ve yeniden toplama anlamına gelir.

## 4. Sunucu Tarafı Ölçüm

Tarayıcı ortamının kısıtları arttıkça ölçümün sunucu tarafına taşınması önem kazandı. Sağladıkları:

- istemci tarafındaki üçüncü taraf script yükünün azalması (performans kazancı),
- veri üzerinde daha fazla kontrol ve zenginleştirme imkânı,
- hassas verinin tarayıcıya çıkmadan işlenebilmesi,
- tanımlayıcı ömrü ve veri kaybı açısından iyileşme.

Dikkat edilmesi gerekenler: altyapı maliyeti ve bakımı, doğru rıza uygulamasının sunucu tarafında da korunması, veri işleme sorumluluğunun artması.

İyi tasarlanmış bir olay şeması, sunucu tarafına geçişi site kodunu yeniden yazmadan mümkün kılar.

## 5. Veri Toplama Stratejisi: Değer Karşılığı

Kullanıcı, karşılığında değer görmediği veriyi paylaşmaz. Sürdürülebilir toplama yolları:

- üyelik ve kayıtlı hesap avantajları (sipariş takibi, hızlı ödeme, favoriler),
- tercih merkezi (kullanıcı kendi ilgi alanlarını ve bildirim sıklığını seçer),
- anket ve tercih formları (kısa, açık amaçlı),
- sadakat programı,
- kişiselleştirilmiş içerik ve öneri.

Karanlık desenlerden (yanıltıcı onay, zorunlu izin) kaçınmak yalnızca uyum gereği değil, veri kalitesi gereğidir: zorla alınan izinler yüksek şikayet ve düşük etkileşim üretir.

## 6. Veri Kalitesi ve İzleme

- zorunlu alanların boş gelme oranı,
- kritik olay hacminde ani düşüş uyarıları,
- yinelenen kayıt oranı,
- kimlik eşleşme oranı,
- şema uyumsuzluğu tespiti,
- kaynak sistemler arası mutabakat kontrolleri.

Ölçümün sessizce bozulması en pahalı hatadır; bu nedenle izleme, toplama kadar önemlidir.

## 7. Aktivasyon

Veri, kullanılmadıkça değer üretmez. Yaygın aktivasyon senaryoları:

- yüksek değerli müşteri segmentine benzer kitle oluşturma,
- sepette bırakma ve göz atma sonrası hatırlatma,
- mevcut müşterileri edinme kampanyalarından dışlama,
- elde tutma ve geri kazanma akışları,
- ürün içi kişiselleştirme ve öneri,
- çevrimdışı satış verisiyle reklam optimizasyonunu besleme.

Her senaryo, rıza durumu kontrolünden geçtikten sonra çalışmalıdır.

## 8. Uygulama Yol Haritası

1. iş sorularını ve öncelikli senaryoları netleştirmek,
2. rıza mimarisini tasarlamak (ilk adım olmalı),
3. olay şemasını ve veri katmanını kurmak,
4. veri ambarına akış kurmak,
5. kimlik çözümlemesini uygulamak,
6. metrik/semantik katmanı tanımlamak,
7. kalite izleme ve uyarıları kurmak,
8. aktivasyon senaryolarını devreye almak,
9. yönetişim süreçlerini (erişim, saklama, silme) işletmeye almak.

## 9. Sık Yapılan Hatalar

- rıza yönetimini son adıma bırakmak,
- "her şeyi topla, sonra bakarız" yaklaşımı (uyum riski ve gürültü üretir),
- kişisel veriyi gereksiz yerlerde saklamak,
- saklama süresi tanımlamamak,
- toplanan verinin hiçbir senaryoda kullanılmaması,
- silme taleplerini karşılayamayacak mimari kurmak,
- veri kalitesini yalnızca kurulum gününde doğrulamak.

## Sık Sorulan Sorular

**Küçük ölçekte de gerekli mi?** Ölçek küçükse katmanlar basitleşir ama sıra değişmez: rıza, temiz olay şeması ve merkezi tanımlar her boyutta gereklidir.

**Üçüncü taraf veri tamamen bitti mi?** Kullanımı daralıyor ve güvenilirliği azalıyor. Dayanıklı strateji, kendi verinizi merkeze almaktır.

**Nereden başlamak en verimli?** Rıza mimarisi ve en kritik dönüşüm akışının doğru ölçümü. Bu iki adım, sonraki her yatırımın getirisini belirler.
