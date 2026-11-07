"""Typed general journal arithmetic, PUBLIC/OFFLINE/NONPOSTING only.
Separate from accounting.validate_journal's strict adjusting-entry evidence policy.
Reference: owner-supplied starter e920ba85...; no publisher answer-key fields.
"""
from dataclasses import dataclass, asdict
from collections import defaultdict
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Literal
import re
from .core import Blocked, minor

def materialize(rows, limit):
    out=[]
    for r in rows:
        if len(out)>=limit: raise Blocked('PUBLIC_BATCH_LIMIT')
        if not isinstance(r,Mapping): raise Blocked('INVALID_SCHEMA','row mapping required')
        out.append(dict(r))
    return out

def identifier(v):
    if type(v) not in (str,int) or not str(v).strip() or len(str(v))>128:
        raise Blocked('INVALID_SCHEMA','identifier')
    return str(v)

def money(v):
    if type(v) not in (str,int,Decimal) or not re.fullmatch(r'[+-]?\d{1,14}(?:\.\d{1,2})?',str(v)):
        raise Blocked('INVALID_SCHEMA','exact decimal required; floats/bools forbidden')
    return minor(int(Decimal(str(v))*100))

def business_date(v):
    if type(v) is not str or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',v): raise Blocked('INVALID_SCHEMA','ISO date')
    try:return date.fromisoformat(v)
    except ValueError as e:raise Blocked('INVALID_SCHEMA','invalid date') from e

def fields(r,required,allowed):
    if not required<=set(r) or set(r)-allowed:raise Blocked('INVALID_SCHEMA','missing or unadmitted fields')

@dataclass(frozen=True)
class JournalDecision:
    entry_id: str
    status: Literal['ACCEPTED','UNBALANCED','INVALID_SCHEMA','UNSUPPORTED']
    reasons: tuple[str,...]
    debit_cents: int
    credit_cents: int
    difference_cents: int|None
    currency_differences: dict[str,int]
    line_count: int
    scope: str='PUBLIC_GENERAL_JOURNAL_ARITHMETIC_NO_POSTING'

class GeneralJournalValidator:
    MAX_ENTRIES=1000
    MAX_LINES_PER_ENTRY=128
    def validate(self,accounts,entries,lines):
        accounts=materialize(accounts,10000);entries=materialize(entries,self.MAX_ENTRIES);lines=materialize(lines,self.MAX_ENTRIES*self.MAX_LINES_PER_ENTRY)
        aid=[]
        for a in accounts:
            fields(a,{'id'},{'id','account_no','name'});aid.append(identifier(a['id']))
        if len(aid)!=len(set(aid)):raise Blocked('INVALID_SCHEMA','duplicate account')
        ids=[identifier(e.get('id')) for e in entries]
        entry_ids=set(ids)
        if len(ids)!=len(entry_ids):raise Blocked('INVALID_SCHEMA','duplicate entry')
        known=set(aid);indexed=defaultdict(list)
        for l in lines:
            fields(l,{'entry_id','account_id','line_no','debit_amount','credit_amount'},{'entry_id','account_id','line_no','debit_amount','credit_amount','currency'})
            eid=identifier(l['entry_id'])
            if eid not in entry_ids:raise Blocked('INVALID_SCHEMA','orphan journal line')
            indexed[eid].append(l)
        decisions=[]
        for e,eid in zip(entries,ids):
            problems=[];totals=defaultdict(int);debits=credits=0;ls=indexed[eid];nums=set()
            try:
                fields(e,{'id','entry_date'},{'id','entry_date','reference','amount','currency','period'})
                business_date(e['entry_date'])
                if 'period' in e and e['period']!=e['entry_date'][:7]:raise Blocked('INVALID_SCHEMA','entry period mismatch')
                if 'amount' in e:money(e['amount'])
            except Blocked as ex:problems.append(str(ex))
            if not 2<=len(ls)<=self.MAX_LINES_PER_ENTRY:problems.append('LINE_COUNT')
            for l in ls:
                try:
                    if identifier(l['account_id']) not in known:raise Blocked('INVALID_SCHEMA','unknown account')
                    n=identifier(l['line_no'])
                    if not re.fullmatch(r'[1-9][0-9]{0,5}',n) or n in nums:raise Blocked('INVALID_SCHEMA','line number')
                    nums.add(n)
                    d=0 if l['debit_amount'] in (None,'') else money(l['debit_amount'])
                    c=0 if l['credit_amount'] in (None,'') else money(l['credit_amount'])
                    if d<0 or c<0 or (d>0)==(c>0):raise Blocked('INVALID_SCHEMA','one positive side required')
                    currency=l.get('currency',e.get('currency','UNSPECIFIED'))
                    if type(currency)is not str or (currency!='UNSPECIFIED' and not re.fullmatch('[A-Z]{3}',currency)):raise Blocked('INVALID_SCHEMA','currency')
                    debits+=d;credits+=c;totals[currency]+=d-c
                    minor(debits);minor(credits)
                except Blocked as ex:problems.append(str(ex))
            status='INVALID_SCHEMA' if problems else 'UNBALANCED' if any(totals.values()) else 'ACCEPTED'
            if status=='UNBALANCED':problems.append('UNBALANCED')
            decisions.append(JournalDecision(eid,status,tuple(sorted(set(problems))),debits,credits,None if status=='INVALID_SCHEMA' else debits-credits,dict(totals),len(ls)))
        return decisions

def validate_general_journals(accounts,entries,lines):
    return [asdict(x) for x in GeneralJournalValidator().validate(accounts,entries,lines)]
