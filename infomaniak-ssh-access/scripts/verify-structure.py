#!/usr/bin/env python3
"""Verify aqfinea.net index.html structural integrity after edits.

Run: python3 scripts/verify-structure.py [path/to/index.html]

Checks:
  1. Section IDs in expected order
  2. Nav links match section order
  3. Section numbering (01, 02, 03, FAQ, Contact)
  4. Div/section tag balance
  5. Zebra-striping alternation (section vs section-alt)
  6. SVG count (expect 4 content SVGs + 1 hero arrow = 5)
  7. AI audit bullet terms (integrity vocabulary, not ops)
  8. No stale "MLOps & Reproducibility" headline
  9. Footer service links
"""
import re
import sys

def verify(html_path):
    with open(html_path, 'r') as f:
        html = f.read()

    errors = []
    passes = []

    # 1. Section order
    sections = re.findall(r'<section id="([^"]+)"', html)
    expected = ['hero', 'consulting', 'audit', 'training', 'about', 'faq', 'contact']
    if sections == expected:
        passes.append(f"Section order correct: {sections}")
    else:
        errors.append(f"Section order mismatch: got {sections}, expected {expected}")

    # 2. Nav links
    nav_html = html.split('<nav>')[1].split('</nav>')[0]
    nav_links = re.findall(r'href="#([^"]+)"', nav_html)
    expected_nav = ['consulting', 'audit', 'training', 'about', 'faq', 'contact']
    if nav_links == expected_nav:
        passes.append(f"Nav links correct: {nav_links}")
    else:
        errors.append(f"Nav links mismatch: got {nav_links}, expected {expected_nav}")

    # 3. Section numbering
    nums = re.findall(r'service-num">([^<]+)<', html)
    expected_nums = ['01', '02', '03', 'FAQ', 'Contact']
    if nums == expected_nums:
        passes.append(f"Section numbers correct: {nums}")
    else:
        errors.append(f"Section numbers mismatch: got {nums}, expected {expected_nums}")

    # 4. Tag balance
    open_divs = html.count('<div')
    close_divs = html.count('</div>')
    if open_divs == close_divs:
        passes.append(f"Div balance OK: {open_divs}/{close_divs}")
    else:
        errors.append(f"Div imbalance: {open_divs} open, {close_divs} close")

    open_sec = html.count('<section')
    close_sec = html.count('</section>')
    if open_sec == close_sec:
        passes.append(f"Section balance OK: {open_sec}/{close_sec}")
    else:
        errors.append(f"Section imbalance: {open_sec} open, {close_sec} close")

    # 5. Zebra striping
    alt_sections = re.findall(r'<section id="([^"]+)"[^>]*class="section section-alt"', html)
    reg_sections = re.findall(r'<section id="([^"]+)"[^>]*class="section"', html)
    # Expected: audit(reg), consulting(alt), training(reg), about(alt), faq(reg), contact(alt)
    expected_reg = ['audit', 'training', 'faq']
    expected_alt = ['consulting', 'about', 'contact']
    if reg_sections == expected_reg and alt_sections == expected_alt:
        passes.append(f"Zebra striping correct: reg={reg_sections}, alt={alt_sections}")
    else:
        errors.append(f"Zebra striping mismatch: reg={reg_sections} (want {expected_reg}), alt={alt_sections} (want {expected_alt})")

    # 6. SVG count
    svg_count = html.count('<svg ')
    if svg_count == 5:
        passes.append(f"SVG count OK: {svg_count} (4 content + 1 hero arrow)")
    else:
        errors.append(f"SVG count unexpected: {svg_count} (expected 5)")

    # 7. AI audit row titles (integrity vocabulary, mirrored 4×4)
    ai_start = html.find('AI &amp; LLM</h3>')
    if ai_start > 0:
        ai_card = html[ai_start:ai_start+3000]
        row_titles = re.findall(r'audit-row-title">([^<]+)<', ai_card)
        expected_titles = ['Eval Integrity', 'Offline vs. Online', 'Prompt &amp; Retrieval Risk', 'Output Reliability']
        if row_titles == expected_titles:
            passes.append(f"AI audit rows correct: {row_titles}")
        else:
            errors.append(f"AI audit rows mismatch: got {row_titles}, expected {expected_titles}")
        # Check production hygiene footnote
        if 'audit-footnote' in ai_card:
            passes.append("Production hygiene footnote present")
        else:
            errors.append("Production hygiene footnote missing")
    else:
        errors.append("AI & LLM audit card not found")

    # 7b. Quant audit row titles (mirrored)
    quant_start = html.find('Quant &amp; Trading</h3>')
    if quant_start > 0:
        quant_card = html[quant_start:quant_start+3000]
        row_titles = re.findall(r'audit-row-title">([^<]+)<', quant_card)
        expected_titles = ['Data Integrity', 'Backtest vs. Live', 'Execution &amp; Latency', 'Pipeline Architecture']
        if row_titles == expected_titles:
            passes.append(f"Quant audit rows correct: {row_titles}")
        else:
            errors.append(f"Quant audit rows mismatch: got {row_titles}, expected {expected_titles}")
    else:
        errors.append("Quant & Trading audit card not found")

    # 8. No stale MLOps headline
    if 'MLOps &amp; Reproducibility' not in html:
        passes.append("No stale 'MLOps & Reproducibility' headline")
    else:
        errors.append("Stale 'MLOps & Reproducibility' headline still present")

    # 9. Footer services
    footer = html.split('<footer')[1].split('</footer>')[0]
    footer_items = re.findall(r'<li><a[^>]*>([^<]+)</a></li>', footer)
    if 'Audit & Diagnostics' in footer_items and 'Consulting' in footer_items and 'Training' in footer_items:
        passes.append(f"Footer services correct: {footer_items[:3]}")
    else:
        errors.append(f"Footer services mismatch: {footer_items}")

    # Report
    print(f"=== STRUCTURAL VERIFICATION ({html_path}) ===\n")
    for p in passes:
        print(f"  PASS: {p}")
    for e in errors:
        print(f"  FAIL: {e}")
    print(f"\n{len(passes)} passed, {len(errors)} failed")
    return len(errors) == 0

if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else 'index.html'
    ok = verify(path)
    sys.exit(0 if ok else 1)
