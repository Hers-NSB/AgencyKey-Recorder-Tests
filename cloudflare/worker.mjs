import {adminPage} from './admin-page.mjs';
import {cleanStorageState} from './recording-session.mjs';

const encoder = new TextEncoder();
const columns = 'id, name, bot_id, creator_id, creator_name, creator_username, revision, updated_at';

class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function json(data, status = 200) {
  return Response.json(data, {status, headers: {
    'Cache-Control': 'no-store, private',
    'Pragma': 'no-cache',
    'X-Content-Type-Options': 'nosniff',
    'Strict-Transport-Security': 'max-age=31536000',
  }});
}

async function digest(value) {
  return crypto.subtle.digest('SHA-256', encoder.encode(value));
}

async function equal(provided, expected) {
  return crypto.subtle.timingSafeEqual(await digest(provided), await digest(expected));
}

async function accessHash(env) {
  const source = encode(await digest(env.ACCESS_TOKEN));
  const row = await env.DB.prepare("SELECT value FROM settings WHERE key = 'app_access'").first();
  if (row) {
    const saved = JSON.parse(row.value);
    if (saved.source === source) return saved.hash;
  }
  return source;
}

async function authorize(request, env) {
  if (!env.ACCESS_TOKEN || !env.ENCRYPTION_KEY) throw new ApiError(503, 'Servicio sin configurar');
  const value = request.headers.get('Authorization') || '';
  let provided = value.startsWith('Bearer ') ? value.slice(7, 520) : '';
  if (value.startsWith('Dropper ')) {
    try {
      const encoded = value.slice(8);
      if (encoded.length>2048 || !/^[A-Za-z0-9_-]+$/.test(encoded)) throw new Error();
      provided = new TextDecoder('utf-8',{fatal:true}).decode(fromBase64url(encoded));
    } catch {throw new ApiError(401,'Contraseña incorrecta o cambiada');}
  }
  const ip = request.headers.get('CF-Connecting-IP') || 'unknown';
  const attemptId = 'app:' + encode(await digest(ip));
  const blocked = await env.DB.prepare('SELECT attempts, expires FROM login_attempts WHERE id = ?').bind(attemptId).first();
  if (blocked?.expires > Date.now() && blocked.attempts >= 10) throw new ApiError(429, 'Demasiados intentos, espera 15 minutos');
  const row = await env.DB.prepare("SELECT value FROM settings WHERE key = 'app_access'").first();
  const saved = row ? JSON.parse(row.value) : null;
  const source = encode(await digest(env.ACCESS_TOKEN));
  let valid;
  if (saved?.source === source && saved.kind === 'pbkdf2') {
    valid = await equal(await passwordHash(provided, saved.salt), saved.hash);
  } else {
    valid = await equal(encode(await digest(provided)), await accessHash(env));
  }
  if (!valid) {
    const ip = request.headers.get('CF-Connecting-IP') || 'unknown';
    const id = 'app:' + encode(await digest(ip));
    const now = Date.now();
    const attempts = await env.DB.prepare(`INSERT INTO login_attempts(id, attempts, expires) VALUES (?, 1, ?)
      ON CONFLICT(id) DO UPDATE SET attempts = CASE WHEN expires < ? THEN 1 ELSE attempts+1 END,
      expires = CASE WHEN expires < ? THEN excluded.expires ELSE expires END RETURNING attempts`).bind(id, now+900000, now, now).first();
    throw new ApiError(attempts.attempts > 10 ? 429 : 401, attempts.attempts > 10 ? 'Demasiados intentos, espera 15 minutos' : 'Contraseña incorrecta o cambiada');
  }
}

async function passwordHash(password, salt) {
  const material = await crypto.subtle.importKey('raw', encoder.encode(password), 'PBKDF2', false, ['deriveBits']);
  return encode(await crypto.subtle.deriveBits({name:'PBKDF2', hash:'SHA-256', salt:decode(salt), iterations:100000}, material, 256));
}

