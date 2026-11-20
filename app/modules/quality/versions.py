from collections import defaultdict
from app.evidence import finding


def profiles(zone, probe):
    return (zone, probe)


def split_versions(records, unverified):
    """Group records by ticket, resolve revisions, then by zone and probe.

    A ticket may carry one row per zone and probe at its winning revision, so
    several same-revision rows are legitimate as long as they describe distinct
    measurement points. Two rows claiming the same point must agree field for
    field; otherwise the ticket is quarantined.
    """
    groups = defaultdict(list)
    for record in records:
        groups[record['key']].append(record)
    ready, duplicates, conflicts = [], [], []
    for key, group in sorted(groups.items()):
        latest = max(row['revision'] for row in group)
        pending = unverified.get(key, 0)
        if pending >= latest:
            conflicts.extend(finding(row,'REV_BLOCKED',f'修订 {pending} 仍有来源未采信') for row in group)
            continue
        candidates = sorted((row for row in group if row['revision']==latest),key=lambda row:row['line'])
        older = [row for row in group if row['revision']!=latest]
        duplicates.extend(finding(row,'SUPERSEDED',f'修订 {latest} 取代旧版本') for row in older)
        by_point = defaultdict(list)
        for row in candidates:
            by_point[profiles(row['zone'], row['probe'])].append(row)
        clashes, chosen, repeated = [], [], []
        for point in sorted(by_point):
            rows = by_point[point]
            signatures = {tuple(row['fields'].items()) for row in rows}
            if len(signatures) > 1:
                clashes.extend(rows)
                continue
            chosen.append(rows[0])
            repeated.extend(rows[1:])
        if clashes:
            conflicts.extend(finding(row,'REV_CONFLICT',
                                     f'最高修订 {latest} 的 {row["zone"]}/{row["probe"]} 温程互相冲突')
                             for row in candidates)
            continue
        ready.extend(sorted(chosen,key=lambda row:row['line']))
        duplicates.extend(finding(row,'EXACT_DUP',f'同为修订 {latest}，保留第 {row["line"]} 行')
                          for row in repeated)
    return ready,duplicates,conflicts
