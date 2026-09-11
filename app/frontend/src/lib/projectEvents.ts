import { useEffect, useState } from 'react';
import { client } from '@/lib/sdkClient';

/** Proje zaman çizelgesi kaydı. */
export interface ProjectEvent {
  id: number;
  project_id: number;
  event_type: 'stage_change' | 'note' | 'file' | 'status_change' | 'delivery' | string;
  title: string;
  body?: string;
  from_value?: string;
  to_value?: string;
  actor_name?: string;
  actor_email?: string;
  visible_to_client?: string;
  attachment_url?: string;
  created_at?: string;
}

export interface Stage {
  key: string;
  label: string;
  order: number;
}

const BASE = '/api/v1/entities/project_events';

/**
 * Aşama listesi arka uçtan geliyor.
 *
 * Kodda iki yerde (panel ve sunucu) ayrı ayrı tanımlamak, birinin
 * değişip diğerinin kalmasıyla sonuçlanır. Tek kaynak sunucu.
 */
export async function fetchStages(): Promise<Stage[]> {
  const res = (await client.apiCall.invoke({
    method: 'GET',
    url: `${BASE}/stages`,
  })) as { data?: { stages?: Stage[] } };
  return res?.data?.stages ?? [];
}

export async function fetchProjectEvents(
  projectId: number,
  clientView = false,
): Promise<ProjectEvent[]> {
  const params = new URLSearchParams({
    project_id: String(projectId),
    client_view: String(clientView),
  });
  const res = (await client.apiCall.invoke({
    method: 'GET',
    url: `${BASE}?${params}`,
  })) as { data?: { items?: ProjectEvent[] } };
  return res?.data?.items ?? [];
}

export async function setProjectStage(payload: {
  project_id: number;
  stage: string;
  status?: string;
  progress?: number;
  note?: string;
  actor_name?: string;
  actor_email?: string;
}): Promise<ProjectEvent> {
  const res = (await client.apiCall.invoke({
    method: 'POST',
    url: `${BASE}/stage`,
    data: payload,
  })) as { data?: ProjectEvent };
  return res?.data as ProjectEvent;
}

export async function addProjectNote(payload: {
  project_id: number;
  title: string;
  body?: string;
  attachment_url?: string;
  actor_name?: string;
  actor_email?: string;
  visible_to_client?: boolean;
  notify_client?: boolean;
}): Promise<ProjectEvent> {
  const res = (await client.apiCall.invoke({
    method: 'POST',
    url: `${BASE}/note`,
    data: payload,
  })) as { data?: ProjectEvent };
  return res?.data as ProjectEvent;
}

export async function deleteProjectEvent(eventId: number): Promise<void> {
  await client.apiCall.invoke({ method: 'DELETE', url: `${BASE}/${eventId}` });
}

/**
 * Aşama anahtarını okunur etikete çevirir.
 *
 * Panellerde ham anahtar ("design") görünüyordu; müşteri bunu okumak
 * zorunda değil. Liste bir kez çekilip modül düzeyinde saklanıyor —
 * her proje kartı ayrı istek atmasın.
 */
let stageCache: Stage[] | null = null;
let stagePromise: Promise<Stage[]> | null = null;

export function useStageLabels(): (key: string | undefined) => string {
  const [stages, setStages] = useState<Stage[]>(stageCache ?? []);

  useEffect(() => {
    if (stageCache) return;
    stagePromise =
      stagePromise ??
      fetchStages()
        .then((liste) => {
          stageCache = liste;
          return liste;
        })
        .catch(() => []);
    let iptal = false;
    void stagePromise.then((liste) => {
      if (!iptal) setStages(liste);
    });
    return () => {
      iptal = true;
    };
  }, []);

  return (key) => {
    if (!key) return '';
    return stages.find((s) => s.key === key)?.label ?? key;
  };
}
