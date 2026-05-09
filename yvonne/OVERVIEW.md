# Yvonne — Personal AI Assistant for Gladys

A quick walkthrough of how the assistant works, what's built today, and where
new things plug in. Nothing here runs without your say-so on improvements.

---

## 1. Big picture

You talk to **Yvonne** in Telegram. Yvonne is the only agent you ever speak
to. Behind her are five specialist sub-agents she delegates to. She reviews
their work before showing you anything.

```mermaid
flowchart LR
    Gladys((👤 Gladys)) -->|Telegram| Yvonne[🤖 Yvonne<br/>Founder Agent]
    Yvonne --> Memory[(🧠 Memory<br/>Profile + Vector Store)]
    Yvonne --> Clients[👥 Clients Agent]
    Yvonne --> Policies[📑 Policies Agent]
    Yvonne --> Followups[📅 Follow-ups Agent]
    Yvonne --> Email[✉️ Email Drafter]
    Yvonne --> Files[📂 Files Agent]
    Yvonne --> Improver[💡 Improvement Agent]

    Memory -.reads/writes.-> Yvonne
    Clients -.draft.-> Yvonne
    Policies -.draft.-> Yvonne
    Followups -.draft.-> Yvonne
    Email -.draft.-> Yvonne
    Files -.draft.-> Yvonne
    Improver -.proposals.-> Yvonne

    Yvonne -->|reviewed reply| Gladys
```

**Key rule:** every sub-agent output passes through Yvonne first. She
sanity-checks tone, accuracy, and completeness before you see it.

---

## 2. What happens on every message

```mermaid
flowchart TD
    A[Gladys sends a message] --> B{Profile mostly empty?}
    B -- yes --> C[Onboarding mode<br/>weave in 1 question]
    B -- no --> D[Read profile + memory<br/>build context]
    C --> D
    D --> E{Does it need a sub-agent?}
    E -- no --> F[Reply directly]
    E -- yes --> G[Call sub-agent]
    G --> H[Review output<br/>tone · facts · completeness]
    H --> I{Good enough?}
    I -- no --> G
    I -- yes --> F
    F --> J[Save anything worth remembering<br/>profile / rule / note]
    J --> K[Reply to Gladys]
```

**What gets remembered automatically:**
- Stable facts (her company, products, work style) → profile
- Hard rules ("never quote without confirming the schedule") → rules list
- One-off context worth recalling later (preferences, decisions, client
  quirks) → vector store for semantic search

---

## 3. The improvement loop (manual approval)

This is the "come up with new agents every day" part. Yvonne only proposes;
Gladys decides.

```mermaid
flowchart TD
    A["Gladys taps /improve<br/>(or asks 'what should we add?')"] --> B[Improver reads<br/>last 7 days of memory]
    B --> C[Claude proposes<br/>1–3 concrete ideas]
    C --> D[Each saved as<br/>status = pending]
    D --> E["Gladys reviews via /proposals"]
    E --> F{Decision}
    F -- approve --> G[status = approved<br/>queued for build]
    F -- reject --> H[status = rejected]
    F -- build now --> I[status = built<br/>after Claude implements]
    G -.you tell us when.-> I
```

Each proposal includes:
- **title** — short name
- **problem** — what pain it addresses
- **evidence** — quote/paraphrase from your memory that justifies it
- **proposal** — what to build, named tools
- **effort** — S / M / L
- **value** — why you'll care

**Nothing is built without you saying so.**

---

## 4. What's available today

| Sub-agent | What it does | Examples |
|-----------|--------------|----------|
| 👥 **Clients** | CRM. Add clients, log calls/visits, look up history. | "Add Tan Wei Ming, prospect, age 32." "What did I tell Mrs Lim last time?" |
| 📑 **Policies** | Library of products and policies you can compare. | "What term plans do we have under \$200/mo?" "Compare AIA Gen X vs PRUactive." |
| 📅 **Follow-ups** | Track who needs a follow-up and when. Surface what's due. | "Remind me to call Mr Chen on Friday about his renewal." `/today` |
| ✉️ **Email Drafter** | Drafts messages in your voice, reviewed by Yvonne before showing you. | "Draft a follow-up to John saying his quote is ready." |
| 📂 **Files** | Sandboxed workspace. Read, write, search documents. | "Save this script under prospecting/cold_call_v3.txt." |
| 💡 **Improvement** | Daily: proposes new tools or sub-agents based on patterns. | `/improve` |
| 🧠 **Memory** | Learns about you over time. Profile + semantic vector store. | "Remember: I never cold-call on Mondays." |

Telegram commands: `/today`, `/clients`, `/improve`, `/proposals`, `/reset`.

---

## 5. Where new things plug in

```mermaid
flowchart LR
    Idea[New idea<br/>from /improve or Gladys] --> Code[Build the sub-agent<br/>under yvonne/agents/]
    Code --> Tool[Register a tool<br/>in yvonne/founder.py]
    Tool --> Yvonne2[🤖 Yvonne can now call it]
```

Adding a new sub-agent is a single file + a tool registration. Memory and
the review pattern are already wired in for free.

---

## 6. Questions to ask Gladys

When you show her this:

1. **What does she want Yvonne to do FIRST every morning?**
   (e.g. summarise overnight WhatsApp, list follow-ups due, prep her day)
2. **How does she want to capture client info?**
   (voice note? typing? forwarding emails? photographing namecards?)
3. **What does her current workflow look like end-to-end** —
   from prospecting to closing to renewal — so we know where the gaps are.
4. **Anything she NEVER wants Yvonne to do?**
   (auto-send messages, auto-quote prices, share data with anyone, etc.)
5. **Which sub-agent feels most useful to start with?** Pick one and we
   build that out properly before adding more.
