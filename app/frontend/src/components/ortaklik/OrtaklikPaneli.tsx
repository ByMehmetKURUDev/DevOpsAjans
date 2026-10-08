import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { AlertTriangle, Copy, FileDown, HandCoins, Landmark, Loader2, RefreshCw } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { getAPIBaseURL } from '@/lib/config';
import { paraBicimle, tarihBicimle } from '@/lib/belge';
import { dekontumAdresi, hataMetni, ibanKaydet, odemeIste, ortakPanelim, type OrtakPaneli } from '@/lib/ortaklik';
import { Alan, GIRDI, KART, Rozet, SayiKarti } from './ortak';

/**
 * Faz 5K — müşteri paneli › Ortaklık (yalnız onaylı ortakta görünür; menüde "Hesabım" grubunda).
 *
 * Veri KİŞİYE ait (oturumdaki kişinin e-postası). Tıklama / aday / satış / kazanç / bakiye, referans kodu
 * ve paylaşım bağlantısı, komisyon defteri (müşteri e-postası maskeli), IBAN (yalnız biçim; kart numarası
 * kabul edilmez) ve para birimi başına ödeme talebi (onaylı bakiyenin tamamı, en az tutar ayardan).
 */
export default function OrtaklikPaneli() {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [veri, setVeri] = useState<OrtakPaneli | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [iban, setIban] = useState('');
  const [ibanAd, setIbanAd] = useState('');
  const [mesgul, setMesgul] = useState<string | null>(null);

  const yukle = useCallback(async () => {
    setHata(null);
    try {
      const v = await ortakPanelim();
      setVeri(v);
      setIbanAd((x) => x || v.ortak?.iban_ad || '');
    } catch (h) {
      setHata(hataMetni(t, h, 'ortaklik.panel.hata'));
    }
  }, [t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const kopyala = async (metin: string) => {
    try {
      await navigator.clipboard.writeText(metin);
      toast.success(t('ortaklik.panel.kopyalandi'));
    } catch {
      /* pano kapalı: metin zaten seçilebilir */
    }
  };

  const ibanYaz = async () => {
    setMesgul('iban');
    try {
      await ibanKaydet(iban, ibanAd);
      setIban('');
      toast.success(t('ortaklik.panel.odeme.kaydedildi'));
      await yukle();
    } catch (h) {
      toast.error(hataMetni(t, h, 'ortaklik.panel.hata'));
    } finally {
      setMesgul(null);
    }
  };

  const iste = async (pb: string) => {
    setMesgul(`talep-${pb}`);
    try {
      await odemeIste(pb);
      toast.success(t('ortaklik.panel.odeme.istendi'));
      await yukle();
    } catch (h) {
      toast.error(hataMetni(t, h, 'ortaklik.panel.hata'));
    } finally {
      setMesgul(null);
    }
  };

  const dekontAc = async (id: number) => {
    try {
      const { adres } = await dekontumAdresi(id);
      window.open(`${getAPIBaseURL()}${adres}`, '_blank', 'noopener');
    } catch (h) {
      toast.error(hataMetni(t, h, 'ortaklik.panel.hata'));
    }
  };

  if (hata) {
    return (
      <p className="text-sm text-red-300" role="alert">
        {hata}
      </p>
    );
  }
  if (!veri) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" aria-label={t('ortaklik.panel.yukleniyor')} />
      </div>
    );
  }
  const o = veri.ortak;
  const bakiyeler = Object.entries(veri.bakiyeler || {});
  const enAz = veri.program?.odeme_en_az || {};

  return (
    <section className="space-y-6" data-testid="ortaklik-paneli" aria-labelledby="ortaklik-panel-baslik">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 id="ortaklik-panel-baslik" className="flex items-center gap-2 text-2xl font-bold">
            <HandCoins className="h-6 w-6 text-purple-300" aria-hidden="true" />
            {t('ortaklik.panel.baslik')}
          </h2>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{t('ortaklik.panel.aciklama')}</p>
        </div>
        <Button variant="outline" size="sm" className="gap-1.5 border-white/20 !bg-transparent" onClick={() => void yukle()}>
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          {t('ortaklik.panel.yenile')}
        </Button>
      </div>

      {veri.durum === 'askida' && (
        <p className="flex items-start gap-2 rounded-xl border border-red-400/30 bg-red-500/10 p-4 text-sm text-red-100" role="status">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-none" aria-hidden="true" />
          {t('ortaklik.panel.askida')}
        </p>
      )}

      {o && (
        <div className={`${KART} grid gap-4 p-5 md:grid-cols-2`}>
          <div className="min-w-0">
            <p className="text-xs uppercase tracking-wider text-muted-foreground">{t('ortaklik.panel.kod')}</p>
            <div className="mt-1 flex items-center gap-2">
              <code className="rounded-md bg-black/40 px-2 py-1 text-lg font-bold tracking-wide" data-testid="ortaklik-kod">
                {o.kod}
              </code>
              <Button size="sm" variant="ghost" className="gap-1" onClick={() => void kopyala(o.kod || '')} aria-label={t('ortaklik.panel.kopyala')}>
                <Copy className="h-4 w-4" aria-hidden="true" />
              </Button>
            </div>
            <p className="mt-2 text-sm text-muted-foreground">{t('ortaklik.panel.oran', { oran: o.oran })}</p>
            {!!veri.program && veri.program.tekrar_ay > 0 && veri.program.tekrar_oran > 0 && (
              <p className="mt-1 text-xs text-muted-foreground" data-testid="ortaklik-tekrar">
                {t('ortaklik.panel.tekrar', { oran: veri.program.tekrar_oran, ay: veri.program.tekrar_ay })}
              </p>
            )}
          </div>
          <div className="min-w-0">
            <p className="text-xs uppercase tracking-wider text-muted-foreground">{t('ortaklik.panel.baglanti')}</p>
            <div className="mt-1 flex items-center gap-2">
              <input readOnly value={o.baglanti || ''} className={`${GIRDI} font-mono text-xs`} onFocus={(e) => e.currentTarget.select()} data-testid="ortaklik-baglanti" />
              <Button size="sm" variant="outline" className="flex-none gap-1 border-white/20 !bg-transparent" onClick={() => void kopyala(o.baglanti || '')}>
                <Copy className="h-4 w-4" aria-hidden="true" />
                {t('ortaklik.panel.kopyala')}
              </Button>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">{t('ortaklik.panel.nasil')}</p>
          </div>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <SayiKarti
          etiket={t('ortaklik.panel.kart.tiklama')}
          deger={veri.tiklama?.son_toplam ?? 0}
          alt={t('ortaklik.panel.kart.tiklamaAlt', { sayi: veri.tiklama?.toplam ?? 0 })}
          testid="ortaklik-tiklama"
        />
        <SayiKarti etiket={t('ortaklik.panel.kart.aday')} deger={veri.aday ?? 0} alt={t('ortaklik.panel.kart.adayAlt')} testid="ortaklik-aday" />
        <SayiKarti etiket={t('ortaklik.panel.kart.satis')} deger={veri.satis ?? 0} alt={t('ortaklik.panel.kart.satisAlt')} testid="ortaklik-satis" />
        <SayiKarti
          etiket={t('ortaklik.panel.kart.kazanc')}
          deger={bakiyeler.length ? bakiyeler.map(([pb, b]) => paraBicimle(b.kazanc, pb, dil)).join(' · ') : paraBicimle(0, 'TRY', dil)}
          testid="ortaklik-kazanc"
        />
      </div>

      <div className={`${KART} p-5`}>
        <h3 className="mb-3 flex items-center gap-2 font-semibold">
          <Landmark className="h-4 w-4 text-purple-300" aria-hidden="true" />
          {t('ortaklik.panel.odeme.baslik')}
        </h3>
        {bakiyeler.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('ortaklik.panel.kazancYok')}</p>
        ) : (
          <ul className="mb-4 grid gap-3 md:grid-cols-2">
            {bakiyeler.map(([pb, b]) => {
              const sinir = enAz[pb] ?? 0;
              const yeter = b.onaylandi > 0 && b.onaylandi >= sinir;
              return (
                <li key={pb} className="rounded-xl border border-white/10 bg-black/20 p-4" data-bakiye={pb}>
                  <p className="text-xs uppercase tracking-wider text-muted-foreground">{t('ortaklik.panel.kart.bakiye')}</p>
                  <p className="text-2xl font-bold tabular-nums">{paraBicimle(b.onaylandi, pb, dil)}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {t('ortaklik.panel.kart.bekleyen')}: {paraBicimle(b.beklemede, pb, dil)} · {t('ortaklik.panel.kart.talepte')}:{' '}
                    {paraBicimle(b.odeme_talebinde, pb, dil)} · {t('ortaklik.panel.kart.odenen')}: {paraBicimle(b.odendi, pb, dil)}
                  </p>
                  <Button
                    size="sm"
                    className="mt-3 gap-1.5"
                    disabled={!yeter || !o?.iban || veri.durum !== 'onaylandi' || mesgul === `talep-${pb}`}
                    onClick={() => void iste(pb)}
                    data-testid={`ortaklik-odeme-iste-${pb}`}
                  >
                    {mesgul === `talep-${pb}` && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
                    {t('ortaklik.panel.odeme.iste', { tutar: paraBicimle(b.onaylandi, pb, dil) })}
                  </Button>
                  <p className="mt-1 text-[11px] text-muted-foreground">{t('ortaklik.panel.odeme.enAz', { tutar: paraBicimle(sinir, pb, dil) })}</p>
                </li>
              );
            })}
          </ul>
        )}
        <div className="grid gap-3 md:grid-cols-[1fr_1fr_auto] md:items-end">
          <Alan etiket={t('ortaklik.panel.odeme.iban')} ipucu={t('ortaklik.panel.odeme.ibanIpucu')}>
            <input
              className={`${GIRDI} font-mono uppercase`}
              value={iban}
              onChange={(e) => setIban(e.target.value)}
              placeholder={o?.iban || 'TR00 0000 0000 0000 0000 0000 00'}
              autoComplete="off"
              inputMode="text"
              maxLength={42}
              data-testid="ortaklik-iban"
            />
          </Alan>
          <Alan etiket={t('ortaklik.panel.odeme.ibanAd')}>
            <input className={GIRDI} value={ibanAd} onChange={(e) => setIbanAd(e.target.value)} maxLength={120} data-testid="ortaklik-iban-ad" />
          </Alan>
          <Button onClick={() => void ibanYaz()} disabled={!iban.trim() || !ibanAd.trim() || mesgul === 'iban'} className="h-10 md:mb-5" data-testid="ortaklik-iban-kaydet">
            {t('ortaklik.panel.odeme.kaydet')}
          </Button>
        </div>
        {o?.iban && <p className="mt-1 text-xs text-muted-foreground">{t('ortaklik.panel.odeme.kayitli', { iban: o.iban, ad: o.iban_ad || '—' })}</p>}
      </div>

      <div className={`${KART} p-5`}>
        <h3 className="mb-3 font-semibold">{t('ortaklik.panel.komisyonlar')}</h3>
        {!veri.komisyonlar?.length ? (
          <p className="text-sm text-muted-foreground">{t('ortaklik.panel.komisyonYok')}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-sm" data-testid="ortaklik-komisyon-tablosu">
              <thead>
                <tr className="text-start text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="py-2 text-start font-medium">{t('ortaklik.panel.sutun.tarih')}</th>
                  <th className="py-2 text-start font-medium">{t('ortaklik.panel.sutun.fatura')}</th>
                  <th className="py-2 text-start font-medium">{t('ortaklik.panel.sutun.musteri')}</th>
                  <th className="py-2 text-end font-medium">{t('ortaklik.panel.sutun.tutar')}</th>
                  <th className="py-2 text-end font-medium">{t('ortaklik.panel.sutun.durum')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {veri.komisyonlar.map((k) => (
                  <tr key={k.id} data-komisyon={k.id}>
                    <td className="py-2">{tarihBicimle(k.created_at, dil)}</td>
                    <td className="py-2">
                      {k.fatura_no || '—'}
                      {k.tur === 'ters' ? (
                        <span className="ms-1 text-xs text-amber-200">· {t('ortaklik.panel.tur.ters')}</span>
                      ) : (
                        <span className="ms-1 text-xs text-muted-foreground">· {t(`ortaklik.panel.kural.${k.kural || 'ilk'}`)}</span>
                      )}
                    </td>
                    <td className="py-2 text-muted-foreground">
                      <bdi>{k.musteri || '—'}</bdi>
                    </td>
                    <td className={`py-2 text-end tabular-nums ${k.tutar < 0 ? 'text-amber-200' : ''}`}>{paraBicimle(k.tutar, k.para_birimi, dil)}</td>
                    <td className="py-2 text-end">
                      <Rozet durum={k.durum}>{t(`ortaklik.panel.durum.${k.durum}`)}</Rozet>
                      {k.durum === 'beklemede' && k.bekleme_bitis && (
                        <span className="block text-[11px] text-muted-foreground">{t('ortaklik.panel.bekleme', { tarih: tarihBicimle(k.bekleme_bitis, dil) })}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className={`${KART} p-5`}>
        <h3 className="mb-3 font-semibold">{t('ortaklik.panel.odeme.talepler')}</h3>
        {!veri.talepler?.length ? (
          <p className="text-sm text-muted-foreground">{t('ortaklik.panel.odeme.talepYok')}</p>
        ) : (
          <ul className="divide-y divide-white/5 text-sm">
            {veri.talepler.map((x) => (
              <li key={x.id} className="flex flex-wrap items-center justify-between gap-2 py-2" data-talep={x.id}>
                <span>
                  {tarihBicimle(x.created_at, dil)} · <b className="tabular-nums">{paraBicimle(x.tutar, x.para_birimi, dil)}</b> · {x.iban}
                  {x.ret_nedeni && <span className="block text-xs text-muted-foreground">{x.ret_nedeni}</span>}
                </span>
                <span className="flex items-center gap-2">
                  <Rozet durum={x.durum}>{t(`ortaklik.panel.talepDurum.${x.durum}`)}</Rozet>
                  {x.dekont_var && (
                    <Button size="sm" variant="ghost" className="gap-1" onClick={() => void dekontAc(x.id)}>
                      <FileDown className="h-4 w-4" aria-hidden="true" />
                      {t('ortaklik.panel.odeme.dekont')}
                    </Button>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
      {/* Vergi / hukuki not: komisyon ödemelerinin vergi yükümlülüğü ortağa ait; bilgilendirme amaçlı. */}
      <p className="text-xs italic text-muted-foreground" data-testid="ortaklik-vergi-notu">
        {t('ortaklik.kosul.bilgi')}
      </p>
    </section>
  );
}
