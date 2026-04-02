"use client";

import { useState, useRef, useCallback } from "react";
import { ingestPDF, listDocuments, deleteDocument } from "@/lib/api";

const CATEGORIES = [
  "Regulatory",
  "Transcript",
  "ESG",
  "Research",
  "Other",
] as const;

type Category = (typeof CATEGORIES)[number];

interface UploadedDoc {
  doc_uuid:      string | null;
  source_name:   string;
  category:      string;
  document_type: string;
  file_name:     string;
  chunk_count:   number;
}

interface Props {
  onClose: () => void;
}

type PanelView = "upload" | "library";

export default function PDFIngestModal({ onClose }: Props) {
  const [view,         setView]        = useState<PanelView>("upload");

  // Upload form state
  const [file,         setFile]        = useState<File | null>(null);
  const [dragOver,     setDragOver]    = useState(false);
  const [sourceName,   setSourceName]  = useState("");
  const [category,     setCategory]    = useState<Category>("Regulatory");
  const [docType,      setDocType]     = useState("");
  const [uploading,    setUploading]   = useState(false);
  const [uploadResult, setUploadResult]= useState<{
    success: boolean; message: string; chunks?: number;
  } | null>(null);

  // Library state
  const [docs,         setDocs]        = useState<UploadedDoc[]>([]);
  const [loadingDocs,  setLoadingDocs] = useState(false);
  const [deletingId,   setDeletingId]  = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── File selection ──────────────────────────────────────────────────────

  function handleFileSelect(selected: File | null) {
    if (!selected) return;
    if (!selected.name.toLowerCase().endsWith(".pdf")) {
      alert("Only PDF files are supported.");
      return;
    }
    setFile(selected);
    setUploadResult(null);
    // Auto-fill source name from filename if empty
    if (!sourceName) {
      setSourceName(selected.name.replace(/\.pdf$/i, "").replace(/[-_]/g, " "));
    }
  }

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    handleFileSelect(e.dataTransfer.files[0] ?? null);
  }, [sourceName]);

  // ── Upload ──────────────────────────────────────────────────────────────

  async function handleUpload() {
    if (!file || !sourceName.trim() || !docType.trim()) return;
    setUploading(true);
    setUploadResult(null);

    try {
      const result = await ingestPDF(
        file,
        sourceName.trim(),
        category,
        docType.trim(),
      );
      setUploadResult({
        success: true,
        message: result.message,
        chunks:  result.chunk_count,
      });
      // Reset form for next upload
      setFile(null);
      setSourceName("");
      setDocType("");
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (err) {
      setUploadResult({
        success: false,
        message: (err as Error).message,
      });
    } finally {
      setUploading(false);
    }
  }

  // ── Library ─────────────────────────────────────────────────────────────

  async function loadLibrary() {
    setLoadingDocs(true);
    try {
      const data = await listDocuments();
      setDocs(data.documents);
    } catch {
      setDocs([]);
    } finally {
      setLoadingDocs(false);
    }
  }

  async function handleDelete(docUuid: string) {
    if (!confirm("Delete this document from the knowledge base?")) return;
    setDeletingId(docUuid);
    try {
      await deleteDocument(docUuid);
      setDocs(prev => prev.filter(d => d.doc_uuid !== docUuid));
    } catch (err) {
      alert((err as Error).message);
    } finally {
      setDeletingId(null);
    }
  }

  function switchView(v: PanelView) {
    setView(v);
    if (v === "library") loadLibrary();
  }

  const formValid = !!file && sourceName.trim().length > 0 && docType.trim().length > 0;

  // ── Render ──────────────────────────────────────────────────────────────

  return (
    // Backdrop
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-white rounded-2xl border border-gray-200 w-full max-w-lg mx-4 overflow-hidden flex flex-col max-h-[90vh]">

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <div className="flex gap-1 bg-gray-100 rounded-lg p-1">
            {(["upload", "library"] as PanelView[]).map(v => (
              <button
                key={v}
                onClick={() => switchView(v)}
                className={`px-4 py-1.5 text-sm font-medium rounded-md transition-colors capitalize ${
                  view === v
                    ? "bg-white text-gray-900 border border-gray-200"
                    : "text-gray-500 hover:text-gray-700"
                }`}
              >
                {v === "upload" ? "Upload PDF" : "Knowledge base"}
              </button>
            ))}
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-lg leading-none"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5">

          {/* ── Upload panel ── */}
          {view === "upload" && (
            <div className="flex flex-col gap-4">

              {/* Drop zone */}
              <div
                onDragOver={e => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={onDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors ${
                  dragOver
                    ? "border-blue-400 bg-blue-50"
                    : file
                    ? "border-green-300 bg-green-50"
                    : "border-gray-200 hover:border-gray-300 bg-gray-50"
                }`}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf"
                  className="hidden"
                  onChange={e => handleFileSelect(e.target.files?.[0] ?? null)}
                />
                {file ? (
                  <div className="flex flex-col items-center gap-1">
                    <span className="text-2xl">📄</span>
                    <p className="text-sm font-medium text-green-700">{file.name}</p>
                    <p className="text-xs text-gray-400">
                      {(file.size / 1024).toFixed(1)} KB — click to change
                    </p>
                  </div>
                ) : (
                  <div className="flex flex-col items-center gap-1">
                    <span className="text-2xl text-gray-300">⬆</span>
                    <p className="text-sm text-gray-500">
                      Drop a PDF here or <span className="text-blue-600">click to browse</span>
                    </p>
                    <p className="text-xs text-gray-400">PDF files only</p>
                  </div>
                )}
              </div>

              {/* Metadata form */}
              <div className="flex flex-col gap-3">
                <div>
                  <label className="text-xs text-gray-500 block mb-1">
                    Source name <span className="text-red-400">*</span>
                  </label>
                  <input
                    type="text"
                    value={sourceName}
                    onChange={e => setSourceName(e.target.value)}
                    placeholder="e.g. SEBI Circular 2025-001"
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                <div className="flex gap-3">
                  <div className="flex-1">
                    <label className="text-xs text-gray-500 block mb-1">Category</label>
                    <select
                      value={category}
                      onChange={e => setCategory(e.target.value as Category)}
                      className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                    >
                      {CATEGORIES.map(c => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
                  </div>

                  <div className="flex-1">
                    <label className="text-xs text-gray-500 block mb-1">
                      Document type <span className="text-red-400">*</span>
                    </label>
                    <input
                      type="text"
                      value={docType}
                      onChange={e => setDocType(e.target.value)}
                      placeholder="e.g. Investment Eligibility"
                      className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                  </div>
                </div>
              </div>

              {/* Result banner */}
              {uploadResult && (
                <div
                  className={`rounded-lg px-4 py-3 text-sm border ${
                    uploadResult.success
                      ? "bg-green-50 border-green-200 text-green-800"
                      : "bg-red-50  border-red-200  text-red-800"
                  }`}
                >
                  {uploadResult.success ? (
                    <>
                      <span className="font-medium">Ingested successfully.</span>{" "}
                      {uploadResult.chunks} chunks added to the knowledge base.
                      The agent can answer questions about this document immediately.
                    </>
                  ) : (
                    <>
                      <span className="font-medium">Upload failed:</span>{" "}
                      {uploadResult.message}
                    </>
                  )}
                </div>
              )}

              {/* Upload button */}
              <button
                onClick={handleUpload}
                disabled={!formValid || uploading}
                className="w-full py-2.5 bg-blue-600 text-white text-sm font-medium rounded-xl hover:bg-blue-700 disabled:opacity-40 transition-colors"
              >
                {uploading ? "Processing…" : "Upload & ingest"}
              </button>

              <p className="text-xs text-gray-400 text-center">
                The document is chunked, embedded, and stored in ChromaDB.
                The agent can reference it in answers immediately.
              </p>
            </div>
          )}

          {/* ── Library panel ── */}
          {view === "library" && (
            <div className="flex flex-col gap-3">
              {loadingDocs ? (
                <div className="text-center py-8 text-sm text-gray-400">
                  Loading knowledge base…
                </div>
              ) : docs.length === 0 ? (
                <div className="text-center py-8 text-sm text-gray-400">
                  No documents in the knowledge base yet.
                  <br />
                  <button
                    onClick={() => switchView("upload")}
                    className="mt-2 text-blue-600 hover:underline"
                  >
                    Upload your first PDF
                  </button>
                </div>
              ) : (
                <>
                  <p className="text-xs text-gray-400">
                    {docs.length} document{docs.length !== 1 ? "s" : ""} in knowledge base
                  </p>
                  {docs.map((doc, i) => (
                    <div
                      key={doc.doc_uuid ?? i}
                      className="border border-gray-100 rounded-xl p-3 flex items-start justify-between gap-3"
                    >
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-800 truncate">
                          {doc.source_name}
                        </p>
                        <p className="text-xs text-gray-400 mt-0.5 truncate">
                          {doc.file_name}
                        </p>
                        <div className="flex gap-2 mt-1.5 flex-wrap">
                          <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
                            {doc.category}
                          </span>
                          {doc.document_type && (
                            <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
                              {doc.document_type}
                            </span>
                          )}
                          <span className="text-xs text-gray-400">
                            {doc.chunk_count} chunks
                          </span>
                        </div>
                      </div>
                      {doc.doc_uuid && (
                        <button
                          onClick={() => handleDelete(doc.doc_uuid!)}
                          disabled={deletingId === doc.doc_uuid}
                          className="text-xs text-red-400 hover:text-red-600 disabled:opacity-40 shrink-0 pt-0.5"
                        >
                          {deletingId === doc.doc_uuid ? "…" : "Delete"}
                        </button>
                      )}
                    </div>
                  ))}
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}