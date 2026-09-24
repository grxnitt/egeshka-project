(function(){
  var OWN_HOSTS=['egematch.online','www.egematch.online','egematch.ru','www.egematch.ru','egeshka-project.vercel.app'];
  var SKIP_HOSTS=['t.me','telegram.me'];
  var id=Number(window.EGE_METRIKA_ID)||0;

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
    if(OWN_HOSTS.indexOf(host)>-1||SKIP_HOSTS.indexOf(host)>-1||/supabase\.co$/.test(host))return null;
    if(!url.searchParams.has('utm_source')){
      url.searchParams.set('utm_source','egematch');
      url.searchParams.set('utm_medium','referral');
      url.searchParams.set('utm_campaign',host.replace(/^www\./,'').replace(/[^a-z0-9]+/g,'_'));
      a.href=url.toString();
    }
    return host;
  }

  function onClick(event){
    var target=event.target&&event.target.closest?event.target:null;
    if(!target)return;
    var a=target.closest('a[href]');
    if(a){
      var host=tagOutbound(a);
      if(host)goal('outbound_school',{host:host});
      else if(a.id==='review-link')goal('review_click');
      else if(a.id==='channel-link')goal('channel_click');
      return;
    }
    if(target.closest('#quiz-start'))goal('quiz_start');
  }

  document.addEventListener('click',onClick,true);
  document.addEventListener('auxclick',onClick,true);
})();
