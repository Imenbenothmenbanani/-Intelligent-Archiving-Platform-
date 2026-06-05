package com.example.scannerfeature.backend.pipeline.request;

import lombok.Data;

@Data
public class ChunkConfig {
    private int maxTokens = 500;
    private int minTokens = 150;
    private double overlapRatio = 0.2;
}
