"""Public nonposting precision-first reconciliation; no dataset/key imports.
Evidence rules adapted from supplied starter, with strict input and global ambiguity.
Matches are proposals. Duplicate/late/amount-mismatch relationships remain review.
"""
from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass
import re,unicodedata
from .general_journal import materialize,identifier,money,business_date,fields
from .core import Blocked,digest

@dataclass(frozen=True)
class MatchPolicy:
    version: str='PUBLIC_PRECISION_FIRST_2'
    max_rows_per_side: int=1000
    max_comparisons: int=250000
    normal_days: int=12
    reference_review_days: int=45
    early_days: int=2
    name_overlap: float=.75

def normalize(v):
    if type(v)is not str or len(v)>4096:raise Blocked('INVALID_SCHEMA','bounded text')
    return re.sub(r'\s+',' ',re.sub('[^A-Z0-9]+',' ',unicodedata.normalize('NFKC',v).upper())).strip()

def references(text):
    return _references_normalized(normalize(text))


def _references_normalized(text):
    out=set()
    for prefix,number in re.findall(r'\b([A-Z]{2,12})\s*(\d{2,12})\b',text):
        out.add(('CHQ' if prefix in {'CHECK','CHEQUE','CHQ'} else prefix)+'-'+number)
    return out

def _party_tokens(name):
    return {x for x in normalize(name).split() if len(x)>=3 and x not in {'THE','AND','LTD','LLC','INC','CO'}}


def name_overlap(name,narrative):
    tokens=_party_tokens(name)
    if not tokens:return 0.0
    return len(tokens & set(normalize(narrative).split()))/len(tokens)

