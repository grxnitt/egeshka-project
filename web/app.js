import { applyLiveRatings } from './supabase-client.js?v=7';
import { chooseSchoolUrl, schoolContent, schoolFilters, schoolLogos } from './school-content.js?v=41';
const $ = (selector) => document.querySelector(selector);
const escape = (value) => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number = n => Number(n).toFixed(1).replace('.', ',');
const criteria = {teachers_score:'Преподаватели',practice_score:'Практика и ДЗ',feedback_score:'Проверка работ',curator_score:'Кураторы',platform_score:'Платформа',workload_score:'Нагрузка и темп',organization_score:'Организация обучения'};
import { labels, quizSubjectKeys, teacherSubjects } from './subjects.js?v=1';
const dialog = $('#detail-dialog');
let catalog, links = {bot:'https://t.me/egematch_bot', channel:'https://t.me/EgeMatch_blog'};
// Started right away so the quiz can wait for it on a slow connection instead of failing.
const catalogReady = fetch('catalog.json?v=4').then(response => { if (!response.ok) throw new Error('catalog'); return response.json(); }).then(async data => { await applyLiveRatings(data); catalog = data; });
catalogReady.catch(() => {});
function showDialog(html){ $('#dialog-content').innerHTML = html; dialog.showModal();document.querySelector("#dialog-content").scrollTop=0; }
$('.close').onclick = () => dialog.close();
dialog.addEventListener('click', e => { if(e.target === dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close();} });
const siteQuiz={step:0,answers:{},suggestedPriorities:[]};
const PRIORITY_LABELS={teacher:'Сильные преподаватели',practice:'Практика и домашние задания',curator:'Куратор и поддержка',platform:'Удобная платформа',price:'Доступная цена'};
const quizSteps=[
 {key:'subject',questionNumber:1,title:'Какой предмет сдаёшь?',options:()=>[...quizSubjectKeys.slice(0,2),'математика базовая',...quizSubjectKeys.slice(2,-1)].map(value=>[labels[value],value])},
 {key:'budget',questionNumber:2,title:'Сколько готов тратить на подготовку в месяц?',options:()=>[['До 3 000 ₽','3000'],['3 000–5 000 ₽','5000'],['5 000–8 000 ₽','8000'],['Больше 8 000 ₽','12000'],['Пока не определился','0']]},
 {key:'format',questionNumber:3,title:'Как тебе удобнее заниматься?',options:()=>[['Вживую с преподавателем — эфиры и вопросы в чате','live'],['В записи, в своём темпе','recorded'],['Один на один с репетитором','individual'],['Не важно, главное — результат','any']]},
 {key:'goal',questionNumber:4,title:'Где ты сейчас и на какой результат идёшь?',pair:true,options:()=>[]},
 {key:'support',questionNumber:5,title:'Сколько сопровождения тебе нужно?',options:()=>[['Справлюсь сам — главное материалы','1'],['Иногда хочу задать вопрос куратору','2'],['Нужны регулярные проверки и дедлайны','3'],['Без жёсткого контроля я всё откладываю','4']]},
 {key:'workload',questionNumber:6,title:'Какой темп подготовки тебе подходит?',options:()=>[['Небольшая нагрузка, без перегруза','1'],['Умеренный темп','2'],['Готов заниматься много','3'],['Максимум практики ради результата','4']]},
 {key:'teacher',questionNumber:7,title:'Насколько важен сильный преподаватель именно по твоему предмету?',options:()=>[['Решающий фактор — хочу лучшего','3'],['Важен, но не главное','2'],['Не принципиально, важнее система','1']]},
 {key:'priority1',questionNumber:8,title:'Что ещё для тебя важнее всего?',options:()=>Object.entries(PRIORITY_LABELS).map(([value,label])=>[label,value])},
];
// Question 4 is two independent choices on one screen: current level and target score (any pair, e.g. "с нуля" -> 90+).
const GOAL_LEVELS=[['Почти с нуля','low'],['Что-то знаю','middle'],['База хорошая','high']];
const goalTargets=()=>siteQuiz.answers.subject==='математика базовая'?[['Сдать на 3','3'],['На 4','4'],['На 5','5']]:[['Просто сдать','60'],['70+','70'],['80+','80'],['90+','90']];
// A big jump from the current level to the target: practice and checked work matter more, and the result warns about pace.
const bigGap=a=>a.subject==='математика базовая'?a.level==='low'&&a.target==='5':(a.level==='low'&&Number(a.target)>=80)||(a.level==='middle'&&a.target==='90');
function goalStep(step){const a=siteQuiz.answers,row=(name,items,current)=>`<div class="quiz-pair-row"><p>${name}</p><div class="quiz-chips" role="radiogroup" aria-label="${name}">${items.map(([label,value])=>`<button type="button" role="radio" aria-checked="${current===value}" class="quiz-chip${current===value?' is-on':''}" data-pair="${name==='Сейчас'?'level':'target'}" data-value="${escape(value)}">${escape(label)}</button>`).join('')}</div></div>`;
 const targets=goalTargets().map(([,v])=>v);if(a.target&&!targets.includes(a.target))delete a.target;
 return `<div class="quiz-pair">${row('Сейчас',GOAL_LEVELS,a.level)}${row('Цель',goalTargets(),a.target)}<button type="button" class="button blue quiz-pair-next"${a.level&&a.target?'':' disabled'}>Дальше <span>→</span></button></div>`;}
