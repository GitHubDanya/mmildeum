# GitHub Commit Message Conventions

The most widely adopted standard on GitHub is the **Conventional Commits** specification, typically paired with classic Git formatting guidelines like the **50/72 rule** and GitHub-specific issue-linking keywords.

## 1. Conventional Commits Structure

Conventional Commits provide a lightweight, machine-readable format that makes it easy to generate automated changelogs and determine semantic version bumps (SemVer).

**Format:**

```text
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

### Common Commit Types

| Type | Purpose | Example |
| :--- | :--- | :--- |
| **`feat`** | Introduces a new feature to the codebase | `feat(auth): add Google OAuth login` |
| **`fix`** | Patches a bug | `fix(api): handle null pointer on user lookup` |
| **`docs`** | Changes to documentation only | `docs: update installation instructions in README` |
| **`style`** | Formatting, missing semicolons, whitespace (no code logic change) | `style: format files with Prettier` |
| **`refactor`** | Code change that neither fixes a bug nor adds a feature | `refactor(cart): simplify tax calculation logic` |
| **`perf`** | Code change that improves performance | `perf(db): index user email column for faster queries` |
| **`test`** | Adding missing tests or correcting existing tests | `test: add unit tests for password validator` |
| **`build`** | Changes affecting the build system or external dependencies | `build: upgrade React to v19` |
| **`ci`** | Changes to CI configuration files and scripts | `ci: add GitHub Actions workflow for linting` |
| **`chore`** | Other changes that don't modify `src` or `test` files | `chore: update .gitignore` |
| **`revert`** | Reverts a previous commit | `revert: feat(auth): add Google OAuth login` |

* **Scopes:** Optional nouns in parentheses specifying the section of the codebase affected, such as `(ui)`, `(parser)`, or `(api)`.
* **Breaking Changes:** Indicated by adding an exclamation mark (`!`) before the colon (e.g., `feat!: drop support for Node 16`) or adding `BREAKING CHANGE:` in the footer.

## 2. Standard Git Formatting Rules

Even when not using Conventional Commits, most repositories follow these core formatting standards:

1. **Use the imperative mood:** Write the subject line as a command ("Add feature" rather than "Added feature" or "Adds feature"). A good test is completing the sentence: *"If applied, this commit will **[your subject line]**."*
2. **Follow the 50/72 rule:** Keep the subject line under **50 characters** so GitHub doesn't truncate it with an ellipsis (`...`), and wrap lines in the body at **72 characters** for readability in terminal logs.
3. **Separate subject from body with a blank line:** Git tools rely on this blank line to distinguish the title from the detailed description.
4. **Do not end the subject line with a period:** Save space and keep titles clean.
5. **Explain *what* and *why*, not *how*:** The code diff already shows *how* the change was made; use the commit body to explain the context, motivation, and side effects.

## 3. GitHub Issue-Closing Keywords

Including specific keywords followed by an issue number in the commit message (or pull request description) automatically closes the corresponding issue when the commit is merged into the default branch:

* `Closes #42`
* `Fixes #42`
* `Resolves #42`

### Complete Example

```text
fix(checkout): prevent duplicate charges on slow connections

Disable the submit button immediately upon the first click and add an 
idempotency key to the payment request payload. Previously, impatient 
users clicking multiple times triggered parallel API calls.

Closes #108
```