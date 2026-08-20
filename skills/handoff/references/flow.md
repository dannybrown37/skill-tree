# How the pieces fit

Two diagrams: the lifecycle of a session under the hook, and who is allowed to write which
file. The rules they encode live in `SKILL.md` and `references/backlog.md` — this is the map.

## Session lifecycle

```mermaid
flowchart TD
    S([Session starts]) --> H["SessionStart hook<br/>handoff_session_start.sh"]
    H --> R{"resolve dir<br/>$HANDOFF_DIR → git root<br/>+ /docs/handoffs"}
    R -->|no repo| Z1([print nothing])
    R --> C{"CURRENT.md<br/>non-empty?"}

    C -->|yes| P1["inject CURRENT.md<br/>+ 'keep it current' line"]
    C -->|no| B{"BACKLOG.md<br/>has a ## title?"}
    B -->|no| Z2([print nothing])
    B -->|yes| P2["inject top item **title only**<br/>+ 'confirm with the user'"]

    P1 --> W[Work]
    P2 --> ASK{User confirms?}
    ASK -->|yes| POP["handoff pop"]
    ASK -->|no| W
    POP -->|"atomic: remove from BACKLOG.md<br/>+ write into CURRENT.md as next action"| W

    W --> T{Task done?}
    T -->|"surfaced work that isn't next"| ADD["handoff add / next<br/>→ BACKLOG.md"] --> W
    T -->|yes| WB["Write-back, same turn:<br/>NARRATIVE.md += claim + evidence + sha<br/>CURRENT.md := new next action + check"]
    WB --> MORE{More work?}
    MORE -->|yes| W
    MORE -->|"all done"| DEL["delete CURRENT.md<br/>NARRATIVE.md stays"] --> Z3([end])
    MORE -->|"context low / compaction"| S

    style POP fill:#2d5,color:#000
    style H fill:#59f,color:#000
```

## The three files and who writes them

```mermaid
flowchart LR
    subgraph FS["docs/handoffs/ (one per repo, resolved from cwd)"]
        CUR["CURRENT.md<br/><i>ephemeral re-entry prompt</i><br/>goal · anchor · read order ·<br/>in flight · ONE next action ·<br/>acceptance check · open questions"]
        NAR["NARRATIVE.md<br/><i>persistent, appended</i><br/>tried &amp; failed · decisions ·<br/>done+evidence · lessons"]
        BLG["BACKLOG.md<br/><i>queue, priority = order</i><br/>## title + body, fence-protected"]
    end

    A["Agent<br/>(Read/Write/Edit)"] -->|writes| CUR
    A -->|appends| NAR
    A -.->|"never hand-edits"| BLG

    CLI["handoff CLI<br/>add · next · remove · edit · path ·<br/>backlog · current · narrative ·<br/>pop · --version"] -->|"sole writer<br/>(re-renders whole file)"| BLG
    CLI -->|"pop only"| CUR
    A -->|invokes| CLI

    HOOK["SessionStart hook"] -->|reads| CUR
    HOOK -->|"reads first title<br/>(awk, no interpreter)"| BLG
    HOOK -->|stdout → context| A

    CUR -.->|points at| NAR
    CUR -.->|points at| REPO[("repo: code, tests,<br/>logs, diffs — referenced<br/>by path, never pasted")]

    style CLI fill:#2d5,color:#000
    style BLG fill:#fd6,color:#000
```

Invariants worth stating outright:

- `pop` is the only bridge from backlog to current, and it is never automatic.
- The hook reads; it never writes and never pops.
- `CURRENT.md` holds exactly one next action — everything else future-tense goes through
  `handoff add`.
