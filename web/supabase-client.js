const config = window.EGESHKA_SUPABASE;

export async function applyLiveRatings(catalog) {
  catalog.schools.forEach(school => {
    school.editorialScore = Number(school.score);
    school.verifiedUserScore = null;
    school.verifiedReviewCount = 0;
    school.isPreliminary = true;
  });
  catalog.teachers.forEach(teacher => {
    teacher.studentScore = null;
    teacher.verifiedReviewCount = 0;
    teacher.isPreliminary = true;
    teacher.criteria = {};
  });
  if (!config?.url || !config?.publishableKey) return catalog;
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 3500);
    const headers = {apikey: config.publishableKey};
    const [response, teacherResponse] = await Promise.all([
      fetch(`${config.url}/rest/v1/rating_snapshots?select=school_id,editorial_score,verified_user_score,verified_review_count,final_score,is_preliminary,calculated_at`, {headers, signal: controller.signal}),
      fetch(`${config.url}/rest/v1/teacher_rating_snapshots?select=teacher_id,verified_review_count,student_score,is_preliminary,explanation_score,practice_score,atmosphere_score,structure_score,exam_value_score,calculated_at`, {headers, signal: controller.signal}),
    ]);
    clearTimeout(timeout);
    if (!response.ok) throw new Error(`rating snapshots: ${response.status}`);
    if (!teacherResponse.ok) throw new Error(`teacher rating snapshots: ${teacherResponse.status}`);
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
    const teacherSnapshots = new Map((await teacherResponse.json()).map(item => [Number(item.teacher_id), item]));
    catalog.teachers.forEach(teacher => {
      const snapshot = teacherSnapshots.get(Number(teacher.id));
      if (!snapshot) return;
      teacher.studentScore = snapshot.student_score == null ? null : Number(snapshot.student_score);
      teacher.verifiedReviewCount = Number(snapshot.verified_review_count || 0);
      teacher.isPreliminary = Boolean(snapshot.is_preliminary);
      teacher.criteria = {
        explanation: snapshot.explanation_score == null ? null : Number(snapshot.explanation_score),
        practice: snapshot.practice_score == null ? null : Number(snapshot.practice_score),
        atmosphere: snapshot.atmosphere_score == null ? null : Number(snapshot.atmosphere_score),
        structure: snapshot.structure_score == null ? null : Number(snapshot.structure_score),
        exam_value: snapshot.exam_value_score == null ? null : Number(snapshot.exam_value_score),
      };
      teacher.ratingCalculatedAt = snapshot.calculated_at;
    });
  } catch (error) {
    console.warn('Используем резервные оценки из каталога:', error);
  }
  return catalog;
}

// Every approved review, individually — for the /reviews page. No personal data comes
// back from public_reviews at all (see its migration), so there is nothing to strip here.
export async function fetchPublicReviews() {
  if (!config?.url || !config?.publishableKey) return [];
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    const headers = {apikey: config.publishableKey};
    const response = await fetch(
      `${config.url}/rest/v1/public_reviews?select=id,school_id,teacher_id,criterion,criteria_json,score,text_positive,text_negative,verified,created_at&order=created_at.desc&limit=1000`,
      {headers, signal: controller.signal},
    );
    clearTimeout(timeout);
    if (!response.ok) throw new Error(`public reviews: ${response.status}`);
    return await response.json();
  } catch (error) {
    console.warn('Не удалось загрузить отзывы:', error);
    return [];
  }
}

// Bumps the view counter for an article and returns the new total. Falls back to
// reading the current count (without incrementing) if the write itself fails, so a
// transient error never shows a blank counter.
export async function incrementArticleView(slug) {
  if (!config?.url || !config?.publishableKey) return null;
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 4000);
    const response = await fetch(`${config.url}/rest/v1/rpc/increment_article_view`, {
      method: 'POST',
      headers: {apikey: config.publishableKey, 'Content-Type': 'application/json'},
      body: JSON.stringify({p_slug: slug}),
      signal: controller.signal,
    });
    clearTimeout(timeout);
    if (!response.ok) throw new Error(`increment_article_view: ${response.status}`);
    return await response.json();
  } catch (error) {
    console.warn('Не удалось обновить счётчик просмотров:', error);
    return fetchArticleViews(slug);
  }
}

// Read-only count, used when this browser already counted a view this session.
export async function fetchArticleViews(slug) {
  if (!config?.url || !config?.publishableKey) return null;
  try {
    const response = await fetch(
      `${config.url}/rest/v1/article_views?slug=eq.${encodeURIComponent(slug)}&select=views`,
      {headers: {apikey: config.publishableKey}},
    );
    if (!response.ok) return null;
    const [row] = await response.json();
    return row ? Number(row.views) : null;
  } catch {
    return null;
  }
}

// Read-only counts for several article cards at once — one request instead of
// one per card. Returns {slug: views}; missing/never-viewed slugs are just absent.
export async function fetchArticleViewsBatch(slugs) {
  if (!config?.url || !config?.publishableKey || !slugs.length) return {};
  try {
    const list = slugs.map(encodeURIComponent).join(',');
    const response = await fetch(
      `${config.url}/rest/v1/article_views?slug=in.(${list})&select=slug,views`,
      {headers: {apikey: config.publishableKey}},
    );
    if (!response.ok) return {};
    const rows = await response.json();
    return Object.fromEntries(rows.map(row => [row.slug, Number(row.views)]));
  } catch {
    return {};
  }
}

export const teacherRatingLabel = teacher => teacher.studentScore == null ? 'Оценка формируется' : `${Number(teacher.studentScore).toFixed(1).replace('.', ',')}/10${teacher.isPreliminary?'*':''}`;

export const ratingMark = school => school.isPreliminary ? '*' : '';

export function ratingBreakdown(school) {
  if (school.isPreliminary || school.verifiedUserScore == null) {
    return '';
  }
  const editorial = Number(school.editorialScore).toFixed(1).replace('.', ',');
  const users = Number(school.verifiedUserScore).toFixed(1).replace('.', ',');
  return `<p class="rating-breakdown"><b>Из чего сложился балл</b><span>Редакция: ${editorial}/10 · Ученики: ${users}/10 · ${Number(school.verifiedReviewCount)} подтверждённых</span></p>`;
}
