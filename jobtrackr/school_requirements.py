"""Evaluate published school requirements without treating a degree as a waiver."""
import re
SUBJECT=r"(?:mathematics|maths|math|english(?: language| literature)?)"
GRADE=r"(?:[1-9](?:\s*[-–/]\s*[1-9])?|[a-g]\*?(?:\s*[-–/]\s*[a-g]\*?)?|[1-9]\s*/\s*[a-g]|[a-g]\s*/\s*[1-9])"

def minimum_grade(text):
 values=re.findall(r"[1-9]|[a-g]\*?",text.lower())
 equivalent={'a*':8,'a':7,'b':5,'c':4,'d':3,'e':2,'f':1,'g':1}
 return min(int(v) if v.isdigit() else equivalent[v] for v in values) if values else None

def check(description,profile):
 reject=[];unknown=[]
 text=description.lower().replace('g.c.s.e.','gcse')
 for sentence in re.split(r'[.!?;\n]',text):
  if not re.search(r'\bgcses?\b',sentence):continue
  if re.search(r'no (?:minimum |specific )?(?:gcse|academic|grade)|(?:gcses?|grades?).{0,25}(?:not required|not considered)|do not (?:require|consider).{0,30}gcses?',sentence):continue
  if re.search(r'\b(?:preferred|desirable)\b',sentence) and not re.search(r'\b(?:must|required|essential|minimum)\b',sentence):continue
  subjects=list(re.finditer(r'\b'+SUBJECT+r'\b',sentence))
  if not subjects:continue
  grades=list(re.finditer(r'\bgrades?\s*(?:of |at least )?('+GRADE+r')(?![a-z0-9])',sentence))
  if not grades:
   grades=list(re.finditer(r'(?<![a-z0-9])('+GRADE+r')\s*(?:or above|and above|or higher|and higher|or equivalent|in (?:math|english)|including|gcses?)\b',sentence))
  # Grade immediately after a subject, e.g. "English C/4 and Maths B/6".
  local_grades={}
  for subject in subjects:
   tail=sentence[subject.end():]
   m=re.match(r'\s*(?:at |of |: |\(\s*)?(?:grade\s*)?('+GRADE+r')(?![a-z0-9])',tail)
   if m:
    token=(subject.end()+m.start(1),subject.end()+m.end(1),m.group(1));grades.append(token);local_grades[subject.start()]=token
  tokens=[(g.start(1),g.end(1),g.group(1)) if hasattr(g,'group') else g for g in grades]
  for subject in subjects:
   name='maths' if subject.group().startswith('math') else 'english'
   have=str(profile.get('gcse_'+name,'')).strip()
   if not tokens:
    unknown.append('GCSE '+name+' requirement needs confirmation');continue
   token=local_grades.get(subject.start()) or min(tokens,key=lambda g:(min(abs(subject.start()-g[1]),abs(g[0]-subject.end())),g[0]>subject.start()))
   minimum=minimum_grade(token[2])
   waiver=re.search(r'\b(?:waiv|discretion|case.by.case|mitigating|extenuating|contextual)',sentence)
   if not have.isdigit():unknown.append('GCSE '+name+' requirement needs confirmation')
   elif int(have)<minimum:
    if waiver:unknown.append('GCSE '+name+' exception needs employer confirmation')
    else:reject.append(f'GCSE {name} requires grade {minimum}; saved grade {have}')
 return list(dict.fromkeys(reject)),list(dict.fromkeys(unknown))
