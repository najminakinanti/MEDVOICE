import{P as i,m as d,c as h,Q as p,a as s,x as l,h as f,H as g}from"./index-h0ujFDGx.js";/**
 * @license lucide-vue-next v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const b=e=>e.replace(/([a-z0-9])([A-Z])/g,"$1-$2").toLowerCase();/**
 * @license lucide-vue-next v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */var r={xmlns:"http://www.w3.org/2000/svg",width:24,height:24,viewBox:"0 0 24 24",fill:"none",stroke:"currentColor","stroke-width":2,"stroke-linecap":"round","stroke-linejoin":"round"};/**
 * @license lucide-vue-next v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const m=({size:e,strokeWidth:a=2,absoluteStrokeWidth:t,color:o,iconNode:n,name:v,class:_,...k},{slots:c})=>i("svg",{...r,width:e||r.width,height:e||r.height,stroke:o||r.stroke,"stroke-width":t?Number(a)*24/Number(e):a,class:["lucide",`lucide-${b(v??"icon")}`],...k},[...n.map(u=>i(...u)),...c.default?[c.default()]:[]]);/**
 * @license lucide-vue-next v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const w=(e,a)=>(t,{slots:o})=>i(m,{...t,iconNode:a,name:e},o);/**
 * @license lucide-vue-next v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const N=w("MicIcon",[["path",{d:"M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z",key:"131961"}],["path",{d:"M19 10v2a7 7 0 0 1-14 0v-2",key:"1vc78b"}],["line",{x1:"12",x2:"12",y1:"19",y2:"22",key:"x3vr5v"}]]),y=(e,a)=>{const t=e.__vccOpts||e;for(const[o,n]of a)t[o]=n;return t},x={key:0,class:"word"},M={class:"name"},B={__name:"Logo",props:{light:Boolean,markOnly:Boolean,size:{type:Number,default:1}},setup(e){return(a,t)=>(d(),h("div",{class:"logo",style:g({"--s":e.size})},[t[0]||(t[0]=p('<svg class="mark" viewBox="0 0 112 60" aria-hidden="true" data-v-8880b4ae><defs data-v-8880b4ae><linearGradient id="lg1" x1="0" y1="0" x2="1" y2="0" data-v-8880b4ae><stop offset="0" stop-color="#9b7fe8" data-v-8880b4ae></stop><stop offset="1" stop-color="#3f2a96" data-v-8880b4ae></stop></linearGradient></defs><path d="M4 34h16l8-20 9 36 10-44 10 50 8-26h8" fill="none" stroke="url(#lg1)" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" data-v-8880b4ae></path><rect x="86" y="6" width="18" height="30" rx="9" fill="none" stroke="#5b3fc8" stroke-width="4" data-v-8880b4ae></rect><path d="M81 30a14 14 0 0 0 28 0M95 44v10M87 54h16" fill="none" stroke="#5b3fc8" stroke-width="4" stroke-linecap="round" data-v-8880b4ae></path><path d="M91 16v10M95 12v18M99 16v10" stroke="#9b7fe8" stroke-width="2.4" stroke-linecap="round" data-v-8880b4ae></path></svg>',1)),e.markOnly?f("",!0):(d(),h("div",x,[s("div",M,[s("span",{class:l(e.light?"l1":"n")},"Med",2),s("span",{class:l(e.light?"l2":"p")},"Voice",2)]),s("div",{class:l(["tag",{light:e.light}])},"AI Clinical Documentation",2)]))],4))}},I=y(B,[["__scopeId","data-v-8880b4ae"]]);export{I as L,N as M,y as _,w as c};
