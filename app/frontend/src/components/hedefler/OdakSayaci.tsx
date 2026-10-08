import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Coffee, Pause, Play, RotateCcw } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { DIS_DUGME, GIRDI, HataSatiri } from '@/components/hedefler/ortak';
import { hataMetni, type Kr, type OkrApi } from '@/lib/okr';

/**
 * Faz 6O — odak sayacı (25/5): çalışma süresi bitince oturum KR'ye NOT olarak kaydedilir (değer değişmez; `tur=odak`,
 * süre dakika) ve mola başlar. Sayaç tarayıcıda; sekme arka planda yavaşlasa da bitiş anına göre hesaplanır.
 */
export default function OdakSayaci({ api, kr, calisma, mola, onKaydedildi }: {
  api: OkrApi;
  kr: Kr;
  calisma: number;
  mola: number;
  onKaydedildi: () => void;
}) {
  const { t } = useTranslation();
  const [evre, setEvre] = useState<'calisma' | 'mola'>('calisma');
  const [kalan, setKalan] = useState(calisma * 60);
  const [calisiyor, setCalisiyor] = useState(false);
  const [notlar, setNotlar] = useState('');
  const [bilgi, setBilgi] = useState<string | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const bitis = useRef<number | null>(null);

  useEffect(() => {
    if (!calisiyor) return;
    if (bitis.current === null) bitis.current = Date.now() + kalan * 1000;
    const zaman = window.setInterval(() => {
      const k = Math.max(0, Math.round(((bitis.current ?? Date.now()) - Date.now()) / 1000));
      setKalan(k);
      if (k === 0) {
        window.clearInterval(zaman);
        bitis.current = null;
        setCalisiyor(false);
        if (evre === 'calisma') {
          api
            .odak(kr.id, { sure_dk: calisma, notlar: notlar || null })
            .then(() => {
              setBilgi(t('hedefler.odak.kaydedildi', { dk: calisma }));
              setNotlar('');
              onKaydedildi();
            })
            .catch((e) => setHata(hataMetni(t, e)));
          setEvre('mola');
          setKalan(mola * 60);
        } else {
          setEvre('calisma');
          setKalan(calisma * 60);
          setBilgi(t('hedefler.odak.molaBitti'));
        }
      }
    }, 500);
    return () => window.clearInterval(zaman);
  }, [api, calisiyor, calisma, evre, kalan, kr.id, mola, notlar, onKaydedildi, t]);

  const durdur = () => {
    setCalisiyor(false);
    bitis.current = null;
  };
  const sifirla = () => {
    durdur();
    setEvre('calisma');
    setKalan(calisma * 60);
  };
  const dk = String(Math.floor(kalan / 60)).padStart(2, '0');
  const sn = String(kalan % 60).padStart(2, '0');
  return (
    <div className="grid gap-2 rounded-xl border border-purple-400/30 bg-purple-500/10 p-3" data-testid="okr-odak">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="flex items-center gap-2 text-sm">
          {evre === 'mola' && <Coffee className="h-4 w-4 text-amber-200" aria-hidden="true" />}
          {evre === 'calisma' ? t('hedefler.odak.calisma', { dk: calisma }) : t('hedefler.odak.mola', { dk: mola })}
        </span>
        <span className="font-mono text-2xl tabular-nums" role="timer" aria-live="off" data-testid="okr-odak-sure">
          {dk}:{sn}
        </span>
      </div>
      {evre === 'calisma' && (
        <input className={GIRDI} value={notlar} maxLength={2000} placeholder={t('hedefler.odak.notIpucu')} onChange={(e) => setNotlar(e.target.value)} aria-label={t('hedefler.odak.not')} />
      )}
      <div className="flex flex-wrap gap-2">
        {calisiyor ? (
          <Button type="button" size="sm" variant="outline" className={DIS_DUGME} onClick={durdur}>
            <Pause className="h-4 w-4" aria-hidden="true" />
            {t('hedefler.odak.duraklat')}
          </Button>
        ) : (
          <Button type="button" size="sm" variant="outline" className={DIS_DUGME} onClick={() => setCalisiyor(true)} data-testid="okr-odak-basla">
            <Play className="h-4 w-4" aria-hidden="true" />
            {t('hedefler.odak.basla')}
          </Button>
        )}
        <Button type="button" size="sm" variant="ghost" className="gap-1.5" onClick={sifirla}>
          <RotateCcw className="h-4 w-4" aria-hidden="true" />
          {t('hedefler.odak.sifirla')}
        </Button>
      </div>
      {bilgi && <p className="text-xs text-emerald-200">{bilgi}</p>}
      <HataSatiri hata={hata} />
    </div>
  );
}
