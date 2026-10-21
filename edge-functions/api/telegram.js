// Tencent EdgeOne Makers Edge Function.
// Telegram controller + five-profile preview. NO LinkedIn automation.
const HELP = [
  "LinkedIn AI Assistant — preview rejimi.",
  "Bot LinkedIn-ə dəvət GÖNDƏRMİR.",
  "",
  "/start — kömək",
  "/status — vəziyyət",
  "/add Ad Soyad | https://www.linkedin.com/in/username/ | Qeyd",
  "/queue — növbəti 5 profil",
  "/run — dərhal 5 profillik preview",
  "/auto_on və /auto_off — avtomatik yoxlama",
  "/mark sent https://www.linkedin.com/in/username/ — əl ilə göndəriş qeyd et",
  "/report — son hadisələr",
  "/draft Ad | Vəzifə | Şirkət | Məqsəd — mətn şablonu"
].join("\n");
const MAX_PROFILES=400;
const DEFAULT_STATE=()=>({profiles:[],events:[],auto:false,lastSlot:"",lastUpdate:0});
function store(){return typeof agent_kv==="undefined"?null:agent_kv;}
async function load(){
  const k=store();
  if(!k) return null;
  const raw=await k.get("agentstate");
  if(!raw)return DEFAULT_STATE();
  const obj=JSON.parse(raw);
  return {...DEFAULT_STATE(),...obj};
}
async function save(state){
  const k=store();
  if(!k)throw new Error("KV STORAGE NOT BOUND");
  await k.put("agentstate",JSON.stringify(state));
}
const response=(message,status=200)=>new Response(message,{status,headers:{"Content-Type":"text/plain; charset=utf-8","Cache-Control":"no-store"}});
async function telegram(env,method,body){
  const token=env.TELEGRAM_BOT_TOKEN;
  if(!token)throw new Error("Missing TELEGRAM_BOT_TOKEN");
  const r=await fetch("https://api.telegram.org/bot"+token+"/"+method,{
    method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)
  });
  const out=await r.json();
  if(!r.ok||!out.ok)throw new Error("Telegram "+method+" failed: "+(out.description||r.status));
  return out.result;
}
async function say(env,chatId,text){
  for(let i=0;i<text.length;i+=3900)
    await telegram(env,"sendMessage",{chat_id:chatId,text:text.slice(i,i+3900),disable_web_page_preview:true});
}
function normalize(raw){
  try{
    const u=new URL(raw.trim());
    if(u.protocol!=="https:"||!["linkedin.com","www.linkedin.com"].includes(u.hostname.toLowerCase()))return null;
    if(!/^\/in\/[a-zA-Z0-9_%\-]+\/?$/.test(u.pathname))return null;
    return "https://www.linkedin.com"+u.pathname.replace(/\/?$/,"/");
  }catch{return null;}
}
function nextFive(st){
  return st.profiles.filter(p=>p.status==="pending").sort((a,b)=>(a.lastPreview||0)-(b.lastPreview||0)).slice(0,5);
}
function listText(rows){
  return rows.map((p,i)=>(i+1)+". "+p.name+"\n"+p.url+(p.note?"\nQeyd: "+p.note:"")).join("\n\n");
}
function record(st,event,detail=""){
  st.events.push({when:new Date().toISOString(),event,detail});
  st.events=st.events.slice(-50);
}
async function preview(env,st,why){
  const rows=nextFive(st);
  if(!rows.length)return "Növbədə profil yoxdur. /add ilə əlavə edin.";
  for(const p of rows)p.lastPreview=Date.now();
  record(st,"preview",why+"; "+rows.length+" profil");
  await save(st);
  await say(env,env.TELEGRAM_OWNER_ID,"5 profillik yoxlama ("+why+"):\n\n"+listText(rows)+"\n\nBu siyahı yalnız preview-dir. LinkedIn-də dəvət göndərilməyib.");
  return "Preview tamamlandı";
}
function bakuNow(){
  const parts=new Intl.DateTimeFormat("en-GB",{timeZone:"Asia/Baku",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",hourCycle:"h23"}).formatToParts(new Date());
  const v=t=>parts.find(p=>p.type===t)?.value||"";
  return {hour:Number(v("hour")),slot:v("year")+"-"+v("month")+"-"+v("day")+"T"+v("hour")};
}
async function handle(env,update){
  const m=update?.message;
  const id=String(env.TELEGRAM_OWNER_ID||"");
  if(!m||String(m.from?.id)!==id||m.chat?.type!=="private")return;
  const text=String(m.text||"").trim();
  if(!text.startsWith("/"))return;
  const [first,...rest]=text.split(" ");
  const cmd=first.split("@")[0].toLowerCase(),arg=rest.join(" ").trim();
  const kv=store();
  if(["/start","/help"].includes(cmd)){await say(env,m.chat.id,HELP);return;}
  if(cmd==="/draft"){
    const bits=arg.split("|").map(s=>s.trim());
    await say(env,m.chat.id,bits.length<4?"İstifadə: /draft Ad | Vəzifə | Şirkət | Məqsəd":"Salam "+bits[0]+", "+bits[2]+" şirkətində "+bits[1]+" olaraq fəaliyyətiniz diqqətimi çəkdi. "+bits[3]+" mövzusunda əlaqə qurmaq istərdim.");
    return;
  }
  if(!kv){await say(env,m.chat.id,"KV Storage hələ bağlanmayıb. EdgeOne layihəsində KV namespace yaradıb onu agent_kv adı ilə bind edin.");return;}
  let st=await load();
  if(update.update_id<=st.lastUpdate)return;
  let result="";
  if(cmd==="/status"){
    const pending=st.profiles.filter(p=>p.status==="pending").length;
    const sent=st.profiles.filter(p=>p.status==="manual_sent").length;
    result="Bot statusu — Bakı\nAvtomatik preview: "+(st.auto?"AKTİV":"BAĞLI")+"\nNövbədə: "+pending+"\nƏl ilə göndərilmiş kimi qeyd: "+sent+"\nQrup: 5 | Saatlar: 09:00–19:00 | 2 saatdan bir\nRejim: PREVIEW; LinkedIn göndərişi YOXDUR.";
  }else if(cmd==="/add"){
    const fields=arg.split("|").map(s=>s.trim());
    const url=normalize(fields[1]||"");
    if(fields.length<2||!fields[0]||!url)result="İstifadə: /add Ad Soyad | https://www.linkedin.com/in/username/ | Qeyd";
    else if(st.profiles.some(p=>p.url===url))result="Bu profil artıq siyahıdadır.";
    else if(st.profiles.length>=MAX_PROFILES)result="Bu versiyada maksimum "+MAX_PROFILES+" profil saxlanır.";
    else {
      st.profiles.push({name:fields[0].slice(0,120),url,note:(fields[2]||"").slice(0,250),status:"pending",lastPreview:0});
      record(st,"add",url);result="Profil əlavə edildi.";
    }
  }else if(cmd==="/queue"){
    const rows=nextFive(st);result=rows.length?"Növbəti 5 profil:\n\n"+listText(rows):"Növbədə profil yoxdur.";
  }else if(cmd==="/run"){
    result=await preview(env,st,"manual");
  }else if(cmd==="/auto_on"){
    st.auto=true;record(st,"auto_on");
    result="Avtomatik preview aktivdir. GitHub Actions cron ayrıca qurulmalıdır. LinkedIn dəvəti göndərilmir.";
  }else if(cmd==="/auto_off"){
    st.auto=false;record(st,"auto_off");result="Avtomatik preview söndürüldü.";
  }else if(cmd==="/mark"){
    const match=arg.match(/^sent\s+(\S+)/i);
    const url=match?normalize(match[1]):null;
    const p=st.profiles.find(p=>p.url===url);
    if(!url)result="İstifadə: /mark sent https://www.linkedin.com/in/username/";
    else if(!p)result="Bu profil növbədə yoxdur.";
    else if(p.status==="manual_sent")result="Artıq əl ilə göndərilmiş kimi qeyd olunub.";
    else {p.status="manual_sent";record(st,"manual_sent",url);result="İstifadəçi qeydi saxlanıldı. LinkedIn təsdiqi deyil.";}
  }else if(cmd==="/report"){
    const rows=st.events.slice(-15).reverse();
    result=rows.length?rows.map(x=>x.when.slice(0,16)+" — "+x.event+(x.detail?" — "+x.detail:"")).join("\n"):"Hələ hadisə yoxdur.";
  }else result=HELP;
  st.lastUpdate=Math.max(st.lastUpdate,Number(update.update_id)||0);
  await save(st);
  await say(env,m.chat.id,result);
}
export async function onRequestGet({request,env}){
  const url=new URL(request.url);
  const setup=url.searchParams.get("setup");
  if(setup!==null){
    if(!env.SETUP_KEY||setup!==env.SETUP_KEY)return response("Forbidden",403);
    if(!env.WEBHOOK_SECRET)return response("Missing WEBHOOK_SECRET",500);
    try{
      const out=await telegram(env,"setWebhook",{
        url:url.origin+"/api/telegram",
        secret_token:env.WEBHOOK_SECRET,
        allowed_updates:["message"]
      });
      return response(out?"webhook registered":"unexpected response");
    }catch(e){console.error("Webhook setup failed",String(e));return response("Setup failed; check function logs",502);}
  }
  if(request.headers.get("X-Agent-Cron-Secret")){
    if(!env.CRON_SECRET||request.headers.get("X-Agent-Cron-Secret")!==env.CRON_SECRET)return response("Forbidden",403);
    try{
      const st=await load();
      if(!st)return response("KV unavailable",503);
      if(!st.auto)return response("Auto disabled");
      const now=bakuNow();
      if(![9,11,13,15,17,19].includes(now.hour))return response("Outside work hours");
      if(st.lastSlot===now.slot)return response("Already ran");
      st.lastSlot=now.slot;
      await save(st);
      return response(await preview(env,st,"automatic"));
    }catch(e){console.error("Cron failed",String(e));return response("Cron error",500);}
  }
  return response("LinkedIn Telegram Agent: webhook endpoint online (preview only)");
}
export async function onRequestPost({request,env}){
  if(!env.WEBHOOK_SECRET||request.headers.get("X-Telegram-Bot-Api-Secret-Token")!==env.WEBHOOK_SECRET)return response("Forbidden",403);
  try{const data=await request.json();await handle(env,data);return response("ok");}
  catch(e){console.error("Telegram webhook error",String(e));return response("Processing failed",500);}
}
