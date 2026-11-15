import {test,beforeEach} from 'node:test';
import assert from 'node:assert/strict';
import {makeEnvironment,installUpstream,request,admin,desktop,firstId,secondId,firstToken,secondToken,input} from './test-support.mjs';
let env,db,upstream;
const route='/v1/admin/profiles/'+firstId;
const credentials='/v1/profiles/'+firstId+'/credentials';
beforeEach(async()=>{const state=makeEnvironment();env=state.env;db=state.sqlite;upstream=installUpstream();assert.equal((await admin(env,'PUT','/v1/admin/agencykey',{api_key:input.api_key})).status,200);upstream.calls=[];});
test('serves a public login page but requires a private admin session for data',async()=>{
 const response=await request(env,'GET','/admin');assert.equal(response.status,200);assert.match(response.headers.get('content-security-policy'),/frame-ancestors 'none'/);const html=await response.text();assert.ok(html.includes('Entrar a AgencyKey Recorder Tests'));assert.ok(!html.includes(env.ADMIN_TOKEN));assert.ok(!html.includes(env.ENCRYPTION_KEY));
 for(const path of ['/v1/admin/session','/v1/admin/profiles']){
  assert.equal((await request(env,'GET',path)).status,401);
  assert.equal((await request(env,'GET',path,undefined,{'Cf-Access-Authenticated-User-Email':'owner@example.test',Authorization:'Bearer '+env.ADMIN_TOKEN},{access:{getIdentity:async()=>({email:'owner@example.test'})}})).status,401);
 }
});
test('desktop password cannot administer settings or bots',async()=>{
 for(const path of ['/v1/admin/profiles','/v1/admin/resolve','/v1/admin/access','/v1/admin/agencykey'])assert.equal((await desktop(env,'POST',path,{})).status,401);
 assert.equal((await desktop(env,'PUT','/v1/profiles/'+firstId,input)).status,403);
 assert.equal((await request(env,'GET','/v1/profiles')).status,401);
});
test('lists all pages and resolves the actual OnlyFans name instead of the CRM alias',async()=>{
 upstream.pages=2;
 const listed=await admin(env,'GET','/v1/admin/creators');assert.equal((await listed.json()).creators.length,2);
 const resolved=await admin(env,'POST','/v1/admin/resolve',{creator_id:'52'});assert.equal((await resolved.json()).creator.name,'Lilith');
 const saved=await admin(env,'PUT',route,{...input,name:'Untrusted',creator:{name:'Wrong'}});assert.equal(saved.status,200);const data=await saved.json();assert.equal(data.name,'Lilith');assert.equal(data.creator.external_id,52);assert.equal(data.revision,1);
});
test('uses canonical username when AgencyKey cannot proxy users/me',async()=>{
 upstream.meStatus=400;const response=await admin(env,'PUT',route,input);assert.equal(response.status,200);assert.equal((await response.json()).name,'@model_52');
});
test('encrypts one API globally and Telegram tokens per bot',async()=>{
 await admin(env,'PUT',route,input);
 const row=db.prepare('SELECT encrypted_secrets FROM profiles WHERE id=?').get(firstId);assert.ok(!row.encrypted_secrets.includes(firstToken));
 const settings=db.prepare("SELECT value FROM settings WHERE key='agencykey'").get();assert.ok(!settings.value.includes(input.api_key));
 for(const response of [await admin(env,'GET','/v1/admin/profiles'),await desktop(env,'GET','/v1/profiles')]){const text=await response.text();assert.ok(!text.includes('api_key'));assert.ok(!text.includes('telegram_token'));}
 const response=await desktop(env,'POST',credentials);assert.match(response.headers.get('cache-control'),/no-store/);const result=await response.json();assert.equal(result.telegram_token,firstToken);assert.equal(result.api_key,input.api_key);
});
test('global API overrides stale per-bot keys supplied by a client',async()=>{
 const response=await admin(env,'PUT',route,{...input,api_key:'ignored-per-bot-key'});assert.equal(response.status,200);assert.equal((await (await desktop(env,'POST',credentials)).json()).api_key,input.api_key);
 assert.equal((await admin(env,'PUT','/v1/admin/agencykey',{api_key:'wrong-key'})).status,400);
 assert.equal((await (await desktop(env,'POST',credentials)).json()).api_key,input.api_key);
});
test('rejects inaccessible IDs without saving a profile',async()=>{
 for(const creator_id of [88,'05',-2])assert.equal((await admin(env,'PUT',route,{...input,creator_id})).status,400);
 assert.equal(db.prepare('SELECT count(*) AS count FROM profiles').get().count,0);
});
test('one bot per model and one configuration per Telegram bot',async()=>{
 await admin(env,'PUT',route,input);
 assert.equal((await admin(env,'PUT','/v1/admin/profiles/'+secondId,{...input,telegram_token:secondToken})).status,409);
 assert.equal((await admin(env,'PUT','/v1/admin/profiles/'+secondId,{...input,creator_id:99})).status,409);
});
test('keeps token during edits and refreshes the OnlyFans name',async()=>{
 await admin(env,'PUT',route,input);upstream.ofNames[52]='Lilith actualizada';
 const response=await admin(env,'PUT',route,{creator_id:52,revision:1});assert.equal(response.status,200);assert.equal((await response.json()).name,'Lilith actualizada');
 assert.equal((await (await desktop(env,'POST',credentials)).json()).telegram_token,firstToken);
 assert.equal((await admin(env,'PUT',route,{creator_id:52,revision:1})).status,409);
});
test('deletes matching revision and blocks deleted credentials',async()=>{
 await admin(env,'PUT',route,input);
 assert.equal((await admin(env,'DELETE',route,undefined,{'If-Match':'2'})).status,409);
 assert.equal((await admin(env,'DELETE',route,undefined,{'If-Match':'1'})).status,200);
 assert.equal((await desktop(env,'POST',credentials)).status,404);
});
test('rejects bad tokens, large bodies, CSRF and invalid upstream JSON',async()=>{
 assert.equal((await admin(env,'PUT',route,{...input,telegram_token:'invalid'})).status,400);
 assert.equal((await admin(env,'PUT',route,'invalid-json')).status,400);
 assert.equal((await admin(env,'PUT',route,'x'.repeat(16385))).status,413);
 assert.equal((await admin(env,'POST','/v1/admin/access',{code:'new-password'},{Origin:'https://evil.test'})).status,403);
 upstream.invalid=true;const response=await admin(env,'PUT',route,input);assert.equal(response.status,502);assert.ok(!(await response.text()).includes(input.api_key));
});
test('ciphertext is bound to its profile identity',async()=>{
 await admin(env,'PUT',route,input);db.prepare('UPDATE profiles SET id=? WHERE id=?').run(secondId,firstId);
 assert.equal((await desktop(env,'POST','/v1/profiles/'+secondId+'/credentials')).status,500);
});
test('custom password revokes old downloads and stores only salted derived hash',async()=>{
 await admin(env,'PUT',route,input);
 const code='mi-contraseña-nueva';assert.equal((await admin(env,'POST','/v1/admin/access',{code})).status,200);
 const saved=db.prepare("SELECT value FROM settings WHERE key='app_access'").get().value;assert.ok(!saved.includes(code));assert.ok(saved.includes('pbkdf2'));
 assert.equal((await desktop(env,'GET','/v1/profiles')).status,401);assert.equal((await desktop(env,'POST',credentials,undefined,code)).status,200);
 assert.equal((await admin(env,'GET','/v1/admin/profiles')).status,200);
 env.ACCESS_TOKEN='new-cloudflare-secret';assert.equal((await desktop(env,'GET','/v1/profiles')).status,200);assert.equal((await desktop(env,'POST',credentials,undefined,code)).status,401);
});
test('limits failed desktop password attempts',async()=>{
 for(let i=0;i<10;i++)assert.equal((await desktop(env,'GET','/v1/profiles',undefined,'wrong')).status,401);
 assert.equal((await desktop(env,'GET','/v1/profiles',undefined,'wrong')).status,429);
});
test('automatically migrates the existing shared API without exposing it',async()=>{
 // Build a legacy encrypted profile using the same AES-GCM envelope.
 db.prepare("DELETE FROM settings WHERE key='agencykey'").run();
 const iv=crypto.getRandomValues(new Uint8Array(12));const raw=Buffer.from(env.ENCRYPTION_KEY,'base64');const key=await crypto.subtle.importKey('raw',raw,'AES-GCM',false,['encrypt']);
 const ciphertext=await crypto.subtle.encrypt({name:'AES-GCM',iv,additionalData:new TextEncoder().encode(firstId)},key,new TextEncoder().encode(JSON.stringify({api_key:input.api_key,telegram_token:firstToken})));
 db.prepare('INSERT INTO profiles(id,name,bot_id,creator_id,creator_name,encrypted_secrets,updated_at) VALUES(?,?,?,?,?,?,?)').run(firstId,'Lilith','12345678',52,'Lilith',JSON.stringify({v:1,iv:Buffer.from(iv).toString('base64'),ciphertext:Buffer.from(ciphertext).toString('base64')}),'now');
 assert.equal((await admin(env,'GET','/v1/admin/settings')).status,200);assert.ok(db.prepare("SELECT value FROM settings WHERE key='agencykey'").get());
 assert.equal((await (await desktop(env,'POST',credentials)).json()).api_key,input.api_key);
});

