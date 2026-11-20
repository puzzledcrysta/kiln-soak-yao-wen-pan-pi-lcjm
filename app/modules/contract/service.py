from app.errors import DataError
from app.evidence import finding
from app.settings import KEY, FIELDS, ZONE_FIELD, PROBE_FIELD, DEFAULT_ZONE, PROBES
from app.modules.domain.values import whole, instant
from .schema import mapping, REQUIRED, MISSING


def zone_probe(values):
    zone = (values.get(ZONE_FIELD) or DEFAULT_ZONE).strip()
    probe = (values.get(PROBE_FIELD) or PROBES[0]).strip()
    if not zone or zone.casefold() in MISSING:
        raise DataError('REQUIRED', '分区不能为空')
    if probe.casefold() in MISSING:
        probe = PROBES[0]
    if probe not in PROBES:
        raise DataError('PROBE', '探头须为 主 或 备')
    return zone, probe


def normalize(source):
    names = mapping(source['header'])
    passed, rejected = [], list(source['rejected'])
    for record in source['rows']:
        values = dict(zip(names,record['values']))
        key = values[KEY]
        revision = None
        try:
            if not any(values[k].casefold() in MISSING for k in (KEY,'修订号')):
                revision = whole(values['修订号'],1,10**9)
            if any(values[k].casefold() in MISSING for k in REQUIRED):
                raise DataError('REQUIRED','主键、修订号、时间和业务字段均须填写')
            changed = instant(values['提交时间']).isoformat()
            zone, probe = zone_probe(values)
        except DataError as error:
            issue = finding(dict(record,key=key),error.code,str(error))
            if revision is not None:
                issue['revision'] = revision
            rejected.append(issue)
            continue
        passed.append({'key':key,'revision':revision,'time':changed,'line':record['line'],
                       'raw':record['raw'],'fields':{field:values[field] for field in FIELDS},
                       'zone':zone,'probe':probe,'note':values.get('原始备注','')})
    return passed, rejected
