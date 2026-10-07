import { lazy, Suspense, useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Lock, Plus, Search } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { DURUM_RENGI, GIRDI, KART, Rozet, SECIM, Yukleniyor } from '@/components/hukuk/ortak';
import { gunYaz, hataMetni, type Dosya, type HukukApi, type Meta, type Muvekkil } from '@/lib/hukuk';

const DosyaDetay = lazy(() => import('@/components/hukuk/DosyaDetay'));

/** Faz 6H — dosyalar: liste (durum/sorumlu/arama), yeni dosya, dosya çalışma alanı. Gizli dosya yalnız yetkiliye gelir. */
export default function Dosyalar({
  api,
  meta,
  acilacak,
  onAcildi,
  onDegisti,
}: {
  api: HukukApi;
  meta: Meta;
  acilacak: number | null;
  onAcildi: () => void;
  onDegisti: () => void;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [liste, setListe] = useState<Dosya[] | null>(null);
  const [muvekkiller, setMuvekkiller] = useState<Muvekkil[]>([]);
  const [durum, setDurum] = useState('');
  const [sorumlu, setSorumlu] = useState('');
  const [q, setQ] = useState('');
  const [seciliId, setSeciliId] = useState<number | null>(acilacak);
  const [yeniMuvekkil, setYeniMuvekkil] = useState('');
  const [yeniKonu, setYeniKonu] = useState('');
  const [yeniTur, setYeniTur] = useState('dava');

  const yukle = useCallback(async () => {
    try {
      setListe((await api.dosyalar({ durum: durum || undefined, sorumlu: sorumlu || undefined, q: q.trim() || undefined })).items);
    } catch (e) {
      toast.error(hataMetni(t, e));
      setListe([]);
    }
  }, [api, durum, sorumlu, q, t]);

  useEffect(() => {
    if (seciliId === null) void yukle();
  }, [yukle, seciliId]);

  useEffect(() => {
    api
      .muvekkiller()
      .then((r) => setMuvekkiller(r.items))
      .catch(() => setMuvekkiller([]));
  }, [api]);

  useEffect(() => {
    if (acilacak !== null) {
      setSeciliId(acilacak);
      onAcildi();
    }
  }, [acilacak, onAcildi]);

  const olustur = async () => {
    if (!yeniMuvekkil) {
      toast.error(t('hukuk.dosya.muvekkilSec'));
      return;
    }
    try {
      const r = await api.dosyaEkle({ muvekkil_id: Number(yeniMuvekkil), konu: yeniKonu.trim(), tur: yeniTur as Dosya['tur'] });
      toast.success(t('hukuk.ortak.kaydedildi'));
      setYeniKonu('');
      onDegisti();
      setSeciliId(r.dosya.id);
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  if (seciliId !== null) {
    return (
      <Suspense fallback={<Yukleniyor />}>
        <DosyaDetay
          api={api}
          meta={meta}
          id={seciliId}
          onKapat={() => {
            setSeciliId(null);
            onDegisti();
          }}
        />
      </Suspense>
    );
  }

  const sinirDolu = meta.dosya_siniri != null && meta.acik_dosya_sayisi >= meta.dosya_siniri;
  return (
    <div className="space-y-4" data-testid="hukuk-dosyalar">
      <div className={`${KART} p-4 sm:p-6`}>
        <h3 className="mb-3 text-base font-semibold">{t('hukuk.dosya.yeni')}</h3>
        {muvekkiller.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('hukuk.dosya.once')}</p>
        ) : (
          <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,160px)_minmax(0,1fr)_auto] sm:items-end">
            <label className="block text-sm">
              <span className="mb-1 block text-muted-foreground">{t('hukuk.dosya.alan.muvekkil')}</span>
              <select className={SECIM} value={yeniMuvekkil} onChange={(e) => setYeniMuvekkil(e.target.value)} data-testid="hukuk-dosya-yeni-muvekkil">
                <option value="">{t('hukuk.dosya.muvekkilSec')}</option>
                {muvekkiller.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.ad}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-muted-foreground">{t('hukuk.dosya.alan.tur')}</span>
              <select className={SECIM} value={yeniTur} onChange={(e) => setYeniTur(e.target.value)}>
                {meta.dosya_turleri.map((x) => (
                  <option key={x} value={x}>
                    {t(`hukuk.dosya.tur.${x}`)}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-muted-foreground">{t('hukuk.dosya.alan.konu')}</span>
              <input className={GIRDI} value={yeniKonu} maxLength={300} onChange={(e) => setYeniKonu(e.target.value)} data-testid="hukuk-dosya-yeni-konu" />
            </label>
            <Button onClick={() => void olustur()} disabled={sinirDolu} className="gap-1.5" data-testid="hukuk-dosya-yeni">
              <Plus className="h-4 w-4" aria-hidden="true" />
              {t('hukuk.ortak.ekle')}
            </Button>
          </div>
        )}
        {sinirDolu && <p className="mt-2 text-xs text-amber-200">{t('hukuk.dosya.sinirDolu', { sinir: meta.dosya_siniri })}</p>}
      </div>

      <div className={`${KART} p-4 sm:p-6`}>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <h3 className="me-auto text-base font-semibold">{t('hukuk.dosya.baslik')}</h3>
          <select className={`${SECIM} w-auto`} value={durum} onChange={(e) => setDurum(e.target.value)} aria-label={t('hukuk.dosya.alan.durum')} data-testid="hukuk-dosya-durum-filtre">
            <option value="">{t('hukuk.ortak.hepsi')}</option>
            {meta.dosya_durumlari.map((x) => (
              <option key={x} value={x}>
                {t(`hukuk.dosya.durum.${x}`)}
              </option>
            ))}
          </select>
          <select className={`${SECIM} w-auto max-w-[220px]`} value={sorumlu} onChange={(e) => setSorumlu(e.target.value)} aria-label={t('hukuk.dosya.alan.sorumlu')}>
            <option value="">{t('hukuk.dosya.alan.sorumlu')}: {t('hukuk.ortak.hepsi')}</option>
            {meta.ekip.map((k) => (
              <option key={k.eposta} value={k.eposta}>
                {k.eposta}
              </option>
            ))}
          </select>
          <div className="relative">
            <Search className="pointer-events-none absolute start-2 top-2.5 h-4 w-4 text-muted-foreground" aria-hidden="true" />
            <input className={`${GIRDI} w-48 ps-8`} value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('hukuk.ortak.ara')} aria-label={t('hukuk.ortak.ara')} />
          </div>
        </div>
        {liste === null ? (
          <Yukleniyor />
        ) : liste.length === 0 ? (
          <p className="py-10 text-center text-sm text-muted-foreground" data-testid="hukuk-dosya-bos">
            {t('hukuk.dosya.bos')}
          </p>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" data-testid="hukuk-dosya-liste">
            {liste.map((d) => (
              <li key={d.id}>
                <button
                  type="button"
                  onClick={() => setSeciliId(d.id)}
                  className="flex h-full w-full flex-col gap-1 rounded-xl border border-white/10 bg-black/20 p-3 text-start transition-colors hover:border-blue-400/40 hover:bg-white/[0.04]"
                  data-dosya-id={d.id}
                  data-testid="hukuk-dosya-ac"
                >
                  <span className="flex items-center gap-1.5">
                    {d.gizli && <Lock className="h-3.5 w-3.5 text-amber-300" aria-label={t('hukuk.dosya.gizliRozet')} />}
                    <span className="truncate font-medium">{d.baslik}</span>
                  </span>
                  <span className="truncate text-xs text-muted-foreground">{d.muvekkil_ad}</span>
                  {d.mahkeme && <span className="truncate text-[11px] text-muted-foreground">{d.mahkeme}</span>}
                  <span className="mt-1 flex flex-wrap items-center gap-1">
                    <Rozet renk={DURUM_RENGI[d.durum]}>{t(`hukuk.dosya.durum.${d.durum}`)}</Rozet>
                    <Rozet>{t(`hukuk.dosya.tur.${d.tur}`)}</Rozet>
                    {d.sonraki_olay && (
                      <Rozet renk={d.sonraki_olay.kalan_gun <= 3 ? 'border-rose-400/50 bg-rose-500/15 text-rose-100' : undefined}>
                        {t('hukuk.dosya.sonrakiOlay', { tur: t(`hukuk.olay.tur.${d.sonraki_olay.tur}`), tarih: gunYaz(d.sonraki_olay.tarih, dil) })}
                      </Rozet>
                    )}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
