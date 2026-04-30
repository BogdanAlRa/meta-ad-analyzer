# Meta Ad Library Video Analyzer

Most ad spy tools show you *what* competitors are running. This one tells you *why* it works.

Paste any brand's Meta Ad Library link. The system downloads their video ads, then runs each one through an **8-pass AI pipeline** built on 4 named AI engines and 4 proprietary systems, layered together so each pass feeds the next, building intelligence no single model could produce alone.

You get: hook archetypes, persuasion scores, claim-to-proof ratios, creative tension maps, and a strategic report comparing all their ads.

**No API keys needed. No setup. One click.**

## The 8-Pass AI Pipeline

**4 AI engines. 4 proprietary systems. 8 passes.**

| Pass | System | What It Does |
|---|---|---|
| 1 | Proprietary discovery engine | Intercepts Meta's GraphQL API to pull ad data from Facebook's internal data layer |
| 2 | FFmpeg | Decomposes video into keyframes at psychologically significant timestamps and extracts audio |
| 3 | OpenAI Whisper | Transcribes every spoken word (the verbal persuasion layer) |
| 4 | Google Gemini Vision | Analyzes every frame visually: composition, text, brand placement, production style |
| 5 | Proprietary extraction architecture | Separates claims from proofs using constrained quote-pinned extraction |
| 6 | Proprietary scoring engine | Deterministic formulas with no AI randomness compute all persuasion metrics |
| 7 | Proprietary adversarial validator | A hostile second pass that cross-checks claims against proofs and flags gaps *(Deep mode)* |
| 8 | Google Gemini Pro | Synthesizes all ad analyses into a cross-brand strategic intelligence report |

The named engines handle perception: hearing and seeing the ad. The proprietary systems handle *judgment*: deciding what counts as a claim, what qualifies as proof, how strong the persuasion architecture actually is, and whether the ad's own logic holds up under adversarial pressure.

This isn't something you can replicate with a prompt. It's 8 coordinated passes where each system's output is structured input for the next, with deterministic scoring, quote-constrained extraction, and adversarial validation built into the pipeline architecture.

## How to Use It

**Step 1.** Go to [facebook.com/ads/library](https://www.facebook.com/ads/library/) and search for a brand

**Step 2.** Copy the URL from your browser's address bar (this is the brand's Ad Library page link)

**Step 3.** Paste that link into the "Brand Ad Library Link" field below

**Step 4.** Choose how many videos to analyze

**Step 5.** Click "Start" and the tool finds the brand's video ads, analyzes the most recent ones, and generates your report

Results appear in 2-3 minutes per video.

## What You Get

For each video ad:

- **Persuasion Score (0-100):** How persuasive is this ad, really? Not a gut feeling. A composite number based on whether the ad actually backs up what it claims, explains how the product works, and builds tension that drives action.
- **Hook Archetype:** What opening strategy does the ad use? Direct address, rapid montage, problem-agitation, demonstration, social proof, curiosity gap, offer-led, or before/after. Know what hooks your competitors are betting on.
- **Claim Extraction:** Every promise the ad makes, pulled as a verbatim quote. Not what the AI *thinks* they said. The exact words from the transcript and on-screen text. If the system can't find the exact words, the claim gets thrown out.
- **Proof Elements with Strength Scores:** Does the ad back up its claims? Every piece of evidence (testimonials, certifications, stats, demos) is scored on how specific, verifiable, and credible it actually is.
- **Mechanism Explicitness:** Does the ad explain *how* the product works, or just say it works? This flag catches ads that make bold promises without showing the mechanism. If your competitors skip this, that's your creative angle.
- **Cognitive Tensions:** The push-pull forces inside the ad. Speed vs. trust. Simplicity vs. control. Cheap vs. risky. Novelty vs. safety. These tensions are what make people *feel* something, and the best ads use them deliberately.
- **Urgency Signals:** Scarcity cues, time pressure, FOMO markers. Is the ad creating urgency, and how?
- **Full Transcript:** Every word spoken in the ad, transcribed.
- **Visual Analysis:** Frame-by-frame breakdown: who's on screen, what they're doing, what text appears, what colors dominate, production quality, setting.

