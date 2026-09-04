# 检查脚本：对比新旧 parse_formula 在 142 只基金公式上的 unknown 主成分（git diff 回归验证）
import subprocess
import sys
import json
import tempfile
import os
import logging
from pathlib import Path

sys.path.insert(0, 'backend/fund-select')
logging.disable(logging.WARNING)


def load_module(src: str, yaml_path: str):
    ns = {'__name__': 'm'}
    exec(compile(src, 'mod', 'exec'), ns)
    ns['_BENCHMARKS_YAML'] = Path(yaml_path)
    ns['_cfg_cache'] = None
    return ns


new_src = open('backend/fund-select/src/data/benchmark_fetcher.py', encoding='utf-8').read()
old_src = subprocess.run(
    ['git', 'show', 'HEAD:backend/fund-select/src/data/benchmark_fetcher.py'],
    capture_output=True, encoding='utf-8').stdout
old_yaml_src = subprocess.run(
    ['git', 'show', 'HEAD:backend/fund-select/config/benchmarks.yaml'],
    capture_output=True, encoding='utf-8').stdout
tmp = tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False, encoding='utf-8')
tmp.write(old_yaml_src)
tmp.close()

formulas = json.load(open('tmp/benchmark_formulas.json', encoding='utf-8'))


def scan(parse):
    out = {}
    for code, f in formulas.items():
        unk = [(c.name, round(c.weight, 2)) for c in parse(f) if c.kind == 'unknown']
        if max((w for _, w in unk), default=0) >= 0.5:
            out[code] = dict(unk)
    return out


m_old_old = load_module(old_src, tmp.name)
m_old_new = load_module(old_src, 'backend/fund-select/config/benchmarks.yaml')
m_new_new = load_module(new_src, 'backend/fund-select/config/benchmarks.yaml')

a = scan(m_old_old['parse_formula'])
b = scan(m_old_new['parse_formula'])
c = scan(m_new_new['parse_formula'])
print('old_code+old_yaml unknown主成分基金数:', len(a))
print('old_code+new_yaml unknown主成分基金数:', len(b))
print('new_code+new_yaml unknown主成分基金数:', len(c))
regress = {k: (b.get(k), c[k]) for k in c if k not in b}
print('新规则新增的 unknown 主成分(回归):', regress if regress else '无')
print('新规则消掉的:', sorted(set(b) - set(c)))
for probe in ('486002',):
    f = formulas.get(probe)
    print(f'--- {probe}: {f!r}')
    print('  old:', [(x.name, x.weight, x.kind) for x in m_old_new['parse_formula'](f)])
    print('  new:', [(x.name, x.weight, x.kind) for x in m_new_new['parse_formula'](f)])
os.unlink(tmp.name)
