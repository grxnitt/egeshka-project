(function(){
  var OWN_HOSTS=['egematch.online','www.egematch.online','egematch.ru','www.egematch.ru','egeshka-project.vercel.app'];
  var SKIP_HOSTS=['t.me','telegram.me'];
  var isLocal=/^(localhost|127\.|192\.168\.|10\.)/.test(location.hostname);
  var configured=Number(window.EGE_METRIKA_ID)||0;
  var id=isLocal?0:configured;

  /* ---- Cookie consent: Metrica is loaded only after the visitor accepts ---- */
  var CONSENT_KEY='egeCookieConsent';
  function readConsent(){try{return localStorage.getItem(CONSENT_KEY)}catch(e){return null}}
  function writeConsent(v){try{localStorage.setItem(CONSENT_KEY,v)}catch(e){}}

  function startMetrika(){
    if(!id||window.__egeMetrika)return;
    window.__egeMetrika=1;
    (function(m,e,t,r,i,k,a){m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};m[i].l=1*new Date();
    k=e.createElement(t);a=e.getElementsByTagName(t)[0];k.async=1;k.src=r;a.parentNode.insertBefore(k,a)})
    (window,document,'script','https://mc.yandex.ru/metrika/tag.js','ym');
    window.ym(id,'init',{clickmap:true,trackLinks:true,accurateTrackBounce:true,webvisor:false});
  }

  function clearMetrikaCookies(){
    var host=location.hostname,parts=host.split('.'),domains=['',host,'.'+host];
    if(parts.length>2)domains.push('.'+parts.slice(-2).join('.'));
    document.cookie.split(';').forEach(function(c){
      var name=c.split('=')[0].trim();
      if(name.indexOf('_ym')!==0)return;
      domains.forEach(function(d){document.cookie=name+'=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/'+(d?';domain='+d:'')});
    });
  }

  function hideBanner(){var box=document.getElementById('cookie-banner');if(box)box.parentNode.removeChild(box)}

  function choose(value){
    var previous=readConsent();
    writeConsent(value);
    hideBanner();
    if(value==='yes'){startMetrika();return}
    clearMetrikaCookies();
    if(previous==='yes')location.reload();
  }

  function showBanner(){
    if(document.getElementById('cookie-banner'))return;
    if(!document.getElementById('cookie-banner-style')){
      var style=document.createElement('style');
      style.id='cookie-banner-style';
      style.textContent='#cookie-banner{position:fixed;z-index:60;left:16px;right:16px;bottom:16px;max-width:760px;margin:0 auto;display:flex;align-items:center;gap:20px;padding:16px 20px;background:#fff;color:#181923;border:1px solid #dededc;border-radius:20px;box-shadow:0 14px 40px rgb(24 25 35/.18);font:14px/1.5 var(--font-ui,Arial,sans-serif)}'
        +'#cookie-banner p{margin:0;flex:1}#cookie-banner a{color:#344bd8;text-decoration:underline;text-underline-offset:3px}'
        +'#cookie-banner .cookie-actions{display:flex;gap:8px;flex:none}'
        +'#cookie-banner button{min-height:44px;padding:0 22px;border:1.5px solid #181923;border-radius:999px;background:#fff;color:#181923;font:600 14px/1 var(--font-ui,Arial,sans-serif);cursor:pointer}'
        +'#cookie-banner button:hover{background:#181923;color:#fff}'
        +'#cookie-banner button:focus-visible,#cookie-banner a:focus-visible{outline:2px solid #344bd8;outline-offset:3px}'
        +'@media(max-width:700px){#cookie-banner{flex-direction:column;align-items:stretch;gap:10px;padding:12px 14px;font-size:13px;line-height:1.4}#cookie-banner button{min-height:40px}#cookie-banner.cookie-above-nav{bottom:calc(88px + env(safe-area-inset-bottom))}#cookie-banner .cookie-actions button{flex:1}}';
      document.head.appendChild(style);
    }
    var box=document.createElement('div');
    box.id='cookie-banner';
    box.setAttribute('role','region');
    box.setAttribute('aria-label','Файлы cookie');
    if(document.querySelector('.mobile-product-nav'))box.className='cookie-above-nav';
    box.innerHTML='<p>Используем cookie Яндекс.Метрики, чтобы понимать, как люди пользуются сайтом. <a href="/privacy#cookies">Подробнее</a></p>'
      +'<div class="cookie-actions"><button type="button" data-cookie="yes">Принять</button><button type="button" data-cookie="no">Отклонить</button></div>';
    box.addEventListener('click',function(event){
      var button=event.target.closest&&event.target.closest('[data-cookie]');
      if(button)choose(button.getAttribute('data-cookie'));
    });
    document.body.appendChild(box);
  }

  document.addEventListener('click',function(event){
    var link=event.target.closest&&event.target.closest('[data-cookie-settings]');
    if(link){event.preventDefault();showBanner()}
  });

  var consent=readConsent();
  if(consent==='yes')startMetrika();
  else if(consent==='no')clearMetrikaCookies();
  else if(configured)showBanner();

  var events=window.egeEvents=window.egeEvents||[];
  function log(kind,name,data){events.push({kind:kind,name:name,data:data||{}});if(events.length>300)events.shift()}

  function goal(name,params){
    log('goal',name,params);
    try{if(id&&window.ym)window.ym(id,'reachGoal',name,params||{})}catch(e){}
  }

  // Visit parameters: a tree shown in Metrica under "Параметры визитов", e.g. Статьи > slug > Прочитал.
  function visit(path){
    log('visit',path.join(' > '));
    try{
      if(!id||!window.ym)return;
      var tree={},node=tree;
      for(var i=0;i<path.length-1;i++){node=node[path[i]]={}}
      node[path[path.length-1]]=1;
      window.ym(id,'params',tree);
    }catch(e){}
  }

  function tagOutbound(a){
    var url;
    try{url=new URL(a.href,location.href)}catch(e){return null}
    if(url.protocol!=='http:'&&url.protocol!=='https:')return null;
    var host=url.hostname.toLowerCase();
    if(host===location.hostname.toLowerCase()||OWN_HOSTS.indexOf(host)>-1||SKIP_HOSTS.indexOf(host)>-1||/supabase\.co$/.test(host))return null;
    if(!url.searchParams.has('utm_source')){
      url.searchParams.set('utm_source','egematch');
      url.searchParams.set('utm_medium','referral');
      url.searchParams.set('utm_campaign',host.replace(/^www\./,'').replace(/[^a-z0-9]+/g,'_'));
      a.href=url.toString();
    }
    return host;
  }

  function isTelegramPath(url,name){
    return url.pathname.toLowerCase().indexOf('/'+name)===0;
  }

  function trackTelegram(a){
    var url;
    try{url=new URL(a.href,location.href)}catch(e){return false}
    var host=url.hostname.toLowerCase();
    if(host!=='t.me'&&host!=='telegram.me')return false;
    if(isTelegramPath(url,'egematch_bot')){
      var source=a.getAttribute('data-source')||(a.id==='review-link'?'review_button':(a.closest&&a.closest('.quiz-result')?'quiz_result':'other'));
      goal('bot_open',{source:source});
      if(a.id==='review-link')goal('review_click');
      return true;
    }
    if(isTelegramPath(url,'egematch_blog')){goal('channel_click',{source:a.getAttribute('data-source')||'other'});return true}
    return true;
  }

  // Home page "how it works": which of the four steps people open.
  function trackHowStep(a){
    var card=a.closest&&a.closest('.how-card');
    if(!card)return;
    var step=card.getAttribute('data-step')||'';
    goal('how_step',{step:step});
    visit(['Главная','Как это работает','Шаг '+step]);
  }

  function onClick(event){
    var target=event.target&&event.target.closest?event.target:null;
    if(!target)return;
    var a=target.closest('a[href]');
    if(a){
      trackArticleClick(a);
      trackHowStep(a);
      if(a.closest&&a.closest('.article-sources'))return;
      var chooseSchool=a.getAttribute('data-choose-school');
      var host=tagOutbound(a);
      if(chooseSchool)goal('choose_school',{school:chooseSchool,source:a.getAttribute('data-source')||'other'});
      if(host)goal('outbound_school',{host:host});
      else trackTelegram(a);
      return;
    }
    if(target.closest('#quiz-start'))goal('quiz_start');
  }

  /* ---- Articles: how far people read and whether they go to Telegram or the rating ---- */
  var articleRoot=document.querySelector('.article-page');
  var articleSlug=((location.pathname.match(/^\/articles\/([a-z0-9-]+)/)||[])[1])||'';

  function trackArticleClick(a){
    if(!articleRoot||!articleSlug)return;
    var url;
    try{url=new URL(a.href,location.href)}catch(e){return}
    var host=url.hostname.toLowerCase(),path=url.pathname.toLowerCase().replace(/\.html$/,'');
    var target=null;
    if(host==='t.me'||host==='telegram.me'){
      if(path.indexOf('/egematch_blog')===0||path.indexOf('/egematch_bot')===0)target='telegram';
    }else if((host===location.hostname.toLowerCase()||OWN_HOSTS.indexOf(host)>-1)&&path.indexOf('/ratings')===0){
      target='ratings';
    }
    if(!target)return;
    goal('article_to_'+target,{slug:articleSlug,place:a.closest('.article-cta')?'card':'text'});
    visit(['Статьи',articleSlug,target==='telegram'?'Клик: Telegram':'Клик: Рейтинг']);
  }

  function trackArticleReading(){
    var body=document.querySelector('.article-body');
    if(!body||!articleSlug)return;
    var active=0,maxProgress=0,marks={},readSent=false,finishSent=false,ticking=false;
    visit(['Статьи',articleSlug,'Открыл']);
    function progress(){
      var r=body.getBoundingClientRect();
      if(!r.height)return 0;
      return Math.min(1,Math.max(0,(window.innerHeight*0.85-r.top)/r.height));
    }
    function mark(key,label){if(!marks[key]){marks[key]=1;visit(['Статьи',articleSlug,label])}}
    function check(){
      var p=progress();
      if(p>maxProgress)maxProgress=p;
      [25,50,75].forEach(function(m){if(maxProgress>=m/100)mark('s'+m,'Прокрутка '+m+'%')});
      if(maxProgress>=0.97)mark('s100','Прокрутка 100%');
      [60,120].forEach(function(t){if(active>=t)mark('t'+t,'Время ≥ '+t+' с')});
      if(!readSent&&maxProgress>=0.5&&active>=20){
        readSent=true;
        goal('article_read',{slug:articleSlug,seconds:active});
        visit(['Статьи',articleSlug,'Прочитал']);
      }
      if(!finishSent&&maxProgress>=0.97&&active>=20){
        finishSent=true;
        goal('article_finish',{slug:articleSlug,seconds:active});
        visit(['Статьи',articleSlug,'Дочитал']);
      }
    }
    window.addEventListener('scroll',function(){
      if(ticking)return;
      ticking=true;
      requestAnimationFrame(function(){ticking=false;check()});
    },{passive:true});
    var timer=setInterval(function(){
      if(document.visibilityState==='visible')active++;
      check();
      if(active>=600)clearInterval(timer);
    },1000);
    check();
  }
  if(articleRoot)trackArticleReading();

  window.egeTrack=goal;
  /* Decorative motion on every page (motion.js is a no-op without support or with reduced motion). */
  (function(){var m=document.createElement('script');m.src='/motion.js?v=33';m.defer=true;document.head.appendChild(m)})();
  /* On-site lead window: only loaded once an API address is configured in analytics-config.js. */
  if(window.EGE_LEADS_API){var leadScript=document.createElement('script');leadScript.src='/lead.js?v=2';leadScript.defer=true;document.head.appendChild(leadScript)}
  document.addEventListener('click',onClick,true);
  document.addEventListener('auxclick',onClick,true);
})();
