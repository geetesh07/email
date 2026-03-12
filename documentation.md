# Engineering Email Intelligence Tool — Documentation

Welcome to the documentation for the `engg-email-intel` tool. This guide explains how the tool works under the hood, what logic it uses to extract information, and the specific keywords and patterns it looks for.

---

## 1. How It Works (The Pipeline)

The tool processes emails in a structured, 5-step pipeline:

### Step 1: Ingestion
The tool reads raw email files (`.msg` from Outlook or standard `.eml` files). It extracts the sender, recipients (To/CC), date sent, subject, and the plain-text body of the email.

### Step 2: Cleaning & Deduplication
Before looking for specifications, the tool cleans the text to avoid false positives:
*   **Signatures:** It scans from the bottom up to find common signature markers (like "Best regards" or "--") and phone number patterns, stripping them out.
*   **Disclaimers:** It removes common legal disclaimers (e.g., "This email is confidential").
*   **Deduplication:** When an email replies to or forwards a previous email, the older text is typically included at the bottom. The tool hashes every paragraph it sees; if it sees the same paragraph again in a newer email, it ignores it. This ensures specs aren't counted twice.

### Step 3: Specification Extraction (Regex Engine)
The core of the tool is a Regular Expression (Regex) engine. It scans the cleaned text for specific patterns of numbers followed by engineering units. For example, it looks for a number, optional decimals, optional spaces, and then "Nm" to identify Torque. 
*(See section 2 for the exact patterns).*

### Step 4: Sentence Tagging & Unresolved Items
Not all engineering data follows a strict "Number + Unit" format. 
*   **Sentence Tagging:** The tool splits the text into sentences and searches for Engineering Keywords (e.g., "gearbox", "mounting"). If it finds one, it extracts that sentence plus the sentence before and after it for context.
*   **Unresolved Items:** It specifically flags sentences that sound like questions or pending decisions by looking for "Unresolved Markers" (e.g., "?", "TBD").

### Step 5: People Mapping & Summarization
*   **People:** It builds a roster of everyone in the thread, deduces their company from their email domain, and tries to guess their role (e.g., "Engineer", "Sales") by looking at their signature block.
*   **Summarization:** Finally, it takes all extracted specs, open items, and people, and generates an Executive Summary and interactive reports.

---

## 2. What We Extract (Categories & Patterns)

The Regex engine looks for 14 specific categories of engineering data. Here is exactly what it looks for:

| Category | Pattern Logic (Simplified) | Example Matches |
| :--- | :--- | :--- |
| **Dimensions** | Number + `mm`, `cm`, `m`, `inch`, `in`, `"` | `100mm`, `4.5 inch`, `3/4"` |
| **Torque** | Number + `Nm`, `N.m`, `kNm`, `lb-ft`, `lbf.ft`, `oz-in` | `450 Nm`, `50 lb-ft` |
| **Speed / RPM** | Number + `RPM`, `rpm`, `r/min`, `rad/s` | `1450 RPM`, `120 rpm` |
| **Power** | Number + `W`, `kW`, `MW`, `HP`, `hp`, `bhp` | `7.5 kW`, `10 HP` |
| **Pressure** | Number + `bar`, `psi`, `Pa`, `kPa`, `MPa`, `atm` | `2.5 bar`, `100 psi` |
| **Temperature**| Number (can be negative) + `°C`, `°F`, `degC`, `degF`, `K` | `55°C`, `-10 degC` |
| **Voltage** | Number + `V`, `kV`, `mV`, `VAC`, `VDC` | `415 VAC`, `12V` |
| **Current** | Number + `A`, `mA`, `kA`, `Amps`, `Amp` | `15 A`, `100mA` |
| **Weight/Mass**| Number + `kg`, `g`, `lbs`, `lb`, `ton`, `tonne` | `92 kg`, `5 lbs` |
| **Tolerance** | `±`, `+`, `-`, `+/-` + Number + `mm`, `%`, `µm`, `micron` | `±0.05mm`, `+/-2%` |
| **Thread/Bolt**| `M` + Number + Optional (`x` or `×` + Number) | `M16`, `M12 × 1.5` |
| **Standards** | `IS`, `ISO`, `ASTM`, `IP`, `NEMA`, `IEC`, etc. + Numbers | `IS 325`, `ISO 6336` |
| **IP Rating** | `IP` + 2 Digits | `IP55`, `IP65` |
| **Efficiency Class**| `IE1`, `IE2`, `IE3`, `IE4`, `EFF1`, `EFF2`, `EFF3` | `IE3`, `EFF1` |

---

## 3. Keywords Mentioned (config.yaml)

The tool relies heavily on lists defined in the `config.yaml` file. These can be easily updated or expanded by editing that file. By default, here are the words chosen:

### A. Material Keywords
We scan for exact mentions of these materials:
*   `SS316`, `SS304`, `SS316L`, `EN8`, `EN19`, `EN24`, `EN31`
*   `mild steel`, `carbon steel`, `stainless steel`, `cast iron`
*   `aluminium 6061`, `aluminum 6061`, `aluminium 7075`
*   `brass`, `bronze`, `copper`, `titanium`, `inconel`
*   `hardened`, `galvanized`, `chrome plated`, `nitrided`, `case hardened`, `heat treated`
*   `POM`, `PTFE`, `nylon`, `PEEK`, `Delrin`

### B. Engineering Trigger Keywords
Sentences containing these words are pulled out for context:
*   `torque`, `RPM`, `speed`, `load`, `force`, `pressure`, `flow`
*   `dimension`, `length`, `width`, `height`, `diameter`, `bore`
*   `material`, `coating`, `finish`, `hardness`, `tensile`
*   `temperature`, `ambient`, `rated`, `capacity`, `efficiency`
*   `mounting`, `flange`, `shaft`, `coupling`, `gearbox`
*   `IP rating`, `protection class`, `duty cycle`
*   `certification`, `approval`, `compliance`, `standard`
*   `delivery`, `drawing`, `revision`
*   `power`, `voltage`, `current`, `weight`, `mass`, `tolerance`
*   `thread`, `bolt`, `nut`, `seal`, `bearing`, `lubrication`, `vibration`, `alignment`, `backlash`, `clearance`, `runout`

### C. Unresolved Markers
Sentences containing these words are flagged as Action Items / Pending Decisions:
*   `?` (Question mark)
*   `confirm`, `TBD`, `tbd`, `pending`
*   `to be decided`, `to be confirmed`, `yet to be`
*   `need to check`, `awaiting`, `not yet finalized`, `open item`

### D. Signature Detecion & Roles
To cut out signatures, we look for lines starting with words like:
*   `--`, `Best regards`, `Kind regards`, `Regards`, `Sincerely`, `Sent from my`, `Get Outlook for`

To figure out someone's job role, we look in their signature block for:
*   `engineer`, `manager`, `director`, `sales`, `purchase`, `procurement`, `technical`, `design`, `project`, `head`, `lead`, `chief`, `senior`, `junior`, `executive`, `officer`, `VP`, `CEO`, `CTO`, `COO`, `MD`, `GM`
