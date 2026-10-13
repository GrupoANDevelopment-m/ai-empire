# Tutorial: first-chat First Chat

## Overview
This tutorial walks you through first chat in AI Empire.

## Prerequisites
- AI Empire installed (see [Quickstart](01-quickstart.md))
- Basic understanding of LLMs and APIs
- A terminal with bash

## Time Required
~15 minutes

## Steps

### Step 1: Prepare your environment
```bash
git clone https://github.com/GrupoANDevelopment-m/ai-empire
cd ai-empire
./install.sh
```

### Step 2: Configure
```bash
cp .env.example .env
# Edit .env with your keys
nano .env
```

### Step 3: Run
```bash
./empire chat
```

## What You Learned
- How to install AI Empire
- How to configure LLM providers
- How to run the chat interface

## Next Steps
- [Tutorial 02: Your First Chat](02-first-chat.md)
- [Tutorial 03: Adding a Custom Skill](03-add-skill.md)

## Troubleshooting
If you encounter issues, check the [FAQ](../faq.md) or open an issue on GitHub.
