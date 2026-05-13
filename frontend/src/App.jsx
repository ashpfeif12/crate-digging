import { useState, useRef, useEffect, useCallback } from "react";

const M = "'IBM Plex Mono', 'Courier New', monospace";
const S = "'IBM Plex Sans', 'Helvetica Neue', sans-serif";
const C = {
  bg: "#0D0D0D", sf: "#161616", sf2: "#1E1E1E",
  bd: "#2A2A2A", bdH: "#444",
  tx: "#E8E4DC", txM: "#8A8578", txD: "#5A5750",
  ac: "#E8593C", ac2: "#D4A843", ac3: "#5DCAA5",
  wax: "#1A1412",
};

const SYSTEM_PROMPT = `You are Crate Digger, an AI DJ agent. You have web search. Your job:

1. SEARCH for the artist's recent DJ sets on 1001tracklists and Ticketmaster
2. PARSE track names, artists, and metadata from search results
3. FILTER and SEQUENCE tracks based on the user's vibe description
4. Return a structured JSON setlist

RULES:
- Search using queries like: site:1001tracklists.com "ARTIST" tracklist 2024 2025
- Search Ticketmaster for complete numbered setlists: ticketmaster "ARTIST" setlist
- Extract BPM, key, label, genre when visible in search snippets
- Only include tracks that appear in real search results. NEVER invent tracks.
- Sequence for smooth transitions: compatible keys, gradual BPM changes, energy arc
- For "most viewed" mode, prioritize festival sets (Coachella, Glastonbury, Tomorrowland etc.)
- For "most liked" mode, prioritize radio mixes and intimate club sets

Return ONLY valid JSON (no markdown, no backticks, no preamble):
{
  "tracklists_found": [
    {"title": "Set name", "date": "YYYY-MM-DD", "venue": "Venue", "track_count": N}
  ],
  "setlist": [
    {
      "position": 1,
      "title": "Track Title",
      "artist": "Artist Name",
      "bpm": 126,
      "key": "Am",
      "label": "Label Name",
      "genre": "House",
      "set_position": "opener|warmup|peak|closer",
      "source_set": "Which set this came from"
    }
  ],
  "reasoning": "2-3 sentences about your selection and sequencing logic",
  "stats": {
    "total_tracks_found": N,
    "sets_analyzed": N,
    "bpm_range": "120-132"
  }
}

BPM/key may be null if not found. set_position should reflect the energy arc you're building.
Aim for 8-14 tracks in the final setlist.`;

function Vinyl({ spinning, size = 48 }) {
  return (
    <div style={{
      width: size, height: size, borderRadius: "50%", flexShrink: 0,
      background: `radial-gradient(circle at center, ${C.ac} ${size*0.12}px, ${C.wax} ${size*0.14}px, ${C.wax} ${size*0.2}px, #222 ${size*0.22}px, #1a1a1a ${size*0.27}px, #222 ${size*0.31}px, #1a1a1a ${size*0.35}px, #222 ${size*0.39}px, #1a1a1a ${size*0.43}px, #222 ${size*0.47}px, transparent ${size*0.5}px)`,
      animation: spinning ? "spin 2s linear infinite" : "none",
    }}/>
  );
}

