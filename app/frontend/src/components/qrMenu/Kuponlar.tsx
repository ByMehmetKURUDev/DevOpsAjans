import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Alan, KART, Rozet, SECIM, tarihYaz } from '@/components/qrMenu/ortak';
import { hataMetni, type Kupon, type Magaza, type MenuApi } from '@/lib/qrMenu';
import { paraYaz } from '@/lib/qrMenuOrtak';

/** Faz 4M — basit kuponlar: yüzde ya da tutar, tarih aralığı, kullanım sınırı. */

const BOS = { kod: '', tur: 'yuzde' as 'yuzde' | 'tutar', deger: '', en_dusuk_tutar: '', baslangic: '', bitis: '', kullanim_siniri: '' };

function yerelTarih(iso: string): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

export default function Kuponlar({ api, magaza, yazilabilir }: { api: MenuApi; magaza: Magaza; yazilabilir: boolean }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [kuponlar, setKuponlar] = useState<Kupon[] | null>(null);
  const [form, setForm] = useState(BOS);
  const [kaydediliyor, setKaydediliyor] = useState(false);

  const yukle = useCallback(async () => {
    try {
      setKuponlar((await api.kuponlar(magaza.id)).items);
    } catch (e) {
      toast.error(hataMetni(t, e));
      setKuponlar([]);
    }
  }, [api, magaza.id, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const olustur = async () => {
    setKaydediliyor(true);
    try {
      await api.kuponOlustur(magaza.id, {
        kod: form.kod,
        tur: form.tur,
        deger: form.deger,
        en_dusuk_tutar: form.en_dusuk_tutar || null,
        baslangic: yerelTarih(form.baslangic),
        bitis: yerelTarih(form.bitis),
        kullanim_siniri: form.kullanim_siniri ? Number(form.kullanim_siniri) : null,
      });
      setForm(BOS);
      toast.success(t('qrMenu.kupon.olusturuldu'));
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setKaydediliyor(false);
    }
  };

  return (
    <div className="space-y-4" data-testid="menu-kuponlar">
      <div className={`${KART} p-4 sm:p-6`}>
        <h4 className="mb-3 font-semibold">{t('qrMenu.kupon.yeni')}</h4>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Alan etiket={t('qrMenu.kupon.kod')}>
            <Input value={form.kod} onChange={(e) => setForm({ ...form, kod: e.target.value.toUpperCase().replace(/\s/g, '') })} maxLength={32} dir="ltr" data-testid="menu-kupon-kod" />
          </Alan>
          <Alan etiket={t('qrMenu.kupon.tur')}>
            <select className={SECIM} value={form.tur} onChange={(e) => setForm({ ...form, tur: e.target.value as 'yuzde' | 'tutar' })} data-testid="menu-kupon-tur">
              <option value="yuzde">{t('qrMenu.kupon.yuzde')}</option>
              <option value="tutar">{t('qrMenu.kupon.tutar', { para: magaza.para_birimi })}</option>
            </select>
          </Alan>
          <Alan etiket={form.tur === 'yuzde' ? t('qrMenu.kupon.yuzdeDeger') : `${t('qrMenu.kupon.tutarDeger')} (${magaza.para_birimi})`}>
            <Input value={form.deger} onChange={(e) => setForm({ ...form, deger: e.target.value })} inputMode="decimal" dir="ltr" data-testid="menu-kupon-deger" />
          </Alan>
          <Alan etiket={t('qrMenu.kupon.sinir')} ipucu={t('qrMenu.kupon.sinirIpucu')}>
            <Input value={form.kullanim_siniri} onChange={(e) => setForm({ ...form, kullanim_siniri: e.target.value.replace(/\D/g, '') })} inputMode="numeric" dir="ltr" />
          </Alan>
          <Alan etiket={t('qrMenu.kupon.baslangic')}>
            <Input type="datetime-local" value={form.baslangic} onChange={(e) => setForm({ ...form, baslangic: e.target.value })} />
          </Alan>
          <Alan etiket={t('qrMenu.kupon.bitis')}>
            <Input type="datetime-local" value={form.bitis} onChange={(e) => setForm({ ...form, bitis: e.target.value })} />
          </Alan>
          <Alan etiket={`${t('qrMenu.kupon.enDusuk')} (${magaza.para_birimi})`}>
            <Input value={form.en_dusuk_tutar} onChange={(e) => setForm({ ...form, en_dusuk_tutar: e.target.value })} inputMode="decimal" dir="ltr" />
          </Alan>
          <div className="flex items-end">
            <Button onClick={() => void olustur()} disabled={!yazilabilir || kaydediliyor || !form.kod || !form.deger} className="w-full gap-1.5" data-testid="menu-kupon-olustur">
              {kaydediliyor ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Plus className="h-4 w-4" aria-hidden="true" />}
              {t('qrMenu.kupon.olustur')}
            </Button>
          </div>
        </div>
      </div>

      <div className={`${KART} p-4 sm:p-6`}>
        {kuponlar === null ? (
          <div className="flex justify-center py-8 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
          </div>
        ) : kuponlar.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">{t('qrMenu.kupon.bos')}</p>
        ) : (
          <ul className="divide-y divide-white/5 rounded-xl border border-white/10">
            {kuponlar.map((c) => (
              <li key={c.id} className="flex flex-wrap items-center gap-3 p-3" data-kupon={c.kod}>
                <span className="font-mono text-sm font-semibold" dir="ltr">
                  {c.kod}
                </span>
                <Rozet>{c.tur === 'yuzde' ? `%${c.deger}` : paraYaz(c.deger, magaza.para_birimi, dil)}</Rozet>
                <Rozet renk={c.durum === 'gecerli' ? 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200' : 'border-amber-400/30 bg-amber-500/10 text-amber-200'}>
                  {c.durum === 'gecerli' ? t('qrMenu.kupon.gecerli') : t(`qrMenu.hata.${c.durum}`)}
                </Rozet>
                <span className="text-xs text-muted-foreground">
                  {t('qrMenu.kupon.kullanim', { sayi: c.kullanim_sayisi, sinir: c.kullanim_siniri ?? '∞' })}
                  {c.bitis && ` · ${t('qrMenu.kupon.sonGun', { tarih: tarihYaz(c.bitis, dil) })}`}
                </span>
                <span className="ms-auto flex items-center gap-2">
                  <label className="flex items-center gap-1.5 text-xs">
                    <input
                      type="checkbox"
                      className="h-4 w-4 accent-purple-500"
                      checked={c.aktif}
                      disabled={!yazilabilir}
                      onChange={async (e) => {
                        try {
                          await api.kuponGuncelle(magaza.id, c.id, { aktif: e.target.checked });
                          await yukle();
                        } catch (er) {
                          toast.error(hataMetni(t, er));
                        }
                      }}
                    />
                    {t('qrMenu.kupon.aktif')}
                  </label>
                  <Button
                    size="icon"
                    variant="ghost"
                    className="h-8 w-8"
                    disabled={!yazilabilir}
                    aria-label={t('qrMenu.sil')}
                    onClick={async () => {
                      if (!window.confirm(t('qrMenu.kupon.silOnay', { kod: c.kod }))) return;
                      try {
                        await api.kuponSil(magaza.id, c.id);
                        await yukle();
                      } catch (er) {
                        toast.error(hataMetni(t, er));
                      }
                    }}
                  >
                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                  </Button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
