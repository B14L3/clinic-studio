"use client";

import { useState } from "react";
import {
  Sparkles,
  Loader2,
  Copy,
  Check,
  Video,
  AlertCircle,
  ScanSearch,
} from "lucide-react";

const API_BASE = "http://localhost:8000";

interface BlueprintOption {
  id: number;
  name: string;
  category: string;
  duration: number;
  segment_count: number;
}

interface AnalyzeResponse {
  recommended_blueprint_id: number;
  blueprint_name: string;
  confidence: number;
  reasoning: string;
  blueprints: BlueprintOption[];
}

interface ReelCopy {
  on_screen_hook: string;
  caption: string;
  call_to_action: string;
  hashtags: string[];
}

interface GenerateResponse {
  status: string;
  video_path: string;
  filename: string;
  video_url: string;
  duration: number;
  copywriting: ReelCopy;
}

export default function StudioDashboard() {
  // Step 1: source footage
  const [sourcePath, setSourcePath] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);

  // Step 2: AI recommendation + blueprint list/selection
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  // Step 3: treatment details + generate
  const [treatment, setTreatment] = useState("");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Step 4: output
  const [result, setResult] = useState<GenerateResponse | null>(null);
  const [copiedField, setCopiedField] = useState<string | null>(null);

  async function handleAnalyze() {
    if (!sourcePath) return;
    setAnalyzing(true);
    setAnalyzeError(null);
    setAnalysis(null);
    setSelectedId(null);
    setResult(null);
    try {
      const res = await fetch(`${API_BASE}/api/reels/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_video_path: sourcePath }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "שגיאה בניתוח הקליפ");
      }
      const data: AnalyzeResponse = await res.json();
      setAnalysis(data);
      setSelectedId(data.recommended_blueprint_id);
    } catch (e) {
      setAnalyzeError(e instanceof Error ? e.message : "משהו השתבש");
    } finally {
      setAnalyzing(false);
    }
  }

  async function handleGenerate() {
    if (!selectedId || !treatment) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch(`${API_BASE}/api/reels/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          blueprint_id: selectedId,
          source_video_path: sourcePath,
          treatment_type: treatment,
          extra_notes: notes || null,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "שגיאה בשרת");
      }
      const data: GenerateResponse = await res.json();
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "משהו השתבש");
    } finally {
      setLoading(false);
    }
  }

  function copyToClipboard(text: string, field: string) {
    navigator.clipboard.writeText(text);
    setCopiedField(field);
    setTimeout(() => setCopiedField(null), 1500);
  }

  return (
    <main dir="rtl" className="min-h-screen bg-stone-50 text-zinc-900 p-6 md:p-10">
      <div className="max-w-3xl mx-auto space-y-8">
        <header className="space-y-1">
          <h1 className="text-2xl font-semibold flex items-center gap-2">
            <Sparkles className="w-6 h-6 text-rose-500" />
            Clinic Studio — יצירת ריל אוטומטית
          </h1>
          <p className="text-sm text-zinc-500">
            העלי נתיב לקליפ מקור, קבלי בלופרינט מומלץ מה-AI, והרכיבי ריל מוכן תוך דקות.
          </p>
        </header>

        {/* Step 1: Source Footage */}
        <section className="bg-white rounded-2xl shadow-sm border border-zinc-200 p-6 space-y-4">
          <h2 className="text-xs font-semibold text-zinc-400 tracking-wide">שלב 1 · קליפ מקור</h2>
          <div>
            <label className="block text-sm font-medium mb-1">נתיב קליפ מקור</label>
            <input
              data-testid="source-path-input"
              value={sourcePath}
              onChange={(e) => setSourcePath(e.target.value)}
              className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-rose-300"
              placeholder="references/treatment_flow/clip.mp4"
            />
            <p className="text-xs text-zinc-400 mt-1">
              נתיב מקומי יחסי ל- D:\ClinicStudio, לדוגמה references/treatment_flow/clip.mp4
            </p>
          </div>
          <button
            type="button"
            data-testid="analyze-button"
            onClick={handleAnalyze}
            disabled={analyzing || !sourcePath}
            className="w-full flex items-center justify-center gap-2 rounded-xl bg-rose-500 text-white py-3 font-medium disabled:opacity-40 hover:bg-rose-600 transition"
          >
            {analyzing ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" /> מנתחת קליפ עם AI...
              </>
            ) : (
              <>
                <ScanSearch className="w-4 h-4" /> Analyze Footage with AI
              </>
            )}
          </button>
          {analyzeError && (
            <p className="text-sm text-red-500 flex items-center gap-1.5">
              <AlertCircle className="w-4 h-4" /> {analyzeError}
            </p>
          )}
        </section>

        {/* Step 2: AI Recommendation & blueprint selection */}
        <section
          data-testid="blueprint-selection"
          className="bg-white rounded-2xl shadow-sm border border-zinc-200 p-6 space-y-5"
        >
          <h2 className="text-xs font-semibold text-zinc-400 tracking-wide">
            שלב 2 · המלצת AI ובחירת בלופרינט
          </h2>

          {analysis ? (
            <>
              <div
                data-testid="ai-recommendation-card"
                className="rounded-xl border border-rose-200 bg-rose-50 p-4 space-y-2"
              >
                <span className="inline-flex items-center gap-1 text-xs font-semibold text-rose-600 bg-rose-100 rounded-full px-2 py-0.5">
                  <Sparkles className="w-3 h-3" /> AI Recommended
                </span>
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-medium">{analysis.blueprint_name}</span>
                  <span className="text-xs text-zinc-500 shrink-0">
                    {Math.round(analysis.confidence * 100)}% ביטחון
                  </span>
                </div>
                <p dir="rtl" data-testid="ai-reasoning" className="text-sm text-zinc-600">
                  {analysis.reasoning}
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {analysis.blueprints.map((bp) => (
                  <button
                    key={bp.id}
                    type="button"
                    data-testid={`blueprint-card-${bp.id}`}
                    onClick={() => setSelectedId(bp.id)}
                    className={`text-right rounded-xl border p-4 transition ${
                      selectedId === bp.id
                        ? "border-rose-400 bg-rose-50"
                        : "border-zinc-200 hover:border-zinc-300"
                    }`}
                  >
                    <div className="font-medium truncate flex items-center gap-1.5">
                      {bp.name}
                      {bp.id === analysis.recommended_blueprint_id && (
                        <Sparkles className="w-3.5 h-3.5 text-rose-500 shrink-0" />
                      )}
                    </div>
                    <div className="text-xs text-zinc-500 mt-1">
                      {bp.category} · {bp.duration}s · {bp.segment_count} קאטים
                    </div>
                  </button>
                ))}
              </div>
            </>
          ) : (
            <p className="text-sm text-zinc-400">
              נתחי קליפ מקור כדי לקבל המלצת AI ולבחור בלופרינט.
            </p>
          )}
        </section>

        {/* Step 3: Treatment details + generate */}
        <section className="bg-white rounded-2xl shadow-sm border border-zinc-200 p-6 space-y-5">
          <h2 className="text-xs font-semibold text-zinc-400 tracking-wide">שלב 3 · פרטי טיפול והפקה</h2>

          <div>
            <label className="block text-sm font-medium mb-1">סוג טיפול</label>
            <input
              data-testid="treatment-input"
              value={treatment}
              onChange={(e) => setTreatment(e.target.value)}
              className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-rose-300"
              placeholder="טיפול מזותרפיה"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">הערות נוספות (אופציונלי)</label>
            <textarea
              data-testid="notes-input"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-rose-300"
            />
          </div>

          <button
            type="button"
            data-testid="generate-button"
            onClick={handleGenerate}
            disabled={loading || !selectedId || !treatment}
            className="w-full flex items-center justify-center gap-2 rounded-xl bg-zinc-900 text-white py-3 font-medium disabled:opacity-40 hover:bg-zinc-800 transition"
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" /> מרכיבה ריל...
              </>
            ) : (
              <>
                <Video className="w-4 h-4" /> צרי ריל
              </>
            )}
          </button>

          {error && (
            <p className="text-sm text-red-500 flex items-center gap-1.5">
              <AlertCircle className="w-4 h-4" /> {error}
            </p>
          )}
        </section>

        {/* Step 4: Output & copy */}
        {result && (
          <section
            data-testid="result-section"
            className="bg-white rounded-2xl shadow-sm border border-zinc-200 p-6"
          >
            <div className="flex flex-col sm:flex-row gap-6">
              <video
                src={`${API_BASE}${result.video_url}`}
                controls
                className="w-full sm:w-[220px] aspect-[9/16] rounded-xl bg-black object-cover shrink-0"
              />
              <div className="flex-1 space-y-4">
                <CopyCard
                  label="הוק (On-screen)"
                  text={result.copywriting.on_screen_hook}
                  field="hook"
                  copiedField={copiedField}
                  onCopy={copyToClipboard}
                />
                <CopyCard
                  label="כתובית"
                  text={result.copywriting.caption}
                  field="caption"
                  copiedField={copiedField}
                  onCopy={copyToClipboard}
                />
                <CopyCard
                  label="קריאה לפעולה"
                  text={result.copywriting.call_to_action}
                  field="cta"
                  copiedField={copiedField}
                  onCopy={copyToClipboard}
                />
                <CopyCard
                  label="האשטגים"
                  text={result.copywriting.hashtags.join(" ")}
                  field="hashtags"
                  copiedField={copiedField}
                  onCopy={copyToClipboard}
                />
              </div>
            </div>
          </section>
        )}
      </div>
    </main>
  );
}

function CopyCard({
  label,
  text,
  field,
  copiedField,
  onCopy,
}: {
  label: string;
  text: string;
  field: string;
  copiedField: string | null;
  onCopy: (text: string, field: string) => void;
}) {
  return (
    <div className="rounded-xl border border-zinc-200 p-3">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-medium text-zinc-500">{label}</span>
        <button
          type="button"
          onClick={() => onCopy(text, field)}
          className="text-xs flex items-center gap-1 text-zinc-500 hover:text-zinc-900"
        >
          {copiedField === field ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
          {copiedField === field ? "הועתק" : "העתק"}
        </button>
      </div>
      <p className="text-sm whitespace-pre-line">{text}</p>
    </div>
  );
}
