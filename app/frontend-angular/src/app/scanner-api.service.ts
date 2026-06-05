import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { map, Observable } from 'rxjs';
import {
  AgentDiagnosticsResponse,
  AgentHealthResponse,
  EsclManagedDevice,
  EsclProvisionRequest,
  OutputFormat,
  ScanRequest,
  ScanResult,
  ScannerCapabilities,
  ScannerDescriptor
} from './models';

@Injectable({ providedIn: 'root' })
export class ScannerApiService {
  private readonly baseUrl = 'http://127.0.0.1:7777/api';

  constructor(private readonly http: HttpClient) {}

  getHealth(): Observable<AgentHealthResponse> {
    return this.http.get<AgentHealthResponse>(`${this.baseUrl}/health`);
  }

  getProviderDiagnostics(): Observable<AgentDiagnosticsResponse> {
    return this.http.get<AgentDiagnosticsResponse>(`${this.baseUrl}/diagnostics/providers`);
  }

  listScanners(refresh = false): Observable<ScannerDescriptor[]> {
    const params = refresh ? new HttpParams().set('refresh', 'true') : undefined;
    return this.http.get<ScannerDescriptor[]>(`${this.baseUrl}/scanners`, { params });
  }

  getScannerCapabilities(scannerId: string): Observable<ScannerCapabilities> {
    return this.http.get<ScannerCapabilities>(
      `${this.baseUrl}/scanner-capabilities/${encodeURIComponent(scannerId)}`
    );
  }

  discoverEsclScanners(
    baseUrls: string[],
    username?: string,
    password?: string
  ): Observable<EsclManagedDevice[]> {
    return this.http.post<EsclManagedDevice[]>(`${this.baseUrl}/escl/discover`, {
      baseUrls,
      username: username || undefined,
      password: password || undefined
    });
  }

  listProvisionedEsclScanners(): Observable<EsclManagedDevice[]> {
    return this.http.get<EsclManagedDevice[]>(`${this.baseUrl}/escl/provisioned`);
  }

  provisionEsclScanner(request: EsclProvisionRequest): Observable<EsclManagedDevice> {
    return this.http.post<EsclManagedDevice>(`${this.baseUrl}/escl/provision`, request);
  }

  removeProvisionedEsclScanner(deviceId: string): Observable<void> {
    return this.http.delete<void>(`${this.baseUrl}/escl/provision/${encodeURIComponent(deviceId)}`);
  }

  scan(request: ScanRequest): Observable<ScanResult> {
    return this.http
      .post(`${this.baseUrl}/scan`, request, {
        observe: 'response',
        responseType: 'blob'
      })
      .pipe(
        map((response) => {
          const contentType =
            response.headers.get('Content-Type') ||
            response.body?.type ||
            this.defaultContentType(request.settings.outputFormat);
          const fileName =
            this.extractFileName(response.headers) ||
            this.buildDefaultFileName(request.settings.outputFormat);

          return {
            fileName,
            contentType,
            blob: new Blob([response.body ?? new Blob()], { type: contentType }),
            scannerId: request.scannerId,
            provider: response.headers.get('X-Scan-Provider') ?? undefined,
            elapsedMs: this.parseElapsedMilliseconds(response.headers.get('X-Scan-Elapsed-Ms'))
          };
        })
      );
  }

  private extractFileName(headers: HttpHeaders): string | null {
    const customHeader = headers.get('X-Scan-File-Name');
    if (customHeader) {
      return customHeader;
    }

    const contentDisposition = headers.get('Content-Disposition');
    if (!contentDisposition) {
      return null;
    }

    const utf8Match = /filename\*=UTF-8''([^;]+)/i.exec(contentDisposition);
    if (utf8Match?.[1]) {
      return decodeURIComponent(utf8Match[1]);
    }

    const plainMatch = /filename="?([^"]+)"?/i.exec(contentDisposition);
    return plainMatch?.[1] ?? null;
  }

  private buildDefaultFileName(outputFormat: OutputFormat): string {
    const extension = outputFormat === 'JPG' ? 'jpg' : outputFormat.toLowerCase();
    return `scan.${extension}`;
  }

  private defaultContentType(outputFormat: OutputFormat): string {
    switch (outputFormat) {
      case 'PNG':
        return 'image/png';
      case 'JPG':
        return 'image/jpeg';
      case 'PDF':
        return 'application/pdf';
    }
  }

  private parseElapsedMilliseconds(rawValue: string | null): number | undefined {
    if (!rawValue) {
      return undefined;
    }

    const parsedValue = Number(rawValue);
    return Number.isFinite(parsedValue) && parsedValue >= 0 ? parsedValue : undefined;
  }
}
