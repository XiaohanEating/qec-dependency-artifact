"""Relational path certificate for native Simulation routing thresholds."""
import ast
import hashlib
import math
import json
from .simulation import CALLS


def source_sites(source):
    tree=ast.parse(source)
    parents={c:n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}
    sites={}
    for node in ast.walk(tree):
        if isinstance(node,ast.Call) and ast.unparse(node.func) not in CALLS:
            raise ValueError('unknown external/callback binding')
        if not (isinstance(node,ast.Call) and ast.unparse(node.func)=='np.random.random'):
            continue
        parent=parents[node]
        if node.args or node.keywords or not (isinstance(parent,ast.Compare) and len(parent.ops)==1 and isinstance(parent.ops[0],ast.Lt)
                and parent.left is node and len(parent.comparators)==1):
            raise ValueError('unsupported RNG consumer')
        threshold=parent.comparators[0]
        if not (isinstance(threshold,ast.Subscript) and isinstance(threshold.value,ast.Name)
                and threshold.value.id in {'x_check_succ_probs','z_check_succ_probs'} and isinstance(threshold.slice,ast.Name)):
            raise ValueError('unknown threshold expression')
        branch=parents[parent]
        if not (isinstance(branch,ast.IfExp) and isinstance(branch.body,ast.Constant) and branch.body.value==1
                and isinstance(branch.orelse,ast.Constant) and branch.orelse.value==0):
            raise ValueError('RNG comparison must emit boolean routing decision')
        sites[node.lineno]=(threshold.value.id,threshold.slice.id)
    if len(sites)!=6:
        raise ValueError('unexpected native RNG source site count')
    return sites


def check_route_path(source,proof,new_thresholds,expected_trace_sha256=None):
    if hashlib.sha256(source.encode('utf-8')).hexdigest()!=proof.get('source_sha256'):
        return {'accepted':False,'reason':'source binding mismatch'}
    try:
        sites=source_sites(source)
    except ValueError as error:
        return {'accepted':False,'reason':str(error)}
    rows=proof.get('trace',())
    trace_hash=hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if expected_trace_sha256 is None or trace_hash!=expected_trace_sha256:
        return {'accepted':False,'reason':'trusted old trace version mismatch'}
    if not rows:
        return {'accepted':False,'reason':'empty trace'}
    margins=[]
    for row in rows:
        site=row.get('site');name,index=sites.get(site,(None,None))
        if name!=row.get('array') or not isinstance(row.get('index'),int) or row['index']<0:
            return {'accepted':False,'reason':'wrong call site/index binding'}
        if row.get('shape') != []:
            return {'accepted':False,'reason':'RNG draw shape is not certified scalar'}
        r,p=float(row['draw']),float(row['old_threshold'])
        try:
            q=float(new_thresholds[name][row['index']])
        except (KeyError,IndexError,TypeError):
            return {'accepted':False,'reason':'threshold snapshot mismatch'}
        if not all(math.isfinite(x) for x in (r,p,q)) or not (0<=r<1 and 0<=p<=1 and 0<=q<=1):
            return {'accepted':False,'reason':'probability domain'}
        if bool(r<p)!=bool(r<q):
            return {'accepted':False,'reason':'routing decision changes','site':site,'index':row['index'],'draw':r}
        margins.append(abs(r-p))
        if row.get('old_guard') != bool(r<p) or row.get('margin') != abs(r-p):
            return {'accepted':False,'reason':'forged guard or margin'}
    return {'accepted':True,'checked_draws':len(rows),'minimum_recorded_margin':min(margins),
            'input_enumerations':0,'new_producer_runs':0,
            'premises':['complete trusted original execution trace', 'same initial routing/state and RNG state',
                        'fixed native code and external bindings', 'threshold arrays immutable throughout both runs',
                        'all RNG calls occur at certified sites with same transitions', 'same non-threshold parameters and successful execution domain'],
            'relation':'lockstep routing branch results; hence same subsequent RNG call sequence, ordered operations and native state'}
