import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, ChevronDown, Info, Megaphone, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { duyuruKapat, duyuruOkundu, duyurularim, tarihGoster, type Duyuru, type DuyuruOnemi } from '@/lib/projeYonetimi';

const SERIT_RENGI: Record<DuyuruOnemi, string> = {
  bilgi: 'border-sky-400/40 bg-sky-500/10 text-sky-50',
  onemli: 'border-amber-400/40 bg-amber-500/10 text-amber-50',
  kritik: 'border-rose-400/50 bg-rose-500/15 text-rose-50',
};
const ROZET_RENGI: Record<DuyuruOnemi, string> = {
  bilgi: 'bg-sky-500/15 text-sky-200',
  onemli: 'bg-amber-500/15 text-amber-200',
  kritik: 'bg-rose-500/20 text-rose-200',
};
const SERITTE_EN_COK = 3;

/**
 * Panelin üstündeki duyuru şeridi + "Tüm duyurular" listesi (Faz 2B).
 *
 * Şeritte kapatılmamış duyurular (en çok üç, en önemlisi önce); kapatınca
 * sunucuya "kapattı" yazılıyor ve bir daha çıkmıyor. Liste açıldığında
 * okunmamışlar okundu işaretleniyor. Duyuru yoksa hiçbir şey çizilmiyor.
 */
export default function DuyuruSeridi() {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [duyurular, setDuyurular] = useState<Duyuru[]>([]);
  const [acik, setAcik] = useState(false);

  const yukle = useCallback(async () => {
    try {
      setDuyurular((await duyurularim()).duyurular);
    } catch {
      setDuyurular([]);
    }
  }, []);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const agirlik = (o: DuyuruOnemi) => (o === 'kritik' ? 0 : o === 'onemli' ? 1 : 2);
  const seritte = duyurular
    .filter((d) => !d.kapatildi)
    .sort((a, b) => agirlik(a.onem) - agirlik(b.onem))
    .slice(0, SERITTE_EN_COK);
  const okunmamis = duyurular.filter((d) => !d.okundu).length;

  const kapat = async (d: Duyuru) => {
    setDuyurular((l) => l.map((x) => (x.id === d.id ? { ...x, kapatildi: true, okundu: true } : x)));
    try {
      await duyuruKapat(d.id);
    } catch {
      /* bir sonraki açılışta yeniden görünür */
    }
  };

  const listeyiAc = async () => {
    const yeni = !acik;
    setAcik(yeni);
    if (!yeni) return;
    const okunacak = duyurular.filter((d) => !d.okundu);
    if (!okunacak.length) return;
    setDuyurular((l) => l.map((x) => ({ ...x, okundu: true })));
    await Promise.allSettled(okunacak.map((d) => duyuruOkundu(d.id)));
  };

  if (duyurular.length === 0) return null;

  return (
    <div className="mb-6 space-y-2" data-testid="duyuru-alani">
      {seritte.length > 0 && (
        <ul className="space-y-2" data-testid="duyuru-seridi" aria-label={t('duyurular.liste.baslik')}>
          {seritte.map((d) => (
            <li
              key={d.id}
              className={`flex items-start gap-3 rounded-2xl border px-4 py-3 text-sm ${SERIT_RENGI[d.onem]}`}
              role={d.onem === 'kritik' ? 'alert' : 'status'}
              data-testid={`duyuru-${d.id}`}
            >
              {d.onem === 'bilgi' ? (
                <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              ) : (
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              )}
              <div className="min-w-0 flex-1">
                <p className="break-words font-semibold">{d.baslik}</p>
                {d.metin && <p className="mt-0.5 whitespace-pre-line break-words opacity-90">{d.metin}</p>}
              </div>
              <button
                type="button"
                onClick={() => void kapat(d)}
                className="shrink-0 rounded-md p-1 opacity-80 hover:bg-white/10 hover:opacity-100"
                aria-label={t('duyurular.serit.kapat')}
                data-testid={`duyuru-kapat-${d.id}`}
              >
                <X className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
      )}
      <button
        type="button"
        onClick={() => void listeyiAc()}
        aria-expanded={acik}
        className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
        data-testid="duyurular-tumu"
      >
        <Megaphone className="h-3.5 w-3.5" aria-hidden="true" />
        {t('duyurular.serit.tumu', { sayi: duyurular.length })}
        {okunmamis > 0 && (
          <span className="rounded-full bg-purple-500/25 px-1.5 text-[10px] text-purple-100">{t('duyurular.serit.yeni', { sayi: okunmamis })}</span>
        )}
        <ChevronDown className={`h-3.5 w-3.5 transition-transform ${acik ? 'rotate-180' : ''}`} aria-hidden="true" />
      </button>
      {acik && (
        <ul className="cam-kart space-y-3 rounded-2xl border border-white/10 bg-white/[0.03] p-4" data-testid="duyuru-listesi">
          {duyurular.map((d) => (
            <li key={d.id} className="border-b border-white/5 pb-3 last:border-0 last:pb-0">
              <div className="mb-1 flex flex-wrap items-center gap-1.5 text-[11px]">
                <span className={`rounded-full px-2 py-0.5 ${ROZET_RENGI[d.onem]}`}>{t(`duyurular.onem.${d.onem}`)}</span>
                <span className="text-muted-foreground">{tarihGoster(d.created_at, dil)}</span>
              </div>
              <p className="break-words text-sm font-medium">{d.baslik}</p>
              {d.metin && <p className="mt-0.5 whitespace-pre-line break-words text-sm text-muted-foreground">{d.metin}</p>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
