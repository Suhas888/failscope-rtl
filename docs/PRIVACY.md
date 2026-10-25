# FailScope RTL — Privacy & Data Handling Policy

## 1. Summary

FailScope RTL is a **local-first, fully offline research prototype**. It does not collect telemetry, track usage, or transmit logs or RTL source code to any external server or third-party service.

---

## 2. Code Inspection Findings

The core implementation in `src/failscope/` was audited for network activity, external service calls, and background telemetry:

- **Zero Network Libraries**: Neither `requests`, `urllib.request`, `httpx`, `aiohttp`, `socket`, nor cloud SDKs are imported anywhere in the core package.
- **Zero Telemetry / Analytics**: No usage trackers, analytics beacons, crash-reporting daemons, or telemetry hooks are present.
- **Local Standard Library Processing**: Ingestion and parsing rely exclusively on Python's standard library (`re`, `xml.etree.ElementTree`, `pathlib`) and local scientific computing libraries (`numpy`, `scikit-learn`).
- **No Native Code Execution from Logs**: Log parsing is strictly lexical. Error lines and XML tags are parsed as text strings; no code found inside logs is evaluated or executed.

---

## 3. Runtime Verification Findings

The runtime behavior of FailScope RTL was verified across all CLI commands (`doctor`, `parse`, `analyze`, `compare`, `benchmark`, `evaluate`):

- **Offline Execution**: Verified that all CLI commands execute normally when completely disconnected from the internet.
- **Local File I/O Only**: File operations are strictly confined to reading the specified input files and writing reports to the user-specified `--out` directory.
- **Self-Contained HTML Reports**: Generated HTML reports use inline styles and inline SVG assets. They make zero outbound requests for external fonts, CDNs, or JavaScript libraries. Reports can be opened in a browser with the network disabled.

---

## 4. Proprietary RTL Protection

- **No HDL Source Access Required**: FailScope RTL inspects only post-simulation text output logs and standard JUnit XML files. It does not parse, modify, or require access to your SystemVerilog, Verilog, or VHDL design files.
- **Non-Destructive**: All input files are opened in read-only mode (`r` with UTF-8 encoding). Input files are never overwritten or deleted.

---

## 5. User Responsibility when Reporting Issues

When sharing sample logs, bug reports, or feature requests on public forums or GitHub issues:
- **Sanitize Proprietary Data**: Ensure that internal hostnames, corporate directory paths, proprietary module/signal names, and IP block names are replaced with generic placeholders (e.g., `dut.v:42`, `tb_top`, `0xDEADBEEF`).
- **Never Upload Credentials**: Never paste environment variables, tokens, or credentials into public issue reports.
