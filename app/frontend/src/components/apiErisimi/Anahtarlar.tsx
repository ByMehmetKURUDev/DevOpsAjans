import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Ban, Loader2, Plus } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { ALAN, BirKezKutusu, DurumRozeti, KART, ROZET, tarihYaz } from '@/components/apiErisimi/ortak';
import {
  anahtarAdi,
  gunEkle,
  gunSonuIso,
  hataMetni,
  type ApiAnahtari,
  type ApiErisimApi,
  type ApiMeta,
  type ApiMod,
} from '@/lib/apiErisimi';

/** Faz 4A — API anahtarları: liste, oluştur (ham anahtar BİR KEZ), iptal. */
export default function Anahtarlar({
  api,
  mod,
  meta,
  onDegisti,
}: {
  api: ApiErisimApi;
  mod: ApiMod;
  meta: ApiMeta | null;
  onDegisti: () => void;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [liste, setListe] = useState<ApiAnahtari[] | null>(null);
  const [hepsi, setHepsi] = useState(false);
  const [form, setForm] = useState(false);
  const [yeni, setYeni] = useState<{ ad: string; ham: string } | null>(null);

  const yukle = useCallback(async () => {
    try {
      setListe(await api.anahtarlar(mod === 'yonetici' && hepsi));
    } catch (e) {
      toast.error(hataMetni(t, e));
      setListe([]);
    }
  }, [api, mod, hepsi, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const sinirDolu = !!meta && meta.anahtar_sayisi >= meta.anahtar_siniri;

  const iptal = async (a: ApiAnahtari) => {
    if (!window.confirm(t('apiErisimi.anahtar.iptalOnay', { ad: a.ad }))) return;
    try {
      await api.anahtarIptal(a.id);
      toast.success(t('apiErisimi.anahtar.iptalEdildi'));
      await yukle();
      onDegisti();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  return (
    <div className="space-y-4" data-testid="api-anahtarlar">
      {yeni && (
        <BirKezKutusu
          deger={yeni.ham}
          uyari={t('apiErisimi.anahtar.birKez', { ad: yeni.ad })}
          testId="api-ham-anahtar"
          onKapat={() => setYeni(null)}
        />
      )}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          {meta && (
            <span className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-xs text-muted-foreground" data-testid="api-anahtar-hakki">
              {t('apiErisimi.anahtar.hak', { sayi: meta.anahtar_sayisi, sinir: meta.anahtar_siniri })}
            </span>
          )}
          {mod === 'yonetici' && (
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <input type="checkbox" checked={hepsi} onChange={(e) => setHepsi(e.target.checked)} />
              {t('apiErisimi.anahtar.hepsi')}
            </label>
          )}
        </div>
        {!form && (
          <Button
            type="button"
            onClick={() => (sinirDolu ? toast.error(t('apiErisimi.hata.anahtar_siniri', { sinir: meta?.anahtar_siniri })) : setForm(true))}
            className="gap-1.5"
            data-testid="api-anahtar-yeni"
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('apiErisimi.anahtar.yeni')}
          </Button>
        )}
      </div>

      {form && meta && (
        <AnahtarFormu
          api={api}
          mod={mod}
          meta={meta}
          onVazgec={() => setForm(false)}
          onOlustu={async (ad, ham) => {
            setForm(false);
            setYeni({ ad, ham });
            await yukle();
            onDegisti();
          }}
        />
      )}

      {liste === null ? (
        <div className="flex justify-center py-10 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
        </div>
      ) : liste.length === 0 ? (
        <p className={`${KART} p-6 text-sm text-muted-foreground`}>{t('apiErisimi.anahtar.bos')}</p>
      ) : (
        <ul className="space-y-3">
          {liste.map((a) => (
            <li key={a.id} className={`${KART} p-4`} data-anahtar-id={a.id}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold text-white" dir="auto">
                      {a.ad}
                    </span>
                    <DurumRozeti durum={a.durum} metin={t(`apiErisimi.durum.${a.durum}`)} />
                    {a.sahip_tur === 'musteri' && mod === 'yonetici' && (
                      <span className={`${ROZET} border-white/10 text-muted-foreground`} dir="ltr">
                        {a.hesap_email}
                      </span>
                    )}
                  </div>
                  <code className="mt-1 block font-mono text-xs text-purple-200" dir="ltr" data-testid="api-anahtar-onek">
                    {a.onek}
                  </code>
                </div>
                {a.durum === 'aktif' && (
                  <Button type="button" variant="outline" size="sm" className="gap-1.5" onClick={() => void iptal(a)} data-testid="api-anahtar-iptal">
                    <Ban className="h-4 w-4" aria-hidden="true" />
                    {t('apiErisimi.anahtar.iptal')}
                  </Button>
                )}
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {a.kapsamlar.map((k) => (
                  <span key={k} className={`${ROZET} border-purple-400/30 bg-purple-500/10 text-purple-100`} title={k}>
                    {t(`apiErisimi.kapsam.${anahtarAdi(k)}`)}
                  </span>
                ))}
              </div>
              <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-1 text-xs text-muted-foreground sm:grid-cols-2">
                <div className="flex gap-1">
                  <dt>{t('apiErisimi.anahtar.sonKullanma')}:</dt>
                  <dd className="text-slate-200">{a.son_kullanma ? tarihYaz(a.son_kullanma, dil, false) : t('apiErisimi.anahtar.suresizKisa')}</dd>
                </div>
                <div className="flex gap-1">
                  <dt>{t('apiErisimi.anahtar.sonKullanim')}:</dt>
                  <dd className="text-slate-200">
                    {a.son_kullanim_at ? tarihYaz(a.son_kullanim_at, dil) : t('apiErisimi.anahtar.hicKullanilmadi')}
                  </dd>
                </div>
                <div className="flex gap-1">
                  <dt>{t('apiErisimi.anahtar.dakikaSiniri')}:</dt>
                  <dd className="text-slate-200">{t('apiErisimi.anahtar.dk', { sayi: a.dakika_siniri })}</dd>
                </div>
                {a.ip_izinleri.length > 0 && (
                  <div className="flex min-w-0 gap-1">
                    <dt>{t('apiErisimi.anahtar.ipKisa')}:</dt>
                    <dd className="truncate text-slate-200" dir="ltr">
                      {a.ip_izinleri.join(', ')}
                    </dd>
                  </div>
                )}
                <div className="flex min-w-0 gap-1">
                  <dt>{t('apiErisimi.anahtar.olusturan')}:</dt>
                  <dd className="truncate text-slate-200" dir="ltr">
                    {a.olusturan || '—'} · {tarihYaz(a.olusturma, dil, false)}
                  </dd>
                </div>
              </dl>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function AnahtarFormu({
  api,
  mod,
  meta,
  onVazgec,
  onOlustu,
}: {
  api: ApiErisimApi;
  mod: ApiMod;
  meta: ApiMeta;
  onVazgec: () => void;
  onOlustu: (ad: string, ham: string) => void;
}) {
  const { t } = useTranslation();
  const ajans = mod === 'yonetici';
  const [ad, setAd] = useState('');
  const [kapsamlar, setKapsamlar] = useState<string[]>([]);
  const [sonKullanma, setSonKullanma] = useState(ajans ? gunEkle(meta.onerilen_ajans_suresi_gun) : '');
  const [suresiz, setSuresiz] = useState(false);
  const [ip, setIp] = useState('');
  const [dakika, setDakika] = useState(String(meta.dakika_siniri));
  const [gonderiliyor, setGonderiliyor] = useState(false);

  const degistir = (k: string) => setKapsamlar((l) => (l.includes(k) ? l.filter((x) => x !== k) : [...l, k]));

  const gonder = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ad.trim()) {
      toast.error(t('apiErisimi.hata.ad_gerekli'));
      return;
    }
    if (!kapsamlar.length) {
      toast.error(t('apiErisimi.hata.kapsam_gerekli'));
      return;
    }
    setGonderiliyor(true);
    try {
      const sonuc = await api.anahtarOlustur({
        ad: ad.trim(),
        kapsamlar,
        son_kullanma: suresiz || !sonKullanma ? null : gunSonuIso(sonKullanma),
        suresiz_onay: ajans && (suresiz || !sonKullanma) ? suresiz : undefined,
        ip_izinleri: ip
          .split(/[\n,]/)
          .map((x) => x.trim())
          .filter(Boolean),
        dakika_siniri: Number(dakika) || undefined,
      });
      onOlustu(sonuc.anahtar.ad, sonuc.ham_anahtar);
    } catch (hata) {
      toast.error(hataMetni(t, hata));
    } finally {
      setGonderiliyor(false);
    }
  };

  return (
    <form onSubmit={gonder} className={`${KART} space-y-5 p-5`} data-testid="api-anahtar-formu">
      <div>
        <label className="mb-1 block text-sm font-medium" htmlFor="api-anahtar-ad">
          {t('apiErisimi.anahtar.ad')}
        </label>
        <input
          id="api-anahtar-ad"
          className={ALAN}
          value={ad}
          maxLength={80}
          onChange={(e) => setAd(e.target.value)}
          placeholder={t('apiErisimi.anahtar.adOrnek')}
        />
      </div>

      <fieldset>
        <legend className="mb-1 text-sm font-medium">{t('apiErisimi.anahtar.kapsamlar')}</legend>
        <p className="mb-2 text-xs text-muted-foreground">{t('apiErisimi.anahtar.kapsamAciklama')}</p>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {meta.kapsamlar.map((k) => (
            <label
              key={k.anahtar}
              className={`flex items-start gap-2 rounded-lg border border-white/10 p-2 text-sm ${k.izinli ? '' : 'opacity-50'}`}
            >
              <input
                type="checkbox"
                className="mt-1"
                disabled={!k.izinli}
                checked={kapsamlar.includes(k.anahtar)}
                onChange={() => degistir(k.anahtar)}
                data-kapsam={k.anahtar}
              />
              <span className="min-w-0">
                <span className="block">{t(`apiErisimi.kapsam.${anahtarAdi(k.anahtar)}`)}</span>
                <span className="block font-mono text-[11px] text-muted-foreground" dir="ltr">
                  {k.anahtar}
                  {k.yazma ? ` · ${t('apiErisimi.anahtar.yazma')}` : ''}
                </span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label className="mb-1 block text-sm font-medium" htmlFor="api-anahtar-bitis">
            {t('apiErisimi.anahtar.sonKullanma')}
          </label>
          <input
            id="api-anahtar-bitis"
            type="date"
            className={ALAN}
            value={sonKullanma}
            min={gunEkle(1)}
            disabled={suresiz}
            onChange={(e) => setSonKullanma(e.target.value)}
          />
          {ajans ? (
            <label className="mt-2 flex items-start gap-2 text-xs text-amber-200">
              <input type="checkbox" className="mt-0.5" checked={suresiz} onChange={(e) => setSuresiz(e.target.checked)} />
              {t('apiErisimi.anahtar.suresizOnay')}
            </label>
          ) : (
            <p className="mt-1 text-xs text-muted-foreground">{t('apiErisimi.anahtar.sonKullanmaAciklama')}</p>
          )}
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium" htmlFor="api-anahtar-dakika">
            {t('apiErisimi.anahtar.dakikaSiniri')}
          </label>
          <input
            id="api-anahtar-dakika"
            type="number"
            min={1}
            max={meta.dakika_siniri}
            className={ALAN}
            value={dakika}
            onChange={(e) => setDakika(e.target.value)}
          />
          <p className="mt-1 text-xs text-muted-foreground">{t('apiErisimi.anahtar.dakikaAciklama', { sinir: meta.dakika_siniri })}</p>
        </div>
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium" htmlFor="api-anahtar-ip">
          {t('apiErisimi.anahtar.ipIzinleri')}
        </label>
        <textarea
          id="api-anahtar-ip"
          className={`${ALAN} min-h-[64px] font-mono`}
          dir="ltr"
          value={ip}
          onChange={(e) => setIp(e.target.value)}
          placeholder="203.0.113.0/24"
        />
        <p className="mt-1 text-xs text-muted-foreground">{t('apiErisimi.anahtar.ipAciklama')}</p>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={gonderiliyor} className="gap-1.5" data-testid="api-anahtar-olustur">
          {gonderiliyor && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
          {t('apiErisimi.anahtar.olustur')}
        </Button>
        <Button type="button" variant="outline" onClick={onVazgec}>
          {t('apiErisimi.vazgec')}
        </Button>
      </div>
    </form>
  );
}
