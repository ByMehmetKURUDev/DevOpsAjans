import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, CalendarDays, ChevronLeft, ChevronRight, Inbox, Loader2, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  bugunIso,
  gunDakikasi,
  gunEkle,
  gunYaz,
  hataMetni,
  saatYaz,
  yerelIso,
  type IsOzeti,
  type Pano as PanoVerisi,
  type SahaApi,
} from '@/lib/sahaServisi';
import { Bos, DURUM_RENK, KART, Yukleniyor } from './ortak';

/**
 * Bir teknisyenin günlük işlerini zaman çizelgesi şeritlerine yerleştirir: örtüşen işler ayrı şeritlere
 * düşer (aralık grafiği açgözlü boyama). Dakikalar gün başından (İstanbul saati).
 */
function seritle(isler: IsOzeti[], gunBas: string, gunBit: string) {
  const kutular = isler
    .filter((x) => x.plan_bas)
    .map((x) => ({
      x,
      bas: x.plan_bas! < gunBas ? 0 : gunDakikasi(x.plan_bas!),
      bit: x.plan_bit && x.plan_bit < gunBit ? gunDakikasi(x.plan_bit) : 24 * 60,
    }))
    .sort((a, b) => a.bas - b.bas || a.x.id - b.x.id);
  const sonlar: number[] = [];
  const yerlesik = kutular.map((k) => {
    let serit = sonlar.findIndex((son) => son <= k.bas);
    if (serit < 0) {
      serit = sonlar.length;
      sonlar.push(k.bit);
    } else sonlar[serit] = k.bit;
    return { ...k, serit };
  });
  const seritSayisi = Math.max(1, sonlar.length);
  return yerlesik.map((k) => ({ ...k, seritSayisi }));
}

/** Yarım saatlik dilim genişliği (px) ve satır yüksekliği. */
const DILIM = 48;
const SATIR = 76;
const TASIMA_TURU = 'application/x-mk-saha';

interface Tasinan {
  id: number;
  eski: number | null;
}

/**
 * Faz 6S — sevk panosu (dispatch): gün görünümünde teknisyen satırları × saat (zaman çizelgesi),
 * hafta görünümünde teknisyen × gün; üstte atanmamış işler kuyruğu. Sürükle-bırak (HTML5, ek paket
 * yok) ile atama / saat değiştirme; kuyruğa bırakmak atamayı kaldırır. Aynı teknisyende örtüşen işler
 * kırmızı çerçeve + uyarı (engellemez). Harita yok: adres için iş ayrıntısında "Haritada aç".
 */
