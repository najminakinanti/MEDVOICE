import{c as i,_ as u}from"./Logo-pex2ByNW.js";import{o as m,O as f,n as p,h as y,a as d,J as v,M as w,w as b,T as k,k as h}from"./index-rIn0-0fQ.js";/**
 * @license lucide-vue-next v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const I=i("PlusIcon",[["path",{d:"M5 12h14",key:"1ays0h"}],["path",{d:"M12 5v14",key:"s699le"}]]),M=["aria-label"],_={__name:"Modal",props:{width:{type:Number,default:560},label:String},emits:["close"],setup(a,{emit:r}){const c=a,s=r,t=h(null),n=e=>{e.key==="Escape"&&s("close")};let o=null;return m(()=>{var e;o=document.activeElement,window.addEventListener("keydown",n),(e=t.value)==null||e.focus()}),f(()=>{window.removeEventListener("keydown",n),o&&o.focus&&o.focus()}),(e,l)=>(p(),y(k,{to:"body"},[d("div",{class:"back",onMousedown:l[0]||(l[0]=b(x=>s("close"),["self"]))},[d("div",{ref_key:"box",ref:t,class:"modal",role:"dialog","aria-modal":"true","aria-label":c.label,tabindex:"-1",style:v({maxWidth:a.width+"px"})},[w(e.$slots,"default",{},void 0)],12,M)],32)]))}},L=u(_,[["__scopeId","data-v-5ea55449"]]);export{L as M,I as P};
