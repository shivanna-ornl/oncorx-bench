"""
OncoRx-Bench: Clinical text templates for benchmark generation.

Each template is a string with placeholders (wrapped in {braces}) that get
filled by the generator from the drug/regimen knowledge base.

Templates are grouped by category/subcategory and indexed for random selection.
"""

# ═══════════════════════════════════════════════════════════════════════
# C1 — Core Medication Extraction
# ═══════════════════════════════════════════════════════════════════════

# C1.1 — Single drug, simple mention
C1_1_TEMPLATES = [
    "Patient is currently taking {drug1}.",
    "Continue {drug1} as previously prescribed.",
    "Start {drug1} today.",
    "The patient was started on {drug1}.",
    "Recommend initiation of {drug1}.",
    "{drug1} was administered during today's visit.",
    "Plan: begin {drug1}.",
    "Patient reports taking {drug1} at home.",
    "Per oncology, continue {drug1}.",
    "Discussed starting {drug1} with the patient.",
    "Assessment/Plan: {drug1} for treatment.",
    "Patient seen in clinic today, currently on {drug1}.",
    "Pt currently receiving {drug1}.",
    "Treatment: {drug1}.",
    "Medications: {drug1}.",
    "{drug1} initiated per protocol.",
    "Oncology recommends {drug1}.",
    "Patient tolerating {drug1} well.",
    "Please continue {drug1}.",
    "Will proceed with {drug1}.",
    "Home medications include {drug1}.",
    "Current therapy: {drug1}.",
    "Active medication: {drug1}.",
    "Patient has been on {drug1} since last visit.",
    "Resume {drug1} after hold period.",
    "Initiate therapy with {drug1} as discussed.",
    "Patient to continue on {drug1} per treatment plan.",
    "Currently maintained on {drug1}.",
    "Ongoing treatment: {drug1}.",
    "The patient is scheduled to receive {drug1}.",
]

# C1.2 — Single drug with dose and/or route
C1_2_TEMPLATES = [
    "Start {drug1} {dose1} {route1}.",
    "{drug1} {dose1} {route1} {freq1}.",
    "Administer {drug1} {dose1} {route1}.",
    "Patient receiving {drug1} {dose1} {route1} {freq1}.",
    "Rx: {drug1} {dose1} {route1} {freq1}.",
    "Give {drug1} {dose1} {route1} {freq1}.",
    "Continue {drug1} at {dose1} {route1} {freq1}.",
    "Plan: {drug1} {dose1} {route1} {freq1}.",
    "{drug1} {dose1} given {route1} today.",
    "Order: {drug1} {dose1} {route1} {freq1}.",
    "Medication list: {drug1} {dose1} {route1} {freq1}.",
    "Patient taking {drug1} {dose1} {route1} {freq1} at home.",
    "Started {drug1} {dose1} {route1} per protocol.",
    "Dose: {drug1} {dose1} {route1}. Verify with pharmacy.",
    "Current dose: {drug1} {dose1} {route1}.",
    "Adjusted {drug1} to {dose1} {route1} {freq1}.",
    "Increase {drug1} to {dose1} {route1} {freq1}.",
    "Chemotherapy order: {drug1} {dose1} {route1} {freq1}.",
    "Pre-medications followed by {drug1} {dose1} {route1}.",
    "Infuse {drug1} {dose1} {route1} over 60 minutes.",
    "Patient received {drug1} {dose1} {route1} without adverse reaction.",
    "Begin {drug1} at {dose1} {route1} {freq1}.",
    "Prescribe {drug1} {dose1} {route1} {freq1}; follow up in 2 weeks.",
    "Pharmacy to dispense {drug1} {dose1} for {route1} administration.",
    "Treatment initiated: {drug1} {dose1} {route1} {freq1}.",
]

