---
title: "Ricardo Martins | About me and my projects"
description: "A short introduction to my background and the projects I build. Read about me below, or explore how I use AI in practice."
url: "/anthropic/"
layout: "resume"
params:
  pdfAsset: "documents/anthropic.pdf"
  pdfDownloadName: "ricardo-martins-anthropic.pdf"
build:
  list: never
  render: always
sitemap:
  disable: true
outputs:
  - HTML
---

## Selected projects: how I build with AI

Examples of my work, with details on my contribution and where AI fits.

I have built projects that use LLMs for editorial workflows and agent-guided operations, as well as products developed with AI assistance. I distinguish between models that power a product's functionality and AI tools I use to build it. Some of my projects use conventional software or publish learning materials. You can browse the full collection on [my projects page](https://rmmartins.com/projects).

### Decodifica.Tech

For [Decodifica.Tech](https://decodifica.tech), I built a pipeline that collects technology news, removes duplicates, and selects material for Portuguese-language editions. Integrations with OpenAI, Groq, and Azure OpenAI turn those sources into articles with added context and podcast scripts; speech synthesis produces the audio. Readers consume the resulting publication rather than interacting with a chatbot.

### Azure SRE Agent Skills

I authored [eight Azure SRE Agent Skills](https://github.com/ricmmartins/azure-sre-agent-skills). My contribution was translating operational procedures into instructions: which evidence to gather, which tools to use, what to check, and how to organize recommendations. Users import the skills into Azure SRE Agent and request assessments of costs, governance, capacity, architecture, incidents, or AI environments. The host agent interprets the instructions and works with the available data. It does not apply suggested changes automatically.

### Startup-Scale Landing Zone

For [Startup-Scale Landing Zone](https://startupscalelanding.zone), I built an optional Copilot CLI agent that asks founders about their workload, reads project context, and helps translate requirements into an infrastructure plan. The LLM handles the conversation and explanations; scripts implement structured planning decisions. The agent runs locally from the `agent-aware` branch, separately from the website.

### AKS Newsletter

For [AKS Newsletter](https://aksnewsletter.com), I built source collection, organization rules, prompts, validation, and publication tooling. LLMs improve descriptions of collected updates. The workflow preserves source links and creates a pull request for review before publication.

### Azure Feed

I built [Azure Feed](https://azurefeed.news) to help engineers follow Azure and Microsoft developer updates without checking dozens of blogs individually. A scheduled GitHub Actions workflow collects RSS feeds daily, removes duplicate entries, and organizes articles from the last 30 days into a structured dataset. A lightweight frontend on GitHub Pages presents a searchable feed. Readers can filter by category or date, bookmark articles locally, and follow links to the original publications. I used AI assistance during development; the core collection and browsing features run through conventional automation.

### PeerSpect and AI-assisted development

I also use AI-assisted development for products such as [PeerSpect](https://www.peerspect.app). In PeerSpect, feedback comes from people. AI assisted the development rather than assessing users or interpreting their comments.

Across the LLM-enabled projects, I focus on connecting models with source data and operational tools, writing clear instructions, and keeping review steps in the workflow. The examples above show where I use models and where conventional software or human judgment does the work.
