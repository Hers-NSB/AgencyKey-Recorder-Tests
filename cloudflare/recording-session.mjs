// Login stays in a remote browser; only the authenticated administrator receives its Live View link.
export async function browserDriver(binding, sdk=null) {
  const {acquire, connect, launch} = sdk || await import('@cloudflare/playwright');
  return {
    async start(profileUrl) {
      const {sessionId} = await acquire(binding, {keep_alive:600000});
      const browser = await connect(binding, {sessionId, persistent:true});
      try {
        const context = browser.contexts()[0];
        if (!context) throw new Error('Browser context unavailable');
        const page = context.pages()[0] || await context.newPage();
        await page.goto(profileUrl, {waitUntil:'domcontentloaded', timeout:45000});
        const cdp = await context.newCDPSession(page);
        const {devtoolsFrontendUrl} = await cdp.send('Cloudflare.getLiveView', {mode:'tab', expiresInMs:300000});
        return {sessionId, live_url:devtoolsFrontendUrl};
      } catch (error) {
        const cdp = await browser.newBrowserCDPSession();
        await cdp.send('Browser.close').catch(()=>{});
        throw error;
      } finally {await browser.close();}
    },
    async check(sessionId, profileUrl) {
      const browser = await connect(binding, {sessionId, persistent:true});
      try {
        for (const context of browser.contexts()) {
          for (const page of context.pages()) {
            const url = new URL(page.url());
            if (url.origin !== 'https://app.agencykey.com' || url.pathname.replace(/\/$/,'') !== new URL(profileUrl).pathname) continue;
            const ready = await page.locator('input[type="password"]').count() === 0 &&
              await Promise.all(page.frames().map(frame=>frame.locator('[id^="postId_"]').count().catch(()=>0))).then(counts=>counts.some(Boolean));
            if (ready) return {state:await context.storageState({indexedDB:true})};
          }
        }
        return null;
      } finally {await browser.close();}
    },
    async verifyFeed(profileUrl, state) {
      const browser = await launch(binding);
      try {
        const context = await browser.newContext({storageState:state, viewport:{width:1280,height:720}});
        const page = await context.newPage();
        const response = await page.goto(profileUrl, {waitUntil:'domcontentloaded',timeout:20000});
        if (response?.status() === 401) return 'login_required';
        if ([403,404].includes(response?.status())) return 'unavailable';
        if (!response?.ok()) return 'connection_error';
        const expected = new URL(profileUrl);
        const deadline = Date.now()+20000;
        while (Date.now()<deadline) {
          const current = new URL(page.url());
          if (current.origin !== expected.origin || /\/(login|sign-in|auth)(\/|$)/.test(current.pathname)) {
            return 'login_required';
          }
          if (current.pathname.replace(/\/$/,'') === expected.pathname) {
            for (const frame of page.frames()) {
              if (await frame.locator('input[type="password"]').first().isVisible().catch(()=>false)) {
                return 'login_required';
              }
              let parent = frame;
              while (parent.parentFrame()) {
                if (!await (await parent.frameElement()).isVisible()) break;
                parent = parent.parentFrame();
              }
              if (parent !== page.mainFrame()) continue;
              const ready = await frame.locator('[id^="postId_"]:not(.m-pinned)').evaluateAll(cards =>
                cards.some(card => {
                  const rect = card.getBoundingClientRect();
                  if (!card.checkVisibility() || rect.bottom <= 100 || rect.top >= innerHeight) return false;
                  return [...card.querySelectorAll('img')].every(img => {
                    const box = img.getBoundingClientRect();
                    return !box.width || !box.height || box.bottom <= 100 || box.top >= innerHeight ||
                      (img.complete && img.naturalWidth > 0);
                  });
                })).catch(()=>false);
              if (ready) return 'ready';
            }
          }
          await page.waitForTimeout(500);
        }
        return 'feed_unverified';
      } finally {
        await browser.close();
      }
    },
    async close(sessionId) {
      const browser = await connect(binding, {sessionId, persistent:true});
      try {const cdp = await browser.newBrowserCDPSession();await cdp.send('Browser.close');}
      finally {await browser.close().catch(()=>{});}
    },
  };
}

function allowedHost(host) {
  return ['agencykey.com','onlyfans.com'].some(domain=>host===domain || host.endsWith('.'+domain));
}

export function cleanStorageState(state) {
  if (!state || !Array.isArray(state.cookies) || !Array.isArray(state.origins) || JSON.stringify(state).length>500000) {
    throw new Error('Invalid browser state');
  }
  const cookies = state.cookies.filter(cookie=>typeof cookie.domain==='string' && allowedHost(cookie.domain.replace(/^\./,'')));
  const origins = state.origins.filter(item=>{
    try {const url=new URL(item.origin);return url.protocol==='https:' && allowedHost(url.hostname);} catch {return false;}
  });
  if (!cookies.length && !origins.some(item=>item.localStorage?.length || item.indexedDB?.length)) throw new Error('Empty browser state');
  return {cookies,origins};
}