# C1.3 — Two drugs mentioned together
C1_3_TEMPLATES = [
    "Patient is on {drug1} and {drug2}.",
    "Start {drug1} and {drug2}.",
    "Continue {drug1} and {drug2} as prescribed.",
    "Current medications include {drug1} and {drug2}.",
    "The patient was started on {drug1} along with {drug2}.",
    "Administer {drug1} followed by {drug2}.",
    "Treatment: {drug1} and {drug2}.",
    "Plan: {drug1} {dose1} {route1}, {drug2} {dose2} {route2}.",
    "Patient receiving {drug1} in combination with {drug2}.",
    "Rx: {drug1} {dose1} and {drug2} {dose2}.",
    "Today's chemo: {drug1} and {drug2}.",
    "{drug1} and {drug2} administered per protocol.",
    "Oncology recommends {drug1} plus {drug2}.",
    "Initiate {drug1} and {drug2} concurrently.",
    "Begin {drug1} {dose1} {route1} and {drug2} {dose2} {route2}.",
    "The regimen includes {drug1} and {drug2}.",
    "Active medications: {drug1}, {drug2}.",
    "Dual therapy with {drug1} and {drug2}.",
    "Combination therapy: {drug1} + {drug2}.",
    "Patient was given {drug1} and {drug2} on Day 1.",
    "Will add {drug2} to current {drug1}.",
    "Home meds: {drug1} daily, {drug2} daily.",
    "Both {drug1} and {drug2} to continue.",
    "Started on {drug1} {dose1} and {drug2} {dose2} today.",
    "Give {drug1} then {drug2} sequentially.",
]

# C1.4 — Supportive care medications (antiemetics, growth factors, etc.)
C1_4_TEMPLATES = [
    "Pre-medicate with {drug1} {dose1} {route1} 30 minutes prior to chemotherapy.",
    "Antiemetic: {drug1} {dose1} {route1} PRN.",
    "Give {drug1} {dose1} {route1} as prophylaxis before chemo.",
    "Supportive care: {drug1} {dose1} {route1} and {drug2} {dose2} {route2}.",
    "Patient to receive {drug1} for supportive care starting day 2.",
    "{drug1} {dose1} {route1} as supportive care during chemotherapy.",
    "Post chemo: {drug1} {dose1} {route1} PRN.",
    "Administer {drug1} {dose1} {route1} as premedication.",
    "Prescribe {drug1} {dose1} {route1} for prophylaxis.",
    "Supportive medication: {drug1} {dose1} {route1} starting 24 hours after chemo.",
    "PRN medications: {drug1} {dose1} and {drug2} {dose2}.",
    "Supportive care includes {drug1} and {drug2}.",
    "Patient taking {drug1} {dose1} {route1} for supportive care.",
    "Start {drug1} {dose1} {route1} for supportive care during chemotherapy.",
    "Continue {drug1} {dose1} {route1} for prophylaxis.",
    "PRN: {drug1} {dose1} {route1} as needed.",
    "Supportive: {drug1} {dose1} {route1} daily.",
    "Give {drug1} {dose1} and {drug2} {dose2} as premedication for {drug3} infusion.",
    "Continue supportive care with {drug1} {dose1} {route1}.",
    "Prescribe {drug1} {dose1} {route1} PRN for symptom management.",
]


# ═══════════════════════════════════════════════════════════════════════
# C2 — Attributes & Instruction Complexity
# ═══════════════════════════════════════════════════════════════════════

# C2.1 — Full dose + route + frequency
C2_1_TEMPLATES = [
    "{drug1} {dose1} {route1} {freq1}. Follow CBC weekly.",
    "Order: {drug1} {dose1} via {route1} {freq1}. Administer over {infusion_time}.",
    "{drug1} {dose1} {route1} {freq1}. Pre-medicate with {drug2} {dose2} {route2}.",
    "Current regimen: {drug1} {dose1} {route1} {freq1}.",
    "Give {drug1} {dose1} {route1}. Repeat {freq1}.",
    "Pharmacy: Please prepare {drug1} {dose1} {route1} {freq1}.",
    "Cycle {cycle_num}: {drug1} {dose1} {route1} {freq1}, Day {cycle_day}.",
    "Chemotherapy: {drug1} {dose1} {route1}, then {drug2} {dose2} {route2}, {freq1}.",
    "{drug1} {dose1} {route1} {freq1}. Hold if ANC < 1000.",
    "Treatment plan: {drug1} {dose1} {route1} {freq1} for 6 cycles.",
    "Begin {drug1} at {dose1} {route1} {freq1}. Renal dosing per CrCl.",
    "Infuse {drug1} {dose1} {route1} over {infusion_time}, {freq1}.",
    "Rx: {drug1} {dose1} {route1} {freq1}. Disp: 30 tablets. Refills: 2.",
    "{drug1} {dose1} {route1} {freq1} on treatment days only.",
    "Dose adjusted to {drug1} {dose1} {route1} {freq1} due to toxicity.",
    "Standard dosing: {drug1} {dose1} {route1} {freq1}.",
    "Patient to receive {drug1} {dose1} {route1} {freq1}; infuse over {infusion_time}, repeat cycle q3w.",
    "Verified order: {drug1} {dose1} {route1} {freq1}. BSA = 1.85m2.",
    "Per protocol: {drug1} {dose1} {route1} x{num_doses} doses {freq1}.",
    "Medication reconciliation: {drug1} {dose1} {route1} {freq1}, confirmed with patient.",
]

