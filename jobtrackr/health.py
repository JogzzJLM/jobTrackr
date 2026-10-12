from datetime import datetime, timezone
from . import store

def health():
 scan=store.setting('scan',{});last=store.setting('last_successful_scan',{})
 issues=[]
 if scan.get('error') or scan.get('errors'):issues.append('Discovery scan failed or incomplete')
 timestamp=last.get('finished') or (scan.get('finished') if not scan.get('error') else None)
 if timestamp:
  try:
   if (datetime.now(timezone.utc)-datetime.fromisoformat(timestamp)).total_seconds()>1800:issues.append('No successful discovery scan for over 30 minutes')
  except (ValueError,TypeError):issues.append('Discovery time unavailable')
 elif not scan.get('running'):issues.append('No successful discovery scan recorded')
 for key,label,flag in [('mail_health','Email','connected'),('sheet_health','Sheet','ok'),('notification_health','Notifications','ok')]:
  value=store.setting(key,{})
  if value.get(flag) is False and value.get('configured',True) and not value.get('pending'):issues.append(label+' needs attention')
 sources=store.setting('sources',{});failed=sum(v.get('ok') is False for v in sources.values())
 if failed:issues.append(str(failed)+' job sources unavailable; other sources continue')
 return {'ok':not issues,'alive':True,'status':'degraded' if issues else 'ok','issues':issues,'scan':scan,'last_successful_scan':last}
