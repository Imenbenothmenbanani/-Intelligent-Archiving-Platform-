import { HttpErrorResponse } from '@angular/common/http';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { MessageService } from 'primeng/api';
import { providePrimeNG } from 'primeng/config';
import { of, Subject, throwError } from 'rxjs';
import { DocumentApiService } from '../document-api.service';
import { EsclManagedDevice, ScannerCapabilities } from '../models';
import { ScannerApiService } from '../scanner-api.service';
import { ScannerTheme } from '../scanner-theme';
import { ScannerPageComponent } from './scanner-page.component';

describe('ScannerPageComponent', () => {
  let component: ScannerPageComponent;
  let fixture: ComponentFixture<ScannerPageComponent>;
  let scannerApiService: jasmine.SpyObj<ScannerApiService>;
  let documentApiService: jasmine.SpyObj<DocumentApiService>;

  const capabilities: ScannerCapabilities = {
    scannerId: 'mock:1',
    provider: 'MOCK',
    capabilitiesVerified: true,
    supportedSources: ['FLATBED', 'ADF'],
    supportedColorModes: ['COLOR', 'GRAYSCALE', 'BLACK_WHITE'],
    supportedOutputFormats: ['PNG', 'JPG', 'PDF'],
    supportsDuplex: true,
    supportsUiFallback: false,
    suggestedDpiValues: [150, 300, 600],
    dpiRange: { min: 75, max: 600, step: 25 },
    supportedPageSizes: ['A4'],
    maxPagesPerBatch: null,
    notes: ['Mock capabilities']
  };

  beforeEach(async () => {
    localStorage.clear();

    scannerApiService = jasmine.createSpyObj<ScannerApiService>('ScannerApiService', [
      'getHealth',
      'getProviderDiagnostics',
      'listScanners',
      'getScannerCapabilities',
      'scan',
      'discoverEsclScanners',
      'listProvisionedEsclScanners',
      'provisionEsclScanner',
      'removeProvisionedEsclScanner'
    ]);
    documentApiService = jasmine.createSpyObj<DocumentApiService>('DocumentApiService', [
      'uploadScannedFile',
      'getHealth',
      'listRecentDocuments'
    ]);

    scannerApiService.getHealth.and.returnValue(of({
      status: 'UP',
      machineName: 'WORKSTATION-01',
      allowMockProvider: false,
      runtimeVersion: '8.0.25'
    }));
    scannerApiService.getProviderDiagnostics.and.returnValue(of({
      timestamp: '2026-04-02T10:00:00Z',
      cachedScannerCount: 0,
      scannerListCacheExpiresAtUtc: null,
      providers: []
    }));
    scannerApiService.listScanners.and.returnValue(of([]));
    scannerApiService.getScannerCapabilities.and.returnValue(of(capabilities));
    scannerApiService.listProvisionedEsclScanners.and.returnValue(of([]));
    documentApiService.getHealth.and.returnValue(of({
      status: 'UP',
      writable: true,
      recentDocumentCount: 0
    }));
    documentApiService.listRecentDocuments.and.returnValue(of([]));

    spyOn(URL, 'createObjectURL').and.returnValue('blob:preview');
    spyOn(URL, 'revokeObjectURL');

    await TestBed.configureTestingModule({
      imports: [ScannerPageComponent],
      providers: [
        provideNoopAnimations(),
        providePrimeNG({
          ripple: true,
          inputStyle: 'filled',
          theme: {
            preset: ScannerTheme,
            options: {
              darkModeSelector: false
            }
          }
        }),
        MessageService,
        { provide: ScannerApiService, useValue: scannerApiService },
        { provide: DocumentApiService, useValue: documentApiService }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(ScannerPageComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('keeps the initial workspace bootstrap lightweight', () => {
    expect(scannerApiService.listScanners).toHaveBeenCalledWith(false);
    expect(scannerApiService.getProviderDiagnostics).not.toHaveBeenCalled();
    expect(scannerApiService.getHealth).not.toHaveBeenCalled();
    expect(documentApiService.getHealth).not.toHaveBeenCalled();
    expect(documentApiService.listRecentDocuments).not.toHaveBeenCalled();
    expect(scannerApiService.listProvisionedEsclScanners).not.toHaveBeenCalled();
  });

  it('keeps the network admin collapsed and loads provisioned scanners only when opened', () => {
    expect(component.networkAdminExpanded).toBeFalse();
    expect(scannerApiService.listProvisionedEsclScanners).not.toHaveBeenCalled();

    component.toggleNetworkAdmin();

    expect(component.networkAdminExpanded).toBeTrue();
    expect(scannerApiService.listProvisionedEsclScanners).toHaveBeenCalledTimes(1);

    component.toggleNetworkAdmin();
    component.toggleNetworkAdmin();

    expect(scannerApiService.listProvisionedEsclScanners).toHaveBeenCalledTimes(1);
  });

  it('loads scanners, selects the first available device, and loads its capabilities', () => {
    scannerApiService.listScanners.and.returnValue(
      of([{ id: 'mock:1', name: 'Mock Scanner', provider: 'MOCK', available: true }])
    );

    component.loadScanners();

    expect(scannerApiService.listScanners).toHaveBeenCalledWith(true);
    expect(component.scanners.length).toBe(1);
    expect(component.selectedScannerId).toBe('mock:1');
    expect(scannerApiService.getScannerCapabilities).toHaveBeenCalledWith('mock:1');
    expect(component.scannerCapabilities?.supportsDuplex).toBeTrue();
    expect(component.statusLevel).toBe('success');
  });

  it('marks provisioned eSCL scanners as network choices in the main list', () => {
    scannerApiService.listScanners.and.returnValue(
      of([{ id: 'escl:1', name: 'Reception AirScan', provider: 'ESCL', available: true }])
    );

    component.loadScanners();

    expect(component.scannerOptions[0]).toEqual(
      jasmine.objectContaining({
        label: 'Reception AirScan',
        value: 'escl:1',
        providerSummary: 'eSCL / AirScan',
        isNetwork: true
      })
    );
    expect(component.availableNetworkScannerCount).toBe(1);
  });

  it('stores the scan result and preview url after a successful final scan', () => {
    scannerApiService.scan.and.returnValue(
      of({
        fileName: 'scan-001.png',
        contentType: 'image/png',
        blob: new Blob(['mock'], { type: 'image/png' }),
        scannerId: 'mock:1',
        provider: 'MOCK'
      })
    );

    component.selectedScannerId = 'mock:1';
    component.scannerCapabilities = capabilities;
    component.selectedScanSource = 'ADF';
    component.enableDuplex = true;
    component.scanDocument();

    expect(scannerApiService.scan).toHaveBeenCalledWith(
      jasmine.objectContaining({
        scannerId: 'mock:1',
        settings: jasmine.objectContaining({
          dpi: 300,
          source: 'ADF',
          duplex: true,
          outputFormat: 'PNG',
          colorMode: 'COLOR',
          enableAutoRotate: true,
          skipBlankPages: false
        })
      })
    );
    expect(component.scanResult?.fileName).toBe('scan-001.png');
    expect(component.previewUrl).toBe('blob:preview');
    expect(component.statusLevel).toBe('success');
    expect(component.canSaveScannedFile).toBeTrue();
  });

  it('uploads the scanned file to the backend', () => {
    documentApiService.uploadScannedFile.and.returnValue(
      of({
        success: true,
        storedFileName: 'scan-001.png',
        contentType: 'image/png',
        fileSize: 1024,
        storedAt: '2026-04-02T10:15:30Z',
        scannerId: 'mock:1',
        provider: 'MOCK'
      })
    );

    component.scanResult = {
      fileName: 'scan-001.png',
      contentType: 'image/png',
      blob: new Blob(['mock'], { type: 'image/png' }),
      scannerId: 'mock:1',
      provider: 'MOCK'
    };
    component.lastCaptureMode = 'final';

    component.saveToServer();

    expect(documentApiService.uploadScannedFile).toHaveBeenCalled();
    expect(component.statusMessage).toContain('Enregistre avec succes');
  });

  it('runs preview scans with capability-aware preview settings and keeps save disabled', () => {
    scannerApiService.scan.and.returnValue(
      of({
        fileName: 'preview-001.jpg',
        contentType: 'image/jpeg',
        blob: new Blob(['preview'], { type: 'image/jpeg' }),
        scannerId: 'mock:1',
        provider: 'MOCK',
        elapsedMs: 320
      })
    );

    component.selectedScannerId = 'mock:1';
    component.scannerCapabilities = capabilities;
    component.previewDocument();

    expect(scannerApiService.scan).toHaveBeenCalledWith(
      jasmine.objectContaining({
        scannerId: 'mock:1',
        settings: jasmine.objectContaining({
          dpi: 150,
          colorMode: 'GRAYSCALE',
          outputFormat: 'JPG',
          duplex: false,
          enableAutoCrop: false,
          enableDeskew: false,
          enableContrastCleanup: false,
          enableAutoRotate: false,
          skipBlankPages: false
        })
      })
    );
    expect(component.lastCaptureMode).toBe('preview');
    expect(component.canSaveScannedFile).toBeFalse();
  });

  it('keeps high dpi values available when the agent exposes a range up to 2400 dpi', () => {
    component.scannerCapabilities = {
      ...capabilities,
      suggestedDpiValues: [],
      dpiRange: { min: 75, max: 2400, step: 75 }
    };

    expect(component.finalDpiOptions.map((option) => option.value)).toContain(2400);
  });

  it('keeps each scanner route visible and prefers the stored successful route', () => {
    localStorage.setItem(
      'scanner-feature.scanner-routes.v1',
      JSON.stringify({
        'twain:x86:1': {
          scannerId: 'twain:x86:1',
          provider: 'TWAIN',
          elapsedMs: 500,
          updatedAt: '2026-03-26T12:00:00.000Z'
        }
      })
    );

    scannerApiService.listScanners.and.returnValue(
      of([
        { id: 'wia:1', name: 'Office Scanner', provider: 'WIA', available: true },
        { id: 'twain:x86:1', name: 'Office Scanner TWAIN', provider: 'TWAIN', available: true },
        { id: 'escl:1', name: 'Reception AirScan', provider: 'ESCL', available: true }
      ])
    );

    component.loadScanners();

    expect(component.scannerOptions.length).toBe(3);
    expect(component.selectedScannerId).toBe('twain:x86:1');
    expect(scannerApiService.getScannerCapabilities).toHaveBeenCalledWith('twain:x86:1');
  });

  it('prefers the healthiest and fastest route from stored route stats', () => {
    localStorage.setItem(
      'scanner-feature.scanner-route-stats.v1',
      JSON.stringify({
        'wia:1': {
          scannerId: 'wia:1',
          provider: 'WIA',
          successCount: 1,
          failureCount: 3,
          averageElapsedMs: 12000,
          lastFailureAt: '2026-03-26T12:05:00.000Z'
        },
        'twain:x86:1': {
          scannerId: 'twain:x86:1',
          provider: 'TWAIN',
          successCount: 4,
          failureCount: 0,
          averageElapsedMs: 1800,
          lastSuccessAt: '2026-03-26T12:10:00.000Z'
        }
      })
    );

    scannerApiService.listScanners.and.returnValue(
      of([
        { id: 'wia:1', name: 'Office Scanner', provider: 'WIA', available: true },
        { id: 'twain:x86:1', name: 'Office Scanner TWAIN', provider: 'TWAIN', available: true }
      ])
    );

    component.loadScanners();

    expect(component.selectedScannerId).toBe('twain:x86:1');
    expect(scannerApiService.getScannerCapabilities).toHaveBeenCalledWith('twain:x86:1');
  });

  it('clears stale scanner choices when a refresh returns no scanners', () => {
    scannerApiService.listScanners.and.returnValues(
      of([{ id: 'mock:1', name: 'Mock Scanner', provider: 'MOCK', available: true }]),
      of([])
    );

    component.loadScanners();
    expect(component.selectedScannerId).toBe('mock:1');
    expect(component.scannerOptions.length).toBe(1);

    component.loadScanners();

    expect(component.scanners).toEqual([]);
    expect(component.scannerOptions).toEqual([]);
    expect(component.selectedScannerId).toBe('');
    expect(component.statusMessage).toContain('Aucun scanner detecte');
  });

  it('does not reroute a failed scan to another scanner automatically', async () => {
    scannerApiService.listScanners.and.returnValue(
      of([
        { id: 'wia:1', name: 'Office Scanner', provider: 'WIA', available: true },
        { id: 'twain:x86:1', name: 'Office Scanner TWAIN', provider: 'TWAIN', available: true }
      ])
    );
    scannerApiService.scan.and.returnValue(
      throwError(() =>
        new HttpErrorResponse({
          status: 500,
          error: { message: 'Driver initialization failed.' }
        })
      )
    );

    component.loadScanners();
    component.scanDocument();
    await fixture.whenStable();

    expect(scannerApiService.scan.calls.count()).toBe(1);
    expect(scannerApiService.scan.calls.argsFor(0)[0].scannerId).toBe('wia:1');
    expect(component.selectedScannerId).toBe('wia:1');
    expect(component.scanResult).toBeNull();
    expect(component.statusLevel).toBe('error');
  });

  it('does not retry another route when the agent is unreachable', async () => {
    scannerApiService.listScanners.and.returnValue(
      of([
        { id: 'wia:1', name: 'Office Scanner', provider: 'WIA', available: true },
        { id: 'twain:x86:1', name: 'Office Scanner TWAIN', provider: 'TWAIN', available: true }
      ])
    );
    scannerApiService.scan.and.returnValue(
      throwError(() => new HttpErrorResponse({ status: 0 }))
    );

    component.loadScanners();
    component.scanDocument();
    await fixture.whenStable();

    expect(scannerApiService.scan.calls.count()).toBe(1);
    expect(component.statusLevel).toBe('error');
    expect(component.statusMessage).toContain('La numerisation finale a echoue.');
  });

  it('cancels an in-flight scan and resets the busy state', () => {
    const scanSubject = new Subject<{
      fileName: string;
      contentType: string;
      blob: Blob;
      scannerId: string;
      provider: string;
    }>();
    scannerApiService.scan.and.returnValue(scanSubject.asObservable());

    component.selectedScannerId = 'mock:1';
    component.scannerCapabilities = capabilities;
    component.scanDocument();
    component.cancelScan();

    expect(component.scanning).toBeFalse();
    expect(component.activeScanMode).toBeNull();
    expect(component.statusMessage).toContain('Numerisation annulee');
  });

  it('discovers and provisions eSCL scanners from the admin section', () => {
    const discoveredDevice: EsclManagedDevice = {
      id: 'escl:lan-1',
      name: 'Scanner reseau',
      baseUrl: 'http://10.0.0.50/eSCL',
      enabled: true,
      reachable: true,
      supportsAdf: true,
      supportsDuplex: false,
      suggestedDpiValues: [150, 300],
      provisioned: false
    };
    const provisionedDevice: EsclManagedDevice = {
      ...discoveredDevice,
      provisioned: true
    };

    scannerApiService.discoverEsclScanners.and.returnValue(of([discoveredDevice]));
    scannerApiService.provisionEsclScanner.and.returnValue(of(provisionedDevice));
    scannerApiService.listScanners.and.returnValue(
      of([{ id: 'escl:lan-1', name: 'Scanner reseau', provider: 'ESCL', available: true }])
    );

    component.esclCandidateUrls = 'http://10.0.0.50/eSCL';
    component.esclUsername = 'scanner';
    component.esclPassword = 'secret';

    component.discoverEsclDevices();
    component.provisionEsclDevice(discoveredDevice);

    expect(scannerApiService.discoverEsclScanners).toHaveBeenCalledWith(
      ['http://10.0.0.50/eSCL'],
      'scanner',
      'secret'
    );
    expect(scannerApiService.provisionEsclScanner).toHaveBeenCalledWith({
      id: 'escl:lan-1',
      name: 'Scanner reseau',
      baseUrl: 'http://10.0.0.50/eSCL',
      username: 'scanner',
      password: 'secret',
      enabled: true
    });
    expect(component.esclProvisionedDevices).toEqual([provisionedDevice]);
    expect(component.esclDiscoveredDevices[0].provisioned).toBeTrue();
    expect(scannerApiService.listScanners).toHaveBeenCalledWith(true);
  });

  it('removes a provisioned eSCL scanner from the admin section', () => {
    const provisionedDevice: EsclManagedDevice = {
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

    scannerApiService.removeProvisionedEsclScanner.and.returnValue(of(void 0));
    scannerApiService.listScanners.and.returnValue(of([]));
    component.esclProvisionedDevices = [provisionedDevice];
    component.esclDiscoveredDevices = [provisionedDevice];

    component.removeProvisionedEsclDevice(provisionedDevice);

    expect(scannerApiService.removeProvisionedEsclScanner).toHaveBeenCalledWith('escl:lan-1');
    expect(component.esclProvisionedDevices).toEqual([]);
    expect(component.esclDiscoveredDevices[0].provisioned).toBeFalse();
  });
});