test('admin login uses a secure server-side session and logout revokes it',async()=>{
 assert.equal((await request(env,'POST','/v1/admin/login',{password:env.ACCESS_TOKEN})).status,401);
 const login=await request(env,'POST','/v1/admin/login',{password:env.ADMIN_TOKEN});assert.equal(login.status,200);
 const raw=login.headers.get('set-cookie');assert.match(raw,/HttpOnly; Secure; SameSite=Strict/);
 const headers={Cookie:raw.split(';')[0]};assert.equal((await request(env,'GET','/v1/admin/session',undefined,headers)).status,200);
 assert.equal((await request(env,'GET','/v1/admin/session',undefined,{Cookie:headers.Cookie+'x'})).status,401);
 assert.equal((await request(env,'POST','/v1/admin/logout',{},headers)).status,200);
 assert.equal((await request(env,'GET','/v1/admin/session',undefined,headers)).status,401);
});
test('private setup link creates the admin password once, with no shared app access',async()=>{
 const token='private-setup-token-for-owner-only';env.ADMIN_SETUP=JSON.stringify({token,expires:Date.now()+3600000});
 assert.equal((await request(env,'POST','/v1/admin/setup',{token:'wrong',password:'private-new-password'})).status,403);
 const response=await request(env,'POST','/v1/admin/setup',{token,password:'private-new-password'});assert.equal(response.status,200);
 assert.equal((await request(env,'POST','/v1/admin/setup',{token,password:'another-private-password'})).status,409);
 assert.equal((await request(env,'POST','/v1/admin/login',{password:env.ADMIN_TOKEN})).status,401);
 assert.equal((await request(env,'POST','/v1/admin/login',{password:'private-new-password'})).status,200);
 assert.equal((await desktop(env,'GET','/v1/profiles',undefined,'private-new-password')).status,401);
 const saved=db.prepare("SELECT value FROM settings WHERE key='admin_access'").get().value;assert.ok(!saved.includes('private-new-password'));assert.ok(!saved.includes(token));
});
test('rejects expired setup links and matching admin and app passwords',async()=>{
 const token='private-bootstrap';env.ADMIN_SETUP=JSON.stringify({token,expires:Date.now()-1});
 assert.equal((await request(env,'POST','/v1/admin/setup',{token,password:'private-new-password'})).status,403);
 env.ADMIN_SETUP=JSON.stringify({token,expires:Date.now()+3600000});
 assert.equal((await request(env,'POST','/v1/admin/setup',{token,password:env.ACCESS_TOKEN})).status,400);
 assert.equal((await admin(env,'POST','/v1/admin/access',{code:env.ADMIN_TOKEN})).status,400);
});
test('changing admin password invalidates prior sessions while preserving app access',async()=>{
 const login=await request(env,'POST','/v1/admin/login',{password:env.ADMIN_TOKEN});const headers={Cookie:login.headers.get('set-cookie').split(';')[0]};
 assert.equal((await request(env,'PUT','/v1/admin/password',{current_password:'wrong',password:'another-private-password'},headers)).status,400);
 const changed=await request(env,'PUT','/v1/admin/password',{current_password:env.ADMIN_TOKEN,password:'another-private-password'},headers);assert.equal(changed.status,200);
 assert.equal((await request(env,'GET','/v1/admin/session',undefined,headers)).status,401);
 assert.equal((await request(env,'GET','/v1/admin/session',undefined,{Cookie:changed.headers.get('set-cookie').split(';')[0]})).status,200);
 assert.equal((await desktop(env,'GET','/v1/profiles')).status,200);
});
test('rate limits admin logins and rejects cross-origin login and setup',async()=>{
 assert.equal((await request(env,'POST','/v1/admin/login',{password:env.ADMIN_TOKEN},{Origin:'https://evil.test'})).status,403);
 assert.equal((await request(env,'POST','/v1/admin/setup',{},{Origin:'https://evil.test'})).status,403);
 for(let i=0;i<10;i++)assert.equal((await request(env,'POST','/v1/admin/login',{password:'wrong'})).status,401);
 assert.equal((await request(env,'POST','/v1/admin/login',{password:env.ADMIN_TOKEN})).status,429);
});

