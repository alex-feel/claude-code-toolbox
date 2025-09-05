---
description: Comprehensive code review with security, performance, and quality analysis
argument-hint: "[file/PR/commit] [focus: security|performance|architecture]"
model: opus
---

# Comprehensive Code Review Protocol

Ultrathink systematically about code quality, security, performance, and architectural decisions. Provide constructive, actionable feedback.

## Review Target

**Code to review**: $ARGUMENTS

Parse arguments to identify:
- Specific files, PRs, or commits
- Review focus areas (security, performance, architecture)
- Context (new feature, bug fix, refactoring)

## Multi-Dimensional Review Framework

### 1. Security Review

#### Authentication & Authorization
- [ ] Proper authentication checks
- [ ] Authorization at appropriate levels
- [ ] Session management security
- [ ] Token validation and expiration

#### Input Validation & Sanitization
- [ ] All user inputs validated
- [ ] SQL injection prevention
- [ ] XSS protection
- [ ] Command injection prevention
- [ ] Path traversal protection

#### Data Protection
- [ ] Sensitive data encrypted
- [ ] No hardcoded secrets
- [ ] Secure communication (HTTPS/TLS)
- [ ] PII handling compliance

#### Security Best Practices
```bash
# Scan for common vulnerabilities
grep -r "eval\|exec\|system" --include="*.js" --include="*.py"
grep -r "password\|secret\|api_key" --exclude-dir=.git
```

### 2. Code Quality Review

#### Clean Code Principles
- **Readability**: Is the code self-documenting?
- **Simplicity**: Is there unnecessary complexity?
- **DRY**: Is there code duplication?
- **SOLID**: Are SOLID principles followed?
- **Naming**: Are names meaningful and consistent?

#### Code Smells to Check
- Long methods (>20 lines)
- Large classes (>300 lines)
- Too many parameters (>3-4)
- Deeply nested code (>3 levels)
- Magic numbers/strings
- Dead code
- Commented-out code

### 3. Performance Review

#### Algorithm Efficiency
- Time complexity analysis
- Space complexity considerations
- Optimal data structure choices
- Avoiding N+1 queries

#### Resource Management
- Memory leaks prevention
- Proper resource cleanup
- Connection pooling
- Caching strategies

#### Performance Patterns
```javascript
// ❌ Bad: Multiple DOM queries
for (let i = 0; i < items.length; i++) {
  document.getElementById('list').appendChild(items[i]);
}

// ✅ Good: Single DOM update
const fragment = document.createDocumentFragment();
items.forEach(item => fragment.appendChild(item));
document.getElementById('list').appendChild(fragment);
```

### 4. Architecture & Design Review

#### Design Patterns
- Appropriate pattern usage
- Over-engineering check
- Flexibility vs complexity balance
- Future extensibility

#### Dependencies
- Minimal coupling
- Clear interfaces
- Dependency injection
- Circular dependency check

### 5. Testing Review

#### Test Coverage
- Unit test presence
- Integration test coverage
- Edge cases covered
- Error scenarios tested

#### Test Quality
- Clear test names
- Single responsibility
- Proper assertions
- No flaky tests

## Review Checklist

### Critical Issues (Must Fix)
- [ ] Security vulnerabilities
- [ ] Data loss risks
- [ ] Breaking changes without migration
- [ ] Performance regressions
- [ ] Accessibility violations

### Major Issues (Should Fix)
- [ ] Poor error handling
- [ ] Missing tests
- [ ] Code duplication
- [ ] Incorrect abstractions
- [ ] Documentation gaps

### Minor Issues (Consider Fixing)
- [ ] Style inconsistencies
- [ ] Naming improvements
- [ ] Comment quality
- [ ] Minor optimizations

## Review Comments Format

### For Each Issue Found

```markdown
**[SEVERITY: Critical|Major|Minor]** - [Category: Security|Performance|Quality]

**File**: `path/to/file.js:42-45`

**Issue**: [Clear description of the problem]

**Impact**: [What could go wrong]

**Suggestion**:
```[language]
// Current code
[problematic code]

// Recommended fix
[improved code]
```

**Rationale**: [Why this change improves the code]
```markdown

## Positive Feedback

Also highlight good practices:
- Well-structured code
- Good test coverage
- Clear documentation
- Performance optimizations
- Security considerations

## Summary Template

```markdown
## Code Review Summary

**Overall Assessment**: [Approve|Request Changes|Comment]

### Statistics
- Files reviewed: X
- Lines of code: Y
- Test coverage: Z%

### Critical Issues: X
[List critical issues]

### Major Issues: Y
[List major issues]

### Minor Suggestions: Z
[List minor suggestions]

### Positive Highlights
[What was done well]

### Required Actions
1. [Must fix before merge]
2. [Should address]

### Recommended Follow-ups
- [Future improvements]
- [Technical debt to track]
```

Now performing comprehensive review of the specified code...
