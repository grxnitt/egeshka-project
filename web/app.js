const $ = (selector) => document.querySelector(selector);
const escape = (value) => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number = n => Number(n).toFixed(1).replace('.', ',');
const criteria = {teachers_score:'Преподаватели',practice_score:'Практика и ДЗ',feedback_score:'Проверка работ',curator_score:'Кураторы',platform_score:'Платформа',workload_score:'Нагрузка и темп',price_quality_score:'Цена / качество'};
const labels = {'русский':'Русский язык','математика':'Математика','обществознание':'Обществознание','физика':'Физика','химия':'Химия','биология':'Биология','информатика':'Информатика','английский':'Английский язык','история':'История','литература':'Литература','география':'География'};
const dialog = $('#detail-dialog');
let catalog, subject = '', expanded = false, mode = 'schools';
function showDialog(html){ $('#dialog-content').innerHTML = html; dialog.showModal(); }
$('.close').onclick = () => dialog.close();
dialog.addEventListener('click', e => { if(e.target === dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close();} });
function methodology(){showDialog('<p class="eyebrow">ПРОЗРАЧНО О ГЛАВНОМ</p><h2>Что стоит за оценкой?</h2><p>В сервисе итоговая оценка складывается из оценки ЕГЭшки до 5 баллов и средней оценки учеников до 5 баллов.</p><h3>Что означает звёздочка?</h3><p>На этой странице показана редакционная часть из каталога бота, приведённая к шкале 0–10. Звёздочка обозначает предварительный балл: пользовательские отзывы в него не включены.</p><h3>Какие критерии учитываем?</h3><p>Преподаватели — 24%, практика — 16%, проверка работ — 14%, кураторы — 14%, платформа — 10%, нагрузка — 8%, цена / качество — 14%.</p><p>Результаты учеников, которые публикуют школы, — заявления этих школ. Они не гарантируют такой же результат каждому ученику.</p>');}
$('#methodology').onclick = methodology; $('#compare-method').onclick = methodology;
function renderSchools(){
  let rows = catalog.schools.filter(s => !subject || s.subjects.includes(subject));
  rows.sort($('#sort').value === 'name' ? (a,b)=>a.name.localeCompare(b.name,'ru') : (a,b)=>b.score-a.score);
  $('#catalog-label').textContent = `${subject ? labels[subject] : 'Все предметы'} · ${rows.length} ${rows.length===1?"школа":rows.length<5?"школы":"школ"}`;
  $('#show-more').hidden = expanded || rows.length<=3;
  $('#school-list').innerHTML = rows.slice(0,expanded?rows.length:3).map((s,i)=>`<article class="school-card"><div class="school-card-top"><span class="school-mark ${i%2?'pink-mark':'blue-mark'}">${s.name.startsWith('100')?'100':escape(s.name.slice(0,1))}</span><span class="rank">${$('#sort').value==='rating'?`${i+1} в этом списке`:'Онлайн-школа'}</span></div><h3>${escape(s.name)}</h3><p class="card-description">${escape(s.description)}</p><div class="card-score"><span>Оценка ЕГЭшки</span><strong>${number(s.score)}<small>/10*</small></strong></div><button class="card-open" data-school="${escape(s.name)}">Подробнее о школе <span>↗</span></button></article>`).join('');
  document.querySelectorAll('[data-school]').forEach(b=>b.onclick=()=>schoolDetails(b.dataset.school));
}
function schoolDetails(name){const s=catalog.schools.find(x=>x.name===name);showDialog(`<p class="eyebrow">ОНЛАЙН-ШКОЛА · ЕГЭ</p><h2>${escape(s.name)}</h2><p>${escape(s.description)}</p><h3>Цена и условия</h3><p>${escape(s.price)}</p><h3>Формат</h3><p>${escape(s.format)}</p><h3>Сильные стороны</h3><p>${escape(s.strengths)}</p><h3>На что обратить внимание</h3><p>${escape(s.weaknesses)}</p><a class="button blue" href="${escape(s.url)}" target="_blank" rel="noopener">Официальный сайт ↗</a>`);}
function candidates(){return mode==='schools'?catalog.schools:catalog.teachers.filter(t=>t.subject===$('#teacher-subject').value);}
function populateComparison(){const rows=candidates();['left','right'].forEach((side,i)=>{$(`#${side}-select`).innerHTML=rows.map((r,j)=>`<option value="${j}">${escape(r.name)}${mode==='teachers'?` · ${escape(r.school)}`:''}</option>`).join('');$(`#${side}-select`).value=String(Math.min(i,rows.length-1));});renderComparison();}
function renderComparison(changed){const rows=candidates(),l=$('#left-select'),r=$('#right-select');if(l.value===r.value&&rows.length>1){const other=changed==='right'?l:r;other.value=String((Number(other.value)+1)%rows.length);}const left=rows[Number(l.value)],right=rows[Number(r.value)];if(!left||!right){$('#comparison-result').textContent='Для сравнения нужны два преподавателя по этому предмету.';return;}
document.querySelectorAll('#left-select option').forEach(o=>o.disabled=o.value===r.value);document.querySelectorAll('#right-select option').forEach(o=>o.disabled=o.value===l.value);
const row=(title,a,b,cls='')=>`<div class="comparison-row ${cls}"><span>${title}</span><p>${a}</p><p>${b}</p></div>`;
let html=row('Оценка ЕГЭшки',`<strong>${number(left.score)}/10*</strong>`,`<strong>${number(right.score)}/10*</strong>`);
if(mode==='schools'){html+=Object.entries(criteria).map(([key,label])=>row(label,`${number(left.criteria[key])}/10*`,`${number(right.criteria[key])}/10*`)).join('');html+=row('Цена и условия',escape(left.price),escape(right.price),'details');}else{html+=row('Школа',escape(left.school),escape(right.school));html+=row('О преподавателе',escape(left.description),escape(right.description),'details');}
$('#comparison-result').innerHTML=html+'<p class="fine">* Предварительная редакционная оценка. Без оценок учеников.</p>';}
$('#left-select').onchange=()=>renderComparison('left');$('#right-select').onchange=()=>renderComparison('right');$('#teacher-subject').onchange=populateComparison;
document.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>{mode=b.dataset.mode;document.querySelectorAll('[data-mode]').forEach(x=>{x.classList.toggle('active',x===b);x.setAttribute('aria-pressed',String(x===b));});$('#teacher-subject-wrap').hidden=mode!=='teachers';populateComparison();});
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