async function key(env) {
  const raw = Uint8Array.from(atob(env.ENCRYPTION_KEY), char => char.charCodeAt(0));
  return crypto.subtle.importKey('raw', raw, 'AES-GCM', false, ['encrypt', 'decrypt']);
}

function encode(bytes) {
  const data = new Uint8Array(bytes);
  let result = '';
  for (let i=0; i<data.length; i+=8192) result += String.fromCharCode(...data.subarray(i,i+8192));
  return btoa(result);
}

function decode(text) {
  return Uint8Array.from(atob(text), char => char.charCodeAt(0));
}

async function encrypt(value, id, env) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = await crypto.subtle.encrypt(
    {name: 'AES-GCM', iv, additionalData: encoder.encode(id)}, await key(env), encoder.encode(JSON.stringify(value)));
  return JSON.stringify({v: 1, iv: encode(iv), ciphertext: encode(ciphertext)});
}

async function decrypt(value, id, env) {
  const data = JSON.parse(value);
  if (data.v !== 1) throw new Error('Unsupported secret format');
  const plaintext = await crypto.subtle.decrypt(
    {name: 'AES-GCM', iv: decode(data.iv), additionalData: encoder.encode(id)}, await key(env), decode(data.ciphertext));
  return JSON.parse(new TextDecoder().decode(plaintext));
}

async function body(request, maximum=16384) {
  const reader = request.body?.getReader();
  if (!reader) throw new ApiError(400, 'Configuración vacía');
  let size = 0;
  const chunks = [];
  while (true) {
    const part = await reader.read();
    if (part.done) break;
    size += part.value.byteLength;
    if (size > maximum) {
      await reader.cancel();
      throw new ApiError(413, 'Configuración demasiado grande');
    }
    chunks.push(part.value);
  }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {bytes.set(chunk, offset); offset += chunk.length;}
  try {
    const data = JSON.parse(new TextDecoder().decode(bytes));
    if (!data || Array.isArray(data) || typeof data !== 'object') throw new Error();
    return data;
  } catch {throw new ApiError(400, 'Configuración inválida');}
}

function text(value, name, maximum) {
  if (typeof value !== 'string' || !value.trim() || value.length > maximum || /[\r\n\x00]/.test(value)) {
    throw new ApiError(400, `${name} inválido`);
  }
  return value.trim();
}

function profile(row) {
  return {
    id: row.id, name: row.name, bot_id: row.bot_id,
    creator: {external_id: row.creator_id, name: row.creator_name, username: row.creator_username},
    revision: row.revision, updated_at: row.updated_at,
  };
}

function base64url(bytes) {
  return encode(bytes).replaceAll('+', '-').replaceAll('/', '_').replaceAll('=', '');
}

function fromBase64url(value) {
  const str = value.replaceAll('-', '+').replaceAll('_', '/');
  return decode(str + '='.repeat((4-str.length%4)%4));
}

function originCheck(request) {
  const origin = request.headers.get('Origin');
  if (origin !== new URL(request.url).origin) throw new ApiError(403, 'Solicitud de otro origen bloqueada');
}

async function adminState(env) {
  const row = await env.DB.prepare("SELECT value FROM settings WHERE key = 'admin_access'").first();
  if (row) return JSON.parse(row.value);
  if (!env.ADMIN_TOKEN || env.ADMIN_TOKEN.length < 24) throw new ApiError(503, 'Acceso de administrador sin configurar');
  return {version:encode(await digest(env.ADMIN_TOKEN)), setup_used:false};
}

function sessionToken(request) {
  const cookie = (request.headers.get('Cookie') || '').split(';').map(x=>x.trim()).find(x=>x.startsWith('__Host-recorder_admin='));
  const token = cookie?.slice('__Host-recorder_admin='.length);
  return token && /^[A-Za-z0-9_-]{43}$/.test(token) ? token : null;
}

async function sessionId(token) {
  return 'admin_session:'+encode(await digest(token));
}

