import ast
from pathlib import Path


def test_graph_ping_route_contract_in_main() -> None:
    main_py = Path(__file__).resolve().parents[1] / 'graph_service' / 'main.py'
    tree = ast.parse(main_py.read_text(encoding='utf-8'))

    ping_fn = None
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == 'graph_ping':
            ping_fn = node
            break

    assert ping_fn is not None, 'graph_ping endpoint handler is missing'

    routes = [
        dec.args[0].value
        for dec in ping_fn.decorator_list
        if isinstance(dec, ast.Call)
        and isinstance(dec.func, ast.Attribute)
        and isinstance(dec.func.value, ast.Name)
        and dec.func.value.id == 'app'
        and dec.func.attr == 'get'
        and dec.args
        and isinstance(dec.args[0], ast.Constant)
        and isinstance(dec.args[0].value, str)
    ]
    assert '/api/graph/ping' in routes

    return_nodes = [node for node in ast.walk(ping_fn) if isinstance(node, ast.Return)]
    assert return_nodes, 'graph_ping must return a JSON response'

    json_payload = None
    for ret in return_nodes:
        value = ret.value
        if not isinstance(value, ast.Call):
            continue
        if not isinstance(value.func, ast.Name) or value.func.id != 'JSONResponse':
            continue
        for kw in value.keywords:
            if kw.arg != 'content' or not isinstance(kw.value, ast.Dict):
                continue
            json_payload = {
                key.value: val.value
                for key, val in zip(kw.value.keys, kw.value.values, strict=True)
                if isinstance(key, ast.Constant)
                and isinstance(key.value, str)
                and isinstance(val, ast.Constant)
            }

    assert json_payload == {'ok': True, 'service': 'graph'}
