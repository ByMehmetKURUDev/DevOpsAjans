import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Ban, Link2, Loader2, Plus, RefreshCw, RotateCw, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import BaglantiKutusu from '@/components/admin/BaglantiKutusu';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  ISLEM_DURUMLARI,
  ISLEM_TURLERI,
  IslemHatasi,
  durumRengi,
  islemHedefleri,
  islemIptal,
  islemListesi,
  islemOlustur,
  islemYenile,
  olumluMu,
  tarihSaatBicimle,
  yerelBaslik,
  type IslemHedefi,
  type IslemTuru,
  type OlusturYaniti,
  type YonetimIslemi,
} from '@/lib/imzaliIslem';

/**
 * Yönetici paneli › İmzalı işlemler.
 *
 * Üstte "Yeni bağlantı" formu (tür → hedef → alıcı, süre, not, e-postayla
 * gönder), altta bütün bağlantılar (tür/durum süzgeci, iptal, yenile).
 * Üretilen bağlantı yalnız o an gösteriliyor: sunucuda jetonun kendisi
 * değil özeti duruyor, liste bir daha bağlantı döndüremiyor. Kaybolursa
 * "Yenile" eskisini iptal edip yenisini üretir.
 */

const SECIM_SINIFI =
  'h-10 w-full rounded-md border border-white/10 bg-white/5 px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-purple-500/40';

interface Onay {
  mesaj: string;
  calistir: () => Promise<void>;
}