Plus a **Strategic Report** that synthesizes patterns across all the videos: what hooks they keep using, what claims they repeat, where their proof is weak, and what creative angles they're leaving on the table.

## Who This Is For

- **Media buyers.** Stop guessing why competitor creatives convert. See the persuasion mechanics behind their best-performing formats so you can build better ads, faster.
- **Creative strategists.** Build briefs backed by data, not instinct. Know exactly what hook archetypes, proof types, and tension structures work in your category before you brief your team.
- **Brand managers.** Monitor how competitors position themselves. Spot when they shift messaging, change proof strategies, or test new creative formats.
- **Agencies.** Generate competitive intelligence reports for clients in minutes, not days. Deliver analysis that goes deeper than "here's what they're running."
- **DTC founders.** Study the ad strategies of brands you admire. Understand why their ads work so you can adapt the patterns, not copy the surface.

## How Much Does It Cost?

**$0.20 per video analyzed.** That's it.

| Videos Analyzed | Cost |
|---|---|
| 1 video | $0.20 |
| 5 videos | $1.00 |
| 10 videos | $2.00 |
| 50 videos | $10.00 |

No subscription. No monthly fee. Pay only for the videos you analyze.

Compare that to AdSpy ($249/month), Foreplay ($49-249/month), or BigSpy ($99-299/month). Those tools show you the ads. They don't tell you *why they work*.

## What the Output Looks Like

### Per-Video Analysis (JSON)

Each video ad produces a structured record with 30+ fields:

```json
{
  "ad_id": "1275238353896498",
  "brand_name": "Athletic Greens",
  "persuasion_score": 72.4,
  "hook_archetype": "direct_address",
  "format": "talking_head",
  "overall_tone": "educational",
  "mechanism_explicitness": 0.70,
  "avg_proof_strength": 0.65,
  "claims_count": 8,
  "claims": [
    {
      "text": "75 vitamins, minerals, and whole food sourced ingredients",
      "type": "descriptive",
      "scope": "product_composition",
      "confidence": 0.95
    }
  ],
  "proofs": [
    {
      "quote": "NSF Certified for Sport",
      "type": "certification",
      "source_class": "institutional",
      "strength": 0.82
    }
  ],
  "tensions": [
    {
      "name": "simplicity_vs_control",
      "pole_a": ["one scoop", "simple"],
      "pole_b": ["75 ingredients", "comprehensive"]
    }
  ],
  "transcript": "...",
  "visual_narrative": "Speaker introduces product, demonstrates mixing..."
}
```

### Strategic Report (Markdown)

Cross-video synthesis covering:
- What hook strategies the brand keeps betting on, and which ones they've stopped using
- How they build their persuasion case from open to close
- Where their claims are strong and where the proof falls short
- What creative tensions they exploit (and which they ignore)
- Production patterns: format, pacing, tone, talent usage
- Actionable gaps and angles you can use in your own creative

## How the Scoring Works

### Deterministic, Not AI Vibes

Every score comes from fixed proprietary formulas. Same ad analyzed twice always produces the same numbers. No AI randomness, no temperature variance, no "it depends on the prompt." The scoring engine is pure rule-based. It measures, it doesn't guess.

What gets measured:
- **Persuasion Composite (0-100).** Weighted combination of mechanism clarity, proof strength, claim density, coverage, tension depth, and urgency. A single number that tells you how well-constructed the ad's argument actually is.
- **Proof Strength.** Each piece of evidence scored on how specific it is, whether you could verify it, and how credible the source is. "Doctor recommended" scores differently than "NSF Certified" because it should.
- **Mechanism Explicitness.** Does the ad explain the *how*, or just promise the *what*? An ad that says "lose weight fast" scores low. An ad that says "blocks carb absorption by binding to the enzyme alpha-amylase" scores high. This is the difference between hype and persuasion.

