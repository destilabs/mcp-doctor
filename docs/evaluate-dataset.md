# Dataset Evaluation

The `evaluate-dataset` command allows you to measure tool calling accuracy for LLM-generated results against expected outcomes in a dataset.

## Overview

This feature evaluates how accurately an LLM calls tools by comparing:
- **Tool Selection**: Did the LLM call the right tools?
- **Tool Order**: Did the LLM call them in the correct order?
- **Parameter Accuracy**: Did the LLM pass the correct parameters? (optional)

## Usage

```bash
mcp-doctor evaluate-dataset \
  --dataset <path-to-dataset.json> \
  --actual-results <path-to-results.json> \
  [--evaluate-params/--no-evaluate-params] \
  [--output-format <table|json|yaml>] \
  [--output <output-file.json>] \
  [--verbose]
```

### Required Arguments

- `--dataset`: Path to the dataset JSON file containing expected tool calls
- `--actual-results`: Path to JSON file containing actual LLM tool call results

### Optional Arguments

- `--evaluate-params/--no-evaluate-params`: Include parameter accuracy in evaluation (default: enabled)
- `--output-format`: Output format - `table`, `json`, or `yaml` (default: `table`)
- `--output`: Path to save evaluation report as JSON
- `--verbose`, `-v`: Show detailed task-by-task evaluation results

## Dataset Format

The dataset file should be a JSON array where each task contains:

```json
[
  {
    "prompt": "User instruction that would be sent to the LLM",
    "tools_called": ["tool_name_1", "tool_name_2"],
    "tools_args": [
      [{"param1": "value1"}],
      [{"param2": "value2"}]
    ]
  }
]
```

### Fields

- `prompt` (string): The natural language instruction given to the LLM
- `tools_called` (array): List of tool names in the order they should be called
- `tools_args` (array): Parallel array of arguments for each tool call
  - Each element is an array containing the parameters for that tool call
  - Can be an empty array `[]` if the tool takes no parameters
  - Usually contains a single dict `[{...}]` with the tool's parameters

## Actual Results Format

The actual results file should be a JSON array where each element corresponds to a task in the dataset:

```json
[
  [
    {
      "tool_name": "tool_name_1",
      "arguments": [{"param1": "value1"}]
    },
    {
      "tool_name": "tool_name_2",
      "arguments": [{"param2": "value2"}]
    }
  ]
]
```

Each task's results is an array of tool calls, where each call contains:
- `tool_name` (string): The name of the tool that was called
- `arguments` (array): The arguments passed to the tool

## Metrics

The evaluation produces the following metrics:

### Overall Metrics

- **Overall Tool Accuracy**: Percentage of tool calls that matched the expected tool (regardless of position)
- **Overall Tool Order Accuracy**: Percentage of tasks where the exact sequence of tools was correct
- **Overall Parameter Accuracy**: Percentage of tool calls where parameters matched exactly (if enabled)
- **Perfect Matches**: Number of tasks that were 100% correct (tools + parameters if enabled)
- **Tool-Only Matches**: Number of tasks where tools were correct regardless of parameters

### Per-Task Metrics

For each task, the evaluation shows:
- **Tool Accuracy**: Fraction of tools called correctly
- **Tool Order Accuracy**: 1.0 if exact sequence matches, 0.0 otherwise
- **Parameter Accuracy**: Fraction of parameters that matched (if enabled)

## Examples

### Basic Evaluation (with parameter checking)

```bash
mcp-doctor evaluate-dataset \
  --dataset lemlist-dataset.json \
  --actual-results sample-results.json
```

Output:
```
📊 Dataset Evaluation
Dataset: lemlist-dataset.json
Actual Results: sample-results.json
Parameter Evaluation: Enabled

           Evaluation Summary            
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┓
┃ Metric                      ┃ Value   ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━┩
│ Total Tasks                 │ 10      │
│ Overall Tool Accuracy       │ 100.00% │
│ Overall Tool Order Accuracy │ 100.00% │
│ Overall Parameter Accuracy  │ 90.00%  │
│ Perfect Matches             │ 8       │
│ Tool-Only Matches           │ 10      │
└─────────────────────────────┴─────────┘
```

### Tool-Only Evaluation (ignoring parameters)

```bash
mcp-doctor evaluate-dataset \
  --dataset lemlist-dataset.json \
  --actual-results sample-results.json \
  --no-evaluate-params
```

This is useful when you want to focus only on whether the LLM selected the right tools, without being strict about parameter values.

### Verbose Output

```bash
mcp-doctor evaluate-dataset \
  --dataset lemlist-dataset.json \
  --actual-results sample-results.json \
  --verbose
```

Shows detailed task-by-task breakdown with individual tool call comparisons.

### JSON Output

```bash
mcp-doctor evaluate-dataset \
  --dataset lemlist-dataset.json \
  --actual-results sample-results.json \
  --output-format json \
  --output evaluation-report.json
```

Saves a structured JSON report for programmatic analysis.

## Parameter Comparison

The parameter comparison is intelligent and handles several edge cases:

### Normalization

Parameters are normalized before comparison:
- `None` is treated as `{}`
- Single-element arrays with a dict `[{...}]` are unwrapped to just the dict
- Nested structures are recursively normalized

### Examples

These are considered equivalent:
```python
# Expected
[{"status": "running"}]

# Actual
{"status": "running"}
```

These are also equivalent:
```python
# Expected
None

# Actual
{}
```

Nested structures are compared recursively:
```python
# Expected
{"filters": [{"in": ["CxO"], "out": []}]}

# Actual
{"filters": [{"in": ["CxO"], "out": []}]}
# ✓ Match
```

## Use Cases

1. **LLM Benchmarking**: Compare different models' tool calling accuracy
2. **Prompt Engineering**: Evaluate how prompt changes affect tool calling
3. **Dataset Quality**: Validate that your synthetic dataset is being used correctly
4. **Regression Testing**: Ensure tool calling accuracy doesn't degrade over time
5. **Fine-tuning Evaluation**: Measure improvement after fine-tuning on tool calling

## Integration with Dataset Generation

You can generate a dataset using `mcp-doctor generate-dataset` and then evaluate LLM performance against it:

```bash
# Step 1: Generate a dataset
mcp-doctor generate-dataset \
  --target "npx lemlist-mcp" \
  --num-tasks 20 \
  --output dataset.json

# Step 2: Run the dataset through your LLM and save results
# (This step depends on your LLM setup)

# Step 3: Evaluate the results
mcp-doctor evaluate-dataset \
  --dataset dataset.json \
  --actual-results llm-results.json \
  --verbose
```

## Tips

1. **Start with --no-evaluate-params**: When first testing, focus on tool selection accuracy before worrying about exact parameters
2. **Use --verbose for debugging**: See exactly which parameters didn't match
3. **Save JSON reports**: Use `--output` to keep historical records of evaluations
4. **Normalize your data**: Ensure actual results follow the expected format exactly

## Limitations

- The evaluation is strict by default - parameters must match exactly (after normalization)
- Order matters - tools must be called in the exact sequence specified
- Currently supports only exact parameter matching (no fuzzy matching or semantic comparison)

## Future Enhancements

Potential improvements for future versions:
- Fuzzy parameter matching with configurable tolerance
- Semantic similarity for string parameters
- Support for approximate numeric comparisons
- Partial credit scoring for nearly-correct tool calls
- Integration with LangSmith for automatic result fetching

