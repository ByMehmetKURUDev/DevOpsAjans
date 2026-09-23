import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Bot, Loader2, Send, X } from 'lucide-react';

import IletisimKanallari from '@/components/IletisimKanallari';
import { asistanaSor, type Mesaj } from '@/lib/asistanAi';

/**
 * "AI Asistan ile Konuş" — sağ alttaki tuş ve açılan sohbet paneli.
 *
 * Tuş prototipteki gibi: bot simgesi, yanında yanıp sönen nokta, yazı
 * mobilde gizleniyor. Sağ altta TEK tuş var: eskiden bunun altında ayrı
 * bir WhatsApp balonu duruyordu, iki balon hem mobilde yer kaplıyor hem
 * de ziyaretçiye gereksiz bir seçim yaptırıyordu. WhatsApp artık panelin
 * içindeki kanal satırında (IletisimKanallari).
 *
 * Cevaplar gerçek bir dil modelinden geliyor (`/api/v1/aihub/gentxt`).
 * AI yapılandırılmamışsa ya da ağ koparsa asistan uydurma bir cevap
 * üretmiyor: hatayı açıkça söylüyor ve iletişim sayfasına yönlendiriyor.
 * Sahte bir "her şeyi bilen" görüntü, ziyaretçi ilk yanlış cevabı
 * aldığında sitenin geri kalanına olan güveni de götürür.
 *
 * Konuşma yalnızca bu sekmede, bellekte duruyor — sunucuya kaydedilmiyor.
 */

/** Panelde tutulan en fazla mesaj; üstten düşüyor. */
const EN_FAZLA = 40;

