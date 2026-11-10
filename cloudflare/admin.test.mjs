import {test} from 'node:test';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir} from 'node:fs/promises';
import worker from './worker.mjs';
import {origin,makeEnvironment,installUpstream,input,firstToken,secondToken,desktop} from './test-support.mjs';

test('password administrator configures a shared API, selects models and rotates app password',async()=>{
 const {env,sqlite}=makeEnvironment();const upstream=installUpstream();env.ADMIN_SETUP=JSON.stringify({token:'browser-private-setup',expires:Date.now()+3600000});
 const browser=await chromium.launch({headless:true,executablePath:process.env.RECORDER_TEST_CHROME,channel:process.env.RECORDER_TEST_CHROME?undefined:(process.platform==='win32'?'msedge':'chrome')});
 try{
 const page=await browser.newPage({viewport:{width:1120,height:900}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route(origin+'/**',async route=>{const req=route.request();const init={method:req.method(),headers:await req.allHeaders()};if(req.postDataBuffer())init.body=req.postDataBuffer();const response=await worker.fetch(new Request(req.url(),init),env);await route.fulfill({status:response.status,headers:Object.fromEntries(response.headers),body:Buffer.from(await response.arrayBuffer())});});
 await page.goto(origin+'/admin#configurar=browser-private-setup');await page.locator('#login-title').filter({hasText:'Crea tu contraseña'}).waitFor();assert.equal(await page.evaluate(()=>location.hash),'');
 await page.locator('#admin-password').fill('private-browser-password');await page.locator('#admin-confirm').fill('mismatch');await page.locator('#login-button').click();await page.locator('#login-error').filter({hasText:'no coinciden'}).waitFor();
 await page.locator('#admin-confirm').fill('private-browser-password');await page.locator('#login-button').click();await page.locator('#empty').waitFor({state:'visible'});assert.ok(!(await page.evaluate(()=>document.cookie)).includes('__Host-recorder_admin'));
 await page.reload();await page.locator('#app-view').waitFor({state:'visible'});await page.locator('#logout').click();await page.locator('#confirm-accept').click();await page.locator('#login-view').waitFor({state:'visible'});
 await page.locator('#admin-password').fill(env.ACCESS_TOKEN);await page.locator('#login-button').click();await page.locator('#login-error').filter({hasText:'incorrecta'}).waitFor();await page.locator('#admin-password').fill('private-browser-password');await page.locator('#login-button').click();await page.locator('#empty').waitFor({state:'visible'});
 await page.locator('#nav-access').click();await page.locator('#agency-key').fill(input.api_key);await page.locator('#save-api').click();await page.locator('#confirm-accept').click();await page.locator('#api-status').filter({hasText:'2 modelos'}).waitFor();assert.equal(await page.locator('#agency-key').inputValue(),'');
 await page.locator('#nav-profiles').click();await page.locator('#add').click();await page.locator('#creator-id option[value="52"]').waitFor({state:'attached'});await page.locator('#telegram-token').fill(firstToken);await page.locator('#creator-id').selectOption('52');await page.waitForFunction(()=>document.getElementById('creator-name').value==='Lilith');await page.locator('#save').click();await page.getByRole('button',{name:'Editar Lilith',exact:true}).waitFor();assert.equal(sqlite.prepare('SELECT name FROM profiles').get().name,'Lilith');
 await page.locator('#add').click();await page.locator('#creator-id option[value="99"]').waitFor({state:'attached'});await page.locator('#telegram-token').fill(secondToken);await page.locator('#creator-id').selectOption('99');await page.waitForFunction(()=>document.getElementById('creator-name').value==='Lola');await page.locator('#save').click();await page.getByRole('button',{name:'Editar Lola',exact:true}).waitFor();
 assert.equal((await (await desktop(env,'GET','/v1/profiles')).json()).profiles.length,2);
 await page.getByRole('button',{name:'Editar Lilith',exact:true}).click();await page.locator('#creator-id option[value="52"]').waitFor({state:'attached'});upstream.ofNames[52]='Lilith actualizada';await page.locator('#save').click();await page.getByRole('button',{name:'Editar Lilith actualizada',exact:true}).waitFor();
 await page.getByRole('button',{name:'Eliminar Lola',exact:true}).click();await page.locator('#confirm-accept').click();await page.waitForFunction(()=>document.querySelectorAll('.bot-row').length===1);
 await page.setViewportSize({width:390,height:850});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await page.setViewportSize({width:1120,height:900});await mkdir('ui-checks',{recursive:true});await page.screenshot({path:'ui-checks/dropper-panel.png',fullPage:true});
 await page.locator('#nav-access').click();await page.locator('#access-input').fill('nueva-contraseña-elegida');await page.locator('#rotate').click();await page.locator('#confirm-accept').click();await page.locator('#access-status').filter({hasText:'Contraseña cambiada'}).waitFor();assert.equal(await page.locator('#access-input').inputValue(),'');assert.equal((await desktop(env,'GET','/v1/profiles')).status,401);assert.equal((await desktop(env,'GET','/v1/profiles',undefined,'nueva-contraseña-elegida')).status,200);assert.deepEqual(errors,[]);
 }finally{await browser.close();sqlite.close();}
});

