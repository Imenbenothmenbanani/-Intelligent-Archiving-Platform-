import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { MessageService } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { CardModule } from 'primeng/card';
import { CheckboxModule } from 'primeng/checkbox';
import { ProgressSpinnerModule } from 'primeng/progressspinner';
import { SelectModule } from 'primeng/select';
import { ToastModule } from 'primeng/toast';
import { catchError, finalize, Observable, Subscription, throwError } from 'rxjs';
import { DocumentApiService } from '../document-api.service';
import {
  ColorMode,
  DEFAULT_SCAN_SETTINGS,
  EsclManagedDevice,
  EsclProvisionRequest,
  OutputFormat,
  ScanSettings,
  ScanResult,
  ScanSource,
  ScannerCapabilities,
  ScannerDescriptor,
  UploadResponse
} from '../models';
import { ScannerApiService } from '../scanner-api.service';
import { PipelineApiService } from '../pipeline-api.service'; // Added import

type StatusLevel = 'success' | 'error' | 'info';
type CaptureMode = 'preview' | 'final';
type SelectOption<T> = {
  label: string;
  value: T;
  disabled?: boolean;
};
type ScannerChoice = SelectOption<string> & {
  displayName: string;
  providerSummary: string;
  isNetwork: boolean;
};
type StoredScannerRoute = {
  scannerId: string;
  provider: string;
  elapsedMs?: number;
  updatedAt: string;
};
type StoredScannerRouteStats = {
  scannerId: string;
  provider: string;
  successCount: number;
  failureCount: number;
  averageElapsedMs?: number;
  lastElapsedMs?: number;
  lastSuccessAt?: string;
  lastFailureAt?: string;
};

const LAST_SCANNER_STORAGE_KEY = 'scanner-feature.last-scanner-id.v1';
const SCANNER_ROUTE_STORAGE_KEY = 'scanner-feature.scanner-routes.v1';
const SCANNER_ROUTE_STATS_STORAGE_KEY = 'scanner-feature.scanner-route-stats.v1';

@Component({
  selector: 'app-scanner-page',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ButtonModule,
    CardModule,
    CheckboxModule,
    ProgressSpinnerModule,
    SelectModule,
    ToastModule
  ],
  templateUrl: './scanner-page.component.html',
  styleUrl: './scanner-page.component.css'
})
export class ScannerPageComponent implements OnDestroy, OnInit {
  scanners: ScannerDescriptor[] = [];
  scannerCapabilities: ScannerCapabilities | null = null;
  scannerChoices: ScannerChoice[] = [];
  selectedScannerId = '';
  selectedOutputFormat: OutputFormat = DEFAULT_SCAN_SETTINGS.outputFormat;
  selectedFinalDpi = DEFAULT_SCAN_SETTINGS.dpi;
  selectedColorMode: ColorMode = DEFAULT_SCAN_SETTINGS.colorMode;
  selectedScanSource: ScanSource = DEFAULT_SCAN_SETTINGS.source;
  enableDocumentCleanup = false;
  enableAutoRotate = DEFAULT_SCAN_SETTINGS.enableAutoRotate ?? true;
  skipBlankPages = DEFAULT_SCAN_SETTINGS.skipBlankPages ?? false;
  enableDuplex = DEFAULT_SCAN_SETTINGS.duplex ?? false;
  scanResult: ScanResult | null = null;
  lastUploadResponse: UploadResponse | null = null;
  previewUrl: string | null = null;
  fullResolutionUrl: string | null = null;
  statusMessage = "Chargez d'abord les scanners depuis l'agent local.";
  statusLevel: StatusLevel = 'info';
  esclCandidateUrls = '';
  esclUsername = '';
  esclPassword = '';
  esclDiscoveredDevices: EsclManagedDevice[] = [];
  esclProvisionedDevices: EsclManagedDevice[] = [];
  esclStatusMessage =
    'Ajoutez une ou plusieurs URL eSCL/AirScan pour provisionner des scanners reseau.';
  esclStatusLevel: StatusLevel = 'info';
  activeScanMode: CaptureMode | null = null;
  lastCaptureMode: CaptureMode | null = null;
  loadingScanners = false;
  loadingCapabilities = false;
  scanning = false;
  saving = false;
  loadingEsclProvisioned = false;
  discoveringEscl = false;
  provisioningEscl = false;
  networkAdminExpanded = false;
  removingEsclDeviceIds = new Set<string>();
  private scanSubscription?: Subscription;
  private previewGeneration = 0;
  private capabilitiesGeneration = 0;
  private networkAdminInitialized = false;
  indexingInProgress = false; // Added property for indexing status
  indexingResult: any = null; // Added property for indexing result
  indexingStep = 0; // 0=OCR, 1=Segmentation, 2=Embedding, 3=Indexation
  
  // Human-in-the-Loop properties
  showHumanInLoop = false;
  ocrExtractedText = '';
  correctedText = '';
  sessionId = '';

  // OCR Options (all false by default)
  ocrOptions = {
    useOrientation: false,
    useUnwarp: false,
    useLayout: false,
    useOcrForImageBlock: false,
    useFormat: false,
    mergeTables: false
  };

  constructor(
    private readonly scannerApiService: ScannerApiService,
    private readonly documentApiService: DocumentApiService,
    private readonly messageService: MessageService,
    private readonly pipelineApiService: PipelineApiService,
    private readonly router: Router
  ) {}

  ngOnInit(): void {
    this.bootstrapWorkspace();
  }

  ngOnDestroy(): void {
    this.scanSubscription?.unsubscribe();
    this.clearPreviewUrls();
  }

  get scannerOptions(): Array<SelectOption<string>> {
    return this.scannerChoices;
  }

  get sourceOptions(): Array<SelectOption<ScanSource>> {
    return this.resolveSupportedSources().map((source) => ({
      label: this.labelForSource(source),
      value: source
    }));
  }

  get colorModeOptions(): Array<SelectOption<ColorMode>> {
    return this.resolveSupportedColorModes().map((mode) => ({
      label: this.labelForColorMode(mode),
      value: mode
    }));
  }

  get outputFormatOptions(): Array<SelectOption<OutputFormat>> {
    return this.resolveSupportedOutputFormats().map((format) => ({
      label: this.labelForOutputFormat(format),
      value: format
    }));
  }

  get finalDpiOptions(): Array<SelectOption<number>> {
    return this.resolveSupportedDpiValues().map((dpi) => ({
      label: `${dpi} PPP`,
      value: dpi
    }));
  }

  get selectedScanner(): ScannerDescriptor | undefined {
    return this.scanners.find((scanner) => scanner.id === this.selectedScannerId);
  }

  get selectedScannerChoice(): ScannerChoice | undefined {
    return this.scannerChoices.find((choice) => choice.value === this.selectedScannerId);
  }

  get hasBusyState(): boolean {
    return this.loadingScanners || this.loadingCapabilities || this.scanning || this.saving;
  }

  get hasEsclBusyState(): boolean {
    return this.loadingEsclProvisioned || this.discoveringEscl || this.provisioningEscl;
  }

  get parsedEsclBaseUrls(): string[] {
    return this.parseEsclBaseUrls(this.esclCandidateUrls);
  }

