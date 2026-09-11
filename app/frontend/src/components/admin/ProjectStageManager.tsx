import { useEffect, useState } from 'react';
import { Loader2, Send, StickyNote } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import ProjectTimeline from '@/components/ProjectTimeline';
import { addProjectNote, fetchStages, setProjectStage, type Stage } from '@/lib/projectEvents';

interface ProjectStageManagerProps {
  projectId: number;
  projectTitle: string;
  clientEmail?: string;
  currentStage?: string;
  adminName?: string;
  adminEmail?: string;
  /** Proje listesi tazelensin diye. */
  onChanged?: () => void;
}

/**
 * Bir projenin aşamasını ilerletir ve not ekler.
 *
 * Aşama değişimi tek bir uca gidiyor; orada projenin durumu güncelleniyor,
 * zaman çizelgesine kayıt düşüyor ve müşteriye bildirim gidiyor. Panelde
 * ayrı ayrı üç işlem yapılsaydı biri unutulabilirdi.
 */
export default function ProjectStageManager({
  projectId,
  projectTitle,
  clientEmail,
  currentStage,
  adminName,
  adminEmail,
  onChanged,
}: ProjectStageManagerProps) {
  const { t } = useTranslation();
  const [stages, setStages] = useState<Stage[]>([]);
  const [stage, setStage] = useState(currentStage || '');
  const [stageNote, setStageNote] = useState('');
  const [noteTitle, setNoteTitle] = useState('');
  const [noteBody, setNoteBody] = useState('');
  const [noteFile, setNoteFile] = useState('');
  const [icNot, setIcNot] = useState(false);
  const [calisiyor, setCalisiyor] = useState(false);
  const [tazele, setTazele] = useState(0);

  useEffect(() => {
    fetchStages()
      .then(setStages)
      .catch(() => toast.error(t('projectStages.stagesError')));
  }, [t]);

  useEffect(() => {
    setStage(currentStage || '');
  }, [currentStage, projectId]);

  const asamayiKaydet = async () => {
    if (!stage) return;
    setCalisiyor(true);
    try {
      await setProjectStage({
        project_id: projectId,
        stage,
        note: stageNote || undefined,
        actor_name: adminName,
        actor_email: adminEmail,
      });
      setStageNote('');
      setTazele((n) => n + 1);
      onChanged?.();
      toast.success(
        clientEmail
          ? t('projectStages.stageSavedNotified', { email: clientEmail })
          : t('projectStages.stageSavedNoClient'),
      );
    } catch (e) {
      const err = e as { message?: string };
      toast.error(err?.message || t('projectStages.saveError'));
    } finally {
      setCalisiyor(false);
    }
  };

  const notEkle = async () => {
    if (!noteTitle.trim()) return;
    setCalisiyor(true);
    try {
      await addProjectNote({
        project_id: projectId,
        title: noteTitle.trim(),
        body: noteBody || undefined,
        attachment_url: noteFile || undefined,
        actor_name: adminName,
        actor_email: adminEmail,
        visible_to_client: !icNot,
        notify_client: !icNot,
      });
      setNoteTitle('');
      setNoteBody('');
      setNoteFile('');
      setTazele((n) => n + 1);
      toast.success(icNot ? t('projectStages.noteSavedInternal') : t('projectStages.noteSaved'));
    } catch (e) {
      const err = e as { message?: string };
      toast.error(err?.message || t('projectStages.saveError'));
    } finally {
      setCalisiyor(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold">{projectTitle}</h3>
        <p className="text-sm text-muted-foreground">
          {clientEmail
            ? t('projectStages.clientBound', { email: clientEmail })
            : t('projectStages.noClient')}
        </p>
      </div>

      {/* Aşama */}
      <section className="rounded-2xl border border-white/10 bg-white/[0.02] p-5">
        <h4 className="mb-4 font-semibold">{t('projectStages.stageTitle')}</h4>

        <div className="grid gap-4 sm:grid-cols-[minmax(0,14rem)_1fr]">
          <div className="grid gap-2">
            <Label htmlFor={`asama-${projectId}`}>{t('projectStages.stageLabel')}</Label>
            <select
              id={`asama-${projectId}`}
              value={stage}
              onChange={(e) => setStage(e.target.value)}
              className="h-11 rounded-xl border border-white/10 bg-[#120b1f] px-3 text-sm text-white outline-none hover:border-purple-500/40 focus:border-purple-400"
            >
              <option value="">{t('projectStages.pickStage')}</option>
              {stages.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>

          <div className="grid gap-2">
            <Label htmlFor={`asama-not-${projectId}`}>{t('projectStages.stageNote')}</Label>
            <Input
              id={`asama-not-${projectId}`}
              value={stageNote}
              onChange={(e) => setStageNote(e.target.value)}
              placeholder={t('projectStages.stageNotePlaceholder')}
            />
          </div>
        </div>

        <p className="mt-3 text-xs text-muted-foreground">{t('projectStages.stageHint')}</p>

        <Button
          type="button"
          onClick={asamayiKaydet}
          disabled={calisiyor || !stage || stage === currentStage}
          className="mt-4 gap-2"
        >
          {calisiyor ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <Send className="h-4 w-4" aria-hidden="true" />
          )}
          {t('projectStages.saveStage')}
        </Button>
      </section>

      {/* Not / dosya */}
      <section className="rounded-2xl border border-white/10 bg-white/[0.02] p-5">
        <h4 className="mb-4 font-semibold">{t('projectStages.noteTitle')}</h4>

        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor={`not-baslik-${projectId}`}>{t('projectStages.noteHeading')}</Label>
            <Input
              id={`not-baslik-${projectId}`}
              value={noteTitle}
              onChange={(e) => setNoteTitle(e.target.value)}
              placeholder={t('projectStages.noteHeadingPlaceholder')}
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor={`not-govde-${projectId}`}>{t('projectStages.noteBody')}</Label>
            <Textarea
              id={`not-govde-${projectId}`}
              rows={3}
              value={noteBody}
              onChange={(e) => setNoteBody(e.target.value)}
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor={`not-dosya-${projectId}`}>{t('projectStages.noteFile')}</Label>
            <Input
              id={`not-dosya-${projectId}`}
              value={noteFile}
              onChange={(e) => setNoteFile(e.target.value)}
              placeholder="https://…"
            />
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={icNot}
              onChange={(e) => setIcNot(e.target.checked)}
              className="h-4 w-4 accent-purple-500"
            />
            {t('projectStages.internalOnly')}
          </label>
        </div>

        <Button
          type="button"
          variant="outline"
          onClick={notEkle}
          disabled={calisiyor || !noteTitle.trim()}
          className="mt-4 gap-2"
        >
          <StickyNote className="h-4 w-4" aria-hidden="true" />
          {t('projectStages.addNote')}
        </Button>
      </section>

      {/* Geçmiş */}
      <section>
        <h4 className="mb-4 font-semibold">{t('projectStages.history')}</h4>
        <ProjectTimeline projectId={projectId} refreshKey={tazele} />
      </section>
    </div>
  );
}
