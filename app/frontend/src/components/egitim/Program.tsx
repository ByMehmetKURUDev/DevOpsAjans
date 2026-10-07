import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CalendarDays, CalendarPlus, ChevronLeft, ChevronRight, Download, Expand, List, Loader2, QrCode, RefreshCw, ScanLine, Trash2, UserX, X } from 'lucide-react';
import { toast } from 'sonner';

import { Alan, DIS_DUGME, KART, Rozet, Yukleniyor } from '@/components/randevu/ortak';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  blobIndir,
  hataMetni,
  tarihSaat,
  yerelGun,
  yerelIso,
  type EgitimApi,
  type Kurs,
  type Oturum,
  type YoklamaDurumu,
  type YoklamaListesi,
} from '@/lib/egitim';

/**
 * Faz 6K — program ve yoklama. Tekrarlayan ders saatleri tek seferde üretilir (haftanın günleri × saat × tarih
 * aralığı), liste ya da aylık takvim görünümü, ICS. Oturum seçilince yoklama: sınıfta gösterilen QR (öğrenci
 * kendi telefon kamerasıyla okutur → kendi öğrenci bağlantısıyla "buradayım") ve tahtaya yazılan 6 haneli kod;
 * eğitmen öğrencinin QR'ını okutmak için okutucuyu açar (etkinlik kapı okutucusu yeniden kullanılıyor); elle
 * düzeltme (var / geç / yok / izinli) ve "gelmeyenleri yok işaretle".
 */

const YOKLAMA_RENK: Record<YoklamaDurumu, string> = {
  var: 'bg-emerald-600 text-white',
  gec: 'bg-amber-500 text-zinc-950',
  yok: 'bg-red-600 text-white',
  izinli: 'bg-sky-600 text-white',
};

function gunAdlari(dil: string): string[] {
  // 2024-01-01 Pazartesi.
  return Array.from({ length: 7 }, (_, i) => {
    try {
      return new Intl.DateTimeFormat(dil, { weekday: 'short', timeZone: 'UTC' }).format(new Date(Date.UTC(2024, 0, 1 + i)));
    } catch {
      return String(i);
    }
  });
}

