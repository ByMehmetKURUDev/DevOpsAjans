import { useEffect, useMemo, useState } from 'react';
import { Check, Copy, Loader2, Sparkles, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import {
  AMAC_SECENEKLERI,
  BUTCE_SECENEKLERI,
  KAPSAM_SECENEKLERI,
  ZAMAN_SECENEKLERI,
  briefUret,
  briefiSakla,
  metindenTahmin,
  saklananiCoz,
  type Brief,
} from '@/lib/kesifBrief';

/**
 * Talepten uzman promptları üretir.
 *
 * Talep kaydı sihirbazın yapılandırılmış cevaplarını TAŞIMIYOR — yalnızca
 * özet metni ve kaynağı var. O yüzden burada metinden bir ilk tahmin
 * çıkarılıyor ve yönetici düzeltiyor: tahmini doğruymuş gibi kullanıp
 * yanlış brief üretmektense, bir tık düzeltme istemek doğru olan. Elle
 * yazılmış taleplerde de aynı ekran çalışıyor.
 *
 * Üretilen metin müşteriye gitmiyor; kopyalanıp bir dil modeline veriliyor.
 */

interface Props {
  talepId: number | string;
  musteri: string;
  konu: string;
  mesaj: string;
  /** Talep kaydındaki `brief` sütunu; daha önce üretildiyse dolu. */
  kayitliBrief?: string | null;
  /** Kaydetme başarılıysa listeyi tazelemek için. */
  onSaved?: () => void;
  onClose: () => void;
}

export default function UzmanPromptlari({
  talepId,
  musteri,
  konu,
  mesaj,
  kayitliBrief,
  onSaved,
  onClose,
}: Props) {
  const { t } = useTranslation();
  const tahmin = useMemo(() => metindenTahmin(mesaj), [mesaj]);
  /*
   * Daha önce üretilmişse onu aç.
   *
   * Brief yalnızca ekranda dursaydı her açılışta yeniden üretilirdi ve
   * yönetici hangi seçimlerle üretildiğini hatırlamak zorunda kalırdı.
   * Kayıt talebin kendi satırında duruyor, yani projeye çevrilse de
   * kayboluyor değil.
   */
  const onceki = useMemo(() => saklananiCoz(kayitliBrief), [kayitliBrief]);

  const [amac, setAmac] = useState(onceki?.girdi.amac || tahmin.amac || '');
  const [kapsam, setKapsam] = useState<string[]>(onceki?.girdi.kapsam || tahmin.kapsam || []);
  const [zaman, setZaman] = useState(onceki?.girdi.zaman || tahmin.zaman || '');
  const [butce, setButce] = useState(onceki?.girdi.butce || '');
  const [yukleniyor, setYukleniyor] = useState(false);
  const [brief, setBrief] = useState<Brief | null>(onceki?.brief || null);
  const [secili, setSecili] = useState('zincir');
  const [kopyalanan, setKopyalanan] = useState('');

  useEffect(() => {
    const kapat = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', kapat);
    return () => window.removeEventListener('keydown', kapat);
  }, [onClose]);

  const kapsamDegistir = (k: string) =>
    setKapsam((o) => (o.includes(k) ? o.filter((x) => x !== k) : [...o, k]));

  const uret = async () => {
    setYukleniyor(true);
    const girdi = {
      amac,
      serbest: mesaj,
      kapsam,
      zaman,
      butce,
      musteri,
      proje: konu,
    };
    try {
      const sonuc = await briefUret(girdi);
      setBrief(sonuc);
      setSecili('zincir');

      // Kayıt ayrı bir adım: üretim başarılı olsa da kayıt başarısız
      // olabilir (yetki, ağ). O durumda metin ekranda duruyor, yalnızca
      // kalıcı olmuyor — bunu sessiz geçmiyoruz.
      const kaydedildi = await briefiSakla(talepId, girdi, sonuc);
      if (kaydedildi) onSaved?.();
      else toast.warning(t('uzman.kaydedilemedi'));
    } catch {
      toast.error(t('uzman.hata'));
    } finally {
      setYukleniyor(false);
    }
  };

  const metin =
    brief && (secili === 'zincir'
      ? brief.zincir
      : brief.roller.find((r) => r.id === secili)?.prompt || '');

  const kopyala = async () => {
    try {
      await navigator.clipboard.writeText(metin || '');
      setKopyalanan(secili);
      setTimeout(() => setKopyalanan(''), 1500);
    } catch {
      // Pano izni yoksa metin zaten ekranda duruyor.
      toast.warning(t('uzman.kopyaHatasi'));
    }
  };

  const cip = (aktif: boolean) =>
    'rounded-full px-3 py-1.5 text-xs transition-colors ' +
    (aktif
      ? 'bg-purple-500/20 text-purple-200 ring-1 ring-purple-400/40'
      : 'bg-white/5 text-muted-foreground hover:text-foreground');

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-background/80 p-4 backdrop-blur-sm">
      <div className="glass relative my-8 w-full max-w-3xl rounded-2xl border border-purple-500/30 p-8">
        <button
          className="absolute right-4 top-4 rounded-lg p-2 hover:bg-white/5"
          onClick={onClose}
          aria-label={t('uzman.kapat')}
        >
          <X className="h-4 w-4" />
        </button>

        <div className="mb-1 flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-purple-300" />
          <h3 className="text-lg font-bold">{t('uzman.baslik')}</h3>
        </div>
        <p className="mb-6 text-xs text-muted-foreground">{t('uzman.aciklama')}</p>

        <div className="space-y-4">
          <div>
            <p className="mb-2 text-[11px] uppercase tracking-widest text-muted-foreground">
              {t('uzman.amac')}
            </p>
            <div className="flex flex-wrap gap-2">
              {AMAC_SECENEKLERI.map((a) => (
                <button key={a} className={cip(amac === a)} onClick={() => setAmac(a)}>
                  {t(`kesif.amac.${a}`, { defaultValue: a })}
                </button>
              ))}
            </div>
          </div>

          <div>
            <p className="mb-2 text-[11px] uppercase tracking-widest text-muted-foreground">
              {t('uzman.kapsam')}
            </p>
            <div className="flex flex-wrap gap-2">
              {KAPSAM_SECENEKLERI.map((k) => (
                <button
                  key={k}
                  className={cip(kapsam.includes(k))}
                  onClick={() => kapsamDegistir(k)}
                >
                  {t(`kesif.kapsam.${k}`, { defaultValue: k })}
                </button>
              ))}
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <p className="mb-2 text-[11px] uppercase tracking-widest text-muted-foreground">
                {t('uzman.zaman')}
              </p>
              <div className="flex flex-wrap gap-2">
                {ZAMAN_SECENEKLERI.map((z) => (
                  <button key={z} className={cip(zaman === z)} onClick={() => setZaman(z)}>
                    {t(`kesif.zaman.${z}`, { defaultValue: z })}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <p className="mb-2 text-[11px] uppercase tracking-widest text-muted-foreground">
                {t('uzman.butce')}
              </p>
              <div className="flex flex-wrap gap-2">
                {BUTCE_SECENEKLERI.map((b) => (
                  <button key={b} className={cip(butce === b)} onClick={() => setButce(b)}>
                    {t(`kesif.butce.${b}`, { defaultValue: b })}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

        <Button
          onClick={uret}
          disabled={yukleniyor}
          className="mt-6 h-11 border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white"
        >
          {yukleniyor ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              {t('uzman.uretiliyor')}
            </>
          ) : (
            t(brief ? 'uzman.yenidenUret' : 'uzman.uret')
          )}
        </Button>

        {onceki?.tarih && (
          <p className="mt-2 text-xs text-muted-foreground">
            {t('uzman.kayitli', {
              tarih: new Date(onceki.tarih).toLocaleString('tr-TR'),
            })}
          </p>
        )}

        {brief && (
          <div className="mt-6">
            <div className="mb-3 flex flex-wrap gap-2">
              <button className={cip(secili === 'zincir')} onClick={() => setSecili('zincir')}>
                {t('uzman.zincir')}
              </button>
              {brief.roller.map((r) => (
                <button
                  key={r.id}
                  className={cip(secili === r.id)}
                  onClick={() => setSecili(r.id)}
                >
                  {r.ad}
                </button>
              ))}
            </div>

            <Textarea
              readOnly
              rows={16}
              value={metin || ''}
              className="border-white/10 bg-white/5 font-mono text-xs"
            />

            <Button
              onClick={kopyala}
              variant="outline"
              className="mt-3 h-11 border-white/20 !bg-transparent"
            >
              {kopyalanan === secili ? (
                <>
                  <Check className="mr-2 h-4 w-4 text-emerald-300" />
                  {t('uzman.kopyalandi')}
                </>
              ) : (
                <>
                  <Copy className="mr-2 h-4 w-4" />
                  {t('uzman.kopyala')}
                </>
              )}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
