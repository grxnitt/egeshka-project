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

  function goal(name,params){
    try{if(id&&window.ym)window.ym(id,'reachGoal',name,params||{})}catch(e){}
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
    if(isTelegramPath(url,'egematch_blog')){goal('channel_click');return true}
    return true;
  }

  function onClick(event){
    var target=event.target&&event.target.closest?event.target:null;
    if(!target)return;
    var a=target.closest('a[href]');
    if(a){
      var host=tagOutbound(a);
      if(host)goal('outbound_school',{host:host});
      else trackTelegram(a);
      return;
    }
    if(target.closest('#quiz-start'))goal('quiz_start');
  }

  window.egeTrack=goal;
  document.addEventListener('click',onClick,true);
  document.addEventListener('auxclick',onClick,true);
})();