# C2.2 — Titration and taper instructions
C2_2_TEMPLATES = [
    "Start {drug1} {dose1_high} {route1} daily x 5 days, then {dose1_med} daily x 5 days, then {dose1_low} daily x 5 days, then stop.",
    "Taper {drug1}: {dose1_high} x 1 week, {dose1_med} x 1 week, {dose1_low} x 1 week, then discontinue.",
    "{drug1} taper: {dose1_high} {route1} daily for 3 days, decrease to {dose1_med} for 3 days, then {dose1_low} for 3 days.",
    "Initiate {drug1} at {dose1_low} {route1} daily, increase to {dose1_med} after 1 week if tolerated, then {dose1_high} at week 3.",
    "Titrate {drug1} up: Week 1: {dose1_low}, Week 2: {dose1_med}, Week 3: {dose1_high} {route1}.",
    "Ramp-up schedule for {drug1}: {dose1_low} daily x 7 days → {dose1_med} daily x 7 days → {dose1_high} daily ongoing.",
    "Dexamethasone taper following {drug1} infusion: 40 mg PO day 1, 20 mg day 2-3, 10 mg day 4, then stop.",
    "{drug1} dose escalation: Start {dose1_low} {route1}, increase by {dose1_increment} every 2 weeks to target {dose1_high}.",
    "Gradually taper {drug1} over 4 weeks: reduce by {dose1_increment} per week from {dose1_high}.",
    "Start {drug1} at {dose1_low} {route1} daily; if no grade ≥2 toxicity by day 14, escalate to {dose1_med}; if tolerated, escalate to {dose1_high} at day 28.",
    "{drug1} taper: {dose1_high} {route1} daily x 4d, then {dose1_med} daily x 4d, then {dose1_low} daily x 4d.",
    "Slow taper: {drug1} {dose1_high} {route1} x2 weeks, then decrease by {dose1_increment} every week until off.",
    "{drug1} taper post-chemo: {dose1_high} daily x 3 days, {dose1_med} daily x 3 days, {dose1_low} daily x 3 days, then off.",
    "Step-wise increase of {drug1}: {dose1_low} for cycle 1, {dose1_med} for cycle 2, {dose1_high} for subsequent cycles if tolerated.",
    "Cross-taper: reduce {drug1} from {dose1_high} to {dose1_low} over 3 weeks while initiating {drug2} at {dose2}.",
]

# C2.3 — PRN / conditional dosing
C2_3_TEMPLATES = [
    "{drug1} {dose1} {route1} every {prn_interval} PRN {prn_reason}.",
    "Give {drug1} {dose1} {route1} as needed for {prn_reason}. Max {max_daily} per day.",
    "{drug1} {dose1} {route1} PRN {prn_reason}. Do not exceed {max_daily} in 24 hours.",
    "If {prn_reason}, administer {drug1} {dose1} {route1}.",
    "{drug1} {dose1} {route1} PRN {prn_reason}; call MD if more than {max_doses} doses needed.",
    "Breakthrough {prn_reason}: {drug1} {dose1} {route1} q{prn_interval} PRN.",
    "Use {drug1} {dose1} {route1} only if {prn_reason}.",
    "PRN orders: {drug1} {dose1} {route1} for {prn_reason}, {drug2} {dose2} {route2} for {prn_reason2}.",
    "{drug1} {dose1} {route1} as needed. Use {drug2} {dose2} {route2} if {drug1} ineffective.",
    "Rescue medication: {drug1} {dose1} {route1} PRN {prn_reason}.",
    "Administer {drug1} if patient develops {prn_reason}.",
    "{drug1} {dose1} {route1} q{prn_interval} PRN, not to exceed {max_daily} daily.",
    "For mild {prn_reason}: {drug1} {dose1} {route1}. For severe: {drug2} {dose2} {route2}.",
    "Standing: {drug1} {dose1} {route1} {freq1}. PRN: {drug2} {dose2} {route2} q{prn_interval} for {prn_reason}.",
    "Sliding scale {drug1}: {dose1_low} for mild, {dose1_med} for moderate, {dose1_high} for severe {prn_reason}.",
]

