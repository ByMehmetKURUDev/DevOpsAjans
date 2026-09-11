import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Bell, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useNotifications } from '@/lib/notifications';

interface NotificationBellProps {
  email: string | undefined;
}

/** "3 dakika önce" gibi göreli zaman; sunucudan gelen ISO damgasından. */
function goreliZaman(iso: string | undefined, t: (k: string, o?: object) => string): string {
  if (!iso) return '';
  const fark = Date.now() - Date.parse(iso);
  if (Number.isNaN(fark)) return '';
  const dakika = Math.floor(fark / 60000);
  if (dakika < 1) return t('notify.justNow');
  if (dakika < 60) return t('notify.minutesAgo', { count: dakika });
  const saat = Math.floor(dakika / 60);
  if (saat < 24) return t('notify.hoursAgo', { count: saat });
  return t('notify.daysAgo', { count: Math.floor(saat / 24) });
}

/**
 * Bildirim çanı.
 *
 * Yalnızca giriş yapmış kullanıcıya görünüyor. Paneli açınca okunmamışlar
 * işaretleniyor — kullanıcı zaten görmüş oluyor.
 */
export default function NotificationBell({ email }: NotificationBellProps) {
  const { t } = useTranslation();
  const { items, unread, loading, markAllRead } = useNotifications(email);
  const [acik, setAcik] = useState(false);
  const kap = useRef<HTMLDivElement>(null);

  // Dışarı tıklanınca ve Esc ile kapansın.
  useEffect(() => {
    if (!acik) return;
    const disari = (e: MouseEvent) => {
      if (kap.current && !kap.current.contains(e.target as Node)) setAcik(false);
    };
    const esc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setAcik(false);
    };
    document.addEventListener('mousedown', disari);
    document.addEventListener('keydown', esc);
    return () => {
      document.removeEventListener('mousedown', disari);
      document.removeEventListener('keydown', esc);
    };
  }, [acik]);

  if (!email) return null;

  const ac = () => {
    const yeniDurum = !acik;
    setAcik(yeniDurum);
    if (yeniDurum) void markAllRead();
  };

  return (
    <div className="relative" ref={kap}>
      <button
        type="button"
        onClick={ac}
        aria-expanded={acik}
        aria-label={
          unread > 0 ? t('notify.bellWithCount', { count: unread }) : t('notify.bell')
        }
        className="relative inline-flex h-10 w-10 items-center justify-center rounded-xl text-muted-foreground transition-colors hover:text-foreground"
      >
        <Bell className="h-5 w-5" aria-hidden="true" />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 inline-flex min-w-[18px] items-center justify-center rounded-full bg-gradient-to-r from-purple-600 to-pink-600 px-1 text-[10px] font-bold leading-[18px] text-white">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>

      {acik && (
        <div
          role="dialog"
          aria-label={t('notify.title')}
          className="absolute end-0 z-50 mt-2 w-[min(22rem,calc(100vw-2rem))] overflow-hidden rounded-2xl border border-white/10 bg-[#0e0818] shadow-2xl"
        >
          <div className="flex items-center justify-between border-b border-white/5 px-4 py-3">
            <h2 className="text-sm font-semibold">{t('notify.title')}</h2>
            {loading && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
          </div>

          <ul className="max-h-80 overflow-y-auto">
            {items.length === 0 ? (
              <li className="px-4 py-8 text-center text-sm text-muted-foreground">
                {t('notify.empty')}
              </li>
            ) : (
              items.map((bildirim) => {
                const govde = (
                  <>
                    <p className="text-sm font-medium leading-snug text-foreground">
                      {bildirim.title}
                    </p>
                    {bildirim.body && (
                      <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                        {bildirim.body}
                      </p>
                    )}
                    <p className="mt-1.5 text-[11px] text-muted-foreground/70">
                      {goreliZaman(bildirim.created_at, t)}
                    </p>
                  </>
                );

                return (
                  <li key={bildirim.id} className="border-b border-white/5 last:border-0">
                    {bildirim.link ? (
                      <Link
                        to={bildirim.link}
                        onClick={() => setAcik(false)}
                        className="block px-4 py-3 transition-colors hover:bg-white/[0.03]"
                      >
                        {govde}
                      </Link>
                    ) : (
                      <div className="px-4 py-3">{govde}</div>
                    )}
                  </li>
                );
              })
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
