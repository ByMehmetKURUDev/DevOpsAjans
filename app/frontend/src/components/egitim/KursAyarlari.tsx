import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Download, Eye, Loader2, Plus, Rocket, Save, Trash2, XCircle } from 'lucide-react';
import { toast } from 'sonner';

import GuvenliMarkdown from '@/components/asistanlar/GuvenliMarkdown';
import { Alan, Anahtar, DIS_DUGME, KART, METIN_ALANI, SECIM } from '@/components/randevu/ortak';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { blobIndir, hataMetni, type EgitimApi, type Egitmen, type Kurs, type Meta } from '@/lib/egitim';
import { DIL_ADLARI, ETKINLIK_DILLERI } from '@/lib/etkinlikOrtak';

/**
 * Faz 6K — kursun genel ayarları: bilgiler, eğitmenler, yer/biçim, tarih ve kapasite, fiyat METNİ (tahsilat
 * yok), kayıt kuralları (hedef kitle → veli bilgisi), devamsızlık/hatırlatma, sertifika koşulları, KVKK
 * saklama süresi, yayın durumu ve paylaşım QR'ı.
 */

type Taslak = Omit<Kurs, 'kapasite' | 'devamsizlik_esik' | 'hatirlatma_saat' | 'kosul_ilerleme' | 'kosul_quiz' | 'kosul_yoklama' | 'sertifika_saat' | 'saklama_gun'> & {
  kapasite: string;
  devamsizlik_esik: string;
  hatirlatma_saat: string;
  kosul_ilerleme: string;
  kosul_quiz: string;
  kosul_yoklama: string;
  sertifika_saat: string;
  saklama_gun: string;
};

const sayiMetni = (n: number | null | undefined) => (n == null ? '' : String(n));

function taslakKur(k: Kurs): Taslak {
  return {
    ...k,
    egitmenler: k.egitmenler.map((e) => ({ ...e })),
    kapasite: sayiMetni(k.kapasite),
    devamsizlik_esik: sayiMetni(k.devamsizlik_esik),
    hatirlatma_saat: sayiMetni(k.hatirlatma_saat),
    kosul_ilerleme: sayiMetni(k.kosul_ilerleme),
    kosul_quiz: sayiMetni(k.kosul_quiz),
    kosul_yoklama: sayiMetni(k.kosul_yoklama),
    sertifika_saat: sayiMetni(k.sertifika_saat),
    saklama_gun: sayiMetni(k.saklama_gun),
  };
}

const sayi = (s: string): number | null => (s.trim() === '' ? null : Number(s));

