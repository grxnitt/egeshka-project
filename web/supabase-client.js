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