async function authorizeAdmin(request, env) {
  const token = sessionToken(request);
  if (!token) throw new ApiError(401, 'Introduce la contraseña de administrador');
  const row = await env.DB.prepare('SELECT value FROM settings WHERE key = ?').bind(await sessionId(token)).first();
  if (!row) throw new ApiError(401, 'Vuelve a iniciar sesión');
  const session = JSON.parse(row.value);
  if (session.expires <= Date.now() || session.version !== (await adminState(env)).version) throw new ApiError(401, 'La sesión caducó. Vuelve a entrar');
}

async function issueSession(env) {
  const token = base64url(crypto.getRandomValues(new Uint8Array(32)));
  const now = Date.now();
  const state = await adminState(env);
  await env.DB.prepare("DELETE FROM settings WHERE key LIKE 'admin_session:%' AND CAST(json_extract(value,'$.expires') AS INTEGER) < ?").bind(now).run();
  await env.DB.prepare('INSERT INTO settings(key,value) VALUES (?,?)').bind(await sessionId(token),JSON.stringify({expires:now+28800000,version:state.version})).run();
  const response = json({authenticated:true});
  response.headers.set('Set-Cookie',`__Host-recorder_admin=${token}; Path=/; Max-Age=28800; HttpOnly; Secure; SameSite=Strict`);
  return response;
}

async function loginLimit(request,env) {
  const id = 'admin:'+encode(await digest(request.headers.get('CF-Connecting-IP') || 'unknown'));
  const now = Date.now();
  const attempts = await env.DB.prepare(`INSERT INTO login_attempts(id, attempts, expires) VALUES (?, 1, ?)
    ON CONFLICT(id) DO UPDATE SET attempts = CASE WHEN expires < ? THEN 1 ELSE attempts+1 END,
    expires = CASE WHEN expires < ? THEN excluded.expires ELSE expires END RETURNING attempts`).bind(id,now+900000,now,now).first();
  if (attempts.attempts > 10) throw new ApiError(429,'Demasiados intentos, espera 15 minutos');
  return id;
}

async function matchesAdmin(password,env) {
  const state = await adminState(env);
  return state.hash ? equal(await passwordHash(password,state.salt),state.hash) : equal(password,env.ADMIN_TOKEN);
}

async function matchesApp(password,env) {
  const row = await env.DB.prepare("SELECT value FROM settings WHERE key = 'app_access'").first();
  const saved = row ? JSON.parse(row.value) : null;
  const source = encode(await digest(env.ACCESS_TOKEN));
  return saved?.source===source && saved.kind==='pbkdf2' ? equal(await passwordHash(password,saved.salt),saved.hash) : equal(encode(await digest(password)),await accessHash(env));
}

async function newAdminPassword(password,env) {
  if (typeof password!=='string' || password.length<12 || password.length>256 || /[\r\n\x00]/.test(password)) throw new ApiError(400,'Usa una contraseña de entre 12 y 256 caracteres');
  if (await matchesApp(password,env)) throw new ApiError(400,'Usa una contraseña distinta de la contraseña de las apps');
  const salt = encode(crypto.getRandomValues(new Uint8Array(16)));
  return {salt,hash:await passwordHash(password,salt),version:crypto.randomUUID(),setup_used:true};
}

async function adminLogin(request,env,setup=false) {
  originCheck(request);
  const attempt = await loginLimit(request,env);
  const input = await body(request);
  if (setup) {
    let config;
    try {config=JSON.parse(env.ADMIN_SETUP || '{}');} catch {config={};}
    if (typeof input.token!=='string' || !config.token || !(config.expires > Date.now()) || !await equal(input.token,config.token)) throw new ApiError(403,'El enlace de configuración no es válido o caducó');
    const state = await newAdminPassword(input.password,env);
    const result = await env.DB.prepare(`INSERT INTO settings(key,value) VALUES ('admin_access',?)
      ON CONFLICT(key) DO UPDATE SET value=excluded.value WHERE json_extract(settings.value,'$.setup_used') IS NOT 1 RETURNING key`).bind(JSON.stringify(state)).first();
    if (!result) throw new ApiError(409,'La contraseña ya fue creada. Entra con ella');
  } else {
    if (typeof input.password!=='string' || input.password.length>256 || !await matchesAdmin(input.password,env)) throw new ApiError(401,'Contraseña de administrador incorrecta');
    if (await matchesApp(input.password,env)) throw new ApiError(403,'Configura una contraseña de administrador distinta de la de las apps');
  }
  await env.DB.prepare('DELETE FROM login_attempts WHERE id = ?').bind(attempt).run();
  return issueSession(env);
}

