import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, Save, ShieldCheck, ShieldOff, Trash2, UserPlus } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { DILLER, hataMetni, IS_TURLERI, type Ayarlar as AyarVerisi, type SahaApi, type Teknisyen } from '@/lib/sahaServisi';
import { Alan, Anahtar, GIRDI, KART, METIN_ALANI, Rozet, SECIM, Yukleniyor } from './ortak';

/**
 * Faz 6S — ayarlar: teknisyenler (hesap ekibinden; `saha_teknisyen` izni + bu listede satır), firma
 * künyesi (servis formunun başlığı), KDV, saklama süresi, servis müşterisine e-postalar, imza
 * zorunluluğu, memnuniyet + Google yorum sayfası, randevu → iş emri, bakım bildirimi.
 */
export default function Ayarlar({ api, saltOkunur }: { api: SahaApi; saltOkunur: boolean }) {
  const { t } = useTranslation();
  const [a, setA] = useState<AyarVerisi | null>(null);
  const [tek, setTek] = useState<{ items: Teknisyen[]; adaylar: { eposta: string; sahip: boolean; durum?: string; teknisyen_izni?: boolean }[]; sinir: number } | null>(null);
  const [yeni, setYeni] = useState({ eposta: '', ad: '', telefon: '', renk: '#22c55e' });
  const [mesgul, setMesgul] = useState(false);

  const yukle = useCallback(async () => {
    try {
      const [x, y] = await Promise.all([api.ayarlar(), api.teknisyenler()]);
      setA(x);
      setTek(y);
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  }, [api, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  if (!a || !tek) return <Yukleniyor />;

  const kaydet = async () => {
    setMesgul(true);
    try {
      const { yorum_sayfalari, eposta_kanali, randevu_modulu, yorum_modulu, ...govde } = a;
      setA({ ...(await api.ayarlarKaydet(govde)), yorum_sayfalari, eposta_kanali, randevu_modulu, yorum_modulu });
      toast.success(t('sahaServisi.kaydedildi'));
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  const teknisyenEkle = async () => {
    try {
      await api.teknisyenEkle({ eposta: yeni.eposta.trim(), ad: yeni.ad.trim() || undefined, telefon: yeni.telefon.trim() || undefined, renk: yeni.renk });
      setYeni({ eposta: '', ad: '', telefon: '', renk: '#22c55e' });
      toast.success(t('sahaServisi.teknisyen.eklendi'));
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const degis = <K extends keyof AyarVerisi>(k: K, v: AyarVerisi[K]) => setA({ ...a, [k]: v });
  // Dış bağımlılık yoksa ilgili ayar devre dışı + nedeni (yönetici görünümünde bilgiler gelmeyebilir).
  const epostaYok = a.eposta_kanali === false;
  const randevuYok = a.randevu_modulu === false;
  const yorumYok = a.yorum_modulu === false || (a.yorum_sayfalari || []).length === 0;

  return (
    <div className="space-y-4" data-testid="saha-ayarlar">
      <section className={`${KART} p-4`} data-testid="saha-teknisyenler">
        <h3 className="text-base font-semibold">{t('sahaServisi.teknisyen.baslik')}</h3>
        <p className="mb-3 text-xs text-muted-foreground">{t('sahaServisi.teknisyen.aciklama', { sinir: tek.sinir })}</p>
        <ul className="divide-y divide-white/5 text-sm">
          {tek.items.map((x) => (
            <li key={x.id} className="flex flex-wrap items-center gap-2 py-2" data-testid="saha-teknisyen">
              <input
                type="color"
                value={x.renk}
                disabled={saltOkunur}
                aria-label={t('sahaServisi.teknisyen.renk')}
                className="h-8 w-8 cursor-pointer rounded border border-white/10 bg-transparent"
                onChange={async (e) => {
                  try {
                    await api.teknisyenGuncelle(x.id, { renk: e.target.value });
                    await yukle();
                  } catch (err) {
                    toast.error(hataMetni(t, err));
                  }
                }}
              />
              <span className="min-w-0 flex-1">
                <span className="font-medium">{x.ad}</span>
                <span className="block truncate text-xs text-muted-foreground" dir="ltr">
                  {x.eposta}
                </span>
              </span>
              {x.konum_rizasi ? (
                <Rozet renk="border-emerald-400/30 bg-emerald-500/10 text-emerald-200">
                  <ShieldCheck className="h-3 w-3" aria-hidden="true" />
                  {t('sahaServisi.teknisyen.rizaVar')}
                </Rozet>
              ) : (
                <Rozet>
                  <ShieldOff className="h-3 w-3" aria-hidden="true" />
                  {t('sahaServisi.teknisyen.rizaYok')}
                </Rozet>
              )}
              {!x.aktif && <Rozet>{t('sahaServisi.pasif')}</Rozet>}
              {!saltOkunur && (
                <span className="flex gap-1">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={async () => {
                      try {
                        await api.teknisyenGuncelle(x.id, { aktif: !x.aktif });
                        await yukle();
                      } catch (e) {
                        toast.error(hataMetni(t, e));
                      }
                    }}
                  >
                    {x.aktif ? t('sahaServisi.pasifYap') : t('sahaServisi.aktifYap')}
                  </Button>
                  <Button
                    size="icon"
                    variant="ghost"
                    className="h-8 w-8"
                    aria-label={t('sahaServisi.sil')}
                    onClick={async () => {
                      if (!window.confirm(t('sahaServisi.teknisyen.silOnay', { ad: x.ad }))) return;
                      try {
                        await api.teknisyenSil(x.id);
                        await yukle();
                      } catch (e) {
                        toast.error(hataMetni(t, e));
                      }
                    }}
                  >
                    <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                  </Button>
                </span>
              )}
            </li>
          ))}
        </ul>
        {!saltOkunur && (
          <div className="mt-3 grid gap-2 rounded-xl border border-white/10 bg-black/20 p-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_8rem_auto] sm:items-end">
            <Alan etiket={t('sahaServisi.teknisyen.kisi')}>
              <select className={SECIM} value={yeni.eposta} onChange={(e) => setYeni({ ...yeni, eposta: e.target.value })} data-testid="saha-teknisyen-aday">
                <option value="">{t('sahaServisi.secin')}</option>
                {tek.adaylar.map((x) => (
                  <option key={x.eposta} value={x.eposta}>
                    {x.eposta}
                    {x.sahip ? ` (${t('sahaServisi.teknisyen.sahip')})` : x.teknisyen_izni ? '' : ` (${t('sahaServisi.teknisyen.izinYok')})`}
                  </option>
                ))}
              </select>
            </Alan>
            <Alan etiket={t('sahaServisi.teknisyen.ad')}>
              <input className={GIRDI} value={yeni.ad} maxLength={120} onChange={(e) => setYeni({ ...yeni, ad: e.target.value })} data-testid="saha-teknisyen-ad" />
            </Alan>
            <Alan etiket={t('sahaServisi.teknisyen.telefon')}>
              <input type="tel" className={GIRDI} value={yeni.telefon} maxLength={24} onChange={(e) => setYeni({ ...yeni, telefon: e.target.value })} dir="ltr" />
            </Alan>
            <Button className="gap-1" disabled={!yeni.eposta} onClick={() => void teknisyenEkle()} data-testid="saha-teknisyen-ekle">
              <UserPlus className="h-4 w-4" aria-hidden="true" />
              {t('sahaServisi.ekle')}
            </Button>
            <p className="text-xs text-muted-foreground sm:col-span-4">{t('sahaServisi.teknisyen.davetIpucu')}</p>
          </div>
        )}
      </section>

      <section className={`${KART} grid gap-3 p-4 sm:grid-cols-2`}>
        <h3 className="text-base font-semibold sm:col-span-2">{t('sahaServisi.ayar.firma')}</h3>
        <Alan etiket={t('sahaServisi.ayar.firmaAdi')} ipucu={t('sahaServisi.ayar.firmaIpucu')}>
          <input className={GIRDI} disabled={saltOkunur} value={a.firma_adi || ''} maxLength={160} onChange={(e) => degis('firma_adi', e.target.value)} data-testid="saha-ayar-firma" />
        </Alan>
        <Alan etiket={t('sahaServisi.ayar.telefon')}>
          <input type="tel" className={GIRDI} disabled={saltOkunur} value={a.telefon || ''} maxLength={24} onChange={(e) => degis('telefon', e.target.value)} dir="ltr" />
        </Alan>
        <Alan etiket={t('sahaServisi.ayar.eposta')} ipucu={t('sahaServisi.ayar.epostaIpucu')}>
          <input type="email" className={GIRDI} disabled={saltOkunur} value={a.eposta || ''} maxLength={254} onChange={(e) => degis('eposta', e.target.value)} dir="ltr" />
        </Alan>
        <Alan etiket={t('sahaServisi.ayar.vergi')}>
          <input className={GIRDI} disabled={saltOkunur} value={a.vergi_no || ''} maxLength={64} onChange={(e) => degis('vergi_no', e.target.value)} />
        </Alan>
        <Alan etiket={t('sahaServisi.ayar.adres')} className="sm:col-span-2">
          <textarea className={METIN_ALANI} disabled={saltOkunur} value={a.adres || ''} maxLength={500} onChange={(e) => degis('adres', e.target.value)} />
        </Alan>
        <Alan etiket={t('sahaServisi.ayar.dil')}>
          <select className={SECIM} disabled={saltOkunur} value={a.varsayilan_dil} onChange={(e) => degis('varsayilan_dil', e.target.value)}>
            {DILLER.map((d) => (
              <option key={d} value={d}>
                {t(`sahaServisi.dil.${d}`)}
              </option>
            ))}
          </select>
        </Alan>
        <div className="grid grid-cols-2 gap-3">
          <Alan etiket={t('sahaServisi.ayar.paraBirimi')}>
            <select className={SECIM} disabled={saltOkunur} value={a.para_birimi} onChange={(e) => degis('para_birimi', e.target.value)}>
              {['TRY', 'USD', 'EUR', 'GBP'].map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('sahaServisi.ayar.kdv')}>
            <input type="number" min={0} max={50} className={GIRDI} disabled={saltOkunur} value={a.kdv_orani} onChange={(e) => degis('kdv_orani', Number(e.target.value))} dir="ltr" />
          </Alan>
        </div>
      </section>

      <section className={`${KART} grid gap-3 p-4 sm:grid-cols-2`}>
        <h3 className="text-base font-semibold sm:col-span-2">{t('sahaServisi.ayar.isleyis')}</h3>
        <Anahtar acik={a.imza_zorunlu} devreDisi={saltOkunur} onDegis={(v) => degis('imza_zorunlu', v)} etiket={t('sahaServisi.ayar.imzaZorunlu')} />
        <Anahtar acik={a.memnuniyet_acik} devreDisi={saltOkunur} onDegis={(v) => degis('memnuniyet_acik', v)} etiket={t('sahaServisi.ayar.memnuniyet')} />
        <Anahtar acik={a.bildirim_planlandi} devreDisi={saltOkunur || epostaYok} onDegis={(v) => degis('bildirim_planlandi', v)} etiket={t('sahaServisi.ayar.bildirimPlanlandi')} />
        <Anahtar acik={a.bildirim_yolda} devreDisi={saltOkunur || epostaYok} onDegis={(v) => degis('bildirim_yolda', v)} etiket={t('sahaServisi.ayar.bildirimYolda')} />
        <Anahtar acik={a.bildirim_tamamlandi} devreDisi={saltOkunur || epostaYok} onDegis={(v) => degis('bildirim_tamamlandi', v)} etiket={t('sahaServisi.ayar.bildirimTamamlandi')} />
        {epostaYok && (
          <p className="text-xs text-amber-200 sm:col-span-2" data-testid="saha-eposta-kanali-yok">
            {t('sahaServisi.ayar.epostaKanaliYok')}
          </p>
        )}
        <div className="space-y-1">
          <Anahtar acik={a.randevu_kancasi} devreDisi={saltOkunur || randevuYok} onDegis={(v) => degis('randevu_kancasi', v)} etiket={t('sahaServisi.ayar.randevuKancasi')} />
          {randevuYok && <p className="ps-6 text-xs text-muted-foreground">{t('sahaServisi.ayar.randevuModuluYok')}</p>}
        </div>
        {a.randevu_kancasi && !randevuYok && (
          <Alan etiket={t('sahaServisi.ayar.randevuTuru')}>
            <select className={SECIM} disabled={saltOkunur} value={a.randevu_is_turu} onChange={(e) => degis('randevu_is_turu', e.target.value as AyarVerisi['randevu_is_turu'])}>
              {IS_TURLERI.map((x) => (
                <option key={x} value={x}>
                  {t(`sahaServisi.tur.${x}`)}
                </option>
              ))}
            </select>
          </Alan>
        )}
        <Alan
          etiket={t('sahaServisi.ayar.yorumSayfasi')}
          ipucu={yorumYok ? t('sahaServisi.ayar.yorumSayfasiYok') : t('sahaServisi.ayar.yorumIpucu')}
        >
          <select
            className={SECIM}
            disabled={saltOkunur || yorumYok}
            value={a.yorum_sayfasi_id ?? ''}
            onChange={(e) => degis('yorum_sayfasi_id', e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">{t('sahaServisi.ayar.yorumOtomatik')}</option>
            {(a.yorum_sayfalari || []).map((y) => (
              <option key={y.id} value={y.id}>
                {y.ad}
              </option>
            ))}
          </select>
        </Alan>
        <Alan etiket={t('sahaServisi.ayar.bakimOnGun')}>
          <input type="number" min={0} max={60} className={GIRDI} disabled={saltOkunur} value={a.bakim_on_gun} onChange={(e) => degis('bakim_on_gun', Number(e.target.value))} dir="ltr" />
        </Alan>
        <Alan etiket={t('sahaServisi.ayar.saklama')} ipucu={t('sahaServisi.ayar.saklamaIpucu')}>
          <input type="number" min={6} max={120} className={GIRDI} disabled={saltOkunur} value={a.saklama_ay} onChange={(e) => degis('saklama_ay', Number(e.target.value))} dir="ltr" />
        </Alan>
        {!saltOkunur && (
          <div className="sm:col-span-2">
            <Button className="gap-1.5" onClick={() => void kaydet()} disabled={mesgul} data-testid="saha-ayar-kaydet">
              {mesgul ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Save className="h-4 w-4" aria-hidden="true" />}
              {t('sahaServisi.kaydet')}
            </Button>
          </div>
        )}
      </section>
    </div>
  );
}
