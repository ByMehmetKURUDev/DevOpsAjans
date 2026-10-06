import { useCallback, useEffect, useMemo, useState, type DragEvent } from 'react';
import { AlertTriangle, CalendarDays, CalendarRange, ChevronLeft, ChevronRight, Download, GripVertical, List, Loader2, Mail, Plus, Sun } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import GonderiCekmecesi from '@/components/icerikStudyosu/GonderiCekmecesi';
import PaylasimPaketi from '@/components/icerikStudyosu/PaylasimPaketi';
import { Bos, DIS_DUGME, DURUM_RENGI, DurumRozeti, KanalIkonu, KART, SECIM, Yukleniyor } from '@/components/icerikStudyosu/ortak';
import type { PlanTaslagi } from '@/components/IcerikStudyosu';
import {
  gecikenleriHatirlat,
  gunAnahtari,
  gunEkle,
  haftaBasi,
  hataMetni,
  saatYaz,
  tarayiciSaatDilimi,
  tarihSaatYaz,
  type Gonderi,
  type GonderiListesi,
  type Meta,
  type StudyoApi,
} from '@/lib/icerikStudyosu';

/**
 * Faz 5I — Sosyal medya planlayıcı: ay / hafta / gün takvimi, liste, kanal/kampanya/durum
 * süzgeci, sürükle-bırak ile tarih değiştirme (HTML5; yeni paket yok — saat korunur, gün
 * kayar), CSV dışa aktarma (Postiz/Buffer). Mobilde (dar ekran) ay/hafta yerine liste/gün.
 * Takvim tarayıcının saat diliminde çiziliyor; gönderinin kendi saat dilimi kayıtta.
 */

type Gorunum = 'ay' | 'hafta' | 'gun' | 'liste';
const BITMIS = ['yayinlandi', 'reddedildi'];

function darMi(): boolean {
  try {
    return window.matchMedia('(max-width: 639px)').matches;
  } catch {
    return false;
  }
}

function aralik(g: Gorunum, odak: Date): [Date, Date] {
  if (g === 'hafta') {
    const b = haftaBasi(odak);
    return [b, gunEkle(b, 6)];
  }
  if (g === 'gun') return [odak, odak];
  const ayBasi = new Date(odak.getFullYear(), odak.getMonth(), 1);
  if (g === 'liste') return [ayBasi, new Date(odak.getFullYear(), odak.getMonth() + 1, 0)];
  const b = haftaBasi(ayBasi);
  return [b, gunEkle(b, 41)];
}

