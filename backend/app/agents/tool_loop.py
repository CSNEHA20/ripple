import json
import logging
from typing import Any, Callable, Type, TypeVar
from pydantic import BaseModel
from app.tenancy import TenantGraph
from app.trace import Trace, ToolResult
from app.tools.registry import TOOL_SCHEMAS, execute_tool
from app.agents.llm import LLMWrapper, get_llm_provider

logger = logging.getLogger("ripple.agents.tool_loop")

T = TypeVar("T", bound=BaseModel)

MAX_TOOL_CALL_STEPS = 6


class ToolLoop:
    """Agent Tool-Calling Loop:
    Coordinates multi-turn LLM reasoning and graph tool execution.
    - Uses tool allow-lists per agent role.
    - Executes tools via execute_tool against the live FalkorDB tenant graph.
    - Emits TraceSteps so the Cypher inspector captures all queries.
    - Enforces citation guardrails and structured schema compliance.
    """

    def __init__(self, mode: str = "replay"):
        self.mode = mode
        self.llm_wrapper = LLMWrapper(mode=mode)
        self.provider = get_llm_provider() if mode == "live" else None

    def run(
        self,
        agent_role: str,
        system_prompt: str,
        user_prompt: str,
        graph: TenantGraph,
        allow_list: list[str],
        schema: Type[T],
        context_data: dict[str, Any] | None = None,
        fallback_generator: Callable[..., dict[str, Any]] | None = None,
        as_of: float | None = None,
        valid_node_ids: list[str] | None = None,
        pre_executed_tools: dict[str, ToolResult] | None = None,
    ) -> dict[str, Any]:
        """Execute the tool calling loop.
        Returns: {
            "final": validated_pydantic_model,
            "tool_calls": list_of_executed_calls,
            "trace": trace_object,
        }
        """
        trace = Trace()
        executed_calls: list[dict[str, Any]] = []

        # Gather tool schemas for allow-listed tools
        allowed_schemas = [s for s in TOOL_SCHEMAS if s.get("name") in allow_list]
        allowed_names = {s["name"] for s in allowed_schemas}

        # 1. If in live mode with a capable provider, attempt interactive tool-calling
        if self.mode == "live" and self.provider:
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            for step_idx in range(MAX_TOOL_CALL_STEPS):
                try:
                    step_response = self.provider.complete_with_tools(messages, allowed_schemas)
                    if not step_response:
                        break

                    tool_calls = step_response.get("tool_calls", [])
                    content = step_response.get("content", "")

                    if not tool_calls:
                        # Agent decided not to call further tools, finished
                        break

                    # Record assistant message with tool calls
                    messages.append({
                        "role": "assistant",
                        "content": content,
                        "tool_calls": [
                            {
                                "id": tc["id"],
                                "type": "function",
                                "function": {
                                    "name": tc["name"],
                                    "arguments": json.dumps(tc.get("arguments", {})),
                                },
                            }
                            for tc in tool_calls
                        ],
                    })

                    # Execute each tool in the allow-list
                    for tc in tool_calls:
                        name = tc["name"]
                        args = tc.get("arguments", {})
                        if name not in allowed_names:
                            logger.warning(f"Agent '{agent_role}' attempted disallowed tool '{name}'. Skipping.")
                            continue

                        # Inject as_of timestamp if applicable
                        if as_of is not None and "as_of" not in args:
                            args["as_of"] = as_of

                        try:
                            result: ToolResult = execute_tool(name=name, graph=graph, arguments=args)
                            if hasattr(result, "trace"):
                                trace.merge(result.trace)

                            tool_data = result.data if hasattr(result, "data") else result
                            executed_calls.append({
                                "tool": name,
                                "arguments": args,
                                "result": tool_data,
                            })

                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc.get("id", name),
                                "name": name,
                                "content": json.dumps(tool_data)[:1500],
                            })
                        except Exception as tool_err:
                            logger.error(f"Error executing tool '{name}': {tool_err}")
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc.get("id", name),
                                "name": name,
                                "content": json.dumps({"error": str(tool_err)}),
                            })
                except Exception as loop_err:
                    logger.warning(f"Tool loop error on step {step_idx}: {loop_err}")
                    break

        # 2. If pre_executed_tools were supplied or fallback needed, record their traces
        if pre_executed_tools:
            for tool_name, t_res in pre_executed_tools.items():
                if hasattr(t_res, "trace"):
                    trace.merge(t_res.trace)
                data = t_res.data if hasattr(t_res, "data") else t_res
                executed_calls.append({
                    "tool": tool_name,
                    "arguments": {},
                    "result": data,
                })

        # 3. Final structured synthesis with citation verification & 1-retry policy
        structured_out = self.llm_wrapper.call_structured(
            prompt=user_prompt,
            system_prompt=system_prompt,
            schema=schema,
            valid_node_ids=valid_node_ids,
            context_data=context_data,
            fallback_generator=fallback_generator,
        )

        return {
            "final": structured_out,
            "tool_calls": executed_calls,
            "trace": trace,
        }