function TrackRow({ track, index, total }) {
  const progress = total > 1 ? index / (total - 1) : 0;
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 14, padding: "14px 16px",
      borderBottom: `1px solid ${C.bd}`,
      background: index % 2 === 0 ? "transparent" : "rgba(255,255,255,0.015)",
    }}
      onMouseEnter={e => e.currentTarget.style.background = "rgba(255,255,255,0.04)"}
      onMouseLeave={e => e.currentTarget.style.background = index % 2 === 0 ? "transparent" : "rgba(255,255,255,0.015)"}
    >
      <div style={{ width: 36, textAlign: "center", position: "relative" }}>
        <span style={{ fontFamily: M, fontSize: 13, color: C.txM }}>{String(index + 1).padStart(2, "0")}</span>
        <div style={{ position: "absolute", left: 0, bottom: -14, width: "100%", height: 3, borderRadius: 2, background: C.bd, overflow: "hidden" }}>
          <div style={{
            width: `${20 + progress * 80}%`, height: "100%", borderRadius: 2,
            background: progress < 0.5
              ? `color-mix(in srgb, ${C.ac3} ${(1 - progress * 2) * 100}%, ${C.ac2})`
              : `color-mix(in srgb, ${C.ac2} ${(1 - (progress - 0.5) * 2) * 100}%, ${C.ac})`,
          }}/>
        </div>
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontFamily: S, fontSize: 14, fontWeight: 500, color: C.tx, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{track.title}</div>
        <div style={{ fontFamily: S, fontSize: 12, color: C.txM, marginTop: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{track.artist}</div>
      </div>
      <div style={{ display: "flex", gap: 6, alignItems: "center", flexShrink: 0, flexWrap: "wrap", justifyContent: "flex-end" }}>
        {track.bpm && <span style={{ fontFamily: M, fontSize: 11, color: C.ac2, background: "rgba(212,168,67,0.1)", padding: "3px 8px", borderRadius: 4 }}>{track.bpm}</span>}
        {track.key && <span style={{ fontFamily: M, fontSize: 11, color: C.ac3, background: "rgba(93,202,165,0.1)", padding: "3px 8px", borderRadius: 4 }}>{track.key}</span>}
        {track.label && <span style={{ fontFamily: M, fontSize: 11, color: C.txD, padding: "3px 8px" }}>{track.label}</span>}
      </div>
    </div>
  );
}

const MODES = [
  { id: "recent", label: "Last 5 sets", desc: "Most recent", icon: "⏱" },
  { id: "most_viewed", label: "Most viewed", desc: "Festival bangers", icon: "👁" },
  { id: "most_liked", label: "Most liked", desc: "Community picks", icon: "♥" },
];

const VIBES = [
  "dark minimal, 126-130bpm, late night",
  "groovy disco house, 120-124bpm, sunset",
  "high energy techno, 132+bpm, peak time",
  "melodic & emotional, 122-128bpm, sunrise",
];

