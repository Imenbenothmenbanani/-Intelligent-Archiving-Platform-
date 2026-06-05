package com.example.scannerfeature.backend.controller;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

@Data
public class ConfirmRequest {
    @JsonProperty("session_id")
    private String sessionId;
    
    @JsonProperty("corrected_text")
    private String correctedText;
    
    @JsonProperty("max_tokens")
    private int maxTokens = 500;
    
    @JsonProperty("overlap_ratio")
    private double overlapRatio = 0.2;
}
