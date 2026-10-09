// Real, pre-generated local review. No candidate or audio fixtures.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright'),assert=require('assert'),fs=require('fs'),path=require('path');
const url=process.env.DEMO_URL||'http://localhost:8877',out=process.env.BROWSER_OUTPUT||'data/role-review';fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage(),errors=[];page.setDefaultTimeout(60000);page.on('pageerror',e=>errors.push(e.message));
 await page.goto(url+'/review/roles');await page.locator('.result-block').first().waitFor();
 const state=()=>page.evaluate(()=>fetch('/api/project').then(r=>r.json()));const before=await state(),applied=before.candidates.find(c=>c.applied);assert(applied?.result);
 const roles=[...new Set(applied.result.segments.map(s=>s.role))].sort();for(const role of ['original','completion','bridge','connection'])assert(roles.includes(role),'Missing real '+role);
 assert.equal(await page.locator('.result-block').count(),applied.result.segments.length);
 for(const s of applied.result.segments){for(const n of s.notes){assert(n.start_tick>=0);assert(n.start_tick+n.duration_tick<=s.end_tick-s.start_tick)}}
 const connection=page.locator('.result-block[data-role=connection]').first();await connection.focus();assert((await page.locator('.result-legend small').innerText()).includes('连接块'));await page.keyboard.press('Delete');assert.equal((await state()).fingerprint,before.fingerprint);
 assert.equal(await page.locator('.canvas-tools .segmented button:not(:disabled)').count(),0);assert.equal(await page.locator('.point[aria-disabled=true]').count(),before.intensity_points.length);
 const captures=[];for(const theme of ['light','dark']){
  if(await page.evaluate(()=>document.documentElement.dataset.theme)!==theme)await page.getByLabel('切换明暗主题').click();
  for(const width of [1440,1020,390]){await page.setViewportSize({width,height:width===390?844:1000});await page.waitForTimeout(250);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);const file='roles-'+theme+'-'+width+'.png';await page.screenshot({path:path.join(out,file),fullPage:true});captures.push(file)}
 }
 await page.setViewportSize({width:1440,height:1000});await page.getByLabel('播放',{exact:true}).click();await page.waitForFunction(()=>{const a=document.querySelector('audio');return a&&!a.paused&&a.currentTime>0});await page.getByLabel('停止',{exact:true}).click();
 await page.getByRole('button',{name:'返回搭建',exact:true}).click();assert.equal(await page.locator('.result-block').count(),0);assert.equal((await state()).fingerprint,before.fingerprint);assert.equal(await page.locator('.canvas-tools .segmented button:disabled').count(),0);
 await page.locator('.candidate').filter({hasText:'已确认'}).click();await page.locator('.result-block').first().waitFor();assert.equal((await state()).fingerprint,before.fingerprint);
 assert.equal(errors.length,0,errors.join('\n'));fs.writeFileSync(path.join(out,'browser-roles.json'),JSON.stringify({real_result:true,roles,ownership_matches:true,notes_clipped:true,readonly_preview:true,focus_details:true,real_wav_playback:true,back_to_editor_preserves_project:true,captures,errors},null,2));await browser.close();console.log('BROWSER_ROLES_PASS');
})().catch(e=>{console.error(e);process.exit(1)});
