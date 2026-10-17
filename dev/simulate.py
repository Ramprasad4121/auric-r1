"""Dev only: replay a pool of saved i.i.d. replies through the live
aggregation/stopping code. Each 'run' r uses a rotation of the pool so runs
see different draws. Reports mean macro score and mean calls per item."""
import json,sys,io,contextlib,statistics as st
sys.path.insert(0,'src'); sys.path.insert(0,'data')
from auric.pipeline import Config,prepare,aggregate,should_stop
from auric.decide import strip
from auric import extract as ex
import score as S
items=json.load(open('data/items.json')); key=json.load(open('data/visible_key.json'))
pool=json.load(open(sys.argv[1]))
def run(cfg,rot):
    out={};calls=[]
    for it in items:
        ctx=prepare(it,cfg); reps=pool[it['id']]; reps=reps[rot:]+reps[:rot]
        samples=[]
        for i in range(cfg.calls):
            samples.append(ex.parse_reply(ctx.h,reps[i%len(reps)],len(ctx.lines)))
            if i+1<cfg.calls and should_stop(ctx,samples,cfg): break
        calls.append(len(samples)); out[it['id']]=strip(aggregate(ctx,samples,cfg))
    with contextlib.redirect_stdout(io.StringIO()): r=S.score(key,out,items)
    return r['macro_exact_match'],r['per_case_rate'],st.mean(calls)
def sweep(name,**kw):
    for b,c in [('1x',1),('3x',3),('10x',10)]:
        res=[run(Config(calls=c,**kw),rot) for rot in range(0,10, 1 if c==1 else (3 if c==3 else 5))][:10]
        m=[x[0] for x in res]
        pc={k:round(st.mean(x[1][k] for x in res),3) for k in res[0][1]}
        print(f"{name:28s} {b:4s} macro={st.mean(m):.3f} sd={st.pstdev(m):.3f} n={len(m)} calls={st.mean(x[2] for x in res):.2f} {pc}",flush=True)
if __name__=='__main__':
    sweep('full')
    for comp in ['vote','prior_pick','adaptive']:
        sweep('no_'+comp,**{comp:False})
