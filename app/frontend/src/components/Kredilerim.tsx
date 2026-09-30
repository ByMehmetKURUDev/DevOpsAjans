import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Coins, ExternalLink, Loader2, RefreshCw, ShoppingCart } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { fiyatlandirmaApi } from '@/api/fiyatlandirma';
import { KREDI_PAKETLERI } from '@/lib/krediPaketleri';
import {
  kalanGun,
  kredilerimiGetir,
  saatBicimle,
  sonKullanmaRengi,
  tarihBicimle,
  turRengi,
  type Kredilerim as KredilerimVerisi,
} from '@/lib/kredi';

/**
 * Müşteri paneli › Kredilerim.
 *
 * Büyük bakiye göstergesi, yaklaşan son kullanmalar ve hareket listesi.
 * Veri jetondaki e-postaya göre sunucuda süzülüyor; açılışta süresi geçmiş
 * krediler de sunucuda işleniyor. "Kredi al" sitedeki Kullandıkça Öde
 * akışının aynısını çağırıyor (`/fiyat-satin-al`, `kredi_paketi`) ve ödeme
 * sayfasına geçiyor; tutar sunucudaki paket tablosundan geliyor.
 */

/** Uyarı eşiği: son kullanmasına bu kadar gün kalan kredi öne çıkıyor. */
const UYARI_GUN = 30;

