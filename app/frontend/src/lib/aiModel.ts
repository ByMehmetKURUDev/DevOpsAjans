/**
 * Sitenin kullandığı dil modeli — tek kaynak.
 *
 * Hem sohbet asistanı (`asistanAi.ts`) hem Keşif Sihirbazı (`kesifAi.ts`)
 * buradan okuyor. İkisinde ayrı ayrı yazılıydı; sağlayıcı değişince birini
 * güncelleyip diğerini unutmak işten değildi ve unutulan taraf sessizce
 * hata dönerdi.
 *
 * Model adı sağlayıcıya bağlı. Şu an Google'ın OpenAI uyumlu ucu
 * kullanılıyor (`APP_AI_BASE_URL` sunucuda tanımlı).
 *
 * Neden `flash-lite`: denenen alternatifler arasında tek jeton israfı
 * yapmayanı buydu. `gemini-3.8-flash` ve `gemini-flash-latest` cevabı
 * yazmadan önce "düşünmeye" jeton harcıyor; birincisi kısa sınırda
 * tamamen boş cevap döndürdü. Bu bölümler kısa cevap istiyor, düşünme
 * bütçesi ödemeye değmiyor.
 */
export const AI_MODELI = 'gemini-3.1-flash-lite';
