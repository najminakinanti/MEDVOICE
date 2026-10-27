import{W as a,n as y,c as d,u as g,J as k}from"./index-rIn0-0fQ.js";/**
 * @license lucide-vue-next v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const p=e=>e.replace(/([a-z0-9])([A-Z])/g,"$1-$2").toLowerCase();/**
 * @license lucide-vue-next v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */var c={xmlns:"http://www.w3.org/2000/svg",width:24,height:24,viewBox:"0 0 24 24",fill:"none",stroke:"currentColor","stroke-width":2,"stroke-linecap":"round","stroke-linejoin":"round"};/**
 * @license lucide-vue-next v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const x=({size:e,strokeWidth:t=2,absoluteStrokeWidth:o,color:s,iconNode:r,name:l,class:f,...u},{slots:n})=>a("svg",{...c,width:e||c.width,height:e||c.height,stroke:s||c.stroke,"stroke-width":o?Number(t)*24/Number(e):t,class:["lucide",`lucide-${p(l??"icon")}`],...u},[...r.map(h=>a(...h)),...n.default?[n.default()]:[]]);/**
 * @license lucide-vue-next v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const i=(e,t)=>(o,{slots:s})=>a(x,{...o,iconNode:t,name:e},s);/**
 * @license lucide-vue-next v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const I=i("MicIcon",[["path",{d:"M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z",key:"131961"}],["path",{d:"M19 10v2a7 7 0 0 1-14 0v-2",key:"1vc78b"}],["line",{x1:"12",x2:"12",y1:"19",y2:"22",key:"x3vr5v"}]]);/**
 * @license lucide-vue-next v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const M=i("ServerIcon",[["rect",{width:"20",height:"8",x:"2",y:"2",rx:"2",ry:"2",key:"ngkwjq"}],["rect",{width:"20",height:"8",x:"2",y:"14",rx:"2",ry:"2",key:"iecqi9"}],["line",{x1:"6",x2:"6.01",y1:"6",y2:"6",key:"16zg32"}],["line",{x1:"6",x2:"6.01",y1:"18",y2:"18",key:"nzw8ys"}]]),v="/ui/assets/logo-B-0fA6CA.png",w=(e,t)=>{const o=e.__vccOpts||e;for(const[s,r]of t)o[s]=r;return o},_=["src"],m={__name:"Logo",props:{size:{type:Number,default:1}},setup(e){return(t,o)=>(y(),d("img",{class:"logo",style:k({"--s":e.size}),src:g(v),alt:"MedVoice — AI Clinical Documentation"},null,12,_))}},A=w(m,[["__scopeId","data-v-5205891a"]]);export{A as L,I as M,M as S,w as _,i as c};
