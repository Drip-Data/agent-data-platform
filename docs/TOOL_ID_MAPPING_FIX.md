# Tool ID Mapping Fix Documentation

## Problem

The ToolScore client was returning old tool IDs (`['microsandbox-mcp-server', 'mcp-search-tool', 'browser-use-mcp-server', 'mcp-deepsearch']`) while the actual registered tool services were using new IDs (`['microsandbox', 'mcp-search-tool', 'browser_use', 'deepsearch']`). This mismatch caused tool execution failures and inconsistent behavior.

## Root Cause

The issue was caused by hardcoded tool IDs in multiple places throughout the codebase:

1. **Parameter Validator**: Had hardcoded tool schemas using old IDs
2. **Configuration Files**: Tool aliases and mappings referenced old IDs
3. **Runtime Components**: Essential tools lists and validation logic used old IDs
4. **Client Components**: Tool descriptions and details used old IDs

## Solution

### 1. Tool ID Mappings
Updated the tool ID mappings from old to new format:

| Old Tool ID | New Tool ID |
|-------------|-------------|
| `mcp-deepsearch` | `deepsearch` |
| `microsandbox-mcp-server` | `microsandbox` |
| `browser-use-mcp-server` | `browser_use` |
| `mcp-search-tool` | `mcp-search-tool` (unchanged) |

### 2. Files Modified

#### Core Configuration Files
- **`config/tool_aliases.yaml`**: Updated all parameter aliases, action aliases, tool alternatives, and error corrections to use new tool IDs
- **`config/unified_tool_mappings.yaml`**: Already had correct mappings with old IDs as aliases

#### Core Components  
- **`core/toolscore/parameter_validator.py`**: 
  - Updated `tool_schemas` dictionary with new tool IDs
  - Fixed validation logic and parameter relationship checks
  - Updated default aliases and alternatives suggestions

- **`core/toolscore/monitoring_api.py`**: 
  - Fixed hardcoded microsandbox reference in execute_tool method

#### Runtime Components
- **`runtimes/reasoning/enhanced_runtime.py`**:
  - Updated `essential_tools` list with new tool IDs
  - Fixed LLM prompt templates to reference new tool IDs
  - Updated validation rules and parameter mappings dictionaries
  - Fixed tool connectivity verification methods

- **`runtimes/reasoning/real_time_tool_client.py`**:
  - Updated `tool_details` dictionary with new tool IDs
  - Fixed tool description generation logic

### 3. Verification

Created `scripts/verify_tool_id_mappings.py` to:
- Scan all relevant files for old tool ID references
- Test ToolScore API responses for correct tool IDs
- Provide detailed reporting of any remaining issues
- Ensure configuration consistency

## Testing

Run the verification script to ensure all fixes are working:

```bash
python3 scripts/verify_tool_id_mappings.py
```

Expected output:
```
✅ Verification PASSED - All files clean
```

## Impact

### Before the Fix
- ToolScore API returned old tool IDs causing execution failures
- Mismatched tool references between different system components
- Parameter validation failed due to ID mismatches
- Tool discovery and execution was inconsistent

### After the Fix
- Consistent tool IDs across all system components
- ToolScore API returns correct new tool IDs
- Parameter validation works with proper tool ID mapping
- Tool execution flows work seamlessly
- Backward compatibility maintained through alias mappings

## Backward Compatibility

The fix maintains backward compatibility by:
- Keeping alias mappings in `unified_tool_mappings.yaml`
- Old tool IDs are mapped to new canonical IDs automatically
- Existing configurations and scripts continue to work
- Gradual migration path for any external dependencies

## Verification Commands

To verify the fix is working:

1. **Check file consistency**:
   ```bash
   python3 scripts/verify_tool_id_mappings.py
   ```

2. **Test ToolScore API** (requires running service):
   ```bash
   curl http://localhost:8091/api/v1/tools/available | jq '.available_tools[].tool_id'
   ```
   Should return: `["deepsearch", "microsandbox", "browser_use", "mcp-search-tool"]`

3. **Test tool execution**:
   ```bash
   curl -X POST http://localhost:8091/api/v1/tools/execute \
     -H "Content-Type: application/json" \
     -d '{"tool_id": "microsandbox", "action": "microsandbox_execute", "parameters": {"code": "print(\"Hello World\")"}}'
   ```

## Related Files

### Modified Files
- `config/tool_aliases.yaml`
- `core/toolscore/parameter_validator.py` 
- `core/toolscore/monitoring_api.py`
- `runtimes/reasoning/enhanced_runtime.py`
- `runtimes/reasoning/real_time_tool_client.py`

### New Files
- `scripts/verify_tool_id_mappings.py`
- `docs/TOOL_ID_MAPPING_FIX.md`

### Unchanged but Important
- `config/unified_tool_mappings.yaml` (already had correct mappings)

## Commit History

1. **85b5c4a**: Fix ToolScore tool ID mappings: Update from old to new IDs
2. **755b12f**: Complete tool ID mapping fixes and add verification script

## Future Maintenance

1. Use the verification script before making tool ID changes
2. Always update both the canonical ID and alias mappings
3. Test both file consistency and API responses
4. Maintain backward compatibility through aliases
5. Document any new tool ID changes in this file