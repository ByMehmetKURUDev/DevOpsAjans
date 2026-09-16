# Bu klasördeki font dosyaları nasıl üretildi

Inter ve Space Grotesk, Google Fonts'tan indirilip **siteye gereken
harflere indirgenerek** buraya kondu. İkisi de SIL Open Font License
altında; kendi sunucundan sunmak lisansın açıkça izin verdiği bir kullanım.

## Neden

Önceden `src/index.css`'in ilk satırında Google Fonts'a bir `@import`
vardı. Tarayıcı önce CSS'i indiriyor, sonra içindeki `@import`'u görüp
ikinci bir istek açıyordu; bu zincir ilk boyamayı ~850 ms geciktiriyordu.

Dosyaları olduğu gibi indirmek de yetmedi: Google'ın hazır alt kümeleri
bütün Avrupa dillerini taşıdığı için ağırlık başına ~130 kB tutuyordu.
Bu yüzden her dosya, sitede gerçekten kullanılan aralıklara indirgendi.

## Alt kümeler

| dosya soneki | aralık | ne için |
|---|---|---|
| `-latin` | `U+0000-00FF` + noktalama, para birimleri | İngilizce, Almanca (ä ö ü ß), Türkçe'nin ü ö ç harfleri |
| `-latin-ext` | `U+0100-017F` (Latin Extended-A) | Türkçe'nin ğ Ğ ı İ ş Ş harfleri |
| `-cyrillic` | `U+0400-045F` + ek | Rusça (`/ru`) |

`unicode-range` sayesinde tarayıcı yalnızca sayfada geçen harfler için
dosya indiriyor — Türkçe bir sayfa Kirilce dosyalarını hiç istemiyor.

Arapça (Noto Naskh Arabic) ve Hintçe (Noto Sans Devanagari) fontları
burada değil; `src/i18n/index.ts` o diller seçilince çalışma zamanında
yüklüyor.

## Yeniden üretmek gerekirse

1. Google Fonts CSS'ini modern bir tarayıcı kimliğiyle çek (woff2 gelmesi için):

   ```
   https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@600;700&display=swap
   ```

2. İçindeki `latin`, `latin-ext` ve `cyrillic` bloklarının `woff2`
   adreslerini indir.

3. `fonttools` ile yukarıdaki tablodaki aralıklara indirge:

   ```
   pip install fonttools brotli
   python3 -m fontTools.subset inter-400-latin-ext.woff2 \
     --output-file=inter-400-latin-ext.woff2 \
     --unicodes=U+0100-017F --flavor=woff2 \
     --layout-features=kern,liga,clig,calt,ccmp,locl,mark,mkmk \
     --no-hinting --desubroutinize
   ```

4. `src/fonts.css` içindeki `@font-face` bloklarının `unicode-range`
   değerleri, dosyaların gerçekte kapsadığı aralıkla **birebir aynı**
   olmalı. Aksi halde tarayıcı gereksiz dosya indirir ya da harf eksik kalır.

5. Değişiklikten sonra Türkçe harfleri kontrol et: ğ Ğ ı İ ş Ş ü ö ç
   ve tipografik işaretler — " " ' — … €
