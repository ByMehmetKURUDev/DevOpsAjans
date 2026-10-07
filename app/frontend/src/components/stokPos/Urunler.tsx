import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, Download, Link2, Pencil, Plus, Printer, RefreshCw, Shapes, Tags, Trash2, Upload, UtensilsCrossed } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { Alan, Anahtar, Bos, DIS_DUGME, GIRDI, KART, METIN_ALANI, Pencere, Rozet, SECIM, Yukleniyor } from '@/components/stokPos/ortak';
import { hataMetni, kurusaCevir, miktarYaz, para, sayiCevir, type Meta, type StokApi, type Urun } from '@/lib/stokPos';

const Etiketler = lazy(() => import('@/components/stokPos/Etiketler'));

/**
 * Faz 6P — ürünler: arama/süzgeç, ekle/düzenle (barkod üret, KDV, kritik eşik), varyant (beden/renk), CSV
 * içe/dışa aktarma, A4 barkod etiketi, QR menü/katalogdan bağlı aktarma.
 */
export default function Urunler({ api, meta, saltOkunur, onMeta, baslangicKritik }: { api: StokApi; meta: Meta; saltOkunur: boolean; onMeta: () => void; baslangicKritik?: boolean }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const pb = meta.ayarlar.para_birimi;
  const [ara, setAra] = useState('');
  const [kategori, setKategori] = useState('');
  const [kritik, setKritik] = useState(!!baslangicKritik);
  const [pasif, setPasif] = useState(false);
  const [veri, setVeri] = useState<{ items: Urun[]; toplam: number; kategoriler: string[] } | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [bilgi, setBilgi] = useState<string | null>(null);
  const [form, setForm] = useState<Urun | 'yeni' | null>(null);
  const [varyantIcin, setVaryantIcin] = useState<Urun | null>(null);
  const [secili, setSecili] = useState<Set<number>>(new Set());
  const [etiket, setEtiket] = useState(false);
  const [menuPencere, setMenuPencere] = useState(false);
  const dosya = useRef<HTMLInputElement | null>(null);
  const yazabilir = meta.yetki.stok && !saltOkunur;

  const yukle = useCallback(async () => {
    setHata(null);
    try {
      setVeri(await api.urunler({ ara: ara.trim() || undefined, kategori: kategori || undefined, kritik, aktif: pasif ? 'hepsi' : 'evet', adet: 200 }));
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  }, [api, ara, kategori, kritik, pasif, t]);

  useEffect(() => {
    const z = window.setTimeout(() => void yukle(), 200);
    return () => window.clearTimeout(z);
  }, [yukle]);

  const sil = async (u: Urun) => {
    if (!window.confirm(t('stokPos.urun.silOnay', { ad: u.ad }))) return;
    try {
      const r = await api.urunSil(u.id);
      setBilgi(t(r.pasif ? 'stokPos.urun.pasifYapildi' : 'stokPos.urun.silindi'));
      void yukle();
      onMeta();
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  };

  const iceAktar = async (f: File) => {
    setBilgi(null);
    setHata(null);
    try {
      const r = await api.iceAktar(f);
      setBilgi(t('stokPos.urun.iceAktarildi', { eklenen: r.eklenen, guncellenen: r.guncellenen, hata: r.hata_sayisi }));
      if (r.hatalar.length) setHata(r.hatalar.slice(0, 5).map((h) => `${t('stokPos.urun.satir', { sayi: h.satir })}: ${t(`stokPos.hata.${h.kod}`, { defaultValue: h.kod })}`).join(' · '));
      void yukle();
      onMeta();
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  };

  const seciliUrunler = (veri?.items || []).filter((u) => secili.has(u.id));
  const hepsiSecili = !!veri?.items.length && veri.items.every((u) => secili.has(u.id));

  return (
    <div className="space-y-3" data-testid="stok-urunler">
      <div className="flex flex-wrap items-center gap-2">
        <input className={cn(GIRDI, 'min-w-0 flex-1 sm:max-w-xs')} value={ara} onChange={(e) => setAra(e.target.value)} placeholder={t('stokPos.urun.araIpucu')} aria-label={t('stokPos.ara')} data-testid="stok-urun-ara" />
        <select className={cn(SECIM, 'w-auto')} value={kategori} onChange={(e) => setKategori(e.target.value)} aria-label={t('stokPos.urun.kategori')}>
          <option value="">{t('stokPos.urun.tumKategoriler')}</option>
          {(veri?.kategoriler || []).map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
        <Anahtar acik={kritik} onDegis={setKritik} etiket={t('stokPos.urun.yalnizKritik')} testid="stok-kritik-suz" />
        {meta.yetki.stok && <Anahtar acik={pasif} onDegis={setPasif} etiket={t('stokPos.urun.pasifler')} />}
      </div>
      <div className="flex flex-wrap gap-2">
        {yazabilir && (
          <Button size="sm" className="gap-1.5" onClick={() => setForm('yeni')} data-testid="stok-urun-yeni">
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('stokPos.urun.yeni')}
          </Button>
        )}
        {yazabilir && (
          <>
            <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => dosya.current?.click()} data-testid="stok-csv-ice">
              <Upload className="h-4 w-4" aria-hidden="true" />
              {t('stokPos.urun.csvIce')}
            </Button>
            <input
              ref={dosya}
              type="file"
              accept=".csv,text/csv"
              className="hidden"
              data-testid="stok-csv-dosya"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void iceAktar(f);
                e.target.value = '';
              }}
            />
          </>
        )}
        {meta.yetki.stok && !saltOkunur && (
          <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => void api.urunlerCsv().catch((e) => setHata(hataMetni(t, e)))} data-testid="stok-csv-disa">
            <Download className="h-4 w-4" aria-hidden="true" />
            {t('stokPos.urun.csvDisa')}
          </Button>
        )}
        <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => setEtiket(true)} disabled={!seciliUrunler.length} data-testid="stok-etiket">
          <Printer className="h-4 w-4" aria-hidden="true" />
          {t('stokPos.urun.etiket', { sayi: seciliUrunler.length })}
        </Button>
        {yazabilir && meta.qr_menu && (
          <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => setMenuPencere(true)} data-testid="stok-menuden">
            <UtensilsCrossed className="h-4 w-4" aria-hidden="true" />
            {t('stokPos.urun.menudenAktar')}
          </Button>
        )}
        <Button size="sm" variant="ghost" onClick={() => void yukle()} aria-label={t('stokPos.yenile')}>
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
      {yazabilir && <p className="text-xs text-muted-foreground">{t('stokPos.urun.csvIpucu')}</p>}
      {bilgi && (
        <p className="rounded-lg border border-emerald-400/30 bg-emerald-500/10 p-2 text-sm text-emerald-100" role="status" data-testid="stok-bilgi">
          {bilgi}
        </p>
      )}
      {hata && (
        <p className="text-sm text-red-300" role="alert">
          {hata}
        </p>
      )}
      {!veri ? (
        <Yukleniyor />
      ) : !veri.items.length ? (
        <Bos>{t('stokPos.urun.yok')}</Bos>
      ) : (
        <div className={`${KART} overflow-hidden`}>
          <div className="flex items-center gap-2 border-b border-white/10 px-3 py-2 text-xs text-muted-foreground">
            <input
              type="checkbox"
              className="h-4 w-4 accent-purple-500"
              checked={hepsiSecili}
              onChange={(e) => setSecili(e.target.checked ? new Set(veri.items.map((u) => u.id)) : new Set())}
              aria-label={t('stokPos.urun.hepsiniSec')}
              data-testid="stok-hepsini-sec"
            />
            <span>{t('stokPos.urun.toplam', { sayi: veri.toplam })}</span>
            <span className="ms-auto">{t('stokPos.urun.sinir', { sayi: meta.sayilar.urun, sinir: meta.sinirlar.urun })}</span>
          </div>
          <ul className="divide-y divide-white/5">
            {veri.items.map((u) => (
              <li key={u.id} className={`flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2.5 ${u.aktif ? '' : 'opacity-60'}`} data-testid="stok-urun-satir" data-urun-id={u.id}>
                <input
                  type="checkbox"
                  className="h-4 w-4 flex-none accent-purple-500"
                  checked={secili.has(u.id)}
                  onChange={(e) => {
                    const s = new Set(secili);
                    if (e.target.checked) s.add(u.id);
                    else s.delete(u.id);
                    setSecili(s);
                  }}
                  aria-label={u.ad}
                />
                <div className="min-w-0 flex-1 basis-40">
                  <p className="flex flex-wrap items-center gap-1.5 text-sm font-medium">
                    <span className="truncate">{u.ad}</span>
                    {u.kritik && (
                      <Rozet renk="border-amber-400/40 bg-amber-500/15 text-amber-200" testid="stok-kritik">
                        <AlertTriangle className="h-3 w-3" aria-hidden="true" />
                        {t('stokPos.urun.kritik')}
                      </Rozet>
                    )}
                    {u.ana_urun_id && <Rozet>{t('stokPos.urun.varyant')}</Rozet>}
                    {u.menu_urun_id && (
                      <Rozet renk="border-sky-400/30 bg-sky-500/10 text-sky-200">
                        <Link2 className="h-3 w-3" aria-hidden="true" />
                        {t('stokPos.urun.qrBagli')}
                      </Rozet>
                    )}
                    {!u.aktif && <Rozet>{t('stokPos.urun.pasif')}</Rozet>}
                  </p>
                  <p className="font-mono text-xs text-muted-foreground" dir="ltr">
                    {u.barkod}
                    {u.sku ? ` · ${u.sku}` : ''}
                    {u.kategori ? ` · ${u.kategori}` : ''}
                  </p>
                </div>
                <div className="text-end text-sm">
                  <p className="font-semibold tabular-nums">{para(u.satis_fiyati, pb, dil)}</p>
                  {u.alis_fiyati !== undefined && <p className="text-xs text-muted-foreground">{t('stokPos.urun.maliyetKisa', { tutar: para(u.alis_fiyati, pb, dil) })}</p>}
                </div>
                <div className="w-24 text-end text-sm tabular-nums" data-testid="stok-urun-stok">
                  {u.stok_takibi ? (
                    <span className={u.stok.toplam < 0 ? 'text-red-300' : u.kritik ? 'text-amber-300' : ''}>
                      {miktarYaz(u.stok.toplam, dil)} {t(`stokPos.birim.${u.birim}`)}
                    </span>
                  ) : (
                    <span className="text-xs text-muted-foreground">{t('stokPos.urun.stoksuz')}</span>
                  )}
                </div>
                {yazabilir && (
                  <div className="flex gap-0.5">
                    <Button size="icon" variant="ghost" className="h-8 w-8" onClick={() => setForm(u)} aria-label={t('stokPos.duzenle')} data-testid="stok-urun-duzenle">
                      <Pencil className="h-4 w-4" aria-hidden="true" />
                    </Button>
                    {!u.ana_urun_id && (
                      <Button size="icon" variant="ghost" className="h-8 w-8" onClick={() => setVaryantIcin(u)} aria-label={t('stokPos.urun.varyantEkle')}>
                        <Shapes className="h-4 w-4" aria-hidden="true" />
                      </Button>
                    )}
                    <Button size="icon" variant="ghost" className="h-8 w-8 text-red-300" onClick={() => void sil(u)} aria-label={t('stokPos.sil')}>
                      <Trash2 className="h-4 w-4" aria-hidden="true" />
                    </Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
      {form && (
        <UrunFormu
          api={api}
          meta={meta}
          urun={form === 'yeni' ? null : form}
          onKapat={() => setForm(null)}
          onKaydedildi={() => {
            setForm(null);
            void yukle();
            onMeta();
          }}
        />
      )}
      {varyantIcin && (
        <VaryantFormu
          api={api}
          ana={varyantIcin}
          onKapat={() => setVaryantIcin(null)}
          onKaydedildi={() => {
            setVaryantIcin(null);
            void yukle();
            onMeta();
          }}
        />
      )}
      {menuPencere && (
        <MenudenAktar
          api={api}
          onKapat={() => setMenuPencere(false)}
          onBitti={(m) => {
            setMenuPencere(false);
            setBilgi(m);
            void yukle();
            onMeta();
          }}
        />
      )}
      {etiket && (
        <Suspense fallback={null}>
          <Etiketler urunler={seciliUrunler} paraBirimi={pb} onKapat={() => setEtiket(false)} />
        </Suspense>
      )}
    </div>
  );
}

const tlMetni = (kurus: number | undefined) => (kurus === undefined ? '' : (kurus / 100).toFixed(2).replace('.', ','));

function UrunFormu({ api, meta, urun, onKapat, onKaydedildi }: { api: StokApi; meta: Meta; urun: Urun | null; onKapat: () => void; onKaydedildi: () => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [g, setG] = useState({
    ad: urun?.ad || '',
    barkod: urun?.barkod || '',
    sku: urun?.sku || '',
    kategori: urun?.kategori || '',
    birim: urun?.birim || 'adet',
    alis: tlMetni(urun?.alis_fiyati),
    satis: tlMetni(urun?.satis_fiyati),
    kdv: String(urun?.kdv_orani ?? meta.ayarlar.varsayilan_kdv),
    kritik: urun?.kritik_esik !== null && urun?.kritik_esik !== undefined ? String(urun.kritik_esik) : '',
    stok_takibi: urun?.stok_takibi ?? true,
    baslangic: '',
    notlar: urun?.notlar || '',
    aktif: urun?.aktif ?? true,
  });
  const [mesgul, setMesgul] = useState(false);
  const [hata, setHata] = useState<string | null>(null);
  const kaydet = async () => {
    setMesgul(true);
    setHata(null);
    const govde: Record<string, unknown> = {
      ad: g.ad,
      barkod: g.barkod.trim() || null,
      sku: g.sku.trim() || null,
      kategori: g.kategori.trim() || null,
      birim: g.birim,
      alis_fiyati: g.alis.trim() || 0,
      satis_fiyati: g.satis.trim(),
      kdv_orani: Number(g.kdv),
      kritik_esik: g.kritik.trim() ? sayiCevir(g.kritik) : null,
      stok_takibi: g.stok_takibi,
      notlar: g.notlar.trim() || null,
    };
    try {
      if (urun) await api.urunGuncelle(urun.id, { ...govde, aktif: g.aktif });
      else await api.urunEkle({ ...govde, baslangic_stok: g.baslangic.trim() ? sayiCevir(g.baslangic) : undefined });
      onKaydedildi();
    } catch (e) {
      setHata(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };
  const uret = async () => {
    try {
      setG({ ...g, barkod: (await api.barkodUret()).barkod });
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  };
  const satisKurus = kurusaCevir(g.satis);
  const alisKurus = kurusaCevir(g.alis) || 0;
  const oran = Number(g.kdv) || 0;
  const matrah = satisKurus !== null ? satisKurus - Math.round((satisKurus * oran) / (100 + oran)) : null;
  return (
    <Pencere baslik={urun ? t('stokPos.urun.duzenleBaslik') : t('stokPos.urun.yeni')} onKapat={onKapat} genis testid="stok-urun-form">
      <div className="grid gap-3 sm:grid-cols-2">
        <Alan etiket={t('stokPos.urun.ad')} className="sm:col-span-2">
          <input className={GIRDI} value={g.ad} onChange={(e) => setG({ ...g, ad: e.target.value })} maxLength={160} data-testid="stok-form-ad" />
        </Alan>
        <Alan etiket={t('stokPos.urun.barkod')} ipucu={t('stokPos.urun.barkodIpucu')}>
          <div className="flex gap-1.5">
            <input className={cn(GIRDI, 'font-mono')} dir="ltr" value={g.barkod} onChange={(e) => setG({ ...g, barkod: e.target.value })} maxLength={32} data-testid="stok-form-barkod" />
            <Button type="button" size="sm" variant="outline" className={`${DIS_DUGME} h-10`} onClick={() => void uret()}>
              {t('stokPos.urun.uret')}
            </Button>
          </div>
        </Alan>
        <Alan etiket={t('stokPos.urun.sku')}>
          <input className={GIRDI} dir="ltr" value={g.sku} onChange={(e) => setG({ ...g, sku: e.target.value })} maxLength={64} />
        </Alan>
        <Alan etiket={t('stokPos.urun.kategori')}>
          <input className={GIRDI} value={g.kategori} onChange={(e) => setG({ ...g, kategori: e.target.value })} maxLength={80} />
        </Alan>
        <Alan etiket={t('stokPos.urun.birim')}>
          <select className={SECIM} value={g.birim} onChange={(e) => setG({ ...g, birim: e.target.value as Urun['birim'] })} data-testid="stok-form-birim">
            {meta.birimler.map((b) => (
              <option key={b} value={b}>
                {t(`stokPos.birim.${b}`)}
              </option>
            ))}
          </select>
        </Alan>
        <Alan etiket={t('stokPos.urun.satisFiyati')} ipucu={t('stokPos.urun.satisIpucu')}>
          <input className={GIRDI} inputMode="decimal" value={g.satis} onChange={(e) => setG({ ...g, satis: e.target.value })} data-testid="stok-form-satis" />
        </Alan>
        <Alan etiket={t('stokPos.urun.kdv')}>
          <select className={SECIM} value={g.kdv} onChange={(e) => setG({ ...g, kdv: e.target.value })} data-testid="stok-form-kdv">
            {meta.ayarlar.kdv_oranlari.map((o) => (
              <option key={o} value={o}>
                %{o}
              </option>
            ))}
          </select>
        </Alan>
        <Alan etiket={t('stokPos.urun.alisFiyati')} ipucu={t('stokPos.urun.alisIpucu')}>
          <input className={GIRDI} inputMode="decimal" value={g.alis} onChange={(e) => setG({ ...g, alis: e.target.value })} data-testid="stok-form-alis" />
        </Alan>
        <div className="self-end pb-2 text-xs text-muted-foreground">
          {matrah !== null &&
            t('stokPos.urun.marjOnizleme', {
              matrah: para(matrah, meta.ayarlar.para_birimi, dil),
              kar: para(matrah - alisKurus, meta.ayarlar.para_birimi, dil),
            })}
        </div>
        <Alan etiket={t('stokPos.urun.kritikEsik')} ipucu={t('stokPos.urun.kritikIpucu')}>
          <input className={GIRDI} inputMode="decimal" value={g.kritik} onChange={(e) => setG({ ...g, kritik: e.target.value })} data-testid="stok-form-kritik" />
        </Alan>
        {!urun && (
          <Alan etiket={t('stokPos.urun.baslangicStok')}>
            <input className={GIRDI} inputMode="decimal" value={g.baslangic} onChange={(e) => setG({ ...g, baslangic: e.target.value })} data-testid="stok-form-baslangic" />
          </Alan>
        )}
        <Alan etiket={t('stokPos.urun.notlar')} className="sm:col-span-2">
          <textarea className={METIN_ALANI} value={g.notlar} onChange={(e) => setG({ ...g, notlar: e.target.value })} maxLength={1000} />
        </Alan>
        <div className="space-y-2 sm:col-span-2">
          <Anahtar acik={g.stok_takibi} onDegis={(v) => setG({ ...g, stok_takibi: v })} etiket={t('stokPos.urun.stokTakibi')} />
          {urun && <Anahtar acik={g.aktif} onDegis={(v) => setG({ ...g, aktif: v })} etiket={t('stokPos.urun.aktif')} />}
        </div>
      </div>
      {hata && (
        <p className="mt-3 text-sm text-red-300" role="alert" data-testid="stok-form-hata">
          {hata}
        </p>
      )}
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="ghost" onClick={onKapat}>
          {t('stokPos.vazgec')}
        </Button>
        <Button onClick={() => void kaydet()} disabled={mesgul || !g.ad.trim() || satisKurus === null} data-testid="stok-form-kaydet">
          {t('stokPos.kaydet')}
        </Button>
      </div>
    </Pencere>
  );
}

function VaryantFormu({ api, ana, onKapat, onKaydedildi }: { api: StokApi; ana: Urun; onKapat: () => void; onKaydedildi: () => void }) {
  const { t } = useTranslation();
  const [beden, setBeden] = useState('');
  const [renk, setRenk] = useState('');
  const [barkod, setBarkod] = useState('');
  const [fiyat, setFiyat] = useState('');
  const [hata, setHata] = useState<string | null>(null);
  const kaydet = async () => {
    try {
      await api.varyantEkle(ana.id, { varyant: { beden, renk }, barkod: barkod.trim() || null, satis_fiyati: fiyat.trim() || null });
      onKaydedildi();
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  };
  return (
    <Pencere baslik={t('stokPos.urun.varyantBaslik', { ad: ana.ad })} onKapat={onKapat}>
      <p className="mb-3 text-xs text-muted-foreground">{t('stokPos.urun.varyantIpucu')}</p>
      <div className="grid grid-cols-2 gap-2">
        <Alan etiket={t('stokPos.urun.beden')}>
          <input className={GIRDI} value={beden} onChange={(e) => setBeden(e.target.value)} maxLength={40} />
        </Alan>
        <Alan etiket={t('stokPos.urun.renk')}>
          <input className={GIRDI} value={renk} onChange={(e) => setRenk(e.target.value)} maxLength={40} />
        </Alan>
        <Alan etiket={t('stokPos.urun.barkod')}>
          <input className={cn(GIRDI, 'font-mono')} dir="ltr" value={barkod} onChange={(e) => setBarkod(e.target.value)} placeholder={t('stokPos.urun.otomatik')} />
        </Alan>
        <Alan etiket={t('stokPos.urun.satisFiyati')}>
          <input className={GIRDI} inputMode="decimal" value={fiyat} onChange={(e) => setFiyat(e.target.value)} placeholder={tlMetni(ana.satis_fiyati)} />
        </Alan>
      </div>
      {hata && <p className="mt-2 text-sm text-red-300">{hata}</p>}
      <div className="mt-4 flex justify-end">
        <Button onClick={() => void kaydet()} disabled={!beden.trim() && !renk.trim()}>
          <Tags className="h-4 w-4" aria-hidden="true" />
          {t('stokPos.urun.varyantEkle')}
        </Button>
      </div>
    </Pencere>
  );
}

function MenudenAktar({ api, onKapat, onBitti }: { api: StokApi; onKapat: () => void; onBitti: (mesaj: string) => void }) {
  const { t } = useTranslation();
  const [liste, setListe] = useState<{ id: number; ad: string; duzen: string; urun: number; bagli: number }[] | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  useEffect(() => {
    api
      .menuKaynaklari()
      .then((r) => setListe(r.items))
      .catch((e) => setHata(hataMetni(t, e)));
  }, [api, t]);
  const aktar = async (id: number) => {
    try {
      const r = await api.menudenAktar(id);
      onBitti(t('stokPos.urun.menudenAktarildi', { eklenen: r.eklenen, guncellenen: r.guncellenen }));
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  };
  return (
    <Pencere baslik={t('stokPos.urun.menudenAktar')} onKapat={onKapat}>
      <p className="mb-3 text-sm text-muted-foreground">{t('stokPos.urun.menuAciklama')}</p>
      {!liste ? (
        <Yukleniyor />
      ) : !liste.length ? (
        <Bos>{t('stokPos.urun.menuYok')}</Bos>
      ) : (
        <ul className="divide-y divide-white/5">
          {liste.map((m) => (
            <li key={m.id} className="flex items-center gap-2 py-2 text-sm">
              <span className="min-w-0 flex-1">
                {m.ad}
                <span className="block text-xs text-muted-foreground">{t('stokPos.urun.menuSayilar', { urun: m.urun, bagli: m.bagli })}</span>
              </span>
              <Button size="sm" onClick={() => void aktar(m.id)}>
                {t('stokPos.urun.aktar')}
              </Button>
            </li>
          ))}
        </ul>
      )}
      {hata && <p className="mt-2 text-sm text-red-300">{hata}</p>}
    </Pencere>
  );
}
