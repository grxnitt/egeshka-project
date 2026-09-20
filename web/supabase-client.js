const config = window.EGESHKA_SUPABASE;

export async function applyLiveRatings(catalog) {
  catalog.schools.forEach(school => {
    school.editorialScore = Number(school.score);
    school.verifiedUserScore = null;
    school.verifiedReviewCount = 0;
    school.isPreliminary = true;
  });
  if (!config?.url || !config?.publishableKey) return catalog;
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 3500);
    const response = await fetch(`${config.url}/rest/v1/rating_snapshots?select=school_id,editorial_score,verified_user_score,verified_review_count,final_score,is_preliminary,calculated_at`, {
      headers: {apikey: config.publishableKey}, signal: controller.signal,
    });
    clearTimeout(timeout);
    if (!response.ok) throw new Error(`rating snapshots: ${response.status}`);
    const snapshots = new Map((await response.json()).map(item => [Number(item.school_id), item]));
    catalog.schools.forEach(school => {
      const snapshot = snapshots.get(Number(school.id));
      if (!snapshot) return;
      school.score = Number(snapshot.final_score);
      school.editorialScore = Number(snapshot.editorial_score);
      school.verifiedUserScore = snapshot.verified_user_score == null ? null : Number(snapshot.verified_user_score);
      school.verifiedReviewCount = Number(snapshot.verified_review_count || 0);
      school.isPreliminary = Boolean(snapshot.is_preliminary);
      school.ratingCalculatedAt = snapshot.calculated_at;
    });
  } catch (error) {
    console.warn('Используем резервные оценки из каталога:', error);
  }
  return catalog;
}

export const ratingMark = school => school.isPreliminary ? '*' : '';

export function ratingBreakdown(school) {
  if (school.isPreliminary || school.verifiedUserScore == null) {
    return '';
  }
  const editorial = Number(school.editorialScore).toFixed(1).replace('.', ',');
  const users = Number(school.verifiedUserScore).toFixed(1).replace('.', ',');
  return `<p class="rating-breakdown"><b>Из чего сложился балл</b><span>Редакция: ${editorial}/10 · Ученики: ${users}/5 · ${Number(school.verifiedReviewCount)} подтверждённых</span></p>`;
}
