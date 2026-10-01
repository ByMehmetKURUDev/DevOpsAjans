import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Copy, ExternalLink, Loader2, MapPin, Pencil, Phone, Plus, Trash2, Users, Video } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Alan, Anahtar, DIS_DUGME, KART, METIN_ALANI, Rozet, SECIM, Yukleniyor, kopyala, sureYaz } from '@/components/randevu/ortak';
import { hataMetni, type Kisi, type Meta, type RandevuApi, type Sayfa, type Tur } from '@/lib/randevu';
import type { KonumTuru, Soru } from '@/lib/randevuOrtak';

/** Faz 5R — etkinlik türleri: liste + düzenleme formu. */

const SURELER = [15, 20, 30, 45, 60, 90, 120, 180, 240];
const EN_ERKEN = [0, 30, 60, 120, 240, 720, 1440, 2880, 10080];
const KONUM_IKONU: Record<KonumTuru, typeof Video> = { jitsi: Video, baglanti: Video, telefon: Phone, yuz_yuze: MapPin };

type Taslak = Omit<Tur, 'id' | 'sayfa_id' | 'sira'> & { id?: number };

function bosTaslak(sayfa: Sayfa, kisiler: Kisi[]): Taslak {
  return {
    slug: '',
    ad: '',
    aciklama: '',
    sure_dk: 30,
    adim_dk: 30,
    konum_turu: 'jitsi',
    konum_degeri: '',
    tampon_once_dk: 0,
    tampon_sonra_dk: 0,
    en_erken_dk: 240,
    en_gec_gun: 60,
    gunluk_sinir: null,
    kapasite: 1,
    telefon: 'istege_bagli',
    sorular: [],
    renk: sayfa.renk,
    atama: 'kisi',
    kisiler: kisiler.filter((k) => k.aktif).slice(0, 1).map((k) => k.id),
    aktif: true,
  };
}

