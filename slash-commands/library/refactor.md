---
description: Systematic code refactoring with patterns, SOLID principles, and safety checks
argument-hint: "[file/module] [goal: performance|readability|maintainability]"
allowed-tools: Read, Write, Edit, MultiEdit, Bash, Grep
---

# Systematic Refactoring Protocol

Ultrathink about code structure, design patterns, and maintainability. Apply refactoring safely with test coverage.

## Refactoring Target

**Code to refactor**: $ARGUMENTS

Analyze arguments for:
- Specific files or modules
- Refactoring goals (performance, readability, maintainability)
- Constraints (backward compatibility, API stability)

## Pre-Refactoring Analysis

### 1. Safety Checks
```bash
# Ensure tests exist and pass
npm test || pytest || go test

# Check current test coverage
npm run coverage

# Create backup branch
git checkout -b refactor-backup-$(date +%Y%m%d)
```

### 2. Code Smell Detection

Identify issues to address:
- **Bloaters**: Long methods, large classes, long parameter lists
- **Object-Orientation Abusers**: Switch statements, refused bequest
- **Change Preventers**: Divergent change, shotgun surgery
- **Dispensables**: Lazy class, duplicate code, dead code
- **Couplers**: Feature envy, inappropriate intimacy, message chains

## Refactoring Catalog

### Method-Level Refactorings

#### Extract Method
```javascript
// Before: Long method
function processOrder(order) {
  // Validate order - 20 lines
  if (!order.id) throw new Error('Invalid');
  // ... more validation

  // Calculate pricing - 30 lines
  let total = 0;
  for (const item of order.items) {
    total += item.price * item.quantity;
  }
  // ... more calculations

  // Send notifications - 15 lines
  emailService.send(order.customer.email, 'Order confirmed');
  // ... more notifications
}

// After: Extracted methods
function processOrder(order) {
  validateOrder(order);
  const pricing = calculatePricing(order);
  sendOrderNotifications(order, pricing);
}

function validateOrder(order) {
  if (!order.id) throw new Error('Invalid order ID');
  // Focused validation logic
}

function calculatePricing(order) {
  return order.items.reduce(
    (total, item) => total + item.price * item.quantity,
    0
  );
}

function sendOrderNotifications(order, pricing) {
  emailService.send(order.customer.email, {
    subject: 'Order Confirmed',
    order,
    pricing
  });
}
```

### Class-Level Refactorings

#### Extract Class
```python
# Before: God class
class UserManager:
    def create_user(self, data): ...
    def update_user(self, id, data): ...
    def delete_user(self, id): ...
    def authenticate(self, credentials): ...
    def authorize(self, user, resource): ...
    def hash_password(self, password): ...
    def verify_password(self, password, hash): ...
    def send_welcome_email(self, user): ...
    def send_password_reset(self, user): ...

# After: Separated concerns
class UserRepository:
    def create(self, data): ...
    def update(self, id, data): ...
    def delete(self, id): ...

class AuthenticationService:
    def authenticate(self, credentials): ...
    def hash_password(self, password): ...
    def verify_password(self, password, hash): ...

class AuthorizationService:
    def authorize(self, user, resource): ...

class UserNotificationService:
    def send_welcome_email(self, user): ...
    def send_password_reset(self, user): ...
```

### Design Pattern Applications

#### Strategy Pattern
```javascript
// Before: Complex conditionals
function calculateShipping(order) {
  if (order.type === 'standard') {
    return order.weight * 0.5;
  } else if (order.type === 'express') {
    return order.weight * 1.5 + 10;
  } else if (order.type === 'overnight') {
    return order.weight * 3 + 25;
  }
}

// After: Strategy pattern
class ShippingStrategy {
  calculate(order) {
    throw new Error('Must implement calculate method');
  }
}

class StandardShipping extends ShippingStrategy {
  calculate(order) {
    return order.weight * 0.5;
  }
}

class ExpressShipping extends ShippingStrategy {
  calculate(order) {
    return order.weight * 1.5 + 10;
  }
}

class OvernightShipping extends ShippingStrategy {
  calculate(order) {
    return order.weight * 3 + 25;
  }
}

const strategies = {
  standard: new StandardShipping(),
  express: new ExpressShipping(),
  overnight: new OvernightShipping()
};

function calculateShipping(order) {
  return strategies[order.type].calculate(order);
}
```

## SOLID Principles Application

### Single Responsibility
```python
# Before: Multiple responsibilities
class Report:
    def gather_data(self): ...
    def process_data(self): ...
    def format_report(self): ...
    def save_to_file(self): ...
    def send_email(self): ...

# After: Single responsibility
class ReportDataGatherer:
    def gather_data(self): ...

class ReportProcessor:
    def process_data(self, data): ...

class ReportFormatter:
    def format(self, processed_data): ...

class ReportPersistence:
    def save(self, report): ...

class ReportDistribution:
    def send_email(self, report): ...
```

### Open/Closed Principle
```javascript
// Before: Modification required for new types
function drawShape(shape) {
  if (shape.type === 'circle') {
    drawCircle(shape);
  } else if (shape.type === 'square') {
    drawSquare(shape);
  }
  // Need to modify this function for new shapes
}

// After: Open for extension, closed for modification
class Shape {
  draw() {
    throw new Error('Must implement draw method');
  }
}

class Circle extends Shape {
  draw() {
    // Circle drawing logic
  }
}

class Square extends Shape {
  draw() {
    // Square drawing logic
  }
}

// Can add new shapes without modifying existing code
function drawShape(shape) {
  shape.draw();
}
```

## Refactoring Workflow

### Step 1: Identify Target
```bash
# Analyze complexity
radon cc -s *.py  # Python
eslint --report complexity  # JavaScript

# Find duplicates
jscpd --min-tokens 50 --reporters "console"
```

### Step 2: Write Characterization Tests
```javascript
// Before refactoring, capture current behavior
describe('Current Behavior', () => {
  it('should handle normal case', () => {
    const result = existingFunction(input);
    expect(result).toMatchSnapshot();
  });

  it('should handle edge case', () => {
    const result = existingFunction(edgeInput);
    expect(result).toMatchSnapshot();
  });
});
```

### Step 3: Refactor Incrementally
1. Make smallest possible change
2. Run tests
3. Commit if green
4. Repeat

### Step 4: Verify Improvements
```bash
# Re-measure complexity
radon cc -s *.py --min B

# Check test coverage
pytest --cov --cov-report=html

# Performance comparison
time python old_version.py
time python refactored_version.py
```

## Refactoring Checklist

### Before Starting
- [ ] Tests exist and pass
- [ ] Test coverage >70%
- [ ] Backup created
- [ ] Requirements understood

### During Refactoring
- [ ] One change at a time
- [ ] Tests run after each change
- [ ] Commits are atomic
- [ ] No behavior changes

### After Refactoring
- [ ] All tests pass
- [ ] Coverage maintained/improved
- [ ] Performance verified
- [ ] Code review completed
- [ ] Documentation updated

## Common Refactoring Patterns

### Replace Conditional with Polymorphism
### Extract Interface
### Replace Inheritance with Delegation
### Introduce Parameter Object
### Replace Magic Numbers with Constants
### Decompose Conditional
### Remove Dead Code
### Consolidate Duplicate Conditional Fragments

Now analyzing and refactoring the specified code...