async function globalApi(env) {
  const saved = await env.DB.prepare("SELECT value FROM settings WHERE key = 'agencykey'").first();
  if (saved) return (await decrypt(saved.value, 'agencykey', env)).api_key;
  const rows = await env.DB.prepare('SELECT id, encrypted_secrets FROM profiles').all();
  const keys = new Set();
  for (const row of rows.results) keys.add((await decrypt(row.encrypted_secrets, row.id, env)).api_key);
  if (keys.size !== 1) throw new ApiError(409, 'Configura la API única de AgencyKey en Ajustes');
  const apiKey = [...keys][0];
  const value = await encrypt({api_key:apiKey}, 'agencykey', env);
  await env.DB.prepare("INSERT INTO settings(key,value) VALUES ('agencykey',?) ON CONFLICT(key) DO NOTHING").bind(value).run();
  return apiKey;
}

async function upstreamJson(url, headers, service) {
  let response;
  try {response = await fetch(url, {headers, signal: AbortSignal.timeout(20000), redirect: 'manual'});}
  catch {throw new ApiError(502, `No se pudo conectar con ${service}`);}
  if (response.status >= 300 && response.status < 400) {
    throw new ApiError(502, `${service} devolvió una redirección inesperada`);
  }
  if (!response.ok) {
    if ([401,403].includes(response.status)) throw new ApiError(400, `Revisa las credenciales y permisos de ${service}`);
    throw new ApiError(502, `${service} respondió HTTP ${response.status}`);
  }
  const reader = response.body.getReader();
  let size = 0;
  const chunks = [];
  while (true) {
    const next = await reader.read();
    if (next.done) break;
    size += next.value.length;
    if (size > 1048576) {await reader.cancel(); throw new ApiError(502, `Respuesta demasiado grande de ${service}`);}
    chunks.push(next.value);
  }
  const data = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {data.set(chunk, offset); offset += chunk.length;}
  try {return JSON.parse(new TextDecoder().decode(data));}
  catch {throw new ApiError(502, `Respuesta inválida de ${service}`);}
}

function creatorId(value) {
  if (!/^[1-9][0-9]{0,15}$/.test(String(value)) || !Number.isSafeInteger(Number(value))) {
    throw new ApiError(400, 'Introduce el ID numérico de OnlyFans de la modelo');
  }
  return Number(value);
}

async function listCreators(apiKey) {
  const creators = [];
  for (let page=1; page<=100; page++) {
    const data = await upstreamJson(`https://app.agencykey.com/api/v1/onlyfans/creators?page=${page}&limit=100`,
      {'x-public-api-key':apiKey, 'Accept':'application/json'}, 'AgencyKey');
    if (!Array.isArray(data.data)) throw new ApiError(502, 'No se pudo leer la lista de modelos');
    for (const item of data.data) {
      const account = item?.account;
      if (!account?.username || !Number.isSafeInteger(Number(account.externalId))) continue;
      // The CRM label (item.name) can be edited; use the OnlyFans username.
      creators.push({external_id:creatorId(account.externalId), name:'@'+account.username, username:account.username});
    }
    const pages = data.pagination?.pages ?? 1;
    if (!Number.isSafeInteger(pages) || pages < 1) throw new ApiError(502, 'Paginación inválida de AgencyKey');
    if (page >= pages) return creators;
  }
  throw new ApiError(502, 'La lista de modelos está incompleta');
}

