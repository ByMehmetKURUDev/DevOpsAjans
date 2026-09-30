import { useCallback, useEffect, useState } from 'react';
import { Bug, ExternalLink, Image as ImageIcon, Loader2, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  GERI_BILDIRIM_DURUMLARI,
  GERI_BILDIRIM_TURLERI,
  ONCELIKLER,
  ProjeHatasi,
  ekAdresi,
  geriBildirimGuncelle,
  geriBildirimListesi,
  goreveDonustur,
  tarihGoster,
  type GeriBildirim,
  type GeriBildirimDurumu,
  type Oncelik,
} from '@/lib/projeYonetimi';

const SECIM =
  'h-9 rounded-md border border-white/10 bg-white/5 px-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-purple-500/40';

const DURUM_RENGI: Record<GeriBildirimDurumu, string> = {
  yeni: 'bg-rose-500/15 text-rose-200',
  inceleniyor: 'bg-amber-500/15 text-amber-200',
  gorev: 'bg-sky-500/15 text-sky-200',
  cozuldu: 'bg-emerald-500/15 text-emerald-200',
  kapatildi: 'bg-white/10 text-muted-foreground',
};

/**
 * Yönetici › Geri bildirimler (Faz 2B).
 *
 * Bütün müşterilerin "Hata bildir" kayıtları: durum/tür süzgeci, ekran
 * görüntüsü (oturumla indirilip gösteriliyor), durum ve öncelik değiştirme,
 * tek tıkla proje görevine dönüştürme. Durum değişince müşteriye bildirim
 * gidiyor (matris: `geri_bildirim_durumu`).
 */