  get canDiscoverEsclDevices(): boolean {
    return this.parsedEsclBaseUrls.length > 0 && !this.hasBusyState && !this.hasEsclBusyState;
  }

  get canProvisionTypedEsclDevice(): boolean {
    return this.parsedEsclBaseUrls.length === 1 && !this.hasBusyState && !this.hasEsclBusyState;
  }

  get availableNetworkScannerCount(): number {
    return this.scannerChoices.filter((choice) => choice.isNetwork && !choice.disabled).length;
  }

  get canCancelActiveScan(): boolean {
    if (!this.scanning) {
      return false;
    }

    if (this.scannerCapabilities?.supportsHardwareCancellation) {
      return true;
    }

    const activeProvider = this.selectedScanner?.provider?.toUpperCase();
    return activeProvider === 'TWAIN' || activeProvider === 'ESCL' || activeProvider === 'MOCK';
  }

  get activityLabel(): string {
    if (this.loadingScanners) {
      return "Inventaire des scanners depuis l'agent Windows local.";
    }

    if (this.loadingCapabilities) {
      return 'Lecture des capacites du scanner selectionne.';
    }

    if (this.scanning) {
      return this.activeScanMode === 'preview'
        ? `Capture en cours pour un apercu rapide a ${this.previewDpi} PPP.`
        : 'Capture en cours pour le fichier final.';
    }

    if (this.saving) {
      return "Envoi du fichier numerise vers l'API Spring Boot.";
    }

    return 'Pret pour la prochaine numerisation.';
  }

  get scanModeSummary(): string {
    return `${this.selectedFinalDpi} PPP / ${this.labelForColorMode(this.selectedColorMode)} / ${this.labelForSource(this.selectedScanSource)}`;
  }

  get previewDpi(): number {
    return this.resolveClosestDpi(150);
  }

  get previewColorMode(): ColorMode {
    const supportedModes = this.resolveSupportedColorModes();
    if (supportedModes.includes('GRAYSCALE')) {
      return 'GRAYSCALE';
    }

    if (supportedModes.includes('COLOR')) {
      return 'COLOR';
    }

    return supportedModes[0] ?? 'COLOR';
  }

  get previewOutputFormat(): OutputFormat {
    const supportedFormats = this.resolveSupportedOutputFormats();
    return (
      ['JPG', 'PNG', 'PDF'].find((format) =>
        supportedFormats.includes(format as OutputFormat)
      ) as OutputFormat | undefined
    ) ?? supportedFormats[0] ?? 'PNG';
  }

  get previewOutputLabel(): string {
    return this.labelForOutputFormat(this.previewOutputFormat);
  }

  get captureLabel(): string {
    return this.lastCaptureMode === 'preview'
      ? 'Apercu rapide'
      : this.lastCaptureMode === 'final'
        ? 'Capture finale'
        : "En attente d'une numerisation";
  }

  get captureModeDetailLabel(): string {
    return this.lastCaptureMode === 'preview' ? 'Apercu seulement' : 'Pret pour enregistrement';
  }

  get canSaveScannedFile(): boolean {
    return !!this.scanResult && this.lastCaptureMode === 'final';
  }

  get canToggleDuplex(): boolean {
    return !!this.scannerCapabilities?.supportsDuplex
      && this.selectedScanSource === 'ADF'
      && this.selectedScanner?.provider !== 'ESCL';
  }

  get capabilityNotes(): string[] {
    return this.scannerCapabilities?.notes ?? [];
  }

  get actionGuidance(): string {
    if (this.loadingScanners) {
      return "Actualisation de la liste en cours depuis l'agent local.";
    }

    if (this.loadingCapabilities) {
      return 'Le scanner selectionne est en cours d analyse pour ajuster automatiquement les options disponibles.';
    }

    if (!this.scanners.length) {
      return "Commencez par actualiser la liste des scanners.";
    }

    if (!this.selectedScannerId) {
      return "Selectionnez un scanner pour activer l'apercu rapide et la numerisation finale.";
    }

    if (this.scanning) {
      return this.activeScanMode === 'preview'
        ? "Apercu en cours. Verifiez ensuite le rendu avant de lancer la capture finale."
        : 'Numerisation finale en cours. Patientez avant de lancer une autre action.';
    }

    if (this.saving) {
      return "Enregistrement en cours sur le serveur. Evitez une nouvelle capture pendant ce transfert.";
    }

    if (!this.scanResult) {
      return "Les options sont filtrees selon le scanner choisi. Faites un apercu rapide puis lancez la numerisation finale.";
    }

    if (!this.canSaveScannedFile) {
      return "L'enregistrement reste indisponible tant qu'un scan final n'a pas ete produit.";
    }

    return "Le document final est pret. Vous pouvez maintenant l'enregistrer sur le serveur.";
  }

  get esclActionGuidance(): string {
    if (this.loadingEsclProvisioned) {
      return 'Lecture de la flotte eSCL provisionnee sur cet agent.';
    }

    if (this.discoveringEscl) {
      return 'Sondage des URL eSCL candidates sur le reseau local.';
    }

    if (this.provisioningEscl) {
      return 'Ajout du scanner reseau dans la configuration persistante de l agent.';
    }

    if (this.removingEsclDeviceIds.size > 0) {
      return 'Suppression du scanner reseau selectionne.';
    }

    if (!this.esclProvisionedDevices.length) {
      return 'Ajoutez un scanner reseau pour le faire apparaitre ensuite dans la liste principale.';
    }

    return 'Les scanners reseau ajoutes apparaissent ensuite dans la liste principale.';
  }

  get networkAdminSummary(): string {
    if (this.availableNetworkScannerCount > 0) {
      return `${this.availableNetworkScannerCount} scanner(s) reseau deja disponible(s) dans la liste principale.`;
    }

    return 'Ajoutez un scanner eSCL / AirScan seulement si vous devez numeriser via le reseau.';
  }

  get statusPanelLabel(): string {
    switch (this.statusLevel) {
      case 'success':
        return 'Pret';
      case 'error':
        return 'Attention';
      default:
        return 'Etat du scanner';
    }
  }

  get scanFileSizeLabel(): string {
    return this.scanResult ? this.formatFileSize(this.scanResult.blob.size) : '';
  }

  get scanTimingLabel(): string {
    if (!this.scanResult?.elapsedMs) {
      return '';
    }

    return this.scanResult.elapsedMs >= 1000
      ? `${(this.scanResult.elapsedMs / 1000).toFixed(1)} s`
      : `${Math.round(this.scanResult.elapsedMs)} ms`;
  }

  private bootstrapWorkspace(): void {
    this.loadScanners(false, false);
  }

  refreshWorkspace(notify = false): void {
    this.loadScanners(false, notify);
    if (this.networkAdminExpanded) {
      this.loadProvisionedEsclDevices(notify);
    }
  }

  toggleNetworkAdmin(): void {
    this.networkAdminExpanded = !this.networkAdminExpanded;

    if (this.networkAdminExpanded && !this.networkAdminInitialized) {
      this.loadProvisionedEsclDevices();
    }
  }

