// Real browser dialog interactions; generation responses are controlled fixtures.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('assert'),fs=require('fs'),path=require('path');
const url=process.env.DEMO_URL||'http://127.0.0.1:8877';
const out=process.env.BROWSER_OUTPUT||'data/generation-notice-evidence';fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const context=await browser.newContext({viewport:{width:1440,height:900}}),page=await context.newPage(),errors=[];
 page.on('pageerror',e=>errors.push(e.message));await page.goto(url);await page.getByRole('heading',{name:'情绪搭建画板'}).waitFor();
 await page.getByRole('button',{name:'选择 A1',exact:true}).click();
 await Promise.all([page.waitForResponse(r=>r.url().endsWith('/api/edit')),page.getByRole('button',{name:'放入所选积木',exact:true}).click()]);
 let requests=0,cancelRequests=0,status='RUNNING',release;
 const submitted=new Promise(resolve=>release=resolve);
 await page.route('**/api/generate',async route=>{requests++;status='RUNNING';if(requests===1)await submitted;
  if(requests===3)return route.fulfill({status:503,json:{detail:'Controlled generation failure'}});
  return route.fulfill({json:{id:'notice-ui-fixture',status:'QUEUED'}});
 });
 await page.route('**/api/jobs/notice-ui-fixture',route=>route.fulfill({json:{status,error:null,progress:{phase:'BASE_COMPLETION'}}}));
 await page.route('**/api/jobs/notice-ui-fixture/cancel',route=>{cancelRequests++;status='CANCELLED';return route.fulfill({json:{status}})});
 assert.equal(await page.getByRole('dialog').count(),0);
 await page.getByRole('button',{name:'生成方案',exact:true}).click();
 const dialog=page.getByRole('dialog',{name:'生成提示'});await dialog.waitFor();
 assert.equal(await dialog.locator('p').innerText(),'服务器性能低下，复杂任务可能耗时过长，本地更快速');
 await page.waitForFunction(()=>document.querySelector('.generation-notice')?.open);
 assert.equal(requests,1); // Visible while the submit response is still pending.
 const geometry=[];
 for(const theme of ['light','dark']){
  await page.evaluate(theme=>document.documentElement.dataset.theme=theme,theme);
  for(const width of [320,390,650,1020,1440,1920]){
   await page.setViewportSize({width,height:width<700?480:700});
   const box=await dialog.boundingBox();assert(box.x>=0&&box.y>=0&&box.x+box.width<=width&&box.y+box.height<=(width<700?480:700));
   geometry.push({width,theme,box});await page.screenshot({path:path.join(out,`notice-${theme}-${width}.png`)});
  }
 }
 await dialog.getByRole('button',{name:'知道了'}).focus();
 assert(await dialog.evaluate(d=>d.contains(document.activeElement)));
 await page.locator('.deployment-note a').evaluate(a=>a.focus());
 assert(await dialog.evaluate(d=>d.contains(document.activeElement))); // Native modal makes the page inert.
 await page.keyboard.press('Tab');
 // Chrome may focus its own browser controls; it must not focus the underlying page.
 assert(await page.evaluate(()=>!document.querySelector('header').contains(document.activeElement)&&!document.querySelector('.workspace').contains(document.activeElement)));
 await dialog.getByRole('button',{name:'知道了'}).click();await dialog.waitFor({state:'hidden'});
 assert.equal(requests,1);assert.equal(cancelRequests,0);release();await page.getByRole('progressbar').waitFor();
 assert.equal(await page.getByRole('button',{name:'生成方案',exact:true}).isDisabled(),true);
 await page.getByRole('button',{name:'取消生成',exact:true}).click();await page.getByText('已取消生成',{exact:true}).waitFor();assert.equal(cancelRequests,1);
 await page.getByRole('button',{name:'生成方案',exact:true}).focus();await page.keyboard.press('Enter');await dialog.waitFor();
 await page.keyboard.press('Escape');await dialog.waitFor({state:'hidden'});assert.equal(requests,2);assert.equal(cancelRequests,1);
 await page.getByRole('button',{name:'取消生成',exact:true}).click();await page.getByText('已取消生成',{exact:true}).waitFor();
 await page.getByRole('button',{name:'生成方案',exact:true}).click();await dialog.waitFor();await dialog.getByRole('button',{name:'知道了'}).click();
 await page.getByRole('alert').getByText('Controlled generation failure',{exact:false}).waitFor();assert.equal(requests,3);assert.equal(cancelRequests,2);
 assert.equal(errors.length,0,errors.join('\n'));await browser.close();
 fs.writeFileSync(path.join(out,'generation-notice.json'),JSON.stringify({url,message_exact:true,submission_not_paused:true,close_does_not_cancel:true,repeated_generation_shows_again:true,escape_supported:true,background_inert:true,submit_failure_visible:true,generation_responses_fixture:true,requests,cancelRequests,geometry,errors},null,2));
 console.log('GENERATION_NOTICE_BROWSER_PASS',geometry.length);
})().catch(e=>{console.error(e);process.exit(1)});
