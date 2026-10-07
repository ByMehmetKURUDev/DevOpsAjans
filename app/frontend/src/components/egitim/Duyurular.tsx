import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, Megaphone, Send } from 'lucide-react';
import { toast } from 'sonner';

import { Alan, KART, METIN_ALANI, Rozet, Yukleniyor } from '@/components/randevu/ortak';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { hataMetni, tarihSaat, type EgitimApi, type Kurs } from '@/lib/egitim';

/**
 * Faz 6K — duyurular: kursun aktif öğrencilerine (18 yaş altında veliye) bilgilendirme e-postası. Pazarlama
 * değil; ders saati değişikliği, ödev hatırlatması gibi kursla ilgili bildirimler için. Duyuru öğrenci
 * sayfasında da listelenir.
 */

type Duyuru = { id: number; konu: string; metin: string; alici: number; created_at: string };

export default function Duyurular({ api, kurs }: { api: EgitimApi; kurs: Kurs }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [liste, setListe] = useState<Duyuru[] | null>(null);
  const [konu, setKonu] = useState('');
  const [metin, setMetin] = useState('');
  const [mesgul, setMesgul] = useState(false);

  const yukle = useCallback(async () => {
    try {
      setListe((await api.duyurular(kurs.id)).items);
    } catch (e) {
      toast.error(hataMetni(t, e));
      setListe([]);
    }
  }, [api, kurs.id, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const gonder = async () => {
    if (!konu.trim() || !metin.trim()) {
      toast.error(t('egitim.hata.zorunlu'));
      return;
    }
    if (!window.confirm(t('egitim.duyuru.onay', { sayi: kurs.ogrenci ?? 0 }))) return;
    setMesgul(true);
    try {
      const r = await api.duyuru(kurs.id, { konu: konu.trim(), metin: metin.trim() });
      toast.success(t('egitim.duyuru.gonderildi', { sayi: r.alici }));
      setKonu('');
      setMetin('');
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  return (
    <div className="grid gap-4" data-testid="egitim-duyurular">
      <div className={`${KART} grid gap-3 p-4 sm:p-6`}>
        <div>
          <h4 className="flex items-center gap-2 text-base font-semibold">
            <Megaphone className="h-4 w-4 text-blue-300" aria-hidden="true" />
            {t('egitim.duyuru.yeni')}
          </h4>
          <p className="mt-1 text-sm text-muted-foreground">{t('egitim.duyuru.aciklama')}</p>
        </div>
        <Alan etiket={t('egitim.duyuru.konu')}>
          <Input value={konu} onChange={(e) => setKonu(e.target.value)} maxLength={150} data-testid="egitim-duyuru-konu" />
        </Alan>
        <Alan etiket={t('egitim.duyuru.metin')}>
          <textarea value={metin} onChange={(e) => setMetin(e.target.value)} rows={5} maxLength={5000} className={METIN_ALANI} data-testid="egitim-duyuru-metin" />
        </Alan>
        <div className="flex justify-end">
          <Button onClick={() => void gonder()} disabled={mesgul || !konu.trim() || !metin.trim()} className="gap-1.5" data-testid="egitim-duyuru-gonder">
            {mesgul ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Send className="h-4 w-4 rtl:-scale-x-100" aria-hidden="true" />}
            {t('egitim.duyuru.gonder')}
          </Button>
        </div>
      </div>
      <div className={`${KART} p-4 sm:p-6`}>
        <h4 className="mb-3 text-base font-semibold">{t('egitim.duyuru.gecmis')}</h4>
        {liste === null ? (
          <Yukleniyor />
        ) : liste.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">{t('egitim.duyuru.bos')}</p>
        ) : (
          <ul className="divide-y divide-white/5" data-testid="egitim-duyuru-liste">
            {liste.map((d) => (
              <li key={d.id} className="py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{d.konu}</span>
                  <Rozet>{t('egitim.duyuru.alici', { sayi: d.alici })}</Rozet>
                  <span className="text-xs text-muted-foreground">{tarihSaat(d.created_at, kurs.saat_dilimi, dil)}</span>
                </div>
                <p className="mt-1 whitespace-pre-line text-sm text-muted-foreground">{d.metin}</p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