export default function Kredilerim({ eposta, ad }: { eposta?: string; ad?: string }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const saat = (n: number) => saatBicimle(n, dil);

  const [veri, setVeri] = useState<KredilerimVerisi | null>(null);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [hata, setHata] = useState(false);
  const [paket, setPaket] = useState<number>(KREDI_PAKETLERI.find((p) => p.populer)?.kredi ?? 25);
  const [aliniyor, setAliniyor] = useState(false);

  const yukle = useCallback(async () => {
    setYukleniyor(true);
    setHata(false);
    try {
      setVeri(await kredilerimiGetir());
    } catch {
      setHata(true);
    } finally {
      setYukleniyor(false);
    }
  }, []);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const krediAl = async () => {
    if (!eposta || aliniyor) return;
    setAliniyor(true);
    try {
      const sonuc = await fiyatlandirmaApi.satinAl({
        kredi_paketi: paket,
        musteri_eposta: eposta,
        musteri_adi: ad || undefined,
      });
      window.location.assign(sonuc.adres);
    } catch {
      toast.error(t('kredi.musteri.satinAlHata'));
      setAliniyor(false);
    }
  };

  const bakiye = veri?.bakiye ?? 0;
  const yakinlar = (veri?.yaklasan_son_kullanma ?? []).filter((k) => {
    const gun = kalanGun(k.tarih);
    return gun !== null && gun <= UYARI_GUN;
  });

  return (
    <div className="space-y-6" data-testid="kredilerim">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        {/* Bakiye */}
        <section className="cam-kart relative overflow-hidden rounded-2xl border border-white/10 bg-white/[0.03] p-6">
          <div className="flex items-start justify-between gap-3">
            <h3 className="flex items-center gap-2 text-lg font-semibold">
              <Coins className="h-5 w-5 text-emerald-400" aria-hidden="true" />
              {t('kredi.musteri.baslik')}
            </h3>
            <Button variant="outline" size="icon" onClick={() => void yukle()} aria-label={t('kredi.yenile')}>
              <RefreshCw className={`h-4 w-4 ${yukleniyor ? 'animate-spin' : ''}`} aria-hidden="true" />
            </Button>
          </div>

          {yukleniyor && !veri ? (
            <div className="flex justify-center py-10 text-muted-foreground">
              <Loader2 className="h-6 w-6 animate-spin" aria-hidden="true" />
            </div>
          ) : hata ? (
            <p className="py-6 text-sm text-red-300">{t('kredi.musteri.hata')}</p>
          ) : (
            <>
              <p className="mt-6 text-xs uppercase tracking-widest text-muted-foreground">{t('kredi.musteri.bakiye')}</p>
              <p className="mt-1 flex items-baseline gap-2">
                <span
                  className={`text-6xl font-bold tracking-tight ${bakiye < 0 ? 'text-red-300' : 'gradient-text'}`}
                  data-testid="kredilerim-bakiye"
                >
                  {saat(bakiye)}
                </span>
                <span className="text-lg text-muted-foreground">{t('kredi.musteri.saatBirim')}</span>
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                {t('kredi.musteri.krediYaklasik', { sayi: saat(Math.max(0, Math.floor(bakiye))) })}
              </p>
              {bakiye < 0 && <p className="mt-2 text-xs text-red-300">{t('kredi.musteri.borcNotu')}</p>}
              <p className="mt-4 max-w-prose text-xs leading-relaxed text-muted-foreground">
                {t('kredi.musteri.aciklama')}
              </p>

              {yakinlar.length > 0 && (
                <div
                  className="mt-5 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-100"
                  role="status"
                >
                  <p className="flex items-center gap-2 font-medium">
                    <AlertTriangle className="h-4 w-4" aria-hidden="true" />
                    {t('kredi.musteri.yaklasanBaslik')}
                  </p>
                  <ul className="mt-2 space-y-1 text-xs">
                    {yakinlar.map((k) => (
                      <li key={k.tarih}>
                        {t('kredi.musteri.yaklasanUyari', { saat: saat(k.miktar), tarih: tarihBicimle(k.tarih, dil) })}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {(veri?.yaklasan_son_kullanma.length ?? 0) > 0 && (
                <div className="mt-5">
                  <p className="text-xs uppercase tracking-widest text-muted-foreground">
                    {t('kredi.musteri.sonKullanmalar')}
                  </p>
                  <ul className="mt-2 space-y-1 text-sm">
                    {veri!.yaklasan_son_kullanma.map((k) => (
                      <li key={k.tarih} className="flex justify-between gap-4">
                        <span className={sonKullanmaRengi(kalanGun(k.tarih))}>{tarihBicimle(k.tarih, dil)}</span>
                        <span className="font-mono">{t('kredi.saatKisa', { deger: saat(k.miktar) })}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </section>

        {/* Kredi al */}
        <section className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6">
          <h3 className="flex items-center gap-2 text-lg font-semibold">
            <ShoppingCart className="h-5 w-5 text-purple-400" aria-hidden="true" />
            {t('kredi.musteri.krediAl')}
          </h3>
          <p className="mt-1 text-xs text-muted-foreground">{t('kredi.musteri.paketSec')}</p>
          <div className="mt-4 grid grid-cols-2 gap-2" role="radiogroup" aria-label={t('kredi.musteri.paketSec')}>
            {KREDI_PAKETLERI.map((p) => {
              const secili = p.kredi === paket;
              return (
                <button
                  key={p.kredi}
                  type="button"
                  role="radio"
                  aria-checked={secili}
                  onClick={() => setPaket(p.kredi)}
                  className={`cam-kart rounded-xl border p-3 text-left transition-colors ${
                    secili ? 'cam-secili border-emerald-500 ring-1 ring-emerald-500/30' : 'border-white/10 hover:border-white/20'
                  }`}
                >
                  <span className="block text-sm font-semibold">
                    {t('kredi.musteri.paket', { kredi: p.kredi })}
                    {p.bonus > 0 && (
                      <span className="text-emerald-400"> {t('kredi.musteri.bonus', { bonus: p.bonus })}</span>
                    )}
                  </span>
                  <span className="mt-1 block font-mono text-xs text-muted-foreground">
                    ${p.fiyat.toLocaleString('en-US')}
                  </span>
                </button>
              );
            })}
          </div>
          <Button className="mt-4 w-full" onClick={() => void krediAl()} disabled={!eposta || aliniyor} data-testid="kredi-al">
            {aliniyor ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" /> : null}
            {t('kredi.musteri.odemeyeGec')}
          </Button>
          <Link
            to="/services#kullandikca-ode"
            className="mt-3 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            {t('kredi.musteri.paketlereBak')}
            <ExternalLink className="h-3 w-3" aria-hidden="true" />
          </Link>
        </section>
      </div>

      {/* Hareketler */}
      <section className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6">
        <h3 className="mb-4 text-lg font-semibold">{t('kredi.musteri.hareketler')}</h3>
        {!veri || veri.hareketler.length === 0 ? (
          <p className="py-4 text-sm text-muted-foreground">
            {yukleniyor ? t('kredi.yukleniyor') : t('kredi.musteri.bos')}
          </p>
        ) : (
          <ol className="space-y-2" data-testid="kredilerim-hareketler">
            {veri.hareketler.map((h) => (
              <li
                key={h.id}
                className="flex flex-wrap items-center gap-3 rounded-xl border border-white/5 bg-white/[0.02] p-3"
              >
                <span className="w-24 shrink-0 text-xs text-muted-foreground">{tarihBicimle(h.created_at, dil)}</span>
                <span
                  className={`inline-block shrink-0 whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-medium ${turRengi(h.tur)}`}
                >
                  {t(`kredi.tur.${h.tur}`, { defaultValue: h.tur })}
                </span>
                <span className="min-w-0 flex-1 text-sm">{h.aciklama || '—'}</span>
                <span
                  className={`shrink-0 font-mono text-sm font-semibold ${h.miktar < 0 ? 'text-amber-300' : 'text-emerald-300'}`}
                >
                  {h.miktar > 0 ? '+' : ''}
                  {t('kredi.saatKisa', { deger: saat(h.miktar) })}
                </span>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
