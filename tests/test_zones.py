import csv
from decimal import Decimal
from io import StringIO
from pathlib import Path
import pytest
from app.errors import DataError
from app.modules.domain.rule import evaluate_ticket, profile, zone_runs
from app.modules.contract.service import normalize
from app.modules.intake.service import intake
from app.modules.quality.service import inspect
from app.pipeline import execute, stages
from app.settings import KEY

ROOT = Path(__file__).resolve().parents[1]


def row(zone, probe, points, target='1000', limit='10', required='20', scale='C'):
    return {'zone': zone, 'probe': probe,
            'fields': {'温标': scale, '测温点': points, '阈值摄氏度': target,
                       '最大采样间隔分钟': limit, '要求保温分钟': required}}


def judge(rows):
    return evaluate_ticket(rows)


def test_single_zone_reads_as_before():
    amount, _, info, required, short, multi, shared, handovers = judge([
        row('A区', '主', '0:900;10:1100;20:1100', required='15')])
    assert amount == Decimal('15.000') and not short
    assert info[0]['probes'] == ['主'] and multi is False and handovers == []


def test_handover_with_witness_continues_soak():
    amount, _, info, _, short, multi, shared, handovers = judge([
        row('A区', '主', '0:900;10:1100;20:1100;30:1100', required='40'),
        row('A区', '备', '30:1100;40:1100;50:1100', required='40')])
    assert amount == Decimal('45.000') and not short
    assert multi is True and handovers and '续算' in handovers[0]
    assert shared == [(Decimal(5), Decimal(50))]


def test_gap_between_probes_is_not_spliced():
    # The backup starts only after the primary stopped: no second witness.
    amount, _, info, _, short, _, _, handovers = judge([
        row('A区', '主', '0:900;10:1100;20:1100;30:1100', required='40'),
        row('A区', '备', '40:1100;50:1100;60:1100', required='40')])
    assert amount == Decimal('25.000') and short
    assert '不能续算' in handovers[0]
    assert [span for span in info[0]['spans']] == [['5.000', '30.000'], ['40.000', '60.000']]


def test_disagreeing_probes_do_not_prove_soak():
    amount, _, _, _, short, _, _, handovers = judge([
        row('A区', '主', '0:900;10:1100;20:1100;30:1100', required='40'),
        row('A区', '备', '30:900;40:1100;50:1100', required='40')])
    assert short and amount == Decimal('25.000')
    assert '矛盾' in handovers[0]


def test_handover_without_shared_instant_cannot_continue():
    amount, _, _, _, _, _, _, handovers = judge([
        row('A区', '主', '0:900;10:1100;15:1100', required='40'),
        row('A区', '备', '20:1100;30:1100;40:1100', required='40')])
    assert '无同刻读数' in handovers[0]


def test_common_soak_is_the_shortest_zone():
    amount, _, info, required, short, _, shared, _ = judge([
        row('A区', '主', '0:900;10:1100;20:1100;30:1100;40:1100', required='20'),
        row('B区', '主', '0:900;10:1100;20:900;30:1100;40:1100', required='20')])
    assert amount == Decimal('15.000') and short
    assert [zone['longest'] for zone in info] == ['35.000', '15.000']
    assert shared == [(Decimal(5), Decimal(15)), (Decimal(25), Decimal(40))]


def test_every_zone_must_hold_for_full_length():
    amount, _, _, _, _, _, _, _ = judge([
        row('A区', '主', '0:900;10:1100;20:1100;30:1100;40:1100', required='20'),
        row('B区', '主', '0:1100;10:1100;20:1100;30:1100;40:1100', required='20')])
    # A区 reaches temperature at minute 5; B区 holds all the way to 40.
    assert amount == Decimal('35.000')


def test_zone_and_probe_columns_are_read():
    payload = (ROOT/'sample_data/zones.csv').read_bytes()
    passed, rejected = normalize(intake(payload))
    assert not rejected
    assert {(item['zone'], item['probe']) for item in passed} >= {('A区','主'),('A区','备')}


