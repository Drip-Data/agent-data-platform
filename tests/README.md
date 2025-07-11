# Browser Use Tool Tests

This directory contains comprehensive tests for the Browser Use Tool, covering all actions and agent interactions.

## Test Structure

### Test Files

1. **`test_browser_use_tool.py`** - Core functionality tests
   - Tests all 25+ browser actions
   - Parameter validation
   - Error handling
   - Basic browser operations

2. **`test_browser_agent_interactions.py`** - Agent integration tests
   - Tool capability registration
   - Action routing
   - State management
   - Concurrent operations
   - Resource cleanup

3. **`run_browser_tests.py`** - Comprehensive test runner
   - Dependency checks
   - Performance benchmarks
   - Stress testing
   - Detailed reporting

### Test Categories

- **Basic Navigation**: URL navigation, page info retrieval
- **Content Extraction**: Page content, accessibility tree, targeted extraction
- **Element Interaction**: Clicking, text input, keyboard actions
- **Scrolling Operations**: Page scrolling, text targeting
- **Tab Management**: Opening, switching, closing tabs
- **AI Task Execution**: Natural language task execution
- **Utility Functions**: Screenshots, PDF generation, waiting
- **Parameter Validation**: Error handling, type checking
- **Agent Integration**: MCP server integration, capability registration

## Running Tests

### Prerequisites

```bash
# Install dependencies
pip install pytest pytest-asyncio playwright browser-use

# Install playwright browsers
playwright install
```

### Quick Test Run

```bash
# Run all tests
python tests/run_browser_tests.py

# Run with visible browser (for debugging)
python tests/run_browser_tests.py --visible

# Run with debug output
python tests/run_browser_tests.py --debug

# Run basic tests only
python tests/run_browser_tests.py --basic-only
```

### Using Pytest

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_browser_use_tool.py

# Run with verbose output
pytest tests/ -v

# Run specific test function
pytest tests/test_browser_use_tool.py::test_browser_use_comprehensive
```

### Test Options

```bash
# Skip performance tests (faster execution)
python tests/run_browser_tests.py --skip-performance

# Skip stress tests
python tests/run_browser_tests.py --skip-stress

# Set custom timeout
python tests/run_browser_tests.py --timeout 600

# Run in debug mode with visible browser
python tests/run_browser_tests.py --debug --visible
```

## Test Results

Test results are saved to multiple files:

- `comprehensive_test_results.json` - Complete test suite results
- `test_results_browser_use.json` - Basic functionality test results
- `test_results_agent_interactions.json` - Agent interaction test results

## Test Coverage

The test suite covers:

### Browser Actions (25+ actions)
- ✅ `browser_use_execute_task` - AI task execution
- ✅ `browser_navigate` - URL navigation
- ✅ `browser_search_google` - Google search
- ✅ `browser_go_back` - Navigation back
- ✅ `browser_click_element` - Element clicking
- ✅ `browser_input_text` - Text input
- ✅ `browser_send_keys` - Keyboard actions
- ✅ `browser_scroll_down/up` - Page scrolling
- ✅ `browser_scroll_to_text` - Text targeting
- ✅ `browser_switch_tab` - Tab switching
- ✅ `browser_open_tab` - New tab creation
- ✅ `browser_close_tab` - Tab closing
- ✅ `browser_extract_content` - Content extraction
- ✅ `browser_get_content` - Page content retrieval
- ✅ `browser_get_ax_tree` - Accessibility tree
- ✅ `browser_get_dropdown_options` - Dropdown handling
- ✅ `browser_select_dropdown_option` - Dropdown selection
- ✅ `browser_drag_drop` - Drag and drop
- ✅ `browser_save_pdf` - PDF generation
- ✅ `browser_screenshot` - Screenshot capture
- ✅ `browser_wait` - Waiting functionality
- ✅ `browser_get_page_info` - Page information
- ✅ `browser_get_current_url` - URL retrieval
- ✅ `browser_close_session` - Session cleanup

### Agent Integration
- ✅ MCP server initialization
- ✅ Tool capability registration
- ✅ Parameter schema validation
- ✅ Action routing
- ✅ Error handling consistency
- ✅ State management
- ✅ Concurrent operation handling
- ✅ Resource cleanup

### Performance & Reliability
- ✅ Navigation performance benchmarks
- ✅ Content extraction performance
- ✅ Stress testing with rapid actions
- ✅ Memory and resource management
- ✅ Error recovery mechanisms

## Debugging Failed Tests

### Common Issues

1. **Browser Launch Failures**
   ```bash
   # Try running with visible browser
   python tests/run_browser_tests.py --visible --debug
   ```

2. **Timeout Issues**
   ```bash
   # Increase timeout
   python tests/run_browser_tests.py --timeout 600
   ```

3. **Dependency Issues**
   ```bash
   # Check dependencies first
   python -c "import browser_use, playwright; print('Dependencies OK')"
   ```

4. **Configuration Issues**
   ```bash
   # Verify configuration
   python -c "from core.config_manager import ConfigManager; print(ConfigManager().get_llm_config())"
   ```

### Debug Output

Enable debug mode for detailed logging:
```bash
python tests/run_browser_tests.py --debug
```

This will show:
- Detailed browser operations
- LLM adapter communications
- Action parameter validation
- Error stack traces

### Browser Inspection

Run with visible browser to see what's happening:
```bash
python tests/run_browser_tests.py --visible
```

## Environment Variables

- `BROWSER_HEADLESS=false` - Run browser in visible mode
- `BROWSER_USE_SERVER_PORT=8003` - MCP server port
- `BROWSER_USE_HOST=localhost` - Server host

## Contributing

When adding new browser actions or features:

1. Add tests to `test_browser_use_tool.py`
2. Add integration tests to `test_browser_agent_interactions.py`
3. Update this README with new test coverage
4. Ensure all tests pass before submitting

## Test Philosophy

These tests follow the principle of testing both:
- **Unit functionality** - Individual actions work correctly
- **Integration behavior** - Actions work together in realistic scenarios
- **Error conditions** - Graceful handling of edge cases
- **Performance characteristics** - Acceptable response times
- **Resource management** - Proper cleanup and memory usage

The goal is to ensure the Browser Use Tool is reliable, performant, and integrates seamlessly with the agent platform.