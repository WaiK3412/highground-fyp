export const STEPS = ['Household', 'Home & damage', 'Safety & needs', 'Photos', 'Review & submit']

// Match CaseRecord.TextChoices for validation/job creation; labels are household wording.
export const DAMAGE_CATEGORIES = [
  { value: 'cleanup', label: 'Cleanup', desc: 'Mud, debris and silt removal' },
  { value: 'repair', label: 'Repair', desc: 'Structural or utility damage' },
  { value: 'essential_items', label: 'Essential items', desc: 'Food, water, bedding, medicine' },
  { value: 'agriculture', label: 'Agriculture', desc: 'Crops, livestock or equipment' },
]

// Match frozen waist y=126 relative to floor y=150/head y=96; other SVG levels use the same person scale.
export const FLOOD_DEPTHS = [
  { value: 'ankle', label: 'Below ankle', desc: 'under 0.3 m', waterY: 142 },
  { value: 'knee', label: 'Knee height', desc: '0.3 to 0.5 m', waterY: 134 },
  { value: 'waist', label: 'Waist height', desc: '0.5 to 1 m indoors', waterY: 126 },
  { value: 'above_head', label: 'Above head', desc: 'more than 1 m', waterY: 94 },
]

export const LIVEABILITY = [
  { value: 'liveable', label: 'Yes — we can stay here' },
  { value: 'partial', label: 'Partially — some rooms unusable' },
  { value: 'unliveable', label: 'No — we cannot stay here' },
]

export const ACCESS_LEVELS = [
  { value: 'normal', label: 'Yes — normal access' },
  { value: 'four_wd', label: 'Only high vehicles / 4x4' },
  { value: 'foot', label: 'On foot only' },
  { value: 'cut_off', label: 'Completely cut off' },
]

// Keep screen 05b wording and "call 999 first": HighGround complements emergency services.
export const URGENCY = [
  { value: 'none', label: 'No safety concerns', desc: 'Everyone is safe and well' },
  {
    value: 'health_risk',
    label: 'Health concern',
    desc: 'Damp or mould exposure, minor illness, hygiene risk',
  },
  {
    value: 'medical_disrupted',
    label: 'Medical needs disrupted',
    desc: 'Medication, medical equipment or ongoing treatment affected by the flood',
  },
  {
    value: 'urgent',
    label: 'Someone needs urgent medical attention',
    desc: 'We will flag this to the district office — but call 999 first',
  },
]

export const VULNERABILITY_FLAGS = [
  { value: 'elderly', label: 'Elderly members (60+)' },
  { value: 'child_under_5', label: 'Children under 5' },
  { value: 'disability', label: 'Members with medical needs or disability' },
  { value: 'single_parent', label: 'Single-parent household' },
]

export const NEEDS_FLAGS = [
  { value: 'food', label: 'Food' },
  { value: 'water', label: 'Safe drinking water' },
  { value: 'hygiene', label: 'Hygiene items' },
  { value: 'bedding', label: 'Bedding & clothing' },
  { value: 'medicine', label: 'Medicine' },
  { value: 'baby_supplies', label: 'Baby supplies' },
]
