package com.example.scannerfeature.backend.pipeline.request;

import lombok.Data;

@Data
public class IndexingRequest {
    private String documentId;
    private OCRConfig ocrConfig;
    private ChunkConfig chunkConfig;
}
