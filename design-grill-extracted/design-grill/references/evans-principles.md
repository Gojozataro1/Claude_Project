# Eric Evans — Domain-Driven Design Principles Reference

## The Core Philosophy

The central premise of DDD is that the **domain** — the subject area to which the software applies — should be the primary driver of design decisions. Not the database schema, not the framework, not the team org chart. The code should model the domain so faithfully that a domain expert could read it and say "yes, that is how our business works."

Software that fails to do this accumulates **accidental complexity**: a growing gap between how the domain works and how the code represents it. Over time this gap makes the system increasingly difficult to change, because every new requirement must be translated twice — once from domain terms into developer terms, and once from developer terms into code.

---

## Strategic Design

### Ubiquitous Language
The single most important practice in DDD. The team — developers and domain experts together — must develop a shared language for the domain, and that language must be used everywhere: in conversations, in documentation, in the code. When the code uses the same terms as the domain experts, there is no translation layer, and misunderstanding is minimized.

The language is **ubiquitous** — it appears everywhere. If a domain expert says "fulfill an order" and the code says `processTransaction()`, the gap is a bug waiting to happen.

**Grill question pattern:** "Can you read this class name and method name out loud to a domain expert and have them immediately understand what it does? If they'd need a translation, the language is not ubiquitous."

**Grill question pattern:** "When a domain concept changes its meaning — say, 'customer' starts meaning something different in the loyalty context versus the billing context — does that force you to change a single overloaded class? That's a language problem."

### Bounded Context
A Bounded Context is an explicit boundary within which a domain model applies. The same term can mean different things in different contexts — and that's fine, as long as the contexts are explicit and their boundaries are well-defined.

The classic example: "Customer" means something different to the Sales team (a prospect who signed) than to the Support team (someone with an active ticket) than to the Billing team (a payer with a payment method). Trying to force one `Customer` class to serve all three contexts produces an anemic, bloated monster.

**Each Bounded Context:**
- Has its own ubiquitous language
- Has its own model (its own set of classes, its own rules)
- Has an explicit interface for communicating with other contexts
- Is typically owned by one team

**Grill question pattern:** "Is 'Product' used in both the catalog context and the order context? What does it mean in each? Do they diverge? If yes, you may need two separate models with a translation layer between them."

### Context Map
A Context Map is a diagram or document that shows all the Bounded Contexts in a system and how they relate to each other. The relationships have names:

- **Shared Kernel:** Two contexts share a subset of the model. Changes require coordination.
- **Customer/Supplier:** One context is upstream (supplier), one is downstream (customer). The downstream depends on the upstream.
- **Conformist:** The downstream adopts the upstream model wholesale, rather than translating.
- **Anti-Corruption Layer (ACL):** A translation layer that protects a clean downstream model from the messiness of an upstream legacy system.
- **Open Host Service:** A well-documented API that multiple contexts can consume.
- **Published Language:** A shared, well-documented exchange format (e.g., an event schema).

**Grill question pattern:** "When your system talks to the legacy ERP, does your domain model speak the ERP's language? Or do you have a translation layer that protects your model? If you don't have an ACL, legacy concepts will leak into your clean domain."

---

## Tactical Design (The Building Blocks)

### Entities
An object defined primarily by its identity — it has continuity through time and across different states. Two Entities are the same if they have the same identity, regardless of attribute values. An `Order` is an entity: it has an ID, and even if every line item changes, it's still the same order.

**Key design rule:** Entities own their lifecycle. They should protect their own invariants. They are not just data containers.

**Grill question pattern:** "This object has an ID and persists over time — good, it's an Entity. But is it protecting its own state? Can external code reach in and set `order.status = "shipped"` without going through the Order's own methods? If so, the entity is an anemic data bag."

### Value Objects
An object defined entirely by its attributes, with no identity of its own. Two Value Objects are equal if their attributes are equal. A `Money(amount=100, currency="USD")` is interchangeable with any other `Money(100, "USD")`. Value Objects should be **immutable** — you don't change a value, you replace it.

Benefits: thread-safety, equality by value, no identity tracking overhead, expressiveness. Overusing Entities where Value Objects would suffice is a common design smell.