# C2.4 — Duration and stop instructions
C2_4_TEMPLATES = [
    "{drug1} {dose1} {route1} {freq1} x {duration}.",
    "Start {drug1} {dose1} {route1}. Continue for {duration}, then reassess.",
    "{drug1} to be given for {duration} total. Review at end of course.",
    "Complete {duration} course of {drug1} {dose1} {route1}.",
    "Give {drug1} for {num_cycles} cycles, then stop and restage.",
    "Continue {drug1} until disease progression or unacceptable toxicity.",
    "{drug1} {dose1} {route1} {freq1} for {duration}. Stop if {stop_condition}.",
    "Treatment duration: {drug1} x {num_cycles} cycles ({duration}), then maintenance with {drug2}.",
    "Time-limited therapy: {drug1} {dose1} {route1} {freq1} for {duration}.",
    "Discontinue {drug1} after {duration} regardless of response.",
    "{drug1} {dose1} {route1} {freq1} x {duration}. If CR achieved, stop. If not, continue for additional {duration}.",
    "Give {drug1} for 2 years or until relapse, whichever comes first.",
    "Stop {drug1} on {stop_date}. Begin {drug2} the following week.",
    "Administer {drug1} {dose1} {route1} on days 1-{last_day} of each {cycle_length}-day cycle x {num_cycles} cycles.",
    "{drug1} to be completed by {stop_date}. Total planned duration: {duration}.",
]


# ═══════════════════════════════════════════════════════════════════════
# C3 — Regimen & Oncology-Style Complexity
# ═══════════════════════════════════════════════════════════════════════

# C3.1 — Multi-drug regimen with explicit drugs
C3_1_TEMPLATES = [
    "Chemotherapy regimen: {drug1} {dose1} {route1} Day 1, {drug2} {dose2} {route2} Day 1, {drug3} {dose3} {route3} Days 1-3. Repeat q{cycle_length}w x {num_cycles} cycles.",
    "Patient to receive {drug1}, {drug2}, and {drug3} per {regimen_name} protocol.",
    "Day 1: {drug1} {dose1} {route1}, {drug2} {dose2} {route2}. Day 8: {drug3} {dose3} {route3}. Cycle q{cycle_length}w.",
    "Initiate {regimen_name}: {drug1} {dose1} IV Day 1, {drug2} {dose2} IV Day 1, {drug3} {dose3} {route3} Days 1-14, q{cycle_length}w.",
    "Multi-agent chemo: {drug1} + {drug2} + {drug3} starting today.",
    "Begin combination therapy with {drug1}, {drug2}, {drug3}, and {drug4}.",
    "Protocol: {drug1} {dose1} {route1}, {drug2} {dose2} {route2}, repeat every {cycle_length} weeks for {num_cycles} cycles.",
    "Ordered: {regimen_name} – {drug1} {dose1} IV, {drug2} {dose2} IV, {drug3} {dose3} IV on Day 1.",
    "Treatment plan: {drug1} / {drug2} / {drug3}, {num_cycles} cycles planned.",
    "Cycle {cycle_num} of {regimen_name}: {drug1} {dose1} {route1} D1, {drug2} {dose2} {route2} D1, {drug3} {dose3} {route3} D1.",
    "Starting {regimen_name} consisting of {drug1} {dose1}, {drug2} {dose2}, and {drug3} {dose3}.",
    "The patient will receive combination {drug1}/{drug2}/{drug3} every {cycle_length} weeks.",
    "Chemo cycle: {drug1} {dose1} IV push, then {drug2} {dose2} IV over 2 hours, then {drug3} {dose3} IV over 46 hours continuous infusion.",
    "{drug1} {dose1} {route1} + {drug2} {dose2} {route2} + {drug3} {dose3} {route3}. Repeat cycle q{cycle_length}w.",
    "Multi-drug order: {drug1} administered first, followed by {drug2}, then {drug3} per {regimen_name} protocol.",
]