  loadScanners(refresh = true, notify = true): void {
    if (this.loadingScanners) {
      return;
    }

    const previousScannerId = this.selectedScannerId;

    this.loadingScanners = true;
    this.setStatus("Chargement des scanners depuis l'agent local...", 'info');

    this.scannerApiService
      .listScanners(refresh)
      .pipe(finalize(() => (this.loadingScanners = false)))
      .subscribe({
        next: (scanners) => {
          this.scanners = scanners;
          this.scannerChoices = this.buildScannerChoices(scanners);
          this.selectedScannerId =
            this.resolveInitialScannerSelection(previousScannerId);

          if (!scanners.length) {
            this.selectedScannerId = '';
            this.scannerChoices = [];
            this.clearScannerCapabilities();
            this.setStatus(
              'Aucun scanner detecte. Connectez un scanner WIA, TWAIN ou eSCL puis rechargez la liste.',
              'info'
            );
            return;
          }

          if (this.selectedScannerId) {
            this.loadScannerCapabilities(this.selectedScannerId);
          }

          this.setStatus(`${scanners.length} scanner(s) charge(s).`, 'success', notify);
        },
        error: (error) => {
          this.scanners = [];
          this.scannerChoices = [];
          this.selectedScannerId = '';
          this.clearScannerCapabilities();
          void this.handleErrorStatus(
            error,
            "L'agent scanner local n'est pas joignable sur http://127.0.0.1:7777."
          );
        }
      });
  }

  onScannerSelectionChange(scannerId: string): void {
    this.selectedScannerId = scannerId;
    this.storeLastScannerId(scannerId);
    this.lastUploadResponse = null;
    this.loadScannerCapabilities(scannerId);
  }

  onSourceSelectionChange(source: ScanSource): void {
    this.selectedScanSource = source;
    if (!this.canToggleDuplex) {
      this.enableDuplex = false;
    }
  }

  loadProvisionedEsclDevices(notify = false): void {
    if (this.loadingEsclProvisioned) {
      return;
    }

    this.loadingEsclProvisioned = true;
    this.setEsclStatus('Lecture des scanners eSCL provisionnes...', 'info');

    this.scannerApiService
      .listProvisionedEsclScanners()
      .pipe(finalize(() => (this.loadingEsclProvisioned = false)))
      .subscribe({
        next: (devices) => {
          this.networkAdminInitialized = true;
          this.esclProvisionedDevices = devices;
          this.setEsclStatus(
            devices.length
              ? `${devices.length} scanner(s) eSCL provisionne(s).`
              : 'Aucun scanner eSCL provisionne pour le moment.',
            'success',
            notify
          );
        },
        error: (error) => {
          void this.handleEsclErrorStatus(
            error,
            "Impossible de lire les scanners eSCL provisionnes depuis l'agent local."
          );
        }
      });
  }

  discoverEsclDevices(): void {
    const baseUrls = this.parsedEsclBaseUrls;
    if (!baseUrls.length || this.hasBusyState || this.hasEsclBusyState) {
      return;
    }

    this.discoveringEscl = true;
    this.setEsclStatus(`Sondage de ${baseUrls.length} URL eSCL...`, 'info');

    this.scannerApiService
      .discoverEsclScanners(baseUrls, this.esclUsername.trim(), this.esclPassword)
      .pipe(finalize(() => (this.discoveringEscl = false)))
      .subscribe({
        next: (devices) => {
          this.esclDiscoveredDevices = devices;
          this.setEsclStatus(
            devices.length
              ? `${devices.length} scanner(s) eSCL detecte(s).`
              : 'Aucun scanner eSCL joignable sur les URL fournies.',
            devices.length ? 'success' : 'info',
            devices.length > 0
          );
        },
        error: (error) => {
          this.esclDiscoveredDevices = [];
          void this.handleEsclErrorStatus(
            error,
            'La detection eSCL a echoue sur les URL fournies.'
          );
        }
      });
  }

  provisionEsclDevice(device: EsclManagedDevice): void {
    if (this.hasBusyState || this.hasEsclBusyState) {
      return;
    }

    this.provisioningEscl = true;
    this.setEsclStatus(`Provisionnement de ${device.name}...`, 'info');

    this.scannerApiService
      .provisionEsclScanner(this.buildEsclProvisionRequest(device))
      .pipe(finalize(() => (this.provisioningEscl = false)))
      .subscribe({
        next: (provisionedDevice) => {
          this.networkAdminInitialized = true;
          this.upsertProvisionedEsclDevice(provisionedDevice);
          this.markDiscoveredDeviceProvisioned(provisionedDevice.id, true);
          this.setEsclStatus(
            `${provisionedDevice.name} est maintenant provisionne sur cet agent.`,
            'success',
            true
          );
          this.loadScanners();
        },
        error: (error) => {
          void this.handleEsclErrorStatus(
            error,
            `Le provisionnement de ${device.name} a echoue.`
          );
        }
      });
  }

  provisionTypedEsclDevice(): void {
    const [baseUrl] = this.parsedEsclBaseUrls;
    if (!baseUrl || !this.canProvisionTypedEsclDevice) {
      return;
    }

    this.provisioningEscl = true;
    this.setEsclStatus(`Provisionnement manuel de ${baseUrl}...`, 'info');

    this.scannerApiService
      .provisionEsclScanner({
        baseUrl,
        username: this.esclUsername.trim() || undefined,
        password: this.esclPassword || undefined,
        enabled: true
      })
      .pipe(finalize(() => (this.provisioningEscl = false)))
      .subscribe({
        next: (provisionedDevice) => {
          this.networkAdminInitialized = true;
          this.upsertProvisionedEsclDevice(provisionedDevice);
          this.markDiscoveredDeviceProvisioned(provisionedDevice.id, true);
          this.setEsclStatus(
            `${provisionedDevice.name} a ete ajoute sans passer par la decouverte.`,
            'success',
            true
          );
          this.loadScanners();
        },
        error: (error) => {
          void this.handleEsclErrorStatus(
            error,
            `Le provisionnement manuel de ${baseUrl} a echoue.`
          );
        }
      });
  }

  removeProvisionedEsclDevice(device: EsclManagedDevice): void {
    if (this.hasBusyState || this.hasEsclBusyState) {
      return;
    }

    this.removingEsclDeviceIds.add(device.id);
    this.setEsclStatus(`Suppression de ${device.name}...`, 'info');

    this.scannerApiService
      .removeProvisionedEsclScanner(device.id)
      .pipe(finalize(() => this.removingEsclDeviceIds.delete(device.id)))
      .subscribe({
        next: () => {
          this.networkAdminInitialized = true;
          this.esclProvisionedDevices = this.esclProvisionedDevices
            .filter((item) => item.id !== device.id);
          this.markDiscoveredDeviceProvisioned(device.id, false);
          this.setEsclStatus(`${device.name} a ete retire de la flotte eSCL.`, 'success', true);
          this.loadScanners();
        },
        error: (error) => {
          void this.handleEsclErrorStatus(
            error,
            `La suppression de ${device.name} a echoue.`
          );
        }
      });
  }

  previewDocument(): void {
    this.performScan('preview');
  }

  scanDocument(): void {
    this.performScan('final');
  }

  cancelScan(): void {
    if (!this.scanning || !this.scanSubscription) {
      return;
    }

    this.scanSubscription.unsubscribe();
    this.scanSubscription = undefined;
    this.scanning = false;
    this.activeScanMode = null;
    this.setStatus('Numerisation annulee.', 'info', true);
  }

