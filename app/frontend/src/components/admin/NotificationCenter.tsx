import { useCallback, useEffect, useState } from 'react';
import { CheckCircle2, Loader2, RefreshCw, Save, Send, XCircle } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  NOTIFY_EVENTS,
  fetchDeliveryLog,
  templateKeys,
  testChannel,
  type DeliveryLog,
} from '@/lib/notifyAdmin';
import { saveSiteSetting, type SettingRow, type SettingsMap } from '@/lib/siteSettings';

interface NotificationCenterProps {
  settings: SettingsMap;
  settingRows: SettingRow[];
  adminEmail?: string;
  adminPhone?: string;
  onSaved: () => Promise<void> | void;
}

const KANALLAR = ['email', 'sms', 'whatsapp'] as const;

const DURUM_RENGI: Record<string, string> = {
  sent: 'bg-emerald-500/15 text-emerald-300',
  failed: 'bg-red-500/15 text-red-300',
  skipped: 'bg-amber-500/15 text-amber-300',
};

/**
 * Bildirim merkezi.
 *
 * Üç soruyu tek ekranda cevaplıyor:
 *  1. Kanallar çalışıyor mu?  → test gönder
 *  2. Ne gitti, ne gitmedi?   → gönderim kayıtları ve sebepleri
 *  3. Ne yazıyor?             → şablonlar
 */