async function resolveCreator(apiKey, id) {
  const creator = (await listCreators(apiKey)).find(x=>x.external_id===id);
  if (!creator) throw new ApiError(400, 'La modelo no está disponible para la API de AgencyKey');
  try {
    const data = await upstreamJson(`https://app.agencykey.com/api/v1/onlyfans/${id}/api2/v2/users/me`,
      {'x-public-api-key':apiKey, 'Accept':'application/json'}, 'OnlyFans');
    if (Number(data.id)!==id) throw new ApiError(502, 'OnlyFans devolvió otra modelo');
    return {external_id:id, name:text(data.name, 'Nombre de OnlyFans',120), username:text(data.username, 'Usuario de OnlyFans',120)};
  } catch (error) {
    // Some AgencyKey accounts cannot proxy users/me. The canonical username
    // remains authoritative; an editable CRM alias must never replace it.
    if (error instanceof ApiError && error.status===502 && error.message==='OnlyFans respondió HTTP 400') return creator;
    throw error;
  }
}

async function verifyBot(token) {
  if (!/^\d{5,20}:[A-Za-z0-9_-]{20,200}$/.test(token)) throw new ApiError(400, 'Token de Telegram inválido');
  return token.split(':')[0];
}

async function listProfiles(env) {
  const result = await env.DB.prepare(`SELECT ${columns} FROM profiles ORDER BY name COLLATE NOCASE`).all();
  return json({profiles: result.results.map(profile), recording_session:await sharedSession(env)});
}

export async function sharedSession(env, includeState=false) {
  const row = await env.DB.prepare("SELECT value FROM settings WHERE key = 'recording_session'").first();
  if (!row) return {configured:false, revision:null};
  const value = JSON.parse(row.value);
  return {configured:true, revision:value.revision, updated_at:value.updated_at,
    ...(includeState ? {state:await decrypt(value.sealed,'recording_session',env)} : {})};
}

export async function saveSharedSession(env, state, revision) {
  try {state=cleanStorageState(state);} catch {throw new ApiError(400,'Sesión de AgencyKey inválida');}
  const value={revision:crypto.randomUUID(),updated_at:new Date().toISOString(),sealed:await encrypt(state,'recording_session',env)};
  const saved=await env.DB.prepare(`INSERT INTO settings(key,value) VALUES ('recording_session',?)
    ON CONFLICT(key) DO UPDATE SET value=excluded.value WHERE json_extract(settings.value,'$.revision') = ? RETURNING key`)
    .bind(JSON.stringify(value),revision).first();
  if (!saved) throw new ApiError(409,'La sesión compartida cambió. Actualiza antes de volver a conectar');
  return {configured:true,revision:value.revision,updated_at:value.updated_at};
}

const desktopJobKey = 'recording_desktop_job';
const desktopResults = new Set(['ready','login_required','unavailable','feed_unverified','connection_error','cancelled']);

async function readDesktopJob(env) {
  const row = await env.DB.prepare('SELECT value FROM settings WHERE key = ?').bind(desktopJobKey).first();
  return row ? {raw:row.value, job:JSON.parse(row.value)} : null;
}

async function replaceDesktopJob(env, entry, job) {
  const value = JSON.stringify(job);
  const result = entry
    ? await env.DB.prepare('UPDATE settings SET value = ? WHERE key = ? AND value = ? RETURNING key')
      .bind(value,desktopJobKey,entry.raw).first()
    : await env.DB.prepare('INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO NOTHING RETURNING key')
      .bind(desktopJobKey,value).first();
  return Boolean(result);
}

function jobStatus(job) {
  if (job.expires<=Date.now() && ['queued','running','finishing'].includes(job.status)) {
    return job.status==='queued' ? 'desktop_offline' : 'expired';
  }
  return job.status;
}

