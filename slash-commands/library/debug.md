---
description: Systematic debugging with root cause analysis and comprehensive fixes
argument-hint: "[error message/issue description] [file:line] [additional context]"
model: opus
---

# Advanced Debugging Protocol

Ultrathink deeply about the issue, considering all possible causes and their likelihood. Create a systematic debugging plan before taking any action.

## Issue Analysis

**Reported issue**: $ARGUMENTS

Parse the arguments to identify:
- Error messages or stack traces
- File and line number references
- Specific function or component names
- Environmental context (production, development, test)
- Reproduction steps or conditions

## Systematic Debugging Workflow

### Phase 1: Information Gathering

#### 1.1 Error Context Analysis
```bash
# Search for error patterns in logs
grep -r "ERROR\|WARN\|FATAL" logs/ --include="*.log" | tail -50

# Check recent changes that might have introduced the issue
git log --oneline -10
git diff HEAD~1

# Identify when the issue started
git bisect start
git bisect bad  # Current version is bad
git bisect good <last-known-good>  # Mark last working version
```

#### 1.2 Code Investigation
Examine the specific area where the error occurs:
- Read the complete file containing the error
- Understand the function/class purpose and dependencies
- Check recent modifications to this code
- Review related test files

#### 1.3 Dependency Analysis
```bash
# Check for dependency issues
npm ls --depth=0  # or pip list, go mod graph, etc.

# Look for version conflicts
npm outdated  # or equivalent for other package managers

# Verify environment variables
env | grep -E "NODE_ENV|DEBUG|LOG_LEVEL"
```

### Phase 2: Hypothesis Formation

Based on the gathered information, form hypotheses about the root cause:

1. **Most Likely Causes** (>70% probability)
   - Recent code changes
   - Configuration issues
   - Missing dependencies
   - Environment differences

2. **Possible Causes** (30-70% probability)
   - Race conditions
   - Memory issues
   - Network problems
   - Third-party service issues

3. **Edge Cases** (<30% probability)
   - Hardware issues
   - Compiler/interpreter bugs
   - OS-specific problems

### Phase 3: Systematic Testing

#### 3.1 Reproduction
Create a minimal reproduction case:
```bash
# Isolate the issue
# Create test file: debug_repro.py/js/etc
```

Document the exact steps:
1. Environment setup required
2. Specific inputs that trigger the issue
3. Expected vs actual behavior
4. Frequency of occurrence (always/sometimes/rarely)

#### 3.2 Hypothesis Testing
For each hypothesis, design a test:

**Hypothesis 1: [Specific cause]**
- Test method: [How to verify]
- Expected result if true: [What we should see]
- Actual result: [What happened]
- Conclusion: [Confirmed/Rejected]

#### 3.3 Advanced Debugging Techniques

**Memory Debugging**:
```bash
# Python
python -m memory_profiler script.py

# Node.js
node --inspect --expose-gc script.js

# Go
go run -race main.go
```

**Performance Profiling**:
```bash
# Generate flame graphs
perf record -g ./program
perf script | flamegraph.pl > flame.svg

# Or use language-specific profilers
```

**Network Debugging**:
```bash
# Monitor network traffic
tcpdump -i any -w debug.pcap
wireshark debug.pcap

# Check API responses
curl -v -X GET/POST "http://api-endpoint"
```

### Phase 4: Root Cause Identification

#### 4.1 Five Whys Analysis
1. Why did the error occur? → [Immediate cause]
2. Why did [immediate cause] happen? → [Underlying cause]
3. Why did [underlying cause] happen? → [Deeper cause]
4. Why did [deeper cause] happen? → [Root cause]
5. Why did [root cause] happen? → [Systemic issue]

#### 4.2 Impact Assessment
- **Scope**: Which components/features are affected?
- **Severity**: Data loss? Security issue? Performance degradation?
- **Users Affected**: How many? Which segments?
- **Workarounds**: Are there temporary solutions?

### Phase 5: Solution Implementation

#### 5.1 Fix Development
Create a comprehensive fix that:
1. Addresses the root cause (not just symptoms)
2. Prevents similar issues in the future
3. Maintains backward compatibility
4. Includes proper error handling