# C3.2 — Regimen acronym only (drugs must be resolved from KB)
C3_2_TEMPLATES = [
    "Start {regimen_name} for cycle 1 today.",
    "Plan: {regimen_name} x {num_cycles} cycles, q{cycle_length}w.",
    "Patient to begin {regimen_name}.",
    "Initiate {regimen_name} per standard protocol.",
    "Cycle {cycle_num} of {regimen_name} administered today.",
    "Continue {regimen_name}. Next cycle due in {cycle_length} weeks.",
    "Oncology recommends {regimen_name} for newly diagnosed {condition}.",
    "Begin {regimen_name} for {intent} treatment of {condition}.",
    "Status: Day 1 cycle {cycle_num} {regimen_name}.",
    "Chemotherapy: {regimen_name}. Treatment plan: {num_cycles} cycles.",
    "Patient completed cycle {cycle_num} of {regimen_name} without significant toxicity.",
    "Switching from {regimen_name_prev} to {regimen_name} due to progression.",
    "Restaging after cycle {cycle_num} of {regimen_name} shows partial response.",
    "IMP: {condition}. Plan: {regimen_name} {intent} chemotherapy.",
    "Assessment: Patient with {condition} s/p {cycle_num} cycles of {regimen_name}.",
    "Recommend: {regimen_name} as {intent} therapy for {condition}.",
    "Will proceed with {regimen_name}. Consent obtained.",
    "Discussed {regimen_name} with patient. Risks, benefits, alternatives reviewed.",
    "Previous treatment: {regimen_name_prev}. Now starting: {regimen_name}.",
    "Standard of care for {condition} is {regimen_name}.",
]

# C3.3 — Regimen with partial drug listing
C3_3_TEMPLATES = [
    "{regimen_name} ({partial_drugs} and other agents) cycle {cycle_num}.",
    "Patient receiving {regimen_name}. Today's infusion: {partial_drugs}.",
    "Day 1 of {regimen_name}: gave {partial_drugs} only. Will give remaining agents Day 8.",
    "{regimen_name} protocol. Today administering {partial_drugs}.",
    "Chemo: {regimen_name}. {partial_drugs} given as planned. Remaining component at home.",
    "Cycle {cycle_num} {regimen_name}: {partial_drugs} infused. Patient tolerated well.",
    "Proceeded with {partial_drugs} per {regimen_name} protocol.",
    "{regimen_name} – {partial_drugs} completed. Next drugs due day {next_day}.",
    "Treatment today: {partial_drugs} as part of {regimen_name} regimen.",
    "{regimen_name}: {partial_drugs} IV, with remaining agents scheduled separately.",
    "Received {partial_drugs} (part of {regimen_name}). Remaining components scheduled for next visit.",
    "Started {regimen_name} today. Infused {partial_drugs}.",
    "Administered the IV portion of {regimen_name}: {partial_drugs}.",
    "{regimen_name} Day {cycle_day}: {partial_drugs} given.",
    "Patient received {partial_drugs} per {regimen_name}. Will continue oral {oral_drug} at home.",
]

# C3.4 — Cycles, lines, and intent metadata
C3_4_TEMPLATES = [
    "Cycle {cycle_num} of {num_cycles} of {intent} {regimen_name} for {condition}. Patient tolerating treatment well.",
    "Second-line therapy with {regimen_name} for relapsed {condition} after failure of {regimen_name_prev}.",
    "Starting third-line {regimen_name} for refractory {condition}. Poor prognosis discussed.",
    "{intent} {regimen_name} planned for {num_cycles} cycles prior to surgical evaluation.",
    "Maintenance {regimen_name} following {num_cycles} cycles of induction {regimen_name_prev}.",
    "{intent} chemotherapy with {regimen_name} x {num_cycles} cycles planned.",
    "Phase: {intent}. Regimen: {regimen_name}. Cycle: {cycle_num}/{num_cycles}. Next cycle: q{cycle_length}w.",
    "Induction: {regimen_name_prev} x {num_cycles} cycles (completed). Consolidation: {regimen_name} x {num_cycles_2} cycles.",
    "Salvage chemotherapy with {regimen_name} for {condition} refractory to {regimen_name_prev}.",
    "Patient on cycle {cycle_num} of {intent} {regimen_name} for stage {stage} {condition}. Plan {num_cycles} total cycles.",
]


# ═══════════════════════════════════════════════════════════════════════
# C4 — Context & Safety
# ═══════════════════════════════════════════════════════════════════════

