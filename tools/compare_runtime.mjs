// Headless Node/Wasm vs native snapshots: no browser is launched.
import {readFileSync, writeFileSync, mkdtempSync, rmSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {join, resolve} from 'node:path';
import {tmpdir} from 'node:os';
import {createRequire} from 'node:module';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';

const [sdkArg, packagePath, specPath, output, baselinePath] = process.argv.slice(2);
if (!output) throw new Error('Usage: node compare_runtime.mjs SDK PACKAGE SPEC OUTPUT');
const sdk=resolve(sdkArg), raw=readFileSync(packagePath), pkg=JSON.parse(raw), spec=JSON.parse(readFileSync(specPath));
const baselineRaw=baselinePath?readFileSync(baselinePath):null,baseline=baselineRaw?JSON.parse(baselineRaw):null;
const require=createRequire(import.meta.url);
const {createTrialEngine,wasmoon}=require(join(sdk,'runtime/play-runtime.cjs'));
let observations=0;
function same(a,b,path='state') {
  if(typeof b==='number'){assert.equal(typeof a,'number',path);assert.ok(Math.abs(a-b)<1e-6,`${path}: ${a} != ${b}`);return;}
  if(b&&typeof b==='object'){assert.ok(a&&typeof a==='object',path);assert.deepEqual(Object.keys(a).sort(),Object.keys(b).sort(),path);for(const key of Object.keys(b))same(a[key],b[key],`${path}.${key}`);return;}
  assert.deepEqual(a,b,path);
}
const dir=mkdtempSync(join(tmpdir(),'edgegame-vm-'));
try {
  writeFileSync(join(dir,'game.lua'),pkg.code);
  writeFileSync(join(dir,'assets.lua'),(pkg.assets?.bitmaps??[]).map((b,i)=>`screen.define_bitmap(${i+1},${b.width},${b.height},"${b.encoding??b.palette}","${b.data??b.pixels}"${b.alpha===undefined?'':`,"${b.alpha}"`})`).join('\n'));
  const cases=[...spec.tests,{name:'lifecycle stress',actions:[
    {kind:'input',value:'a'},{kind:'step',value:50,count:180},{kind:'input',value:'pause'},
    {kind:'step',value:50,count:30},{kind:'input',value:'a'},{kind:'input',value:'stop'},
    {kind:'step',value:50,count:30},{kind:'input',value:'restart'},{kind:'input',value:'b'}]}];
  for(const test of cases){
    const commands=[];
    for(const a of test.actions) for(let i=0;i<(a.count??1);i++) commands.push(a.kind==='input'?[`key ${a.value}`,{type:'input',key:a.value}]:a.kind==='buttons'?[`buttons ${a.value}`,{type:'buttons',mask:a.value}]:[`step ${a.value}`,{type:'step',dt:a.value}]);
    const flags=[...(pkg.runtime_profile==='resources-v2'?['--resources-v2']:[]),...(pkg.requires?.includes('graphics-v2')?['--graphics-v2']:[])];
    const native=spawnSync(join(sdk,'.tools/bin/game-runner'),[join(dir,'game.lua'),join(dir,'assets.lua'),...flags],{input:commands.map(c=>c[0]).join('\n')+'\nquit\n',encoding:'utf8',maxBuffer:128*1024*1024,timeout:30000});
    assert.equal(native.status,0,native.stderr||native.error?.message||native.stdout.slice(-1000));
    const expected=native.stdout.trim().split('\n').map(JSON.parse);
    const engine=await createTrialEngine(wasmoon,join(sdk,'runtime/glue.wasm'),pkg);
    const previous=baseline?await createTrialEngine(wasmoon,join(sdk,'runtime/glue.wasm'),baseline):null;
    try {
      const actual=[engine.initial,...commands.map(c=>engine.command(c[1]))];
      const historic=previous?[previous.initial,...commands.map(c=>previous.command(c[1]))]:null;
      assert.equal(actual.length,expected.length);
      for(let i=0;i<actual.length;i++){
        assert.equal(expected[i].ok,true,JSON.stringify(expected[i]));
        same(actual[i].game,expected[i].game,`${test.name}[${i}]`);
        same(actual[i].audio,expected[i].audio,'audio');observations++;
        if(historic){same(actual[i].game,historic[i].game,'historical state/scene');same(actual[i].audio,historic[i].audio,'historical audio');}
      }
    }finally{engine.close();previous?.close();}
  }
  const report={passed:true,package_sha256:createHash('sha256').update(raw).digest('hex'),observations,cases:cases.length,scope:'Node/Wasm and native snapshots/audio; no browser'};
  if(baselineRaw){report.baseline_package_sha256=createHash('sha256').update(baselineRaw).digest('hex');report.matches_baseline_observations=true;}
  writeFileSync(output,JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
}finally{rmSync(dir,{recursive:true,force:true});}
