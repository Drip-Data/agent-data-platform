import importlib.util
from pathlib import Path
import types
import sys

dummy_vm = types.ModuleType("core.llm.validation_middleware")
dummy_vm.validation_middleware = types.SimpleNamespace(validate_before_llm_call=lambda x: (True, x, None))
dummy_vm.ResponseValidationResult = object
dummy_vm.validate_llm_response = lambda x: None
sys.modules["core.llm.validation_middleware"] = dummy_vm

spec = importlib.util.spec_from_file_location(
    "reasoning_response_parser",
    Path(__file__).resolve().parents[1] / "core/llm/response_parsers/reasoning_response_parser.py",
)
parser_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parser_module)
ReasoningResponseParser = parser_module.ReasoningResponseParser


def test_parse_malformed_json():
    parser = ReasoningResponseParser()
    raw = '{thinking:"ok", action:"browser_navigate", tool_id:"browser_use"}'
    result = parser.parse_response(raw)
    assert result.get('action') == 'browser_navigate'
    assert result.get('tool_id') == 'browser_use'
