// Actual browser recording. CDP frames are timed and later conformed to 30 fps.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs=require('fs'),path=require('path');
const out=path.resolve(process.env.VIDEO_RAW||'data/video-recording');fs.mkdirSync(out,{recursive:true});
const pause=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 const b=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args:['--autoplay-policy=no-user-gesture-required']});
 const c=await b.newContext({viewport:{width:1920,height:1080},deviceScaleFactor:1});const p=await c.newPage();const errors=[];p.on('pageerror',e=>errors.push(e.message));await p.goto('http://127.0.0.1:8765');await p.getByRole('heading',{name:'情绪搭建画板'}).waitFor();
 await p.evaluate(()=>{localStorage.setItem('theme','light')});await p.reload();await p.getByRole('heading',{name:'情绪搭建画板'}).waitFor();
 // Set timeline through genuine UI, before recording.
 while((await p.evaluate(()=>fetch('/api/project').then(r=>r.json()))).grid_count>8){await p.getByLabel('减少四拍').click();await pause(130)}
 let n=0,frames=[],marks={},running=true;const begin=performance.now();
 const client=await c.newCDPSession(p);
 client.on('Page.screencastFrame',async ev=>{if(running){const file=String(n++).padStart(6,'0')+'.jpg';fs.writeFileSync(path.join(out,file),Buffer.from(ev.data,'base64'));frames.push({file,time:(performance.now()-begin)/1000});if(n%20===0)fs.writeFileSync(path.join(out,'frames.json'),JSON.stringify(frames))}await client.send('Page.screencastFrameAck',{sessionId:ev.sessionId}).catch(()=>{})});
 await client.send('Page.startScreencast',{format:'jpeg',quality:88,maxWidth:1920,maxHeight:1080,everyNthFrame:1});
 function mark(name){marks[name]=(performance.now()-begin)/1000;fs.writeFileSync(path.join(out,'marks.json'),JSON.stringify(marks,null,2));console.log(name,marks[name].toFixed(1))}
 async function overlay(title,body){await p.evaluate(({title,body})=>{document.getElementById('video-intro')?.remove();const x=document.createElement('div');x.id='video-intro';Object.assign(x.style,{position:'fixed',inset:'0',zIndex:'100',background:'rgba(237,240,243,.96)',display:'flex',flexDirection:'column',justifyContent:'center',alignItems:'center',color:'#26333d',padding:'120px'});const h=document.createElement('h1');h.textContent=title;Object.assign(h.style,{fontSize:'56px',lineHeight:'1.4',marginBottom:'30px'});const s=document.createElement('p');s.textContent=body;Object.assign(s.style,{fontSize:'29px',lineHeight:'1.9',maxWidth:'1200px',textAlign:'center',whiteSpace:'pre-line'});x.append(h,s);document.body.append(x)},{title,body})}
 mark('intro');await overlay('EmoBlocks 情绪积木','以情绪为引导，以旋律积木为载体\n低门槛音乐创作工作流');await pause(1600);
 await overlay('你决定音乐在何时如何发展','规划长段配乐的旋律、情绪与起伏\n让音乐灵活满足视频、游戏等场景的需要');await pause(1600);
 mark('scenario');await overlay('假设你正在给一段视频配乐','开头平静 → 中段紧张 → 熟悉旋律达到高潮 → 结尾回落\n这些变化，需要出现在你指定的位置');await pause(2500);
 await p.evaluate(()=>document.getElementById('video-intro')?.remove());mark('materials');await pause(2500);
 const first=p.getByRole('button',{name:/选择 A1/}).first();await first.click();await p.getByRole('button',{name:/^播放 A1$/}).first().click();await pause(2200);await p.getByLabel('停止',{exact:true}).click();
 await p.getByLabel('新旋律方式').selectOption('counter');await p.getByRole('button',{name:'新旋律',exact:true}).click();await pause(2400);
 await p.locator('.cards').evaluate(x=>x.scrollTop=x.scrollHeight);await pause(2500);await p.locator('.cards').evaluate(x=>x.scrollTop=0);await pause(2500);
 mark('curve');await p.getByRole('button',{name:'手绘强度',exact:true}).click();const rect=await p.locator('svg.canvas').boundingBox();const w=850,H=340,pad=34,total=15360;
 const X=t=>rect.x+pad+t/total*(w-pad-16),Y=v=>rect.y+H-45-v*(H-90);
 await p.mouse.move(X(0)+2,Y(.2));await p.mouse.down();for(let k=0;k<=32;k++){const t=k*480;const v=t<=9600?.2+.7*t/9600:.9-.65*(t-9600)/5760;await p.mouse.move(X(t),Y(v),{steps:3});await pause(70)}await p.mouse.up();await pause(1500);await p.getByRole('button',{name:'选择 / 调整',exact:true}).click();
 mark('assembly');
 for(const [i,label,emotion] of [[0,'A1','平静／安定'],[1,'A2','平静／安定'],[4,'A3','悬疑／不安'],[5,'A1','紧张／危机'],[7,'A2','振奋／坚定']]){
  const m=p.getByRole('button',{name:'选择 '+label,exact:true}).first();await m.scrollIntoViewIfNeeded();await m.click();
  // Click empty cell to clear block selection; use actual pointer drop for first block.
  await p.locator('svg.canvas').click({position:{x:pad+i/8*(w-pad-16)+8,y:H-18}});
  if(i===0){const source=p.locator('.material').filter({has:m});const box=await source.boundingBox();await p.mouse.move(box.x+55,box.y+40);await p.mouse.down();await p.mouse.move(X(i*1920),Y(.2),{steps:18});await p.mouse.up();await pause(500);}
  let state=await p.evaluate(()=>fetch('/api/project').then(r=>r.json()));
  if(!state.placements.some(v=>v.start_tick===i*1920)){await p.getByLabel('放置格').fill(String(i+1));await p.getByRole('button',{name:'放入所选积木',exact:true}).click();}
  await pause(400);await p.locator('svg.canvas .block').last().click();if(emotion!=='平静／安定')await p.getByRole('button',{name:emotion,exact:true}).click();await pause(1000);
 }
 await p.locator('svg.canvas').click({position:{x:pad+6/8*(w-pad-16)+8,y:H-18}});await p.getByLabel('放置格').fill('7');await p.getByRole('button',{name:'标为留白',exact:true}).click();await pause(1700);
 mark('generate');await p.getByRole('button',{name:'生成方案',exact:true}).click();
 const started=Date.now();while(Date.now()-started<610000){await pause(3000);if(await p.locator('.candidate').count())break;if(await p.locator('.error').count())throw Error(await p.locator('.error').innerText())}
 if(!await p.locator('.candidate').count())throw Error('Real generation timed out');mark('ready');await pause(2300);
 const prepared=await p.evaluate(()=>fetch('/api/project').then(r=>r.json()));const audible=prepared.candidates[0].id;
 for(const kind of ['comparison','final'])for(const fmt of ['wav','mid','mmp']){const r=await c.request.get(`http://127.0.0.1:8765/api/assets/${audible}/${kind}/${fmt}`);if(!r.ok())throw Error(await r.text());fs.writeFileSync(path.join(out,kind+'.'+fmt),await r.body())}
 function pcm(file){const buf=fs.readFileSync(path.join(out,file));let offset=12;while(buf.toString('ascii',offset,offset+4)!=='data')offset+=8+buf.readUInt32LE(offset+4)+(buf.readUInt32LE(offset+4)%2);return new Int16Array(buf.buffer,buf.byteOffset+offset+8,buf.readUInt32LE(offset+4)/2)}
 const before=pcm('comparison.wav'),after=pcm('final.wav'),window=9*44100*2;let best=0,score=-1;for(let sec=0;(sec*44100*2+window)<=Math.min(before.length,after.length);sec++){let cost=0;for(let i=sec*44100*2;i<sec*44100*2+window;i++)cost+=(before[i]-after[i])**2;if(cost>score){score=cost;best=sec}}
 if(score===0)throw Error('A/B identical; choose an honest musical difference sample');fs.writeFileSync(path.join(out,'audio-window.json'),JSON.stringify({start_seconds:best,duration_seconds:9}));
 await p.locator('.candidate').first().click();await p.getByLabel('对比版本').selectOption('comparison');await p.getByLabel('播放',{exact:true}).click();await p.evaluate(t=>document.querySelector('audio').currentTime=t,best);mark('comparison');await pause(9000);await p.getByLabel('停止',{exact:true}).click();await p.getByLabel('对比版本').selectOption('final');await p.getByLabel('播放',{exact:true}).click();await p.evaluate(t=>document.querySelector('audio').currentTime=t,best);mark('final');await pause(9000);await p.getByLabel('停止',{exact:true}).click();
 mark('confirm');await p.getByRole('button',{name:'确认所选方案',exact:true}).click();await p.getByRole('button',{name:'确认所选方案',exact:true}).waitFor({state:'visible'});await p.waitForFunction(()=>!document.querySelector('button[title="撤销"]').disabled);await pause(2500);await p.getByTitle('撤销',{exact:true}).click();await pause(1700);if(await p.locator('.error').count())throw Error(await p.locator('.error').innerText());await p.getByTitle('重做',{exact:true}).click();await pause(1700);
 const state=await p.evaluate(()=>fetch('/api/project').then(r=>r.json()));const cid=state.candidates[0].id;for(const kind of ['comparison','final'])for(const fmt of ['wav','mid','mmp']){const r=await c.request.get(`http://127.0.0.1:8765/api/assets/${cid}/${kind}/${fmt}`);if(!r.ok())throw Error(await r.text());fs.writeFileSync(path.join(out,kind+'.'+fmt),await r.body())}
 fs.writeFileSync(path.join(out,'project.json'),JSON.stringify(state,null,2));await pause(2300);
 mark('workflow');await overlay('以工作流组织生成能力','采集原料 → 制作与拓展积木 → 绘制情绪线 → 自主搭建积木\n智能补齐积木 → 积木情绪渲染 → 桥接积木 → 调校成曲');await pause(3000);
 await overlay('模型持续更新，创作控制持续保留','不同生成模型经适配接入，随技术迭代\n自动补全与连接算法承接用户设计\n当前公开 Demo 使用规则算法与真实 LMMS 渲染');await pause(3000);
 mark('outro');await overlay('EmoBlocks 情绪积木','让更多人参与音乐创作\n掌握长程结构，调整局部表达\n在线 Demo 地址待云端部署验收后加入');await pause(2500);mark('end');
 running=false;await client.send('Page.stopScreencast');fs.writeFileSync(path.join(out,'frames.json'),JSON.stringify(frames));fs.writeFileSync(path.join(out,'browser-errors.json'),JSON.stringify(errors));await b.close();console.log('RECORD_READY',frames.length);if(errors.length)throw Error(errors.join('\n'));
})().catch(e=>{console.error(e);process.exit(1)});
