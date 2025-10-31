I am internationalizing this project. I need you to go through all the added `.html` (or Jinja/template) files and wrap **only user-visible, static text** with the translation function `{{ _('...') }}`.

Follow these **strict rules**:

1.  **Wrap Text Content:** Wrap text that appears directly between HTML tags.
    * If text spans multiple lines, treat it as a single logical string. Wrap the entire block and preserve its internal line breaks and indentation. (See Example 6).
2.  **Wrap Specific Attributes:** Wrap text in these attribute values: `title`, `placeholder`, `alt`, `aria-label`, and `label`. You may also wrap `data-*` attributes *only if* they clearly contain user-visible text.
    * If an attribute value spans multiple lines, treat it as one logical string; wrap the entire value once.
3.  **Handle Mixed Content (Preference):** If static text is mixed with template variables, the **preferred method** is to keep the entire phrase together using parameterized translations. Use gettext-style Python formatting (`%(var)s`) for placeholders. (See Example 3).
4.  **Handle Mixed Content (Fallback):** If parameterization is not possible, wrap *only* the static parts, leaving the variables untouched. (See Example 3, Alternative).
5.  **Handle Child Tags:** If text contains child tags that are purely for *formatting* (like `<strong>`, `<em>`, `<span>`, `<br>`), wrap the entire content *including the tags* as a single translatable unit. This preserves context for translators. (See Example 4).

---

**Do NOT Wrap (Exclusions):**

* Text *already* inside `{{ ... }}` or `{% ... %}` blocks (e.g., variables, logic).
* Text that is *already* wrapped in a translation call (e.g., `_('...')`, `gettext(...)`).
* Text that contains partially translated segments (to avoid nested translation calls).
* Whitespace-only or empty strings.
* Standalone punctuation-only content (like `<span>!</span>` or `<td>,</td>`).
* Standalone HTML entities (like a lone `&nbsp;`), but **DO** wrap text that contains entities as part of a larger string (See Example 5).
* Text inside `<script>`, `<style>`, or HTML comment (`<!-- -->`) blocks.
* **URL paths, routes, or file paths** in `href`, `src`, `action` attributes (wrap only the visible link text, not the URL itself).
* Numeric values that appear to be data rather than prose (like IDs, counts, or raw timestamps), unless they are clearly part of a sentence.

---

**Preservation:**

* Preserve all original indentation, surrounding whitespace, and spacing.
* Preserve original attribute quotes (single vs. double). The `{{ _('...') }}` call must go *inside* the existing quotes.
* When text contains quotes, use the opposite quote style for the outer wrapper (e.g., `{{ _('He said "Hi"') }}` or `{{ _("It's fine") }}`).
* If a literal `%` appears in text, escape it as `%%` inside the translation string to avoid placeholder conflicts.
* If literal `<` or `>` characters (not HTML tags) appear in text, preserve them.
* Maintain valid HTML and Jinja syntax at all times.

---

**Special Case: Mixed Attribute Content**

If an attribute mixes variables and text, separate them carefully:
* **From:** `title="{{ user.role }} account"`
* **To:** `title="{{ user.role }} {{ _('account') }}"` *(Note: This separation is a fallback. A parameterized approach is better if the template system supports it.)*

---

**Examples:**

**Example 1: Basic Tag Content**
* **From:** `<h1>Hello World</h1>`
* **To:** `<h1>{{ _('Hello World') }}</h1>`

**Example 2: Basic Attribute Content**
* **From:** `<input type="text" placeholder="Your Name">`
* **To:** `<input type="text" placeholder="{{ _('Your Name') }}">`

**Example 3: Mixed Static and Variable Content**
* **From:** `<p>Hello {{ user.name }}, welcome!</p>`
* **PREFERRED To:** `<p>{{ _('Hello %(name)s, welcome!', name=user.name) }}</p>`
* **Alternative To:** `<p>{{ _('Hello') }} {{ user.name }}{{ _(', welcome!') }}</p>`

**Example 4: Text with Formatting Tags**
* **From:** `<p>Welcome back, <strong>dear user</strong>!</p>`
* **To:** `<p>{{ _('Welcome back, <strong>dear user</strong>!') }}</p>`

**Example 5: Text with HTML Entity**
* **From:** `<p>Copyright &copy; 2024 My Company</p>`
* **To:** `<p>{{ _('Copyright &copy; 2024 My Company') }}</p>`

**Example 6: Multi-line Text**
* **From:**
```html
    <p>
        This is a longer paragraph
        that spans multiple lines.
    </p>
```
* **To:**
```html
    <p>{{ _('This is a longer paragraph
        that spans multiple lines.') }}</p>
```

**Example 7: IGNORE - Already a Variable**
* **From:** `<p>{{ user.name }}</p>`
* **To:** `<p>{{ user.name }}</p>` (No change)

**Example 8: IGNORE - Already Translated**
* **From:** `<p>{{ _('Already translated') }}</p>`
* **To:** `<p>{{ _('Already translated') }}</p>` (No change)

---

**Final Instruction:**
Apply these rules consistently across all added files. **Prefer the parameterized translation method (Example 3) when possible.**

If you encounter an ambiguous case, apply your best judgment based on these rules and flag it in your summary for review. After processing, provide a concise summary of changes made and any edge cases or uncertainties that require attention.
