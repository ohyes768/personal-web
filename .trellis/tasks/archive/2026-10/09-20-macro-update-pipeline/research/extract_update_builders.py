"""One-shot structural extraction of the existing, contract-tested stages.

Run from repository root, once. The resulting Python is normal source code;
this migration helper is not imported by the service.
"""
import ast
from pathlib import Path


root = Path("backend/macro/src")
routes_path = root / "api/routes.py"
source = routes_path.read_text(encoding="utf-8")
tree = ast.parse(source)
model_import = next(
    node for node in tree.body
    if isinstance(node, ast.ImportFrom) and node.module == "src.models"
)
models = {alias.name for alias in model_import.names}
groups = {
    "fred": {"us_treasuries", "vix", "tga", "ted_spread"},
    "cross_source": {"exchange_rates", "hibor", "fund_flow", "china_bonds"},
    "final": {"eu_bonds", "jp_bonds", "legacy", "commodities", "indices"},
    "a_share": {"dr007", "dr001"},
}
context_names = {
    "settings": "settings", "logger": "logger",
    "_fetch_us_treasuries": "fetch_us_treasuries",
    "_fetch_oecd_bonds": "fetch_oecd_bonds",
    "_fetch_exchange_rates": "fetch_exchange_rates",
    "_compute_incremental_start": "compute_incremental_start",
    "_has_observations": "has_observations",
    "_empty_increment_is_current": "empty_increment_is_current",
    "_empty_increment_fail_message": "empty_increment_fail_message",
    "_build_response_data_with_rates": "build_response_data_with_rates",
    "_EXCHANGE_REBUILD_MSG": "exchange_rebuild_msg",
}
context_names.update({
    name: name for name in (
        "get_data_service", "get_fred_service", "get_vix_service",
        "get_hibor_service", "get_dr007_service", "get_dr001_service",
        "get_fund_flow_service", "get_china_bond_service",
        "get_commodity_service", "get_index_service",
    )
})


class Dependencies(ast.NodeTransformer):
    def visit_Name(self, node):
        if node.id in context_names and isinstance(node.ctx, ast.Load):
            return ast.copy_location(ast.Attribute(
                value=ast.Name(id="context", ctx=ast.Load()),
                attr=context_names[node.id], ctx=ast.Load(),
            ), node)
        if node.id == "_NoNewData":
            node.id = "NoNewData"
        return node


class PreparedNoOp(ast.NodeTransformer):
    # Returns inside stage callbacks are payload/data returns, not no-op responses.
    def visit_FunctionDef(self, node):
        return node

    def visit_AsyncFunctionDef(self, node):
        return node

    def visit_Return(self, node):
        return ast.copy_location(ast.Raise(
            exc=ast.Call(func=ast.Name(id="UpdateNoOp", ctx=ast.Load()),
                         args=[node.value], keywords=[]), cause=None,
        ), node)


builders = {group: [] for group in groups}
entries = {}
replacements = []
for function in tree.body:
    if not isinstance(function, ast.AsyncFunctionDef):
        continue
    decorators = [
        d for d in function.decorator_list if isinstance(d, ast.Call)
        and d.args and isinstance(d.args[0], ast.Constant)
        and isinstance(d.args[0].value, str)
        and (d.args[0].value == "/update" or d.args[0].value.startswith("/update/"))
    ]
    if not decorators:
        continue
    path = decorators[0].args[0].value
    key = path.rsplit("/", 1)[-1].replace("-", "_") if path != "/update" else "legacy"
    outer = next(node for node in function.body if isinstance(node, ast.Try))
    success = next(k.value.value for k in outer.body[-1].value.keywords if k.arg == "message")
    error = next(k.value for k in outer.handlers[0].body[-1].value.keywords if k.arg == "message")
    failure = error.values[0].value.removesuffix(": ")
    entries[key] = (success, failure)
    if key not in {"volume", "turnover", "margin"}:
        group = next(group for group, keys in groups.items() if key in keys)
        position = next(i for i, node in enumerate(outer.body) if (
            isinstance(node, ast.Try) or isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Await)
        ))
        invocation = outer.body[position]
        call = invocation.body[0].value.value if isinstance(invocation, ast.Try) else invocation.value.value
        assert isinstance(call, ast.Call) and len(call.args) == 4
        setup = [PreparedNoOp().visit(node) for node in outer.body[:position]]
        no_data = None
        if isinstance(invocation, ast.Try):
            no_data = ast.FunctionDef(
                name="on_no_data", args=ast.arguments(posonlyargs=[], args=[],
                kwonlyargs=[], kw_defaults=[], defaults=[]),
                body=invocation.handlers[0].body, decorator_list=[],
            )
            setup.append(no_data)
        setup.append(ast.Return(value=ast.Call(
            func=ast.Name(id="UpdatePlan", ctx=ast.Load()),
            args=[ast.Call(func=ast.Name(id="UpdateStages", ctx=ast.Load()), args=call.args, keywords=[])],
            keywords=[ast.keyword(arg="on_no_data", value=ast.Name(id="on_no_data", ctx=ast.Load()))] if no_data else [],
        )))
        builder = ast.FunctionDef(
            name=f"build_{key}", args=ast.arguments(posonlyargs=[],
            args=[ast.arg(arg="context", annotation=ast.Name(id="UpdateContext", ctx=ast.Load()))],
            kwonlyargs=[], kw_defaults=[], defaults=[]),
            body=setup, decorator_list=[], returns=ast.Name(id="UpdatePlan", ctx=ast.Load()),
        )
        builder = ast.fix_missing_locations(Dependencies().visit(builder))
        builders[group].append(builder)
    doc = ast.get_docstring(function)
    wrapper = f'async def {function.name}():\n    """{doc}"""\n    return await UpdatePipeline.execute(UPDATE_SPECS["{key}"], _update_context())'
    replacements.append((function.lineno - 1, function.end_lineno, wrapper))

