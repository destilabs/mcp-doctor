"""Example script showing how to generate actual_results.json for evaluation.

This demonstrates how to run prompts from a dataset through an LLM
and capture the tool calls for evaluation.
"""

import json
from pathlib import Path
from typing import Any, Dict, List


def extract_tool_calls_from_llm_response(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract tool calls from an LLM response.
    
    This is a simplified example. Your actual implementation will depend
    on the LLM provider and SDK you're using.
    
    Args:
        response: Raw response from the LLM API
        
    Returns:
        List of tool calls with tool_name and arguments
        
    Example response formats:
    
    OpenAI:
    {
        "choices": [{
            "message": {
                "tool_calls": [
                    {
                        "function": {
                            "name": "get_campaigns",
                            "arguments": '{"status": "running"}'
                        }
                    }
                ]
            }
        }]
    }
    
    Anthropic:
    {
        "content": [
            {
                "type": "tool_use",
                "name": "get_campaigns",
                "input": {"status": "running"}
            }
        ]
    }
    """
    tool_calls = []
    
    if "choices" in response:
        message = response["choices"][0].get("message", {})
        raw_tool_calls = message.get("tool_calls", [])
        
        for tc in raw_tool_calls:
            function = tc.get("function", {})
            tool_calls.append({
                "tool_name": function.get("name", ""),
                "arguments": [json.loads(function.get("arguments", "{}"))],
            })
    
    elif "content" in response:
        for block in response["content"]:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tool_calls.append({
                    "tool_name": block.get("name", ""),
                    "arguments": [block.get("input", {})],
                })
    
    return tool_calls


def run_dataset_through_llm(
    dataset_path: Path,
    output_path: Path,
    llm_client: Any = None,
) -> None:
    """Run each prompt in dataset through LLM and save results.
    
    Args:
        dataset_path: Path to dataset JSON file
        output_path: Path to save actual results
        llm_client: Your LLM client instance (OpenAI, Anthropic, etc.)
    """
    with open(dataset_path) as f:
        dataset = json.load(f)
    
    all_results = []
    
    for task in dataset:
        response = llm_client.generate(task["prompt"])
        
        tool_calls = extract_tool_calls_from_llm_response(response)
        all_results.append(tool_calls)
    
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2)
    
    print(f"✅ Saved {len(all_results)} task results to {output_path}")


def example_with_openai():
    """Example using OpenAI SDK."""
    try:
        from openai import OpenAI
    except ImportError:
        print("OpenAI SDK not installed. Run: pip install openai")
        return
    
    client = OpenAI()
    
    dataset_path = Path("lemlist-dataset.json")
    output_path = Path("openai-results.json")
    
    with open(dataset_path) as f:
        dataset = json.load(f)
    
    all_results = []
    
    for task in dataset:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": task["prompt"]}],
            tools=[],
        )
        
        tool_calls = []
        message = response.choices[0].message
        
        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append({
                    "tool_name": tc.function.name,
                    "arguments": [json.loads(tc.function.arguments)],
                })
        
        all_results.append(tool_calls)
    
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2)
    
    print(f"✅ OpenAI results saved to {output_path}")


def example_with_anthropic():
    """Example using Anthropic SDK."""
    try:
        from anthropic import Anthropic
    except ImportError:
        print("Anthropic SDK not installed. Run: pip install anthropic")
        return
    
    client = Anthropic()
    
    dataset_path = Path("lemlist-dataset.json")
    output_path = Path("anthropic-results.json")
    
    with open(dataset_path) as f:
        dataset = json.load(f)
    
    all_results = []
    
    for task in dataset:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": task["prompt"]}],
            tools=[],
        )
        
        tool_calls = []
        
        for block in response.content:
            if block.type == "tool_use":
                tool_calls.append({
                    "tool_name": block.name,
                    "arguments": [block.input],
                })
        
        all_results.append(tool_calls)
    
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2)
    
    print(f"✅ Anthropic results saved to {output_path}")


if __name__ == "__main__":
    print("Example: Generating actual results for evaluation\n")
    
    print("Choose your LLM provider:")
    print("1. OpenAI")
    print("2. Anthropic")
    print("3. Mock (for demonstration)")
    
    choice = input("\nEnter choice (1-3): ").strip()
    
    if choice == "1":
        example_with_openai()
    elif choice == "2":
        example_with_anthropic()
    else:
        run_dataset_through_llm(
            Path("lemlist-dataset.json"),
            Path("mock-results.json"),
            llm_client=None,
        )

