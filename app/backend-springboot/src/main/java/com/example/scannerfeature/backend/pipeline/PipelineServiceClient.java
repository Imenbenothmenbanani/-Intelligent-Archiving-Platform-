package com.example.scannerfeature.backend.pipeline;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.util.UriComponentsBuilder;

import java.io.IOException;
import java.util.HashMap;
import java.util.Map;

/**
 * Pipeline Service Client - Calls the unified FastAPI pipeline service
 * that orchestrates all existing Python services (OCR, Chunk, Embedding, Storage)
 * Implements the two-step Human-in-the-Loop flow.
 */
@Slf4j
@Service
public class PipelineServiceClient {

    @Value("${service.pipeline.url:http://localhost:8082}")
    private String pipelineServiceUrl;

    private final RestTemplate restTemplate = new RestTemplate();

    /**
     * Step 1: Run OCR and return extracted text for Human-in-the-Loop
     * This pauses the pipeline and waits for user confirmation.
     */
    public OCRResult runOCR(
            MultipartFile file,
            String documentId,
            boolean useOrientation,
            boolean useUnwarp,
            boolean useLayout,
            boolean useOcrForImageBlock,
            boolean useFormat,
            boolean mergeTables) {

        String endpoint = pipelineServiceUrl + "/pipeline/ocr";
        
        System.out.println("[PipelineClient] Sending OCR request to: " + endpoint);
        System.out.println("[PipelineClient] OCR Options - Orientation: " + useOrientation + ", Unwarp: " + useUnwarp + 
                         ", Layout: " + useLayout + ", OcrForImageBlock: " + useOcrForImageBlock + 
                         ", Format: " + useFormat + ", MergeTables: " + mergeTables);

        try {
            MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
            body.add("file", new ByteArrayResource(file.getBytes()) {
                @Override
                public String getFilename() {
                    return file.getOriginalFilename();
                }
            });

            UriComponentsBuilder uriBuilder = UriComponentsBuilder.fromHttpUrl(endpoint)
                    .queryParam("document_id", documentId)
                    .queryParam("use_orientation", useOrientation)
                    .queryParam("use_unwarp", useUnwarp)
                    .queryParam("use_layout", useLayout)
                    .queryParam("use_ocr_for_image_block", useOcrForImageBlock)
                    .queryParam("use_format", useFormat)
                    .queryParam("use_merge_layout", mergeTables);

            System.out.println("[PipelineClient] Built URI: " + uriBuilder.toUriString());

            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.MULTIPART_FORM_DATA);

            HttpEntity<MultiValueMap<String, Object>> requestEntity = new HttpEntity<>(body, headers);

            ResponseEntity<OCRResult> response = restTemplate.postForEntity(
                    uriBuilder.toUriString(), requestEntity, OCRResult.class);

            if (response.getBody() != null) {
                log.info("OCR completed for document: {}", documentId);
                System.out.println("[PipelineClient] OCR Response - Session ID: " + response.getBody().getSessionId() + 
                                 ", Extracted text length: " + (response.getBody().getExtractedText() != null ? response.getBody().getExtractedText().length() : 0));
                return response.getBody();
            } else {
                throw new PipelineException("Pipeline service returned null response");
            }

        } catch (RestClientException | IOException e) {
            log.error("Failed to run OCR: {}", e.getMessage());
            System.out.println("[PipelineClient] OCR ERROR: " + e.getMessage());
            e.printStackTrace();
            throw new PipelineException("Failed to run OCR", e);
        }
    }

    /**
     * Step 2: User confirms/corrects OCR text and continues with indexing
     */
    public IndexingResult confirmAndIndex(
            String sessionId,
            String correctedText,
            int maxTokens,
            double overlapRatio) {

        String endpoint = pipelineServiceUrl + "/pipeline/confirm";

        try {
            System.out.println("[PipelineClient] Confirming and indexing for session: " + sessionId);
            System.out.println("[PipelineClient] Corrected text length: " + (correctedText != null ? correctedText.length() : 0) + " chars");
            
            // Build URL with query parameters (FastAPI expects Query params, not body)
            UriComponentsBuilder uriBuilder = UriComponentsBuilder.fromHttpUrl(endpoint)
                    .queryParam("session_id", sessionId)
                    .queryParam("corrected_text", correctedText != null ? correctedText : "")
                    .queryParam("max_tokens", maxTokens)
                    .queryParam("overlap_ratio", overlapRatio);
            
            System.out.println("[PipelineClient] Confirm URL: " + uriBuilder.toUriString());

            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);

            HttpEntity<Void> requestEntity = new HttpEntity<>(null, headers);

            ResponseEntity<IndexingResult> response = restTemplate.postForEntity(
                    uriBuilder.toUriString(), requestEntity, IndexingResult.class);

            if (response.getBody() != null) {
                System.out.println("[PipelineClient] Indexing response - Chunks indexed: " + response.getBody().getChunksIndexed());
                log.info("Indexing completed for session: {}", sessionId);
                return response.getBody();
            } else {
                throw new PipelineException("Pipeline service returned null response");
            }

        } catch (org.springframework.web.client.HttpClientErrorException e) {
            System.out.println("[PipelineClient] HTTP Error: " + e.getStatusCode() + " - " + e.getResponseBodyAsString());
            log.error("Pipeline service HTTP error: {} - {}", e.getStatusCode(), e.getResponseBodyAsString());
            throw new PipelineException("Pipeline service error: " + e.getResponseBodyAsString(), e);
        } catch (RestClientException e) {
            System.out.println("[PipelineClient] Confirm ERROR: " + e.getMessage());
            log.error("Failed to confirm and index: {}", e.getMessage());
            e.printStackTrace();
            throw new PipelineException("Failed to confirm and index: " + e.getMessage(), e);
        }
    }

    /**
     * Query documents using the pipeline service
     */
    public QueryResult queryDocuments(String queryText, int topK, int rerankTopN) {
        String endpoint = pipelineServiceUrl + "/pipeline/query";

        try {
            UriComponentsBuilder uriBuilder = UriComponentsBuilder.fromHttpUrl(endpoint)
                    .queryParam("query_text", queryText)
                    .queryParam("top_k", topK)
                    .queryParam("rerank_top_n", rerankTopN);

            HttpEntity<Void> requestEntity = new HttpEntity<>(null, HttpHeaders.EMPTY);

            ResponseEntity<QueryResult> response = restTemplate.postForEntity(
                    uriBuilder.toUriString(), requestEntity, QueryResult.class);

            if (response.getBody() != null) {
                log.info("Query completed");
                return response.getBody();
            } else {
                throw new PipelineException("Pipeline service returned null response");
            }

        } catch (RestClientException e) {
            log.error("Failed to query documents: {}", e.getMessage());
            throw new PipelineException("Failed to query documents", e);
        }
    }

    /**
     * Fetch chunk details (including bounding box) from the pipeline service
     */
    public Map<String, Object> getChunkDetails(String chunkId) {
        String endpoint = pipelineServiceUrl + "/pipeline/chunk/" + chunkId;

        try {
            HttpEntity<Void> requestEntity = new HttpEntity<>(null, HttpHeaders.EMPTY);
            ResponseEntity<Map> response = restTemplate.getForEntity(endpoint, Map.class);

            if (response.getBody() != null) {
                log.info("Fetched chunk details for: {}", chunkId);
                return response.getBody();
            } else {
                throw new PipelineException("Pipeline service returned null response");
            }

        } catch (RestClientException e) {
            log.error("Failed to fetch chunk details: {}", e.getMessage());
            throw new PipelineException("Failed to fetch chunk details", e);
        }
    }

    /**
     * Fetch document image from the pipeline service
     */
    public ResponseEntity<?> getDocumentImage(String documentId) {
        String endpoint = pipelineServiceUrl + "/pipeline/document/" + documentId;

        try {
            ResponseEntity<byte[]> response = restTemplate.getForEntity(endpoint, byte[].class);
            
            if (response.getBody() != null) {
                log.info("Fetched document image for: {}", documentId);
                
                // Determine content type from headers or default to image/jpeg
                HttpHeaders headers = new HttpHeaders();
                String contentType = response.getHeaders().getContentType() != null ? 
                    response.getHeaders().getContentType().toString() : "image/jpeg";
                headers.setContentType(MediaType.parseMediaType(contentType));
                
                return new ResponseEntity<>(response.getBody(), headers, HttpStatus.OK);
            } else {
                throw new PipelineException("Pipeline service returned null response");
            }

        } catch (RestClientException e) {
            log.error("Failed to fetch document image: {}", e.getMessage());
            throw new PipelineException("Failed to fetch document image", e);
        }
    }

    @Data
    public static class OCRResult {
        private boolean success;
        @JsonProperty("session_id")
        private String sessionId;
        @JsonProperty("document_id")
        private String documentId;
        @JsonProperty("extracted_text")
        private String extractedText;
        private String message;
    }

    @Data
    public static class IndexingResult {
        private boolean success;
        @JsonProperty("session_id")
        private String sessionId;
        @JsonProperty("document_id")
        private String documentId;
        @JsonProperty("extracted_text")
        private String extractedText;
        @JsonProperty("human_in_loop")
        private boolean humanInLoop;
        @JsonProperty("steps_completed")
        private int stepsCompleted;
        @JsonProperty("chunks_created")
        private int chunksCreated;
        @JsonProperty("chunks_indexed")
        private int chunksIndexed;
        private StorageInfo storage;
        private String message;

        @Data
        public static class StorageInfo {
            private String documentBucket;
            private String chunksBucket;
        }
    }

    @Data
    public static class QueryResult {
        private boolean success;
        private String query;
        private int totalHits;
        private int returnedCount;
        private Object[] results;
        private String message;
    }

    public static class PipelineException extends RuntimeException {
        public PipelineException(String message) {
            super(message);
        }

        public PipelineException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
