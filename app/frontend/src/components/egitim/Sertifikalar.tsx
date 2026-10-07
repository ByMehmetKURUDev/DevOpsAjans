import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Award, BadgeCheck, Ban, Download, ExternalLink, Loader2, ShieldAlert } from 'lucide-react';
import { toast } from 'sonner';

import { Cubuk } from '@/components/egitim/Ogrenciler';
import { DIS_DUGME, KART, Rozet, Yukleniyor } from '@/components/randevu/ortak';
import { Button } from '@/components/ui/button';
import { EgitimUcHatasi, blobIndir, hataMetni, tarihSaat, type EgitimApi, type Istatistik, type Kurs, type Sertifika } from '@/lib/egitim';

/**
 * Faz 6K — sertifikalar: koşul tablosu (ilerleme %, quiz ortalaması, yoklama %), koşulu sağlayanlara toplu
 * verme, tek tek verme (koşul sağlanmadıysa onayla "yine de ver"), PDF indirme, iptal ve doğrulama bağlantısı.
 * Doğrulama sayfası yalnız maskeli ad + kurs + tarih gösterir.
 */

type Satir = { id: number; ad: string; kod: string } & Istatistik;

export default function Sertifikalar({ api, kurs }: { api: EgitimApi; kurs: Kurs }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [satirlar, setSatirlar] = useState<Satir[] | null>(null);
  const [sertifikalar, setSertifikalar] = useState<Sertifika[] | null>(null);
  const [mesgul, setMesgul] = useState<string | null>(null);

  const yukle = useCallback(async () => {
    try {
      const [i, s] = await Promise.all([api.ilerleme(kurs.id), api.sertifikalar(kurs.id)]);
      setSatirlar(i.items);
      setSertifikalar(s.items);
    } catch (e) {
      toast.error(hataMetni(t, e));
      setSatirlar([]);
      setSertifikalar([]);
    }
  }, [api, kurs.id, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const toplu = async () => {
    setMesgul('toplu');
    try {
      const r = await api.sertifikaToplu(kurs.id);
      toast.success(t('egitim.sertifika.topluSonuc', { verilen: r.verilen, kalan: r.uygun_olmayan }));
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(null);
    }
  };

  const ver = async (s: Satir, zorla: boolean) => {
    if (zorla && !window.confirm(t('egitim.sertifika.zorlaOnay', { ad: s.ad }))) return;
    setMesgul(`ver-${s.id}`);
    try {
      await api.sertifikaVer(kurs.id, s.id, zorla);
      toast.success(t('egitim.sertifika.verildi'));
      await yukle();
    } catch (e) {
      if (e instanceof EgitimUcHatasi && e.kod === 'kosul_saglanmadi') toast.error(t('egitim.hata.kosul_saglanmadi'));
      else toast.error(hataMetni(t, e));
    } finally {
      setMesgul(null);
    }
  };

  const pdf = async (c: Sertifika) => {
    setMesgul(`pdf-${c.id}`);
    try {
      blobIndir(await api.sertifikaPdf(kurs.id, c.id), `sertifika-${c.kod_yazi}.pdf`);
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(null);
    }
  };

  const iptal = async (c: Sertifika) => {
    if (!window.confirm(t('egitim.sertifika.iptalOnay'))) return;
    try {
      await api.sertifikaIptal(kurs.id, c.id);
      toast.success(t('egitim.sertifika.iptalEdildi'));
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const kosulYazi = (k: Istatistik['kosullar']['ilerleme'], yuzde: boolean) =>
    `${k.deger == null ? '—' : yuzde ? `%${k.deger}` : k.deger} / ${yuzde ? `%${k.esik}` : k.esik}`;

  return (
    <div className="grid gap-4" data-testid="egitim-sertifikalar">
      <div className={`${KART} p-4 sm:p-6`}>
        <div className="flex flex-wrap items-start gap-3">
          <span className="flex h-10 w-10 flex-none items-center justify-center rounded-xl bg-blue-500/15">
            <Award className="h-5 w-5 text-blue-200" aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <h4 className="text-base font-semibold">{t('egitim.sertifika.baslik')}</h4>
            <p className="mt-1 text-sm text-muted-foreground">
              {kurs.sertifika_aktif
                ? t('egitim.sertifika.kosulOzeti', { ilerleme: kurs.kosul_ilerleme, quiz: kurs.kosul_quiz, yoklama: kurs.kosul_yoklama })
                : t('egitim.sertifika.kapali')}
            </p>
            {kurs.sertifika_aktif && kurs.otomatik_sertifika && <p className="mt-1 text-xs text-muted-foreground">{t('egitim.sertifika.otomatikNotu')}</p>}
          </div>
          {kurs.sertifika_aktif && (
            <Button onClick={() => void toplu()} disabled={mesgul !== null} className="gap-1.5" data-testid="egitim-sertifika-toplu">
              {mesgul === 'toplu' ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <BadgeCheck className="h-4 w-4" aria-hidden="true" />}
              {t('egitim.sertifika.toplu')}
            </Button>
          )}
        </div>
      </div>

      <div className={`${KART} p-4 sm:p-6`}>
        <h4 className="mb-3 text-base font-semibold">{t('egitim.sertifika.durumTablosu')}</h4>
        {satirlar === null ? (
          <Yukleniyor />
        ) : satirlar.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">{t('egitim.ogrenci.bos')}</p>
        ) : (
          <ul className="divide-y divide-white/5" data-testid="egitim-sertifika-tablo">
            {satirlar.map((s) => (
              <li key={s.id} className="flex flex-col gap-2 py-3 lg:flex-row lg:items-center" data-ogrenci-id={s.id}>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{s.ad}</span>
                    {s.sertifika ? (
                      <Rozet renk="border-blue-400/40 bg-blue-500/15 text-blue-200">{t('egitim.ogrenci.sertifikali')}</Rozet>
                    ) : s.uygun ? (
                      <Rozet renk="border-emerald-400/40 bg-emerald-500/15 text-emerald-200">{t('egitim.sertifika.uygun')}</Rozet>
                    ) : (
                      <Rozet>{t('egitim.sertifika.uygunDegil')}</Rozet>
                    )}
                  </div>
                  <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
                    <span className={s.kosullar.ilerleme.tamam ? 'text-emerald-300' : ''}>
                      {t('egitim.ilerleme.ilerleme')}: {kosulYazi(s.kosullar.ilerleme, true)}
                    </span>
                    <span className={s.kosullar.quiz.tamam ? 'text-emerald-300' : ''}>
                      {t('egitim.ilerleme.quiz')}: {kosulYazi(s.kosullar.quiz, false)}
                    </span>
                    <span className={s.kosullar.yoklama.tamam ? 'text-emerald-300' : ''}>
                      {t('egitim.ilerleme.yoklama')}: {kosulYazi(s.kosullar.yoklama, true)}
                    </span>
                  </div>
                </div>
                <div className="flex flex-wrap gap-3">
                  <Cubuk deger={s.ilerleme} etiket={t('egitim.ilerleme.ilerleme')} />
                  <Cubuk deger={s.yoklama} etiket={t('egitim.ilerleme.yoklama')} />
                </div>
                {kurs.sertifika_aktif && !s.sertifika && (
                  <Button
                    size="sm"
                    variant={s.uygun ? 'default' : 'outline'}
                    className={s.uygun ? 'gap-1.5' : DIS_DUGME}
                    disabled={mesgul !== null}
                    onClick={() => void ver(s, !s.uygun)}
                    data-testid="egitim-sertifika-ver"
                  >
                    {mesgul === `ver-${s.id}` ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Award className="h-4 w-4" aria-hidden="true" />}
                    {s.uygun ? t('egitim.sertifika.ver') : t('egitim.sertifika.zorla')}
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className={`${KART} p-4 sm:p-6`}>
        <h4 className="mb-3 text-base font-semibold">{t('egitim.sertifika.verilenler')}</h4>
        {sertifikalar === null ? (
          <Yukleniyor />
        ) : sertifikalar.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">{t('egitim.sertifika.bos')}</p>
        ) : (
          <ul className="divide-y divide-white/5" data-testid="egitim-sertifika-liste">
            {sertifikalar.map((c) => (
              <li key={c.id} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center" data-kod={c.kod}>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{c.ad || c.ad_maskeli || '—'}</span>
                    <code className="text-xs text-blue-200" dir="ltr">
                      {c.kod_yazi}
                    </code>
                    {c.iptal_at && (
                      <Rozet renk="border-red-400/40 bg-red-500/15 text-red-200">
                        <ShieldAlert className="me-1 h-3 w-3" aria-hidden="true" />
                        {t('egitim.sertifika.iptal')}
                      </Rozet>
                    )}
                  </div>
                  <div className="mt-0.5 text-xs text-muted-foreground">{tarihSaat(c.verilme_at, kurs.saat_dilimi, dil, { dateStyle: 'medium' })}</div>
                </div>
                <div className="flex flex-wrap items-center gap-1">
                  {!c.iptal_at && (
                    <Button size="sm" variant="outline" className={DIS_DUGME} disabled={mesgul !== null} onClick={() => void pdf(c)} data-testid="egitim-sertifika-pdf">
                      {mesgul === `pdf-${c.id}` ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Download className="h-4 w-4" aria-hidden="true" />}
                      PDF
                    </Button>
                  )}
                  <a
                    href={`/egitim/sertifika/${c.kod}`}
                    target="_blank"
                    rel="noopener"
                    className="inline-flex h-9 items-center gap-1 rounded-md px-2 text-sm text-blue-200 hover:underline"
                    data-testid="egitim-sertifika-dogrula"
                  >
                    <ExternalLink className="h-4 w-4" aria-hidden="true" />
                    {t('egitim.sertifika.dogrula')}
                  </a>
                  {!c.iptal_at && (
                    <Button size="icon" variant="ghost" className="h-9 w-9 text-red-300" aria-label={t('egitim.sertifika.iptalEt')} title={t('egitim.sertifika.iptalEt')} onClick={() => void iptal(c)}>
                      <Ban className="h-4 w-4" aria-hidden="true" />
                    </Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
