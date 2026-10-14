# Answer pipeline

```
question ─► generator (+ tools) ─► repair citations ─► automatic checks ─► reviewer ─┐
                ▲                                                                      │
                └──────────── fix request (only the problems) ◄── problems? ◄──────────┘
                                                   │ none, or rounds used up
                                                   ▼
                          best draft ─► remove unsupported sentences ─► number citations ─► result
```

## 1. Generator

**Instructions**
- the data model;
- core rules;
- conflict rules;
- the available tools;
- the working order: query first, extract facts, cite, answer.

**Input:** the sources, each with its run identifier, and the question, separated by clear structural
markers.

**Citations:** every fact is followed by a citation naming the source and quoting its exact words. An
ellipsis may skip words inside a quote.

**Gaps:** anything the records do not contain is listed under a fixed "not in company records" heading.

**Ordering:** text written alongside a tool request is discarded. The whole answer must be written after
the tool results arrive.

## 2. Automatic checks (no model)

In this order:
1. **Repair.**
   - A citation with a missing bracket is closed.
   - A quote that is not in its source is replaced by the most similar passage of about the same length,
     if they are at least 90% similar.
2. **Split.** The answer is split into lines and numbered sentences. Bullets and headings are kept.
   Quotes, abbreviations and initials never end a sentence.
3. **Sentence checks.** Each sentence is flagged for:
   - a citation of an unknown source;
   - a citation without a quote, or a quote that is not in its source;
   - a factual sentence with no citation;
   - a source written as plain text or as a fake link;
   - leaked reasoning.

   Headings and statements of missing information need no citation.

Quote matching forgives letter case, spacing and typographic quotes and dashes, **and nothing else**.

## 3. Reviewer

**Input**
- the same sources (now including every tool result);
- a trace of which tool, with which arguments, produced which sources or errors;
- the draft with numbered sentences.

**Constraints:** the reviewer cannot use tools. If it tries, the draft is marked "not checked".

**Output:** a structured verdict for each sentence (supported or not, and why), plus the parts of the
question the sources do not answer and any false premises left uncorrected. Extra text around the verdict
is tolerated, and it gets one retry if the verdict is unusable.

**Strictness**
- A sentence the reviewer does not judge counts as unconfirmed.
- A sentence that states a superseded fact as current is unsupported.

## 4. Fix rounds

The generator's own conversation, tool exchanges included, continues with a request to fix only the
listed problems and copy every other sentence word for word. The list includes unanswered parts and
uncorrected premises.

The number of rounds is limited. The loop stops early when a draft is clean or its review is unusable.

## 5. Choosing the result

**Score:** whether the draft was reviewed, then the number of problem sentences, then unanswered parts
plus false premises. Lower is better, and the best draft wins, not the latest.

**Removal:** sentences with problems are removed and listed with a plain-language reason. If nothing
verifiable remains, the answer is a fixed "couldn't find a verifiable answer" message.

**Status**
- **verified;**
- **partly verified:** something was removed, is missing, or the question had a false premise;
- **not checked:** the review failed.

**Rendering:** citations become numbered footnotes in order of first use. The source list shows each
source's type, label, date and quoted passages.

## Freshness and conflict rules (given to the model)

1. Prefer the latest decision that has not been superseded, then recorded change history, then
   documents, then tickets, then chat.
2. When sources disagree, say so, and say which one wins and why.
3. If only superseded sources answer the question, say so.
4. If a document's figure differs from the latest recorded change, treat the document as out of date.
5. Never state a superseded fact as current.

Structure marks what has been superseded; the model judges whether content is stale.