export default function KursAyarlari({ api, meta, kurs, onKaydedildi, onSilindi }: { api: EgitimApi; meta: Meta; kurs: Kurs; onKaydedildi: (k: Kurs) => void; onSilindi: () => void }) {
  const { t } = useTranslation();
  const [d, setD] = useState<Taslak>(() => taslakKur(kurs));
  const [kaydediliyor, setKaydediliyor] = useState(false);
  const [onizleme, setOnizleme] = useState(false);
  const [hataAlani, setHataAlani] = useState<string | null>(null);
  const ayarla = <K extends keyof Taslak>(alan: K, deger: Taslak[K]) => setD((x) => ({ ...x, [alan]: deger }));

  const govde = (durum?: Kurs['durum']) => ({
    ad: d.ad,
    slug: d.slug,
    ozet: d.ozet,
    aciklama: d.aciklama,
    renk: d.renk,
    egitmenler: d.egitmenler.filter((e) => e.ad.trim() || e.eposta.trim()),
    bicim: d.bicim,
    mekan: d.mekan,
    adres: d.adres,
    online_baglanti: d.online_baglanti,
    baslangic_tarihi: d.baslangic_tarihi || null,
    bitis_tarihi: d.bitis_tarihi || null,
    kapasite: sayi(d.kapasite),
    fiyat_metni: d.fiyat_metni,
    kayit_acik: d.kayit_acik,
    bekleme_listesi: d.bekleme_listesi,
    hedef_kitle: d.hedef_kitle,
    telefon: d.telefon,
    dil: d.dil,
    kvkk_metni: d.kvkk_metni,
    arama_motoru: d.arama_motoru,
    listede_goster: d.listede_goster,
    devamsizlik_esik: sayi(d.devamsizlik_esik) ?? 0,
    hatirlatma_saat: sayi(d.hatirlatma_saat) ?? 0,
    sertifika_aktif: d.sertifika_aktif,
    otomatik_sertifika: d.otomatik_sertifika,
    kosul_ilerleme: sayi(d.kosul_ilerleme) ?? 0,
    kosul_quiz: sayi(d.kosul_quiz) ?? 0,
    kosul_yoklama: sayi(d.kosul_yoklama) ?? 0,
    sertifika_sablon: d.sertifika_sablon,
    sertifika_saat: sayi(d.sertifika_saat),
    saklama_gun: sayi(d.saklama_gun) ?? meta.saklama.varsayilan,
    ...(durum ? { durum } : {}),
  });

  const kaydet = async (durum?: Kurs['durum']) => {
    setKaydediliyor(true);
    setHataAlani(null);
    try {
      const k = await api.guncelle(kurs.id, govde(durum));
      setD(taslakKur(k));
      onKaydedildi(k);
      toast.success(durum === 'yayinda' ? t('egitim.ayar.yayinlandi') : t('egitim.kaydedildi'));
    } catch (e) {
      const alan = (e as { alan?: string | null }).alan;
      setHataAlani(alan || null);
      toast.error(hataMetni(t, e));
    } finally {
      setKaydediliyor(false);
    }
  };

  const sil = async () => {
    if (!window.confirm(t('egitim.ayar.silOnay'))) return;
    try {
      await api.sil(kurs.id);
      toast.success(t('egitim.ayar.silindi'));
      onSilindi();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const qrIndir = async () => {
    try {
      blobIndir(await api.qrBlob(kurs.id, 'png'), `kurs-${kurs.slug}-qr.png`);
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const egitmenDegis = (i: number, alan: keyof Egitmen, deger: string) =>
    ayarla('egitmenler', d.egitmenler.map((e, j) => (j === i ? { ...e, [alan]: deger } : e)));

  const hataSinifi = (alan: string) => (hataAlani === alan || hataAlani?.startsWith(`${alan}.`) ? 'ring-2 ring-red-400' : '');

  return (
    <div className="grid gap-4" data-testid="egitim-ayarlar">
      <div className={`${KART} grid gap-4 p-4 sm:p-6 md:grid-cols-2`}>
        <h4 className="text-base font-semibold md:col-span-2">{t('egitim.ayar.bilgiler')}</h4>
        <Alan etiket={t('egitim.alan.ad')}>
          <Input value={d.ad} onChange={(e) => ayarla('ad', e.target.value)} maxLength={160} className={hataSinifi('ad')} data-testid="egitim-ad" />
        </Alan>
        <Alan etiket={t('egitim.alan.slug')} ipucu={`${meta.adres_tabani}${d.slug}`}>
          <Input value={d.slug} onChange={(e) => ayarla('slug', e.target.value.toLowerCase())} maxLength={50} dir="ltr" className={hataSinifi('slug')} />
        </Alan>
        <Alan etiket={t('egitim.alan.ozet')} className="md:col-span-2">
          <Input value={d.ozet} onChange={(e) => ayarla('ozet', e.target.value)} maxLength={300} data-testid="egitim-ozet" />
        </Alan>
        <div className="md:col-span-2">
          <div className="mb-1 flex items-center justify-between gap-2">
            <span className="text-sm font-medium text-white/90">{t('egitim.alan.aciklama')}</span>
            <Button size="sm" variant="ghost" className="gap-1" onClick={() => setOnizleme((v) => !v)}>
              <Eye className="h-4 w-4" aria-hidden="true" />
              {onizleme ? t('egitim.ayar.duzenle') : t('egitim.ayar.onizle')}
            </Button>
          </div>
          {onizleme ? (
            <div className="min-h-[84px] rounded-md border border-white/10 bg-black/30 p-3 text-sm">
              <GuvenliMarkdown metin={d.aciklama || '—'} />
            </div>
          ) : (
            <textarea value={d.aciklama} onChange={(e) => ayarla('aciklama', e.target.value)} maxLength={20000} rows={6} className={METIN_ALANI} />
          )}
          <span className="mt-1 block text-xs text-muted-foreground">{t('egitim.ayar.markdownIpucu')}</span>
        </div>
        <Alan etiket={t('egitim.alan.renk')}>
          <input type="color" value={d.renk} onChange={(e) => ayarla('renk', e.target.value)} className="h-10 w-20 cursor-pointer rounded-md border border-white/10 bg-transparent" />
        </Alan>
        <Alan etiket={t('egitim.alan.dil')}>
          <select value={d.dil} onChange={(e) => ayarla('dil', e.target.value)} className={SECIM}>
            {ETKINLIK_DILLERI.map((x) => (
              <option key={x} value={x}>
                {DIL_ADLARI[x]}
              </option>
            ))}
          </select>
        </Alan>
        <div className="md:col-span-2">
          <span className="mb-1 block text-sm font-medium text-white/90">{t('egitim.alan.egitmenler')}</span>
          <span className="mb-2 block text-xs text-muted-foreground">{t('egitim.ayar.egitmenIpucu')}</span>
          <div className="grid gap-2">
            {d.egitmenler.map((e, i) => (
              <div key={i} className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
                <Input value={e.ad} onChange={(x) => egitmenDegis(i, 'ad', x.target.value)} placeholder={t('egitim.ayar.egitmenAd')} maxLength={120} aria-label={t('egitim.ayar.egitmenAd')} />
                <Input value={e.eposta} onChange={(x) => egitmenDegis(i, 'eposta', x.target.value)} placeholder="egitmen@ornek.com" type="email" dir="ltr" aria-label={t('egitim.alan.eposta')} />
                <Button variant="ghost" size="icon" aria-label={t('egitim.sil')} onClick={() => ayarla('egitmenler', d.egitmenler.filter((_, j) => j !== i))}>
                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                </Button>
              </div>
            ))}
            {d.egitmenler.length < 10 && (
              <Button variant="outline" size="sm" className={`${DIS_DUGME} w-fit`} onClick={() => ayarla('egitmenler', [...d.egitmenler, { ad: '', eposta: '' }])} data-testid="egitim-egitmen-ekle">
                <Plus className="h-4 w-4" aria-hidden="true" />
                {t('egitim.ayar.egitmenEkle')}
              </Button>
            )}
          </div>
        </div>
      </div>

      <div className={`${KART} grid gap-4 p-4 sm:p-6 md:grid-cols-2`}>
        <h4 className="text-base font-semibold md:col-span-2">{t('egitim.ayar.zamanYer')}</h4>
        <Alan etiket={t('egitim.alan.baslangicTarihi')}>
          <Input type="date" value={d.baslangic_tarihi || ''} onChange={(e) => ayarla('baslangic_tarihi', e.target.value || null)} className={hataSinifi('baslangic_tarihi')} />
        </Alan>
        <Alan etiket={t('egitim.alan.bitisTarihi')} ipucu={t('egitim.ayar.bitisIpucu')}>
          <Input type="date" value={d.bitis_tarihi || ''} onChange={(e) => ayarla('bitis_tarihi', e.target.value || null)} className={hataSinifi('bitis_tarihi')} />
        </Alan>
        <Alan etiket={t('egitim.alan.bicim')}>
          <select value={d.bicim} onChange={(e) => ayarla('bicim', e.target.value as Kurs['bicim'])} className={SECIM}>
            {(['yuz_yuze', 'online', 'karma'] as const).map((x) => (
              <option key={x} value={x}>
                {t(`egitim.bicim.${x}`)}
              </option>
            ))}
          </select>
        </Alan>
        <Alan etiket={t('egitim.alan.mekan')}>
          <Input value={d.mekan} onChange={(e) => ayarla('mekan', e.target.value)} maxLength={160} />
        </Alan>
        <Alan etiket={t('egitim.alan.adres')} className="md:col-span-2">
          <textarea value={d.adres} onChange={(e) => ayarla('adres', e.target.value)} maxLength={500} rows={2} className={METIN_ALANI} />
        </Alan>
        {d.bicim !== 'yuz_yuze' && (
          <Alan etiket={t('egitim.alan.onlineBaglanti')} ipucu={t('egitim.ayar.onlineIpucu')} className="md:col-span-2">
            <Input value={d.online_baglanti} onChange={(e) => ayarla('online_baglanti', e.target.value)} dir="ltr" placeholder="https://" className={hataSinifi('online_baglanti')} />
          </Alan>
        )}
        <Alan etiket={t('egitim.alan.kapasite')} ipucu={t('egitim.ayar.kapasiteIpucu')}>
          <Input type="number" min={1} value={d.kapasite} onChange={(e) => ayarla('kapasite', e.target.value)} className={hataSinifi('kapasite')} data-testid="egitim-kapasite" />
        </Alan>
        <Alan etiket={t('egitim.alan.fiyat')} ipucu={t('egitim.ayar.fiyatIpucu')}>
          <Input value={d.fiyat_metni} onChange={(e) => ayarla('fiyat_metni', e.target.value)} maxLength={300} placeholder={t('egitim.ayar.fiyatOrnek')} data-testid="egitim-fiyat" />
        </Alan>
      </div>

      <div className={`${KART} grid gap-4 p-4 sm:p-6 md:grid-cols-2`}>
        <h4 className="text-base font-semibold md:col-span-2">{t('egitim.ayar.kayit')}</h4>
        <Alan etiket={t('egitim.alan.hedefKitle')} ipucu={t('egitim.ayar.hedefIpucu')}>
          <select value={d.hedef_kitle} onChange={(e) => ayarla('hedef_kitle', e.target.value as Kurs['hedef_kitle'])} className={SECIM} data-testid="egitim-hedef-kitle">
            {(['yetiskin', 'cocuk', 'karma'] as const).map((x) => (
              <option key={x} value={x}>
                {t(`egitim.hedef.${x}`)}
              </option>
            ))}
          </select>
        </Alan>
        <Alan etiket={t('egitim.alan.telefon')}>
          <select value={d.telefon} onChange={(e) => ayarla('telefon', e.target.value as Kurs['telefon'])} className={SECIM}>
            {(['gizli', 'istege_bagli', 'zorunlu'] as const).map((x) => (
              <option key={x} value={x}>
                {t(`egitim.telefonKurali.${x}`)}
              </option>
            ))}
          </select>
        </Alan>
        <div className="grid gap-2 md:col-span-2">
          <Anahtar acik={d.kayit_acik} onDegis={(v) => ayarla('kayit_acik', v)} etiket={t('egitim.ayar.kayitAcik')} />
          <Anahtar acik={d.bekleme_listesi} onDegis={(v) => ayarla('bekleme_listesi', v)} etiket={t('egitim.ayar.beklemeListesi')} />
          <Anahtar acik={d.listede_goster} onDegis={(v) => ayarla('listede_goster', v)} etiket={t('egitim.ayar.listedeGoster')} />
          <Anahtar acik={d.arama_motoru} onDegis={(v) => ayarla('arama_motoru', v)} etiket={t('egitim.ayar.aramaMotoru')} />
        </div>
        <Alan etiket={t('egitim.alan.kvkk')} ipucu={t('egitim.ayar.kvkkIpucu')} className="md:col-span-2">
          <textarea value={d.kvkk_metni} onChange={(e) => ayarla('kvkk_metni', e.target.value)} maxLength={3000} rows={3} className={METIN_ALANI} />
        </Alan>
        <Alan etiket={t('egitim.alan.saklama')} ipucu={t('egitim.ayar.saklamaIpucu', { en_az: meta.saklama.en_az, en_cok: meta.saklama.en_cok })}>
          <Input type="number" min={meta.saklama.en_az} max={meta.saklama.en_cok} value={d.saklama_gun} onChange={(e) => ayarla('saklama_gun', e.target.value)} className={hataSinifi('saklama_gun')} />
        </Alan>
      </div>

      <div className={`${KART} grid gap-4 p-4 sm:p-6 md:grid-cols-2`}>
        <h4 className="text-base font-semibold md:col-span-2">{t('egitim.ayar.yoklamaIletisim')}</h4>
        <Alan etiket={t('egitim.alan.devamsizlikEsik')} ipucu={t('egitim.ayar.devamsizlikIpucu')}>
          <Input type="number" min={0} max={100} value={d.devamsizlik_esik} onChange={(e) => ayarla('devamsizlik_esik', e.target.value)} />
        </Alan>
        <Alan etiket={t('egitim.alan.hatirlatma')} ipucu={t('egitim.ayar.hatirlatmaIpucu')}>
          <select value={d.hatirlatma_saat} onChange={(e) => ayarla('hatirlatma_saat', e.target.value)} className={SECIM}>
            {['0', '1', '2', '3', '6', '12', '24', '48'].map((x) => (
              <option key={x} value={x}>
                {x === '0' ? t('egitim.ayar.hatirlatmaYok') : t('egitim.ayar.saatOnce', { sayi: Number(x) })}
              </option>
            ))}
          </select>
        </Alan>
      </div>

      <div className={`${KART} grid gap-4 p-4 sm:p-6 md:grid-cols-3`}>
        <h4 className="text-base font-semibold md:col-span-3">{t('egitim.ayar.sertifika')}</h4>
        <div className="grid gap-2 md:col-span-3">
          <Anahtar acik={d.sertifika_aktif} onDegis={(v) => ayarla('sertifika_aktif', v)} etiket={t('egitim.ayar.sertifikaAktif')} />
          <Anahtar acik={d.otomatik_sertifika} onDegis={(v) => ayarla('otomatik_sertifika', v)} etiket={t('egitim.ayar.otomatikSertifika')} devreDisi={!d.sertifika_aktif} />
        </div>
        <Alan etiket={t('egitim.alan.kosulIlerleme')}>
          <Input type="number" min={0} max={100} value={d.kosul_ilerleme} onChange={(e) => ayarla('kosul_ilerleme', e.target.value)} />
        </Alan>
        <Alan etiket={t('egitim.alan.kosulQuiz')}>
          <Input type="number" min={0} max={100} value={d.kosul_quiz} onChange={(e) => ayarla('kosul_quiz', e.target.value)} />
        </Alan>
        <Alan etiket={t('egitim.alan.kosulYoklama')}>
          <Input type="number" min={0} max={100} value={d.kosul_yoklama} onChange={(e) => ayarla('kosul_yoklama', e.target.value)} />
        </Alan>
        <Alan etiket={t('egitim.alan.sablon')}>
          <select value={d.sertifika_sablon} onChange={(e) => ayarla('sertifika_sablon', e.target.value as Kurs['sertifika_sablon'])} className={SECIM}>
            {(['klasik', 'modern'] as const).map((x) => (
              <option key={x} value={x}>
                {t(`egitim.sablon.${x}`)}
              </option>
            ))}
          </select>
        </Alan>
        <Alan etiket={t('egitim.alan.sertifikaSaat')}>
          <Input type="number" min={1} value={d.sertifika_saat} onChange={(e) => ayarla('sertifika_saat', e.target.value)} />
        </Alan>
        <p className="text-xs text-muted-foreground md:col-span-3">{t('egitim.ayar.kosulIpucu')}</p>
      </div>

      <div className={`${KART} flex flex-wrap items-center gap-2 p-4`}>
        <Button onClick={() => void kaydet()} disabled={kaydediliyor} className="gap-1.5" data-testid="egitim-kaydet">
          {kaydediliyor ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Save className="h-4 w-4" aria-hidden="true" />}
          {t('egitim.kaydet')}
        </Button>
        {kurs.durum === 'taslak' && (
          <Button onClick={() => void kaydet('yayinda')} disabled={kaydediliyor} variant="outline" className={DIS_DUGME} data-testid="egitim-yayinla">
            <Rocket className="h-4 w-4" aria-hidden="true" />
            {t('egitim.ayar.yayinla')}
          </Button>
        )}
        {kurs.durum === 'yayinda' && (
          <Button onClick={() => void kaydet('tamamlandi')} disabled={kaydediliyor} variant="outline" className={DIS_DUGME}>
            {t('egitim.ayar.tamamla')}
          </Button>
        )}
        {kurs.durum !== 'arsiv' && kurs.durum !== 'taslak' && (
          <Button onClick={() => void kaydet('arsiv')} disabled={kaydediliyor} variant="outline" className={DIS_DUGME}>
            <XCircle className="h-4 w-4" aria-hidden="true" />
            {t('egitim.ayar.arsivle')}
          </Button>
        )}
        <Button onClick={() => void qrIndir()} variant="outline" className={DIS_DUGME} data-testid="egitim-qr-indir">
          <Download className="h-4 w-4" aria-hidden="true" />
          {t('egitim.ayar.qrIndir')}
        </Button>
        <span className="flex-1" />
        <Button onClick={() => void sil()} variant="ghost" className="gap-1.5 text-red-300 hover:text-red-200">
          <Trash2 className="h-4 w-4" aria-hidden="true" />
          {t('egitim.ayar.sil')}
        </Button>
      </div>
    </div>
  );
}
