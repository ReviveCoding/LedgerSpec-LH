"""Durable append-only synthetic evaluation journal; not a governing authority.
SQLite transactions serialize admissions. Storage ACL/rollback custody is external.
"""
from contextlib import closing
from pathlib import Path
import sqlite3,json,hashlib,os
class Denied(ValueError):pass
def need(x,c):
 if not x:raise Denied(c)
def canon(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(b):return hashlib.sha256(b).hexdigest()
class Journal:
 def __init__(self,path,binding,*,create=False,lock_timeout=1.0):
  need(binding.get('realm')=='TEST_ONLY','REAL_JOURNAL_DEPLOYMENT_NOT_ENROLLED')
  need(0<lock_timeout<=5,'FINITE_LOCK_BUDGET')
  self.path=Path(path).absolute();self.binding=canon(binding);self.timeout=lock_timeout
  for p in (self.path,*self.path.parents):
   if p.exists():need(not p.is_symlink() and not getattr(p.lstat(),'st_file_attributes',0)&0x400,'JOURNAL_REPARSE')
  if create:
   with self.path.open('xb') as f:f.flush();os.fsync(f.fileno())
   with closing(self._db()) as db, db:
    db.execute('CREATE TABLE binding(raw BLOB NOT NULL)');db.execute('INSERT INTO binding VALUES(?)',(self.binding,))
    db.execute('CREATE TABLE events(seq INTEGER PRIMARY KEY, raw BLOB NOT NULL, sha TEXT NOT NULL UNIQUE)')
  need(self.path.exists(),'JOURNAL_MISSING_NO_RECREATE')
  st=self.path.stat();self.identity=(st.st_dev,st.st_ino)
  self.read()
 def _db(self):
  db=sqlite3.connect(self.path.as_uri()+'?mode=rw',uri=True,timeout=self.timeout)
  db.execute('PRAGMA synchronous=FULL');db.execute('PRAGMA trusted_schema=OFF');return db
 def _validate(self,db):
  st=self.path.stat();need(st.st_size<=2097152,'JOURNAL_SIZE_BOUND');need((st.st_dev,st.st_ino)==self.identity,'JOURNAL_FILE_REPLACED')
  need(not self.path.is_symlink() and not getattr(st,'st_file_attributes',0)&0x400,'JOURNAL_REPARSE')
  need(db.execute('PRAGMA integrity_check').fetchone()==('ok',),'JOURNAL_CORRUPT')
  need(db.execute('SELECT raw FROM binding').fetchall()==[(self.binding,)],'BINDING_DRIFT')
  parent=digest(self.binding);events=[];admitted={};completed=set();last_request=0
  bounded=db.execute('SELECT seq,raw,sha FROM events ORDER BY seq LIMIT 257').fetchall()
  need(len(bounded)<=256,'JOURNAL_EVENT_BOUND')
  for seq,raw,pin in bounded:
   need(type(raw)is bytes and len(raw)<=16384,'JOURNAL_ROW_BOUND')
   q=json.loads(raw);need(seq==len(events)+1 and digest(raw)==pin and q['previous']==parent and canon(q)==raw,'JOURNAL_CHAIN')
   need(set(q)=={'kind','previous','request_seq','input_sha','cohort_key','result_sha'},'EVENT_FIELDS')
   need(q['kind'] in ('ADMITTED','COMPLETED'),'EVENT_KIND')
   if q['kind']=='ADMITTED':
    need(q['request_seq']==last_request+1 and q['cohort_key'] not in admitted and q['result_sha'] is None,'ADMISSION_CHAIN')
    last_request=q['request_seq'];admitted[q['cohort_key']]=q
   else:
    a=admitted.get(q['cohort_key']);need(a and q['cohort_key'] not in completed and all(a[k]==q[k] for k in ('input_sha','request_seq')),'RESULT_CHAIN');completed.add(q['cohort_key'])
   parent=pin;events.append(q)
  return events,parent,admitted,completed,last_request
 def read(self):
  db=self._db()
  try:db.execute('PRAGMA query_only=ON');return self._validate(db)[0]
  finally:db.close()
 def append(self,kind,request_seq,input_sha,cohort_key,result_sha=None,*,fault=None):
  need(kind in ('ADMITTED','COMPLETED') and type(request_seq)is int,'EVENT_INPUT')
  need(all(type(x)is str and len(x)==64 and set(x)<=set('0123456789abcdef') for x in (input_sha,cohort_key)),'HASH_INPUT')
  db=self._db()
  try:
   db.execute('BEGIN IMMEDIATE');events,parent,admitted,completed,last=self._validate(db)
   if kind=='ADMITTED':need(request_seq==last+1 and cohort_key not in admitted and result_sha is None,'REPLAY_OR_SEQUENCE_OR_UNKNOWN')
   else:
    a=admitted.get(cohort_key);need(a and cohort_key not in completed and a['request_seq']==request_seq and a['input_sha']==input_sha,'RESULT_BINDING')
    need(type(result_sha)is str and len(result_sha)==64 and set(result_sha)<=set('0123456789abcdef'),'RESULT_HASH')
   q={'kind':kind,'previous':parent,'request_seq':request_seq,'input_sha':input_sha,'cohort_key':cohort_key,'result_sha':result_sha};b=canon(q)
   need(len(events)<256,'JOURNAL_EVENT_BOUND')
   db.execute('INSERT INTO events VALUES(?,?,?)',(len(events)+1,b,digest(b)))
   if fault:fault('BEFORE_COMMIT')
   db.commit()
   if fault:fault('AFTER_COMMIT')
   return digest(b)
  except BaseException:
   if db.in_transaction:db.rollback()
   raise
  finally:db.close()
