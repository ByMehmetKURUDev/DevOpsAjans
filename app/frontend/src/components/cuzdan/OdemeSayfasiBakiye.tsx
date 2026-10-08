import { useEffect, useRef, useState } from 'react';
import { Loader2, Wallet } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { BelgeHatasi, paraBicimle } from '@/lib/belge';
import { faturamiBakiyedenOde, istekAnahtari, odemeSayfasiBakiyesi, type FaturaBakiyeBilgisi } from '@/lib/cuzdan';

/**
 * Faz 5C — Girişsiz ödeme sayfasında (`/ode/<jeton>`) oturum açıksa ve fatura bu hesabınsa "Bakiyeden öde".
 * Sunucu jetonun faturası başka hesabınsa 404 döndürür; o durumda (ve bakiye yoksa) hiçbir şey çizilmez.
 */
export default function OdemeSayfasiBakiye({ jeton, onOdendi }: { jeton: string; onOdendi: (tam: boolean) => void }) {
  const { t, i18n } = useTranslation();
  const [bilgi, setBilgi] = useState<FaturaBakiyeBilgisi | null>(null);
  const [mesgul, setMesgul] = useState(false);
  const anahtar = useRef(istekAnahtari());

  useEffect(() => {
    let iptal = false;
    odemeSayfasiBakiyesi(jeton)
      .then((b) => {
        if (!iptal) setBilgi(b);
      })
      .catch(() => {
        if (!iptal) setBilgi(null);
      });
    return () => {
      iptal = true;
    };
  }, [jeton]);

  if (!bilgi || !bilgi.uygulanabilir || bilgi.bakiye <= 0) return null;

  const tutar = Math.min(bilgi.bakiye, bilgi.kalan);
  const tam = bilgi.bakiye >= bilgi.kalan;
  const metin = paraBicimle(tutar, bilgi.para_birimi, i18n.language);

  const ode = async () => {
    setMesgul(true);
    try {
      await faturamiBakiyedenOde(bilgi.fatura_id, tam ? null : tutar.toFixed(2), anahtar.current);
      anahtar.current = istekAnahtari();
      toast.success(t('cuzdan.odemeSayfasi.basarili'));
      setBilgi(null);
      onOdendi(tam);
    } catch (h) {
      const kod = h instanceof BelgeHatasi ? h.kod : 'genel';
      toast.error(t(`cuzdan.hata.${kod}`, { defaultValue: t('cuzdan.hata.genel') }));
    } finally {
      setMesgul(false);
    }
  };

  return (
    <div className="mt-7 rounded-xl border border-purple-400/30 bg-purple-500/[0.07] p-4" data-testid="odeme-sayfasi-bakiye">
      <p className="flex items-center gap-2 text-sm font-semibold text-white">
        <Wallet className="h-4 w-4 text-purple-300" aria-hidden="true" />
        {t('cuzdan.odemeSayfasi.baslik')}
      </p>
      <p className="mt-1 text-sm text-muted-foreground">
        {t('cuzdan.odemeSayfasi.aciklama', { tutar: paraBicimle(bilgi.bakiye, bilgi.para_birimi, i18n.language) })}
      </p>
      <button
        type="button"
        onClick={() => void ode()}
        disabled={mesgul}
        className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-xl border border-purple-300/40 bg-purple-500/20 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-purple-500/30 disabled:opacity-60"
        data-testid="odeme-sayfasi-bakiyeden-ode"
      >
        {mesgul && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
        {t('cuzdan.odemeSayfasi.dugme', { tutar: metin })}
      </button>
    </div>
  );
}
