import { HttpHeaders } from '@angular/common/http';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import {
  AgentDiagnosticsResponse,
  AgentHealthResponse,
  DEFAULT_SCAN_SETTINGS,
  EsclManagedDevice,
  ScanRequest,
  ScannerCapabilities
} from './models';
import { ScannerApiService } from './scanner-api.service';

describe('ScannerApiService', () => {
  let service: ScannerApiService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()]
    });

    service = TestBed.inject(ScannerApiService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('reads the local agent health endpoint', () => {
    const expected: AgentHealthResponse = {
      status: 'UP',
      machineName: 'WORKSTATION-01',
      allowMockProvider: false,
      runtimeVersion: '8.0.25'
    };

    let actual = expected;

    service.getHealth().subscribe((response) => {
      actual = response;
    });

    const request = httpMock.expectOne('http://127.0.0.1:7777/api/health');
    expect(request.request.method).toBe('GET');
    request.flush(expected);

    expect(actual).toEqual(expected);
  });

  it('loads provider diagnostics from the local agent', () => {
    const expected: AgentDiagnosticsResponse = {
      timestamp: '2026-04-02T10:00:00Z',
      cachedScannerCount: 1,
      scannerListCacheExpiresAtUtc: null,
      providers: [
        {
          provider: 'WIA',
          status: 'HEALTHY',
          summary: 'WIA is ready.',
          discoveredScannerCount: 1,
          details: { windowsOnly: 'true' }
        }
      ]
    };

    let actual = expected;

    service.getProviderDiagnostics().subscribe((response) => {
      actual = response;
    });

    const request = httpMock.expectOne('http://127.0.0.1:7777/api/diagnostics/providers');
    expect(request.request.method).toBe('GET');
    request.flush(expected);

    expect(actual).toEqual(expected);
  });

  it('lists scanners from the localhost agent', () => {
    const expected = [{ id: 'mock:1', name: 'Mock Scanner', provider: 'MOCK', available: true }];
    let actual = expected;

    service.listScanners(true).subscribe((response) => {
      actual = response;
    });

    const request = httpMock.expectOne('http://127.0.0.1:7777/api/scanners?refresh=true');
    expect(request.request.method).toBe('GET');
    request.flush(expected);

    expect(actual).toEqual(expected);
  });

  it('loads scanner capabilities from the localhost agent', () => {
    const expected: ScannerCapabilities = {
      scannerId: 'wia:office',
      provider: 'WIA',
      capabilitiesVerified: true,
      supportedSources: ['FLATBED', 'ADF'],
      supportedColorModes: ['COLOR', 'GRAYSCALE'],
      supportedOutputFormats: ['PNG', 'PDF'],
      supportsDuplex: true,
      supportsUiFallback: false,
      suggestedDpiValues: [150, 300, 600],
      dpiRange: { min: 75, max: 600, step: 25 },
      supportedPageSizes: ['A4'],
      maxPagesPerBatch: null,
      notes: ['Test capabilities']
    };

    let actual = expected;

    service.getScannerCapabilities('wia:office').subscribe((response) => {
      actual = response;
    });

    const request = httpMock.expectOne(
      'http://127.0.0.1:7777/api/scanner-capabilities/wia%3Aoffice'
    );
    expect(request.request.method).toBe('GET');
    request.flush(expected);

    expect(actual).toEqual(expected);
  });

  it('maps binary scan responses into a scan result', () => {
    const requestBody: ScanRequest = {
      scannerId: 'mock:1',
      settings: { ...DEFAULT_SCAN_SETTINGS, outputFormat: 'PNG' }
    };

    let actualFileName = '';
    let actualContentType = '';
    let actualElapsedMs: number | undefined;

    service.scan(requestBody).subscribe((response) => {
      actualFileName = response.fileName;
      actualContentType = response.contentType;
      actualElapsedMs = response.elapsedMs;
    });

    const request = httpMock.expectOne('http://127.0.0.1:7777/api/scan');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual(requestBody);
    request.flush(new Blob(['binary-data'], { type: 'image/png' }), {
      headers: new HttpHeaders({
        'Content-Type': 'image/png',
        'X-Scan-File-Name': 'scan-001.png',
        'X-Scan-Provider': 'MOCK',
        'X-Scan-Elapsed-Ms': '842'
      })
    });

    expect(actualFileName).toBe('scan-001.png');
    expect(actualContentType).toBe('image/png');
    expect(actualElapsedMs).toBe(842);
  });

  it('discovers eSCL scanners from candidate base urls', () => {
    const expected: EsclManagedDevice[] = [
      {
        id: 'escl:lan-1',
        name: 'Scanner reseau',
        baseUrl: 'http://10.0.0.50/eSCL',
        enabled: true,
        reachable: true,
        supportsAdf: true,
        supportsDuplex: false,
        suggestedDpiValues: [150, 300],
        provisioned: false
      }
    ];

    let actual = expected;

    service
      .discoverEsclScanners(['http://10.0.0.50/eSCL'], 'scanner', 'secret')
      .subscribe((response) => {
        actual = response;
      });

    const request = httpMock.expectOne('http://127.0.0.1:7777/api/escl/discover');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({
      baseUrls: ['http://10.0.0.50/eSCL'],
      username: 'scanner',
      password: 'secret'
    });
    request.flush(expected);

    expect(actual).toEqual(expected);
  });

  it('lists and provisions eSCL scanners through the local agent', () => {
    const expected: EsclManagedDevice = {
      id: 'escl:lan-1',
      name: 'Scanner reseau',
      baseUrl: 'http://10.0.0.50/eSCL',
      enabled: true,
      reachable: true,
      supportsAdf: true,
      supportsDuplex: true,
      suggestedDpiValues: [150, 300, 600],
      provisioned: true
    };

    let actualProvisioned: EsclManagedDevice | undefined;
    let actualList: EsclManagedDevice[] = [];

    service.listProvisionedEsclScanners().subscribe((response) => {
      actualList = response;
    });

    const listRequest = httpMock.expectOne('http://127.0.0.1:7777/api/escl/provisioned');
    expect(listRequest.request.method).toBe('GET');
    listRequest.flush([expected]);

    service.provisionEsclScanner({
      id: expected.id,
      name: expected.name,
      baseUrl: expected.baseUrl,
      enabled: true
    }).subscribe((response) => {
      actualProvisioned = response;
    });

    const provisionRequest = httpMock.expectOne('http://127.0.0.1:7777/api/escl/provision');
    expect(provisionRequest.request.method).toBe('POST');
    provisionRequest.flush(expected);

    expect(actualList).toEqual([expected]);
    expect(actualProvisioned).toEqual(expected);
  });

  it('removes a provisioned eSCL scanner from the local agent', () => {
    let completed = false;

    service.removeProvisionedEsclScanner('escl:lan-1').subscribe(() => {
      completed = true;
    });

    const request = httpMock.expectOne('http://127.0.0.1:7777/api/escl/provision/escl%3Alan-1');
    expect(request.request.method).toBe('DELETE');
    request.flush(null);

    expect(completed).toBeTrue();
  });
});