test('Workers runtime connects to AgencyKey without unsupported redirect mode or leaking keys',async()=>{
 const {Miniflare,Response:RuntimeResponse}=await import('miniflare');
 const {build}=await import('esbuild');
 const {readFileSync}=await import('node:fs');
 const {fileURLToPath}=await import('node:url');
 const bundle=await build({entryPoints:[fileURLToPath(new URL('./worker.mjs',import.meta.url))],bundle:true,write:false,format:'esm',platform:'browser',target:'es2022',external:['node:*','cloudflare:*']});
 let redirect=false;const calls=[];
 const runtime=new Miniflare({modules:true,script:bundle.outputFiles[0].text,compatibilityDate:'2026-07-30',compatibilityFlags:['nodejs_compat'],d1Databases:{DB:'test-db'},bindings:{ADMIN_TOKEN:env.ADMIN_TOKEN,ACCESS_TOKEN:env.ACCESS_TOKEN,ENCRYPTION_KEY:env.ENCRYPTION_KEY},outboundService:async req=>{
  const url=new URL(req.url);calls.push(url.href);
  assert.equal(url.origin,'https://app.agencykey.com');assert.equal(req.headers.get('x-public-api-key'),input.api_key);
  if(redirect)return new RuntimeResponse(null,{status:302,headers:{Location:'https://untrusted.example/collect'}});
  return new RuntimeResponse(JSON.stringify({data:[{name:'CRM alias',account:{externalId:52,username:'model_52'}}],pagination:{pages:1}}),{headers:{'Content-Type':'application/json'}});
 }});
 try {
  const database=await runtime.getD1Database('DB');
  const schema=readFileSync(new URL('./schema.sql',import.meta.url),'utf8');for(const sql of schema.split(';').map(x=>x.trim()).filter(Boolean))await database.prepare(sql).run();
  const login=await runtime.dispatchFetch('https://dropper.test/v1/admin/login',{method:'POST',headers:{Origin:'https://dropper.test','Content-Type':'application/json'},body:JSON.stringify({password:env.ADMIN_TOKEN})});assert.equal(login.status,200);
  const cookie=login.headers.get('set-cookie').split(';')[0];
  const save=()=>runtime.dispatchFetch('https://dropper.test/v1/admin/agencykey',{method:'PUT',headers:{Origin:'https://dropper.test','Content-Type':'application/json',Cookie:cookie},body:JSON.stringify({api_key:input.api_key})});
  const result=await save();assert.equal(result.status,200);assert.equal((await result.json()).creators[0].username,'model_52');assert.equal(calls.length,1);
  redirect=true;const rejected=await save();assert.equal(rejected.status,502);assert.match((await rejected.json()).error,/redirección/);assert.equal(calls.length,2);
 }finally{await runtime.dispose();}
});