export default function Pano({ api, onAc, saltOkunur }: { api: SahaApi; onAc: (id: number) => void; saltOkunur: boolean }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const rtl = typeof document !== 'undefined' && document.documentElement.dir === 'rtl';
  const [gun, setGun] = useState(bugunIso);
  const [gorunum, setGorunum] = useState<'gun' | 'hafta'>('gun');
  const [veri, setVeri] = useState<PanoVerisi | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [mesgul, setMesgul] = useState(false);
  const [hedef, setHedef] = useState<string | null>(null);
  const tasinan = useRef<Tasinan | null>(null);

  const yukle = useCallback(async () => {
    setHata(null);
    try {
      setVeri(await api.pano(gun, gorunum));
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  }, [api, gun, gorunum, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  // Görünen saat aralığı: 07–21, işler dışarı taşıyorsa genişler.
  const [basSaat, bitSaat] = useMemo(() => {
    let b = 7;
    let e = 21;
    for (const x of veri?.isler || []) {
      if (!x.plan_bas || x.plan_bas < (veri?.bas || '') || gorunum !== 'gun') continue;
      b = Math.min(b, Math.floor(gunDakikasi(x.plan_bas) / 60));
      const son = x.plan_bit && x.plan_bit < (veri?.bit || '') ? gunDakikasi(x.plan_bit) : 24 * 60;
      e = Math.max(e, Math.ceil(son / 60));
    }
    return [Math.max(0, b), Math.min(24, e)];
  }, [veri, gorunum]);
  const dilimSayisi = (bitSaat - basSaat) * 2;
  const iz = dilimSayisi * DILIM;

  const birak = async (teknisyen: number | null, plan_bas?: string) => {
    const x = tasinan.current;
    tasinan.current = null;
    setHedef(null);
    if (!x || saltOkunur) return;
    if (teknisyen === x.eski && !plan_bas) return;
    setMesgul(true);
    try {
      const d = await api.plan(x.id, {
        teknisyen_id: teknisyen,
        eski_teknisyen_id: x.eski,
        ...(plan_bas ? { plan_bas } : {}),
      });
      if (d.cakismalar?.length) toast.warning(t('sahaServisi.pano.cakismaUyari', { no: d.cakismalar.map((c) => c.no).join(', ') }));
      else toast.success(teknisyen ? t('sahaServisi.pano.atandi', { no: d.no }) : t('sahaServisi.pano.kuyrugaAlindi', { no: d.no }));
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  const surukleBasla = (e: DragEvent, is: IsOzeti, eski: number | null) => {
    if (saltOkunur) return;
    tasinan.current = { id: is.id, eski };
    try {
      e.dataTransfer.setData(TASIMA_TURU, String(is.id));
      e.dataTransfer.setData('text/plain', is.no);
      e.dataTransfer.effectAllowed = 'move';
    } catch {
      /* bazı tarayıcılar */
    }
  };

  const izdenSaat = (e: DragEvent<HTMLDivElement>): string => {
    const r = e.currentTarget.getBoundingClientRect();
    const x = rtl ? r.right - e.clientX : e.clientX - r.left;
    const dilim = Math.max(0, Math.min(dilimSayisi - 1, Math.floor(x / DILIM)));
    const dk = basSaat * 60 + dilim * 30;
    return `${String(Math.floor(dk / 60)).padStart(2, '0')}:${String(dk % 60).padStart(2, '0')}`;
  };

  const isKarti = (x: IsOzeti, eski: number | null, kucuk = false) => {
    const cakisan = (x.cakisan || []).length > 0;
    return (
      <div
        key={`${x.id}-${eski ?? 'k'}`}
        draggable={!saltOkunur}
        onDragStart={(e) => surukleBasla(e, x, eski)}
        onDragEnd={() => setHedef(null)}
        onClick={() => onAc(x.id)}
        onKeyDown={(e) => e.key === 'Enter' && onAc(x.id)}
        role="button"
        tabIndex={0}
        title={cakisan ? t('sahaServisi.pano.cakisma') : undefined}
        className={`group flex h-full min-w-0 cursor-grab flex-col justify-center overflow-hidden rounded-lg border px-2 py-1 text-start text-xs shadow-sm active:cursor-grabbing ${DURUM_RENK[x.durum]} ${
          cakisan ? 'ring-2 ring-red-500' : ''
        } ${kucuk ? '' : 'absolute inset-x-0 top-1 bottom-1'}`}
        data-testid="saha-pano-is"
        data-is-id={x.id}
        data-cakisma={cakisan ? '1' : '0'}
      >
        <span className="flex items-center gap-1 truncate font-semibold">
          {cakisan && <AlertTriangle className="h-3 w-3 flex-none text-red-300" aria-label={t('sahaServisi.pano.cakisma')} />}
          <span className="tabular-nums" dir="ltr">
            {x.plan_bas ? saatYaz(x.plan_bas, dil) : ''}
          </span>
          <span className="truncate">{x.baslik}</span>
        </span>
        <span className="truncate text-[11px] opacity-80">{x.musteri_ad}</span>
      </div>
    );
  };

  const surukleUzerinde = (anahtar: string) => (e: DragEvent) => {
    if (saltOkunur || !tasinan.current) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    if (hedef !== anahtar) setHedef(anahtar);
  };

  const gunler = useMemo(() => (veri && gorunum === 'hafta' ? Array.from({ length: 7 }, (_, i) => gunEkle(veri.gun, i)) : []), [veri, gorunum]);
  const gunAdi = (iso: string) => {
    const d = new Date(new Date(iso).getTime() + 3 * 3600 * 1000);
    return d.toISOString().slice(0, 10);
  };

  return (
    <div className="space-y-4" data-testid="saha-pano">
      <div className="flex flex-wrap items-center gap-2">
        <Button size="icon" variant="ghost" onClick={() => setGun(gunEkle(gun, gorunum === 'hafta' ? -7 : -1))} aria-label={t('sahaServisi.pano.onceki')}>
          <ChevronLeft className="h-5 w-5 rtl:rotate-180" aria-hidden="true" />
        </Button>
        <Button size="sm" variant="outline" className="!bg-transparent border-white/20" onClick={() => setGun(bugunIso())}>
          {t('sahaServisi.pano.bugun')}
        </Button>
        <Button size="icon" variant="ghost" onClick={() => setGun(gunEkle(gun, gorunum === 'hafta' ? 7 : 1))} aria-label={t('sahaServisi.pano.sonraki')}>
          <ChevronRight className="h-5 w-5 rtl:rotate-180" aria-hidden="true" />
        </Button>
        <p className="min-w-0 flex-1 truncate text-base font-semibold" data-testid="saha-pano-gun">
          {gorunum === 'hafta' && veri ? `${gunYaz(veri.gun, dil)} – ${gunYaz(gunEkle(veri.gun, 6), dil)}` : gunYaz(gun, dil, true)}
        </p>
        <div className="flex rounded-lg border border-white/10 p-0.5" role="group" aria-label={t('sahaServisi.pano.gorunum')}>
          {(['gun', 'hafta'] as const).map((g) => (
            <button
              key={g}
              type="button"
              aria-pressed={gorunum === g}
              onClick={() => setGorunum(g)}
              className={`rounded-md px-3 py-1.5 text-sm ${gorunum === g ? 'bg-purple-500/25 text-white' : 'text-muted-foreground hover:text-white'}`}
              data-testid={`saha-pano-${g}`}
            >
              {t(`sahaServisi.pano.${g}`)}
            </button>
          ))}
        </div>
        <Button size="icon" variant="ghost" onClick={() => void yukle()} aria-label={t('sahaServisi.yenile')}>
          {mesgul ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <RefreshCw className="h-4 w-4" aria-hidden="true" />}
        </Button>
      </div>
      {hata && (
        <p className="text-sm text-red-300" role="alert">
          {hata}
        </p>
      )}
      {!veri ? (
        <Yukleniyor />
      ) : (
        <>
          {/* Atanmamış işler kuyruğu (buraya bırakmak atamayı kaldırır). */}
          <section
            className={`${KART} p-3 ${hedef === 'kuyruk' ? 'ring-2 ring-purple-400' : ''}`}
            onDragOver={surukleUzerinde('kuyruk')}
            onDragLeave={() => setHedef(null)}
            onDrop={(e) => {
              e.preventDefault();
              void birak(null);
            }}
            aria-labelledby="saha-kuyruk-b"
            data-testid="saha-pano-kuyruk"
          >
            <h3 id="saha-kuyruk-b" className="mb-2 flex items-center gap-2 text-sm font-semibold">
              <Inbox className="h-4 w-4 text-purple-300" aria-hidden="true" />
              {t('sahaServisi.pano.kuyruk', { sayi: veri.kuyruk.length })}
            </h3>
            {veri.kuyruk.length === 0 ? (
              <p className="text-xs text-muted-foreground">{t('sahaServisi.pano.kuyrukBos')}</p>
            ) : (
              <div className="flex gap-2 overflow-x-auto pb-1">
                {veri.kuyruk.map((x) => (
                  <div key={x.id} className="h-14 w-56 flex-none">
                    {isKarti(x, x.teknisyenler[0]?.id ?? null, true)}
                  </div>
                ))}
              </div>
            )}
            {!saltOkunur && <p className="mt-2 text-[11px] text-muted-foreground">{t('sahaServisi.pano.ipucu')}</p>}
          </section>

          {veri.teknisyenler.length === 0 ? (
            <div className={`${KART} p-6`}>
              <Bos>{t('sahaServisi.pano.teknisyenYok')}</Bos>
            </div>
          ) : gorunum === 'gun' ? (
            <div className={`${KART} overflow-x-auto`} data-testid="saha-pano-cizelge">
              <div style={{ minWidth: iz + 160 }}>
                <div className="flex border-b border-white/10 text-[11px] text-muted-foreground">
                  <div className="sticky start-0 z-10 w-40 flex-none bg-[#0b0614]/95 px-3 py-2">{t('sahaServisi.pano.teknisyen')}</div>
                  <div className="relative flex-none" style={{ width: iz }}>
                    {Array.from({ length: bitSaat - basSaat }, (_, i) => (
                      // Konum satır yönüne göre (rtl'de sağdan); yalnız rakamlar ltr.
                      <span key={i} className="absolute top-2 border-s border-white/10 ps-1" style={{ insetInlineStart: i * DILIM * 2 }}>
                        <span dir="ltr">{String(basSaat + i).padStart(2, '0')}:00</span>
                      </span>
                    ))}
                    <div className="h-8" />
                  </div>
                </div>
                {veri.teknisyenler.map((te) => {
                  const isleri = veri.isler.filter((x) => x.teknisyenler.some((y) => y.id === te.id));
                  return (
                    <div key={te.id} className="flex border-b border-white/5 last:border-b-0" data-teknisyen={te.id}>
                      <div className="sticky start-0 z-10 flex w-40 flex-none items-center gap-2 bg-[#0b0614]/95 px-3" style={{ height: SATIR }}>
                        <span className="h-3 w-3 flex-none rounded-full" style={{ background: te.renk }} aria-hidden="true" />
                        <span className="truncate text-sm font-medium">{te.ad}</span>
                      </div>
                      <div
                        className={`relative flex-none ${hedef === `t${te.id}` ? 'bg-purple-500/10' : ''}`}
                        style={{
                          width: iz,
                          height: SATIR,
                          backgroundImage: `repeating-linear-gradient(${rtl ? 'to left' : 'to right'}, rgba(255,255,255,0.06) 0 1px, transparent 1px ${DILIM}px)`,
                        }}
                        onDragOver={surukleUzerinde(`t${te.id}`)}
                        onDragLeave={() => setHedef(null)}
                        onDrop={(e) => {
                          e.preventDefault();
                          void birak(te.id, yerelIso(veri.gun, izdenSaat(e)));
                        }}
                        data-testid="saha-pano-iz"
                        data-teknisyen-id={te.id}
                      >
                        {seritle(isleri, veri.bas, veri.bit).map(({ x, bas, bit, serit, seritSayisi }) => {
                          // Örtüşen işler alt alta şeritlere bölünür (yazılar üst üste binmesin; çakışma kırmızı çerçeveli).
                          const sol = ((Math.max(bas, basSaat * 60) - basSaat * 60) / 30) * DILIM;
                          const gen = Math.max(40, ((Math.min(bit, bitSaat * 60) - Math.max(bas, basSaat * 60)) / 30) * DILIM - 3);
                          const yuk = SATIR / seritSayisi;
                          return (
                            <div key={x.id} className="absolute" style={{ insetInlineStart: sol, width: gen, top: serit * yuk, height: yuk }}>
                              {isKarti(x, te.id)}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className={`${KART} overflow-x-auto`} data-testid="saha-pano-hafta">
              <table className="w-full min-w-[900px] table-fixed border-collapse text-sm">
                <thead>
                  <tr className="text-[11px] text-muted-foreground">
                    <th className="w-36 px-3 py-2 text-start font-medium">{t('sahaServisi.pano.teknisyen')}</th>
                    {gunler.map((g) => (
                      <th key={g} className={`px-2 py-2 text-start font-medium ${g === bugunIso() ? 'text-purple-200' : ''}`}>
                        <CalendarDays className="me-1 inline h-3 w-3" aria-hidden="true" />
                        {gunYaz(g, dil)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {veri.teknisyenler.map((te) => (
                    <tr key={te.id} className="border-t border-white/5 align-top">
                      <td className="px-3 py-2">
                        <span className="flex items-center gap-2">
                          <span className="h-3 w-3 rounded-full" style={{ background: te.renk }} aria-hidden="true" />
                          <span className="truncate font-medium">{te.ad}</span>
                        </span>
                      </td>
                      {gunler.map((g) => {
                        const anahtar = `h${te.id}-${g}`;
                        const isleri = veri.isler.filter((x) => x.plan_bas && gunAdi(x.plan_bas) === g && x.teknisyenler.some((y) => y.id === te.id));
                        return (
                          <td
                            key={g}
                            className={`h-24 border-s border-white/5 p-1 ${hedef === anahtar ? 'bg-purple-500/10' : ''}`}
                            onDragOver={surukleUzerinde(anahtar)}
                            onDragLeave={() => setHedef(null)}
                            onDrop={(e) => {
                              e.preventDefault();
                              const x = tasinan.current ? [...veri.isler, ...veri.kuyruk].find((y) => y.id === tasinan.current!.id) : null;
                              const dk = x?.plan_bas ? gunDakikasi(x.plan_bas) : 9 * 60;
                              void birak(te.id, yerelIso(g, `${String(Math.floor(dk / 60)).padStart(2, '0')}:${String(dk % 60).padStart(2, '0')}`));
                            }}
                            data-testid="saha-pano-hucre"
                          >
                            <div className="flex flex-col gap-1">
                              {isleri.map((x) => (
                                <div key={x.id} className="h-11">
                                  {isKarti(x, te.id, true)}
                                </div>
                              ))}
                            </div>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
