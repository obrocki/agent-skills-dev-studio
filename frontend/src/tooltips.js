// Best-practice tooltip microcopy derived from the Agent Skills spec research.
// Wording is third person and concrete; shown via the title attribute.

export const NAME_HELP =
  'Name: 1-64 chars, lowercase a-z, 0-9 and hyphens. ' +
  'No leading, trailing, or consecutive hyphens. Matches the parent directory. ' +
  'Avoid: uppercase, prefixes, or reserved words.'

export const DESCRIPTION_HELP =
  'Description: state what the skill does AND when to use it, plus trigger keywords (<=1024 chars). ' +
  'Write in third person ("Extracts...", "Use when..."). ' +
  'Avoid: vague text, duplicating model knowledge, first/second person ("I can help").'

export const CONTENT_HELP =
  'Body: plain Markdown with clear headings, steps, and examples. ' +
  'Keep concise (<500 lines); add only context the model lacks. ' +
  'Avoid: duplicating common knowledge or burying many alternatives.'

export const NAME_PLACEHOLDER = 'extract-pdf-tables'

export const DESCRIPTION_PLACEHOLDER =
  'Extract text and tables from PDF files and fill forms. Use when working with PDFs, forms, or document extraction.'

export const CONTENT_PLACEHOLDER = '# Skill body\n\nDescribe steps, examples, and guardrails in Markdown.'

export const CODE_HELP =
  'Python code (optional): runs as an agent tool when the skill is invoked. ' +
  'It receives a JSON object on stdin with "time_zone", "locale", and "user_input", ' +
  'and should print its result to stdout.'

export const CODE_PLACEHOLDER =
  'import sys, json\ndata = json.load(sys.stdin)\nprint(data["user_input"])'
