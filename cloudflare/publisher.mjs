import savedUploadProfiles from '../agencykey-perfiles.json' with { type: 'json' };

const agency = 'https://app.agencykey.com/api/v1/onlyfans';
const storageHost = 'of2transcoder.s3-accelerate.amazonaws.com';
const converter = 'https://convert.onlyfans.com/file/upload';
export const maxPhotoBytes = 10 * 1024 * 1024;
export const maxPublishBody = Math.ceil(maxPhotoBytes / 3) * 4 + 16_384;

export class PublicationError extends Error {
  constructor(status, message, {uncertain = false, retryAfter} = {}) {
    super(message);
    this.status = status;
    this.uncertain = uncertain;
    this.retryAfter = retryAfter;
  }
}

function replyWait(value) {
  const seconds = /^\d+$/.test(value ?? '') ? Number(value)
    : Math.ceil((Date.parse(value) - Date.now()) / 1000);
  return Number.isFinite(seconds) ? Math.min(86400, Math.max(1, seconds)) : 60;
}

async function request(url, init, step, final = false, fallback = false) {
  let response;
  try {
    response = await fetch(url, {...init, redirect:'manual', signal:AbortSignal.timeout(60_000)});
  } catch {
    throw new PublicationError(502, step + ': conexión interrumpida', {uncertain:final});
  }
  if (response.ok || (fallback && response.status === 400)) return response;
  if (response.body) await response.body.cancel().catch(()=>{});
  if (response.status === 429)
    throw new PublicationError(429, 'AgencyKey limitó las publicaciones', {retryAfter:replyWait(response.headers.get('Retry-After'))});
  const definitive = [400,401,403,404,422].includes(response.status);
  throw new PublicationError(definitive ? 422 : 502, step + ': HTTP ' + response.status,
    {uncertain:final && !definitive});
}

async function jsonResponse(response, step, uncertain = false) {
  const reader = response.body?.getReader();
  const decoder = new TextDecoder();
  let raw = '';
  let size = 0;
  try {
    if (!reader) throw Error();
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 1_048_576) throw Error();
      raw += decoder.decode(value, {stream:true});
    }
    return JSON.parse(raw + decoder.decode());
  } catch {
    await reader?.cancel().catch(()=>{});
    throw new PublicationError(502, step + ': respuesta inválida', {uncertain});
  }
}

export function decodePhoto(encoded) {
  if (encoded === undefined) return null;
  if (typeof encoded !== 'string' || encoded.length > Math.ceil(maxPhotoBytes / 3) * 4)
    throw new PublicationError(413, 'La foto supera 10 MiB');
  let raw;
  try {raw = atob(encoded);} catch {throw new PublicationError(400, 'Foto inválida');}
  if (raw.length > maxPhotoBytes) throw new PublicationError(413, 'La foto supera 10 MiB');
  const kind = raw.startsWith('\xff\xd8\xff') ? ['jpg','image/jpeg']
    : raw.startsWith('\x89PNG\r\n\x1a\n') ? ['png','image/png'] : null;
  if (!kind) throw new PublicationError(400, 'La foto debe ser JPEG o PNG');
  return {bytes:Uint8Array.from(raw, char=>char.charCodeAt(0)), extension:kind[0], type:kind[1]};
}

const jsonInit = (headers, payload) => ({
  method:'POST',headers:{...headers,'Content-Type':'application/json'},body:JSON.stringify(payload),
});

async function uploadPhoto(base, creatorId, headers, photo) {
  const filename = 'dropper-' + crypto.randomUUID() + '.' + photo.extension;
  const nonce = crypto.getRandomValues(new Uint32Array(2));
  const key = `upload/${crypto.randomUUID()}/${String((BigInt(nonce[0])*2n**32n+BigInt(nonce[1]))%10n**12n).padStart(12,'0')}/${filename}`;
  const info = await request(base+'/users/me',{headers},'Configuración de la modelo',false,true);
  let profile;
  if (info.status === 400) {
    await info.body?.cancel();
    profile = savedUploadProfiles[String(creatorId)];
  } else {
    profile = await jsonResponse(info, 'Configuración de la modelo');
  }
  const args = profile?.upload?.geoUploadArgs;
  if (String(profile?.id) !== String(creatorId) || String(args?.additional?.user) !== String(creatorId)
      || typeof args.preset !== 'string' || typeof args.isDelay !== 'boolean' || typeof args.needThumbs !== 'boolean')
    throw new PublicationError(422, 'Faltan ajustes de subida para esta modelo');
  const signed = await jsonResponse(await request(base+'/upload/signed/create',jsonInit(headers,{
    key,parts:1,contentType:photo.type,secure:false,userPrefix:'upload',
  }),'Carga firmada'),'Carga firmada');
  let url;
  try {url = new URL(signed.putUrl);} catch {throw new PublicationError(502, 'Dirección de carga inválida');}
  if (url.protocol !== 'https:' || url.host !== storageHost || url.username || url.password
      || !url.search || !url.pathname.startsWith('/upload/')
      || signed.key !== key || typeof signed.uploadToken !== 'string' || !signed.uploadToken)
    throw new PublicationError(502, 'Destino de carga inesperado');
  const stored = await request(url.href,{method:'PUT',headers:{'Content-Type':photo.type},body:photo.bytes},'Subida de foto');
  const etag = stored.headers.get('ETag');
  await stored.body?.cancel();
  if (!etag) throw new PublicationError(502, 'La foto no tiene confirmación de almacenamiento');
  const fields = new FormData();
  const params = {
    preset:args.preset,isDelay:String(args.isDelay),needThumbs:String(args.needThumbs),
    'additional[user]':String(creatorId), 'file[ETag]':etag,
    'file[Location]':url.origin+url.pathname,'file[Key]':key,'file[Bucket]':'of2transcoder',
    'file[name]':filename,'file[uploadToken]':signed.uploadToken,
  };
  if (profile.hasWatermarkPhoto) {
    params['watermark[text]'] = profile.watermarkText;
    params['watermark[position]'] = profile.watermarkPosition;
  }
  for (const [name,value] of Object.entries(params)) fields.append(name, value);
  const processed = await jsonResponse(await request(converter,{
    method:'POST',headers:{Accept:'application/json'},body:fields,
  },'Procesamiento de la foto'),'Procesamiento de la foto');
  const attachment = {name:filename};
  for (const field of ['processId','host','extra']) {
    if (typeof processed?.[field] !== 'string' || !processed[field])
      throw new PublicationError(502, 'AgencyKey no confirmó el procesamiento de la foto');
    attachment[field] = processed[field];
  }
  return attachment;
}

export async function publishWithAgencyKey(apiKey, creatorId, text, photo, beforeFinalPost) {
  const base = `${agency}/${creatorId}/api2/v2`;
  const headers = {'x-public-api-key':apiKey,Accept:'application/json'};
  const payload = {text,expireDays:1};
  if (photo) payload.mediaFiles = [await uploadPhoto(base,creatorId,headers,photo)];
  await beforeFinalPost();
  const data = await jsonResponse(await request(base+'/posts',jsonInit(headers,payload),'Crear post',true),'Crear post',true);
  const id = typeof data?.id === 'string' ? data.id : Number.isSafeInteger(data?.id) ? String(data.id) : '';
  if (!/^[1-9]\d{0,24}$/.test(id) || (photo && data.mediaCount === 0))
    throw new PublicationError(502, 'AgencyKey no confirmó el post completo. Revisa el muro', {uncertain:true});
  return id;
}
