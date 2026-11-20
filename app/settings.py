import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_ROOT = ROOT / 'sample_data'
DB = Path(os.getenv('WORKBENCH_DB', str(ROOT/'state/ledger.sqlite3')))
TITLE = '窑温判批'
SLUG = 'kiln-soak'
KEY = '烧成单'
FIELDS = ('温标', '测温点', '阈值摄氏度', '最大采样间隔分钟', '要求保温分钟')
ZONE_FIELD = '分区'
PROBE_FIELD = '探头'
DEFAULT_ZONE = '本区'
PROBES = ('主', '备')
ROLE = '陶瓷厂烧成质检员'
UNIT = '分钟'
RULE_VERSION = 'kiln-soak-1.0'
SIGNATURE = '连续保温段'
TABS = {'intake': '温程采信', 'contract': '测点契约', 'quality': '异常窑单', 'domain': '保温判批', 'reconcile': '窑批勾稽', 'runs': '烧成批次', 'review': '签批证据'}
