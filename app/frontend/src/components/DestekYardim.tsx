import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { ArrowLeft, BookOpen, Clock, Loader2, Search } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { makaleAra, makaleGetir, slaBilgisi, type Makale, type MakaleOzeti, type SlaBilgisi } from '@/lib/destek';

/**
 * Müşteri paneli › Destek sekmesinin üstü (Faz 2C).
 *
 * Solda bilgi bankası araması ve makale okuma (modül `bilgi_bankasi`
 * kapalıysa hiç görünmez), sağda destek saatleri ve öncelik başına ilk
 * yanıt hedefi (SLA bilgisi).
 */

const KART = 'cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6';

function saatMetni(dk: number, t: (k: string, o?: Record<string, unknown>) => string): string {
  const saat = Math.floor(dk / 60);
  const dakika = dk % 60;
  if (saat >= 9 && dk % 540 === 0) return t('yardim.sla.isGunu', { sayi: dk / 540 });
  if (saat && dakika) return t('yardim.sla.saatDakika', { saat, dakika });
  if (saat) return t('yardim.sla.saat', { sayi: saat });
  return t('yardim.sla.dakika', { sayi: dakika });
}

export function MakaleGorunumu({ makale, geri }: { makale: Makale; geri: () => void }) {
  const { t } = useTranslation();
  return (
    <div data-testid={`kb-okunan-${makale.id}`}>
      <Button size="sm" variant="ghost" className="-ms-2 mb-2 gap-1" onClick={geri}>
        <ArrowLeft className="h-4 w-4 rtl:rotate-180" aria-hidden="true" /> {t('yardim.kb.geri')}
      </Button>
      {makale.kategori && <p className="text-xs uppercase tracking-widest text-purple-300">{makale.kategori}</p>}
      <h4 className="mt-1 text-lg font-semibold">{makale.baslik}</h4>
      <div
        className="prose prose-invert text-sm mt-3 max-w-none"
        // Sunucu izinli etiket listesiyle temizledi (services/guvenli_html.py).
        dangerouslySetInnerHTML={{ __html: makale.html }}
      />
    </div>
  );
}

export default function DestekYardim({ kbAcik }: { kbAcik: boolean }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [sla, setSla] = useState<SlaBilgisi | null>(null);
  const [sorgu, setSorgu] = useState('');
  const [sonuclar, setSonuclar] = useState<MakaleOzeti[] | null>(null);
  const [araniyor, setAraniyor] = useState(false);
  const [okunan, setOkunan] = useState<Makale | null>(null);

  useEffect(() => {
    slaBilgisi()
      .then(setSla)
      .catch(() => setSla(null));
  }, []);

  const ara = useCallback(
    async (q: string) => {
      setAraniyor(true);
      try {
        setSonuclar(await makaleAra(q, dil));
      } catch {
        setSonuclar([]);
      } finally {
        setAraniyor(false);
      }
    },
    [dil]
  );

  useEffect(() => {
    if (kbAcik) void ara('');
  }, [kbAcik, ara]);

  const gonder = (e: FormEvent) => {
    e.preventDefault();
    setOkunan(null);
    void ara(sorgu.trim());
  };

  const ac = async (id: number) => {
    try {
      setOkunan(await makaleGetir(id, dil));
    } catch {
      setOkunan(null);
    }
  };

  const gunler = sla?.mesai.gunler ?? [];
  const gunAraligi =
    gunler.length && gunler.every((g, i) => i === 0 || g === gunler[i - 1] + 1)
      ? `${t(`yardim.gun.${gunler[0]}`)}–${t(`yardim.gun.${gunler[gunler.length - 1]}`)}`
      : gunler.map((g) => t(`yardim.gun.${g}`)).join(', ');

  return (
    <div className={`mb-8 grid gap-6 ${kbAcik ? 'lg:grid-cols-[2fr_1fr]' : ''}`} data-testid="destek-yardim">
      {kbAcik && (
        <section className={KART} data-testid="kb-arama">
          <h3 className="flex items-center gap-2 text-lg font-semibold">
            <BookOpen className="h-5 w-5 text-purple-300" aria-hidden="true" /> {t('yardim.kb.baslik')}
          </h3>
          <p className="mt-1 text-sm text-muted-foreground">{t('yardim.kb.aciklama')}</p>
          <form onSubmit={gonder} className="mt-4 flex gap-2">
            <Input
              value={sorgu}
              onChange={(e) => setSorgu(e.target.value)}
              placeholder={t('yardim.kb.araYer')}
              aria-label={t('yardim.kb.araYer')}
              className="bg-white/5"
              data-testid="kb-ara-girdi"
            />
            <Button type="submit" className="gap-2" data-testid="kb-ara">
              {araniyor ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              <span className="hidden sm:inline">{t('yardim.kb.ara')}</span>
            </Button>
          </form>
          <div className="mt-4">
            {okunan ? (
              <MakaleGorunumu makale={okunan} geri={() => setOkunan(null)} />
            ) : sonuclar === null ? null : sonuclar.length === 0 ? (
              <p className="text-sm text-muted-foreground">{sorgu.trim() ? t('yardim.kb.sonucYok') : t('yardim.kb.bosMusteri')}</p>
            ) : (
              <ul className="divide-y divide-white/5">
                {sonuclar.slice(0, 8).map((m) => (
                  <li key={m.id}>
                    <button
                      type="button"
                      onClick={() => void ac(m.id)}
                      className="w-full py-3 text-left hover:text-purple-200"
                      data-testid={`kb-sonuc-${m.id}`}
                    >
                      <span className="block font-medium">{m.baslik}</span>
                      <span className="line-clamp-2 block text-xs text-muted-foreground">{m.ozet}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      )}

      {sla && (
        <section className={KART} data-testid="sla-bilgisi">
          <h3 className="flex items-center gap-2 text-lg font-semibold">
            <Clock className="h-5 w-5 text-cyan-300" aria-hidden="true" /> {t('yardim.sla.musteriBaslik')}
          </h3>
          <p className="mt-2 text-sm">
            {t('yardim.sla.mesaiMetni', { gunler: gunAraligi, bas: sla.mesai.bas, bit: sla.mesai.bit })}
          </p>
          <ul className="mt-3 space-y-1 text-sm">
            {(['acil', 'yuksek', 'normal', 'dusuk'] as const).map((o) => (
              <li key={o} className="flex justify-between gap-3">
                <span className="text-muted-foreground">{t(`yardim.oncelik.${o}`)}</span>
                <span>{t('yardim.sla.ilkYanitIcinde', { sure: saatMetni(sla.hedefler[o].ilk_yanit_dk, t) })}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-muted-foreground">{t('yardim.sla.musteriNot')}</p>
        </section>
      )}
    </div>
  );
}
