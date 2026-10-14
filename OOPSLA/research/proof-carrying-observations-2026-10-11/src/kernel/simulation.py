"""Independent exact source relation checker for idle_error in Simulation.

The theorem assumes the specified native interfaces: adding DEPOLARIZE1
changes only noise payload, not targets, measurements, route state or RNG.
No Flow tags, guessed relation E, or candidate load list is trusted.
"""
import ast
import hashlib


FORBIDDEN = {"eval", "exec", "globals", "locals", "getattr", "setattr", "compile", "__import__"}
CALLS = frozenset(['GF','SGSOP','all_checks','all_checks().without_noise','all_qbts.items','all_qbts.values','c.append',
    'col_G.copy','commute','cyclic_shift_matrix','embed_code','enumerate','galois.GF','generators.append','get_logicals',
    'get_nbr','gfH.row_reduce','int','logicals.append','make_circle','manhattan','matrix_power','matrix_rank',
    'measure_x_checks','measure_z_checks','min','np.abs','np.any','np.append','np.arange','np.array','np.concatenate',
    'np.delete','np.empty','np.eye','np.hstack','np.hstack([A, B]).astype','np.hstack([B.T, A.T]).astype','np.kron',
    'np.linalg.matrix_rank','np.ones','np.random.random','np.roll','np.std','np.vstack','np.where','np.zeros',
    'os.path.realpath','os.path.split','par2gen','print','range','rref_H.copy','self.c.append','self.detectors',
    'self.lr_round','self.observables','self.sr_round','stim.Circuit','stim.target_rec','sum','swaps.append','x_rs.append','z_rs.append'])


def check_source(source, proof, parameter="idle_error"):
    if proof.get("rule") != "noise-payload-erasure-v1" or proof.get("parameter") != parameter:
        return {"accepted":False,"reason":"wrong proof rule or parameter"}
    if proof.get("source_sha256") != hashlib.sha256(source.encode("utf-8")).hexdigest():
        return {"accepted":False,"reason":"source version mismatch"}
    tree=ast.parse(source)
    # Kernel rescans complete definition source and independently binds parents.
    parents={c:n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}
    loads=[]
    stores=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Call) and ast.unparse(node.func) not in CALLS:
            return {'accepted':False,'reason':'unknown external/callback binding','call':ast.unparse(node.func)}
        if isinstance(node,ast.FunctionDef) and node.name==parameter:
            return {'accepted':False,'reason':'parameter/function shadowing'}
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in FORBIDDEN:
            return {"accepted":False,"reason":"dynamic binding operation"}
        if isinstance(node, (ast.Global,ast.Nonlocal)) and parameter in node.names:
            return {"accepted":False,"reason":"parameter rebinding"}
        if isinstance(node,ast.arg) and node.arg==parameter:
            return {"accepted":False,"reason":"parameter shadowing"}
        if isinstance(node,ast.Name) and node.id==parameter:
            if isinstance(node.ctx,ast.Store):
                # Only initial module-level numeric literal assignment allowed.
                parent=parents[node]
                if not (isinstance(parent,ast.Assign) and parents.get(parent) is tree and
                        isinstance(parent.value,ast.Constant) and isinstance(parent.value.value,(int,float))):
                    return {"accepted":False,"reason":"parameter aliased or mutated"}
                stores.append(node.lineno)
            elif isinstance(node.ctx,ast.Load):
                cursor=node
                while cursor in parents and not isinstance(cursor,ast.Call):
                    cursor=parents[cursor]
                call=cursor
                if not (isinstance(call,ast.Call) and isinstance(call.func,ast.Attribute) and call.func.attr=='append'
                        and ast.unparse(call.func.value)=='self.c' and len(call.args)==3 and not call.keywords
                        and isinstance(call.args[0],ast.Constant) and call.args[0].value=='DEPOLARIZE1'
                        and node in set(ast.walk(call.args[2]))):
                    return {"accepted":False,"reason":"parameter affects control, target, state or unknown call", "line":node.lineno}
                # noise payload may use fixed scalar arithmetic only
                if any(isinstance(x,(ast.Call,ast.IfExp,ast.Compare,ast.Attribute)) for x in ast.walk(call.args[2])):
                    return {"accepted":False,"reason":"non-arithmetic noise expression"}
                ancestor=call
                while ancestor in parents and not isinstance(ancestor,ast.FunctionDef):
                    ancestor=parents[ancestor]
                if not isinstance(ancestor,ast.FunctionDef) or ancestor.name!='simulate':
                    return {"accepted":False,"reason":"unsupported enclosing transition"}
                enclosing=parents.get(ancestor)
                if not isinstance(enclosing,ast.ClassDef) or enclosing.name!='Simulation':
                    return {'accepted':False,'reason':'unsupported lexical scope'}
                loads.append({"line":node.lineno,"call_line":call.lineno,"kind":"DEPOLARIZE1", "payload":ast.unparse(call.args[2])})
    if len(stores)!=1 or len(loads)!=2:
        return {"accepted":False,"reason":"unexpected parameter definition/use count"}
    # Erase the proved parameter-dependent calls' numerical arguments only.
    class Erase(ast.NodeTransformer):
        def visit_Call(self,node):
            if node.lineno in {r['call_line'] for r in loads}:
                node.args[2]=ast.Constant(0)
            return self.generic_visit(node)
    normalized=ast.dump(Erase().visit(tree),include_attributes=False)
    return {"accepted":True,"parameter":parameter,"checked_loads":sorted(loads,key=lambda r:r['line']),
            "structural_transition_sha256":hashlib.sha256(normalized.encode()).hexdigest(),
            "relation":"identical ordered non-noise state transitions and RNG calls; circuit differs only in DEPOLARIZE1 payload",
            "premises":["fixed module definitions and external bindings", "numeric finite idle parameter", "same initial global data and RNG state", "no concurrent global or alias mutation", "DEPOLARIZE1 append has no measurement/RNG side effect", "successful executions; payload probabilities within native allowed domain"],
            "input_enumerations":0,"provided_load_list_trusted":False}
