import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CornerDownRight, Target } from 'lucide-react';

import type { BolumProps } from '@/components/hedefler/Liste';
import { Bos, HataSatiri, IlerlemeCubugu, KART, Rozet, Yukleniyor } from '@/components/hedefler/ortak';
import { DURUM_METIN_RENGI, hataMetni, yuzde, type AgacDugumu } from '@/lib/okr';

function Dugum({ d, cocuklar, derinlik, ac }: { d: AgacDugumu; cocuklar: Map<number | null, AgacDugumu[]>; derinlik: number; ac: (id: number) => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const altlar = cocuklar.get(d.id) || [];
  return (
    <li data-testid="okr-agac-dugum" data-hedef={d.id}>
      <div
        className={`flex flex-wrap items-center gap-2 rounded-xl border border-white/10 p-2.5 ${d.secili_donemde ? 'bg-white/[0.03]' : 'bg-transparent opacity-80'}`}
        style={{ marginInlineStart: `${Math.min(derinlik, 6) * 1.25}rem` }}
      >
        {derinlik > 0 ? <CornerDownRight className="h-4 w-4 flex-none text-muted-foreground" aria-hidden="true" /> : <Target className="h-4 w-4 flex-none text-purple-300" aria-hidden="true" />}
        <button type="button" onClick={() => ac(d.id)} className="min-w-0 flex-1 break-words text-start text-sm font-medium hover:underline">
          {d.baslik}
        </button>
        {!d.secili_donemde && d.donem && <Rozet>{d.donem}</Rozet>}
        {d.durum !== 'etkin' && <Rozet>{t(`hedefler.hedef.durumlar.${d.durum}`)}</Rozet>}
        <div className="flex w-full items-center gap-2 sm:w-48">
          <div className="min-w-0 flex-1">
            <IlerlemeCubugu ilerleme={d.ilerleme} durum={d.durum_rengi} etiket={d.baslik} kucuk />
          </div>
          <span className={`w-10 text-end text-xs tabular-nums ${d.durum_rengi ? DURUM_METIN_RENGI[d.durum_rengi] : ''}`}>{yuzde(d.ilerleme, dil)}</span>
        </div>
      </div>
      {altlar.length > 0 && (
        <ul className="mt-1.5 grid gap-1.5">
          {altlar.map((a) => (
            <Dugum key={a.id} d={a} cocuklar={cocuklar} derinlik={derinlik + 1} ac={ac} />
          ))}
        </ul>
      )}
    </li>
  );
}

/** Faz 6O — hizalama ağacı: seçili dönemin hedefleri ve üst zincirleri (başka dönemdeki üst hedef soluk + dönem rozeti). */
export default function Agac({ api, donem, surum, ac }: BolumProps) {
  const { t } = useTranslation();
  const [dugumler, setDugumler] = useState<AgacDugumu[] | null>(null);
  const [hata, setHata] = useState<string | null>(null);

  useEffect(() => {
    let iptal = false;
    setHata(null);
    api
      .agac(donem.id)
      .then((r) => !iptal && setDugumler(r.items))
      .catch((e) => !iptal && setHata(hataMetni(t, e)));
    return () => {
      iptal = true;
    };
  }, [api, donem.id, surum, t]);

  const cocuklar = useMemo(() => {
    const m = new Map<number | null, AgacDugumu[]>();
    for (const d of dugumler || []) {
      const k = d.ust_id ?? null;
      m.set(k, [...(m.get(k) || []), d]);
    }
    return m;
  }, [dugumler]);

  if (hata) return <HataSatiri hata={hata} />;
  if (!dugumler) return <Yukleniyor />;
  const kokler = cocuklar.get(null) || [];
  return (
    <div className={`${KART} p-3 sm:p-4`} data-testid="okr-agac">
      <p className="mb-3 text-xs text-muted-foreground">{t('hedefler.agac.aciklama')}</p>
      {kokler.length === 0 ? (
        <Bos>{t('hedefler.liste.bos')}</Bos>
      ) : (
        <ul className="grid gap-1.5">
          {kokler.map((d) => (
            <Dugum key={d.id} d={d} cocuklar={cocuklar} derinlik={0} ac={ac} />
          ))}
        </ul>
      )}
    </div>
  );
}