test('accepts UTF-8 app passwords encoded by the Windows client without breaking Bearer access',async()=>{
 const code='Contraseña 🔐 2026';
 assert.equal((await admin(env,'POST','/v1/admin/access',{code})).status,200);
 const encoded=Buffer.from(code,'utf8').toString('base64url');
 assert.equal((await request(env,'GET','/v1/profiles',undefined,{Authorization:'Dropper '+encoded})).status,200);
 assert.equal((await desktop(env,'GET','/v1/profiles')).status,401);
 assert.equal((await request(env,'GET','/v1/profiles',undefined,{Authorization:'Dropper invalid%%'})).status,401);
});


test('desktop update checks return only authenticated profile revision metadata',async()=>{
 const path='/v1/profile-revisions';
 assert.equal((await request(env,'GET',path)).status,401);
 assert.deepEqual(await (await desktop(env,'GET',path)).json(),{profiles:[]});
 const saved=await (await admin(env,'PUT',route,input)).json();
 const {profiles}=await (await desktop(env,'GET',path)).json();
 assert.deepEqual(profiles,[{id:firstId,revision:saved.revision,updated_at:saved.updated_at}]);
});

test('feed check is private and requires the requested model and a saved session',async()=>{
 const path='/v1/admin/recording-session/feed/'+firstId;
 assert.equal((await desktop(env,'POST',path,{})).status,401);
 assert.equal((await admin(env,'POST',path,{})).status,404);
 assert.equal((await admin(env,'PUT',route,input)).status,200);
 const response=await admin(env,'POST',path,{});
 assert.deepEqual(await response.json(),{status:'no_session'});
});