  saveToServer(): void {
    if (!this.scanResult || this.saving || this.lastCaptureMode !== 'final') {
      return;
    }

    this.saving = true;
    this.setStatus("Enregistrement du document numerise sur le serveur...", 'info');

    this.documentApiService
      .uploadScannedFile(this.scanResult)
      .pipe(finalize(() => (this.saving = false)))
      .subscribe({
        next: (response) => {
          this.lastUploadResponse = response;
          this.setStatus(
            `Enregistre avec succes sous ${response.storedFileName}`,
            'success',
            true
          );
          
          // Trigger indexing pipeline after successful upload
          this.triggerIndexing(response.storedFileName);
        },
        error: (error) => {
          void this.handleErrorStatus(
            error,
            "L'API Spring Boot n'est pas joignable. En developpement, demarrez le backend sur http://localhost:8080 avec le proxy Angular."
          );
        }
      });
  }

  // Method to trigger the indexing pipeline (Step 1: Run OCR)
  triggerIndexing(fileName: string): void {
    if (this.indexingInProgress) {
      return;
    }

    this.indexingInProgress = true;
    this.indexingStep = 0;
    this.indexingResult = null;
    this.showHumanInLoop = false;
    
    // Create indexing request
    const indexingRequest = {
      documentId: fileName,
      ocrConfig: {
        useDocOrientationClassify: this.enableAutoRotate,
        useDocUnwarping: true,
        useLayoutDetection: true,
        useOcrForImageBlock: false,
        formatBlockContent: true,
        mergeTables: this.enableDocumentCleanup
      },
      chunkConfig: {
        maxTokens: 500,
        minTokens: 150,
        overlapRatio: 0.2
      }
    };

    // Create a file object from the scan result for the indexing pipeline
    const file = new File([this.scanResult!.blob], fileName, {
      type: this.scanResult!.contentType
    });

    // Step 1: Run OCR and pause for Human-in-the-Loop
    this.pipelineApiService.runOCR(file, fileName, indexingRequest).subscribe({
      next: (result) => {
        this.indexingInProgress = false;
        
        if (result.success) {
          // Show Human-in-the-Loop interface
          this.showHumanInLoop = true;
          this.sessionId = result.session_id;
          this.ocrExtractedText = result.extracted_text;
          this.correctedText = result.extracted_text; // Pre-fill with extracted text
          
          this.messageService.add({
            severity: 'info',
            summary: 'OCR Complete',
            detail: 'Please review and correct the extracted text, then confirm to continue.'
          });
        } else {
          this.setStatus(`OCR failed: ${result.message}`, 'error', true);
        }
      },
      error: (error) => {
        this.indexingInProgress = false;
        this.setStatus(`OCR failed: ${error.message}`, 'error', true);
      }
    });
  }

  // Method to trigger indexing from OCR options (after scan)
  triggerIndexingFromOptions(): void {
    if (!this.scanResult) {
      this.messageService.add({
        severity: 'warn',
        summary: 'Warning',
        detail: 'No scanned document available'
      });
      return;
    }

    const fileName = this.scanResult.fileName;
    
    if (this.indexingInProgress) {
      return;
    }

    console.log('[OCR] Starting OCR pipeline for:', fileName);
    this.indexingInProgress = true;
    this.indexingStep = 0;
    this.indexingResult = null;
    this.showHumanInLoop = false;
    
    // Create indexing request with OCR options from UI
    const indexingRequest = {
      documentId: fileName,
      ocrConfig: {
        useDocOrientationClassify: this.ocrOptions.useOrientation,
        useDocUnwarping: this.ocrOptions.useUnwarp,
        useLayoutDetection: this.ocrOptions.useLayout,
        useOcrForImageBlock: this.ocrOptions.useOcrForImageBlock,
        formatBlockContent: this.ocrOptions.useFormat,
        mergeTables: this.ocrOptions.mergeTables
      },
      chunkConfig: {
        maxTokens: 500,
        minTokens: 150,
        overlapRatio: 0.2
      }
    };

    // Create a file object from the scan result
    const file = new File([this.scanResult!.blob], fileName, {
      type: this.scanResult!.contentType
    });

    console.log('[OCR] Calling pipeline.runOCR()...');
    // Step 1: Run OCR and pause for Human-in-the-Loop
    this.pipelineApiService.runOCR(file, fileName, indexingRequest).subscribe({
      next: (result) => {
        console.log('[OCR] Pipeline response:', result);
        this.indexingInProgress = false;
        
        if (result && result.success) {
          // Access snake_case fields from backend response
          const sessionId = result['session_id'] || result.sessionId;
          const extractedText = result['extracted_text'] || result.extractedText || '';
          
          console.log('[OCR] Session ID:', sessionId);
          console.log('[OCR] Extracted text length:', extractedText.length);
          
          // Show Human-in-the-Loop interface
          this.showHumanInLoop = true;
          this.sessionId = sessionId;
          this.ocrExtractedText = extractedText;
          this.correctedText = extractedText || 'No text extracted';
          
          console.log('[OCR] Human-in-the-loop UI activated');
          
          this.messageService.add({
            severity: 'info',
            summary: 'OCR Complete',
            detail: `Extracted ${extractedText.length} characters. Review and correct the text.`
          });
        } else {
          console.error('[OCR] OCR failed:', result);
          this.setStatus(`OCR failed: ${result?.message || 'Unknown error'}`, 'error', true);
          this.messageService.add({
            severity: 'error',
            summary: 'OCR Failed',
            detail: result?.message || 'Unknown error'
          });
        }
      },
      error: (error) => {
        console.error('[OCR] Pipeline error:', error);
        this.indexingInProgress = false;
        this.setStatus(`OCR failed: ${error.message || error}`, 'error', true);
        this.messageService.add({
          severity: 'error',
          summary: 'OCR Error',
          detail: error.message || error.toString()
        });
      }
    });
  }

