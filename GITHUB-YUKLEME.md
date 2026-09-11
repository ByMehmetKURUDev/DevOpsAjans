# Dosyaları GitHub'a nasıl yüklerim?

Hiç komut satırı bilmeden, tarayıcıdan. Adım adım.

---

## Yöntem 1 — Tarayıcıdan sürükle bırak (en kolay)

Bu yöntem küçük değişiklikler için yeterli, komut satırı gerekmez.

1. Bilgisayarınızda `mehmetkuru-dev-kaynak.zip` dosyasını açın (sağ tık →
   "Tümünü ayıkla" / "Aç"). İçinden bir klasör çıkar.
2. Tarayıcıda `github.com/ByMehmetKURUDev/DevOpsAjans` adresine gidin.
3. **Add file → Upload files** düğmesine basın.
4. Çıkardığınız klasörün **içindekileri** (klasörün kendisini değil) pencereye
   sürükleyin. `app`, `render.yaml`, `YAYINLAMA.md` gibi her şey gitsin.
5. Aşağıdaki kutuya ne yaptığınızı bir cümleyle yazın, örneğin
   `Yeni logo ve blog sayfalama`.
6. **Commit changes** düğmesine basın. Bitti.

> **Dikkat:** Bu yöntem klasörleri tek tek yükler ve **silinen dosyaları
> silmez**. Örneğin eski logo dosyaları depoda kalmaya devam eder. Önemli
> bir temizlik yaptıysanız Yöntem 2'yi kullanın.

---

## Yöntem 2 — GitHub Desktop (önerilen)

Kurulumu beş dakika, sonrası hep kolay. Komut yok, hep düğme.

### Bir kerelik kurulum

1. `desktop.github.com` adresinden **GitHub Desktop**'ı indirin, kurun.
2. Açılışta **Sign in to GitHub.com** ile hesabınıza girin.
3. **File → Clone repository → GitHub.com** → listeden `DevOpsAjans` seçin →
   **Clone**. Depo bilgisayarınıza iner; hangi klasöre indiğini not edin.

### Her güncellemede

1. Size verdiğim ZIP'i açın.
2. İçindekileri, klonladığınız klasörün üzerine kopyalayın
   ("değiştirilsin mi?" diye sorunca **Evet**).
3. GitHub Desktop'a geçin — sol tarafta değişen bütün dosyaları listeler.
4. Sol altta **Summary** kutusuna bir cümle yazın.
5. **Commit to main** → sonra üstteki **Push origin** düğmesi.

Bu kadar. Silinen dosyalar da doğru şekilde silinir.

---

## Yöntem 3 — Yama dosyası (git bilen biri için)

Size ayrıca `tum-fazlar.patch` veriyorum. Bütün değişiklikleri tek tek,
açıklamalarıyla birlikte taşır:

```bash
git clone https://github.com/ByMehmetKURUDev/DevOpsAjans.git
cd DevOpsAjans
git checkout -b faz1-seo-onarim
git am < tum-fazlar.patch
git push -u origin faz1-seo-onarim
```

Sonra GitHub'da **Compare & pull request** çıkar; inceleyip **Merge**
dersiniz.

---

## Hangisini seçmeliyim?

| Durum | Yöntem |
|---|---|
| Sadece birkaç dosya değişti | 1 — tarayıcıdan yükle |
| ZIP'in tamamını gönderiyorum | 2 — GitHub Desktop |
| Değişiklikleri tek tek görmek istiyorum | 3 — yama |

Uzun vadede 2'yi öğrenmenizi öneririm: Claude Code ile çalışmaya devam
edecekseniz her turda aynı üç düğmeye basacaksınız.

---

## Sık karşılaşılanlar

**"Bu dosya çok büyük" hatası**
GitHub tek dosyada 100 MB sınırı koyuyor. Depoda o boyutta dosya yok;
bu hatayı alıyorsanız yanlışlıkla `node_modules` klasörünü de yüklüyorsunuz.
Onu yüklemeyin — `.gitignore` zaten dışarıda bırakıyor, ama sürükle bırakta
elle ayıklamanız gerekir.

**"node_modules" ve "dist" klasörlerini yüklemeli miyim?**
Hayır. `node_modules` indirilen paketler, `dist` ise derlenmiş çıktı.
İkisi de koddan yeniden üretiliyor. Size verdiğim kaynak ZIP'inde
zaten yoklar.

**Yanlış bir şey yükledim, geri alabilir miyim?**
Evet, hiçbir şey kaybolmaz. GitHub'da **Commits** sekmesinden ilgili
kaydı açıp **Revert** diyebilirsiniz.
