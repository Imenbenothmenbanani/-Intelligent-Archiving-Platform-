package com.example.scannerfeature.backend.controller;

import com.example.scannerfeature.backend.dto.BackendHealthResponse;
import com.example.scannerfeature.backend.dto.StoredDocumentSummary;
import com.example.scannerfeature.backend.dto.StorageResult;
import com.example.scannerfeature.backend.dto.UploadResponse;
import com.example.scannerfeature.backend.pipeline.PipelineServiceClient;
import com.example.scannerfeature.backend.pipeline.PipelineServiceClient.IndexingResult;
import com.example.scannerfeature.backend.pipeline.PipelineServiceClient.QueryResult;
import com.example.scannerfeature.backend.pipeline.request.IndexingRequest;
import com.example.scannerfeature.backend.pipeline.request.QueryRequest;
import com.example.scannerfeature.backend.service.DocumentStorageService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Validated
@RestController
@RequestMapping("/api/documents")
public class DocumentController {

    private final DocumentStorageService documentStorageService;
    private final PipelineServiceClient pipelineServiceClient;

    public DocumentController(DocumentStorageService documentStorageService, PipelineServiceClient pipelineServiceClient) {
        this.documentStorageService = documentStorageService;
        this.pipelineServiceClient = pipelineServiceClient;
    }

    @GetMapping("/health")
    public ResponseEntity<BackendHealthResponse> getHealth() {
        return ResponseEntity.ok(documentStorageService.getStorageHealth());
    }

    @GetMapping("/recent")
    public ResponseEntity<List<StoredDocumentSummary>> listRecentDocuments(
            @RequestParam(value = "limit", defaultValue = "8") int limit) {
        return ResponseEntity.ok(documentStorageService.listRecentDocuments(limit));
    }

    @PostMapping(value = "/upload", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<UploadResponse> uploadDocument(
            @RequestPart("file") MultipartFile file,
            @RequestParam("originalFileName") @NotBlank String originalFileName,
            @RequestParam(value = "contentType", required = false) String contentType,
            @RequestParam Map<String, String> requestParams) {

        Map<String, String> metadata = new HashMap<>(requestParams);
        metadata.remove("originalFileName");
        metadata.remove("contentType");

        StorageResult result = documentStorageService.store(file, originalFileName, contentType, metadata);
        return ResponseEntity.ok(new UploadResponse(
                true,
                result.storedFileName(),
                result.contentType(),
                result.fileSize(),
                result.storedAt(),
                metadata.get("scannerId"),
                metadata.get("provider")));
    }

    @PostMapping(value = "/index", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<IndexingResult> indexDocument(
            @RequestPart("file") MultipartFile file,
            @RequestPart(value = "request", required = false) @Valid IndexingRequest request) {

        System.out.println("[Backend] /index endpoint called");
        System.out.println("[Backend] File name: " + file.getOriginalFilename());
        System.out.println("[Backend] Request received: " + (request != null ? "YES" : "NULL"));

        String documentId = request != null ? request.getDocumentId() : "doc-" + System.currentTimeMillis();
        
        boolean useOrientation = true;
        boolean useUnwarp = true;
        boolean useLayout = true;
        boolean useOcrForImageBlock = false;
        boolean useFormat = true;
        boolean mergeTables = false;
        int maxTokens = 500;
        double overlapRatio = 0.2;
        
        if (request != null && request.getOcrConfig() != null) {
            useOrientation = request.getOcrConfig().isUseDocOrientationClassify();
            useUnwarp = request.getOcrConfig().isUseDocUnwarping();
            useLayout = request.getOcrConfig().isUseLayoutDetection();
            useOcrForImageBlock = request.getOcrConfig().isUseOcrForImageBlock();
            useFormat = request.getOcrConfig().isFormatBlockContent();
            mergeTables = request.getOcrConfig().isMergeTables();
            
            System.out.println("[Backend] OCR Config - Orientation: " + useOrientation + ", Unwarp: " + useUnwarp + 
                             ", Layout: " + useLayout + ", OcrForImageBlock: " + useOcrForImageBlock + 
                             ", Format: " + useFormat + ", MergeTables: " + mergeTables);
        } else {
            System.out.println("[Backend] No OCR Config received - using defaults");
        }
        
        if (request != null && request.getChunkConfig() != null) {
            maxTokens = request.getChunkConfig().getMaxTokens();
            overlapRatio = request.getChunkConfig().getOverlapRatio();
        }

        System.out.println("[Backend] Calling runOCR with options - Orientation: " + useOrientation);
        
        // TWO-STEP FLOW: Step 1 - Run OCR and return extracted text for Human-in-the-Loop
        PipelineServiceClient.OCRResult ocrResult = pipelineServiceClient.runOCR(
                file, documentId, useOrientation, useUnwarp, useLayout, useOcrForImageBlock, useFormat, mergeTables
        );

        // Return session ID and extracted text for user review
        IndexingResult indexingResult = new IndexingResult();
        indexingResult.setSuccess(true);
        indexingResult.setSessionId(ocrResult.getSessionId());
        indexingResult.setDocumentId(documentId);
        indexingResult.setExtractedText(ocrResult.getExtractedText());
        indexingResult.setMessage("OCR completed. Please review and correct the text.");

        System.out.println("[Backend] OCR Result - Session ID: " + ocrResult.getSessionId() + 
                         ", Text length: " + (ocrResult.getExtractedText() != null ? ocrResult.getExtractedText().length() : 0));

        return ResponseEntity.ok(indexingResult);
    }

    @PostMapping("/confirm")
    public ResponseEntity<IndexingResult> confirmAndIndex(
            @Valid @RequestBody ConfirmRequest request) {

        System.out.println("[Backend] /confirm endpoint called");
        System.out.println("[Backend] Session ID: " + request.getSessionId());
        System.out.println("[Backend] Corrected text length: " + (request.getCorrectedText() != null ? request.getCorrectedText().length() : 0));
        System.out.println("[Backend] Max tokens: " + request.getMaxTokens() + ", Overlap ratio: " + request.getOverlapRatio());

        // Step 2 - User confirms/corrects and continues with indexing
        IndexingResult result = pipelineServiceClient.confirmAndIndex(
                request.getSessionId(),
                request.getCorrectedText(),
                request.getMaxTokens(),
                request.getOverlapRatio()
        );

        System.out.println("[Backend] Confirm result - Success: " + result.isSuccess() + ", Chunks indexed: " + result.getChunksIndexed());

        return ResponseEntity.ok(result);
    }

    @PostMapping("/query")
    public ResponseEntity<QueryResult> queryDocuments(
            @Valid @RequestBody QueryRequest request) {

        QueryResult result = pipelineServiceClient.queryDocuments(
                request.getQueryText(),
                request.getTopK(),
                request.getRerankTopN()
        );

        return ResponseEntity.ok(result);
    }

    @GetMapping("/chunk/{chunkId}")
    public ResponseEntity<?> getChunkDetails(
            @PathVariable @NotBlank String chunkId) {
        return ResponseEntity.ok(pipelineServiceClient.getChunkDetails(chunkId));
    }

    @GetMapping("/document/{documentId}")
    public ResponseEntity<?> getDocumentImage(
            @PathVariable @NotBlank String documentId) {
        return pipelineServiceClient.getDocumentImage(documentId);
    }
}