### Every Claim Is Pinned to Exact Words

The system doesn't paraphrase or summarize. Every claim it extracts must be a verbatim quote from the transcript or on-screen text. If it can't point to the exact words in the source material, the claim gets rejected. This is enforced by the proprietary extraction architecture, not by asking nicely.

### 11 Proof Types, Scored Individually

Authority, popularity, demonstration, measurement, narrative testimony, comparison, guarantee, scarcity, certification, peer affiliation, and mechanistic visualization. Each one scored against multiple specificity cues and penalty flags. You'll see exactly what kind of proof the brand uses, and what kind they don't.

### 7-Tier Source Credibility

Not all proof is equal. An NSF certification carries more weight than a self-asserted claim. The system ranks every proof source from institutional (highest credibility) down through platform-verified, third-party media, influencer, user-generated, and self-asserted (lowest). The weighting formulas are proprietary.

## Input Reference

| Field | Required | Description |
|---|---|---|
| Brand Ad Library Link or Name | Yes | Paste the brand's Ad Library page URL. You can also enter just the brand name. |
| Number of videos | No | How many video ads to analyze (default: 5, max: 50) |
| Analysis depth | No | Standard or Deep (default: standard) |

## Technical Details

- **Runtime:** Python 3.12 on Apify Cloud
- **Time per video:** ~2-3 min (standard), ~3-5 min (deep)
- **Named AI engines:** OpenAI Whisper (transcription), Google Gemini 2.5 Flash (vision + report generation), FFmpeg (video decomposition)
- **Proprietary systems:** Ad discovery engine, constrained extraction architecture, deterministic scoring engine, adversarial validation framework
- **Infrastructure:** Playwright Chromium + residential proxies for Meta Ad Library access
- **Pipeline:** 8 coordinated passes where each system's output is structured input for the next

## FAQ

**Do I need any API keys?**
No. Everything is included in the per-video price. Just paste a brand link and run.

**What ad formats are supported?**
Video ads only. The tool finds video ads on the brand's Ad Library page, downloads them, and analyzes the visual frames and audio.

**How does it find the videos?**
A proprietary discovery engine intercepts Meta's GraphQL API responses to pull structured ad data. The most recent videos are analyzed first.

**Can I just do this myself with ChatGPT or Claude?**
You can ask an AI to watch a video and tell you about it. What you'll get is a description: "this ad features a woman talking about a supplement." What you won't get is a persuasion score based on deterministic formulas, claims pinned to verbatim quotes, proof elements scored by type and source credibility, mechanism explicitness flags, cognitive tension mapping, and an adversarial validation layer that catches when the ad contradicts itself. That's the difference between a description and an analysis. The pipeline coordinates 4 AI engines and 4 proprietary systems across 8 passes. Each pass feeds structured output into the next. You can't replicate that workflow in a chat window.

**What's the difference between Standard and Deep analysis?**
Standard gives you the full analysis: transcript, visual breakdown, claims, proofs, scores, and a strategic report. That's what most people need. Deep adds an extra layer: an adversarial validation pass that acts like a skeptical reviewer, cross-checking every claim against every proof, looking for contradictions, unsupported assertions, or inflated confidence. Think of Standard as "what is this ad doing?" and Deep as "is what this ad claims actually holding up?"

**Can I analyze competitor ads?**
Yes. Any brand with public ads on the Meta Ad Library. Paste their link, hit start.

**What if a video has no audio?**
Still works. It analyzes visual frames and on-screen text. The transcript will be empty but all other analysis proceeds normally.

**What if I enter a brand name instead of a link?**
It'll search the Meta Ad Library for that name. This works but may return results from multiple pages with similar names. For best results, use the direct Ad Library page link.
