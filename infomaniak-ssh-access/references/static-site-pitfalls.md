# Static Site CSS Pitfalls (aqfinea.net session)

## 1. Fixed Hero Canvas + `.main-content` Wrapper

When using a fixed `<canvas>` background with `position: fixed; z-index: 0`, ALL content after the hero MUST be inside a wrapper with `position: relative; z-index: 2; background: <solid>`.

**Pitfall:** If `.main-content` closes before the footer, sections outside it will be transparent — the fixed canvas shows through, causing flashing particles and unreadable text.

**Fix:** Keep `.main-content` open until after the last non-footer section:
```html
<div class="main-content">   <!-- opens after hero -->
  <section>...</section>      <!-- has bg via z-index:2 -->
  <section>...</section>
  <!-- do NOT close here -->
</div>                        <!-- closes before footer -->
<footer>...</footer>
```

## 2. prefers-reduced-motion for Canvas Animations

Always gate canvas animations:
```js
if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
  canvas.style.display = 'none';
  return;
}
```

## 3. Email Obfuscation + noscript Fallback

```html
<a class="obfuscated-email" data-user="contact" data-domain="aqfinea.net"></a>
<noscript><a href="mailto:contact@aqfinea.net">contact@aqfinea.net</a></noscript>
```

Without noscript, JS-disabled browsers see nothing.

## 4. Formspree AJAX CDN Pattern

```html
<div data-fs-success></div>
<div data-fs-error></div>
<form id="contact-form">
  <input name="email" data-fs-field required>
  <span data-fs-error="email"></span>
  <button data-fs-submit-btn>Send</button>
</form>
<script>
window.formspree = window.formspree || function(){
  (formspree.q = formspree.q || []).push(arguments);
};
formspree('initForm', { formElement: '#contact-form', formId: 'YOUR_ID' });
</script>
<script src="https://unpkg.com/@formspree/ajax@1" defer></script>
```

## 5. SVG Figure Sizing in Cards

When moving a full-width SVG into a card, wrap it in `.fig-frame` with a max-width to match the visual weight of section-level graphics:
```css
.fig-frame { max-width: 340px; margin: 1rem auto; }
```

## 6. Collapsible Examples: Use `<details>`, Never `:hover`

When reducing visual density of bullet-heavy cards, use `<details>`/`<summary>` for collapsible
example text. This is accessible (keyboard-navigable, ARIA-friendly) and works on mobile (tap
to expand). `:hover`-based reveal fails on touch devices and is inaccessible.

Pattern for dim collapsible "e.g." line in audit rows:
```html
<details class="audit-row-eg">
  <summary>e.g.</summary>
  <span>examples text here — in DOM for SEO, collapsed by default</span>
</details>
```
```css
.audit-row-eg summary { list-style: none; opacity: 0.5; cursor: pointer; }
.audit-row-eg summary::marker { display: none; }
.audit-row-eg summary::after { content: ' ›'; }
.audit-row-eg[open] summary::after { content: ' ‹'; }
.audit-row-eg span { opacity: 0.55; font-size: 0.72rem; }
```

## 7. Mirrored Row Structure for Two-Column Cards

When presenting "one discipline, two domains" (e.g. Quant ↔ AI), use 4+4 mirrored rows
with shared payoff sentences. Row titles should be verbally parallel (Data Integrity ↔
Eval Integrity, Backtest vs. Live ↔ Offline vs. Online) so the crosswalk is visible at
a glance without explanatory prose. Asymmetric bullet counts (5 vs 4) create visual
heaviness — always equalize, demoting the weakest item to a muted footnote if needed.