async function recordingAdmin(request, env, path) {
  const root='/v1/admin/recording-session';
  if (path===root && request.method==='GET') return json(await sharedSession(env));
  const owner=await sessionId(sessionToken(request));
  const entry=await readDesktopJob(env);
  const feed=path.match(/^\/v1\/admin\/recording-session\/feed\/([a-f0-9-]{36})$/);
  const connect=path===root+'/connect';
  if (request.method==='POST' && (connect || feed)) {
    if (entry && ['queued','running','finishing'].includes(jobStatus(entry.job))) {
      throw new ApiError(409,'Ya hay una solicitud de Chrome en curso');
    }
    const profile=feed
      ? await env.DB.prepare('SELECT creator_id FROM profiles WHERE id = ?').bind(feed[1]).first()
      : null;
    if (feed && !profile) throw new ApiError(404,'La configuración de la modelo ya no existe');
    const session=await sharedSession(env);
    if (feed && !session.configured) return json({status:'no_session'});
    const job={id:crypto.randomUUID(),owner,kind:connect?'connect':'feed',
      ...(profile?{creator_id:profile.creator_id}:{}),revision:session.revision,status:'queued',expires:Date.now()+45000};
    if (!await replaceDesktopJob(env,entry,job)) throw new ApiError(409,'Ya hay una solicitud de Chrome en curso');
    return json({id:job.id,status:job.status},202);
  }
  if (request.method==='POST' && [root+'/check',root+'/cancel'].includes(path)) {
    const {id}=await body(request);
    if (!entry || entry.job.id!==id || entry.job.owner!==owner) return json({status:'expired'});
    const status=jobStatus(entry.job);
    if (path.endsWith('/cancel') && ['queued','running'].includes(status)) {
      const cancelled=await replaceDesktopJob(env,entry,{...entry.job,status:'cancelled'});
      return json({status:cancelled?'cancelled':'finishing'});
    }
    return json({status,checked_at:entry.job.checked_at});
  }
  throw new ApiError(405,'Método no permitido');
}

async function desktopRecordingJob(request,env) {
  const entry=await readDesktopJob(env);
  if (request.method==='POST') {
    if (!entry || jobStatus(entry.job)!=='queued') return json({job:null});
    const job={...entry.job,status:'running',claim:crypto.randomUUID(),expires:Date.now()+300000};
    if (!await replaceDesktopJob(env,entry,job)) return json({job:null});
    const {id,claim,kind,creator_id}=job;
    return json({job:{id,claim,kind,creator_id}});
  }
  if (request.method!=='PUT') throw new ApiError(405,'Método no permitido');
  const input=await body(request,524288);
  if (!entry || entry.job.id!==input.id || entry.job.claim!==input.claim || jobStatus(entry.job)!=='running') {
    return json({active:false});
  }
  if (!input.status) return json({active:true});
  if (!desktopResults.has(input.status)) throw new ApiError(400,'Resultado de Chrome inválido');
  const job={...entry.job,status:input.status,checked_at:new Date().toISOString()};
  if (job.kind==='connect' && input.status==='ready') {
    const finishing={...entry.job,status:'finishing',expires:Date.now()+30000};
    if (!await replaceDesktopJob(env,entry,finishing)) return json({active:false});
    try {await saveSharedSession(env,input.state,job.revision);}
    catch {job.status='connection_error';}
    await replaceDesktopJob(env,{raw:JSON.stringify(finishing)},job);
  } else if (!await replaceDesktopJob(env,entry,job)) {
    return json({active:false});
  }
  return json({active:false});
}

