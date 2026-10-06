import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { CheckCircle2, Loader2 } from 'lucide-react';

import AydinlatmaSatiri from '@/components/AydinlatmaSatiri';
import { Button } from '@/components/ui/button';
import { VITRIN, TalepHatasi, talepGonder } from '@/lib/modulVitrini';

/**
 * "Bu modülü/paketi isteyin" formu (Faz 4V).
 *
 * Yeni bir form altyapısı değil: gönderim `POST /api/v1/modul-vitrini/talep`
 * ucuna gidiyor, o da kaydı mevcut `inquiries` akışına yazıyor (CRM adayı
 * kendiliğinden açılıyor, yöneticiye iletişim formu bildirimi gidiyor).
 *
 * KVKK (Faz 4G deseni): gönder düğmesinin altında aydınlatma satırı +
 * /gizlilik bağlantısı (onay kutusu YOK); pazarlama izni ayrı, isteğe bağlı,
 * varsayılan işaretsiz kutu — metni sunucudaki izin metniyle aynı
 * (`services/pazarlama_izni.METINLER`, test karşılaştırıyor).
 */
const ALAN = 'w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-purple-400 focus:outline-none';

export default function TalepFormu({
  tur,
  anahtar,
  dil,
  isletmeTuru = '',
}: {
  tur: 'modul' | 'paket';
  anahtar: string;
  dil: string;
  isletmeTuru?: string;
}) {
  const { t } = useTranslation();
  const [form, setForm] = useState({ ad: '', eposta: '', telefon: '', isletme: isletmeTuru, not: '', bal: '' });
  const [izin, setIzin] = useState(false);
  const [durum, setDurum] = useState<'bos' | 'gonderiliyor' | 'tamam'>('bos');
  const [hata, setHata] = useState('');

  const yaz = (alan: keyof typeof form) => (o: { target: { value: string } }) => setForm((f) => ({ ...f, [alan]: o.target.value }));

  const gonder = async (olay: FormEvent) => {
    olay.preventDefault();
    if (durum !== 'bos') return;
    if (!form.ad.trim()) return setHata(t('modulVitrini.form.hata.ad_gerekli'));
    if (!form.eposta.trim()) return setHata(t('modulVitrini.form.hata.eposta_gecersiz'));
    setHata('');
    setDurum('gonderiliyor');
    try {
      await talepGonder({
        tur,
        anahtar,
        ad: form.ad.trim(),
        eposta: form.eposta.trim(),
        telefon: form.telefon.trim() || undefined,
        isletme_turu: form.isletme || undefined,
        not: form.not.trim() || undefined,
        dil,
        pazarlama_izni: izin,
        web_sitesi: form.bal || undefined,
      });
      setDurum('tamam');
    } catch (h) {
      const kod = h instanceof TalepHatasi ? h.kod : 'genel';
      setHata(t(`modulVitrini.form.hata.${kod}`, { defaultValue: t('modulVitrini.form.hata.genel') }));
      setDurum('bos');
    }
  };

  const baslik = t(tur === 'modul' ? 'modulVitrini.form.baslikModul' : 'modulVitrini.form.baslikPaket');

  return (
    <section
      id="talep"
      className="cam-kart cam-gok scroll-mt-28 rounded-3xl border border-white/10 bg-white/[0.03] p-6 md:p-10"
      aria-labelledby="talep-baslik"
      data-talep-formu={`${tur}:${anahtar}`}
    >
      {durum === 'tamam' ? (
        <div className="py-6 text-center" role="status" data-talep-tamam>
          <CheckCircle2 className="mx-auto mb-3 h-10 w-10 text-emerald-400" aria-hidden="true" />
          <h2 id="talep-baslik" className="text-xl font-semibold">
            {t('modulVitrini.form.basarili')}
          </h2>
          <p className="mx-auto mt-2 max-w-lg text-sm text-muted-foreground">{t('modulVitrini.form.basariliMetin')}</p>
        </div>
      ) : (
        <form onSubmit={gonder} className="grid gap-8 lg:grid-cols-5" noValidate>
          <div className="lg:col-span-2">
            <h2 id="talep-baslik" className="text-2xl font-bold md:text-3xl">
              {baslik}
            </h2>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{t('modulVitrini.form.giris')}</p>
          </div>
          <div className="min-w-0 space-y-4 lg:col-span-3">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="min-w-0">
                <label htmlFor="talep-ad" className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {t('modulVitrini.form.ad')} *
                </label>
                <input id="talep-ad" name="ad" required maxLength={120} autoComplete="name" value={form.ad} onChange={yaz('ad')} className={ALAN} />
              </div>
              <div className="min-w-0">
                <label htmlFor="talep-eposta" className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {t('modulVitrini.form.eposta')} *
                </label>
                <input
                  id="talep-eposta"
                  name="eposta"
                  type="email"
                  required
                  maxLength={254}
                  autoComplete="email"
                  dir="ltr"
                  value={form.eposta}
                  onChange={yaz('eposta')}
                  className={ALAN}
                />
              </div>
              <div className="min-w-0">
                <label htmlFor="talep-telefon" className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {t('modulVitrini.form.telefon')}
                </label>
                <input
                  id="talep-telefon"
                  name="telefon"
                  type="tel"
                  maxLength={40}
                  autoComplete="tel"
                  dir="ltr"
                  value={form.telefon}
                  onChange={yaz('telefon')}
                  className={ALAN}
                />
              </div>
              <div className="min-w-0">
                <label htmlFor="talep-isletme" className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {t('modulVitrini.form.isletme')}
                </label>
                <select id="talep-isletme" name="isletme_turu" value={form.isletme} onChange={yaz('isletme')} className={`${ALAN} bg-background`}>
                  <option value="">{t('modulVitrini.form.isletmeSec')}</option>
                  {VITRIN.paketler.map((p) => (
                    <option key={p.anahtar} value={p.anahtar}>
                      {t(`modulVitrini.p.${p.anahtar}.ad`)}
                    </option>
                  ))}
                  <option value="diger">{t('modulVitrini.form.diger')}</option>
                </select>
              </div>
            </div>
            <div>
              <label htmlFor="talep-not" className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {t('modulVitrini.form.not')}
              </label>
              <textarea
                id="talep-not"
                name="not"
                rows={4}
                maxLength={2000}
                value={form.not}
                onChange={yaz('not')}
                placeholder={t('modulVitrini.form.notYerTutucu')}
                className={`${ALAN} resize-y`}
              />
            </div>
            {/* Bal küpü: ekranda ve ekran okuyucuda yok; bot doldurursa sunucu sessizce yok sayar. */}
            <div className="absolute -start-[9999px] h-px w-px overflow-hidden" aria-hidden="true">
              <label htmlFor="talep-web">Web</label>
              <input id="talep-web" name="web_sitesi" tabIndex={-1} autoComplete="off" value={form.bal} onChange={yaz('bal')} />
            </div>
            <label className="flex cursor-pointer items-start gap-3 text-sm text-muted-foreground" data-pazarlama-izni>
              <input
                type="checkbox"
                checked={izin}
                onChange={(o) => setIzin(o.target.checked)}
                className="mt-0.5 h-4 w-4 shrink-0 accent-purple-500"
              />
              <span>
                {t('modulVitrini.form.pazarlama')}{' '}
                <span className="text-xs opacity-70">({t('modulVitrini.form.istegeBagli')})</span>
              </span>
            </label>
            {hata && (
              <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300" role="alert" data-talep-hata>
                {hata}
              </p>
            )}
            <Button
              type="submit"
              disabled={durum === 'gonderiliyor'}
              className="h-12 w-full gap-2 border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white"
              data-talep-gonder
            >
              {durum === 'gonderiliyor' && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
              {t(durum === 'gonderiliyor' ? 'modulVitrini.form.gonderiliyor' : 'modulVitrini.form.gonder')}
            </Button>
            <AydinlatmaSatiri className="text-center text-[11px] leading-relaxed text-muted-foreground" />
          </div>
        </form>
      )}
    </section>
  );
}
