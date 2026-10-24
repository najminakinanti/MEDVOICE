import{c as r,_ as m}from"./Logo-VV9YcYDv.js";import{o as f,M as p,m as v,g as y,a as l,H as k,K as g,w as h,T as M,j as b}from"./index-h0ujFDGx.js";/**
 * @license lucide-vue-next v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const S=r("CircleCheckIcon",[["circle",{cx:"12",cy:"12",r:"10",key:"1mglay"}],["path",{d:"m9 12 2 2 4-4",key:"dzmm74"}]]);/**
 * @license lucide-vue-next v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const C=r("PlusIcon",[["path",{d:"M5 12h14",key:"1ays0h"}],["path",{d:"M12 5v14",key:"s699le"}]]);/**
 * @license lucide-vue-next v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const P=r("XIcon",[["path",{d:"M18 6 6 18",key:"1bl5f8"}],["path",{d:"m6 6 12 12",key:"d8bk6v"}]]),u="mv.mics";function D(){try{return{dokter:"",pasien:"",...JSON.parse(localStorage.getItem(u)||"{}")}}catch{return{dokter:"",pasien:""}}}function N(e){try{localStorage.setItem(u,JSON.stringify({dokter:e.dokter||"",pasien:e.pasien||""}))}catch{}}async function B(){return(await navigator.mediaDevices.getUserMedia({audio:!0})).getTracks().forEach(t=>t.stop()),(await navigator.mediaDevices.enumerateDevices()).filter(t=>t.kind==="audioinput").map((t,s)=>({id:t.deviceId,label:t.label||"Mikrofon "+(s+1)}))}async function K(e){const a=t=>navigator.mediaDevices.getUserMedia({audio:t});if(!e)return a(!0);try{return await a({deviceId:{exact:e}})}catch{return a(!0)}}function L(e=""){return/mp4|aac/.test(e)?"m4a":/ogg/.test(e)?"ogg":"webm"}const w=["aria-label"],x={__name:"Modal",props:{width:{type:Number,default:560},label:String},emits:["close"],setup(e,{emit:a}){const t=e,s=a,c=b(null),i=o=>{o.key==="Escape"&&s("close")};let n=null;return f(()=>{var o;n=document.activeElement,window.addEventListener("keydown",i),(o=c.value)==null||o.focus()}),p(()=>{window.removeEventListener("keydown",i),n&&n.focus&&n.focus()}),(o,d)=>(v(),y(M,{to:"body"},[l("div",{class:"back",onMousedown:d[0]||(d[0]=h(_=>s("close"),["self"]))},[l("div",{ref_key:"box",ref:c,class:"modal",role:"dialog","aria-modal":"true","aria-label":t.label,tabindex:"-1",style:k({maxWidth:e.width+"px"})},[g(o.$slots,"default",{},void 0)],12,w)],32)]))}},T=m(x,[["__scopeId","data-v-3391ba0f"]]);export{S as C,T as M,C as P,P as X,B as a,D as l,K as o,L as r,N as s};
