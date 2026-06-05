package com.example.scannerfeature.backend.dto;

public record BackendHealthResponse(
        String status,
        boolean writable,
        long recentDocumentCount
) {
}