  // Method to confirm OCR results and continue with indexing (Step 2)
  confirmOCRResults(): void {
    console.log('[Confirm] Confirm button clicked!');
    
    if (!this.sessionId) {
      this.messageService.add({
        severity: 'warn',
        summary: 'Warning',
        detail: 'No active session found'
      });
      return;
    }

    console.log('[Confirm] Session ID:', this.sessionId);
    console.log('[Confirm] Corrected text length:', this.correctedText?.length);

    this.indexingInProgress = true;
    this.indexingStep = 1; // Start with Segmentation
    this.showHumanInLoop = false;
    
    // Simulate step progression visually
    setTimeout(() => {
      if (this.indexingInProgress && this.indexingStep === 1) {
        this.indexingStep = 2; // Move to Embedding
      }
    }, 2000);
    
    setTimeout(() => {
      if (this.indexingInProgress && this.indexingStep === 2) {
        this.indexingStep = 3; // Move to Indexation
      }
    }, 12000);

    const indexingRequest = {
      chunkConfig: {
        maxTokens: 500,
        minTokens: 150,
        overlapRatio: 0.2
      }
    };

    console.log('[Confirm] Calling confirmAndIndex()...');
    // Step 2: Confirm and continue with chunking + indexing
    this.pipelineApiService.confirmAndIndex(
      this.sessionId,
      this.correctedText,
      indexingRequest
    ).subscribe({
      next: (result) => {
        console.log('[Confirm] Indexing response:', result);
        this.indexingInProgress = false;
        this.indexingResult = result;
        this.sessionId = '';

        if (result && result.success) {
          this.setStatus(`Document indexed successfully with ${result.chunksIndexed} chunks`, 'success', true);
          this.showHumanInLoop = false;
          this.messageService.add({
            severity: 'success',
            summary: 'Success',
            detail: `Document indexed with ${result.chunksIndexed} chunks`
          });
          
          // Clear state for clean start after 3 seconds so user sees success message
          setTimeout(() => {
            this.scanResult = null;
            this.previewUrl = null;
            this.fullResolutionUrl = null;
            this.lastUploadResponse = null;
            this.router.navigate(['/']); // Refresh clean start
          }, 3000);
        } else {
          this.setStatus(`Indexing failed: ${result?.message}`, 'error', true);
          this.messageService.add({
            severity: 'error',
            summary: 'Indexing Failed',
            detail: result?.message || 'Unknown error'
          });
        }
      },
      error: (error) => {
        console.error('[Confirm] Indexing error:', error);
        this.indexingInProgress = false;
        this.showHumanInLoop = true; // Show again so user can retry
        this.setStatus(`Indexing failed: ${error.message || error}`, 'error', true);
        this.messageService.add({
          severity: 'error',
          summary: 'Indexing Error',
          detail: error.message || error.toString()
        });
      }
    });
  }

  // Cancel Human-in-the-Loop
  cancelIndexing(): void {
    this.showHumanInLoop = false;
    this.indexingInProgress = false;
    this.sessionId = '';
    this.messageService.add({
      severity: 'info',
      summary: 'Cancelled',
      detail: 'Indexing cancelled'
    });
  }

  // Method to navigate to query page
  goToQueryPage(): void {
    this.router.navigate(['/query']);
  }

  hasPreview(): boolean {
    return !!this.previewUrl && !!this.scanResult;
  }

  isImagePreview(): boolean {
    return !!this.scanResult?.contentType && this.scanResult.contentType.startsWith('image/');
  }

  isPdfPreview(): boolean {
    return this.scanResult?.contentType === 'application/pdf';
  }

  private loadScannerCapabilities(scannerId: string): void {
    const generation = ++this.capabilitiesGeneration;

    if (!scannerId) {
      this.clearScannerCapabilities();
      return;
    }

    this.loadingCapabilities = true;

    this.scannerApiService
      .getScannerCapabilities(scannerId)
      .pipe(
        finalize(() => {
          if (generation === this.capabilitiesGeneration) {
            this.loadingCapabilities = false;
          }
        })
      )
      .subscribe({
        next: (capabilities) => {
          if (generation !== this.capabilitiesGeneration) {
            return;
          }

          this.scannerCapabilities = capabilities;
          this.applyCapabilities(capabilities);
        },
        error: (error) => {
          if (generation !== this.capabilitiesGeneration) {
            return;
          }

          this.scannerCapabilities = null;
          this.enableDuplex = false;
          void this.handleErrorStatus(
            error,
            'Impossible de lire les capacites du scanner selectionne.'
          );
        }
      });
  }

  private clearScannerCapabilities(): void {
    this.capabilitiesGeneration++;
    this.scannerCapabilities = null;
    this.loadingCapabilities = false;
    this.enableDuplex = false;
  }

  private applyCapabilities(capabilities: ScannerCapabilities): void {
    const supportedSources = this.resolveSupportedSources(capabilities);
    const supportedColorModes = this.resolveSupportedColorModes(capabilities);
    const supportedOutputFormats = this.resolveSupportedOutputFormats(capabilities);
    const supportedDpiValues = this.resolveSupportedDpiValues(capabilities);

    this.selectedScanSource = supportedSources.includes(this.selectedScanSource)
      ? this.selectedScanSource
      : supportedSources.includes(DEFAULT_SCAN_SETTINGS.source)
        ? DEFAULT_SCAN_SETTINGS.source
        : supportedSources[0];

    this.selectedColorMode = supportedColorModes.includes(this.selectedColorMode)
      ? this.selectedColorMode
      : supportedColorModes.includes(DEFAULT_SCAN_SETTINGS.colorMode)
        ? DEFAULT_SCAN_SETTINGS.colorMode
        : supportedColorModes[0];

    this.selectedOutputFormat = supportedOutputFormats.includes(this.selectedOutputFormat)
      ? this.selectedOutputFormat
      : this.resolvePreferredOutputFormat(supportedOutputFormats);

    this.selectedFinalDpi = supportedDpiValues.includes(this.selectedFinalDpi)
      ? this.selectedFinalDpi
      : this.resolveClosestValue(supportedDpiValues, DEFAULT_SCAN_SETTINGS.dpi);

    if (!this.canToggleDuplex) {
      this.enableDuplex = false;
    }
  }

  private performScan(captureMode: CaptureMode): void {
    if (!this.selectedScannerId || this.scanning || this.loadingCapabilities) {
      return;
    }

    const initialScannerId = this.selectedScannerId;
    const scanCandidateIds = this.buildScanCandidateIds(initialScannerId);
    const scanSettings = this.buildScanSettings(captureMode);

    this.scanning = true;
    this.activeScanMode = captureMode;
    this.lastUploadResponse = null;
    this.setStatus(
      captureMode === 'preview'
        ? `Creation de l'apercu rapide en ${this.previewOutputLabel.toLowerCase()} a ${this.previewDpi} PPP...`
        : 'Creation de la capture finale...',
      'info'
    );

    this.scanSubscription = this.executeScanWithFailover(
      captureMode,
      scanCandidateIds,
      scanSettings
    )
      .pipe(
        finalize(() => {
          this.scanning = false;
          this.activeScanMode = null;
          this.scanSubscription = undefined;
        })
      )
      .subscribe({
        next: (result) => {
          this.scanResult = result;
          this.lastCaptureMode = captureMode;
          this.promoteSuccessfulScannerRoute(result);
          void this.applyPreviewUrlsAsync(result);
          const routeDetail =
            result.scannerId !== initialScannerId
              ? ` via ${this.describeScannerRoute(result.scannerId)}`
              : '';
          this.setStatus(
            captureMode === 'preview'
              ? `Apercu pret${routeDetail} : ${result.fileName}. Lancez le scan final avant l'enregistrement.`
              : `Capture finale terminee${routeDetail} : ${result.fileName}`,
            'success',
            true
          );
        },
        error: (error) => {
          void this.handleErrorStatus(
            error,
            captureMode === 'preview'
              ? "L'apercu rapide a echoue."
              : 'La numerisation finale a echoue.'
          );
        }
      });
  }

