import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { EyeOff, Loader2, Pencil, Plus, Tag, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { Alan, Anahtar, DIS_DUGME, KART, Rozet, SECIM, Yukleniyor } from '@/components/randevu/ortak';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { hataMetni, yerelGirdi, yerelIso, type BiletTuru, type Etkinlik, type EtkinlikApi, type IndirimKodu, type Meta } from '@/lib/etkinlik';
import { paraYaz, tarihYaz } from '@/lib/etkinlikOrtak';

/**
 * Faz 6E — bilet türleri (ad, fiyat, para birimi, kontenjan, satış aralığı, kişi başı sınır, gizli tür)
 * ve indirim kodları. Ücretli tür YALNIZ ajans etkinliğinde (ödeme ajansın hesabına gidiyor);
 * müşteri etkinliğinde fiyat alanı yok, "ödeme bilgisi" metni Ayarlar'da.
 */

type TurTaslak = {
  id?: number;
  ad: string;
  aciklama: string;
  fiyat: string;
  para_birimi: string;
  kontenjan: string;
  satis_bas: string;
  satis_bit: string;
  kisi_basi_en_cok: string;
  gizli: boolean;
  gizli_kod: string;
  aktif: boolean;
  /** Düzenlemeye başlarken ücretli miydi (ödeme sağlayıcısı yokken yalnız ücretsizden ücretliye geçiş kapalı). */
  ilkUcretli?: boolean;
};

const BOS_TUR: TurTaslak = {
  ad: '', aciklama: '', fiyat: '0', para_birimi: 'TRY', kontenjan: '', satis_bas: '', satis_bit: '', kisi_basi_en_cok: '5',
  gizli: false, gizli_kod: '', aktif: true,
};

export default function Biletler({ api, meta, etkinlik }: { api: EtkinlikApi; meta: Meta; etkinlik: Etkinlik }) {
  const { t, i18n } = useTranslation();
  const tz = etkinlik.saat_dilimi;
  const ucretli = meta.ucretli_bilet && etkinlik.ajans;
  const [turler, setTurler] = useState<BiletTuru[] | null>(null);
  const [indirimler, setIndirimler] = useState<IndirimKodu[] | null>(null);
  const [taslak, setTaslak] = useState<TurTaslak | null>(null);
  const [kaydediliyor, setKaydediliyor] = useState(false);
  const [kod, setKod] = useState({ kod: '', tur: 'yuzde' as IndirimKodu['tur'], deger: '10', kullanim_siniri: '', son_tarih: '' });
  // Ödeme sağlayıcısı anahtarları tanımlı değilse ücretsiz türü ücretliye çevirmek kapalı (açıklamayla).
  const fiyatKapali = ucretli && !meta.odeme_hazir && !taslak?.ilkUcretli;

  const yukle = useCallback(async () => {
    try {
      const [a, b] = await Promise.all([api.turler(etkinlik.id), api.indirimler(etkinlik.id)]);
      setTurler(a.items);
      setIndirimler(b.items);
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  }, [api, etkinlik.id, t]);
  useEffect(() => {
    void yukle();
  }, [yukle]);

  const duzenle = (x: BiletTuru) =>
    setTaslak({
      id: x.id, ad: x.ad, aciklama: x.aciklama, fiyat: String(x.fiyat / 100), para_birimi: x.para_birimi,
      kontenjan: x.kontenjan == null ? '' : String(x.kontenjan), satis_bas: yerelGirdi(x.satis_bas, tz), satis_bit: yerelGirdi(x.satis_bit, tz),
      kisi_basi_en_cok: String(x.kisi_basi_en_cok), gizli: x.gizli, gizli_kod: x.gizli_kod, aktif: x.aktif, ilkUcretli: x.fiyat > 0,
    });

  const turKaydet = async () => {
    if (!taslak) return;
    setKaydediliyor(true);
    const g: Partial<BiletTuru> = {
      ad: taslak.ad, aciklama: taslak.aciklama, kontenjan: taslak.kontenjan.trim() === '' ? null : Number(taslak.kontenjan),
      satis_bas: yerelIso(taslak.satis_bas, tz), satis_bit: yerelIso(taslak.satis_bit, tz), kisi_basi_en_cok: Number(taslak.kisi_basi_en_cok || 1),
      gizli: taslak.gizli, gizli_kod: taslak.gizli ? taslak.gizli_kod : '', aktif: taslak.aktif,
    };
    if (ucretli && !fiyatKapali) {
      g.fiyat = Math.round(Number(String(taslak.fiyat).replace(',', '.') || 0) * 100);
      g.para_birimi = taslak.para_birimi;
    }
    try {
      if (taslak.id) await api.turGuncelle(etkinlik.id, taslak.id, g);
      else await api.turOlustur(etkinlik.id, g);
      setTaslak(null);
      toast.success(t('etkinlik.ayar.kaydedildi'));
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setKaydediliyor(false);
    }
  };

  const turSil = async (x: BiletTuru) => {
    if (!window.confirm(t('etkinlik.bilet.silOnay', { ad: x.ad }))) return;
    try {
      await api.turSil(etkinlik.id, x.id);
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const kodEkle = async () => {
    try {
      await api.indirimOlustur(etkinlik.id, {
        kod: kod.kod, tur: kod.tur, deger: kod.tur === 'yuzde' ? Number(kod.deger) : Math.round(Number(kod.deger.replace(',', '.')) * 100),
        kullanim_siniri: kod.kullanim_siniri ? Number(kod.kullanim_siniri) : null, son_tarih: yerelIso(kod.son_tarih, tz),
      });
      setKod({ kod: '', tur: 'yuzde', deger: '10', kullanim_siniri: '', son_tarih: '' });
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  if (!turler || !indirimler) return <Yukleniyor />;
  const para = turler.find((x) => x.fiyat > 0)?.para_birimi || 'TRY';

  return (
    <div className="space-y-4" data-testid="etkinlik-biletler">
      <div className={`${KART} p-4 sm:p-6`}>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-base font-semibold">{t('etkinlik.bilet.turler')}</h3>
          <Button size="sm" className="gap-1.5" onClick={() => setTaslak({ ...BOS_TUR })} data-testid="etkinlik-tur-yeni">
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('etkinlik.bilet.yeniTur')}
          </Button>
        </div>
        {!ucretli && <p className="mb-3 rounded-lg border border-amber-400/30 bg-amber-500/10 p-3 text-xs text-amber-100">{t('etkinlik.bilet.ucretsizNot')}</p>}
        <ul className="space-y-2" data-testid="etkinlik-tur-listesi">
          {turler.map((x) => (
            <li key={x.id} data-tur={x.id} className="flex flex-wrap items-center gap-3 rounded-xl border border-white/10 bg-black/20 p-3">
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-center gap-2 font-medium">
                  {x.ad}
                  {x.gizli && (
                    <Rozet>
                      <EyeOff className="h-3 w-3" aria-hidden="true" />
                      {t('etkinlik.bilet.gizli')}
                    </Rozet>
                  )}
                  {!x.aktif && <Rozet>{t('etkinlik.bilet.pasif')}</Rozet>}
                </span>
                <span className="block text-xs text-muted-foreground">
                  {x.fiyat > 0 ? paraYaz(x.fiyat, x.para_birimi, i18n.language) : t('etkinlik.bilet.ucretsiz')}
                  {' · '}
                  {t('etkinlik.bilet.satilan', { sayi: x.satilan ?? 0 })}
                  {x.kontenjan != null && ` / ${x.kontenjan}`}
                  {x.satis_bit && ` · ${t('etkinlik.bilet.satisBitis')}: ${tarihYaz(x.satis_bit, tz, i18n.language, { dateStyle: 'medium', timeStyle: 'short' })}`}
                </span>
              </span>
              <Button size="icon" variant="ghost" aria-label={t('etkinlik.duzenle')} onClick={() => duzenle(x)}>
                <Pencil className="h-4 w-4" aria-hidden="true" />
              </Button>
              <Button size="icon" variant="ghost" aria-label={t('etkinlik.sil')} onClick={() => void turSil(x)}>
                <Trash2 className="h-4 w-4" aria-hidden="true" />
              </Button>
            </li>
          ))}
        </ul>
        {taslak && (
          <div className="mt-4 grid gap-3 rounded-xl border border-purple-400/30 bg-purple-500/5 p-4 md:grid-cols-2" data-testid="etkinlik-tur-formu">
            <Alan etiket={t('etkinlik.bilet.ad')}>
              <Input value={taslak.ad} maxLength={120} placeholder={t('etkinlik.bilet.adOrnek')} onChange={(e) => setTaslak({ ...taslak, ad: e.target.value })} data-testid="etkinlik-tur-ad" />
            </Alan>
            {ucretli ? (
              <div className="grid grid-cols-[minmax(0,1fr)_6rem] gap-2">
                <Alan etiket={t('etkinlik.bilet.fiyat')} ipucu={t(fiyatKapali ? 'etkinlik.bilet.odemeHazirDegil' : 'etkinlik.bilet.fiyatIpucu')}>
                  <Input inputMode="decimal" value={fiyatKapali ? '0' : taslak.fiyat} disabled={fiyatKapali} onChange={(e) => setTaslak({ ...taslak, fiyat: e.target.value })} data-testid="etkinlik-tur-fiyat" />
                </Alan>
                <Alan etiket={t('etkinlik.bilet.paraBirimi')}>
                  <select className={SECIM} value={taslak.para_birimi} disabled={fiyatKapali} onChange={(e) => setTaslak({ ...taslak, para_birimi: e.target.value })}>
                    {meta.para_birimleri.map((p) => (
                      <option key={p}>{p}</option>
                    ))}
                  </select>
                </Alan>
              </div>
            ) : (
              <div />
            )}
            <Alan etiket={t('etkinlik.bilet.aciklama')} className="md:col-span-2">
              <Input value={taslak.aciklama} maxLength={500} onChange={(e) => setTaslak({ ...taslak, aciklama: e.target.value })} />
            </Alan>
            <Alan etiket={t('etkinlik.bilet.kontenjan')} ipucu={t('etkinlik.bilet.kontenjanIpucu')}>
              <Input type="number" min={1} value={taslak.kontenjan} onChange={(e) => setTaslak({ ...taslak, kontenjan: e.target.value })} data-testid="etkinlik-tur-kontenjan" />
            </Alan>
            <Alan etiket={t('etkinlik.bilet.kisiBasi')}>
              <Input type="number" min={1} max={meta.en_cok_adet} value={taslak.kisi_basi_en_cok} onChange={(e) => setTaslak({ ...taslak, kisi_basi_en_cok: e.target.value })} />
            </Alan>
            <Alan etiket={t('etkinlik.bilet.satisBas')}>
              <Input type="datetime-local" value={taslak.satis_bas} onChange={(e) => setTaslak({ ...taslak, satis_bas: e.target.value })} />
            </Alan>
            <Alan etiket={t('etkinlik.bilet.satisBit')}>
              <Input type="datetime-local" value={taslak.satis_bit} onChange={(e) => setTaslak({ ...taslak, satis_bit: e.target.value })} />
            </Alan>
            <div className="flex flex-wrap items-center gap-4 md:col-span-2">
              <Anahtar acik={taslak.aktif} onDegis={(v) => setTaslak({ ...taslak, aktif: v })} etiket={t('etkinlik.bilet.aktif')} />
              <Anahtar acik={taslak.gizli} onDegis={(v) => setTaslak({ ...taslak, gizli: v })} etiket={t('etkinlik.bilet.gizliTur')} />
              {taslak.gizli && (
                <Input className="max-w-[14rem]" value={taslak.gizli_kod} placeholder={t('etkinlik.bilet.gizliKod')} onChange={(e) => setTaslak({ ...taslak, gizli_kod: e.target.value.toUpperCase() })} dir="ltr" />
              )}
            </div>
            <div className="flex justify-end gap-2 md:col-span-2">
              <Button variant="ghost" onClick={() => setTaslak(null)}>
                {t('etkinlik.vazgec')}
              </Button>
              <Button onClick={() => void turKaydet()} disabled={kaydediliyor} className="gap-1.5" data-testid="etkinlik-tur-kaydet">
                {kaydediliyor && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
                {t('etkinlik.kaydet')}
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* İndirim kodu yalnız ücretli bilette anlamlı: müşteri etkinliğinde (ücretsiz) bölüm yok. */}
      {ucretli && (
      <div className={`${KART} p-4 sm:p-6`} data-testid="etkinlik-indirimler">
        <h3 className="mb-1 flex items-center gap-2 text-base font-semibold">
          <Tag className="h-4 w-4 text-purple-300" aria-hidden="true" />
          {t('etkinlik.indirim.baslik')}
        </h3>
        <p className="mb-3 text-sm text-muted-foreground">{t('etkinlik.indirim.aciklama')}</p>
        <div className="mb-3 grid gap-2 sm:grid-cols-[minmax(0,1fr)_8rem_7rem_7rem_minmax(0,1fr)_auto] sm:items-end">
          <Alan etiket={t('etkinlik.indirim.kod')}>
            <Input value={kod.kod} onChange={(e) => setKod({ ...kod, kod: e.target.value.toUpperCase() })} placeholder="ERKEN10" dir="ltr" />
          </Alan>
          <Alan etiket={t('etkinlik.indirim.tur')}>
            <select className={SECIM} value={kod.tur} onChange={(e) => setKod({ ...kod, tur: e.target.value as IndirimKodu['tur'] })}>
              <option value="yuzde">{t('etkinlik.indirim.yuzde')}</option>
              <option value="tutar">{t('etkinlik.indirim.tutar')}</option>
            </select>
          </Alan>
          <Alan etiket={kod.tur === 'yuzde' ? '%' : para}>
            <Input inputMode="decimal" value={kod.deger} onChange={(e) => setKod({ ...kod, deger: e.target.value })} />
          </Alan>
          <Alan etiket={t('etkinlik.indirim.sinir')}>
            <Input type="number" min={1} value={kod.kullanim_siniri} onChange={(e) => setKod({ ...kod, kullanim_siniri: e.target.value })} />
          </Alan>
          <Alan etiket={t('etkinlik.indirim.sonTarih')}>
            <Input type="datetime-local" value={kod.son_tarih} onChange={(e) => setKod({ ...kod, son_tarih: e.target.value })} />
          </Alan>
          <Button variant="outline" className={DIS_DUGME} onClick={() => void kodEkle()} disabled={!kod.kod}>
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('etkinlik.ekle')}
          </Button>
        </div>
        {indirimler.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('etkinlik.indirim.bos')}</p>
        ) : (
          <ul className="divide-y divide-white/5">
            {indirimler.map((i) => (
              <li key={i.id} className="flex flex-wrap items-center gap-3 py-2 text-sm">
                <span className="font-mono font-semibold" dir="ltr">
                  {i.kod}
                </span>
                <span className="text-muted-foreground">{i.tur === 'yuzde' ? `%${i.deger}` : paraYaz(i.deger, para, i18n.language)}</span>
                <span className="text-muted-foreground">
                  {t('etkinlik.indirim.kullanim', { sayi: i.kullanilan })}
                  {i.kullanim_siniri != null && ` / ${i.kullanim_siniri}`}
                </span>
                {!i.aktif && <Rozet>{t('etkinlik.bilet.pasif')}</Rozet>}
                <span className="ms-auto flex gap-1">
                  <Button size="sm" variant="ghost" onClick={() => void api.indirimGuncelle(etkinlik.id, i.id, { aktif: !i.aktif }).then(yukle).catch((e) => toast.error(hataMetni(t, e)))}>
                    {i.aktif ? t('etkinlik.indirim.kapat') : t('etkinlik.indirim.ac')}
                  </Button>
                  <Button size="icon" variant="ghost" aria-label={t('etkinlik.sil')} onClick={() => void api.indirimSil(etkinlik.id, i.id).then(yukle).catch((e) => toast.error(hataMetni(t, e)))}>
                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                  </Button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
      )}
    </div>
  );
}
