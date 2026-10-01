import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, Plus, Trash2, X } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { AiCevirDugmesi, Alan, CeviriAlanlari, DIS_DUGME, GorselSecici, METIN_ALANI, SECIM } from '@/components/qrMenu/ortak';
import { hataMetni, type Magaza, type MenuApi, type MenuMeta, type UrunGirdisi } from '@/lib/qrMenu';
import {
  ALERJENLER,
  DIL_ADLARI,
  ETIKETLER,
  type Alerjen,
  type Ceviriler,
  type Etiket,
  type MenuGorsel,
  type MenuKategori,
  type MenuUrun,
  type SecenekGrubu,
  type TekCeviri,
} from '@/lib/qrMenuOrtak';

/** Faz 4M — ürün formu: fiyat, görsel, seçenek grupları, etiket/alerjen, çeviriler. */

interface GrupTaslagi {
  id: string;
  ad: string;
  tur: 'tek' | 'coklu';
  zorunlu: boolean;
  en_az: string;
  en_cok: string;
  ceviriler: TekCeviri;
  secenekler: { id: string; ad: string; fiyat_farki: string; ceviriler: TekCeviri }[];
}

const yeniKimlik = (on: string) => `${on}${Math.random().toString(36).slice(2, 8)}`;

function taslak(g: SecenekGrubu): GrupTaslagi {
  return {
    id: g.id,
    ad: g.ad,
    tur: g.tur,
    zorunlu: g.zorunlu,
    en_az: String(g.en_az),
    en_cok: String(g.en_cok),
    ceviriler: g.ceviriler || {},
    secenekler: g.secenekler.map((s) => ({ id: s.id, ad: s.ad, fiyat_farki: String(s.fiyat_farki || 0), ceviriler: s.ceviriler || {} })),
  };
}

