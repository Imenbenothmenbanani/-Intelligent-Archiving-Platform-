import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import {
  BackendHealthResponse,
  ScanResult,
  StoredDocumentSummary,
  UploadResponse
} from './models';

@Injectable({ providedIn: 'root' })
export class DocumentApiService {
  private readonly baseUrl = '/api/documents';

  constructor(private readonly http: HttpClient) {}

  getHealth(): Observable<BackendHealthResponse> {
    return this.http.get<BackendHealthResponse>(`${this.baseUrl}/health`);
  }

  listRecentDocuments(limit = 8): Observable<StoredDocumentSummary[]> {
    return this.http.get<StoredDocumentSummary[]>(`${this.baseUrl}/recent?limit=${limit}`);
  }

  uploadScannedFile(scanResult: ScanResult): Observable<UploadResponse> {
    const formData = new FormData();
    const file = new File([scanResult.blob], scanResult.fileName, {
      type: scanResult.contentType
    });

    formData.append('file', file, scanResult.fileName);
    formData.append('originalFileName', scanResult.fileName);
    formData.append('contentType', scanResult.contentType);
    formData.append('scannerId', scanResult.scannerId);

    if (scanResult.provider) {
      formData.append('provider', scanResult.provider);
    }

    return this.http.post<UploadResponse>(`${this.baseUrl}/upload`, formData);
  }
}
