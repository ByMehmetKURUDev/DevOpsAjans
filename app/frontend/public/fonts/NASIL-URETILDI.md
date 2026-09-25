# Bu klasördeki font dosyaları nasıl üretildi

Plus Jakarta Sans (arayüz ve başlıklar), JetBrains Mono (kod ve etiket
yazıları) ve Inter (Rusça yedeği), Google Fonts'tan indirilip **siteye
gereken harflere indirgenerek** buraya kondu. Üçü de SIL Open Font
License altında; kendi sunucundan sunmak lisansın açıkça izin verdiği
bir kullanım.

Plus Jakarta Sans'ın Kiril alt kümesi Google Fonts'ta yok. Bu yüzden
Inter dosyaları duruyor: `unicode-range` sayesinde Rusça sayfalarda
tarayıcı kendiliğinden Inter'e düşüyor, diğer dillerde Inter hiç
indirilmiyor.

## Neden

Önceden `src/index.css`'in ilk satırında Google Fonts'a bir `@import`
vardı. Tarayıcı önce CSS'i indiriyor, sonra içindeki `@import`'u görüp
ikinci bir istek açıyordu; bu zincir ilk boyamayı ~850 ms geciktiriyordu.

Dosyaları olduğu gibi indirmek de yetmedi: Google'ın hazır alt kümeleri
bütün Avrupa dillerini taşıdığı için ağırlık başına ~130 kB tutuyordu.
Bu yüzden her dosya, sitede gerçekten kullanılan aralıklara indirgendi.

## Plus Jakarta Sans neden tek dosya

Uzun süre beş kalınlık (400/500/600/700/800) için ayrı ayrı, her biri de
`latin` ve `latin-ext` olmak üzere ikiye bölünmüş **dokuz** dosya vardı.
Ana sayfa bu kalınlıkların hepsini kullanıyor, yani ilk açılışta 156 kB
font ve dokuz ayrı istek iniyordu — PageSpeed'in kritik yol ağacında
hepsi tek tek görünüyordu.

Plus Jakarta Sans aslında **değişken (variable)** bir font: kalınlık bir
eksen, tek dosya 200–800 arasındaki her kalınlığı üretiyor. Google'ın
statik kalınlıkları da zaten aynı değişken kaynaktan üretildiği için
çizim birebir aynı. Dokuz dosya / 156 kB yerine tek dosya / 29 kB.

JetBrains Mono'da değişken sürüm işe yaramıyor: tek dosyası 42 kB, oysa
sitede iki kalınlık kullanılıyor ve ana sayfada bunlardan yalnızca biri
iniyor. Onun yerine `latin` ve `latin-ext` tek dosyada birleştirildi.

## Alt kümeler

| dosya | aralık | ne için |
|---|---|---|
| `jakarta-degisken-latin` | `U+0000-017F` + noktalama, para birimleri | bütün Latin diller, Türkçe dâhil; 200–800 arası her kalınlık |
| `jetbrains-<ağırlık>-latin-tam` | aynı aralık | kod alanı ve mono etiketler |
| `jetbrains-<ağırlık>-cyrillic` | `U+0301, U+0400-045F, …` | Rusça (`/ru`) mono yazılar |
| `inter-<ağırlık>-cyrillic` | `U+0301, U+0400-045F, …` | Rusça (`/ru`) — Jakarta'da Kiril yok |

Inter'in Latin dosyaları silindi: yığında Jakarta önce geldiği için o
aralıklarda Inter hiçbir sayfada inmiyordu — ölçtük, `/ru` dâhil hiçbir
dilde istenmiyordu. Depoda 198 kB ölü ağırlıktı.

`unicode-range` sayesinde tarayıcı yalnızca sayfada geçen harfler için
dosya indiriyor — Türkçe bir sayfa Kirilce dosyalarını hiç istemiyor.

Arapça (Noto Naskh Arabic) ve Hintçe (Noto Sans Devanagari) fontları
burada değil; `src/i18n/index.ts` o diller seçilince çalışma zamanında
yüklüyor.

## Yeniden üretmek gerekirse

1. Değişken kaynak TTF'leri Google Fonts deposundan al:

   ```
   curl -sSL -o "PlusJakartaSans[wght].ttf" \
     "https://raw.githubusercontent.com/google/fonts/main/ofl/plusjakartasans/PlusJakartaSans%5Bwght%5D.ttf"
   curl -sSL -o "JetBrainsMono[wght].ttf" \
     "https://raw.githubusercontent.com/google/fonts/main/ofl/jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf"
   ```

2. `fonttools` ile aşağıdaki aralığa indirge. Değişken eksen (`wght`)
   kendiliğinden korunuyor — `--instance` verme, yoksa tek kalınlığa düşer:

   ```
   pip install fonttools brotli
   ARALIK="U+0000-017F,U+2000-206F,U+2074,U+20A0-20BF,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD"
   python3 -m fontTools.subset "PlusJakartaSans[wght].ttf" \
     --output-file=jakarta-degisken-latin.woff2 \
     --unicodes="$ARALIK" --flavor=woff2 \
     --layout-features=kern,liga,clig,calt,ccmp,locl,mark,mkmk --no-hinting
   ```

3. JetBrains Mono için önce kalınlığı sabitle, sonra aynı aralığa indirge:

   ```
   python3 -m fontTools.varLib.instancer "JetBrainsMono[wght].ttf" wght=400 -o jb-400.ttf
   python3 -m fontTools.subset jb-400.ttf \
     --output-file=jetbrains-400-latin-tam.woff2 \
     --unicodes="$ARALIK" --flavor=woff2 \
     --layout-features=kern,liga,clig,calt,ccmp,locl,mark,mkmk --no-hinting
   ```

4. `src/fonts.css` içindeki `@font-face` bloklarının `unicode-range`
   değerleri, dosyaların gerçekte kapsadığı aralıkla **birebir aynı**
   olmalı. Aksi halde tarayıcı gereksiz dosya indirir ya da harf eksik kalır.

5. Dosya adını değiştir — aynı adla üzerine yazma. Fontlar uzun süreli
   önbellekleniyor; ad aynı kalırsa eski dosyası önbellekte duran
   ziyaretçide harf eksik kalabilir.

6. Değişiklikten sonra harfleri kontrol et: ğ Ğ ı İ ş Ş ü ö ç, logodaki
   ® işareti ve tipografik işaretler — " " ' — … €