def test_legacy_header_defaults_to_single_zone():
    payload = (ROOT/'sample_data/legacy.csv').read_bytes()
    row_, = normalize(intake(payload))[0]
    assert (row_['zone'], row_['probe']) == ('本区', '主')


def test_same_revision_profiles_coexist():
    result = inspect(*normalize(intake((ROOT/'sample_data/zones.csv').read_bytes())))
    assert len([row_ for row_ in result['ready'] if row_['key'] == 'M0002']) == 2
    assert result['rejected'] == []


def test_duplicate_point_still_explained():
    payload = (ROOT/'sample_data/shift.csv').read_bytes()
    result = inspect(*normalize(intake(payload)))
    assert [row_['key'] for row_ in result['suppressed'] if row_['code'] == 'EXACT_DUP'] == ['00101']


def test_bad_probe_rejected():
    payload = (ROOT/'sample_data/zones.csv').read_bytes()
    lines = list(csv.reader(StringIO(payload.decode('utf-8'))))
    assert lines[1][4] == '主'
    bad = [line for line in lines if len(line) > 4 and line[0] == 'M0003' and line[4] == '备']
    assert len(bad) == 1
    bad[0][4] = '第三支'
    out = StringIO(newline='')
    csv.writer(out).writerows(lines)
    _, rejected = normalize(intake(out.getvalue().encode()))
    assert [row_['code'] for row_ in rejected if row_['key'] == 'M0003'] == ['PROBE']


def test_conflicting_zone_profile_quarantined():
    payload = (ROOT/'sample_data/zones.csv').read_bytes()
    lines = list(csv.reader(StringIO(payload.decode('utf-8'))))
    clash = lines[1].copy()
    clash[6] = '0:1200;10:1200;20:1200;30:1200;40:1200'
    lines.append(clash)
    out = StringIO(newline='')
    csv.writer(out).writerows(lines)
    result = inspect(*normalize(intake(out.getvalue().encode())))
    assert 'M0001' not in {row_['key'] for row_ in result['ready']}
    assert {row_['code'] for row_ in result['rejected'] if row_['key'] == 'M0001'} == {'REV_CONFLICT'}


def test_zone_sample_reconciles_and_flags_short():
    source = (ROOT/'sample_data/zones.csv').read_bytes()
    book = (ROOT/'sample_data/zones_external.csv').read_bytes()
    report = execute(source, book)
    assert report['balanced']
    blocked = {item['key']: item['code'] for item in report['blocked']}
    assert blocked == {'M0003':'SOAK_SHORT','M0004':'SOAK_SHORT','M0005':'SOAK_SHORT','M0006':'HOLD_BOOK'}


def test_offbook_handover_blocks_confirmation():
    source = (ROOT/'sample_data/zones.csv').read_bytes()
    book = (ROOT/'sample_data/zones_external.csv').read_bytes()
    report = execute(source, book)
    m0006 = next(item for item in report['blocked'] if item['key'] == 'M0006')
    assert 'AMOUNT_DELTA' in m0006['detail']


def test_legacy_ticket_not_blocked_by_difference():
    source = (ROOT/'sample_data/shift.csv').read_bytes()
    book = (ROOT/'sample_data/external.csv').read_bytes()
    report = execute(source, book)
    assert report['blocked'] == []
    assert report['book']['mismatched'] == 3


def test_short_length_ticket_flagged_in_domain():
    result = stages((ROOT/'sample_data/zones.csv').read_bytes())
    by_key = {row_['key']: row_ for row_ in result['accepted']}
    assert by_key['M0005']['short'] and by_key['M0005']['multi']
    assert by_key['M0006']['handover'] and not by_key['M0006']['short']


