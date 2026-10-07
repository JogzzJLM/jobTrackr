"""ApplicationTrackr-style Sankey, using actual recorded stage transitions."""
from collections import Counter
from . import store
STAGES=('Applied','Assessment','Interview','Offer','Rejected','Withdrawn')
COLORS={'Applications':'#4f46e5','Applied':'#4f46e5','Assessment':'#af52de','Interview':'#ff9500','Offer':'#34c759','Rejected':'#ff3b30','Withdrawn':'#8e8e93'}
def counts(jobs):
 flows=Counter()
 for job in jobs:
  if job['status'] not in STAGES:continue
  stages=[]
  for record in reversed(store.history(job['id'])):
   event=record['event'];stage=event.removeprefix('Status: ')
   if event.startswith('Status: ') and stage in STAGES and stage not in stages:stages.append(stage)
  if not stages:stages=[job['status']]
  if job['status'] in stages:stages=stages[:stages.index(job['status'])+1]
  else:stages.append(job['status'])
  for a,b in zip(['Applications']+stages,stages):
   if a!=b:flows[a,b]+=1
 return flows

def sheet_counts(rows):
 flows=Counter()
 for row in rows:
  stages=[]
  for value in row.get('stages',[]):
   if value and (not stages or stages[-1]!=value):stages.append(value)
  for a,b in zip(['Applications']+stages,stages):
   if a!=b:flows[a,b]+=1
 return flows

def html():
 import plotly.graph_objects as go
 rows=store.setting('sheet_rows',None)
 from . import sheets
 flows=sheet_counts(sheets.snapshot()) if rows is None else sheet_counts(rows)
 if not flows:return '<html><body style="font:15px system-ui;color:#555;padding:24px">Your application flow will appear when you track your first application.</body></html>'
 nodes=['Applications']+list(dict.fromkeys(s for pair in flows for s in pair if s!='Applications'))
 totals=Counter()
 for (a,b),n in flows.items():totals[b]+=n
 totals['Applications']=sum(n for (a,b),n in flows.items() if a=='Applications')
 fig=go.Figure(go.Sankey(arrangement='snap',node={'pad':24,'thickness':20,'label':[f'{s} ({totals[s]})' for s in nodes],'color':[COLORS.get(s,'#64748b') for s in nodes]},link={'source':[nodes.index(a) for a,b in flows],'target':[nodes.index(b) for a,b in flows],'value':list(flows.values()),'color':['rgba(79,70,229,0.18)']*len(flows)}))
 fig.update_layout(font_size=13,font_family='Inter,system-ui',height=210,margin={'l':15,'r':15,'t':15,'b':15},paper_bgcolor='white')
 return fig.to_html(include_plotlyjs='/assets/plotly.js',full_html=True,config={'responsive':True,'displayModeBar':False})
