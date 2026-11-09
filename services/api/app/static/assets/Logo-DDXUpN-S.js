import{Y as n,n as g,c as k,u as a,W as i,J as p,B as m}from"./index-CSryPS8y.js";/**
 * @license lucide-vue-next v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const v=e=>e.replace(/([a-z0-9])([A-Z])/g,"$1-$2").toLowerCase();/**
 * @license lucide-vue-next v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */var r={xmlns:"http://www.w3.org/2000/svg",width:24,height:24,viewBox:"0 0 24 24",fill:"none",stroke:"currentColor","stroke-width":2,"stroke-linecap":"round","stroke-linejoin":"round"};/**
 * @license lucide-vue-next v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const _=({size:e,strokeWidth:o=2,absoluteStrokeWidth:t,color:s,iconNode:c,name:d,class:L,...u},{slots:l})=>n("svg",{...r,width:e||r.width,height:e||r.height,stroke:s||r.stroke,"stroke-width":t?Number(o)*24/Number(e):o,class:["lucide",`lucide-${v(d??"icon")}`],...u},[...c.map(h=>n(...h)),...l.default?[l.default()]:[]]);/**
 * @license lucide-vue-next v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const f=(e,o)=>(t,{slots:s})=>n(_,{...t,iconNode:o,name:e},s);/**
 * @license lucide-vue-next v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const M=f("MicIcon",[["path",{d:"M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z",key:"131961"}],["path",{d:"M19 10v2a7 7 0 0 1-14 0v-2",key:"1vc78b"}],["line",{x1:"12",x2:"12",y1:"19",y2:"22",key:"x3vr5v"}]]),w="/ui/assets/logo-B-0fA6CA.png",y="/ui/assets/logo-hero-BiVLldVV.png",x=(e,o)=>{const t=e.__vccOpts||e;for(const[s,c]of o)t[s]=c;return t},b=["src"],B={__name:"Logo",props:{size:{type:Number,default:1},dark:Boolean},setup(e){const o=e;return(t,s)=>(g(),k("img",{class:m(["logo",{dark:o.dark||a(i).dark}]),style:p({"--s":e.size}),src:o.dark||a(i).dark?a(y):a(w),alt:"MedVoice — AI Clinical Documentation"},null,14,b))}},A=x(B,[["__scopeId","data-v-6d153af8"]]);export{A as L,M,x as _,f as c,y as h};
