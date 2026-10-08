import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, TicketPercent, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { BelgeHatasi, paraBicimle, type Kalem } from '@/lib/belge';
import { indirimSatiriMi, onizle, type Onizleme } from '@/lib/indirimKodu';

/**
 * Faz 5K — yönetici teklif / fatura formundaki "İndirim kodu" alanı.
 *
 * "Önizle" kodu sunucuda doğrular (tarih, sınır, en az tutar, kapsam, para birimi, kişi başı — alıcının
 * e-postasıyla) ve indirimi + yeni toplamı gösterir; KAYDEDİLMEZ. Kayıtta kod yeniden doğrulanır ve
 * "İndirim (KOD)" satırı(ları) sunucuda eklenir (KDV oranı başına). Boş bırakmak kodu kaldırır.
 * Metinler `indirimKodu` ek paketinde (çağıran bileşen paketi yüklüyor).
 */
export default function IndirimKoduGirdisi({
  deger,
  onDegis,
  kalemler,
  paraBirimi,
  belgeTuru,
  eposta,
  belgeId,
}: {
  deger: string;
  onDegis: (v: string) => void;
  kalemler: Kalem[];
  paraBirimi: string;
  belgeTuru: 'teklif' | 'fatura';
  eposta?: string;
  belgeId?: number;
}) {
  const { t, i18n } = useTranslation();
  const [sonuc, setSonuc] = useState<Onizleme | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [yukleniyor, setYukleniyor] = useState(false);

  const dene = async () => {
    if (!deger.trim()) return;
    setYukleniyor(true);
    setHata(null);
    setSonuc(null);
    try {
      const dolu = kalemler.filter((k) => !indirimSatiriMi(k) && (k.aciklama || '').trim() && k.birim_fiyat !== '');
      setSonuc(await onizle({ kod: deger.trim(), kalemler: dolu, para_birimi: paraBirimi, belge_turu: belgeTuru, eposta: eposta || undefined, belge_id: belgeId }));
    } catch (h) {
      const kod = h instanceof BelgeHatasi ? h.kod : 'genel';
      const ek = h instanceof BelgeHatasi ? h.ek : {};
      setHata(t(`indirimKodu.hata.${kod}`, { ...ek, defaultValue: t('indirimKodu.hata.genel') }));
    } finally {
      setYukleniyor(false);
    }
  };

  return (
    <div className="grid gap-2" data-testid={`${belgeTuru}-indirim-kodu`}>
      <label htmlFor={`${belgeTuru}-indirim-kodu-girdi`} className="flex items-center gap-1.5 text-sm font-medium">
        <TicketPercent className="h-4 w-4 text-purple-300" aria-hidden="true" />
        {t('indirimKodu.belge.baslik')}
      </label>
      <div className="flex flex-wrap items-center gap-2">
        <input
          id={`${belgeTuru}-indirim-kodu-girdi`}
          value={deger}
          maxLength={32}
          autoComplete="off"
          placeholder={t('indirimKodu.belge.yerTutucu')}
          onChange={(e) => {
            onDegis(e.target.value.replace(/\s+/g, ''));
            setSonuc(null);
            setHata(null);
          }}
          className="h-10 w-48 rounded-md border border-white/10 bg-white/5 px-3 text-sm uppercase tracking-wide placeholder:normal-case placeholder:tracking-normal"
          data-testid="belge-indirim-kodu"
        />
        <Button type="button" size="sm" variant="outline" className="h-10 border-white/20 !bg-transparent" disabled={!deger.trim() || yukleniyor} onClick={() => void dene()}
          data-testid="belge-indirim-onizle">
          {yukleniyor && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
          {t('indirimKodu.belge.uygula')}
        </Button>
        {deger && (
          <Button type="button" size="sm" variant="ghost" className="h-10 gap-1" onClick={() => { onDegis(''); setSonuc(null); setHata(null); }}>
            <X className="h-3.5 w-3.5" aria-hidden="true" />
            {t('indirimKodu.belge.kaldir')}
          </Button>
        )}
      </div>
      {sonuc && (
        <p className="text-xs text-emerald-300" role="status" data-testid="belge-indirim-sonuc">
          {t('indirimKodu.belge.onizleme', {
            tutar: paraBicimle(sonuc.indirim, paraBirimi, i18n.language),
            toplam: paraBicimle(sonuc.genel_toplam, paraBirimi, i18n.language),
          })}
        </p>
      )}
      {hata && (
        <p className="text-xs text-red-300" role="alert" data-testid="belge-indirim-hata">
          {hata}
        </p>
      )}
      <p className="text-xs text-muted-foreground">{t('indirimKodu.belge.ipucu')}</p>
    </div>
  );
}
