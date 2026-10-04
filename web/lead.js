/* Lead request window for the "Выбрать школу" buttons.
   Loaded by analytics.js only when window.EGE_LEADS_API is set. For a school the server lists as accepting
   requests, the button opens this form instead of the school's own site; for every other school (or if the
   server is unreachable) the button keeps working as a plain link. */
(function(){
  var API=(window.EGE_LEADS_API||'').replace(/\/+$/,'');
  if(!API)return;
  var SUBJECTS=['Русский','Математика профильная','Математика базовая','Обществознание','Физика','Химия','Биология','Информатика','Английский','История','Литература','География'];
  var TYPES={phone:{label:'Телефон',placeholder:'+7 900 123-45-67',mode:'tel',auto:'tel'},telegram:{label:'Telegram',placeholder:'@username',mode:'text',auto:'off'},vk:{label:'VK',placeholder:'vk.com/username',mode:'url',auto:'off'}};
  var schools={};
  var dialog=null;

  function goal(name,params){try{window.egeTrack&&window.egeTrack(name,params)}catch(e){}}
  function el(tag,attrs,children){
    var node=document.createElement(tag);
    Object.keys(attrs||{}).forEach(function(key){
      if(key==='text')node.textContent=attrs[key];
      else if(key==='class')node.className=attrs[key];
      else node.setAttribute(key,attrs[key]);
    });
    (children||[]).forEach(function(child){node.appendChild(typeof child==='string'?document.createTextNode(child):child)});
    return node;
  }
  function request(path,options){
    return fetch(API+path,options).then(function(response){
      return response.json().catch(function(){return {}}).then(function(data){return {status:response.status,data:data}});
    });
  }

  function injectStyles(){
    if(document.getElementById('lead-styles'))return;
    var css='.lead-dialog{border:0;border-radius:24px;padding:32px;max-width:520px;width:calc(100% - 32px);max-height:92dvh;overflow:auto;color:var(--ink,#181923);background:var(--paper,#faf8f5)}'
      +'.lead-dialog::backdrop{background:#11152d88;backdrop-filter:blur(5px)}'
      +'.lead-dialog h2{font-size:26px;margin:0 0 6px;letter-spacing:-1px}.lead-dialog p{font-size:14px;margin:0 0 14px;line-height:1.5}'
      +'.lead-close{position:absolute;right:14px;top:10px;background:transparent;border:0;font-size:30px;line-height:1}'
      +'.lead-form{display:grid;gap:14px}.lead-field{display:grid;gap:6px;font-size:13px;font-weight:600}'
      +'.lead-field input[type=text],.lead-field input[type=tel],.lead-field input[type=url],.lead-field select{width:100%;border:1px solid var(--line,#dededc);border-radius:12px;background:#fff;padding:12px 14px;font:inherit;font-weight:400;color:inherit}'
      +'.lead-types{display:flex;gap:8px;flex-wrap:wrap}.lead-types label{position:relative}.lead-types input{position:absolute;opacity:0}'
      +'.lead-types span{display:inline-block;padding:9px 16px;border:1px solid var(--line,#dededc);border-radius:999px;background:#fff;font-size:13px;font-weight:600;cursor:pointer}'
      +'.lead-types input:checked+span{background:var(--blue,#344bd8);border-color:var(--blue,#344bd8);color:#fff}'
      +'.lead-types input:focus-visible+span{outline:3px solid var(--pink,#ff4d8d);outline-offset:3px}'
      +'.lead-check{display:flex;gap:10px;align-items:flex-start;font-size:12px;line-height:1.5;font-weight:400}.lead-check input{margin-top:3px;flex-shrink:0}'
      +'.lead-hp{position:absolute;left:-9999px;width:1px;height:1px;overflow:hidden}'
      +'.lead-error{color:#b3123f;font-size:13px;font-weight:600;margin:0}'
      +'.lead-submit{border:0;border-radius:999px;padding:16px 24px;background:var(--blue,#344bd8);color:#fff;font-weight:700;font-size:14px}.lead-submit[disabled]{opacity:.55;cursor:default}'
      +'.lead-link{background:none;border:0;padding:0;font-size:12px;text-decoration:underline;text-underline-offset:4px;color:inherit}'
      +'.lead-skip{font-size:12px;color:var(--muted,#62656f);text-align:center}.lead-skip a{text-decoration:underline;text-underline-offset:4px}';
    var style=el('style',{id:'lead-styles'});
    style.textContent=css;
    document.head.appendChild(style);
  }

  function close(){if(dialog&&dialog.open)dialog.close()}
  function open(content){
    injectStyles();
    if(!dialog){
      dialog=el('dialog',{class:'lead-dialog','aria-label':'Заявка в школу'});
      dialog.addEventListener('click',function(event){if(event.target===dialog)close()});
      document.body.appendChild(dialog);
    }
    dialog.textContent='';
    dialog.appendChild(el('button',{type:'button',class:'lead-close','aria-label':'Закрыть'},['×']));
    dialog.firstChild.onclick=close;
    dialog.appendChild(content);
    if(!dialog.open)dialog.showModal();
  }

  function showMessage(title,text,extra){
    var box=el('div',{},[el('h2',{text:title}),el('p',{text:text})]);
    if(extra)box.appendChild(extra);
    open(box);
  }

  function showWithdraw(token,school){
    var button=el('button',{type:'button',class:'lead-link',text:'Отозвать заявку и согласие'});
    button.onclick=function(){
      button.disabled=true;
      request('/api/leads/withdraw',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:token})}).then(function(result){
        goal('lead_withdraw',{school:school});
        showMessage(result.data.ok?'Заявка отозвана':'Не удалось отозвать заявку',result.data.ok?'Мы удалили заявку и попросили школу удалить ваши данные.':'Напишите нам в Telegram или на почту из политики конфиденциальности, и мы удалим данные вручную.');
      }).catch(function(){button.disabled=false});
    };
    return el('p',{class:'lead-skip'},[
      'Передумали? ',button
    ]);
  }

  function openForm(schoolName,source,href){
    var info=schools[schoolName];
    var form=el('form',{class:'lead-form',novalidate:'novalidate'});
    var state={type:info.contactTypes[0]};
    var consentVersion='',busy=false;
    var error=el('p',{class:'lead-error',role:'alert'});
    var submit=el('button',{type:'submit',class:'lead-submit',text:'Отправить заявку',disabled:'disabled'});

    var nameInput=el('input',{type:'text',name:'name',autocomplete:'given-name',maxlength:'80',required:'required'});
    var subjectSelect=el('select',{name:'subject',required:'required'},[el('option',{value:'',text:'Выберите предмет'})]);
    SUBJECTS.forEach(function(subject){subjectSelect.appendChild(el('option',{value:subject,text:subject}))});
    try{var saved=JSON.parse(sessionStorage.getItem('egeshka-quiz')||'{}');if(saved&&saved.subject)SUBJECTS.forEach(function(s,i){if(s.toLowerCase()===String(saved.subject).toLowerCase())subjectSelect.selectedIndex=i+1})}catch(e){}
    var contactInput=el('input',{type:'tel',name:'contact',maxlength:'120',required:'required'});
    var typeBox=el('div',{class:'lead-types',role:'radiogroup','aria-label':'Как с вами связаться'});
    function applyType(){
      var cfg=TYPES[state.type];
      contactInput.setAttribute('placeholder',cfg.placeholder);
      contactInput.setAttribute('inputmode',cfg.mode);
      contactInput.setAttribute('autocomplete',cfg.auto);
      contactInput.setAttribute('aria-label',cfg.label);
    }
    info.contactTypes.forEach(function(type,index){
      var radio=el('input',{type:'radio',name:'contact_type',value:type});
      if(index===0)radio.checked=true;
      radio.onchange=function(){state.type=type;applyType()};
      typeBox.appendChild(el('label',{},[radio,el('span',{text:TYPES[type].label})]));
    });
    applyType();

    var guardian=el('input',{type:'checkbox',name:'guardian'});
    var consent=el('input',{type:'checkbox',name:'consent'});
    var consentText=el('span',{text:'Загружаем текст согласия…'});
    var honeypot=el('input',{type:'text',name:'website',tabindex:'-1',autocomplete:'off','aria-hidden':'true'});

    form.appendChild(el('label',{class:'lead-field'},['Имя',nameInput]));
    form.appendChild(el('label',{class:'lead-field'},['Предмет',subjectSelect]));
    if(info.contactTypes.length>1)form.appendChild(el('div',{class:'lead-field'},['Как с вами связаться',typeBox]));
    form.appendChild(el('label',{class:'lead-field'},[info.contactTypes.length>1?'Контакт':TYPES[state.type].label,contactInput]));
    form.appendChild(el('label',{class:'lead-check'},[guardian,el('span',{text:'Заявку оставляет родитель или законный представитель'})]));
    form.appendChild(el('label',{class:'lead-check'},[consent,consentText]));
    form.appendChild(el('div',{class:'lead-hp','aria-hidden':'true'},[honeypot]));
    form.appendChild(error);
    form.appendChild(submit);
    var skip=el('p',{class:'lead-skip'},['Или ',el('a',{href:href||'#',target:'_blank',rel:'noopener',text:'перейти на сайт школы'}),' без заявки.']);
    form.appendChild(skip);

    var box=el('div',{},[
      el('h2',{text:'Заявка в «'+schoolName+'»'}),
      el('p',{text:'Школа свяжется с вами сама. Мы передадим только то, что вы укажете ниже.'}),
      form
    ]);
    open(box);
    goal('lead_open',{school:schoolName,source:source});

    request('/api/lead-consent?school='+encodeURIComponent(schoolName)).then(function(result){
      if(!result.data.text)throw new Error('no consent');
      consentVersion=result.data.version;
      consentText.textContent=result.data.text;
      submit.removeAttribute('disabled');
    }).catch(function(){consentText.textContent='Не удалось загрузить текст согласия. Обновите страницу или перейдите на сайт школы.'});

    form.addEventListener('submit',function(event){
      event.preventDefault();
      if(busy||!consentVersion)return;
      error.textContent='';
      if(!consent.checked){error.textContent='Отметьте согласие на передачу данных школе.';return}
      busy=true;submit.setAttribute('disabled','disabled');submit.textContent='Отправляем…';
      request('/api/leads',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
        school:schoolName,name:nameInput.value,subject:subjectSelect.value,contact_type:state.type,contact:contactInput.value,
        guardian:guardian.checked,consent:true,consent_version:consentVersion,website:honeypot.value,source:source
      })}).then(function(result){
        busy=false;submit.removeAttribute('disabled');submit.textContent='Отправить заявку';
        if(result.data.ok){
          goal('lead_sent',{school:schoolName,source:source});
          if(result.data.duplicate)showMessage('Заявка уже у школы','Вы недавно уже оставляли заявку в эту школу. Повторно мы её не отправляем: школа свяжется с вами по прежней.');
          else showMessage('Заявка отправлена','Школа свяжется с вами выбранным способом. Если не ответят в течение нескольких дней, напишите нам в Telegram.',showWithdraw(result.data.token,schoolName));
        }else error.textContent=result.data.error||'Не получилось отправить заявку. Попробуйте ещё раз.';
      }).catch(function(){
        busy=false;submit.removeAttribute('disabled');submit.textContent='Отправить заявку';
        error.textContent='Нет связи с сервером. Попробуйте позже или перейдите на сайт школы.';
      });
    });
    nameInput.focus();
  }

  function onClick(event){
    var link=event.target&&event.target.closest?event.target.closest('a[data-choose-school]'):null;
    if(!link)return;
    var name=link.getAttribute('data-choose-school');
    if(!schools[name]||!schools[name].contactTypes.length)return;
    if(event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;
    event.preventDefault();
    event.stopPropagation();
    var source=link.getAttribute('data-source')||'other';
    goal('choose_school',{school:name,source:source,lead_form:1});
    openForm(name,source,link.getAttribute('href'));
  }

  request('/api/lead-schools').then(function(result){
    (result.data.schools||[]).forEach(function(item){
      var types=(item.contactTypes||[]).filter(function(t){return TYPES[t]});
      if(item.name&&types.length)schools[item.name]={contactTypes:types};
    });
    if(Object.keys(schools).length)window.addEventListener('click',onClick,true);
  }).catch(function(){});
})();