export default function GeriBildirimler() {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [liste, setListe] = useState<GeriBildirim[]>([]);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [durum, setDurum] = useState('acik');
  const [tur, setTur] = useState('');
  const [gorseller, setGorseller] = useState<Record<number, string>>({});

  const yukle = useCallback(async () => {
    setYukleniyor(true);
    try {
      setListe(await geriBildirimListesi({ durum: durum || undefined, tur: tur || undefined }));
    } catch {
      toast.error(t('geriBildirim.hata.yuklenemedi'));
    } finally {
      setYukleniyor(false);
    }
  }, [durum, tur, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  useEffect(
    () => () => {
      Object.values(gorseller).forEach((u) => URL.revokeObjectURL(u));
    },
    // Yalnız bileşen kapanırken.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  const hata = (h: unknown) =>
    toast.error(h instanceof ProjeHatasi ? t(`geriBildirim.hata.${h.kod}`, { defaultValue: t('geriBildirim.hata.genel') }) : t('geriBildirim.hata.genel'));

  const degistir = async (fb: GeriBildirim, girdi: Partial<{ durum: GeriBildirimDurumu; oncelik: Oncelik }>) => {
    try {
      const y = await geriBildirimGuncelle(fb.id, girdi);
      setListe((l) => l.map((x) => (x.id === fb.id ? y : x)));
    } catch (h) {
      hata(h);
    }
  };

  const donustur = async (fb: GeriBildirim) => {
    try {
      const y = await goreveDonustur(fb.id, true);
      setListe((l) => l.map((x) => (x.id === fb.id ? y.geri_bildirim : x)));
      toast.success(t('geriBildirim.yonetici.donusturuldu'));
    } catch (h) {
      hata(h);
    }
  };

  const gorselAc = async (ekId: number, adres: string) => {
    if (gorseller[ekId]) return;
    try {
      const u = await ekAdresi(adres);
      setGorseller((g) => ({ ...g, [ekId]: u }));
    } catch (h) {
      hata(h);
    }
  };

  return (
    <section className="space-y-4" data-testid="gb-yonetim">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-xl font-semibold">
            <Bug className="h-5 w-5 text-rose-300" /> {t('geriBildirim.yonetici.baslik')}
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">{t('geriBildirim.yonetici.aciklama')}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-xs text-muted-foreground">
            {t('geriBildirim.yonetici.filtreDurum')}{' '}
            <select value={durum} onChange={(e) => setDurum(e.target.value)} className={SECIM} data-testid="gb-filtre-durum">
              <option value="acik">{t('geriBildirim.yonetici.acik')}</option>
              <option value="">{t('geriBildirim.yonetici.hepsi')}</option>
              {GERI_BILDIRIM_DURUMLARI.map((d) => (
                <option key={d} value={d}>
                  {t(`geriBildirim.durum.${d}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-muted-foreground">
            {t('geriBildirim.yonetici.filtreTur')}{' '}
            <select value={tur} onChange={(e) => setTur(e.target.value)} className={SECIM}>
              <option value="">{t('geriBildirim.yonetici.hepsi')}</option>
              {GERI_BILDIRIM_TURLERI.map((d) => (
                <option key={d} value={d}>
                  {t(`geriBildirim.tur.${d}`)}
                </option>
              ))}
            </select>
          </label>
          <Button size="sm" variant="ghost" onClick={() => void yukle()} aria-label={t('geriBildirim.yenile')}>
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {yukleniyor ? (
        <div className="flex justify-center py-10 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
        </div>
      ) : liste.length === 0 ? (
        <p className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-8 text-center text-sm text-muted-foreground">
          {t('geriBildirim.yonetici.bos')}
        </p>
      ) : (
        <ul className="grid gap-3">
          {liste.map((fb) => (
            <li key={fb.id} className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-4" data-testid={`gb-satir-${fb.id}`}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <div className="mb-1 flex flex-wrap items-center gap-1.5 text-[11px]">
                    <span className="rounded-full bg-white/10 px-2 py-0.5">{t(`geriBildirim.tur.${fb.tur}`)}</span>
                    <span className={`rounded-full px-2 py-0.5 ${DURUM_RENGI[fb.durum]}`}>{t(`geriBildirim.durum.${fb.durum}`)}</span>
                    {fb.gorev_id ? (
                      <span className="rounded-full bg-sky-500/10 px-2 py-0.5 text-sky-200">
                        {t('geriBildirim.yonetici.gorevVar', { id: fb.gorev_id })}
                      </span>
                    ) : null}
                    <span className="text-muted-foreground">{tarihGoster(fb.created_at, dil)}</span>
                  </div>
                  <p className="break-words font-medium">{fb.baslik}</p>
                  {fb.aciklama && <p className="mt-1 whitespace-pre-line break-words text-sm text-muted-foreground">{fb.aciklama}</p>}
                  <dl className="mt-2 grid gap-x-4 gap-y-0.5 text-[11px] text-muted-foreground sm:grid-cols-2">
                    <div className="min-w-0 break-all">
                      <dt className="inline">{t('geriBildirim.yonetici.musteri')}: </dt>
                      <dd className="inline text-foreground/80">{fb.musteri_eposta}</dd>
                    </div>
                    <div className="min-w-0 break-words">
                      <dt className="inline">{t('geriBildirim.yonetici.proje')}: </dt>
                      <dd className="inline text-foreground/80">{fb.proje_basligi || t('geriBildirim.yonetici.projesiz')}</dd>
                    </div>
                    {fb.sayfa_adresi && (
                      <div className="min-w-0 break-all sm:col-span-2">
                        <dt className="inline">{t('geriBildirim.yonetici.sayfa')}: </dt>
                        <dd className="inline text-foreground/80">
                          {/^https?:\/\//i.test(fb.sayfa_adresi) ? (
                            <a href={fb.sayfa_adresi} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 hover:text-purple-200">
                              {fb.sayfa_adresi} <ExternalLink className="h-3 w-3" />
                            </a>
                          ) : (
                            fb.sayfa_adresi
                          )}
                        </dd>
                      </div>
                    )}
                    {fb.tarayici && (
                      <div className="min-w-0 break-words sm:col-span-2">
                        <dt className="inline">{t('geriBildirim.yonetici.tarayici')}: </dt>
                        <dd className="inline">{fb.tarayici}</dd>
                      </div>
                    )}
                  </dl>
                  {fb.ekler.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {fb.ekler.map((ek) =>
                        gorseller[ek.id] ? (
                          <img key={ek.id} src={gorseller[ek.id]} alt={fb.baslik} className="max-h-60 max-w-full rounded-lg border border-white/10" />
                        ) : (
                          <button
                            key={ek.id}
                            type="button"
                            onClick={() => void gorselAc(ek.id, ek.adres)}
                            className="inline-flex items-center gap-1 rounded-md border border-white/10 px-2 py-1 text-xs hover:border-purple-400/50"
                            data-testid={`gb-ek-${ek.id}`}
                          >
                            <ImageIcon className="h-3.5 w-3.5" /> {t('geriBildirim.yonetici.ekGoster')}
                          </button>
                        ),
                      )}
                    </div>
                  )}
                </div>
                <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto sm:flex-col sm:items-stretch">
                  <select
                    value={fb.durum}
                    onChange={(e) => void degistir(fb, { durum: e.target.value as GeriBildirimDurumu })}
                    className={SECIM}
                    aria-label={t('geriBildirim.alan.durum')}
                    data-testid={`gb-durum-sec-${fb.id}`}
                  >
                    {GERI_BILDIRIM_DURUMLARI.filter((d) => d !== 'gorev' || fb.gorev_id).map((d) => (
                      <option key={d} value={d}>
                        {t(`geriBildirim.durum.${d}`)}
                      </option>
                    ))}
                  </select>
                  <select
                    value={fb.oncelik || 'normal'}
                    onChange={(e) => void degistir(fb, { oncelik: e.target.value as Oncelik })}
                    className={SECIM}
                    aria-label={t('geriBildirim.yonetici.oncelik')}
                  >
                    {ONCELIKLER.map((o) => (
                      <option key={o} value={o}>
                        {t(`geriBildirim.oncelik.${o}`)}
                      </option>
                    ))}
                  </select>
                  {!fb.gorev_id && fb.proje_id && (
                    <Button size="sm" onClick={() => void donustur(fb)} data-testid={`gb-yonetim-donustur-${fb.id}`}>
                      {t('geriBildirim.yonetici.donustur')}
                    </Button>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
