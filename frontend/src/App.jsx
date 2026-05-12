import { useState, useRef, useEffect } from "react";

const MONO = "'IBM Plex Mono', 'Courier New', monospace";
const SANS = "'IBM Plex Sans', 'Helvetica Neue', sans-serif";

// -- Color system: dark vinyl crate aesthetic --
const C = {
  bg: "#0D0D0D",
  surface: "#161616",
  surface2: "#1E1E1E",
  border: "#2A2A2A",
  borderHover: "#444",
  text: "#E8E4DC",
  textMuted: "#8A8578",
  textDim: "#5A5750",
  accent: "#E8593C",    // warm orange-red, like a wax seal
  accent2: "#D4A843",   // gold, like a label
  accent3: "#5DCAA5",   // teal, for success states
  wax: "#1A1412",       // dark brown, vinyl grooves
};

// -- Fake data for demo (since we can't actually scrape 1001tracklists from here) --
const DEMO_TRACKS = {
  "Peggy Gou": {
    recent: [
      { title: "Starry Night", artist: "Peggy Gou", bpm: 124, key: "Am", label: "Gudu Records", year: 2023, genre: "House", setPosition: "opener", playCount: 4, buyLink: "https://www.beatport.com" },
      { title: "Lobster Telephone", artist: "Peggy Gou", bpm: 122, key: "Cm", label: "Ninja Tune", year: 2021, genre: "Electro", setPosition: "opener", playCount: 3, buyLink: "https://www.beatport.com" },
      { title: "Nabi", artist: "Peggy Gou", bpm: 120, key: "Dm", label: "Gudu Records", year: 2024, genre: "Melodic House", setPosition: "warmup", playCount: 5, buyLink: "https://www.beatport.com" },
      { title: "Han Jan", artist: "Peggy Gou", bpm: 128, key: "Gm", label: "Gudu Records", year: 2019, genre: "Tech House", setPosition: "peak", playCount: 5, buyLink: "https://www.beatport.com" },
      { title: "Nanana", artist: "Peggy Gou", bpm: 126, key: "F", label: "Gudu Records", year: 2023, genre: "House", setPosition: "peak", playCount: 5, buyLink: "https://www.beatport.com" },
      { title: "I Go", artist: "Peggy Gou", bpm: 130, key: "Am", label: "Gudu Records", year: 2022, genre: "House", setPosition: "peak", playCount: 4, buyLink: "https://www.beatport.com" },
      { title: "Sparkle", artist: "Peggy Gou", bpm: 118, key: "Bb", label: "Gudu Records", year: 2024, genre: "Disco House", setPosition: "warmup", playCount: 3, buyLink: "https://www.beatport.com" },
      { title: "It Makes You Forget", artist: "Peggy Gou", bpm: 123, key: "Fm", label: "Ninja Tune", year: 2018, genre: "House", setPosition: "peak", playCount: 5, buyLink: "https://www.beatport.com" },
      { title: "1+1=11", artist: "Peggy Gou ft. Lenny Kravitz", bpm: 125, key: "Em", label: "Gudu Records", year: 2024, genre: "House", setPosition: "closer", playCount: 2, buyLink: "https://www.beatport.com" },
      { title: "Djembe Monk", artist: "GgDeams (Peggy Gou & Gerd Janson)", bpm: 127, key: "Cm", label: "Running Back", year: 2020, genre: "Minimal", setPosition: "peak", playCount: 3, buyLink: "https://www.beatport.com" },
      { title: "Hungboo", artist: "Peggy Gou", bpm: 133, key: "Dm", label: "Rekids", year: 2017, genre: "Techno", setPosition: "peak", playCount: 4, buyLink: "https://www.beatport.com" },
      { title: "Travelling Without Arriving", artist: "Peggy Gou", bpm: 135, key: "Gm", label: "Phonica White", year: 2016, genre: "Techno", setPosition: "closer", playCount: 3, buyLink: "https://www.beatport.com" },
    ],
    mostViewed: [
      { title: "Nanana", artist: "Peggy Gou", bpm: 126, key: "F", label: "Gudu Records", year: 2023, genre: "House", setPosition: "peak", playCount: 5, buyLink: "https://www.beatport.com" },
      { title: "It Makes You Forget", artist: "Peggy Gou", bpm: 123, key: "Fm", label: "Ninja Tune", year: 2018, genre: "House", setPosition: "peak", playCount: 5, buyLink: "https://www.beatport.com" },
      { title: "Han Jan", artist: "Peggy Gou", bpm: 128, key: "Gm", label: "Gudu Records", year: 2019, genre: "Tech House", setPosition: "peak", playCount: 5, buyLink: "https://www.beatport.com" },
      { title: "Starry Night", artist: "Peggy Gou", bpm: 124, key: "Am", label: "Gudu Records", year: 2023, genre: "House", setPosition: "opener", playCount: 4, buyLink: "https://www.beatport.com" },
      { title: "I Go", artist: "Peggy Gou", bpm: 130, key: "Am", label: "Gudu Records", year: 2022, genre: "House", setPosition: "peak", playCount: 4, buyLink: "https://www.beatport.com" },
      { title: "Hungboo", artist: "Peggy Gou", bpm: 133, key: "Dm", label: "Rekids", year: 2017, genre: "Techno", setPosition: "peak", playCount: 4, buyLink: "https://www.beatport.com" },
      { title: "Nabi", artist: "Peggy Gou", bpm: 120, key: "Dm", label: "Gudu Records", year: 2024, genre: "Melodic House", setPosition: "warmup", playCount: 5, buyLink: "https://www.beatport.com" },
      { title: "1+1=11", artist: "Peggy Gou ft. Lenny Kravitz", bpm: 125, key: "Em", label: "Gudu Records", year: 2024, genre: "House", setPosition: "closer", playCount: 2, buyLink: "https://www.beatport.com" },
    ],
    mostLiked: [
      { title: "It Makes You Forget", artist: "Peggy Gou", bpm: 123, key: "Fm", label: "Ninja Tune", year: 2018, genre: "House", setPosition: "peak", playCount: 5, buyLink: "https://www.beatport.com" },
      { title: "Nabi", artist: "Peggy Gou", bpm: 120, key: "Dm", label: "Gudu Records", year: 2024, genre: "Melodic House", setPosition: "warmup", playCount: 5, buyLink: "https://www.beatport.com" },
      { title: "Starry Night", artist: "Peggy Gou", bpm: 124, key: "Am", label: "Gudu Records", year: 2023, genre: "House", setPosition: "opener", playCount: 4, buyLink: "https://www.beatport.com" },
      { title: "Lobster Telephone", artist: "Peggy Gou", bpm: 122, key: "Cm", label: "Ninja Tune", year: 2021, genre: "Electro", setPosition: "opener", playCount: 3, buyLink: "https://www.beatport.com" },
      { title: "Sparkle", artist: "Peggy Gou", bpm: 118, key: "Bb", label: "Gudu Records", year: 2024, genre: "Disco House", setPosition: "warmup", playCount: 3, buyLink: "https://www.beatport.com" },
      { title: "Travelling Without Arriving", artist: "Peggy Gou", bpm: 135, key: "Gm", label: "Phonica White", year: 2016, genre: "Techno", setPosition: "closer", playCount: 3, buyLink: "https://www.beatport.com" },
      { title: "Djembe Monk", artist: "GgDeams (Peggy Gou & Gerd Janson)", bpm: 127, key: "Cm", label: "Running Back", year: 2020, genre: "Minimal", setPosition: "peak", playCount: 3, buyLink: "https://www.beatport.com" },
    ],
  }
};

