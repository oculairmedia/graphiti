#!/usr/bin/env python3
from pathlib import Path

path = Path('/opt/stacks/graphiti/graphiti_core/driver/falkordb_driver.py')
text = path.read_text()

# insert helper after _wrap_vector_params_in_query definition
marker = '    return query\n\n\nclass FalkorDriverSession(GraphDriverSession):'
helper = '    return query\n\n\n'
helper += 'def _summarize_value(val: Any, depth: int = 0):\n'
helper += '    if depth > 2:\n'
helper += "        return '...'\n"
helper += '    if _is_vector_list(val):\n'
helper += "        sample = ', '.join(f'{x:.4f}' for x in val[:5])\n"
helper += "        return f'<vector len={len(val)} sample=[{sample}]>'\n"
helper += '    if isinstance(val, list):\n'
helper += '        result = [_summarize_value(item, depth + 1) for item in val[:5]]\n'
helper += '        if len(val) > 5:\n'
helper += "            result.append('...')\n"
helper += '        return result\n'
helper += '    if isinstance(val, dict):\n'
helper += '        result = {}\n'
helper += '        for idx, (k, v) in enumerate(val.items()):\n'
helper += '            if idx >= 5:\n'
helper += "                result['...'] = '...'\n"
helper += '                break\n'
helper += '            result[k] = _summarize_value(v, depth + 1)\n'
helper += '        return result\n'
helper += '    return val\n\n\n'
helper += 'def _summarize_params(params: dict[str, Any]) -> dict[str, Any]:\n'
helper += '    return {k: _summarize_value(v) for k, v in params.items()}\n\n\n'

if marker not in text:
    raise SystemExit('marker not found when inserting helpers')
text = text.replace(marker, helper + 'class FalkorDriverSession(GraphDriverSession):')

# update run method logging
old_run = '    async def run(self, query: str | list, **kwargs: Any) -> Any:\n        # FalkorDB does not support argument for Label Set, so it\'s converted into an array of queries\n        if isinstance(query, list):\n            for cypher, params in query:\n                params = convert_datetimes_to_strings(params)\n                wrapped_cypher = _wrap_vector_params_in_query(str(cypher), params)\n                if logger.isEnabledFor(logging.DEBUG):\n                    logger.debug("Falkor RUN(list) query:\\\n%s\\\\nparams=%s", wrapped_cypher, params)\n                try:\n                    await self.graph.query(wrapped_cypher, params)  # type: ignore[reportUnknownArgumentType]\n                except Exception:\n                    logger.error(\n                        "Falkor RUN(list) query failed:\\\n%s\\\\nparams=%s",\n                        wrapped_cypher,\n                        params,\n                        exc_info=True,\n                    )\n                    raise\n        else:\n            params = _flatten_params(dict(kwargs))\n            params = convert_datetimes_to_strings(params)\n            wrapped_query = _wrap_vector_params_in_query(str(query), params)\n            if logger.isEnabledFor(logging.DEBUG):\n                logger.debug("Falkor RUN query:\\\n%s\\\\nparams=%s", wrapped_query, params)\n            try:\n                await self.graph.query(wrapped_query, params)  # type: ignore[reportUnknownArgumentType]\n            except Exception:\n                logger.error(\n                    "Falkor RUN query failed:\\\n%s\\\\nparams=%s",\n                    wrapped_query,\n                    params,\n                    exc_info=True,\n                )\n                raise\n        # Assuming `graph.query` is async (ideal); otherwise, wrap in executor\n        return None\n\n'

new_run = '    async def run(self, query: str | list, **kwargs: Any) -> Any:\n        # FalkorDB does not support argument for Label Set, so it\'s converted into an array of queries\n        if isinstance(query, list):\n            for cypher, params in query:\n                params = convert_datetimes_to_strings(params)\n                wrapped_cypher = _wrap_vector_params_in_query(str(cypher), params)\n                summary = _summarize_params(params)\n                logger.info("Falkor RUN(list) query:\\\n%s\\\\nparams=%s", wrapped_cypher[:2000], summary)\n                try:\n                    await self.graph.query(wrapped_cypher, params)  # type: ignore[reportUnknownArgumentType]\n                except Exception:\n                    logger.error(\n                        "Falkor RUN(list) query failed:\\\n%s\\\\nparams=%s",\n                        wrapped_cypher[:2000],\n                        summary,\n                        exc_info=True,\n                    )\n                    raise\n        else:\n            params = _flatten_params(dict(kwargs))\n            params = convert_datetimes_to_strings(params)\n            wrapped_query = _wrap_vector_params_in_query(str(query), params)\n            summary = _summarize_params(params)\n            logger.info("Falkor RUN query:\\\n%s\\\\nparams=%s", wrapped_query[:2000], summary)\n            try:\n                await self.graph.query(wrapped_query, params)  # type: ignore[reportUnknownArgumentType]\n            except Exception:\n                logger.error(\n                    "Falkor RUN query failed:\\\n%s\\\\nparams=%s",\n                    wrapped_query[:2000],\n                    summary,\n                    exc_info=True,\n                )\n                raise\n        # Assuming `graph.query` is async (ideal); otherwise, wrap in executor\n        return None\n\n'

if old_run not in text:
    raise SystemExit('old run method not found')
text = text.replace(old_run, new_run)

# update execute_query logging
old_exec = "        if logger.isEnabledFor(logging.DEBUG):\n            logger.debug(\"Falkor EXECUTE query on graph '%s':\\\\n%s\\\\nparams=%s\", graph_name, cypher_query_, params)\n        try:\n            result = await graph.query(cypher_query_, params)  # type: ignore[reportUnknownArgumentType]\n        except Exception as e:\n            logger.error(\n                \"Falkor EXECUTE query failed on graph '%s':\\\\n%s\\\\nparams=%s\",\n                graph_name,\n                cypher_query_,\n                params,\n                exc_info=True,\n            )\n            if 'already indexed' in str(e):\n                logger.info(f'Index already exists: {e}')\n                return None\n            raise\n\n        # Convert the result header to a list of strings\n        header = [h[1] for h in result.header]\n"

new_exec = "        summary = _summarize_params(params)\n        logger.info(\"Falkor EXECUTE query on graph '%s':\\\\n%s\\\\nparams=%s\", graph_name, cypher_query_[:2000], summary)\n        try:\n            result = await graph.query(cypher_query_, params)  # type: ignore[reportUnknownArgumentType]\n        except Exception as e:\n            logger.error(\n                \"Falkor EXECUTE query failed on graph '%s':\\\\n%s\\\\nparams=%s\",\n                graph_name,\n                cypher_query_[:2000],\n                summary,\n                exc_info=True,\n            )\n            if 'already indexed' in str(e):\n                logger.info(f'Index already exists: {e}')\n                return None\n            raise\n\n        # Convert the result header to a list of strings\n        header = [h[1] for h in result.header]\n"

if old_exec not in text:
    raise SystemExit('old execute_query block not found')
text = text.replace(old_exec, new_exec)

path.write_text(text)
print('Driver logging updated with summaries')
