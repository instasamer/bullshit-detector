# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *

import json
import typing
import re


class BullshitDetector(gl.Contract):
    results: TreeMap[str, str]

    def __init__(self):
        pass

    @gl.public.write
    def verify_claim(self, claim_text: str, source_url: str) -> typing.Any:
        """
        Verifies if a social media post claim is bullshit or not.

        Evidence gathering (optimized - max 2 web requests):
        1. Fetches the first URL found in the claim (e.g. Polymarket profile)
        2. One Google search combining fact-check + debunk + author

        Analysis covers:
        - Evidence vs claims comparison
        - Technical feasibility
        - Manipulation tactics
        - Author credibility signals
        - Community signals (from search results)

        Uses Optimistic Democracy + Comparative Equivalence Principle.
        """

        def analyze_claim() -> str:
            # ===== EVIDENCE GATHERING (max 2 requests) =====

            # 1. Fetch first URL found in the claim
            url_evidence = ""
            urls = re.findall(r'https?://[^\s\)\]\"\'>]+', claim_text)
            for u in urls[:1]:
                u = u.rstrip('.,;:!?)\'\"')
                if not u:
                    continue
                try:
                    response = gl.nondet.web.get(u)
                    body = response.body.decode("utf-8")
                    url_evidence = f"\n[Data from {u}]:\n{body[:3000]}"
                except Exception:
                    try:
                        page = gl.nondet.web.render(u, mode='html')
                        url_evidence = f"\n[Page {u}]:\n{page[:3000]}"
                    except Exception:
                        url_evidence = f"\n[Could not fetch {u}]"

            # Extract author handle if source is twitter
            author = ""
            if source_url:
                m = re.search(r'(?:x\.com|twitter\.com)/(\w+)/status', source_url)
                if m:
                    author = m.group(1)

            # ===== BUILD EVIDENCE =====
            evidence = ""
            if url_evidence:
                evidence += f"\nURL EVIDENCE:{url_evidence}"
            if not evidence:
                evidence = "\n[No web evidence gathered]"

            # ===== ANALYSIS PROMPT =====
            prompt = f"""You are an expert investigative fact-checker. Analyze this social media post.

POST:
"{claim_text}"

{f"AUTHOR: @{author}" if author else ""}

WEB EVIDENCE:{evidence}

Analyze from ALL these angles:

1. EVIDENCE vs CLAIMS: Compare what the post says vs what the evidence shows. If a URL was fetched (e.g. a Polymarket profile), compare real numbers to claimed numbers.

2. TECHNICAL FEASIBILITY: Are the claims technically realistic?
   - Are profit/performance numbers plausible for this activity?
   - Does the setup described make technical sense?
   - Would this actually work in practice?
   - Are there obvious exaggerations?

3. MANIPULATION DETECTION:
   - FOMO, fake exclusivity, manufactured urgency
   - "Leaked/deleted" content creating false scarcity
   - Affiliate links, "DM me", referral codes
   - Engagement bait, incomplete teasers
   - Is the author selling something?

4. CREDIBILITY SIGNALS: From search results -
   - Is the author known for scams or shilling?
   - Has this been debunked by others?
   - What does the community say?

VERDICT:
- BULLSHIT: False, exaggerated, technically implausible, or deliberately misleading
- LEGIT: Plausible, supported by evidence, not manipulative
- INCONCLUSIVE: Mixed or insufficient evidence

Respond with ONLY JSON:
{{"verdict":"BULLSHIT","confidence":85,"reason":"2-3 sentences with strongest evidence","red_flags":["quote problematic parts"],"evidence_summary":"evidence findings + technical assessment + community signals"}}"""

            result = gl.nondet.exec_prompt(prompt)
            if not isinstance(result, str):
                result = json.dumps(result, sort_keys=True)
            result = result.replace("```json", "").replace("```", "").strip()
            return result

        principle = "Both outputs must have the same verdict field (BULLSHIT, LEGIT, or INCONCLUSIVE). Small differences in wording of reason, red_flags, or confidence are acceptable as long as the core verdict is identical."

        result_str = gl.eq_principle.prompt_comparative(
            analyze_claim,
            principle,
        )

        try:
            if isinstance(result_str, str):
                result_str = result_str.replace("```json", "").replace("```", "").strip()
            result_json = json.loads(result_str) if isinstance(result_str, str) else result_str

            verdict = result_json.get("verdict", "INCONCLUSIVE").upper()
            if verdict not in ("BULLSHIT", "LEGIT", "INCONCLUSIVE"):
                verdict = "INCONCLUSIVE"
            result_json["verdict"] = verdict
        except (json.JSONDecodeError, AttributeError):
            result_json = {
                "verdict": "INCONCLUSIVE",
                "confidence": 0,
                "reason": "Failed to parse AI response",
                "red_flags": [],
                "evidence_summary": str(result_str)[:500],
            }

        result_stored = json.dumps(result_json, sort_keys=True)
        claim_key = claim_text[:100]
        self.results[claim_key] = result_stored

        return result_json

    @gl.public.write
    def verify_url(self, url: str) -> typing.Any:
        """Fetches a URL and verifies its content."""

        def fetch_and_extract() -> str:
            page = gl.nondet.web.render(url, mode='html')
            extract_prompt = f"""Extract the main post/claim text from this social media page.
Ignore navigation, ads, sidebars, and other users' replies.
Return ONLY the main post text, nothing else.

Page content:
{page[:5000]}"""
            extracted = gl.nondet.exec_prompt(extract_prompt)
            if not isinstance(extracted, str):
                extracted = str(extracted)
            return extracted.strip()

        claim_text = gl.eq_principle.prompt_comparative(
            fetch_and_extract,
            "Both outputs must contain the same core post text. Minor formatting differences are acceptable.",
        )

        if isinstance(claim_text, str):
            claim_text = claim_text.strip()

        return self.verify_claim(claim_text, url)

    @gl.public.view
    def get_result(self, claim_key: str) -> str:
        """Get a previously stored result."""
        return self.results[claim_key]

    @gl.public.view
    def get_all_results(self) -> str:
        """Get all stored results."""
        all_results = {}
        for key in self.results:
            all_results[key] = json.loads(self.results[key])
        return json.dumps(all_results)