export default function AsistanSohbeti() {
  const { t, i18n } = useTranslation();
  const [acik, setAcik] = useState(false);
  const [mesajlar, setMesajlar] = useState<Mesaj[]>([]);
  const [girdi, setGirdi] = useState('');
  const [bekliyor, setBekliyor] = useState(false);
  const [hata, setHata] = useState(false);

  const listeSonu = useRef<HTMLDivElement | null>(null);
  const kutu = useRef<HTMLTextAreaElement | null>(null);
  const iptal = useRef<AbortController | null>(null);

  const paketler = ([1, 2, 3, 4, 5] as const).map((n) => t(`packages.option${n}`));

  // Yeni mesaj gelince alta kay.
  useEffect(() => {
    listeSonu.current?.scrollIntoView({ block: 'end' });
  }, [mesajlar, bekliyor]);

  // Panel açılınca yazı kutusuna odaklan; Esc kapatsın.
  useEffect(() => {
    if (!acik) return;
    kutu.current?.focus();
    const kapat = (o: KeyboardEvent) => {
      if (o.key === 'Escape') setAcik(false);
    };
    window.addEventListener('keydown', kapat);
    return () => window.removeEventListener('keydown', kapat);
  }, [acik]);

  // Bileşen kalkarsa uçan istek iptal olsun.
  useEffect(() => () => iptal.current?.abort(), []);

  const gonder = (metin: string) => {
    const soru = metin.trim();
    if (!soru || bekliyor) return;

    const yeniGecmis = [...mesajlar, { rol: 'kullanici', metin: soru } as Mesaj].slice(-EN_FAZLA);
    setMesajlar(yeniGecmis);
    setGirdi('');
    setHata(false);
    setBekliyor(true);

    iptal.current?.abort();
    const kontrol = new AbortController();
    iptal.current = kontrol;

    asistanaSor({ gecmis: yeniGecmis, paketler, dil: i18n.language }, kontrol.signal)
      .then((cevap) =>
        setMesajlar((m) => [...m, { rol: 'asistan', metin: cevap }].slice(-EN_FAZLA)),
      )
      .catch((e) => {
        if ((e as Error)?.name === 'AbortError') return;
        setHata(true);
      })
      .finally(() => setBekliyor(false));
  };

  const tuslar = (o: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter gönderir, Shift+Enter satır atlar — sohbet kutularının alışkanlığı.
    if (o.key === 'Enter' && !o.shiftKey) {
      o.preventDefault();
      gonder(girdi);
    }
  };

  const ornekler = [t('asistan.ornek1'), t('asistan.ornek2'), t('asistan.ornek3')];

  return (
    <>
      {/* Açma tuşu — sağ altta, tek başına */}
      <button
        type="button"
        onClick={() => setAcik((a) => !a)}
        aria-expanded={acik}
        aria-controls="asistan-paneli"
        /*
          Yazı `sm` altında gizleniyor; mobilde tuşun içinde yalnızca
          aria-hidden bir ikon kalıyordu, yani ERİŞİLEBİLİR ADI YOKTU.
          Ekran okuyucu kullanan bir ziyaretçi telefonda tuşun ne
          yaptığını duyamıyordu (Lighthouse mobil erişilebilirlik 95).
          Görünen yazı olsun olmasın ad burada duruyor.
        */
        aria-label={acik ? t('asistan.kapat') : t('asistan.ac')}
        className="fixed bottom-6 end-6 z-40 group flex items-center gap-2.5 rounded-full bg-primary px-4 py-3 text-xs font-bold text-background shadow-[0_0_30px_rgb(var(--hero-a)/0.5)] transition-transform duration-300 hover:scale-105 active:scale-95 motion-reduce:transition-none motion-reduce:hover:scale-100"
      >
        <span className="relative flex items-center justify-center">
          {acik ? (
            <X className="h-5 w-5" aria-hidden="true" />
          ) : (
            <>
              <Bot className="h-5 w-5" aria-hidden="true" />
              <span className="absolute -end-1 -top-1 flex h-2.5 w-2.5 items-center justify-center rounded-full bg-background">
                <span className="h-1.5 w-1.5 rounded-full bg-primary motion-safe:animate-ping motion-reduce:hidden" />
              </span>
            </>
          )}
        </span>
        <span className="hidden font-mono tracking-tight sm:inline">
          {acik ? t('asistan.kapat') : t('asistan.ac')}
        </span>
      </button>

      {/* Panel */}
      {acik && (
        <section
          id="asistan-paneli"
          aria-label={t('asistan.baslik')}
          className="fixed bottom-24 end-4 z-40 flex max-h-[min(70vh,560px)] w-[min(24rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-2xl border border-white/12 bg-background/95 shadow-2xl backdrop-blur-xl sm:end-6"
        >
          <header className="flex items-start gap-3 border-b border-white/10 px-4 py-3">
            <span className="mt-0.5 flex h-8 w-8 flex-none items-center justify-center rounded-xl bg-primary/15">
              <Bot className="h-4 w-4 text-primary" aria-hidden="true" />
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-bold">{t('asistan.baslik')}</span>
              <span className="mt-0.5 block font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                {t('asistan.altBaslik')}
              </span>
            </span>
            <button
              type="button"
              onClick={() => setAcik(false)}
              aria-label={t('asistan.kapat')}
              className="ms-auto rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-white/5 hover:text-foreground"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          </header>

          {/* Doğrudan iletişim: WhatsApp, arama, SMS, e-posta, toplantı */}
          <IletisimKanallari />

          {/* Konuşma */}
          <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4" aria-live="polite">
            {mesajlar.length === 0 && (
              <>
                <p className="text-sm leading-relaxed text-muted-foreground">
                  {t('asistan.karsilama')}
                </p>
                <div className="mt-4 space-y-2">
                  {ornekler.map((o) => (
                    <button
                      key={o}
                      type="button"
                      onClick={() => gonder(o)}
                      className="block w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2.5 text-start text-sm text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
                    >
                      {o}
                    </button>
                  ))}
                </div>
              </>
            )}

            {mesajlar.map((m, i) => (
              <div
                key={`${i}-${m.metin.slice(0, 12)}`}
                className={m.rol === 'kullanici' ? 'flex justify-end' : 'flex justify-start'}
              >
                <p
                  className={`max-w-[85%] whitespace-pre-line rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed ${
                    m.rol === 'kullanici'
                      ? 'bg-primary/15 text-foreground'
                      : 'border border-white/10 bg-white/[0.03] text-muted-foreground'
                  }`}
                >
                  {m.metin}
                </p>
              </div>
            ))}

            {bekliyor && (
              <p className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin text-primary" aria-hidden="true" />
                {t('asistan.yaziyor')}
              </p>
            )}

            {hata && (
              <p className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-3.5 py-2.5 text-sm text-amber-200">
                {t('asistan.hata')}
              </p>
            )}

            <div ref={listeSonu} />
          </div>

          {/* Yazma alanı */}
          <div className="border-t border-white/10 p-3">
            <div className="flex items-end gap-2">
              <textarea
                ref={kutu}
                rows={1}
                value={girdi}
                onChange={(e) => setGirdi(e.target.value)}
                onKeyDown={tuslar}
                placeholder={t('asistan.yerTutucu')}
                aria-label={t('asistan.yerTutucu')}
                className="max-h-28 min-h-[40px] flex-1 resize-none rounded-xl border border-white/12 bg-white/[0.03] px-3 py-2.5 text-sm outline-none transition-colors placeholder:text-muted-foreground/60 focus:border-primary/50"
              />
              <button
                type="button"
                onClick={() => gonder(girdi)}
                disabled={!girdi.trim() || bekliyor}
                aria-label={t('asistan.gonder')}
                className="grid h-10 w-10 flex-none place-items-center rounded-xl bg-primary text-background transition-opacity disabled:opacity-40"
              >
                <Send className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
            <p className="mt-2 font-mono text-[10px] leading-relaxed text-muted-foreground/70">
              {t('asistan.uyari')}
            </p>
          </div>
        </section>
      )}
    </>
  );
}
