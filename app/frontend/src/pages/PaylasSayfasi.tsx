import { useEffect, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { AlertCircle, Download, FileText, Home, Loader2, Lock } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  DosyaHatasi,
  adresiIndir,
  boyutBicimle,
  paylasimBilgisi,
  paylasimdanIndir,
  tarihBicimle,
  type PaylasimBilgisi,
} from '@/lib/dosyalar';

/**
 * Girişsiz paylaşım sayfası: `/paylas/<jeton>` (Faz 2C).
 *
 * Jetonun kendisi yetki; sayfa yalnız dosya adı, boyutu, son kullanma ve
 * kalan indirme hakkını gösteriyor (müşteri, klasör, depo anahtarı yok).
 * Parolalıysa parola sorulur; her indirme sayaçtan düşer. Arama motorları
 * için noindex; prerender edilmiyor.
 */
export default function PaylasSayfasi() {
  const { jeton = '' } = useParams<{ jeton: string }>();
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [bilgi, setBilgi] = useState<PaylasimBilgisi | null>(null);
  const [hataKodu, setHataKodu] = useState<string | null>(null);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [sifre, setSifre] = useState('');
  const [indiriliyor, setIndiriliyor] = useState(false);
  const [formHatasi, setFormHatasi] = useState<string | null>(null);
  const [indirildi, setIndirildi] = useState(false);

  useEffect(() => {
    const etiket = document.createElement('meta');
    etiket.name = 'robots';
    etiket.content = 'noindex, nofollow';
    document.head.appendChild(etiket);
    const onceki = document.title;
    return () => {
      etiket.remove();
      document.title = onceki;
    };
  }, []);

  useEffect(() => {
    document.title = t('dosyalar.paylas.sayfaBasligi');
  }, [t]);

  useEffect(() => {
    let iptal = false;
    paylasimBilgisi(jeton)
      .then((b) => {
        if (!iptal) setBilgi(b);
      })
      .catch((h) => {
        if (!iptal) setHataKodu(h instanceof DosyaHatasi ? h.kod : 'genel');
      })
      .finally(() => {
        if (!iptal) setYukleniyor(false);
      });
    return () => {
      iptal = true;
    };
  }, [jeton]);

  const indir = async (e: FormEvent) => {
    e.preventDefault();
    setIndiriliyor(true);
    setFormHatasi(null);
    try {
      const sonuc = await paylasimdanIndir(jeton, sifre);
      adresiIndir(sonuc.adres);
      setIndirildi(true);
      setBilgi((b) => (b && b.kalan_indirme !== null ? { ...b, kalan_indirme: Math.max(0, b.kalan_indirme - 1) } : b));
    } catch (h) {
      const kod = h instanceof DosyaHatasi ? h.kod : 'genel';
      if (kod === 'sifre_yanlis') setFormHatasi(t('dosyalar.paylas.sifreYanlis'));
      else setHataKodu(kod);
    } finally {
      setIndiriliyor(false);
    }
  };

  let icerik;
  if (yukleniyor) {
    icerik = (
      <div className="flex min-h-[40vh] items-center justify-center text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" aria-hidden="true" />
      </div>
    );
  } else if (hataKodu || !bilgi) {
    icerik = (
      <div className="cam-kart mx-auto max-w-lg rounded-3xl border border-white/10 bg-white/[0.03] p-6 text-center sm:p-8" data-testid="paylas-hata">
        <AlertCircle className="mx-auto mb-3 h-10 w-10 text-amber-300" aria-hidden="true" />
        <h1 className="text-xl font-semibold">{t('dosyalar.paylas.gecersizBaslik')}</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {t(`dosyalar.paylas.neden.${hataKodu || 'bulunamadi'}`, { defaultValue: t('dosyalar.paylas.neden.bulunamadi') })}
        </p>
        <Button asChild variant="outline" className="mt-6 !bg-transparent">
          <Link to="/">
            <Home className="mr-2 h-4 w-4" aria-hidden="true" />
            {t('dosyalar.paylas.anaSayfa')}
          </Link>
        </Button>
      </div>
    );
  } else {
    icerik = (
      <div className="cam-kart mx-auto max-w-lg rounded-3xl border border-white/10 bg-white/[0.03] p-6 sm:p-8" data-testid="paylas-kart">
        <p className="text-xs uppercase tracking-[0.25em] text-purple-300">{t('dosyalar.paylas.ust')}</p>
        <h1 className="mt-3 flex items-start gap-3 break-all text-xl font-semibold" data-testid="paylas-ad">
          <FileText className="mt-1 h-5 w-5 shrink-0 text-purple-300" aria-hidden="true" />
          {bilgi.ad}
        </h1>
        <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
          <div className="rounded-xl bg-white/[0.03] p-3">
            <dt className="text-xs text-muted-foreground">{t('dosyalar.paylas.boyut')}</dt>
            <dd className="font-medium">{boyutBicimle(bilgi.boyut, dil)}</dd>
          </div>
          <div className="rounded-xl bg-white/[0.03] p-3">
            <dt className="text-xs text-muted-foreground">{t('dosyalar.paylas.sonKullanma')}</dt>
            <dd className="font-medium">{tarihBicimle(bilgi.son_kullanma, dil, true)}</dd>
          </div>
          {bilgi.kalan_indirme !== null && (
            <div className="col-span-2 rounded-xl bg-white/[0.03] p-3">
              <dt className="text-xs text-muted-foreground">{t('dosyalar.paylas.kalanHak')}</dt>
              <dd className="font-medium" data-testid="paylas-kalan">
                {bilgi.kalan_indirme}
              </dd>
            </div>
          )}
        </dl>
        <form onSubmit={indir} className="mt-6 space-y-3">
          {bilgi.sifreli && (
            <label className="block text-sm">
              <span className="mb-1 flex items-center gap-2 text-muted-foreground">
                <Lock className="h-4 w-4" aria-hidden="true" /> {t('dosyalar.paylas.sifreGerekli')}
              </span>
              <Input
                type="password"
                value={sifre}
                onChange={(e) => setSifre(e.target.value)}
                autoComplete="off"
                className="bg-white/5"
                data-testid="paylas-sifre"
              />
            </label>
          )}
          {formHatasi && (
            <p className="text-sm text-red-300" role="alert">
              {formHatasi}
            </p>
          )}
          <Button
            type="submit"
            disabled={indiriliyor || (bilgi.sifreli && !sifre) || bilgi.kalan_indirme === 0}
            className="w-full gap-2 bg-gradient-to-r from-purple-600 to-pink-600 text-white"
            data-testid="paylas-indir"
          >
            {indiriliyor ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
            {t('dosyalar.indir')}
          </Button>
          {indirildi && <p className="text-center text-xs text-emerald-300">{t('dosyalar.paylas.basladi')}</p>}
        </form>
      </div>
    );
  }

  return (
    <div className="px-4 pb-20 pt-28 sm:pt-32" data-testid="paylas-sayfasi">
      {icerik}
    </div>
  );
}