const QUIZ_TOTAL=quizSteps.filter(step=>step.questionNumber).length;
const FORMAT_LABELS={live:'живые занятия',recorded:'занятия в записи',individual:'занятия один на один'};
const FORMAT_MISSING={live:'живых занятий',recorded:'занятий в записи',individual:'занятий один на один'};

// ---- Quiz matching ----------------------------------------------------------------------------
// 1. Each criterion starts at its methodology weight (BASE_WEIGHTS). Answers only multiply that weight
//    by an importance factor (IMPORTANCE table below), so every answer's effect is one readable line.
// 2. A school is judged on each criterion relative to the other schools (percentile 0..1), not on the raw
//    7.5-9 score where everyone looks alike: "кураторы лучше 80% школ" is what actually separates them.
// 3. Hard conditions (format, budget, a needed service that is missing) subtract fixed percentage points
//    and are always shown under "Учти", instead of being blended into the weights.
const BASE_WEIGHTS={teachers_score:.20,practice_score:.16,feedback_score:.14,curator_score:.14,platform_score:.14,workload_score:.08,organization_score:.14};
const PRIORITY_TO_FIELD={teacher:'teachers_score',practice:'practice_score',curator:'curator_score',platform:'platform_score'};
// answer -> {criterion: multiplier}. Multipliers from several answers multiply, capped at x4.
const IMPORTANCE={
 support:{'1':{curator_score:.5},'3':{curator_score:2,feedback_score:2,organization_score:1.5},'4':{curator_score:3,feedback_score:3,organization_score:2}},
 level:{low:{curator_score:1.5,feedback_score:1.5,platform_score:1.5},high:{teachers_score:1.5,practice_score:1.5}},
 target:{'90':{teachers_score:1.5,practice_score:1.5},'5':{teachers_score:1.3,practice_score:1.3}},
 workload:{'1':{workload_score:2},'4':{practice_score:1.5}},
 teacher:{'1':{teachers_score:.7},'2':{teachers_score:1.5},'3':{teachers_score:3}},
 gap:{'1':{practice_score:1.3,feedback_score:1.3}},
};
const PRIORITY_MULTIPLIER=2;
function importanceOf(a){const m=Object.fromEntries(Object.keys(BASE_WEIGHTS).map(key=>[key,1]));const apply=table=>Object.entries(table||{}).forEach(([key,f])=>{m[key]*=f;});
 const answers={...a,gap:bigGap(a)?'1':'0'};Object.entries(IMPORTANCE).forEach(([answer,table])=>apply(table[answers[answer]]));
 [a.priority1,a.priority2].forEach(p=>{if(PRIORITY_TO_FIELD[p])m[PRIORITY_TO_FIELD[p]]*=PRIORITY_MULTIPLIER;});
 Object.keys(m).forEach(key=>{m[key]=Math.min(4,m[key]);});return m;}
