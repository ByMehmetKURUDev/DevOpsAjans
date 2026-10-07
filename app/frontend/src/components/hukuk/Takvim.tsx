import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CalendarPlus, ChevronLeft, ChevronRight, Download } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { OlayFormu, OlaySatiri } from '@/components/hukuk/DosyaKayitlari';
import { Alan, KART, OLAY_RENGI, SECIM, SekmeDugmesi, Yukleniyor } from '@/components/hukuk/ortak';
import { ayBasi, ayEkle, gunEkle, gunYaz, haftaBasi, hataMetni, type Dosya, type HukukApi, type Meta, type Olay } from '@/lib/hukuk';

type Gorunum = 'ay' | 'hafta';

/** Faz 6H — takvim: ay/hafta görünümü, sorumlu avukat süzgeci, ICS (sorumlu başına), olay ekleme. */
export default function Takvim({ api, meta }: { api: HukukApi; meta: Meta }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [gorunum, setGorunum] = useState<Gorunum>('ay');
  const [imlec, setImlec] = useState(meta.bugun);
  const [sorumlu, setSorumlu] = useState('');
  const [olaylar, setOlaylar] = useState<Olay[] | null>(null);
  const [dosyalar, setDosyalar] = useState<Dosya[]>([]);
  const [dosyaId, setDosyaId] = useState('');
  const [secilenGun, setSecilenGun] = useState<string | null>(null);

  const aralik = useMemo(() => {
    if (gorunum === 'hafta') {
      const bas = haftaBasi(imlec);
      return { bas, bit: gunEkle(bas, 6) };
    }
    const bas = haftaBasi(ayBasi(imlec));
    return { bas, bit: gunEkle(bas, 41) };
  }, [gorunum, imlec]);

  const yukle = useCallback(async () => {
    try {
      setOlaylar((await api.olaylar({ bas: aralik.bas, bit: aralik.bit, sorumlu: sorumlu || undefined })).items);
    } catch (e) {
      toast.error(hataMetni(t, e));
      setOlaylar([]);
    }
  }, [api, aralik, sorumlu, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  useEffect(() => {
    api
      .dosyalar()
      .then((r) => setDosyalar(r.items))
      .catch(() => setDosyalar([]));
  }, [api]);

  const gunler = useMemo(() => {
    const n = gorunum === 'hafta' ? 7 : 42;
    return Array.from({ length: n }, (_, i) => gunEkle(aralik.bas, i));
  }, [aralik.bas, gorunum]);
  const gunAdlari = useMemo(
    () => gunler.slice(0, 7).map((g) => new Intl.DateTimeFormat(dil, { weekday: 'short', timeZone: 'UTC' }).format(new Date(`${g}T00:00:00Z`))),
    [gunler, dil]
  );
  const gruplu = useMemo(() => {
    const m: Record<string, Olay[]> = {};
    for (const o of olaylar || []) (m[o.tarih] ||= []).push(o);
    return m;
  }, [olaylar]);

  const ileri = (n: number) => setImlec(gorunum === 'hafta' ? gunEkle(imlec, 7 * n) : ayEkle(imlec, n));
  const baslik =
    gorunum === 'hafta'
      ? `${gunYaz(aralik.bas, dil)} – ${gunYaz(aralik.bit, dil)}`
      : new Intl.DateTimeFormat(dil, { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(new Date(`${ayBasi(imlec)}T00:00:00Z`));

  const ics = async () => {
    try {
      await api.icsIndir(sorumlu, dil.slice(0, 2));
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const listelenen = (secilenGun ? gruplu[secilenGun] || [] : (olaylar || []).filter((o) => o.tarih >= meta.bugun && !o.tamamlandi)) as Olay[];

  return (
    <div className="space-y-4" data-testid="hukuk-takvim">
      <div className={`${KART} p-4 sm:p-6`}>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <div className="flex gap-1" role="tablist">
            <SekmeDugmesi secili={gorunum === 'ay'} onClick={() => setGorunum('ay')} testid="takvim-ay">
              {t('hukuk.takvim.ay')}
            </SekmeDugmesi>
            <SekmeDugmesi secili={gorunum === 'hafta'} onClick={() => setGorunum('hafta')} testid="takvim-hafta">
              {t('hukuk.takvim.hafta')}
            </SekmeDugmesi>
          </div>
          <Button size="icon" variant="ghost" aria-label={t('hukuk.takvim.onceki')} onClick={() => ileri(-1)}>
            <ChevronLeft className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
          </Button>
          <span className="min-w-[10rem] text-center text-sm font-semibold" data-testid="hukuk-takvim-baslik">
            {baslik}
          </span>
          <Button size="icon" variant="ghost" aria-label={t('hukuk.takvim.sonraki')} onClick={() => ileri(1)}>
            <ChevronRight className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setImlec(meta.bugun)}>
            {t('hukuk.takvim.bugun')}
          </Button>
          <select className={`${SECIM} ms-auto w-auto max-w-[220px]`} value={sorumlu} onChange={(e) => setSorumlu(e.target.value)} aria-label={t('hukuk.takvim.sorumlu')} data-testid="hukuk-takvim-sorumlu">
            <option value="">{t('hukuk.takvim.sorumlu')}: {t('hukuk.ortak.hepsi')}</option>
            {meta.ekip.map((k) => (
              <option key={k.eposta} value={k.eposta}>
                {k.eposta}
              </option>
            ))}
          </select>
          <Button size="sm" variant="outline" className="gap-1 !bg-transparent" onClick={() => void ics()} title={t('hukuk.takvim.icsIpucu')} data-testid="hukuk-takvim-ics">
            <Download className="h-4 w-4" aria-hidden="true" />
            {t('hukuk.takvim.ics')}
          </Button>
        </div>
        {olaylar === null ? (
          <Yukleniyor />
        ) : (
          <div className="overflow-x-auto">
            <div className="grid min-w-[560px] grid-cols-7 gap-px overflow-hidden rounded-xl border border-white/10 bg-white/10" data-testid="hukuk-takvim-izgara" data-gorunum={gorunum}>
              {gunAdlari.map((a, i) => (
                <div key={i} className="bg-black/40 px-2 py-1 text-center text-[11px] font-medium text-muted-foreground">
                  {a}
                </div>
              ))}
              {gunler.map((g) => {
                const disarida = gorunum === 'ay' && g.slice(0, 7) !== imlec.slice(0, 7);
                const liste = gruplu[g] || [];
                return (
                  <button
                    type="button"
                    key={g}
                    onClick={() => setSecilenGun(secilenGun === g ? null : g)}
                    className={`flex flex-col gap-0.5 bg-black/30 p-1 text-start align-top ${gorunum === 'hafta' ? 'min-h-[160px]' : 'min-h-[84px]'} ${
                      disarida ? 'opacity-40' : ''
                    } ${secilenGun === g ? 'ring-2 ring-inset ring-blue-400/60' : ''}`}
                    data-gun={g}
                  >
                    <span className={`text-[11px] ${g === meta.bugun ? 'rounded bg-blue-500/40 px-1 font-bold text-white' : 'text-muted-foreground'}`}>{Number(g.slice(8))}</span>
                    {liste.slice(0, gorunum === 'hafta' ? 8 : 3).map((o) => (
                      <span key={o.id} className={`truncate rounded border px-1 text-[10px] ${OLAY_RENGI[o.tur]} ${o.tamamlandi ? 'line-through opacity-60' : ''}`} data-olay-tur={o.tur}>
                        {o.saat ? `${o.saat} ` : ''}
                        {o.baslik || t(`hukuk.olay.tur.${o.tur}`)}
                      </span>
                    ))}
                    {liste.length > (gorunum === 'hafta' ? 8 : 3) && <span className="text-[10px] text-muted-foreground">+{liste.length - (gorunum === 'hafta' ? 8 : 3)}</span>}
                  </button>
                );
              })}
            </div>
          </div>
        )}
        <p className="mt-2 text-xs text-muted-foreground">{t('hukuk.takvim.icsIpucu')}</p>
      </div>

      <div className={`${KART} space-y-3 p-4 sm:p-6`}>
        <h3 className="text-base font-semibold">{secilenGun ? gunYaz(secilenGun, dil, { dateStyle: 'full' }) : t('hukuk.takvim.yaklasan')}</h3>
        {listelenen.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('hukuk.olay.bos')}</p>
        ) : (
          <ul className="space-y-1.5" data-testid="hukuk-takvim-liste">
            {listelenen.map((o) => (
              <OlaySatiri key={o.id} o={o} api={api} dil={dil} onDegisti={() => void yukle()} />
            ))}
          </ul>
        )}
      </div>

      <div className={`${KART} space-y-3 p-4 sm:p-6`}>
        <h3 className="flex items-center gap-2 text-base font-semibold">
          <CalendarPlus className="h-4 w-4" aria-hidden="true" />
          {t('hukuk.olay.yeni')}
        </h3>
        <Alan etiket={t('hukuk.olay.alan.dosya')}>
          <select className={SECIM} value={dosyaId} onChange={(e) => setDosyaId(e.target.value)} data-testid="hukuk-takvim-dosya">
            <option value="">{t('hukuk.olay.alan.dosyaYok')}</option>
            {dosyalar.map((d) => (
              <option key={d.id} value={d.id}>
                {d.baslik} · {d.muvekkil_ad}
              </option>
            ))}
          </select>
        </Alan>
        <OlayFormu api={api} meta={meta} dosyaId={dosyaId ? Number(dosyaId) : null} varsayilanTarih={secilenGun || meta.bugun} key={secilenGun || 'yok'} onEklendi={() => void yukle()} />
      </div>
    </div>
  );
}
