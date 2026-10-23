"use client";

import { useEffect, useState } from "react";
import {
  Sparkles,
  Loader2,
  Copy,
  Check,
  Video,
  AlertCircle,
  ScanSearch,
  UploadCloud,
  ChevronDown,
} from "lucide-react";

interface Segment {
  start_time: number;
  end_time: number;
  action_description: string;
}

interface RawClip {
  filename: string;
  file_path: string;
  size_mb: number;
}

interface AnalyzeResponse {
  segments: Segment[];
  visual_summary_hebrew: string;
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
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [accordionOpen, setAccordionOpen] = useState(false);
  const [rawClips, setRawClips] = useState<RawClip[]>([]);

  // Step 2: editable highlight timeline
  const [segments, setSegments] = useState<Segment[]>([]);
  const [visualSummary, setVisualSummary] = useState("");

  // Step 3: treatment details + generate
  const [treatment, setTreatment] = useState("");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Step 4: output
  const [result, setResult] = useState<GenerateResponse | null>(null);
  const [copiedField, setCopiedField] = useState<string | null>(null);

  useEffect(() => {
    if (!accordionOpen) return;
    fetch("/api/raw-clips")
      .then((r) => r.json())
      .then((data: RawClip[]) => setRawClips(data))
      .catch(() => setRawClips([]));
  }, [accordionOpen]);

  async function handleAnalyze(pathOverride?: string) {
    const path = pathOverride ?? sourcePath;
    if (!path) return;
    setAnalyzing(true);
    setAnalyzeError(null);
    setSegments([]);
    setVisualSummary("");
    setResult(null);
    try {
      const res = await fetch("/api/reels/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_video_path: path }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "שגיאה בניתוח הקליפ");
      }
      const data: AnalyzeResponse = await res.json();
      setSegments(data.segments);
      setVisualSummary(data.visual_summary_hebrew);
    } catch (e) {
      setAnalyzeError(e instanceof Error ? e.message : "משהו השתבש");
    } finally {
      setAnalyzing(false);
    }
  }

  async function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-selecting the same file again later
    if (!file) return;

