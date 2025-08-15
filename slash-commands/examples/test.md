---
description: Comprehensive test generation following TDD principles with coverage analysis
argument-hint: "[file/module/feature] [test-type: unit|integration|e2e] [coverage-target]"
allowed-tools: Read, Write, Edit, MultiEdit, Bash, Grep
---

# Comprehensive Testing Strategy

Ultrathink about the testing requirements, considering the testing pyramid, coverage goals, and the specific needs of the code. Apply Test-Driven Development (TDD) principles where applicable.

## Test Request Analysis

**Testing target**: $ARGUMENTS

Parse arguments to determine:
- Specific files, modules, or features to test
- Test type preference (unit, integration, e2e, performance)
- Coverage targets (e.g., 80%, 90%, 100%)
- Special requirements (mocking, fixtures, async testing)
- Framework preferences

## Test-Driven Development (TDD) Workflow

### Step 1: Understand Requirements

Before writing any tests, thoroughly understand:
1. **Functional Requirements**: What should the code do?
2. **Non-functional Requirements**: Performance, security, scalability
3. **Edge Cases**: Boundary conditions, error scenarios
4. **Integration Points**: External dependencies, APIs

### Step 2: Test Planning

#### Testing Pyramid Strategy
```text
        /\
       /e2e\      (5-10%) - Critical user journeys
      /------\
     /integr. \   (20-30%) - Component interactions
    /----------\
   /   unit     \ (60-70%) - Individual functions/methods
  /______________\
```

#### Test Categories to Create

1. **Unit Tests** - Isolated function/method testing
2. **Integration Tests** - Component interaction testing
3. **End-to-End Tests** - Full workflow validation
4. **Performance Tests** - Load and stress testing
5. **Security Tests** - Vulnerability scanning
6. **Accessibility Tests** - A11y compliance

### Step 3: Framework Detection

```bash
# Detect testing framework
if [ -f "package.json" ]; then
  # JavaScript/TypeScript project
  grep -E "jest|mocha|vitest|jasmine" package.json
  FRAMEWORK="detected_framework"
elif [ -f "requirements.txt" ] || [ -f "pyproject.toml" ]; then
  # Python project
  grep -E "pytest|unittest|nose" requirements.txt pyproject.toml
  FRAMEWORK="pytest"  # Default to pytest
elif [ -f "go.mod" ]; then
  # Go project
  FRAMEWORK="go test"
elif [ -f "Cargo.toml" ]; then
  # Rust project
  FRAMEWORK="cargo test"
fi
```

## Comprehensive Test Generation

### Phase 1: Unit Test Creation

#### 1.1 Test File Structure
```javascript
// tests/unit/[module].test.js
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { functionToTest } from '../src/module';

describe('Module Name', () => {
  describe('functionToTest', () => {
    // Setup and teardown
    beforeEach(() => {
      // Reset state, create fixtures
    });

    afterEach(() => {
      // Cleanup
    });

    // Happy path tests
    describe('Happy Path', () => {
      it('should handle normal input correctly', () => {
        // Arrange
        const input = 'valid input';
        const expected = 'expected output';

        // Act
        const result = functionToTest(input);

        // Assert
        expect(result).toBe(expected);
      });
    });

    // Edge cases
    describe('Edge Cases', () => {
      it('should handle empty input', () => {
        expect(functionToTest('')).toBe('');
      });

      it('should handle null input', () => {
        expect(() => functionToTest(null)).toThrow('Input cannot be null');
      });

      it('should handle maximum size input', () => {
        const largeInput = 'x'.repeat(10000);
        expect(() => functionToTest(largeInput)).not.toThrow();
      });
    });

    // Error conditions
    describe('Error Handling', () => {
      it('should throw on invalid type', () => {
        expect(() => functionToTest(123)).toThrow(TypeError);
      });

      it('should handle network timeouts gracefully', async () => {
        jest.setTimeout(100);
        await expect(functionWithTimeout()).rejects.toThrow('Timeout');
      });
    });
  });
});
```

#### 1.2 Parameterized Testing
```python
import pytest

@pytest.mark.parametrize("input,expected", [
    ("hello", "HELLO"),
    ("world", "WORLD"),
    ("123", "123"),
    ("", ""),
    (" spaces ", " SPACES "),
])
def test_uppercase_conversion(input, expected):
    """Test uppercase conversion with various inputs"""
    assert to_uppercase(input) == expected

@pytest.mark.parametrize("invalid_input", [
    None,
    123,
    [],
    {},
])
def test_uppercase_invalid_types(invalid_input):
    """Test that invalid types raise TypeError"""
    with pytest.raises(TypeError):
        to_uppercase(invalid_input)
```