// Kept for ratings.js links and the bot payload: does the student need this service at all.
const chosen=(a,name)=>[a.priority1,a.priority2].includes(name);
const NEEDS={curator_score:a=>Number(a.curator)>=3||chosen(a,'curator'),feedback_score:a=>Number(a.control)>=3,platform_score:a=>chosen(a,'platform'),practice_score:a=>chosen(a,'practice')};
const NEED_REASONS={curator_score:{none:'нет куратора, а он тебе нужен',tier:'куратор — только на старших тарифах'},feedback_score:{none:'нет проверки работ, а она тебе нужна',tier:'проверка работ — не на всех тарифах'},platform_score:{none:'нет платформы, а она тебе важна',tier:'платформа — не на всех тарифах'},practice_score:{none:'нет практики, а она тебе важна',tier:'практика — не на всех тарифах'}};
// Fixed costs in percentage points, so the trade-off is the same for every school.
const PENALTY={formatMissing:35,recordedMissing:12,formatUnsure:6,needNone:15,needTier:5,overBudgetMax:40,priceUnknown:3};
// Best student-reviewed rating (needs 3+ reviews) among this school's teachers for the quiz's
// subject, if any — mirrors best_subject_teacher_scores() in egeshka_bot/bot.py.
function subjectTeacherScore(school,a){const subjectLabel=labels[a.subject];if(!subjectLabel||!catalog?.teachers)return null;const rated=catalog.teachers.filter(t=>t.school===school.name&&teacherSubjects(t).includes(subjectLabel)&&t.studentScore!=null).map(t=>Number(t.studentScore));return rated.length?Math.max(...rated):null;}
// A criterion the school does not offer ("none") is left out of its match entirely.
const offeredKeys=school=>Object.keys(BASE_WEIGHTS).filter(key=>school.criteriaStatus?.[key]!=='none');
// Position of a value among catalog schools that offer the criterion (mirrors _position in scoring.py).
// percentile: share of schools it beats (ties count half) - for "лучше N% школ".
// score: half percentile, half place on the min..max scale, so 8.7 vs 8.9 stays close.
let percentileCache=null;
function position(key,value){if(!percentileCache||percentileCache.catalog!==catalog){percentileCache={catalog,values:{}};}
 const values=percentileCache.values[key]||(percentileCache.values[key]=catalog.schools.filter(s=>s.criteriaStatus?.[key]!=='none'&&s.criteria[key]!=null).map(s=>Number(s.criteria[key])));
 if(values.length<2)return {percentile:.5,score:.5};let below=0,equal=0;values.forEach(v=>{if(v<value-1e-9)below++;else if(Math.abs(v-value)<1e-9)equal++;});
 const p=(below+equal/2)/values.length,low=Math.min(...values),high=Math.max(...values),scale=high-low<1e-9?.5:Math.min(1,Math.max(0,(value-low)/(high-low)));
 return {percentile:p,score:(p+scale)/2};}
// A rated teacher for the chosen subject moves the match by bounded points (mirrors SUBJECT_TEACHER in scoring.py).
const SUBJECT_TEACHER={perPoint:4,min:-6,max:8,need:{'1':.5,'2':1,'3':1.5}};
const FACTOR_LABELS={teachers_score:'преподаватели',practice_score:'практика',feedback_score:'проверка работ',curator_score:'кураторы',platform_score:'платформа',workload_score:'нагрузка',organization_score:'организация',subject_teacher:'препод по предмету',format:'формат занятий',budget:'бюджет',needs:'нужные услуги'};
function subjectTeacherPoints(subjectScore,schoolTeachers,a){if(subjectScore==null)return 0;const raw=Math.max(SUBJECT_TEACHER.min,Math.min(SUBJECT_TEACHER.max,(subjectScore-schoolTeachers)*SUBJECT_TEACHER.perPoint));return Math.round(raw*(SUBJECT_TEACHER.need[a.teacher||'2']??1)*10)/10;}
// Months of payments left until the exam, counting the current one (mirrors months_to_exam in scoring.py).
function monthsToExam(today=new Date()){const m=today.getMonth()+1,examYear=m>=7?today.getFullYear()+1:today.getFullYear();return Math.max(1,(examYear-today.getFullYear())*12+5-m+1);}
function needPenalty(school,a){let points=0;const reasons=[];for(const [key,needed] of Object.entries(NEEDS)){const status=school.criteriaStatus?.[key]||'yes';if(status!=='yes'&&needed(a)){points+=status==='none'?PENALTY.needNone:PENALTY.needTier;reasons.push(NEED_REASONS[key][status]);}}return {points,reasons};}
// Over budget costs up to 40 points (50 points per 100% over: 10% over = -5, 80% over = -40). With "Цена" as a priority
// a cheaper school earns up to PRICE_BONUS_MAX points against the budget, or without one against the median price.
const PRICE_BONUS_MAX=20;
// "Ещё подходят": places 4-6 under the top three, only if they still fit reasonably (mirrors MORE_MIN_SCORE in bot.py).
const MORE_MIN_SCORE=40;
function medianPrice(){const p=catalog.schools.map(s=>Number(s.monthlyPriceFrom||0)).filter(v=>v>0).sort((x,y)=>x-y);if(!p.length)return 0;const m=Math.floor(p.length/2);return p.length%2?p[m]:(p[m-1]+p[m])/2;}
function budgetFit(school,a){if(a.subject==='математика базовая')return {points:0};const wantsCheap=chosen(a,'price'),price=Number(school.monthlyPriceFrom||0);
 if(!a.budget||a.budget==='0'){const ref=wantsCheap?medianPrice():0;if(ref&&price>0&&price<ref)return {points:Math.round(PRICE_BONUS_MAX*(1-price/ref)*10)/10,pro:'дешевле большинства школ'};return {points:0};}
 if(price<=0)return {points:-PENALTY.priceUnknown,con:'цена не опубликована — уточни у школы'};const budget=Number(a.budget);
 if(price<=budget){const bonus=wantsCheap?Math.round(PRICE_BONUS_MAX*(1-price/budget)*10)/10:0;return {points:bonus,pro:'входит в бюджет'};}
 return {points:-Math.min(PENALTY.overBudgetMax,(price-budget)/budget*50),con:'может быть выше бюджета'};}
