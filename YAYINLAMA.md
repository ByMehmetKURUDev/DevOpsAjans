# Yayınlama ve otomasyon kılavuzu

Hedef: Claude Code ile geliştirmeye devam etmek, GitHub'a push ettiğinde
sitenin kendiliğinden yayınlanması, elle tuşa basmanın bitmesi.

---

## Önce şunu bilin: Atoms'tan ayrılmak bir taşıma işi

Site kodu tek başına bir Vite SPA değil. `@metagptx/web-sdk` bütün
çağrılarını **kendi origin'ine göreli** atıyor:

```
/api/v1/auth/...                giriş, oturum
/api/v1/entities/blog_posts     panelden girilen yazılar
/api/v1/entities/site_settings  panel ayarları, SEO metinleri
/api/v1/storage/...             dosya yükleme
/api/v1/aihub/...               AI uçları
```

Bu uçların tamamı depodaki `app/backend` (FastAPI) içinde **var** — Atoms
onu sadece Lambda olarak çalıştırıyor. Yani taşıma gerçek bir taşıma, sıfırdan
yazım değil. Ama frontend'i başka bir yere koyup arka ucu bırakırsanız panel,
giriş ve müşteri alanı çalışmaz. İkisi birlikte taşınmalı.

Taşınabilirlik durumu:

| Parça | Bağımlılık | Taşınır mı |
|---|---|---|
| Veritabanı | SQLAlchemy + asyncpg (Postgres) | Evet — Neon / Render Postgres |
| Depolama | S3 uyumlu presigned URL | Evet — Cloudflare R2 |
| AI uçları | `APP_AI_BASE_URL` + `APP_AI_KEY` | Evet — OpenAI uyumlu her sağlayıcı |
| **Giriş (OIDC)** | `OIDC_ISSUER_URL`, `OIDC_CLIENT_ID` | **Tek gerçek iş** — kendi sağlayıcınız gerekir |

Kod standart OIDC + PKCE kullanıyor, yani Google / Auth0 / Clerk'e geçiş
ayar değişikliği seviyesinde. Yine de test edilmesi gereken tek yer burası.

---

## Önerilen kurulum

```
GitHub (ByMehmetKURUDev/DevOpsAjans)
  ├── push → Vercel      → app/frontend  → mehmetkuru.dev
  └── push → Render      → app/backend   → api (Vercel /api/* ile aynı origin)
                            └── Neon Postgres
```

**Neden Vercel:** `vercel.json` içindeki tek satırlık `/api/*` yönlendirmesi
SDK'nın göreli çağrılarını arka uca taşıyor — **frontend kodunda tek satır
değişiklik gerekmiyor**. Her dal ve her PR için ayrı önizleme adresi üretiyor;
Claude Code bir PR açtığında canlı adresi yorumda görüyorsunuz, beğenirseniz
merge ediyorsunuz. "Elle tuşa basma" adımı böylece kayboluyor.

**Neden Render:** `render.yaml` depoda duruyor, altyapı da kodla yönetiliyor.
Push → derleme → yayın otomatik. Railway ve Fly.io da olur; Render'ı
`render.yaml` depoda durabildiği için seçtim.

**Neden Cloudflare Pages değil:** Git LFS'i desteklemiyor (aşağıya bakın) ve
`/api/*` yönlendirmesi için ayrıca bir Worker yazmak gerekiyor. Ucuz ve hızlı,
ama bu depo için fazladan iş çıkarıyor.

---

## Adımlar

### 1. Git LFS'i kaldırın (kendi bilgisayarınızda)

Depodaki `.gitattributes` bütün `jpg/png/svg`'yi LFS'e alıyor. Toplam içerik
1 MB bile değil — LFS burada hiçbir şey kazandırmıyor, ama host tarafında
sorun çıkarıyor (Cloudflare hiç desteklemiyor, Vercel'de ayrıca açmak gerek).

Bu komutları **LFS içeriğinin gerçekten indirilmiş olduğu** kendi
makinenizde çalıştırın — aksi halde 129 baytlık işaretçi dosyaları
gerçek görsellerin yerine geçer:

```bash
git lfs pull                  # önce bütün içeriği indirin
git lfs ls-files | grep ' - ' # ÇIKTI BOŞ OLMALI; değilse durun
rm .gitattributes
git lfs uninstall --local
git add -A && git commit -m "Git LFS kaldırıldı: görseller depoda düz dosya"
```

### 2. Vercel

* New Project → depoyu seçin
* **Root Directory: `app/frontend`**
* Framework Preset: Other (vite.config zaten her şeyi yapıyor)
* Environment Variables:
  * `SITE_API_BASE_URL` = arka uç adresi (prerender panel ayarlarını buradan okuyor)
  * `VITE_SITE_URL` = `https://mehmetkuru.dev`
* `app/frontend/vercel.json` içindeki `BACKEND-ADRESI` satırını gerçek
  arka uç adresiyle değiştirin.
* Domain: `mehmetkuru.dev` → Vercel'in verdiği A / CNAME kayıtlarını DNS'e girin.

### 3. Render

* New → Blueprint → depoyu seçin (`render.yaml` okunur)
* `sync: false` işaretli değişkenleri panelden doldurun
* `DATABASE_URL` için Neon'da ücretsiz bir Postgres açıp bağlantı dizesini yapıştırın
  (kod Neon'un `channel_binding` parametresini zaten temizliyor)

### 4. Geçiş

1. Önce Vercel'in geçici adresinde (`*.vercel.app`) her şeyi test edin:
   giriş, panel, blog kaydı, dosya yükleme.
2. Veritabanını Atoms'tan alıp Neon'a aktarın (`pg_dump` / `pg_restore`).
3. En son DNS'i çevirin. TTL'i bir gün önceden 300 saniyeye düşürün.
4. Search Console'da `mehmetkuru.dev` mülkünü koruyun, sitemap'i yeniden gönderin.

---

## Günlük akış (kurulumdan sonra)

```
Claude Code'a iş verirsiniz
  → yeni dal + commit + PR
  → Vercel PR'a canlı önizleme adresi yorumlar
  → beğenirseniz "Merge"
  → main'e geçer, site ve API kendiliğinden yayınlanır
```

Tek tuş kalır: PR'daki **Merge**. Onu da istemezseniz `main`'e doğrudan push
edin, aynı otomasyon çalışır.

---

## Bu depoya eklenen dosyalar

| Dosya | İş |
|---|---|
| `app/frontend/vercel.json` | `/api/*` yönlendirmesi, SPA yedeği, önbellek ve güvenlik başlıkları |
| `render.yaml` | FastAPI servisi ve ortam değişkeni iskeleti |

`vercel.json` içindeki iki `rewrites` kuralının **sırası önemli**: önce
`/api/*`, sonra her şeyi `/index.html`'e düşüren yedek. Vercel dosya sistemine
önce baktığı için prerender edilen 99 statik sayfa bu yedekten etkilenmez;
yalnızca `/admin` ve `/client` gibi dosyası olmayan yollar uygulamaya düşer.
