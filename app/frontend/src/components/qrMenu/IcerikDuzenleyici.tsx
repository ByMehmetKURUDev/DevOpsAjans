import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowDown, ArrowUp, Eye, EyeOff, Loader2, Pencil, Plus, Trash2, X } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import UrunFormu from '@/components/qrMenu/UrunFormu';
import { AiCevirDugmesi, Alan, CeviriAlanlari, DIS_DUGME, GorselSecici, KART, Rozet, sayiYaz } from '@/components/qrMenu/ortak';
import { hataMetni, type Icerik, type Magaza, type MenuApi, type MenuMeta } from '@/lib/qrMenu';
import { ETIKET_RENGI, paraYaz, type Ceviriler, type MenuGorsel, type MenuKategori, type MenuUrun } from '@/lib/qrMenuOrtak';

/** Faz 4M — menü düzenleyici: kategoriler, ürünler, sıralama, hızlı fiyat, stok. */

function HizliFiyat({ urun, para, dil, onKaydet, devreDisi }: { urun: MenuUrun; para: string; dil: string; onKaydet: (f: string) => Promise<void>; devreDisi: boolean }) {
  const { t } = useTranslation();
  const [deger, setDeger] = useState(String(urun.fiyat));
  const [kaydediliyor, setKaydediliyor] = useState(false);
  useEffect(() => setDeger(String(urun.fiyat)), [urun.fiyat]);
  const kaydet = async () => {
    const temiz = deger.trim();
    if (!temiz || Number(temiz.replace(',', '.')) === urun.fiyat) {
      setDeger(String(urun.fiyat));
      return;
    }
    setKaydediliyor(true);
    try {
      await onKaydet(temiz);
    } catch {
      setDeger(String(urun.fiyat));
    } finally {
      setKaydediliyor(false);
    }
  };
  return (
    <label className="flex items-center gap-1" title={paraYaz(urun.fiyat, para, dil)}>
      <span className="sr-only">{t('qrMenu.urun.fiyat')}</span>
      <Input
        value={deger}
        inputMode="decimal"
        onChange={(e) => setDeger(e.target.value)}
        onBlur={() => void kaydet()}
        onKeyDown={(e) => {
          if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
        }}
        disabled={devreDisi || kaydediliyor}
        className="h-8 w-24 text-end tabular-nums"
        dir="ltr"
        data-testid="menu-hizli-fiyat"
      />
      <span className="text-xs text-muted-foreground">{para}</span>
    </label>
  );
}

