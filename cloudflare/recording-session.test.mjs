import {test} from 'node:test';
import assert from 'node:assert/strict';
import {browserDriver,cleanStorageState} from './recording-session.mjs';
import {saveSharedSession} from './worker.mjs';
import {makeEnvironment,admin,desktop,request} from './test-support.mjs';

const state={cookies:[{name:'session',value:'private-session-cookie',domain:'.agencykey.com',path:'/',expires:-1,httpOnly:true,secure:true,sameSite:'Lax'}],origins:[{origin:'https://app.agencykey.com',localStorage:[{name:'token',value:'private-storage-token'}]}]};

test('shared session survives a new client and is encrypted, with stale refreshes rejected',async()=>{
  const {env,sqlite}=makeEnvironment();
  try {
    assert.equal((await desktop(env,'GET','/v1/recording-session')).status,409);
    const saved=await saveSharedSession(env,state,null);
    const raw=sqlite.prepare("SELECT value FROM settings WHERE key='recording_session'").get().value;
    assert.ok(!raw.includes('private-session-cookie') && !raw.includes('private-storage-token'));
    const metadata=await (await admin(env,'GET','/v1/admin/recording-session')).json();
    assert.equal(metadata.configured,true);assert.equal(metadata.state,undefined);
    const first=await desktop(env,'GET','/v1/recording-session');assert.match(first.headers.get('cache-control'),/no-store/);
    assert.deepEqual((await first.json()).state,state);
    const replacement=structuredClone(state);replacement.cookies[0].value='refreshed-cookie';
    const update=await desktop(env,'PUT','/v1/recording-session',{state:replacement,revision:saved.revision});assert.equal(update.status,200);
    assert.equal((await desktop(env,'PUT','/v1/recording-session',{state,revision:saved.revision})).status,409);
    assert.equal((await (await desktop(env,'GET','/v1/recording-session')).json()).state.cookies[0].value,'refreshed-cookie');
    assert.equal((await request(env,'GET','/v1/recording-session')).status,401);
    assert.equal((await desktop(env,'POST','/v1/admin/recording-session/connect',{})).status,401);
    assert.equal((await admin(env,'POST','/v1/admin/recording-session/connect',{}, {Origin:'https://evil.test'})).status,403);
  } finally {sqlite.close();}
});

test('browser export excludes unrelated authentication domains and rejects empty state',()=>{
  const extra=structuredClone(state);extra.cookies.push({domain:'.unrelated.test',value:'other-login'});extra.origins.push({origin:'https://agencykey.com.evil.test',localStorage:[{name:'token',value:'bad'}]});
  assert.deepEqual(cleanStorageState(extra),state);
  assert.throws(()=>cleanStorageState({cookies:[],origins:[]}));
});

test('web login exports IndexedDB only after matching the intended model feed',async()=>{
  let url='https://app.agencykey.com/login';let feedCount=0;const calls=[];
  const page={url:()=>url,locator:()=>({count:async()=>url.endsWith('/login')?1:0}),frames:()=>[{locator:()=>({count:async()=>feedCount})}]};
  const context={pages:()=>[page],storageState:async options=>{calls.push(options);return state;}};
  let disconnected=0;
  const sdk={connect:async()=>({contexts:()=>[context],close:async()=>{disconnected++;}})};
  const driver=await browserDriver({},sdk);
  assert.equal(await driver.check('session','https://app.agencykey.com/models/52'),null);
  url='https://app.agencykey.com/models/99';feedCount=1;
  assert.equal(await driver.check('session','https://app.agencykey.com/models/52'),null);
  url='https://app.agencykey.com/models/52';feedCount=0;
  assert.equal(await driver.check('session','https://app.agencykey.com/models/52'),null);
  feedCount=1;assert.deepEqual((await driver.check('session','https://app.agencykey.com/models/52')).state,state);
  assert.deepEqual(calls,[{indexedDB:true}]);assert.equal(disconnected,4);
});

test('feed verification opens a single model in a temporary browser with the saved state',async()=>{
  const target='https://app.agencykey.com/models/52';
  let current=target, closed=0;
  const frame={parentFrame:()=>null,locator:selector=>selector.startsWith('input')
    ? {first:()=>({isVisible:async()=>false})} : {evaluateAll:async()=>true}};
  const page={goto:async url=>{assert.equal(url,target);return {ok:()=>true,status:()=>200};},
    url:()=>current,frames:()=>[frame],mainFrame:()=>frame};
  const sdk={launch:async()=>({newContext:async options=>{
    assert.deepEqual(options.storageState,state);return {newPage:async()=>page};
  },close:async()=>{closed++;}})};
  const driver=await browserDriver({},sdk);
  assert.equal(await driver.verifyFeed(target,state),'ready');
  current='https://app.agencykey.com/login';
  assert.equal(await driver.verifyFeed(target,state),'login_required');
  assert.equal(closed,2);
});
