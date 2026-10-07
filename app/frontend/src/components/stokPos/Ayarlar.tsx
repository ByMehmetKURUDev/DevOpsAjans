import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Info, MapPin, Plus, Star } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { Alan, Anahtar, GIRDI, KART, METIN_ALANI, Rozet, SECIM } from '@/components/stokPos/ortak';
import { hataMetni, type Ayarlar as AyarTipi, type Meta, type StokApi } from '@/lib/stokPos';

/** Faz 6P — ayarlar: fiş/fatura künyesi, KDV oranları (değiştirilebilir), eksi stok, kasiyer yetkileri, QR menü eşitleme, şubeler. */
export default function Ayarlar({ api, meta, onMeta }: { api: StokApi; meta: Meta; onMeta: () => void }) {
  const { t } = useTranslation();
  const [a, setA] = useState<AyarTipi>(meta.ayarlar);
  const [oranlar, setOranlar] = useState(meta.ayarlar.kdv_oranlari.join(', '));
  const [mesaj, setMesaj] = useState<{ ok: boolean; metin: string } | null>(null);
  const [yeniKonum, setYeniKonum] = useState('');
  const kaydet = async () => {
    setMesaj(null);
    const liste = oranlar
      .split(/[,;\s]+/)
      .map((x) => x.trim())
      .filter(Boolean)
      .map(Number);
    try {
      const r = await api.ayarlarKaydet({
        firma_adi: a.firma_adi,
        adres: a.adres,
        telefon: a.telefon,
        eposta: a.eposta,
        vergi_dairesi: a.vergi_dairesi,
        vergi_no: a.vergi_no,
        para_birimi: a.para_birimi,
        kdv_oranlari: liste,
        varsayilan_kdv: a.varsayilan_kdv,
        eksi_stok: a.eksi_stok,
        kasa_iade: a.kasa_iade,
        kasa_indirim_yuzde: a.kasa_indirim_yuzde,
        qr_stok_esitle: a.qr_stok_esitle,
        kritik_bildirim: a.kritik_bildirim,
        fis_notu: a.fis_notu,
      });
      setA(r);
      setOranlar(r.kdv_oranlari.join(', '));
      setMesaj({ ok: true, metin: t('stokPos.ayar.kaydedildi') });
      onMeta();
    } catch (e) {
      setMesaj({ ok: false, metin: hataMetni(t, e) });
    }
  };
  const konumEkle = async () => {
    try {
      await api.konumEkle({ ad: yeniKonum });
      setYeniKonum('');
      onMeta();
    } catch (e) {
      setMesaj({ ok: false, metin: hataMetni(t, e) });
    }
  };
  const konumGuncelle = async (id: number, g: Record<string, unknown>) => {
    try {
      await api.konumGuncelle(id, g);
      onMeta();
    } catch (e) {
      setMesaj({ ok: false, metin: hataMetni(t, e) });
    }
  };
  const aktifSayi = meta.konumlar.filter((k) => k.aktif).length;
  return (
    <div className="space-y-4" data-testid="stok-ayarlar">
      <div className="flex items-start gap-2 rounded-xl border border-sky-400/30 bg-sky-500/10 p-3 text-sm text-sky-100">
        <Info className="mt-0.5 h-4 w-4 flex-none" aria-hidden="true" />
        <p>{t('stokPos.ayar.yasal')}</p>
      </div>
      <div className={`${KART} grid gap-3 p-4 sm:grid-cols-2`}>
        <h3 className="font-semibold sm:col-span-2">{t('stokPos.ayar.kunye')}</h3>
        <Alan etiket={t('stokPos.ayar.firmaAdi')}>
          <input className={GIRDI} value={a.firma_adi || ''} onChange={(e) => setA({ ...a, firma_adi: e.target.value })} maxLength={160} data-testid="stok-ayar-firma" />
        </Alan>
        <Alan etiket={t('stokPos.alici.telefon')}>
          <input className={GIRDI} value={a.telefon || ''} onChange={(e) => setA({ ...a, telefon: e.target.value })} maxLength={32} />
        </Alan>
        <Alan etiket={t('stokPos.alici.adres')} className="sm:col-span-2">
          <input className={GIRDI} value={a.adres || ''} onChange={(e) => setA({ ...a, adres: e.target.value })} maxLength={500} />
        </Alan>
        <Alan etiket={t('stokPos.alici.vergiDairesi')}>
          <input className={GIRDI} value={a.vergi_dairesi || ''} onChange={(e) => setA({ ...a, vergi_dairesi: e.target.value })} maxLength={80} />
        </Alan>
        <Alan etiket={t('stokPos.alici.vergiNo')}>
          <input className={GIRDI} value={a.vergi_no || ''} onChange={(e) => setA({ ...a, vergi_no: e.target.value })} inputMode="numeric" />
        </Alan>
        <Alan etiket={t('stokPos.alici.eposta')}>
          <input className={GIRDI} value={a.eposta || ''} onChange={(e) => setA({ ...a, eposta: e.target.value })} type="email" />
        </Alan>
        <Alan etiket={t('stokPos.ayar.paraBirimi')}>
          <select className={SECIM} value={a.para_birimi} onChange={(e) => setA({ ...a, para_birimi: e.target.value })}>
            {['TRY', 'USD', 'EUR', 'GBP'].map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </Alan>
        <Alan etiket={t('stokPos.ayar.fisNotu')} className="sm:col-span-2" ipucu={t('stokPos.ayar.fisNotuIpucu')}>
          <textarea className={METIN_ALANI} value={a.fis_notu || ''} onChange={(e) => setA({ ...a, fis_notu: e.target.value })} maxLength={300} />
        </Alan>
      </div>
      <div className={`${KART} grid gap-3 p-4 sm:grid-cols-2`}>
        <h3 className="font-semibold sm:col-span-2">{t('stokPos.ayar.vergiVeKasa')}</h3>
        <Alan etiket={t('stokPos.ayar.kdvOranlari')} ipucu={t('stokPos.ayar.kdvIpucu', { varsayilan: meta.varsayilan_kdv_oranlari.join(', ') })}>
          <input className={GIRDI} value={oranlar} onChange={(e) => setOranlar(e.target.value)} data-testid="stok-ayar-kdv" />
        </Alan>
        <Alan etiket={t('stokPos.ayar.varsayilanKdv')}>
          <select className={SECIM} value={a.varsayilan_kdv} onChange={(e) => setA({ ...a, varsayilan_kdv: Number(e.target.value) })}>
            {a.kdv_oranlari.map((o) => (
              <option key={o} value={o}>
                %{o}
              </option>
            ))}
          </select>
        </Alan>
        <Alan etiket={t('stokPos.ayar.kasaIndirim')} ipucu={t('stokPos.ayar.kasaIndirimIpucu')}>
          <input
            className={GIRDI}
            type="number"
            min={0}
            max={100}
            value={a.kasa_indirim_yuzde}
            onChange={(e) => setA({ ...a, kasa_indirim_yuzde: Math.max(0, Math.min(100, Number(e.target.value) || 0)) })}
          />
        </Alan>
        <div className="space-y-2 self-end sm:col-span-2">
          <Anahtar acik={a.eksi_stok} onDegis={(v) => setA({ ...a, eksi_stok: v })} etiket={t('stokPos.ayar.eksiStok')} testid="stok-ayar-eksi" />
          <Anahtar acik={a.kasa_iade} onDegis={(v) => setA({ ...a, kasa_iade: v })} etiket={t('stokPos.ayar.kasaIade')} testid="stok-ayar-kasa-iade" />
          <Anahtar acik={a.kritik_bildirim} onDegis={(v) => setA({ ...a, kritik_bildirim: v })} etiket={t('stokPos.ayar.kritikBildirim')} />
          <Anahtar acik={a.qr_stok_esitle} onDegis={(v) => setA({ ...a, qr_stok_esitle: v })} etiket={t('stokPos.ayar.qrEsitle')} />
        </div>
      </div>
      {mesaj && (
        <p className={`text-sm ${mesaj.ok ? 'text-emerald-300' : 'text-red-300'}`} role="status" data-testid="stok-ayar-mesaj">
          {mesaj.metin}
        </p>
      )}
      <div className="flex justify-end">
        <Button onClick={() => void kaydet()} data-testid="stok-ayar-kaydet">
          {t('stokPos.kaydet')}
        </Button>
      </div>

      <div className={`${KART} space-y-3 p-4`}>
        <h3 className="flex items-center gap-2 font-semibold">
          <MapPin className="h-4 w-4" aria-hidden="true" />
          {t('stokPos.ayar.konumlar')}
          <span className="text-xs font-normal text-muted-foreground">{t('stokPos.ayar.konumSinir', { sayi: aktifSayi, sinir: meta.sinirlar.sube })}</span>
        </h3>
        <ul className="divide-y divide-white/5">
          {meta.konumlar.map((k) => (
            <li key={k.id} className={`flex flex-wrap items-center gap-2 py-2 text-sm ${k.aktif ? '' : 'opacity-60'}`}>
              <input
                className={cn(GIRDI, 'h-9 min-w-0 flex-1')}
                defaultValue={k.ad}
                onBlur={(e) => e.target.value.trim() && e.target.value !== k.ad && void konumGuncelle(k.id, { ad: e.target.value })}
                aria-label={t('stokPos.konum')}
              />
              {k.varsayilan ? (
                <Rozet renk="border-purple-400/40 bg-purple-500/15 text-purple-100">
                  <Star className="h-3 w-3" aria-hidden="true" />
                  {t('stokPos.ayar.varsayilan')}
                </Rozet>
              ) : (
                <>
                  {k.aktif && (
                    <Button size="sm" variant="ghost" onClick={() => void konumGuncelle(k.id, { varsayilan: true })}>
                      {t('stokPos.ayar.varsayilanYap')}
                    </Button>
                  )}
                  <Button size="sm" variant="ghost" onClick={() => void konumGuncelle(k.id, { aktif: !k.aktif })}>
                    {k.aktif ? t('stokPos.ayar.pasifYap') : t('stokPos.ayar.aktifYap')}
                  </Button>
                </>
              )}
            </li>
          ))}
        </ul>
        <div className="flex gap-2">
          <input className={GIRDI} value={yeniKonum} onChange={(e) => setYeniKonum(e.target.value)} placeholder={t('stokPos.ayar.yeniKonum')} maxLength={80} data-testid="stok-yeni-konum" />
          <Button onClick={() => void konumEkle()} disabled={!yeniKonum.trim() || aktifSayi >= meta.sinirlar.sube} className="gap-1.5">
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('stokPos.ekle')}
          </Button>
        </div>
      </div>
    </div>
  );
}
