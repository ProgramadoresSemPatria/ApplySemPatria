#!/usr/bin/env python3
"""URL/form apply channel (headed Playwright, agent-assisted).

Opens the apply URL in a VISIBLE browser so the user can follow along, extracts
the form schema, best-effort autofills known fields from applicant-profile.json,
uploads the resume to file inputs, then holds the browser open. Submission is
gated behind --submit.

Because ATS forms vary widely, this is agent-assisted: the driving agent should
read the printed field schema, then re-run with --answers to fill gaps before
--submit.

Usage:
  url_apply.py inspect --url URL [--hold 120]
  url_apply.py apply   --url URL [--answers answers.json] [--hold 180] [--submit]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import form_answers  # noqa: E402
from browser_session import launch_context  # noqa: E402
from flow_runner import resolve_recipe, run_recipe  # noqa: E402
from track_store import load_profile as load_track_profile  # noqa: E402

PROFILE_PATH = ROOT / "applicant-profile.json"

JS_EXTRACT_FIELDS = r"""
() => {
  const out = [];
  const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const txt = (el) => clean(el ? (el.innerText || el.textContent || '') : '');

  // The question text for an input (label[for], wrapping label, aria, placeholder,
  // then climbing ancestors for a legend/heading/label/question container).
  const questionFor = (el) => {
    if (el.id) {
      try {
        const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
        if (l && txt(l)) return txt(l);
      } catch (e) {}
    }
    const wrap = el.closest('label');
    if (wrap && txt(wrap)) return txt(wrap);
    if (el.getAttribute('aria-label')) return clean(el.getAttribute('aria-label'));
    const lb = el.getAttribute('aria-labelledby');
    if (lb) {
      const t = lb.split(/\s+/).map(id => txt(document.getElementById(id))).join(' ').trim();
      if (t) return t;
    }
    if (el.placeholder) return clean(el.placeholder);
    const sel = ':scope > legend, :scope > label, :scope > .question-title, '
      + ':scope > [class*=question], :scope > [class*=label], '
      + ':scope > h1, :scope > h2, :scope > h3, :scope > h4, :scope > h5, :scope > p, :scope > span';
    let node = el;
    for (let i = 0; i < 5 && node; i++) {
      node = node.parentElement;
      if (!node) break;
      const cand = node.querySelector(sel);
      if (cand && !cand.contains(el)) {
        const t = txt(cand);
        if (t && t.length <= 300) return t;
      }
    }
    const prev = el.previousElementSibling;
    if (prev && txt(prev)) return txt(prev).slice(0, 200);
    return '';
  };

  // For a radio/checkbox, the option's own text (to know which one to pick).
  const optionFor = (el) => {
    if (el.id) {
      try {
        const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
        if (l && txt(l)) return txt(l);
      } catch (e) {}
    }
    const wrap = el.closest('label');
    if (wrap && txt(wrap)) return txt(wrap);
    // Common ATS pattern (e.g. Loxo): <input> Label <br> — label is a raw text node.
    let acc = '';
    let node = el.nextSibling;
    while (node) {
      if (node.nodeType === 1) {
        const tag = node.tagName;
        if (['BR', 'INPUT', 'SELECT', 'TEXTAREA', 'LABEL'].includes(tag)) break;
        acc += ' ' + (node.innerText || node.textContent || '');
      } else if (node.nodeType === 3) {
        acc += ' ' + node.textContent;
      }
      node = node.nextSibling;
    }
    acc = clean(acc);
    if (acc) return acc.slice(0, 120);
    const sib = el.nextElementSibling;
    if (sib && txt(sib)) return txt(sib).slice(0, 120);
    const prev = el.previousElementSibling;
    if (prev && txt(prev)) return txt(prev).slice(0, 120);
    return el.value || '';
  };

  // Radio group question: strip Yes/No option labels from container text.
  const groupQuestionFor = (el) => {
    const name = el.name;
    if (!name) return '';
    let radios;
    try {
      radios = document.querySelectorAll('input[type="radio"][name="' + CSS.escape(name) + '"]');
    } catch (e) { return ''; }
    if (!radios.length) return '';
    let node = radios[0].parentElement;
    for (let i = 0; i < 8 && node; i++) {
      let q = txt(node);
      radios.forEach((r) => {
        const o = optionFor(r);
        if (o) q = q.replace(new RegExp('\\b' + o.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\b', 'gi'), '');
      });
      q = clean(q.replace(/\*\s*$/, ''));
      if (q.length > 25 && !/^(yes|no)$/i.test(q)) return q.slice(0, 320);
      node = node.parentElement;
    }
    return '';
  };

  let idx = 0;
  document.querySelectorAll('input, textarea, select').forEach((el) => {
    const type = (el.type || el.tagName).toLowerCase();
    if (['hidden','submit','button','image'].includes(type)) return;
    if (el.offsetParent === null && type !== 'file') return; // skip invisible (except file)
    el.setAttribute('data-jsidx', String(idx));
    const field = {
      idx: idx,
      tag: el.tagName.toLowerCase(),
      type: type,
      name: el.name || '',
      id: el.id || '',
      label: questionFor(el),
      required: el.required || el.getAttribute('aria-required') === 'true',
      value: el.value || ''
    };
    if (el.tagName.toLowerCase() === 'select') {
      field.options = Array.from(el.options).map(o => o.text.trim()).filter(Boolean);
    }
    if (type === 'radio' || type === 'checkbox') {
      field.option = optionFor(el);
      field.group = el.name || '';
      if (type === 'radio') {
        const gq = groupQuestionFor(el);
        if (gq) field.label = gq;
      }
    }
    out.push(field);
    idx++;
  });
  return out;
}
"""


def load_profile(track_id: str | None = None) -> dict[str, Any]:
    return load_track_profile(track_id)


def _pick_option(options: list[str], value: str, option_regex: str | None) -> str | None:
    """Choose the best <select> option for a resolved value."""
    if not options:
        return None
    if option_regex:
        for opt in options:
            try:
                if re.search(option_regex, opt, re.I):
                    return opt
            except re.error:
                break
    val_l = (value or "").strip().lower()
    if val_l:
        for opt in options:  # exact
            if opt.strip().lower() == val_l:
                return opt
        for opt in options:  # substring either direction
            ol = opt.strip().lower()
            if val_l in ol or ol in val_l:
                return opt
    return None


async def extract_fields(page) -> list[dict[str, Any]]:
    try:
        return await page.evaluate(JS_EXTRACT_FIELDS)
    except Exception:  # noqa: BLE001
        return []


async def autofill(
    page,
    fields,
    profile,
    answers: dict[str, str],
    *,
    track_id: str | None = None,
) -> dict[str, Any]:
    """Fill fields via the deterministic knowledge base. Unresolved fields are
    returned so the agent can answer only those (minimal tokens)."""
    report: dict[str, Any] = {
        "filled": [],
        "needs_input": [],   # matched a rule but profile value is blank -> ask user
        "unmapped": [],      # no rule matched -> agent must decide + add a rule
        "resume_uploaded": False,
    }
    rules = form_answers.load_bank(track_id)
    resume = Path(profile.get("resume_path", "")).expanduser()
    satisfied_groups: set[str] = set()

    for field in fields:
        sel = f"[data-jsidx='{field['idx']}']"
        ftype = field["type"]

        if ftype == "radio" and field.get("group") in satisfied_groups:
            continue

        if ftype == "file":
            if resume.exists():
                try:
                    await page.set_input_files(sel, str(resume))
                    # Fire change/input so custom widgets (Loxo better-file-input,
                    # etc.) update their visible filename state.
                    await page.eval_on_selector(
                        sel,
                        "el => { el.dispatchEvent(new Event('change', {bubbles:true}));"
                        " el.dispatchEvent(new Event('input', {bubbles:true})); }",
                    )
                    report["resume_uploaded"] = True
                except Exception:  # noqa: BLE001
                    pass
            continue

        res = form_answers.resolve(field, profile, answers, rules)
        stub = {
            "idx": field["idx"],
            "label": field.get("label") or field.get("name") or field.get("id"),
            "type": ftype,
            "required": bool(field.get("required")),
        }
        if field.get("options"):
            stub["options"] = field["options"]
        if field.get("option"):
            stub["option"] = field["option"]
        if field.get("group"):
            stub["group"] = field["group"]

        if res["status"] != "ok":
            stub["reason"] = res["reason"]
            if res["status"] == "empty":
                stub["source"] = res["source"]
                report["needs_input"].append(stub)
            else:
                report["unmapped"].append(stub)
            continue

        value = res["value"]
        try:
            if field["tag"] == "select":
                chosen = _pick_option(field.get("options", []), value, res.get("option_regex"))
                if not chosen:
                    stub["reason"] = "no option matched"
                    report["unmapped"].append(stub)
                    continue
                await page.select_option(sel, label=chosen)
                value = chosen
            elif ftype in ("checkbox", "radio"):
                opt = str(field.get("option") or "").strip()
                val = str(value).strip()
                should = False
                if res.get("option_regex") and opt:
                    try:
                        should = bool(re.search(res["option_regex"], opt, re.I))
                    except re.error:
                        should = False
                if not should and opt and val:
                    should = opt.lower() == val.lower()
                if not should and ftype == "checkbox" and val.lower() in ("yes", "true", "1", "on"):
                    should = True
                if not should:
                    continue
                try:
                    await page.check(sel, force=True)
                except Exception:
                    if opt:
                        lab = page.get_by_text(opt, exact=True)
                        if await lab.count() > 0:
                            await lab.first.click(force=True)
                        else:
                            raise
                    else:
                        raise
                if ftype == "radio" and field.get("group"):
                    satisfied_groups.add(field["group"])
            else:
                await page.fill(sel, str(value))
            report["filled"].append(
                {"idx": field["idx"], "label": stub["label"], "value": str(value)[:60],
                 "source": res["source"]}
            )
        except Exception as exc:  # noqa: BLE001
            stub["reason"] = f"fill error: {str(exc)[:80]}"
            report["unmapped"].append(stub)
    return report


def print_autofill_report(report: dict[str, Any]) -> None:
    print(f"\n✓ filled {len(report['filled'])} field(s)"
          f" · resume={'yes' if report['resume_uploaded'] else 'no'}")
    for f in report["filled"]:
        print(f"    [{f['idx']}] {f['label']} = {f['value']}  ({f['source']})")
    if report["needs_input"]:
        print(f"\n⚠ NEEDS INPUT — profile field blank ({len(report['needs_input'])}):")
        for f in report["needs_input"]:
            req = "REQUIRED" if f["required"] else "optional"
            print(f"    [{f['idx']}] ({req}) {f['label']}  ← {f['source']}")
    if report["unmapped"]:
        print(f"\n❓ UNMAPPED — no rule in bank ({len(report['unmapped'])}):")
        for f in report["unmapped"]:
            req = "REQUIRED" if f["required"] else "optional"
            opts = f"  options={f['options']}" if f.get("options") else ""
            opt = f"  ·opt:{f['option']}" if f.get("option") else ""
            grp = f"  (group:{f['group']})" if f.get("group") else ""
            reason = f"  ← {f['reason']}" if f.get("reason") else ""
            print(f"    [{f['idx']}] ({req}) [{f['type']}] {f['label']}{opts}{opt}{grp}{reason}")


async def fill_country_dropdown(page, country: str) -> bool:
    """UnlockCareer-style country picker (button opens a list, not <select>)."""
    btn = page.get_by_role("button", name=re.compile(r"select your country", re.I))
    if await btn.count() == 0:
        return False
    try:
        await btn.first.click(timeout=8000)
        await asyncio.sleep(0.6)
        opt = page.get_by_text(country, exact=False)
        for i in range(await opt.count()):
            t = (await opt.nth(i).inner_text()).strip()
            if country.lower() in t.lower():
                await opt.nth(i).click()
                return True
    except Exception:  # noqa: BLE001
        return False
    return False


async def notify_form_change(page) -> None:
    """React/Vue controlled forms often keep submit disabled until input/change fire."""
    await page.evaluate(
        """() => document.querySelectorAll('input, textarea, select').forEach(el => {
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
        })"""
    )
    await asyncio.sleep(0.8)


async def try_submit(page) -> dict[str, Any]:
    before = page.url
    for name in (r"Submit application", r"^Submit", r"Send application",
                 r"^Apply$", r"^Apply\b", r"^Enviar", r"Enviar candidatura", r"Postular"):
        btn = page.get_by_role("button", name=re.compile(name, re.I))
        if await btn.count() > 0:
            try:
                await btn.first.wait_for(state="visible", timeout=5000)
                for _ in range(15):
                    if await btn.first.is_enabled():
                        break
                    await asyncio.sleep(0.4)
            except Exception:  # noqa: BLE001
                pass
            if not await btn.first.is_enabled():
                # React forms: native validity passes but button stays disabled until
                # internal state catches up — enable when the form itself is valid.
                ok = await page.evaluate(
                    """() => {
                      const f = document.querySelector('form');
                      const b = document.querySelector('button[type=submit]');
                      if (!f || !b || !f.checkValidity()) return false;
                      b.disabled = false;
                      b.removeAttribute('disabled');
                      return true;
                    }"""
                )
                if not ok:
                    return {"clicked": name, "confirmed": False,
                            "error": "submit button disabled; form invalid"}
            await btn.first.click(timeout=20000)
            await asyncio.sleep(4.5)
            after = page.url
            try:
                body = (await page.inner_text("body"))[:3000].lower()
            except Exception:  # noqa: BLE001
                body = ""
            cues = ("thank you", "thanks for", "received", "submitted",
                    "application has been", "we'll be in touch", "we will be in touch",
                    "obrigad", "recebemos", "gracias", "hemos recibido", "successfully")
            confirmed = (after != before) or any(c in body for c in cues)
            return {"clicked": name, "url_before": before, "url_after": after,
                    "confirmed": confirmed}
    return {"clicked": None, "confirmed": False}


def log_submission(url: str, resolved_url: str, *, company: str = "", role: str = "",
                   confirmed: bool = False, job_key: str = "") -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo
    path = ROOT / "state" / "url-applications.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {"submitted": []}
    entry: dict[str, Any] = {
        "url": url,
        "resolved_url": resolved_url,
        "company": company,
        "role": role,
        "confirmed": confirmed,
        "submitted_at": datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat(),
    }
    jk = (job_key or "").strip()
    if jk:
        entry["job_key"] = jk
    data.setdefault("submitted", []).append(entry)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


async def resolve_shortlink(page) -> None:
    """LinkedIn lnkd.in links hit a safety interstitial. Follow the external
    destination anchor so we land on the real apply form."""
    for _ in range(3):
        if "lnkd.in" not in page.url:
            return
        try:
            hrefs = await page.eval_on_selector_all(
                "a[href]",
                "els => els.map(e=>e.href).filter(h => h && "
                "!h.includes('linkedin.com') && !h.includes('lnkd.in') && "
                "!h.startsWith('javascript'))",
            )
        except Exception:  # noqa: BLE001
            hrefs = []
        if not hrefs:
            return
        print(f"resolving lnkd.in → {hrefs[0]}")
        await page.goto(hrefs[0], wait_until="domcontentloaded", timeout=90000)
        await asyncio.sleep(3.5)


APPLY_CTA = re.compile(
    r"apply for this job|apply now|apply here|^apply$|start application|"
    r"aplicar|candidat|postular|enviar candidatura",
    re.I,
)


async def reveal_form(page) -> None:
    """Many job pages show the description first; the form appears after an
    'Apply' CTA. Click it if the form isn't already on the page."""
    fields = await extract_fields(page)
    fillable = [f for f in fields if f["type"] not in ("checkbox", "radio")]
    if len(fillable) >= 3:
        return
    for role in ("link", "button"):
        loc = page.get_by_role(role, name=APPLY_CTA)
        if await loc.count() > 0:
            print(f"clicking apply CTA ({role})…")
            try:
                await loc.first.click(timeout=10000)
                await asyncio.sleep(4.0)
            except Exception:  # noqa: BLE001
                pass
            return


async def run(
    cmd: str,
    url: str,
    *,
    answers: dict[str, str],
    hold: int,
    submit: bool,
    company: str = "",
    role: str = "",
    track_id: str | None = None,
) -> None:
    profile = load_profile(track_id)
    pw, browser, ctx = await launch_context(headless=False)
    try:
        page = await ctx.new_page()
        print(f"opening: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=90000)
        await asyncio.sleep(4.0)
        await resolve_shortlink(page)
        await reveal_form(page)
        print(f"landed:  {page.url}")

        # Prefer a saved deterministic recipe (no LLM) for known ATS domains.
        recipe = resolve_recipe(page.url)
        if recipe:
            print(f"\n✓ deterministic recipe matched: {recipe['name']}")

        fields = await extract_fields(page)
        print(f"\nform fields detected: {len(fields)}  (compact schema)")
        for f in fields:
            req = "req" if f.get("required") else "opt"
            opts = f"  {{{', '.join(f['options'][:8])}}}" if f.get("options") else ""
            opt = f"  ·opt:{f['option']}" if f.get("option") else ""
            print(f"  #{f['idx']:>2} [{f['type']:<8}] ({req}) {f.get('label','')}{opts}{opt}")

        if cmd == "apply":
            if recipe:
                result = await run_recipe(
                    page, recipe, variables={"role": ""}, profile=profile, send=submit
                )
                print(f"\n✓ deterministic recipe ran: {recipe['name']}")
            report = await autofill(page, fields, profile, answers, track_id=track_id)
            if await fill_country_dropdown(page, profile.get("country", "Brazil")):
                report.setdefault("filled", []).append(
                    {"idx": -1, "label": "Country of residence", "value": profile.get("country", "Brazil"),
                     "source": "country-dropdown"}
                )
            await notify_form_change(page)
            print_autofill_report(report)
            gaps = [f for f in report["needs_input"] + report["unmapped"] if f["required"]]
            if submit:
                if gaps:
                    print(f"\n⚠ {len(gaps)} required field(s) unresolved — NOT submitting.")
                else:
                    res = await try_submit(page)
                    print(f"submit: {json.dumps(res, ensure_ascii=False)}")
                    if res.get("clicked"):
                        log_submission(url, page.url, company=company, role=role,
                                       confirmed=bool(res.get("confirmed")))
                        if res.get("confirmed"):
                            print("✓ submission confirmed + logged")
                        else:
                            print("⚠ clicked submit but no confirmation detected — "
                                  "logged as unconfirmed; verify in the open browser")
                        from table_refresh import refresh_applications_table  # noqa: E402
                        refresh_applications_table()
            elif gaps:
                print(f"\n→ {len(gaps)} required gap(s). Answer them, add rules to "
                      "form-answers.json (or fill profile), then re-run with --submit.")

        print(f"\nholding browser open {hold}s for review…")
        await asyncio.sleep(hold)
    finally:
        await browser.close()
        await pw.stop()


def main() -> int:
    parser = argparse.ArgumentParser(description="URL/form apply channel (headed)")
    parser.add_argument("command", choices=["inspect", "apply"])
    parser.add_argument("--url", required=True)
    parser.add_argument("--answers", type=Path, help="JSON map of field name/id/label -> value")
    parser.add_argument("--hold", type=int, default=120, help="Seconds to keep browser open")
    parser.add_argument("--submit", action="store_true", help="Click submit if no required gaps")
    parser.add_argument("--company", default="", help="Company (for the submission log)")
    parser.add_argument("--role", default="", help="Role (for the submission log)")
    parser.add_argument("--track", default=None, help="Career track (profile + form answers + resume)")
    args = parser.parse_args()

    answers: dict[str, str] = {}
    if args.answers and args.answers.exists():
        answers = json.loads(args.answers.read_text(encoding="utf-8"))

    asyncio.run(
        run(
            args.command,
            args.url,
            answers=answers,
            hold=args.hold,
            submit=args.submit,
            company=args.company,
            role=args.role,
            track_id=args.track,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