### Phase 2: Integration Testing

#### 2.1 API Integration Tests
```javascript
// tests/integration/api.test.js
describe('API Integration', () => {
  let server;
  let database;

  beforeAll(async () => {
    // Start test server
    server = await startTestServer();
    // Connect to test database
    database = await connectTestDb();
  });

  afterAll(async () => {
    await server.close();
    await database.disconnect();
  });

  describe('POST /api/users', () => {
    it('should create a new user', async () => {
      const userData = {
        name: 'Test User',
        email: 'test@example.com'
      };

      const response = await request(server)
        .post('/api/users')
        .send(userData)
        .expect(201);

      expect(response.body).toMatchObject({
        id: expect.any(String),
        ...userData
      });

      // Verify database persistence
      const dbUser = await database.users.findById(response.body.id);
      expect(dbUser).toBeDefined();
    });

    it('should handle duplicate emails', async () => {
      const userData = {
        name: 'Duplicate User',
        email: 'existing@example.com'
      };

      // Create first user
      await request(server)
        .post('/api/users')
        .send(userData)
        .expect(201);

      // Attempt duplicate
      const response = await request(server)
        .post('/api/users')
        .send(userData)
        .expect(409);

      expect(response.body.error).toContain('Email already exists');
    });
  });
});
```

#### 2.2 Database Integration Tests
```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

@pytest.fixture
def test_db():
    """Create a test database session"""
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    yield session

    session.close()
    Base.metadata.drop_all(engine)

def test_user_creation(test_db):
    """Test creating a user in the database"""
    user = User(name="Test User", email="test@example.com")
    test_db.add(user)
    test_db.commit()

    retrieved = test_db.query(User).filter_by(email="test@example.com").first()
    assert retrieved is not None
    assert retrieved.name == "Test User"

def test_cascade_delete(test_db):
    """Test that deleting a user cascades to related records"""
    user = User(name="Test User", email="test@example.com")
    post = Post(title="Test Post", user=user)
    test_db.add_all([user, post])
    test_db.commit()

    test_db.delete(user)
    test_db.commit()

    assert test_db.query(Post).count() == 0
```

### Phase 3: End-to-End Testing

#### 3.1 Browser Automation Tests
```javascript
// tests/e2e/user-flow.test.js
import { test, expect } from '@playwright/test';

test.describe('User Registration Flow', () => {
  test('should complete full registration process', async ({ page }) => {
    // Navigate to registration page
    await page.goto('/register');

    // Fill registration form
    await page.fill('[data-testid="name-input"]', 'John Doe');
    await page.fill('[data-testid="email-input"]', 'john@example.com');
    await page.fill('[data-testid="password-input"]', 'SecurePass123!');
    await page.fill('[data-testid="confirm-password"]', 'SecurePass123!');

    // Accept terms
    await page.check('[data-testid="terms-checkbox"]');

    // Submit form
    await page.click('[data-testid="submit-button"]');

    // Verify email verification page
    await expect(page).toHaveURL('/verify-email');
    await expect(page.locator('h1')).toContainText('Verify Your Email');

    // Simulate email verification (in test mode)
    await page.goto('/verify-email?token=test-token');

    // Should redirect to dashboard
    await expect(page).toHaveURL('/dashboard');
    await expect(page.locator('[data-testid="welcome-message"]'))
      .toContainText('Welcome, John Doe');
  });

  test('should show validation errors', async ({ page }) => {
    await page.goto('/register');

    // Submit empty form
    await page.click('[data-testid="submit-button"]');

    // Check validation messages
    await expect(page.locator('[data-testid="name-error"]'))
      .toContainText('Name is required');
    await expect(page.locator('[data-testid="email-error"]'))
      .toContainText('Email is required');
    await expect(page.locator('[data-testid="password-error"]'))
      .toContainText('Password is required');
  });
});
```

### Phase 4: Test Utilities & Helpers

#### 4.1 Mock Factories
```javascript
// tests/factories/user.factory.js
import { faker } from '@faker-js/faker';

export const createMockUser = (overrides = {}) => ({
  id: faker.string.uuid(),
  name: faker.person.fullName(),
  email: faker.internet.email(),
  createdAt: faker.date.past(),
  ...overrides
});

export const createMockUsers = (count = 10, overrides = {}) =>
  Array.from({ length: count }, () => createMockUser(overrides));
```

