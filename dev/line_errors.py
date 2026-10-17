"""Dev only: per-phrasing error rates of the extractor over a pool, against the regex oracle."""
import json,sys,re
sys.path.insert(0,'src')
from collections import Counter,defaultdict
from auric.pipeline import Config,prepare
from auric import extract as ex, regex_baseline as rb
items=json.load(open('data/items.json')); pool=json.load(open(sys.argv[1]))
tot=Counter(); err=Counter(); kinds=defaultdict(Counter); n=0; e=0
for it in items:
    ctx=prepare(it,Config()); h=ctx.h
    golds=[ex.canon(rb.extract(h,l,'declined')) for l in ctx.lines]
    for r in pool[it['id']]:
        p=ex.parse_reply(h,r,len(ctx.lines))
        for k,l in enumerate(ctx.lines):
            t=rb.HEDGE.sub('',l)
            for nm in h.people: t=re.sub(rf'\b{nm}\b','P',t)
            t=re.sub(r'\d\d:00','T',t)
            for s in h.stations: t=re.sub(s,'S',t,flags=re.I)
            got=p.get(k,('bad',None)); g='BAD' if got[0]=='bad' else ex.canon(got[1])
            tot[t]+=1; n+=1
            if g!=golds[k]:
                err[t]+=1; e+=1
                gk=golds[k].split('|')[-1] if '|' in golds[k] else golds[k]
                kinds[t]['BAD' if g=='BAD' else ('NONE' if g=='NONE' else 'wrong')]+=1
print('line error rate',e/n)
for t,c in sorted(err.items(),key=lambda x:-x[1]/tot[x[0]])[:40]:
    print(f"{c/tot[t]:.2f} {c:4d}/{tot[t]:4d} {dict(kinds[t])} {t}")
