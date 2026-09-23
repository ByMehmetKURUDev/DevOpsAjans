import { useEffect, useMemo, useRef, useState } from 'react';
import { Play, RotateCcw } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';

/**
 * Canlı kod deneme alanı.
 *
 * Ziyaretçi soldaki kutuya yazıyor, sağda anında sonucu görüyor.
 * Amaç gösteriş değil: "bu ekibin elinde ne var" sorusunu anlatmak
 * yerine gösteriyor.
 *
 * GÜVENLİK -- burası ziyaretçinin yazdığı kodu ÇALIŞTIRIYOR, o yüzden
 * yalıtım pazarlık konusu değil:
 *
 *  - iframe `sandbox="allow-scripts"` ile açılıyor ve `allow-same-origin`
 *    VERİLMİYOR. İkisi birlikte verilseydi çerçeve kendi kum havuzundan
 *    çıkıp ana sayfanın DOM'una, oturum jetonuna ve localStorage'ına
 *    erişebilirdi. Verilmeyince çerçeve benzersiz, boş bir origin'de
 *    çalışıyor; siteyle hiçbir bağı kalmıyor.
 *  - Üretilen belgeye CSP ekleniyor: dışarıdan betik, görsel ya da
 *    bağlantı yüklenemiyor. Böylece deneme alanı başkasının sunucusuna
 *    istek atmak için kullanılamıyor.
 *  - Kod hiçbir yere gönderilmiyor, kaydedilmiyor; yalnızca bu sekmede.
 *
 * Çalıştırma gecikmeli (600 ms): her tuşa basışta yeniden kurmak hem
 * yarım yazılmış kodu sürekli hata ekranına çeviriyor hem de boşuna
 * iş yapıyor.
 */

const BASLANGIC = `<!-- Yazın, sağda anında çalışsın -->
<div class="kutu">
  <h2>Merhaba <span id="ad">dünya</span></h2>
  <button onclick="degistir()">Değiştir</button>
</div>

<style>
  body { font-family: system-ui, sans-serif; background: #0b0f14; color: #e6edf3;
         display: grid; place-items: center; height: 100vh; margin: 0; }
  .kutu { text-align: center; }
  h2 { font-weight: 800; letter-spacing: -.02em; }
  #ad { color: #00dc82; }
  button { margin-top: 12px; padding: 10px 18px; border: 0; border-radius: 10px;
           background: #00dc82; color: #0b0f14; font-weight: 700; cursor: pointer; }
</style>

<script>
  const isimler = ['dünya', 'İstanbul', 'geliştirici', 'ziyaretçi'];
  let i = 0;
  function degistir() {
    i = (i + 1) % isimler.length;
    document.getElementById('ad').textContent = isimler[i];
  }
</script>`;

/**
 * Ziyaretçinin kodunu, dışarıya çıkamayan bir belgeye sarar.
 *
 * CSP 'unsafe-inline' içeriyor çünkü deneme alanının bütün anlamı
 * satır içi betik ve stil yazabilmek. Tehlikeli olan satır içi kod
 * değil, o kodun neye erişebildiği -- erişimi sandbox kapatıyor.
 */
function belgeyiKur(kod: string): string {
  return `<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy"
      content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:;">
</head><body>${kod}</body></html>`;
}

export default function KodDenemeAlani() {
  const { t } = useTranslation();
  const [kod, setKod] = useState(BASLANGIC);
  const [calisan, setCalisan] = useState(BASLANGIC);
  const zamanlayici = useRef<number | null>(null);

  // Yazmayı bırakınca çalıştır.
  useEffect(() => {
    if (zamanlayici.current) window.clearTimeout(zamanlayici.current);
    zamanlayici.current = window.setTimeout(() => setCalisan(kod), 600);
    return () => {
      if (zamanlayici.current) window.clearTimeout(zamanlayici.current);
    };
  }, [kod]);

  const belge = useMemo(() => belgeyiKur(calisan), [calisan]);

  return (
    <section
      id="playground"
      className="border-t border-white/10 py-24"
      aria-labelledby="playground-baslik"
    >
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mb-10 text-center">
          <p className="mb-4 text-xs uppercase tracking-[0.3em] text-primary">
            {t('playground.etiket')}
          </p>
          <h2 id="playground-baslik" className="mb-4 text-4xl font-bold md:text-5xl">
            {t('playground.baslik')}{' '}
            <span className="gradient-text">{t('playground.baslikVurgu')}</span>
          </h2>
          <p className="mx-auto max-w-2xl text-muted-foreground">{t('playground.aciklama')}</p>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="flex flex-col">
            <div className="mb-2 flex items-center justify-between">
              <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                {t('playground.kod')}
              </span>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setKod(BASLANGIC)}
                  className="!bg-transparent !hover:bg-transparent h-8 border-white/20"
                >
                  <RotateCcw className="me-1.5 h-3.5 w-3.5" />
                  {t('playground.sifirla')}
                </Button>
                <Button
                  size="sm"
                  onClick={() => setCalisan(kod)}
                  className="h-8 border-0 bg-primary text-background"
                >
                  <Play className="me-1.5 h-3.5 w-3.5" />
                  {t('playground.calistir')}
                </Button>
              </div>
            </div>
            <textarea
              value={kod}
              onChange={(e) => setKod(e.target.value)}
              spellCheck={false}
              aria-label={t('playground.kod')}
              className="h-[420px] w-full resize-none rounded-2xl border border-white/10 bg-white/[0.03] p-4 font-mono text-xs leading-relaxed outline-none transition-colors focus:border-primary/50"
            />
          </div>

          <div className="flex flex-col">
            <span className="mb-2 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              {t('playground.sonuc')}
            </span>
            <iframe
              title={t('playground.sonuc')}
              srcDoc={belge}
              /*
                allow-same-origin BİLEREK yok: sandbox'tan çıkıp ana
                sayfaya erişmesini engelleyen şey tam olarak bu.
              */
              sandbox="allow-scripts"
              className="h-[420px] w-full rounded-2xl border border-white/10 bg-background"
            />
          </div>
        </div>

        <p className="mt-4 text-center font-mono text-[11px] text-muted-foreground">
          {t('playground.not')}
        </p>
      </div>
    </section>
  );
}