// The format a student asked for is close to a deal-breaker (less so for recordings, which most schools
// add on top of live lessons anyway). Unconfirmed formats cost a little and say so.
function formatFit(school,a){const format=a.format;if(!format||format==='any')return {points:0};const lessons=schoolFilters[school.name]?.lessons||[],unsure=schoolFilters[school.name]?.unsure||[];if(lessons.includes(format))return {points:0,pro:`есть ${FORMAT_LABELS[format]}`};if(unsure.includes(format))return {points:-PENALTY.formatUnsure,con:`${FORMAT_LABELS[format]} не подтверждены — уточни у школы`};return {points:-(format==='recorded'?PENALTY.recordedMissing:PENALTY.formatMissing),con:`нет ${FORMAT_MISSING[format]}`};}
function matchSchool(school,a){if(!school.subjects.includes(a.subject))return null;const keys=offeredKeys(school),importance=importanceOf(a);
 const subjectTeacher=subjectTeacherScore(school,a),teachersValue=Number(school.criteria.teachers_score||0);const pros=[],cons=[],factors={};let teacherPoints=0;
 if(subjectTeacher!=null&&keys.includes('teachers_score')){if(subjectTeacher>=teachersValue+.5)pros.push(`сильный препод именно по этому предмету (${number(subjectTeacher)})`);else if(subjectTeacher<=teachersValue-1)cons.push(`по этому предмету отзывы ниже, чем в среднем по школе (${number(subjectTeacher)})`);teacherPoints=subjectTeacherPoints(subjectTeacher,teachersValue,a);}
 const weights=Object.fromEntries(keys.map(key=>[key,BASE_WEIGHTS[key]*importance[key]]));const weightSum=Object.values(weights).reduce((x,y)=>x+y,0);const ranked=[];
 keys.forEach(key=>{const pos=position(key,Number(school.criteria[key]||0));factors[key]=weightSum?weights[key]/weightSum*(pos.score-.5)*100:0;if(importance[key]>=1.5)ranked.push({key,p:pos.percentile,importance:importance[key]});});
 const ff=formatFit(school,a),bf=budgetFit(school,a),need=needPenalty(school,a);
 Object.assign(factors,{subject_teacher:teacherPoints,format:ff.points,budget:bf.points,needs:-need.points});
 if(ff.pro)pros.push(ff.pro);if(ff.con)cons.push(ff.con);if(bf.pro)pros.push(bf.pro);if(bf.con)cons.push(bf.con);cons.push(...need.reasons);
 ranked.sort((x,y)=>y.importance-x.importance).forEach(({key,p})=>{const name=criteria[key].toLowerCase();if(p>=.7)pros.push(`${name} — лучше ${Math.round(p*100)}% школ`);else if(p<=.3)cons.push(`${name} — слабее большинства школ`);});
 if(!pros.length)pros.push('ровное совпадение по всем критериям');
 const percent=50+Object.values(factors).reduce((x,y)=>x+y,0);
 const shown=Object.entries(factors).filter(([,v])=>Math.abs(v)>=1.5).map(([k,v])=>[FACTOR_LABELS[k],Math.round(v)]).sort((x,y)=>Math.abs(y[1])-Math.abs(x[1])).slice(0,3);
 return {score:Math.round(Math.max(5,Math.min(97,percent))*10)/10,pros:pros.slice(0,3),cons:cons.slice(0,2),factors:shown,teachers:teachersValue+teacherPoints/10,price:Number(school.monthlyPriceFrom||0)};}
// "Подбор помог?" goes to analytics only; a "no" asks for one reason so weights can be tuned on real answers.
function bindQuizFeedback(a){const box=document.querySelector('[data-quiz-feedback]');if(!box)return;const send=(useful,reason)=>{try{window.egeTrack&&window.egeTrack('quiz_feedback',{useful,reason:reason||'',subject:a.subject})}catch{}box.innerHTML='<span>Спасибо, это поможет сделать подбор точнее.</span>';};
 box.onclick=event=>{const b=event.target.closest('button');if(!b)return;if(b.dataset.fb==='yes')return send('yes');if(b.dataset.fb==='no'){box.innerHTML='<span>Что не так?</span>'+['Дорого','Не тот формат','Не знаю эти школы','Ждал другую школу','Другое'].map(r=>`<button type="button" data-reason="${r}">${r}</button>`).join('');return;}if(b.dataset.reason)send('no',b.dataset.reason);};}
