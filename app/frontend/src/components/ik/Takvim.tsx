import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CalendarPlus, ChevronLeft, ChevronRight } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Bos, DIS_DUGME, KART, Rozet, Yukleniyor } from '@/components/ik/ortak';
import { DURUM_RENGI, TUR_RENGI, aralikYaz, gunAdlari, gunEkle, haftaGunu, hataMetni, type IkApi, type Meta, type Takvim } from '@/lib/ik';

function ayKaydir(ay: string, n: number): string {
  const [y, a] = ay.split('-').map(Number);
  const d = new Date(Date.UTC(y, a - 1 + n, 1));
  return d.toISOString().slice(0, 7);
}

/** Faz 6I — izin takvimi (ay görünümü): onaylı ve bekleyen izinler, resmi tatiller; ICS ile takvime ekleme. */
export default function TakvimBolumu({ api, meta }: { api: IkApi; meta: Meta }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [ay, setAy] = useState(meta.bugun.slice(0, 7));
  const [veri, setVeri] = useState<Takvim | null>(null);
  const [secili, setSecili] = useState<string | null>(null);

  const yukle = useCallback(async () => {
    setVeri(null);
    try {
      setVeri(await api.takvim(ay));
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  }, [api, ay, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const hucreler = useMemo(() => {
    if (!veri) return [];
    const bos = haftaGunu(veri.ilk);
    const sonuc: (string | null)[] = Array.from({ length: bos }, () => null);
    for (let g = veri.ilk; g <= veri.son; g = gunEkle(g, 1)) sonuc.push(g);
    while (sonuc.length % 7) sonuc.push(null);
    return sonuc;
  }, [veri]);

  const tatil = useMemo(() => Object.fromEntries((veri?.tatiller || []).map((x) => [x.tarih, x])), [veri]);
  const gunIzinleri = (g: string) => (veri?.izinler || []).filter((i) => i.baslangic <= g && i.bitis >= g);
  const adlar = gunAdlari(dil, 'short');
  let ayAdi = ay;
  try {
    const [y, a] = ay.split('-').map(Number);
    ayAdi = new Intl.DateTimeFormat(dil === 'ar' ? 'ar-u-nu-latn' : dil, { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(new Date(Date.UTC(y, a - 1, 1)));
  } catch {
    /* yoksay */
  }
  const gosterilen = secili ? gunIzinleri(secili) : veri?.izinler || [];

  return (
    <div className="space-y-4">
      <div className={`${KART} flex flex-wrap items-center gap-2 p-3`}>
        <Button size="icon" variant="ghost" aria-label={t('ik.takvim.onceki')} onClick={() => setAy(ayKaydir(ay, -1))}>
          <ChevronLeft className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
        </Button>
        <h3 className="min-w-[10rem] text-center text-base font-semibold" data-testid="ik-takvim-ay">
          {ayAdi}
        </h3>
        <Button size="icon" variant="ghost" aria-label={t('ik.takvim.sonraki')} onClick={() => setAy(ayKaydir(ay, 1))}>
          <ChevronRight className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setAy(meta.bugun.slice(0, 7))}>
          {t('ik.takvim.bugun')}
        </Button>
        <Button variant="outline" className={`${DIS_DUGME} ms-auto`} onClick={() => void api.izinIcs().catch((e) => toast.error(hataMetni(t, e)))} data-testid="ik-takvim-ics">
          <CalendarPlus className="h-4 w-4" aria-hidden="true" />
          {t('ik.takvim.ics')}
        </Button>
      </div>
      <div className={`${KART} p-2 sm:p-4`}>
        {!veri ? (
          <Yukleniyor />
        ) : (
          <div className="grid grid-cols-7 gap-1" role="grid" aria-label={ayAdi} data-testid="ik-takvim">
            {adlar.map((a, i) => (
              <div key={a} className={`pb-1 text-center text-[11px] font-medium ${veri.calisma_gunleri.includes(i) ? 'text-muted-foreground' : 'text-muted-foreground/60'}`} role="columnheader">
                {a}
              </div>
            ))}
            {hucreler.map((g, k) => {
              if (!g) return <div key={k} className="min-h-[3.5rem] sm:min-h-[5.5rem]" aria-hidden="true" />;
              const izinler = gunIzinleri(g);
              const tt = tatil[g];
              const calisma = veri.calisma_gunleri.includes(haftaGunu(g));
              return (
                <button
                  key={g}
                  type="button"
                  role="gridcell"
                  onClick={() => setSecili(secili === g ? null : g)}
                  aria-pressed={secili === g}
                  className={`flex min-h-[3.5rem] flex-col items-stretch gap-0.5 rounded-lg border p-1 text-start text-[11px] transition-colors sm:min-h-[5.5rem] ${
                    secili === g ? 'border-purple-400/60 bg-purple-500/15' : 'border-white/10 bg-black/20 hover:border-white/25'
                  } ${!calisma || (tt && tt.oran >= 1) ? 'opacity-80' : ''} ${g === meta.bugun ? 'ring-1 ring-purple-400/70' : ''}`}
                  data-gun={g}
                >
                  <span className={`font-semibold ${!calisma ? 'text-muted-foreground' : ''}`}>{Number(g.slice(8))}</span>
                  {tt && (
                    <span className="truncate rounded bg-rose-500/20 px-1 text-[10px] text-rose-100" title={tt.ad}>
                      {tt.oran < 1 ? `½ ${tt.ad}` : tt.ad}
                    </span>
                  )}
                  <span className="hidden flex-col gap-0.5 sm:flex">
                    {izinler.slice(0, 3).map((i) => (
                      <span
                        key={i.id}
                        className={`truncate rounded px-1 text-[10px] text-white ${i.durum === 'beklemede' ? 'border border-dashed border-white/50' : ''}`}
                        style={{ background: `${TUR_RENGI[i.tur]}${i.durum === 'beklemede' ? '55' : 'cc'}` }}
                        title={`${i.personel_ad} — ${t(`ik.tur.${i.tur}`)}`}
                      >
                        {i.personel_ad}
                      </span>
                    ))}
                    {izinler.length > 3 && <span className="text-[10px] text-muted-foreground">+{izinler.length - 3}</span>}
                  </span>
                  {izinler.length > 0 && (
                    <span className="flex flex-wrap gap-0.5 sm:hidden" aria-label={t('ik.takvim.izinliSayisi', { sayi: izinler.length })}>
                      {izinler.slice(0, 4).map((i) => (
                        <span key={i.id} className="h-1.5 w-1.5 rounded-full" style={{ background: TUR_RENGI[i.tur] }} />
                      ))}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        )}
      </div>
      <div className={`${KART} p-3 sm:p-4`}>
        <h4 className="mb-2 text-sm font-semibold">{secili ? t('ik.takvim.gunIzinleri', { gun: aralikYaz(secili, secili, dil) }) : t('ik.takvim.ayIzinleri')}</h4>
        {gosterilen.length === 0 ? (
          <Bos>{t('ik.takvim.bos')}</Bos>
        ) : (
          <ul className="space-y-1.5">
            {gosterilen.map((i) => (
              <li key={i.id} className="flex flex-wrap items-center gap-2 text-xs">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: TUR_RENGI[i.tur] }} aria-hidden="true" />
                <span className="font-medium">{i.personel_ad}</span>
                <span className="text-muted-foreground">
                  {t(`ik.tur.${i.tur}`)} · {aralikYaz(i.baslangic, i.bitis, dil)}
                </span>
                <Rozet renk={DURUM_RENGI[i.durum]}>{t(`ik.durum.${i.durum}`)}</Rozet>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
