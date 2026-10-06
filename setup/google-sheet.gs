// One-time setup: bind this script to a separate JobTrackr sheet.
// Set Script Property JOBTRACKR_SYNC_TOKEN to the same secret as the stack.
// Deploy as a web app, execute as yourself, allow access to Anyone.
// The endpoint authenticates every request with that private token.
function doPost(e) {
  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    const data = JSON.parse(e.postData.contents);
    const token = PropertiesService.getScriptProperties().getProperty('JOBTRACKR_SYNC_TOKEN');
    if (!token || data.token !== token) throw new Error('Not authorised');
    if (!Array.isArray(data.jobs)) throw new Error('Invalid records');
    const book = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = book.getSheetByName('JobTrackr') || book.insertSheet('JobTrackr');
    const fields = ['id','company','title','location','link','status','notes','reminder','deadline','source'];
    sheet.getRange(1,1,1,fields.length).setValues([fields]);
    sheet.setFrozenRows(1);
    const existing = sheet.getLastRow()>1 ? sheet.getRange(2,1,sheet.getLastRow()-1,1).getValues() : [];
    const index = new Map(existing.map((row,i)=>[String(row[0]),i+2]));
    let next = sheet.getLastRow()+1;
    data.jobs.forEach(job=>{
      if (!job.id) throw new Error('Missing job ID');
      const row=index.get(String(job.id))||next++;
      index.set(String(job.id),row);
      // Prevent spreadsheet formulas in scraped text or notes.
      const values=fields.map(key=>{const value=String(job[key]||'');return /^[=+@-]/.test(value)?"'"+value:value;});
      sheet.getRange(row,1,1,fields.length).setValues([values]);
    });
    return ContentService.createTextOutput(JSON.stringify({ok:true,count:data.jobs.length})).setMimeType(ContentService.MimeType.JSON);
  } catch(error) {
    return ContentService.createTextOutput(JSON.stringify({ok:false})).setMimeType(ContentService.MimeType.JSON);
  } finally { lock.releaseLock(); }
}
