/* Lead request window for the "Выбрать школу" buttons.
   Loaded by analytics.js only when window.EGE_LEADS_API is set. For a school the server lists as accepting
   requests, the button opens this form instead of the school's own site; for every other school (or if the
   server is unreachable) the button keeps working as a plain link. */
(function(){
  var API=(window.EGE_LEADS_API||'').replace(/\/+$/,'');
  if(!API)return;
  var SUBJECTS=['Русский','Математика профильная','Математика базовая','Обществознание','Физика','Химия','Биология','Информатика','Английский','История','Литература','География'];
  var TYPES={
    phone:{chip:'Телефон',label:'Номер телефона',placeholder:'+7 900 123-45-67',hint:'Например, +7 900 123-45-67',type:'tel',mode:'tel',auto:'tel',via:'по телефону'},
    telegram:{chip:'Telegram',label:'Ник в Telegram',placeholder:'@username',hint:'Ник начинается с @, например @ivan_petrov',type:'text',mode:'text',auto:'off',via:'в Telegram'},
    vk:{chip:'VK',label:'Ссылка на профиль VK',placeholder:'https://vk.com/id123456',hint:'Вставьте ссылку на ваш профиль, не только имя',type:'url',mode:'url',auto:'off',via:'в VK'},
    email:{chip:'Почта',label:'Электронная почта',placeholder:'name@mail.ru',hint:'Адрес, который вы читаете',type:'email',mode:'email',auto:'email',via:'на почту'}
  };
  var schools={};
  var dialog=null;

  /* The same rules as the server (egeshka_bot/leads.py); the server stays the source of truth. */
  var CHECKS={
    phone:function(v){var d=v.replace(/\D/g,'');if(d.length===11&&(d[0]==='7'||d[0]==='8'))d=d.slice(1);return d.length===10&&'3489'.indexOf(d[0])>-1?'':'Проверьте номер: нужно 10 цифр после +7, например +7 900 123-45-67.'},
    telegram:function(v){v=v.trim().replace(/^(https?:\/\/)?(t\.me|telegram\.me)\//i,'').replace(/^@/,'');return /^[A-Za-z][A-Za-z0-9_]{4,31}$/.test(v)?'':'Проверьте ник: от 5 до 32 латинских букв, цифр или _, например @ivan_petrov.'},
    vk:function(v){return /^(https?:\/\/)?(m\.)?(vk\.com|vk\.ru)\/.+/i.test(v.trim())?'':'Нужна ссылка на профиль, например https://vk.com/id123456. Откройте свою страницу VK и скопируйте адрес из строки браузера.'},
    email:function(v){v=v.trim();return v.length<=120&&/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(v)?'':'Проверьте адрес почты, например name@mail.ru.'}
  };

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
  /* Plain text with http(s) links turned into anchors, built with DOM nodes so nothing is parsed as markup. */
  function linkified(text,tag){
    var node=el(tag||'span');
    text.split(/(https?:\/\/[^\s)]*[^\s).,;])/).forEach(function(part,index){
      if(index%2)node.appendChild(el('a',{href:part,target:'_blank',rel:'noopener',text:part}));
      else if(part)node.appendChild(document.createTextNode(part));
    });
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
      +'.lead-dialog h2{font-size:26px;margin:0 36px 8px 0;letter-spacing:-1px}.lead-dialog p{font-size:14px;margin:0 0 14px;line-height:1.5}'
      +'.lead-close{position:absolute;right:14px;top:10px;background:transparent;border:0;font-size:30px;line-height:1}'
      +'.lead-form{display:grid;gap:16px}.lead-field{display:grid;gap:6px;font-size:13px;font-weight:600}'
      +'.lead-field input[type=text],.lead-field input[type=tel],.lead-field input[type=url],.lead-field input[type=email],.lead-field select{width:100%;border:1px solid var(--line,#dededc);border-radius:12px;background:#fff;padding:12px 14px;font:inherit;font-size:16px;font-weight:400;color:inherit}'
      +'.lead-field input[aria-invalid=true],.lead-field select[aria-invalid=true]{border-color:#b3123f;background:#fff6f8}'
      +'.lead-hint{font-size:12px;font-weight:400;color:var(--muted,#62656f);margin:0!important;line-height:1.4!important}'
      +'.lead-fielderr{font-size:12px;font-weight:600;color:#b3123f;margin:0!important;line-height:1.4!important}.lead-fielderr:empty{display:none}'
      +'.lead-types{display:flex;gap:8px;flex-wrap:wrap}.lead-types label{position:relative}.lead-types input{position:absolute;opacity:0}'
      +'.lead-types span{display:inline-block;padding:9px 16px;border:1px solid var(--line,#dededc);border-radius:999px;background:#fff;font-size:13px;font-weight:600;cursor:pointer}'
      +'.lead-types input:checked+span{background:var(--blue,#344bd8);border-color:var(--blue,#344bd8);color:#fff}'
      +'.lead-types input:focus-visible+span{outline:3px solid var(--pink,#ff4d8d);outline-offset:3px}'
      +'.lead-check{display:flex;gap:10px;align-items:flex-start;font-size:13px;line-height:1.5;font-weight:400}.lead-check input{margin-top:3px;flex-shrink:0;width:18px;height:18px}'
      +'.lead-consent{font-size:12px;line-height:1.5}.lead-consent a,.lead-skip a{text-decoration:underline;text-underline-offset:3px;word-break:break-word}'
      +'.lead-group{display:grid;gap:8px;border:0;margin:0;padding:0;min-width:0}.lead-group legend{font-size:13px;font-weight:600;padding:0;margin-bottom:6px}'
      +'.lead-hp{position:absolute;left:-9999px;width:1px;height:1px;overflow:hidden}'
      +'.lead-error{color:#b3123f;font-size:13px;font-weight:600;margin:0}.lead-error:empty{display:none}'
      +'.lead-submit{border:0;border-radius:999px;padding:16px 24px;background:var(--blue,#344bd8);color:#fff;font-weight:700;font-size:15px}.lead-submit[disabled]{opacity:.55;cursor:default}'
      +'.lead-link{background:none;border:0;padding:0;font-size:12px;text-decoration:underline;text-underline-offset:4px;color:inherit}'
      +'.lead-skip{font-size:12px;color:var(--muted,#62656f);text-align:center}'
      +'@media(max-width:520px){.lead-dialog{padding:24px 18px;border-radius:20px}.lead-dialog h2{font-size:23px}}';
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
    var closeButton=el('button',{type:'button',class:'lead-close','aria-label':'Закрыть'},['×']);
    closeButton.onclick=close;
    dialog.appendChild(closeButton);
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
        showMessage(result.data.ok?'Заявка отозвана':'Не удалось отозвать заявку',result.data.ok?'Мы удалили вашу заявку. Если она уже была передана школе, мы попросили школу удалить ваши данные.':'Напишите нам на почту из политики конфиденциальности, укажите контакт из заявки, и мы удалим данные вручную.');
      }).catch(function(){button.disabled=false});
    };
    return el('p',{class:'lead-skip'},['Передумали? ',button,'. Эта ссылка есть только в этом окне.']);
  }

  function openForm(schoolName,source,href){
    var info=schools[schoolName];
    var state={type:info.contactTypes[0]};
    var consentVersion='',busy=false;
    var form=el('form',{class:'lead-form',novalidate:'novalidate'});
    var error=el('p',{class:'lead-error',role:'alert'});
    var submit=el('button',{type:'submit',class:'lead-submit',text:'Отправить заявку',disabled:'disabled'});

    function field(input,labelText,id,hint){
      var err=el('p',{class:'lead-fielderr',id:id+'-err'});
      input.setAttribute('id',id);
      input.setAttribute('aria-describedby',id+'-err');
      var label=el('label',{class:'lead-field','for':id},[el('span',{text:labelText}),input]);
      if(hint)label.appendChild(hint);
      label.appendChild(err);
      return {label:label,err:err,input:input};
    }
    function fail(f,message){f.err.textContent=message;f.input.setAttribute('aria-invalid','true');return message?f:null}
    function clear(f){f.err.textContent='';f.input.removeAttribute('aria-invalid')}

    var subjectSelect=el('select',{name:'subject',required:'required'},[el('option',{value:'',text:'Выберите предмет'})]);
    SUBJECTS.forEach(function(subject){subjectSelect.appendChild(el('option',{value:subject,text:subject}))});
    try{var saved=JSON.parse(sessionStorage.getItem('egeshka-quiz')||'{}');if(saved&&saved.subject)SUBJECTS.forEach(function(s,i){if(s.toLowerCase()===String(saved.subject).toLowerCase())subjectSelect.selectedIndex=i+1})}catch(e){}
    var subjectField=field(subjectSelect,'Какой предмет ЕГЭ нужен','lead-subject');

    var nameInput=el('input',{type:'text',name:'name',autocomplete:'given-name',maxlength:'80'});
    var nameField=field(nameInput,'Как к вам обращаться','lead-name');

    var contactInput=el('input',{name:'contact',maxlength:'120'});
    var contactHint=el('p',{class:'lead-hint'});
    var contactLabelText=el('span');
    var contactErr=el('p',{class:'lead-fielderr',id:'lead-contact-err'});
    contactInput.setAttribute('id','lead-contact');
    contactInput.setAttribute('aria-describedby','lead-contact-err');
    var contactField={label:el('label',{class:'lead-field','for':'lead-contact'},[contactLabelText,contactInput,contactHint,contactErr]),err:contactErr,input:contactInput};
    function applyType(){
      var cfg=TYPES[state.type];
      contactLabelText.textContent=cfg.label;
      contactInput.setAttribute('type',cfg.type);
      contactInput.setAttribute('placeholder',cfg.placeholder);
      contactInput.setAttribute('inputmode',cfg.mode);
      contactInput.setAttribute('autocomplete',cfg.auto);
      contactHint.textContent=cfg.hint;
      clear(contactField);
    }

    var typeBox=el('div',{class:'lead-types',role:'radiogroup','aria-label':'Как связаться'});
    info.contactTypes.forEach(function(type,index){
      var radio=el('input',{type:'radio',name:'contact_type',value:type});
      if(index===0)radio.checked=true;
      radio.onchange=function(){if(state.type!==type){state.type=type;contactInput.value='';applyType()}};
      typeBox.appendChild(el('label',{},[radio,el('span',{text:TYPES[type].chip})]));
    });
    applyType();

    var adult=el('input',{type:'radio',name:'applicant',value:'adult'});
    var guardian=el('input',{type:'radio',name:'applicant',value:'guardian'});
    var applicantErr=el('p',{class:'lead-fielderr',id:'lead-applicant-err'});
    var applicantNote=el('p',{class:'lead-hint'});
    var applicantGroup=el('fieldset',{class:'lead-group','aria-describedby':'lead-applicant-err'},[
      el('legend',{text:'Кто оставляет заявку'}),
      el('label',{class:'lead-check'},[adult,el('span',{text:'Мне есть 18 лет'})]),
      el('label',{class:'lead-check'},[guardian,el('span',{text:'Я родитель или законный представитель ученика'})]),
      applicantNote,applicantErr
    ]);
    function noteApplicant(){applicantNote.textContent=guardian.checked?'Укажите своё имя и свой контакт. Школа свяжется с вами.':'';applicantErr.textContent=''}
    adult.onchange=guardian.onchange=noteApplicant;

    var consent=el('input',{type:'checkbox',name:'consent',id:'lead-consent'});
    var consentText=el('span',{class:'lead-consent',text:'Загружаем текст согласия…'});
    var consentErr=el('p',{class:'lead-fielderr',id:'lead-consent-err'});
    consent.setAttribute('aria-describedby','lead-consent-err');
    consent.onchange=function(){consentErr.textContent=''};
    var honeypot=el('input',{type:'text',name:'website',tabindex:'-1',autocomplete:'off','aria-hidden':'true'});

    form.appendChild(subjectField.label);
    form.appendChild(nameField.label);
    if(info.contactTypes.length>1)form.appendChild(el('div',{class:'lead-field'},[el('span',{text:'Как с вами связаться'}),typeBox]));
    form.appendChild(contactField.label);
    form.appendChild(applicantGroup);
    form.appendChild(el('div',{},[el('label',{class:'lead-check','for':'lead-consent'},[consent,consentText]),consentErr]));
    form.appendChild(el('div',{class:'lead-hp','aria-hidden':'true'},[honeypot]));
    form.appendChild(error);
    form.appendChild(submit);
    form.appendChild(el('p',{class:'lead-skip'},['Или ',el('a',{href:href||'#',target:'_blank',rel:'noopener',text:'перейти на сайт школы'}),' без заявки.']));

    open(el('div',{},[
      el('h2',{text:'Заявка в «'+schoolName+'»'}),
      el('p',{text:'Оставьте контакт, и школа свяжется с вами сама. Мы передадим школе только то, что вы укажете ниже.'}),
      form
    ]));
    goal('lead_open',{school:schoolName,source:source});

    function validate(){
      var first=null;
      [subjectField,nameField,contactField].forEach(clear);
      var checks=[
        [subjectField,subjectSelect.value?'':'Выберите предмет.'],
        [nameField,/^.{2,80}$/.test(nameInput.value.trim())?'':'Укажите имя, от 2 символов.'],
        [contactField,contactInput.value.trim()?CHECKS[state.type](contactInput.value):'Укажите контакт: '+TYPES[state.type].label.toLowerCase()+'.']
      ];
      checks.forEach(function(item){if(item[1]){fail(item[0],item[1]);first=first||item[0].input}});
      if(!adult.checked&&!guardian.checked){applicantErr.textContent='Выберите вариант. Ученикам младше 18 лет заявку оставляет родитель.';first=first||adult}
      if(!consent.checked){consentErr.textContent='Без согласия мы не можем передать заявку школе.';first=first||consent}
      return first;
    }
    contactInput.addEventListener('blur',function(){
      if(!contactInput.value.trim())return;
      var message=CHECKS[state.type](contactInput.value);
      if(message)fail(contactField,message);else clear(contactField);
    });
    contactInput.addEventListener('input',function(){if(contactInput.getAttribute('aria-invalid'))clear(contactField)});
    nameInput.addEventListener('input',function(){clear(nameField)});
    subjectSelect.addEventListener('change',function(){clear(subjectField)});

    request('/api/lead-consent?school='+encodeURIComponent(schoolName)).then(function(result){
      if(!result.data.text)throw new Error('no consent');
      consentVersion=result.data.version;
      consentText.textContent='';
      consentText.appendChild(linkified(result.data.text));
      submit.removeAttribute('disabled');
    }).catch(function(){consentText.textContent='Не удалось загрузить текст согласия. Обновите страницу или перейдите на сайт школы.'});

    form.addEventListener('submit',function(event){
      event.preventDefault();
      if(busy||!consentVersion)return;
      error.textContent='';
      var invalid=validate();
      if(invalid){invalid.focus();return}
      busy=true;submit.setAttribute('disabled','disabled');submit.textContent='Отправляем…';
      request('/api/leads',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
        school:schoolName,name:nameInput.value,subject:subjectSelect.value,contact_type:state.type,contact:contactInput.value,
        applicant:guardian.checked?'guardian':'adult',consent:true,consent_version:consentVersion,website:honeypot.value,source:source
      })}).then(function(result){
        busy=false;submit.removeAttribute('disabled');submit.textContent='Отправить заявку';
        if(result.data.ok){
          goal('lead_sent',{school:schoolName,source:source});
          if(result.data.duplicate)showMessage('Заявка уже у школы','Вы недавно уже оставляли заявку в эту школу. Повторно мы её не отправляем: школа свяжется с вами по прежней.');
          else showMessage('Заявка отправлена','Школа свяжется с вами '+TYPES[state.type].via+'. Если не ответят за несколько рабочих дней, напишите нам в Telegram.',showWithdraw(result.data.token,schoolName));
        }else error.textContent=result.data.error||'Не получилось отправить заявку. Попробуйте ещё раз.';
      }).catch(function(){
        busy=false;submit.removeAttribute('disabled');submit.textContent='Отправить заявку';
        error.textContent='Нет связи с сервером. Попробуйте позже или перейдите на сайт школы.';
      });
    });
    subjectSelect.focus();
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
