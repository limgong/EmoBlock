// Decode and play the real deployed WAV in Chrome. No claim of device/listening acceptance.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('fs'), path = require('path'), assert = require('assert');
const url = process.env.DEMO_URL || 'http://127.0.0.1:8876';
const out = process.env.BROWSER_OUTPUT || 'data/cloud-browser';
const state = process.env.ACCEPTANCE_STATE || 'data/cloud-acceptance/private-restart-state.json';
(async () => {
  const browser = await chromium.launch({headless:true, executablePath:process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  const report = [];
  for (const session of JSON.parse(fs.readFileSync(state))) {
    const context = await browser.newContext({viewport:{width:1440,height:1000}});
    await context.addCookies(Object.entries(session.cookies).map(([name,value]) => ({name,value,url,httpOnly:true,sameSite:'Strict'})));
    const page = await context.newPage(), errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(url);
    await page.getByRole('button', {name:/^方案 1/}).first().click();
    assert(await page.locator('audio').evaluate(a => a.paused), 'Selection must not autoplay');
    const versions = [];
    for (const kind of ['comparison','final']) {
      await page.getByLabel('对比版本').selectOption(kind);
      await page.getByRole('button', {name:'播放',exact:true}).click();
      await page.waitForFunction(() => { const a=document.querySelector('audio');return a && !a.paused && a.currentTime > .1 && a.duration > 0 && !a.error; });
      const actual = await page.locator('audio').evaluate(a => ({duration:a.duration,src:a.currentSrc,error:a.error?.code || null}));
      assert(actual.src.endsWith(`/api/assets/${session.candidate_id}/${kind}/wav`));
      versions.push({kind,duration:actual.duration,error:actual.error});
      await page.getByRole('button', {name:'停止',exact:true}).click();
      assert(await page.locator('audio').evaluate(a => a.paused && a.currentTime===0));
    }
    assert.equal(errors.length,0,errors.join('\n'));
    await page.screenshot({path:path.join(out,session.mode+'-confirmed.png'),fullPage:true});
    report.push({mode:session.mode,selection_autoplay:false,versions,stop_reset:true,errors});
    await context.close();
  }
  await browser.close();
  fs.writeFileSync(path.join(out,'browser-audio.json'),JSON.stringify(report,null,2));
  console.log('CHROME_REAL_WAV_PASS',report.length);
})().catch(error => { console.error(error);process.exit(1); });
