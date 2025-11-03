"""Run dataset prompts through an LLM with actual MCP tools and capture results.

This script:
1. Connects to an MCP server to get available tools
2. Runs each dataset prompt through an LLM with those tools
3. Captures which tools the LLM actually calls
4. Saves results in format for evaluate-dataset command
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run_dataset_with_openai(
    dataset_path: Path,
    mcp_target: str,
    output_path: Path,
    model: str = "gpt-4o",
    timeout: int = 30,
    env_vars: Optional[Dict[str, str]] = None,
) -> None:
    """Run dataset through OpenAI with MCP tools.
    
    Args:
        dataset_path: Path to dataset JSON file
        mcp_target: MCP server URL or NPX command
        output_path: Where to save actual results
        model: OpenAI model to use
        timeout: Request timeout in seconds
        env_vars: Environment variables for NPX command
    """
    try:
        from openai import OpenAI
    except ImportError:
        logger.error("OpenAI SDK not installed. Run: pip install openai")
        return
    
    from mcp_analyzer.mcp_client import MCPClient
    
    logger.info(f"Connecting to MCP server: {mcp_target}")
    
    npx_kwargs = {}
    headers = {}
    
    if env_vars:
        npx_kwargs["env_vars"] = env_vars
        if "LEMLIST_API_KEY" in env_vars:
            headers["x-api-key"] = env_vars["LEMLIST_API_KEY"]
        for key in ["API_KEY", "AUTHORIZATION"]:
            if key in env_vars:
                headers["x-api-key"] = env_vars[key]
                break
    
    client = MCPClient(
        mcp_target, 
        timeout=timeout, 
        headers=headers if headers else None,
        **npx_kwargs
    )
    
    try:
        server_info = await client.get_server_info()
        logger.info(f"Connected to: {server_info.server_name or 'MCP Server'}")
        logger.info(f"Transport: {client._transport}")
        
        tools = await client.get_tools()
        logger.info(f"Retrieved {len(tools)} tools from MCP server")
        
        openai_tools = convert_mcp_tools_to_openai(tools)
        
        with open(dataset_path) as f:
            dataset = json.load(f)
        
        logger.info(f"Running {len(dataset)} prompts through {model}")
        
        openai_client = OpenAI()
        all_results = []
        
        for idx, task in enumerate(dataset):
            prompt = task["prompt"]
            logger.info(f"Task {idx + 1}/{len(dataset)}: {prompt[:60]}...")
            
            response = openai_client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                tools=openai_tools,
            )
            
            tool_calls = []
            tool_call_trace = []
            message = response.choices[0].message
            
            if message.tool_calls:
                for tc in message.tool_calls:
                    tool_calls.append({
                        "tool_name": tc.function.name,
                        "arguments": [json.loads(tc.function.arguments)],
                    })
                    tool_call_trace.append({
                        "id": tc.id,
                        "tool_name": tc.function.name,
                        "arguments": json.loads(tc.function.arguments),
                    })
                    logger.info(f"  → Called: {tc.function.name}")
            else:
                logger.info("  → No tools called")
            
            usage = response.usage
            task_result = {
                "query": prompt,
                "tool_calls": tool_calls,
                "tool_call_trace": tool_call_trace,
                "tokens": {
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens,
                },
                "model": model,
                "finish_reason": response.choices[0].finish_reason,
            }
            
            all_results.append(task_result)
        
        with open(output_path, "w") as f:
            json.dump(all_results, f, indent=2)
        
        logger.info(f"✅ Results saved to {output_path}")
        
    finally:
        await client.close()


async def run_dataset_with_anthropic(
    dataset_path: Path,
    mcp_target: str,
    output_path: Path,
    model: str = "claude-sonnet-4-20250514",
    timeout: int = 30,
    env_vars: Optional[Dict[str, str]] = None,
) -> None:
    """Run dataset through Anthropic with MCP tools.
    
    Args:
        dataset_path: Path to dataset JSON file
        mcp_target: MCP server URL or NPX command
        output_path: Where to save actual results
        model: Anthropic model to use
        timeout: Request timeout in seconds
        env_vars: Environment variables for NPX command
    """
    try:
        from anthropic import Anthropic
    except ImportError:
        logger.error("Anthropic SDK not installed. Run: pip install anthropic")
        return
    
    from mcp_analyzer.mcp_client import MCPClient
    
    logger.info(f"Connecting to MCP server: {mcp_target}")
    
    npx_kwargs = {}
    headers = {}
    
    if env_vars:
        npx_kwargs["env_vars"] = env_vars
        if "LEMLIST_API_KEY" in env_vars:
            headers["x-api-key"] = env_vars["LEMLIST_API_KEY"]
        for key in ["API_KEY", "AUTHORIZATION"]:
            if key in env_vars:
                headers["x-api-key"] = env_vars[key]
                break
    
    client = MCPClient(
        mcp_target, 
        timeout=timeout, 
        headers=headers if headers else None,
        **npx_kwargs
    )
    
    try:
        server_info = await client.get_server_info()
        logger.info(f"Connected to: {server_info.server_name or 'MCP Server'}")
        logger.info(f"Transport: {client._transport}")
        
        tools = await client.get_tools()
        logger.info(f"Retrieved {len(tools)} tools from MCP server")
        
        anthropic_tools = convert_mcp_tools_to_anthropic(tools)
        
        with open(dataset_path) as f:
            dataset = json.load(f)
        
        logger.info(f"Running {len(dataset)} prompts through {model}")
        
        anthropic_client = Anthropic()
        all_results = []
        
        for idx, task in enumerate(dataset):
            prompt = task["prompt"]
            logger.info(f"Task {idx + 1}/{len(dataset)}: {prompt[:60]}...")
            
            response = anthropic_client.messages.create(
                model=model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
                tools=anthropic_tools,
            )
            
            tool_calls = []
            tool_call_trace = []
            
            for block in response.content:
                if block.type == "tool_use":
                    tool_calls.append({
                        "tool_name": block.name,
                        "arguments": [block.input],
                    })
                    tool_call_trace.append({
                        "id": block.id,
                        "tool_name": block.name,
                        "arguments": block.input,
                    })
                    logger.info(f"  → Called: {block.name}")
            
            if not tool_calls:
                logger.info("  → No tools called")
            
            task_result = {
                "query": prompt,
                "tool_calls": tool_calls,
                "tool_call_trace": tool_call_trace,
                "tokens": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
                },
                "model": model,
                "stop_reason": response.stop_reason,
            }
            
            all_results.append(task_result)
        
        with open(output_path, "w") as f:
            json.dump(all_results, f, indent=2)
        
        logger.info(f"✅ Results saved to {output_path}")
        
    finally:
        await client.close()


def convert_mcp_tools_to_openai(mcp_tools: List[Any]) -> List[Dict[str, Any]]:
    """Convert MCP tools to OpenAI tools format."""
    openai_tools = []
    
    for tool in mcp_tools:
        parameters = tool.parameters if hasattr(tool, 'parameters') else tool.input_schema
        
        openai_tool = {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "No description",
                "parameters": parameters or {"type": "object", "properties": {}},
            }
        }
        openai_tools.append(openai_tool)
    
    return openai_tools


def convert_mcp_tools_to_anthropic(mcp_tools: List[Any]) -> List[Dict[str, Any]]:
    """Convert MCP tools to Anthropic tools format."""
    anthropic_tools = []
    
    for tool in mcp_tools:
        parameters = tool.parameters if hasattr(tool, 'parameters') else tool.input_schema
        
        anthropic_tool = {
            "name": tool.name,
            "description": tool.description or "No description",
            "input_schema": parameters or {"type": "object", "properties": {}},
        }
        anthropic_tools.append(anthropic_tool)
    
    return anthropic_tools


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Run dataset through LLM with actual MCP tools"
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        required=True,
        help="Path to dataset JSON file",
    )
    parser.add_argument(
        "--mcp-target",
        required=True,
        help="MCP server URL or NPX command",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Where to save actual results JSON",
    )
    parser.add_argument(
        "--provider",
        choices=["openai", "anthropic"],
        default="openai",
        help="LLM provider to use",
    )
    parser.add_argument(
        "--model",
        help="Model name (defaults: gpt-4o for OpenAI, claude-sonnet-4-20250514 for Anthropic)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Request timeout in seconds",
    )
    parser.add_argument(
        "--env-vars",
        help='Environment variables as JSON (e.g., \'{"API_KEY": "value"}\')',
    )
    
    args = parser.parse_args()
    
    env_vars = None
    if args.env_vars:
        env_vars = json.loads(args.env_vars)
    elif os.getenv("LEMLIST_API_KEY"):
        env_vars = {"LEMLIST_API_KEY": os.getenv("LEMLIST_API_KEY")}
    
    if args.provider == "openai":
        model = args.model or "gpt-4o"
        await run_dataset_with_openai(
            args.dataset,
            args.mcp_target,
            args.output,
            model=model,
            timeout=args.timeout,
            env_vars=env_vars,
        )
    else:
        model = args.model or "claude-sonnet-4-20250514"
        await run_dataset_with_anthropic(
            args.dataset,
            args.mcp_target,
            args.output,
            model=model,
            timeout=args.timeout,
            env_vars=env_vars,
        )


if __name__ == "__main__":
    asyncio.run(main())
