import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "parameter_validator",
    Path(__file__).resolve().parents[1] / "core/toolscore/parameter_validator.py",
)
pv_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pv_module)
ParameterValidator = pv_module.ParameterValidator


def test_generate_fibonacci_code():
    validator = ParameterValidator()
    result = validator.validate_tool_call('microsandbox', 'microsandbox_execute', {}, '计算斐波那契数列前10项')
    assert 'code' in result.suggestions
    assert 'fibonacci' in result.suggestions['code']
