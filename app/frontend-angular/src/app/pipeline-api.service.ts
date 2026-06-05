import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable, throwError } from 'rxjs';
import { catchError, map } from 'rxjs/operators';
import { IndexingRequest, IndexingResult, QueryRequest, QueryResult } from './models';

@Injectable({ providedIn: 'root' })
export class PipelineApiService {
  private readonly baseUrl = '/api/documents';

  constructor(private readonly http: HttpClient) {}

  // Step 1: Run OCR and return extracted text for Human-in-the-Loop
  runOCR(file: File, documentId: string, request: IndexingRequest): Observable<any> {
    console.log('[PipelineAPI] runOCR called');
    console.log('[PipelineAPI] OCR Options:', {
      useDocOrientationClassify: request.ocrConfig?.useDocOrientationClassify,
      useDocUnwarping: request.ocrConfig?.useDocUnwarping,
      useLayoutDetection: request.ocrConfig?.useLayoutDetection,
      formatBlockContent: request.ocrConfig?.formatBlockContent,
      mergeTables: request.ocrConfig?.mergeTables
    });

    const formData = new FormData();
    formData.append('file', file, file.name);
    
    // Create a JSON Blob and append it as the request part
    const requestBlob = new Blob([JSON.stringify(request)], { type: 'application/json' });
    formData.append('request', requestBlob, 'request.json');
    
    console.log('[PipelineAPI] POST /api/documents/index with file and request parts');

    return this.http.post<any>(`${this.baseUrl}/index`, formData).pipe(
      catchError((error) => {
        console.error('[PipelineAPI] runOCR error:', error);
        return throwError(() => error);
      })
    );
  }

  // Step 2: Confirm OCR results and continue with chunking + indexing
  confirmAndIndex(sessionId: string, correctedText: string, request: IndexingRequest): Observable<IndexingResult> {
    console.log('[API] confirmAndIndex called with sessionId:', sessionId);
    console.log('[API] Corrected text length:', correctedText?.length);
    
    // Use JSON body instead of URL params to handle large text properly
    const body = {
      session_id: sessionId,
      corrected_text: correctedText,
      max_tokens: request.chunkConfig?.maxTokens ?? 500,
      overlap_ratio: request.chunkConfig?.overlapRatio ?? 0.2
    };

    console.log('[API] POST /api/documents/confirm with body:', { sessionId, textLength: correctedText.length });
    
    return this.http.post<IndexingResult>(`${this.baseUrl}/confirm`, body).pipe(
      catchError((error) => {
        console.error('[API] confirmAndIndex error:', error);
        return throwError(() => error);
      })
    );
  }

  queryDocuments(request: QueryRequest): Observable<QueryResult> {
    return this.http.post<any>(`${this.baseUrl}/query`, request).pipe(
      map(res => {
        if (res.results && !res.documents) {
          res.documents = res.results.map((r: any) => ({
            documentId: r.document_id || r.documentId || 'Unknown',
            chunkId: r.chunk_id || r.chunkId || 'Unknown',
            content: r.text || r.content || '',
            highlightedText: r.text || r.highlightedText || '',
            score: r.score || 0,
            pageNumber: r.page || 1
          }));
        }
        return res as QueryResult;
      })
    );
  }

  // Fetch chunk details including bounding box for highlighting
  getChunkDetails(chunkId: string): Observable<any> {
    return this.http.get<any>(`${this.baseUrl}/chunk/${chunkId}`).pipe(
      catchError((error) => {
        console.error('[PipelineAPI] getChunkDetails error:', error);
        return throwError(() => error);
      })
    );
  }
}
