import { applyLiveRatings } from './supabase-client.js?v=4';
const $ = (selector) => document.querySelector(selector);
const escape = (value) => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number = n => Number(n).toFixed(1).replace('.', ',');
const criteria = {teachers_score:'Преподаватели',practice_score:'Практика и ДЗ',feedback_score:'Проверка работ',curator_score:'Кураторы',platform_score:'Платформа',workload_score:'Нагрузка и темп',organization_score:'Организация обучения'};
import { labels, quizSubjectKeys } from './subjects.js?v=1';
const dialog = $('#detail-dialog');
let catalog, links = {bot:'https://t.me/egematch_bot', channel:'https://t.me/EgeMatch_blog'};
// Started right away so the quiz can wait for it on a slow connection instead of failing.
const catalogReady = fetch('catalog.json?v=4').then(response => { if (!response.ok) throw new Error('catalog'); return response.json(); }).then(async data => { await applyLiveRatings(data); catalog = data; });
catalogReady.catch(() => {});
function showDialog(html){ $('#dialog-content').innerHTML = html; dialog.showModal();document.querySelector("#dialog-content").scrollTop=0; }
$('.close').onclick = () => dialog.close();
dialog.addEventListener('click', e => { if(e.target === dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close();} });
const siteQuiz={step:0,answers:{}};
const PRIORITY_LABELS={teacher:'Сильные преподаватели',practice:'Практика и домашние задания',curator:'Куратор и поддержка',platform:'Удобная платформа',price:'Доступная цена'};
const quizSteps=[
 {key:'subject',questionNumber:1,title:'Какой предмет сдаёшь?',options:()=>[...quizSubjectKeys.slice(0,2),'математика базовая',...quizSubjectKeys.slice(2,-1)].map(value=>[labels[value],value])},
 {key:'budget',questionNumber:2,title:'Сколько готов тратить на подготовку в месяц?',options:()=>[['До 3 000 ₽','3000'],['3 000–5 000 ₽','5000'],['5 000–8 000 ₽','8000'],['Больше 8 000 ₽','12000'],['Пока не определился','0']]},
 {key:'level',questionNumber:3,title:'Как оцениваешь свои знания по предмету сейчас?',options:()=>[['Начинаю почти с нуля','low'],['Что-то знаю, нужна система','middle'],['База хорошая, хочу усилить результат','high']]},
 {key:'target',questionNumber:4,title:'На какой балл ЕГЭ ориентируешься?',options:()=>siteQuiz.answers.subject==='математика базовая'?[['Оценка 3','3'],['Оценка 4','4'],['Оценка 5','5']]:[['60+','60'],['70+','70'],['80+','80'],['90+','90']]},
 {key:'curator',questionNumber:5,title:'Нужен ли тебе куратор, который следит за прогрессом?',options:()=>[['Справлюсь сам, куратор не нужен','1'],['Иногда хочу спросить куратора','2'],['Нужен регулярный контроль куратора','3'],['Без куратора я всё откладываю','4']]},
 {key:'workload',questionNumber:6,title:'Какой темп подготовки тебе подходит?',options:()=>[['Небольшая нагрузка, без перегруза','1'],['Умеренный темп','2'],['Готов заниматься много','3'],['Максимум практики ради результата','4']]},
 {key:'priority1',questionNumber:7,title:'Что для тебя важнее всего? Выбери главный приоритет.',options:()=>Object.entries(PRIORITY_LABELS).map(([value,label])=>[label,value])},
 {key:'priority2',questionNumber:null,title:'Дополнительный приоритет',subtitle:'Можно выбрать ещё один пункт.',options:()=>[...Object.entries(PRIORITY_LABELS).filter(([value])=>value!==siteQuiz.answers.priority1).map(([value,label])=>[label,value]),['Пропустить второй приоритет','none']]},
 {key:'control',questionNumber:8,title:'Как у тебя с самодисциплиной в подготовке?',options:()=>[['Отлично — планирую и делаю сам','1'],['Хорошо, но нужны напоминания','2'],['Слабо — нужны проверки и дедлайны','3'],['Совсем никак без жёсткого контроля','4']]},
];

