# MicroSandbox Server Tests

This directory contains comprehensive tests for the MicroSandbox Server, covering all actions and agent interactions.

## Test Structure

### Test Files

1. **`test_microsandbox_server.py`** - Core functionality tests
   - Tests all 7 microsandbox actions
   - Parameter validation and error handling
   - Session management
   - Package installation
   - Performance monitoring
   - Fallback execution

2. **`test_microsandbox_agent_interactions.py`** - Agent integration tests
   - Tool capability registration
   - Action routing and error handling
   - Session state management
   - Performance metrics integration
   - Health monitoring
   - MCP protocol compliance

3. **`run_microsandbox_tests.py`** - Comprehensive test runner
   - Dependency checks
   - MicroSandbox server management
   - Integration testing
   - Performance benchmarks
   - Detailed reporting

### Test Categories

- **Basic Code Execution**: Python code execution, error handling
- **Session Management**: Session creation, persistence, cleanup
- **Package Installation**: Python package installation and verification
- **Performance Monitoring**: Stats collection, health status
- **Parameter Validation**: Error handling, input validation
- **Fallback Execution**: Local execution when MicroSandbox unavailable
- **Agent Integration**: MCP server integration, capability registration

## Running Tests

### Prerequisites

```bash
# Install dependencies
pip install pytest pytest-asyncio microsandbox psutil aiohttp

# Start MicroSandbox server (optional - tests can start it automatically)
python -m microsandbox --host 127.0.0.1 --port 5555
```

### Quick Test Run

```bash
# Run all tests
python tests/run_microsandbox_tests.py

# Run with debug output
python tests/run_microsandbox_tests.py --debug

# Run basic tests only
python tests/run_microsandbox_tests.py --basic-only
```

### Using Pytest

```bash
# Run all tests
pytest tests/test_microsandbox*.py

# Run specific test file
pytest tests/test_microsandbox_server.py

# Run with verbose output
pytest tests/test_microsandbox*.py -v

# Run specific test function
pytest tests/test_microsandbox_server.py::test_microsandbox_comprehensive
```

### Test Options

```bash
# Skip performance tests (faster execution)
python tests/run_microsandbox_tests.py --skip-performance

# Skip integration tests
python tests/run_microsandbox_tests.py --skip-integration

# Set custom timeout
python tests/run_microsandbox_tests.py --timeout 600

# Run in debug mode
python tests/run_microsandbox_tests.py --debug
```

## Test Results

Test results are saved to multiple files:

- `comprehensive_microsandbox_test_results.json` - Complete test suite results
- `test_results_microsandbox_server.json` - Basic functionality test results
- `test_results_microsandbox_agent_interactions.json` - Agent interaction test results

## Test Coverage

The test suite covers:

### MicroSandbox Actions (7 actions)
- ✅ `microsandbox_execute` - Python code execution
- ✅ `microsandbox_install_package` - Package installation
- ✅ `microsandbox_list_sessions` - Session listing
- ✅ `microsandbox_close_session` - Session cleanup
- ✅ `microsandbox_cleanup_expired` - Expired session cleanup
- ✅ `microsandbox_get_performance_stats` - Performance metrics
- ✅ `microsandbox_get_health_status` - Health monitoring

### Code Execution Features
- ✅ Simple Python code execution
- ✅ Mathematical calculations and imports
- ✅ Error handling and stderr capture
- ✅ Timeout handling
- ✅ Fallback to local Python executor
- ✅ Concurrent execution

### Session Management
- ✅ Session creation and persistence
- ✅ Variable persistence across executions
- ✅ Session listing and metadata
- ✅ Manual session closing
- ✅ Automatic expired session cleanup
- ✅ Session state consistency

### Package Management
- ✅ Package installation
- ✅ Version-specific installation
- ✅ Installation verification and import testing
- ✅ Error handling for invalid packages
- ✅ Package name validation

### Performance & Monitoring
- ✅ Real-time performance metrics collection
- ✅ Memory usage monitoring
- ✅ Execution time tracking
- ✅ Success rate calculation
- ✅ Error distribution analysis
- ✅ Health status assessment
- ✅ Performance recommendations

### Agent Integration
- ✅ MCP server initialization
- ✅ Tool capability registration (7 capabilities)
- ✅ Parameter schema validation
- ✅ Action routing to handlers
- ✅ Error handling consistency
- ✅ Concurrent request handling
- ✅ Protocol compliance

### Fallback & Reliability
- ✅ Local Python executor fallback
- ✅ MicroSandbox server connectivity checks
- ✅ Graceful degradation
- ✅ Automatic server startup (optional)
- ✅ Error recovery mechanisms

## Debugging Failed Tests

### Common Issues

1. **MicroSandbox Server Not Running**
   ```bash
   # Start the server manually
   python -m microsandbox --host 127.0.0.1 --port 5555
   
   # Or let the test runner start it automatically
   python tests/run_microsandbox_tests.py --debug
   ```

2. **Dependency Issues**
   ```bash
   # Install missing dependencies
   pip install microsandbox psutil aiohttp
   
   # Check dependency status
   python -c "import microsandbox, psutil; print('Dependencies OK')"
   ```

3. **Timeout Issues**
   ```bash
   # Increase timeout
   python tests/run_microsandbox_tests.py --timeout 600
   ```

4. **Configuration Issues**
   ```bash
   # Verify configuration
   python -c "from core.config_manager import ConfigManager; print(ConfigManager().get_ports_config())"
   ```

### Debug Output

Enable debug mode for detailed logging:
```bash
python tests/run_microsandbox_tests.py --debug
```

This will show:
- Detailed MicroSandbox operations
- Server connectivity checks
- Performance metrics
- Error stack traces

### MicroSandbox Server Management

The test runner can automatically manage the MicroSandbox server:
- Checks if server is running
- Starts server if needed
- Uses fallback execution if server unavailable
- Provides connectivity diagnostics

## Environment Variables

- `MICROSANDBOX_MCP_SERVER_PORT=8090` - MCP server port
- `MICROSANDBOX_HOST=localhost` - Server host
- `MICROSANDBOX_LISTEN_HOST=0.0.0.0` - Bind address

## Test Performance

Typical execution times:
- Basic functionality tests: ~30-60 seconds
- Agent interaction tests: ~10-20 seconds
- Integration tests: ~15-30 seconds
- Performance tests: ~20-40 seconds

Total comprehensive test time: ~1-3 minutes

## Contributing

When adding new microsandbox actions or features:

1. Add tests to `test_microsandbox_server.py`
2. Add integration tests to `test_microsandbox_agent_interactions.py`
3. Update this README with new test coverage
4. Ensure all tests pass before submitting

## Test Philosophy

These tests follow the principle of testing both:
- **Unit functionality** - Individual actions work correctly
- **Integration behavior** - Actions work together in realistic scenarios
- **Error conditions** - Graceful handling of edge cases
- **Performance characteristics** - Acceptable response times
- **Fallback mechanisms** - Robust operation when dependencies unavailable
- **Agent compatibility** - Seamless integration with agent platform

The goal is to ensure the MicroSandbox Server is reliable, performant, and integrates seamlessly with the agent platform while providing secure code execution capabilities.

## Security Considerations

The tests verify:
- ✅ Code execution isolation
- ✅ Session isolation between users
- ✅ Timeout enforcement
- ✅ Package validation
- ✅ Error message sanitization
- ✅ Resource usage monitoring

Note: Tests use safe test code only. Malicious code testing should be done in isolated environments.