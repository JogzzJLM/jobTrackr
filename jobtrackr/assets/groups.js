/* Location variants stay separate records; only discovery cards are grouped. */
(function(root){
 'use strict';
 const words=v=>String(v||'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();
 const escape=v=>v.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
 function programme(j){
  if(j.route_type!=='Direct employer')return j.id;
  try{const u=new URL(j.apply_url||j.link);if(u.hostname==='student.kpmgcareers.co.uk'){
   const p=u.searchParams,keys=['programme','business_area','intake_year','start_date'];
   if(keys.every(k=>p.get(k)))return words(j.company)+'|'+keys.map(k=>words(p.get(k))).join('|');
  }}catch{}
  if(!j.location)return j.id;
  const title=String(j.title||'').replace(new RegExp('\\b'+escape(j.location)+'\\b','gi'),' ');
  return words(j.company)+'|'+words(title);
 }
 function title(j){return String(j.title||'').replace(j.location?new RegExp('\\b'+escape(j.location)+'\\b','gi'):/$^/,' ').replace(/\s*[-–]\s*[-–]\s*/g,' - ').replace(/\s{2,}/g,' ').replace(/^[\s-–]+|[\s-–]+$/g,'').trim();}
 function group(items){
  const result=[],map=new Map();for(const j of items){const key=programme(j);let family=map.get(key);if(!family){family={...j,family_key:key,members:[]};map.set(key,family);result.push(family);}family.members.push(j);}
  for(const f of result){if(f.members.length>1)f.title=title(f);f.members.sort((a,b)=>String(a.location).localeCompare(b.location));}
  return result;
 }
 const api={programme,group};if(typeof module!=='undefined')module.exports=api;else root.JobGroups=api;
})(typeof window==='undefined'?{}:window);
