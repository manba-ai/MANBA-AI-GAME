// Test-only package builders. No prebuilt game is shipped with Play.
import {deflateSync} from 'node:zlib';
const code=`local status,ticks
function init() status='paused';ticks=0 end
function input(key)
 if key=='action' or key=='a' then status='running'
 elseif key=='pause' or key=='stop' then status='paused'
 elseif key=='restart' then init() end
end
function update(dt) if status=='running' and dt>0 then ticks=ticks+1 end return true end
function draw() screen.clear(0);screen.rect(10,20,4,4,65535) end
function snapshot() return {status=status,ticks=ticks,score=0} end
function records_restore(raw) return raw=='R1|' end
function records_export() return 'R1|' end
function records_finish() end
function records_storage(ok) end`;
export function runtimeFixture(){return {format:'edge.game/1',sdk:1,name:'Runtime check',engine:'custom',config:{viewport:{width:320,height:240}},requires:['records-v1'],records:{version:1,key:'1'.repeat(64)},code};}
export const runtimeRules={tests:[
 {name:'initial state',actions:[{kind:'step',value:50,count:3}],expect:[{path:'ticks',value:0},{path:'status',value:'paused'}]},
 {name:'start and pause',actions:[{kind:'input',value:'a'},{kind:'step',value:50,count:3},{kind:'input',value:'pause'},{kind:'step',value:50,count:5}],expect:[{path:'ticks',value:3},{path:'status',value:'paused'}]},
 {name:'restart',actions:[{kind:'input',value:'a'},{kind:'step',value:50,count:2},{kind:'input',value:'restart'}],expect:[{path:'ticks',value:0},{path:'status',value:'paused'}]}
]};
export function expandedFixture(){
 const pkg=runtimeFixture();pkg.runtime_profile='resources-v2';pkg.requires.push('resources-v2','graphics-v2','bitmap-v1');
 pkg.assets={bitmaps:Array.from({length:65},()=>({width:1,height:1,palette:'0000ffff'+'0000'.repeat(14),pixels:'1'}))};
 pkg.code+=`\nfunction draw() screen.clear(0);screen.sprite_region(65,30,20,0,0,1,1,false,4,4) end
 function snapshot() return {status=status,ticks=ticks,score=0,viewport={width=320,height=240},scene={{'c',0},{'R',65,30,20,0,0,1,1,false,4,4}}} end`;
 return pkg;
}
export function hdFixture(){
 const pkg=runtimeFixture(),raw=Buffer.alloc(641);raw[2]=255;raw[3]=255;raw[512]=15;raw[640]=1;
 pkg.requires.push('bitmap-v1','bitmap-indexed8-v2','bitmap-zlib-v1');
 pkg.assets={bitmaps:[{width:1,height:1,encoding:'indexed8-zlib',data:deflateSync(raw).toString('base64')}]};
 pkg.code+='\nfunction draw() screen.clear(0);screen.sprite(1,20,20,false) end';
 return pkg;
}
