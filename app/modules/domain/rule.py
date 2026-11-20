from decimal import Decimal as D
from app.errors import DataError
from .values import number, parts


def evaluate(row):
    scale = row['温标'].upper()
    if scale not in {'C', 'F'}:
        raise DataError('TEMP_SCALE', '温标须为 C 或 F')
    target = number(row['阈值摄氏度'], 0, 1800)
    limit = number(row['最大采样间隔分钟'], D('0.001'), 1440)
    required = number(row['要求保温分钟'], D('0.001'), 1440)
    readings = {}
    for reading in parts(row['测温点']):
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
    segments, gaps = [], []
    for (left, a), (right, b) in zip(sorted(readings.items()), sorted(readings.items())[1:]):
        if right-left > limit:
            gaps.append((f'{left}–{right} 缺测', right-left, '分钟'))
            continue
        if max(a, b) < target or max(a, b) == target > min(a, b):
            continue
        start, end = left, right
        if min(a, b) < target:
            crossing = left + (target-a)*(right-left)/(b-a)
            start, end = (crossing, right) if a < b else (left, crossing)
        if segments and segments[-1][1] == start:
            segments[-1] = (segments[-1][0], end)
        else:
            segments.append((start, end))
    longest = max((end-start for start, end in segments), default=D(0))
    evidence = [(f'{start:.3f}–{end:.3f} 达温', f'{end-start:.3f}', '分钟') for start,end in segments]
    evidence.extend(gaps)
    evidence.append(('判批', '达标' if longest >= required else '保温不足', ''))
    return longest.quantize(D('0.001')), evidence
