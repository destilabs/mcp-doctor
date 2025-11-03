from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from mcp_analyzer.dataset_evaluator import evaluate_dataset, load_dataset
from mcp_analyzer.mcp_client import MCPClient

from .accuracy_calculator import calculate_tool_accuracy
from .llm_providers import LLMProvider, create_provider
from .result_formatters import format_evaluation_result, format_generation_result
from .server_config import detect_server_config

logger = logging.getLogger(__name__)
load_dotenv()


@dataclass
class EvaluationResult:
    query: str
    expected_tools: list[str]
    actual_tools: list[str]
    tool_accuracy: float
    execution_success: bool
    response: str
    errors: list[str]


class MCPEvaluator:
    def __init__(
        self,
        server_target: str,
        provider: str = "anthropic",
        model: str | None = None,
        timeout: int = 30,
        **kwargs: Any,
    ) -> None:
        self.server_config = detect_server_config(
            server_target, timeout=timeout, **kwargs
        )
        self.provider_name = provider
        self.model = model

        self._mcp_client: MCPClient | None = None
        self._llm_provider: LLMProvider | None = None

        logger.info("Initialized MCP evaluator for: %s", server_target)

    async def __aenter__(self) -> MCPEvaluator:
        self._mcp_client = MCPClient(
            self.server_config.target,
            timeout=self.server_config.timeout,
            headers=self.server_config.headers,
            env_vars=self.server_config.env_vars,
            working_dir=self.server_config.working_dir,
        )
        await self._mcp_client.__aenter__()

        self._llm_provider = create_provider(self.provider_name, self.model)

        server_info = await self._mcp_client.get_server_info()
        tools = await self._mcp_client.get_tools()
        logger.info("Connected to: %s (%d tools)", server_info.server_name, len(tools))

        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._mcp_client:
            await self._mcp_client.__aexit__(exc_type, exc_val, exc_tb)

    async def evaluate_query(
        self, query: str, expected_tools: list[str] | None = None
    ) -> EvaluationResult:
        if not self._mcp_client or not self._llm_provider:
            raise RuntimeError("Evaluator not initialized. Use async context manager.")

        logger.info(
            "Evaluating query: %s", query[:50] + "..." if len(query) > 50 else query
        )

        tools = await self._mcp_client.get_tools()
        actual_tools_called: list[str] = []
        execution_success = True
        response = ""
        errors: list[str] = []

        try:
            response, actual_tools_called = await self._llm_provider.query_with_tools(
                query, tools, self._mcp_client
            )
        except Exception as e:
            execution_success = False
            errors.append(str(e))
            logger.error("Query evaluation failed: %s", str(e))

        tool_accuracy = calculate_tool_accuracy(
            expected_tools or [], actual_tools_called
        )

        result = EvaluationResult(
            query=query,
            expected_tools=expected_tools or [],
            actual_tools=actual_tools_called,
            tool_accuracy=tool_accuracy,
            execution_success=execution_success,
            response=response,
            errors=errors,
        )

        logger.info(
            "Evaluation complete - Accuracy: %.2f, Success: %s",
            tool_accuracy,
            execution_success,
        )
        return result

    async def generate_actual_results(
        self, dataset_path: Path, output_path: Path
    ) -> None:
        if not self._mcp_client or not self._llm_provider:
            raise RuntimeError("Evaluator not initialized. Use async context manager.")

        logger.info("Generating actual results for dataset: %s", dataset_path)

        dataset = load_dataset(dataset_path)
        actual_results = []

        for i, task in enumerate(dataset):
            prompt = task["prompt"]
            logger.info(
                "Processing task %d/%d: %s", i + 1, len(dataset), prompt[:50] + "..."
            )

            tools = await self._mcp_client.get_tools()
            actual_tools_called: list[str] = []

            try:
                _, actual_tools_called = await self._llm_provider.query_with_tools(
                    prompt, tools, self._mcp_client
                )

                task_result = format_generation_result(
                    prompt,
                    actual_tools_called,
                    self.provider_name,
                    self._get_model_name(),
                )

                actual_results.append(task_result)

            except Exception as e:
                logger.error("Task %d failed: %s", i + 1, str(e))
                actual_results.append(
                    {
                        "query": prompt,
                        "tool_calls": [],
                        "model": f"{self.provider_name}-error",
                        "finish_reason": "error",
                    }
                )

        with open(output_path, "w") as f:
            json.dump(actual_results, f, indent=2)

        logger.info("Actual results saved to: %s", output_path)

    async def run_dataset_evaluation(
        self, dataset_path: Path, output_path: Path | None = None
    ) -> dict[str, Any]:
        if not self._mcp_client or not self._llm_provider:
            raise RuntimeError("Evaluator not initialized. Use async context manager.")

        logger.info("Running dataset evaluation: %s", dataset_path)

        dataset = load_dataset(dataset_path)
        actual_results = []

        for i, task in enumerate(dataset):
            prompt = task["prompt"]
            expected_tools = [tc["tool_name"] for tc in task.get("tool_calls", [])]

            logger.info("Task %d/%d: %s", i + 1, len(dataset), prompt[:50] + "...")

            result = await self.evaluate_query(prompt, expected_tools)

            actual_results.append(
                format_evaluation_result(
                    prompt,
                    result.actual_tools,
                    self.provider_name,
                    self._get_model_name(),
                    result.execution_success,
                )
            )

        evaluation_report = evaluate_dataset(
            dataset,
            actual_results,
            evaluate_params=True,
            dataset_path=str(dataset_path),
        )

        report_dict = evaluation_report.to_dict()

        if output_path:
            with open(output_path, "w") as f:
                json.dump(report_dict, f, indent=2)
            logger.info("Evaluation report saved to: %s", output_path)

        logger.info(
            "Dataset evaluation complete - Overall accuracy: %.2f",
            evaluation_report.overall_tool_accuracy,
        )

        return report_dict

    async def run_interactive_chat(self) -> None:
        if not self._mcp_client:
            raise RuntimeError("Evaluator not initialized. Use async context manager.")

        server_info = await self._mcp_client.get_server_info()
        tools = await self._mcp_client.get_tools()

        print("\n🤖 MCP Tool Calling Evaluator")
        print(f"📡 Server: {server_info.server_name} ({len(tools)} tools)")
        print(f"🧠 LLM: {self.provider_name}")
        print("Commands: 'quit', 'dataset <path>', or ask questions.\n")

        while True:
            try:
                query = input("Query: ").strip()
                if query.lower() in ["quit", "exit", "q"]:
                    break

                if not query:
                    continue

                if query.startswith("dataset "):
                    dataset_path = Path(query[8:].strip())
                    try:
                        report = await self.run_dataset_evaluation(dataset_path)
                        print("\n📊 Dataset Evaluation Complete")
                        print(
                            f"Overall Tool Accuracy: {report['overall_tool_accuracy']:.2f}"
                        )
                        print(
                            f"Perfect Matches: {report['perfect_matches']}/{report['total_tasks']}"
                        )
                        print(
                            f"Tool-Only Matches: {report['tool_only_matches']}/{report['total_tasks']}"
                        )
                    except Exception as e:
                        print(f"❌ Dataset evaluation failed: {e}")
                    continue

                result = await self.evaluate_query(query)
                print(f"\n🤖 {result.response}")
                print(
                    f"📊 Accuracy: {result.tool_accuracy:.2f} | Tools: {result.actual_tools}"
                )
                if result.errors:
                    print(f"❌ Errors: {result.errors}")
                print()

            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error("Chat error: %s", str(e))
                print(f"❌ Error: {e}")

    def _get_model_name(self) -> str:
        if self.model:
            return self.model
        if self.provider_name == "anthropic":
            return "claude-sonnet-4-20250514"
        elif self.provider_name == "openai":
            return "gpt-4o"
        return "unknown"


