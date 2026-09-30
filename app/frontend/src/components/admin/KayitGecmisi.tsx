import { Fragment, useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { ChevronDown, ChevronRight, Filter, Loader2, RefreshCw, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  denetimListesi,
  denetimOzeti,
  filtreSecenekleri,
  goreliZaman,
  islemRengi,
  tamZaman,
  type DenetimFiltresi,
  type DenetimOzeti,
  type DenetimSatiri,
  type FiltreSecenekleri,
} from '@/lib/denetim';

/**
 * Yönetici paneli › Kayıt geçmişi (denetim kaydı).
 *
 * "Kim, ne zaman, hangi kaydı, neyi değiştirdi" sorusunun cevabı. Satırlar
 * arka uçta her veritabanı yazımından kendiliğinden düşüyor; burada
 * yalnız okunuyor. Satır açılınca alan bazında eski → yeni farkı görünüyor
 * (gizli alanlar "***" olarak gelir). Müşteri sitesine yapılan bakım
 * erişimleri ayrı: Müşteri siteleri › günlük.
 */

const ADET = 50;
const BOS_FILTRE: DenetimFiltresi = { aktor: '', tablo: '', islem: '', baslangic: '', bitis: '' };
const SECIM_SINIFI =
  'h-10 w-full rounded-md border border-white/10 bg-white/5 px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-purple-500/40';

function useTabloAdi() {
  const { t } = useTranslation();
  return (ad: string) => t(`denetim.tablo.${ad}`, { defaultValue: ad });
}

function Deger({ deger }: { deger: unknown }) {
  const { t } = useTranslation();
  if (deger === null || deger === undefined || deger === '') {
    return <span className="italic text-muted-foreground">{t('denetim.fark.bos')}</span>;
  }
  if (deger === '***') {
    return (
      <span className="rounded border border-white/10 bg-white/5 px-1.5 py-0.5 text-[11px] text-muted-foreground">
        {t('denetim.fark.gizli')}
      </span>
    );
  }
  if (typeof deger === 'boolean') {
    return <span>{deger ? t('denetim.fark.evet') : t('denetim.fark.hayir')}</span>;
  }
  const metin = typeof deger === 'object' ? JSON.stringify(deger) : String(deger);
  return <span className="break-all">{metin}</span>;
}

function FarkTablosu({ satir }: { satir: DenetimSatiri }) {
  const { t } = useTranslation();
  const alanlar = Object.entries(satir.degisiklik ?? {});
  return (
    <div className="space-y-3">
      {alanlar.length === 0 ? (
        <p className="text-xs text-muted-foreground">{t('denetim.fark.yok')}</p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-white/10">
          <table className="w-full text-left text-xs">
            <thead className="text-muted-foreground">
              <tr className="border-b border-white/10">
                <th className="px-3 py-2 font-medium">{t('denetim.fark.alan')}</th>
                <th className="px-3 py-2 font-medium">{t('denetim.fark.eski')}</th>
                <th className="px-3 py-2 font-medium">{t('denetim.fark.yeni')}</th>
              </tr>
            </thead>
            <tbody>
              {alanlar.map(([alan, [eski, yeni]]) => (
                <tr key={alan} className="border-b border-white/5 last:border-0 align-top">
                  <td className="whitespace-nowrap px-3 py-2 font-mono text-[11px] text-foreground/80">{alan}</td>
                  <td className="px-3 py-2 text-red-300/90">
                    <Deger deger={eski} />
                  </td>
                  <td className="px-3 py-2 text-emerald-300/90">
                    <Deger deger={yeni} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <dl className="flex flex-wrap gap-x-6 gap-y-1 text-[11px] text-muted-foreground">
        {satir.istek_yolu && (
          <div>
            <dt className="inline">{t('denetim.fark.istek')}: </dt>
            <dd className="inline font-mono">{satir.istek_yolu}</dd>
          </div>
        )}
        {satir.ip_ozeti && (
          <div>
            <dt className="inline">{t('denetim.fark.ip')}: </dt>
            <dd className="inline font-mono">{satir.ip_ozeti}</dd>
          </div>
        )}
      </dl>
    </div>
  );
}

function Kisi({ satir }: { satir: DenetimSatiri }) {
  const { t } = useTranslation();
  const rol = t(`denetim.rol.${satir.aktor_rol || 'sistem'}`, { defaultValue: satir.aktor_rol || '' });
  return (
    <span className="block min-w-0">
      <span className="block break-all">{satir.aktor_eposta || rol}</span>
      {satir.aktor_eposta && <span className="block text-[11px] text-muted-foreground">{rol}</span>}
    </span>
  );
}

function IslemRozeti({ islem }: { islem: string }) {
  const { t } = useTranslation();
  return (
    <span className={`inline-block whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-medium ${islemRengi(islem)}`}>
      {t(`denetim.islem.${islem}`, { defaultValue: islem })}
    </span>
  );
}

function OzetKartlari({ ozet }: { ozet: DenetimOzeti | null }) {
  const { t } = useTranslation();
  const tabloAdi = useTabloAdi();
  if (!ozet) return null;
  const enTablo = ozet.tablolar[0];
  const enKisi = ozet.aktorler[0];
  const kisiAdi = (ad: string) => (ad.includes('@') ? ad : t(`denetim.rol.${ad}`, { defaultValue: ad }));
  const kart = 'cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-4';
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <div className={kart}>
        <p className="text-[11px] uppercase tracking-widest text-muted-foreground">{t('denetim.ozet.toplam')}</p>
        <p className="mt-1 text-2xl font-semibold">{ozet.toplam}</p>
        <p className="text-[11px] text-muted-foreground">{t('denetim.ozet.sure', { sayi: ozet.gun })}</p>
      </div>
      <div className={kart}>
        <p className="text-[11px] uppercase tracking-widest text-muted-foreground">{t('denetim.ozet.enCokTablo')}</p>
        <p className="mt-1 truncate text-lg font-semibold">{enTablo ? tabloAdi(enTablo.ad) : '—'}</p>
        {enTablo && <p className="text-[11px] text-muted-foreground">{t('denetim.ozet.islemSayisi', { sayi: enTablo.sayi })}</p>}
      </div>
      <div className={kart}>
        <p className="text-[11px] uppercase tracking-widest text-muted-foreground">{t('denetim.ozet.enAktif')}</p>
        <p className="mt-1 truncate text-lg font-semibold" title={enKisi?.ad}>
          {enKisi ? kisiAdi(enKisi.ad) : '—'}
        </p>
        {enKisi && <p className="text-[11px] text-muted-foreground">{t('denetim.ozet.islemSayisi', { sayi: enKisi.sayi })}</p>}
      </div>
      <div className={kart}>
        <p className="text-[11px] uppercase tracking-widest text-muted-foreground">{t('denetim.ozet.dagilim')}</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {ozet.islemler.length === 0 ? (
            <span className="text-sm text-muted-foreground">—</span>
          ) : (
            ozet.islemler.map((i) => (
              <span key={i.ad} className={`rounded-full border px-2 py-0.5 text-[11px] ${islemRengi(i.ad)}`}>
                {t(`denetim.islem.${i.ad}`, { defaultValue: i.ad })} · {i.sayi}
              </span>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

export default function KayitGecmisi() {
  const { t, i18n } = useTranslation();
  const tabloAdi = useTabloAdi();
  const dil = i18n.language;

  const [taslak, setTaslak] = useState<DenetimFiltresi>(BOS_FILTRE);
  const [filtre, setFiltre] = useState<DenetimFiltresi>(BOS_FILTRE);
  const [satirlar, setSatirlar] = useState<DenetimSatiri[]>([]);
  const [toplam, setToplam] = useState(0);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [dahaYukleniyor, setDahaYukleniyor] = useState(false);
  const [acik, setAcik] = useState<number | null>(null);
  const [ozet, setOzet] = useState<DenetimOzeti | null>(null);
  const [secenekler, setSecenekler] = useState<FiltreSecenekleri>({ tablolar: [], islemler: [], roller: [] });
  const istekNo = useRef(0);

  const yukle = useCallback(async () => {
    const no = ++istekNo.current;
    setYukleniyor(true);
    try {
      const liste = await denetimListesi(filtre, 0, ADET);
      if (no !== istekNo.current) return;
      setSatirlar(liste.items);
      setToplam(liste.total);
      setAcik(null);
    } catch {
      if (no === istekNo.current) toast.error(t('denetim.hata'));
    } finally {
      if (no === istekNo.current) setYukleniyor(false);
    }
  }, [filtre, t]);

  const yanYukle = useCallback(async () => {
    try {
      const [o, s] = await Promise.all([denetimOzeti(), filtreSecenekleri()]);
      setOzet(o);
      setSecenekler(s);
    } catch {
      /* özet ve seçenekler olmadan da liste çalışır */
    }
  }, []);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  useEffect(() => {
    void yanYukle();
  }, [yanYukle]);

  const dahaFazla = async () => {
    setDahaYukleniyor(true);
    try {
      const liste = await denetimListesi(filtre, satirlar.length, ADET);
      setSatirlar((onceki) => {
        const gorulen = new Set(onceki.map((s) => s.id));
        return [...onceki, ...liste.items.filter((s) => !gorulen.has(s.id))];
      });
      setToplam(liste.total);
    } catch {
      toast.error(t('denetim.hata'));
    } finally {
      setDahaYukleniyor(false);
    }
  };

  const uygula = (o?: FormEvent) => {
    o?.preventDefault();
    setFiltre({ ...taslak });
  };

  const temizle = () => {
    setTaslak(BOS_FILTRE);
    setFiltre(BOS_FILTRE);
  };

  const secimDegisti = (alan: keyof DenetimFiltresi, deger: string) => {
    const yeni = { ...taslak, [alan]: deger };
    setTaslak(yeni);
    // Seçim kutuları ve tarihler hemen uygulanıyor; metin kutusu Enter/Filtrele ile.
    setFiltre((f) => ({ ...f, [alan]: deger }));
  };

  const filtreVar = Object.values(filtre).some((d) => (d ?? '').toString().trim() !== '');
  const kayitEtiketi = (s: DenetimSatiri) => `${tabloAdi(s.tablo)}${s.kayit_id ? ` #${s.kayit_id}` : ''}`;

  return (
    <div className="space-y-5">
      <OzetKartlari ozet={ozet} />

      <div className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6">
        <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h3 className="text-lg font-semibold">{t('denetim.baslik')}</h3>
            <p className="mt-1 max-w-2xl text-xs text-muted-foreground">{t('denetim.aciklama')}</p>
          </div>
          <Button
            variant="outline"
            size="icon"
            onClick={() => {
              void yukle();
              void yanYukle();
            }}
            aria-label={t('denetim.yenile')}
          >
            <RefreshCw className={`h-4 w-4 ${yukleniyor ? 'animate-spin' : ''}`} aria-hidden="true" />
          </Button>
        </div>

        {/* Filtre çubuğu */}
        <form onSubmit={uygula} className="mb-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
          <label className="block lg:col-span-2">
            <span className="mb-1 block text-[11px] uppercase tracking-widest text-muted-foreground">
              {t('denetim.filtre.kisi')}
            </span>
            <Input
              value={taslak.aktor ?? ''}
              onChange={(o) => setTaslak({ ...taslak, aktor: o.target.value })}
              placeholder={t('denetim.filtre.kisiOrnek')}
              className="bg-white/5 border-white/10"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-[11px] uppercase tracking-widest text-muted-foreground">
              {t('denetim.filtre.tablo')}
            </span>
            <select
              value={taslak.tablo ?? ''}
              onChange={(o) => secimDegisti('tablo', o.target.value)}
              className={SECIM_SINIFI}
            >
              <option value="" className="bg-background">{t('denetim.filtre.hepsi')}</option>
              {secenekler.tablolar.map((ad) => (
                <option key={ad} value={ad} className="bg-background">
                  {tabloAdi(ad)}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-[11px] uppercase tracking-widest text-muted-foreground">
              {t('denetim.filtre.islem')}
            </span>
            <select
              value={taslak.islem ?? ''}
              onChange={(o) => secimDegisti('islem', o.target.value)}
              className={SECIM_SINIFI}
            >
              <option value="" className="bg-background">{t('denetim.filtre.hepsi')}</option>
              {(secenekler.islemler.length ? secenekler.islemler : ['olustur', 'guncelle', 'sil']).map((ad) => (
                <option key={ad} value={ad} className="bg-background">
                  {t(`denetim.islem.${ad}`, { defaultValue: ad })}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-[11px] uppercase tracking-widest text-muted-foreground">
              {t('denetim.filtre.baslangic')}
            </span>
            <Input
              type="date"
              value={taslak.baslangic ?? ''}
              max={taslak.bitis || undefined}
              onChange={(o) => secimDegisti('baslangic', o.target.value)}
              className="bg-white/5 border-white/10"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-[11px] uppercase tracking-widest text-muted-foreground">
              {t('denetim.filtre.bitis')}
            </span>
            <Input
              type="date"
              value={taslak.bitis ?? ''}
              min={taslak.baslangic || undefined}
              onChange={(o) => secimDegisti('bitis', o.target.value)}
              className="bg-white/5 border-white/10"
            />
          </label>
          <div className="flex flex-wrap items-center gap-2 sm:col-span-2 lg:col-span-6">
            <Button type="submit" variant="outline" className="gap-2">
              <Filter className="h-4 w-4" aria-hidden="true" />
              {t('denetim.filtre.uygula')}
            </Button>
            {filtreVar && (
              <Button type="button" variant="ghost" onClick={temizle} className="gap-2">
                <X className="h-4 w-4" aria-hidden="true" />
                {t('denetim.filtre.temizle')}
              </Button>
            )}
            <span className="ms-auto text-xs text-muted-foreground" data-testid="denetim-sayac">
              {t('denetim.gosterilen', { sayi: satirlar.length, toplam })}
            </span>
          </div>
        </form>

        {yukleniyor && satirlar.length === 0 ? (
          <div className="flex justify-center py-10 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
          </div>
        ) : satirlar.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">{t('denetim.bos')}</p>
        ) : (
          <>
            {/* Geniş ekran: tablo */}
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full text-left text-sm">
                <thead className="text-xs text-muted-foreground">
                  <tr className="border-b border-white/10">
                    <th className="w-6 py-2" aria-hidden="true" />
                    <th className="py-2 pr-4 font-medium">{t('denetim.sutun.zaman')}</th>
                    <th className="py-2 pr-4 font-medium">{t('denetim.sutun.kisi')}</th>
                    <th className="py-2 pr-4 font-medium">{t('denetim.sutun.islem')}</th>
                    <th className="py-2 pr-4 font-medium">{t('denetim.sutun.kayit')}</th>
                    <th className="py-2 font-medium">{t('denetim.sutun.ozet')}</th>
                  </tr>
                </thead>
                <tbody>
                  {satirlar.map((s) => {
                    const acikMi = acik === s.id;
                    return (
                      <Fragment key={s.id}>
                        <tr
                          onClick={() => setAcik(acikMi ? null : s.id)}
                          className={`cursor-pointer border-b border-white/5 align-top hover:bg-white/[0.04] ${acikMi ? 'bg-white/[0.04]' : ''}`}
                          aria-expanded={acikMi}
                          data-testid="denetim-satiri"
                        >
                          <td className="py-2.5 text-muted-foreground">
                            {acikMi ? (
                              <ChevronDown className="h-4 w-4" aria-hidden="true" />
                            ) : (
                              <ChevronRight className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
                            )}
                          </td>
                          <td className="whitespace-nowrap py-2.5 pr-4 text-xs">
                            <span className="block">{goreliZaman(s.created_at, dil)}</span>
                            <span className="block text-[11px] text-muted-foreground">{tamZaman(s.created_at, dil)}</span>
                          </td>
                          <td className="max-w-[16rem] py-2.5 pr-4 text-xs">
                            <Kisi satir={s} />
                          </td>
                          <td className="py-2.5 pr-4">
                            <IslemRozeti islem={s.islem} />
                          </td>
                          <td className="whitespace-nowrap py-2.5 pr-4 text-xs">{kayitEtiketi(s)}</td>
                          <td className="py-2.5 text-xs text-muted-foreground">
                            <span className="line-clamp-2 break-all">{s.ozet || '—'}</span>
                          </td>
                        </tr>
                        {acikMi && (
                          <tr className="border-b border-white/5">
                            <td />
                            <td colSpan={5} className="pb-4 pt-1">
                              <FarkTablosu satir={s} />
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Mobil: kartlar */}
            <ul className="space-y-3 md:hidden">
              {satirlar.map((s) => {
                const acikMi = acik === s.id;
                return (
                  <li key={s.id} className="rounded-xl border border-white/10 bg-white/[0.02]">
                    <button
                      type="button"
                      onClick={() => setAcik(acikMi ? null : s.id)}
                      className="w-full space-y-2 p-4 text-start"
                      aria-expanded={acikMi}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <IslemRozeti islem={s.islem} />
                        <span className="text-[11px] text-muted-foreground" title={tamZaman(s.created_at, dil)}>
                          {goreliZaman(s.created_at, dil)}
                        </span>
                      </div>
                      <p className="text-sm font-medium">{kayitEtiketi(s)}</p>
                      {s.ozet && <p className="break-all text-xs text-muted-foreground">{s.ozet}</p>}
                      <div className="text-xs">
                        <Kisi satir={s} />
                      </div>
                    </button>
                    {acikMi && (
                      <div className="border-t border-white/10 p-4">
                        <p className="mb-2 text-[11px] text-muted-foreground">{tamZaman(s.created_at, dil)}</p>
                        <FarkTablosu satir={s} />
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>

            {satirlar.length < toplam && (
              <div className="mt-5 flex justify-center">
                <Button variant="outline" onClick={() => void dahaFazla()} disabled={dahaYukleniyor} className="gap-2">
                  {dahaYukleniyor && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
                  {t('denetim.dahaFazla')}
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
