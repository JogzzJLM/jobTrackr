// Bound to JobTrackr's private applications spreadsheet.
// Script properties: JOBTRACKR_SPREADSHEET_ID and JOBTRACKR_SYNC_TOKEN.
// Deploy as yourself; Anyone may reach the endpoint, but every write requires the token.
function doPost(e) {
  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    const data = JSON.parse(e.postData.contents);
    const props = PropertiesService.getScriptProperties();
    const token = props.getProperty('JOBTRACKR_SYNC_TOKEN');
    if (!token || data.token !== token) throw new Error('Not authorised');
    if (data.layout !== 'applications-v2' || !Array.isArray(data.jobs)) throw new Error('Invalid layout');
    const stages = ['Applied','Assessment','Interview','Offer','Rejected','Withdrawn'];
    const safe = value => { const text=String(value || ''); return /^[=+@-]/.test(text) ? "'"+text : text; };
    const rows = data.jobs.map(job => {
      if (!job.id || !job.company || !job.title || !Array.isArray(job.stages) ||
          !job.stages.length || job.stages.length>10 || job.stages[0]!=='Applied' ||
          job.stages.some(stage=>!stages.includes(stage))) throw new Error('Invalid application');
      return [safe(job.company),safe(job.title),...Array.from({length:10},(_,i)=>safe(job.stages[i])),safe(job.id)];
    });
    const id = props.getProperty('JOBTRACKR_SPREADSHEET_ID');
    if (!id) throw new Error('Spreadsheet not configured');
    const book = SpreadsheetApp.openById(id);
    const sheet = book.getSheetByName('JobTrackr') || book.insertSheet('JobTrackr');
    const first = String(sheet.getRange(1,1).getValue());
    if (first && first!=='id' && first!=='Company') throw new Error('Unexpected sheet; existing data preserved');
    const oldRows = sheet.getLastRow();
    const headers = ['Company','Role',...Array.from({length:10},(_,i)=>'Stage '+(i+1)),'Job ID'];
    sheet.getRange(1,1,1,13).setValues([headers]);
    if (rows.length) sheet.getRange(2,1,rows.length,13).setValues(rows);
    // Remove the old discovery mirror and obsolete rows only from the managed tab.
    // Changes remain recoverable through Google Sheets version history.
    if (oldRows>rows.length+1) sheet.getRange(rows.length+2,1,oldRows-rows.length-1,13).clearContent();
    sheet.setFrozenRows(1);
    sheet.hideColumns(13);
    sheet.getRange(1,1,1,12).setFontWeight('bold').setBackground('#dbeafe');
    sheet.setColumnWidth(1,180); sheet.setColumnWidth(2,320); sheet.setColumnWidths(3,10,125);
    sheet.getRange(1,1,Math.max(rows.length+1,1),12).setWrap(true);
    return ContentService.createTextOutput(JSON.stringify({ok:true,count:rows.length,layout:'applications-v2'})).setMimeType(ContentService.MimeType.JSON);
  } catch(error) {
    return ContentService.createTextOutput(JSON.stringify({ok:false})).setMimeType(ContentService.MimeType.JSON);
  } finally { lock.releaseLock(); }
}