  private executeScanWithFailover(
    captureMode: CaptureMode,
    scanCandidateIds: string[],
    settings: ScanSettings,
    attemptIndex = 0
  ): Observable<ScanResult> {
    const scannerId = scanCandidateIds[attemptIndex];
    return this.scannerApiService.scan({ scannerId, settings }).pipe(
      catchError((error) => {
        if (this.shouldRecordRouteFailure(error)) {
          this.rememberFailedScannerRoute(scannerId);
        }

        if (!this.shouldRetryWithAlternateRoute(error, scanCandidateIds, attemptIndex)) {
          return throwError(() => error);
        }

        const nextScannerId = scanCandidateIds[attemptIndex + 1];
        this.setStatus(
          captureMode === 'preview'
            ? `Apercu: ${this.describeScannerRoute(scannerId)} indisponible. Bascule automatique vers ${this.describeScannerRoute(nextScannerId)}...`
            : `Scan final: ${this.describeScannerRoute(scannerId)} indisponible. Bascule automatique vers ${this.describeScannerRoute(nextScannerId)}...`,
          'info'
        );

        return this.executeScanWithFailover(
          captureMode,
          scanCandidateIds,
          settings,
          attemptIndex + 1
        );
      })
    );
  }

  private buildScanCandidateIds(primaryScannerId: string): string[] {
    return [primaryScannerId];
  }

  private shouldRetryWithAlternateRoute(
    error: unknown,
    scanCandidateIds: string[],
    attemptIndex: number
  ): boolean {
    if (attemptIndex >= scanCandidateIds.length - 1) {
      return false;
    }

    return error instanceof HttpErrorResponse && error.status > 0;
  }

  private buildScanSettings(captureMode: CaptureMode): ScanSettings {
    const isPreview = captureMode === 'preview';
    return {
      ...DEFAULT_SCAN_SETTINGS,
      dpi: isPreview ? this.previewDpi : this.selectedFinalDpi,
      colorMode: isPreview ? this.previewColorMode : this.selectedColorMode,
      source: this.selectedScanSource,
      duplex: isPreview ? false : this.canToggleDuplex ? this.enableDuplex : false,
      outputFormat: isPreview ? this.previewOutputFormat : this.selectedOutputFormat,
      enableAutoCrop: isPreview ? false : this.enableDocumentCleanup,
      enableDeskew: isPreview ? false : this.enableDocumentCleanup,
      enableContrastCleanup: isPreview ? false : this.enableDocumentCleanup,
      enableAutoRotate: isPreview ? false : this.enableAutoRotate,
      skipBlankPages: isPreview ? false : this.skipBlankPages
    };
  }

  private buildScannerChoices(scanners: ScannerDescriptor[]): ScannerChoice[] {
    return this.rankScanners(scanners).map((scanner) => this.buildScannerChoice(scanner));
  }

  private buildScannerChoice(scanner: ScannerDescriptor): ScannerChoice {
    const providerSummary = this.labelForProvider(scanner.provider);
    return {
      label: scanner.name,
      displayName: scanner.name,
      value: scanner.id,
      disabled: !scanner.available,
      providerSummary,
      isNetwork: this.isNetworkProvider(scanner.provider)
    };
  }

  private rankScanners(scanners: ScannerDescriptor[]): ScannerDescriptor[] {
    const storedRoutes = this.readStoredScannerRoutes();
    const lastScannerId = this.readStoredLastScannerId();
    const storedRouteStats = this.readStoredScannerRouteStats();

    return [...scanners].sort((left, right) => {
      const scoreDelta =
        this.scoreScannerCandidate(
          right,
          storedRoutes[right.id],
          lastScannerId,
          storedRouteStats[right.id]
        )
        - this.scoreScannerCandidate(
          left,
          storedRoutes[left.id],
          lastScannerId,
          storedRouteStats[left.id]
        );

      if (scoreDelta !== 0) {
        return scoreDelta;
      }

      if (!!left.available !== !!right.available) {
        return left.available ? -1 : 1;
      }

      const nameOrder = left.name.localeCompare(right.name);
      if (nameOrder !== 0) {
        return nameOrder;
      }

      return left.provider.localeCompare(right.provider);
    });
  }

  private scoreScannerCandidate(
    scanner: ScannerDescriptor,
    storedRoute: StoredScannerRoute | undefined,
    lastScannerId: string | null,
    routeStats: StoredScannerRouteStats | undefined
  ): number {
    let score = scanner.available ? 1000 : 0;

    if (storedRoute?.scannerId === scanner.id) {
      score += 320;
    }
    else if (storedRoute?.provider === scanner.provider) {
      score += 120;
    }

    if (lastScannerId === scanner.id) {
      score += 60;
    }

    if (routeStats) {
      score += Math.min(routeStats.successCount * 24, 160);
      score -= Math.min(routeStats.failureCount * 28, 180);
      score += this.performanceScore(routeStats.averageElapsedMs ?? routeStats.lastElapsedMs);

      if (this.isRecentTimestamp(routeStats.lastSuccessAt, 24 * 60)) {
        score += 30;
      }

      if (this.isRecentTimestamp(routeStats.lastFailureAt, 15)) {
        score -= 180;
      }
    }

    score += this.providerBaseScore(scanner.provider);
    return score;
  }

  private providerBaseScore(provider: string): number {
    switch (provider.toUpperCase()) {
      case 'WIA':
        return 30;
      case 'ESCL':
        return 25;
      case 'TWAIN':
        return 20;
      default:
        return 10;
    }
  }

  private resolveInitialScannerSelection(previousScannerId: string): string {
    const availableChoiceValues = this.scannerChoices
      .filter((choice) => !choice.disabled)
      .map((choice) => choice.value);

    if (availableChoiceValues.includes(previousScannerId)) {
      return previousScannerId;
    }

    const lastScannerId = this.readStoredLastScannerId();
    if (lastScannerId && availableChoiceValues.includes(lastScannerId)) {
      return lastScannerId;
    }

    return availableChoiceValues[0] ?? '';
  }

  private rememberSuccessfulScannerRoute(result: ScanResult): void {
    const successfulScanner = this.scanners.find((scanner) => scanner.id === result.scannerId);
    if (!successfulScanner) {
      return;
    }

    const storedRoutes = this.readStoredScannerRoutes();
    storedRoutes[successfulScanner.id] = {
      scannerId: successfulScanner.id,
      provider: successfulScanner.provider,
      elapsedMs: result.elapsedMs,
      updatedAt: new Date().toISOString()
    };

    this.writeStoredScannerRoutes(storedRoutes);
    this.storeLastScannerId(successfulScanner.id);

    const routeStats = this.readStoredScannerRouteStats();
    const previousStats = routeStats[successfulScanner.id];
    const successCount = (previousStats?.successCount ?? 0) + 1;
    const lastElapsedMs = result.elapsedMs;
    const averageElapsedMs = this.calculateAverageElapsedMs(
      previousStats?.averageElapsedMs ?? previousStats?.lastElapsedMs,
      previousStats?.successCount ?? 0,
      result.elapsedMs
    );

    routeStats[successfulScanner.id] = {
      scannerId: successfulScanner.id,
      provider: successfulScanner.provider,
      successCount,
      failureCount: previousStats?.failureCount ?? 0,
      averageElapsedMs,
      lastElapsedMs,
      lastSuccessAt: new Date().toISOString(),
      lastFailureAt: previousStats?.lastFailureAt
    };

    this.writeStoredScannerRouteStats(routeStats);
  }

  private promoteSuccessfulScannerRoute(result: ScanResult): void {
    const previousScannerId = this.selectedScannerId;
    this.rememberSuccessfulScannerRoute(result);
    this.scannerChoices = this.buildScannerChoices(this.scanners);
    this.selectedScannerId = result.scannerId;

    if (result.scannerId !== previousScannerId) {
      this.loadScannerCapabilities(result.scannerId);
    }
  }

