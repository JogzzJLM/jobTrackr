/* Cache the server-saved preference to prevent a flash on reload. */
(function(){
 const profiles=['ocean','forest','berry','sunset'];
 const apply=value=>{const profile=profiles.includes(value)?value:'ocean';document.documentElement.dataset.palette=profile;try{localStorage.setItem('jobtrackr-colour',profile);}catch{}return profile;};
 let cached='ocean';try{cached=localStorage.getItem('jobtrackr-colour')||cached;}catch{}
 apply(cached);window.JobTheme={apply,profiles};
})();
