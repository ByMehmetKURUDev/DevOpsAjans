import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Target } from 'lucide-react';

import { paylasilanHedefler, para, sayiYaz, yuzde, type PaylasilanHedef } from '@/lib/okr';

const RENK: Record<string, string> = { tamam: 'bg-emerald-400', yolunda: 'bg-emerald-500', riskli: 'bg-amber-400', geride: 'bg-rose-500' };

function Cubuk({ oran, durum, etiket }: { oran: number | null; durum: string | null; etiket: string }) {
  const { i18n } = useTranslation();
  const d = Math.max(0, Math.min(1, oran ?? 0));
  return (
    <div
      className="h-2 w-full overflow-hidden rounded-full bg-white/10"
      role="progressbar"
      aria-label={etiket}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(d * 100)}
      aria-valuetext={yuzde(d, i18n.language || 'tr')}
    >
      <div className={`h-full rounded-full ${durum ? RENK[durum] || 'bg-purple-400' : 'bg-purple-400'}`} style={{ width: `${d * 100}%` }} />
    </div>
  );
}

/**
 * Faz 6O — müşteri panelinin genel görünümünde "Ajansınızla ortak hedefler" kartı: ajansın bu hesaba bağlayıp
 * PAYLAŞTIĞI hedefler ve KR ilerlemesi (salt okunur; check-in notları, sahip ve güven paylaşılmaz). Hedefler modülü
 * kapalı olsa da görünür (portal parçası). Paylaşılan hedef yoksa hiç çizilmez.
 */
export default function PaylasilanHedefler() {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [liste, setListe] = useState<PaylasilanHedef[]>([]);

  useEffect(() => {
    let iptal = false;
    paylasilanHedefler()
      .then((r) => !iptal && setListe(r.items || []))
      .catch(() => undefined);
    return () => {
      iptal = true;
    };
  }, []);

  if (!liste.length) return null;
  const donemAdi = (d: PaylasilanHedef['donem']) =>
    d.ad || (d.tur === 'ceyrek' && d.yil && d.ceyrek ? t('hedefKarti.ceyrek', { yil: d.yil, ceyrek: d.ceyrek }) : d.tur === 'yil' && d.yil ? String(d.yil) : d.etiket);
  return (
    <section className="cam-kart mb-6 rounded-2xl border border-white/10 bg-white/[0.03] p-5" aria-labelledby="okr-kart-baslik" data-testid="okr-paylasilan">
      <h3 id="okr-kart-baslik" className="mb-1 flex items-center gap-2 text-lg font-semibold">
        <Target className="h-5 w-5 text-purple-300" aria-hidden="true" />
        {t('hedefKarti.baslik')}
      </h3>
      <p className="mb-4 text-xs text-muted-foreground">{t('hedefKarti.aciklama')}</p>
      <div className="grid gap-4 lg:grid-cols-2">
        {liste.map((h) => (
          <article key={h.id} className="min-w-0 rounded-xl border border-white/10 p-4" data-testid="okr-paylasilan-hedef">
            <div className="mb-2 flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="break-words font-medium">{h.baslik}</p>
                <p className="text-xs text-muted-foreground">
                  {donemAdi(h.donem)}
                  {h.kapandi ? ` · ${t('hedefKarti.kapandi')}` : ''}
                </p>
              </div>
              <span className="flex-none text-lg font-semibold tabular-nums">{yuzde(h.ilerleme, dil)}</span>
            </div>
            <Cubuk oran={h.ilerleme} durum={h.durum_rengi} etiket={h.baslik} />
            {h.durum_rengi && <p className="mt-1 text-xs text-muted-foreground">{t(`hedefKarti.durum.${h.durum_rengi}`)}</p>}
            <ul className="mt-3 grid gap-2">
              {h.krler.map((k) => (
                <li key={k.id} className="grid gap-1 text-sm">
                  <div className="flex items-start justify-between gap-2">
                    <span className="min-w-0 break-words">{k.baslik}</span>
                    <span className="flex-none text-xs tabular-nums text-muted-foreground">
                      {k.tur === 'kilometre'
                        ? t('hedefKarti.kilometre', { tamam: k.kilometre_tamam, toplam: k.kilometre_toplam })
                        : k.tur === 'evet_hayir'
                          ? k.mevcut >= 1
                            ? t('hedefKarti.tamamlandi')
                            : t('hedefKarti.bekliyor')
                          : k.tur === 'para'
                            ? `${para(k.mevcut, k.para_birimi, dil)} / ${para(k.hedef, k.para_birimi, dil)}`
                            : `${sayiYaz(k.mevcut, dil)} / ${sayiYaz(k.hedef, dil)}${k.tur === 'yuzde' ? '%' : k.birim ? ` ${k.birim}` : ''}`}
                    </span>
                  </div>
                  <Cubuk oran={k.ilerleme} durum={null} etiket={k.baslik} />
                </li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </section>
  );
}