const SELECTION_MODES = [
  { id: "recent", label: "Last 5 sets", desc: "Most recent tracklists", icon: "⏱" },
  { id: "mostViewed", label: "Most viewed", desc: "Highest traffic sets", icon: "👁" },
  { id: "mostLiked", label: "Most liked", desc: "Community favorites", icon: "♥" },
];

const VIBE_PRESETS = [
  "dark minimal, 126-130bpm, late night",
  "groovy disco house, 120-124bpm, sunset",
  "high energy techno, 132+bpm, peak time",
  "melodic & emotional, 122-128bpm, sunrise",
  "eclectic & weird, mixed bpm, afterhours",
];

// -- Spinning vinyl animation --
function Vinyl({ spinning }) {
  return (
    <div style={{
      width: 48, height: 48, borderRadius: "50%",
      background: `radial-gradient(circle at center, ${C.accent} 6px, ${C.wax} 7px, ${C.wax} 10px, #222 11px, #1a1a1a 13px, #222 15px, #1a1a1a 17px, #222 19px, #1a1a1a 21px, #222 23px, transparent 24px)`,
      animation: spinning ? "spin 2s linear infinite" : "none",
      flexShrink: 0,
    }} />
  );
}

// -- Track row in the setlist --
function TrackRow({ track, index, total }) {
  const progress = total > 1 ? index / (total - 1) : 0;
  // Energy color: teal (low) -> gold (mid) -> orange-red (high)
  const energyColor = progress < 0.5
    ? `color-mix(in srgb, ${C.accent3} ${(1 - progress * 2) * 100}%, ${C.accent2})`
    : `color-mix(in srgb, ${C.accent2} ${(1 - (progress - 0.5) * 2) * 100}%, ${C.accent})`;

  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 14, padding: "14px 16px",
      borderBottom: `1px solid ${C.border}`,
      background: index % 2 === 0 ? "transparent" : "rgba(255,255,255,0.015)",
      transition: "background 0.2s",
    }}
      onMouseEnter={e => e.currentTarget.style.background = "rgba(255,255,255,0.04)"}
      onMouseLeave={e => e.currentTarget.style.background = index % 2 === 0 ? "transparent" : "rgba(255,255,255,0.015)"}
    >
      {/* Position number with energy bar */}
      <div style={{ width: 36, textAlign: "center", position: "relative" }}>
        <span style={{ fontFamily: MONO, fontSize: 13, color: C.textMuted }}>{String(index + 1).padStart(2, "0")}</span>
        <div style={{
          position: "absolute", left: 0, bottom: -14, width: "100%", height: 3,
          borderRadius: 2, background: C.border, overflow: "hidden",
        }}>
          <div style={{
            width: `${20 + progress * 80}%`, height: "100%", borderRadius: 2,
            background: energyColor,
            transition: "width 0.5s ease",
          }} />
        </div>
      </div>

      {/* Track info */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontFamily: SANS, fontSize: 14, fontWeight: 500, color: C.text,
          whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
        }}>
          {track.title}
        </div>
        <div style={{
          fontFamily: SANS, fontSize: 12, color: C.textMuted, marginTop: 2,
          whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
        }}>
          {track.artist}
        </div>
      </div>

      {/* Metadata pills */}
      <div style={{ display: "flex", gap: 6, alignItems: "center", flexShrink: 0 }}>
        <span style={{
          fontFamily: MONO, fontSize: 11, color: C.accent2, background: "rgba(212,168,67,0.1)",
          padding: "3px 8px", borderRadius: 4,
        }}>{track.bpm}</span>
        <span style={{
          fontFamily: MONO, fontSize: 11, color: C.accent3, background: "rgba(93,202,165,0.1)",
          padding: "3px 8px", borderRadius: 4,
        }}>{track.key}</span>
        <span style={{
          fontFamily: MONO, fontSize: 11, color: C.textDim,
          padding: "3px 8px",
        }}>{track.label}</span>
      </div>

      {/* Buy link */}
      <a href={track.buyLink} target="_blank" rel="noopener noreferrer" style={{
        fontFamily: MONO, fontSize: 10, color: C.accent, textDecoration: "none",
        border: `1px solid ${C.accent}33`, padding: "4px 10px", borderRadius: 4,
        transition: "all 0.2s", flexShrink: 0, letterSpacing: 1,
        textTransform: "uppercase",
      }}
        onMouseEnter={e => { e.currentTarget.style.background = C.accent + "22"; }}
        onMouseLeave={e => { e.currentTarget.style.background = "transparent"; }}
      >buy</a>
    </div>
  );
}