// Short chip texts for the result cards: a school pupil should get it at a glance.
const SHORT_REASONS={'преподаватели':'сильные преподаватели','практика и дз':'много практики','проверка работ':'сильная проверка работ','кураторы':'сильные кураторы','платформа':'удобная платформа','нагрузка и темп':'комфортный темп','организация обучения':'чёткая организация'};
function shortReason(text){const m=text.match(/^(.+?) — лучше \d+% школ$/);if(m)return SHORT_REASONS[m[1]]||m[1];const weak=text.match(/^(.+?) — слабее большинства школ$/);if(weak)return `${weak[1]} слабее многих`;
 return text.replace('входит в бюджет','в бюджете').replace('может быть выше бюджета','дороже твоего бюджета').replace('дешевле большинства школ','дешевле многих').replace(/^есть /,'').replace(/сильный препод именно по этому предмету.*/,'сильный препод по предмету').replace(/ — уточни у школы$/,'');}
// Home "how it works": the mini leaderboard and the VS cards show the real top schools.
function renderHowArt(){if(!catalog)return;const top=[...catalog.schools].filter(s=>s.subjects.length>=5).sort((a,b)=>b.score-a.score).slice(0,3);
 const logo=s=>`<span class="at-logo">${schoolLogos[s.name]?`<img src="/${escape(schoolLogos[s.name])}" alt="">`:`<b>${escape(s.name.slice(0,1))}</b>`}</span>`;
 const rows=$('#how-top-rows');if(rows&&top.length)rows.innerHTML=top.map((s,i)=>`<div class="at-row${i?'':' is-first'}"><b>${i+1}</b>${logo(s)}<span class="at-name">${escape(s.name)}</span><i><u style="width:${Math.round(s.score*10)}%"></u></i><em>${number(s.score)}</em></div>`).join('');
 [['#how-vs-a',top[0]],['#how-vs-b',top[1]]].forEach(([sel,s])=>{const el=$(sel);if(!el||!s)return;el.querySelector('.at-logo').outerHTML=logo(s);el.querySelector(':scope>b').textContent=s.name;const c=s.criteria||{};[c.teachers_score,c.practice_score].forEach((v,i)=>{const row=el.querySelectorAll('.av-row')[i];if(!row||!(v>0))return;row.querySelector('em').textContent=number(v);row.querySelector('u').style.width=`${Math.round(v*10)}%`;});});
 document.querySelectorAll('.how-art img').forEach(img=>img.addEventListener('error',()=>img.remove(),{once:true}));}
// Home: top three schools, same order as the ratings page with no subject chosen (broad schools first).
function renderHomeTop(){const list=$('#home-top-list');if(!list||!catalog)return;
 const top=[...catalog.schools].filter(s=>s.subjects.length>=5).sort((a,b)=>b.score-a.score).slice(0,3);
 const price=s=>Number(s.monthlyPriceFrom)>0?`от ${Number(s.monthlyPriceFrom).toLocaleString('ru-RU')} ₽/мес`:'цена у школы';
 list.innerHTML=top.map((s,i)=>`<a class="home-top-card" href="/schools/${escape(s.reviewSlug)}"><div class="home-top-head"><span class="school-mark school-mark-logo ${i%2?'pink-mark':'blue-mark'}"><b>${escape(s.name.slice(0,1))}</b>${schoolLogos[s.name]?`<img src="${escape(schoolLogos[s.name])}" alt="" aria-hidden="true">`:''}</span><span class="home-top-place">${i+1} место</span></div><h3>${escape(s.name)}</h3><p class="home-top-fit">${escape(schoolContent[s.name]?.fit||s.description)}</p><div class="home-top-meta"><span>${escape(price(s))}</span><strong class="home-top-score">${number(s.score)}<small>/10</small></strong></div><span class="home-top-more">Подробнее о школе <span aria-hidden="true">→</span></span></a>`).join('');
 list.removeAttribute('aria-busy');
 list.querySelectorAll('img').forEach(img=>img.addEventListener('error',()=>img.remove(),{once:true}));}
