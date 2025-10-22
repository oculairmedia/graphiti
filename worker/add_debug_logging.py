#!/usr/bin/env python3
from pathlib import Path

path = Path('/opt/stacks/graphiti/graphiti_core/driver/falkordb_driver.py')
text = path.read_text()
old = '        if isinstance(query, list):\n            for cypher, params in query:\n                params = convert_datetimes_to_strings(params)\n                cypher = _wrap_vector_params_in_query(str(cypher), params)\n                await self.graph.query(cypher, params)  # type: ignore[reportUnknownArgumentType]\n        else:\n            params = _flatten_params(dict(kwargs))\n            params = convert_datetimes_to_strings(params)\n            query = _wrap_vector_params_in_query(str(query), params)\n\n            await self.graph.query(query, params)  # type: ignore[reportUnknownArgumentType]\n'
if old not in text:
    print('pattern not found, printing snippet around run method for manual edit')
    idx = text.find('async def run')
    print(text[idx : idx + 400])
    raise SystemExit
new = '        if isinstance(query, list):\n            for cypher, params in query:\n                params = convert_datetimes_to_strings(params)\n                wrapped_cypher = _wrap_vector_params_in_query(str(cypher), params)\n                if logger.isEnabledFor(logging.DEBUG):\n                    logger.debug("Falkor RUN(list) query:\\n%s\\nparams=%s", wrapped_cypher, params)\n                try:\n                    await self.graph.query(wrapped_cypher, params)  # type: ignore[reportUnknownArgumentType]\n                except Exception:\n                    logger.error(\n                        "Falkor RUN(list) query failed:\\n%s\\nparams=%s",\n                        wrapped_cypher,\n                        params,\n                        exc_info=True,\n                    )\n                    raise\n        else:\n            params = _flatten_params(dict(kwargs))\n            params = convert_datetimes_to_strings(params)\n            wrapped_query = _wrap_vector_params_in_query(str(query), params)\n            if logger.isEnabledFor(logging.DEBUG):\n                logger.debug("Falkor RUN query:\\n%s\\nparams=%s", wrapped_query, params)\n            try:\n                return await self.graph.query(wrapped_query, params)  # type: ignore[reportUnknownArgumentType]\n            except Exception:\n                logger.error(\n                    "Falkor RUN query failed:\\n%s\\nparams=%s",\n                    wrapped_query,\n                    params,\n                    exc_info=True,\n                )\n                raise\n'
path.write_text(text.replace(old, new))
print('Updated driver with debug logging')
