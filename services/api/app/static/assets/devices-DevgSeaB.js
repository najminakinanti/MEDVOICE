import{c as r}from"./Logo-pex2ByNW.js";/**
 * @license lucide-vue-next v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const s=r("CircleCheckIcon",[["circle",{cx:"12",cy:"12",r:"10",key:"1mglay"}],["path",{d:"m9 12 2 2 4-4",key:"dzmm74"}]]);/**
 * @license lucide-vue-next v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const o=r("XIcon",[["path",{d:"M18 6 6 18",key:"1bl5f8"}],["path",{d:"m6 6 12 12",key:"d8bk6v"}]]),c="mv.mics";function d(){try{return{dokter:"",pasien:"",...JSON.parse(localStorage.getItem(c)||"{}")}}catch{return{dokter:"",pasien:""}}}function u(e){try{localStorage.setItem(c,JSON.stringify({dokter:e.dokter||"",pasien:e.pasien||""}))}catch{}}async function m(){return(await navigator.mediaDevices.getUserMedia({audio:!0})).getTracks().forEach(t=>t.stop()),(await navigator.mediaDevices.enumerateDevices()).filter(t=>t.kind==="audioinput").map((t,i)=>({id:t.deviceId,label:t.label||"Mikrofon "+(i+1)}))}async function l(e){const a=t=>navigator.mediaDevices.getUserMedia({audio:t});if(!e)return a(!0);try{return await a({deviceId:{exact:e}})}catch{return a(!0)}}function g(e=""){return/mp4|aac/.test(e)?"m4a":/ogg/.test(e)?"ogg":"webm"}export{s as C,o as X,m as a,d as l,l as o,g as r,u as s};