    setUploading(true);
    setUploadError(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch("/api/upload", { method: "POST", body: formData });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "העלאת הקובץ נכשלה");
      }
      const data: { filename: string; file_path: string; size_mb: number } = await res.json();
      setSourcePath(data.file_path);
      setUploading(false);
      await handleAnalyze(data.file_path);
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : "משהו השתבש בהעלאה");
      setUploading(false);
    }
  }

  function handleSegmentChange(index: number, field: keyof Segment, value: string) {
    setSegments((current) =>
      current.map((segment, i) => {
        if (i !== index) return segment;
        if (field === "action_description") {
          return { ...segment, action_description: value };
        }
        return { ...segment, [field]: Number(value) };
      }),
    );
  }

  function handleDeleteSegment(index: number) {
    setSegments((current) => current.filter((_, i) => i !== index));
  }

  async function handleGenerate() {
    if (segments.length === 0 || !treatment) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch("/api/reels/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_video_path: sourcePath,
          segments,
          visual_summary: visualSummary || null,
          treatment_name: treatment,
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
            העלי קליפ מקור, ערכי את חיתוכי ה-AI, והרכיבי ריל מוכן תוך דקות.
          </p>
        </header>

        {/* Step 1: Source Footage */}
        <section className="bg-white rounded-2xl shadow-sm border border-zinc-200 p-6 space-y-4">
          <h2 className="text-xs font-semibold text-zinc-400 tracking-wide">שלב 1 · קליפ מקור</h2>

          <input
            id="raw-clip-file-input"
            type="file"
            accept="video/*,video/mp4,video/quicktime"
            data-testid="file-input"
            className="hidden"
            disabled={uploading}
            onChange={handleFileSelect}
          />

          {/*
            A native <label for=...> is used instead of a button that proxies
            a programmatic .click() on the hidden input. iOS Safari frequently
            refuses to open the native photo/file picker when .click() is
            called via JS on a display:none input, even from a real tap
            handler — but tapping a label associated with a file input is
            spec-guaranteed to activate it on every browser, including iOS.
          */}
          <label
            htmlFor="raw-clip-file-input"
            data-testid="upload-button"
            aria-disabled={uploading}
            className={`w-full flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-rose-300 bg-rose-50/50 py-8 text-rose-600 font-medium transition ${
              uploading ? "opacity-50 pointer-events-none" : "cursor-pointer hover:bg-rose-50"
            }`}
          >
            {uploading ? (
              <>
                <Loader2 className="w-6 h-6 animate-spin" />
                <span data-testid="upload-progress">מעלה קובץ...</span>
              </>
            ) : (
              <>
                <UploadCloud className="w-6 h-6" />
                <span>Select Video from Device / Photo Library</span>
              </>
            )}
          </label>

          {uploadError && (
            <p className="text-sm text-red-500 flex items-center gap-1.5">
              <AlertCircle className="w-4 h-4" /> {uploadError}
            </p>
          )}

          {sourcePath && !uploading && (
            <p className="text-xs text-zinc-500">
              קליפ נבחר: <span className="font-mono">{sourcePath}</span>
            </p>
          )}

          <div className="border-t border-zinc-100 pt-3">
            <button
              type="button"
              data-testid="toggle-manual-source"
              onClick={() => setAccordionOpen((v) => !v)}
              className="text-xs text-zinc-500 hover:text-zinc-800 flex items-center gap-1"
            >
              <ChevronDown
                className={`w-3.5 h-3.5 transition-transform ${accordionOpen ? "rotate-180" : ""}`}
              />
              קבצים קיימים / הזנת נתיב ידנית (לבדיקות פיתוח)
            </button>

            {accordionOpen && (
              <div data-testid="manual-source-panel" className="mt-3 space-y-3">
                <div>
                  <label className="block text-xs font-medium text-zinc-500 mb-1">
                    קבצים שהועלו בעבר
                  </label>
                  {rawClips.length > 0 ? (
                    <div className="space-y-1 max-h-32 overflow-y-auto">
                      {rawClips.map((c) => (
                        <button
                          key={c.file_path}
                          type="button"
                          onClick={() => setSourcePath(c.file_path)}
                          className={`w-full text-right text-xs rounded-lg border px-2 py-1.5 transition ${
                            sourcePath === c.file_path
                              ? "border-rose-400 bg-rose-50"
                              : "border-zinc-200 hover:border-zinc-300"
                          }`}
                        >
                          {c.filename} · {c.size_mb}MB
                        </button>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-zinc-400">אין קבצים קיימים ב-raw_clips/.</p>
                  )}
                </div>

                <div>
                  <label className="block text-xs font-medium text-zinc-500 mb-1">
                    נתיב מקומי (לבדיקות פיתוח)
                  </label>
                  <input
                    data-testid="source-path-input"
                    value={sourcePath}
                    onChange={(e) => setSourcePath(e.target.value)}
                    className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-rose-300"
                    placeholder="references/treatment_flow/clip.mp4"
                  />
                </div>
              </div>
            )}
          </div>

          <button
            type="button"
            data-testid="analyze-button"
            onClick={() => handleAnalyze()}
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

        {/* Step 2: editable highlight timeline */}
        <section
          data-testid="segment-timeline"
          className="bg-white rounded-2xl shadow-sm border border-zinc-200 p-6 space-y-5"
        >
          <h2 className="text-xs font-semibold text-zinc-400 tracking-wide">
            שלב 2 · ציר זמן לחיתוכים
          </h2>

          {segments.length > 0 ? (
            <>
              <p dir="rtl" data-testid="visual-summary" className="text-sm text-zinc-600">
                {visualSummary}
              </p>
              <div className="space-y-3">
                {segments.map((segment, index) => (
                  <div
                    key={index}
                    data-testid={`segment-row-${index}`}
                    className="rounded-xl border border-zinc-200 p-3 space-y-2"
                  >
                    <div className="flex gap-2">
                      <label className="flex-1 text-xs text-zinc-500">
                        התחלה
                        <input
                          type="number"
                          step="0.1"
                          data-testid={`segment-start-${index}`}
                          value={segment.start_time}
                          onChange={(e) => handleSegmentChange(index, "start_time", e.target.value)}
                          className="mt-1 w-full rounded-lg border border-zinc-300 px-2 py-1.5 text-sm"
                        />
                      </label>
                      <label className="flex-1 text-xs text-zinc-500">
                        סיום
                        <input
                          type="number"
                          step="0.1"
                          data-testid={`segment-end-${index}`}
                          value={segment.end_time}
                          onChange={(e) => handleSegmentChange(index, "end_time", e.target.value)}
                          className="mt-1 w-full rounded-lg border border-zinc-300 px-2 py-1.5 text-sm"
                        />
                      </label>
                    </div>
                    <input
                      data-testid={`segment-action-${index}`}
                      value={segment.action_description}
                      onChange={(e) =>
                        handleSegmentChange(index, "action_description", e.target.value)
                      }
                      className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm"
                    />
                    <button
                      type="button"
                      data-testid={`segment-delete-${index}`}
                      onClick={() => handleDeleteSegment(index)}
                      className="text-xs text-red-500 hover:text-red-700"
                    >
                      Delete
                    </button>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p className="text-sm text-zinc-400">
              נתחי קליפ מקור כדי לקבל חיתוכים מוצעים ולערוך אותם.
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
            disabled={loading || segments.length === 0 || !treatment}
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
                src={result.video_url}
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
