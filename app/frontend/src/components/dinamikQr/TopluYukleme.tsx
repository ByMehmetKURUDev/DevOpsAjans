import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, CheckCircle2, Download, FileUp, Loader2, XCircle } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { hataMetni, type QrApi, type QrKaydi, type QrMeta, type TopluOnizleme } from '@/lib/dinamikQr';

import { KART } from './ortak';

/**
 * Faz 4Q — toplu oluşturma: CSV yükle → sunucu satır satır doğrular (önizleme +
 * hatalı satırlar) → geçerli satırları oluştur → oluşturulanları ZIP indir.
 * Sınırlar sunucuda (satır, boyut, hesabın kalan kayıt hakkı).
 */

const ORNEK_CSV =
  'ad;tur;hedef;mesaj;takma_ad\n' +
  'Mağaza vitrini;url;https://ornek.com/vitrin;;vitrin\n' +
  'Google yorum;google_yorum;ChIJN1t_tDeuEmsRUsoyG83frY4;;\n' +
  'WhatsApp destek;whatsapp;+905551112233;Merhaba, bilgi almak istiyorum;\n' +
  'Kampanya kısa linki;kisa_link;https://ornek.com/kampanya;;\n';

export default function TopluYukleme({
  api,
  meta,
  onGeri,
  onBitti,
}: {
  api: QrApi;
  meta: QrMeta | null;
  onGeri: () => void;
  onBitti: (olusturulan: QrKaydi[]) => void;
}) {
  const { t } = useTranslation();
  const [onizleme, setOnizleme] = useState<TopluOnizleme | null>(null);
  const [dosyaAdi, setDosyaAdi] = useState('');
  const [yukleniyor, setYukleniyor] = useState(false);
  const [olusturuluyor, setOlusturuluyor] = useState(false);
  const [sonuc, setSonuc] = useState<{ olusturulan: QrKaydi[]; hatalar: { satir: number; kod: string }[] } | null>(null);
  const girdi = useRef<HTMLInputElement | null>(null);

  const ornekIndir = () => {
    const blob = new Blob(['﻿' + ORNEK_CSV], { type: 'text/csv;charset=utf-8' });
    const adres = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = adres;
    a.download = 'qr-ornek.csv';
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.setTimeout(() => URL.revokeObjectURL(adres), 4000);
  };

  const yukle = async (dosya: File | undefined) => {
    if (!dosya) return;
    const sinir = (meta?.csv_en_cok_kb ?? 512) * 1024;
    if (dosya.size > sinir) {
      toast.error(t('dinamikQr.hata.dosya_buyuk', { en_cok_kb: meta?.csv_en_cok_kb ?? 512 }));
      return;
    }
    setDosyaAdi(dosya.name);
    setYukleniyor(true);
    setSonuc(null);
    try {
      setOnizleme(await api.topluOnizleme(dosya));
    } catch (e) {
      setOnizleme(null);
      toast.error(hataMetni(t, e));
    } finally {
      setYukleniyor(false);
    }
  };

  const olustur = async () => {
    if (!onizleme) return;
    const gecerli = onizleme.satirlar.filter((s) => s.gecerli);
    if (!gecerli.length) return;
    setOlusturuluyor(true);
    try {
      const s = await api.topluOlustur(gecerli);
      setSonuc(s);
      toast.success(t('dinamikQr.toplu.sonuc', { sayi: s.olusturulan.length }));
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setOlusturuluyor(false);
    }
  };

  return (
    <div className={`${KART} space-y-5 p-4 sm:p-6`} data-testid="qr-toplu">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="sm" onClick={onGeri} className="gap-1 px-2">
          <ArrowLeft className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
          {t('dinamikQr.ayrinti.geri')}
        </Button>
        <h3 className="text-lg font-semibold">{t('dinamikQr.toplu.baslik')}</h3>
      </div>
      <div className="space-y-2 text-sm text-muted-foreground">
        <p>{t('dinamikQr.toplu.aciklama', { satir: meta?.csv_en_cok_satir ?? 500, kb: meta?.csv_en_cok_kb ?? 512 })}</p>
        <p className="text-xs">{t('dinamikQr.toplu.sutunlar')}</p>
      </div>
      <div className="flex flex-wrap gap-2">
        <input
          ref={girdi}
          type="file"
          accept=".csv,text/csv"
          className="sr-only"
          data-testid="qr-toplu-dosya"
          onChange={(e) => {
            void yukle(e.target.files?.[0]);
            e.target.value = '';
          }}
        />
        <Button onClick={() => girdi.current?.click()} disabled={yukleniyor} className="gap-1.5">
          {yukleniyor ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <FileUp className="h-4 w-4" aria-hidden="true" />}
          {t('dinamikQr.toplu.dosyaSec')}
        </Button>
        <Button variant="outline" className="gap-1.5 !bg-transparent border-white/20" onClick={ornekIndir}>
          <Download className="h-4 w-4" aria-hidden="true" />
          {t('dinamikQr.toplu.ornekIndir')}
        </Button>
      </div>

      {onizleme && (
        <div className="space-y-3" data-testid="qr-toplu-onizleme">
          <p className="text-sm">
            <span className="text-muted-foreground">{dosyaAdi}: </span>
            {t('dinamikQr.toplu.ozet', { toplam: onizleme.toplam, gecerli: onizleme.gecerli, hatali: onizleme.hatali })}
            {onizleme.kalan_hak !== null && (
              <span className="text-muted-foreground"> · {t('dinamikQr.toplu.kalanHak', { sayi: onizleme.kalan_hak })}</span>
            )}
          </p>
          <div className="max-h-96 overflow-auto rounded-lg border border-white/10">
            <table className="w-full min-w-[560px] text-xs">
              <thead className="sticky top-0 bg-black/70 text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 text-start font-medium">#</th>
                  <th className="px-3 py-2 text-start font-medium">{t('dinamikQr.liste.ad')}</th>
                  <th className="px-3 py-2 text-start font-medium">{t('dinamikQr.liste.tur')}</th>
                  <th className="px-3 py-2 text-start font-medium">{t('dinamikQr.ayrinti.hedef')}</th>
                  <th className="px-3 py-2 text-start font-medium">{t('dinamikQr.liste.durum')}</th>
                </tr>
              </thead>
              <tbody>
                {onizleme.satirlar.map((s) => (
                  <tr key={s.satir} className="border-t border-white/5" data-qr-toplu-satir={s.satir} data-gecerli={s.gecerli}>
                    <td className="px-3 py-1.5 tabular-nums text-muted-foreground">{s.satir}</td>
                    <td className="px-3 py-1.5">{s.ad || '—'}</td>
                    <td className="px-3 py-1.5">
                      {s.kisa_link ? t('dinamikQr.tur.kisa_link') : t(`dinamikQr.tur.${s.tur}`, { defaultValue: s.tur || '—' })}
                    </td>
                    <td className="max-w-[220px] truncate px-3 py-1.5" dir="ltr">
                      {s.hedef_ozet || '—'}
                    </td>
                    <td className="px-3 py-1.5">
                      {s.gecerli ? (
                        <span className="inline-flex items-center gap-1 text-emerald-300">
                          <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                          {t('dinamikQr.toplu.gecerli')}
                        </span>
                      ) : (
                        <span className="inline-flex items-start gap-1 text-red-300">
                          <XCircle className="mt-0.5 h-3.5 w-3.5 flex-none" aria-hidden="true" />
                          {s.hata?.alan ? `${t(`dinamikQr.alan.${s.hata.alan}`, { defaultValue: s.hata.alan })}: ` : ''}
                          {t(`dinamikQr.hata.${s.hata?.kod ?? 'genel'}`, { ...(s.hata ?? {}), defaultValue: t('dinamikQr.hata.genel') })}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!sonuc && (
            <Button onClick={olustur} disabled={olusturuluyor || onizleme.gecerli === 0} className="gap-1.5" data-testid="qr-toplu-olustur">
              {olusturuluyor && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
              {t('dinamikQr.toplu.olustur', { sayi: onizleme.gecerli })}
            </Button>
          )}
        </div>
      )}

      {sonuc && (
        <div className="space-y-3 rounded-xl border border-emerald-400/20 bg-emerald-500/[0.06] p-4" data-testid="qr-toplu-sonuc">
          <p className="text-sm">{t('dinamikQr.toplu.sonuc', { sayi: sonuc.olusturulan.length })}</p>
          {sonuc.hatalar.length > 0 && (
            <ul className="list-inside list-disc text-xs text-red-200">
              {sonuc.hatalar.map((h) => (
                <li key={`${h.satir}-${h.kod}`}>
                  {t('dinamikQr.toplu.satir', { satir: h.satir })}: {t(`dinamikQr.hata.${h.kod}`, { ...h, defaultValue: t('dinamikQr.hata.genel') })}
                </li>
              ))}
            </ul>
          )}
          <div className="flex flex-wrap gap-2">
            {sonuc.olusturulan.length > 0 && (
              <Button
                variant="outline"
                className="gap-1.5 !bg-transparent border-white/20"
                onClick={() =>
                  api.zipIndir(sonuc.olusturulan.map((k) => k.id), 'png').catch((e) => toast.error(hataMetni(t, e)))
                }
              >
                <Download className="h-4 w-4" aria-hidden="true" />
                {t('dinamikQr.liste.zipPng')}
              </Button>
            )}
            <Button onClick={() => onBitti(sonuc.olusturulan)}>{t('dinamikQr.toplu.listeyeDon')}</Button>
          </div>
        </div>
      )}
    </div>
  );
}
