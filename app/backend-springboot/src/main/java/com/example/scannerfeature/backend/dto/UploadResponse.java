package com.example.scannerfeature.backend.dto;

import java.time.OffsetDateTime;

public record UploadResponse(
        boolean success,
        String storedFileName,
        String contentType,
        long fileSize,
        OffsetDateTime storedAt,
        String scannerId,
        String provider
) {
}