# C4.1 — Discontinued / on hold
C4_1_TEMPLATES = [
    "{drug1} was discontinued due to {reason}.",
    "Hold {drug1} pending lab results.",
    "{drug1} stopped on {stop_date} because of {reason}.",
    "Discontinue {drug1}; start {drug2} instead.",
    "{drug1} held secondary to {reason}. Will reassess next visit.",
    "Patient no longer taking {drug1}. Stopped 2 weeks ago for {reason}.",
    "Therapeutic change: D/C {drug1}, begin {drug2}.",
    "{drug1} on hold until ANC > 1500.",
    "Held {drug1} this cycle due to {reason}. Will resume if resolved.",
    "Per patient, stopped {drug1} self due to {reason}.",
    "Status: {drug1} DISCONTINUED. Reason: {reason}.",
    "{drug1} permanently discontinued secondary to {reason}.",
    "Temporarily holding {drug1}. Continue {drug2} as scheduled.",
    "Cycle {cycle_num} held: {drug1} withheld for {reason}.",
    "{drug1} was held and then re-initiated at a reduced dose of {dose1_low}.",
    "Provider discontinued {drug1} and transitioned to {drug2} {dose2} {route2}.",
    "{drug1} held x 2 weeks. Labs improving. Will resume at 75% dose.",
    "D/C {drug1} per patient request secondary to {reason}.",
    "Treatment modification: omit {drug1} from {regimen_name} due to {reason}.",
    "Not a candidate for {drug1}. Switched to {drug2}.",
]

# C4.2 — Allergy / adverse drug reaction
C4_2_TEMPLATES = [
    "ALLERGY: {drug1} – {reaction}.",
    "Patient reports allergy to {drug1} (reaction: {reaction}).",
    "Known allergy to {drug1}: {reaction}. Avoid {drug1} and related agents.",
    "Allergies: {drug1} ({reaction}), {drug2} ({reaction2}).",
    "Patient developed {reaction} to {drug1} during cycle {cycle_num}. {drug1} discontinued.",
    "Drug allergy: {drug1} → {reaction}. Documented in chart.",
    "History of {reaction} with {drug1}. Alternative therapy will be selected after review.",
    "{drug1} contraindicated due to prior {reaction}.",
    "ADR: {drug1} caused {reaction}. Severity: {severity}.",
    "Intolerance to {drug1}: {reaction}. Therapy changed after review.",
    "Patient reports prior anaphylactic reaction to {drug1}.",
    "ALLERGY LIST: {drug1} ({reaction}). No other known drug allergies.",
    "Adverse reaction to {drug1}: {reaction}. Grade {grade} toxicity.",
    "NKDA except {drug1} – {reaction}.",
    "Hypersensitivity to {drug1} documented. Cross-reactivity with {drug_related} possible.",
    "Patient allergic to {drug1}. Previous treatment with {drug1} resulted in {reaction}.",
]

# C4.3 — Negated drug mentions
C4_3_TEMPLATES = [
    "Patient is not on {drug1}.",
    "No {drug1} at this time.",
    "Denied taking {drug1}.",
    "Patient is not currently receiving {drug1}.",
    "Not a candidate for {drug1} due to {reason}.",
    "{drug1} was considered but not started.",
    "We will not be using {drug1} in this regimen.",
    "Patient declined {drug1}.",
    "No indication for {drug1} at this time.",
    "{drug1} is not recommended for this patient.",
    "{drug1} was NOT administered today.",
    "Defer {drug1}. Not appropriate for current clinical scenario.",
    "Patient has never received {drug1}.",
    "No history of {drug1} use.",
    "Treatment plan does not include {drug1}.",
    "Discussed {drug1} but patient opted against it.",
    "No {drug1} in the current regimen.",
    "Ruled out {drug1} due to {reason}.",
    "{drug1} not given this cycle.",
    "Did not administer {drug1}; {drug2} given instead.",
]

# C4.4 — Medication history / conflicts
C4_4_TEMPLATES = [
    "Past treatment: {drug1} for {condition_prev}. Current: {drug2} for {condition}.",
    "Previously treated with {regimen_name_prev} ({num_cycles_prev} cycles). Now starting {regimen_name}.",
    "History of {drug1} use. Current medication {drug2}; interaction status not assessed.",
    "Prior regimen: {regimen_name_prev}. Changed to {regimen_name} due to {reason}.",
    "Medication history: {drug1} ({date_range_prev}), {drug2} ({date_range_curr}).",
    "Patient reports taking {drug1} from {date_range_prev}. Currently on {drug2}.",
    "Concurrent medications: {drug1} (for {reason1}) and {drug2}; medication review requested.",
    "Medication reconciliation lists {drug1} and {drug2}; coadministration review pending.",
    "Previously received {drug1}. Cumulative lifetime dose: {cumulative_dose}. Max: {max_dose}.",
    "Medication review flag: {drug1} and {drug2}. Interaction status not yet assessed.",
    "Prior line: {drug1}. Second line: {drug2}. Third line: {drug3}.",
    "Patient has received {cumulative_dose} of lifetime {drug1}. Approaching max cumulative dose.",
    "Previous treatment history significant for {num_cycles_prev} cycles {regimen_name_prev} followed by {regimen_name}.",
]


