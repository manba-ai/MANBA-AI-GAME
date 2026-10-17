import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {createRequire} from 'node:module';
import {Worker} from 'node:worker_threads';
import {once} from 'node:events';
import vm from 'node:vm';
const require=createRequire(import.meta.url);
const {parseGame,maxFileBytes}=require(resolve(process.env.MANBA_TEST_SDK||'.work/sdk','runtime/play-runtime.cjs'));

import {runtimeFixture,runtimeRules,expandedFixture,hdFixture} from './runtime-fixtures.mjs';
const fixture=JSON.stringify(runtimeFixture());
const html=readFileSync(process.env.MANBA_TEST_PLAY||new URL('../play.html',import.meta.url),'utf8');
const imported=process.env.MANBA_TEST_PACKAGE?readFileSync(process.env.MANBA_TEST_PACKAGE,'utf8'):fixture;
const workerSource=JSON.parse(html.match(/const __workerSource=("(?:[^"\\]|\\.)*");/)[1]);
function worker(){return new Worker(new URL('./offline-worker-host.mjs',import.meta.url),{workerData:workerSource});}
async function message(w,data){const reply=once(w,'message');w.postMessage(data);return (await reply)[0];}

test('release Worker satisfies all authored rules of the imported game',{timeout:20000},async()=>{
  const pkg=JSON.parse(imported);
  const spec=process.env.MANBA_TEST_SPEC?JSON.parse(readFileSync(process.env.MANBA_TEST_SPEC,'utf8')):runtimeRules;
  for(const rule of spec.tests){
    const w=worker();
    try{
      let frame=await message(w,{type:'init',package:pkg});assert.equal(frame.ok,true,frame.error);
      for(const action of rule.actions){
        const command=action.kind==='input'?{type:'input',key:action.value}:action.kind==='buttons'?{type:'buttons',mask:action.value}:{type:'step',dt:action.value};
        for(let i=0;i<(action.count??1);i++){
          const reply=once(w,'message');w.postMessage(command);w.postMessage({type:'ack'});frame=(await reply)[0];
          assert.equal(frame.ok,true,frame.error);
        }
      }
      for(const expectation of rule.expect){
        assert.equal(expectation.op??'eq','eq','Fixture must use exact expected state');
        const value=expectation.path.split('.').reduce((state,key)=>state[key],frame.game);
        assert.deepEqual(value,expectation.value,rule.name+': '+expectation.path);
      }
    }finally{await w.terminate();}
  }
});

test('Play embeds its runtime without bundled games or external I/O',()=>{
  assert.doesNotMatch(html,/<(?:script|link|img)[^>]+(?:src|href)=/i);
  assert.doesNotMatch(html,/<script[^>]+type=["']module/i);
  assert.match(html,/connect-src 'none'/);
  assert.doesNotMatch(html,/new WebSocket|navigator\.(?:serial|usb)|\/trial\/v1\//);
  assert.match(workerSource,/data:application\/octet-stream;base64,AGFzb/);
  assert.doesNotMatch(workerSource,/importScripts\('\.\/wasmoon|await import\('\.\/engine|new URL\('\.\/glue/);
  for(const match of html.matchAll(/<script>([\s\S]*?)<\/script>/g))new vm.Script(match[1]);
  assert.doesNotMatch(html,/demo-star|demo-snake|DEMO_GAMES|Star Catch|薄荷贪吃蛇/);
  assert.match(html,/MANBA 手柄/);
});

test('page errors retain their location; extension errors never show a game failure',()=>{
  const scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
  const boxes=new Map(),handlers={};
  const box=id=>{if(!boxes.has(id))boxes.set(id,{hidden:true,textContent:''});return boxes.get(id);};
  vm.runInNewContext(scripts[0][1],{
    window:{addEventListener:(type,handler)=>{handlers[type]=handler;}},
    document:{getElementById:box},
  });
  const error={message:"Uncaught SyntaxError: Identifier 'l' has already been declared",lineno:17,colno:9};
  handlers.error({...error,filename:'chrome-extension://example/inpageScript.js'});
  assert.equal(box('notice').hidden,true);
  assert.equal(box('notice').textContent,'');
  handlers.error({...error,filename:'file:///portable/play.html'});
  assert.match(box('notice').textContent,/file:\/\/\/portable\/play\.html:17:9/);
  assert.equal(box('notice').hidden,false);
  const gameError=box('notice').textContent;
  for(const scheme of ['chrome-extension','moz-extension','safari-extension','safari-web-extension','blob:chrome-extension']){
    let suppressed=false;
    handlers.error({...error,filename:scheme+'://example/injected.js',preventDefault(){suppressed=true;}});
    assert.equal(box('notice').textContent,gameError);
    assert.equal(suppressed,false,'The browser console must retain the extension error');
  }
  handlers.error({...error,filename:'blob:null/worker'});
  assert.match(box('notice').textContent,/blob:null\/worker:17:9/);
  handlers.error({...error,filename:''});
  assert.match(box('notice').textContent,/来源：浏览器未提供/);
});

test('import accepts BOM, restores legacy controls, rejects wrong format and unsupported features',()=>{
  const version=parseGame('\uFEFF'+fixture);
  assert.equal(version.name,'Runtime check');assert.equal(version.spec.ui.controls.action,'确认 / 动作');
  assert.throws(()=>parseGame('bad'),/有效的游戏包/);
  assert.throws(()=>parseGame('{}'),/格式不兼容/);
  assert.throws(()=>parseGame(JSON.stringify({...version.package,config:{viewport:{width:320,height:320}}})),/320×240/);
  assert.throws(()=>parseGame(JSON.stringify({...version.package,requires:['buttons-v1','buttons-v1']})),/不支持的能力/);
  assert.throws(()=>parseGame(fixture+' '.repeat(524288)),/大小限制/);
  assert.throws(()=>parseGame(JSON.stringify({...version.package,requires:['future-v9']})),/不支持的能力/);
  assert.throws(()=>parseGame(JSON.stringify({...version.package,code:'x'.repeat(maxFileBytes+1)})),/大小限制/);
  assert.throws(()=>parseGame(JSON.stringify({...version.package,runtime_profile:'resources-v2'})),/配置不一致/);
  assert.throws(()=>parseGame(JSON.stringify({...version.package,ui:{controller:{}}})),/按键配置/);
});

test('actual embedded Worker boots WASM with no I/O, runs imported code, pauses and releases records',{timeout:20000},async()=>{
  const w=worker();
  try{
    const pkg=JSON.parse(fixture);
    let frame=await message(w,{type:'init',package:pkg});assert.equal(frame.ok,true,frame.error);
    assert.ok(frame.game.scene.length);assert.equal(frame.game.status,'paused');
    // Ack is intentionally withheld so each explicit command can be observed.
    let next=once(w,'message');w.postMessage({type:'input',key:'action'});w.postMessage({type:'ack'});
    frame=(await next)[0];assert.equal(frame.game.status,'running');
    next=once(w,'message');w.postMessage({type:'step',dt:33});w.postMessage({type:'ack'});frame=(await next)[0];assert.equal(frame.ok,true,frame.error);
    next=once(w,'message');w.postMessage({type:'input',key:'pause'});w.postMessage({type:'ack'});frame=(await next)[0];assert.equal(frame.game.status,'paused');
    frame=await message(w,{type:'close',records:true});assert.equal(frame.records_closed,true);assert.match(frame.records,/^R1\|/);
  }finally{await w.terminate();}
});

test('bad Lua terminates only its Worker; another game can still be loaded',{timeout:20000},async()=>{
  const bad=worker();
  try{const frame=await message(bad,{type:'init',package:{...JSON.parse(fixture),code:'not valid lua !!!'}});assert.ok(frame.error);}
  finally{await bad.terminate();}
  const good=worker();
  try{assert.equal((await message(good,{type:'init',package:JSON.parse(fixture)})).ok,true);}
  finally{await good.terminate();}
});

test('resources-v2 permits 65 bitmaps and graphics-v2; legacy rejects the same atlas',{timeout:20000},async()=>{
  const pkg=expandedFixture();
  assert.equal(pkg.assets.bitmaps.length,65);assert.equal(pkg.runtime_profile,'resources-v2');
  assert.throws(()=>parseGame(JSON.stringify({...pkg,runtime_profile:'legacy',requires:pkg.requires.filter(x=>x!=='resources-v2')})),/图集/);
  const version=parseGame(JSON.stringify(pkg)),w=worker();
  try{
    const frame=await message(w,{type:'init',package:version.package});
    assert.equal(frame.ok,true,frame.error);
    assert.ok(frame.game.scene.some(row=>row[0]==='R'));
  }finally{await w.terminate();}
});

test('embedded Worker decodes HD zlib assets and accepts A input',{timeout:20000},async()=>{
  const version=parseGame(JSON.stringify(hdFixture()));
  assert.ok(version.package.assets.bitmaps.some(b=>b.encoding==='indexed8-zlib'));
  const w=worker();
  const command=async data=>{const next=once(w,'message');w.postMessage(data);w.postMessage({type:'ack'});return (await next)[0];};
  try{
    let frame=await message(w,{type:'init',package:version.package});assert.equal(frame.ok,true,frame.error);
    assert.equal(frame.game.viewport.height,240);assert.ok(frame.game.scene.some(c=>c[0]==='s'));
    frame=await command({type:'input',key:'a'});assert.equal(frame.ok,true,frame.error);
    frame=await command({type:'input',key:'a'});assert.equal(frame.ok,true,frame.error);
    for(let i=0;i<30;i++)frame=await command({type:'step',dt:33});
    assert.equal(frame.ok,true,frame.error);assert.ok(frame.game.scene.length);
    frame=await command({type:'input',key:'pause'});assert.equal(frame.ok,true,frame.error);
  }finally{await w.terminate();}
});

// The complete delivered page is also evaluated with tiny DOM doubles. This is
// wiring/lifecycle coverage, not a browser or visual compatibility claim.
test('delivered page selects files, starts its embedded Worker and recovers from invalid input',{timeout:20000},async()=>{
  class Element {
    handlers={};dataset={};disabled=false;hidden=false;textContent='';value='';files=[];className='';
    addEventListener(type,fn){(this.handlers[type]??=[]).push(fn);}
    removeEventListener(){} setAttribute(){} insertAdjacentElement(){} setPointerCapture(){} click(){this.clicked=true;}
    querySelector(){return this.label??=new Element();}
    getContext(){return {fillRect(){},fillText(){},save(){},restore(){},drawImage(){},translate(){},scale(){},createImageData:(w,h)=>({data:new Uint8ClampedArray(w*h*4)}),putImageData(){}};}
    focus(){document.activeElement=this;} getBoundingClientRect(){return {left:0,top:0,width:320,height:240};}
  }
  const ids=new Map(),$=id=>{if(!ids.has(id))ids.set(id,new Element());return ids.get(id);};
  const keys=['restart','up','down','left','right','x','y','a','b'].map(key=>Object.assign(new Element(),{dataset:{key}}));
  const document=Object.assign(new Element(),{getElementById:$,createElement:()=>new Element(),hidden:false,hasFocus:()=>true,
    querySelectorAll:selector=>selector.startsWith('.face')?keys.slice(5):keys,body:{classList:{add(){},remove(){}}}});
  const sourceUrls=new Map(),workers=[],timers=new Set();
  const schedule=(fn,ms)=>{const id=setTimeout(()=>{timers.delete(id);fn();},ms);timers.add(id);return id;};
  class LocalWorker{
    constructor(url){
      this.node=new Worker(new URL('./offline-worker-host.mjs',import.meta.url),{workerData:sourceUrls.get(url).source});workers.push(this);
      this.node.on('message',data=>this.onmessage?.({data}));this.node.on('error',error=>this.onerror?.(error));
    }
    postMessage(value){this.node.postMessage(value);}terminate(){return this.node.terminate();}
  }
  const context=vm.createContext({document,console,location:{hostname:'',protocol:'file:',host:''},navigator:{getGamepads:()=>[]},
    WebAssembly,Worker:LocalWorker,Blob:class {constructor(parts){this.source=parts.join('');}},
    URL:{createObjectURL:blob=>{const url='blob:null/'+sourceUrls.size;sourceUrls.set(url,blob);return url;},revokeObjectURL:url=>sourceUrls.delete(url)},
    TextEncoder,TextDecoder,atob,btoa,performance,structuredClone,queueMicrotask,
    setTimeout:schedule,clearTimeout,setInterval:()=>0,requestAnimationFrame:fn=>schedule(fn,1),cancelAnimationFrame:clearTimeout,
    fetch:()=>{throw Error('Unexpected offline network request');}});
  context.window=Object.assign(new Element(),{});context.globalThis=context;
  async function until(predicate){for(let i=0;i<300;i++){if(predicate())return;await new Promise(resolve=>setTimeout(resolve,10));}throw Error('Page did not become ready: '+$('notice').textContent);}
  try{
    const scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
    $('notice').hidden=true;
    vm.runInContext(scripts[0][1],context,{timeout:5000});
    context.window.handlers.error[0]({
      message:"Uncaught SyntaxError: Identifier 'l' has already been declared",
      filename:'chrome-extension://example/inpageScript.js',lineno:1,colno:1,
    });
    assert.equal($('notice').hidden,true);
    // Host scripts may already use these names. Every Play module must remain
    // scoped so the delivered page can boot in that same global environment.
    vm.runInContext('const l=1,__modules=2,__workerSource=3;',context);
    vm.runInContext(scripts.at(-1)[1],context,{timeout:5000});
    assert.equal($('status').textContent,'等待选择游戏');
    $('file').files=[{name:'test.edgegame',size:Buffer.byteLength(imported),text:async()=>imported}];$('file').onchange();
    await until(()=>$('status').textContent==='离线运行中');
    assert.equal($('title').textContent,JSON.parse(imported).name);assert.equal($('play').disabled,false);
    $('play').onclick();await until(()=>$('play').textContent==='暂停');
    $('file').files=[{name:'broken.edgegame',size:3,text:async()=>'bad'}];$('file').onchange();
    await until(()=>$('status').textContent==='未能打开游戏');assert.match($('notice').textContent,/有效的游戏包/);
    $('file').files=[{name:'test.edgegame',size:Buffer.byteLength(imported),text:async()=>imported}];$('file').onchange();
    await until(()=>$('status').textContent==='离线运行中');assert.equal($('notice').hidden,true);
    $('reload').onclick();await until(()=>workers.length===3&&$('status').textContent==='离线运行中');
    assert.equal($('download').disabled,false);$('download').onclick();
    assert.ok([...sourceUrls.values()].some(v=>v.source===imported));
    const replacement=JSON.stringify({...JSON.parse(imported),name:'Second import'});
    $('file').files=[{name:'second.edgegame',size:Buffer.byteLength(replacement),text:async()=>replacement}];$('file').onchange();
    await until(()=>$('title').textContent==='Second import'&&$('status').textContent==='离线运行中');
  }finally{for(const id of timers)clearTimeout(id);await Promise.all(workers.map(w=>w.terminate()));}
});
