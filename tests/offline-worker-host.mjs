// Execute the delivered classic Worker in a browser-shaped VM, without a browser,
// Node globals, disk reads, module imports or network inside the runtime.
import {parentPort,workerData} from 'node:worker_threads';
import vm from 'node:vm';
const forbidden=()=>{throw Error('Offline runtime attempted external I/O');};
const context=vm.createContext({console,setTimeout,clearTimeout,performance,TextEncoder,TextDecoder,
  URL,atob,btoa,fetch:forbidden,importScripts:forbidden,XMLHttpRequest:forbidden,
  location:{href:'blob:null/offline-test'},postMessage:value=>parentPort.postMessage(value),close:()=>parentPort.close()});
vm.runInContext('self=globalThis',context);
vm.runInContext(workerData,context,{timeout:5000});
parentPort.on('message',data=>context.onmessage({data}));
