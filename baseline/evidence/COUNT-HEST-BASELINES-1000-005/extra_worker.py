"""CLI bridge to existing frozen general comparators; preserves metadata bytes."""
import argparse,json
from pathlib import Path
from baseline.hest1000 import general_baselines as codec
from baseline.hest1000 import pilot

def main():
    p=argparse.ArgumentParser();p.add_argument('worker');p.add_argument('stage',choices=['encode','decode'])
    p.add_argument('method',choices=codec.METHODS);p.add_argument('source');p.add_argument('output');p.add_argument('--blocked',nargs='*',default=[])
    a=p.parse_args()
    if a.worker!='worker':p.error('expected worker')
    out=Path(a.output)
    if a.stage=='encode':
        out.mkdir(exist_ok=False)
        result=codec.encode(a.source,a.method,out/'archive.bin')
    else:
        pilot.install_guard(a.blocked)
        for root in a.blocked:
            try:open(Path(root)/'guard-probe','rb')
            except PermissionError:pass
            else:raise RuntimeError('decoder guard probe failed')
        result=codec.decode(Path(a.source)/'archive.bin',out)
    print(json.dumps(result,sort_keys=True))

if __name__=='__main__':main()
