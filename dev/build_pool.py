"""Dev only: draw N i.i.d. extraction samples per visible item and save raw
replies, so aggregation strategies can be compared offline on identical draws."""
import json,sys,concurrent.futures as cf
sys.path.insert(0,'src')
from auric.parse import *; from auric import extract as ex
from auric.client import GraniteClient
from auric.pipeline import relevant_mask
N=int(sys.argv[1]); out=sys.argv[2]
items=json.load(open('data/items.json')); c=GraniteClient()
def one(a):
    it,k=a; iid=it['id']; head,lines=split_item(it['text']); h=parse_header(head)
    sub=[l for l,m in zip(lines,relevant_mask(h,lines,True)) if m]
    cid=f"{iid}"; c.set_cap(cid,10**6)
    try: return iid,k,c.chat(cid,ex.build_messages(h,sub))
    except Exception as e: return iid,k,""
pool={}
with cf.ThreadPoolExecutor(16) as e:
    for iid,k,r in e.map(one,[(it,k) for it in items for k in range(N)]):
        pool.setdefault(iid,[]).append(r)
json.dump(pool,open(out,'w'))
print(dict(c.usage))
