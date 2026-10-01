import { memo, useEffect, useMemo, useRef, useState } from 'react';
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
 *  - Faz 4G: çerçeve `srcdoc` DEĞİL, ayrı bir belge (`/kod-deneme/`,
 *    `public/kod-deneme/index.html`). srcdoc belgesi sitenin CSP'sini miras
 *    alıyor; CSP zorunlu olunca ziyaretçinin satır içi betiği engellenirdi.
 *    O yolda sitenin CSP'si ayrılıyor (`public/_headers`), belge kendi meta
 *    CSP'sini taşıyor. Kod `postMessage` ile gidiyor: çerçeve "hazırım"
 *    deyince (kaynağı bu çerçeve olan ileti) kod yollanıyor; her çalıştırmada
 *    çerçeve yeniden yükleniyor (`key`). Çerçeve yalnız istemcide çiziliyor:
 *    prerender HTML'inde yok, başka sayfaların açılışında boşuna yüklenmesin.
 *
 * Çalıştırma gecikmeli (600 ms): her tuşa basışta yeniden kurmak hem
 * yarım yazılmış kodu sürekli hata ekranına çeviriyor hem de boşuna
 * iş yapıyor.
 */

interface OrnekMetinleri {
  yorum: string;
  merhaba: string;
  degistir: string;
  isimler: string[];
  /** Kod içindeki adlar: Türkçede Türkçe, diğer dillerde İngilizce. */
  sinif: string;
  dizi: string;
  fonksiyon: string;
}

/**
 * Başlangıç örneği ziyaretçinin dilinde: yorum, selam, düğme ve dönen
 * adlar i18n'den geliyor. Türkçe çıktı eskisiyle harfi harfine aynı.
 */
function ornekKod(m: OrnekMetinleri): string {
  const liste = m.isimler.map((ad) => `'${ad.replace(/'/g, "\\'")}'`).join(', ');
  return `<!-- ${m.yorum} -->
<div class="${m.sinif}">
  <h2>${m.merhaba} <span id="ad">${m.isimler[0] ?? ''}</span></h2>
  <button onclick="${m.fonksiyon}()">${m.degistir}</button>
</div>

<style>
  body { font-family: system-ui, sans-serif; background: #0b0f14; color: #e6edf3;
         display: grid; place-items: center; height: 100vh; margin: 0; }
  .${m.sinif} { text-align: center; }
  h2 { font-weight: 800; letter-spacing: -.02em; }
  #ad { color: #00dc82; }
  button { margin-top: 12px; padding: 10px 18px; border: 0; border-radius: 10px;
           background: #00dc82; color: #0b0f14; font-weight: 700; cursor: pointer; }
</style>

<script>
  const ${m.dizi} = [${liste}];
  let i = 0;
  function ${m.fonksiyon}() {
    i = (i + 1) % ${m.dizi}.length;
    document.getElementById('ad').textContent = ${m.dizi}[i];
  }
</script>`;
}

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

function KodDenemeAlani() {
  const { t, i18n } = useTranslation();
  const turkce = (i18n.language || 'tr').startsWith('tr');
  const BASLANGIC = useMemo(
    () =>
      ornekKod({
        yorum: t('playground.ornekYorum', 'Yazın, sağda anında çalışsın'),
        merhaba: t('playground.ornekMerhaba', 'Merhaba'),
        degistir: t('playground.ornekDegistir', 'Değiştir'),
        isimler: t('playground.ornekIsimler', 'dünya,İstanbul,geliştirici,ziyaretçi')
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
        sinif: turkce ? 'kutu' : 'box',
        dizi: turkce ? 'isimler' : 'names',
        fonksiyon: turkce ? 'degistir' : 'change',
      }),
    [t, turkce],
  );
  const [kod, setKod] = useState(BASLANGIC);
  const [calisan, setCalisan] = useState(BASLANGIC);
  const zamanlayici = useRef<number | null>(null);

  // Dil değişince örnek de değişsin — ama ziyaretçi kodu değiştirdiyse
  // onun yazdığına dokunulmuyor.
  const oncekiBaslangic = useRef(BASLANGIC);
  useEffect(() => {
    const onceki = oncekiBaslangic.current;
    oncekiBaslangic.current = BASLANGIC;
    if (onceki === BASLANGIC) return;
    setKod((k) => (k === onceki ? BASLANGIC : k));
    setCalisan((c) => (c === onceki ? BASLANGIC : c));
  }, [BASLANGIC]);

  // Yazmayı bırakınca çalıştır.
  useEffect(() => {
    if (zamanlayici.current) window.clearTimeout(zamanlayici.current);
    zamanlayici.current = window.setTimeout(() => setCalisan(kod), 600);
    return () => {
      if (zamanlayici.current) window.clearTimeout(zamanlayici.current);
    };
  }, [kod]);

  const belge = useMemo(() => belgeyiKur(calisan), [calisan]);

  // Çalıştırıcı çerçeve: istemcide çizilir; her yeni kodda yeniden yüklenir.
  const [istemcide, setIstemcide] = useState(false);
  const [surum, setSurum] = useState(0);
  const cerceve = useRef<HTMLIFrameElement | null>(null);
  const sonBelge = useRef(belge);
  useEffect(() => setIstemcide(true), []);
  useEffect(() => {
    if (sonBelge.current === belge) return; // ilk çizim: çerçeve zaten bu kodu isteyecek
    sonBelge.current = belge;
    setSurum((s) => s + 1);
  }, [belge]);
  useEffect(() => {
    const dinle = (e: MessageEvent) => {
      const pencere = cerceve.current?.contentWindow;
      if (!pencere || e.source !== pencere) return;
      if ((e.data as { tur?: string } | null)?.tur !== 'mk-kod-hazir') return;
      // Kum havuzundaki çerçevenin kökeni opak ("null"): hedef '*' olmak zorunda;
      // giden yalnız ziyaretçinin kendi yazdığı kod.
      pencere.postMessage({ tur: 'mk-kod', kod: sonBelge.current }, '*');
    };
    window.addEventListener('message', dinle);
    return () => window.removeEventListener('message', dinle);
  }, []);

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
            {istemcide ? (
              <iframe
                key={surum}
                ref={cerceve}
                title={t('playground.sonuc')}
                src="/kod-deneme/"
                /*
                  allow-same-origin BİLEREK yok: sandbox'tan çıkıp ana
                  sayfaya erişmesini engelleyen şey tam olarak bu.
                */
                sandbox="allow-scripts"
                data-kod-deneme
                className="h-[420px] w-full rounded-2xl border border-white/10 bg-background"
              />
            ) : (
              <div className="h-[420px] w-full rounded-2xl border border-white/10 bg-background" aria-hidden="true" />
            )}
          </div>
        </div>

        <p className="mt-4 text-center font-mono text-[11px] text-muted-foreground">
          {t('playground.not')}
        </p>
      </div>
    </section>
  );
}

export default memo(KodDenemeAlani);
