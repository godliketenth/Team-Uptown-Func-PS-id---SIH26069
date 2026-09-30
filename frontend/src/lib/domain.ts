import type { EventStatus, EventType, Severity, SourceType, WarningLevel } from "./types";

/* Event type = one hue, used identically on map pins, badges, charts and
   filters. Status uses a separate neutral scale so the two never collide.

   Every hue sits at a mid lightness so the same hex carries on the warm
   charcoal ground and on the warm paper ground without being restated per
   theme. Blue is permitted here and nowhere in the chrome: rain and flood are
   water, and letting them be blue is what frees the surfaces to stay warm. */
export const EVENT_COLORS: Record<EventType, string> = {
  RAIN: "#4A90D9",
  FLOOD: "#1F8A8A",
  THUNDERSTORM: "#8E5FC4",
  HEATWAVE: "#DD7038",
  FOG: "#9A8D7C",
  DUST_STORM: "#B07C3C",
  STRONG_WIND: "#6FA8B5",
};

export const EVENT_LABELS: Record<EventType, string> = {
  RAIN: "Rain",
  FLOOD: "Flood",
  THUNDERSTORM: "Thunderstorm",
  HEATWAVE: "Heatwave",
  FOG: "Fog",
  DUST_STORM: "Dust Storm",
  STRONG_WIND: "Strong Wind",
};

/* Flood and rain sit close on the hue wheel, so every event type also carries
   a distinct glyph - colour is never the only channel. */
export const EVENT_GLYPHS: Record<EventType, string> = {
  RAIN: "☂",
  FLOOD: "≋",
  THUNDERSTORM: "⚡",
  HEATWAVE: "☀",
  FOG: "▤",
  DUST_STORM: "⛰",
  STRONG_WIND: "➤",
};

export const EVENT_TYPES: EventType[] = [
  "RAIN",
  "FLOOD",
  "THUNDERSTORM",
  "HEATWAVE",
  "FOG",
  "DUST_STORM",
  "STRONG_WIND",
];

export const STATUS_COLORS: Record<EventStatus, string> = {
  DETECTED: "#9E9285",
  CORROBORATING: "#9E9285",
  NEEDS_REVIEW: "#E8A83A",
  VERIFIED: "#45B87C",
  REJECTED: "#D14A47",
  RESOLVED: "#7A6F62",
};

export const STATUS_LABELS: Record<EventStatus, string> = {
  DETECTED: "Detected",
  CORROBORATING: "Corroborating",
  NEEDS_REVIEW: "Needs review",
  VERIFIED: "Verified",
  REJECTED: "Rejected",
  RESOLVED: "Resolved",
};

export const EVENT_STATUSES: EventStatus[] = [
  "DETECTED",
  "CORROBORATING",
  "NEEDS_REVIEW",
  "VERIFIED",
  "REJECTED",
  "RESOLVED",
];

export const SEVERITY_COLORS: Record<Severity, string> = {
  LOW: "#7A6F62",
  MODERATE: "#E8A83A",
  HIGH: "#DD7038",
  SEVERE: "#D14A47",
};

export const SEVERITY_ORDER: Severity[] = ["LOW", "MODERATE", "HIGH", "SEVERE"];

/* IMD-style four-colour warning scale. The vocabulary and the actions follow
   IMD's published bulletin scale, which is what makes the output legible to a
   district officer. The thresholds that trigger each level are ours, derived
   from accumulated evidence rather than forecast intensity — the UI says so
   wherever the level is shown. */
export const WARNING_LEVELS: WarningLevel[] = ["GREEN", "YELLOW", "ORANGE", "RED"];

export const WARNING_COLORS: Record<WarningLevel, string> = {
  GREEN: "#45B87C",
  YELLOW: "#E8A83A",
  ORANGE: "#DD7038",
  RED: "#D14A47",
};

export const WARNING_LABELS: Record<WarningLevel, string> = {
  GREEN: "No warning",
  YELLOW: "Watch",
  ORANGE: "Alert",
  RED: "Warning",
};

export const WARNING_ACTIONS: Record<WarningLevel, string> = {
  GREEN: "No action needed",
  YELLOW: "Be updated",
  ORANGE: "Be prepared",
  RED: "Take action",
};

/** Pin diameter is driven by the warning level, so the biggest marks on the
    map are the ones that need action — not merely the noisiest. */
