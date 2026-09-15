const $ = (selector) => document.querySelector(selector);
const escape = (value) => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number = n => Number(n).toFixed(1).replace('.', ',');
const criteria = {teachers_score:'Преподаватели',practice_score:'Практика и ДЗ',feedback_score:'Проверка работ',curator_score:'Кураторы',platform_score:'Платформа',workload_score:'Нагрузка и темп',price_quality_score:'Цена / качество'};
const teacherCriteria = {explanation:'Объяснение материала',practice:'Практика и разбор ошибок',feedback:'Обратная связь',tempo:'Темп и нагрузка',communication:'Общение и атмосфера'};
const labels = {'русский':'Русский язык','математика':'Математика','обществознание':'Обществознание','физика':'Физика','химия':'Химия','биология':'Биология','информатика':'Информатика','английский':'Английский язык','история':'История','литература':'Литература','география':'География'};
const dialog = $('#detail-dialog');
let catalog, subject = '', expanded = false, mode = 'schools';
function showDialog(html){ $('#dialog-content').innerHTML = html; dialog.showModal(); }
$('.close').onclick = () => dialog.close();
dialog.addEventListener('click', e => { if(e.target === dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close();} });
function methodology(){showDialog(`<div class="method-view"><p class="eyebrow">ПРОЗРАЧНО О ГЛАВНОМ</p><h2>Как работает рейтинг</h2><p class="method-lead">Две независимые оценки складываются в один понятный результат.</p><div class="rating-formula"><div class="formula-card expert"><small>Редакция ЕГЭшки</small><strong>до 5</strong><span>по открытым данным</span></div><b class="formula-sign">+</b><div class="formula-card students"><small>Ученики</small><strong>до 5</strong><span>по одобренным отзывам</span></div><b class="formula-sign">=</b><div class="formula-card total"><small>Общий рейтинг</small><strong>до 10</strong><span>итоговая оценка</span></div></div><div class="method-note"><strong>★ Предварительная оценка</strong><span>Отзывов учеников пока недостаточно, поэтому показана только редакционная часть, пересчитанная на шкалу 0–10.</span></div><h3>Что входит в оценку ЕГЭшки</h3><div class="weight-grid"><div class="weight-item"><b>24%</b><span>Преподаватели</span></div><div class="weight-item"><b>16%</b><span>Практика</span></div><div class="weight-item"><b>14%</b><span>Проверка работ</span></div><div class="weight-item"><b>14%</b><span>Кураторы</span></div><div class="weight-item"><b>14%</b><span>Цена / качество</span></div><div class="weight-item"><b>10%</b><span>Платформа</span></div><div class="weight-item"><b>8%</b><span>Нагрузка</span></div></div><p class="trust-note"><strong>Важно:</strong> результаты учеников, которые публикуют школы, — заявления самих школ. Они не гарантируют такой же результат каждому.</p></div>`);}
$('#methodology').onclick = methodology; $('#compare-method').onclick = methodology;
function renderSchools(){
  let rows = catalog.schools.filter(s => !subject || s.subjects.includes(subject));
  rows.sort($('#sort').value === 'name' ? (a,b)=>a.name.localeCompare(b.name,'ru') : (a,b)=>b.score-a.score);
  $('#catalog-label').textContent = `${subject ? labels[subject] : 'Все предметы'} · ${rows.length} ${rows.length===1?"школа":rows.length<5?"школы":"школ"}`;
  $('#show-more').hidden = expanded || rows.length<=3;
  $('#school-list').innerHTML = rows.slice(0,expanded?rows.length:3).map((s,i)=>`<article class="school-card"><div class="school-card-top"><span class="school-mark ${i%2?'pink-mark':'blue-mark'}">${s.name.startsWith('100')?'100':escape(s.name.slice(0,1))}</span><span class="rank">${$('#sort').value==='rating'?`${i+1} в этом списке`:'Онлайн-школа'}</span></div><h3>${escape(s.name)}</h3><p class="card-description">${escape(s.description)}</p><div class="card-score"><span>Оценка ЕГЭшки</span><strong>${number(s.score)}<small>/10*</small></strong></div><button class="card-open" data-school="${escape(s.name)}">Подробнее о школе <span>↗</span></button></article>`).join('');
  document.querySelectorAll('[data-school]').forEach(b=>b.onclick=()=>schoolDetails(b.dataset.school));
}
function schoolDetails(name){const s=catalog.schools.find(x=>x.name===name);const top=Object.entries(s.criteria).sort((a,b)=>b[1]-a[1]).slice(0,3);showDialog(`<div class="school-detail"><div class="detail-hero"><div><p class="eyebrow">ОНЛАЙН-ШКОЛА · ЕГЭ</p><h2>${escape(s.name)}</h2><p>${escape(s.description)}</p></div><div class="detail-score"><small>Оценка ЕГЭшки</small><strong>${number(s.score)}</strong><span>из 10*</span></div></div><div class="detail-subjects">${s.subjects.map(x=>`<span>${escape(labels[x]||x)}</span>`).join('')}</div><h3>Что особенно хорошо</h3><div class="detail-highlights">${top.map(([key,value])=>`<div><span>${escape(criteria[key])}</span><strong>${number(value)}</strong><i><b style="width:${value*10}%"></b></i></div>`).join('')}</div><div class="detail-grid"><article class="detail-card price"><small>ЦЕНА И УСЛОВИЯ</small><h3>Сколько стоит</h3><p>${escape(s.price)}</p></article><article class="detail-card format"><small>КАК ПРОХОДИТ ОБУЧЕНИЕ</small><h3>Формат</h3><p>${escape(s.format)}</p></article><article class="detail-card strength"><small>СИЛЬНАЯ СТОРОНА</small><h3>Почему выбирают</h3><p>${escape(s.strengths)}</p></article><article class="detail-card attention"><small>ПЕРЕД ОПЛАТОЙ</small><h3>Что проверить</h3><p>${escape(s.weaknesses)}</p></article></div><div class="detail-footer"><p>* Предварительная редакционная оценка по открытым данным.</p><a class="button blue" href="${escape(s.url)}" target="_blank" rel="noopener">Перейти на сайт школы <span>↗</span></a></div></div>`);}
function candidates(){return mode==='schools'?catalog.schools:catalog.teachers.filter(t=>t.subject===$('#teacher-subject').value);}
function populateComparison(){const rows=candidates();['left','right'].forEach((side,i)=>{$(`#${side}-select`).innerHTML=rows.map((r,j)=>`<option value="${j}">${escape(r.name)}${mode==='teachers'?` · ${escape(r.school)}`:''}</option>`).join('');$(`#${side}-select`).value=String(Math.min(i,rows.length-1));});renderComparison();}
function renderComparison(changed){const rows=candidates(),l=$('#left-select'),r=$('#right-select');if(l.value===r.value&&rows.length>1){const other=changed==='right'?l:r;other.value=String((Number(other.value)+1)%rows.length);}const left=rows[Number(l.value)],right=rows[Number(r.value)];if(!left||!right){$('#comparison-result').textContent='Для сравнения нужны два преподавателя по этому предмету.';return;}
document.querySelectorAll('#left-select option').forEach(o=>o.disabled=o.value===r.value);document.querySelectorAll('#right-select option').forEach(o=>o.disabled=o.value===l.value);
const row=(title,a,b,cls='')=>`<div class="comparison-row ${cls}"><span>${title}</span><p>${a}</p><p>${b}</p></div>`;
const meter=value=>`<span class="meter-value">${number(value)}</span><span class="meter" aria-hidden="true"><i style="width:${Math.max(0,Math.min(100,Number(value)*10))}%"></i></span>`;
let html=row('Шкала 0–10*',escape(left.name),escape(right.name),'column-heads');
html+=row('Общая оценка',`<strong>${number(left.score)}</strong>`,`<strong>${number(right.score)}</strong>`);
if(mode==='schools'){html+=Object.entries(criteria).map(([key,label])=>row(label,meter(left.criteria[key]),meter(right.criteria[key]))).join('');html+='<p class="fine">* Предварительно: по оценкам ЕГЭшки, без отзывов учеников.</p>';}else{
 html+=row('Школа',escape(left.school),escape(right.school));
 html+='<div class="criteria-title"><strong>По оценкам учеников</strong><span>Отдельные критерии · шкала 1–5</span></div>';
 const teacherMetric=(teacher,key)=>Number.isFinite(Number(teacher.criteria?.[key]))?meter(Number(teacher.criteria[key])):'<span class="no-score">Пока нет оценок</span>';
 html+=Object.entries(teacherCriteria).map(([key,label])=>row(label,teacherMetric(left,key),teacherMetric(right,key),'teacher-metric')).join('');
 html+='<p class="fine">Критерии появятся после одобренных отзывов учеников.</p>';
}
if(mode==='schools'){html+=`<details><summary class="comparison-summary">Цена и условия</summary>${row('Цена и условия',escape(left.price),escape(right.price),'details')}</details>`;}else{
 const teacherCard=t=>`<article class="teacher-compare-card"><div><span>${escape(t.school)}</span><strong>${number(t.score)}<small>/10*</small></strong></div><h3>${escape(t.name)}</h3><p>${escape(t.description)}</p><a href="${escape(t.url)}" target="_blank" rel="noopener">Открыть профиль <b>↗</b></a></article>`;
 html+=`<details class="teacher-details"><summary class="comparison-summary">Подробнее о преподавателях</summary><div class="teacher-compare-cards">${teacherCard(left)}${teacherCard(right)}</div></details>`;
}
$('#comparison-result').innerHTML=html;}
$('#left-select').onchange=()=>renderComparison('left');$('#right-select').onchange=()=>renderComparison('right');$('#teacher-subject').onchange=populateComparison;
document.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>{mode=b.dataset.mode;document.querySelectorAll('[data-mode]').forEach(x=>{x.classList.toggle('active',x===b);x.setAttribute('aria-pressed',String(x===b));});$('#teacher-subject-wrap').hidden=mode!=='teachers';$('#left-label').textContent=mode==='teachers'?'2. Первый преподаватель':'Первая школа';$('#right-label').textContent=mode==='teachers'?'3. Второй преподаватель':'Вторая школа';populateComparison();});
$('#sort').onchange=renderSchools;$('#show-more').onclick=()=>{expanded=true;renderSchools();};
try{
 const response=await fetch('catalog.json');if(!response.ok)throw new Error('catalog');catalog=await response.json();
 $('#subject-list').innerHTML=[['','Все предметы'],...Object.entries(labels)].map(([value,label])=>`<button class="subject ${value===''?'active':''}" data-subject="${value}" aria-pressed="${value===''}">${label}</button>`).join('');
 document.querySelectorAll('[data-subject]').forEach(b=>b.onclick=()=>{subject=b.dataset.subject;expanded=false;document.querySelectorAll('[data-subject]').forEach(x=>{x.classList.toggle('active',x===b);x.setAttribute('aria-pressed',String(x===b));});renderSchools();$('#schools').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});});
 $('#teacher-subject').innerHTML=[...new Set(catalog.teachers.map(t=>t.subject))].sort().map(s=>`<option>${escape(s)}</option>`).join('');
 $('#hero-score-one').textContent=number(catalog.schools.find(s=>s.name==='Умскул').score)+'*';$('#hero-score-two').textContent=number(catalog.schools.find(s=>s.name==='100балльный репетитор').score)+'*';
 renderSchools();populateComparison();
 const config=await fetch('links.json').then(r=>r.json());$('#channel-link').href=config.channel;$('#review-link').href=config.bot;
}catch(error){$('#school-list').innerHTML='<p>Не удалось загрузить каталог. Обнови страницу, чтобы попробовать ещё раз.</p>';console.error(error);}
if(!matchMedia('(prefers-reduced-motion: reduce)').matches&&'IntersectionObserver' in window){
 const observer=new IntersectionObserver(entries=>entries.forEach(entry=>{if(entry.isIntersecting){entry.target.classList.add('revealed');observer.unobserve(entry.target);}}),{threshold:0.08});
 document.querySelectorAll('.school-grid,.reviews,.channel-section').forEach(node=>{node.classList.add('reveal-ready');observer.observe(node);});
 const heroArt=$('.hero-art'),heroCard=$('.match-card');
 heroArt.addEventListener('pointermove',event=>{const bounds=heroArt.getBoundingClientRect();heroCard.style.setProperty('--ry',`${((event.clientX-bounds.left)/bounds.width-.5)*8}deg`);heroCard.style.setProperty('--rx',`${((event.clientY-bounds.top)/bounds.height-.5)*-8}deg`);});
 heroArt.addEventListener('pointerleave',()=>{heroCard.style.setProperty('--ry','0deg');heroCard.style.setProperty('--rx','0deg');});
}