**Grill question pattern:** "Does 'Address' need an ID? Can you replace one `Address(street, city, zip)` with another that has the same values and nothing breaks? If yes — it should be a Value Object, not an Entity."

### Aggregates
An Aggregate is a cluster of Entities and Value Objects that are treated as a unit for the purpose of data changes. Each Aggregate has a **root Entity** (the Aggregate Root). The outside world can only reference the root — never the internal members directly. The root is responsible for enforcing all invariants that apply to the cluster.

**The key rule:** A transaction should not span multiple Aggregate boundaries. If you need to update two Aggregates in one transaction, you likely have the wrong Aggregate boundaries — or you need to use eventual consistency and domain events.

**Grill question pattern:** "Can the outside world directly access and modify an `OrderLineItem`, bypassing the `Order`? If yes, who enforces the invariant that an order's total is always consistent with its line items?"

**Grill question pattern:** "Are you updating two Aggregates in a single transaction? That's a strong signal your boundaries are wrong."

### Domain Events
Something that happened in the domain that the business cares about. Domain Events are the bridge between Aggregates — they allow one Aggregate to react to a change in another without creating a direct dependency. They are also the natural integration mechanism between Bounded Contexts.

Events are named in the past tense: `OrderPlaced`, `PaymentConfirmed`, `ItemShipped`. They capture what happened, who caused it, and when.

**Grill question pattern:** "When an order is placed, does the inventory system get updated by the Order directly calling the Inventory service? Or does the Order raise an `OrderPlaced` event and the Inventory context reacts? The first couples two contexts; the second keeps them independent."

### Repositories
A Repository provides the illusion that your Aggregates live in an in-memory collection. It hides all persistence concerns. Callers ask for an Aggregate by identity; the Repository fetches it, regardless of where it's actually stored.

Critical: Repositories are defined in the domain layer but implemented in the infrastructure layer. The interface belongs to the domain; the SQL implementation belongs to the infrastructure. This is DIP applied to persistence.

**Grill question pattern:** "Does your `OrderService` (domain) import `SqlOrderRepository` (infrastructure) directly? The domain should depend on an `OrderRepository` interface, and the infrastructure should implement it. Dependency direction: inward."

### Domain Services
Some operations are not natural responsibilities of any single Entity or Value Object. When the operation is significant in the domain but doesn't belong to an object, it belongs in a Domain Service. Domain Services are stateless. They operate on domain objects and use the ubiquitous language.

Do not confuse Domain Services with Application Services. Application Services orchestrate use cases and handle cross-cutting concerns (transactions, authorization). Domain Services contain domain logic.

**Grill question pattern:** "Is this service doing domain logic — applying business rules — or is it just orchestrating calls? If it's orchestration with no business logic, it may be an Application Service, not a Domain Service."

---

## The Distillation Principle

Not all parts of a domain are equally important. Evans identifies three types of subdomains:

- **Core Domain:** The part of the domain that gives the business its competitive advantage. This is where your best developers should spend most of their time. This is what you should build — not buy.
- **Supporting Subdomain:** Necessary for the business to function but not differentiating. Consider buying or using a simple solution.
- **Generic Subdomain:** Commodity functionality that has nothing to do with competitive advantage (authentication, email delivery, billing). Buy or use open source. Never build from scratch.

**Grill question pattern:** "You're spending weeks building a notification system from scratch. Is sending emails your competitive advantage? If not, why aren't you using an off-the-shelf service and spending those weeks on the Core Domain?"

---

## Evans' Test for a Good Domain Model

> "The model is the backbone of a language used by all team members. The model and the heart of the design shape each other."

A good domain model:
1. Reflects how the business actually works, not how a developer imagined it.
2. Uses the same vocabulary as domain experts.
3. Makes the implicit explicit — every business rule is visible in the model, not hidden in SQL or conditionals.
4. Allows new domain concepts to be added without surgery on existing code.
5. Makes complex operations simple to express in terms of the model.

When the model diverges from reality, the divergence is technical debt of the worst kind — it is conceptual debt, and it compounds faster than any other kind.