export const WARNING_PIN_SIZE: Record<WarningLevel, number> = {
  GREEN: 20,
  YELLOW: 25,
  ORANGE: 31,
  RED: 38,
};

export const SOURCE_LABELS: Record<SourceType, string> = {
  GOVERNMENT: "Government",
  WEATHER_API: "Weather API",
  CITIZEN: "Citizen",
  SOCIAL: "Social",
  WEB_RSS: "Web / RSS",
  SATELLITE: "Satellite",
};

export const SOURCE_TRUST: Record<SourceType, number> = {
  GOVERNMENT: 1.0,
  WEATHER_API: 1.0,
  SATELLITE: 0.9,
  WEB_RSS: 0.7,
  CITIZEN: 0.6,
  SOCIAL: 0.5,
};

export const LANGUAGE_LABELS: Record<string, string> = {
  en: "EN",
  hi: "HI",
  gu: "GU",
  bn: "BN",
  ta: "TA",
};

/* Indian states present in the prototype's geocoding table. */
export const STATES: string[] = [
  "Andhra Pradesh",
  "Assam",
  "Bihar",
  "Chandigarh",
  "Chhattisgarh",
  "Delhi",
  "Goa",
  "Gujarat",
  "Haryana",
  "Himachal Pradesh",
  "Jammu and Kashmir",
  "Jharkhand",
  "Karnataka",
  "Kerala",
  "Madhya Pradesh",
  "Maharashtra",
  "Odisha",
  "Punjab",
  "Rajasthan",
  "Tamil Nadu",
  "Telangana",
  "Uttar Pradesh",
  "Uttarakhand",
  "West Bengal",
];

export const DISTRICTS_BY_STATE: Record<string, string[]> = {
  "Andhra Pradesh": ["NTR", "Visakhapatnam"],
  Assam: ["Dibrugarh", "Kamrup Metropolitan"],
  Bihar: ["Gaya", "Patna"],
  Chandigarh: ["Chandigarh"],
  Chhattisgarh: ["Raipur"],
  Delhi: ["New Delhi"],
  Goa: ["North Goa"],
  Gujarat: ["Ahmedabad", "Kachchh", "Rajkot", "Surat", "Vadodara"],
  Haryana: ["Faridabad", "Gurugram"],
  "Himachal Pradesh": ["Shimla"],
  "Jammu and Kashmir": ["Jammu", "Srinagar"],
  Jharkhand: ["Ranchi"],
  Karnataka: ["Bengaluru Urban", "Dakshina Kannada", "Dharwad", "Mysuru"],
  Kerala: ["Ernakulam", "Kozhikode", "Thiruvananthapuram"],
  "Madhya Pradesh": ["Bhopal", "Indore", "Jabalpur"],
  Maharashtra: ["Aurangabad", "Mumbai Suburban", "Nagpur", "Nashik", "Pune", "Thane"],
  Odisha: ["Cuttack", "Khordha", "Puri"],
  Punjab: ["Amritsar", "Ludhiana"],
  Rajasthan: ["Bikaner", "Jaipur", "Jodhpur", "Udaipur"],
  "Tamil Nadu": ["Chennai", "Coimbatore", "Madurai", "Tiruchirappalli"],
  Telangana: ["Hyderabad", "Warangal"],
  "Uttar Pradesh": [
    "Agra",
    "Gautam Buddha Nagar",
    "Ghaziabad",
    "Kanpur Nagar",
    "Lucknow",
    "Prayagraj",
    "Varanasi",
  ],
  Uttarakhand: ["Dehradun"],
  "West Bengal": ["Darjeeling", "Howrah", "Kolkata"],
};

export const OPEN_STATUSES: EventStatus[] = [
  "DETECTED",
  "CORROBORATING",
  "NEEDS_REVIEW",
  "VERIFIED",
];

export function isOpen(status: EventStatus) {
  return OPEN_STATUSES.includes(status);
}

export const ROLE_RANK: Record<string, number> = {
  PUBLIC_USER: 0,
  ANALYST: 1,
  VERIFIER: 2,
  ADMIN: 3,
};

export function atLeast(role: string | undefined, minimum: string) {
  if (!role) return false;
  return (ROLE_RANK[role] ?? -1) >= (ROLE_RANK[minimum] ?? 99);
}