async def create_evaluator(
    server_target: str, provider: str = "anthropic", **kwargs: Any
) -> MCPEvaluator:
    return MCPEvaluator(server_target, provider, **kwargs)


async def main() -> None:
    import sys

    if len(sys.argv) < 2:
        print("Usage: python evaluator.py <server_target> [command] [options]")
        print("\nCommands:")
        print("  chat                    Interactive chat mode (default)")
        print("  dataset <path>          Evaluate a dataset")
        print("  generate <dataset> <output>  Generate actual results")
        print("\nExamples:")
        print("  # Interactive chat")
        print('  python evaluator.py "https://api.example.com/mcp"')
        print()
        print("  # Evaluate dataset")
        print(
            '  python evaluator.py "https://api.example.com/mcp" dataset my-dataset.json'
        )
        print()
        print("  # Generate actual results for existing evaluate-dataset command")
        print(
            '  python evaluator.py "https://api.example.com/mcp" generate my-dataset.json results.json'
        )
        return

    server_target = sys.argv[1]
    command = sys.argv[2] if len(sys.argv) > 2 else "chat"
    provider = "anthropic"

    try:
        async with await create_evaluator(server_target, provider) as evaluator:
            if command == "chat":
                await evaluator.run_interactive_chat()

            elif command == "dataset":
                if len(sys.argv) < 4:
                    print("Usage: python evaluator.py <server> dataset <dataset_path>")
                    return
                dataset_path = Path(sys.argv[3])
                report = await evaluator.run_dataset_evaluation(dataset_path)
                print("\n📊 Final Results:")
                print(f"Overall Tool Accuracy: {report['overall_tool_accuracy']:.2f}")
                print(
                    f"Perfect Matches: {report['perfect_matches']}/{report['total_tasks']}"
                )

            elif command == "generate":
                if len(sys.argv) < 5:
                    print(
                        "Usage: python evaluator.py <server> generate <dataset_path> <output_path>"
                    )
                    return
                dataset_path = Path(sys.argv[3])
                output_path = Path(sys.argv[4])
                await evaluator.generate_actual_results(dataset_path, output_path)
                print(f"\n✅ Actual results generated: {output_path}")
                print(
                    "Now run: mcp-doctor evaluate-dataset --dataset {} --actual-results {}".format(
                        dataset_path, output_path
                    )
                )

            else:
                print(f"Unknown command: {command}")

    except Exception as e:
        logger.error("Evaluator failed: %s", str(e))
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
