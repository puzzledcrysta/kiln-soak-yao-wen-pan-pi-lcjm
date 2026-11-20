from collections import defaultdict
from app.errors import DataError
from app.evidence import finding
from app.settings import UNIT
from .rule import evaluate_ticket


def calculate(records):
    """Judge each ticket once, from all of its zone/probe profiles."""
    grouped, order = defaultdict(list), []
    for record in records:
        if not grouped[record['key']]:
            order.append(record['key'])
        grouped[record['key']].append(record)
    accepted, rejected = [], []
    for key in order:
        rows = grouped[key]
        try:
            amount, proof, zones, required, short, multi, shared, handovers = evaluate_ticket(rows)
        except DataError as error:
            rejected.extend(finding(row,error.code,str(error)) for row in rows)
            continue
        head = rows[0]
        accepted.append({'key':key,'line':head['line'],'revision':head['revision'],
                         'amount':format(amount,'f'),'unit':UNIT,'required':format(required,'f'),
                         'short':short,'multi':multi,'handover':bool(handovers),
                         'profiles':len(rows),
                         'common':[[f'{start:.3f}',f'{end:.3f}'] for start,end in shared],
                         'raw':head['raw'],'zones':zones,
                         'proof':[{'metric':label,'value':str(value),'unit':unit} for label,value,unit in proof]})
    return accepted,rejected
