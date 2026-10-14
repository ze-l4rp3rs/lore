# Tools

## Contract

- **A tool is a function plus a description of its parameters.** The model sees the description. Tools
  are discovered automatically.
- **A tool returns evidence items.** Each item becomes its own citable source. Any other result becomes a
  single source holding the whole result.
- **A tool reports failure by failing.** The loop tells the model about the error and records it, but an
  error never becomes a citable source.
- **Graph queries are read-only and parameterised:** text from the user or the model is never inserted
  into a query.
- **A user identity,** if a tool needs one, is supplied by the system, never by the model. The tool must
  return only what that user may see.

## Turning graph records into evidence

| Record | Shown as | Label | Text (what quotes are checked against) |
|---|---|---|---|
| Document | document | title | its content |
| Chat message | chat | channel | the message text; the author is shown beside it, not inside it |
| Ticket | ticket | key and title | description, status, resolution, blocker |
| Decision | decision | key and title | description, rationale, impact, status |
| Change | change | entity and field | "field changed from A to B on date by person, with the reason" |
| Project or person | project / person | name | a short summary |

- Each evidence item's reference is the record's identity, so references are stable.
- Each item carries a current or superseded status from the record's current flag.

A role statement ("this person is the owner of that project") is also evidence. Its reference combines
the role, the person and the entity, so two owners stay two sources.

## The tools

**General graph search**
- Accepts a natural-language request or a read-only graph query.
- Queries are recognised first. Any query that would change data is rejected, and queries run in
  read-only mode anyway.
- Natural language is matched on whole words to a fixed set of query shapes: owners, people involved,
  lists by type, and keyword search.
- Whole records become typed evidence; other result rows get one source each. Results are capped, and the
  result says when more matched.

**Ownership lookup**
- Formal responsibility as recorded now: a project's owner and sponsor (or a team's lead, a ticket's
  assignee, a document's author, a decision's approver).
- When the request names something exactly, only that record is used.

**Expertise lookup**
- Ranks people by evidence of involvement with a topic and with everything one step from it.
- Weights: owner or sponsor 3, approver 3, dissenter 2, author 2, assignee or reporter 2, each chat
  message 1, each recorded change 1 (at most five messages and five changes count per person).
- Recent activity counts more, measured from the topic's latest activity, not today's date: full weight
  within 30 days, three quarters within 90, half after that.
- Each result lists the items behind the score.

**Decision tracing**
- Finds a decision by identity, key or title.
- Returns the decision, its approver, its chain of overrides, reversals and supersessions (both
  directions), and the documents and messages it rests on (at most twelve, oldest first). It also returns
  each dissenter with the messages that show the dissent.
- If several decisions match and none exactly, it returns the top three and says so.

**Timeline**
- The recorded changes to the best-matching project or ticket, oldest first, optionally for one field,
  with people shown by name.
- Optionally, each field's value on a given date, computed from the changes.

**Follow-up drafting**
- Drafts a message or ticket for a named person. It checks the person exists and **executes nothing**.
- Each draft is returned with the response as a proposed action, with the sources that justify it, for a
  person to confirm.

**Current time**
- Returns the current time.

## Adding a tool

1. Write the function and have it return evidence. Use the standard conversion for graph records.
2. Write its description, saying clearly **when** to use it instead of similar tools.
3. Register it, and add one line about it to the generator's instructions.
4. Test it with a simulated graph client:
   - its queries are parameterised;
   - its evidence text and references are right;
   - failures fail.
