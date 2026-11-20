from app.settings import KEY, FIELDS, ZONE_FIELD, PROBE_FIELD
from app.errors import DataError

REQUIRED = (KEY,'修订号','提交时间',*FIELDS)
ALIASES = {'业务编号':KEY,'版本':'修订号','更新时刻':'提交时间','备注':'原始备注',
           '窑区':ZONE_FIELD,'区':ZONE_FIELD,'探点':PROBE_FIELD,'测点类型':PROBE_FIELD}
MISSING = {'','-','n/a','null','未知'}


def mapping(header):
    names = [ALIASES.get(name,name) for name in header]
    if len(set(names)) != len(names) or set(REQUIRED)-set(names):
        raise DataError('CONTRACT','必需字段缺失或新旧字段重复')
    return names