// -- Main app --
export default function CrateDigger() {
  const [artist, setArtist] = useState("Peggy Gou");
  const [selectionMode, setSelectionMode] = useState("recent");
  const [vibe, setVibe] = useState("");
  const [step, setStep] = useState(0); // 0=input, 1=scraping, 2=building, 3=done
  const [trackPool, setTrackPool] = useState([]);
  const [setlist, setSetlist] = useState([]);
  const [reasoning, setReasoning] = useState("");
  const [error, setError] = useState("");
  const vibeRef = useRef(null);

  // Simulate scraping + AI setlist building
  async function handleDig() {
    if (!artist.trim() || !vibe.trim()) return;
    setError("");
    setStep(1);
    setSetlist([]);
    setReasoning("");

    // Stage 1: "Scrape" (demo: use fake data)
    await new Promise(r => setTimeout(r, 1800));
    const artistData = DEMO_TRACKS[artist];
    if (!artistData) {
      setError(`No data found for "${artist}". Demo only supports: ${Object.keys(DEMO_TRACKS).join(", ")}`);
      setStep(0);
      return;
    }
    const pool = artistData[selectionMode] || artistData.recent;
    setTrackPool(pool);

    // Stage 2: Call Claude API to build the setlist
    setStep(2);
    try {
      const response = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: "claude-sonnet-4-20250514",
          max_tokens: 1000,
          system: `You are a professional DJ and crate digger. You receive a pool of tracks with metadata (BPM, key, genre, label, set position, play frequency) and a "vibe" description from the user. Your job is to:
1. Filter tracks that match the vibe (BPM range, genre feel, energy).
2. Sequence them into a coherent setlist with smooth transitions (compatible keys, gradual BPM progression, energy arc).
3. Return ONLY valid JSON, no markdown, no backticks, no preamble. The JSON must be:
{"reasoning": "2-3 sentences explaining your choices", "setlist": [array of track titles IN ORDER]}
Only include track titles that exist in the pool. Never invent tracks.`,
          messages: [{
            role: "user",
            content: `Track pool:\n${JSON.stringify(pool, null, 2)}\n\nVibe: "${vibe}"\n\nBuild me an ordered setlist from this pool. Return only JSON.`
          }]
        })
      });

      const data = await response.json();
      const text = data.content?.map(i => i.text || "").join("\n") || "";
      const clean = text.replace(/```json|```/g, "").trim();

      try {
        const parsed = JSON.parse(clean);
        const orderedTitles = parsed.setlist || [];
        const ordered = orderedTitles
          .map(t => pool.find(p => p.title.toLowerCase() === t.toLowerCase()))
          .filter(Boolean);

        if (ordered.length === 0) {
          // Fallback: just use the pool filtered roughly by vibe
          setSetlist(pool.slice(0, 8));
          setReasoning("Showing tracks from the pool (AI sequencing unavailable).");
        } else {
          setSetlist(ordered);
          setReasoning(parsed.reasoning || "");
        }
      } catch (parseErr) {
        // Fallback
        setSetlist(pool.slice(0, 8));
        setReasoning("Showing tracks from the pool — AI returned non-parseable response.");
      }
      setStep(3);
    } catch (fetchErr) {
      // Fallback without API
      setSetlist(pool.slice(0, 8));
      setReasoning("Showing full track pool (connect API for AI-sequenced setlists).");
      setStep(3);
    }
  }

  // Keyboard shortcut
  useEffect(() => {
    const handler = (e) => {
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && step === 0) handleDig();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [artist, vibe, selectionMode, step]);

  return (
    <div style={{
      fontFamily: SANS, color: C.text, minHeight: "100vh",
      background: `linear-gradient(180deg, ${C.bg} 0%, #0a0a0a 100%)`,
      padding: "0 0 60px",
    }}>
      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes fadeUp { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes pulse { 0%,100% { opacity: 0.4; } 50% { opacity: 1; } }
      `}</style>

      {/* -- Header -- */}
      <div style={{
        padding: "40px 32px 32px", borderBottom: `1px solid ${C.border}`,
        background: `linear-gradient(180deg, rgba(232,89,60,0.04) 0%, transparent 100%)`,
      }}>
        <div style={{ maxWidth: 800, margin: "0 auto" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 8 }}>
            <Vinyl spinning={step === 1 || step === 2} />
            <div>
              <h1 style={{
                fontFamily: MONO, fontSize: 28, fontWeight: 600, letterSpacing: -1,
                color: C.text, lineHeight: 1.1,
              }}>
                crate<span style={{ color: C.accent }}>digger</span>
              </h1>
              <p style={{
                fontFamily: MONO, fontSize: 11, color: C.textDim, letterSpacing: 2,
                textTransform: "uppercase", marginTop: 4,
              }}>
                ai-powered setlist builder
              </p>
            </div>
          </div>
        </div>
      </div>

      <div style={{ maxWidth: 800, margin: "0 auto", padding: "0 24px" }}>

        {/* -- Step 1: Input -- */}
        <div style={{
          marginTop: 32, padding: 24, borderRadius: 8,
          border: `1px solid ${C.border}`, background: C.surface,
        }}>
          {/* Artist input */}
          <label style={{ fontFamily: MONO, fontSize: 11, color: C.textDim, letterSpacing: 1.5, textTransform: "uppercase", display: "block", marginBottom: 8 }}>
            artist
          </label>
          <input
            value={artist}
            onChange={e => setArtist(e.target.value)}
            placeholder="e.g. Peggy Gou, Keinemusik, Dixon..."
            disabled={step > 0 && step < 3}
            style={{
              width: "100%", padding: "12px 16px", fontFamily: SANS, fontSize: 16,
              background: C.surface2, border: `1px solid ${C.border}`, borderRadius: 6,
              color: C.text, transition: "border-color 0.2s",
            }}
            onFocus={e => e.target.style.borderColor = C.accent}
            onBlur={e => e.target.style.borderColor = C.border}
          />

          {/* Selection mode */}
          <label style={{ fontFamily: MONO, fontSize: 11, color: C.textDim, letterSpacing: 1.5, textTransform: "uppercase", display: "block", marginTop: 24, marginBottom: 10 }}>
            pull sets by
          </label>
          <div style={{ display: "flex", gap: 8 }}>
            {SELECTION_MODES.map(m => (
              <button
                key={m.id}
                onClick={() => step === 0 || step === 3 ? setSelectionMode(m.id) : null}
                style={{
                  flex: 1, padding: "12px 8px", borderRadius: 6, cursor: "pointer",
                  background: selectionMode === m.id ? C.accent + "18" : C.surface2,
                  border: `1px solid ${selectionMode === m.id ? C.accent + "66" : C.border}`,
                  transition: "all 0.2s", textAlign: "center",
                }}
              >
                <div style={{ fontSize: 18, marginBottom: 4 }}>{m.icon}</div>
                <div style={{ fontFamily: SANS, fontSize: 13, fontWeight: 500, color: selectionMode === m.id ? C.accent : C.text }}>{m.label}</div>
                <div style={{ fontFamily: MONO, fontSize: 10, color: C.textDim, marginTop: 2 }}>{m.desc}</div>
              </button>
            ))}
          </div>

          {/* Vibe input */}
          <label style={{ fontFamily: MONO, fontSize: 11, color: C.textDim, letterSpacing: 1.5, textTransform: "uppercase", display: "block", marginTop: 24, marginBottom: 8 }}>
            describe the vibe
          </label>
          <textarea
            ref={vibeRef}
            value={vibe}
            onChange={e => setVibe(e.target.value)}
            placeholder="dark minimal, 126-130bpm, late night..."
            disabled={step > 0 && step < 3}
            rows={2}
            style={{
              width: "100%", padding: "12px 16px", fontFamily: SANS, fontSize: 15,
              background: C.surface2, border: `1px solid ${C.border}`, borderRadius: 6,
              color: C.text, resize: "vertical", lineHeight: 1.5,
              transition: "border-color 0.2s",
            }}
            onFocus={e => e.target.style.borderColor = C.accent}
            onBlur={e => e.target.style.borderColor = C.border}
          />

          {/* Vibe presets */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 10 }}>
            {VIBE_PRESETS.map(v => (
              <button
                key={v}
                onClick={() => { setVibe(v); vibeRef.current?.focus(); }}
                style={{
                  padding: "5px 12px", borderRadius: 20, cursor: "pointer",
                  background: vibe === v ? C.accent2 + "22" : "transparent",
                  border: `1px solid ${vibe === v ? C.accent2 + "66" : C.border}`,
                  fontFamily: MONO, fontSize: 11, color: vibe === v ? C.accent2 : C.textMuted,
                  transition: "all 0.15s",
                }}
              >
                {v}
              </button>
            ))}
          </div>

          {/* Error message */}
          {error && (
            <div style={{
              marginTop: 16, padding: "10px 14px", borderRadius: 6,
              background: "rgba(232,89,60,0.1)", border: `1px solid ${C.accent}44`,
              fontFamily: MONO, fontSize: 12, color: C.accent,
            }}>
              {error}
            </div>
          )}

          {/* Dig button */}
          <button
            onClick={step === 3 ? () => { setStep(0); setSetlist([]); setTrackPool([]); setReasoning(""); } : handleDig}
            disabled={step > 0 && step < 3}
            style={{
              marginTop: 24, width: "100%", padding: "14px 24px", borderRadius: 6,
              background: step === 3 ? C.surface2 : C.accent,
              border: step === 3 ? `1px solid ${C.border}` : "none",
              color: step === 3 ? C.text : "#fff",
              fontFamily: MONO, fontSize: 14, fontWeight: 600, letterSpacing: 1,
              textTransform: "uppercase", cursor: step > 0 && step < 3 ? "wait" : "pointer",
              transition: "all 0.2s", opacity: (step > 0 && step < 3) ? 0.6 : 1,
            }}
          >
            {step === 0 && "dig"}
            {step === 1 && "scraping 1001tracklists..."}
            {step === 2 && "building setlist..."}
            {step === 3 && "new dig"}
          </button>
        </div>

        {/* -- Loading state -- */}
        {(step === 1 || step === 2) && (
          <div style={{
            marginTop: 24, padding: 32, textAlign: "center",
            border: `1px solid ${C.border}`, borderRadius: 8, background: C.surface,
          }}>
            <Vinyl spinning={true} />
            <p style={{
              fontFamily: MONO, fontSize: 13, color: C.textMuted, marginTop: 16,
              animation: "pulse 1.5s ease infinite",
            }}>
              {step === 1 ? `Pulling ${selectionMode === "recent" ? "last 5 sets" : selectionMode === "mostViewed" ? "most viewed sets" : "most liked sets"} for ${artist}...` : "Claude is sequencing your setlist..."}
            </p>
            {step === 1 && trackPool.length === 0 && (
              <p style={{ fontFamily: MONO, fontSize: 11, color: C.textDim, marginTop: 8 }}>
                Scraping tracklists → parsing tracks → deduplicating pool
              </p>
            )}
          </div>
        )}

        {/* -- Track Pool Summary -- */}
        {trackPool.length > 0 && step >= 2 && (
          <div style={{
            marginTop: 24, padding: "16px 20px", borderRadius: 8,
            border: `1px solid ${C.border}`, background: C.surface,
            animation: "fadeUp 0.4s ease",
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontFamily: MONO, fontSize: 11, color: C.textDim, letterSpacing: 1.5, textTransform: "uppercase" }}>
                track pool
              </span>
              <span style={{ fontFamily: MONO, fontSize: 12, color: C.accent3 }}>
                {trackPool.length} tracks found
              </span>
            </div>
            <div style={{ display: "flex", gap: 16, marginTop: 12, flexWrap: "wrap" }}>
              {[
                { label: "BPM range", value: `${Math.min(...trackPool.map(t => t.bpm))}–${Math.max(...trackPool.map(t => t.bpm))}` },
                { label: "Genres", value: [...new Set(trackPool.map(t => t.genre))].join(", ") },
                { label: "Labels", value: [...new Set(trackPool.map(t => t.label))].slice(0, 3).join(", ") },
                { label: "Years", value: `${Math.min(...trackPool.map(t => t.year))}–${Math.max(...trackPool.map(t => t.year))}` },
              ].map(s => (
                <div key={s.label} style={{ flex: "1 1 140px" }}>
                  <div style={{ fontFamily: MONO, fontSize: 10, color: C.textDim, textTransform: "uppercase", letterSpacing: 1 }}>{s.label}</div>
                  <div style={{ fontFamily: SANS, fontSize: 13, color: C.textMuted, marginTop: 2 }}>{s.value}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* -- Setlist Output -- */}
        {step === 3 && setlist.length > 0 && (
          <div style={{ animation: "fadeUp 0.5s ease" }}>
            {/* Reasoning */}
            {reasoning && (
              <div style={{
                marginTop: 24, padding: "14px 20px", borderRadius: 8,
                background: `linear-gradient(135deg, rgba(232,89,60,0.06), rgba(212,168,67,0.06))`,
                border: `1px solid ${C.accent}22`,
              }}>
                <div style={{
                  fontFamily: MONO, fontSize: 10, color: C.accent, letterSpacing: 1.5,
                  textTransform: "uppercase", marginBottom: 6,
                }}>
                  agent reasoning
                </div>
                <p style={{ fontFamily: SANS, fontSize: 13, color: C.textMuted, lineHeight: 1.6 }}>
                  {reasoning}
                </p>
              </div>
            )}

            {/* Setlist header */}
            <div style={{
              marginTop: 20, padding: "16px 20px 0",
              display: "flex", justifyContent: "space-between", alignItems: "baseline",
            }}>
              <div>
                <span style={{
                  fontFamily: MONO, fontSize: 11, color: C.textDim, letterSpacing: 1.5,
                  textTransform: "uppercase",
                }}>
                  your setlist
                </span>
                <span style={{
                  fontFamily: MONO, fontSize: 11, color: C.accent,
                  marginLeft: 12,
                }}>
                  {setlist.length} tracks
                </span>
              </div>
              <span style={{ fontFamily: MONO, fontSize: 11, color: C.textDim }}>
                {Math.min(...setlist.map(t => t.bpm))}–{Math.max(...setlist.map(t => t.bpm))} BPM
              </span>
            </div>

            {/* Track list */}
            <div style={{
              marginTop: 12, borderRadius: 8, overflow: "hidden",
              border: `1px solid ${C.border}`, background: C.surface,
            }}>
              {setlist.map((track, i) => (
                <TrackRow key={track.title + i} track={track} index={i} total={setlist.length} />
              ))}
            </div>

            {/* Energy arc visualization */}
            <div style={{
              marginTop: 16, padding: "16px 20px", borderRadius: 8,
              border: `1px solid ${C.border}`, background: C.surface,
            }}>
              <div style={{
                fontFamily: MONO, fontSize: 10, color: C.textDim, letterSpacing: 1.5,
                textTransform: "uppercase", marginBottom: 12,
              }}>
                energy arc
              </div>
              <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 48 }}>
                {setlist.map((track, i) => {
                  const h = 12 + (track.bpm - Math.min(...setlist.map(t => t.bpm))) /
                    (Math.max(...setlist.map(t => t.bpm)) - Math.min(...setlist.map(t => t.bpm)) || 1) * 36;
                  const progress = setlist.length > 1 ? i / (setlist.length - 1) : 0;
                  return (
                    <div
                      key={i}
                      title={`${track.title} — ${track.bpm} BPM`}
                      style={{
                        flex: 1, height: h, borderRadius: "3px 3px 0 0",
                        background: `linear-gradient(180deg, ${C.accent}${Math.round(40 + progress * 60).toString(16)}, ${C.accent3}${Math.round(20 + (1 - progress) * 40).toString(16)})`,
                        transition: "height 0.5s ease",
                        cursor: "default",
                      }}
                    />
                  );
                })}
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6 }}>
                <span style={{ fontFamily: MONO, fontSize: 10, color: C.textDim }}>opener</span>
                <span style={{ fontFamily: MONO, fontSize: 10, color: C.textDim }}>peak</span>
                <span style={{ fontFamily: MONO, fontSize: 10, color: C.textDim }}>closer</span>
              </div>
            </div>
          </div>
        )}

        {/* -- Footer note -- */}
        <div style={{
          marginTop: 40, textAlign: "center", padding: "20px 0",
          borderTop: `1px solid ${C.border}`,
        }}>
          <p style={{ fontFamily: MONO, fontSize: 11, color: C.textDim, lineHeight: 1.8 }}>
            Powered by 1001Tracklists data + Claude API<br />
            Stage 1: scrape artist sets → Stage 2: characterize tracks → Stage 3: AI-sequenced setlist
          </p>
          <p style={{ fontFamily: MONO, fontSize: 10, color: C.textDim + "88", marginTop: 8 }}>
            Demo mode — connect a 1001tracklists scraper for live data
          </p>
        </div>
      </div>
    </div>
  );
}
