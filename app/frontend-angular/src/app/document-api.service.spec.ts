import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { DocumentApiService } from './document-api.service';
import { ScanResult } from './models';

describe('DocumentApiService', () => {
  let service: DocumentApiService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()]
    });

    service = TestBed.inject(DocumentApiService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('reads backend health through the Spring Boot API', () => {
    let actualStatus = '';

    service.getHealth().subscribe((response) => {
      actualStatus = response.status;
    });

    const request = httpMock.expectOne('/api/documents/health');
    expect(request.request.method).toBe('GET');
    request.flush({
      status: 'UP',
      writable: true,
      recentDocumentCount: 3
    });

    expect(actualStatus).toBe('UP');
  });

  it('lists recent scanned documents from the backend', () => {
    let actualFileName = '';

    service.listRecentDocuments(5).subscribe((response) => {
      actualFileName = response[0]?.storedFileName ?? '';
    });

    const request = httpMock.expectOne('/api/documents/recent?limit=5');
    expect(request.request.method).toBe('GET');
    request.flush([
      {
        storedFileName: 'scan-002.pdf',
        contentType: 'application/pdf',
        fileSize: 24567,
        storedAt: '2026-04-02T10:15:30Z'
      }
    ]);

    expect(actualFileName).toBe('scan-002.pdf');
  });

  it('uploads scanned files to the Spring Boot backend', () => {
    const scanResult: ScanResult = {
      fileName: 'scan-001.pdf',
      contentType: 'application/pdf',
      blob: new Blob(['pdf-bytes'], { type: 'application/pdf' }),
      scannerId: 'mock:1',
      provider: 'MOCK'
    };

    let responseBody: string | undefined;

    service.uploadScannedFile(scanResult).subscribe((response) => {
      responseBody = response.storedFileName;
    });

    const request = httpMock.expectOne('/api/documents/upload');
    expect(request.request.method).toBe('POST');
    expect(request.request.body instanceof FormData).toBeTrue();

    const payload = request.request.body as FormData;
    expect(payload.get('originalFileName')).toBe('scan-001.pdf');
    expect(payload.get('contentType')).toBe('application/pdf');
    expect(payload.get('scannerId')).toBe('mock:1');
    expect(payload.get('provider')).toBe('MOCK');

    request.flush({
      success: true,
      storedFileName: 'scan-001.pdf',
      contentType: 'application/pdf',
      fileSize: 12345,
      storedAt: '2026-04-02T10:15:30Z',
      scannerId: 'mock:1',
      provider: 'MOCK'
    });

    expect(responseBody).toBe('scan-001.pdf');
  });
});