// One label per card so three results read as three different choices, not three copies of "fits".
function matchBadge(top,item,index){if(index===0)return 'Лучшее совпадение';const priced=top.filter(x=>x.match.price>0);const cheapest=priced.length?priced.reduce((x,y)=>y.match.price<x.match.price?y:x):null;if(cheapest===item&&cheapest.match.price<(top[0].match.price||Infinity))return 'Выгоднее по цене';const strongest=top.reduce((x,y)=>y.match.teachers>x.match.teachers?y:x);if(strongest===item&&item.match.teachers>top[0].match.teachers)return 'Сильнее преподаватели';return '';}
const shortPrice=value=>value.length>118?`${value.slice(0,115).trim()}…`:value;
const schoolCardUrl=name=>{const target=catalog.schools.find(item=>item.name===name);return target?`/schools/${target.reviewSlug}?from=quiz`:'/ratings';};
// Bot deep link: the original nine fields plus lesson format and teacher importance
// (egeshka_bot/bot.py profile_from_payload still accepts old nine-field links).
function quizPayload(a){const subjectIndex=quizSubjectKeys.indexOf(a.subject);return `q_${subjectIndex}_${a.budget}_${a.level}_${a.target}_${a.curator}_${a.workload}_${a.priority1||'none'}_none_${a.control}_${a.format||'any'}_${a.teacher||'2'}`;}
let quizRun=0;
// "Считаем совпадения": a short calculation screen before the result. It also covers a slow catalog:
// if the data has not arrived when the animation ends, the screen waits for it (up to 20 s).
function runQuizCalculation(){
  const run=quizRun,reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
  const stages=['Сверяем ответы с оценками школ','Учитываем бюджет и формат','Взвешиваем твои приоритеты','Собираем лучшие совпадения'];
  const stageStart=[0,3,5,8],segments=10,tick=reduced?110:300;
  showDialog(`<div class="quiz-calc"><div class="quiz-calc-orbit" aria-hidden="true"><i class="a"></i><i class="b"></i><i class="ring"></i></div><h2>Считаем совпадения</h2><span class="quiz-calc-meter" aria-hidden="true">${'<i></i>'.repeat(segments)}</span><ul class="quiz-calc-list" aria-hidden="true">${stages.map(text=>`<li>${text}</li>`).join('')}</ul><p class="quiz-calc-wait" hidden>Данные школ ещё загружаются — это займёт пару секунд.</p><p class="quiz-calc-sr" role="status">${stages[0]}</p></div>`);
  const root=document.querySelector('.quiz-calc'),bars=[...root.querySelectorAll('.quiz-calc-meter i')],items=[...root.querySelectorAll('.quiz-calc-list li')],status=root.querySelector('.quiz-calc-sr');
  const alive=()=>run===quizRun&&dialog.open;
  const mark=stage=>items.forEach((item,i)=>{item.className=stage>=items.length||i<stage?'is-done':i===stage?'is-active':'';});
  const finish=async()=>{
    mark(items.length);
    if(!catalog){root.querySelector('.quiz-calc-wait').hidden=false;status.textContent='Ждём данные школ';try{await Promise.race([catalogReady,new Promise((_,reject)=>setTimeout(()=>reject(new Error('timeout')),20000))]);}catch{}}
    await new Promise(resolve=>setTimeout(resolve,reduced?0:380));
    if(alive())renderQuizResult();
  };
  let filled=0;mark(0);
  const timer=setInterval(()=>{
    if(!alive()){clearInterval(timer);return;}
    bars[filled++].classList.add('on');
    let stage=0;stageStart.forEach((start,i)=>{if(filled>=start)stage=i;});
    if(filled<segments){mark(stage);status.textContent=stages[stage];}
    else{clearInterval(timer);finish();}
  },tick);
}
function ratingsUrl(a){const params=new URLSearchParams({subject:a.subject});if(a.budget&&a.budget!=='0')params.set('budget',a.budget);if(NEEDS.curator_score(a))params.set('curator','1');const priorities=[a.priority1,a.priority2].filter(value=>value&&value!=='price'&&value!=='none');if(priorities.length)params.set('priority',priorities.join(','));return `/ratings?${params.toString()}`;}
function renderQuizResult(){if(!catalog){showDialog('<div class="quiz-result"><h2>Не удалось загрузить каталог школ</h2><p>Проверь соединение и обнови страницу, чтобы пройти подбор заново — ответы вводить не придётся долго, вопросов немного.</p><div class="quiz-result-actions"><button type="button" class="quiz-edit">Начать заново</button></div></div>');document.querySelector('.quiz-edit').onclick=()=>{siteQuiz.step=0;renderSiteQuiz();};return;}try{sessionStorage.setItem('egeshka-quiz',JSON.stringify(siteQuiz.answers));}catch{} const a=siteQuiz.answers;const ranked=catalog.schools.map(school=>({school,match:matchSchool(school,a)})).filter(x=>x.match).sort((x,y)=>y.match.score-x.match.score);const top=ranked.slice(0,3);const more=ranked.slice(3,6).filter(x=>x.match.score>=MORE_MIN_SCORE);try{window.egeTrack&&window.egeTrack('quiz_complete',{subject:a.subject,results:top.length})}catch{} const compareUrl=top.length>=2?`/compare?${new URLSearchParams({compareLeft:top[0].school.name,compareRight:top[1].school.name})}`:null;
 const levelLabel=(GOAL_LEVELS.find(([,v])=>v===a.level)||[''])[0],targetLabel=(goalTargets().find(([,v])=>v===a.target)||[''])[0];
 const recap=[labels[a.subject],levelLabel&&targetLabel?`${levelLabel.toLowerCase()} → ${targetLabel}`:'',a.budget&&a.budget!=='0'?`до ${Number(a.budget).toLocaleString('ru-RU')} ₽`:''].filter(Boolean).join(' · ');
 const gapNote=bigGap(a)?`<p class="qr-note">До ${escape(targetLabel)} с твоего уровня — реально, но нужен плотный график. Мы уже подняли школы с практикой и проверкой работ.</p>`:'';
 const price=school=>a.subject==='математика базовая'?'цена уточняется':Number(school.monthlyPriceFrom)>0?`от ${Number(school.monthlyPriceFrom).toLocaleString('ru-RU')} ₽/мес`:'цену уточни у школы';
 const cards=top.map((item,index)=>{const {school,match}=item;const badge=(index?matchBadge(top,item,index):'').toLowerCase();const topic=badge.includes('преподав')?'преподав':badge.includes('цен')?'бюджет':'';const tags=[badge,...match.pros.map(shortReason).filter(t=>!topic||!t.includes(topic))].filter(Boolean).filter((t,k,arr)=>arr.indexOf(t)===k).slice(0,2);
  return `<li class="qr-card${index?'':' is-first'}">${index?'':'<span class="qr-best">Лучшее совпадение</span>'}<div class="qr-top"><span class="qr-place">${index+1}</span><a class="qr-name" href="${escape(schoolCardUrl(school.name))}">${escape(school.name)}</a><b class="qr-pct">${Math.round(match.score)}%</b></div>${tags.length?`<div class="qr-tags">${tags.map((t,k)=>`<span${k===0&&badge?' class="is-accent"':''}>${escape(t)}</span>`).join('')}</div>`:''}${match.cons.length?`<p class="qr-warn">${escape(shortReason(match.cons[0]))}</p>`:''}<div class="qr-bottom"><span class="qr-price">${escape(price(school))}</span><a class="qr-about" href="${escape(schoolCardUrl(school.name))}">О школе</a><a class="qr-choose" href="${escape(chooseSchoolUrl(school))}" target="_blank" rel="noopener" data-choose-school="${escape(school.name)}" data-source="quiz_result">Выбрать школу <span aria-hidden="true">→</span></a></div></li>`;}).join('');
 const moreBlock=more.length?`<details class="qr-more"><summary>Ещё ${more.length} ${more.length===1?'школа':'школы'}</summary><ul>${more.map(({school,match})=>`<li><a href="${escape(schoolCardUrl(school.name))}"><span>${escape(school.name)}</span><b>${Math.round(match.score)}%</b></a></li>`).join('')}</ul></details>`:'';
 showDialog(`<div class="quiz-result qr"><h2>${top.length?'Твои школы':'Пока пусто'}</h2><p class="qr-recap">${escape(recap)}</p>${top.length?'':'<p class="qr-empty">По этому предмету подходящих школ пока нет. Попробуй другой предмет.</p>'}${gapNote}<ol class="qr-list">${cards}</ol>${moreBlock}<div class="qr-actions">${compareUrl?`<a href="${escape(compareUrl)}">Сравнить топ-2</a>`:''}<a href="${escape(links.bot)}?start=${quizPayload(a)}" target="_blank" rel="noopener">Курсы в боте</a><a href="${escape(ratingsUrl(a))}">Все в рейтинге</a><button type="button" class="quiz-edit">Изменить ответы</button></div><p class="qr-hint">% — насколько школа подходит именно тебе, а не место в рейтинге.</p><div class="quiz-feedback" data-quiz-feedback><span>Подбор помог?</span><button type="button" data-fb="yes">Да</button><button type="button" data-fb="no">Не очень</button></div></div>`);document.querySelector('.quiz-edit').onclick=()=>{siteQuiz.step=0;renderSiteQuiz();};bindQuizFeedback(a);return;}