# ═══════════════════════════════════════════════════════════════════════
# C5 — Noise, Ambiguity & Domain Messiness
# ═══════════════════════════════════════════════════════════════════════

# C5.1 — Abbreviations and shortened forms
C5_1_TEMPLATES = [
    "Start {drug_abbrev} {dose1} {route1} {freq1}.",
    "Patient receiving {drug_abbrev} as part of chemo regimen.",
    "Give {drug_abbrev} {dose1} {route1}.",
    "Day 1: {drug_abbrev} {dose1} IV. Day 2: {drug_abbrev2} {dose2} IV.",
    "{drug_abbrev} infusing now. {drug_abbrev2} to follow.",
    "Chemo: {drug_abbrev} + {drug_abbrev2}, q3w.",
    "{drug_abbrev} given, {drug_abbrev2} held due to toxicity.",
    "Premedicate, then {drug_abbrev} {dose1} {route1}.",
    "Treatment includes {drug_abbrev} and {drug_abbrev2}.",
    "Pt on {drug_abbrev} based regimen.",
    "Received {drug_abbrev} without incident.",
    "Cycle 2: {drug_abbrev} {dose1}, {drug_abbrev2} {dose2}.",
    "Tolerated {drug_abbrev} well. Will continue.",
    "D/C {drug_abbrev}. Start {drug_abbrev2}.",
    "Order: {drug_abbrev} {dose1} {route1} {freq1}. Verify with pharmacy.",
]

# C5.2 — Brand name usage
C5_2_TEMPLATES = [
    "Patient is currently on {brand_name}.",
    "Start {brand_name} {dose1} {route1} {freq1}.",
    "{brand_name} administered per protocol.",
    "Continue {brand_name} as previously prescribed.",
    "Switch from {brand_name} to {brand_name2}.",
    "Home medications: {brand_name} {dose1} {route1}.",
    "Rx: {brand_name} {dose1} {route1} {freq1}.",
    "{brand_name} ongoing. Tolerating well.",
    "Started {brand_name} for {condition}.",
    "Patient reports taking {brand_name} daily.",
    "Medications: {brand_name} ({drug1_generic}) {dose1}, {brand_name2} ({drug2_generic}) {dose2}.",
    "Added {brand_name} to regimen.",
    "Discussed risks/benefits of {brand_name} with patient.",
    "{brand_name} covered by insurance. Will proceed.",
    "Infusion: {brand_name} {dose1} {route1} over {infusion_time}.",
]

# C5.3 — Misspellings / typos
C5_3_TEMPLATES = [
    "Start {drug_misspelled} {dose1} {route1}.",
    "Pt on {drug_misspelled} and {drug2}.",
    "Continue {drug_misspelled} as directed.",
    "Administer {drug_misspelled} {dose1} {route1} {freq1}.",
    "Received {drug_misspelled} today without incident.",
    "{drug_misspelled} and {drug_misspelled2} given per chemo protocol.",
    "Current meds include {drug_misspelled}.",
    "Chemo: {drug_misspelled} + {drug2}.",
    "Pt taking {drug_misspelled} at home.",
    "Order for {drug_misspelled} {dose1}.",
    "Rx: {drug_misspelled} {dose1} {route1} {freq1}.",
    "Infused {drug_misspelled} {dose1} IV.",
    "Treatment: {drug_misspelled} based regimen.",
    "Plan: {drug_misspelled} {dose1} {route1} {freq1} x {duration}.",
    "Please dispense {drug_misspelled} {dose1}.",
]

