package com.example.scannerfeature.backend.pipeline.request;

import lombok.Data;

@Data
public class QueryRequest {
    private String queryText;
    private int topK = 50;
    private int rerankTopN = 5;
}