function Takvim({ oturumlar, tz, dil, onSec }: { oturumlar: Oturum[]; tz: string; dil: string; onSec: (o: Oturum) => void }) {
  const { t } = useTranslation();
  const bugun = new Date();
  const [ay, setAy] = useState(() => {
    const ilk = oturumlar.find((o) => new Date(o.bitis) >= bugun) || oturumlar[0];
    const g = ilk ? yerelGun(ilk.baslangic, tz) : bugun.toISOString().slice(0, 10);
    return { y: Number(g.slice(0, 4)), a: Number(g.slice(5, 7)) - 1 };
  });
  const gunler = gunAdlari(dil);
  const ilkGun = new Date(Date.UTC(ay.y, ay.a, 1));
  const bosluk = (ilkGun.getUTCDay() + 6) % 7;
  const gunSayisi = new Date(Date.UTC(ay.y, ay.a + 1, 0)).getUTCDate();
  const gruplar = useMemo(() => {
    const m: Record<string, Oturum[]> = {};
    for (const o of oturumlar) (m[yerelGun(o.baslangic, tz)] ||= []).push(o);
    return m;
  }, [oturumlar, tz]);
  const ayAdi = new Intl.DateTimeFormat(dil, { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(ilkGun);
  const kaydir = (n: number) => setAy(({ y, a }) => ({ y: a + n < 0 ? y - 1 : a + n > 11 ? y + 1 : y, a: (a + n + 12) % 12 }));
  return (
    <div data-testid="egitim-takvim">
      <div className="mb-2 flex items-center justify-between">
        <Button size="icon" variant="ghost" aria-label={t('egitim.program.oncekiAy')} onClick={() => kaydir(-1)}>
          <ChevronLeft className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
        </Button>
        <span className="font-medium capitalize">{ayAdi}</span>
        <Button size="icon" variant="ghost" aria-label={t('egitim.program.sonrakiAy')} onClick={() => kaydir(1)}>
          <ChevronRight className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
        </Button>
      </div>
      <div className="grid grid-cols-7 gap-1 text-center text-[11px] text-muted-foreground">
        {gunler.map((g) => (
          <div key={g}>{g}</div>
        ))}
      </div>
      <div className="mt-1 grid grid-cols-7 gap-1">
        {Array.from({ length: bosluk }, (_, i) => (
          <div key={`b${i}`} />
        ))}
        {Array.from({ length: gunSayisi }, (_, i) => {
          const gun = `${ay.y}-${String(ay.a + 1).padStart(2, '0')}-${String(i + 1).padStart(2, '0')}`;
          const liste = gruplar[gun] || [];
          return (
            <div key={gun} className={`min-h-[3.5rem] rounded-md border p-1 text-start ${liste.length ? 'border-blue-400/30 bg-blue-500/10' : 'border-white/5'}`}>
              <div className="text-[10px] text-muted-foreground">{i + 1}</div>
              {liste.map((o) => (
                <button
                  key={o.id}
                  type="button"
                  onClick={() => onSec(o)}
                  className={`mt-0.5 block w-full truncate rounded px-1 text-start text-[10px] ${o.durum === 'iptal' ? 'bg-white/5 text-muted-foreground line-through' : 'bg-blue-500/30 text-white hover:bg-blue-500/50'}`}
                >
                  {tarihSaat(o.baslangic, tz, dil, { hour: '2-digit', minute: '2-digit' })}
                </button>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function YoklamaPaneli({ api, kurs, oturum, onKapat, onDegisti }: { api: EgitimApi; kurs: Kurs; oturum: Oturum; onKapat: () => void; onDegisti: () => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [v, setV] = useState<YoklamaListesi | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const [tamEkran, setTamEkran] = useState(false);
  const [mesgul, setMesgul] = useState(false);

  const yukle = useCallback(async () => {
    try {
      setV(await api.yoklama(kurs.id, oturum.id));
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  }, [api, kurs.id, oturum.id, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const kod = v?.yoklama.kod;
  useEffect(() => {
    if (!kod) return;
    let adres: string | null = null;
    let iptal = false;
    api
      .oturumQr(kurs.id, oturum.id)
      .then((b) => {
        if (iptal) return;
        adres = URL.createObjectURL(b);
        setQr(adres);
      })
      .catch(() => undefined);
    return () => {
      iptal = true;
      if (adres) URL.revokeObjectURL(adres);
    };
  }, [api, kurs.id, oturum.id, kod]);

  // Yoklama açıkken liste 15 sn'de bir tazelenir (öğrenciler QR'ı okuttukça).
  useEffect(() => {
    if (!v?.yoklama.acik) return;
    const z = window.setInterval(() => {
      if (document.visibilityState === 'visible') void yukle();
    }, 15000);
    return () => window.clearInterval(z);
  }, [v?.yoklama.acik, yukle]);

  const isaretle = async (ogid: number, durum: YoklamaDurumu | null) => {
    try {
      await api.yoklamaDuzelt(kurs.id, oturum.id, ogid, durum);
      await yukle();
      onDegisti();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const yenile = async () => {
    if (!window.confirm(t('egitim.yoklama.yenileOnay'))) return;
    try {
      await api.qrYenile(kurs.id, oturum.id);
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const kapat = async () => {
    setMesgul(true);
    try {
      const s = await api.yoklamaKapat(kurs.id, oturum.id);
      toast.success(t('egitim.yoklama.yokIsaretlendi', { sayi: s.yok }));
      await yukle();
      onDegisti();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  if (!v) return <Yukleniyor />;
  const katilan = v.items.filter((x) => x.durum === 'var' || x.durum === 'gec').length;
  return (
    <div className={`${KART} grid gap-4 p-4 sm:p-6`} data-testid="egitim-yoklama" data-oturum-id={oturum.id}>
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="text-base font-semibold">{t('egitim.yoklama.baslik')}</h4>
        <span className="text-sm text-muted-foreground">{tarihSaat(oturum.baslangic, kurs.saat_dilimi, dil)}</span>
        <Rozet renk={v.yoklama.acik ? 'border-emerald-400/40 bg-emerald-500/15 text-emerald-200' : undefined}>
          {v.yoklama.acik ? t('egitim.yoklama.acik') : t('egitim.yoklama.kapali')}
        </Rozet>
        <span className="flex-1" />
        <Button size="sm" variant="ghost" className="gap-1" onClick={onKapat}>
          <X className="h-4 w-4" aria-hidden="true" />
          {t('egitim.kapat')}
        </Button>
      </div>
      <div className="grid gap-4 md:grid-cols-[14rem_minmax(0,1fr)]">
        <div className="flex flex-col items-center gap-2 rounded-xl border border-white/10 bg-white p-3 text-center text-zinc-900">
          {qr ? <img src={qr} alt={t('egitim.yoklama.qrAlt')} width={192} height={192} className="h-48 w-48" data-testid="egitim-yoklama-qr" /> : <Loader2 className="h-8 w-8 animate-spin" aria-hidden="true" />}
          <span className="text-xs text-zinc-500">{t('egitim.yoklama.kod')}</span>
          <code className="text-2xl font-extrabold tracking-[0.3em]" dir="ltr" data-testid="egitim-yoklama-kod">
            {v.yoklama.kod}
          </code>
        </div>
        <div className="grid content-start gap-2 text-sm">
          <p className="text-muted-foreground">{t('egitim.yoklama.ipucu')}</p>
          <p className="text-xs text-muted-foreground">
            {t('egitim.yoklama.pencere', { bas: tarihSaat(v.yoklama.pencere_bas, kurs.saat_dilimi, dil, { timeStyle: 'short' }), bit: tarihSaat(v.yoklama.pencere_bit, kurs.saat_dilimi, dil, { timeStyle: 'short' }) })}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => setTamEkran(true)} data-testid="egitim-yoklama-tam-ekran">
              <Expand className="h-4 w-4" aria-hidden="true" />
              {t('egitim.yoklama.tamEkran')}
            </Button>
            <a
              href={`/egitim/okut/${kurs.id}/${oturum.id}?mod=${api.mod}`}
              target="_blank"
              rel="noopener"
              className="inline-flex h-9 items-center gap-1.5 rounded-md bg-blue-600 px-3 text-sm font-medium text-white hover:bg-blue-500"
              data-testid="egitim-okutucu-ac"
            >
              <ScanLine className="h-4 w-4" aria-hidden="true" />
              {t('egitim.yoklama.okutucu')}
            </a>
            <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => void yenile()}>
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              {t('egitim.yoklama.qrYenile')}
            </Button>
          </div>
          <p className="font-medium" data-testid="egitim-yoklama-sayac">
            {t('egitim.yoklama.sayac', { sayi: katilan, toplam: v.items.length })}
          </p>
        </div>
      </div>
      <ul className="divide-y divide-white/5">
        {v.items.map((o) => (
          <li key={o.id} className="flex flex-wrap items-center gap-2 py-2" data-ogrenci-id={o.id} data-yoklama={o.durum || ''}>
            <span className="min-w-0 flex-1 truncate">{o.ad}</span>
            {o.kaynak && o.zaman && (
              <span className="text-[11px] text-muted-foreground">
                {t(`egitim.yoklamaKaynak.${o.kaynak}`)} · {tarihSaat(o.zaman, kurs.saat_dilimi, dil, { timeStyle: 'short' })}
              </span>
            )}
            <div className="flex gap-1" role="group" aria-label={o.ad}>
              {(['var', 'gec', 'yok', 'izinli'] as const).map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => void isaretle(o.id, o.durum === d ? null : d)}
                  aria-pressed={o.durum === d}
                  className={`rounded-md px-2 py-1 text-xs transition-colors ${o.durum === d ? YOKLAMA_RENK[d] : 'bg-white/[0.05] text-muted-foreground hover:bg-white/10'}`}
                  data-yoklama-dugme={d}
                >
                  {t(`egitim.yoklamaDurum.${d}`)}
                </button>
              ))}
            </div>
          </li>
        ))}
      </ul>
      {v.items.length > 0 && (
        <Button size="sm" variant="outline" className={`${DIS_DUGME} w-fit`} onClick={() => void kapat()} disabled={mesgul}>
          <UserX className="h-4 w-4" aria-hidden="true" />
          {t('egitim.yoklama.gelmeyenler')}
        </Button>
      )}
      {tamEkran && (
        <div className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-6 bg-white p-6 text-zinc-900" role="dialog" aria-modal="true" aria-label={t('egitim.yoklama.tamEkran')}>
          <button type="button" onClick={() => setTamEkran(false)} className="absolute end-4 top-4 rounded-full bg-zinc-100 p-2 hover:bg-zinc-200" aria-label={t('egitim.kapat')}>
            <X className="h-6 w-6" aria-hidden="true" />
          </button>
          <h2 className="text-center text-2xl font-bold">{kurs.ad}</h2>
          {qr && <img src={qr} alt={t('egitim.yoklama.qrAlt')} className="h-[min(60vh,80vw)] w-[min(60vh,80vw)]" />}
          <p className="text-center text-lg">{t('egitim.yoklama.tamEkranIpucu')}</p>
          <code className="text-5xl font-extrabold tracking-[0.3em]" dir="ltr">
            {v.yoklama.kod}
          </code>
        </div>
      )}
    </div>
  );
}

export default function Program({ api, kurs, yonetim }: { api: EgitimApi; kurs: Kurs; yonetim: boolean }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const tz = kurs.saat_dilimi;
  const [oturumlar, setOturumlar] = useState<Oturum[] | null>(null);
  const [aktif, setAktif] = useState(0);
  const [gorunum, setGorunum] = useState<'liste' | 'takvim'>('liste');
  const [secili, setSecili] = useState<Oturum | null>(null);
  const bugun = new Date().toISOString().slice(0, 10);
  const [uret, setUret] = useState({ bas: kurs.baslangic_tarihi || bugun, bit: kurs.bitis_tarihi || '', gunler: [] as number[], saat: '19:00', sure: '90', konu: '' });
  const [tek, setTek] = useState({ bas: '', sure: '90', konu: '' });
  const [mesgul, setMesgul] = useState(false);
  const gunler = gunAdlari(dil);

  const yukle = useCallback(async () => {
    try {
      const g = await api.oturumlar(kurs.id);
      setOturumlar(g.items);
      setAktif(g.aktif_ogrenci);
    } catch (e) {
      toast.error(hataMetni(t, e));
      setOturumlar([]);
    }
  }, [api, kurs.id, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const uretGonder = async () => {
    setMesgul(true);
    try {
      const s = await api.oturumUret(kurs.id, { bas_tarih: uret.bas, bit_tarih: uret.bit, gunler: uret.gunler, saat: uret.saat, sure_dk: Number(uret.sure), konu: uret.konu });
      toast.success(t('egitim.program.uretildi', { sayi: s.eklenen, atlanan: s.atlanan }));
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  const tekEkle = async () => {
    const bas = yerelIso(tek.bas, tz);
    if (!bas) {
      toast.error(t('egitim.hata.zorunlu'));
      return;
    }
    setMesgul(true);
    try {
      const bit = new Date(new Date(bas).getTime() + Number(tek.sure || 60) * 60000).toISOString().replace('.000Z', 'Z');
      await api.oturumEkle(kurs.id, { baslangic: bas, bitis: bit, konu: tek.konu });
      toast.success(t('egitim.program.eklendi'));
      setTek({ bas: '', sure: tek.sure, konu: '' });
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  const iptalEt = async (o: Oturum) => {
    try {
      await api.oturumGuncelle(kurs.id, o.id, { durum: o.durum === 'iptal' ? 'planli' : 'iptal' });
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const sil = async (o: Oturum) => {
    if (!window.confirm(t('egitim.program.silOnay'))) return;
    try {
      await api.oturumSil(kurs.id, o.id);
      if (secili?.id === o.id) setSecili(null);
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const icsIndir = async () => {
    try {
      blobIndir(await api.takvimBlob(kurs.id), `${kurs.slug}.ics`);
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  return (
    <div className="grid gap-4" data-testid="egitim-program">
      {yonetim && (
        <div className={`${KART} grid gap-3 p-4 sm:p-6`}>
          <h4 className="flex items-center gap-2 text-base font-semibold">
            <CalendarPlus className="h-4 w-4 text-blue-300" aria-hidden="true" />
            {t('egitim.program.uretBaslik')}
          </h4>
          <p className="text-sm text-muted-foreground">{t('egitim.program.uretIpucu')}</p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Alan etiket={t('egitim.program.basTarih')}>
              <Input type="date" value={uret.bas} onChange={(e) => setUret({ ...uret, bas: e.target.value })} data-testid="egitim-uret-bas" />
            </Alan>
            <Alan etiket={t('egitim.program.bitTarih')}>
              <Input type="date" value={uret.bit} onChange={(e) => setUret({ ...uret, bit: e.target.value })} data-testid="egitim-uret-bit" />
            </Alan>
            <Alan etiket={t('egitim.program.saat')}>
              <Input type="time" value={uret.saat} onChange={(e) => setUret({ ...uret, saat: e.target.value })} data-testid="egitim-uret-saat" />
            </Alan>
            <Alan etiket={t('egitim.program.sureDk')}>
              <Input type="number" min={10} max={720} value={uret.sure} onChange={(e) => setUret({ ...uret, sure: e.target.value })} />
            </Alan>
          </div>
          <fieldset>
            <legend className="mb-1 text-sm font-medium text-white/90">{t('egitim.program.gunler')}</legend>
            <div className="flex flex-wrap gap-1">
              {gunler.map((g, i) => {
                const secildi = uret.gunler.includes(i);
                return (
                  <button
                    key={i}
                    type="button"
                    aria-pressed={secildi}
                    onClick={() => setUret({ ...uret, gunler: secildi ? uret.gunler.filter((x) => x !== i) : [...uret.gunler, i].sort() })}
                    className={`rounded-md px-3 py-1.5 text-sm ${secildi ? 'bg-blue-600 text-white' : 'bg-white/[0.05] text-muted-foreground hover:bg-white/10'}`}
                    data-gun={i}
                  >
                    {g}
                  </button>
                );
              })}
            </div>
          </fieldset>
          <div className="flex flex-wrap items-end gap-2">
            <Alan etiket={t('egitim.program.konu')} className="min-w-[12rem] flex-1">
              <Input value={uret.konu} onChange={(e) => setUret({ ...uret, konu: e.target.value })} maxLength={160} />
            </Alan>
            <Button onClick={() => void uretGonder()} disabled={mesgul || !uret.bas || !uret.bit || !uret.gunler.length} className="gap-1.5" data-testid="egitim-uret">
              {mesgul ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <CalendarDays className="h-4 w-4" aria-hidden="true" />}
              {t('egitim.program.uret')}
            </Button>
          </div>
          <details className="text-sm">
            <summary className="cursor-pointer text-muted-foreground">{t('egitim.program.tekBaslik')}</summary>
            <div className="mt-2 flex flex-wrap items-end gap-2">
              <Alan etiket={t('egitim.program.baslangic')}>
                <Input type="datetime-local" value={tek.bas} onChange={(e) => setTek({ ...tek, bas: e.target.value })} data-testid="egitim-tek-bas" />
              </Alan>
              <Alan etiket={t('egitim.program.sureDk')}>
                <Input type="number" min={10} max={720} value={tek.sure} onChange={(e) => setTek({ ...tek, sure: e.target.value })} className="w-24" />
              </Alan>
              <Alan etiket={t('egitim.program.konu')} className="min-w-[10rem] flex-1">
                <Input value={tek.konu} onChange={(e) => setTek({ ...tek, konu: e.target.value })} maxLength={160} />
              </Alan>
              <Button onClick={() => void tekEkle()} disabled={mesgul || !tek.bas} variant="outline" className={DIS_DUGME} data-testid="egitim-tek-ekle">
                {t('egitim.ekle')}
              </Button>
            </div>
          </details>
        </div>
      )}

      {secili && (
        <YoklamaPaneli
          api={api}
          kurs={kurs}
          oturum={secili}
          onKapat={() => setSecili(null)}
          onDegisti={() => void yukle()}
        />
      )}

      <div className={`${KART} p-4 sm:p-6`}>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <h4 className="text-base font-semibold">{t('egitim.program.baslik')}</h4>
          <span className="text-xs text-muted-foreground">{t('egitim.program.ozet', { sayi: oturumlar?.length ?? 0, ogrenci: aktif })}</span>
          <span className="flex-1" />
          <div className="flex gap-1" role="tablist" aria-label={t('egitim.program.gorunum')}>
            <Button size="sm" variant={gorunum === 'liste' ? 'secondary' : 'ghost'} className="gap-1" onClick={() => setGorunum('liste')} aria-pressed={gorunum === 'liste'}>
              <List className="h-4 w-4" aria-hidden="true" />
              {t('egitim.program.liste')}
            </Button>
            <Button size="sm" variant={gorunum === 'takvim' ? 'secondary' : 'ghost'} className="gap-1" onClick={() => setGorunum('takvim')} aria-pressed={gorunum === 'takvim'} data-testid="egitim-takvim-ac">
              <CalendarDays className="h-4 w-4" aria-hidden="true" />
              {t('egitim.program.takvim')}
            </Button>
          </div>
          <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => void icsIndir()}>
            <Download className="h-4 w-4" aria-hidden="true" />
            ICS
          </Button>
        </div>
        {oturumlar === null ? (
          <Yukleniyor />
        ) : oturumlar.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground" data-testid="egitim-program-bos">
            {t('egitim.program.bos')}
          </p>
        ) : gorunum === 'takvim' ? (
          <Takvim oturumlar={oturumlar} tz={tz} dil={dil} onSec={setSecili} />
        ) : (
          <ul className="divide-y divide-white/5" data-testid="egitim-oturum-liste">
            {oturumlar.map((o) => (
              <li key={o.id} className="flex flex-wrap items-center gap-2 py-2" data-oturum-id={o.id}>
                <span className={`min-w-0 flex-1 ${o.durum === 'iptal' ? 'text-muted-foreground line-through' : ''}`}>
                  <span className="block text-sm">{tarihSaat(o.baslangic, tz, dil, { dateStyle: 'full', timeStyle: 'short' })}</span>
                  {o.konu && <span className="block text-xs text-muted-foreground">{o.konu}</span>}
                </span>
                {o.yoklama_acik && <Rozet renk="border-emerald-400/40 bg-emerald-500/15 text-emerald-200">{t('egitim.yoklama.acik')}</Rozet>}
                <Rozet>{t('egitim.program.katilan', { sayi: o.katilan ?? 0, toplam: aktif })}</Rozet>
                <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => setSecili(o)} disabled={o.durum === 'iptal'} data-testid="egitim-yoklama-ac">
                  <QrCode className="h-4 w-4" aria-hidden="true" />
                  {t('egitim.yoklama.baslik')}
                </Button>
                {yonetim && (
                  <>
                    <Button size="sm" variant="ghost" onClick={() => void iptalEt(o)}>
                      {o.durum === 'iptal' ? t('egitim.program.geriAl') : t('egitim.program.iptal')}
                    </Button>
                    <Button size="icon" variant="ghost" className="h-8 w-8 text-red-300" aria-label={t('egitim.sil')} onClick={() => void sil(o)}>
                      <Trash2 className="h-4 w-4" aria-hidden="true" />
                    </Button>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