export default function ImzaliIslemler() {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [liste, setListe] = useState<YonetimIslemi[]>([]);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [filtreTur, setFiltreTur] = useState('');
  const [filtreDurum, setFiltreDurum] = useState('');
  const [formAcik, setFormAcik] = useState(false);
  const [sonBaglanti, setSonBaglanti] = useState<OlusturYaniti | null>(null);
  const [onay, setOnay] = useState<Onay | null>(null);
  const [calisiyor, setCalisiyor] = useState(false);

  // Form
  const [tur, setTur] = useState<IslemTuru>('teklif_kabul');
  const [hedefler, setHedefler] = useState<IslemHedefi[]>([]);
  const [hedefId, setHedefId] = useState('');
  const [alici, setAlici] = useState('');
  const [gun, setGun] = useState('14');
  const [not, setNot] = useState('');
  const [baglanti, setBaglanti] = useState('');
  const [ilerlet, setIlerlet] = useState(true);
  const [epostaGonder, setEpostaGonder] = useState(true);
  const [gonderiliyor, setGonderiliyor] = useState(false);

  const hataMetni = useCallback(
    (h: unknown) => {
      const kod = h instanceof IslemHatasi ? h.kod : 'genel';
      return t(`islem.hata.${kod}`, { defaultValue: t('islem.hata.genel') });
    },
    [t],
  );

  const yukle = useCallback(async () => {
    setYukleniyor(true);
    try {
      setListe(await islemListesi({ tur: filtreTur || undefined, durum: filtreDurum || undefined }));
    } catch (h) {
      toast.error(hataMetni(h));
    } finally {
      setYukleniyor(false);
    }
  }, [filtreTur, filtreDurum, hataMetni]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  useEffect(() => {
    if (!formAcik) return;
    let iptal = false;
    setHedefler([]);
    setHedefId('');
    setAlici('');
    islemHedefleri(tur)
      .then((h) => {
        if (!iptal) setHedefler(h);
      })
      .catch((h) => toast.error(hataMetni(h)));
    return () => {
      iptal = true;
    };
  }, [tur, formAcik, hataMetni]);

  const hedefSec = (deger: string) => {
    setHedefId(deger);
    const h = hedefler.find((x) => String(x.id) === deger);
    setAlici(h?.alici || '');
  };

  const gunSayi = Number(gun);
  const gunGecerli = Number.isInteger(gunSayi) && gunSayi >= 1 && gunSayi <= 90;

  const gonder = async (e: FormEvent) => {
    e.preventDefault();
    if (!hedefId || !gunGecerli) return;
    setGonderiliyor(true);
    try {
      const yanit = await islemOlustur({
        tur,
        hedef_id: Number(hedefId),
        alici_eposta: alici.trim() || undefined,
        gun: gunSayi,
        not: not.trim() || undefined,
        baglanti: tur === 'teslimat_onay' ? baglanti.trim() || undefined : undefined,
        ilerlet: tur === 'teslimat_onay' ? ilerlet : undefined,
        eposta_gonder: epostaGonder,
      });
      setSonBaglanti(yanit);
      setFormAcik(false);
      setNot('');
      setBaglanti('');
      toast.success(t('islem.yonetim.olusturuldu'));
      await yukle();
    } catch (h) {
      toast.error(hataMetni(h));
    } finally {
      setGonderiliyor(false);
    }
  };

  const iptalEt = (islem: YonetimIslemi) =>
    setOnay({
      mesaj: t('islem.yonetim.iptalOnay', { baslik: islem.baslik, eposta: islem.alici_eposta }),
      calistir: async () => {
        await islemIptal(islem.id);
        toast.success(t('islem.yonetim.iptalEdildi'));
      },
    });

  const yenile = (islem: YonetimIslemi) =>
    setOnay({
      mesaj: t(islem.durum === 'bekliyor' ? 'islem.yonetim.yenileOnayBekleyen' : 'islem.yonetim.yenileOnay', {
        baslik: islem.baslik,
        eposta: islem.alici_eposta,
      }),
      calistir: async () => {
        const yanit = await islemYenile(islem.id, { eposta_gonder: epostaGonder });
        setSonBaglanti(yanit);
        toast.success(t('islem.yonetim.olusturuldu'));
      },
    });

  const onayla = async () => {
    if (!onay) return;
    setCalisiyor(true);
    try {
      await onay.calistir();
      setOnay(null);
      await yukle();
    } catch (h) {
      toast.error(hataMetni(h));
    } finally {
      setCalisiyor(false);
    }
  };

  return (
    <div className="space-y-6" data-testid="islem-yonetim">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-2xl font-bold">
            <Link2 className="h-6 w-6 text-purple-300" aria-hidden="true" />
            {t('islem.yonetim.baslik')}
          </h2>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{t('islem.yonetim.aciklama')}</p>
        </div>
        <Button onClick={() => setFormAcik((a) => !a)} className="gap-2" data-testid="islem-yeni">
          {formAcik ? <X className="h-4 w-4" aria-hidden="true" /> : <Plus className="h-4 w-4" aria-hidden="true" />}
          {formAcik ? t('islem.vazgec') : t('islem.yonetim.yeni')}
        </Button>
      </div>

      {sonBaglanti && (
        <BaglantiKutusu yanit={sonBaglanti} onKapat={() => setSonBaglanti(null)} />
      )}

      {formAcik && (
        <form
          onSubmit={gonder}
          className="cam-kart grid gap-4 rounded-2xl border border-white/10 bg-white/[0.03] p-6 md:grid-cols-2"
          data-testid="islem-form"
        >
          <div className="grid gap-2">
            <label htmlFor="islem-tur" className="text-sm font-medium">
              {t('islem.yonetim.tur')}
            </label>
            <select
              id="islem-tur"
              name="tur"
              value={tur}
              onChange={(e) => setTur(e.target.value as IslemTuru)}
              className={SECIM_SINIFI}
            >
              {ISLEM_TURLERI.map((k) => (
                <option key={k} value={k}>
                  {t(`islem.tur.${k}.baslik`)}
                </option>
              ))}
            </select>
          </div>
          <div className="grid gap-2">
            <label htmlFor="islem-hedef" className="text-sm font-medium">
              {t(`islem.yonetim.hedef.${tur}`)}
            </label>
            <select
              id="islem-hedef"
              name="hedef"
              value={hedefId}
              onChange={(e) => hedefSec(e.target.value)}
              className={SECIM_SINIFI}
              required
            >
              <option value="">{hedefler.length ? t('islem.yonetim.hedefSec') : t('islem.yonetim.hedefYok')}</option>
              {hedefler.map((h) => (
                <option key={h.id} value={h.id}>
                  {h.etiket}
                  {h.ek ? ` · ${tur === 'teslimat_onay' ? t(`panel.asama.${h.ek}.ad`, { defaultValue: h.ek }) : t(`islem.teklifDurumu.${h.ek}`, { defaultValue: h.ek })}` : ''}
                </option>
              ))}
            </select>
          </div>
          <div className="grid gap-2">
            <label htmlFor="islem-alici" className="text-sm font-medium">
              {t('islem.yonetim.alici')}
            </label>
            <Input
              id="islem-alici"
              name="alici"
              type="email"
              value={alici}
              onChange={(e) => setAlici(e.target.value)}
              placeholder="musteri@alan.com"
            />
          </div>
          <div className="grid gap-2">
            <label htmlFor="islem-gun" className="text-sm font-medium">
              {t('islem.yonetim.gun')}
            </label>
            <Input
              id="islem-gun"
              name="gun"
              type="number"
              min={1}
              max={90}
              value={gun}
              onChange={(e) => setGun(e.target.value)}
              aria-invalid={!gunGecerli}
            />
          </div>
          <div className="grid gap-2 md:col-span-2">
            <label htmlFor="islem-not" className="text-sm font-medium">
              {t('islem.yonetim.not')} <span className="text-xs text-muted-foreground">({t('islem.istegeBagli')})</span>
            </label>
            <Textarea
              id="islem-not"
              name="not"
              rows={2}
              maxLength={2000}
              value={not}
              onChange={(e) => setNot(e.target.value)}
              placeholder={t('islem.yonetim.notYertutucu')}
            />
          </div>
          {tur === 'teslimat_onay' && (
            <>
              <div className="grid gap-2 md:col-span-2">
                <label htmlFor="islem-baglanti" className="text-sm font-medium">
                  {t('islem.yonetim.teslimBaglantisi')}{' '}
                  <span className="text-xs text-muted-foreground">({t('islem.istegeBagli')})</span>
                </label>
                <Input
                  id="islem-baglanti"
                  name="baglanti"
                  value={baglanti}
                  onChange={(e) => setBaglanti(e.target.value)}
                  placeholder="https://…"
                />
              </div>
              <label className="flex items-center gap-2 text-sm md:col-span-2">
                <input
                  type="checkbox"
                  name="ilerlet"
                  checked={ilerlet}
                  onChange={(e) => setIlerlet(e.target.checked)}
                  className="h-4 w-4 accent-purple-500"
                />
                {t('islem.yonetim.ilerlet')}
              </label>
            </>
          )}
          <label className="flex items-center gap-2 text-sm md:col-span-2">
            <input
              type="checkbox"
              name="eposta"
              checked={epostaGonder}
              onChange={(e) => setEpostaGonder(e.target.checked)}
              className="h-4 w-4 accent-purple-500"
            />
            {t('islem.yonetim.epostaGonder')}
          </label>
          <div className="md:col-span-2">
            <Button type="submit" disabled={gonderiliyor || !hedefId || !gunGecerli} className="gap-2">
              {gonderiliyor ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <Link2 className="h-4 w-4" aria-hidden="true" />
              )}
              {t('islem.yonetim.olustur')}
            </Button>
          </div>
        </form>
      )}

      <section className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-4 sm:p-6">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <select
            aria-label={t('islem.yonetim.tur')}
            value={filtreTur}
            onChange={(e) => setFiltreTur(e.target.value)}
            className={`${SECIM_SINIFI} !w-auto`}
            data-testid="islem-filtre-tur"
          >
            <option value="">{t('islem.yonetim.tumTurler')}</option>
            {ISLEM_TURLERI.map((k) => (
              <option key={k} value={k}>
                {t(`islem.tur.${k}.baslik`)}
              </option>
            ))}
          </select>
          <select
            aria-label={t('islem.yonetim.durumSutun')}
            value={filtreDurum}
            onChange={(e) => setFiltreDurum(e.target.value)}
            className={`${SECIM_SINIFI} !w-auto`}
            data-testid="islem-filtre-durum"
          >
            <option value="">{t('islem.yonetim.tumDurumlar')}</option>
            {ISLEM_DURUMLARI.map((k) => (
              <option key={k} value={k}>
                {t(`islem.durumAdi.${k}`)}
              </option>
            ))}
          </select>
          <Button variant="outline" size="sm" className="gap-2 !bg-transparent" onClick={() => void yukle()}>
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            {t('islem.yenile')}
          </Button>
        </div>

        {yukleniyor ? (
          <div className="flex justify-center py-10 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
          </div>
        ) : liste.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">{t('islem.yonetim.bos')}</p>
        ) : (
          <ul className="divide-y divide-white/5" data-testid="islem-liste">
            {liste.map((islem) => (
              <li key={islem.id} className="py-4" data-testid={`islem-satir-${islem.id}`}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded-full border border-purple-400/30 bg-purple-500/10 px-2 py-0.5 text-xs text-purple-200">
                        {t(`islem.tur.${islem.tur}.baslik`, { defaultValue: islem.tur })}
                      </span>
                      <span
                        className={`rounded-full border px-2 py-0.5 text-xs ${durumRengi(islem.durum)}`}
                        data-testid="islem-durum"
                      >
                        {t(`islem.durumAdi.${islem.durum}`, { defaultValue: islem.durum })}
                      </span>
                      {islem.sonuc && (
                        <span
                          className={`rounded-full border px-2 py-0.5 text-xs ${
                            olumluMu(islem.sonuc)
                              ? 'border-emerald-400/30 bg-emerald-500/10 text-emerald-300'
                              : 'border-amber-400/30 bg-amber-500/10 text-amber-300'
                          }`}
                          data-testid="islem-sonuc-rozeti"
                        >
                          {t(`islem.sonuc.${islem.sonuc}`)}
                        </span>
                      )}
                    </div>
                    <p className="mt-1 break-words font-medium">{yerelBaslik(islem, t, dil)}</p>
                    <p className="mt-0.5 break-all text-xs text-muted-foreground">
                      {islem.alici_eposta} · {t('islem.yonetim.sonKullanmaKisa', { tarih: tarihSaatBicimle(islem.son_kullanma, dil) })}
                      {islem.kullanildi_at &&
                        ` · ${t('islem.yonetim.kullanildiKisa', { tarih: tarihSaatBicimle(islem.kullanildi_at, dil) })}`}
                    </p>
                    {islem.sonuc_notu && (
                      <p className="mt-2 whitespace-pre-line break-words rounded-lg border border-white/5 bg-white/[0.02] p-2 text-sm">
                        {islem.sonuc_notu}
                      </p>
                    )}
                  </div>
                  <div className="flex shrink-0 gap-2">
                    {islem.durum === 'bekliyor' && (
                      <Button
                        variant="outline"
                        size="sm"
                        className="gap-1 !bg-transparent"
                        onClick={() => iptalEt(islem)}
                        data-testid={`islem-iptal-${islem.id}`}
                      >
                        <Ban className="h-4 w-4" aria-hidden="true" />
                        {t('islem.yonetim.iptal')}
                      </Button>
                    )}
                    {islem.durum !== 'kullanildi' && (
                      <Button
                        variant="outline"
                        size="sm"
                        className="gap-1 !bg-transparent"
                        onClick={() => yenile(islem)}
                        data-testid={`islem-yenile-${islem.id}`}
                      >
                        <RotateCw className="h-4 w-4" aria-hidden="true" />
                        {t('islem.yonetim.yenileDugme')}
                      </Button>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {onay && (
        <div
          className="fixed inset-0 z-[70] flex items-center justify-center bg-black/70 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="islem-yonetim-onay-baslik"
          onClick={() => !calisiyor && setOnay(null)}
        >
          <div
            className="cam-kart w-full max-w-md rounded-2xl border border-white/10 bg-background p-6 shadow-2xl"
            onClick={(o) => o.stopPropagation()}
            data-testid="islem-yonetim-onay"
          >
            <h3 id="islem-yonetim-onay-baslik" className="text-lg font-semibold">
              {t('islem.yonetim.onayBaslik')}
            </h3>
            <p className="mt-3 break-words text-sm text-muted-foreground">{onay.mesaj}</p>
            <div className="mt-6 flex justify-end gap-2">
              <Button variant="outline" className="!bg-transparent" onClick={() => setOnay(null)} disabled={calisiyor}>
                {t('islem.vazgec')}
              </Button>
              <Button onClick={() => void onayla()} disabled={calisiyor} data-testid="islem-yonetim-onayla" autoFocus>
                {calisiyor && <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />}
                {t('islem.yonetim.devam')}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