async function adminHandle(request, env, path) {
  if (path === '/v1/admin/login' && request.method === 'POST') return adminLogin(request,env);
  if (path === '/v1/admin/setup' && request.method === 'POST') return adminLogin(request,env,true);
  await authorizeAdmin(request, env);
  if (request.method !== 'GET') originCheck(request);
  if (path.startsWith('/v1/admin/recording-session')) return recordingAdmin(request,env,path);
  if (path === '/v1/admin/logout' && request.method === 'POST') {
    await env.DB.prepare('DELETE FROM settings WHERE key = ?').bind(await sessionId(sessionToken(request))).run();
    const response=json({authenticated:false});
    response.headers.set('Set-Cookie','__Host-recorder_admin=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Strict');
    return response;
  }
  if (path === '/v1/admin/password' && request.method === 'PUT') {
    const input=await body(request);
    if (typeof input.current_password!=='string' || !await matchesAdmin(input.current_password,env)) throw new ApiError(400,'La contraseña actual es incorrecta');
    const state=await newAdminPassword(input.password,env);
    await env.DB.prepare("INSERT INTO settings(key,value) VALUES ('admin_access',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value").bind(JSON.stringify(state)).run();
    return issueSession(env);
  }
  if (path === '/v1/admin/session' && request.method === 'GET') return json({authenticated: true});
  if (path === '/v1/admin/settings' && request.method === 'GET') {
    let configured = false;
    try {await globalApi(env); configured = true;} catch (error) {if (!(error instanceof ApiError) || error.status!==409) throw error;}
    return json({api_configured:configured});
  }
  if (path === '/v1/admin/agencykey' && request.method === 'PUT') {
    const input = await body(request);
    const apiKey = text(input.api_key, 'API de AgencyKey',512);
    const creators = await listCreators(apiKey);
    const value = await encrypt({api_key:apiKey}, 'agencykey',env);
    await env.DB.prepare("INSERT INTO settings(key,value) VALUES ('agencykey',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value").bind(value).run();
    return json({configured:true,creators});
  }
  if (path === '/v1/admin/creators' && request.method === 'GET') return json({creators:await listCreators(await globalApi(env))});
  if (path === '/v1/admin/access' && request.method === 'POST') {
    const input = await body(request);
    const code = input.code ? text(input.code, 'Código', 256) : base64url(crypto.getRandomValues(new Uint8Array(32)));
    if (code.length < 8) throw new ApiError(400, 'Usa una contraseña de al menos 8 caracteres');
    if (await matchesAdmin(code,env)) throw new ApiError(400,'Usa una contraseña distinta de la contraseña de administrador');
    const salt = encode(crypto.getRandomValues(new Uint8Array(16)));
    const value = JSON.stringify({kind:'pbkdf2', source:encode(await digest(env.ACCESS_TOKEN)), salt, hash:await passwordHash(code,salt)});
    await env.DB.prepare("INSERT INTO settings(key, value) VALUES ('app_access', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value").bind(value).run();
    return json({code});
  }
  if (path === '/v1/admin/profiles' && request.method === 'GET') return listProfiles(env);
  if (path === '/v1/admin/resolve' && request.method === 'POST') {
    const input = await body(request);
    const id = creatorId(input.creator_id);
    const apiKey = await globalApi(env);
    return json({creator: await resolveCreator(apiKey, id)});
  }
  const match = path.match(/^\/v1\/admin\/profiles\/([a-f0-9-]{36})$/);
  if (!match) throw new ApiError(404, 'Recurso no encontrado');
  const id = match[1];
  if (request.method === 'DELETE') {
    const revision = Number(request.headers.get('If-Match'));
    if (!Number.isSafeInteger(revision) || revision < 1) throw new ApiError(400, 'Versión inválida');
    const result = await env.DB.prepare('DELETE FROM profiles WHERE id = ? AND revision = ?').bind(id, revision).run();
    if (!result.meta.changes) throw new ApiError(409, 'La configuración cambió, actualiza la lista');
    return json({deleted: id});
  }
  if (request.method !== 'PUT') throw new ApiError(405, 'Método no permitido');
  const input = await body(request);
  const revision = input.revision ?? 0;
  if (!Number.isSafeInteger(revision) || revision < 0) throw new ApiError(400, 'Versión inválida');
  const existing = await env.DB.prepare('SELECT * FROM profiles WHERE id = ?').bind(id).first();
  if ((existing?.revision || 0) !== revision) throw new ApiError(409, 'La configuración cambió, actualiza la lista');
  const previous = existing ? await decrypt(existing.encrypted_secrets, id, env) : {};
  const apiKey = await globalApi(env);
  const token = text(input.telegram_token || previous.telegram_token, 'Token de Telegram', 256);
  const modelId = creatorId(input.creator_id);
  const [creator, botId] = await Promise.all([resolveCreator(apiKey, modelId), verifyBot(token)]);
  const encrypted = await encrypt({telegram_token: token}, id, env);
  const now = new Date().toISOString();
  let result;
  try {
    result = await env.DB.prepare(`INSERT INTO profiles
      (id, name, bot_id, creator_id, creator_name, creator_username, encrypted_secrets, revision, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
      ON CONFLICT(id) DO UPDATE SET name=excluded.name, bot_id=excluded.bot_id, creator_id=excluded.creator_id,
      creator_name=excluded.creator_name, creator_username=excluded.creator_username,
      encrypted_secrets=excluded.encrypted_secrets, revision=profiles.revision+1, updated_at=excluded.updated_at
      WHERE profiles.revision = ?`).bind(id, creator.name, botId, creator.external_id, creator.name, creator.username, encrypted, now, revision).run();
  } catch (error) {
    if (String(error.message).includes('profiles.creator_id')) throw new ApiError(409, 'Esta modelo ya tiene un bot asignado');
    if (String(error.message).includes('UNIQUE constraint failed')) throw new ApiError(409, 'Este bot ya tiene una configuración');
    throw error;
  }
  if (!result.meta.changes) throw new ApiError(409, 'La configuración cambió, actualiza la lista');
  return json({id, name: creator.name, bot_id: botId, creator, revision: revision+1, updated_at: now});
}

