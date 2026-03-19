# MultAI — User Guide

**Version:** 0.2.260318C Alpha | **Date:** 2026-03-18

---

## What is MultAI?

MultAI is a research assistant that sends your questions to **seven different AI services at the same time** — Claude, ChatGPT, Copilot, Perplexity, Grok, DeepSeek, and Gemini — then collects all the answers and combines them into a single, polished report.

It runs as a plugin inside **Claude Code**, the command-line tool from Anthropic. You simply type your question in plain English, and MultAI takes care of everything: opening browsers, submitting prompts, waiting for answers, and synthesizing the results. No coding required.

**Why use seven AIs instead of one?** Every AI has blind spots. By comparing answers from multiple sources, you get a more complete, more balanced picture — with less risk of missing something important.

---

## What Can MultAI Do?

### Ask Any Question to 7 AIs at Once

The simplest way to use MultAI: just ask a question. MultAI sends it to all seven AI platforms simultaneously and gives you a combined answer.

> **Example:** "What are the key trends in renewable energy for 2026?"
>
> **What you get:** Answers from all 7 AIs, synthesized into a single report highlighting consensus, disagreements, and unique insights from each source.

### Research a Product in Depth

Want to understand what a software product can really do? The **Solution Researcher** runs a deep competitive intelligence analysis across all seven AIs and produces a structured capability report.

> **Example:** "Research Notion — I want to understand its project management features"
>
> **What you get:** A Consolidated Intelligence Report covering capabilities, limitations, pricing, and how it compares to alternatives — backed by evidence from seven independent AI assessments.

### Map an Entire Market

Need to understand a whole product category? The **Landscape Researcher** creates a comprehensive market landscape report with interactive charts.

> **Example:** "Give me a market landscape of project management tools"
>
> **What you get:** A 9-section market landscape report with leader/challenger classifications, trend analysis, and interactive comparison charts — all auto-generated from seven AI perspectives.

### Compare Products Side by Side

Once you have research reports on multiple products, the **Comparator** creates and maintains a feature-by-feature spreadsheet comparing them all.

> **Example:** "Add Asana to the comparison matrix"
>
> **What you get:** An updated Excel spreadsheet with Asana's capabilities ticked against every feature in the matrix, complete with weighted scoring.

### Combine AI Answers into One Report

The **Consolidator** merges raw AI answers into a single structured report. This usually runs automatically as part of the other workflows, but you can also invoke it directly.

---

## Before You Start

### What You Need