export default function NotificationCenter({
  settings,
  settingRows,
  adminEmail,
  adminPhone,
  onSaved,
}: NotificationCenterProps) {
  const { t } = useTranslation();
  const [log, setLog] = useState<DeliveryLog>({ items: [], total: 0, summary: {} });
  const [suzgec, setSuzgec] = useState<string>('');
  const [yukleniyor, setYukleniyor] = useState(false);
  const [deneniyor, setDeneniyor] = useState<string>('');
  const [hedef, setHedef] = useState<Record<string, string>>({});
  const [aktifOlay, setAktifOlay] = useState<string>(NOTIFY_EVENTS[0].key);
  const [sablon, setSablon] = useState<Record<string, string>>({});
  const [kaydediliyor, setKaydediliyor] = useState(false);

  const logYukle = useCallback(async () => {
    setYukleniyor(true);
    try {
      setLog(await fetchDeliveryLog(suzgec || undefined));
    } catch {
      // Arka uç henüz yayında değilse panel yine açılmalı.
      setLog({ items: [], total: 0, summary: {} });
    } finally {
      setYukleniyor(false);
    }
  }, [suzgec]);

  useEffect(() => {
    void logYukle();
  }, [logYukle]);

  useEffect(() => {
    setHedef({
      email: adminEmail ?? '',
      sms: adminPhone ?? '',
      whatsapp: adminPhone ?? '',
    });
  }, [adminEmail, adminPhone]);

  useEffect(() => {
    const anahtarlar = templateKeys(aktifOlay);
    setSablon({
      [anahtarlar.title]: settings[anahtarlar.title] ?? '',
      [anahtarlar.body]: settings[anahtarlar.body] ?? '',
    });
  }, [aktifOlay, settings]);

  const dene = async (kanal: string) => {
    const adres = (hedef[kanal] || '').trim();
    if (!adres) {
      toast.error(t('notifyAdmin.targetMissing'));
      return;
    }
    setDeneniyor(kanal);
    try {
      const sonuc = await testChannel(kanal, adres);
      if (sonuc.status === 'sent') toast.success(t('notifyAdmin.testSent', { channel: kanal }));
      else toast.error(`${kanal}: ${sonuc.detail}`);
      await logYukle();
    } catch (e) {
      const err = e as { message?: string };
      toast.error(err?.message || t('notifyAdmin.testError'));
    } finally {
      setDeneniyor('');
    }
  };

  const sablonKaydet = async () => {
    setKaydediliyor(true);
    try {
      for (const [anahtar, deger] of Object.entries(sablon)) {
        const mevcut = settingRows.find((r) => r.setting_key === anahtar);
        if ((mevcut?.setting_value ?? '') === deger) continue;
        await saveSiteSetting(settingRows, anahtar, deger, 'notify', anahtar);
      }
      toast.success(t('notifyAdmin.templateSaved'));
      await onSaved();
    } catch (e) {
      const err = e as { message?: string };
      toast.error(err?.message || t('notifyAdmin.testError'));
    } finally {
      setKaydediliyor(false);
    }
  };

  const olay = NOTIFY_EVENTS.find((e) => e.key === aktifOlay) ?? NOTIFY_EVENTS[0];
  const anahtarlar = templateKeys(aktifOlay);

  return (
    <div className="space-y-8">
      {/* Kanal testi */}
      <section className="rounded-2xl border border-white/10 bg-white/[0.02] p-6">
        <h3 className="text-lg font-semibold">{t('notifyAdmin.testTitle')}</h3>
        <p className="mb-5 text-sm text-muted-foreground">{t('notifyAdmin.testDesc')}</p>

        <div className="grid gap-4 md:grid-cols-3">
          {KANALLAR.map((kanal) => {
            const ozet = log.summary[kanal] ?? {};
            return (
              <div key={kanal} className="rounded-xl border border-white/10 p-4">
                <div className="mb-3 flex items-center justify-between">
                  <span className="font-semibold uppercase tracking-wide">{kanal}</span>
                  <span
                    className={`rounded-full px-2 py-0.5 text-[11px] ${
                      settings[`notify_${kanal}`] === '1'
                        ? 'bg-emerald-500/15 text-emerald-300'
                        : 'bg-white/10 text-muted-foreground'
                    }`}
                  >
                    {settings[`notify_${kanal}`] === '1'
                      ? t('notifyAdmin.on')
                      : t('notifyAdmin.off')}
                  </span>
                </div>

                <Label htmlFor={`hedef-${kanal}`} className="text-xs">
                  {kanal === 'email' ? t('notifyAdmin.targetEmail') : t('notifyAdmin.targetPhone')}
                </Label>
                <Input
                  id={`hedef-${kanal}`}
                  value={hedef[kanal] ?? ''}
                  onChange={(e) => setHedef((h) => ({ ...h, [kanal]: e.target.value }))}
                  className="mt-1.5"
                />

                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => dene(kanal)}
                  disabled={deneniyor === kanal}
                  className="mt-3 w-full gap-2"
                >
                  {deneniyor === kanal ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                  ) : (
                    <Send className="h-3.5 w-3.5" aria-hidden="true" />
                  )}
                  {t('notifyAdmin.sendTest')}
                </Button>

                {Object.keys(ozet).length > 0 && (
                  <p className="mt-3 text-[11px] text-muted-foreground">
                    {Object.entries(ozet)
                      .map(([durum, adet]) => `${durum}: ${adet}`)
                      .join(' · ')}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {/* Şablonlar */}
      <section className="rounded-2xl border border-white/10 bg-white/[0.02] p-6">
        <h3 className="text-lg font-semibold">{t('notifyAdmin.templateTitle')}</h3>
        <p className="mb-5 text-sm text-muted-foreground">{t('notifyAdmin.templateDesc')}</p>

        <div className="mb-5 flex flex-wrap gap-2" role="group">
          {NOTIFY_EVENTS.map((e) => (
            <button
              key={e.key}
              type="button"
              onClick={() => setAktifOlay(e.key)}
              aria-pressed={aktifOlay === e.key}
              className={`rounded-full border px-4 py-2 text-sm font-semibold transition-colors ${
                aktifOlay === e.key
                  ? 'border-purple-400 bg-purple-500/20 text-white'
                  : 'border-white/10 text-muted-foreground hover:border-purple-500/40 hover:text-white'
              }`}
            >
              {t(e.labelKey)}
            </button>
          ))}
        </div>

        <div className="grid gap-5">
          <div className="grid gap-2">
            <Label htmlFor={`tpl-baslik-${aktifOlay}`}>{t('notifyAdmin.tplTitle')}</Label>
            <Input
              id={`tpl-baslik-${aktifOlay}`}
              value={sablon[anahtarlar.title] ?? ''}
              onChange={(e) => setSablon((s) => ({ ...s, [anahtarlar.title]: e.target.value }))}
              placeholder={t('notifyAdmin.tplPlaceholder')}
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor={`tpl-govde-${aktifOlay}`}>{t('notifyAdmin.tplBody')}</Label>
            <Textarea
              id={`tpl-govde-${aktifOlay}`}
              rows={5}
              value={sablon[anahtarlar.body] ?? ''}
              onChange={(e) => setSablon((s) => ({ ...s, [anahtarlar.body]: e.target.value }))}
              placeholder={t('notifyAdmin.tplPlaceholder')}
            />
          </div>

          <div>
            <p className="mb-2 text-xs text-muted-foreground">{t('notifyAdmin.tokensHint')}</p>
            <div className="flex flex-wrap gap-2">
              {olay.tokens.map((token) => (
                <code
                  key={token}
                  className="rounded-lg bg-purple-500/15 px-2 py-1 text-xs text-purple-200"
                >
                  {`{{${token}}}`}
                </code>
              ))}
            </div>
          </div>
        </div>

        <Button type="button" onClick={sablonKaydet} disabled={kaydediliyor} className="mt-5 gap-2">
          {kaydediliyor ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <Save className="h-4 w-4" aria-hidden="true" />
          )}
          {t('notifyAdmin.saveTemplate')}
        </Button>
      </section>

      {/* Gönderim kayıtları */}
      <section className="rounded-2xl border border-white/10 bg-white/[0.02] p-6">
        <div className="mb-1 flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-lg font-semibold">
            {t('notifyAdmin.logTitle')} ({log.total})
          </h3>
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={suzgec}
              onChange={(e) => setSuzgec(e.target.value)}
              aria-label={t('notifyAdmin.filter')}
              className="h-9 rounded-lg border border-white/10 bg-[#120b1f] px-3 text-sm text-white outline-none hover:border-purple-500/40"
            >
              <option value="">{t('notifyAdmin.allStatuses')}</option>
              <option value="sent">sent</option>
              <option value="failed">failed</option>
              <option value="skipped">skipped</option>
            </select>
            <Button type="button" variant="outline" size="sm" onClick={logYukle} className="gap-2">
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
              {t('notifyAdmin.refresh')}
            </Button>
          </div>
        </div>
        <p className="mb-5 text-sm text-muted-foreground">{t('notifyAdmin.logDesc')}</p>

        {yukleniyor ? (
          <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            {t('notifyAdmin.loading')}
          </div>
        ) : log.items.length === 0 ? (
          <p className="py-6 text-sm text-muted-foreground">{t('notifyAdmin.logEmpty')}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[46rem] border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-white/10 text-xs uppercase tracking-wide text-muted-foreground">
                  <th className="py-2 pe-4">{t('notifyAdmin.colTime')}</th>
                  <th className="py-2 pe-4">{t('notifyAdmin.colChannel')}</th>
                  <th className="py-2 pe-4">{t('notifyAdmin.colStatus')}</th>
                  <th className="py-2 pe-4">{t('notifyAdmin.colTo')}</th>
                  <th className="py-2">{t('notifyAdmin.colDetail')}</th>
                </tr>
              </thead>
              <tbody>
                {log.items.map((satir) => (
                  <tr key={satir.id} className="border-b border-white/5 align-top">
                    <td className="whitespace-nowrap py-2.5 pe-4 text-xs text-muted-foreground">
                      {satir.created_at ? new Date(satir.created_at).toLocaleString('tr-TR') : '—'}
                    </td>
                    <td className="py-2.5 pe-4 uppercase">{satir.channel}</td>
                    <td className="py-2.5 pe-4">
                      <span
                        className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] ${
                          DURUM_RENGI[satir.delivery_status ?? ''] ?? 'bg-white/10'
                        }`}
                      >
                        {satir.delivery_status === 'sent' ? (
                          <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                        ) : (
                          <XCircle className="h-3 w-3" aria-hidden="true" />
                        )}
                        {satir.delivery_status}
                      </span>
                    </td>
                    <td className="py-2.5 pe-4 text-xs">{satir.recipient_email}</td>
                    <td className="py-2.5 text-xs text-muted-foreground">
                      {satir.delivery_detail || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