test('admin queues a local Chrome connection and only the claiming app can complete it',async()=>{
 const root='/v1/admin/recording-session';
 const claim='/v1/recording-desktop-job';
 const login=await request(env,'POST','/v1/admin/login',{password:env.ADMIN_TOKEN});
 const cookie={Cookie:login.headers.get('set-cookie').split(';')[0]};
 const queued=await request(env,'POST',root+'/connect',{},cookie);
 assert.equal(queued.status,202);
 const {id}=await queued.json();
 assert.equal((await request(env,'POST',claim)).status,401);
 const {job}=await (await desktop(env,'POST',claim)).json();
 assert.deepEqual(job,{id,kind:'connect',claim:job.claim});
 assert.deepEqual(await (await desktop(env,'POST',claim)).json(),{job:null});
 assert.deepEqual(await (await desktop(env,'PUT',claim,{id,claim:'invalid',status:'ready'})).json(),{active:false});
 assert.equal((await (await request(env,'POST',root+'/check',{id},cookie)).json()).status,'running');
 const state={cookies:[{name:'session',domain:'.agencykey.com',value:'test-only'}],origins:[]};
 assert.equal((await desktop(env,'PUT',claim,{id,claim:job.claim,status:'ready',state})).status,200);
 assert.equal((await (await request(env,'POST',root+'/check',{id},cookie)).json()).status,'ready');
 assert.equal((await (await admin(env,'POST',root+'/check',{id})).json()).status,'expired');
 const result=await (await desktop(env,'GET','/v1/recording-session')).json();
 assert.deepEqual(result.state,state);
 assert.equal((await admin(env,'PUT',route,input)).status,200);
 const feed=await (await request(env,'POST',root+'/feed/'+firstId,{},cookie)).json();
 const next=(await (await desktop(env,'POST',claim)).json()).job;
 assert.equal(next.kind,'feed');
 assert.equal(next.creator_id,52);
 assert.equal(next.creator_username,'model_52');
 assert.equal(next.id,feed.id);
 assert.equal((await (await request(env,'POST',root+'/cancel',{id:feed.id},cookie)).json()).status,'cancelled');
 assert.deepEqual(await (await desktop(env,'PUT',claim,{id:feed.id,claim:next.claim})).json(),{active:false});
});

test('persists profile checks across session refreshes and invalidates them when reconnecting', async()=>{
 const root='/v1/admin/recording-session';
 const claim='/v1/recording-desktop-job';
 const state={cookies:[{name:'session',domain:'.agencykey.com',value:'test-only'}],origins:[]};
 const login=await request(env,'POST','/v1/admin/login',{password:env.ADMIN_TOKEN});
 const cookie={Cookie:login.headers.get('set-cookie').split(';')[0]};
 const web=async(method,path,data)=>(await request(env,method,path,data,cookie)).json();
 const profiles='/v1/admin/profiles';
 const status=async()=>(await web('GET',profiles)).profiles[0].feed.status;
 const complete=async(path,result)=>{
   const queued=await web('POST',root+path,{});
   const {job}=await (await desktop(env,'POST',claim)).json();
   assert.equal(job.id,queued.id);
   await desktop(env,'PUT',claim,{id:job.id,claim:job.claim,...result});
   return web('POST',root+'/check',{id:job.id});
 };
 await web('PUT',profiles+'/'+firstId,input);
 assert.equal(await status(),'no_session');
 await complete('/connect',{status:'ready',state});
 assert.equal(await status(),'pending');
 assert.equal((await complete('/feed/'+firstId,{status:'ready'})).status,'desktop_update_required');
 assert.equal((await complete('/feed/'+firstId,{status:'feed_unverified',feed_checked:true})).status,'desktop_update_required');
 assert.equal(await status(),'desktop_update_required');
 assert.equal((await complete('/feed/'+firstId,{status:'ready',profile_checked:true})).status,'desktop_update_required');
 const mismatch=await complete('/feed/'+firstId,{status:'ready',identity_checked:true,observed_username:'otra_modelo'});
 assert.equal(mismatch.status,'wrong_profile');
 assert.equal(mismatch.expected_username,'model_52');
 assert.equal(mismatch.observed_username,'otra_modelo');
 assert.equal(await status(),'wrong_profile');
 assert.equal((await complete('/feed/'+firstId,{status:'ready',identity_checked:true})).status,'profile_unverified');
 assert.equal((await complete('/feed/'+firstId,{status:'ready',identity_checked:true,observed_username:'Model_52'})).status,'ready');
 const session=await (await desktop(env,'GET','/v1/recording-session')).json();
 assert.equal((await desktop(env,'PUT','/v1/recording-session',{state,revision:session.revision})).status,200);
 assert.equal(await status(),'ready');
 await complete('/connect',{status:'ready',state});
 assert.equal(await status(),'pending');
});
