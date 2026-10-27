import{W as n,n as d,c as p,u as h,J as g}from"./index-DFWjcie_.js";/**
 * @license lucide-vue-next v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const _=e=>e.replace(/([a-z0-9])([A-Z])/g,"$1-$2").toLowerCase();/**
 * @license lucide-vue-next v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */var a={xmlns:"http://www.w3.org/2000/svg",width:24,height:24,viewBox:"0 0 24 24",fill:"none",stroke:"currentColor","stroke-width":2,"stroke-linecap":"round","stroke-linejoin":"round"};/**
 * @license lucide-vue-next v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const m=({size:e,strokeWidth:t=2,absoluteStrokeWidth:o,color:s,iconNode:c,name:l,class:x,...i},{slots:r})=>n("svg",{...a,width:e||a.width,height:e||a.height,stroke:s||a.stroke,"stroke-width":o?Number(t)*24/Number(e):t,class:["lucide",`lucide-${_(l??"icon")}`],...i},[...c.map(u=>n(...u)),...r.default?[r.default()]:[]]);/**
 * @license lucide-vue-next v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const v=(e,t)=>(o,{slots:s})=>n(m,{...o,iconNode:t,name:e},s);/**
 * @license lucide-vue-next v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const M=v("MicIcon",[["path",{d:"M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z",key:"131961"}],["path",{d:"M19 10v2a7 7 0 0 1-14 0v-2",key:"1vc78b"}],["line",{x1:"12",x2:"12",y1:"19",y2:"22",key:"x3vr5v"}]]),k="/ui/assets/logo-B-0fA6CA.png",f=(e,t)=>{const o=e.__vccOpts||e;for(const[s,c]of t)o[s]=c;return o},w=["src"],y={__name:"Logo",props:{size:{type:Number,default:1}},setup(e){return(t,o)=>(d(),p("img",{class:"logo",style:g({"--s":e.size}),src:h(k),alt:"MedVoice — AI Clinical Documentation"},null,12,w))}},A=f(y,[["__scopeId","data-v-5205891a"]]);export{A as L,M,f as _,v as c};
