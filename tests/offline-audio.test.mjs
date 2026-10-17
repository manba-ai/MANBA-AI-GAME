import test from 'node:test';
import assert from 'node:assert/strict';
import {deflateSync} from 'node:zlib';
import {resolve} from 'node:path';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const {decodeSample,validateAudioBank,renderAudio,sampleRate,GameAudioPlayer}=require(resolve(process.env.MANBA_TEST_SDK||'.work/sdk','runtime/play-runtime.cjs'));

const effect={id:'jump',wave:'pulse',frequency:440,end_frequency:880,duration_ms:100,volume:.3,duty:.5};
function sample(values,compressed=false){
  const data=Buffer.alloc(values.length*2);let previous=0;
  values.forEach((v,i)=>{const value=v&65535;data.writeUInt16LE(compressed?(value-previous)&65535:value,i*2);previous=value;});
  return {format:compressed?'pcm-s16le-delta-zlib':'pcm-s16le',sample_rate:16000,frames:values.length,chunks:[(compressed?deflateSync(data):data).toString('base64')]};
}
test('raw and delta-zlib PCM reproduce signed samples exactly including overflow and silence',()=>{
  const values=[0,32767,-32768,-1,0,12345,-12345];
  for(const compressed of [false,true])assert.deepEqual([...decodeSample(sample(values,compressed))],values.map(v=>v/32768));
  const pcm=sample(values,true);const bank={effects:[{id:'clip',volume:.5,sample:pcm}]};
  assert.deepEqual([...renderAudio(bank,'clip')],values.map(v=>Math.trunc(v*.5)/32768));
});
test('synth renders all waves and musical tempo locally with bounded finite output',()=>{
  for(const wave of ['pulse','triangle','noise','sine','saw']){
    const audio=renderAudio({effects:[{...effect,wave}]},'jump');
    assert.equal(audio.length,2400);assert.ok(audio.some(v=>v!==0));assert.ok(audio.every(v=>Number.isFinite(v)&&Math.abs(v)<=1));
  }
  const music=renderAudio({effects:[],music:{bpm:120,tracks:[{wave:'triangle',volume:.2,notes:[[69,4],[0,4]]}]}},'music');
  assert.equal(music.length,sampleRate);assert.ok(music.subarray(0,8000).some(v=>v!==0));assert.ok(music.subarray(8000).every(v=>v===0));
});
test('malformed audio and compressed bombs fail before unbounded allocation',()=>{
  assert.throws(()=>decodeSample({...sample([0]),frames:128001}));
  assert.throws(()=>decodeSample({...sample([0]),chunks:['%%%%']}));
  assert.throws(()=>decodeSample({...sample([0],true),chunks:[deflateSync(Buffer.alloc(1000000)).toString('base64')]}));
  assert.throws(()=>validateAudioBank({effects:[{...effect,duration_ms:1e9}]}));
  assert.throws(()=>validateAudioBank({effects:[effect,effect]}));
  assert.throws(()=>validateAudioBank({effects:[],music:{bpm:0,tracks:[]}}));
  assert.throws(()=>validateAudioBank({effects:[],music:{bpm:120,tracks:[{wave:'sine',volume:.1,notes:[[69,4]]},{wave:'sine',volume:.1,notes:[[69,8]]}]}}));
});
test('offline buffer path caches locally and never fetches audio',async t=>{
  t.mock.method(globalThis,'fetch',()=>{throw Error('Network forbidden');});
  const audio=new GameAudioPlayer();audio.configure({package:{assets:{audio:{effects:[effect]}}}});
  audio.context={createBuffer(channels,length,rate){assert.equal(channels,1);assert.equal(rate,16000);const samples=new Float32Array(length);return {getChannelData:()=>samples};}};
  const a=await audio.buffer('jump'),b=await audio.buffer('jump');assert.equal(a,b);assert.ok(a.getChannelData(0).some(v=>v!==0));
});