export default function Turler({ api, meta, sayfa }: { api: RandevuApi; meta: Meta; sayfa: Sayfa }) {
  const { t } = useTranslation();
  const [turler, setTurler] = useState<Tur[] | null>(null);
  const [sinir, setSinir] = useState<number | null>(null);
  const [kisiler, setKisiler] = useState<Kisi[]>([]);
  const [taslak, setTaslak] = useState<Taslak | null>(null);
  const [kaydediliyor, setKaydediliyor] = useState(false);

  const yukle = useCallback(async () => {
    try {
      const [l, k] = await Promise.all([api.turler(sayfa.id), api.kisiler(sayfa.id)]);
      setTurler(l.items);
      setSinir(l.tur_siniri);
      setKisiler(k.items);
    } catch (e) {
      toast.error(hataMetni(t, e));
      setTurler([]);
    }
  }, [api, sayfa.id, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const alan = <K extends keyof Taslak>(k: K, v: Taslak[K]) => setTaslak((x) => (x ? { ...x, [k]: v } : x));

  const kaydet = async () => {
    if (!taslak) return;
    if (!taslak.ad.trim()) {
      toast.error(t('randevu.hata.zorunlu'));
      return;
    }
    setKaydediliyor(true);
    const { id, ...govde } = taslak;
    const g: Partial<Tur> = { ...govde, slug: govde.slug.trim() || undefined } as Partial<Tur>;
    if (!g.slug) delete g.slug;
    try {
      if (id) await api.turGuncelle(sayfa.id, id, g);
      else await api.turOlustur(sayfa.id, g);
      toast.success(t('randevu.kaydedildi'));
      setTaslak(null);
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setKaydediliyor(false);
    }
  };

  const sil = async (tur: Tur) => {
    if (!window.confirm(t('randevu.turler.silOnay', { ad: tur.ad }))) return;
    try {
      await api.turSil(sayfa.id, tur.id);
      toast.success(t('randevu.silindi'));
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const aktiflik = async (tur: Tur) => {
    try {
      await api.turGuncelle(sayfa.id, tur.id, { aktif: !tur.aktif });
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  if (turler === null) return <Yukleniyor />;
  const sinirDolu = sinir !== null && turler.length >= sinir;

  if (taslak) {
    const soruGuncelle = (i: number, s: Partial<Soru>) =>
      alan('sorular', taslak.sorular.map((x, k) => (k === i ? { ...x, ...s } : x)));
    return (
      <div className={`${KART} p-4 sm:p-6`} data-testid="randevu-tur-formu">
        <h3 className="mb-4 text-base font-semibold">{taslak.id ? t('randevu.turler.duzenle') : t('randevu.turler.yeni')}</h3>
        <div className="grid gap-4 md:grid-cols-2">
          <Alan etiket={t('randevu.turler.ad')} className="md:col-span-2">
            <Input value={taslak.ad} onChange={(e) => alan('ad', e.target.value)} maxLength={120} placeholder={t('randevu.turler.adOrnek')} data-testid="randevu-tur-ad" />
          </Alan>
          <Alan etiket={t('randevu.turler.aciklama')} className="md:col-span-2">
            <textarea className={METIN_ALANI} value={taslak.aciklama} onChange={(e) => alan('aciklama', e.target.value)} maxLength={2000} />
          </Alan>
          <Alan etiket={t('randevu.turler.slug')} ipucu={t('randevu.turler.slugIpucu')}>
            <Input value={taslak.slug} onChange={(e) => alan('slug', e.target.value.toLowerCase())} maxLength={50} dir="ltr" placeholder="tanisma-gorusmesi" />
          </Alan>
          <Alan etiket={t('randevu.turler.renk')}>
            <input type="color" className="h-10 w-20 rounded-md border border-white/10 bg-transparent" value={taslak.renk} onChange={(e) => alan('renk', e.target.value)} />
          </Alan>
          <Alan etiket={t('randevu.turler.sure')}>
            <select className={SECIM} value={taslak.sure_dk} onChange={(e) => alan('sure_dk', Number(e.target.value))} data-testid="randevu-tur-sure">
              {[...new Set([...SURELER, taslak.sure_dk])].sort((a, b) => a - b).map((d) => (
                <option key={d} value={d}>
                  {sureYaz(t, d)}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('randevu.turler.adim')} ipucu={t('randevu.turler.adimIpucu')}>
            <select className={SECIM} value={taslak.adim_dk} onChange={(e) => alan('adim_dk', Number(e.target.value))}>
              {meta.adimlar.map((d) => (
                <option key={d} value={d}>
                  {sureYaz(t, d)}
                </option>
              ))}
            </select>
          </Alan>

          <fieldset className="md:col-span-2">
            <legend className="mb-2 text-sm font-semibold">{t('randevu.turler.konum')}</legend>
            <div className="grid gap-3 sm:grid-cols-2">
              <select className={SECIM} value={taslak.konum_turu} onChange={(e) => alan('konum_turu', e.target.value as KonumTuru)} data-testid="randevu-tur-konum" aria-label={t('randevu.turler.konum')}>
                {meta.konum_turleri.map((k) => (
                  <option key={k} value={k}>
                    {t(`randevu.konum.${k}`)}
                  </option>
                ))}
              </select>
              {taslak.konum_turu !== 'jitsi' && (
                <Input
                  value={taslak.konum_degeri}
                  onChange={(e) => alan('konum_degeri', e.target.value)}
                  maxLength={300}
                  placeholder={t(`randevu.konumYer.${taslak.konum_turu}`)}
                  aria-label={t(`randevu.konumYer.${taslak.konum_turu}`)}
                  dir={taslak.konum_turu === 'yuz_yuze' ? undefined : 'ltr'}
                />
              )}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{t(`randevu.konumIpucu.${taslak.konum_turu}`)}</p>
          </fieldset>

          <fieldset className="md:col-span-2">
            <legend className="mb-2 text-sm font-semibold">{t('randevu.turler.zamanlama')}</legend>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <Alan etiket={t('randevu.turler.tamponOnce')}>
                <Input type="number" min={0} max={240} step={5} value={taslak.tampon_once_dk} onChange={(e) => alan('tampon_once_dk', Number(e.target.value) || 0)} />
              </Alan>
              <Alan etiket={t('randevu.turler.tamponSonra')}>
                <Input type="number" min={0} max={240} step={5} value={taslak.tampon_sonra_dk} onChange={(e) => alan('tampon_sonra_dk', Number(e.target.value) || 0)} />
              </Alan>
              <Alan etiket={t('randevu.turler.enErken')}>
                <select className={SECIM} value={taslak.en_erken_dk} onChange={(e) => alan('en_erken_dk', Number(e.target.value))}>
                  {[...new Set([...EN_ERKEN, taslak.en_erken_dk])].sort((a, b) => a - b).map((d) => (
                    <option key={d} value={d}>
                      {d === 0 ? t('randevu.turler.hemen') : sureYaz(t, d)}
                    </option>
                  ))}
                </select>
              </Alan>
              <Alan etiket={t('randevu.turler.enGec')}>
                <Input type="number" min={1} max={365} value={taslak.en_gec_gun} onChange={(e) => alan('en_gec_gun', Number(e.target.value) || 1)} />
              </Alan>
              <Alan etiket={t('randevu.turler.gunlukSinir')} ipucu={t('randevu.turler.bosSinirsiz')}>
                <Input
                  type="number"
                  min={1}
                  max={100}
                  value={taslak.gunluk_sinir ?? ''}
                  onChange={(e) => alan('gunluk_sinir', e.target.value === '' ? null : Number(e.target.value))}
                />
              </Alan>
              <Alan etiket={t('randevu.turler.kapasite')} ipucu={t('randevu.turler.kapasiteIpucu')}>
                <Input type="number" min={1} max={meta.kapasite_en_cok} value={taslak.kapasite} onChange={(e) => alan('kapasite', Math.max(1, Number(e.target.value) || 1))} data-testid="randevu-tur-kapasite" />
              </Alan>
            </div>
          </fieldset>

          <fieldset className="md:col-span-2">
            <legend className="mb-2 text-sm font-semibold">{t('randevu.turler.ekip')}</legend>
            <div className="grid gap-3 sm:grid-cols-2">
              <select className={SECIM} value={taslak.atama} onChange={(e) => alan('atama', e.target.value as Tur['atama'])} aria-label={t('randevu.turler.atama')} disabled={taslak.kapasite > 1}>
                {meta.atama_turleri.map((a) => (
                  <option key={a} value={a}>
                    {t(`randevu.atama.${a}`)}
                  </option>
                ))}
              </select>
              <p className="text-xs text-muted-foreground">{t(`randevu.atamaIpucu.${taslak.atama}`)}</p>
            </div>
            <ul className="mt-2 flex flex-wrap gap-2">
              {kisiler.map((k) => {
                const sira = taslak.kisiler.indexOf(k.id);
                const secili = sira >= 0;
                return (
                  <li key={k.id}>
                    <label className={`flex cursor-pointer items-center gap-2 rounded-lg border px-2.5 py-1.5 text-sm ${secili ? 'border-purple-400/50 bg-purple-500/15' : 'border-white/10'}`}>
                      <input
                        type={taslak.atama === 'kisi' ? 'radio' : 'checkbox'}
                        name="randevu-kisi"
                        className="accent-purple-500"
                        checked={secili}
                        onChange={(e) => {
                          if (taslak.atama === 'kisi') alan('kisiler', [k.id]);
                          else alan('kisiler', e.target.checked ? [...taslak.kisiler, k.id] : taslak.kisiler.filter((x) => x !== k.id));
                        }}
                      />
                      {k.ad}
                      {secili && taslak.atama === 'ilk_musait' && <span className="text-[11px] text-purple-200">#{sira + 1}</span>}
                      {!k.aktif && <span className="text-[11px] text-amber-300">{t('randevu.pasif')}</span>}
                    </label>
                  </li>
                );
              })}
            </ul>
          </fieldset>

          <fieldset className="md:col-span-2">
            <legend className="mb-2 text-sm font-semibold">{t('randevu.turler.form')}</legend>
            <p className="mb-2 text-xs text-muted-foreground">{t('randevu.turler.formIpucu')}</p>
            <Alan etiket={t('randevu.turler.telefon')}>
              <select className={SECIM} value={taslak.telefon} onChange={(e) => alan('telefon', e.target.value as Tur['telefon'])}>
                {meta.telefon_secenekleri.map((x) => (
                  <option key={x} value={x}>
                    {t(`randevu.telefon.${x}`)}
                  </option>
                ))}
              </select>
            </Alan>
            <ul className="mt-3 space-y-2" data-testid="randevu-sorular">
              {taslak.sorular.map((s, i) => (
                <li key={s.id || i} className="grid gap-2 rounded-xl border border-white/10 p-3 sm:grid-cols-[minmax(0,1fr)_10rem_auto_auto] sm:items-center">
                  <Input value={s.etiket} onChange={(e) => soruGuncelle(i, { etiket: e.target.value })} maxLength={200} placeholder={t('randevu.turler.soruEtiket')} aria-label={t('randevu.turler.soruEtiket')} />
                  <select className={SECIM} value={s.tur} onChange={(e) => soruGuncelle(i, { tur: e.target.value as Soru['tur'] })} aria-label={t('randevu.turler.soruTuru')}>
                    {meta.soru_turleri.map((x) => (
                      <option key={x} value={x}>
                        {t(`randevu.soruTur.${x}`)}
                      </option>
                    ))}
                  </select>
                  <Anahtar acik={s.zorunlu} onDegis={(v) => soruGuncelle(i, { zorunlu: v })} etiket={t('randevu.turler.zorunlu')} />
                  <Button type="button" size="icon" variant="ghost" className="h-8 w-8" aria-label={t('randevu.sil')} onClick={() => alan('sorular', taslak.sorular.filter((_, k) => k !== i))}>
                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                  </Button>
                  {s.tur === 'secim' && (
                    <Input
                      className="sm:col-span-4"
                      value={s.secenekler.join(', ')}
                      onChange={(e) => soruGuncelle(i, { secenekler: e.target.value.split(',').map((x) => x.trimStart()) })}
                      onBlur={(e) => soruGuncelle(i, { secenekler: e.target.value.split(',').map((x) => x.trim()).filter(Boolean) })}
                      placeholder={t('randevu.turler.seceneklerIpucu')}
                      aria-label={t('randevu.turler.secenekler')}
                    />
                  )}
                </li>
              ))}
            </ul>
            {taslak.sorular.length < meta.en_cok_soru && (
              <Button
                type="button"
                size="sm"
                variant="outline"
                className={`mt-2 ${DIS_DUGME}`}
                onClick={() => alan('sorular', [...taslak.sorular, { id: '', etiket: '', tur: 'metin', zorunlu: false, secenekler: [] }])}
                data-testid="randevu-soru-ekle"
              >
                <Plus className="h-4 w-4" aria-hidden="true" />
                {t('randevu.turler.soruEkle', { sayi: meta.en_cok_soru - taslak.sorular.length })}
              </Button>
            )}
          </fieldset>

          <div className="md:col-span-2">
            <Anahtar acik={taslak.aktif} onDegis={(v) => alan('aktif', v)} etiket={t('randevu.turler.aktif')} />
          </div>
        </div>
        <div className="mt-6 flex flex-wrap justify-end gap-2">
          <Button variant="ghost" onClick={() => setTaslak(null)}>
            {t('randevu.vazgec')}
          </Button>
          <Button onClick={() => void kaydet()} disabled={kaydediliyor} className="gap-1.5" data-testid="randevu-tur-kaydet">
            {kaydediliyor && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            {t('randevu.kaydet')}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className={`${KART} p-4 sm:p-6`} data-testid="randevu-turler">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-base font-semibold">{t('randevu.turler.baslik')}</h3>
          {sinir !== null && <p className="text-xs text-muted-foreground">{t('randevu.turler.hak', { sayi: turler.length, sinir })}</p>}
        </div>
        <Button onClick={() => setTaslak(bosTaslak(sayfa, kisiler))} disabled={sinirDolu} className="gap-1.5" data-testid="randevu-tur-yeni">
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t('randevu.turler.yeni')}
        </Button>
      </div>
      {turler.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted-foreground">{t('randevu.turler.bos')}</p>
      ) : (
        <ul className="grid gap-3 lg:grid-cols-2" data-testid="randevu-tur-listesi">
          {turler.map((tur) => {
            const Ikon = KONUM_IKONU[tur.konum_turu] || Video;
            const adres = `${sayfa.adres_url}/${tur.slug}`;
            return (
              <li key={tur.id} className="flex gap-3 rounded-xl border border-white/10 bg-black/20 p-3" data-tur={tur.slug}>
                <span className="w-1.5 flex-none rounded-full" style={{ background: tur.renk }} aria-hidden="true" />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="truncate font-medium">{tur.ad}</span>
                    {!tur.aktif && <Rozet renk="border-amber-400/30 bg-amber-500/10 text-amber-200">{t('randevu.pasif')}</Rozet>}
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                    <Rozet>{sureYaz(t, tur.sure_dk)}</Rozet>
                    <Rozet>
                      <Ikon className="h-3 w-3" aria-hidden="true" />
                      {t(`randevu.konum.${tur.konum_turu}`)}
                    </Rozet>
                    {tur.kapasite > 1 && (
                      <Rozet>
                        <Users className="h-3 w-3" aria-hidden="true" />
                        {t('randevu.turler.grup', { sayi: tur.kapasite })}
                      </Rozet>
                    )}
                    {tur.kisiler.length > 1 && <Rozet>{t(`randevu.atama.${tur.atama}`)}</Rozet>}
                  </div>
                  <div className="mt-1 flex min-w-0 items-center gap-1 text-xs">
                    <span className="truncate font-mono text-purple-200" dir="ltr">
                      /{sayfa.slug}/{tur.slug}
                    </span>
                    <Button size="icon" variant="ghost" className="h-7 w-7 flex-none" aria-label={t('randevu.kopyala')} onClick={() => kopyala(adres, t('randevu.kopyalandi'), t('randevu.kopyalanamadi'))}>
                      <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                    </Button>
                    <a href={`/randevu/${sayfa.slug}/${tur.slug}`} target="_blank" rel="noopener" aria-label={t('randevu.ac')} className="text-muted-foreground hover:text-white">
                      <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                    </a>
                  </div>
                </div>
                <div className="flex flex-none flex-col items-end gap-1">
                  <Button size="sm" variant="ghost" className="h-8 gap-1" onClick={() => setTaslak({ ...tur })} data-testid="randevu-tur-duzenle">
                    <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                    {t('randevu.duzenle')}
                  </Button>
                  <div className="flex items-center gap-1">
                    <button type="button" className="text-[11px] text-muted-foreground hover:text-white" onClick={() => void aktiflik(tur)}>
                      {tur.aktif ? t('randevu.turler.pasifYap') : t('randevu.turler.aktifYap')}
                    </button>
                    <Button size="icon" variant="ghost" className="h-7 w-7" aria-label={t('randevu.sil')} onClick={() => void sil(tur)}>
                      <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                    </Button>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