sources_dir = root / "services/update_sources"
sources_dir.mkdir(exist_ok=True)
(sources_dir / "__init__.py").write_text('"""Source-specific stage builders for registered incremental updates."""\n', encoding="utf-8")
for group, functions in builders.items():
    used_models = sorted({node.id for function in functions for node in ast.walk(function)
                          if isinstance(node, ast.Name) and node.id in models})
    imports = f'''"""{group.replace('_', ' ').title()} update preparation and four-stage adapters."""
from datetime import datetime

import pandas as pd

from src.models import ({', '.join(used_models)})
from src.services.update_pipeline import (
    NoNewData, UpdateContext, UpdateNoOp, UpdatePlan, UpdateStages,
)


'''
    (sources_dir / f"{group}.py").write_text(imports + "\n\n\n".join(ast.unparse(f) for f in functions) + "\n", encoding="utf-8")

# Market adapters already live in the registry. Move them intact and expose the
# same context/plan signature as the other domains, without recursive dispatch.
registry_path = root / "services/update_registry.py"
registry_tree = ast.parse(registry_path.read_text(encoding="utf-8"))
market_factory = next(n for n in registry_tree.body if isinstance(n, ast.FunctionDef) and n.name == "_market_stages")
market_body = '''"""A-share market source adapters (BaoStock and margin balance)."""
import pandas as pd

from src.models import (
    MarginData, MarginUpdateData, TurnoverData, TurnoverUpdateData,
    VolumeData, VolumeUpdateData,
)
from src.services.update_pipeline import UpdateContext, UpdatePlan, UpdateStages


'''
market_body += ast.unparse(market_factory) + "\n\n"
for key, value_key, data_type, payload_type, factory in (
    ("volume", "total_amount_yi", "VolumeData", "VolumeUpdateData", "get_baostock_service"),
    ("turnover", "turnover_rate", "TurnoverData", "TurnoverUpdateData", "get_baostock_service"),
    ("margin", "rzye", "MarginData", "MarginUpdateData", "get_margin_service"),
):
    market_body += f'''\ndef build_{key}(context: UpdateContext) -> UpdatePlan:
    build = _market_stages("{key}", "{value_key}", "{key}", {data_type}, {payload_type})
    return UpdatePlan(build(context.get_data_service(), context.{factory}()))
\n'''
(sources_dir / "market.py").write_text(market_body, encoding="utf-8")

entry_node = next(n for n in registry_tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_ENTRIES" for t in n.targets))
entry_values = []
for row in entry_node.value.elts:
    key, path, payload, test = row.elts
    k = key.value
    entry_values.append(f'    ("{k}", "{path.value}", {payload.id}, "{test.value}", build_{k}, {entries[k][0]!r}, {entries[k][1]!r}),')
registry_imports = '''"""Executable source registry for every incremental update endpoint."""
from collections.abc import Callable
from dataclasses import dataclass

'''
registry_imports += ast.unparse(next(n for n in registry_tree.body if isinstance(n, ast.ImportFrom) and n.module == "src.models")) + "\n"
registry_imports += "from src.services.update_pipeline import UpdateContext, UpdatePlan\n"
for group, keys in groups.items():
    registry_imports += f"from src.services.update_sources.{group} import ({', '.join('build_' + k for k in sorted(keys))})\n"
registry_imports += "from src.services.update_sources.market import build_volume, build_turnover, build_margin\n"
registry_body = '''

@dataclass(frozen=True)
class UpdateSpec:
    key: str
    endpoint: str
    payload_type: type
    contract_test_file: str
    build_stages: Callable[[UpdateContext], UpdatePlan]
    success_message: str
    failure_message: str


_ENTRIES = (
'''
registry_body += "\n".join(entry_values) + '''
)

UPDATE_SPECS = {
    key: UpdateSpec(key, endpoint, payload_type, contract_test_file, builder, success, failure)
    for key, endpoint, payload_type, contract_test_file, builder, success, failure in _ENTRIES
}
'''
registry_path.write_text(registry_imports + registry_body, encoding="utf-8")

lines = source.splitlines()
for start, end, replacement in reversed(replacements):
    lines[start:end] = replacement.splitlines()
updated = "\n".join(lines) + "\n"
updated = updated.replace("from src.services.update_pipeline import UpdatePipeline", "from src.services.update_pipeline import UpdateContext, UpdatePipeline")
context_fields = ["settings", "logger", "is_updating", "acquire_update_lock", "release_update_lock"]
context_fields += [name for name in context_names if name.startswith("get_")]
context_fields += ["get_baostock_service", "get_margin_service"]
context_fields += [name for name in context_names if name.startswith("_")]
context_factory = "def _update_context() -> UpdateContext:\n    return UpdateContext(\n"
for name in context_fields:
    context_factory += f"        {context_names.get(name, name)}={name},\n"
context_factory += "    )\n\n\n"
anchor = '@router.post("/fetch/us-treasuries/history", response_model=UpdateResponse)'
updated = updated.replace(anchor, context_factory + anchor, 1)
routes_path.write_text(updated, encoding="utf-8")
print("Extracted 18 registered builders; all incremental routes now delegate to execute().")
