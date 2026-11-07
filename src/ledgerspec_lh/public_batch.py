import json
from collections import defaultdict
from .core import Blocked,canonical,digest
from .general_journal import materialize,identifier,validate_general_journals
from .reconciliation import BankReconciler
from .public_batch_contract import PAGE_SIZE
from .planning import Plan,Task,ToolCall

class PublicBatchMCP:
    def __init__(self,kind,data):
        self.kind=kind;data=self.data=json.loads(canonical(data));self.read_pages=set();self.results=[];self.result=None
        if kind=='GENERAL_JOURNALS':
            if set(data)!={'accounts','journal_entries','journal_lines'}:raise Blocked('INVALID_SCHEMA','journal input fields')
            self.entries=materialize(data['journal_entries'],1000);self.accounts=materialize(data['accounts'],10000);self.lines=materialize(data['journal_lines'],128000)
            ids=[identifier(e.get('id')) for e in self.entries]
            entry_ids=set(ids)
            if len(entry_ids)!=len(ids) or not ids:raise Blocked('INVALID_SCHEMA','entry identifiers')
            self.lines_by_entry=defaultdict(list)
            for position,line in enumerate(self.lines):
                entry_id=identifier(line.get('entry_id'))
                if entry_id not in entry_ids:raise Blocked('INVALID_SCHEMA','orphan journal lines')
                self.lines_by_entry[entry_id].append((position,line))
            self.pages=[self.entries[i:i+PAGE_SIZE] for i in range(0,len(self.entries),PAGE_SIZE)]
        elif kind=='BANK_RECONCILIATION':
            if set(data)!={'ledger_entries','bank_lines'}:raise Blocked('INVALID_SCHEMA','bank input fields')
            self.reconciler=BankReconciler()
            self.ledger,self.bank=self.reconciler.prepare(data['ledger_entries'],data['bank_lines'])
            rows=[{'side':'ledger','record':r} for r in self.ledger]+[{'side':'bank','record':r} for r in self.bank]
            if not rows:raise Blocked('INVALID_SCHEMA','empty bank batch')
            self.pages=[rows[i:i+PAGE_SIZE] for i in range(0,len(rows),PAGE_SIZE)]
        else:raise Blocked('UNSUPPORTED','public batch kind')
        if len(self.pages)>20:raise Blocked('PUBLIC_PAGE_LIMIT')
        self.page_digests=[digest(page) for page in self.pages]
        self.page_ids=[f'public-page-{i}-{value}' for i,value in enumerate(self.page_digests)]
    def call(self,call):
        name=call.name;args=call.arguments
        if name in {'read_public_page','validate_general_journal_page'}:
            if set(args)!={'page_index'} or type(args['page_index'])is not int or not 0<=args['page_index']<len(self.pages):raise Blocked('TOOL_SCHEMA')
            i=args['page_index'];page=self.pages[i]
            if len(page)>PAGE_SIZE:raise Blocked('PUBLIC_CALL_LIMIT')
            if name=='read_public_page':
                self.read_pages.add(i);return {'page_id':self.page_ids[i],'count':len(page),'digest':self.page_digests[i],'scope':'PUBLIC_READ_ONLY'}
            if self.kind!='GENERAL_JOURNALS' or i not in self.read_pages or any(r['page_index']==i for r in self.results):raise Blocked('PUBLIC_PAGE_STATE')
            lines=[line for _,line in sorted(item for entry in page for item in self.lines_by_entry[identifier(entry['id'])])]
            result=validate_general_journals(self.accounts,page,lines);self.results.append({'page_index':i,'decisions':result});return self.results[-1]
        if args:raise Blocked('TOOL_SCHEMA')
        if self.read_pages!=set(range(len(self.pages))):raise Blocked('PUBLIC_INCOMPLETE_READ')
        if name=='reconcile_public_bank_batch':
            if self.kind!='BANK_RECONCILIATION' or self.result is not None:raise Blocked('PUBLIC_BATCH_STATE')
            self.result=self.reconciler._reconcile_prepared(self.ledger,self.bank);return self.result
        if name=='finalize_public_analysis':
            if self.kind=='GENERAL_JOURNALS':
                if len(self.results)!=len(self.pages):raise Blocked('PUBLIC_INCOMPLETE_ANALYSIS')
                decisions=[x for r in sorted(self.results,key=lambda r:r['page_index']) for x in r['decisions']]
                if len(decisions)!=len(self.entries):raise Blocked('PUBLIC_COVERAGE')
                return {'decisions':decisions,'input_count':{'entries':len(self.entries),'lines':len(self.lines),'accounts':len(self.accounts)},'analysis_status':'COMPLETE','financial_effects':0}
            if self.result is None:raise Blocked('PUBLIC_INCOMPLETE_ANALYSIS')
            return {'reconciliation':self.result,'analysis_status':'COMPLETE_WITH_REVIEW' if self.result['reconciliation_status']=='REVIEW_REQUIRED' else 'COMPLETE_NONPOSTING_PROPOSALS','financial_effects':0}
        raise Blocked('TOOL_NOT_ADMITTED')

class PublicBatchPlanner:
    """Deterministic task planner for bounded accounting batches."""
    def plan(self,gateway):
        tasks=[];analysis=[]
        for i,id in enumerate(gateway.page_ids):
            read=f'read-{i}';tasks.append(Task(id=read,dependencies=[],source_ids=[id],tool=ToolCall(name='read_public_page',arguments={'page_index':i})))
            if gateway.kind=='GENERAL_JOURNALS':
                v=f'validate-{i}';tasks.append(Task(id=v,dependencies=[read],source_ids=[id],tool=ToolCall(name='validate_general_journal_page',arguments={'page_index':i})));analysis.append(v)
        if gateway.kind=='BANK_RECONCILIATION':
            # Up to 20 pages. Existing Task dependency bound is16: chain read pages, then depend on final read.
            for i in range(1,len(tasks)):tasks[i].dependencies=[tasks[i-1].id]
            tasks.append(Task(id='reconcile',dependencies=[tasks[-1].id],source_ids=gateway.page_ids,tool=ToolCall(name='reconcile_public_bank_batch',arguments={})));analysis=['reconcile']
        # Journals max1000 ->10 pages, preserving existing16 dependency and32 task bounds.
        tasks.append(Task(id='receipt',dependencies=analysis,source_ids=gateway.page_ids,tool=ToolCall(name='finalize_public_analysis',arguments={})))
        return Plan(tasks=tasks)
