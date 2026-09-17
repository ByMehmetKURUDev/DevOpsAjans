import { useEffect, useState } from 'react';
import { FileText, Flag, Loader2, MessageSquare, Paperclip } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { fetchProjectEvents, type ProjectEvent } from '@/lib/projectEvents';

interface ProjectTimelineProps {
  projectId: number;
  /** Müşteri panelinde true: iç notlar gizlenir. */
  clientView?: boolean;
  /** Dışarıdan tetiklenen yenileme (aşama değiştirince artırılır). */
  refreshKey?: number;
}

const IKONLAR: Record<string, typeof Flag> = {
  stage_change: Flag,
  status_change: Flag,
  note: MessageSquare,
  file: Paperclip,
  delivery: FileText,
};

/**
 * Proje zaman çizelgesi.
 *
 * Aynı bileşen hem yönetici hem müşteri panelinde; tek fark `clientView`.
 * İki ayrı liste yazmak, birinde gösterilen bir kaydın diğerinde
 * unutulmasıyla sonuçlanırdı.
 */
export default function ProjectTimeline({
  projectId,
  clientView = false,
  refreshKey = 0,
}: ProjectTimelineProps) {
  const { t } = useTranslation();
  const [events, setEvents] = useState<ProjectEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [hata, setHata] = useState(false);

  useEffect(() => {
    let iptal = false;
    setLoading(true);
    setHata(false);
    fetchProjectEvents(projectId, clientView)
      .then((liste) => {
        if (!iptal) setEvents(liste);
      })
      .catch(() => {
        if (!iptal) setHata(true);
      })
      .finally(() => {
        if (!iptal) setLoading(false);
      });
    return () => {
      iptal = true;
    };
  }, [projectId, clientView, refreshKey]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        {t('projectTimeline.loading')}
      </div>
    );
  }

  if (hata) {
    return <p className="py-6 text-sm text-muted-foreground">{t('projectTimeline.error')}</p>;
  }

  if (events.length === 0) {
    return <p className="py-6 text-sm text-muted-foreground">{t('projectTimeline.empty')}</p>;
  }

  return (
    <ol className="relative space-y-4 border-s border-white/10 ps-6">
      {events.map((olay) => {
        const Ikon = IKONLAR[olay.event_type] ?? MessageSquare;
        const gizli = olay.visible_to_client === '0';
        return (
          <li key={olay.id} className="relative">
            <span className="absolute -start-[31px] top-1 flex h-5 w-5 items-center justify-center rounded-full border border-white/10 bg-[#150c24]">
              <Ikon className="h-3 w-3 text-purple-300" aria-hidden="true" />
            </span>

            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-medium">{olay.title}</p>
                {gizli && (
                  <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[11px] text-amber-300">
                    {t('projectTimeline.internal')}
                  </span>
                )}
              </div>

              {olay.body && (
                <p className="mt-2 whitespace-pre-line text-sm leading-6 text-muted-foreground">
                  {olay.body}
                </p>
              )}

              {olay.attachment_url && (
                <a
                  href={olay.attachment_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-3 inline-flex items-center gap-1.5 text-xs font-semibold text-purple-300 underline underline-offset-4 hover:text-pink-300"
                >
                  <Paperclip className="h-3.5 w-3.5" aria-hidden="true" />
                  {t('projectTimeline.attachment')}
                </a>
              )}

              <p className="mt-3 text-[11px] text-muted-foreground/70">
                {olay.created_at ? new Date(olay.created_at).toLocaleString('tr-TR') : ''}
                {olay.actor_name ? ` · ${olay.actor_name}` : ''}
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