export default function UrunFormu({
  api,
  meta,
  magaza,
  kategoriler,
  urun,
  kategoriId,
  onKapat,
  onKaydedildi,
}: {
  api: MenuApi;
  meta: MenuMeta;
  magaza: Magaza;
  kategoriler: MenuKategori[];
  urun: MenuUrun | null;
  kategoriId: number;
  onKapat: () => void;
  onKaydedildi: () => void;
}) {
  const { t } = useTranslation();
  const [kategori, setKategori] = useState(urun?.kategori_id ?? kategoriId);
  const [ad, setAd] = useState(urun?.ad ?? '');
  const [aciklama, setAciklama] = useState(urun?.aciklama ?? '');
  const [fiyat, setFiyat] = useState(urun ? String(urun.fiyat) : '');
  const [indirimli, setIndirimli] = useState(urun?.indirimli_fiyat != null ? String(urun.indirimli_fiyat) : '');
  const [gorsel, setGorsel] = useState<MenuGorsel | null>(urun?.gorsel ?? null);
  const [gruplar, setGruplar] = useState<GrupTaslagi[]>((urun?.secenek_gruplari || []).map(taslak));
  const [etiketler, setEtiketler] = useState<Etiket[]>(urun?.etiketler ?? []);
  const [alerjenler, setAlerjenler] = useState<Alerjen[]>(urun?.alerjenler ?? []);
  const [kalori, setKalori] = useState(urun?.kalori != null ? String(urun.kalori) : '');
  const [stoktaYok, setStoktaYok] = useState(urun?.stokta_yok ?? false);
  const [gizli, setGizli] = useState(urun?.gizli ?? false);
  const [ceviriler, setCeviriler] = useState<Ceviriler>(urun?.ceviriler ?? {});
  const [kaydediliyor, setKaydediliyor] = useState(false);
  const [ceviriliyor, setCeviriliyor] = useState(false);
  const [mevcutId, setMevcutId] = useState<number | null>(urun?.id ?? null);
  const ekDiller = magaza.ek_diller;

  const girdi = (): UrunGirdisi => ({
    kategori_id: kategori,
    ad: ad.trim(),
    aciklama: aciklama.trim(),
    fiyat: fiyat.trim(),
    indirimli_fiyat: indirimli.trim() || null,
    gorsel: gorsel?.anahtar ?? null,
    etiketler,
    alerjenler,
    kalori: kalori.trim() ? Number(kalori) : null,
    stokta_yok: stoktaYok,
    gizli,
    ceviriler,
    secenek_gruplari: gruplar.map((g) => ({
      id: g.id,
      ad: g.ad.trim(),
      tur: g.tur,
      zorunlu: g.zorunlu,
      en_az: Number(g.en_az) || 0,
      en_cok: Number(g.en_cok) || g.secenekler.length,
      ceviriler: g.ceviriler,
      secenekler: g.secenekler.map((s) => ({ id: s.id, ad: s.ad.trim(), fiyat_farki: (s.fiyat_farki.trim() || '0') as unknown as number, ceviriler: s.ceviriler })),
    })),
  });

  const kaydet = async (kapat = true): Promise<MenuUrun | null> => {
    setKaydediliyor(true);
    try {
      const sonuc = mevcutId ? await api.urunGuncelle(magaza.id, mevcutId, girdi()) : await api.urunOlustur(magaza.id, girdi());
      setMevcutId(sonuc.id);
      if (kapat) {
        toast.success(t('qrMenu.kaydedildi'));
        onKaydedildi();
      }
      return sonuc;
    } catch (e) {
      toast.error(hataMetni(t, e));
      return null;
    } finally {
      setKaydediliyor(false);
    }
  };

  const aiCevir = async () => {
    setCeviriliyor(true);
    try {
      const kayit = await kaydet(false);
      if (!kayit) return;
      const y = await api.cevir(magaza.id, { tur: 'urun', id: kayit.id });
      const u = y.kayit as MenuUrun;
      setCeviriler(u.ceviriler);
      setGruplar(u.secenek_gruplari.map(taslak));
      toast.success(t('qrMenu.ceviri.tamam'));
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setCeviriliyor(false);
    }
  };

  const grupGuncelle = (i: number, g: Partial<GrupTaslagi>) => setGruplar((l) => l.map((x, j) => (j === i ? { ...x, ...g } : x)));
  const secenekGuncelle = (gi: number, si: number, s: Partial<GrupTaslagi['secenekler'][number]>) =>
    setGruplar((l) => l.map((x, j) => (j === gi ? { ...x, secenekler: x.secenekler.map((y, k) => (k === si ? { ...y, ...s } : y)) } : x)));
  const degistir = <T,>(liste: T[], deger: T) => (liste.includes(deger) ? liste.filter((x) => x !== deger) : [...liste, deger]);

  return (
    <div className="fixed inset-0 z-[70] flex items-end justify-center bg-black/70 sm:items-center sm:p-4" role="dialog" aria-modal="true" aria-labelledby="urun-formu-baslik">
      <div className="max-h-[94vh] w-full overflow-y-auto rounded-t-2xl border border-white/10 bg-[#120b1f] p-4 sm:max-w-3xl sm:rounded-2xl sm:p-6" data-testid="menu-urun-formu">
        <div className="mb-4 flex items-center justify-between gap-2">
          <h3 id="urun-formu-baslik" className="text-lg font-semibold">
            {urun ? t('qrMenu.urun.duzenle') : t('qrMenu.urun.yeni')}
          </h3>
          <Button size="icon" variant="ghost" aria-label={t('qrMenu.kapat')} onClick={onKapat}>
            <X className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Alan etiket={t('qrMenu.urun.ad')}>
            <Input value={ad} onChange={(e) => setAd(e.target.value)} maxLength={120} data-testid="menu-urun-ad" />
          </Alan>
          <Alan etiket={t('qrMenu.urun.kategori')}>
            <select className={SECIM} value={kategori} onChange={(e) => setKategori(Number(e.target.value))}>
              {kategoriler.map((k) => (
                <option key={k.id} value={k.id}>
                  {k.ad}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('qrMenu.urun.aciklama')} className="sm:col-span-2">
            <textarea value={aciklama} onChange={(e) => setAciklama(e.target.value)} maxLength={1000} className={METIN_ALANI} data-testid="menu-urun-aciklama" />
          </Alan>
          <Alan etiket={`${t('qrMenu.urun.fiyat')} (${magaza.para_birimi})`}>
            <Input value={fiyat} onChange={(e) => setFiyat(e.target.value)} inputMode="decimal" dir="ltr" placeholder="0,00" data-testid="menu-urun-fiyat" />
          </Alan>
          <Alan etiket={`${t('qrMenu.urun.indirimliFiyat')} (${magaza.para_birimi})`} ipucu={t('qrMenu.urun.indirimliIpucu')}>
            <Input value={indirimli} onChange={(e) => setIndirimli(e.target.value)} inputMode="decimal" dir="ltr" data-testid="menu-urun-indirimli" />
          </Alan>
          <GorselSecici
            api={api}
            magazaId={magaza.id}
            gorsel={gorsel}
            onDegis={setGorsel}
            etiket={t('qrMenu.urun.gorsel')}
            testid="menu-urun-gorsel"
            enCokMb={meta.gorsel_en_cok_mb}
          />
          <Alan etiket={t('qrMenu.urun.kalori')} ipucu={t('qrMenu.urun.kaloriIpucu')}>
            <Input value={kalori} onChange={(e) => setKalori(e.target.value.replace(/\D/g, ''))} inputMode="numeric" dir="ltr" />
          </Alan>
        </div>

        {/* Seçenek grupları */}
        <fieldset className="mt-5 rounded-xl border border-white/10 p-3 sm:p-4">
          <legend className="px-1 text-sm font-semibold">{t('qrMenu.secenek.baslik')}</legend>
          <p className="mb-3 text-xs text-muted-foreground">{t('qrMenu.secenek.aciklama')}</p>
          <div className="space-y-3">
            {gruplar.map((g, gi) => (
              <div key={g.id} className="rounded-xl border border-white/10 bg-black/20 p-3" data-secenek-grubu={gi}>
                <div className="grid gap-2 sm:grid-cols-[minmax(0,1.4fr)_auto_auto_auto]">
                  <Input value={g.ad} onChange={(e) => grupGuncelle(gi, { ad: e.target.value })} placeholder={t('qrMenu.secenek.grupAdi')} maxLength={60} data-testid="menu-grup-ad" />
                  <select className={`${SECIM} sm:w-36`} value={g.tur} onChange={(e) => grupGuncelle(gi, { tur: e.target.value as 'tek' | 'coklu' })} data-testid="menu-grup-tur">
                    <option value="tek">{t('qrMenu.secenek.tek')}</option>
                    <option value="coklu">{t('qrMenu.secenek.coklu')}</option>
                  </select>
                  <label className="flex items-center gap-1.5 text-sm">
                    <input type="checkbox" className="h-4 w-4 accent-purple-500" checked={g.zorunlu} onChange={(e) => grupGuncelle(gi, { zorunlu: e.target.checked })} data-testid="menu-grup-zorunlu" />
                    {t('qrMenu.secenek.zorunlu')}
                  </label>
                  <Button size="icon" variant="ghost" aria-label={t('qrMenu.sil')} onClick={() => setGruplar((l) => l.filter((_, j) => j !== gi))}>
                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                  </Button>
                </div>
                {g.tur === 'coklu' && (
                  <div className="mt-2 flex flex-wrap items-center gap-3 text-sm">
                    <label className="flex items-center gap-1.5">
                      {t('qrMenu.secenek.enAz')}
                      <Input value={g.en_az} onChange={(e) => grupGuncelle(gi, { en_az: e.target.value.replace(/\D/g, '') })} className="h-8 w-16" inputMode="numeric" dir="ltr" />
                    </label>
                    <label className="flex items-center gap-1.5">
                      {t('qrMenu.secenek.enCok')}
                      <Input value={g.en_cok} onChange={(e) => grupGuncelle(gi, { en_cok: e.target.value.replace(/\D/g, '') })} className="h-8 w-16" inputMode="numeric" dir="ltr" data-testid="menu-grup-en-cok" />
                    </label>
                  </div>
                )}
                <ul className="mt-2 space-y-1.5">
                  {g.secenekler.map((s, si) => (
                    <li key={s.id} className="grid grid-cols-[minmax(0,1fr)_7rem_auto] items-center gap-2">
                      <Input value={s.ad} onChange={(e) => secenekGuncelle(gi, si, { ad: e.target.value })} placeholder={t('qrMenu.secenek.secenekAdi')} maxLength={60} data-testid="menu-secenek-ad" />
                      <Input
                        value={s.fiyat_farki}
                        onChange={(e) => secenekGuncelle(gi, si, { fiyat_farki: e.target.value })}
                        inputMode="decimal"
                        dir="ltr"
                        aria-label={t('qrMenu.secenek.fiyatFarki')}
                        placeholder="+0"
                        data-testid="menu-secenek-fiyat"
                      />
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-8 w-8"
                        aria-label={t('qrMenu.sil')}
                        disabled={g.secenekler.length <= 1}
                        onClick={() => grupGuncelle(gi, { secenekler: g.secenekler.filter((_, k) => k !== si) })}
                      >
                        <Trash2 className="h-4 w-4" aria-hidden="true" />
                      </Button>
                    </li>
                  ))}
                </ul>
                <Button
                  size="sm"
                  variant="ghost"
                  className="mt-1 gap-1"
                  onClick={() => grupGuncelle(gi, { secenekler: [...g.secenekler, { id: yeniKimlik('s'), ad: '', fiyat_farki: '0', ceviriler: {} }] })}
                  data-testid="menu-secenek-ekle"
                >
                  <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                  {t('qrMenu.secenek.secenekEkle')}
                </Button>
                {ekDiller.length > 0 && (
                  <details className="mt-2 text-sm">
                    <summary className="cursor-pointer text-xs text-purple-200">{t('qrMenu.secenek.ceviriler')}</summary>
                    <div className="mt-2 space-y-2">
                      {ekDiller.map((dil) => (
                        <div key={dil} className="grid gap-1.5 sm:grid-cols-3" dir={dil === 'ar' ? 'rtl' : 'ltr'}>
                          <span className="text-xs text-muted-foreground sm:col-span-3">{DIL_ADLARI[dil]}</span>
                          <Input
                            value={g.ceviriler[dil] || ''}
                            onChange={(e) => grupGuncelle(gi, { ceviriler: { ...g.ceviriler, [dil]: e.target.value } })}
                            placeholder={g.ad}
                            lang={dil}
                            className="h-8"
                          />
                          {g.secenekler.map((s, si) => (
                            <Input
                              key={s.id}
                              value={s.ceviriler[dil] || ''}
                              onChange={(e) => secenekGuncelle(gi, si, { ceviriler: { ...s.ceviriler, [dil]: e.target.value } })}
                              placeholder={s.ad}
                              lang={dil}
                              className="h-8"
                            />
                          ))}
                        </div>
                      ))}
                    </div>
                  </details>
                )}
              </div>
            ))}
          </div>
          <Button
            size="sm"
            variant="outline"
            className={`${DIS_DUGME} mt-3`}
            disabled={gruplar.length >= 10}
            onClick={() =>
              setGruplar((l) => [
                ...l,
                { id: yeniKimlik('g'), ad: '', tur: 'tek', zorunlu: false, en_az: '0', en_cok: '1', ceviriler: {}, secenekler: [{ id: yeniKimlik('s'), ad: '', fiyat_farki: '0', ceviriler: {} }] },
              ])
            }
            data-testid="menu-grup-ekle"
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('qrMenu.secenek.grupEkle')}
          </Button>
        </fieldset>

        {/* Etiketler ve alerjenler */}
        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <fieldset>
            <legend className="mb-2 text-sm font-semibold">{t('qrMenu.urun.etiketler')}</legend>
            <div className="flex flex-wrap gap-2">
              {ETIKETLER.map((e) => (
                <label key={e} className={`flex cursor-pointer items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs ${etiketler.includes(e) ? 'border-purple-400/60 bg-purple-500/20' : 'border-white/10'}`}>
                  <input type="checkbox" className="h-3.5 w-3.5 accent-purple-500" checked={etiketler.includes(e)} onChange={() => setEtiketler((l) => degistir(l, e))} data-etiket={e} />
                  {t(`qrMenuSayfa.etiket.${e}`)}
                </label>
              ))}
            </div>
          </fieldset>
          <fieldset>
            <legend className="mb-2 text-sm font-semibold">{t('qrMenu.urun.alerjenler')}</legend>
            <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
              {ALERJENLER.map((a) => (
                <label key={a} className="flex cursor-pointer items-center gap-1.5 text-xs">
                  <input type="checkbox" className="h-3.5 w-3.5 accent-amber-500" checked={alerjenler.includes(a)} onChange={() => setAlerjenler((l) => degistir(l, a))} data-alerjen={a} />
                  {t(`qrMenuSayfa.alerjen.${a}`)}
                </label>
              ))}
            </div>
            <p className="mt-1 text-[11px] text-muted-foreground">{t('qrMenu.urun.alerjenIpucu')}</p>
          </fieldset>
        </div>

        <div className="mt-4 flex flex-wrap gap-4">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" className="h-4 w-4 accent-red-500" checked={stoktaYok} onChange={(e) => setStoktaYok(e.target.checked)} />
            {t('qrMenuSayfa.stoktaYok')}
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" className="h-4 w-4 accent-purple-500" checked={gizli} onChange={(e) => setGizli(e.target.checked)} />
            {t('qrMenu.urun.gizli')}
          </label>
        </div>

        {/* Çeviriler */}
        <div className="mt-5">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm font-semibold">{t('qrMenu.ceviri.baslik')}</span>
            <AiCevirDugmesi acik={meta.ai_ceviri} ekDilVar={ekDiller.length > 0} yukleniyor={ceviriliyor} onTikla={() => void aiCevir()} testid="menu-urun-ai" />
          </div>
          <CeviriAlanlari diller={ekDiller} ceviriler={ceviriler} onDegis={setCeviriler} aciklamaVar testid="menu-urun-ceviri" />
        </div>

        <div className="sticky bottom-0 -mx-4 mt-6 flex justify-end gap-2 border-t border-white/10 bg-[#120b1f] px-4 py-3 sm:-mx-6 sm:px-6">
          <Button variant="ghost" onClick={onKapat}>
            {t('qrMenu.vazgec')}
          </Button>
          <Button onClick={() => void kaydet(true)} disabled={kaydediliyor || !ad.trim() || !fiyat.trim()} className="gap-1.5" data-testid="menu-urun-kaydet">
            {kaydediliyor && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            {t('qrMenu.kaydet')}
          </Button>
        </div>
      </div>
    </div>
  );
}