def test_zone_sample_confirm_blocked_via_api(client):
    source = (ROOT/'sample_data/zones.csv').read_text(encoding='utf-8')
    book = (ROOT/'sample_data/zones_external.csv').read_text(encoding='utf-8')
    run = client.post('/api/runs', json={'data': source, 'book': book}).json()
    assert run['balanced']
    assert {item['key'] for item in run['blocked']} == {'M0003','M0004','M0005','M0006'}
    response = client.post(f'/api/review/{run["manifest"]["run_id"]}',
                           json={'version': 0, 'decision': '确认', 'note': '已核对'})
    assert (response.status_code, response.json()['code']) == (422, 'HANDOVER')
    returned = client.post(f'/api/review/{run["manifest"]["run_id"]}',
                           json={'version': 0, 'decision': '退回', 'note': '交接未成证，退回复测'})
    assert returned.status_code == 200


def test_legacy_run_confirm_still_works(client):
    run = client.post('/api/runs', json={}).json()
    assert run['blocked'] == []
    response = client.post(f'/api/review/{run["manifest"]["run_id"]}',
                           json={'version': 0, 'decision': '确认', 'note': '已逐条核对'})
    assert response.status_code == 200


def test_replay_does_not_add_batch(client):
    run = client.post('/api/runs', json={}).json()
    again = client.post(f'/api/runs/{run["manifest"]["run_id"]}/replay').json()
    assert again == run
    assert len(client.get('/api/runs').json()) == 1


def test_overlapping_but_unwitnessed_window_is_not_bridged():
    # The main stops at 20; the backup samples 25 and 35, and its sampling
    # window begins after the main's last read, so no minute was read by both.
    amount, _, info, _, short, _, _, handovers = judge([
        row('A区', '主', '0:900;5:1100;10:1100;15:1100;20:1100', required='40'),
        row('A区', '备', '25:1100;35:1100', required='40')])
    assert '无同刻读数' in handovers[0]
    assert amount == Decimal('17.500')  # 5–20 from main; the 20–25 drop is unbridged
    assert short


def test_probe_dip_inside_shared_window_breaks_zone_soak():
    amount, _, info, _, short, _, _, handovers = judge([
        row('A区', '主', '0:1100;10:1100;20:1100;30:1100', required='5'),
        row('A区', '备', '0:1100;10:1100;20:900;30:1100', required='5')])
    # Both probes cover 0–30, but they disagree at minute 20, so the zone's
    # continuity is split there: 0–15 then 25–30, longest 15.
    assert amount == Decimal('15.000')
    assert info[0]['spans'] == [['0.000', '15.000'], ['25.000', '30.000']]
    assert '矛盾' in handovers[0]


def test_short_common_soak_cannot_be_confirmed_even_when_offbook_matches(client):
    source = (ROOT/'sample_data/zones.csv').read_text(encoding='utf-8')
    # Give M0005 exactly the value the rule computes (15) so the ledger matches;
    # it is still short of the 20 minutes the ticket requires.
    book = (ROOT/'sample_data/zones_external.csv').read_text(encoding='utf-8')
    run = client.post('/api/runs', json={'data': source, 'book': book}).json()
    m0005 = next(item for item in run['blocked'] if item['key'] == 'M0005')
    assert m0005['code'] == 'SOAK_SHORT'
    matched = next(item for item in run['book']['rows'] if item['key'] == 'M0005')
    assert matched['code'] == 'MATCH'
    response = client.post(f'/api/review/{run["manifest"]["run_id"]}',
                           json={'version': 0, 'decision': '确认', 'note': '已核对'})
    assert (response.status_code, response.json()['code']) == (422, 'HANDOVER')


def test_blocked_list_exported(client):
    source = (ROOT/'sample_data/zones.csv').read_text(encoding='utf-8')
    book = (ROOT/'sample_data/zones_external.csv').read_text(encoding='utf-8')
    run = client.post('/api/runs', json={'data': source, 'book': book}).json()
    exported = client.get(f'/api/export/{run["manifest"]["run_id"]}').json()
    assert {item['key'] for item in exported['blocked']} == {'M0003','M0004','M0005','M0006'}