async function handle(request, env) {
  const path = new URL(request.url).pathname;
  if (path === '/') return Response.redirect(new URL('/admin',request.url).href,302);
  if (path === '/admin' || path === '/admin/') {
    if (request.method !== 'GET') throw new ApiError(405, 'Método no permitido');
    const nonce = base64url(crypto.getRandomValues(new Uint8Array(18)));
    return new Response(adminPage(nonce), {headers: {'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
      'Content-Security-Policy': `default-src 'none'; script-src 'nonce-${nonce}'; style-src 'nonce-${nonce}'; connect-src 'self'; img-src 'self' data:; form-action 'self'; base-uri 'none'; frame-ancestors 'none'`}});
  }
  if (path === '/health' && request.method === 'GET') return json({service: 'agencykey-recorder-tests', version: 5});
  if (path.startsWith('/v1/admin/')) return adminHandle(request, env, path);
  await authorize(request, env);
  if (path==='/v1/recording-desktop-job') return desktopRecordingJob(request,env);
  if (path==='/v1/recording-session') {
    if (request.method==='GET') {
      const session=await sharedSession(env,true);
      if (!session.configured) throw new ApiError(409,'Conecta la sesión compartida de AgencyKey desde la web');
      return json(session);
    }
    if (request.method==='PUT') {
      const input=await body(request,524288);
      if (typeof input.revision!=='string' || !(await sharedSession(env)).configured) throw new ApiError(409,'Conecta AgencyKey desde la web');
      return json(await saveSharedSession(env,input.state,input.revision));
    }
    throw new ApiError(405,'Método no permitido');
  }
  if (path === '/v1/profiles' && request.method === 'GET') return listProfiles(env);
  if (path === '/v1/profile-revisions' && request.method === 'GET') {
    const {results} = await env.DB.prepare('SELECT id, revision, updated_at FROM profiles').all();
    return json({profiles:results});
  }
  const match = path.match(/^\/v1\/profiles\/([a-f0-9-]{36})\/credentials$/);
  if (match && request.method === 'POST') {
    const row = await env.DB.prepare('SELECT * FROM profiles WHERE id = ?').bind(match[1]).first();
    if (!row) throw new ApiError(404, 'La configuración ya no existe');
    const secret = await decrypt(row.encrypted_secrets,row.id,env);
    return json({...profile(row), telegram_token:secret.telegram_token, api_key:await globalApi(env)});
  }
  if (['PUT','DELETE','PATCH','POST'].includes(request.method)) throw new ApiError(403, 'Gestiona las configuraciones desde el panel privado');
  throw new ApiError(404, 'Recurso no encontrado');
}

export default {
  async fetch(request, env) {
    try {
      const result = await handle(request, env);
      console.log(JSON.stringify({method: request.method, path: new URL(request.url).pathname, status: result.status}));
      return result;
    } catch (error) {
      const status = error instanceof ApiError ? error.status : 500;
      if (status === 500) console.error(JSON.stringify({event: 'config_error', type: error.name}));
      return json({error: status === 500 ? 'No se pudo procesar la configuración' : error.message}, status);
    }
  },
};


