Decide whether the customer's answer shows they understood the point.

They answered in their own words, so do not require the exact wording. Judge the
**concept**:

- Did they get the thing that matters? Then `correct: true`.
- Did they get it partly, or say something that happens to contain the right
  words without the meaning? Then `correct: false` with `missingConcept` naming
  what is absent.

Set `confidence` honestly. Below 0.6 the code will ask them to tap an option
instead of acting on your judgement, which is the right outcome when you are not
sure — telling someone they are wrong when they were right is worse than one
extra tap.

Reply with JSON only.
