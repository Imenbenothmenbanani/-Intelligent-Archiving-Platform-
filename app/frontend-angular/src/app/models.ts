export type ColorMode = 'COLOR' | 'GRAYSCALE' | 'BLACK_WHITE';
export type ScanSource = 'FLATBED' | 'ADF';
export type OutputFormat = 'PNG' | 'JPG' | 'PDF';
export type SupportedDpi = number;

export interface ScannerDescriptor {
  id: string;
  name: string;
  provider: string;
  available: boolean;
}

export interface ScanSettings {
  dpi: number;
  colorMode: ColorMode;
  source: ScanSource;
  duplex?: boolean;
  outputFormat: OutputFormat;
  enableAutoCrop?: boolean;
  enableDeskew?: boolean;
  enableContrastCleanup?: boolean;
  enableAutoRotate?: boolean;
  skipBlankPages?: boolean;
}

export interface ScanRequest {
  scannerId: string;
  settings: ScanSettings;
}

export interface ScanResult {
  fileName: string;
  contentType: string;
  blob: Blob;
  scannerId: string;
  provider?: string;
  elapsedMs?: number;
}

export interface UploadResponse {
  success: boolean;
  storedFileName: string;
  contentType: string;
  fileSize: number;
  storedAt: string;
  scannerId?: string;
  provider?: string;
}

export interface AgentHealthResponse {
  status: string;
  machineName: string;
  allowMockProvider: boolean;
  runtimeVersion: string;
}

export interface ProviderDiagnostic {
  provider: string;
  status: 'HEALTHY' | 'DEGRADED' | 'UNAVAILABLE' | 'DISABLED';
  summary: string;
  discoveredScannerCount: number;
  details: Record<string, string>;
  lastSuccessAtUtc?: string | null;
  lastFailureAtUtc?: string | null;
  averageScanDurationMilliseconds?: number | null;
  failureBackoffExpiresAtUtc?: string | null;
}

export interface AgentDiagnosticsResponse {
  timestamp: string;
  cachedScannerCount: number;
  scannerListCacheExpiresAtUtc?: string | null;
  providers: ProviderDiagnostic[];
}

export interface BackendHealthResponse {
  status: string;
  writable: boolean;
  recentDocumentCount: number;
}

export interface StoredDocumentSummary {
  storedFileName: string;
  contentType: string;
  fileSize: number;
  storedAt: string;
}

export interface EsclDiscoveryRequest {
  baseUrls: string[];
  username?: string;
  password?: string;
}

export interface EsclProvisionRequest {
  baseUrl: string;
  name?: string;
  id?: string;
  username?: string;
  password?: string;
  enabled?: boolean;
}

export interface EsclManagedDevice {
  id: string;
  name: string;
  baseUrl: string;
  enabled: boolean;
  reachable: boolean;
  supportsAdf: boolean;
  supportsDuplex: boolean;
  suggestedDpiValues: number[];
  provisioned: boolean;
}

export interface ScannerValueRange {
  min: number;
  max: number;
  step: number;
}

export interface ScannerCapabilities {
  scannerId: string;
  provider: string;
  capabilitiesVerified: boolean;
  supportedSources: ScanSource[];
  supportedColorModes: ColorMode[];
  supportedOutputFormats: OutputFormat[];
  supportsDuplex: boolean;
  supportsUiFallback: boolean;
  suggestedDpiValues: number[];
  dpiRange: ScannerValueRange | null;
  supportedPageSizes: string[];
  maxPagesPerBatch: number | null;
  notes: string[];
  supportsHardwareCancellation?: boolean;
}

export const DEFAULT_SCAN_SETTINGS: ScanSettings = {
  dpi: 300,
  colorMode: 'COLOR',
  source: 'FLATBED',
  duplex: false,
  outputFormat: 'PNG',
  enableAutoRotate: true,
  skipBlankPages: false
};

// OCR Configuration
export interface OCRConfig {
  useDocOrientationClassify: boolean;
  useDocUnwarping: boolean;
  useLayoutDetection: boolean;
  useOcrForImageBlock: boolean;
  formatBlockContent: boolean;
  mergeTables: boolean;
}

// Chunk Configuration
export interface ChunkConfig {
  maxTokens: number;
  minTokens: number;
  overlapRatio: number;
}

// Embedding Configuration
export interface EmbeddingConfig {
  topK: number;
  rerankTopN: number;
}

// Indexing Request and Response
export interface IndexingRequest {
  documentId?: string;
  documentPath?: string;
  ocrConfig?: OCRConfig;
  chunkConfig?: ChunkConfig;
}

export interface IndexingResult {
  success: boolean;
  message: string;
  embeddedCount: number;
  chunksCreated?: number;
  chunksIndexed?: number;
  sessionId?: string;
  session_id?: string;      // snake_case from backend
  documentId?: string;
  document_id?: string;     // snake_case from backend
  extractedText?: string;
  extracted_text?: string;  // snake_case from backend
  humanInLoop?: boolean;
  storage?: {
    document_bucket?: string;
    chunks_bucket?: string;
  };
}

// Query Request and Response
export interface QueryRequest {
  queryText: string;
  topK: number;
  rerankTopN: number;
}

export interface QueryResult {
  success: boolean;
  message: string;
  totalHits: number;
  returnedCount: number;
  documents: DocumentDetails[];
}

export interface DocumentDetails {
  documentId: string;
  chunkId: string;
  content: string;
  highlightedText: string;
  pageNumber: number;
  score: number;
  imageUrl?: string;
}
