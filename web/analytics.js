(function(){
  var OWN_HOSTS=['egematch.online','www.egematch.online','egematch.ru','www.egematch.ru','egeshka-project.vercel.app'];
  var SKIP_HOSTS=['t.me','telegram.me'];
  var isLocal=/^(localhost|127\.|192\.168\.|10\.)/.test(location.hostname);
  var id=isLocal?0:Number(window.EGE_METRIKA_ID)||0;

  if(id){
    (function(m,e,t,r,i,k,a){m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};m[i].l=1*new Date();
    k=e.createElement(t);a=e.getElementsByTagName(t)[0];k.async=1;k.src=r;a.parentNode.insertBefore(k,a)})
    (window,document,'script','https://mc.yandex.ru/metrika/tag.js','ym');
    window.ym(id,'init',{clickmap:true,trackLinks:true,accurateTrackBounce:true,webvisor:false});
  }

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

  function onClick(event){
    var target=event.target&&event.target.closest?event.target:null;
    if(!target)return;
    var a=target.closest('a[href]');
    if(a){
      trackArticleClick(a);
      if(a.closest&&a.closest('.article-sources'))return;
      var host=tagOutbound(a);
      if(host)goal('outbound_school',{host:host});
      else trackTelegram(a);
      return;
    }
    if(target.closest('#quiz-start'))goal('quiz_start');
  }

  /* ---- Articles: where readers go and how far they read ---- */
  var articleRoot=document.querySelector('.article-page');
  var listRoot=document.querySelector('.articles-page');
  var articleSlug=((location.pathname.match(/^\/articles\/([a-z0-9-]+)/)||[])[1])||'';
  if(articleSlug==='index')articleSlug='';

  function slugOf(url){return ((url.pathname.match(/^\/articles\/([a-z0-9-]+)/)||[])[1])||''}

  function articlePlace(el){
    var map=[['.art-tldr','tldr'],['.art-callout','callout'],['.article-cta','cta'],['.article-sources','sources'],
      ['.article-more','related'],['.article-body','body'],['.article-card.is-featured','list_featured'],['.article-card','list'],
      ['.breadcrumbs','nav'],['.back-row','nav'],['.header','header'],['.mobile-product-nav','nav'],['.footer','footer']];
    for(var i=0;i<map.length;i++){if(el.closest(map[i][0]))return map[i][1]}
    return 'other';
  }

  function articleTarget(url){
    var host=url.hostname.toLowerCase(),path=url.pathname.toLowerCase().replace(/\.html$/,'').replace(/\/index$/,'/');
    if(host==='t.me'||host==='telegram.me'){
      return path.indexOf('/egematch_bot')===0?'bot':path.indexOf('/egematch_blog')===0?'channel':'telegram_other';
    }
    if(host!==location.hostname.toLowerCase()&&OWN_HOSTS.indexOf(host)<0)return 'source';
    if(url.hash==='#compare'||url.search.indexOf('compareLeft')>-1)return 'compare';
    if(url.search.indexOf('start=quiz')>-1)return 'quiz';
    if(path.indexOf('/ratings')===0)return 'ratings';
    if(path.indexOf('/schools/')===0)return 'school';
    if(path.indexOf('/teachers/')===0)return 'teacher';
    if(path==='/articles'||path==='/articles/')return 'articles_list';
    if(path.indexOf('/articles/')===0)return 'article';
    if(path.indexOf('/methodology')===0)return 'methodology';
    if(path==='/'||path==='')return 'home';
    return 'site';
  }

  function trackArticleClick(a){
    if(!articleRoot&&!listRoot)return;
    var url;
    try{url=new URL(a.href,location.href)}catch(e){return}
    if(url.protocol!=='http:'&&url.protocol!=='https:')return;
    var target=articleTarget(url),place=articlePlace(a);
    if(target==='article'){
      var to=slugOf(url);
      goal('article_open',{slug:to,from:place,source_slug:articleSlug||'list'});
      visit(['Статьи','Открытия',to]);
    }
    if(articleRoot&&articleSlug){
      goal('article_click',{target:target,place:place,slug:articleSlug});
      visit(['Статьи',articleSlug,'Клик: '+target]);
    }
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
  document.addEventListener('click',onClick,true);
  document.addEventListener('auxclick',onClick,true);
})();