  private describeScannerRoute(scannerId: string): string {
    const scanner = this.scanners.find((item) => item.id === scannerId);
    if (!scanner) {
      return scannerId;
    }

    return `${scanner.name} (${scanner.provider})`;
  }

  private readStoredScannerRoutes(): Record<string, StoredScannerRoute> {
    try {
      const rawValue = localStorage.getItem(SCANNER_ROUTE_STORAGE_KEY);
      return rawValue ? (JSON.parse(rawValue) as Record<string, StoredScannerRoute>) : {};
    } catch {
      return {};
    }
  }

  private readStoredScannerRouteStats(): Record<string, StoredScannerRouteStats> {
    try {
      const rawValue = localStorage.getItem(SCANNER_ROUTE_STATS_STORAGE_KEY);
      return rawValue ? (JSON.parse(rawValue) as Record<string, StoredScannerRouteStats>) : {};
    } catch {
      return {};
    }
  }

  private writeStoredScannerRoutes(routes: Record<string, StoredScannerRoute>): void {
    try {
      localStorage.setItem(SCANNER_ROUTE_STORAGE_KEY, JSON.stringify(routes));
    } catch {
      // Ignore storage failures. Routing still works for the current session.
    }
  }

  private writeStoredScannerRouteStats(stats: Record<string, StoredScannerRouteStats>): void {
    try {
      localStorage.setItem(SCANNER_ROUTE_STATS_STORAGE_KEY, JSON.stringify(stats));
    } catch {
      // Ignore storage failures. Routing still works for the current session.
    }
  }

  private readStoredLastScannerId(): string | null {
    try {
      return localStorage.getItem(LAST_SCANNER_STORAGE_KEY);
    } catch {
      return null;
    }
  }

  private storeLastScannerId(scannerId: string): void {
    try {
      localStorage.setItem(LAST_SCANNER_STORAGE_KEY, scannerId);
    } catch {
      // Ignore storage failures. Selection still works for the current session.
    }
  }

  private rememberFailedScannerRoute(scannerId: string): void {
    const failedScanner = this.scanners.find((scanner) => scanner.id === scannerId);
    if (!failedScanner) {
      return;
    }

    const routeStats = this.readStoredScannerRouteStats();
    const previousStats = routeStats[failedScanner.id];
    routeStats[failedScanner.id] = {
      scannerId: failedScanner.id,
      provider: failedScanner.provider,
      successCount: previousStats?.successCount ?? 0,
      failureCount: (previousStats?.failureCount ?? 0) + 1,
      averageElapsedMs: previousStats?.averageElapsedMs,
      lastElapsedMs: previousStats?.lastElapsedMs,
      lastSuccessAt: previousStats?.lastSuccessAt,
      lastFailureAt: new Date().toISOString()
    };

    this.writeStoredScannerRouteStats(routeStats);
  }

  private shouldRecordRouteFailure(error: unknown): boolean {
    return error instanceof HttpErrorResponse && error.status > 0;
  }

  private performanceScore(elapsedMs: number | undefined): number {
    if (!elapsedMs || elapsedMs <= 0) {
      return 0;
    }

    if (elapsedMs <= 2500) {
      return 120;
    }

    if (elapsedMs <= 5000) {
      return 80;
    }

    if (elapsedMs <= 9000) {
      return 50;
    }

    if (elapsedMs <= 15000) {
      return 20;
    }

    return -20;
  }

  private isRecentTimestamp(timestamp: string | undefined, maxAgeMinutes: number): boolean {
    if (!timestamp) {
      return false;
    }

    const value = Date.parse(timestamp);
    if (Number.isNaN(value)) {
      return false;
    }

    return Date.now() - value <= maxAgeMinutes * 60 * 1000;
  }

  private calculateAverageElapsedMs(
    previousAverage: number | undefined,
    previousSuccessCount: number,
    latestElapsedMs: number | undefined
  ): number | undefined {
    if (!latestElapsedMs || latestElapsedMs <= 0) {
      return previousAverage;
    }

    if (!previousAverage || previousSuccessCount <= 0) {
      return latestElapsedMs;
    }

    return Math.round(
      ((previousAverage * previousSuccessCount) + latestElapsedMs) / (previousSuccessCount + 1)
    );
  }

  private resolveSupportedSources(capabilities = this.scannerCapabilities): ScanSource[] {
    return capabilities?.supportedSources?.length
      ? capabilities.supportedSources
      : ['FLATBED', 'ADF'];
  }

  private resolveSupportedColorModes(capabilities = this.scannerCapabilities): ColorMode[] {
    return capabilities?.supportedColorModes?.length
      ? capabilities.supportedColorModes
      : ['COLOR', 'GRAYSCALE', 'BLACK_WHITE'];
  }

  private resolveSupportedOutputFormats(capabilities = this.scannerCapabilities): OutputFormat[] {
    return capabilities?.supportedOutputFormats?.length
      ? capabilities.supportedOutputFormats
      : ['PNG', 'JPG', 'PDF'];
  }

  private resolveSupportedDpiValues(capabilities = this.scannerCapabilities): number[] {
    const explicitValues = (capabilities?.suggestedDpiValues ?? [])
      .filter((value) => value >= 75 && value <= 2400)
      .sort((left, right) => left - right);
    if (explicitValues.length > 0) {
      return [...new Set(explicitValues)];
    }

    const range = capabilities?.dpiRange;
    const defaults = [150, 200, 300, 600, 1200, 2400];
    if (!range) {
      return defaults;
    }

    const clampedValues = defaults
      .map((value) => this.snapDpiToRange(value, range.min, range.max, range.step))
      .filter((value, index, allValues) => allValues.indexOf(value) === index)
      .sort((left, right) => left - right);

    return clampedValues.length > 0
      ? clampedValues
      : [this.snapDpiToRange(DEFAULT_SCAN_SETTINGS.dpi, range.min, range.max, range.step)];
  }

  private resolvePreferredOutputFormat(supportedFormats: OutputFormat[]): OutputFormat {
    return (
      ['PNG', 'JPG', 'PDF'].find((format) =>
        supportedFormats.includes(format as OutputFormat)
      ) as OutputFormat | undefined
    ) ?? supportedFormats[0] ?? 'PNG';
  }

  private resolveClosestDpi(target: number): number {
    return this.resolveClosestValue(this.resolveSupportedDpiValues(), target);
  }

  private resolveClosestValue(values: number[], target: number): number {
    if (!values.length) {
      return target;
    }

    return values.reduce((closest, current) =>
      Math.abs(current - target) < Math.abs(closest - target) ? current : closest
    );
  }

  private snapDpiToRange(value: number, min: number, max: number, step: number): number {
    const clampedValue = Math.min(Math.max(value, min), max);
    if (step <= 0) {
      return clampedValue;
    }

    const snappedValue = min + Math.round((clampedValue - min) / step) * step;
    return Math.min(Math.max(snappedValue, min), max);
  }

  private labelForSource(source: ScanSource): string {
    return source === 'ADF' ? 'Chargeur automatique' : 'Vitre';
  }

  private labelForColorMode(colorMode: ColorMode): string {
    switch (colorMode) {
      case 'GRAYSCALE':
        return 'Niveaux de gris';
      case 'BLACK_WHITE':
        return 'Noir et blanc';
      default:
        return 'Couleur';
    }
  }