class BankReconciler:
    def __init__(self,policy=MatchPolicy()):self.policy=policy
    def prepare(self,ledger_entries,bank_lines):
        p=self.policy;ledger=materialize(ledger_entries,p.max_rows_per_side);bank=materialize(bank_lines,p.max_rows_per_side)
        if len(ledger)*len(bank)>p.max_comparisons:raise Blocked('PUBLIC_COMPARISON_BUDGET')
        for rows,kind in [(ledger,'ledger'),(bank,'bank')]:
            ids=set()
            for x in rows:
                required={'id','book','entry_date','reference','counterparty','amount'} if kind=='ledger' else {'id','account','posted_date','narrative','amount'}
                allowed=required|({'entered_by','entered_at','currency'} if kind=='ledger' else {'currency'})
                fields(x,required,allowed);id=identifier(x['id'])
                if id in ids:raise Blocked('INVALID_SCHEMA','duplicate record IDs')
                ids.add(id);x['id']=id
                normalize(x['book'] if kind=='ledger' else x['account'])
                business_date(x['entry_date'] if kind=='ledger' else x['posted_date']);money(x['amount'])
                for k in (['reference','counterparty'] if kind=='ledger' else ['narrative']):normalize(x[k])
                if 'currency' in x and (type(x['currency'])is not str or not re.fullmatch('[A-Z]{3}',x['currency'])):raise Blocked('INVALID_SCHEMA','currency')
        return ledger,bank
    def reconcile(self,ledger_entries,bank_lines):
        ledger,bank=self.prepare(ledger_entries,bank_lines)
        return self._reconcile_prepared(ledger,bank)

    def _reconcile_prepared(self,ledger,bank):
        policy=self.policy
        edges=[];review=[];contradictions=[]
        fingerprints=defaultdict(list)
        bank_groups=defaultdict(list)
        for b in bank:
            normalized=normalize(b['narrative'])
            amount=money(b['amount'])
            account=(b['account'],b.get('currency','UNSPECIFIED'))
            day=business_date(b['posted_date']).toordinal()
            bank_groups[account].append((day,b,amount,_references_normalized(normalized),set(normalized.split()),unicodedata.normalize('NFKC',b['narrative']).upper()))
            fingerprints[(*account,b['posted_date'],normalized,amount)].append(b['id'])
        dated_groups={}
        for account,items in bank_groups.items():
            items.sort(key=lambda row:row[0])
            dated_groups[account]=([row[0] for row in items],items)
        for l in ledger:
            dates,items=dated_groups.get((l['book'],l.get('currency','UNSPECIFIED')),([],[]))
            day=business_date(l['entry_date']).toordinal()
            lo=bisect_left(dates,day-policy.early_days)
            hi=bisect_right(dates,day+policy.reference_review_days)
            lr=references(l['reference'])
            lm=money(l['amount'])
            party=_party_tokens(l['counterparty'])
            party_refs=references(l['counterparty'])
            literal=unicodedata.normalize('NFKC',l['reference']).upper().strip()
            literal_pattern=None
            if len(literal)>=6 and re.search(r'[A-Z]',literal) and re.search(r'[0-9]',literal):
                literal_pattern=re.compile(r'(?<![A-Z0-9])'+re.escape(literal)+r'(?![A-Z0-9])')
            for bday,b,bm,br,words,narrative in items[lo:hi]:
                days=bday-day
                same=bool(lr and lr==br and len(lr)==1)
                # Raw reference proof may resolve a multi-token match or a bank token from the party name.
                # Unexplained extra reference tokens keep the relationship in conflict.
                if not same and literal_pattern and lr<=br and (br-lr)<=party_refs:
                    same=bool(literal_pattern.search(narrative))
                overlap=len(party & words)/len(party) if party else 0.0
                target=None
                if not same and lr and br and lr!=br:
                    if lm==bm and overlap>=policy.name_overlap:
                        target,reason=contradictions,'CONTRADICTORY_REFERENCE'
                elif lm==0 or bm==0 or (lm>0)!=(bm>0):
                    if same:
                        target,reason=contradictions,'SIGN_OR_ZERO_CONTRADICTION'
                elif lm!=bm:
                    if same:
                        target,reason=review,'REFERENCE_AMOUNT_MISMATCH_POSSIBLE_FEE_PARTIAL_OR_KEYING'
                elif days>policy.normal_days:
                    if same:
                        target,reason=review,'LATE_POSTING_REVIEW'
                elif same:
                    target,reason=edges,'EXACT_REFERENCE_AND_AMOUNT'
                elif not br and overlap>=policy.name_overlap:
                    target,reason=edges,'AMOUNT_AND_COUNTERPARTY'
                if target is not None:
                    evidence={'ledger_id':l['id'],'bank_id':b['id'],'days':days,
                              'difference_cents':lm-bm,'source_sha256':digest([l,b]),'reason':reason}
                    if target is edges:
                        evidence['status']='PUBLIC_NONPOSTING_PROPOSAL'
                    target.append(evidence)
        by_l=defaultdict(list);by_b=defaultdict(list)
        for e in edges:by_l[e['ledger_id']].append(e);by_b[e['bank_id']].append(e)
        duplicates=[sorted(v) for v in fingerprints.values() if len(v)>1];dupids={i for group in duplicates for i in group}
        def preferred(candidates):
            strong=[e for e in candidates if e['reason']=='EXACT_REFERENCE_AND_AMOUNT']
            return strong if strong else candidates
        preferred_left={key:preferred(candidates) for key,candidates in by_l.items()}
        preferred_right={key:preferred(candidates) for key,candidates in by_b.items()}
        matches=[];deferred=[]
        for e in edges:
            l=e['ledger_id'];b=e['bank_id'];pl=preferred_left[l];pb=preferred_right[b]
            if b in dupids:deferred.append({**e,'reason':'DUPLICATE_BANK_REVIEW'});continue
            if len(pl)!=1 or len(pb)!=1 or e!=pl[0] or e!=pb[0]:deferred.append({**e,'reason':'AMBIGUOUS_RELATIONSHIP'});continue
            matches.append(e)
        used_l={e['ledger_id'] for e in matches};used_b={e['bank_id'] for e in matches}
        assert len(used_l)==len(used_b)==len(matches)
        review=[item for item in review if item['bank_id'] not in used_b]
        p=policy
        order=lambda e:(e['ledger_id'],e['bank_id'])
        return {'scope':'PUBLIC_OFFLINE_NONPOSTING','policy_version':p.version,'matches':sorted(matches,key=order),'review_relationships':sorted(review,key=order),'deferred_ambiguous':sorted(deferred,key=order),'contradictions':sorted(contradictions,key=order),'duplicate_bank_groups':sorted(duplicates),'unmatched_ledger_ids':sorted({x['id'] for x in ledger}-used_l),'unmatched_bank_ids':sorted({x['id'] for x in bank}-used_b),'input_count':{'ledger':len(ledger),'bank':len(bank)},'predicted_pair_count':len(matches),'accounting_postings':0,'reconciliation_status':'REVIEW_REQUIRED' if len(used_l)!=len(ledger) or len(used_b)!=len(bank) else 'PROPOSALS_COMPLETE_NOT_POSTED','input_sha256':digest({'ledger':ledger,'bank':bank})}
