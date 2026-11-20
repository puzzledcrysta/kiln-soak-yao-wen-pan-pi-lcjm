from decimal import Decimal as D
from app.errors import DataError
from .values import number, parts


def profile(fields):
    """Normalize one temperature profile: one zone measured by one probe."""
    scale = fields['温标'].upper()
    if scale not in {'C', 'F'}:
        raise DataError('TEMP_SCALE', '温标须为 C 或 F')
    target = number(fields['阈值摄氏度'], 0, 1800)
    limit = number(fields['最大采样间隔分钟'], D('0.001'), 1440)
    required = number(fields['要求保温分钟'], D('0.001'), 1440)
    readings = {}
    for reading in parts(fields['测温点']):
        tick, sep, raw = reading.partition(':')
        if not sep:
            raise DataError('TEMP_POINT', '测温点须包含分钟和温度')
        minute = number(tick, 0, 10080)
        temp = number(raw, -100, 3300)
        if minute in readings and readings[minute] != temp:
            raise DataError('TEMP_CONFLICT', f'第 {minute} 分钟温度冲突')
        readings[minute] = temp
    if len(readings) < 2:
        raise DataError('TEMP_COVERAGE', '至少需要两个不同采样点')
    if scale == 'F':
        target = target * 9 / 5 + 32
    return {'scale': scale, 'target': target, 'limit': limit,
            'required': required, 'readings': readings}


def segments(readings, target, limit):
    """Soak intervals for a single probe. A gap or a dip ends continuity."""
    spans, gaps = [], []
    ordered = sorted(readings.items())
    for (left, a), (right, b) in zip(ordered, ordered[1:]):
        if right-left > limit:
            gaps.append((f'{left}–{right} 缺测', right-left, '分钟'))
            continue
        if max(a, b) < target or max(a, b) == target > min(a, b):
            continue
        start, end = left, right
        if min(a, b) < target:
            crossing = left + (target-a)*(right-left)/(b-a)
            start, end = (crossing, right) if a < b else (left, crossing)
        if spans and spans[-1][1] == start:
            spans[-1] = (spans[-1][0], end)
        else:
            spans.append((start, end))
    return spans, gaps


def longest(spans):
    return max((end-start for start, end in spans), default=D(0))


def merge(spans):
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def activity(readings, limit):
    """Minute windows a probe actually sampled: consecutive reads within limit."""
    ordered = sorted(readings.items())
    return merge([(left, right) for (left, _), (right, _) in zip(ordered, ordered[1:])
                  if right-left <= limit])


def intersect(first, second):
    shared, left, right = [], 0, 0
    while left < len(first) and right < len(second):
        start = max(first[left][0], second[right][0])
        end = min(first[left][1], second[right][1])
        if start < end:
            shared.append((start, end))
        if first[left][1] < second[right][1]:
            left += 1
        else:
            right += 1
    return shared


def subtract(spans, windows):
    """Remove ``windows`` from ``spans``; used to replace a probe's account of
    the handover window with the two-probe consensus."""
    pieces = list(spans)
    for cut_start, cut_end in windows:
        remaining = []
        for start, end in pieces:
            if cut_end <= start or cut_start >= end:
                remaining.append((start, end))
                continue
            if start < cut_start:
                remaining.append((start, cut_start))
            if cut_end < end:
                remaining.append((cut_end, end))
        pieces = remaining
    return pieces


def handover(first, second):
    """What the two probes together prove about one zone's continuity.

    Returns ``(witnessed, note)``. The change-over is witnessed only when both
    probes read at least one common minute, so both readings attest to the
    boundary. Any common minute where they disagree about being at temperature
    is reported, and the zone is never counted as soaking there.
    """
    shared = sorted(set(first['readings']) & set(second['readings']))
    if not shared:
        return False, '两支探头无同刻读数作证，不能续算'
    conflicts = [minute for minute in shared
                 if (first['readings'][minute] >= first['target'])
                 != (second['readings'][minute] >= second['target'])]
    if not any(first['readings'][minute] >= first['target'] for minute in shared):
        return True, '交接同刻读数均为掉温，不能续算'
    if conflicts:
        return True, f'交接第 {conflicts[0]} 分钟两支探头达温判断矛盾，只取共同达温'
    return True, f'{shared[0]}–{shared[-1]} 两支探头读数见证交接，续算'