function renderSiteQuiz(options={}){quizRun++;const step=quizSteps[siteQuiz.step];if(!step)return options.instant?renderQuizResult():runQuizCalculation();const progressLabel=step.questionNumber?`Вопрос ${step.questionNumber} из ${QUIZ_TOTAL}`:step.title;const heading=step.questionNumber?step.title:step.subtitle;showDialog(`<div class="site-quiz"><div class="quiz-progress"><span>${escape(progressLabel)}</span><i><b style="width:${(siteQuiz.step+1)/quizSteps.length*100}%"></b></i></div><h2>${escape(heading)}</h2>${step.pair?goalStep(step):''}<div class="quiz-options"${step.pair?' hidden':''}>${step.options().map(([label,value])=>{const suggested=(step.key==='priority1'||step.key==='priority2')&&siteQuiz.suggestedPriorities.includes(value);return `<button data-quiz-value="${escape(value)}" class="${suggested?'is-suggested':''}"><span class="quiz-option-label">${escape(label)}${suggested?'<em>По твоим фильтрам</em>':''}</span><span class="quiz-option-arrow">→</span></button>`;}).join('')}</div>${siteQuiz.step?'<button class="quiz-back">← Назад</button>':''}</div>`);document.querySelectorAll('[data-quiz-value]').forEach(button=>button.onclick=()=>{const value=button.dataset.quizValue;siteQuiz.answers[step.key]=value;if(step.key==='support'){siteQuiz.answers.curator=value;siteQuiz.answers.control=value;}siteQuiz.step++;renderSiteQuiz();});if(step.pair){document.querySelectorAll('[data-pair]').forEach(chip=>chip.onclick=()=>{const field=chip.dataset.pair;siteQuiz.answers[field]=chip.dataset.value;siteQuiz.answers.goal=`${siteQuiz.answers.level||''}|${siteQuiz.answers.target||''}`;document.querySelectorAll(`[data-pair="${field}"]`).forEach(other=>{const on=other===chip;other.classList.toggle('is-on',on);other.setAttribute('aria-checked',on);});$('.quiz-pair-next').disabled=!(siteQuiz.answers.level&&siteQuiz.answers.target);});$('.quiz-pair-next').onclick=()=>{siteQuiz.step++;renderSiteQuiz();};}const back=$('.quiz-back');if(back)back.onclick=()=>{siteQuiz.step--;renderSiteQuiz();};}
// Subject/budget can arrive pre-answered from the ratings filters (see ratings.js
// syncQuizLink): skip the leading questions the visitor already answered there.
function startQuiz(preset={}){
  siteQuiz.answers={};
  siteQuiz.step=0;
  siteQuiz.suggestedPriorities=String(preset.priority||'').split(',').filter(key=>PRIORITY_LABELS[key]);
  if(quizSubjectKeys.includes(preset.subject)){
    siteQuiz.answers.subject=preset.subject;
    siteQuiz.step=1;
    if(['0','3000','5000','8000','12000'].includes(preset.budget)){
      siteQuiz.answers.budget=preset.budget;
      siteQuiz.step=2;
    }
  }
  renderSiteQuiz();
}
$('#quiz-start').onclick=()=>startQuiz();
// Step 3 of "how it works" opens the quiz in place; without JS the link reloads the page with ?start=quiz.
document.querySelectorAll('[data-quiz-link]').forEach(link=>link.addEventListener('click',event=>{event.preventDefault();$('#quiz-start').click();}));
const applyLinks=()=>{$('#channel-link').href=links.channel;$('#review-link').href=links.bot;document.querySelectorAll('[data-bot-link]').forEach(link=>{link.href=links.bot;});};
applyLinks();
try{
 await catalogReady;
 renderHomeTop();renderHowArt();
 {const facts=document.querySelector('[data-fact="schools"]');if(facts&&catalog)facts.textContent=catalog.schools.length;const people=document.querySelector('[data-fact="teachers"]');if(people&&catalog)people.textContent=`${Math.floor(catalog.teachers.length/10)*10}+`;}
 try{const fresh=await fetch('links.json');if(fresh.ok){links=await fresh.json();applyLinks();}}catch{}
 if(new URLSearchParams(location.search).get('resume')==='quiz'){
  let saved=null;try{saved=JSON.parse(sessionStorage.getItem('egeshka-quiz'));}catch{}
  const targets=saved?.subject==='математика базовая'?['3','4','5']:['60','70','80','90'];
  const validPriority=value=>!value||Object.keys(PRIORITY_LABELS).includes(value);
  if(saved&&quizSubjectKeys.includes(saved.subject)&&['0','3000','5000','8000','12000'].includes(saved.budget)&&['low','middle','high'].includes(saved.level)&&targets.includes(saved.target)&&['live','recorded','individual','any'].includes(saved.format)&&['1','2','3','4'].includes(saved.support)&&['1','2','3','4'].includes(saved.curator)&&['1','2','3','4'].includes(saved.workload)&&['1','2','3'].includes(saved.teacher)&&validPriority(saved.priority1)&&validPriority(saved.priority2)&&['1','2','3','4'].includes(saved.control)){siteQuiz.answers=saved;siteQuiz.step=quizSteps.length;renderSiteQuiz({instant:true});}
  else $('#quiz-start').click();
 }
 const startParams=new URLSearchParams(location.search);
 if(startParams.get('start')==='quiz'){startQuiz({subject:startParams.get('subject'),budget:startParams.get('budget'),priority:startParams.get('priority')});history.replaceState(null,'',location.pathname);}
}catch(error){
 console.error(error);
}