# C5.4 — High-noise clinical text (multiple drugs, labs, vitals mixed in)
C5_4_TEMPLATES = [
    "Pt {age}y/o {sex} w/ {condition} s/p C{cycle_num} {regimen_name}. Vitals stable. WBC 3.2, plt 145, Hgb 10.1. Creat 0.9. Meds: {drug1} {dose1} {route1}, {drug2} {dose2} {route2}, Aspirin 81mg PO daily, Famotidine 20mg PO BID, Lorazepam 0.5mg PO PRN. Plan: proceed with next cycle.",
    "Progress note: {condition} on {regimen_name}. Labs: ANC 1800, plt 95k. Tolerated {drug1} well. Held {drug2} d/t thrombocytopenia. Cont {drug3} {dose3} {route3}. F/u 2 wks w/ CBC.",
    "MRN {mrn}. {age}{sex}. Dx: {condition}. Current cycle: C{cycle_num}D1 {regimen_name}. Pre-chemo labs within acceptable limits. Premeds: {drug_premedx} given. Infused {drug1} {dose1} IV over 3hrs, then {drug2} {dose2} IV push, then {drug3} {dose3} IV over 46hrs CI. Tolerated well. D/C home.",
    "Telephone encounter: Patient c/o N/V x2 days post chemo ({regimen_name} C{cycle_num}). Taking {drug_antiemetic} q8h but minimal relief. Added {drug_antiemetic2}. Reminded to take {drug1} and {drug2} as prescribed. Hydration encouraged.",
    "Discharge summary: {age}y/o with {condition} admitted for febrile neutropenia s/p C{cycle_num} {regimen_name}. Treated with {drug_abx1} and {drug_abx2}. Blood cultures negative. ANC recovered to 1200. D/C on {drug_abx_oral}. Resume {regimen_name} in 2 weeks with dose reduction.",
    "Med reconciliation: {drug1} {dose1} {route1} {freq1}, {drug2} {dose2} {route2} {freq2}, {drug3} {dose3} {route3} daily, Atenolol 50mg PO daily, Amlodipine 5mg PO daily, Metformin 500mg PO BID, Lisinopril 10mg PO daily. Allergies: {drug_allergy} – rash. NKFA.",
    "Oncology consult: {age}y/o w/ newly dx {condition}. Pathology reviewed. ECOG {ecog}. Rec: {regimen_name} x{num_cycles} cycles {intent}. Discussed with pt/family. Consent obtained. Baseline labs/imaging ordered. Start date pending.",
    "Infusion center note: Pt arrived for C{cycle_num}D1 {regimen_name}. Pre-chemo checklist complete. Port accessed. NS flush. {drug_premed1} {dose_pm1} IV, {drug_premed2} {dose_pm2} IV given. {drug1} {dose1} IV in 250mL NS over {infusion_time1}. {drug2} {dose2} IV in 500mL D5W over {infusion_time2}. No reactions. VS stable. D/C in good condition.",
]


# ═══════════════════════════════════════════════════════════════════════
# Helper: Collect all templates keyed by subcategory code
# ═══════════════════════════════════════════════════════════════════════

TEMPLATES_BY_SUBCATEGORY = {
    "C1.1_single_drug_simple":     C1_1_TEMPLATES,
    "C1.2_single_drug_dose":       C1_2_TEMPLATES,
    "C1.3_two_drugs":              C1_3_TEMPLATES,
    "C1.4_supportive_care":        C1_4_TEMPLATES,
    "C2.1_dose_route_freq":        C2_1_TEMPLATES,
    "C2.2_titration_taper":        C2_2_TEMPLATES,
    "C2.3_prn_conditional":        C2_3_TEMPLATES,
    "C2.4_duration_stop":          C2_4_TEMPLATES,
    "C3.1_multi_drug_explicit":    C3_1_TEMPLATES,
    "C3.2_regimen_acronym_only":   C3_2_TEMPLATES,
    "C3.3_regimen_partial":        C3_3_TEMPLATES,
    "C3.4_cycles_lines_intent":    C3_4_TEMPLATES,
    "C4.1_discontinued_hold":      C4_1_TEMPLATES,
    "C4.2_allergy_adr":            C4_2_TEMPLATES,
    "C4.3_negated":                C4_3_TEMPLATES,
    "C4.4_med_history_conflict":   C4_4_TEMPLATES,
    "C5.1_abbreviations":          C5_1_TEMPLATES,
    "C5.2_brand_names":            C5_2_TEMPLATES,
    "C5.3_misspellings":           C5_3_TEMPLATES,
    "C5.4_high_noise":             C5_4_TEMPLATES,
}