| Requirement | Details |
|-------------|---------|
| **Operating system** | macOS (recommended), Linux, or Windows |
| **Python** | Version 3.11 or higher — [download here](https://www.python.org/downloads/) |
| **Google Chrome** | Latest version — [download here](https://www.google.com/chrome/) |
| **Claude Code** | Anthropic's CLI tool — [install instructions](https://docs.anthropic.com/en/docs/claude-code) |

### Log In to AI Platforms

MultAI uses your existing Chrome browser sessions to interact with AI platforms. Before your first run, open Chrome and sign in to each platform:

| Platform | URL | Account |
|----------|-----|---------|
| Claude.ai | [claude.ai](https://claude.ai) | Free Anthropic account |
| ChatGPT | [chat.openai.com](https://chat.openai.com) | Free OpenAI account |
| Microsoft Copilot | [copilot.microsoft.com](https://copilot.microsoft.com) | Free Microsoft account |
| Perplexity | [perplexity.ai](https://www.perplexity.ai) | Free account |
| Grok | [grok.com](https://grok.com) | Free X/Twitter account |
| DeepSeek | [chat.deepseek.com](https://chat.deepseek.com) | Free account |
| Google Gemini | [gemini.google.com](https://gemini.google.com) | Free Google account |

> **Tip:** You don't need to sign in to all seven. MultAI will use whichever platforms you're logged into and skip the rest.

---

## Installation

### Option A: Plugin Install (Recommended)

This is the easiest way to get started. One command does everything.

**Step 1.** Open your terminal (Terminal on macOS, or your preferred terminal app).

**Step 2.** Run:

```
claude plugin install alo-exp/multai
```

**Step 3.** That's it. Dependencies install automatically the first time you use MultAI.

---

### Option B: Manual Install

If you prefer to manage the installation yourself, or if the plugin install didn't work:

**Step 1.** Open your terminal.

**Step 2.** Clone the repository:

```
git clone https://github.com/alo-exp/multai.git
```

**Step 3.** Enter the project directory:

```
cd multai
```

**Step 4.** Run the setup script:

```
bash setup.sh
```

**Step 5.** Wait for setup to complete (usually takes 1-2 minutes). You'll see progress messages as it installs the required packages and downloads the browser automation tools.

When you see `Setup complete. You're ready to use MultAI.` — you're done.

---

### Optional: Enable Smart Recovery

MultAI includes a "smart recovery" feature that uses a backup AI to help when something goes wrong during a research run (for example, if a platform's layout has changed). This is optional but recommended.

**To enable it, you need a free API key from one of these providers:**

#### Option 1: Free Google Gemini API Key (Recommended)

1. Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Click **Create API Key** and copy the key
3. Create a file called `.env` in the MultAI project folder and add:
   ```
   GOOGLE_API_KEY=your_key_here
   ```

#### Option 2: Anthropic API Key

1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Create an API key and copy it
3. Add to your `.env` file:
   ```
   ANTHROPIC_API_KEY=your_key_here
   ```

Then run: `bash setup.sh --with-fallback`

---

## Your First Research Run

Here's a step-by-step walkthrough of your first MultAI run:

**Step 1.** Open Claude Code in the MultAI project directory:

```
cd multai
claude
```

**Step 2.** Type your research question naturally. For example:

> What are the pros and cons of using Kubernetes for small teams?

**Step 3.** MultAI automatically detects that this is a multi-AI research question and submits it to all seven platforms. You'll see progress messages as each platform responds:

```
[Claude.ai] Navigating to https://claude.ai/new
[ChatGPT] Navigating to https://chat.openai.com
[Perplexity] Navigating to https://www.perplexity.ai
...
```

**Step 4.** After all platforms respond (usually 2-5 minutes for a regular question), MultAI synthesizes the answers into a single combined report. The report opens automatically in the interactive viewer.

> **Tip:** If you want deeper, more thorough research, include the word "deep" in your request:
> "Do a deep research on Kubernetes for small teams"

---

## Viewing Your Reports

### The Report Viewer

MultAI includes a beautiful interactive report viewer that displays your research results. It opens automatically when a report is ready.

**What you'll see:**

- **Top navigation bar** — Click vendor/section names to jump directly to that section
- **Left sidebar** — Full table of contents; click any heading to navigate
- **Main content area** — Your research report with formatted text, tables, and interactive charts
- **Export buttons** (bottom right):
  - 📋 **Copy** — Copies the report for pasting into Google Docs or other editors
  - 📄 **PDF** — Exports the report as a PDF file

### Where Reports Are Saved

All reports are saved in the `reports/` folder inside the MultAI project directory. Each research run creates its own subfolder:

```
reports/
├── my-kubernetes-research/
│   ├── Claude.ai-raw-response.md       (individual AI answers)
│   ├── ChatGPT-raw-response.md
│   ├── ...
│   ├── status.json                      (run metadata)
│   └── my-kubernetes-research - Raw AI Responses.md  (combined archive)
```

---

## DEEP vs. REGULAR Mode

MultAI has two research modes:

| | REGULAR Mode | DEEP Mode |
|---|---|---|
| **Speed** | 2-5 minutes | 10-30 minutes |
| **Depth** | Quick, focused answers | Thorough research with web browsing |
| **When to use** | Quick questions, fact-checking | Market research, competitive intelligence |
| **How to request** | Just ask your question | Include "deep" in your request |

> **Example (REGULAR):** "What is Terraform?"
>
> **Example (DEEP):** "Do a deep research on Terraform's enterprise features"

---

## Tips and Tricks

**Run fewer platforms for speed.** If you only need a quick answer, you can ask MultAI to use just a few platforms:
> "Use only Claude and ChatGPT to answer: What is Infrastructure as Code?"

**Check your budget before a big run.** Each AI platform has usage limits. Ask MultAI to show your remaining budget:
> "Show me the rate limit budget"

**Re-run a single failed platform.** If one platform didn't respond, you can re-run just that one:
> "Run the same question on just Perplexity"

**DEEP mode on ChatGPT and Claude takes time.** Deep Research on these platforms can take 10-20 minutes. This is normal — they're doing thorough web research behind the scenes.

**Reports are cumulative.** Each run creates a new folder. Your old reports are never overwritten or deleted.

---

## Troubleshooting

### Chrome won't connect

**What happened:** MultAI couldn't connect to your Chrome browser.

**Fix:** Close all Chrome windows completely, wait a few seconds, then try again. If that doesn't work, the research run will automatically launch a new Chrome instance.

### Rate limited

**What happened:** You've used up your free quota on one or more AI platforms.

**Fix:** Wait a while (usually a few hours), or check your budget with: "Show me the rate limit budget." MultAI automatically skips platforms that are over their limit.

### A platform returned no results

**What happened:** One of the seven AIs didn't respond or had an error.

**Fix:** This is normal — the other platforms' answers are still used. You can re-run just the failed platform if you want its input.

### Report viewer shows a blank page

**What happened:** The report viewer loaded before the file was ready, or the server isn't running.

**Fix:** Refresh the page. If that doesn't work, ask MultAI to reopen the report.

---

## Further Reading

| Resource | Description |
|----------|-------------|
| [CONTRIBUTOR-GUIDE.md](CONTRIBUTOR-GUIDE.md) | Technical reference for contributors — CLI details, platform internals, adding new platforms, tests, CI/CD |
| [GitHub Repository](https://github.com/alo-exp/multai) | Source code, issues, and releases |
| [Claude Code Documentation](https://docs.anthropic.com/en/docs/claude-code) | How to use Claude Code (the tool MultAI runs inside) |

---

*MultAI is open source. Built with Python, Playwright, and Claude Code.*
