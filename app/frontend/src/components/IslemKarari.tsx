import { useState, type ReactNode } from 'react';
import { CheckCircle2, ExternalLink, FileCheck2, Loader2, MessageSquareWarning, PackageCheck, ReceiptText, XCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import {
  olumluMu,
  tarihSaatBicimle,
  tutarBicimle,
  yerelBaslik,
  type IslemSonucu,
  type KararlikIslem,
} from '@/lib/imzaliIslem';

/**
 * Bir imzalı işlemin kartı: özet + karar düğmeleri + onay penceresi.
 *
 * Aynı kart iki yerde çiziliyor: girişsiz `/islem/<jeton>` sayfası ve
 * müşteri panelindeki "Onay bekleyenler". Kararın nereye gideceğini
 * (`onKarar`) çağıran veriyor; kart yalnız ne gösterileceğini ve hangi
 * sonucun not istediğini biliyor.
 *
 * Her karar önce bir onay penceresinden geçiyor: bağlantı tek kullanımlık,
 * yanlış düğmeye basılan karar geri alınamıyor.
 */

const NOT_SINIRI = 2000;

const TUR_IKONU: Record<string, typeof ReceiptText> = {
  teklif_kabul: ReceiptText,
  teslimat_onay: PackageCheck,
  rapor_goruntule: FileCheck2,
};

function guvenliAdres(adres?: string | null): string | null {
  if (!adres) return null;
  try {
    const u = new URL(adres);
    return u.protocol === 'https:' || u.protocol === 'http:' ? u.toString() : null;
  } catch {
    return null;
  }
}

function Satir({ etiket, children }: { etiket: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 border-b border-white/5 py-2 last:border-b-0 sm:flex-row sm:items-baseline sm:justify-between sm:gap-4">
      <dt className="text-xs uppercase tracking-wider text-muted-foreground">{etiket}</dt>
      <dd className="min-w-0 break-words text-sm sm:text-right">{children}</dd>
    </div>
  );
}

export default function IslemKarari({
  islem,
  onKarar,
  kompakt = false,
  testId = 'islem-karti',
}: {
  islem: KararlikIslem;
  onKarar: (sonuc: IslemSonucu, not?: string) => Promise<void>;
  kompakt?: boolean;
  testId?: string;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const a = islem.ayrinti || {};
  const [secilen, setSecilen] = useState<IslemSonucu | null>(null);
  const [not, setNot] = useState('');
  const [calisiyor, setCalisiyor] = useState(false);
  const [hata, setHata] = useState<string | null>(null);

  const Ikon = TUR_IKONU[islem.tur] ?? FileCheck2;
  const notZorunlu = secilen ? islem.not_zorunlu.includes(secilen) : false;
  const notAlani = secilen === 'red' || secilen === 'revizyon';
  const notGecersiz = (notZorunlu && !not.trim()) || not.length > NOT_SINIRI;
  const incele = guvenliAdres(a.baglanti);
  // Sunucunun başlığı Türkçe (e-posta için); kartta seçili dilde kur.
  const baslik = yerelBaslik(islem, t, dil);

  const ac = (sonuc: IslemSonucu) => {
    setSecilen(sonuc);
    setNot('');
    setHata(null);
  };

  const onayla = async () => {
    if (!secilen || notGecersiz) return;
    setCalisiyor(true);
    setHata(null);
    try {
      await onKarar(secilen, notAlani ? not.trim() : undefined);
      setSecilen(null);
    } catch (h) {
      const kod = (h as { kod?: string })?.kod;
      setHata(t(`islem.hata.${kod ?? 'genel'}`, { defaultValue: t('islem.hata.genel') }));
    } finally {
      setCalisiyor(false);
    }
  };

  return (
    <article
      className={`cam-kart rounded-2xl border border-white/10 bg-white/[0.03] ${kompakt ? 'p-4 sm:p-5' : 'p-5 sm:p-7'}`}
      data-testid={testId}
    >
      <header className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-purple-600 to-pink-600">
          <Ikon className="h-5 w-5 text-white" aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-xs uppercase tracking-widest text-muted-foreground">
            {t(`islem.tur.${islem.tur}.baslik`, { defaultValue: islem.tur })}
          </p>
          <h2 className={`${kompakt ? 'text-base' : 'text-lg sm:text-xl'} break-words font-semibold`}>{baslik}</h2>
        </div>
      </header>

      {!kompakt && (
        <p className="mt-3 text-sm text-muted-foreground">
          {t(`islem.tur.${islem.tur}.aciklama`, { defaultValue: '' })}
        </p>
      )}

      <dl className="mt-4 rounded-xl border border-white/5 bg-white/[0.02] px-4 py-1">
        {islem.tur === 'teklif_kabul' && (
          <>
            <Satir etiket={t('islem.alan.tutar')}>
              <span className="text-lg font-bold" data-testid="islem-tutar">
                {tutarBicimle(a.tutar, a.para_birimi, dil)}
              </span>
            </Satir>
            {a.paket && <Satir etiket={t('islem.alan.paket')}>{a.paket}</Satir>}
            {a.profil && <Satir etiket={t('islem.alan.profil')}>{a.profil}</Satir>}
            {a.donem && (
              <Satir etiket={t('islem.alan.donem')}>{t(`islem.donem.${a.donem}`, { defaultValue: a.donem })}</Satir>
            )}
            {a.eklentiler && a.eklentiler.length > 0 && (
              <Satir etiket={t('islem.alan.eklentiler')}>{a.eklentiler.join(', ')}</Satir>
            )}
            {a.ai_pm && <Satir etiket={t('islem.alan.aiPm')}>{a.ai_pm}</Satir>}
            {a.kredi && <Satir etiket={t('islem.alan.kredi')}>{t('islem.krediPaketi', { sayi: a.kredi })}</Satir>}
            {a.fatura_no && <Satir etiket={t('islem.alan.fatura')}>{a.fatura_no}</Satir>}
          </>
        )}
        {islem.tur === 'teslimat_onay' && (
          <>
            {a.proje && <Satir etiket={t('islem.alan.proje')}>{a.proje}</Satir>}
            {a.asama && (
              <Satir etiket={t('islem.alan.asama')}>
                {t(`panel.asama.${a.asama}.ad`, { defaultValue: a.asama_etiketi || a.asama })}
              </Satir>
            )}
          </>
        )}
        {islem.tur === 'rapor_goruntule' && (
          <>
            {a.alan_adi && <Satir etiket={t('islem.alan.site')}>{a.alan_adi}</Satir>}
            {a.puan != null && <Satir etiket={t('islem.alan.puan')}>{a.puan}/100</Satir>}
          </>
        )}
        {a.not && (
          <Satir etiket={t('islem.alan.not')}>
            <span className="whitespace-pre-line">{a.not}</span>
          </Satir>
        )}
        {islem.son_kullanma && (
          <Satir etiket={t('islem.alan.sonKullanma')}>{tarihSaatBicimle(islem.son_kullanma, dil)}</Satir>
        )}
      </dl>

      {incele && (
        <a
          href={incele}
          target="_blank"
          rel="noopener noreferrer nofollow"
          className="mt-4 inline-flex items-center gap-2 text-sm text-purple-300 underline-offset-4 hover:underline"
        >
          <ExternalLink className="h-4 w-4" aria-hidden="true" />
          {t('islem.inceleBaglantisi')}
        </a>
      )}

      <div className={`mt-5 grid gap-3 ${islem.sonuclar.length > 1 ? 'sm:grid-cols-2' : ''}`}>
        {islem.sonuclar.map((sonuc) => {
          const olumlu = olumluMu(sonuc);
          return (
            <Button
              key={sonuc}
              type="button"
              size="lg"
              variant={olumlu ? 'default' : 'outline'}
              className={`h-12 w-full gap-2 ${olumlu ? '' : '!bg-transparent'}`}
              onClick={() => ac(sonuc)}
              data-testid={`islem-eylem-${sonuc}`}
            >
              {olumlu ? (
                <CheckCircle2 className="h-5 w-5" aria-hidden="true" />
              ) : sonuc === 'revizyon' ? (
                <MessageSquareWarning className="h-5 w-5" aria-hidden="true" />
              ) : (
                <XCircle className="h-5 w-5" aria-hidden="true" />
              )}
              {t(`islem.eylem.${sonuc}`)}
            </Button>
          );
        })}
      </div>

      {secilen && (
        <div
          className="fixed inset-0 z-[70] flex items-end justify-center bg-black/70 p-0 sm:items-center sm:p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="islem-onay-baslik"
          onClick={() => !calisiyor && setSecilen(null)}
        >
          <div
            className="cam-kart w-full max-w-md rounded-t-2xl border border-white/10 bg-background p-6 shadow-2xl sm:rounded-2xl"
            onClick={(o) => o.stopPropagation()}
            data-testid="islem-onay-penceresi"
          >
            <h3 id="islem-onay-baslik" className="text-lg font-semibold">
              {t(`islem.onay.${secilen}.baslik`)}
            </h3>
            <p className="mt-2 break-words text-sm text-muted-foreground">{t(`islem.onay.${secilen}.metin`)}</p>
            {notAlani && (
              <div className="mt-4 grid gap-2">
                <label htmlFor="islem-onay-not" className="text-sm font-medium">
                  {t(`islem.onay.${secilen}.notEtiket`)}
                  {!notZorunlu && <span className="ml-1 text-xs text-muted-foreground">({t('islem.istegeBagli')})</span>}
                </label>
                <Textarea
                  id="islem-onay-not"
                  rows={4}
                  value={not}
                  maxLength={NOT_SINIRI}
                  onChange={(e) => setNot(e.target.value)}
                  placeholder={t(`islem.onay.${secilen}.notYertutucu`)}
                  data-testid="islem-onay-not"
                  autoFocus
                />
                <p className="text-right text-xs text-muted-foreground">
                  {not.length}/{NOT_SINIRI}
                </p>
              </div>
            )}
            {hata && (
              <p className="mt-3 text-sm text-red-300" role="alert">
                {hata}
              </p>
            )}
            <div className="mt-6 grid grid-cols-2 gap-2">
              <Button
                variant="outline"
                className="!bg-transparent"
                onClick={() => setSecilen(null)}
                disabled={calisiyor}
              >
                {t('islem.vazgec')}
              </Button>
              <Button
                onClick={() => void onayla()}
                disabled={calisiyor || notGecersiz}
                data-testid="islem-onayla"
                autoFocus={!notAlani}
              >
                {calisiyor && <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />}
                {t(`islem.onay.${secilen}.dugme`)}
              </Button>
            </div>
          </div>
        </div>
      )}
    </article>
  );
}
