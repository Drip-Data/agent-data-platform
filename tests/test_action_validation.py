import importlib.util
from pathlib import Path
import types
import sys

# Stub out heavy dependencies before loading the parser module
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


def test_action_correction():
    parser = ReasoningResponseParser()
    corrected = parser._validate_and_correct_action('browser_get_content', 'browser_use')
    assert corrected == 'browser_extract_content'
