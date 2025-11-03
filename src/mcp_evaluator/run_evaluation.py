from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from .evaluator import create_evaluator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run_and_display_results(
    server_target: str, dataset_path: Path, output_path: Path
) -> None:
    logger.info("Starting dataset evaluation...")
    logger.info("Server: %s", server_target)
    logger.info("Dataset: %s", dataset_path)
    logger.info("Output: %s", output_path)

    async with await create_evaluator(server_target) as evaluator:
        logger.info("\n" + "=" * 70)
        logger.info("GENERATING ACTUAL RESULTS")
        logger.info("=" * 70)
        await evaluator.generate_actual_results(dataset_path, output_path)

        with open(output_path) as f:
            results = json.load(f)

        print_results_summary(results, dataset_path, output_path)

        report_path = output_path.parent / "evaluation-report.json"
        print_evaluation_summary(
            await evaluator.run_dataset_evaluation(dataset_path, report_path),
            report_path,
        )


def print_results_summary(
    results: list[dict[str, Any]], dataset_path: Path, output_path: Path
) -> None:
    print("\n" + "=" * 70)
    print("📊 EVALUATION RESULTS")
    print("=" * 70)
    print(f"Dataset: {dataset_path}")
    print(f"Total Tasks: {len(results)}")
    print("=" * 70)

    for i, result in enumerate(results, 1):
        query = result["query"]
        tools = [tc["tool_name"] for tc in result.get("tool_calls", [])]
        model = result.get("model", "unknown")

        print(f"\n[{i}/{len(results)}] {query[:60]}...")
        print(f"  Model: {model}")
        print(f"  Tools Called: {tools if tools else 'None'}")
        print(f"  Success: {result.get('finish_reason') != 'error'}")

    print("\n" + "=" * 70)
    print(f"✅ Results saved to: {output_path}")
    print("=" * 70)


def print_evaluation_summary(report: dict[str, Any], report_path: Path) -> None:
    print("\n" + "=" * 70)
    print("📈 ACCURACY EVALUATION")
    print("=" * 70)

    print(f"\n🎯 Overall Tool Accuracy: {report['overall_tool_accuracy']:.2%}")
    print(f"🎯 Overall Order Accuracy: {report['overall_tool_order_accuracy']:.2%}")

    if report.get("overall_param_accuracy"):
        print(f"🎯 Overall Param Accuracy: {report['overall_param_accuracy']:.2%}")

    print(f"\n✨ Perfect Matches: {report['perfect_matches']}/{report['total_tasks']}")
    print(
        f"✨ Tool-Only Matches: {report['tool_only_matches']}/{report['total_tasks']}"
    )

    print("\n" + "=" * 70)
    print(f"📄 Detailed report saved to: {report_path}")
    print("=" * 70)


async def main() -> None:
    import sys

    if len(sys.argv) < 3:
        print(
            "Usage: python run_evaluation.py <server_target> <dataset_path> [output_path]"
        )
        print("\nExample:")
        print(
            '  python src/mcp_evaluator/run_evaluation.py "https://api.example.com/mcp" dataset.json results.json'
        )
        return

    server_target = sys.argv[1]
    dataset_path = Path(sys.argv[2])
    output_path = (
        Path(sys.argv[3]) if len(sys.argv) > 3 else Path("evaluator-results.json")
    )

    try:
        await run_and_display_results(server_target, dataset_path, output_path)
    except Exception as e:
        logger.error("Evaluation failed: %s", str(e))
        print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