def zone_runs(zone, probes):
    """Continuous at-temperature stretches of one zone, main and backup combined.

    Within the window both probes sampled, the zone counts as soaking only where
    both agree it was at temperature, so a dip seen by either probe breaks
    continuity. Each probe is believed alone where it sampled without the other.
    When the probes share no sampling instant the change-over is unwitnessed and
    the overlapping window is dropped rather than bridged, so a drop at the probe
    change never becomes continuous soaking.
    """
    if len(probes) == 1:
        name, reading = next(iter(probes.items()))
        spans, gaps = segments(reading['readings'], reading['target'], reading['limit'])
        return merge(spans), gaps, [f'{name}探头单测']
    ordered = sorted(probes.items(), key=lambda item: (min(item[1]['readings']), item[0] != '主'))
    (first_name, first), (second_name, second) = ordered
    first_hot, first_gaps = segments(first['readings'], first['target'], first['limit'])
    second_hot, second_gaps = segments(second['readings'], second['target'], second['limit'])
    gaps = [*first_gaps, *second_gaps]
    change = f'{first_name}→{second_name}'
    witnessed, note = handover(first, second)
    first_domain = activity(first['readings'], first['limit'])
    second_domain = activity(second['readings'], second['limit'])
    overlap = intersect(first_domain, second_domain)
    only_first = subtract(first_domain, overlap)
    only_second = subtract(second_domain, overlap)
    if witnessed:
        consensus = intersect(first_hot, second_hot)
        combined = merge([*intersect(first_hot, only_first), *intersect(second_hot, only_second),
                          *intersect(consensus, overlap)])
    else:
        # Nothing in the overlap is attested by both probes, so it cannot join
        # the two probes' stretches; leave those stretches separate.
        combined = merge([*intersect(first_hot, only_first), *intersect(second_hot, only_second)])
    return combined, gaps, [f'{change} {note}']


def common(runs_by_zone):
    """Intervals continuously at temperature in every zone at once.

    Intersection is associative, so fold one zone at a time instead of taking
    the Cartesian product of every zone's runs.
    """
    if not runs_by_zone:
        return []
    shared = runs_by_zone[0]
    for runs in runs_by_zone[1:]:
        shared = merge(intersect(shared, runs))
        if not shared:
            return []
    return shared


def evaluate(row):
    """Evaluate a single profile; retained for legacy callers and samples."""
    reading = profile(row)
    spans, gaps = segments(reading['readings'], reading['target'], reading['limit'])
    reached = longest(spans)
    evidence = [(f'{start:.3f}–{end:.3f} 达温', f'{end-start:.3f}', '分钟') for start, end in spans]
    evidence.extend(gaps)
    evidence.append(('判批', '达标' if reached >= reading['required'] else '保温不足', ''))
    return reached.quantize(D('0.001')), evidence


def evaluate_ticket(records):
    """Judge one firing ticket from its per-zone main/backup profiles.

    ``records`` holds the ticket's accepted rows, each with ``zone``, ``probe``
    and ``fields``. The ticket length is the longest interval in which every
    zone is continuously at temperature, so one zone cooling down shortens the
    whole ticket. A single-profile ticket behaves exactly as before.
    """
    zones, required = {}, D(0)
    for record in records:
        reading = profile(record['fields'])
        zones.setdefault(record['zone'], {})[record['probe']] = reading
        required = max(required, reading['required'])
    runs_by_zone, info, evidence = [], [], []
    for zone in sorted(zones):
        runs, gaps, notes = zone_runs(zone, zones[zone])
        runs_by_zone.append(runs)
        info.append({'zone': zone, 'probes': sorted(zones[zone]), 'longest': f'{longest(runs):.3f}',
                     'spans': [[f'{start:.3f}', f'{end:.3f}'] for start, end in runs], 'notes': notes})
        label = f'{zone} ' if len(zones) > 1 else ''
        evidence.extend((f'{label}{start:.3f}–{end:.3f} 达温', f'{end-start:.3f}', '分钟')
                        for start, end in runs)
        evidence.extend(gaps)
        evidence.extend((note, '', '') for note in notes)
    shared = common(runs_by_zone)
    reached = longest(shared)
    if len(zones) > 1:
        evidence.extend((f'各区共同达温 {start:.3f}–{end:.3f}', f'{end-start:.3f}', '分钟')
                        for start, end in shared)
    short = reached < required
    evidence.append(('判批', '保温不足' if short else '达标', ''))
    multi = len(zones) > 1 or any(len(probes) > 1 for probes in zones.values())
    handovers = [name for run in info for name in run['notes'] if '→' in name]
    return reached.quantize(D('0.001')), evidence, info, required, short, multi, shared, handovers