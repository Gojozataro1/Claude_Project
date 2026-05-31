# Robert C. Martin — Core Principles Reference

## The SOLID Principles

### S — Single Responsibility Principle (SRP)
A module should have one, and only one, reason to change. More precisely: a module should be responsible to one, and only one, actor. "Actor" means a person or group of people who share a common need that drives change. When two actors share a module, a change for one risks breaking something for the other. The smell is a class or module that knows too much — it reaches into persistence, business logic, and presentation all at once.

**Grill question pattern:** "If the UI team wants to change how this is displayed, does that touch the same class that the billing team would need to change to update pricing logic? If yes — that class has multiple reasons to change."

### O — Open/Closed Principle (OCP)
A software artifact should be open for extension but closed for modification. The goal is to protect high-level components from changes in lower-level ones. When new behavior is needed, the design should accommodate it by adding new code, not by rewriting existing code. This is achieved through abstraction — defining stable interfaces that higher-level policies depend on, so that new implementations can be swapped in without touching the policy.

**Grill question pattern:** "If we add a new payment provider next year, which files change? If the answer is 'the PaymentService class itself' rather than 'we add a new class that implements the PaymentProvider interface', the OCP is violated."

### L — Liskov Substitution Principle (LSP)
Subtypes must be substitutable for their base types without breaking the correctness of the program. This is not just a rule about inheritance — it's a contract rule. If a caller is written against an abstraction, any concrete implementation must honor the behavioral contract implied by that abstraction. Violations produce fragile code: callers start checking types, adding `instanceof` guards, or breaking in unexpected ways.

**Grill question pattern:** "If I replace this concrete class with any other implementation of its interface, should the callers' behavior remain correct? If not, the abstraction is a lie."

### I — Interface Segregation Principle (ISP)
No client should be forced to depend on methods it does not use. Fat interfaces create harmful couplings. When a client implements or depends on an interface that has methods it doesn't need, it becomes coupled to changes in those methods even though it doesn't care about them. Prefer many narrow interfaces over a single wide one.

**Grill question pattern:** "Does this interface have methods that half the implementors will throw `NotImplementedException` on? If yes, split it."

### D — Dependency Inversion Principle (DIP)
High-level policy should not depend on low-level detail. Both should depend on abstractions. Abstractions should not depend on details — details should depend on abstractions. In practice: your business logic should not import your database layer. Your use cases should not import your HTTP framework. The arrows of dependency should point inward, toward the domain.

**Grill question pattern:** "Does the Order class import anything from the persistence package? Does the checkout service know that payment is done by Stripe? If yes — the dependency is inverted in the wrong direction."

---

## Clean Architecture

### The Dependency Rule
Source code dependencies must point only inward — toward higher-level policies. Nothing in an inner circle can know about something in an outer circle. The outer rings are mechanisms (frameworks, databases, UI, external services). The inner rings are policy (use cases, entities, domain logic). This boundary protects the business from technological churn.

**Layers (inside out):**
1. **Entities** — enterprise-wide business rules. Pure domain objects. No frameworks, no I/O.
2. **Use Cases** — application-specific business rules. Orchestrate entities to fulfill user goals.
3. **Interface Adapters** — convert data between use cases and external formats (controllers, presenters, gateways).
4. **Frameworks & Drivers** — the web framework, the database, the UI. The outermost ring. Plug-in, replaceable.

**Grill question pattern:** "Can you run your business logic — your core use cases — without a database, without HTTP, without a message broker? If not, the dependency rule is being violated somewhere."

### Screaming Architecture
The top-level structure of a system should scream its purpose, not its mechanism. A project structure that reveals `controllers/`, `models/`, `views/` is screaming "Rails app." A project that reveals `orders/`, `fulfillment/`, `billing/` is screaming "e-commerce." The architecture should be about the domain, not the delivery mechanism.

**Grill question pattern:** "If I look at the top-level folders of this codebase, do I understand the business it supports? Or do I just see a framework's folder convention?"

---

## Component Principles

### Cohesion
- **REP (Reuse/Release Equivalence Principle):** Group things that are released together.
- **CCP (Common Closure Principle):** Group things that change together. If two classes change for the same reason at the same time, they belong in the same component.
- **CRP (Common Reuse Principle):** Don't force users of a component to depend on things they don't need.

### Coupling
- **ADP (Acyclic Dependencies Principle):** No cycles in the dependency graph between components. Cycles make it impossible to understand what depends on what.
- **SDP (Stable Dependencies Principle):** Depend in the direction of stability. Unstable components (volatile, frequently changing) should not be depended upon by stable ones.
- **SAP (Stable Abstractions Principle):** Stable components should be abstract. The more stable something is, the more abstract it should be — because abstractions are the mechanism by which extension is possible without modification.

---

## Clean Code Principles (The Craft)

- **Names reveal intent.** If a name requires a comment to explain it, it has failed.
- **Functions do one thing.** If a function does something and *also* does something else, extract.
- **No side effects.** A function that claims to calculate something should not secretly change state.
- **Command/Query Separation.** A function either changes state OR returns a value. Never both.
- **DRY (Don't Repeat Yourself).** Duplication is the root of all evil in software. Every piece of knowledge should have a single, authoritative representation.
- **The Boy Scout Rule.** Leave the code cleaner than you found it.
- **Prefer exceptions to error codes.** Error codes require immediate handling and pollute call sites. Exceptions can be handled at the right level.

---

## Martin's Definition of Good Design

> "The goal of software architecture is to minimize the human resources required to build and maintain the required system."

A design is good if it makes change easy. A design is bad if it makes change expensive. Every principle is ultimately in service of this: protecting the system's ability to accommodate new requirements without disproportionate cost.

The enemy of good design is not complexity per se — it is **accidental complexity**: complexity that arises from poor coupling, poor separation of concerns, and dependencies that flow in the wrong direction.