#### 5.2 Code Changes
```python
# Before (buggy code)
def process_data(data):
    # Issue: No null check
    return data.upper()

# After (fixed code)
def process_data(data):
    # Fix: Added null check and type validation
    if data is None:
        raise ValueError("Data cannot be None")
    if not isinstance(data, str):
        raise TypeError(f"Expected str, got {type(data)}")
    return data.upper()
```

#### 5.3 Defensive Programming
Add safeguards to prevent recurrence:
- Input validation
- Boundary checks
- Error recovery mechanisms
- Logging for future debugging
- Monitoring/alerting

### Phase 6: Testing & Validation

#### 6.1 Test Creation
Write comprehensive tests for the fix:

```python
def test_process_data_with_none():
    """Test that None input raises ValueError"""
    with pytest.raises(ValueError, match="Data cannot be None"):
        process_data(None)

def test_process_data_with_invalid_type():
    """Test that non-string input raises TypeError"""
    with pytest.raises(TypeError):
        process_data(123)

def test_process_data_happy_path():
    """Test normal operation"""
    assert process_data("hello") == "HELLO"

def test_process_data_edge_cases():
    """Test edge cases"""
    assert process_data("") == ""
    assert process_data(" ") == " "
    assert process_data("123") == "123"
```

#### 6.2 Regression Testing
Ensure the fix doesn't break existing functionality:
```bash
# Run full test suite
npm test  # or pytest, go test, etc.

# Run specific test categories
npm test -- --grep "integration"

# Check test coverage
npm run coverage
```

### Phase 7: Documentation

#### 7.1 Code Documentation
Add clear comments explaining:
- Why the bug occurred
- How the fix prevents it
- Any non-obvious implementation choices

#### 7.2 Knowledge Base Update
Document the issue for future reference:

```markdown
# Issue: [Brief Description]

## Symptoms
- Error message: [Exact error]
- Occurs when: [Conditions]
- Affected versions: [Version range]

## Root Cause
[Detailed explanation of why it happened]

## Solution
[How it was fixed]

## Prevention
[How to avoid similar issues]

## Related Issues
- Links to similar problems
- Dependencies or blockers
```

### Phase 8: Monitoring & Prevention

#### 8.1 Add Monitoring
```javascript
// Add metrics/logging
logger.info('Processing started', {
  inputSize: data.length,
  timestamp: Date.now()
});

try {
  const result = processData(data);
  metrics.increment('process.success');
  return result;
} catch (error) {
  metrics.increment('process.error');
  logger.error('Processing failed', { error, data });
  throw error;
}
```

#### 8.2 Set Up Alerts
Configure monitoring for:
- Error rate thresholds
- Performance degradation
- Resource usage anomalies
- Failed health checks

## Debugging Checklist

- [ ] Issue reproduced locally
- [ ] Root cause identified (not just symptoms)
- [ ] Fix implemented and tested
- [ ] Edge cases considered
- [ ] Tests written (unit, integration)
- [ ] Performance impact assessed
- [ ] Security implications reviewed
- [ ] Documentation updated
- [ ] Monitoring added
- [ ] Code reviewed
- [ ] Deployment plan created

## Common Debugging Patterns

### Pattern 1: Null/Undefined Reference
**Symptoms**: TypeError, NullPointerException
**Common Causes**: Missing initialization, async timing issues
**Fix Strategy**: Add null checks, use optional chaining

### Pattern 2: Race Condition
**Symptoms**: Intermittent failures, works in debug mode
**Common Causes**: Concurrent access, missing synchronization
**Fix Strategy**: Add locks, use atomic operations, sequence properly

### Pattern 3: Memory Leak
**Symptoms**: Growing memory usage, eventual crash
**Common Causes**: Retained references, unclosed resources
**Fix Strategy**: Proper cleanup, weak references, resource pooling

### Pattern 4: Off-by-One Error
**Symptoms**: Missing last element, array index errors
**Common Causes**: Incorrect loop bounds, fence-post errors
**Fix Strategy**: Careful boundary analysis, inclusive/exclusive ranges

## Emergency Hotfix Protocol

If this is a production emergency:

1. **Immediate Mitigation**
   - Rollback if possible
   - Apply temporary workaround
   - Scale resources if needed

2. **Quick Fix**
   - Minimal change to stop bleeding
   - Focus on stability over perfection
   - Document as technical debt

3. **Proper Fix**
   - Schedule follow-up for complete solution
   - Add to backlog with high priority
   - Include lessons learned

Now analyzing the specific issue and applying this debugging protocol...
