from app.evidence import distribution
from app.modules.intake.service import intake
from app.modules.contract.service import normalize
from app.modules.quality.service import inspect
from app.modules.domain.service import calculate
from app.modules.reconcile.service import compare


def stages(source):
    raw = intake(source)
    contract, rejected = normalize(raw)
    quality = inspect(contract,rejected)
    accepted, domain_bad = calculate(quality['ready'])
    bad = sorted([*quality['rejected'],*domain_bad],key=lambda row:row['line'])
    return {'intake':raw,'contract':contract,'quality':quality,'accepted':accepted,
            'domain_bad':domain_bad,'rejected':bad}


def holds(accepted,book):
    """Tickets that cannot be confirmed: multi-zone common soak short or off-book.

    A ticket judged across zones or across a main/backup handover is only
    cleared when its longest common soak both meets the required minutes and
    agrees with the independent ledger. Legacy single-profile tickets keep the
    existing behaviour, where a difference merely requires a review note.
    """
    by_key = {row['key']:row for row in book['rows']}
    blocked = []
    for row in accepted:
        if not (row['multi'] or row['handover']):
            continue
        if row['short']:
            blocked.append({'key':row['key'],'line':row['line'],'code':'SOAK_SHORT',
                            'detail':f'共同保温 {row["amount"]} 分钟，少于要求的 {row["required"]} 分钟'})
            continue
        reference = by_key.get(row['key'])
        if reference is None or reference['code'] != 'MATCH':
            code = (reference or {}).get('code') or 'MISSING_BOOK'
            delta = (reference or {}).get('delta','0')
            blocked.append({'key':row['key'],'line':row['line'],'code':'HOLD_BOOK',
                            'detail':f'共同保温与外部账不符（{code}，差 {delta} 分钟）'})
    return blocked


def execute(source,book):
    result = stages(source)
    raw, accepted, bad = (result[key] for key in ('intake','accepted','rejected'))
    suppressed = result['quality']['suppressed']
    profiles = sum(row['profiles'] for row in accepted)
    counts = {'input':raw['input_count'],'accepted':profiles,'rejected':len(bad),
              'suppressed':len(suppressed),'blank':len(raw['blank_lines']),'repeated_header':len(raw['header_lines'])}
    balanced = counts['input'] == sum(value for key,value in counts.items() if key!='input')
    if not balanced:
        raise RuntimeError('来源记录数量无法闭合')
    reconciliation = compare(accepted,book)
    return {'counts':counts,'balanced':balanced,'accepted':accepted,'quarantine':bad,'suppressed':suppressed,
            'reasons':distribution(bad),'book':reconciliation,'encoding':raw['encoding'],
            'blocked':holds(accepted,reconciliation)}