/** Gönderinin yerel planlanan değerine (kendi saat diliminde) `gun` farkını ekler. */
function gunKaydir(planlanan: string, fark: number): string {
  const [tarih, saat = '10:00'] = planlanan.split('T');
  const [y, a, g] = tarih.split('-').map(Number);
  const d = new Date(Date.UTC(y, a - 1, g + fark));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}T${saat.slice(0, 5)}`;
}

function gunFarki(a: string, b: string): number {
  const [y1, a1, g1] = a.split('-').map(Number);
  const [y2, a2, g2] = b.split('-').map(Number);
  return Math.round((Date.UTC(y2, a2 - 1, g2) - Date.UTC(y1, a1 - 1, g1)) / 86400000);
}

export default function Planlayici({
  api,
  meta,
  taslak,
  onTaslakKullanildi,
  acilacak,
  onAcildi,
}: {
  api: StudyoApi;
  meta: Meta;
  taslak: PlanTaslagi | null;
  onTaslakKullanildi: () => void;
  acilacak: number | null;
  onAcildi: () => void;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const tz = useMemo(() => tarayiciSaatDilimi(meta.varsayilan_saat_dilimi), [meta.varsayilan_saat_dilimi]);
  const [dar, setDar] = useState(darMi);
  const [gorunum, setGorunum] = useState<Gorunum>(() => (darMi() ? 'liste' : 'ay'));
  const [odak, setOdak] = useState<Date>(() => new Date());
  const [suzgec, setSuzgec] = useState<{ kanal: string; kampanya: string; durum: string }>({ kanal: '', kampanya: '', durum: '' });
  const [veri, setVeri] = useState<GonderiListesi | null>(null);
  const [yukleniyor, setYukleniyor] = useState(false);
  const [cekmece, setCekmece] = useState<{ gonderi: Gonderi | null; gun?: string | null; taslak?: PlanTaslagi | null } | null>(null);
  const [paketId, setPaketId] = useState<number | null>(null);
  const [surukle, setSurukle] = useState<number | null>(null);
  const [hedefGun, setHedefGun] = useState<string | null>(null);

  useEffect(() => {
    let m: MediaQueryList | null = null;
    try {
      m = window.matchMedia('(max-width: 639px)');
    } catch {
      return;
    }
    const dinle = () => setDar(m!.matches);
    m.addEventListener?.('change', dinle);
    return () => m?.removeEventListener?.('change', dinle);
  }, []);

  const etkin: Gorunum = dar && (gorunum === 'ay' || gorunum === 'hafta') ? 'liste' : gorunum;
  const [bas, bit] = aralik(etkin, odak);

  const yukle = useCallback(async () => {
    setYukleniyor(true);
    try {
      setVeri(
        await api.gonderiler({
          bas: gunAnahtari(bas),
          bit: gunAnahtari(bit),
          tz,
          kanal: suzgec.kanal || undefined,
          kampanya: suzgec.kampanya || undefined,
          durum: suzgec.durum || undefined,
          tarihsiz: etkin === 'liste',
        })
      );
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setYukleniyor(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, gunAnahtari(bas), gunAnahtari(bit), tz, suzgec, etkin, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  // AI yazardan gelen taslak → yeni gönderi çekmecesi.
  useEffect(() => {
    if (taslak) {
      setCekmece({ gonderi: null, taslak });
      onTaslakKullanildi();
    }
  }, [taslak, onTaslakKullanildi]);

  // Bildirim bağlantısı (`?gonderi=`) ya da Onaylar sekmesinden açılacak gönderi.
  useEffect(() => {
    if (!acilacak) return;
    api
      .gonderi(acilacak)
      .then((g) => setCekmece({ gonderi: g }))
      .catch(() => undefined)
      .finally(onAcildi);
  }, [acilacak, api, onAcildi]);

  const gunler = useMemo(() => {
    const m = new Map<string, Gonderi[]>();
    for (const g of veri?.items ?? []) {
      if (!g.gun) continue;
      const l = m.get(g.gun) ?? [];
      l.push(g);
      m.set(g.gun, l);
    }
    return m;
  }, [veri]);

  const simdi = Date.now();
  const gecikenler = (veri?.items ?? []).filter((g) => g.planlanan_at && Date.parse(g.planlanan_at) < simdi && !BITMIS.includes(g.durum));
  const yazilabilir = (g: Gonderi) => meta.yonetici || g.yoneten === 'musteri';

  // Gecikenleri yöneticilere e-postayla bildir. Uç e-posta gitmese de 200 dönüyor; "gitti"
  // demeden önce kanal durumunu okuyoruz.
  const [hatirlatiliyor, setHatirlatiliyor] = useState(false);
  const hatirlat = async () => {
    setHatirlatiliyor(true);
    try {
      const s = await gecikenleriHatirlat();
      if (s.eposta_durumu === 'sent') toast.success(t('icerikStudyosu.plan.hatirlatildi', { sayi: s.alici_sayisi }));
      else toast.warning(t('icerikStudyosu.plan.hatirlatmaGitmedi', { ayrinti: s.eposta_ayrinti || s.eposta_durumu }));
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setHatirlatiliyor(false);
    }
  };

  const kaydir = (yon: number) => {
    const d = new Date(odak);
    if (etkin === 'ay' || etkin === 'liste') d.setMonth(d.getMonth() + yon, 1);
    else if (etkin === 'hafta') d.setDate(d.getDate() + 7 * yon);
    else d.setDate(d.getDate() + yon);
    setOdak(d);
  };

  const birak = async (e: DragEvent, gun: string) => {
    e.preventDefault();
    setHedefGun(null);
    const id = Number(e.dataTransfer.getData('text/plain')) || surukle;
    setSurukle(null);
    const g = veri?.items.find((x) => x.id === id);
    if (!g || !g.planlanan || !g.gun || g.gun === gun) return;
    const yeni = gunKaydir(g.planlanan, gunFarki(g.gun, gun));
    try {
      await api.gonderiGuncelle(g.id, { planlanan: yeni });
      toast.success(t('icerikStudyosu.plan.tasindi'));
      await yukle();
    } catch (err) {
      toast.error(hataMetni(t, err));
    }
  };

  const degisti = (g: Gonderi | null) => {
    void yukle();
    if (g && cekmece) setCekmece({ ...cekmece, gonderi: g });
  };

  const kart = (g: Gonderi) => (
    <TakvimKarti
      key={g.id}
      g={g}
      dil={dil}
      tz={tz}
      suruklenir={yazilabilir(g) && g.durum !== 'yayinlandi' && !!g.planlanan && !dar}
      surukleniyor={surukle === g.id}
      onBasla={() => setSurukle(g.id)}
      onBitir={() => {
        setSurukle(null);
        setHedefGun(null);
      }}
      onAc={() => setCekmece({ gonderi: g })}
    />
  );

  const hucre = (d: Date, digerAy = false, yukseklik = 'min-h-[96px]') => {
    const anahtar = gunAnahtari(d);
    const liste = gunler.get(anahtar) ?? [];
    const bugun = anahtar === gunAnahtari(new Date());
    return (
      <div
        key={anahtar}
        className={`group/hucre ${yukseklik} min-w-0 rounded-lg border p-1 ${hedefGun === anahtar ? 'border-fuchsia-400 bg-fuchsia-500/10' : 'border-white/5'} ${
          digerAy ? 'opacity-50' : ''
        }`}
        onDragOver={(e) => {
          e.preventDefault();
          e.dataTransfer.dropEffect = 'move';
          if (hedefGun !== anahtar) setHedefGun(anahtar);
        }}
        onDragLeave={() => setHedefGun((h) => (h === anahtar ? null : h))}
        onDrop={(e) => birak(e, anahtar)}
        data-is-gun={anahtar}
      >
        <div className="mb-0.5 flex items-center justify-between">
          <span className={`text-[11px] tabular-nums ${bugun ? 'rounded bg-fuchsia-500/30 px-1 text-white' : 'text-muted-foreground'}`}>{d.getDate()}</span>
          {!dar && (
            <button type="button" className="rounded p-0.5 text-muted-foreground opacity-0 hover:bg-white/10 hover:text-white focus:opacity-100 group-hover/hucre:opacity-100"
              onClick={() => setCekmece({ gonderi: null, gun: anahtar })} aria-label={t('icerikStudyosu.plan.buGuneEkle')}>
              <Plus className="h-3 w-3" aria-hidden="true" />
            </button>
          )}
        </div>
        <div className="space-y-0.5">
          {liste.map(kart)}
        </div>
      </div>
    );
  };

  const gunAdlari = useMemo(() => {
    const b = haftaBasi(new Date(2026, 0, 5));
    return Array.from({ length: 7 }, (_, i) => new Intl.DateTimeFormat(dil, { weekday: 'short' }).format(gunEkle(b, i)));
  }, [dil]);

  const baslik = (() => {
    try {
      if (etkin === 'ay' || etkin === 'liste') return new Intl.DateTimeFormat(dil, { month: 'long', year: 'numeric' }).format(odak);
      if (etkin === 'hafta') return `${new Intl.DateTimeFormat(dil, { day: 'numeric', month: 'short' }).format(bas)} – ${new Intl.DateTimeFormat(dil, { day: 'numeric', month: 'short', year: 'numeric' }).format(bit)}`;
      return new Intl.DateTimeFormat(dil, { weekday: 'long', day: 'numeric', month: 'long' }).format(odak);
    } catch {
      return gunAnahtari(odak);
    }
  })();

  const listeGruplari = useMemo(() => {
    const gruplar: { anahtar: string; items: Gonderi[] }[] = [];
    const tarihsiz = (veri?.items ?? []).filter((g) => !g.gun);
    const sirali = (veri?.items ?? []).filter((g) => g.gun).sort((a, b) => (a.planlanan_at || '').localeCompare(b.planlanan_at || ''));
    for (const g of sirali) {
      const son = gruplar[gruplar.length - 1];
      if (son && son.anahtar === g.gun) son.items.push(g);
      else gruplar.push({ anahtar: g.gun!, items: [g] });
    }
    if (tarihsiz.length) gruplar.push({ anahtar: '', items: tarihsiz });
    return gruplar;
  }, [veri]);

  const GORUNUMLER: { anahtar: Gorunum; ikon: typeof List; masaustu?: boolean }[] = [
    { anahtar: 'ay', ikon: CalendarDays, masaustu: true },
    { anahtar: 'hafta', ikon: CalendarRange, masaustu: true },
    { anahtar: 'gun', ikon: Sun },
    { anahtar: 'liste', ikon: List },
  ];

  return (
    <div className="space-y-4" data-testid="is-planlayici" data-gorunum={etkin}>
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex rounded-lg border border-white/10 p-0.5" role="group" aria-label={t('icerikStudyosu.plan.gorunum')}>
            {GORUNUMLER.map(({ anahtar, ikon: Ikon, masaustu }) => (
              <button
                key={anahtar}
                type="button"
                onClick={() => setGorunum(anahtar)}
                aria-pressed={etkin === anahtar}
                data-is-gorunum={anahtar}
                className={`${masaustu ? 'hidden sm:inline-flex' : 'inline-flex'} items-center gap-1 rounded-md px-2.5 py-1.5 text-xs ${
                  etkin === anahtar ? 'bg-white/10 text-white' : 'text-muted-foreground hover:text-white'
                }`}
              >
                <Ikon className="h-3.5 w-3.5" aria-hidden="true" />
                {t(`icerikStudyosu.plan.gorunumler.${anahtar}`)}
              </button>
            ))}
          </div>
          <div className="inline-flex items-center gap-1">
            <button type="button" className="rounded-md p-1.5 hover:bg-white/10" onClick={() => kaydir(-1)} aria-label={t('icerikStudyosu.plan.onceki')} data-testid="is-onceki">
              <ChevronLeft className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
            </button>
            <button type="button" className="rounded-md px-2 py-1 text-xs hover:bg-white/10" onClick={() => setOdak(new Date())}>
              {t('icerikStudyosu.plan.bugun')}
            </button>
            <button type="button" className="rounded-md p-1.5 hover:bg-white/10" onClick={() => kaydir(1)} aria-label={t('icerikStudyosu.plan.sonraki')} data-testid="is-sonraki">
              <ChevronRight className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
            </button>
            <span className="ms-1 text-sm font-medium capitalize" data-testid="is-donem">{baslik}</span>
            {yukleniyor && <Loader2 className="ms-1 h-3.5 w-3.5 animate-spin text-muted-foreground" aria-hidden="true" />}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" size="sm" className={DIS_DUGME}
            onClick={() => api.csvIndir({ bas: gunAnahtari(bas), bit: gunAnahtari(bit), tz, ...Object.fromEntries(Object.entries(suzgec).filter(([, v]) => v)) }).catch((e) => toast.error(hataMetni(t, e)))}
            data-testid="is-csv">
            <Download className="h-3.5 w-3.5" aria-hidden="true" />
            {t('icerikStudyosu.plan.csv')}
          </Button>
          <Button type="button" size="sm" className="gap-1.5" onClick={() => setCekmece({ gonderi: null, gun: etkin === 'gun' ? gunAnahtari(odak) : null })} data-testid="is-yeni-gonderi">
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('icerikStudyosu.plan.yeni')}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        <select className={SECIM} value={suzgec.kanal} onChange={(e) => setSuzgec((s) => ({ ...s, kanal: e.target.value }))} aria-label={t('icerikStudyosu.plan.kanal')} data-testid="is-suzgec-kanal">
          <option value="">{t('icerikStudyosu.plan.tumKanallar')}</option>
          {meta.kanallar.map((k) => (
            <option key={k} value={k}>
              {t(`icerikOnay.kanal.${k}`)}
            </option>
          ))}
        </select>
        <select className={SECIM} value={suzgec.kampanya} onChange={(e) => setSuzgec((s) => ({ ...s, kampanya: e.target.value }))} aria-label={t('icerikStudyosu.plan.kampanya')} data-testid="is-suzgec-kampanya">
          <option value="">{t('icerikStudyosu.plan.tumKampanyalar')}</option>
          {[...new Set([...(veri?.kampanyalar ?? []), ...(suzgec.kampanya ? [suzgec.kampanya] : [])])].map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
        <select className={SECIM} value={suzgec.durum} onChange={(e) => setSuzgec((s) => ({ ...s, durum: e.target.value }))} aria-label={t('icerikStudyosu.plan.durum')}>
          <option value="">{t('icerikStudyosu.plan.tumDurumlar')}</option>
          {meta.durumlar.map((d) => (
            <option key={d} value={d}>
              {t(`icerikOnay.durum.${d}`)}
            </option>
          ))}
        </select>
      </div>

      {gecikenler.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-sm text-amber-100" data-testid="is-geciken">
          <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span className="min-w-0 flex-1">{t('icerikStudyosu.plan.geciken', { sayi: gecikenler.length })}</span>
          {meta.yonetici && (
            <Button type="button" size="sm" variant="outline" className={DIS_DUGME} onClick={hatirlat} disabled={hatirlatiliyor} data-testid="is-geciken-hatirlat">
              {hatirlatiliyor ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Mail className="h-3.5 w-3.5" aria-hidden="true" />}
              {t('icerikStudyosu.plan.hatirlat')}
            </Button>
          )}
        </div>
      )}

      {!veri ? (
        <Yukleniyor />
      ) : etkin === 'ay' ? (
        <div className={`${KART} p-2`} data-testid="is-takvim-ay">
          <div className="mb-1 grid grid-cols-7 gap-1 text-center text-[11px] text-muted-foreground">
            {gunAdlari.map((g) => (
              <span key={g}>{g}</span>
            ))}
          </div>
          <div className="grid grid-cols-7 gap-1">
            {Array.from({ length: 42 }, (_, i) => gunEkle(bas, i)).map((d) => hucre(d, d.getMonth() !== odak.getMonth()))}
          </div>
        </div>
      ) : etkin === 'hafta' ? (
        <div className={`${KART} p-2`} data-testid="is-takvim-hafta">
          <div className="grid grid-cols-7 gap-1">
            {Array.from({ length: 7 }, (_, i) => gunEkle(bas, i)).map((d, i) => (
              <div key={i} className="min-w-0">
                <p className="mb-1 text-center text-[11px] text-muted-foreground">{gunAdlari[i]}</p>
                {hucre(d, false, 'min-h-[280px]')}
              </div>
            ))}
          </div>
        </div>
      ) : etkin === 'gun' ? (
        <div className={`${KART} p-3`} data-testid="is-takvim-gun">
          {(gunler.get(gunAnahtari(odak)) ?? []).length === 0 ? (
            <Bos>{t('icerikStudyosu.plan.gunBos')}</Bos>
          ) : (
            <div className="space-y-2">
              {(gunler.get(gunAnahtari(odak)) ?? []).map((g) => (
                <SatirKarti key={g.id} g={g} tz={tz} dil={dil} onAc={() => setCekmece({ gonderi: g })} />
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-4" data-testid="is-liste">
          {listeGruplari.length === 0 && <Bos testid="is-liste-bos">{t('icerikStudyosu.plan.bos')}</Bos>}
          {listeGruplari.map((grup) => (
            <section key={grup.anahtar || 'tarihsiz'}>
              <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {grup.anahtar
                  ? new Intl.DateTimeFormat(dil, { weekday: 'long', day: 'numeric', month: 'long' }).format(new Date(`${grup.anahtar}T12:00:00`))
                  : t('icerikStudyosu.plan.tarihsiz')}
              </h4>
              <div className="space-y-2">
                {grup.items.map((g) => (
                  <SatirKarti key={g.id} g={g} tz={tz} dil={dil} onAc={() => setCekmece({ gonderi: g })} />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
      <p className="text-[11px] text-muted-foreground">{t('icerikStudyosu.plan.saatDilimiNotu', { tz })}</p>

      {cekmece && (
        <GonderiCekmecesi
          key={cekmece.gonderi?.id ?? 'yeni'}
          api={api}
          meta={meta}
          gonderi={cekmece.gonderi}
          taslak={cekmece.taslak ?? null}
          gun={cekmece.gun}
          kampanyalar={veri?.kampanyalar ?? []}
          varsayilanTz={tz}
          onKapat={() => setCekmece(null)}
          onDegisti={degisti}
          onPaket={(id) => setPaketId(id)}
        />
      )}
      {paketId && (
        <PaylasimPaketi
          api={api}
          gonderiId={paketId}
          yazilabilir={!!veri?.items.find((x) => x.id === paketId && yazilabilir(x)) || meta.yonetici}
          onKapat={() => setPaketId(null)}
          onDegisti={() => void yukle()}
        />
      )}
    </div>
  );
}

function TakvimKarti({
  g,
  dil,
  tz,
  suruklenir,
  surukleniyor,
  onBasla,
  onBitir,
  onAc,
}: {
  g: Gonderi;
  dil: string;
  tz: string;
  suruklenir: boolean;
  surukleniyor: boolean;
  onBasla: () => void;
  onBitir: () => void;
  onAc: () => void;
}) {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      draggable={suruklenir}
      onDragStart={(e) => {
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', String(g.id));
        onBasla();
      }}
      onDragEnd={onBitir}
      onClick={onAc}
      data-is-gonderi={g.id}
      data-durum={g.durum}
      className={`flex w-full min-w-0 items-start gap-1 rounded-md border-s-2 px-1.5 py-1 text-start text-[11px] leading-tight hover:bg-white/10 ${
        DURUM_RENGI[g.durum] ?? ''
      } ${surukleniyor ? 'opacity-40' : ''}`}
      title={`${g.baslik} — ${t(`icerikOnay.durum.${g.durum}`)}`}
    >
      {suruklenir && <GripVertical className="mt-px h-3 w-3 shrink-0 opacity-50" aria-hidden="true" />}
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-0.5 opacity-80">
          <span className="tabular-nums">{saatYaz(g.planlanan_at, dil, tz)}</span>
          {g.kanallar.slice(0, 3).map((k) => (
            <KanalIkonu key={k} kanal={k} className="h-3 w-3" />
          ))}
          {g.kanallar.length > 3 && <span>+{g.kanallar.length - 3}</span>}
        </span>
        <span className="block truncate font-medium">{g.baslik}</span>
      </span>
    </button>
  );
}

function SatirKarti({ g, tz, dil, onAc }: { g: Gonderi; tz: string; dil: string; onAc: () => void }) {
  const { t } = useTranslation();
  return (
    <button type="button" onClick={onAc} className={`${KART} flex w-full min-w-0 flex-col gap-1.5 p-3 text-start hover:bg-white/[0.06] sm:flex-row sm:items-center`} data-is-gonderi={g.id} data-durum={g.durum}>
      <span className="w-24 shrink-0 text-xs tabular-nums text-muted-foreground">{g.planlanan_at ? saatYaz(g.planlanan_at, dil, tz) : '—'}</span>
      <span className="min-w-0 flex-1">
        <span className="block truncate font-medium">{g.baslik}</span>
        <span className="mt-0.5 flex flex-wrap items-center gap-1 text-[11px] text-muted-foreground">
          {g.kanallar.map((k) => (
            <KanalIkonu key={k} kanal={k} className="h-3 w-3" />
          ))}
          {g.kampanya && <span>· {g.kampanya}</span>}
          {g.planlanan_at && <span className="sm:hidden">· {tarihSaatYaz(g.planlanan_at, dil, tz)}</span>}
          {g.uyarilar.length > 0 && <AlertTriangle className="h-3 w-3 text-amber-300" aria-label={t('icerikStudyosu.uyariVar')} />}
        </span>
      </span>
      <DurumRozeti durum={g.durum} />
    </button>
  );
}