export default function IcerikDuzenleyici({ api, meta, magaza, yazilabilir }: { api: MenuApi; meta: MenuMeta; magaza: Magaza; yazilabilir: boolean }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [icerik, setIcerik] = useState<Icerik | null>(null);
  const [yeniKategori, setYeniKategori] = useState('');
  const [urunFormu, setUrunFormu] = useState<{ urun: MenuUrun | null; kategoriId: number } | null>(null);
  const [kategoriFormu, setKategoriFormu] = useState<{ kategori: MenuKategori; ad: string; ceviriler: Ceviriler; gorsel: MenuGorsel | null; gizli: boolean } | null>(null);
  const [mesgul, setMesgul] = useState<string | null>(null);

  const yukle = useCallback(async () => {
    try {
      setIcerik(await api.icerik(magaza.id));
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  }, [api, magaza.id, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const is = async (anahtar: string, fn: () => Promise<unknown>, basari?: string) => {
    setMesgul(anahtar);
    try {
      await fn();
      if (basari) toast.success(basari);
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
      await yukle();
    } finally {
      setMesgul(null);
    }
  };

  if (!icerik) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
      </div>
    );
  }

  const urunler = (kid: number) => icerik.urunler.filter((u) => u.kategori_id === kid);
  const sinirDolu = icerik.urun_siniri !== null && icerik.urun_sayisi >= icerik.urun_siniri;
  const ekDiller = magaza.ek_diller;

  const kategoriTasi = (i: number, yon: -1 | 1) => {
    const idler = icerik.kategoriler.map((k) => k.id);
    const j = i + yon;
    if (j < 0 || j >= idler.length) return;
    [idler[i], idler[j]] = [idler[j], idler[i]];
    void is(`ks-${idler[i]}`, () => api.kategoriSirala(magaza.id, idler));
  };
  const urunTasi = (kid: number, i: number, yon: -1 | 1) => {
    const idler = urunler(kid).map((u) => u.id);
    const j = i + yon;
    if (j < 0 || j >= idler.length) return;
    [idler[i], idler[j]] = [idler[j], idler[i]];
    void is(`us-${idler[i]}`, () => api.urunSirala(magaza.id, idler));
  };

  return (
    <div className="space-y-4" data-testid="menu-icerik">
      <div className={`${KART} flex flex-wrap items-end gap-3 p-4`}>
        <label className="block min-w-[200px] flex-1 text-sm">
          <span className="mb-1 block text-muted-foreground">{t('qrMenu.kategori.yeni')}</span>
          <Input
            value={yeniKategori}
            onChange={(e) => setYeniKategori(e.target.value)}
            maxLength={80}
            placeholder={t('qrMenu.kategori.ornek')}
            disabled={!yazilabilir}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && yeniKategori.trim()) {
                void is('yk', () => api.kategoriOlustur(magaza.id, { ad: yeniKategori.trim() }).then(() => setYeniKategori('')));
              }
            }}
            data-testid="menu-yeni-kategori"
          />
        </label>
        <Button
          onClick={() => void is('yk', () => api.kategoriOlustur(magaza.id, { ad: yeniKategori.trim() }).then(() => setYeniKategori('')))}
          disabled={!yazilabilir || !yeniKategori.trim() || mesgul === 'yk'}
          className="gap-1.5"
          data-testid="menu-kategori-ekle"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t('qrMenu.kategori.ekle')}
        </Button>
        <span className="text-xs text-muted-foreground" data-testid="menu-urun-hakki">
          {icerik.urun_siniri !== null
            ? t('qrMenu.urun.hak', { sayi: sayiYaz(icerik.urun_sayisi, dil), sinir: sayiYaz(icerik.urun_siniri, dil) })
            : t('qrMenu.urun.toplam', { sayi: sayiYaz(icerik.urun_sayisi, dil) })}
        </span>
      </div>

      {icerik.kategoriler.length === 0 && (
        <p className={`${KART} p-6 text-center text-sm text-muted-foreground`} data-testid="menu-kategori-yok">
          {t('qrMenu.kategori.bos')}
        </p>
      )}

      {icerik.kategoriler.map((k, ki) => {
        const liste = urunler(k.id);
        return (
          <section key={k.id} className={`${KART} p-4`} data-kategori={k.id} aria-label={k.ad}>
            <header className="mb-3 flex flex-wrap items-center gap-2">
              {k.gorsel && <img src={k.gorsel.k} alt="" width={36} height={36} className="h-9 w-9 rounded-lg object-cover" loading="lazy" decoding="async" />}
              <h4 className="min-w-0 flex-1 truncate font-semibold">
                {k.ad}
                {k.gizli && (
                  <Rozet renk="ms-2 border-white/15 bg-white/[0.05] text-muted-foreground">
                    <EyeOff className="h-3 w-3" aria-hidden="true" />
                    {t('qrMenu.gizli')}
                  </Rozet>
                )}
              </h4>
              <div className="flex items-center gap-1">
                <Button size="icon" variant="ghost" className="h-8 w-8" disabled={!yazilabilir || ki === 0} aria-label={t('qrMenu.yukari')} onClick={() => kategoriTasi(ki, -1)}>
                  <ArrowUp className="h-4 w-4" aria-hidden="true" />
                </Button>
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-8 w-8"
                  disabled={!yazilabilir || ki === icerik.kategoriler.length - 1}
                  aria-label={t('qrMenu.asagi')}
                  onClick={() => kategoriTasi(ki, 1)}
                >
                  <ArrowDown className="h-4 w-4" aria-hidden="true" />
                </Button>
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-8 w-8"
                  disabled={!yazilabilir}
                  aria-label={t('qrMenu.duzenle')}
                  onClick={() => setKategoriFormu({ kategori: k, ad: k.ad, ceviriler: k.ceviriler || {}, gorsel: k.gorsel, gizli: !!k.gizli })}
                  data-testid="menu-kategori-duzenle"
                >
                  <Pencil className="h-4 w-4" aria-hidden="true" />
                </Button>
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-8 w-8"
                  disabled={!yazilabilir || liste.length > 0}
                  title={liste.length ? t('qrMenu.hata.kategori_dolu') : undefined}
                  aria-label={t('qrMenu.sil')}
                  onClick={() => {
                    if (window.confirm(t('qrMenu.kategori.silOnay', { ad: k.ad }))) void is(`ksil-${k.id}`, () => api.kategoriSil(magaza.id, k.id));
                  }}
                >
                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                </Button>
              </div>
            </header>

            {liste.length === 0 ? (
              <p className="mb-3 text-sm text-muted-foreground">{t('qrMenu.urun.bos')}</p>
            ) : (
              <ul className="mb-3 divide-y divide-white/5 rounded-xl border border-white/10">
                {liste.map((u, ui) => (
                  <li key={u.id} className="flex flex-wrap items-center gap-2 p-2.5 sm:flex-nowrap" data-urun={u.id} data-urun-ad={u.ad}>
                    <div className="flex min-w-0 flex-1 items-center gap-2">
                      <div className="h-11 w-11 flex-none overflow-hidden rounded-lg border border-white/10 bg-black/30">
                        {u.gorsel && <img src={u.gorsel.k} alt="" width={44} height={44} className="h-full w-full object-cover" loading="lazy" decoding="async" />}
                      </div>
                      <div className="min-w-0">
                        <div className={`truncate text-sm font-medium ${u.gizli ? 'text-muted-foreground line-through' : ''}`}>{u.ad}</div>
                        <div className="mt-0.5 flex flex-wrap gap-1">
                          {u.indirimli_fiyat !== null && (
                            <Rozet renk="border-emerald-400/30 bg-emerald-500/10 text-emerald-200">{paraYaz(u.indirimli_fiyat, magaza.para_birimi, dil)}</Rozet>
                          )}
                          {u.secenek_gruplari.length > 0 && <Rozet>{t('qrMenu.urun.secenekSayisi', { sayi: u.secenek_gruplari.length })}</Rozet>}
                          {u.etiketler.slice(0, 3).map((e) => (
                            <Rozet key={e} renk={ETIKET_RENGI[e]}>
                              {t(`qrMenuSayfa.etiket.${e}`)}
                            </Rozet>
                          ))}
                          {u.stokta_yok && <Rozet renk="border-red-400/30 bg-red-500/10 text-red-200">{t('qrMenuSayfa.stoktaYok')}</Rozet>}
                        </div>
                      </div>
                    </div>
                    <div className="flex flex-wrap items-center gap-1">
                      <HizliFiyat
                        urun={u}
                        para={magaza.para_birimi}
                        dil={dil}
                        devreDisi={!yazilabilir}
                        onKaydet={async (f) => {
                          try {
                            await api.urunGuncelle(magaza.id, u.id, { fiyat: f });
                            toast.success(t('qrMenu.urun.fiyatKaydedildi'));
                            await yukle();
                          } catch (e) {
                            toast.error(hataMetni(t, e));
                            throw e;
                          }
                        }}
                      />
                      <label className="flex items-center gap-1 px-1 text-xs" title={t('qrMenuSayfa.stoktaYok')}>
                        <input
                          type="checkbox"
                          className="h-4 w-4 accent-red-500"
                          checked={u.stokta_yok}
                          disabled={!yazilabilir || mesgul === `st-${u.id}`}
                          onChange={(e) => {
                            // İyimser güncelleme: kutu hemen değişsin; hata olursa yeniden yüklemede geri döner.
                            const yeni = e.target.checked;
                            setIcerik((x) => x && { ...x, urunler: x.urunler.map((y) => (y.id === u.id ? { ...y, stokta_yok: yeni } : y)) });
                            void is(`st-${u.id}`, () => api.urunGuncelle(magaza.id, u.id, { stokta_yok: yeni }));
                          }}
                          data-testid="menu-stok"
                        />
                        <span className="hidden sm:inline">{t('qrMenu.urun.stokYok')}</span>
                      </label>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-8 w-8"
                        disabled={!yazilabilir}
                        aria-label={u.gizli ? t('qrMenu.goster') : t('qrMenu.gizle')}
                        onClick={() => void is(`g-${u.id}`, () => api.urunGuncelle(magaza.id, u.id, { gizli: !u.gizli }))}
                      >
                        {u.gizli ? <EyeOff className="h-4 w-4" aria-hidden="true" /> : <Eye className="h-4 w-4" aria-hidden="true" />}
                      </Button>
                      <Button size="icon" variant="ghost" className="h-8 w-8" disabled={!yazilabilir || ui === 0} aria-label={t('qrMenu.yukari')} onClick={() => urunTasi(k.id, ui, -1)}>
                        <ArrowUp className="h-4 w-4" aria-hidden="true" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-8 w-8"
                        disabled={!yazilabilir || ui === liste.length - 1}
                        aria-label={t('qrMenu.asagi')}
                        onClick={() => urunTasi(k.id, ui, 1)}
                        data-testid="menu-urun-asagi"
                      >
                        <ArrowDown className="h-4 w-4" aria-hidden="true" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-8 w-8"
                        disabled={!yazilabilir}
                        aria-label={t('qrMenu.duzenle')}
                        onClick={() => setUrunFormu({ urun: u, kategoriId: k.id })}
                        data-testid="menu-urun-duzenle"
                      >
                        <Pencil className="h-4 w-4" aria-hidden="true" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-8 w-8"
                        disabled={!yazilabilir}
                        aria-label={t('qrMenu.sil')}
                        onClick={() => {
                          if (window.confirm(t('qrMenu.urun.silOnay', { ad: u.ad }))) void is(`usil-${u.id}`, () => api.urunSil(magaza.id, u.id), t('qrMenu.silindi'));
                        }}
                      >
                        <Trash2 className="h-4 w-4" aria-hidden="true" />
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <Button
              size="sm"
              variant="outline"
              className={DIS_DUGME}
              disabled={!yazilabilir || sinirDolu}
              title={sinirDolu ? t('qrMenu.hata.urun_siniri', { sinir: icerik.urun_siniri }) : undefined}
              onClick={() => setUrunFormu({ urun: null, kategoriId: k.id })}
              data-testid="menu-urun-ekle"
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
              {t('qrMenu.urun.ekle')}
            </Button>
          </section>
        );
      })}

      {urunFormu && (
        <UrunFormu
          api={api}
          meta={meta}
          magaza={magaza}
          kategoriler={icerik.kategoriler}
          urun={urunFormu.urun}
          kategoriId={urunFormu.kategoriId}
          onKapat={() => setUrunFormu(null)}
          onKaydedildi={() => {
            setUrunFormu(null);
            void yukle();
          }}
        />
      )}

      {kategoriFormu && (
        <div className="fixed inset-0 z-[70] flex items-end justify-center bg-black/70 p-0 sm:items-center sm:p-4" role="dialog" aria-modal="true" aria-labelledby="kategori-formu-baslik">
          <div className="max-h-[92vh] w-full overflow-y-auto rounded-t-2xl border border-white/10 bg-[#120b1f] p-5 sm:max-w-lg sm:rounded-2xl" data-testid="menu-kategori-formu">
            <div className="mb-4 flex items-center justify-between">
              <h3 id="kategori-formu-baslik" className="text-lg font-semibold">
                {t('qrMenu.kategori.duzenle')}
              </h3>
              <Button size="icon" variant="ghost" aria-label={t('qrMenu.kapat')} onClick={() => setKategoriFormu(null)}>
                <X className="h-4 w-4" aria-hidden="true" />
              </Button>
            </div>
            <div className="space-y-4">
              <Alan etiket={t('qrMenu.kategori.ad')}>
                <Input value={kategoriFormu.ad} maxLength={80} onChange={(e) => setKategoriFormu({ ...kategoriFormu, ad: e.target.value })} />
              </Alan>
              <GorselSecici
                api={api}
                magazaId={magaza.id}
                gorsel={kategoriFormu.gorsel}
                onDegis={(g) => setKategoriFormu({ ...kategoriFormu, gorsel: g })}
                etiket={t('qrMenu.kategori.gorsel')}
                enCokMb={meta.gorsel_en_cok_mb}
              />
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" className="h-4 w-4 accent-purple-500" checked={kategoriFormu.gizli} onChange={(e) => setKategoriFormu({ ...kategoriFormu, gizli: e.target.checked })} />
                {t('qrMenu.kategori.gizli')}
              </label>
              <div>
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <span className="text-sm font-medium">{t('qrMenu.ceviri.baslik')}</span>
                  <AiCevirDugmesi
                    acik={meta.ai_ceviri}
                    ekDilVar={ekDiller.length > 0}
                    yukleniyor={mesgul === 'kai'}
                    onTikla={async () => {
                      setMesgul('kai');
                      try {
                        await api.kategoriGuncelle(magaza.id, kategoriFormu.kategori.id, { ad: kategoriFormu.ad });
                        const y = await api.cevir(magaza.id, { tur: 'kategori', id: kategoriFormu.kategori.id });
                        setKategoriFormu({ ...kategoriFormu, ceviriler: (y.kayit as MenuKategori).ceviriler });
                        toast.success(t('qrMenu.ceviri.tamam'));
                      } catch (e) {
                        toast.error(hataMetni(t, e));
                      } finally {
                        setMesgul(null);
                      }
                    }}
                  />
                </div>
                <CeviriAlanlari diller={ekDiller} ceviriler={kategoriFormu.ceviriler} onDegis={(c) => setKategoriFormu({ ...kategoriFormu, ceviriler: c })} />
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="ghost" onClick={() => setKategoriFormu(null)}>
                  {t('qrMenu.vazgec')}
                </Button>
                <Button
                  onClick={() =>
                    void is(
                      'kf',
                      () =>
                        api
                          .kategoriGuncelle(magaza.id, kategoriFormu.kategori.id, {
                            ad: kategoriFormu.ad,
                            ceviriler: kategoriFormu.ceviriler,
                            gorsel: kategoriFormu.gorsel?.anahtar ?? null,
                            gizli: kategoriFormu.gizli,
                          })
                          .then(() => setKategoriFormu(null)),
                      t('qrMenu.kaydedildi')
                    )
                  }
                  disabled={mesgul === 'kf'}
                  data-testid="menu-kategori-kaydet"
                >
                  {t('qrMenu.kaydet')}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