export default function CrateDigger() {
  const [artist, setArtist] = useState("");
  const [mode, setMode] = useState("recent");
  const [vibe, setVibe] = useState("");
  const [step, setStep] = useState(0);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [statusMsg, setStatusMsg] = useState("");
  const vibeRef = useRef(null);

  const handleDig = useCallback(async () => {
    if (!artist.trim() || !vibe.trim()) { setError("Need both an artist and a vibe description."); return; }
    setError(""); setStep(1); setResult(null); setStatusMsg("Searching for sets...");

    const modeDesc = mode === "recent" ? "5 most recent" : mode === "most_viewed" ? "5 most viewed/popular festival" : "5 most liked";
    const userPrompt = `Find the ${modeDesc} sets by ${artist} on 1001tracklists. Search for their tracklists, then search Ticketmaster for their complete setlists with track listings. From the tracks you find across these sets, build me an ordered setlist matching this vibe: "${vibe}". Remember: search first, then build. Only use real tracks from search results.`;

    try {
      const response = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: "claude-sonnet-4-20250514",
          max_tokens: 4096,
          system: SYSTEM_PROMPT,
          tools: [{ type: "web_search_20250305", name: "web_search" }],
          messages: [{ role: "user", content: userPrompt }],
        }),
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.error?.message || `API returned ${response.status}`);
      }

      const data = await response.json();
      const searchCalls = data.content?.filter(b => b.type === "server_tool_use")?.length || 0;
      setStatusMsg(`Ran ${searchCalls} searches, building setlist...`);
      setStep(2);

      const textBlocks = data.content?.filter(b => b.type === "text") || [];
      const fullText = textBlocks.map(b => b.text).join("\n");

      let parsed = null;
      try {
        const jsonMatch = fullText.match(/\{[\s\S]*"setlist"[\s\S]*\}/);
        if (jsonMatch) parsed = JSON.parse(jsonMatch[0].replace(/```json|```/g, "").trim());
      } catch (e1) {
        try {
          parsed = JSON.parse(fullText.replace(/```json|```/g, "").replace(/^[^{]*/, "").replace(/[^}]*$/, ""));
        } catch (e2) { console.error("Parse failed:", fullText.substring(0, 500)); }
      }

      if (parsed?.setlist?.length > 0) {
        const total = parsed.setlist.length;
        parsed.setlist.forEach((t, i) => {
          if (!t.set_position) {
            if (i < total * 0.15) t.set_position = "opener";
            else if (i < total * 0.35) t.set_position = "warmup";
            else if (i < total * 0.8) t.set_position = "peak";
            else t.set_position = "closer";
          }
        });
        setResult(parsed); setStep(3);
      } else {
        setError("Agent returned results but couldn't structure them. Check console.");
        console.log("Raw:", fullText); setStep(0);
      }
    } catch (err) {
      console.error("Dig failed:", err);
      setError(err.message || "Something went wrong."); setStep(0);
    }
  }, [artist, mode, vibe]);

  useEffect(() => {
    const h = (e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && step === 0) handleDig(); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [handleDig, step]);

  const setlist = result?.setlist || [];
  const bpms = setlist.filter(t => t.bpm).map(t => t.bpm);

  return (
    <div style={{ fontFamily: S, color: C.tx, minHeight: "100vh", background: `linear-gradient(180deg, ${C.bg} 0%, #0a0a0a 100%)`, padding: "0 0 60px" }}>
      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes fadeUp { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes pulse { 0%,100% { opacity: 0.4; } 50% { opacity: 1; } }
      `}</style>

      {/* Header */}
      <div style={{ padding: "40px 32px 32px", borderBottom: `1px solid ${C.bd}`, background: `linear-gradient(180deg, rgba(232,89,60,0.04) 0%, transparent 100%)` }}>
        <div style={{ maxWidth: 800, margin: "0 auto", display: "flex", alignItems: "center", gap: 16 }}>
          <Vinyl spinning={step === 1 || step === 2} />
          <div>
            <h1 style={{ fontFamily: M, fontSize: 28, fontWeight: 600, letterSpacing: -1, lineHeight: 1.1 }}>crate<span style={{ color: C.ac }}>digger</span></h1>
            <p style={{ fontFamily: M, fontSize: 11, color: C.txD, letterSpacing: 2, textTransform: "uppercase", marginTop: 4 }}>claude + web search → ai setlist builder</p>
          </div>
        </div>
      </div>

      <div style={{ maxWidth: 800, margin: "0 auto", padding: "0 24px" }}>
        {/* Input */}
        <div style={{ marginTop: 32, padding: 24, borderRadius: 8, border: `1px solid ${C.bd}`, background: C.sf }}>
          <label style={{ fontFamily: M, fontSize: 11, color: C.txD, letterSpacing: 1.5, textTransform: "uppercase", display: "block", marginBottom: 8 }}>artist</label>
          <input value={artist} onChange={e => setArtist(e.target.value)} placeholder="e.g. Peggy Gou, Keinemusik, Dixon..." disabled={step > 0 && step < 3}
            style={{ width: "100%", padding: "12px 16px", fontFamily: S, fontSize: 16, background: C.sf2, border: `1px solid ${C.bd}`, borderRadius: 6, color: C.tx }}
            onFocus={e => e.target.style.borderColor = C.ac} onBlur={e => e.target.style.borderColor = C.bd} />

          <label style={{ fontFamily: M, fontSize: 11, color: C.txD, letterSpacing: 1.5, textTransform: "uppercase", display: "block", marginTop: 24, marginBottom: 10 }}>pull sets by</label>
          <div style={{ display: "flex", gap: 8 }}>
            {MODES.map(m => (
              <button key={m.id} onClick={() => (step === 0 || step === 3) && setMode(m.id)}
                style={{ flex: 1, padding: "12px 8px", borderRadius: 6, cursor: "pointer", textAlign: "center", background: mode === m.id ? C.ac + "18" : C.sf2, border: `1px solid ${mode === m.id ? C.ac + "66" : C.bd}` }}>
                <div style={{ fontSize: 18, marginBottom: 4 }}>{m.icon}</div>
                <div style={{ fontFamily: S, fontSize: 13, fontWeight: 500, color: mode === m.id ? C.ac : C.tx }}>{m.label}</div>
                <div style={{ fontFamily: M, fontSize: 10, color: C.txD, marginTop: 2 }}>{m.desc}</div>
              </button>
            ))}
          </div>

          <label style={{ fontFamily: M, fontSize: 11, color: C.txD, letterSpacing: 1.5, textTransform: "uppercase", display: "block", marginTop: 24, marginBottom: 8 }}>describe the vibe</label>
          <textarea ref={vibeRef} value={vibe} onChange={e => setVibe(e.target.value)} placeholder="dark minimal, 126-130bpm, late night..." disabled={step > 0 && step < 3} rows={2}
            style={{ width: "100%", padding: "12px 16px", fontFamily: S, fontSize: 15, background: C.sf2, border: `1px solid ${C.bd}`, borderRadius: 6, color: C.tx, resize: "vertical", lineHeight: 1.5 }}
            onFocus={e => e.target.style.borderColor = C.ac} onBlur={e => e.target.style.borderColor = C.bd} />
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 10 }}>
            {VIBES.map(v => (
              <button key={v} onClick={() => { setVibe(v); vibeRef.current?.focus(); }}
                style={{ padding: "5px 12px", borderRadius: 20, cursor: "pointer", background: vibe === v ? C.ac2 + "22" : "transparent", border: `1px solid ${vibe === v ? C.ac2 + "66" : C.bd}`, fontFamily: M, fontSize: 11, color: vibe === v ? C.ac2 : C.txM }}>{v}</button>
            ))}
          </div>

          {error && <div style={{ marginTop: 16, padding: "10px 14px", borderRadius: 6, background: "rgba(232,89,60,0.1)", border: `1px solid ${C.ac}44`, fontFamily: M, fontSize: 12, color: C.ac }}>{error}</div>}

          <button onClick={step === 3 ? () => { setStep(0); setResult(null); } : handleDig} disabled={step > 0 && step < 3}
            style={{ marginTop: 24, width: "100%", padding: "14px 24px", borderRadius: 6, background: step === 3 ? C.sf2 : C.ac, border: step === 3 ? `1px solid ${C.bd}` : "none", color: step === 3 ? C.tx : "#fff", fontFamily: M, fontSize: 14, fontWeight: 600, letterSpacing: 1, textTransform: "uppercase", cursor: step > 0 && step < 3 ? "wait" : "pointer", opacity: (step > 0 && step < 3) ? 0.6 : 1 }}>
            {step === 0 && "dig"}{step === 1 && "searching 1001tracklists + ticketmaster..."}{step === 2 && "building setlist..."}{step === 3 && "new dig"}
          </button>
        </div>

        {/* Loading */}
        {(step === 1 || step === 2) && (
          <div style={{ marginTop: 24, padding: 32, textAlign: "center", border: `1px solid ${C.bd}`, borderRadius: 8, background: C.sf }}>
            <Vinyl spinning size={56} />
            <p style={{ fontFamily: M, fontSize: 13, color: C.txM, marginTop: 16, animation: "pulse 1.5s ease infinite" }}>{statusMsg}</p>
            <p style={{ fontFamily: M, fontSize: 11, color: C.txD, marginTop: 8 }}>{step === 1 ? "Claude is searching the web for tracklists and track metadata" : "Filtering by vibe, matching keys, building energy arc"}</p>
          </div>
        )}

        {/* Results */}
        {step === 3 && result && (
          <div style={{ animation: "fadeUp 0.5s ease" }}>
            {result.tracklists_found?.length > 0 && (
              <div style={{ marginTop: 24, padding: "14px 20px", borderRadius: 8, border: `1px solid ${C.bd}`, background: C.sf }}>
                <div style={{ fontFamily: M, fontSize: 10, color: C.txD, letterSpacing: 1.5, textTransform: "uppercase", marginBottom: 10 }}>sets analyzed</div>
                {result.tracklists_found.map((tl, i) => (
                  <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0", borderBottom: i < result.tracklists_found.length - 1 ? `1px solid ${C.bd}` : "none" }}>
                    <span style={{ fontFamily: S, fontSize: 13, color: C.txM }}>{tl.title || tl.venue}</span>
                    <span style={{ fontFamily: M, fontSize: 11, color: C.txD }}>{tl.date}{tl.track_count ? ` · ${tl.track_count} tracks` : ""}</span>
                  </div>
                ))}
              </div>
            )}

            {result.reasoning && (
              <div style={{ marginTop: 20, padding: "14px 20px", borderRadius: 8, background: `linear-gradient(135deg, rgba(232,89,60,0.06), rgba(212,168,67,0.06))`, border: `1px solid ${C.ac}22` }}>
                <div style={{ fontFamily: M, fontSize: 10, color: C.ac, letterSpacing: 1.5, textTransform: "uppercase", marginBottom: 6 }}>agent reasoning</div>
                <p style={{ fontFamily: S, fontSize: 13, color: C.txM, lineHeight: 1.6 }}>{result.reasoning}</p>
              </div>
            )}

            <div style={{ marginTop: 20, padding: "16px 20px 0", display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
              <div>
                <span style={{ fontFamily: M, fontSize: 11, color: C.txD, letterSpacing: 1.5, textTransform: "uppercase" }}>your setlist</span>
                <span style={{ fontFamily: M, fontSize: 11, color: C.ac, marginLeft: 12 }}>{setlist.length} tracks</span>
              </div>
              {bpms.length > 0 && <span style={{ fontFamily: M, fontSize: 11, color: C.txD }}>{Math.min(...bpms)}–{Math.max(...bpms)} BPM</span>}
            </div>

            <div style={{ marginTop: 12, borderRadius: 8, overflow: "hidden", border: `1px solid ${C.bd}`, background: C.sf }}>
              {setlist.map((track, i) => <TrackRow key={`${track.title}-${i}`} track={track} index={i} total={setlist.length} />)}
            </div>

            {bpms.length > 1 && (
              <div style={{ marginTop: 16, padding: "16px 20px", borderRadius: 8, border: `1px solid ${C.bd}`, background: C.sf }}>
                <div style={{ fontFamily: M, fontSize: 10, color: C.txD, letterSpacing: 1.5, textTransform: "uppercase", marginBottom: 12 }}>energy arc</div>
                <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 48 }}>
                  {setlist.map((track, i) => {
                    const bpm = track.bpm || (bpms.reduce((a,b) => a+b, 0) / bpms.length);
                    const range = Math.max(...bpms) - Math.min(...bpms) || 1;
                    const h = 12 + ((bpm - Math.min(...bpms)) / range) * 36;
                    const p = setlist.length > 1 ? i / (setlist.length - 1) : 0;
                    return <div key={i} title={`${track.title} — ${bpm} BPM`} style={{ flex: 1, height: h, borderRadius: "3px 3px 0 0", background: `linear-gradient(180deg, ${C.ac}${Math.round(40 + p * 60).toString(16).padStart(2,'0')}, ${C.ac3}${Math.round(20 + (1-p) * 40).toString(16).padStart(2,'0')})` }}/>;
                  })}
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6 }}>
                  <span style={{ fontFamily: M, fontSize: 10, color: C.txD }}>opener</span>
                  <span style={{ fontFamily: M, fontSize: 10, color: C.txD }}>peak</span>
                  <span style={{ fontFamily: M, fontSize: 10, color: C.txD }}>closer</span>
                </div>
              </div>
            )}

            {result.stats && (
              <div style={{ marginTop: 16, padding: "12px 20px", borderRadius: 8, border: `1px solid ${C.bd}`, background: C.sf, display: "flex", gap: 24, flexWrap: "wrap" }}>
                {[{ label: "Sets analyzed", value: result.stats.sets_analyzed }, { label: "Tracks found", value: result.stats.total_tracks_found }, { label: "BPM range", value: result.stats.bpm_range }].filter(s => s.value).map(s => (
                  <div key={s.label}>
                    <div style={{ fontFamily: M, fontSize: 10, color: C.txD, textTransform: "uppercase", letterSpacing: 1 }}>{s.label}</div>
                    <div style={{ fontFamily: M, fontSize: 14, color: C.ac2, marginTop: 2 }}>{s.value}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <div style={{ marginTop: 40, textAlign: "center", padding: "20px 0", borderTop: `1px solid ${C.bd}` }}>
          <p style={{ fontFamily: M, fontSize: 11, color: C.txD, lineHeight: 1.8 }}>claude + web search → ai setlist builder<br/>no backend, no scraping — one api call does everything</p>
        </div>
      </div>
    </div>
  );
}
