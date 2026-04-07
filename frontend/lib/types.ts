export interface ToolCall {
  tool:  string;
  input: Record<string, unknown>;
}

export interface SourceDoc {
  source:    string;
  category:  string;
  docType:   string;
  relevance: number;
  snippet:   string;
}

export interface Message {
  id:              string;
  role:            "human" | "ai";
  content:         string;
  toolCalls?:      ToolCall[];
  sources?:        SourceDoc[];
  isStreaming?:    boolean;
  activeTools?:    string[];   // tools currently running
}

export interface Session {
  id:    string;
  label: string;
}

 //"gemini-2.5-flash" | "gemini-2.5-pro";
export type ModelType = "gemini-2.5-flash";