// Mirrors egeshka_bot/scoring.py exactly (same weights, same thresholds) so
// the site and the bot always recommend schools the same way.
const BASE_WEIGHTS={teachers_score:.24,practice_score:.16,feedback_score:.14,curator_score:.14,platform_score:.10,workload_score:.08,organization_score:.14};
const PRIORITY_TO_FIELD={teacher:'teachers_score',practice:'practice_score',curator:'curator_score',platform:'platform_score'};
function personalizedWeights(a,keys){const w={...BASE_WEIGHTS};[a.priority1,a.priority2].forEach(p=>{const field=PRIORITY_TO_FIELD[p];if(field)w[field]+=.10;});const curatorNeed=Number(a.curator);if(curatorNeed>=3)w.curator_score+=.06;if(curatorNeed>=4)w.curator_score+=.04;const controlNeed=Number(a.control);if(controlNeed>=3){w.feedback_score+=.05;w.organization_score+=.03;}if(controlNeed>=4)w.feedback_score+=.04;if(a.level==='low'){w.curator_score+=.06;w.feedback_score+=.03;}else if(a.level==='high'){w.teachers_score+=.04;w.practice_score+=.04;}const target=Number(a.target);if(target>=90){w.teachers_score+=.06;w.practice_score+=.06;}else if(target>=85){w.teachers_score+=.03;w.practice_score+=.03;}const workload=Number(a.workload);if(workload===1||workload===4)w.workload_score+=.05;if(keys)Object.keys(w).forEach(key=>{if(!keys.includes(key))delete w[key];});const total=Object.values(w).reduce((sum,value)=>sum+value,0);Object.keys(w).forEach(key=>w[key]=w[key]/total);return w;}
// A criterion the school does not offer ("none") is left out of the match and of its score; one offered only
// on some tariffs ("tier") stays in. Needing something that is missing costs 0.5 ("none") or 0.2 ("tier").
const offeredKeys=school=>Object.keys(BASE_WEIGHTS).filter(key=>school.criteriaStatus?.[key]!=='none');
const baselineWeights=keys=>{const total=keys.reduce((sum,key)=>sum+BASE_WEIGHTS[key],0);return Object.fromEntries(keys.map(key=>[key,BASE_WEIGHTS[key]/total]));};
const chosen=(a,name)=>[a.priority1,a.priority2].includes(name);
const NEEDS={curator_score:a=>Number(a.curator)>=3||chosen(a,'curator'),feedback_score:a=>Number(a.control)>=3,platform_score:a=>chosen(a,'platform'),practice_score:a=>chosen(a,'practice')};
const NEED_REASONS={curator_score:{none:'нет куратора, а он тебе нужен',tier:'куратор — только на старших тарифах'},feedback_score:{none:'нет проверки работ, а она тебе нужна',tier:'проверка работ — не на всех тарифах'},platform_score:{none:'нет платформы, а она тебе важна',tier:'платформа — не на всех тарифах'},practice_score:{none:'нет практики, а она тебе важна',tier:'практика — не на всех тарифах'}};
function needPenalty(school,a){let delta=0;const reasons=[];for(const [key,needed] of Object.entries(NEEDS)){const status=school.criteriaStatus?.[key]||'yes';if(status!=='yes'&&needed(a)){delta-=status==='none'?.5:.2;reasons.push(NEED_REASONS[key][status]);}}return {delta,reasons};}
function budgetFit(school,a){if(!a.budget||a.subject==='математика базовая')return 0;const price=Number(school.monthlyPriceFrom||0);if(price<=0)return 0;const amplify=[a.priority1,a.priority2].includes('price')?1.6:1;const budget=Number(a.budget);if(price<=budget)return .4*amplify;const overRatio=(price-budget)/Math.max(budget,1);return -Math.min(1.2*amplify,overRatio*.8*amplify);}
function matchSchool(school,a){if(!school.subjects.includes(a.subject))return null;const keys=offeredKeys(school),w=personalizedWeights(a,keys);let fit=Object.entries(w).reduce((sum,[key,weight])=>sum+Number(school.criteria[key]||0)*weight,0);const bf=budgetFit(school,a),need=needPenalty(school,a);fit=Math.max(0,Math.min(10,fit+bf+need.delta));const reasons=[];if(bf>0)reasons.push('входит в бюджет');else if(bf<0)reasons.push('может быть выше бюджета');reasons.push(...need.reasons);const base=baselineWeights(keys);Object.keys(w).filter(key=>w[key]>base[key]+.01).sort((x,y)=>w[y]-w[x]).forEach(key=>{const value=Number(school.criteria[key]||0);if(value>=8.5)reasons.push(`сильные ${criteria[key].toLowerCase()} (${number(value)})`);else if(value<=7.5)reasons.push(`стоит проверить ${criteria[key].toLowerCase()} (${number(value)})`);});if(!reasons.length)reasons.push('ровное совпадение по всем критериям');return {score:Math.round(fit/10*1000)/10,reasons:reasons.slice(0,3)};}
const shortPrice=value=>value.length>118?`${value.slice(0,115).trim()}…`:value;
const schoolCardUrl=name=>{const target=catalog.schools.find(item=>item.name===name);return target?`/schools/${target.reviewSlug}?from=quiz`:'/ratings';};
function quizPayload(a){const subjectIndex=quizSubjectKeys.indexOf(a.subject);return `q_${subjectIndex}_${a.budget}_${a.level}_${a.target}_${a.curator}_${a.workload}_${a.priority1||'none'}_${a.priority2||'none'}_${a.control}`;}
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
function renderQuizResult(){if(!catalog){showDialog('<div class="quiz-result"><h2>Не удалось загрузить каталог школ</h2><p>Проверь соединение и обнови страницу, чтобы пройти подбор заново — ответы вводить не придётся долго, вопросов всего восемь.</p><div class="quiz-result-actions"><button type="button" class="quiz-edit">Начать заново</button></div></div>');document.querySelector('.quiz-edit').onclick=()=>{siteQuiz.step=0;renderSiteQuiz();};return;}try{sessionStorage.setItem('egeshka-quiz',JSON.stringify(siteQuiz.answers));}catch{} const a=siteQuiz.answers;const top=catalog.schools.map(school=>({school,match:matchSchool(school,a)})).filter(x=>x.match).sort((x,y)=>y.match.score-x.match.score).slice(0,3);try{window.egeTrack&&window.egeTrack('quiz_complete',{subject:a.subject,results:top.length})}catch{} const compareUrl=top.length>=2?`/compare?${new URLSearchParams({compareLeft:top[0].school.name,compareRight:top[1].school.name})}`:null;const cards=top.map(({school,match},index)=>`<article class="quiz-match"><div class="quiz-match-head"><span>${index+1}</span><h3>${escape(school.name)}</h3><strong>${number(match.score)}%<small>совпадение</small></strong></div><ul class="quiz-match-reasons">${match.reasons.map(reason=>`<li>${escape(reason)}</li>`).join('')}</ul><small><b>Ориентир по цене:</b> ${escape(a.subject==='математика базовая'?'Цена базовой математики уточняется отдельно.':shortPrice(school.price))}</small><a class="quiz-card-link" href="${escape(schoolCardUrl(school.name))}">Открыть карточку <span>→</span></a></article>`).join('');showDialog(`<div class="quiz-result"><h2>${top.length?`${['','Один вариант','Два варианта','Три варианта'][top.length]} под твои ответы`:'Пока нет подходящих вариантов'}</h2><p>${top.length?'Проценты показывают, насколько каждая школа подходит именно тебе, а не её место в общем рейтинге.':'По этому предмету пока нет подходящих школ в каталоге. Попробуй другой предмет или открой общий рейтинг.'}</p><div class="quiz-matches">${cards}</div><div class="quiz-result-actions">${compareUrl?`<a class="button blue" href="${escape(compareUrl)}">Сравнить первые две <span>→</span></a>`:''}<a class="button pink" href="${escape(links.bot)}?start=${quizPayload(a)}" target="_blank" rel="noopener">Открыть в боте: курсы и отзывы <span>↗</span></a><button type="button" class="quiz-edit">Изменить ответы</button></div><p class="quiz-bot-note">В боте — тот же подбор, но уже с карточками курсов, отзывами учеников и возможностью оставить свой отзыв. Отвечать заново не придётся.</p></div>`);document.querySelector('.quiz-edit').onclick=()=>{siteQuiz.step=0;renderSiteQuiz();};return;}
function renderSiteQuiz(options={}){quizRun++;const step=quizSteps[siteQuiz.step];if(!step)return options.instant?renderQuizResult():runQuizCalculation();const progressLabel=step.questionNumber?`Вопрос ${step.questionNumber} из 8`:step.title;const heading=step.questionNumber?step.title:step.subtitle;showDialog(`<div class="site-quiz"><div class="quiz-progress"><span>${escape(progressLabel)}</span><i><b style="width:${(siteQuiz.step+1)/quizSteps.length*100}%"></b></i></div><h2>${escape(heading)}</h2><div class="quiz-options">${step.options().map(([label,value])=>`<button data-quiz-value="${escape(value)}">${escape(label)}<span>→</span></button>`).join('')}</div>${siteQuiz.step?'<button class="quiz-back">← Назад</button>':''}</div>`);document.querySelectorAll('[data-quiz-value]').forEach(button=>button.onclick=()=>{siteQuiz.answers[step.key]=button.dataset.quizValue;siteQuiz.step++;renderSiteQuiz();});const back=$('.quiz-back');if(back)back.onclick=()=>{siteQuiz.step--;renderSiteQuiz();};}
$('#quiz-start').onclick=()=>{siteQuiz.step=0;siteQuiz.answers={};renderSiteQuiz();};
// Step 3 of "how it works" opens the quiz in place; without JS the link reloads the page with ?start=quiz.
document.querySelectorAll('[data-quiz-link]').forEach(link=>link.addEventListener('click',event=>{event.preventDefault();$('#quiz-start').click();}));
const applyLinks=()=>{$('#channel-link').href=links.channel;$('#review-link').href=links.bot;document.querySelectorAll('[data-bot-link]').forEach(link=>{link.href=links.bot;});};
applyLinks();
try{
 await catalogReady;
 try{const fresh=await fetch('links.json');if(fresh.ok){links=await fresh.json();applyLinks();}}catch{}
 if(new URLSearchParams(location.search).get('resume')==='quiz'){
  let saved=null;try{saved=JSON.parse(sessionStorage.getItem('egeshka-quiz'));}catch{}
  const targets=saved?.subject==='математика базовая'?['3','4','5']:['60','70','80','90'];
  const validPriority=value=>!value||Object.keys(PRIORITY_LABELS).includes(value);
  if(saved&&quizSubjectKeys.includes(saved.subject)&&['0','3000','5000','8000','12000'].includes(saved.budget)&&['low','middle','high'].includes(saved.level)&&targets.includes(saved.target)&&['1','2','3','4'].includes(saved.curator)&&['1','2','3','4'].includes(saved.workload)&&validPriority(saved.priority1)&&validPriority(saved.priority2)&&['1','2','3','4'].includes(saved.control)){siteQuiz.answers=saved;siteQuiz.step=quizSteps.length;renderSiteQuiz({instant:true});}
  else $('#quiz-start').click();
 }
 if(new URLSearchParams(location.search).get('start')==='quiz'){$('#quiz-start').click();history.replaceState(null,'',location.pathname);}
}catch(error){
 console.error(error);
}
