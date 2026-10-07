/* Location variants stay separate records; only discovery cards are grouped. */
(function(root){
 'use strict';
 const words=v=>String(v||'').normalize('NFKC').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();
 const escape=v=>v.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
 const intake='(?:January|February|March|April|May|June|July|August|September|October|November|December|Spring|Summer|Autumn|Fall|Winter|20\\d{2})';
 // Geography aliases, not employer-specific programme rules.
 const officeAliases={'crawley':['Gatwick'],'stoke on trent':['Stoke'],'newcastle upon tyne':['Newcastle'],'newcastle':['Newcastle upon Tyne']};
 const regions=['Midlands','East Midlands','West Midlands','East Anglia','South East','South West','North East','North West','North East & West','Scotland','Wales','Northern Ireland','England','United Kingdom','UK'];
 function locationNames(j){
  const location=String(j.location||'');
  const parts=location.split(/[,;|]/).map(p=>p.trim()).filter(Boolean);
  const candidates=[location,...parts,...(officeAliases[words(location)]||[])];
  for(const p of parts)candidates.push(...(officeAliases[words(p)]||[]));
  return [...new Set(candidates.filter(Boolean))].sort((a,b)=>b.length-a.length);
 }
 function roleTitle(j){
  let title=String(j.title||'').normalize('NFKC');
  for(const name of locationNames(j)){
   const pattern=words(name).split(' ').map(escape).join('[\\s,()\\-–—/]+');
   // A location must end a title segment, or precede the intake date.
   // Preserve role phrases such as "London Market Analyst".
   title=title.replace(new RegExp('\\b'+pattern+'\\b(?=\\s*(?:$|[,()\\-–—]|'+intake+'\\b))','gi'),' ');
  }
  // Sources sometimes label the title with a region instead of the city in metadata.
  const regionPattern=regions.sort((a,b)=>b.length-a.length).map(name=>escape(name).replace(/ /g,'\\s+')).join('|');
  title=title.replace(new RegExp('\\s*[-–—|]\\s*(?:'+regionPattern+')\\s*(?=$|[-–—|]|'+intake+'\\b)','gi'),' ');
  return title.replace(/\s*[-–—]\s*[-–—]\s*/g,' - ').replace(/\s{2,}/g,' ').replace(/^[\s,()\-–—|]+|[\s,()\-–—|]+$/g,'').trim();
 }
 function programme(j){
  // Recruiter names do not identify the underlying employer reliably.
  if(j.route_type!=='Direct employer'||!words(j.company)||!j.location)return j.id;
  try{const u=new URL(j.apply_url||j.link);if(u.hostname==='student.kpmgcareers.co.uk'){
   const p=u.searchParams,keys=['programme','business_area','intake_year','start_date'];
   if(keys.every(k=>p.get(k)))return words(j.company)+'|'+keys.map(k=>words(p.get(k))).join('|');
  }}catch{}
  const title=words(roleTitle(j));
  return title?words(j.company)+'|'+title:j.id;
 }
 function group(items){
  const result=[],map=new Map();for(const j of items){const key=programme(j);let family=map.get(key);if(!family){family={...j,family_key:key,members:[]};map.set(key,family);result.push(family);}family.members.push(j);}
  for(const f of result){if(f.members.length>1)f.title=roleTitle(f);f.members.sort((a,b)=>String(a.location).localeCompare(b.location));}
  return result;
 }
 const api={programme,group,roleTitle};if(typeof module!=='undefined')module.exports=api;else root.JobGroups=api;
})(typeof window==='undefined'?{}:window);
