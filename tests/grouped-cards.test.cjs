const assert=require('node:assert/strict');const {group}=require('../jobtrackr/assets/groups.js');
const role=(id,city,year=2027,area='Audit ACA')=>({id,title:`Graduate ${area} ${city} Autumn ${year}`,company:'KPMG',location:city,route_type:'Direct employer',apply_url:`https://student.kpmgcareers.co.uk/graduates${year}/Login.aspx?programme=Graduate&business_area=${encodeURIComponent(area)}&intake_year=${year}&start_date=Autumn&location=${city}`});
let rows=group([role('1','London'),role('2','Leeds'),role('3','Bristol')]);assert.equal(rows.length,1);assert.equal(rows[0].members.length,3);assert(!rows[0].title.includes('London'));assert.equal(rows[0].members[0].location,'Bristol');
assert.equal(group([role('1','London'),role('2','Leeds',2026),role('3','Leeds',2027,'Tax ACA')]).length,3);
assert.equal(group([{...role('1','London'),route_type:'Recruiter advert'},{...role('2','Leeds'),route_type:'Recruiter advert'}]).length,2);
assert.equal(group([{id:'r1',company:'RSM',title:'Audit Graduate - Leeds - September 2027',location:'Leeds',route_type:'Direct employer'},{id:'r2',company:'RSM',title:'Audit Graduate - London - September 2027',location:'London',route_type:'Direct employer'}]).length,1);
console.log('Grouped programme and location tests passed');
