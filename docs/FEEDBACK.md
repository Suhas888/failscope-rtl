# Providing Feedback on FailScope RTL

We actively seek feedback from FPGA developers and RTL verification engineers evaluating FailScope RTL on their regression logs.

---

> [!WARNING]
> **Confidentiality Warning**: Never upload or paste proprietary RTL source code, confidential regression logs, internal corporate paths, credentials, or personal information. Always sanitize your logs with generic names (e.g. `dut.v`, `counter_tb`, `0xDEADBEEF`) before sharing.

---

## Issue Template

When submitting feedback or reporting grouping issues, please use the following template:

```markdown
### 1. Environment & Tool Version
- FailScope Version (`failscope version`):
- Python Version (`python --version`):
- Operating System (Windows / Linux / macOS):
- Simulator / Test Runner (Verilator / UVM / Cocotb / Other):

### 2. Sanitized Log Excerpt
<!-- Paste 3-10 sanitized lines demonstrating the error format (NO proprietary code) -->
```text
[Paste sanitized error lines here]
```

### 3. Command Executed
<!-- Example: failscope analyze sanitized.log --out report.html -->
```bash

```

### 4. Grouping Behavior
- **Observed Grouping**: What clusters did FailScope generate? (e.g., merged unrelated errors into Cluster 0; split identical assertion into 5 clusters)
- **Expected Grouping**: How should an experienced verification engineer group these failures?

### 5. Reproducible Steps
1. ...
2. ...

### 6. Additional Context / Suggestions
- 
```