#### 4.2 Custom Assertions
```python
# tests/assertions.py
def assert_valid_email(email):
    """Custom assertion for email validation"""
    import re
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    assert re.match(pattern, email), f"Invalid email format: {email}"

def assert_within_range(value, min_val, max_val):
    """Assert value is within specified range"""
    assert min_val <= value <= max_val, \
        f"Value {value} not in range [{min_val}, {max_val}]"

def assert_performance(func, max_time=1.0):
    """Assert function executes within time limit"""
    import time
    start = time.time()
    func()
    duration = time.time() - start
    assert duration < max_time, \
        f"Function took {duration:.2f}s, exceeding {max_time}s limit"
```

### Phase 5: Coverage Analysis

#### 5.1 Coverage Configuration
```javascript
// vitest.config.js or jest.config.js
export default {
  test: {
    coverage: {
      enabled: true,
      reporter: ['text', 'lcov', 'html'],
      exclude: [
        'node_modules/',
        'tests/',
        '*.config.js',
        'dist/'
      ],
      thresholds: {
        statements: 80,
        branches: 75,
        functions: 80,
        lines: 80
      }
    }
  }
};
```

#### 5.2 Coverage Commands
```bash
# Run tests with coverage
npm run test:coverage

# Generate coverage report
nyc report --reporter=html

# Check coverage thresholds
nyc check-coverage --lines 80 --functions 80 --branches 75

# Find uncovered lines
grep -n "0x" coverage/lcov.info | head -20
```

### Phase 6: Performance Testing

```javascript
// tests/performance/load.test.js
import { check } from 'k6';
import http from 'k6/http';

export const options = {
  stages: [
    { duration: '2m', target: 100 }, // Ramp up to 100 users
    { duration: '5m', target: 100 }, // Stay at 100 users
    { duration: '2m', target: 0 },   // Ramp down to 0 users
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'], // 95% of requests under 500ms
    http_req_failed: ['rate<0.1'],    // Error rate under 10%
  },
};

export default function () {
  const response = http.get('https://api.example.com/endpoint');

  check(response, {
    'status is 200': (r) => r.status === 200,
    'response time < 500ms': (r) => r.timings.duration < 500,
    'body contains expected data': (r) => r.body.includes('expected'),
  });
}
```

## Test Execution Strategy

### Running Tests
```bash
# Run all tests
npm test

# Run specific test type
npm run test:unit
npm run test:integration
npm run test:e2e

# Run tests in watch mode
npm test -- --watch

# Run tests with debugging
node --inspect-brk ./node_modules/.bin/jest --runInBand

# Run specific test file
npm test -- user.test.js

# Run tests matching pattern
npm test -- --grep "should create"
```

### Continuous Testing
```yaml
# .github/workflows/test.yml
name: Test Suite
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        node-version: [16, 18, 20]

    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: ${{ matrix.node-version }}

      - run: npm ci
      - run: npm run test:unit
      - run: npm run test:integration
      - run: npm run test:e2e

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage/lcov.info
```

## Test Documentation

### Test Plan Template
```markdown
# Test Plan: [Feature Name]

## Scope
- Components to test: [List]
- Out of scope: [List]

## Test Scenarios
1. **Scenario**: [Description]
   - **Given**: [Preconditions]
   - **When**: [Actions]
   - **Then**: [Expected results]

## Test Data
- Valid inputs: [Examples]
- Invalid inputs: [Examples]
- Edge cases: [Examples]

## Dependencies
- External services: [List]
- Test data setup: [Requirements]

## Risk Assessment
- High risk areas: [List]
- Mitigation strategies: [List]
```

## Testing Best Practices Checklist

- [ ] Tests are independent and can run in any order
- [ ] Each test has a single clear purpose
- [ ] Test names clearly describe what is being tested
- [ ] AAA pattern (Arrange, Act, Assert) is followed
- [ ] Appropriate use of beforeEach/afterEach for setup/teardown
- [ ] Mocks are properly reset between tests
- [ ] No hardcoded values (use constants or factories)
- [ ] Tests cover happy path, edge cases, and error conditions
- [ ] Performance-critical code has benchmark tests
- [ ] Security-sensitive code has security tests
- [ ] Accessibility requirements have a11y tests
- [ ] Integration points have contract tests
- [ ] Coverage meets project thresholds
- [ ] Tests run in CI/CD pipeline
- [ ] Flaky tests are identified and fixed

Now generating comprehensive tests for the specified target...
