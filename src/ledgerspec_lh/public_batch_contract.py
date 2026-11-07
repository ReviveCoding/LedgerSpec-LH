"""Additional public offline tools; no extension to protected effect authority."""
PAGE_SIZE=100
PUBLIC_TOOLS={n:{'risk':'read_only' if n=='read_public_page' else 'proposal','idempotency':'source-and-batch-digest','scope':'PUBLIC_OFFLINE_NONPOSTING','schema':'public-batch-1','timeout_seconds':5,'retries':0} for n in ['read_public_page','validate_general_journal_page','reconcile_public_bank_batch','finalize_public_analysis']}
def tool_schemas():
    integer={'type':'integer','minimum':0,'maximum':19}
    return {n:{'type':'object','properties':{'page_index':integer},'required':['page_index'],'additionalProperties':False} if n in ['read_public_page','validate_general_journal_page'] else {'type':'object','properties':{},'additionalProperties':False} for n in PUBLIC_TOOLS}