  private labelForOutputFormat(outputFormat: OutputFormat): string {
    switch (outputFormat) {
      case 'JPG':
        return 'Image JPG';
      case 'PDF':
        return 'Document PDF';
      default:
        return 'Image PNG';
    }
  }

  private labelForProvider(provider: string): string {
    return this.isNetworkProvider(provider) ? 'eSCL / AirScan' : provider;
  }

  private isNetworkProvider(provider: string): boolean {
    return provider.toUpperCase() === 'ESCL';
  }

  private async applyPreviewUrlsAsync(result: ScanResult): Promise<void> {
    const generation = ++this.previewGeneration;
    const originalUrl = URL.createObjectURL(result.blob);
    this.clearPreviewUrls();
    this.fullResolutionUrl = originalUrl;
    this.previewUrl = originalUrl;

    const lighterPreviewUrl = await this.buildLightweightPreviewUrl(result);
    if (!lighterPreviewUrl || generation !== this.previewGeneration) {
      if (lighterPreviewUrl) {
        URL.revokeObjectURL(lighterPreviewUrl);
      }

      return;
    }

    if (this.previewUrl && this.previewUrl !== this.fullResolutionUrl) {
      URL.revokeObjectURL(this.previewUrl);
    }

    this.previewUrl = lighterPreviewUrl;
  }

  private async buildLightweightPreviewUrl(result: ScanResult): Promise<string | null> {
    if (!result.contentType.startsWith('image/') || result.blob.size < 512 * 1024) {
      return null;
    }

    if (typeof createImageBitmap !== 'function') {
      return null;
    }

    try {
      const bitmap = await createImageBitmap(result.blob);
      try {
        const longestEdge = Math.max(bitmap.width, bitmap.height);
        if (longestEdge <= 1440) {
          return null;
        }

        const scale = 1440 / longestEdge;
        const canvas = document.createElement('canvas');
        canvas.width = Math.max(1, Math.round(bitmap.width * scale));
        canvas.height = Math.max(1, Math.round(bitmap.height * scale));
        const context = canvas.getContext('2d');
        if (!context) {
          return null;
        }

        context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
        const previewBlob = await new Promise<Blob | null>((resolve) =>
          canvas.toBlob(resolve, 'image/jpeg', 0.86)
        );

        return previewBlob ? URL.createObjectURL(previewBlob) : null;
      } finally {
        bitmap.close();
      }
    } catch {
      return null;
    }
  }

  private clearPreviewUrls(): void {
    this.previewGeneration++;

    if (this.previewUrl && this.previewUrl !== this.fullResolutionUrl) {
      URL.revokeObjectURL(this.previewUrl);
    }

    if (this.fullResolutionUrl) {
      URL.revokeObjectURL(this.fullResolutionUrl);
    }

    this.previewUrl = null;
    this.fullResolutionUrl = null;
  }

  isProvisionedEsclDevice(deviceId: string): boolean {
    return this.esclProvisionedDevices.some((device) => device.id === deviceId);
  }

  isRemovingEsclDevice(deviceId: string): boolean {
    return this.removingEsclDeviceIds.has(deviceId);
  }

  private setStatus(message: string, level: StatusLevel, notify = false): void {
    this.statusMessage = message;
    this.statusLevel = level;

    if (notify) {
      this.messageService.clear('scanner-page');
      this.messageService.add({
        key: 'scanner-page',
        severity: level,
        summary: this.resolveToastSummary(level),
        detail: message
      });
    }
  }

  private setEsclStatus(message: string, level: StatusLevel, notify = false): void {
    this.esclStatusMessage = message;
    this.esclStatusLevel = level;

    if (notify) {
      this.messageService.add({
        key: 'scanner-page',
        severity: level,
        summary: 'Scanners LAN',
        detail: message
      });
    }
  }

  private async handleErrorStatus(error: unknown, networkFallback: string): Promise<void> {
    const message = await this.resolveError(error, networkFallback);
    this.setStatus(message, 'error', true);
  }

  private async handleEsclErrorStatus(error: unknown, networkFallback: string): Promise<void> {
    const message = await this.resolveError(error, networkFallback);
    this.setEsclStatus(message, 'error', true);
  }

  private async resolveError(error: unknown, networkFallback: string): Promise<string> {
    if (error instanceof HttpErrorResponse) {
      if (error.status === 0) {
        return networkFallback;
      }

      if (error.error instanceof Blob) {
        const blobMessage = await this.readBlobErrorMessage(error.error);
        if (blobMessage) {
          return blobMessage;
        }
      }

      if (typeof error.error === 'string' && error.error.trim()) {
        return error.error;
      }

      if (error.error?.message) {
        return error.error.message;
      }

      if (error.error?.title) {
        return [error.error.title, error.error.detail].filter(Boolean).join(': ');
      }

      if (error.message) {
        return error.message;
      }
    }

    return 'Erreur inattendue.';
  }

  private async readBlobErrorMessage(errorBlob: Blob): Promise<string | null> {
    try {
      const text = (await errorBlob.text()).trim();
      if (!text) {
        return null;
      }

      try {
        const parsed = JSON.parse(text) as {
          message?: string;
          title?: string;
          detail?: string;
        };
        if (parsed.message) {
          return parsed.message;
        }

        if (parsed.title) {
          return [parsed.title, parsed.detail].filter(Boolean).join(': ');
        }
      } catch {
        return text;
      }

      return text;
    } catch {
      return null;
    }
  }

  private resolveToastSummary(level: StatusLevel): string {
    switch (level) {
      case 'success':
        return 'Termine';
      case 'error':
        return 'Action impossible';
      default:
        return 'Information';
    }
  }

  private formatFileSize(bytes: number): string {
    if (bytes < 1024) {
      return `${bytes} o`;
    }

    const kilobytes = bytes / 1024;
    if (kilobytes < 1024) {
      return `${kilobytes.toFixed(1)} Ko`;
    }

    const megabytes = kilobytes / 1024;
    return `${megabytes.toFixed(2)} Mo`;
  }

  private parseEsclBaseUrls(rawValue: string): string[] {
    return [...new Set(
      rawValue
        .split(/[\r\n,;]+/)
        .map((value) => value.trim())
        .filter((value) => /^https?:\/\//i.test(value))
    )];
  }

  private buildEsclProvisionRequest(device: EsclManagedDevice): EsclProvisionRequest {
    return {
      id: device.id,
      name: device.name,
      baseUrl: device.baseUrl,
      username: this.esclUsername.trim() || undefined,
      password: this.esclPassword || undefined,
      enabled: true
    };
  }

  private upsertProvisionedEsclDevice(device: EsclManagedDevice): void {
    const otherDevices = this.esclProvisionedDevices.filter((item) => item.id !== device.id);
    this.esclProvisionedDevices = [...otherDevices, device]
      .sort((left, right) => left.name.localeCompare(right.name));
  }

  private markDiscoveredDeviceProvisioned(deviceId: string, provisioned: boolean): void {
    this.esclDiscoveredDevices = this.esclDiscoveredDevices.map((device) =>
      device.id === deviceId ? { ...device, provisioned } : device
    );
  }
}
